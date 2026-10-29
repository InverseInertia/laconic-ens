"""`!regression`: a least-squares fit through points, with units: a polynomial, or a model of any
form in one or more variables.

    D = [0, 1, 2, 3; 1.1, 2.9, 5.2, 7.1] * 'm   one column per point: the x row, then the y row
    !regression a, b, c                         the coefficients, lowest power first:
      data: D                                   y = a + b·x + c·x²
      r2: R2                                    optional: a name for the coefficient of determination

    t = [0, 1, 2, 3] * 's                       x and y in units of their own: two vectors
    s = [0.1, 4.8, 19.7, 44.0] * 'm
    !regression p                               one name: a vector of coefficients; needs `degree:`
      data: t, s                                and an x without units (all coefficients share one)
      degree: 2

    !regression A, k                            a model: the coefficients are the header's names,
      model: v(t) = A*exp(-k*t)                 the model's parameters are the data's variables
      data: t, s                                one vector per parameter, then y (or a matrix with
                                                a row for each, then the y row)

A block looks like a solver block (sheettext reads it as one, so its option lines, Rename and the
editor's suggestions work the same), but a fit is quick and exact, so it is computed every time the
sheet runs: there is no Run button and no stored result. Coefficient k has the units of y / x^k.
A model is fitted by scipy's least squares, from the coefficients' values above the block when they
have one (they carry the units, as a solver's starting values do), else from 1 in the units the
model gives them (`model_units`). What the block defines is visible below it, like an assignment's
name, and a model's function too."""
import warnings
from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np
import pint

from .functions import FUNCTIONS
from .nodes import BinOp, Call, FuncDef, Name, Neg, refs
from .parser import ParseError, parse_expr
from .sheettext import definition, is_name

KEYS = ("data", "degree", "model", "r2")
KEY_NOTES = {
    "data": "a matrix with an x row and a y row, one column per point; or two vectors: x, y",
    "degree": "the polynomial's degree; needed when one name holds every coefficient",
    "model": "the function to fit instead of a polynomial: y(x) = A*exp(-k*x), in the header's names",
    "r2": "a name to hold R², the coefficient of determination",
}
MAX_DEGREE = 20
MAX_MODEL_POINTS = 5000   # a model is evaluated point by point, on every run of the sheet


class RegressionError(Exception):
    pass


@dataclass
class Block:
    line: int
    end: int
    names: list = field(default_factory=list)   # the coefficients, lowest power first (or one vector)
    data: list = field(default_factory=list)    # one node (a 2-row matrix) or two (x, y)
    data_src: list = field(default_factory=list)
    degree: int = None
    model: object = None                        # the model: a FuncDef, `y(x, z) = body`
    model_src: str = ""
    r2: str = None
    errors: dict = field(default_factory=dict)  # option line number -> message
    problem: str = ""

    def nodes(self):
        return list(self.data)


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
    return [p.strip() for p in out]


def _expr(src):
    if not src:
        raise RegressionError("data needs an expression on each side of the comma")
    try:
        return parse_expr(src)
    except ParseError as e:
        raise RegressionError(str(e)) from None


