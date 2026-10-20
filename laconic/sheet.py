"""Runs a whole worksheet top to bottom. Each line either produces a result or
an error; an error never stops later lines (lines that depend on a failed
variable fail on their own with 'x is not defined')."""
import math
from dataclasses import asdict, dataclass, field, fields, is_dataclass

import pint

from .evaluator import EvalError, Evaluator
from .latex import Fmt, Printer, escape, name_latex
from .nodes import (Assign, BinOp, Convert, FuncDef, Implicit, Neg, Num,
                    UnitDef, UnitLit)
from .si import reduce_si
from .parser import ParseError, parse_expr, parse_line


@dataclass
class LineResult:
    n: int
    source: str
    kind: str  # blank comment heading meta command assign expr funcdef unitdef error
    lhs: str = ""
    stages: list = field(default_factory=list)
    text: str = ""
    error: str = ""

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


def evaluate(text, siunitx=False, global_units=None):
    """`global_units` are the instance's (name, definition) pairs. Units are
    defined before any line is evaluated, so a definition applies to the whole
    sheet, wherever it sits."""
    lines = text.splitlines()
    has_defs = any(s.startswith("'") and "=" in s for s in (l.strip() for l in lines))
    ev = Evaluator(global_units or (), fork=has_defs)
    fmt = Fmt(ev.ureg, siunitx=siunitx, custom=ev.custom)
    defs, here, used = {}, {}, set()
    for i, raw in enumerate(lines, 1):
        s = raw.strip()
        if s.startswith("'") and "=" in s:
            defs[i] = _define_unit(i, raw, s, ev, fmt, here, used)
    results = []
    for i, raw in enumerate(lines, 1):
        s = raw.strip()
        if i in defs:
            results.append(defs[i])
        elif not s:
            results.append(LineResult(i, raw, "blank"))
        elif s.startswith("##"):
            results.append(LineResult(i, raw, "heading", text=s[2:].strip()))
        elif s.startswith("#@"):
            results.append(LineResult(i, raw, "meta", text=s[2:].strip()))
        elif s.startswith("#"):
            results.append(LineResult(i, raw, "comment", text=s[1:].strip()))
        elif s.startswith("!"):
            results.append(_run_command(i, raw, s, ev))
        else:
            results.append(_run_line(i, raw, s, ev, fmt, used))
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
        return LineResult(i, raw, "error", error=_describe(e, stmt, ev))


def _run_command(i, raw, s, ev):
    """`!clear` removes every variable whose name does not start with ~.
    `!clearf` does the same for user functions. `!noassume` keeps computed results in the
    units that came out of the arithmetic instead of reducing them to SI, until
    `!assume` restores the default."""
    parts = s[1:].split()
    name = parts[0] if parts else ""
    if name not in ("clear", "clearf", "assume", "noassume"):
        return LineResult(i, raw, "error",
                          error=f"Unknown command '!{name}'. Available: !clear, !clearf, !assume, !noassume")
    if len(parts) > 1:
        return LineResult(i, raw, "error", error=f"!{name} takes no arguments")
    if name in ("assume", "noassume"):
        ev.assume = name == "assume"
        text = "Units are reduced to SI again" if ev.assume else "Units are kept as typed unless converted with ->"
        return LineResult(i, raw, "command", text=text)
    if name == "clearf":
        gone = [n for n in ev.funcs if not n.startswith("~")]
        for n in gone:
            del ev.funcs[n]
        ev.cleared_funcs.update(gone)
        text = f"Cleared {', '.join(gone)}" if gone else "Nothing to clear"
        return LineResult(i, raw, "command", text=text)
    gone = [n for n in ev.vars if not n.startswith("~")]
    for n in gone:
        del ev.vars[n]
    ev.cleared.update(gone)
    text = f"Cleared {', '.join(gone)}" if gone else "Nothing to clear"
    return LineResult(i, raw, "command", text=text)


def _run_line(i, raw, s, ev, fmt, used):
    stmt = None
    try:
        stmt = parse_line(s)
        used |= _unit_names(stmt)
        if isinstance(stmt, FuncDef):
            printer = Printer(ev, fmt, local=stmt.params)
            sym = printer.tex(stmt.body)
            ev.funcs[stmt.name] = (stmt.params, stmt.body)
            head = f"{name_latex(stmt.name)}\\left({', '.join(name_latex(p) for p in stmt.params)}\\right)"
            return LineResult(i, raw, "funcdef", lhs=head, stages=[sym], text=s)

        expr = stmt.expr
        value = ev.check_finite(ev.eval(expr))
        literal = _is_literal(expr, ev)
        # Explicit `->` conversions and typed-in quantities are shown as given;
        # computed results are reduced to simple SI unless !noassume is active.
        if ev.assume and not (literal or isinstance(expr, Convert)):
            value = reduce_si(value, ev.ureg)
        sym = Printer(ev, fmt).tex(expr)
        sub = Printer(ev, fmt, subst=True).tex(expr)
        res = fmt.quantity(value)
        stages = [res] if literal else _dedupe([sym, sub, res])
        if isinstance(stmt, Assign):
            ev.vars[stmt.name] = value
            return LineResult(i, raw, "assign", lhs=name_latex(stmt.name), stages=stages,
                              text=f"{stmt.name} = {fmt.plain(value)}")
        return LineResult(i, raw, "expr", stages=stages, text=fmt.plain(value))
    except Exception as e:
        return LineResult(i, raw, "error", error=_describe(e, stmt, ev))


def _describe(e, stmt, ev):
    if isinstance(e, (ParseError, EvalError)):
        return str(e)
    if isinstance(e, pint.errors.DimensionalityError):
        return f"Incompatible units: {e}"
    if isinstance(e, pint.errors.PintError):
        return str(e)
    if isinstance(e, ZeroDivisionError):
        return "Division by zero"
    return f"{type(e).__name__}: {e}"
