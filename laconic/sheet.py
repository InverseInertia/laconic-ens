"""Runs a whole worksheet top to bottom. Each line either produces a result or
an error; an error never stops later lines (lines that depend on a failed
variable fail on their own with 'x is not defined')."""
from dataclasses import asdict, dataclass, field

import numpy as np
import pint

from .evaluator import EvalError, Evaluator
from .latex import Fmt, Printer, name_latex
from .nodes import Assign, BinOp, Convert, FuncDef, Implicit, Neg, Num, UnitLit
from .si import reduce_si
from .parser import ParseError, parse_line


@dataclass
class LineResult:
    n: int
    source: str
    kind: str  # blank comment heading command assign expr funcdef error
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


def run(text, siunitx=False):
    ev = Evaluator()
    fmt = Fmt(ev.ureg, siunitx=siunitx)
    results = []
    for i, raw in enumerate(text.splitlines(), 1):
        s = raw.strip()
        if not s:
            results.append(LineResult(i, raw, "blank"))
        elif s.startswith("##"):
            results.append(LineResult(i, raw, "heading", text=s[2:].strip()))
        elif s.startswith("#"):
            results.append(LineResult(i, raw, "comment", text=s[1:].strip()))
        elif s.startswith("!"):
            results.append(_run_command(i, raw, s, ev))
        else:
            results.append(_run_line(i, raw, s, ev, fmt))
    return results


def _run_command(i, raw, s, ev):
    """`!clear` removes every variable whose name does not start with ~.
    User functions are left alone."""
    parts = s[1:].split()
    name = parts[0] if parts else ""
    if name != "clear":
        return LineResult(i, raw, "error", error=f"Unknown command '!{name}'. Available: !clear")
    if len(parts) > 1:
        return LineResult(i, raw, "error", error="!clear takes no arguments")
    gone = [n for n in ev.vars if not n.startswith("~")]
    for n in gone:
        del ev.vars[n]
    ev.cleared.update(gone)
    text = f"Cleared {', '.join(gone)}" if gone else "Nothing to clear"
    return LineResult(i, raw, "command", text=text)


def _run_line(i, raw, s, ev, fmt):
    stmt = None
    try:
        stmt = parse_line(s)
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
        # computed results are reduced to simple SI.
        if not (literal or isinstance(expr, Convert)):
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
