"""Expressions compiled to plain numbers: the solver's fast path (solver.py).

A solver evaluates the same equations hundreds of times with only its unknowns changing. Evaluated
the usual way (evaluator.py), every step builds and checks a quantity with units, which is most of
the time a solve takes. Once the first evaluation has checked the units, the same expressions can run
on plain numbers in SI base units instead: unit literals become constant factors, the sheet's values
their SI magnitudes, and the unknowns arrive as SI magnitudes.

    compile(node, ev, unknowns)  a function of {unknown key: SI magnitude} giving the expression's SI
                                 magnitude, or raises Unsupported when the expression has something this
                                 does not do (text, an offset unit such as 'degC, a symbol, a complex
                                 number); the solver then keeps to the usual evaluation.

It follows the evaluator's rules: `*` multiplies matrices unless both sides are lanes of a `.f(...)`
running on whole vectors, `.f(...)` runs f once on whole vectors when every step of it acts element by
element (evaluator.LANE_SAFE) and else once per element, a name is a parameter, an unknown, a value of
the sheet or a constant. A built-in is called through the evaluator's own implementation, on numbers
without units, and its answer taken in SI base units (so an angle comes back in radians), which keeps
one implementation of each. The solver checks the first answer against the usual evaluation and keeps
to that one if they differ, so what this gets wrong costs speed, not a wrong answer."""
import numpy as np

from .evaluator import CONSTANTS, FUNCTIONS, LANE_SAFE, LANE_TABLE, _offset, is_complex
from .nodes import BinOp, Call, Convert, Implicit, Matrix, Name, Neg, Num, UnitLit


def _pick(M, i, j):
    return np.asarray(M)[np.asarray(i).astype(int) - 1, np.asarray(j).astype(int) - 1]


# Built-ins as plain numpy on SI numbers, for those whose answer does not depend on units: the same
# as the evaluator's (sum adds every element, transpose makes a vector two-dimensional, heaviside is 1 at
# zero). The others go through the evaluator's own, on numbers without units.
NATIVE = {
    "transpose": lambda A: np.atleast_2d(A).T, "sum": lambda A: float(np.sum(A)), "mean": lambda A: float(np.mean(A)),
    "min": lambda A: float(np.min(A)), "max": lambda A: float(np.max(A)),
    "rows": lambda A: float(np.atleast_2d(A).shape[0]), "cols": lambda A: float(np.atleast_2d(A).shape[1]),
    "length": lambda A: float(np.size(A)),
    "abs": np.abs, "sqrt": np.sqrt, "exp": np.exp, "ln": np.log, "log10": np.log10,
    "heaviside": lambda x: np.heaviside(x, 1.0), "step": lambda x: np.heaviside(x, 1.0), "heav": lambda x: np.heaviside(x, 1.0),
    "maximum": np.maximum, "minimum": np.minimum, "clip": np.clip, "sign": np.sign,
    "where": lambda c, a, b: np.where(np.asarray(c) != 0, a, b), "pick": _pick,
    "floor": np.floor, "ceil": np.ceil,
}


class Unsupported(Exception):
    """Something compile() does not do: the expression is evaluated the usual way."""


class _NoLanes(Exception):
    """A body that cannot run on whole vectors: compiled to one call per element."""


def _si(ev, q):
    """A quantity's magnitude in SI base units, as numbers."""
    if isinstance(q, str) or is_complex(q):
        raise Unsupported()
    if _offset(q, ev.ureg):
        raise Unsupported()
    m = q.to_base_units().magnitude
    return np.asarray(m, dtype=float) if np.ndim(m) else float(m)


