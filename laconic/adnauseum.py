"""The working of a line under `!adnauseum`: every intermediate result and every unit that cancels.

`steps(ev, fmt, expr, raw)` gives the stages that go between a line's substituted form and its
result. The tree is worked out one level at a time, innermost first: each stage replaces every
operation whose operands are already numbers with the number it gives. Before a product or a
quotient of two quantities whose units cancel, a stage shows the numbers and the units apart,
with the cancelled units struck through. Last, when the result is shown in other units than the
arithmetic gave (`kN·m` as `J`), the arithmetic's unit is written out in SI base units and
cancelled down."""
from collections import defaultdict
from fractions import Fraction

import numpy as np

from .latex import MUL, Printer
from .nodes import BinOp, Call, Convert, Implicit, Matrix, Neg, Polar, is_literal


def _children(n):
    if isinstance(n, Neg):
        return [n.operand]
    if isinstance(n, BinOp):
        return [] if is_literal(n) else [n.left, n.right]
    if isinstance(n, Polar):
        return [n.magnitude, n.angle]
    if isinstance(n, Call):
        return list(n.args)
    if isinstance(n, Matrix):
        return [e for row in n.rows for e in row]
    return []   # numbers, names, units and typed-in quantities are shown as they are


def _heights(node, out):
    """Each operation's height in the tree (a leaf is 0), by id, into `out`; returns the node's."""
    kids = _children(node)
    h = 1 + max(_heights(k, out) for k in kids) if kids else 0
    if kids:
        out[id(node)] = (h, node)
    return h


class _Stepper(Printer):
    """The substituted printer, with the operations in `known` shown as the values they gave,
    and those in `cancel` as their numbers then their units, cancelled."""
    def __init__(self, ev, fmt, known, cancel=()):
        super().__init__(ev, fmt, subst=True)
        self.known, self.cancel = known, set(cancel)

    def p(self, n):
        if id(n) in self.known:
            return self.value(self.known[id(n)])
        if id(n) in self.cancel:
            return self.cancelled(n)
        return super().p(n)

    def cancelled(self, n):
        a, b = self.ev.eval(n.left), self.ev.eval(n.right)
        sa, sb = (self.value(self.ev.Q(q.magnitude)) for q in (a, b))
        num = f"\\frac{{{sa[0]}}}{{{sb[0]}}}" if n.op == "/" else \
            f"{self.child_tex(sa, MUL)} \\cdot {self.child_tex(sb, MUL)}"
        sign = -1 if n.op == "/" else 1
        factors = list(a.unit_items()) + [(u, sign * e) for u, e in b.unit_items()]
        return f"{num}\\,{units(self.fmt, self.ev.ureg, factors)}", MUL

    @staticmethod
    def child_tex(s, need):
        return f"\\left({s[0]}\\right)" if s[1] < need else s[0]


def _cancels(ev, n):
    """Whether `n` is a product or quotient of two scalar quantities with a unit in common
    that cancels."""
    if not (isinstance(n, BinOp) and n.op in ("*", "/")):
        return False
    try:
        a, b = ev.eval(n.left), ev.eval(n.right)
    except Exception:
        return False
    if np.ndim(a.magnitude) or np.ndim(b.magnitude):
        return False
    left, right = dict(a.unit_items()), dict(b.unit_items())
    if n.op == "*":
        right = {u: -e for u, e in right.items()}
    return any(u in right and (e > 0) == (right[u] > 0) for u, e in left.items())


def _power(e):
    f = Fraction(e).limit_denominator(100)
    return str(f.numerator) if f.denominator == 1 else f"{f.numerator}/{f.denominator}"


def _factor(fmt, ureg, name, exp, struck=False):
    tex = fmt.unit_inline(ureg.Unit(name))
    if exp != 1:
        tex = f"{{{tex}}}^{{{_power(exp)}}}"
    return f"\\cancel{{{tex}}}" if struck else tex


def units(fmt, ureg, factors):
    """`factors`, (unit name, exponent) pairs as the arithmetic met them, as one fraction with
    each unit that is both above and below the line struck through as far as it cancels."""
    up, down = defaultdict(float), defaultdict(float)
    for name, e in factors:
        (up if e > 0 else down)[name] += abs(e)
    above, below = [], []
    for name in list(up) + [n for n in down if n not in up]:
        gone = min(up.get(name, 0), down.get(name, 0))
        for side, total in ((above, up.get(name, 0)), (below, down.get(name, 0))):
            if total - gone > 1e-12:
                side.append(_factor(fmt, ureg, name, total - gone))
            if gone:
                side.append(_factor(fmt, ureg, name, gone, struck=True))
    top, bottom = " \\cdot ".join(above) or "1", " \\cdot ".join(below)
    return f"\\frac{{{top}}}{{{bottom}}}" if bottom else top


def _base(ev, fmt, raw):
    """`raw` with its unit written out in SI base units, unit by unit, and cancelled; then in
    the base units that are left."""
    ureg = ev.ureg
    factors = []
    for name, e in raw.unit_items():
        factors += [(b, be * e) for b, be in ureg.Quantity(1, name).to_base_units().unit_items()]
    base = raw.to_base_units()
    mag = Printer(ev, fmt).value(ev.Q(base.magnitude))[0]
    return [f"{mag}\\,{units(fmt, ureg, factors)}", fmt.quantity(base)]


def steps(ev, fmt, expr, raw, result):
    """The stages between `expr` substituted and its result `result` (as the line shows it):
    `raw` is what the arithmetic gave before the result was put in the units it is shown in."""
    tree = expr.expr if isinstance(expr, Convert) else expr
    ops = {}
    _heights(tree, ops)
    known, out = {}, []
    for level in range(1, max((h for h, _ in ops.values()), default=0) + 1):
        now = [n for h, n in ops.values() if h == level]
        cancel = [id(n) for n in now if _cancels(ev, n)]
        if cancel:
            out.append(_Stepper(ev, fmt, known, cancel).tex(tree))
        for n in now:
            known[id(n)] = ev.eval(n)
        out.append(_Stepper(ev, fmt, known).tex(tree))
    if raw.unit_items() and raw.units != result.units:
        try:
            out += _base(ev, fmt, raw)
        except Exception:   # an offset unit, degC, has no product form to cancel
            pass
    return out
