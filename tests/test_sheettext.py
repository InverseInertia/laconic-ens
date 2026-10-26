"""The worksheet text module, at its interface: line kinds, block ownership, expression spans,
tokens and definitions. The lexer and definition cases are shared with the editor's JS through
sheettext_vectors.json (see test_sheettext.js)."""
import json
from pathlib import Path

import pytest

from laconic.sheettext import definition, is_name, scan, tokenize

VECTORS = json.loads(Path(__file__).with_name("sheettext_vectors.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", VECTORS["tokens"], ids=lambda c: c["line"])
def test_tokens(case):
    assert [[t.kind, t.start, t.text] for t in tokenize(case["line"])] == case["tokens"]


@pytest.mark.parametrize("case", VECTORS["definitions"], ids=lambda c: c["line"])
def test_definitions(case):
    d = definition(case["line"])
    assert (d and [d.kind, d.name, list(d.params)]) == case["def"]


@pytest.mark.parametrize("case", VECTORS["solver_blocks"], ids=lambda c: f"{c['text']}@{c['line']}")
def test_solver_block_of_a_line(case):
    b = scan(case["text"]).owner(case["line"])
    got = {"kind": b.command, "unknowns": [u.strip() for u in b.args.split(",")]} \
        if b and b.kind == "solver" else None
    assert got == case["block"]


# Each case: worksheet text, then per line (kind, header line of the owning block or None).
LINES = [
    ("", []),
    ("x = 1\n\n## Head\n#@ meta\n# note\n!clear\n2*x\nf(x) = x\n'u = 2'm",
     [("assign", None), ("blank", None), ("heading", None), ("meta", None), ("comment", None),
      ("command", None), ("expr", None), ("funcdef", None), ("unitdef", None)]),
    ("!plot x, x = 0 .. 1\n  title: A\n  grid: off\n\nx = 2",
     [("plot", 1), ("plotopt", 1), ("plotopt", 1), ("blank", None), ("assign", None)]),
    ("!plot x, x = 0 .. 1\n  y = 2",                       # only option lines belong to a plot
     [("plot", 1), ("assign", None)]),
    ("!root x\n  equation: x = 1\n  # aside\n  y = 2\n  #@ result {}\n\n  z = 1",
     [("solver", 1), ("solveropt", 1), ("solveropt", 1), ("solveropt", 1), ("solveropt", 1),
      ("blank", None), ("assign", None)]),                # a solver owns every indented line until a blank
    ("!root x\n  !root y\n  'u = 2'm",                     # owned lines are never headers; a unit definition stays one
     [("solver", 1), ("solveropt", 1), ("unitdef", 1)]),
    ("!plot x, x = 0 .. 1\n!minimize d\n  objective: d",
     [("plot", 1), ("solver", 2), ("solveropt", 2)]),
    ("!plot\n'u == 2",                                     # a bare !plot is a command; any '...= starts a unit definition
     [("command", None), ("unitdef", None)]),
]


@pytest.mark.parametrize("text,expected", LINES)
def test_line_kinds_and_owners(text, expected):
    sheet = scan(text)
    assert [(l.kind, l.block) for l in sheet.lines] == expected
    for l in sheet.lines:
        b = sheet.owner(l.n)
        assert (b.header if b else None) == l.block
        assert not b or b.lines[0].n == b.header and l in b.lines


def _spans(line):
    return [line.text[a:b] for a, b in line.spans]


# Each case: one line in context (the last line of the text), and the parts of it that are expressions.
SPANS = [
    ("x = a + 1", ["x = a + 1"]),
    ("# a comment", []),
    ("!clear", []),
    ("!plot f(x), x = 0 .. L", [" f(x), x = 0 .. L"]),
    ("!plot f(x), x = 0 .. 1\n  xlim: 0 .. L", ["0 .. L"]),
    ("!plot f(x), x = 0 .. 1\n  title: L", []),
    ('!plot f(x), x = 0 .. 1\n  note: "peak L" at (a, b)', ["a, b"]),
    ("!root x, y", [" x, y"]),
    ("!root x\n  equation: x^2 = L", ["x^2 = L"]),
    ("!root x\n  bounds x: 0 .. L", ["x", "0 .. L"]),
    ("!root x\n  method: hybr", []),
    ('!root x\n  #@ result {"hash": "x"}', []),
]


@pytest.mark.parametrize("text,expected", SPANS)
def test_expression_spans(text, expected):
    assert _spans(scan(text).lines[-1]) == expected


def test_options_and_stored_results_are_read_by_the_owning_block():
    sheet = scan('!plot f(x), x = 0 .. 1\n  color 2: red\n!root x\n  bounds x: 0 .. 1\n  #@ result {"a":1}')
    plot, bounds, stored = sheet.line(2), sheet.line(4), sheet.line(5)
    assert (plot.option.key, plot.option.arg, plot.option.value) == ("color", "2", "red")
    assert (bounds.option.key, bounds.option.arg, bounds.option.value) == ("bounds", "x", "0 .. 1")
    assert stored.result == '{"a":1}' and stored.option is None
    assert sheet.block(1).command == "plot" and sheet.block(1).args == "f(x), x = 0 .. 1"
    assert sheet.block(3).command == "root" and sheet.block(3).end == 5 and sheet.block(4) is None


@pytest.mark.parametrize("text,lines", [
    ("a\nb", [("a", "\n"), ("b", "")]),
    ("a\r\nb\r\n", [("a", "\r\n"), ("b", "\r\n")]),
    ("a\n\n", [("a", "\n"), ("", "\n")]),
])
def test_line_endings_are_kept_apart_from_the_text(text, lines):
    sheet = scan(text)
    assert [(l.text, l.eol) for l in sheet.lines] == lines
    assert "".join(l.text + l.eol for l in sheet.lines) == text


def test_tokens_stay_inside_the_expressions_and_uses_skip_parameters():
    sheet = scan('h(g) = g + k\n!plot g*x, x = 0 .. 1\n  title: g\n  xlim: 0 .. ~g')
    assert [t.text for t in sheet.line(1).tokens("name")] == ["h", "g", "g", "k"]
    assert sheet.line(1).uses({"g", "k"}) == [[11, 1]]
    assert sheet.line(3).tokens() == [] and sheet.line(4).uses({"g"}) == [[13, 2]]


@pytest.mark.parametrize("s,ok", [("x", True), ("~g", True), ("σ_max", True), ("x`!", True),
                                  ("1a", False), ("'m", False), ("a b", False), ("", False)])
def test_is_name(s, ok):
    assert is_name(s) is ok
