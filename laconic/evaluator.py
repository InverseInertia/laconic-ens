"""Evaluator: walks the AST and produces Pint quantities.

Every value is a Pint Quantity, scalars and matrices alike, so the arithmetic
code has one path instead of two."""
import math
from functools import lru_cache

import numpy as np
import pint

from .nodes import (Assign, BinOp, Call, Convert, ExprStmt, FuncDef, Implicit,
                    Matrix, Name, Neg, Num, UnitLit)

CONSTANTS = {"pi": math.pi, "e": math.e}


class EvalError(Exception):
    pass


@lru_cache(maxsize=1)
def registry():
    # Building a registry takes a noticeable fraction of a second, so share one.
    return pint.UnitRegistry(autoconvert_offset_to_baseunit=True)


def _ndim(q):
    return np.ndim(q.magnitude)


class Evaluator:
    def __init__(self):
        self.ureg = registry()
        self.Q = self.ureg.Quantity
        self.vars = {}
        self.funcs = {}
        self.cleared = set()   # names removed by !clear, for a clearer error

    # ---- name classification (shared with the LaTeX printer) -------------
    def is_var(self, name, local=()):
        return name in self.vars or name in local

    def is_unit(self, name):
        try:
            self.ureg.parse_units(name)
            return True
        except Exception:
            return False

    def is_unit_node(self, node):
        """True for `'kN` and `'mm^4`. Units are lexically marked, so a bare
        name is always a variable."""
        if isinstance(node, UnitLit):
            return True
        return isinstance(node, BinOp) and node.op == "^" and self.is_unit_node(node.left)

    # ---- evaluation -------------------------------------------------------
    def eval(self, node, scope=None):
        scope = self.vars if scope is None else scope
        return getattr(self, "ev_" + type(node).__name__)(node, scope)

    def ev_Num(self, n, scope):
        return self.Q(n.value)

    def ev_Name(self, n, scope):
        if n.name in scope:
            return scope[n.name]
        if n.name in CONSTANTS:
            return self.Q(CONSTANTS[n.name])
        if n.name in self.cleared:
            raise EvalError(f"'{n.name}' was removed by !clear")
        hint = f". Units need an apostrophe: '{n.name}" if self.is_unit(n.name) else ""
        raise EvalError(f"'{n.name}' is not defined{hint}")

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
        num = f"{n.number.value:g}"
        for f in n.factors:
            if not self.is_unit_node(f):
                what = f.name if isinstance(f, Name) else "an expression"
                raise EvalError(f"{what} cannot follow a number directly. Write {num}*{what} to multiply; "
                                f"units need an apostrophe, e.g. {num}'{what}")
        first = self.unit_value(n.factors[0], scope)
        result = self.Q(n.number.value, first.units)  # direct build keeps degC working
        for f in n.factors[1:]:
            result = result * self.unit_value(f, scope)
        return result

    def ev_BinOp(self, n, scope):
        a, b = self.eval(n.left, scope), self.eval(n.right, scope)
        op = n.op
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
                return np.matmul(a, b)
            except ValueError:
                raise EvalError(f"Shape mismatch for *: {np.shape(a.magnitude)} * {np.shape(b.magnitude)}. "
                                "Use .* for elementwise") from None
        return a * b

    def power(self, a, b):
        if _ndim(b) != 0 or not b.dimensionless:
            raise EvalError("Exponent must be a dimensionless scalar")
        n = float(b.to("dimensionless").magnitude)
        if _ndim(a) == 2:
            if n != int(n):
                raise EvalError("Matrix powers must be integers")
            n = int(n)
            try:
                return self.Q(np.linalg.matrix_power(a.magnitude, n), a.units ** n)
            except np.linalg.LinAlgError:
                raise EvalError("Matrix is singular") from None
        return a ** n

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
                try:
                    out.append(float(e.to(unit0).magnitude))
                except pint.errors.DimensionalityError:
                    raise EvalError("Matrix entries must share one dimension") from None
            data.append(out)
        return self.Q(np.array(data), unit0)

    def ev_Convert(self, n, scope):
        v, target = self.eval(n.expr, scope), self.eval(n.target, scope)
        return v.to(target.units)

    def ev_Call(self, n, scope):
        args = [self.eval(a, scope) for a in n.args]
        if n.func in self.funcs:
            params, body = self.funcs[n.func]
            if len(args) != len(params):
                raise EvalError(f"{n.func} takes {len(params)} argument(s), got {len(args)}")
            return self.eval(body, {**self.vars, **dict(zip(params, args))})
        fn = getattr(self, "fn_" + n.func, None)
        if fn is None:
            raise EvalError(f"Unknown function '{n.func}'")
        try:
            return fn(*args)
        except TypeError as e:
            if "positional argument" in str(e):
                raise EvalError(f"Wrong number of arguments for {n.func}") from None
            raise
        except np.linalg.LinAlgError as e:
            raise EvalError(f"{n.func}: {e}") from None

    # ---- built-in functions ----------------------------------------------
    def _dimless(self, x, fname):
        if not x.dimensionless:
            raise EvalError(f"{fname} needs a dimensionless argument")
        return x.to("dimensionless").magnitude

    def _square(self, A, fname):
        if _ndim(A) != 2 or A.magnitude.shape[0] != A.magnitude.shape[1]:
            raise EvalError(f"{fname} needs a square matrix")
        return A

    def fn_sqrt(self, x): return x ** 0.5
    def fn_abs(self, x): return abs(x)
    def fn_sin(self, x): return self.Q(np.sin(x.to("radian").magnitude))
    def fn_cos(self, x): return self.Q(np.cos(x.to("radian").magnitude))
    def fn_tan(self, x): return self.Q(np.tan(x.to("radian").magnitude))
    def fn_asin(self, x): return self.Q(np.arcsin(self._dimless(x, "asin")), "radian")
    def fn_acos(self, x): return self.Q(np.arccos(self._dimless(x, "acos")), "radian")
    def fn_atan(self, x): return self.Q(np.arctan(self._dimless(x, "atan")), "radian")
    def fn_exp(self, x): return self.Q(np.exp(self._dimless(x, "exp")))
    def fn_ln(self, x): return self.Q(np.log(self._dimless(x, "ln")))
    def fn_log10(self, x): return self.Q(np.log10(self._dimless(x, "log10")))

    def fn_det(self, A):
        self._square(A, "det")
        return self.Q(np.linalg.det(A.magnitude), A.units ** A.magnitude.shape[0])

    def fn_inv(self, A):
        self._square(A, "inv")
        return self.Q(np.linalg.inv(A.magnitude), A.units ** -1)

    def fn_transpose(self, A): return self.Q(np.atleast_2d(A.magnitude).T, A.units)
    def fn_norm(self, x): return self.Q(np.linalg.norm(x.magnitude), x.units)
    def fn_identity(self, n): return self.Q(np.eye(int(self._dimless(n, "identity"))))

    def fn_solve(self, A, b):
        self._square(A, "solve")
        return self.Q(np.linalg.solve(A.magnitude, b.magnitude), b.units / A.units)

    # ---- statements -------------------------------------------------------
    def check_finite(self, q):
        if not np.all(np.isfinite(np.asarray(q.magnitude, dtype=float))):
            raise EvalError("Result is not finite (division by zero or domain error)")
        return q
