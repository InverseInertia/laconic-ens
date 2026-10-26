"""Solver blocks: `!root`, `!minimize` and `!maximize`, with the indented option lines under them.

    x = 1'm                          starting values come from ordinary variables above
    y = 1'm
    !root x, y                       find x and y that make every equation hold
      equation: x^2 + y^2 = 4'm^2
      equation: x = y

    !minimize d                      or !maximize
      objective: cost(d)
      constraint: d >= 0.5'm         <=, >= or =
      bounds d: 0'm .. 3'm
      method: SLSQP

The numerics are scipy's (`scipy.optimize.root`, `brentq`, `minimize`), run on plain floats in the
unit each unknown was started in. Evaluating a sheet never runs a solver, since that can be slow:
it hashes everything the solver reads and compares that with the `#@ result` line stored inside
the block. Same hash, the stored answer is current; different, it is out of date. Running is done
on request (see solverjobs.py) and the answer is written back into the block as a result line, so
the worksheet file alone carries it."""
import hashlib
import json
import math
import time
import warnings
from dataclasses import dataclass, field, fields, is_dataclass

import numpy as np

from .blockedit import BlockEditor
from .nodes import BinOp, Call, Name, UnitLit
from .parser import ParseError, parse_expr
from .sheettext import is_name

KINDS = ("root", "minimize", "maximize")
ROOT_METHODS = ("hybr", "lm", "broyden1", "broyden2", "krylov", "brentq")
MIN_METHODS = ("BFGS", "Nelder-Mead", "Powell", "L-BFGS-B", "TNC", "SLSQP", "trust-constr", "COBYLA")
WITH_BOUNDS = ("Nelder-Mead", "Powell", "L-BFGS-B", "TNC", "SLSQP", "trust-constr", "COBYLA")
WITH_CONSTRAINTS = ("SLSQP", "trust-constr", "COBYLA")
KEYS = {"root": ("equation", "bounds", "method", "tol", "maxiter", "timeout", "autorun"),
        "minimize": ("objective", "constraint", "bounds", "method", "tol", "maxiter", "timeout", "autorun"),
        "maximize": ("objective", "constraint", "bounds", "method", "tol", "maxiter", "timeout", "autorun")}
# What the editor shows next to each option and method in its suggestions (see vocab.py).
KEY_NOTES = {
    "equation": "lhs = rhs, or one expression that is zero",
    "objective": "the expression to minimize or maximize",
    "constraint": "lhs <= rhs, >= or =",
    "bounds": "low .. high on an unknown; either end may be auto",
    "method": "which scipy solver to use",
    "tol": "convergence tolerance passed to scipy",
    "maxiter": "iteration limit passed to scipy",
    "timeout": "seconds before a run is killed (default 300)",
    "autorun": "on: solve again after the inputs change",
}
METHOD_NOTES = {
    "hybr": "Powell hybrid (MINPACK). Default",
    "lm": "Levenberg-Marquardt; more equations than unknowns allowed (least squares)",
    "broyden1": "Broyden's good method; large systems, no Jacobian",
    "broyden2": "Broyden's bad method; large systems, no Jacobian",
    "krylov": "Newton-Krylov; large systems",
    "brentq": "one unknown bracketed by bounds; default when the bounds bracket it",
    "BFGS": "quasi-Newton. Default without bounds or constraints",
    "Nelder-Mead": "simplex, no gradients; noisy or kinked objectives; bounds",
    "Powell": "direction set, no gradients; bounds",
    "L-BFGS-B": "quasi-Newton with bounds. Default with bounds; many unknowns",
    "TNC": "truncated Newton; bounds",
    "SLSQP": "bounds and constraints. Default with constraints",
    "trust-constr": "interior point; bounds and constraints, many unknowns",
    "COBYLA": "no gradients; bounds and <= / >= constraints",
}
NOT_PARAMETERS = ("timeout", "autorun")   # how a run is supervised, not what it computes
DEFAULT_TIMEOUT = 300.0
RECORD_VERSION = 1
LOG_TRACE_LINES = 120                      # evaluations written to the log before it goes quiet



class SolverError(Exception):
    pass


class StopSolve(Exception):
    """Raised inside a sheet run once the requested block has been solved, to skip the rest."""


