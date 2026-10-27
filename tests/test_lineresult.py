"""The line result protocol: the interface every result answers (lineresult.py), the two block
lookups the endpoints use, and the contract on the JSON rows /api/eval sends to the page.

The contract tests pin the shape of a row. If one fails, the shape changed: change
static/rows.js (and whatever else reads the rows) on purpose, then the expected shape here."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from laconic import evaluate, server
from laconic.sheet import block_at, solver_blocks

PLOT = "a = 2\n!plot a*x, x = 0 .. 1\n  title: T\n  grid: off\nb = 3\n"
ROOT = "x = 1\n!root x\n  equation: x^2 = 2\nz = x + 1\n"

COMMON = {"n": int, "end": int, "kind": str, "source": str, "text": str, "latex": str, "latex_rows": list,
          "error": str, "warning": str, "stale": bool, "symbols": dict}
PLOT_KEYS = {"svg", "spec", "moved"}
SOLVER_KEYS = {"kind", "unknowns", "hash", "status", "tainted", "autorun", "method", "timeout",
               "values", "summary", "note", "record"}


@pytest.fixture(autouse=True)
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("LENS_CONFIG_DIR", str(tmp_path))


def rows(text, **kw):
    return server.evaluate(server.Sheet(text=text, **kw))


# ---- the interface ---------------------------------------------------------------------------

def test_a_line_owns_itself_and_a_block_header_owns_its_block():
    r = evaluate(PLOT).results
    assert [(x.n, x.end) for x in r] == [(1, 1), (2, 4), (3, 3), (4, 4), (5, 5)]
    assert list(r[1].lines) == [2, 3, 4] and r[1].owns(4) and not r[1].owns(5) and not r[0].owns(2)
    assert r[1].block.kind == "plot" and r[1].block.header == 2
    assert [x.block for x in (r[0], r[2], r[4])] == [None, None, None]


def test_a_payload_belongs_to_its_kind_only():
    r = evaluate(PLOT + ROOT).results
    assert [x.n for x in r if x.plot] == [2] and [x.n for x in r if x.solver] == [7]
    assert r[1].plot.spec["title"] == "T" and r[1].plot.svg.startswith("<svg") and not r[1].plot.moved
    assert r[6].solver.status == "none" and not r[6].solver.current


def test_a_block_header_that_fails_still_owns_its_lines_but_has_no_payload():
    r = evaluate("!plot nope(x), x = 0 .. 1\n  grid: off\n!root y\n  equation: y = \n").results
    assert [(x.kind, x.end) for x in (r[0], r[2])] == [("error", 2), ("error", 4)]
    assert r[0].block.kind == "plot" and r[0].plot is None and r[2].block.kind == "solver" and r[2].solver is None


def test_a_view_set_with_the_mouse_shows_as_moved():
    r = evaluate("!plot x, x = 0 .. 1\n  xview: 0.2 .. 0.4\n").results[0]
    assert r.plot.moved


def test_a_run_can_stop_after_a_line():
    ws = evaluate(PLOT + "nope +\n", until=4)
    assert [r.n for r in ws.results] == [1, 2, 3, 4] and ws.block(2).plot


def test_block_at_finds_a_block_by_its_header_only():
    assert block_at(PLOT, 2).plot.spec == evaluate(PLOT).results[1].plot.spec
    assert block_at(PLOT, 1) is None and block_at(PLOT, 3) is None and block_at(PLOT, 99) is None
    assert block_at("!plot nope(x), x = 0 .. 1\n", 1).plot is None    # there, but it does not draw


def test_solver_blocks_are_the_blocks_that_read_with_their_hashes():
    both = ROOT + "y = 0\n!minimize y\n  objective: (y - z)^2\n!root w\n  equation: w = 1\n"
    full = [r.solver.hash for r in evaluate(both).results if r.solver]
    assert [r.n for r in solver_blocks(both)] == [2, 6]          # line 8 has no start value, so it does not read
    assert [r.solver.hash for r in solver_blocks(both)] == full
    assert solver_blocks(PLOT) == []


# ---- the contract: rows as /api/eval sends them -----------------------------------------------

def test_every_row_has_the_common_fields_and_only_its_own_payload():
    text = ("## Head\n# note\n\n!sigfigs 3\n'smoot = 1.7'm\nf(t) = 2*t\nx = f(2)\nx + 1\nnope +\n"
            + PLOT + ROOT)
    out = rows(text)
    json.dumps(out)                           # what the page gets is plain JSON
    assert [r["n"] for r in out] == list(range(1, len(text.splitlines()) + 1))
    for r in out:
        payload = {"plot"} if r["kind"] == "plot" else {"solver"} if r["kind"] == "solver" else set()
        assert set(r) == set(COMMON) | payload, r["kind"]
        assert all(isinstance(r[k], t) for k, t in COMMON.items()), r["kind"]
        assert set(r["symbols"]) == {"defines", "uses"}
    kinds = [r["kind"] for r in out]
    assert kinds == ["heading", "comment", "blank", "command", "unitdef", "funcdef", "assign", "expr", "error",
                     "assign", "plot", "plotopt", "plotopt", "assign", "assign", "solver", "solveropt", "assign"]


def test_a_row_says_the_lines_it_owns():
    out = rows(PLOT)
    assert [(r["n"], r["end"]) for r in out] == [(1, 1), (2, 4), (3, 3), (4, 4), (5, 5)]


def test_latex_rows_break_a_calculation_one_stage_per_row():
    one, many, bare, err = rows("L = 2'm\nM = 3 * L\n3 * L\nnope +")
    assert one["latex_rows"] == [one["latex"]]
    assert many["latex_rows"][0].startswith("M = 3") and many["latex_rows"][1].startswith("= ")
    assert len(many["latex_rows"]) == 3 and " ".join(many["latex_rows"]) == many["latex"]
    assert not bare["latex_rows"][0].startswith("=") and " ".join(bare["latex_rows"]) == bare["latex"]
    assert err["latex_rows"] == []


def test_the_display_parts_of_a_row():
    x, err, cmd = rows("x = 2'm\nnope +\n!sigfigs 3")
    assert x["latex"].startswith("x =") and x["text"] == "x = 2 m" and not x["error"]
    assert err["error"] and not err["latex"] and err["source"] == "nope +"
    assert cmd["text"] and cmd["source"] == "!sigfigs 3"
    g = rows("~g = 1\ng = 2")[1]
    assert g["warning"].startswith("Changes the global ~g")
    both = rows("~g = 1\ng = 2 * 'degC")[1]["warning"]   # the evaluator's notes join the line's own
    assert both.startswith("Changes the global ~g") and "'delta_degC" in both
    three = rows("~i = 1\ni = 2 * 'degC")[1]["warning"].split(". ")   # global, imaginary unit, offset unit
    assert three[0].startswith("Changes the global ~i") and any(t.startswith("i reads like") for t in three)
    assert "'delta_degC" in three[-1]


def test_a_plot_row_carries_its_picture_and_spec():
    p = rows(PLOT)[1]["plot"]
    assert set(p) == PLOT_KEYS and p["svg"].startswith("<svg") and p["moved"] is False
    assert p["spec"]["title"] == "T" and p["spec"]["grid"] is False
    assert all(isinstance(v, (int, float)) or v is None for v in p["spec"]["series"][0]["y"])


def test_a_solver_row_carries_its_state():
    s = rows(ROOT)[1]["solver"]
    assert set(s) == SOLVER_KEYS
    assert s["status"] == "none" and s["unknowns"] == ["x"] and s["record"] is None
    assert [set(v) for v in s["values"]] == [{"name", "lhs", "rhs", "latex"}]


def test_the_latex_view_adds_a_snippet_to_every_row():
    out = rows("x = 2\n\n" + PLOT, view="latex")
    assert all(set(r) - set(COMMON) - {"plot", "solver"} == {"snippet"} for r in out)
    assert out[0]["snippet"] == "x = 2" and out[1]["snippet"] is None and "axis" in out[3]["snippet"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_page_reads_every_row_the_server_sends():
    """static/rows.js over real rows, so a change to the shape that the page would miss fails here."""
    text = "## Head\n\n!sigfigs 3\nx = 2\nnope +\n" + PLOT + ROOT
    script = ("const R = require(process.argv[1]); const rows = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
              "console.log(JSON.stringify(rows.map((r) => { const m = R.model(r, {view: 'latex'});"
              " return m && [m.line, m.end, m.body.type]; })))")
    rows_js = Path(__file__).parents[1] / "laconic" / "static" / "rows.js"
    for view, kinds in (("typeset", ["text", "text", "text", "tex", "error", "tex", "plot", "tex", "tex", "solver", "tex"]),
                        ("latex", ["snippet", "text", "snippet", "snippet", "error", "snippet", "snippet", "snippet",
                                   "snippet", "snippet", "snippet"])):
        r = subprocess.run(["node", "-e", script, str(rows_js)], input=json.dumps(rows(text, view=view)),
                           capture_output=True, text=True, check=True)
        models = [m for m in json.loads(r.stdout) if m]
        assert [m[2] for m in models] == kinds, view
    lines = [(m[0], m[1]) for m in models]
    assert (7, 9) in lines and (12, 13) in lines and not {8, 9, 13} & {a for a, _ in lines}
