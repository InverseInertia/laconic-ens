"""Runs a whole worksheet top to bottom. Each line either produces a result or
an error; an error never stops later lines (lines that depend on a failed
variable fail on their own with 'x is not defined')."""
import math
import re
from dataclasses import dataclass, field, fields, is_dataclass

import pint

from . import catalogue
from .blockedit import newline
from .evaluator import EvalError, Evaluator
from .latex import Fmt, Printer, name_latex
from .lineresult import LineResult, PlotPayload, SolverPayload
from .nodes import (Assign, BinOp, Convert, FuncDef, Implicit, Neg, Num,
                    UnitDef, UnitLit)
from .si import reduce_si
from .parser import ParseError, parse_expr, parse_line
from .plotopts import PlotError, parse_option, parse_plot
from .plotspec import Builder
from .sheettext import scan
from .symbols import FUNCTION, ScopeError, SymbolTable
from .plotsvg import render_svg
from . import commands, solver
from .commands import CommandError
from .solver import SolverError


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
    symbols: SymbolTable = None   # which names each line sees
    needed: list = field(default_factory=list)        # (name, definition) of instance units the sheet uses but does not define
    declarations: list = field(default_factory=list)  # \\DeclareSIUnit lines for the .tex export

    def block(self, header):
        """The result of the block whose header is on line `header`, or None."""
        r = self.results[header - 1] if 1 <= header <= len(self.results) else None
        return r if r is not None and r.block is not None and r.n == header else None

    def portable_text(self):
        """The source with the unit definitions it relies on appended, so a copy
        opened on another instance evaluates the same way. Units are hoisted, so
        definitions at the end are fine. They end their lines as the file does."""
        if not self.needed:
            return self.text
        nl = newline(self.text)
        lines = ["#@ unit definitions used above, added when this sheet was saved"]
        lines += [f"'{n} = {d}" for n, d in self.needed]
        lines.append("#@ end of unit definitions")
        return self.text.rstrip("\r\n") + nl * 2 + nl.join(lines) + nl


def run(text, siunitx=False, global_units=None):
    return evaluate(text, siunitx, global_units).results


def evaluate(text, siunitx=False, global_units=None, solve=None, until=None):
    """`global_units` are the instance's (name, definition) pairs. Units are
    defined before any line is evaluated, so a definition applies to the whole
    sheet, wherever it sits. `solve` is a SolverRequest: the block it names is solved
    instead of read, and `solver.StopSolve` ends the run once it is. With `until`, the run
    stops after that line: nothing below a line changes its result, so this is enough to read
    a block (its `needed` and `declarations` then cover only the lines that ran)."""
    sheet = scan(text)
    has_defs = any(l.kind == "unitdef" for l in sheet.lines)
    ev = Evaluator(global_units or (), fork=has_defs)
    fmt = Fmt(ev.ureg, siunitx=siunitx, custom=ev.custom, mode=ev.mode)
    defs, here, used = {}, {}, set()
    for l in sheet.lines:
        if l.kind == "unitdef":
            defs[l.n] = _define_unit(l.n, l.text, l.text.strip(), ev, fmt, here, used)
    results, owned = [], {}   # `owned`: option lines of a plot, handled when the plot ran
    for l in sheet.lines:
        if until is not None and l.n > until:
            break
        i, raw, s = l.n, l.text, l.text.strip()
        ev.symbols.line = i
        if i in defs:
            results.append(defs[i])
        elif i in owned:
            results.append(owned.pop(i))
        elif l.kind == "solver":
            r, owned = _run_solver(i, raw, sheet.block(i), ev, fmt, used, solve)
            results.append(r)
        elif l.kind == "plot":
            r, owned = _run_plot(i, raw, sheet.block(i), ev, fmt, used)
            results.append(r)
        elif l.kind == "blank":
            results.append(LineResult(i, raw, "blank"))
        elif l.kind in ("heading", "meta"):
            results.append(LineResult(i, raw, l.kind, text=s[2:].strip()))
        elif l.kind == "comment":
            results.append(LineResult(i, raw, "comment", text=s[1:].strip()))
        elif l.kind == "command":
            results.append(_run_command(i, raw, s, ev))
        else:
            results.append(_run_line(i, raw, s, ev, fmt, used))
    for r, l in zip(results, sheet.lines):
        r.symbols = _symbols(ev.symbols, l)
    ws = Worksheet(text, results, ev.symbols)
    # Instance units the sheet relies on, with the units those are defined in terms of.
    need, todo = set(), [n for n in used if n in ev.globals]
    while todo:
        n = todo.pop()
        if n not in need:
            need.add(n)
            todo += [m for m in _unit_names(parse_expr(ev.globals[n])) if m in ev.globals]
    ws.needed = [(n, d) for n, d in ev.globals.items() if n in need and n not in here]
    ws.declarations = fmt.declarations()
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