def parse_block(handle):
    """The `!regression` block `handle` (a sheettext.Block). Problems with single option lines go
    in `errors`, keyed by line number; a problem with the whole block is `problem`."""
    b = Block(handle.header, handle.end)
    names = _split_top(handle.args) if handle.args else []
    if not names or not all(is_name(n) for n in names):
        b.problem = ("!regression reads `!regression a, b, c`: names for the coefficients, lowest power "
                     "first, or one name for all of them with `degree:`")
        return b
    bare = [n.lstrip("~") for n in names]
    if len(set(bare)) != len(bare):
        b.problem = "A name is listed twice"
        return b
    b.names = names
    seen = set()
    for line in handle.members:
        n, o = line.n, line.option
        if line.result is None and line.text.strip().startswith("#"):
            continue
        try:
            if line.result is not None:
                raise RegressionError("A regression is worked out as the sheet runs and stores no result; "
                                      "remove this line")
            if not o:
                raise RegressionError("Option lines read `key: value`")
            if o.key not in KEYS:
                raise RegressionError(f"Unknown option '{o.key}'. Under !regression: " + ", ".join(KEYS))
            if o.arg:
                raise RegressionError(f"{o.key} does not take a name before the colon")
            if o.key in seen:
                raise RegressionError(f"{o.key} is given twice")
            if not o.value:
                raise RegressionError(f"{o.key} needs a value")
            seen.add(o.key)
            _apply_option(b, o.key, o.value)
        except RegressionError as e:
            b.errors[n] = str(e)
    if b.errors:
        count = len(b.errors)
        b.problem = f"{count} option line{'s' * (count != 1)} below need{'s' * (count == 1)} fixing"
    elif not b.data:
        b.problem = "!regression needs a `data:` line: a matrix with an x row and a y row, or `data: x, y`"
    elif b.model is not None:
        b.problem = _model_problem(b, bare)
    elif len(b.data) > 2:
        b.problem = ("data is one matrix (an x row and a y row) or two vectors, `data: x, y`. "
                     "For more variables, give a `model:` such as `z(x, y) = a + b*x + c*y`")
    elif b.degree is None and len(names) == 1:
        b.problem = (f"Give the degree (`degree: 2`), or name each coefficient: "
                     f"`!regression {names[0]}0, {names[0]}1, {names[0]}2`")
    elif b.degree is not None and len(names) > 1 and b.degree != len(names) - 1:
        b.problem = (f"{len(names)} names make a polynomial of degree {len(names) - 1}, but `degree:` "
                     f"says {b.degree}. Give one name per coefficient, or one name for all of them")
    elif b.degree is None:
        b.degree = len(names) - 1
    if b.r2 is not None and b.r2.lstrip("~") in bare:
        b.problem = b.problem or f"'{b.r2}' is already a coefficient"
    return b


def _model_problem(b, bare):
    """What is wrong with a block that has a `model:`, or ""."""
    params, used = b.model.params, refs(b.model.body).names
    if b.degree is not None:
        return "degree: is for a polynomial; the model says what is fitted. Remove one of them"
    if clash := [p for p in params if p in bare]:
        return f"'{clash[0]}' is a coefficient and one of the model's variables; rename one of them"
    if missing := [n for n in bare if n not in used]:
        return f"The coefficient {missing[0]} does not appear in the model"
    n = len(params) + 1
    if len(b.data) not in (1, n):
        return (f"The model has {len(params)} variable{'s' * (len(params) != 1)}, so data is a matrix with {n} rows "
                f"or {n} vectors: `data: {', '.join(params)}, {b.model.name.lstrip('~')}`")
    return ""


def _apply_option(b, key, value):
    if key == "data":
        parts = _split_top(value)
        b.data = [_expr(p) for p in parts]
        b.data_src = parts
    elif key == "model":
        d = definition(value)
        if d is None or d.kind != "funcdef":
            raise RegressionError("model reads `y(x) = a + b*exp(k*x)`: a function of the data's variables, "
                                  "in the coefficients the header names")
        if len(set(d.params)) != len(d.params):
            raise RegressionError("A variable is listed twice in the model")
        b.model = FuncDef(d.name, d.params, _expr(d.body))
        b.model_src = value
    elif key == "degree":
        try:
            d = float(value)
        except ValueError:
            raise RegressionError("degree needs a whole number") from None
        if d != int(d) or not 0 <= d <= MAX_DEGREE:
            raise RegressionError(f"degree is a whole number from 0 to {MAX_DEGREE}")
        b.degree = int(d)
    elif key == "r2":
        if not is_name(value):
            raise RegressionError("r2 names the variable that holds R², e.g. `r2: R2`")
        b.r2 = value


# ---- the fit -------------------------------------------------------------------------------------
@dataclass
class Fit:
    coefficients: list   # one quantity per name: a scalar each, or one vector for a single name
    r2: float
    points: int
    degree: int          # None for a model
    x_name: str          # the names the data came from, when they were plain names (else "")
    y_name: str


def _real(q, what):
    if np.iscomplexobj(q.magnitude):
        raise RegressionError(f"The {what} values are complex; a regression fits real numbers")
    mag = np.asarray(q.magnitude, dtype=float)
    if not np.all(np.isfinite(mag)):
        raise RegressionError(f"The {what} values are not all finite")
    return mag


def _multiplicative(q):
    """An offset unit (°C, °F) cannot be raised to a power, so such data is fitted in kelvin."""
    return q if q._is_multiplicative else q.to_base_units()


def _points(b, ev, names=("x", "y")):
    cols, row = columns(ev, [ev.eval(node) for node in b.data], names)
    return [_multiplicative(c) for c in cols], row


