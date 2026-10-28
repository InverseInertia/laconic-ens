"""`!regression`: a least-squares polynomial through points, with units.

    D = [0, 1, 2, 3; 1.1, 2.9, 5.2, 7.1] * 'm   one column per point: the x row, then the y row
    !regression a, b, c                         the coefficients, lowest power first:
      data: D                                   y = a + b·x + c·x²
      r2: R2                                    optional: a name for the coefficient of determination

    t = [0, 1, 2, 3] * 's                       x and y in units of their own: two vectors
    s = [0.1, 4.8, 19.7, 44.0] * 'm
    !regression p                               one name: a vector of coefficients; needs `degree:`
      data: t, s                                and an x without units (all coefficients share one)
      degree: 2

A block looks like a solver block (sheettext reads it as one, so its option lines, Rename and the
editor's suggestions work the same), but a fit is quick and exact, so it is computed every time the
sheet runs: there is no Run button and no stored result. Coefficient k has the units of y / x^k.
What the block defines is visible below it, like an assignment's name."""
import warnings
from dataclasses import dataclass, field

import numpy as np

from .parser import ParseError, parse_expr
from .sheettext import is_name

KEYS = ("data", "degree", "r2")
KEY_NOTES = {
    "data": "a matrix with an x row and a y row, one column per point; or two vectors: x, y",
    "degree": "the polynomial's degree; needed when one name holds every coefficient",
    "r2": "a name to hold R², the coefficient of determination",
}
MAX_DEGREE = 20


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


def _apply_option(b, key, value):
    if key == "data":
        parts = _split_top(value)
        if len(parts) > 2:
            raise RegressionError("data is one matrix (an x row and a y row) or two vectors, `data: x, y`")
        b.data = [_expr(p) for p in parts]
        b.data_src = parts
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
    degree: int
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


def _points(b, ev):
    """The x and y quantities, as flat vectors of the same length."""
    vals = [ev.eval(n) for n in b.data]
    if len(vals) == 1:
        d = vals[0]
        mag = np.asarray(d.magnitude)
        if mag.ndim != 2 or mag.shape[0] != 2:
            shape = "a single number" if mag.ndim == 0 else "×".join(str(s) for s in (mag.shape if mag.ndim == 2 else (mag.size,)))
            hint = "; use transpose() to turn a two-column table on its side" if mag.ndim == 2 and mag.shape[1] == 2 else ""
            raise RegressionError(f"data is a matrix with 2 rows, the x values then the y values, one column per "
                                  f"point; this is {shape}{hint}. Or give two vectors, `data: x, y`")
        x, y = ev.Q(mag[0], d.units), ev.Q(mag[1], d.units)
    else:
        x, y = vals
        for q, what in ((x, "x"), (y, "y")):
            m = np.asarray(q.magnitude)
            if m.ndim == 2 and 1 not in m.shape or m.ndim > 2:
                raise RegressionError(f"The {what} data is a matrix; give a row or column vector")
        x, y = ev.Q(np.ravel(x.magnitude), x.units), ev.Q(np.ravel(y.magnitude), y.units)
        if x.magnitude.size != y.magnitude.size:
            raise RegressionError(f"There are {x.magnitude.size} x values and {y.magnitude.size} y values")
    return _multiplicative(x), _multiplicative(y)


def fit(b, ev):
    """Fit the block's polynomial to its data. Returns a Fit; raises RegressionError."""
    x, y = _points(b, ev)
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
        coeffs = [ev.Q(np.array([q.to(y.units).magnitude for q in coeffs]), y.units)]
    names = [getattr(n, "name", "") for n in b.data] if len(b.data) == 2 else ["", ""]
    return Fit(coeffs, r2, npts, deg, *names)


def _numbered(name, deg):
    stem = name.rstrip("`!@")
    return [f"{stem}{k}" for k in range(deg + 1)]


def describe(f):
    return f"degree {f.degree}, {f.points} point{'s' * (f.points != 1)}"