def _run_command(i, raw, s, ev):
    """A `!name` line: run through the command registry (commands.py), which changes the sheet mode."""
    try:
        return LineResult(i, raw, "command", text=commands.run(s, ev.mode, ev))
    except CommandError as e:
        return LineResult(i, raw, "error", error=str(e))


def _run_plot(i, raw, block, ev, fmt, used):
    """A `!plot` line and the option lines under it. Returns the plot's result and the
    results for its option lines, keyed by line number. A bad option line is reported
    on that line and the plot is drawn without it."""
    src = {l.n: l.text for l in block.members}
    owned, opts = {}, []
    for l in block.members:
        o = l.option
        try:
            key, idx, value = parse_option(o.key, o.arg, o.value)
            opts.append((l.n, key, idx, value))
            owned[l.n] = LineResult(l.n, l.text, "plotopt")
        except PlotError as e:
            owned[l.n] = LineResult(l.n, l.text, "error", error=str(e))

    nodes = []

    def parse(src):
        node = parse_expr(src)
        used.update(_unit_names(node))
        nodes.append(node)
        return node
    try:
        series, var, lo, hi = parse_plot(block.args)
        b = Builder(ev, fmt, parse)
        spec = b.build(i, series, var, lo, hi, opts)
    except Exception as e:
        return LineResult(i, raw, "error", error=_describe(e), block=block), owned
    for n, msg in b.errors:
        owned[n] = LineResult(n, src[n], "error", error=msg)
    text = spec["title"] or "plot " + ", ".join(s["label"] for s in spec["series"])
    return LineResult(i, raw, "plot", text=text, block=block, payload=PlotPayload(spec, render_svg(spec, uid=i)),
                      stale=solver.tainted(ev, nodes)), owned


def _run_solver(i, raw, handle, ev, fmt, used, solve):
    """A `!root`, `!minimize` or `!maximize` line with its option lines. Nothing is solved here:
    the stored result is compared by hash with the block's current inputs and, fitting or not, its
    values are what the unknowns hold below (a result that no longer fits is marked out of date, as
    is everything computed from it). Only a SolveRequest for this very line runs the solver."""
    members, block = handle.members, solver.parse_block(handle)
    owned = {}
    for l in members:
        msg = block.errors.get(l.n)
        owned[l.n] = LineResult(l.n, l.text, "error" if msg else "solveropt", error=msg or "")
    mine = solve is not None and solve.line == i

    def fail(msg):
        if mine:
            solve.outcome = {"ok": False, "message": msg, "record": None}
            raise solver.StopSolve
        ev.stale |= {ev.vkey(n) for n in block.unknowns}   # what reads them below is not trustworthy either
        return LineResult(i, raw, "error", error=msg, block=handle), owned

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
    for u in prob.unknowns:     # below the block, an unknown holds what the block says
        ev.symbols.bind(u.key, value=fmt.plain(ev.vars[u.key]))
    values = [_value(u.name, fmt.var(u.key), fmt.quantity(ev.vars[u.key])) for u in prob.unknowns]
    plain = [f"{u.key} = {fmt.plain(ev.vars[u.key])}" for u in prob.unknowns]
    obj = prob.stored_objective(stored) if qs is not None else None
    if obj is not None:
        word = "minimum" if block.kind == "minimize" else "maximum"
        values.append(_value(word, rf"\text{{{word}}}", fmt.quantity(obj)))
        plain.append(f"{word} = {fmt.plain(obj)}")
    info = SolverPayload(block.kind, block.unknowns, h, status, taint, block.autorun, prob.method,
                         block.timeout, values, summary=solver.describe_record(stored) if qs is not None else "",
                         note=block.stored_note, record=stored if qs is not None else None)
    return LineResult(i, raw, "solver", text="; ".join(plain), block=handle, payload=info,
                      stale=status != "valid" or taint), owned


def _value(name, lhs, rhs):
    return {"name": name, "lhs": lhs, "rhs": rhs, "latex": f"{lhs} = {rhs}"}


def solve_block(text, line, global_units=None, log=print, mode="run"):
    """Solve the block whose header is on `line` (1-based), in this process. Returns
    {"ok", "message", "record", "hash", ...}; `record` is what write_result stores. The whole sheet
    is evaluated up to that line, so upstream blocks use their stored results as they do on screen."""
    b = scan(text).block(line)
    if b is None or b.kind != "solver":
        return {"ok": False, "message": f"Line {line} is not a !root, !minimize or !maximize line", "record": None}
    req = solver.SolveRequest(line, log, mode)
    try:
        evaluate(text, global_units=global_units, solve=req)
    except solver.StopSolve:
        pass
    return req.outcome or {"ok": False, "message": f"Line {line} was not reached", "record": None}


