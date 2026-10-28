"""Symbolic math through sympy: symbols declared with `$`, expressions over them, and solving
`!symsolve` blocks (read by symsolve.py).

    $m, $a, $F                a declaration: m, a and F are symbols (`~$g` declares a global one)
    p = m*a                   p holds the expression m·a, and the sheet shows it as math
    !symsolve a               solve equations for symbols; with one solution (or `pick: n`)
      equation: F = m*a       the unknowns hold it below the block: a = F/m
    m = 2'kg                  a symbol given a value is a number from here on, so
    F = 10'N
    acc = a                   a = F/m is worked out with Pint: 5 m/s²

A symbol is a variable whose value is a sympy Symbol (symbols.py keeps it like any other value).
An expression that reaches one is built as a sympy expression from the same AST the evaluator
and the LaTeX printer read (`build`), never from text. While it is built, each number with units
(a variable, a typed quantity, a call sympy does not know) is held as a `Value`, a stand-in
symbol that carries its Pint quantity, so Pint and not sympy does unit arithmetic:

- when no symbol is left, the expression is worked out with Pint (`to_quantity`), units and all;
- when symbols are left, the result is symbolic. A dimensionless number goes into it as a sympy
  number; a number with units, or a matrix, is an error, since a symbolic result has no units.

Symbols bind late: when a stored expression is used, each symbol in it takes the value of the
variable of that name where it is used (`resolve`): below `m = 2'kg`, in a plot over m, or as a
function's parameter m. A symbol that has no value there stays a symbol.

Symbolic trig works in radians, so a trig function of a symbol is an error below `!trigdeg`.

sympy takes a moment to import, so this module is imported only when a sheet declares a symbol."""
from collections import ChainMap

import numpy as np
import sympy as sp
from sympy.printing.latex import LatexPrinter
from sympy.printing.precedence import PRECEDENCE
from sympy.printing.str import StrPrinter

from .evaluator import EvalError, is_symbolic
from .functions import FUNCTIONS
from .latex import ADD, ATOM, MUL, POW, name_latex
from .nodes import Str


class Value(sp.Dummy):
    """A number from the sheet inside a sympy expression: a stand-in symbol that carries its Pint
    quantity `q`. `label` names where it came from, for messages; `named` when that is a variable."""

    def __new__(cls, label, q, named=False):
        obj = super().__new__(cls, label)
        obj.q, obj.label, obj.named = q, label, named
        return obj

    @property
    def precedence(self):
        """How tightly it binds as printed (sympy's scale), so sympy parenthesizes it like
        latex.Printer would: a negative or two-part complex number binds as a sum, a number with
        units or in scientific notation as a product."""
        m = np.asarray(self.q.magnitude)
        if m.ndim:
            return PRECEDENCE["Atom"]
        if np.iscomplexobj(m):
            z = complex(m)
            return PRECEDENCE["Add"] if (z.real and z.imag) or (z.real or z.imag) < 0 else PRECEDENCE["Mul"]
        x = float(m)
        if x < 0:
            return PRECEDENCE["Add"]
        if not self.q.dimensionless or (x and not 1e-4 <= abs(x) < 1e7):
            return PRECEDENCE["Mul"]
        return PRECEDENCE["Atom"]


def symbols_in(expr):
    """The symbols left in `expr`: its free symbols that are not stand-ins for numbers."""
    return {s for s in expr.free_symbols if not isinstance(s, Value)}


def number(v):
    """A Python number as an exact sympy number where it is one: 2.0 -> 2, 0.5 -> 0.5 (a Float)."""
    if isinstance(v, complex) or np.iscomplexobj(v):
        z = complex(v)
        return number(z.real) + number(z.imag) * sp.I if z.imag else number(z.real)
    v = float(v)
    if np.isinf(v):
        return sp.oo if v > 0 else -sp.oo
    if v.is_integer() and abs(v) < 1e15:
        return sp.Integer(int(v))
    return sp.Float(v)


# ---- binding symbols to the sheet's values -----------------------------------------------------
def _lookup(ev, name, scope):
    if name in scope:
        return scope[name]
    return scope.get(ev.vkey(name))


def resolve(ev, expr, scope, seen=frozenset()):
    """`expr` with each symbol that has a value in `scope` (by its name, as `ev` keys it) replaced:
    by a Value for a number, by that expression (resolved in turn) for a symbolic one."""
    rep = {}
    for s in symbols_in(expr):
        if s.name in seen:
            continue
        v = _lookup(ev, s.name, scope)
        if v is None or (is_symbolic(v) and v == s):
            continue
        rep[s] = resolve(ev, v, scope, seen | {s.name}) if is_symbolic(v) else Value(s.name, v, named=True)
    return expr.xreplace(rep) if rep else expr