# ---- parsing a block --------------------------------------------------------------------------
@dataclass
class Rel:
    line: int
    src: str
    op: str          # "=", "<=", ">=" (equations: "=")
    node: object     # BinOp: the quantity that is zero (equation, equality) or non-negative (inequality)


@dataclass
class Block:
    kind: str
    line: int
    end: int
    unknowns: list = field(default_factory=list)
    equations: list = field(default_factory=list)
    objective: tuple = None                    # (line, node)
    constraints: list = field(default_factory=list)
    bounds: list = field(default_factory=list)  # (line, name or None, low node or None, high node or None)
    method: str = None
    tol: float = None
    maxiter: int = None
    timeout: float = DEFAULT_TIMEOUT
    autorun: bool = False
    canon: list = field(default_factory=list)  # the lines that decide the answer, whitespace-normalised
    errors: dict = field(default_factory=dict)  # option line number -> message
    problem: str = ""                           # what is wrong with the block as a whole
    stored: dict = None                         # the `#@ result` record, if one is readable
    stored_note: str = ""                       # why a result line was ignored
    result_lines: list = field(default_factory=list)

    def nodes(self):
        out = [r.node for r in self.equations + self.constraints]
        if self.objective:
            out.append(self.objective[1])
        for _, _, lo, hi in self.bounds:
            out += [n for n in (lo, hi) if n is not None]
        return out


def split_relation(src):
    """`a <= b` -> ("a", "<=", "b"); no relation -> (src, None, None). `=` and `==` are the same."""
    depth, quoted, i = 0, False, 0
    found = []
    while i < len(src):
        c = src[i]
        if c == '"':
            quoted = not quoted
        elif not quoted:
            if c in "([":
                depth += 1
            elif c in ")]":
                depth -= 1
            elif depth == 0:
                two = src[i:i + 2]
                if two in ("<=", ">=", "=="):
                    found.append((i, two, 2))
                    i += 2
                    continue
                if c == "=":
                    found.append((i, "=", 1))
        i += 1
    if not found:
        return src.strip(), None, None
    if len(found) > 1:
        raise SolverError("Only one of =, <= or >= is allowed in a line")
    pos, op, width = found[0]
    lhs, rhs = src[:pos].strip(), src[pos + width:].strip()
    if not lhs or not rhs:
        raise SolverError(f"Both sides of {op} need an expression")
    return lhs, "=" if op == "==" else op, rhs


def _expr(src, what):
    if not src.strip():
        raise SolverError(f"{what} needs an expression")
    try:
        return parse_expr(src)
    except ParseError as e:
        raise SolverError(str(e)) from None


def _relation(n, src, allowed, what, need_relation=False):
    lhs, op, rhs = split_relation(src)
    if op is None:
        if need_relation:
            raise SolverError(f"A {what} needs <=, >= or =, e.g. `{what}: x + y >= 1'm`")
        return Rel(n, src, "=", _expr(lhs, what))                   # a bare expression is "= 0"
    if op not in allowed:
        raise SolverError("An equation uses = here; inequalities belong to a constraint in !minimize or !maximize")
    a, b = _expr(lhs, what), _expr(rhs, what)
    return Rel(n, src, op, BinOp("-", b, a) if op == "<=" else BinOp("-", a, b))


def _bounds(value):
    parts = value.split("..")
    if len(parts) != 2:
        raise SolverError("Bounds read `low .. high`; either end can be `auto`")
    ends = [None if p.strip().lower() in ("", "auto") else _expr(p, "A bound") for p in parts]
    if ends == [None, None]:
        raise SolverError("Give at least one bound, or remove the line")
    return ends


def _choice(value, options, what):
    low = {o.lower(): o for o in options}
    if value.lower() not in low:
        raise SolverError(f"{what} is one of: " + ", ".join(options))
    return low[value.lower()]


def _number(value, key, whole=False, lo=0.0):
    try:
        n = float(value)
    except ValueError:
        raise SolverError(f"{key} needs a number") from None
    if not math.isfinite(n) or n <= lo or (whole and n != int(n)):
        raise SolverError(f"{key} needs a " + ("whole " if whole else "") + f"number above {lo:g}")
    return int(n) if whole else n


