"""Evaluator: walks the AST and produces Pint quantities.

Every value is a Pint Quantity, scalars and matrices alike, so the arithmetic
code has one path instead of two."""
import copy
import math
import re
import shutil
import tempfile
import threading
from functools import lru_cache

import numpy as np
import pint
from pathlib import Path

from .commands import SheetMode
from .symbols import FUNCTION, VARIABLE, SymbolTable
from .nodes import BinOp, Name, Str, UnitLit
from . import props as _props
from . import catalogue
from .functions import FUNCTIONS, builtin
from .parser import parse_expr

CONSTANTS = {"pi": math.pi, "e": math.e, "∞": math.inf}
_TINY = 1e-12   # an imaginary part this much smaller than the whole value is rounding noise


def _settle(m):
    """A numpy result that is complex only through rounding (eigenvalues of a symmetric matrix)
    as real; anything else unchanged."""
    if np.iscomplexobj(m) and np.all(np.abs(m.imag) <= 1e-9 * max(1.0, np.abs(m).max())):
        return m.real
    return m


class EvalError(Exception):
    pass


# The server builds the registries in the background as it starts (`warm`); a request that
# arrives meanwhile waits for that build rather than starting a second one.
_building = threading.RLock()


def registry():
    with _building:
        return _registry()


@lru_cache(maxsize=1)
def _registry():
    # Building a registry takes a noticeable fraction of a second, so share one.
    # Pint's pound is `lb`, which reads as a force as easily as a mass. Name it `lbm`
    # (matching `lbf`) and drop `lb`. Pint's year symbol is `a` (annum), which nobody reads
    # as a year; make `yr` the symbol and keep `a` as an alias. Pint's liter symbol is `l`,
    # easily misread as a 1; print the capital `L` (mL, kL) and keep `l` as an alias.
    # Pint's hour symbol is `h`, which is also the symbol of Planck's constant ('h_P);
    # print `hr` (km/hr) and keep `h` as an alias.
    src = Path(pint.__file__).parent
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copy(src / "constants_en.txt", tmp)
        text = (src / "default_en.txt").read_text(encoding="utf-8")
        renamed = text.replace("7e3 * grain = lb = avoirdupois_pound", "7e3 * grain = lbm = avoirdupois_pound")
        assert renamed != text, "pint's pound definition changed"
        before = renamed
        renamed = renamed.replace("year = 365.25 * day = a = yr = julian_year", "year = 365.25 * day = yr = a = julian_year")
        assert renamed != before, "pint's year definition changed"
        before = renamed
        renamed = renamed.replace("liter = decimeter ** 3 = l = L =", "liter = decimeter ** 3 = L = l =")
        assert renamed != before, "pint's liter definition changed"
        before = renamed
        renamed = renamed.replace("hour = 60 * minute = h = hr", "hour = 60 * minute = hr = h")
        assert renamed != before, "pint's hour definition changed"
        (Path(tmp) / "default_en.txt").write_text(renamed, encoding="utf-8")
        ureg = pint.UnitRegistry(str(Path(tmp) / "default_en.txt"), autoconvert_offset_to_baseunit=True)
    catalogue.define(ureg)
    return ureg


def _ndim(q):
    return np.ndim(q.magnitude)


def _array(m):
    """A magnitude as a numpy array: float, or complex when it has an imaginary part."""
    m = np.asarray(m)
    return m if np.iscomplexobj(m) else m.astype(float)


def is_complex(q):
    return np.iscomplexobj(q.magnitude)


def _offset(q, ureg):
    """True if q's units hold an offset unit such as degC, whose zero is not zero."""
    return any(ureg.Quantity(0, u).to_base_units().magnitude != 0 for u, _ in q.unit_items())


UNIT_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")


def names_in(node):
    """Every Name node under `node` (used to keep unit definitions free of variables)."""
    if isinstance(node, Name):
        return [node.name]
    out = []
    for v in getattr(node, "__dict__", {}).values():
        for item in (v if isinstance(v, tuple) else (v,)):
            for x in (item if isinstance(item, tuple) else (item,)):
                out += names_in(x)
    return out


