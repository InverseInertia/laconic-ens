"""Runs a whole worksheet top to bottom. Each line either produces a result or
an error; an error never stops later lines (lines that depend on a failed
variable fail on their own with 'x is not defined')."""
import math
import re
from dataclasses import dataclass, field

import pint

from . import catalogue
from .blockedit import newline
from .evaluator import EvalError, Evaluator, is_symbolic
from .latex import Fmt, Printer, name_latex
from .lineresult import LineResult, PlotPayload, RegressionPayload, SolverPayload
from .nodes import Assign, Convert, FuncDef, Neg, Num, UnitDef, is_literal, refs
from .si import reduce_si
from .parser import ParseError, parse_expr, parse_line
from .plotopts import PlotError, parse_option, parse_plot
from .plotspec import Builder
from .sheettext import scan
from .symbols import FUNCTION, ScopeError, SymbolTable
from .plotsvg import render_svg
from . import commands, regression, solver, symsolve
from .commands import CommandError
from .regression import RegressionError
from .solver import SolverError


def _dedupe(stages):
    out = []
    for s in stages:
        if s and (not out or s != out[-1]):
            out.append(s)
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


def evaluate(text, siunitx=False, global_units=None, until=None):
    """`global_units` are the instance's (name, definition) pairs. Units are
    defined before any line is evaluated, so a definition applies to the whole
    sheet, wherever it sits. With `until`, the run stops after that line: nothing below a
    line changes its result, so this is enough to read a block (its `needed` and
    `declarations` then cover only the lines that ran)."""
    return _run(text, siunitx, global_units, until)[0]


def evaluator_at(text, line, global_units=None):
    """The evaluator as line `line` finds it: every line above has run, none from `line` on.
    What a solve session builds its problem on, so a run sees what the block sees on screen."""
    ev = _run(text, global_units=global_units, until=line - 1)[1]
    ev.symbols.line = line
    ev.notes.clear()
    return ev


def _run(text, siunitx=False, global_units=None, until=None):
    """Run the sheet. Returns the Worksheet and the evaluator as the last line left it."""
    sheet = scan(text)
    has_defs = any(l.kind == "unitdef" for l in sheet.lines)
    ev = Evaluator(global_units or (), fork=has_defs)
    fmt = Fmt(ev.ureg, siunitx=siunitx, custom=ev.custom, mode=ev.mode)
    fmt.table = ev.symbols
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
        ev.notes.clear()
        if i in defs:
            results.append(defs[i])
        elif i in owned:
            results.append(owned.pop(i))
        elif l.kind == "solver":
            run_block = {"regression": _run_regression, "symsolve": _run_symsolve}.get(sheet.block(i).command, _run_solver)
            r, owned = run_block(i, raw, sheet.block(i), ev, fmt, used)
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
        elif l.kind == "symdef":
            results.append(_run_symdef(i, raw, s, ev))
        else:
            results.append(_run_line(i, raw, s, ev, fmt, used))
        _add_notes(results[-1], ev.notes)
    for r, l in zip(results, sheet.lines):
        r.symbols = _symbols(ev.symbols, l)
    ws = Worksheet(text, results, ev.symbols)
    # Instance units the sheet relies on, with the units those are defined in terms of.
    need, todo = set(), [n for n in used if n in ev.globals]
    while todo:
        n = todo.pop()
        if n not in need:
            need.add(n)
            todo += [m for m in refs(parse_expr(ev.globals[n])).units if m in ev.globals]
    ws.needed = [(n, d) for n, d in ev.globals.items() if n in need and n not in here]
    ws.declarations = fmt.declarations()
    return ws, ev