def parse_block(block):
    """The solver block `block` (a sheettext.Block). Problems with single option lines go in
    `errors`, keyed by line number; a problem with the whole block is `problem`."""
    b = Block(kind=block.command, line=block.header, end=block.end)
    names = [s.strip() for s in _split_top(block.args)] if block.args else []
    if not names or not all(is_name(n) for n in names):
        b.problem = f"!{b.kind} reads `!{b.kind} x, y`: the variables to solve for, each started above the block"
        return b
    b.unknowns = names
    seen = set()
    for line in block.members:
        n, raw, o = line.n, line.text, line.option
        if line.result is not None:
            b.result_lines.append(n)
            try:
                rec = json.loads(line.result)
                if not isinstance(rec, dict) or not isinstance(rec.get("hash"), str):
                    raise ValueError
                b.stored, b.stored_note = rec, ""
            except ValueError:
                b.stored, b.stored_note = None, f"the result on line {n} could not be read"
            continue
        if raw.strip().startswith("#"):
            continue
        try:
            if not o:
                raise SolverError("Option lines read `key: value`")
            key, target, value = o.key, o.arg, o.value
            if key not in KEYS[b.kind]:
                raise SolverError(f"Unknown option '{key}'. Under !{b.kind}: " + ", ".join(KEYS[b.kind]))
            if target and key != "bounds":
                raise SolverError(f"{key} does not take a name before the colon")
            if not value:
                raise SolverError(f"{key} needs a value")
            _apply_option(b, n, key, target, value, seen)
            if key not in NOT_PARAMETERS:
                b.canon.append(" ".join(raw.split()))
        except SolverError as e:
            b.errors[n] = str(e)
    if b.errors:
        count = len(b.errors)
        b.problem = f"{count} option line{'s' * (count != 1)} below need{'s' * (count == 1)} fixing"
    elif b.kind == "root" and not b.equations:
        b.problem = "!root needs at least one `equation:` line"
    elif b.kind != "root" and not b.objective:
        b.problem = f"!{b.kind} needs an `objective:` line"
    return b


def _apply_option(b, n, key, target, value, seen):
    if key in ("objective", "method", "tol", "maxiter", "timeout", "autorun") and key in seen:
        raise SolverError(f"{key} is given twice")
    seen.add(key)
    if key == "equation":
        b.equations.append(_relation(n, value, ("=",), "equation"))
    elif key == "objective":
        lhs, op, _ = split_relation(value)
        if op:
            raise SolverError("An objective is one expression, with no =, <= or >=")
        b.objective = (n, _expr(lhs, "An objective"))
    elif key == "constraint":
        b.constraints.append(_relation(n, value, ("=", "<=", ">="), "constraint", need_relation=True))
    elif key == "bounds":
        lo, hi = _bounds(value)
        b.bounds.append((n, target, lo, hi))
    elif key == "method":
        b.method = _choice(value, ROOT_METHODS if b.kind == "root" else MIN_METHODS, "method")
    elif key == "tol":
        b.tol = _number(value, "tol")
    elif key == "maxiter":
        b.maxiter = _number(value, "maxiter", whole=True)
    elif key == "timeout":
        b.timeout = _number(value, "timeout")
    elif key == "autorun":
        w = value.lower()
        if w not in ("on", "off"):
            raise SolverError("autorun is on or off")
        b.autorun = w == "on"


def _split_top(s):
    out, depth, cur = [], 0, []
    for c in s:
        depth += (c in "([") - (c in ")]")
        if c == "," and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    out.append("".join(cur))
    return out


# ---- what a block reads: dependencies, the hash, out-of-date tracking ------------------------
def refs(node):
    """(variable names, called function names, unit names) used anywhere under `node`."""
    names, calls, units = set(), set(), set()
    todo = [node]
    while todo:
        n = todo.pop()
        if isinstance(n, Name):
            names.add(n.name)
        elif isinstance(n, UnitLit):
            units.add(n.unit)
        elif isinstance(n, Call):
            calls.add(n.func)
            todo.extend(n.args)
        elif is_dataclass(n) and not isinstance(n, type):
            todo.extend(getattr(n, f.name) for f in fields(n))
        elif isinstance(n, (tuple, list)):
            todo.extend(n)
    return names, calls, units


