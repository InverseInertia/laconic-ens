"""Reverse Polish input (`!rpn`, rpn.py): the translation into the infix parser's AST, units,
functions, the errors a stack gives, the typeset (infix) result, Rename, and which lines the mode
covers."""
import pytest

from laconic import run
from laconic.exports import export
from laconic.parser import parse_expr, parse_line as parse_infix
from laconic.rename import rename
from laconic.rpn import RPNError, parse_expr_rpn, parse_line
from laconic.sheet import evaluator_at
from laconic.sheettext import scan


def shown(r):
    return r.text.split("= ")[-1]


@pytest.mark.parametrize("rpn, infix", [
    ("3 4 +", "3 + 4"),
    ("a b c * +", "a + b * c"),
    ("a b + c *", "(a + b) * c"),
    ("a b - c -", "a - b - c"),
    ("a b c - -", "a - (b - c)"),
    ("x 2 ^", "x^2"),
    ("A B .*", "A .* B"),
    ("A B ./", "A ./ B"),
    ("3'm", "3'm"),
    ("2.5e3'Pa", "2.5e3'Pa"),
    ("9.81'm/'s^2", "9.81'm/'s^2"),
    ("12'kN'm", "12'kN'm"),
    ("-4", "-4"),
    ("4i", "4i"),
    ("∞", "∞"),
    ("x neg", "-x"),
    ("x 'km ->", "x -> 'km"),
    ("5'V 30'deg ∠", "5'V∠30'deg"),
    ("[1, 2; 3, 4] det", "det([1, 2; 3, 4])"),
    ("x sqrt", "sqrt(x)"),
    ("A i idx", "idx(A, i)"),
    ("A B hstack/2", "hstack(A, B)"),
    ("A B .f/2", ".f(A, B)"),
    ('"Tcrit" "Water" props/2', 'props("Tcrit", "Water")'),
    ("~g 2 *", "~g * 2"),
])
def test_rpn_builds_the_tree_the_infix_parser_builds(rpn, infix):
    from laconic.evaluator import Evaluator
    from laconic.functions import FUNCTIONS
    arity = lambda name: FUNCTIONS[name].arity if name in FUNCTIONS else None   # noqa: E731
    Evaluator()   # fills FUNCTIONS
    assert parse_expr_rpn(rpn, arity) == parse_expr(infix)


def test_an_assignment_keeps_its_name_and_a_function_its_head():
    assert parse_line("F = m a *") == parse_infix("F = m * a")
    assert parse_line("f(x, y) = x 2 ^ y +") == parse_infix("f(x, y) = x^2 + y")


def test_lines_below_rpn_run_with_units():
    rs = run("m = 2'kg\na = 3'm/'s^2\n!rpn\nF = m a *\n3'm 4'm +\n9.81'm/'s^2 'ft/'s^2 ->\nv = 10'V 30'deg ∠")
    assert rs[3].text == "F = 6 N"
    assert shown(rs[4]) == "7 m"
    assert shown(rs[5]) == "32.19 ft/s²"
    assert rs[6].kind == "assign" and not rs[6].error


def test_functions_by_name_by_count_and_elementwise():
    rs = run("!rpn\nhypot(a, b) = a 2 ^ b 2 ^ + sqrt\nc = 3 4 hypot\nf(x) = x 2 ^ 1 +\n3 f\n"
             "A = [1, 2; 3, 4]\nA 1 hypot\nA 1 .hypot/2\n16 sqrt\nA 2 idx\n[1, 2] [3, 4] hstack/2")
    assert rs[1].kind == "funcdef" and rs[1].stages == [r"\sqrt{a^{2} + b^{2}}"]
    assert rs[2].text == "c = 5"
    assert shown(rs[4]) == "10"
    assert "error" not in rs[7].kind and rs[7].text.startswith("[[1.414")
    assert shown(rs[8]) == "4"
    assert rs[9].text == "[[3 4]]"
    assert rs[10].text == "[[1 2 3 4]]"


def test_a_variable_the_line_sees_wins_over_a_function_of_its_name_and_parameters_are_local():
    rs = run("f(x) = 2*x\n!rpn\nf = 10\nf 1 +\nf 3 f/1 +\ng(f) = f 1 +\n4 g")
    assert shown(rs[3]) == "11"          # f the variable
    assert shown(rs[4]) == "16"          # f/1 still calls the function
    assert shown(rs[6]) == "5"           # g's parameter f is a value, not the function