def _define_unit(i, raw, s, ev, fmt, here, used):
    """One `'name = value` line. A definition identical to an instance-wide one is
    accepted (that is what a portable copy carries); a different one is an error."""
    stmt = None
    try:
        stmt = parse_line(s)
        if not isinstance(stmt, UnitDef):
            return _run_line(i, raw, s, ev, fmt, used)
        used |= refs(stmt.expr).units
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
        return LineResult(i, raw, "error", error=describe(e))


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
        used.update(refs(node).units)
        nodes.append(node)
        return node
    try:
        series, var, lo, hi, points = parse_plot(block.args)
        b = Builder(ev, fmt, parse)
        spec = b.build(i, series, var, lo, hi, opts, points)
    except Exception as e:
        return LineResult(i, raw, "error", error=describe(e), block=block), owned
    for n, msg in b.errors:
        owned[n] = LineResult(n, src[n], "error", error=msg)
    text = spec["title"] or "plot " + ", ".join(s["label"] for s in spec["series"])
    return LineResult(i, raw, "plot", text=text, block=block, payload=PlotPayload(spec, render_svg(spec, uid=i)),
                      stale=ev.symbols.tainted(nodes)), owned


def _run_solver(i, raw, handle, ev, fmt, used):
    """A `!root`, `!minimize` or `!maximize` line with its option lines. Nothing is solved here
    (that is solvesession.py's): the stored result is compared by hash with the block's current
    inputs and, fitting or not, its values are what the unknowns hold below (a result that no
    longer fits is marked out of date, as is everything computed from it)."""
    members, block = handle.members, solver.parse_block(handle)
    owned = {}
    for l in members:
        msg = block.errors.get(l.n)
        owned[l.n] = LineResult(l.n, l.text, "error" if msg else "solveropt", error=msg or "")

    def fail(msg):
        ev.symbols.mark_stale(ev.vkey(n) for n in block.unknowns)   # what reads them below is not trustworthy either
        return LineResult(i, raw, "error", error=msg, block=handle), owned

    if block.problem:
        return fail(block.problem)
    for node in block.nodes():
        used |= refs(node).units
    try:
        prob = solver.prepare(block, ev, describe)
        h = prob.digest()
    except Exception as e:
        return fail(describe(e))
    stored = block.stored
    qs = prob.stored_quantities(stored) if stored is not None else None
    status = "none" if qs is None else ("valid" if stored.get("hash") == h else "stale")
    try:
        prob.probe()   # also when the stored result is current: the line's notes come from this run
    except Exception as e:
        return fail(describe(e))
    taint = ev.symbols.tainted(block.nodes()) or any(ev.symbols.is_stale(u.key) for u in prob.unknowns)
    held = qs if qs is not None else [ev.vars[u.key] for u in prob.unknowns]
    for u, q in zip(prob.unknowns, held):     # below the block, an unknown holds what the block says
        ev.symbols.define(u.key, q, text=fmt.plain(q), stale=status != "valid" or taint)
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