def _reach(ev, nodes, local=()):
    """Walk `nodes` and the bodies of the user functions they call. Yields (kind, key, extra)."""
    seen, todo = set(), [(n, frozenset(local)) for n in nodes]
    while todo:
        node, loc = todo.pop()
        names, calls, units = refs(node)
        for u in units:
            yield "unit", u, None
        for nm in names:
            if nm not in loc:
                yield "var", ev.vkey(nm), None
        for fn in calls:
            fk = ev.fkey(fn)
            if fk in ev.funcs and fk not in seen:
                seen.add(fk)
                params, body = ev.funcs[fk]
                yield "func", fk, (params, body)
                todo.append((body, frozenset(params)))


def tainted(ev, nodes, local=()):
    """True if evaluating `nodes` reads a value that came from an out-of-date solver."""
    return bool(ev.stale) and any(k == "var" and key in ev.stale for k, key, _ in _reach(ev, nodes, local))


def _qdigest(q):
    """A quantity as hashable text. Values are cut to 12 significant digits, so a last-bit
    difference in a library (another machine, another BLAS) does not make a result look stale.
    Done with numpy, since a matrix input can have a million entries. A complex input is
    digested as its real parts followed by its imaginary parts."""
    mag = np.asarray(q.magnitude)
    flat = np.concatenate([mag.real.ravel(), mag.imag.ravel()]) if np.iscomplexobj(mag) else mag.astype(float).ravel()
    with np.errstate(divide="ignore", invalid="ignore"):
        exp = np.where(flat == 0, 0.0, np.floor(np.log10(np.abs(flat))))
        mant = np.round(flat / 10.0 ** (exp - 11))
    blob = mant.astype(np.int64).tobytes() + exp.astype(np.int16).tobytes()
    return [str(q.units), list(mag.shape), hashlib.sha256(blob).hexdigest()]


