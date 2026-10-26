"""Runs a whole worksheet top to bottom. Each line either produces a result or
an error; an error never stops later lines (lines that depend on a failed
variable fail on their own with 'x is not defined')."""
import math
import re
from dataclasses import asdict, dataclass, field, fields, is_dataclass

import pint

from .evaluator import EvalError, Evaluator
from .latex import Fmt, Printer, escape, name_latex
from .nodes import (Assign, BinOp, Convert, FuncDef, Implicit, Neg, Num,
                    UnitDef, UnitLit)
from .si import reduce_si
from .parser import ParseError, parse_expr, parse_line
from .plotopts import (OPT_RE, PlotError, block_end, canon, is_plot_line,
                       parse_option, parse_plot)
from .plotspec import Builder
from .rename import global_spans
from .plotsvg import render_svg
from . import solver
from .solver import SolverError


@dataclass
class LineResult:
    n: int
    source: str
    kind: str  # blank comment heading meta command assign expr funcdef unitdef plot plotopt solver solveropt error
    lhs: str = ""
    stages: list = field(default_factory=list)
    text: str = ""
    error: str = ""
    svg: str = ""          # plot: the picture
    plot: dict = None      # plot: the data and settings it was drawn from (see plotspec.py)
    end: int = 0           # plot, solver: last line of its option lines
    solver: dict = None    # solver: status, hash and values of the block (see _run_solver)
    stale: bool = False    # reads a value from a solver whose result is out of date
    warning: str = ""      # shown under the result: the line works but may not do what was meant
    gdef: str = ""         # assign, funcdef: the name this line makes global, without its ~
    gspans: list = field(default_factory=list)  # [column, length] of each global name in the source line

    @property
    def latex(self):
        parts = [p for p in ([self.lhs] if self.lhs else []) + self.stages if p]
        return " = ".join(parts)

    def to_dict(self):
        d = asdict(self)
        d["latex"] = self.latex
        return d


def _is_literal(n, ev):
    """`12'kN/'m`, `8.5e7'mm^4`: one typed-in quantity and nothing computed.
    `10'kN / 5'mm` has two numbers, so it is a calculation."""
    def count(n):
        """Number of numeric leaves, or None if the tree is anything else."""
        if isinstance(n, (Implicit, Num)):
            return 1
        if isinstance(n, UnitLit):
            return 0
        if isinstance(n, Neg):
            return count(n.operand)
        if isinstance(n, BinOp) and n.op == "^":
            return count(n.left)          # the exponent is not a quantity
        if isinstance(n, BinOp) and n.op in "*/":
            a, b = count(n.left), count(n.right)
            return None if a is None or b is None else a + b
        return None

    def has_implicit(n):
        if isinstance(n, Implicit):
            return True
        if isinstance(n, Neg):
            return has_implicit(n.operand)
        return isinstance(n, BinOp) and (has_implicit(n.left) or has_implicit(n.right))
    return count(n) == 1 and has_implicit(n)


def _dedupe(stages):
    out = []
    for s in stages:
        if s and (not out or s != out[-1]):
            out.append(s)
    return out


def _unit_names(node):
    """Names of the units used anywhere under `node`."""
    if isinstance(node, UnitLit):
        return {node.unit}
    out = set()
    if is_dataclass(node):
        for f in fields(node):
            out |= _unit_names(getattr(node, f.name))
    elif isinstance(node, tuple):
        for x in node:
            out |= _unit_names(x)
    return out


@dataclass
class Worksheet:
    """The result of running a sheet: one LineResult per line, plus what a
    portable copy of it needs to carry along."""
    text: str
    results: list
    needed: list = field(default_factory=list)        # (name, definition) of instance units the sheet uses but does not define
    declarations: list = field(default_factory=list)  # \\DeclareSIUnit lines for the .tex export

    def portable_text(self):
        """The source with the unit definitions it relies on appended, so a copy
        opened on another instance evaluates the same way. Units are hoisted, so
        definitions at the end are fine."""
        if not self.needed:
            return self.text
        lines = ["#@ unit definitions used above, added when this sheet was saved"]
        lines += [f"'{n} = {d}" for n, d in self.needed]
        lines.append("#@ end of unit definitions")
        return self.text.rstrip("\n") + "\n\n" + "\n".join(lines) + "\n"


def run(text, siunitx=False, global_units=None):
    return evaluate(text, siunitx, global_units).results