def _run_regression(i, raw, handle, ev, fmt, used):
    """A `!regression` line with its option lines. Unlike a solver block it is worked out here,
    every run (a least-squares fit is quick and exact), and defines its coefficients (and R²) for
    the lines below, as an assignment does."""
    block = regression.parse_block(handle)
    owned = {}
    for l in handle.members:
        msg = block.errors.get(l.n)
        owned[l.n] = LineResult(l.n, l.text, "error" if msg else "solveropt", error=msg or "")

    def fail(msg):
        return LineResult(i, raw, "error", error=msg, block=handle), owned

    if block.problem:
        return fail(block.problem)
    for node in block.nodes():
        used |= refs(node).units
    try:
        f = regression.fit(block, ev)
        stale = ev.symbols.tainted(block.nodes())
        defined = []
        for name, q in zip(block.names, f.coefficients):
            if ev.mode.assume:
                q = reduce_si(q, ev.ureg)
            defined.append((ev.symbols.define(name, q, text=fmt.plain(q), stale=stale).key, q))
        r2 = ev.Q(f.r2, "dimensionless")
        if block.r2:
            r2_key = ev.symbols.define(block.r2, r2, text=fmt.plain(r2), stale=stale).key
        if block.model:
            m = block.model
            fkey = ev.symbols.define_function(m.name, m.params, m.body).key
    except Exception as e:
        return fail(describe(e))
    values = [_value(key, fmt.var(key), fmt.quantity(q)) for key, q in defined]
    values.append(_value(r2_key if block.r2 else "R²", fmt.var(r2_key) if block.r2 else "R^{2}", fmt.quantity(r2)))
    plain = [f"{key} = {fmt.plain(q)}" for key, q in defined]
    plain.append(f"{r2_key if block.r2 else 'R²'} = {fmt.plain(r2)}")
    if block.model:
        head = f"{fmt.var(fkey)}\\left({', '.join(name_latex(p) for p in m.params)}\\right)"
        model = f"{head} = {Printer(ev, fmt, local=m.params).tex(m.body)}"
    else:
        model = _polynomial(f, defined, ev, fmt)
    tex = r"\begin{gathered} " + model + r" \\ " + r",\quad ".join(v["latex"] for v in values) + r" \end{gathered}"
    info = RegressionPayload(block.names, f.degree, f.points, f.r2, model, values)
    return LineResult(i, raw, "regression", stages=[tex], block=handle, payload=info, stale=stale,
                      text="; ".join(plain) + f"  ({regression.describe(f)})"), owned


def _polynomial(f, defined, ev, fmt):
    """The fitted polynomial in the names it defined: `y = a + b x + c x^2`."""
    x = fmt.var(ev.vkey(f.x_name)) if f.x_name else "x"
    y = fmt.var(ev.vkey(f.y_name)) if f.y_name else "y"
    if len(defined) == 1 and f.degree > 0:
        base = fmt.var(defined[0][0])
        coeffs = [f"{{{base}}}_{{{k + 1}}}" for k in range(f.degree + 1)]
    else:
        coeffs = [fmt.var(key) for key, _ in defined]
    terms = [c if k == 0 else rf"{c}\,{x}" if k == 1 else rf"{c}\,{{{x}}}^{{{k}}}" for k, c in enumerate(coeffs)]
    return f"{y} = " + " + ".join(terms)


def _value(name, lhs, rhs):
    return {"name": name, "lhs": lhs, "rhs": rhs, "latex": f"{lhs} = {rhs}"}


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
    ends = [b.end for b in scan(text).blocks.values() if b.kind == "solver" and b.command not in ("regression", "symsolve")]
    if not ends:
        return []
    ws = evaluate(text, global_units=global_units, until=max(ends))
    return [r for r in ws.results if r.solver]


def _run_line(i, raw, s, ev, fmt, used):
    stmt = None
    try:
        stmt = parse_line(s)
        used |= refs(stmt).units
        if isinstance(stmt, FuncDef):
            printer = Printer(ev, fmt, local=stmt.params)
            sym = printer.tex(stmt.body)
            name = ev.symbols.define_function(stmt.name, stmt.params, stmt.body)
            key = name.key
            head = f"{fmt.var(key, function=True)}\\left({', '.join(name_latex(p) for p in stmt.params)}\\right)"
            return LineResult(i, raw, "funcdef", lhs=head, stages=[sym], text=s,
                              warning=_global_note(stmt.name, name, ev.symbols))

        expr = stmt.expr
        value = _symbolic_value(ev, expr)
        if value is not None and is_symbolic(value):
            return _symbolic_line(i, raw, stmt, value, ev, fmt)
        value = ev.settle(ev.check_finite(ev.eval(expr) if value is None else value, expr))
        literal = is_literal(expr) and not catalogue.holds_constant(value, ev.ureg)
        # A typed-in quantity or number is shown once, as typed: never rounded to the
        # sheet's figures, which only apply to what the sheet computes.
        typed = literal or _bare_number(expr)
        # Explicit `->` conversions and typed-in quantities are shown as given;
        # computed results are reduced to simple SI unless !noassume is active.
        value = catalogue.settle_ratio(value)   # mm/mm stays only on a result that is only mm/mm
        if ev.mode.assume and not (literal or isinstance(expr, Convert)):
            value = reduce_si(value, ev.ureg, ev.mode.freq)
            if ev.mode.angle == "degree" and dict(value.unit_items()) == {"radian": 1}:
                value = value.to("degree")
        stale = ev.symbols.tainted([expr])
        sym = Printer(ev, fmt).tex(expr)
        sub = Printer(ev, fmt, subst=True).tex(expr)
        sig = 12 if typed else None
        res = fmt.quantity(value, sig)
        plain = fmt.plain(value, sig)
        stages = [res] if typed or ev.mode.short else _dedupe([sym, sub, res])
        if isinstance(stmt, Assign):
            name = ev.symbols.define(stmt.name, value, text=plain, stale=stale)
            key = name.key
            return LineResult(i, raw, "assign", lhs=fmt.var(key), stages=stages,
                              text=f"{key} = {plain}", stale=stale,
                              warning=". ".join(filter(None, [_global_note(stmt.name, name, ev.symbols),
                                                       _imaginary_note(stmt.name, ev.mode)])))
        return LineResult(i, raw, "expr", stages=stages, text=plain, stale=stale)
    except Exception as e:
        return LineResult(i, raw, "error", error=describe(e))


