"""Line parser. Assignment and function definitions are split off first (by
sheettext.definition) so the Lark grammar only has to describe expressions (this avoids an
LALR reduce/reduce clash between `f(x) = ...` and the call `f(x)`)."""

from lark import Lark, Transformer, v_args
from lark.exceptions import UnexpectedInput

from . import catalogue
from .nodes import (Assign, BinOp, Call, Convert, ExprStmt, FuncDef, Implicit,
                    Matrix, Name, Neg, Num, Polar, Str, UnitDef, UnitLit)
from .sheettext import NAME, NUMBER, STRING, UNIT, definition

GRAMMAR = r"""
?start: expr

?expr: sum
     | sum "->" sum                 -> convert

?sum: polar
    | sum "+" polar                 -> add
    | sum "-" polar                 -> sub

?polar: product
      | product "∠" product         -> polar

?product: unary
        | product "*" unary         -> mul
        | product "/" unary         -> div
        | product ".*" unary        -> emul
        | product "./" unary        -> ediv

?unary: "-" unary                   -> neg
      | power
      | NUMBER power_nn+            -> implicit

?power: atom
      | atom "^" pexp               -> pow

?power_nn: atom_nn
         | atom_nn "^" pexp         -> pow

?pexp: "-" pexp                     -> neg
     | power

?atom: NUMBER                       -> num
     | STRING                       -> string
     | atom_nn

?atom_nn: NAME                      -> name
        | UNIT                      -> unitlit
        | "∞"                       -> infinity
        | "(" expr ")"
        | NAME "(" args ")"         -> call
        | "[" row (";" row)* "]"    -> matrix

args: expr ("," expr)*
row: expr ("," expr)*

%import common.WS
%ignore WS
""" + f"""
NAME: /{NAME}/
NUMBER: /{NUMBER}/
STRING: /{STRING}/
UNIT: /{UNIT}/
"""


def _number(t):
    """A NUMBER token's value: `4i` and `4j` are imaginary."""
    t = str(t)
    return complex(0, float(t[:-1])) if t[-1] in "ij" else float(t)


@v_args(inline=True)
class _ToAst(Transformer):
    def num(self, t): return Num(_number(t))
    def string(self, t): return Str(str(t)[1:-1])
    def name(self, t): return Name(str(t))
    def infinity(self): return Name("∞")
    def unitlit(self, t): return UnitLit(str(t)[1:])
    def neg(self, x): return Neg(x)
    def add(self, a, b): return BinOp("+", a, b)
    def sub(self, a, b): return BinOp("-", a, b)
    def mul(self, a, b): return BinOp("*", a, b)
    def div(self, a, b): return BinOp("/", a, b)
    def emul(self, a, b): return BinOp(".*", a, b)
    def ediv(self, a, b): return BinOp("./", a, b)
    def pow(self, a, b): return BinOp("^", a, b)
    def convert(self, a, b): return Convert(a, b)
    def polar(self, r, angle): return Polar(r, angle)
    def implicit(self, n, *factors): return Implicit(Num(_number(n)), tuple(factors))
    def args(self, *a): return tuple(a)
    def row(self, *a): return tuple(a)
    def call(self, name, args): return Call(str(name), args)
    def matrix(self, *rows): return Matrix(tuple(rows))


_parser = Lark(GRAMMAR, parser="lalr", start="start", transformer=_ToAst())

class ParseError(Exception):
    pass


def parse_expr(src):
    try:
        return _parser.parse(src)
    except UnexpectedInput as e:
        col = getattr(e, "column", 0)
        bad = src[max(col - 1, 0):]
        raise ParseError(f"Syntax error at column {col}: {bad[:12]!r}{catalogue.syntax_hint(bad)}") from None


def parse_line(src):
    src = src.strip()
    d = definition(src)
    if d is None:
        return ExprStmt(parse_expr(src))
    if d.kind == "unitdef":
        return UnitDef(d.name, parse_expr(d.body), d.body.strip())
    if d.kind == "funcdef":
        return FuncDef(d.name, d.params, parse_expr(d.body))
    return Assign(d.name, parse_expr(d.body))