def numeric(ev, name, value, scope):
    """The quantity a symbolic variable `name` stands for in `scope`, for the numeric evaluator
    (a plot, a solver, a calculation that only uses it). Its symbols must all have values there."""
    r = resolve(ev, value, scope)
    left = sorted(s.name for s in symbols_in(r))
    if left:
        if left == [name.lstrip("~")]:
            raise EvalError(f"'{name}' is a symbol and has no value here")
        names = ", ".join(left)
        raise EvalError(f"'{name}' is symbolic: {names} in it {'has' if len(left) == 1 else 'have'} "
                        f"no value here. Give {'it' if len(left) == 1 else 'them'} values above this line")
    return to_quantity(ev, r)


def reaches(ev, nodes):
    """True if evaluating `nodes` reads a symbolic value (directly or through user functions)."""
    vals = ev.vars
    return any(kind == "var" and key in vals and is_symbolic(vals[key])
               for kind, key, _ in ev.symbols.reach(nodes))


# ---- AST -> sympy ------------------------------------------------------------------------------
def _heaviside(x):
    return sp.Heaviside(x, 1)   # 1 at zero, as the sheet's heaviside


_FUNCS = {"sqrt": sp.sqrt, "abs": sp.Abs, "floor": sp.floor, "ceil": sp.ceiling,
          "heaviside": _heaviside, "step": _heaviside, "heav": _heaviside,
          "sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "asin": sp.asin, "acos": sp.acos, "atan": sp.atan,
          "exp": sp.exp, "ln": sp.log, "log10": lambda x: sp.log(x, 10),
          "re": sp.re, "im": sp.im, "conj": sp.conjugate, "arg": sp.arg}
_ANGLES = {"sin", "cos", "tan", "asin", "acos", "atan", "arg"}
_CONSTANTS = {"pi": sp.pi, "e": sp.E, "∞": sp.oo}


class Builder:
    """Builds the sympy expression for an AST node. `scope` is what names mean (the sheet's values,
    or a plot's); `local` holds a user function's parameters, bound to sympy expressions."""

    def __init__(self, ev, scope=None, local=None):
        self.ev = ev
        self.scope = ev.vars if scope is None else scope
        self.local = local or {}
        self.names = ChainMap(self.local, self.scope)

    def build(self, n):
        return getattr(self, "b_" + type(n).__name__)(n)

    def numeric(self, n, label, named=False):
        """`n` worked out by the numeric evaluator, as a Value."""
        return Value(label, self.ev.eval(n, dict(self.names)), named)

    def fallback(self, n, parts, what):
        """A node sympy has no form for: fine as a number, an error with a symbol in it."""
        left = set().union(*(symbols_in(p) for p in parts)) if parts else set()
        if left:
            raise EvalError(f"{what} takes numbers only, and {', '.join(sorted(s.name for s in left))} "
                            f"{'is a symbol' if len(left) == 1 else 'are symbols'} here")
        return self.numeric(n, what)

    def b_Num(self, n):
        return number(n.value)

    def b_Str(self, n):
        return self.ev.ev_Str(n, self.scope)

    def b_Name(self, n):
        v = _lookup(self.ev, n.name, self.names)
        if v is not None:
            return resolve(self.ev, v, self.names) if is_symbolic(v) else Value(n.name, v, named=True)
        if n.name in _CONSTANTS:
            return _CONSTANTS[n.name]
        return self.ev.ev_Name(n, self.scope)   # raises the evaluator's own message

    def b_UnitLit(self, n):
        return self.numeric(n, "'" + n.unit)

    def b_Implicit(self, n):
        return self.numeric(n, "a typed quantity")

    def b_Neg(self, n):
        return -self.build(n.operand)

    def b_BinOp(self, n):
        a, b = self.build(n.left), self.build(n.right)
        if n.op == "+":
            return a + b
        if n.op == "-":
            return a - b
        if n.op == "*":
            return a * b
        if n.op == "/":
            if b == 0:
                raise EvalError("Division by zero")
            return a / b
        if n.op == "^":
            return a ** b
        return self.fallback(n, (a, b), n.op)

    def b_Polar(self, n):
        return self.fallback(n, (self.build(n.magnitude), self.build(n.angle)), "∠")

    def b_Matrix(self, n):
        return self.fallback(n, [self.build(e) for row in n.rows for e in row], "A matrix")

    def b_Convert(self, n):
        return self.fallback(n, (self.build(n.expr),), "-> (a symbolic result has no units to convert)")

    def b_Call(self, n):
        ev, f = self.ev, n.func
        fkey = ev.fkey(f)
        if fkey in ev.funcs:
            params, body = ev.funcs[fkey]
            if any(isinstance(a, Str) for a in n.args):
                raise EvalError(f"{f} is a user function and cannot take text")
            if len(n.args) != len(params):
                raise EvalError(f"{f} takes {len(params)} argument(s), got {len(n.args)}")
            args = [self.build(a) for a in n.args]
            ev._calls.append(f)
            try:
                return Builder(ev, self.scope, dict(zip(params, args))).build(body)
            finally:
                ev._calls.pop()
        if f not in _FUNCS or any(isinstance(a, Str) for a in n.args):
            parts = [self.build(a) for a in n.args if not isinstance(a, Str)]
            return self.fallback(n, parts, f"{f}()")
        if len(n.args) != 1:
            raise EvalError(f"Wrong number of arguments for {f}")
        x = self.build(n.args[0])
        degrees = ev.mode.angle == "degree" and f in _ANGLES
        if symbols_in(x):
            if degrees:
                raise EvalError(f"{f}() of a symbol works in radians, and !trigdeg is on. "
                                f"Use !trigrad above this line")
            return _FUNCS[f](x)
        if degrees or x.atoms(Value):
            return self.numeric(n, f"{f}()")   # numbers: the evaluator's own rules (units, !trigdeg)
        return _FUNCS[f](x)                    # exact numbers stay exact: sqrt(2)