def _symbolic_value(ev, expr):
    """For an expression that reaches a symbol (symbolic.py): its sympy expression, or the quantity
    it works out to when every symbol in it has a value. None for any other expression."""
    if not any(is_symbolic(v) for v in ev.vars.values()):
        return None
    from . import symbolic
    return symbolic.evaluate(ev, expr) if symbolic.reaches(ev, [expr]) else None


def _symbolic_line(i, raw, stmt, value, ev, fmt):
    """An expression or assignment whose result is symbolic: shown as typed, with the numbers that
    go into it, then as sympy gives it."""
    from . import symbolic
    expr = stmt.expr
    res = symbolic.latex(value, ev, fmt)
    stages = [res] if ev.mode.short else _dedupe([Printer(ev, fmt).tex(expr), Printer(ev, fmt, subst=True).tex(expr)])
    if res.replace(" ", "") != stages[-1].replace(" ", ""):   # sympy spaces some things differently: e^{- t}
        stages.append(res)
    plain = symbolic.plain(value, fmt)
    stale = ev.symbols.tainted([expr])
    if isinstance(stmt, Assign):
        name = ev.symbols.define(stmt.name, value, text=plain, stale=stale)
        return LineResult(i, raw, "assign", lhs=fmt.var(name.key), stages=stages, text=f"{name.key} = {plain}",
                          stale=stale, warning=_global_note(stmt.name, name, ev.symbols))
    return LineResult(i, raw, "expr", stages=stages, text=plain, stale=stale)


def _run_symdef(i, raw, s, ev):
    """`$a, $b` or `~$g`: declares symbols, variables whose value is a sympy Symbol (symbolic.py)."""
    try:
        stmt = parse_line(s)
        import sympy
        keys, notes = [], []
        for name in stmt.names:
            sym = ev.symbols.define(name, sympy.Symbol(name.lstrip("~")), text="symbol", symbol=True)
            keys.append(sym.key)
            notes.append(_global_note(name, sym, ev.symbols).replace(f"Write {sym.key}", f"Write ~${sym.name}"))
        text = ("symbol " if len(keys) == 1 else "symbols ") + ", ".join(keys)
        return LineResult(i, raw, "symdef", text=text, warning=". ".join(filter(None, notes)))
    except Exception as e:
        return LineResult(i, raw, "error", error=describe(e))