def columns(ev, vals, names=("x", "y"), key="data"):
    """Points given as `data:` gives them (a plot's `points:` too): `vals` is one matrix with a row
    per name (the variables, then y) and a column per point, or one vector per name. Returns one
    flat vector of quantities per name, all the same length, and whether the points are laid out in
    a row (a matrix's rows, or a row vector of the first variable) rather than a column."""
    n = len(names)
    if len(vals) == 1:
        d = vals[0]
        mag = np.asarray(d.magnitude)
        if mag.ndim != 2 or mag.shape[0] != n:
            shape = "a single number" if mag.ndim == 0 else "×".join(str(s) for s in (mag.shape if mag.ndim == 2 else (mag.size,)))
            hint = (f"; use transpose() to turn a {n}-column table on its side"
                    if mag.ndim == 2 and mag.shape[1] == n else "")
            rows = ("the x values then the y values" if list(names) == ["x", "y"]
                    else "a row for " + ", ".join(names[:-1]) + f", then the {names[-1]} row")
            raise RegressionError(f"{key} is a matrix with {n} rows, {rows}, one column per point; this is "
                                  f"{shape}{hint}. Or give {n} vectors, `{key}: {', '.join(names)}`")
        cols, row = [ev.Q(mag[k], d.units) for k in range(n)], True
    else:
        for q, what in zip(vals, names):
            m = np.asarray(q.magnitude)
            if m.ndim == 2 and 1 not in m.shape or m.ndim > 2:
                raise RegressionError(f"The {what} {'data' if key == 'data' else 'values'} are a matrix; "
                                      f"give a row or column vector")
        row = np.ndim(vals[0].magnitude) == 2 and np.shape(vals[0].magnitude)[0] == 1
        cols = [ev.Q(np.ravel(q.magnitude), q.units) for q in vals]
        sizes = [c.magnitude.size for c in cols]
        if len(set(sizes)) > 1:
            raise RegressionError("There are " + " and ".join(f"{k} {w} values" for k, w in zip(sizes, names)))
    return cols, row