@pytest.mark.parametrize("src, error", [
    ("1 +", "RPN: `+` needs two values, the stack has one"),
    ("+", "RPN: `+` needs two values, the stack is empty"),
    ("neg", "RPN: `neg` needs one value, the stack is empty"),
    ("1 2 3 +", "RPN: 2 values are left on the stack; an expression must leave exactly one"),
    ("1 2 hstack/3", "RPN: `hstack/3` needs three values, the stack has two"),
    ("x f/0", "RPN: `f/0` calls f with no values; a function takes at least one"),
    ("m*a", "RPN: `m*a` is not a number, unit, name or operator. Separate every value and operator with a space: `m a *`"),
    ("sqrt(2)", "RPN: `sqrt(2)` is not a value or operator. Write a call as its values and then the function's name"),
    ("-x", "RPN: `-x` is not a value. Minus a name is written `x neg`"),
    ("A .f","RPN: `.f` needs the number of values f takes, e.g. `.f/2`"),
    ("1 $x +", "$x declares a symbol"),
])
def test_a_stack_that_runs_short_or_has_values_left_is_an_error_on_the_line(src, error):
    r = run("!rpn\n" + src + "\n2 3 *")
    assert r[1].kind == "error" and r[1].error.startswith(error)
    assert shown(r[2]) == "6"            # the lines below still run


def test_an_assignment_with_nothing_after_its_name_is_still_an_error():
    with pytest.raises(RPNError, match="there is no expression"):
        parse_expr_rpn("   ")


def test_results_are_typeset_in_infix_as_the_same_line_typed_infix_is():
    head = "m = 2'kg\na = 3'm/'s^2\nf(x) = x^2 + 1\n"
    rpn = run(head + "!rpn\nF = m a *\nm a + f\nq(t) = t 2 ^ 3 *\n")
    infix = run(head + "F = m * a\nf(m + a)\nq(t) = t^2 * 3\n")
    for r, i in zip(rpn[4:], infix[3:]):
        assert (r.kind, r.lhs, r.stages) == (i.kind, i.lhs, i.stages)
    assert rpn[4].stages[0] == r"m \cdot a"


def test_exports_show_infix():
    tex = export("m = 2\na = 3\n!rpn\nF = m a *", "tex")
    assert r"m \cdot a" in tex and "m a *" not in tex.split(r"\begin{document}")[-1].replace("% !rpn", "")


def test_symbols_work_in_reverse_polish():
    rs = run("$x\n!rpn\nq = x 2 ^ 3 *\nx = 2\nq 1 +")
    assert rs[2].kind == "assign" and "{x}^{2}" in rs[2].stages[-1]
    assert shown(rs[4]) == "13"


def test_rename_reaches_names_on_reverse_polish_lines():
    text = "m = 2\nf(x) = x 2 *\n!rpn\nF = m 3 *\nm f\nm m f/1 +"
    edits, count = rename(text, "m", "mass")
    assert count == 5
    from laconic.blockedit import apply
    renamed = apply(text, edits)
    assert renamed.endswith("F = mass 3 *\nmass f\nmass mass f/1 +")
    edits, count = rename(text, "f", "g")
    assert apply(text, edits).endswith("m g\nm m g/1 +") and count == 3


def test_what_rpn_leaves_alone():
    """Unit definitions, comments, headings, commands, symbols and the lines a block owns read as on
    any other line; !rpn off and the end of the sheet end the mode, !clear does not."""
    text = ("!rpn\n'smoot = 1.7018'm\n## Heading\n# a b +\n$s\nx = 2\n!root x\n  equation: x^2 = 4\n"
            "S = 0\n!loop i = 1 .. 3\n  S = S + i\n!plot x*t, t = 0 .. 1\n  xlim: 0 .. 2\n!clear\n1'smoot 2 *\n"
            "!rpn off\n2 * 3")
    rs = run(text)
    assert [r.kind for r in rs if r.error] == []
    assert rs[1].kind == "unitdef" and rs[3].kind == "comment"
    assert rs[9].kind == "loop" and rs[9].text.startswith("S = 6")
    assert shown(rs[14]) == "3.404 m"
    assert shown(rs[16]) == "6"


def test_the_editor_reads_the_same_lines_as_reverse_polish_as_the_run_does():
    """sheettext's Line.rpn (which the editor's isRpnAt is held to) is true exactly where the sheet
    runs a calculation with the mode on."""
    text = ("x = 1\n!rpn\nx 1 +\n\n# c\n!rpn nonsense\ny = x 2 *\n!root x\n  equation: x = 2\n  !rpn off\n"
            "x 3 +\n!rpn off\nx + 1\n!rpn on\nz = x 1 +")
    sheet = scan(text)
    for line in sheet.lines:
        calculation = line.block is None and line.kind in ("blank", "funcdef", "assign", "expr")
        assert line.rpn == (calculation and evaluator_at(text, line.n).mode.rpn), line.n
    assert [l.n for l in sheet.lines if l.rpn] == [3, 4, 7, 11, 15]
