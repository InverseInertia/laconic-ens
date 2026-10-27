"""AST node types. One tree feeds both the evaluator and the LaTeX printer."""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Num:
    value: float  # complex for an imaginary literal, `4i`


@dataclass(frozen=True)
class Str:
    """`"Water"`: text, only meaningful as a built-in function argument."""
    value: str


@dataclass(frozen=True)
class Name:
    name: str


@dataclass(frozen=True)
class UnitLit:
    unit: str


@dataclass(frozen=True)
class Neg:
    operand: Any


@dataclass(frozen=True)
class BinOp:
    op: str  # + - * / .* ./ ^
    left: Any
    right: Any


@dataclass(frozen=True)
class Polar:
    """`5'V∠30'deg`: a complex number from its magnitude and angle."""
    magnitude: Any
    angle: Any


@dataclass(frozen=True)
class Implicit:
    """`2 m v^2`: a number followed by one or more juxtaposed factors."""
    number: Num
    factors: tuple


@dataclass(frozen=True)
class Call:
    func: str
    args: tuple


@dataclass(frozen=True)
class Matrix:
    rows: tuple


@dataclass(frozen=True)
class Convert:
    expr: Any
    target: Any


@dataclass(frozen=True)
class Assign:
    name: str
    expr: Any


@dataclass(frozen=True)
class FuncDef:
    name: str
    params: tuple
    body: Any


@dataclass(frozen=True)
class UnitDef:
    """`'smoot = 1.7018'm`: defines a unit. `source` is the right-hand side as typed."""
    name: str
    expr: Any
    source: str


@dataclass(frozen=True)
class ExprStmt:
    expr: Any


def is_literal(n):
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
