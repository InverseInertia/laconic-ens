"""Solver stress run: every case in solver_cases.py through the real worker process, checked against
known answers. Not part of pytest (it takes about a minute). `python tests/stress/run_solver_stress.py [name filter...]`.
WRONG on Nelder-Mead Rosenbrock 10D, Rastrigin, the unbracketed triple root and trust-constr with 40 constraints is
expected: those are local-method limits (see the notes printed beside them)."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from laconic import evaluate, solverjobs
from laconic.blockedit import apply
from laconic.solver import write_result

def main():
    from solver_cases import CASES
    jobs = solverjobs.Jobs(); jobs.warm(); time.sleep(2)
    out = []
    pick = sys.argv[1:] 
    for c in CASES:
        if pick and not any(p.lower() in c["name"].lower() for p in pick): continue
        t0 = time.monotonic()
        ev = evaluate(c["text"]).results
        t_eval = time.monotonic() - t0
        hdr = ev[c["line"] - 1]
        if hdr.kind != "solver":
            print(f"SETUP-ERR {c['name']}: {hdr.error or hdr.kind}", flush=True); out.append((c["name"], "setup", hdr.error)); continue
        job = jobs.start(c["text"], c["line"], "run", [])
        while job.state == "running": time.sleep(0.05)
        wall = time.monotonic() - t0
        o = job.outcome or {}
        rec = o.get("record")
        verdict, note = "?", ""
        if job.state != c["expect"]:
            verdict = "FAIL"; note = f"state {job.state}: {job.error or o.get('message','')}"[:300]
        elif rec:
            try: good, note = c["check"](rec)
            except Exception as e: good, note = False, f"check crashed {e}"
            # stored result must read back as valid
            txt = apply(c["text"], write_result(c["text"], c["line"], rec))
            st = evaluate(txt).results[c["line"] - 1].solver["status"]
            verdict = ("PASS" if good else "WRONG") + ("" if st == "valid" else f" (reload status {st})")
        else:
            verdict = "PASS"; note = job.log[-1][:120]
        nfev = o.get("nfev", "-"); meth = rec["method"] if rec else ""
        print(f"{verdict:5} | {c['name'][:62]:62} | {meth:12} | nfev {str(nfev):>6} | {wall:6.2f}s (sheet eval {t_eval*1000:.0f} ms) | {note}", flush=True)
        out.append((c["name"], verdict, note, nfev, wall))
    jobs.shutdown()
    print(f"{sum(1 for o in out if str(o[1]).startswith('PASS'))} of {len(out)} PASS")

if __name__ == "__main__":
    main()