def build(ev, node, scope=None):
    return Builder(ev, scope).build(node)


def to_symbolic(expr):
    """`expr` with every Value put in as a sympy number. A Value with units or a matrix cannot be."""
    rep = {}
    for v in expr.atoms(Value):
        q = v.q
        if np.ndim(q.magnitude):
            raise EvalError("A symbolic expression holds single numbers, and "
                            + (f"{v.label} is a matrix" if v.named else "this one has a matrix in it"))
        if not q.dimensionless:
            if v.named:
                raise EvalError(f"{v.label} ({float(np.real(q.magnitude)):g} {q.units:~P}) has units, and a symbolic "
                                f"result cannot carry units. Declare {v.label} a symbol too (${v.label}), or give "
                                f"the symbols values above this line")
            raise EvalError(f"A symbolic result cannot carry units, and {v.label} has them. Give the symbols "
                            f"values above this line to work it out with units")
        rep[v] = number(q.to("dimensionless").magnitude)
    return expr.xreplace(rep) if rep else expr


def evaluate(ev, node):
    """A line's expression that reaches a symbol: a sympy expression when symbols are left in it,
    else the quantity it works out to (with units, by Pint)."""
    out = build(ev, node)
    if not symbols_in(out):
        return to_quantity(ev, out)
    out = to_symbolic(out)
    if out.has(sp.zoo, sp.nan):
        raise EvalError("Result is not finite (division by zero or domain error)")
    return out


# ---- sympy -> a Pint quantity ------------------------------------------------------------------
def _radians(q):
    return q.to("radian").magnitude


def _num(ev, x):
    if x is sp.zoo or x is sp.nan:
        raise EvalError("Result is not finite (division by zero or domain error)")
    if x is sp.oo or x is -sp.oo:
        return ev.Q(float(x))
    z = complex(x.evalf())
    return ev.Q(z.real if z.imag == 0 else z)


def to_quantity(ev, expr):
    """Work out a sympy expression with no symbols left in it. Its Values carry their units."""
    q = lambda e: to_quantity(ev, e)
    if isinstance(expr, Value):
        return expr.q
    if isinstance(expr, sp.Symbol):
        raise EvalError(f"'{expr.name}' is a symbol and has no value here")
    if expr.is_number and not expr.atoms(Value):
        return _num(ev, expr)
    if expr.is_Add:
        out = q(expr.args[0])
        for a in expr.args[1:]:
            b = q(a)
            out = ev._shape_guard(lambda: out + b, out, b, "+")
        return out
    if expr.is_Mul:
        out = q(expr.args[0])
        for a in expr.args[1:]:
            out = ev.mul(out, q(a))
        return out
    if expr.is_Pow:
        return ev.power(q(expr.base), q(expr.exp))
    f = type(expr)
    args = [q(a) for a in expr.args]
    if f in (sp.sin, sp.cos, sp.tan):
        return ev.Q(getattr(np, f.__name__)(_radians(args[0])))
    if f in (sp.asin, sp.acos, sp.atan):
        return ev.Q(getattr(np, "arc" + f.__name__[1:])(ev._dimless(args[0], f.__name__)), "radian")
    if f is sp.arg:
        return ev.Q(np.angle(args[0].magnitude), "radian")
    by_sympy = {sp.exp: "exp", sp.log: "ln", sp.Abs: "abs", sp.floor: "floor", sp.ceiling: "ceil",
                sp.Heaviside: "heaviside", sp.re: "re", sp.im: "im", sp.conjugate: "conj"}
    if f in by_sympy:
        return FUNCTIONS[by_sympy[f]].impl(ev, args[0])
    raise EvalError(f"{f.__name__} cannot be worked out as a number here")