def _run_symsolve(i, raw, handle, ev, fmt, used):
    """A `!symsolve` line with its equations. Like a regression it is worked out every run (sympy,
    see symbolic.py); with one solution, or the one `pick:` names, its unknowns hold it below."""
    block = symsolve.parse_block(handle)

    def owned():
        return {l.n: LineResult(l.n, l.text, "error" if l.n in block.errors else "solveropt",
                                error=block.errors.get(l.n, "")) for l in handle.members}

    def fail(msg):
        return LineResult(i, raw, "error", error=msg, block=handle), owned()

    if block.problem:
        return fail(block.problem)
    for node in block.nodes():
        used |= refs(node).units
    from . import symbolic   # sympy, imported only for a sheet that uses it
    try:
        sols = symbolic.solve(block, ev)
    except Exception as e:
        return fail(describe(e))
    if not sols:
        return fail(f"No solution: sympy finds none for {', '.join(block.unknowns)}")
    if block.pick is not None and block.pick > len(sols):
        n = len(sols)
        block.errors[block.pick_line] = f"There {'is' if n == 1 else 'are'} only {n} solution{'s' * (n != 1)}"
        return fail(block.errors[block.pick_line])
    stale = ev.symbols.tainted(block.nodes())

    def row(sol):
        return r",\; ".join(f"{fmt.var(k)} = {symbolic.latex(v, ev, fmt)}" for k, v in sol.items())

    def text(sol):
        return ", ".join(f"{k} = {symbolic.plain(v, fmt)}" for k, v in sol.items())
    if len(sols) == 1:
        tex, plain = row(sols[0]), text(sols[0])
    else:
        tex = (r"\begin{gathered} " + r" \\ ".join(rf"\text{{({k})}}\quad {row(sol)}" for k, sol in enumerate(sols, 1))
               + r" \end{gathered}")
        plain = "; ".join(f"({k}) {text(sol)}" for k, sol in enumerate(sols, 1))
    warning = ""
    chosen = sols[0] if len(sols) == 1 else sols[block.pick - 1] if block.pick else None
    if chosen is None:
        names = ", ".join(block.unknowns)
        warning = (f"{len(sols)} solutions, so {names} {'stays a symbol' if len(block.unknowns) == 1 else 'stay symbols'} "
                   f"below. Add `pick: 1` (or another number) to use one")
    else:
        for key, v in chosen.items():   # below the block, the unknowns hold the solution, as after !root
            if not symbolic.symbols_in(v):
                v = ev.settle(symbolic.to_quantity(ev, v))
                ev.symbols.define(key, v, text=fmt.plain(v), stale=stale)
            elif v != ev.vars.get(key):
                ev.symbols.define(key, v, text=symbolic.plain(v, fmt), stale=stale)
    return LineResult(i, raw, "symsolve", stages=[tex], text=plain, block=handle, stale=stale,
                      warning=warning), owned()


def _bare_number(expr):
    """`3.14159`, `-2.5`: a real number typed on its own. An imaginary one (`4i`) is
    left to the usual stages, since `!complex polar` shows it differently from how it was typed."""
    n = expr.operand if isinstance(expr, Neg) else expr
    return isinstance(n, Num) and not isinstance(n.value, complex)


def _add_notes(r, notes):
    """Join the evaluator's notes for a line to its own warnings (`_global_note`,
    `_imaginary_note`). A line that failed shows its error alone."""
    if notes and r.kind != "error":
        r.warning = ". ".join(filter(None, [r.warning, *notes]))


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


def describe(e):
    """An exception as the message a line shows for it."""
    if isinstance(e, (ParseError, EvalError, PlotError, SolverError, RegressionError, ScopeError)):
        return str(e)
    if isinstance(e, pint.errors.DimensionalityError):
        dims = [d for dim in (e.dim1, e.dim2) for d in re.findall(r"\[(\w+)\]", str(dim))]
        return catalogue.mismatch(dims) or f"Incompatible units: {e}"
    if isinstance(e, pint.errors.PintError):
        return str(e)
    if isinstance(e, ZeroDivisionError):
        return "Division by zero"
    return f"{type(e).__name__}: {e}"
