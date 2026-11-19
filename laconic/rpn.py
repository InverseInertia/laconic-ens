"""Reverse Polish input: the lines below `!rpn` (and above `!rpn off`) are read here instead of
by the infix grammar. Each expression is translated into the same AST nodes `parser.py` builds,
so evaluation, units, typesetting (in ordinary infix), symbolic math and the exports work as they
do for any line, and only the reading of the text differs.

    F = m a *            an assignment keeps its infix name; the right of = is RPN
    f(x) = x 2 ^ 1 +     a function definition takes its body in RPN
    3'm 4'm +            a bare expression is RPN throughout

Tokens are separated by whitespace. A value is a number in the sheet's own syntax, with its
units (`3'm`, `2.5e3'Pa`, `9.81'm/'s^2`, `-4`, `4i`, `∞`), a unit on its own (`'km`), a quoted
string (`"Water"`), a matrix written as anywhere else (`[1, 2; 3, 4]`, read whole by the infix
parser) or a name. The binary operators are the grammar's: `+ - * / ^ .* ./`, `∠` (polar) and
`->` (convert the value below into the units on top). `neg` is unary minus.

A function is called by its name followed by the number of values it takes, `f/2` (`.f/2` calls
it on each element). A user function, or a built-in that always takes the same number of
arguments, can be called by its name alone. A name the line can see as a variable, or a function
definition's parameter, is always that variable."""
import re

from .nodes import Assign, BinOp, Call, Convert, ExprStmt, FuncDef, Matrix, Name, Neg, Polar
from .parser import ParseError, parse_expr, parse_line as parse_infix_line
from .sheettext import NAME, NUMBER, UNIT, definition

NEG = "neg"
BINARY = ("+", "-", "*", "/", "^", ".*", "./")

_UNITS = rf"{UNIT}(?:\^-?{NUMBER})?(?:[*/]?{UNIT}(?:\^-?{NUMBER})?)*"
_LITERAL = re.compile(rf"-?(?:{NUMBER}(?:{_UNITS})?|{_UNITS}|∞)\Z")
_CALL = re.compile(rf"(\.?)({NAME})/(\d+)\Z")
_NAME = re.compile(rf"(\.?)({NAME})\Z")
_WORDS = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")


class RPNError(ParseError):
    pass


def _word(n):
    return _WORDS[n] if n < len(_WORDS) else str(n)


def _count(n):
    """`two values`, `one value`."""
    return f"{_word(n)} value{'s' * (n != 1)}"


def tokens(src):
    """The whitespace-separated tokens of `src`, a quoted string or a bracketed matrix (which may
    hold spaces) each in one piece."""
    out, i, n = [], 0, len(src)
    while i < n:
        if src[i].isspace():
            i += 1
            continue
        j = i
        if src[i] == '"':
            k = src.find('"', i + 1)
            j = n if k < 0 else k + 1
        elif src[i] == "[":
            depth = 0
            while j < n:
                c = src[j]
                if c == '"':
                    k = src.find('"', j + 1)
                    j = n - 1 if k < 0 else k
                elif c == "[":
                    depth += 1
                elif c == "]":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            j = min(j + 1, n)
        else:
            while j < n and not src[j].isspace():
                j += 1
        out.append(src[i:j])
        i = j
    return out


def _bad(tok):
    if "(" in tok or ")" in tok:
        return (f"RPN: `{tok}` is not a value or operator. Write a call as its values and then the "
                f"function's name, `x sqrt` or `a b f/2`")
    if tok.startswith("-") and _NAME.match(tok[1:]):
        return f"RPN: `{tok}` is not a value. Minus a name is written `{tok[1:]} neg`"
    return (f"RPN: `{tok}` is not a number, unit, name or operator. Separate every value and "
            f"operator with a space: `m a *`")


def parse_expr_rpn(src, arity=None, local=()):
    """The expression node for the RPN text `src`. `arity(name)` is how many arguments a bare `name`
    takes when it calls a function, or None when it is a variable; names in `local` (a function's
    parameters) are always variables. Raises RPNError for a stack that runs short or has more
    than one value left."""
    stack = []

    def pop(tok, k):
        if len(stack) < k:
            has = f"the stack has {_word(len(stack))}" if stack else "the stack is empty"
            raise RPNError(f"RPN: `{tok}` needs {_count(k)}, {has}")
        args = stack[len(stack) - k:]
        del stack[len(stack) - k:]
        return args

    def call(tok, dot, name, k):
        if k == 0:
            raise RPNError(f"RPN: `{tok}` calls {name} with no values; a function takes at least one")
        stack.append(Call(name, tuple(pop(tok, k)), elementwise=bool(dot)))

    for tok in tokens(src):
        if tok in BINARY:
            a, b = pop(tok, 2)
            stack.append(BinOp(tok, a, b))
        elif tok == "->":
            a, b = pop(tok, 2)
            stack.append(Convert(a, b))
        elif tok == "∠":
            a, b = pop(tok, 2)
            stack.append(Polar(a, b))
        elif tok == NEG:
            stack.append(Neg(pop(tok, 1)[0]))
        elif tok.startswith('"'):
            stack.append(parse_expr(tok))
        elif tok.startswith("["):
            node = parse_expr(tok)
            if not isinstance(node, Matrix):
                raise RPNError(f"RPN: `{tok}` is not a matrix")
            stack.append(node)
        elif _LITERAL.match(tok):
            stack.append(parse_expr(tok))
        elif m := _CALL.match(tok):
            call(tok, m.group(1), m.group(2), int(m.group(3)))
        elif m := _NAME.match(tok):
            dot, name = m.groups()
            if "$" in name:
                parse_expr(name)          # says how a symbol is declared
            k = None if name in local or arity is None else arity(name)
            if dot and k is None:
                raise RPNError(f"RPN: `{tok}` needs the number of values {name} takes, e.g. `{tok}/2`")
            if k is None:
                stack.append(Name(name))
            else:
                call(tok, dot, name, k)
        else:
            raise RPNError(_bad(tok))
    if not stack:
        raise RPNError("RPN: there is no expression. Write values, then the operator: `3 4 +`")
    if len(stack) > 1:
        raise RPNError(f"RPN: {len(stack)} values are left on the stack; an expression must leave exactly one")
    return stack[0]


def parse_line(src, arity=None):
    """A line read in reverse Polish: an assignment's name and a function's head stay as written,
    and the expression is RPN. Unit definitions and symbol declarations read as on any line."""
    src = src.strip()
    d = definition(src)
    if d is not None and d.kind in ("unitdef", "symdef"):
        return parse_infix_line(src)
    if d is None:
        return ExprStmt(parse_expr_rpn(src, arity))
    if d.kind == "funcdef":
        return FuncDef(d.name, d.params, parse_expr_rpn(d.body, arity, local=d.params))
    return Assign(d.name, parse_expr_rpn(d.body, arity))
