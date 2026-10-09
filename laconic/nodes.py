"""AST node types. One tree feeds both the evaluator and the LaTeX printer."""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Num:
    value: float


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
class ExprStmt:
    expr: Any