def block_at(text, line, global_units=None):
    """The result of the block whose header is on `line`, or None when no block starts there. The
    text alone says where the block is, so the sheet runs only as far as its last line."""
    b = scan(text).block(line)
    if b is None:
        return None
    return evaluate(text, global_units=global_units, until=b.end).block(line)


def solver_blocks(text, global_units=None):
    """The results of the solver blocks that read (they carry a SolverPayload), top to bottom. The
    sheet runs only as far as the last block, and not at all when there is none."""
    ends = [b.end for b in scan(text).blocks.values() if b.kind == "solver"]
    if not ends:
        return []
    ws = evaluate(text, global_units=global_units, until=max(ends))
    return [r for r in ws.results if r.solver]


def _run_line(i, raw, s, ev, fmt, used):
    stmt = None
    try:
        stmt = parse_line(s)
        used |= _unit_names(stmt)
        if isinstance(stmt, FuncDef):
            printer = Printer(ev, fmt, local=stmt.params)
            sym = printer.tex(stmt.body)
            name = ev.symbols.bind(stmt.name, FUNCTION, params=stmt.params)
            key = name.key
            ev.funcs[key] = (stmt.params, stmt.body)
            head = f"{fmt.var(key)}\\left({', '.join(name_latex(p) for p in stmt.params)}\\right)"
            return LineResult(i, raw, "funcdef", lhs=head, stages=[sym], text=s,
                              warning=_global_note(stmt.name, name, ev.symbols))

        expr = stmt.expr
        value = ev.settle(ev.check_finite(ev.eval(expr), expr))
        literal = _is_literal(expr, ev)
        # Explicit `->` conversions and typed-in quantities are shown as given;
        # computed results are reduced to simple SI unless !noassume is active.
        if ev.mode.assume and not (literal or isinstance(expr, Convert)):
            value = reduce_si(value, ev.ureg)
            if ev.mode.angle == "degree" and dict(value.unit_items()) == {"radian": 1}:
                value = value.to("degree")
        stale = solver.tainted(ev, [expr])
        sym = Printer(ev, fmt).tex(expr)
        sub = Printer(ev, fmt, subst=True).tex(expr)
        res = fmt.quantity(value)
        stages = [res] if literal or ev.mode.short else _dedupe([sym, sub, res])
        if isinstance(stmt, Assign):
            name = ev.symbols.bind(stmt.name, value=fmt.plain(value))
            key = name.key
            ev.vars[key] = value
            (ev.stale.add if stale else ev.stale.discard)(key)
            return LineResult(i, raw, "assign", lhs=fmt.var(key), stages=stages,
                              text=f"{key} = {fmt.plain(value)}", stale=stale,
                              warning=_global_note(stmt.name, name, ev.symbols) or _imaginary_note(stmt.name, ev.mode))
        return LineResult(i, raw, "expr", stages=stages, text=fmt.plain(value), stale=stale)
    except Exception as e:
        return LineResult(i, raw, "error", error=_describe(e))


def _imaginary_note(name, mode):
    """The warning on a variable named i or j while complex numbers are on: it reads as the
    imaginary unit, which the sheet writes 1i."""
    bare = name.lstrip("~")
    if bare not in ("i", "j") or mode.complex == "real":
        return ""
    return (f"{bare} reads like the imaginary unit, but here it is a variable. Write the imaginary "
            f"unit as 1{bare}, or use another name (or !complex real)")


def _global_note(name, sym, table):
    """The warning on a definition of a global written without its ~. The editor adds the ~ as
    a global is typed, so a plain name here usually means the ~ was deleted by accident."""
    first = table.first_global(sym)
    if first is None or first is sym or name.startswith("~"):
        return ""
    kind = "function" if sym.kind == FUNCTION else "global"
    return f"Changes the {kind} {sym.key}, defined on line {first.line}. Write {sym.key} if that is meant"


def _symbols(table, line):
    """A row's part of the symbol table: the symbols its line defines (each with the last line
    it is visible on) and [column, length, symbol id] of each name on it that means one."""
    return {"defines": [s.to_dict() for s in table.defined_on(line.n)], "uses": table.uses(line)}


def _describe(e):
    if isinstance(e, (ParseError, EvalError, PlotError, SolverError, ScopeError)):
        return str(e)
    if isinstance(e, pint.errors.DimensionalityError):
        dims = [d for dim in (e.dim1, e.dim2) for d in re.findall(r"\[(\w+)\]", str(dim))]
        return catalogue.mismatch(dims) or f"Incompatible units: {e}"
    if isinstance(e, pint.errors.PintError):
        return str(e)
    if isinstance(e, ZeroDivisionError):
        return "Division by zero"
    return f"{type(e).__name__}: {e}"