def evaluate(text, siunitx=False, global_units=None, solve=None):
    """`global_units` are the instance's (name, definition) pairs. Units are
    defined before any line is evaluated, so a definition applies to the whole
    sheet, wherever it sits. `solve` is a SolverRequest: the block it names is solved
    instead of read, and `solver.StopSolve` ends the run once it is."""
    lines = text.splitlines()
    has_defs = any(s.startswith("'") and "=" in s for s in (l.strip() for l in lines))
    ev = Evaluator(global_units or (), fork=has_defs)
    fmt = Fmt(ev.ureg, siunitx=siunitx, custom=ev.custom)
    defs, here, used = {}, {}, set()
    for i, raw in enumerate(lines, 1):
        s = raw.strip()
        if s.startswith("'") and "=" in s:
            defs[i] = _define_unit(i, raw, s, ev, fmt, here, used)
    results, owned = [], {}   # `owned`: option lines of a plot, handled when the plot ran
    for i, raw in enumerate(lines, 1):
        s = raw.strip()
        if i in defs:
            results.append(defs[i])
        elif i in owned:
            results.append(owned.pop(i))
        elif solver.is_solver_line(s):
            r, owned = _run_solver(i, raw, lines, ev, fmt, used, solve)
            results.append(r)
        elif is_plot_line(s):
            r, owned = _run_plot(i, raw, lines, ev, fmt, used)
            results.append(r)
        elif not s:
            results.append(LineResult(i, raw, "blank"))
        elif s.startswith("##"):
            results.append(LineResult(i, raw, "heading", text=s[2:].strip()))
        elif s.startswith("#@"):
            results.append(LineResult(i, raw, "meta", text=s[2:].strip()))
        elif s.startswith("#"):
            results.append(LineResult(i, raw, "comment", text=s[1:].strip()))
        elif s.startswith("!"):
            results.append(_run_command(i, raw, s, ev, fmt))
        else:
            results.append(_run_line(i, raw, s, ev, fmt, used))
    for r, spans in zip(results, global_spans(text)):
        r.gspans = spans(ev.gnames_at(r.n))
    ws = Worksheet(text, results)
    # Instance units the sheet relies on, with the units those are defined in terms of.
    need, todo = set(), [n for n in used if n in ev.globals]
    while todo:
        n = todo.pop()
        if n not in need:
            need.add(n)
            todo += [m for m in _unit_names(parse_expr(ev.globals[n])) if m in ev.globals]
    ws.needed = [(n, d) for n, d in ev.globals.items() if n in need and n not in here]
    for name, macro in fmt.macros.items():
        if name in fmt.builtin:
            ws.declarations.append(rf"\DeclareSIUnit{{\{macro}}}{{\ensuremath{{{fmt.builtin[name]}}}}}  % {name}")
            continue
        ws.declarations.append(f"% 1 {name} = {ev.custom.get(name) or '?'}".replace("\n", " "))
        ws.declarations.append(rf"\DeclareSIUnit{{\{macro}}}{{{escape(name)}}}")
    return ws


def _define_unit(i, raw, s, ev, fmt, here, used):
    """One `'name = value` line. A definition identical to an instance-wide one is
    accepted (that is what a portable copy carries); a different one is an error."""
    stmt = None
    try:
        stmt = parse_line(s)
        if not isinstance(stmt, UnitDef):
            return _run_line(i, raw, s, ev, fmt, used)
        used |= _unit_names(stmt.expr)
        name = stmt.name
        if name in here:
            raise EvalError(f"'{name}' is already defined on line {here[name]}")
        if name in ev.globals:
            mine, theirs = ev.eval(stmt.expr), ev.Q(1, name)
            same = (mine.dimensionality == theirs.dimensionality and
                    math.isclose(mine.to_base_units().magnitude, theirs.to_base_units().magnitude, rel_tol=1e-9))
            if not same:
                raise EvalError(f"'{name}' differs from this instance's own definition, {name} = {ev.globals[name]}. "
                                "Rename the unit here, or change the definition under Units")
            q = mine
        else:
            q = ev.define_unit(name, stmt.expr, stmt.source)
        here[name] = i
        shown = ev.Q(q.magnitude, q.units)
        return LineResult(i, raw, "unitdef", lhs="1\\," + fmt.unit_inline(ev.ureg.parse_units(name)),
                          stages=[fmt.quantity(shown)], text=f"1 {name} = {fmt.plain(shown)}")
    except Exception as e:
        return LineResult(i, raw, "error", error=_describe(e))