# ---- printing ----------------------------------------------------------------------------------
class _Latex(LatexPrinter):
    """sympy's LaTeX, with the sheet's names, numbers and imaginary unit."""

    def __init__(self, ev, fmt):
        super().__init__({"mul_symbol": "dot", "ln_notation": True, "inv_trig_style": "full", "imaginary_unit": "ri"})
        self.ev, self.fmt = ev, fmt

    def _print_Value(self, e):
        from .latex import Printer
        return Printer(self.ev, self.fmt).value(e.q)[0]

    def _print_Symbol(self, e, style="plain"):
        key = self.ev.vkey(e.name)
        return self.fmt.var(key) if key in self.ev.vars else name_latex(e.name)

    def _print_Float(self, e):
        return self.fmt.number(float(e))

    def _print_Heaviside(self, e, exp=None):
        tex = rf"\operatorname{{H}}\left({self._print(e.args[0])}\right)"
        return f"{tex}^{{{exp}}}" if exp else tex

    def _print_re(self, e, exp=None):
        return rf"\operatorname{{Re}}\left({self._print(e.args[0])}\right)"

    def _print_im(self, e, exp=None):
        return rf"\operatorname{{Im}}\left({self._print(e.args[0])}\right)"


class _Plain(StrPrinter):
    def __init__(self, fmt):
        super().__init__()
        self.fmt = fmt

    def _print_Value(self, e):
        return self.fmt.plain(e.q)

    def _print_Symbol(self, e):
        return e.name

    def _print_Float(self, e):
        return self.fmt._plain_number(float(e))

    def _print_ImaginaryUnit(self, e):
        return "i"


def latex(expr, ev, fmt):
    return _Latex(ev, fmt).doprint(expr)


def plain(expr, fmt):
    return _Plain(fmt).doprint(expr).replace("**", "^")


def level(expr):
    """How tightly `expr` binds as latex() prints it, on latex.py's scale (ADD .. ATOM)."""
    if isinstance(expr, Value):
        return {PRECEDENCE["Add"]: ADD, PRECEDENCE["Mul"]: MUL}.get(expr.precedence, ATOM)
    if expr.is_Add or expr.could_extract_minus_sign():
        return ADD
    if expr.is_Mul:
        return MUL
    if expr.is_Pow or (expr.is_Rational and not expr.is_Integer):
        return POW
    return ATOM


def substituted(ev, fmt, key, value):
    """A symbolic variable as the substituted stage of a line shows it: what it stands for here,
    numbers in place (with their units). Returns (tex, level)."""
    r = resolve(ev, value, ev.vars)
    if isinstance(r, sp.Symbol) and not isinstance(r, Value):
        return fmt.var(key), ATOM
    return latex(r, ev, fmt), level(r)


# ---- !symsolve ---------------------------------------------------------------------------------
_SOLVED = {}   # (equations, unknowns) as srepr text -> sympy's solutions; a sheet runs on every edit


def solve(block, ev):
    """The block's solutions: a list of {unknown key: sympy expression}. Raises EvalError, or puts
    a message for one equation line in `block.errors` and raises EvalError for the block."""
    syms, keys = [], []
    for name in block.unknowns:
        key, bare = ev.vkey(name), name.lstrip("~")
        v = ev.vars.get(key)
        if not (isinstance(v, sp.Symbol) and not isinstance(v, Value) and v.name == bare):
            what = "is not defined" if v is None else "is not a symbol here"
            raise EvalError(f"'{name}' {what}. Declare it as a symbol above the block: ${bare}")
        syms.append(v)
        keys.append(key)
    eqs = []
    for n, lhs, rhs in block.equations:
        try:
            e = build(ev, lhs) - (build(ev, rhs) if rhs is not None else 0)
            e = to_symbolic(e)
            if not symbols_in(e) & set(syms):
                raise EvalError("This equation has none of the unknowns in it" if symbols_in(e) or e != 0
                                else "This equation holds whatever the unknowns are")
        except EvalError as err:
            block.errors[n] = str(err)
            continue
        eqs.append(e)
    if block.errors:
        raise EvalError("An equation below needs fixing")
    k = (tuple(sp.srepr(e) for e in eqs), tuple(sp.srepr(s) for s in syms))
    if k not in _SOLVED:
        try:
            found = sp.solve(eqs, syms, dict=True)
        except NotImplementedError as err:
            raise EvalError(f"sympy cannot solve this: {err}") from None
        if len(_SOLVED) > 256:
            _SOLVED.clear()
        _SOLVED[k] = found
    return [{key: sol.get(s, s) for key, s in zip(keys, syms)} for sol in _SOLVED[k]]