def fit(b, ev):
    """Fit the block's polynomial or model to its data. Returns a Fit; raises RegressionError."""
    if b.model is not None:
        return _fit_model(b, ev)
    (x, y), row = _points(b, ev)
    xm, ym = _real(x, "x"), _real(y, "y")
    deg, npts = b.degree, xm.size
    if np.unique(xm).size <= deg:
        raise RegressionError(f"A degree-{deg} polynomial needs at least {deg + 1} different x values; "
                              f"the data has {np.unique(xm).size}")
    single = len(b.names) == 1 and deg > 0
    one = ev.Q(1, x.units)
    if single and not one.dimensionless:
        raise RegressionError(f"x is in {x.units:~P}, so each coefficient has units of its own and they cannot share "
                              f"one vector. Name each one: `!regression {', '.join(_numbered(b.names[0], deg))}`")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        try:
            c = np.polynomial.polynomial.polyfit(xm, ym, deg)
        except Exception as e:
            raise RegressionError(f"The fit failed: {e}") from None
    # A term whose part of y is rounding error (an exact fit's zero coefficient comes out as 1e-15)
    # is zero, as `Fmt` hides a complex value's negligible part.
    scale = float(np.max(np.abs(ym)))
    reach = float(np.max(np.abs(xm))) ** np.arange(deg + 1)
    c = np.where(np.abs(c) * reach < 1e-12 * scale, 0.0, c)
    resid = ym - np.polynomial.polynomial.polyval(xm, c)
    ss_res, ss_tot = float(resid @ resid), float(((ym - ym.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else (1.0 if ss_res == 0 else 0.0)
    coeffs = [ev.Q(float(c[k]), y.units / x.units ** k) for k in range(deg + 1)]
    if single:
        # The vector lies as the data does: a row for a matrix's x row or a row of x values.
        v = np.array([q.to(y.units).magnitude for q in coeffs])
        coeffs = [ev.Q(v[None, :] if row else v[:, None], y.units)]
    names = [getattr(n, "name", "") for n in b.data] if len(b.data) == 2 else ["", ""]
    return Fit(coeffs, r2, npts, deg, *names)


# ---- a model ------------------------------------------------------------------------------------
# A dimension is {base dimension: exponent}. While the model's units are worked out, the dimension
# of an expression is affine in the coefficients' unknown ones: (known part, {coefficient: factor}).
_SAME = {"abs", "floor", "ceil", "re", "im", "conj"}           # the result has the argument's units
_PURE = {"sin", "cos", "tan", "asin", "acos", "atan", "exp", "ln", "log10", "heaviside", "arg"}


class _Unsupported(Exception):
    """A model the units walk cannot read (a matrix, text, a function it does not know)."""


def _dims(q):
    return {d: Fraction(e).limit_denominator(1000) for d, e in q.dimensionality.items()}


def _add(a, b, k=1):
    """The affine dimension a + k·b."""
    const, terms = dict(a[0]), dict(a[1])
    for d, e in b[0].items():
        const[d] = const.get(d, 0) + k * e
    for j, e in b[1].items():
        terms[j] = terms.get(j, 0) + k * e
    return ({d: e for d, e in const.items() if e}, {j: e for j, e in terms.items() if e})


def _scale(a, p):
    return ({d: p * e for d, e in a[0].items()}, {j: p * e for j, e in a[1].items()})


_ZERO = ({}, {})


class _Units:
    """Works out the units the coefficients need for the model to come out in y's units. The
    dimension of each part of the model is affine in the coefficients' unknown ones; every sum,
    every argument of exp or sin, and the model against y is an equation between them, solved
    exactly. What varies is local: a coefficient, a variable, a user function's parameter."""

    def __init__(self, ev):
        self.ev, self.equations, self.roots = ev, [], {}   # roots: base dimension -> a unit of it

    def known(self, q):
        for name, _ in self.ev.Q(1, q.units).to_root_units().unit_items():
            for d in self.ev.ureg.Quantity(1, name).dimensionality:
                self.roots.setdefault(d, name)
        return (_dims(q), {})

    def _varies(self, node, local):
        r = refs(node)
        return bool(r.names & set(local)) or any(self.ev.fkey(f) in self.ev.funcs for f in r.calls)

    def _power(self, node, local):
        n = self.ev.eval(node)
        if np.ndim(n.magnitude) or not n.dimensionless or np.iscomplexobj(n.magnitude):
            raise _Unsupported
        return Fraction(float(n.to("dimensionless").magnitude)).limit_denominator(1000)

    def dim(self, node, local, depth=0):
        """The affine dimension of `node`, where `local` maps the names that vary to theirs."""
        if not self._varies(node, local):
            return self.known(self.ev.eval(node))
        if isinstance(node, Name):
            return local[node.name]
        if isinstance(node, Neg):
            return self.dim(node.operand, local, depth)
        if isinstance(node, BinOp):
            a = self.dim(node.left, local, depth)
            if node.op == "^":
                if self._varies(node.right, local):   # x^k: both sides are plain numbers
                    if a[0] and not a[1]:
                        raise RegressionError("A power whose exponent is fitted needs a base without units: "
                                              "divide the base by its unit, as in (x/1'm)^b")
                    self.equations += [a, self.dim(node.right, local, depth)]
                    return _ZERO
                return _scale(a, self._power(node.right, local))
            b = self.dim(node.right, local, depth)
            if node.op in ("+", "-"):
                self.equations.append(_add(a, b, -1))
                return a
            return _add(a, b, -1 if node.op in ("/", "./") else 1)
        if isinstance(node, Call) and not any(type(a).__name__ == "Str" for a in node.args):
            args = [self.dim(a, local, depth) for a in node.args]
            fkey = self.ev.fkey(node.func)
            if fkey in self.ev.funcs:
                params, body = self.ev.funcs[fkey]
                if len(params) != len(args) or depth > 20:
                    raise _Unsupported
                return self.dim(body, dict(zip(params, args)), depth + 1)   # it sees only its parameters
            if len(args) == 1 and node.func in _PURE:
                self.equations.append(args[0])
                return _ZERO
            if len(args) == 1 and node.func == "sqrt":
                return _scale(args[0], Fraction(1, 2))
            if len(args) == 1 and node.func in _SAME:
                return args[0]
        raise _Unsupported

    def solve(self, count, model_dim, y_dim, fixed):
        """[dimension of each coefficient], with the `fixed` ones (index: dimension) as given and
        any the model leaves free dimensionless. Raises RegressionError when no units work."""
        eqs = self.equations + [_add(model_dim, (y_dim, {}), -1)]
        eqs += [_add(({}, {j: Fraction(1)}), (d, {}), -1) for j, d in fixed.items()]
        dims = sorted({d for c, _ in eqs for d in c})
        rows = [[t.get(j, Fraction(0)) for j in range(count)] + [-c.get(d, Fraction(0)) for d in dims]
                for c, t in eqs]
        pivots = []
        for col in range(count):
            r = len(pivots)
            p = next((k for k in range(r, len(rows)) if rows[k][col]), None)
            if p is None:
                continue
            rows[r], rows[p] = rows[p], rows[r]
            rows[r] = [v / rows[r][col] for v in rows[r]]
            for k in range(len(rows)):
                if k != r and rows[k][col]:
                    f = rows[k][col]
                    rows[k] = [v - f * w for v, w in zip(rows[k], rows[r])]
            pivots.append(col)
        if any(any(row[count:]) for row in rows[len(pivots):]):
            raise RegressionError("The model's units do not work out: no units for its coefficients make it come "
                                  "out in the units of the y data" + (", with the values they have above the block"
                                                                     if fixed else ""))
        out = [{} for _ in range(count)]
        for k, col in enumerate(pivots):
            out[col] = {d: rows[k][count + i] for i, d in enumerate(dims) if rows[k][count + i]}
        return out

    def unit(self, dim):
        u = self.ev.ureg.dimensionless
        for d, e in dim.items():
            u = u * self.ev.ureg.Unit(self.roots[d]) ** (int(e) if e.denominator == 1 else float(e))
        return u


_NUMPY = {"sin": np.sin, "cos": np.cos, "tan": np.tan, "asin": np.arcsin, "acos": np.arccos, "atan": np.arctan,
          "exp": np.exp, "ln": np.log, "log10": np.log10, "sqrt": np.sqrt, "abs": np.abs, "floor": np.floor,
          "ceil": np.ceil}
_OPS = {"+": np.add, "-": np.subtract, "*": np.multiply, ".*": np.multiply, "/": np.divide, "./": np.divide,
        "^": np.power}


def _compile(ev, node, local, depth=0):
    """The model as a numpy function of its local names, every value in SI root units: a model whose
    units work out gives the same numbers in root units as in any others, and runs on every point at
    once. Raises _Unsupported for what it cannot read; the fit then evaluates point by point."""
    if not (bool(refs(node).names & local) or any(ev.fkey(f) in ev.funcs for f in refs(node).calls)):
        q = ev.eval(node)
        if np.ndim(q.magnitude) or np.iscomplexobj(q.magnitude) or not q._is_multiplicative:
            raise _Unsupported
        c = float(q.to_root_units().magnitude)
        return lambda env: c
    if isinstance(node, Name):
        name = node.name
        return lambda env: env[name]
    if isinstance(node, Neg):
        f = _compile(ev, node.operand, local, depth)
        return lambda env: -f(env)
    if isinstance(node, BinOp) and node.op in _OPS:
        op, a, b = _OPS[node.op], _compile(ev, node.left, local, depth), _compile(ev, node.right, local, depth)
        return lambda env: op(a(env), b(env))
    if isinstance(node, Call) and not any(type(a).__name__ == "Str" for a in node.args):
        args = [_compile(ev, a, local, depth) for a in node.args]
        fkey = ev.fkey(node.func)
        if fkey in ev.funcs:
            params, body = ev.funcs[fkey]
            if len(params) != len(args) or depth > 20:
                raise _Unsupported
            f = _compile(ev, body, set(params), depth + 1)
            return lambda env: f(dict(zip(params, (a(env) for a in args))))
        trig = node.func in ("sin", "cos", "tan", "asin", "acos", "atan")
        if len(args) == 1 and node.func in _NUMPY and not (trig and ev.mode.angle == "degree"):
            fn, a = _NUMPY[node.func], args[0]
            return lambda env: fn(a(env))
    raise _Unsupported


def _start(ev, name):
    """A coefficient's value above the block, which the fit starts from, or None."""
    q = ev.vars.get(ev.vkey(name))
    if q is None or not isinstance(q, pint.Quantity) or np.ndim(q.magnitude) or np.iscomplexobj(q.magnitude):
        return None
    return q if np.isfinite(float(q.magnitude)) else None


def _fit_model(b, ev):
    from scipy.optimize import least_squares   # imported on first use, as the solver does

    m = b.model
    bare, names = [n.lstrip("~") for n in b.names], [*m.params, m.name.lstrip("~")]
    cols, _ = _points(b, ev, names)
    *xs, y = cols
    for q, what in zip(cols, names):
        _real(q, what)
    npts, count = y.magnitude.size, len(bare)
    if npts < count:
        raise RegressionError(f"{count} coefficients need at least {count} points; the data has {npts}")
    if npts > MAX_MODEL_POINTS:
        raise RegressionError(f"A model is fitted on every edit, so it takes at most {MAX_MODEL_POINTS} points; "
                              f"the data has {npts}")

    # The coefficients' units: worked out from the model, keeping those of a value above the block.
    # A model the walk cannot read gets the units of those values, else none.
    starts = [_start(ev, n) for n in b.names]
    cunits = [q.units if q is not None else ev.ureg.dimensionless for q in starts]
    units, fast = _Units(ev), None
    unknowns = {n: ({}, {j: Fraction(1)}) for j, n in enumerate(bare)}
    point = {p: units.known(x[0]) for p, x in zip(m.params, xs)}
    fixed = {j: units.known(q)[0] for j, q in enumerate(starts) if q is not None}
    try:
        dims = units.solve(count, units.dim(m.body, {**unknowns, **point}), units.known(y)[0], fixed)
        cunits = [starts[j].units if j in fixed else units.unit(d) for j, d in enumerate(dims)]
        fast = _compile(ev, m.body, set(bare) | set(m.params))
    except (_Unsupported, pint.errors.PintError, ValueError, KeyError, ZeroDivisionError):
        pass
    p0 = np.array([float(q.to(u).magnitude) if q is not None else 1.0 for q, u in zip(starts, cunits)])
    ym, yu = _real(y, "y"), y.units

    # Point by point through the evaluator, units and all.
    scope, factors = dict(ev.vars), {}
    at = [[ev.Q(float(v), x.units) for v in x.magnitude] for x in xs]   # each variable at each point

    def slow(p, points=range(npts)):
        for name, v, u in zip(bare, p, cunits):
            scope[name] = ev.Q(float(v), u)
        out = np.empty(len(points))
        for k, i in enumerate(points):
            for name, x in zip(m.params, at):
                scope[name] = x[i]
            q = ev.eval(m.body, scope)
            if np.ndim(q.magnitude) or np.iscomplexobj(q.magnitude):
                raise RegressionError("The model gives " + ("a matrix" if np.ndim(q.magnitude) else "a complex value")
                                      + f" at point {i + 1}; it must give one real number")
            if q.units not in factors:
                factors[q.units] = float(ev.Q(1, q.units).to(yu).magnitude)
            out[k] = float(q.magnitude) * factors[q.units]
        return out

    # Every point at once, in root units (see _compile).
    root = [float(ev.Q(1, u).to_root_units().magnitude) for u in cunits]
    env = {p: np.asarray(x.to_root_units().magnitude, dtype=float) for p, x in zip(m.params, xs)}
    y_root = float(ev.Q(1, yu).to_root_units().magnitude)

    def quick(p):
        env.update({name: v * f for name, v, f in zip(bare, p, root)})
        return np.broadcast_to(fast(env) / y_root, (npts,))

    try:
        first = slow(p0)
    except pint.errors.DimensionalityError as e:
        raise RegressionError(f"The model's units do not work out ({e}). Give the coefficients values with "
                              f"units above the block to start from") from None
    except ZeroDivisionError:
        first = np.full(npts, np.nan)
    if not np.all(np.isfinite(first)):
        raise RegressionError("The model cannot be worked out at every point from where the fit starts. Give the "
                              "coefficients values above the block to start from")
    if fast is not None:
        with np.errstate(all="ignore"):
            agree = np.allclose(quick(p0), first, rtol=1e-9, atol=1e-12 * float(np.max(np.abs(first)) or 1))
        fast = fast if agree else None
    model = quick if fast is not None else slow

    def residuals(p):
        with np.errstate(all="ignore"):
            r = model(p) - ym
        return np.where(np.isfinite(r), r, 1e150)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            sol = least_squares(residuals, p0, method="lm" if npts > count else "trf", x_scale="jac")
    except RegressionError:
        raise
    except Exception as e:
        raise RegressionError(f"The fit failed: {e}") from None
    if not sol.success or not np.all(np.isfinite(sol.x)) or np.any(np.abs(sol.fun) >= 1e149):
        raise RegressionError("The fit did not settle. Give the coefficients values above the block to start "
                              "from, nearer the answer")
    resid = sol.fun
    ss_res, ss_tot = float(resid @ resid), float(((ym - ym.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else (1.0 if ss_res == 0 else 0.0)
    coeffs = [ev.Q(float(v), u) for v, u in zip(sol.x, cunits)]
    return Fit(coeffs, r2, npts, None, "", "")


def _numbered(name, deg):
    stem = name.rstrip("`!@")
    return [f"{stem}{k}" for k in range(deg + 1)]


def describe(f):
    kind = "model" if f.degree is None else f"degree {f.degree}"
    return f"{kind}, {f.points} point{'s' * (f.points != 1)}"