def _run_command(i, raw, s, ev, fmt):
    """`!clear` removes every variable whose name does not start with ~.
    `!clearf` does the same for user functions. `!noassume` keeps computed results in the
    units that came out of the arithmetic instead of reducing them to SI, until
    `!assume` restores the default. `!trigdeg` and `!trigrad` set the angle unit
    that trig functions read bare numbers in and that inverse ones return. `!short`
    shows only each line's final result, without intermediate steps, until
    `!long` restores the full display. `!sigfigs n`, `!sigfigsbig n` (keeps trailing zeros) and `!decplace n` choose how results
    are printed, by significant figures (4 by default) or by decimal places; the last one
    given wins. Only the display is rounded."""
    parts = s[1:].split()
    name = parts[0] if parts else ""
    if name == "plotspec":
        return _plotspec_command(i, raw, s, ev)
    if name == "plot":     # a plot statement with something after it never gets here
        return LineResult(i, raw, "error", error="A plot reads `!plot f(x), x = low .. high`")
    if name in ("sigfigs", "sigfigsbig", "decplace"):
        return _precision_command(i, raw, name, parts[1:], fmt)
    if name not in ("clear", "clearf", "assume", "noassume", "trigdeg", "trigrad",
                    "short", "long"):
        return LineResult(i, raw, "error",
                          error=f"Unknown command '!{name}'. Available: !clear, !clearf, !assume, "
                                "!noassume, !trigdeg, !trigrad, !short, !long, !sigfigs, !decplace, !plot, !plotspec, "
                                "!root, !minimize, !maximize")
    if len(parts) > 1:
        return LineResult(i, raw, "error", error=f"!{name} takes no arguments")
    if name in ("assume", "noassume"):
        ev.assume = name == "assume"
        text = "Units are reduced to SI again" if ev.assume else "Units are kept as typed unless converted with ->"
        return LineResult(i, raw, "command", text=text)
    if name in ("short", "long"):
        ev.short = name == "short"
        text = "Showing final results only, without steps" if ev.short else "Showing steps again"
        return LineResult(i, raw, "command", text=text)
    if name == "clearf":
        gone = [n for n in ev.funcs if not n.startswith("~")]
        for n in gone:
            del ev.funcs[n]
        ev.cleared_funcs.update(gone)
        return LineResult(i, raw, "command", text=_cleared(gone, [n for n in ev.funcs if n.startswith("~")]))
    if name in ("trigdeg", "trigrad"):
        ev.angle = "degree" if name == "trigdeg" else "radian"
        text = ("Trig functions take and return degrees" if ev.angle == "degree"
                else "Trig functions take and return radians")
        return LineResult(i, raw, "command", text=text)
    gone = [n for n in ev.vars if not n.startswith("~")]
    for n in gone:
        del ev.vars[n]
    ev.cleared.update(gone)
    ev.stale -= set(gone)
    return LineResult(i, raw, "command", text=_cleared(gone, [n for n in ev.vars if n.startswith("~")]))


def _cleared(gone, kept):
    """`!clear` and `!clearf` name what they kept as well, since a global surviving one is easy to miss."""
    text = f"Cleared {', '.join(gone)}" if gone else "Nothing to clear"
    if kept:
        text += f". Kept global{'s' * (len(kept) > 1)} {', '.join(kept)}"
    return text


def _precision_command(i, raw, name, args, fmt):
    """`!sigfigs 5` or `!decplace 2`: how many digits results are displayed with."""
    lo, hi = (0, 15) if name == "decplace" else (1, 15)
    if len(args) != 1 or not re.fullmatch(r"\d+", args[0]) or not lo <= int(args[0]) <= hi:
        return LineResult(i, raw, "error", error=f"!{name} takes a whole number from {lo} to {hi}, e.g. `!{name} 3`")
    n = int(args[0])
    if name != "decplace":
        fmt.sig, fmt.places, fmt.keep_zeros = n, None, name == "sigfigsbig"
        text = f"Results show {n} significant figure{'s' * (n != 1)}" + (", trailing zeros kept" if fmt.keep_zeros else "")
    else:
        fmt.places = n
        text = f"Results show {n} decimal place{'s' * (n != 1)}"
    return LineResult(i, raw, "command", text=text)


def _plotspec_command(i, raw, s, ev):
    """`!plotspec grid: off` sets an option for every plot below it; `!plotspec reset` clears them."""
    words = s[1:].split(None, 1)
    rest = words[1].strip() if len(words) > 1 else ""
    if rest == "reset":
        ev.plotdefs.clear()
        return LineResult(i, raw, "command", text="Plot options are back to the defaults")
    m = re.fullmatch(r"([A-Za-z]\w*)\s*:\s*(.*)", rest)
    try:
        if not m:
            raise PlotError("!plotspec reads `!plotspec key: value` or `!plotspec reset`")
        key, _, value = parse_option(m.group(1), None, m.group(2), sheet=True)
    except PlotError as e:
        return LineResult(i, raw, "error", error=str(e))
    ev.plotdefs[key] = value
    return LineResult(i, raw, "command", text=f"Plots below: {key} {canon(key, value)}")