@lru_cache(maxsize=4)
def _registry_with(units):
    """A registry with the instance's global units defined. Built once per distinct
    list and never mutated afterwards. Returns (registry, valid names, errors)."""
    ev = Evaluator(fork=True)
    ok, bad = [], {}
    for name, definition in units:
        try:
            ev.define_unit(name, parse_expr(definition))
            ok.append(name)
        except Exception as e:
            bad[name] = str(e)
    return ev.ureg, tuple(ok), bad


def check_units(units):
    """Validate (name, definition) pairs in order. Returns one error string or None per pair."""
    ev = Evaluator(fork=True)
    errors = []
    for name, definition in units:
        try:
            ev.define_unit(name, parse_expr(definition))
            errors.append(None)
        except Exception as e:
            errors.append(str(e))
    return errors


class Evaluator:
    def __init__(self, global_units=(), fork=False):
        """`global_units` are (name, definition) pairs from the instance settings.
        A sheet that defines units of its own needs `fork=True`: Pint cannot
        undefine a unit, so each run gets a private copy of the registry."""
        units = tuple((str(n), str(d)) for n, d in global_units)
        with _building:
            if units:
                base, ok, _ = _registry_with(units)
            else:
                base, ok = registry(), ()
        self._owned = fork
        self.ureg = copy.deepcopy(base) if fork else base
        self.globals = {n: d for n, d in units if n in ok}   # instance-wide units
        self.custom = dict(self.globals)                     # globals plus this sheet's, name -> definition
        self.Q = self.ureg.Quantity
        self.vars = {}
        self.funcs = {}
        self.symbols = SymbolTable()  # which names each line sees; filled in by sheet.py
        self.stale = set()     # variable keys whose value comes from a solver result that is out of date
        self.mode = SheetMode()  # what the ! commands above the current line set; changed only by commands.py
        self.notes = []        # warnings for the line being run; sheet.py clears them per line and shows them
        self._calls = []       # the user functions being evaluated, innermost last, to name in a note
        self.nan_hint = None   # why the value being computed may be NaN; read by check_finite

    # ---- name classification (shared with the LaTeX printer) -------------
    def is_var(self, name, local=()):
        return self.vkey(name) in self.vars or name in local

    def vkey(self, name):
        """The key a variable is stored under at the current line (a global's has its ~)."""
        return self.symbols.key(name, VARIABLE)

    def fkey(self, name):
        return self.symbols.key(name, FUNCTION)

    def is_unit(self, name):
        try:
            self.ureg.parse_units(name)
            return True
        except Exception:
            return False

    def define_unit(self, name, expr, source=""):
        """Define `name` as the value of `expr`, which may use numbers and units only."""
        if not self._owned:
            raise RuntimeError("define_unit needs an Evaluator built with fork=True")
        if not UNIT_NAME_RE.match(name):
            raise EvalError("Unit names use ASCII letters, digits and _, and start with a letter")
        if self.is_unit(name):
            means = str(self.ureg.parse_units(name))  # `dsmoot` reads as deci + smoot
            raise EvalError(f"'{name}' is already a unit" + ("" if means == name else f" ({means})"))
        if names_in(expr):
            raise EvalError("A unit definition can use only numbers and units")
        q = self.eval(expr)
        if _ndim(q) != 0:
            raise EvalError("A unit definition must be a single value")
        mag = float(q.magnitude)
        if not math.isfinite(mag) or mag <= 0:
            raise EvalError("A unit must be defined as a positive number of something")
        for uname, _ in q.unit_items():
            if self.ureg.Quantity(0, uname).to_base_units().magnitude != 0:
                raise EvalError("Offset units such as 'degC cannot be used to define a unit")
        text = f"{name} = {mag!r}"
        if q.units != self.ureg.Unit("dimensionless"):
            text += f" * {q.units}"
        self.ureg.define(text)
        self.custom[name] = source or ""
        return q

    def is_unit_node(self, node):
        """True for `'kN` and `'mm^4`. Units are lexically marked, so a bare
        name is always a variable."""
        if isinstance(node, UnitLit):
            return True
        return isinstance(node, BinOp) and node.op == "^" and self.is_unit_node(node.left)

    def note(self, msg):
        """Warn about the line being run: it works but may not do what was meant. A note
        raised inside a user function names it, and each note is kept once per line."""
        if not msg:
            return
        if self._calls:
            msg = f"In {self._calls[-1]}(): {msg}"
        if msg not in self.notes:
            self.notes.append(msg)

    # ---- evaluation -------------------------------------------------------
    def eval(self, node, scope=None):
        scope = self.vars if scope is None else scope
        return getattr(self, "ev_" + type(node).__name__)(node, scope)

    def ev_Num(self, n, scope):
        return self.Q(n.value)

    def ev_Name(self, n, scope):
        if n.name in scope:
            return scope[n.name]
        key = self.vkey(n.name)
        if key in scope:
            return scope[key]
        if n.name in CONSTANTS:
            return self.Q(CONSTANTS[n.name])
        if n.name in self.mode.cleared:
            raise EvalError(f"'{n.name}' was removed by !clear")
        hint = f". Units need an apostrophe: '{n.name}" if self.is_unit(n.name) else ""
        raise EvalError(f"'{n.name}' is not defined{hint}")

    def ev_Str(self, n, scope):
        raise EvalError("Text in quotes can only be an argument to a function such as props")

    def ev_UnitLit(self, n, scope):
        try:
            return self.Q(1, self.ureg.parse_units(n.unit))
        except Exception:
            raise EvalError(f"Unknown unit '{n.unit}'") from None

    def ev_Neg(self, n, scope):
        return -self.eval(n.operand, scope)

    def unit_value(self, node, scope):
        if isinstance(node, UnitLit):
            return self.ev_UnitLit(node, scope)
        exp = self.eval(node.right, scope)
        return self.unit_value(node.left, scope) ** float(exp.to("dimensionless").magnitude)

    def ev_Implicit(self, n, scope):
        """`12'kN/'m`: a number followed by units. A variable after a number
        needs an explicit `*`, so `3 x` is an error rather than a guess."""
        v = n.number.value
        num = f"{v.imag:g}i" if isinstance(v, complex) else f"{v:g}"
        for f in n.factors:
            if not self.is_unit_node(f):
                what = f.name if isinstance(f, Name) else "an expression"
                raise EvalError(f"{what} cannot follow a number directly. Write {num}*{what} to multiply; "
                                f"units need an apostrophe, e.g. {num}'{what}")
        first = self.unit_value(n.factors[0], scope)
        if isinstance(n.number.value, complex) and _offset(first, self.ureg):
            raise EvalError("A complex number cannot carry an offset unit such as 'degC")
        result = self.Q(n.number.value, first.units)  # direct build keeps degC working
        for f in n.factors[1:]:
            result = result * self.unit_value(f, scope)
        return result

    def ev_BinOp(self, n, scope):
        a, b = self.eval(n.left, scope), self.eval(n.right, scope)
        op = n.op
        if op in ("*", "/", ".*", "./"):
            self.note(catalogue.offset_note(self.ureg, a, b))
        if op == "+":
            return self._shape_guard(lambda: a + b, a, b, "+")
        if op == "-":
            return self._shape_guard(lambda: a - b, a, b, "-")
        if op == "*":
            return self.mul(a, b)
        if op == "/":
            if _ndim(b) >= 1:
                raise EvalError("Cannot divide by a matrix. Use solve(A, b) or inv(A)")
            return a / b
        if op == ".*":
            return self._shape_guard(lambda: a * b, a, b, ".*")
        if op == "./":
            return self._shape_guard(lambda: a / b, a, b, "./")
        if op == "^":
            return self.power(a, b)
        raise EvalError(f"Unknown operator {op}")

    def _shape_guard(self, fn, a, b, op):
        try:
            return fn()
        except ValueError:
            raise EvalError(f"Shape mismatch for {op}: {np.shape(a.magnitude)} vs {np.shape(b.magnitude)}") from None

    def mul(self, a, b):
        """`*` is matrix multiplication when both sides are arrays, else scaling."""
        if _ndim(a) >= 1 and _ndim(b) >= 1:
            try:
                return self.Q(np.matmul(a.magnitude, b.magnitude), a.units * b.units)
            except ValueError:
                raise EvalError(f"Shape mismatch for *: {np.shape(a.magnitude)} * {np.shape(b.magnitude)}. "
                                "Use .* for elementwise") from None
        return a * b

    def power(self, a, b):
        if _ndim(b) != 0 or not b.dimensionless:
            raise EvalError("Exponent must be a dimensionless scalar")
        if is_complex(b):
            if not a.dimensionless or _ndim(a) != 0:
                raise EvalError("A complex exponent needs a dimensionless scalar base")
            return self.Q(complex(a.to("dimensionless").magnitude) ** complex(b.to("dimensionless").magnitude))
        n = float(b.to("dimensionless").magnitude)
        if _ndim(a) == 2:
            if n != int(n):
                raise EvalError("Matrix powers must be integers")
            n = int(n)
            try:
                return self.Q(np.linalg.matrix_power(a.magnitude, n), a.units ** n)
            except np.linalg.LinAlgError:
                raise EvalError("Matrix is singular") from None
        if n != int(n):
            self._negative(a, "A negative number to a fractional power is complex. "
                              "Add 0i to the base for the complex result: (x + 0i)^0.5")
        with np.errstate(invalid="ignore"):   # NaN is reported by check_finite
            return self._as_numpy(a) ** n

    def ev_Matrix(self, n, scope):
        rows = [[self.eval(e, scope) for e in row] for row in n.rows]
        if len({len(r) for r in rows}) != 1:
            raise EvalError("Matrix rows must all have the same length")
        unit0 = rows[0][0].units
        data = []
        for row in rows:
            out = []
            for e in row:
                if _ndim(e) != 0:
                    raise EvalError("Matrix entries must be scalars")
                if e.units == unit0:
                    out.append(np.asarray(e.magnitude).item())
                    continue
                try:
                    out.append(np.asarray(e.to(unit0).magnitude).item())
                except pint.errors.DimensionalityError:
                    raise EvalError("Matrix entries must share one dimension") from None
            data.append(out)
        return self.Q(_array(data), unit0)

    def ev_Polar(self, n, scope):
        """`r∠θ` is r·e^(iθ). A bare-number angle is read in the current angle unit, as in sin."""
        r, angle = self.eval(n.magnitude, scope), self.eval(n.angle, scope)
        if is_complex(r) or is_complex(angle):
            raise EvalError("Both sides of ∠ must be real: a magnitude and an angle")
        if _offset(r, self.ureg):
            raise EvalError("A complex number cannot carry an offset unit such as 'degC")
        try:
            theta = self._radians(angle)
        except pint.errors.DimensionalityError:
            raise EvalError("The right side of ∠ must be an angle, e.g. 30'deg") from None
        try:
            return self.Q(np.asarray(r.magnitude) * np.exp(1j * np.asarray(theta)), r.units)
        except ValueError:
            raise EvalError(f"Shape mismatch for ∠: {np.shape(r.magnitude)} vs {np.shape(theta)}") from None

    def ev_Convert(self, n, scope):
        v, mark = self.eval(n.expr, scope), len(self.notes)
        target = self.eval(n.target, scope)
        del self.notes[mark:]   # a target such as 'degF/'s only names units
        return v.to(target.units)

    def ev_Call(self, n, scope):
        args = [a.value if isinstance(a, Str) else self.eval(a, scope) for a in n.args]
        fkey = self.fkey(n.func)
        if fkey in self.funcs:
            if any(isinstance(a, str) for a in args):
                raise EvalError(f"{n.func} is a user function and cannot take text")
            params, body = self.funcs[fkey]
            if len(args) != len(params):
                raise EvalError(f"{n.func} takes {len(params)} argument(s), got {len(args)}")
            self._calls.append(n.func)
            try:
                return self.eval(body, {**self.vars, **dict(zip(params, args))})
            finally:
                self._calls.pop()
        fn = FUNCTIONS.get(n.func)
        if fn is None:
            if n.func in self.mode.cleared_funcs:
                raise EvalError(f"'{n.func}' was removed by !clearf")
            raise EvalError(f"Unknown function '{n.func}'")
        try:
            return fn.impl(self, *args)
        except TypeError as e:
            if "positional argument" in str(e):
                raise EvalError(f"Wrong number of arguments for {n.func}") from None
            raise
        except np.linalg.LinAlgError as e:
            raise EvalError(f"{n.func}: {e}") from None
        except _props.PropsError as e:
            raise EvalError(str(e)) from None

    # ---- built-in functions ----------------------------------------------
    # Each is declared to the function registry by its @builtin line (see functions.py): its
    # signature in suggestions and, when it has one, its LaTeX form.
    def _dimless(self, x, fname):
        if not x.dimensionless:
            raise EvalError(f"{fname} needs a dimensionless argument")
        return x.to("dimensionless").magnitude

    def _square(self, A, fname):
        if _ndim(A) != 2 or A.magnitude.shape[0] != A.magnitude.shape[1]:
            raise EvalError(f"{fname} needs a square matrix")
        return A

    def _real(self, x, fname):
        """x, refused when it is complex: `fname` orders or rounds numbers."""
        if is_complex(x):
            raise EvalError(f"{fname} needs a real argument. Use re(), im() or abs() first")
        return x

    @builtin("sqrt(x)", tex=r"\sqrt{{{0}}}")
    def fn_sqrt(self, x):
        self._negative(x, "sqrt of a negative number is complex. Add 0i for the complex result: sqrt(x + 0i)")
        with np.errstate(invalid="ignore"):
            return self._as_numpy(x) ** 0.5

    @builtin("abs(x)", tex=r"\left|{0}\right|")
    def fn_abs(self, x): return abs(x)
    @builtin("floor(x)", tex=r"\left\lfloor {0} \right\rfloor")
    def fn_floor(self, x): return self.Q(np.floor(self._real(x, "floor").magnitude), x.units)
    @builtin("ceil(x)", tex=r"\left\lceil {0} \right\rceil")
    def fn_ceil(self, x): return self.Q(np.ceil(self._real(x, "ceil").magnitude), x.units)

    @builtin("heaviside(x)", tex=r"\operatorname{{H}}\left({0}\right)", aliases=("step", "heav"))
    def fn_heaviside(self, x):
        """Unit step: 0 below zero, 1 at zero and above. The argument may carry any unit."""
        return self.Q(np.where(np.asarray(self._real(x, "heaviside").magnitude) < 0, 0.0, 1.0))

    def _radians(self, x):
        """Magnitude of x in radians; a bare number is read in the current angle unit."""
        if not x.unit_items():
            x = self.Q(x.magnitude, self.mode.angle)
        return x.to("radian").magnitude

    @builtin("sin(angle)", tex=r"\sin\left({0}\right)")
    def fn_sin(self, x): return self.Q(np.sin(self._radians(x)))
    @builtin("cos(angle)", tex=r"\cos\left({0}\right)")
    def fn_cos(self, x): return self.Q(np.cos(self._radians(x)))
    @builtin("tan(angle)", tex=r"\tan\left({0}\right)")
    def fn_tan(self, x): return self.Q(np.tan(self._radians(x)))
    @builtin("asin(x)", tex=r"\arcsin\left({0}\right)")
    def fn_asin(self, x): return self.Q(np.arcsin(self._dimless(x, "asin")), "radian").to(self.mode.angle)
    @builtin("acos(x)", tex=r"\arccos\left({0}\right)")
    def fn_acos(self, x): return self.Q(np.arccos(self._dimless(x, "acos")), "radian").to(self.mode.angle)
    @builtin("atan(x)", tex=r"\arctan\left({0}\right)")
    def fn_atan(self, x): return self.Q(np.arctan(self._dimless(x, "atan")), "radian").to(self.mode.angle)
    @builtin("exp(x)", tex=r"e^{{{0}}}", binds="pow")
    def fn_exp(self, x): return self.Q(np.exp(self._dimless(x, "exp")))
    @builtin("ln(x)", tex=r"\ln\left({0}\right)")
    def fn_ln(self, x): return self.Q(np.log(self._positive(x, "ln")))
    @builtin("log10(x)", tex=r"\log_{{10}}\left({0}\right)")
    def fn_log10(self, x): return self.Q(np.log10(self._positive(x, "log10")))

    def _positive(self, x, fname):
        m = self._dimless(x, fname)
        self._negative(x, f"{fname} of a negative number is complex. Add 0i for the complex result: {fname}(x + 0i)")
        return m

    def _as_numpy(self, x):
        """x with a numpy magnitude. Python's own `(-4.0) ** 0.5` is complex; numpy's is NaN,
        so a real sheet stays real unless a complex number goes in."""
        return x if is_complex(x) else self.Q(_array(x.magnitude)[()], x.units)

    def _negative(self, x, hint):
        """Remember `hint` when x is real and negative somewhere. The result is still NaN, as
        plots and solvers expect; check_finite gives the hint instead of its usual message."""
        if not is_complex(x) and np.any(np.asarray(x.magnitude) < 0):
            self.nan_hint = hint

    # ---- complex numbers ---------------------------------------------------
    @builtin("re(z)", tex=r"\operatorname{{Re}}\left({0}\right)")
    def fn_re(self, z): return self.Q(np.real(z.magnitude), z.units)
    @builtin("im(z)", tex=r"\operatorname{{Im}}\left({0}\right)")
    def fn_im(self, z): return self.Q(np.imag(z.magnitude), z.units)
    @builtin("conj(z)", tex=r"\overline{{{0}}}")
    def fn_conj(self, z): return self.Q(np.conj(z.magnitude), z.units)

    @builtin("arg(z)", tex=r"\operatorname{{Arg}}\left({0}\right)")
    def fn_arg(self, z):
        """The angle of z, in the current angle unit (as atan gives it)."""
        return self.Q(np.angle(z.magnitude), "radian").to(self.mode.angle)

    # ---- matrices ----------------------------------------------------------
    # Every function works on the raw numpy magnitude and puts the unit back
    # afterwards, so Pint stays out of the inner loops.
    def _mat(self, A, fname):
        """The magnitude of A as a 2-D float array. A 1-D array reads as a column."""
        m = _array(A.magnitude)
        if m.ndim == 0:
            raise EvalError(f"{fname} needs a matrix or vector")
        return m.reshape(-1, 1) if m.ndim == 1 else m

    def _vec(self, A, fname):
        m = _array(A.magnitude)
        if m.ndim == 0 or (m.ndim == 2 and 1 not in m.shape):
            raise EvalError(f"{fname} needs a vector")
        return m.ravel()

    def _int(self, x, fname, lo=0):
        if _ndim(x) != 0 or not x.dimensionless or is_complex(x):
            raise EvalError(f"{fname} needs a dimensionless whole number")
        v = float(x.to("dimensionless").magnitude)
        if v != int(v) or v < lo:
            raise EvalError(f"{fname} needs a whole number of at least {lo}")
        return int(v)

    def _index(self, x, size, fname, axis):
        """A 1-based index checked against `size`, as 0-based."""
        i = self._int(x, fname, lo=-10**9)
        if not 1 <= i <= size:
            raise EvalError(f"{fname}: {axis} {i} is out of range 1..{size}")
        return i - 1

    @builtin("idx(A, i)", tex=r"{{{0:atom}}}_{{{1}}}", args=2)
    def fn_idx(self, A, i):
        """A vector element, or a matrix row as a row vector. Counts from 1."""
        m = _array(A.magnitude)
        if m.ndim == 0:
            raise EvalError("idx needs a matrix or vector")
        if m.ndim == 1 or 1 in m.shape:
            v = m.ravel()
            return self.Q(v[self._index(i, v.size, "idx", "index")], A.units)
        return self.Q(m[self._index(i, m.shape[0], "idx", "row")][None, :], A.units)

    @builtin("elem(A, i, j)", tex=r"{{{0:atom}}}_{{{1},\,{2}}}", args=3)
    def fn_elem(self, A, i, j):
        """The entry in row i, column j. Counts from 1."""
        m = self._mat(A, "elem")
        return self.Q(m[self._index(i, m.shape[0], "elem", "row"),
                        self._index(j, m.shape[1], "elem", "column")], A.units)

    @builtin("row(A, i)")
    def fn_row(self, A, i):
        m = self._mat(A, "row")
        return self.Q(m[self._index(i, m.shape[0], "row", "row")][None, :], A.units)

    @builtin("col(A, j)")
    def fn_col(self, A, j):
        m = self._mat(A, "col")
        return self.Q(m[:, self._index(j, m.shape[1], "col", "column")][:, None], A.units)

    @builtin("rows(A)")
    def fn_rows(self, A): return self.Q(float(self._mat(A, "rows").shape[0]))
    @builtin("cols(A)")
    def fn_cols(self, A): return self.Q(float(self._mat(A, "cols").shape[1]))
    @builtin("length(A)")
    def fn_length(self, A): return self.Q(float(np.asarray(A.magnitude).size))

    @builtin("det(A)", tex=r"\det\left({0}\right)")
    def fn_det(self, A):
        self._square(A, "det")
        return self.Q(np.linalg.det(A.magnitude), A.units ** A.magnitude.shape[0])

    @builtin("inv(A)", tex=r"{0:atom}^{{-1}}", binds="pow")
    def fn_inv(self, A):
        self._square(A, "inv")
        return self.Q(np.linalg.inv(A.magnitude), A.units ** -1)

    @builtin("pinv(A)", tex=r"{0:atom}^{{+}}", binds="pow")
    def fn_pinv(self, A): return self.Q(np.linalg.pinv(self._mat(A, "pinv")), A.units ** -1)
    @builtin("transpose(A)", tex=r"{0:atom}^{{T}}", binds="pow")
    def fn_transpose(self, A): return self.Q(np.atleast_2d(A.magnitude).T, A.units)

    @builtin("trace(A)", tex=r"\operatorname{{tr}}\left({0}\right)")
    def fn_trace(self, A):
        self._square(A, "trace")
        return self.Q(np.trace(A.magnitude).item(), A.units)

    @builtin("rank(A)")
    def fn_rank(self, A): return self.Q(float(np.linalg.matrix_rank(self._mat(A, "rank"))))

    @builtin("cond(A)")
    def fn_cond(self, A):
        return self.Q(float(np.linalg.cond(self._mat(A, "cond"))))

    @builtin("norm(x)", tex=r"\left\lVert {0} \right\rVert")
    def fn_norm(self, x): return self.Q(np.linalg.norm(x.magnitude), x.units)

    @builtin("diag(A)")
    def fn_diag(self, A):
        """A vector becomes a diagonal matrix, a matrix gives its diagonal as a column."""
        m = _array(A.magnitude)
        if m.ndim == 2 and 1 not in m.shape:
            return self.Q(np.diag(m)[:, None], A.units)
        return self.Q(np.diag(self._vec(A, "diag")), A.units)

    @builtin("identity(n)")
    def fn_identity(self, n): return self.Q(np.eye(self._int(n, "identity", 1)))
    @builtin("zeros(rows, cols)")
    def fn_zeros(self, r, c=None):
        return self.Q(np.zeros((self._int(r, "zeros", 1), self._int(c if c is not None else r, "zeros", 1))))
    @builtin("ones(rows, cols)")
    def fn_ones(self, r, c=None):
        return self.Q(np.ones((self._int(r, "ones", 1), self._int(c if c is not None else r, "ones", 1))))

    @builtin("solve(A, b)")
    def fn_solve(self, A, b):
        self._square(A, "solve")
        return self.Q(np.linalg.solve(A.magnitude, b.magnitude), b.units / A.units)

    @builtin("lstsq(A, b)")
    def fn_lstsq(self, A, b):
        """Least-squares solution of A x = b for any shape of A."""
        x = np.linalg.lstsq(self._mat(A, "lstsq"), self._mat(b, "lstsq"), rcond=None)[0]
        return self.Q(x, b.units / A.units)

    @builtin("chol(A)")
    def fn_chol(self, A):
        """Lower-triangular L with A = L * transpose(L)."""
        self._square(A, "chol")
        return self.Q(np.linalg.cholesky(A.magnitude), A.units ** 0.5)

    @builtin("eigvals(A)")
    def fn_eigvals(self, A):
        self._square(A, "eigvals")
        w = _settle(np.linalg.eigvals(A.magnitude))
        return self.Q(np.sort(w)[:, None], A.units)

    @builtin("eigvecs(A)")
    def fn_eigvecs(self, A):
        """Unit-length eigenvectors as columns, in the order eigvals gives the values."""
        self._square(A, "eigvecs")
        w, v = np.linalg.eig(A.magnitude)
        w, v = _settle(w), _settle(v)
        return self.Q(v[:, np.argsort(w)])

    @builtin("svdvals(A)")
    def fn_svdvals(self, A):
        return self.Q(np.linalg.svd(self._mat(A, "svdvals"), compute_uv=False)[:, None], A.units)

    @builtin("dot(a, b)", tex=r"{0:mul} \cdot {1:mul}", binds="mul", args=2)
    def fn_dot(self, a, b):
        x, y = self._vec(a, "dot"), self._vec(b, "dot")
        if x.size != y.size:
            raise EvalError(f"dot needs vectors of equal length, got {x.size} and {y.size}")
        return self.Q((x @ y).item(), a.units * b.units)

    @builtin("cross(a, b)", tex=r"{0:mul} \times {1:mul}", binds="mul", args=2)
    def fn_cross(self, a, b):
        x, y = self._vec(a, "cross"), self._vec(b, "cross")
        if x.size != 3 or y.size != 3:
            raise EvalError("cross needs two vectors of length 3")
        out = np.cross(x, y)
        row = np.shape(a.magnitude) == (1, 3)
        return self.Q(out[None, :] if row else out[:, None], a.units * b.units)

    @builtin("kron(A, B)", tex=r"{0:mul} \otimes {1:mul}", binds="mul", args=2)
    def fn_kron(self, a, b):
        return self.Q(np.kron(self._mat(a, "kron"), self._mat(b, "kron")), a.units * b.units)

    def _stack(self, fname, axis, first, rest):
        parts = [first, *rest]
        mats = [self._mat(p, fname) for p in parts]
        u0 = parts[0].units
        try:
            mags = [m * float(self.Q(1, p.units).to(u0).magnitude) for m, p in zip(mats, parts)]
            return self.Q(np.concatenate(mags, axis=axis), u0)
        except pint.errors.DimensionalityError:
            raise EvalError(f"{fname}: all parts must share one dimension") from None
        except ValueError:
            raise EvalError(f"{fname}: the parts do not fit together "
                            f"({'rows' if axis == 1 else 'columns'} differ)") from None

    @builtin("hstack(A, B, ...)")
    def fn_hstack(self, a, *rest): return self._stack("hstack", 1, a, rest)
    @builtin("vstack(A, B, ...)")
    def fn_vstack(self, a, *rest): return self._stack("vstack", 0, a, rest)

    def _reduce(self, fn, A):
        return self.Q(fn(_array(A.magnitude)).item(), A.units)

    @builtin("sum(A)")
    def fn_sum(self, A): return self._reduce(np.sum, A)
    @builtin("mean(A)")
    def fn_mean(self, A): return self._reduce(np.mean, A)
    @builtin("min(A)")
    def fn_min(self, A): return self._reduce(np.min, self._real(A, "min"))
    @builtin("max(A)")
    def fn_max(self, A): return self._reduce(np.max, self._real(A, "max"))

    @builtin('props("D", "T", T, "P", p, "Water")')
    def fn_props(self, out, *args):
        """Material and fluid properties from CoolProp: props("D", "T", 300'K, "P", 1'atm, "Water")."""
        return _props.props(self.ureg, out, *args)

    # ---- checks -----------------------------------------------------------
    def check_finite(self, q, expr=None):
        """NaN is always an error. Infinity is too, unless `expr` reaches a typed-in ∞
        (directly or through a variable holding one), so 1/0 still reports a problem."""
        mag = _array(q.magnitude)
        hint, self.nan_hint = self.nan_hint, None
        if np.any(np.isnan(mag)) and hint:
            raise EvalError(hint)
        if np.any(np.isnan(mag)) or (np.any(np.isinf(mag)) and not self.uses_infinity(expr)):
            raise EvalError("Result is not finite (division by zero or domain error)")
        return q

    def settle(self, q):
        """A line's value as the sheet keeps it: a complex value whose imaginary parts are all
        zero becomes real. Under `!complex real` a value with an imaginary part is an error;
        one too small to show (1e-12 of the value) is dropped instead."""
        if not is_complex(q):
            return q
        m = np.asarray(q.magnitude)
        if self.mode.complex == "real":
            if np.any(np.abs(m.imag) > _TINY * np.abs(m)):
                raise EvalError("The result is complex, and !complex real allows only real results")
            return self.Q(m.real, q.units)
        return self.Q(m.real, q.units) if not np.any(m.imag) else q

    def uses_infinity(self, expr):
        for name in names_in(expr) if expr is not None else ():
            if name == "∞":
                return True
            if self.is_var(name) and np.any(np.isinf(_array(self.vars[self.vkey(name)].magnitude))):
                return True
        return False
