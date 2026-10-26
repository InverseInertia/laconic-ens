"""The worker process behind Run, Interrupt and Verify, and the endpoints that drive it. These start
real worker processes, so they take a second or two."""
import time

import pytest

pytest.importorskip("scipy")

from fastapi import HTTPException

from laconic import evaluate, server, solverjobs
from laconic.blockedit import apply, from_json
from laconic.server import SolveEditBody, SolveStartBody, SolveStoreBody
from laconic.solverjobs import Busy, Jobs

ROOT = "x = 1'm\n!root x\n  equation: x^2 = 4'm^2\n"
SLOW = "x = 1'm\n!root x\n  equation: x^2 = 4'm^2\n  timeout: 1\n"


def sleepy_worker(conn):
    """Stands in for a solver stuck inside one call: reports in, then never returns."""
    conn.recv()
    conn.send(("begin", None))
    conn.send(("log", "started"))
    time.sleep(120)


@pytest.fixture()
def pool():
    j = Jobs()
    yield j
    j.shutdown()


@pytest.fixture()
def sleepy():
    j = Jobs(target=sleepy_worker)
    yield j
    j.shutdown()


def wait(j, job, seconds=30):
    end = time.monotonic() + seconds
    while job.state == "running" and time.monotonic() < end:
        time.sleep(0.05)
    return job


def test_a_run_streams_its_log_and_returns_the_record(pool):
    job = wait(pool, pool.start(ROOT, 2, "run", []))
    assert job.state == "done", job.error
    assert job.outcome["ok"] and job.outcome["record"]["values"][0]["mag"] == pytest.approx(2.0)
    assert job.log[0].startswith("!root x") and any(l.startswith("converged") for l in job.log)
    view = job.view(since=2)
    assert view["log"] == job.log[2:] and view["next"] == len(job.log) and view["outcome"]["hash"]


def test_the_worker_stays_up_for_the_next_job(pool):
    first = wait(pool, pool.start(ROOT, 2, "run", []))
    pid = pool._proc.pid
    second = wait(pool, pool.start(ROOT, 2, "run", []))
    assert first.state == second.state == "done" and pool._proc.pid == pid


def test_a_failure_is_a_finished_job_with_the_reason(pool):
    bad = "x = 1\n!root x\n  equation: x^2 = -1\n  maxiter: 3\n"
    job = wait(pool, pool.start(bad, 2, "run", []))
    assert job.state == "failed" and job.error and job.outcome["record"] is None


def test_the_hash_a_job_computes_is_the_one_the_sheet_shows(pool):
    job = wait(pool, pool.start(ROOT, 2, "run", []))
    shown = next(r for r in evaluate(ROOT).results if r.kind == "solver")
    assert job.outcome["hash"] == shown.solver["hash"]


def test_only_one_job_runs_at_a_time(sleepy):
    sleepy.start(ROOT, 2, "run", [])
    with pytest.raises(Busy):
        sleepy.start(ROOT, 2, "run", [])


def test_interrupting_kills_the_worker_even_when_it_is_stuck(sleepy):
    job = sleepy.start(ROOT, 2, "run", [])
    while "started" not in job.log:
        time.sleep(0.05)
    stuck = sleepy._proc
    sleepy.interrupt(job.id)
    assert job.state == "interrupted" and "Nothing was stored" in job.log[-1]
    stuck.join(5)
    assert not stuck.is_alive()
    nxt = sleepy.start(ROOT, 2, "run", [])         # a fresh worker takes the next job
    assert nxt.state == "running" and sleepy._proc is not stuck


def test_a_job_over_its_time_limit_is_stopped(sleepy, monkeypatch):
    # The limit counts from when the worker takes the job; start-up allowance is not added to it.
    monkeypatch.setattr(solverjobs, "STARTUP_SLACK", 100.0)
    job = wait(sleepy, sleepy.start(SLOW, 2, "run", []), seconds=10)
    assert job.state == "timeout" and "1 s limit" in job.log[-1]
    assert job.finished - job.started < 5


def test_a_worker_that_dies_is_reported(sleepy):
    job = sleepy.start(ROOT, 2, "run", [])
    sleepy._proc.kill()
    assert wait(sleepy, job, seconds=10).state == "failed" and "stopped unexpectedly" in job.error


def test_a_line_that_is_not_a_block_is_refused(pool):
    with pytest.raises(Exception, match="not a !root"):
        pool.start(ROOT, 1, "run", [])


# ---- the endpoints -------------------------------------------------------------------------------------
@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("LENS_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(server, "jobs", Jobs())
    yield server
    server.jobs.shutdown()


def run_via_api(api, text, line=2, mode="run"):
    job_id = api.solve_start(SolveStartBody(text=text, line=line, mode=mode))["job"]
    end = time.monotonic() + 30
    while time.monotonic() < end:
        view = api.solve_poll(job_id)
        if view["state"] != "running":
            return view
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def edited(text, out):
    """`text` with an endpoint's edits made."""
    return apply(text, from_json(text, out["edits"]))


def test_run_then_store_writes_the_result_into_the_sheet(api):
    view = run_via_api(api, ROOT)
    assert view["state"] == "done"
    stored = api.solve_store(SolveStoreBody(text=ROOT, record=view["outcome"]["record"]))
    assert stored["ok"] and stored["lines"] == [2]
    assert next(r for r in evaluate(edited(ROOT, stored)).results if r.kind == "solver").solver["status"] == "valid"


def test_a_result_for_inputs_that_changed_meanwhile_is_not_stored(api):
    view = run_via_api(api, ROOT)
    edited = ROOT.replace("4'm^2", "9'm^2")
    out = api.solve_store(SolveStoreBody(text=edited, record=view["outcome"]["record"]))
    assert out["ok"] is False and "inputs changed" in out["error"]


def test_the_result_goes_to_the_block_even_after_lines_were_added_above_it(api):
    view = run_via_api(api, ROOT)
    shifted = "# a new first line\n\n" + ROOT
    out = api.solve_store(SolveStoreBody(text=shifted, record=view["outcome"]["record"]))
    assert out["ok"] and out["lines"] == [4]


def test_verify_through_the_api(api):
    view = run_via_api(api, ROOT)
    text = edited(ROOT, api.solve_store(SolveStoreBody(text=ROOT, record=view["outcome"]["record"])))
    again = run_via_api(api, text, mode="verify")
    assert again["outcome"]["verify"]["same"] is True


def test_busy_and_bad_requests_are_http_errors(api):
    with pytest.raises(HTTPException) as e:
        api.solve_start(SolveStartBody(text=ROOT, line=1))
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        api.solve_start(SolveStartBody(text=ROOT, line=2, mode="sideways"))
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        api.solve_poll("nope")
    assert e.value.status_code == 404
    api.jobs = server.jobs = Jobs(target=sleepy_worker)
    first = api.solve_start(SolveStartBody(text=ROOT, line=2))
    with pytest.raises(HTTPException) as e:
        api.solve_start(SolveStartBody(text=ROOT, line=2))
    assert e.value.status_code == 409
    assert api.solve_interrupt(first["job"])["state"] == "interrupted"


def test_autorun_is_toggled_in_the_text(api):
    on = api.solve_edit(SolveEditBody(text=ROOT, line=2, autorun=True))
    assert on["ok"] and "  autorun: on\n" in edited(ROOT, on)
    assert edited(edited(ROOT, on), api.solve_edit(SolveEditBody(text=edited(ROOT, on), line=2, autorun=False))) == ROOT
    assert api.solve_edit(SolveEditBody(text=ROOT, line=1, autorun=True))["ok"] is False