def _run_plot(i, raw, lines, ev, fmt, used):
    """A `!plot` line and the option lines under it. Returns the plot's result and the
    results for its option lines, keyed by line number. A bad option line is reported
    on that line and the plot is drawn without it."""
    end = block_end(lines, i - 1)
    owned, opts = {}, []
    for n in range(i + 1, end + 1):
        m = OPT_RE.match(lines[n - 1])
        try:
            key, idx, value = parse_option(m.group(1), m.group(2), m.group(3))
            opts.append((n, key, idx, value))
            owned[n] = LineResult(n, lines[n - 1], "plotopt")
        except PlotError as e:
            owned[n] = LineResult(n, lines[n - 1], "error", error=str(e))

    nodes = []

    def parse(src):
        node = parse_expr(src)
        used.update(_unit_names(node))
        nodes.append(node)
        return node
    try:
        series, var, lo, hi = parse_plot(raw)
        b = Builder(ev, fmt, parse)
        spec = b.build(i, series, var, lo, hi, opts)
    except Exception as e:
        return LineResult(i, raw, "error", error=_describe(e), end=end), owned
    for n, msg in b.errors:
        owned[n] = LineResult(n, lines[n - 1], "error", error=msg)
    text = spec["title"] or "plot " + ", ".join(s["label"] for s in spec["series"])
    return LineResult(i, raw, "plot", text=text, svg=render_svg(spec, uid=i), plot=spec, end=end,
                      stale=solver.tainted(ev, nodes)), owned


def _run_solver(i, raw, lines, ev, fmt, used, solve):
    """A `!root`, `!minimize` or `!maximize` line with its option lines. Nothing is solved here:
    the stored result is compared by hash with the block's current inputs and, fitting or not, its
    values are what the unknowns hold below (a result that no longer fits is marked out of date, as
    is everything computed from it). Only a SolveRequest for this very line runs the solver."""
    block = solver.parse_block(lines, i - 1)
    owned = {}
    for n in range(i + 1, block.end + 1):
        msg = block.errors.get(n)
        owned[n] = LineResult(n, lines[n - 1], "error" if msg else "solveropt", error=msg or "")
    mine = solve is not None and solve.line == i

    def fail(msg):
        if mine:
            solve.outcome = {"ok": False, "message": msg, "record": None}
            raise solver.StopSolve
        ev.stale |= {ev.vkey(n) for n in block.unknowns}   # what reads them below is not trustworthy either
        return LineResult(i, raw, "error", error=msg, end=block.end), owned

    if block.problem:
        return fail(block.problem)
    for node in block.nodes():
        used |= _unit_names(node)
    try:
        prob = solver.prepare(block, ev, _describe)
        h = prob.digest()
    except Exception as e:
        return fail(_describe(e))
    stored = block.stored
    qs = prob.stored_quantities(stored) if stored is not None else None
    status = "none" if qs is None else ("valid" if stored.get("hash") == h else "stale")
    if mine or status != "valid":
        try:
            prob.probe()
        except Exception as e:
            return fail(_describe(e))
    if mine:
        out = prob.solve(solve.log)
        out["hash"] = h
        if solve.mode == "verify" and out["record"] is not None:
            if stored is None or stored.get("hash") != h:
                out["verify"] = {"same": None, "diff": None,
                                 "note": "There is no current stored result to compare with. Run it first."}
            else:
                same, diff = solver.compare(stored, out["record"])
                out["verify"] = {"same": same, "diff": diff, "note": ""}
        solve.outcome = out
        raise solver.StopSolve
    taint = solver.tainted(ev, block.nodes()) or any(u.key in ev.stale for u in prob.unknowns)
    keys = {u.key for u in prob.unknowns}
    if status != "valid" or taint:
        ev.stale |= keys
    else:
        ev.stale -= keys
    if qs is not None:
        for u, q in zip(prob.unknowns, qs):
            ev.vars[u.key] = q
    values = [_value(u.name, fmt.var(u.key), fmt.quantity(ev.vars[u.key])) for u in prob.unknowns]
    plain = [f"{u.key} = {fmt.plain(ev.vars[u.key])}" for u in prob.unknowns]
    obj = prob.stored_objective(stored) if qs is not None else None
    if obj is not None:
        word = "minimum" if block.kind == "minimize" else "maximum"
        values.append(_value(word, rf"\text{{{word}}}", fmt.quantity(obj)))
        plain.append(f"{word} = {fmt.plain(obj)}")
    info = {"kind": block.kind, "unknowns": block.unknowns, "hash": h, "status": status, "tainted": taint,
            "autorun": block.autorun, "method": prob.method, "timeout": block.timeout, "values": values,
            "summary": solver.describe_record(stored) if qs is not None else "", "note": block.stored_note,
            "record": stored if qs is not None else None}
    return LineResult(i, raw, "solver", text="; ".join(plain), end=block.end, solver=info,
                      stale=status != "valid" or taint), owned