def digest(block, ev, unknowns):
    """A short hash of everything the solver reads: the block's own lines, the starting values,
    every variable and function they reach, the units they use. The stored result is current
    exactly when its hash equals this."""
    own = {u.key for u in unknowns}
    deps, funcs, units = {}, {}, {}
    for kind, key, extra in _reach(ev, block.nodes()):
        if kind == "var" and key in ev.vars and key not in own:
            deps[key] = _qdigest(ev.vars[key])
        elif kind == "func":
            funcs[key] = [list(extra[0]), repr(extra[1])]
        elif kind == "unit":
            try:
                units[key] = str(ev.Q(1, ev.ureg.parse_units(key)).to_base_units())
            except Exception:
                units[key] = key
    parts = {"v": RECORD_VERSION, "kind": block.kind, "unknowns": block.unknowns, "angle": ev.mode.angle,
             "lines": block.canon, "start": [_qdigest(ev.vars[u.key]) for u in unknowns],
             "vars": deps, "funcs": funcs, "units": units}
    blob = json.dumps(parts, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


# ---- the problem: unknowns, evaluation, the scipy calls ------------------------------------
@dataclass
class Unknown:
    name: str
    key: str
    units: object
    shape: tuple
    size: int
    off: int
    start: object   # the starting quantity


@dataclass
class Eval:
    """One expression evaluated repeatedly, with the unit its values were first seen in."""
    rel: Rel
    units: object = None
    size: int = 0


class Problem:
    def __init__(self, block, ev, describe):
        self.block, self.ev, self.describe = block, ev, describe
        self.kind = block.kind
        self.unknowns, self.eqs, self.cons, self.obj = [], [], [], None
        self.nfev = 0
        self._quiet = False
        self._probed = False
        self.log = lambda msg: None
        self._resolve()
        self._bounds()
        self.method = self._choose_method()
        b = block
        self.eqs = [Eval(r) for r in b.equations]
        self.cons = [Eval(r) for r in b.constraints]
        if b.objective:
            self.obj = Eval(Rel(b.objective[0], "objective", "", b.objective[1]))

    # -- setup
    def _resolve(self):
        ev, off, seen = self.ev, 0, set()
        for name in self.block.unknowns:
            key = ev.vkey(name)
            if key in seen:
                raise SolverError(f"'{name}' is listed twice")
            seen.add(key)
            if key not in ev.vars:
                raise SolverError(f"'{name}' needs a starting value: define it above the block, e.g. {name} = 1")
            q = ev.vars[key]
            if np.iscomplexobj(q.magnitude):
                raise SolverError(f"The starting value of '{name}' is complex; the solver works with real numbers")
            mag = np.asarray(q.magnitude, dtype=float)
            if not np.all(np.isfinite(mag)):
                raise SolverError(f"The starting value of '{name}' is not finite")
            self.unknowns.append(Unknown(name, key, q.units, mag.shape, mag.size, off, q))
            off += mag.size
        self.n = off
        self.x0 = np.concatenate([np.asarray(u.start.magnitude, dtype=float).ravel() for u in self.unknowns])

    def _bounds(self):
        lo, hi = np.full(self.n, -np.inf), np.full(self.n, np.inf)
        by_key = {u.key: u for u in self.unknowns}
        for line, target, lo_node, hi_node in self.block.bounds:
            if target is None and len(self.unknowns) == 1:
                target = self.unknowns[0].name
            if target is None:
                raise SolverError(f"line {line}: name the variable, `bounds x: low .. high`")
            u = by_key.get(self.ev.vkey(target))
            if u is None:
                raise SolverError(f"line {line}: '{target}' is not one of the unknowns")
            for node, arr, label in ((lo_node, lo, "low"), (hi_node, hi, "high")):
                if node is None:
                    continue
                try:
                    q = self.ev.eval(node).to(u.units)
                    if np.iscomplexobj(q.magnitude):
                        raise SolverError("a bound must be real")
                    mag = np.broadcast_to(np.asarray(q.magnitude, dtype=float), u.shape).ravel()
                except Exception as e:
                    raise SolverError(f"line {line}: {label} bound: {self.describe(e)}") from None
                arr[u.off:u.off + u.size] = mag
        if np.any(lo > hi):
            raise SolverError("A lower bound is above its upper bound")
        self.lo, self.hi = lo, hi
        self.bounded = bool(np.isfinite(lo).any() or np.isfinite(hi).any())

    def _choose_method(self):
        b = self.block
        if self.kind == "root":
            scalar = self.n == 1
            if self.bounded and not scalar:
                raise SolverError("Bounds on a !root bracket a single unknown; use !minimize for several")
            if b.method == "brentq" and not (scalar and self.bounded):
                raise SolverError("brentq needs one unknown and a `bounds` line that brackets the root")
            if b.method:
                return b.method
            return "brentq" if scalar and self.bounded else "hybr"
        m = b.method
        if m is None:
            m = "SLSQP" if (b.constraints) else "L-BFGS-B" if self.bounded else "BFGS"
        if self.bounded and m not in WITH_BOUNDS:
            raise SolverError(f"{m} does not take bounds. Use one of: " + ", ".join(WITH_BOUNDS))
        if b.constraints and m not in WITH_CONSTRAINTS:
            raise SolverError(f"{m} does not take constraints. Use one of: " + ", ".join(WITH_CONSTRAINTS))
        if m == "COBYLA" and any(c.op == "=" for c in b.constraints):
            raise SolverError("COBYLA takes only <= and >= constraints")
        return m

    def probe(self):
        """Evaluate everything once at the starting values: catches undefined names, unit
        mismatches and a wrong number of equations now, while the sheet is being edited, and
        raises the evaluator's notes (an offset unit after `*`) for the block's header."""
        if self._probed:
            return
        self._probed = True
        try:
            self.set_x(self.x0)
            for e in self.eqs + self.cons:
                self._vec(e, self.x0)
            if self.obj is not None and len(self._vec(self.obj, self.x0)) != 1:
                raise SolverError(f"line {self.obj.rel.line}: the objective must be a single number, not a matrix")
        finally:
            self.set_x(self.x0)
        if self.kind == "root":
            m = sum(e.size for e in self.eqs)
            if self.method == "brentq" and m != 1:
                raise SolverError("brentq solves one equation in one unknown")
            if self.method == "lm":
                if m < self.n:
                    raise SolverError(f"{m} equation{'s' * (m != 1)} for {self.n} unknowns: lm needs at least as many equations as unknowns")
            elif m != self.n:
                raise SolverError(f"{m} equation{'s' * (m != 1)} for {self.n} unknown{'s' * (self.n != 1)}: "
                                  "a root needs as many equations as unknowns (counting every entry of a matrix)")

    # -- evaluation
    def set_x(self, x):
        for u in self.unknowns:
            seg = np.asarray(x[u.off:u.off + u.size], dtype=float)
            self.ev.vars[u.key] = self.ev.Q(float(seg[0]) if u.shape == () else seg.reshape(u.shape), u.units)

    def where(self, x):
        parts = []
        for u in self.unknowns:
            vals = np.asarray(x[u.off:u.off + u.size])
            shown = ", ".join(f"{v:.6g}" for v in vals[:4]) + (", ..." if vals.size > 4 else "")
            parts.append(f"{u.name} = " + (shown if u.size == 1 else f"[{shown}]") + f" {u.units:~P}".rstrip())
        return "; ".join(parts)

    def _vec(self, e, x):
        try:
            q = self.ev.eval(e.rel.node)
            if e.units is None:
                e.units = q.units
            elif q.units != e.units:
                q = q.to(e.units)
            if np.iscomplexobj(q.magnitude):
                raise SolverError(f"line {e.rel.line} is complex at {self.where(x)}; the solver works with "
                                  "real numbers. Solve for re() and im() separately, or use abs()")
            v = np.asarray(q.magnitude, dtype=float).ravel()
        except SolverError:
            raise
        except Exception as ex:
            raise SolverError(f"line {e.rel.line}: {self.describe(ex)}") from None
        e.size = v.size
        if not np.all(np.isfinite(v)):
            raise SolverError(f"line {e.rel.line} is not finite at {self.where(x)} "
                              "(division by zero or outside a function's domain). Start nearer a solution or add bounds")
        return v

    def _trace(self, what, value, x):
        self.nfev += 1
        if self._quiet:
            return
        if self.nfev <= LOG_TRACE_LINES * 0.4 or self.nfev % 10 == 0:
            if self.nfev > LOG_TRACE_LINES:
                self._quiet = True
                self.log("  ... (further evaluations not listed)")
                return
            self.log(f"  eval {self.nfev:>4}  {what} = {value:.6e}   at {self.where(x)}")

    def residual(self, x):
        self.set_x(x)
        f = np.concatenate([self._vec(e, x) for e in self.eqs])
        self._trace("max|F|", float(np.max(np.abs(f))) if f.size else 0.0, x)
        return f

    def objective(self, x):
        self.set_x(x)
        v = float(self._vec(self.obj, x)[0])
        self._trace("objective", v, x)
        return v

    def constraint_fun(self, e):
        def g(x):
            self.set_x(x)
            return self._vec(e, x)
        return g

    def violation(self, x):
        worst = 0.0
        for e in self.cons:
            g = self.constraint_fun(e)(x)
            worst = max(worst, float(np.max(np.abs(g))) if e.rel.op == "=" else float(max(0.0, -np.min(g))))
        return worst

    # -- running
    def solve(self, log):
        """Run the solver. Returns {"ok", "message", "record", "resid", "nfev", "seconds"}.
        The starting values are put back afterwards."""
        self.probe()
        self.log, self.nfev, self._quiet = log, 0, False
        t0 = time.monotonic()
        b = self.block
        log(f"!{self.kind} {', '.join(b.unknowns)}   method {self.method}"
            + (f", tol {b.tol:g}" if b.tol else "") + (f", maxiter {b.maxiter}" if b.maxiter else ""))
        log(f"{self.n} unknown{'s' * (self.n != 1)}, " + (
            f"{sum(e.size for e in self.eqs)} equation entries" if self.kind == "root" else
            f"{len(self.cons)} constraint{'s' * (len(self.cons) != 1)}"
            + (", bounded" if self.bounded else "")))
        log("start:  " + self.where(self.x0))
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                x, ok, message = self._run()
            for w in {str(w.message) for w in caught}:
                log(f"warning: {w}")
        except SolverError as e:
            log(f"error: {e}")
            return {"ok": False, "message": str(e), "record": None, "nfev": self.nfev,
                    "seconds": time.monotonic() - t0}
        finally:
            self.set_x(self.x0)
        seconds = time.monotonic() - t0
        resid, obj = self._summary(x)
        log(("converged: " if ok else "NOT converged: ") + message)
        log("result: " + self.where(x))
        if obj is not None:
            log(f"{'minimum' if self.kind == 'minimize' else 'maximum'} objective = {obj:.9g} {self.obj.units:~P}".rstrip())
        if self.kind == "root" or self.cons:
            log(f"{'max |residual|' if self.kind == 'root' else 'constraint violation'} = {resid:.3e}")
        log(f"{self.nfev} evaluations, {seconds:.3f} s")
        if not ok:
            return {"ok": False, "message": message, "record": None, "nfev": self.nfev, "seconds": seconds}
        return {"ok": True, "message": message, "nfev": self.nfev, "seconds": seconds,
                "record": self.record(x, obj, resid, message)}

    def _summary(self, x):
        self.set_x(x)
        try:
            if self.kind == "root":
                return float(np.max(np.abs(self.residual(x)))), None
            return self.violation(x), float(self._vec(self.obj, x)[0])
        finally:
            self.set_x(self.x0)

    def _run(self):
        from scipy import optimize
        b, x0 = self.block, self.x0
        if self.kind == "root":
            if self.method == "brentq":
                return self._brentq(optimize)
            opts = {}
            if b.maxiter:
                opts["maxfev" if self.method == "hybr" else "maxiter"] = b.maxiter
            r = optimize.root(self.residual, x0, method=self.method, tol=b.tol, options=opts or None)
            return np.atleast_1d(r.x), bool(r.success), str(r.message).strip()
        sign = -1.0 if self.kind == "maximize" else 1.0
        kw = {}
        if self.bounded:
            kw["bounds"] = optimize.Bounds(self.lo, self.hi)
        if self.cons:
            kw["constraints"] = [{"type": "eq" if e.rel.op == "=" else "ineq", "fun": self.constraint_fun(e)}
                                 for e in self.cons]
        opts = {}
        if b.maxiter:
            opts["maxiter"] = b.maxiter
        if self.method in ("L-BFGS-B", "TNC"):
            # These cap function evaluations too, and every finite-difference gradient costs n + 1 of
            # them; scipy's defaults (15000, and 10 n for TNC) stop large problems long before they converge.
            opts["maxfun"] = max(15000, (b.maxiter or 500) * (self.n + 1))
        x_in = np.clip(x0, self.lo, self.hi) if self.bounded else x0
        r = optimize.minimize(lambda x: sign * self.objective(x), x_in, method=self.method, tol=b.tol,
                              options=opts or None, **kw)
        x = np.atleast_1d(r.x)
        ok, message = bool(r.success), str(r.message).strip()
        if ok and self.cons:
            v = self.violation(x)
            if v > 1e-4 * max(1.0, float(np.max(np.abs(x0)))):
                ok, message = False, f"the solver reported success but the constraints are violated by {v:.3g}"
        return x, ok, message

    def _brentq(self, optimize):
        lo, hi = float(self.lo[0]), float(self.hi[0])
        if not (math.isfinite(lo) and math.isfinite(hi)):
            raise SolverError("brentq needs both ends of the bracket: `bounds x: low .. high`")
        f = lambda x: float(self.residual(np.array([x]))[0])
        flo, fhi = f(lo), f(hi)
        self.log(f"bracket: f({lo:.6g}) = {flo:.4e}, f({hi:.6g}) = {fhi:.4e}")
        if flo * fhi > 0:
            raise SolverError(f"The equation has the same sign at both ends of the bounds "
                              f"({flo:.4g} and {fhi:.4g}), so the bracket may hold no root. Widen the bounds or move them")
        b = self.block
        # One evaluation per step, so a generous cap costs little; scipy's 100 is too few for a
        # flat (multiple) root, where Brent falls back to slow steps.
        kw = {"maxiter": b.maxiter or 1000}
        if b.tol:
            kw["xtol"] = b.tol
        x, r = optimize.brentq(f, lo, hi, full_output=True, disp=False, **kw)
        if r.converged:
            return np.array([x]), True, "bracketed root found"
        return np.array([x]), False, (f"the bracket did not close within {kw['maxiter']} steps (last x = {x:.6g}). "
                                      "Raise `maxiter:` or loosen `tol:`")

    # -- results
    def record(self, x, obj, resid, message):
        import scipy
        values = []
        for u in self.unknowns:
            seg = np.asarray(x[u.off:u.off + u.size], dtype=float)
            values.append({"mag": float(seg[0]) if u.shape == () else seg.reshape(u.shape).tolist(),
                           "unit": str(u.units)})
        rec = {"hash": digest(self.block, self.ev, self.unknowns), "kind": self.kind, "method": self.method,
               "scipy": scipy.__version__, "values": values, "nfev": self.nfev, "message": message}
        if self.kind == "root" or self.cons:
            rec["resid"] = float(f"{resid:.3g}")
        if obj is not None:
            rec["obj"] = {"mag": obj, "unit": str(self.obj.units)}
        return rec

    def digest(self):
        return digest(self.block, self.ev, self.unknowns)

    def stored_quantities(self, record):
        """The stored values as quantities, or None if they no longer fit these unknowns."""
        vals = record.get("values")
        if not isinstance(vals, list) or len(vals) != len(self.unknowns):
            return None
        out = []
        for u, v in zip(self.unknowns, vals):
            try:
                units = self.ev.ureg.parse_units(v["unit"])
                mag = np.asarray(v["mag"], dtype=float)
                if mag.shape != u.shape or not np.all(np.isfinite(mag)):
                    return None
                q = self.ev.Q(float(mag) if u.shape == () else mag, units)
                if q.dimensionality != u.start.dimensionality:
                    return None
            except Exception:
                return None
            out.append(q)
        return out

    def stored_objective(self, record):
        o = record.get("obj")
        if self.obj is None or not isinstance(o, dict):
            return None
        try:
            return self.ev.Q(float(o["mag"]), self.ev.ureg.parse_units(o["unit"]))
        except Exception:
            return None


def prepare(block, ev, describe):
    """The block's Problem, or a SolverError saying what is wrong with it."""
    try:
        return Problem(block, ev, describe)
    except SolverError:
        raise
    except Exception as e:
        raise SolverError(describe(e)) from None


def compare(old, new):
    """How far a freshly computed record is from a stored one: (same, largest relative difference)."""
    def flat(rec):
        out = []
        for v in rec.get("values", []):
            out += list(np.asarray(v["mag"], dtype=float).ravel())
        if "obj" in rec:
            out.append(float(rec["obj"]["mag"]))
        return np.array(out)
    a, b = flat(old), flat(new)
    if a.shape != b.shape or [v["unit"] for v in old.get("values", [])] != [v["unit"] for v in new.get("values", [])]:
        return False, math.inf
    scale = max(float(np.max(np.abs(a))) if a.size else 0.0, 1e-300)
    diff = float(np.max(np.abs(a - b)) / scale) if a.size else 0.0
    return diff <= 1e-6, diff


def describe_record(rec):
    """One line about a stored result for the page: method, work done, how close."""
    bits = [rec.get("method", "")]
    if rec.get("nfev"):
        bits.append(f"{rec['nfev']} evaluations")
    if "resid" in rec:
        bits.append(("residual " if rec.get("kind") == "root" else "constraint violation ") + f"{rec['resid']:.2g}")
    return " · ".join(b for b in bits if b)


# ---- editing the text ----------------------------------------------------------------------------
def _editor(text, header):
    ed = BlockEditor(text, header)
    if ed.kind != "solver":
        raise SolverError(f"Line {header} is not a solver block")
    return ed


def write_result(text, header, record):
    """The edits that store `record` as the block's last line, replacing any earlier result."""
    ed = _editor(text, header)
    ed.store_result(record)
    return ed.edits()


def set_option(text, header, key, value):
    """The edits that set (or with value None, remove) one `key: value` line of the block."""
    ed = _editor(text, header)
    if value is None:
        ed.remove(key)
    else:
        ed.set(key, value)
    return ed.edits()


# ---- one run request, threaded through a sheet evaluation -------------------------------------------
class SolveRequest:
    """Asks `evaluate` to solve the block on `line` instead of reading its stored result.
    `mode` is "run" or "verify" (run, then compare with what is stored)."""
    def __init__(self, line, log, mode="run"):
        self.line, self.log, self.mode = line, log, mode
        self.outcome = None
