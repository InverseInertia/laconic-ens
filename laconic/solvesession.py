"""The solve session: from "this block needs solving" to "its answer is in the text".

Evaluating a sheet never runs a solver (see solver.py); everything that does goes through here,
so the page and the command line follow one set of rules:

    pending(text, units)                the solver blocks that are not up to date, top to bottom
    solve(text, line, units, log, mode) run ("run") or re-check ("verify") one block in this process
    store(text, record, units)          (edits, lines): the record written into every block whose
                                        inputs hash to the record's hash
    solve_all(text, units, ...)         solve each pending block and store its answer, until none is left

Running is behind a seam. A runner is any callable `runner(text, line, units, log, mode)` that
returns the outcome `solve` returns: `solve` itself, or `solverjobs.Jobs.run`, which runs it in a
worker process that a timeout or an interrupt can stop. The page drives the worker through its
jobs (start, poll, interrupt) and then asks for `store`, since the text may change meanwhile.

An outcome is {"ok", "message", "record", "hash", ...}; `record` is what `store` writes, and a
verify adds {"verify": {"same", "diff", "note"}}."""
import sys

from . import solver
from .sheet import describe, evaluator_at, solver_blocks
from .sheettext import scan
from .solver import SolverError


def block(text, line):
    """The parsed solver block whose header is on `line`. Raises SolverError for any other line."""
    b = scan(text).block(line)
    if b is None or b.kind != "solver":
        raise SolverError(f"Line {line} is not a !root, !minimize or !maximize line")
    return solver.parse_block(b)


def pending(text, units=()):
    """The results of the solver blocks whose stored result is missing or out of date."""
    return [r for r in solver_blocks(text, units) if r.solver.status != "valid"]


def solve(text, line, units=(), log=print, mode="run"):
    """Solve the block on `line` in this process, from the values the lines above give it (so an
    upstream block's stored answer is used as it is on screen). The text is not changed."""
    try:
        b = block(text, line)
    except SolverError as e:
        return _failed(str(e))
    if b.problem:
        return _failed(b.problem)
    ev = evaluator_at(text, line, units)
    try:
        prob = solver.prepare(b, ev, describe)
        h = prob.digest()
        prob.probe()
    except Exception as e:
        return _failed(describe(e))
    out = prob.solve(log)
    out["hash"] = h
    if mode == "verify" and out["record"] is not None:
        out["verify"] = _verify(b.stored, h, out["record"])
    return out


def _failed(message):
    return {"ok": False, "message": message, "record": None}


def _verify(stored, h, record):
    """How a fresh answer compares with the stored one: only a current stored result is compared."""
    if stored is None or stored.get("hash") != h:
        return {"same": None, "diff": None, "note": "There is no current stored result to compare with. Run it first."}
    same, diff = solver.compare(stored, record)
    return {"same": same, "diff": diff, "note": ""}


def store(text, record, units=()):
    """(edits against `text`, header lines): `record` written into every block whose inputs hash
    to its hash. Blocks with the same inputs have the same answer, so all of them get it. None
    matches when the text changed while the solver ran; then nothing is written."""
    h = record.get("hash")
    lines = [r.n for r in solver_blocks(text, units) if r.solver.hash == h]
    return [e for n in lines for e in solver.write_result(text, n, record)], lines


def solve_all(text, units=(), runner=solve, log=None, saved=lambda text: None):
    """Solve the blocks that are not up to date, top to bottom (a later block may read an earlier
    one's answer), storing each answer as it arrives and passing the new text to `saved`. A block
    that fails is not tried again. Returns the final text. `log` gets progress and the runner's log."""
    from .blockedit import apply
    log = log or (lambda m: print(m, file=sys.stderr))
    tried = set()
    while True:
        todo = [r for r in pending(text, units) if r.solver.hash not in tried]
        if not todo:
            return text
        r = todo[0]
        tried.add(r.solver.hash)
        log(f"{r.n:>3}  solving {r.source.strip()}")
        out = runner(text, r.n, units, lambda m: log("       " + m), "run")
        if not out["ok"]:
            log(f"{r.n:>3}  FAILED  {out['message']}")
            continue
        edits, _ = store(text, out["record"], units)
        text = apply(text, edits)
        saved(text)