def _value(name, lhs, rhs):
    return {"name": name, "lhs": lhs, "rhs": rhs, "latex": f"{lhs} = {rhs}"}


def solve_block(text, line, global_units=None, log=print, mode="run"):
    """Solve the block whose header is on `line` (1-based), in this process. Returns
    {"ok", "message", "record", "hash", ...}; `record` is what write_result stores. The whole sheet
    is evaluated up to that line, so upstream blocks use their stored results as they do on screen."""
    lines = text.splitlines()
    if not 1 <= line <= len(lines) or not solver.is_solver_line(lines[line - 1]):
        return {"ok": False, "message": f"Line {line} is not a !root, !minimize or !maximize line", "record": None}
    req = solver.SolveRequest(line, log, mode)
    try:
        evaluate(text, global_units=global_units, solve=req)
    except solver.StopSolve:
        pass
    return req.outcome or {"ok": False, "message": f"Line {line} was not reached", "record": None}


def _run_line(i, raw, s, ev, fmt, used):
    stmt = None
    try:
        stmt = parse_line(s)
        used |= _unit_names(stmt)
        if isinstance(stmt, FuncDef):
            printer = Printer(ev, fmt, local=stmt.params)
            sym = printer.tex(stmt.body)
            key = ev.bind_key(stmt.name, func=True)
            ev.funcs[key] = (stmt.params, stmt.body)
            head = f"{fmt.var(key)}\\left({', '.join(name_latex(p) for p in stmt.params)}\\right)"
            return LineResult(i, raw, "funcdef", lhs=head, stages=[sym], text=s,
                              **_global_note(i, stmt.name, key, ev, func=True))

        expr = stmt.expr
        value = ev.check_finite(ev.eval(expr), expr)
        literal = _is_literal(expr, ev)
        # Explicit `->` conversions and typed-in quantities are shown as given;
        # computed results are reduced to simple SI unless !noassume is active.
        if ev.assume and not (literal or isinstance(expr, Convert)):
            value = reduce_si(value, ev.ureg)
            if ev.angle == "degree" and dict(value.unit_items()) == {"radian": 1}:
                value = value.to("degree")
        stale = solver.tainted(ev, [expr])
        sym = Printer(ev, fmt).tex(expr)
        sub = Printer(ev, fmt, subst=True).tex(expr)
        res = fmt.quantity(value)
        stages = [res] if literal or ev.short else _dedupe([sym, sub, res])
        if isinstance(stmt, Assign):
            key = ev.bind_key(stmt.name)
            ev.vars[key] = value
            (ev.stale.add if stale else ev.stale.discard)(key)
            return LineResult(i, raw, "assign", lhs=fmt.var(key), stages=stages,
                              text=f"{key} = {fmt.plain(value)}", stale=stale,
                              **_global_note(i, stmt.name, key, ev))
        return LineResult(i, raw, "expr", stages=stages, text=fmt.plain(value), stale=stale)
    except Exception as e:
        return LineResult(i, raw, "error", error=_describe(e))


def _global_note(i, name, key, ev, func=False):
    """What a definition of a global puts on its row: the name, on the line that first makes
    it global, or a warning when it is assigned without its ~. The editor adds the ~ as a
    global is typed, so a plain name here usually means the ~ was deleted by accident."""
    if not key.startswith("~"):
        return {}
    first = ev.gline.setdefault((func, key), i)
    if first == i:
        return {"gdef": key[1:]}
    if name.startswith("~"):
        return {}
    kind = "function" if func else "global"
    return {"warning": f"Changes the {kind} {key}, defined on line {first}. Write {key} if that is meant"}


def _describe(e):
    if isinstance(e, (ParseError, EvalError, PlotError, SolverError)):
        return str(e)
    if isinstance(e, pint.errors.DimensionalityError):
        return f"Incompatible units: {e}"
    if isinstance(e, pint.errors.PintError):
        return str(e)
    if isinstance(e, ZeroDivisionError):
        return "Division by zero"
    return f"{type(e).__name__}: {e}"