def compile(node, ev, unknowns):
    """`node` as a function of {unknown key: SI magnitude}. `unknowns` are the unknowns' keys."""
    unknowns = set(unknowns)
    cache = {}   # (function key, lanes) -> compiled body

    def name(n, params, lanes):
        if n.name in params:
            k = n.name
            return lambda env, scope: scope[k]
        key = ev.vkey(n.name)
        if key in unknowns or n.name in unknowns:
            k = key if key in unknowns else n.name
            if lanes:
                raise _NoLanes()   # a vector of the sheet's inside a vectorized body: per element
            return lambda env, scope: env[k]
        for k in (n.name, key):
            if k in ev.vars:
                v = ev.vars[k]
                if not hasattr(v, "units"):
                    raise Unsupported()
                c = _si(ev, v)
                if lanes and np.ndim(c):
                    raise _NoLanes()
                return lambda env, scope: c
        if n.name in CONSTANTS:
            c = _si(ev, ev.Q(CONSTANTS[n.name]))
            return lambda env, scope: c
        raise Unsupported()

    def const(q):
        c = _si(ev, q)
        return lambda env, scope: c

    def body(fkey, lanes):
        if (fkey, lanes) not in cache:
            cache[(fkey, lanes)] = None   # recursion: not compiled
            params, b = ev.funcs[fkey]
            cache[(fkey, lanes)] = (params, build(b, set(params), lanes))
        got = cache[(fkey, lanes)]
        if got is None:
            raise Unsupported()
        return got

    def builtin(fname, argc_nodes, params, lanes):
        if fname not in FUNCTIONS:
            raise Unsupported()
        if lanes and fname not in LANE_SAFE:
            raise _NoLanes()
        impl = FUNCTIONS[fname].impl
        table = fname in LANE_TABLE
        args = [build(a, params, lanes and not (table and i == 0)) for i, a in enumerate(argc_nodes)]
        Q = ev.Q
        if fname in NATIVE:
            native = NATIVE[fname]
            if len(args) == 1:
                a0 = args[0]
                return lambda env, scope: native(a0(env, scope))
            return lambda env, scope: native(*[a(env, scope) for a in args])

        def call(env, scope):
            try:
                r = impl(ev, *[Q(a(env, scope)) for a in args])
            except Exception as ex:
                raise ArithmeticError(str(ex)) from None
            if isinstance(r, str) or is_complex(r):
                raise ArithmeticError("not a real number")
            m = r.to_base_units().magnitude
            return np.asarray(m, dtype=float) if np.ndim(m) else float(m)
        return call

    def build(n, params, lanes):
        t = type(n)
        if t is Num:
            if isinstance(n.value, complex):
                raise Unsupported()
            v = float(n.value)
            return lambda env, scope: v
        if t is Name:
            return name(n, params, lanes)
        if t in (UnitLit, Implicit):
            return const(ev.eval(n, ev.vars))
        if t is Neg:
            a = build(n.operand, params, lanes)
            return lambda env, scope: -a(env, scope)
        if t is Convert:   # the same quantity in other units: in SI, the same numbers
            return build(n.expr, params, lanes)
        if t is BinOp:
            a, b = build(n.left, params, lanes), build(n.right, params, lanes)
            op = n.op
            if op == "+":
                return lambda env, scope: a(env, scope) + b(env, scope)
            if op == "-":
                return lambda env, scope: a(env, scope) - b(env, scope)
            if op in (".*",) or (op == "*" and lanes):
                return lambda env, scope: a(env, scope) * b(env, scope)
            if op == "*":
                def mul(env, scope):
                    x, y = a(env, scope), b(env, scope)
                    return x @ y if np.ndim(x) >= 1 and np.ndim(y) >= 1 else x * y
                return mul
            if op in ("/", "./"):
                return lambda env, scope: a(env, scope) / b(env, scope)
            if op == "^":
                if lanes:
                    return lambda env, scope: np.power(a(env, scope), b(env, scope))
                def pw(env, scope):
                    x, y = a(env, scope), b(env, scope)
                    if np.ndim(x) == 2:
                        return np.linalg.matrix_power(x, int(y))
                    return np.power(x, y)
                return pw
            raise Unsupported()
        if t is Matrix:
            if lanes:
                raise _NoLanes()
            cells = [[build(e, params, lanes) for e in row] for row in n.rows]
            Q = ev.Q
            def matrix(env, scope):
                return ev.matrix([[Q(c(env, scope)) for c in row] for row in cells]).magnitude
            return matrix
        if t is Call:
            fkey = ev.fkey(n.func)
            if any(type(a).__name__ == "Str" for a in n.args):
                raise Unsupported()
            if fkey not in ev.funcs:
                return builtin(n.func, n.args, params, lanes)
            args = [build(a, params, lanes) for a in n.args]
            if n.elementwise and not lanes:
                return elementwise(fkey, args)
            p, f = body(fkey, lanes)
            def user(env, scope):
                return f(env, dict(zip(p, [a(env, scope) for a in args])))
            return user
        raise Unsupported()

    def elementwise(fkey, args):
        """`.f(...)`: on whole vectors when f's body allows, else once per element."""
        try:
            p, f = body(fkey, True)
            def vector(env, scope):
                vals = [a(env, scope) for a in args]
                shape = next((np.shape(v) for v in vals if np.ndim(v)), ())
                r = f(env, dict(zip(p, vals)))
                return np.full(shape, float(r)) if np.ndim(r) == 0 and shape else r
            return vector
        except _NoLanes:
            cache.pop((fkey, True), None)
        p, f = body(fkey, False)
        def each(env, scope):
            vals = [a(env, scope) for a in args]
            shape = next((np.shape(v) for v in vals if np.ndim(v)), ())
            if not shape:
                return f(env, dict(zip(p, vals)))
            out = np.empty(shape)
            for idx in np.ndindex(shape):
                out[idx] = f(env, dict(zip(p, [v[idx] if np.ndim(v) else v for v in vals])))
            return out
        return each

    try:
        fn = build(node, set(), False)
    except _NoLanes:
        raise Unsupported() from None
    except RecursionError:
        raise Unsupported() from None
    return lambda env: fn(env, {})
