"""Line parser. Assignment and function definitions are split off with regexes
so the Lark grammar only has to describe expressions (this avoids an
LALR reduce/reduce clash between `f(x) = ...` and the call `f(x)`)."""
import re

from lark import Lark, Transformer, v_args
from lark.exceptions import UnexpectedInput

from .nodes import (Assign, BinOp, Call, Convert, ExprStmt, FuncDef, Implicit,
                    Matrix, Name, Neg, Num, Str, UnitDef, UnitLit)

GRAMMAR = r"""
?start: expr

?expr: sum
     | sum "->" sum                 -> convert

?sum: product
    | sum "+" product               -> add
    | sum "-" product               -> sub

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

NAME: /~?[^\W\d]\w*[`!@]*/
NUMBER: /(\d+(\.\d+)?|\.\d+)([eE][+-]?\d+)?/
STRING: /"[^"\n]*"/
UNIT: /'(?:(?:[^\W\d]|°)[\w°]*|%)/

%import common.WS
%ignore WS
"""


@v_args(inline=True)
class _ToAst(Transformer):
    def num(self, t): return Num(float(t))
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
    def implicit(self, n, *factors): return Implicit(Num(float(n)), tuple(factors))
    def args(self, *a): return tuple(a)
    def row(self, *a): return tuple(a)
    def call(self, name, args): return Call(str(name), args)
    def matrix(self, *rows): return Matrix(tuple(rows))


_parser = Lark(GRAMMAR, parser="lalr", start="start", transformer=_ToAst())

_FUNC_RE = re.compile(
    r"^(~?[^\W\d]\w*)\s*\(\s*([^\W\d]\w*(?:\s*,\s*[^\W\d]\w*)*)\s*\)\s*=(?!=)\s*(.+)$")
_UNITDEF_RE = re.compile(r"^'([^\W\d]\w*)\s*=(?!=)\s*(.+)$")
_ASSIGN_RE = re.compile(r"^(~?[^\W\d]\w*[`!@]*)\s*=(?!=)\s*(.+)$")


class ParseError(Exception):
    pass


def parse_expr(src):
    try:
        return _parser.parse(src)
    except UnexpectedInput as e:
        col = getattr(e, "column", 0)
        bad = src[max(col - 1, 0):]
        hint = ""
        if bad.startswith("%"):
            hint = ". Percent is a unit: write 5'%"
        elif bad.startswith("$"):
            hint = ". Currencies are units named by their ISO code: write 5'USD, 'EUR, 'GBP"
        raise ParseError(f"Syntax error at column {col}: {bad[:12]!r}{hint}") from None


def parse_line(src):
    src = src.strip()
    m = _UNITDEF_RE.match(src)
    if m:
        return UnitDef(m.group(1), parse_expr(m.group(2)), m.group(2).strip())
    m = _FUNC_RE.match(src)
    if m:
        params = tuple(p.strip() for p in m.group(2).split(","))
        return FuncDef(m.group(1), params, parse_expr(m.group(3)))
    m = _ASSIGN_RE.match(src)
    if m:
        return Assign(m.group(1), parse_expr(m.group(2)))
    return ExprStmt(parse_expr(src))
