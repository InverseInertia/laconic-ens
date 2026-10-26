"""The block editor: the one writer of block-owned lines. Each case is a sheet, a header line, a
list of changes, and the sheet that should result."""
import pytest

from laconic.blockedit import BlockEditor, Edit, apply, from_json, newline, to_json
from laconic.sheettext import scan

PLOT = "!plot x, x = 0 .. 1\n"
SOLVE = "x = 1\n!root x\n  equation: x^2 = 2\n"
RESULT = '  #@ result {"hash":"a"}\n'

CASES = [
    # name, text, header, changes, expected
    ("add to an empty block", PLOT + "z = 1\n", 1, [("set", "grid", "off")],
     PLOT + "  grid: off\nz = 1\n"),
    ("add after the last option", PLOT + "  title: T\n\nz = 1", 1, [("set", "grid", "off")],
     PLOT + "  title: T\n  grid: off\n\nz = 1"),
    ("replace in place", PLOT + "  xview: 0 .. 1\n  grid: off\n", 1, [("set", "xview", "0 .. 2")],
     PLOT + "  xview: 0 .. 2\n  grid: off\n"),
    ("replace keeps that line's indent", PLOT + "  grid: off\n      xview: 0 .. 1\n", 1, [("set", "xview", "1 .. 2")],
     PLOT + "  grid: off\n      xview: 1 .. 2\n"),
    ("replace removes duplicates", PLOT + "  xview: 0 .. 1\n  grid: off\n  xview: 5 .. 6\n", 1,
     [("set", "xview", "1 .. 2")], PLOT + "  xview: 1 .. 2\n  grid: off\n"),
    ("remove", PLOT + "  xview: 0 .. 1\n  grid: off\n", 1, [("remove", "xview")], PLOT + "  grid: off\n"),
    ("remove the last option", PLOT + "  grid: off\nz = 1\n", 1, [("remove", "grid")], PLOT + "z = 1\n"),
    ("remove what is not there", PLOT + "  grid: off\n", 1, [("remove", "xview")], PLOT + "  grid: off\n"),
    ("set then remove", PLOT, 1, [("set", "grid", "off"), ("remove", "grid")], PLOT),
    ("four-space indent", PLOT + "    grid: off\n", 1, [("set", "title", "T")], PLOT + "    grid: off\n    title: T\n"),
    ("tab indent", PLOT + "\tgrid: off\n", 1, [("set", "title", "T")], PLOT + "\tgrid: off\n\ttitle: T\n"),
    ("series argument", PLOT + "  color: red\n  color 2: blue\n", 1, [("set", "color", "navy", "2")],
     PLOT + "  color: red\n  color 2: navy\n"),
    ("series argument written 02", PLOT + "  color 02: blue\n", 1, [("remove", "color", "2")], PLOT),
    ("no argument is not series 1", PLOT + "  color: red\n", 1, [("set", "color", "blue", "1")],
     PLOT + "  color: red\n  color 1: blue\n"),
    ("header on the last line, no newline", "z = 1\n!plot x, x = 0 .. 1", 2, [("set", "grid", "off")],
     "z = 1\n!plot x, x = 0 .. 1\n  grid: off"),
    ("block on the last lines, no newline", PLOT + "  grid: off", 1, [("set", "title", "T")],
     PLOT + "  grid: off\n  title: T"),
    ("removing the last line keeps no newline", PLOT + "  grid: off\n  title: T", 1, [("remove", "title")],
     PLOT + "  grid: off"),
    ("CRLF", (PLOT + "  xview: 0 .. 1\n  grid: off\nz = 1\n").replace("\n", "\r\n"), 1,
     [("set", "xview", "0 .. 2"), ("set", "title", "T")],
     (PLOT + "  xview: 0 .. 2\n  grid: off\n  title: T\nz = 1\n").replace("\n", "\r\n")),
    ("CRLF, header alone on the last line", "z = 1\r\n!plot x, x = 0 .. 1", 2, [("set", "grid", "off")],
     "z = 1\r\n!plot x, x = 0 .. 1\r\n  grid: off"),
    ("solver option goes before the result", SOLVE + RESULT, 2, [("set", "autorun", "on")],
     SOLVE + "  autorun: on\n" + RESULT),
    ("store a result", SOLVE + "z = x\n", 2, [("store", {"hash": "a"})], SOLVE + RESULT + "z = x\n"),
    ("store replaces the result", SOLVE + '  #@ result {"hash":"old"}\n', 2, [("store", {"hash": "a"})], SOLVE + RESULT),
    ("a result not last is moved last", "x = 1\n!root x\n" + RESULT + "  equation: x^2 = 2\n", 2,
     [("store", {"hash": "a"})], SOLVE + RESULT),
    ("append a block-owned line", SOLVE + RESULT, 2, [("append", "# by hand")], SOLVE + "  # by hand\n" + RESULT),
    ("a solver comment is not an option", SOLVE + "  # autorun: on\n", 2, [("remove", "autorun")], SOLVE + "  # autorun: on\n"),
]


def run(text, header, changes):
    ed = BlockEditor(text, header)
    for op, *a in changes:
        {"set": ed.set, "remove": ed.remove, "store": ed.store_result, "append": ed.append}[op](*a)
    return ed.edits()


@pytest.mark.parametrize("text, header, changes, expected", [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_block_editor(text, header, changes, expected):
    edits = run(text, header, changes)
    assert apply(text, edits) == expected
    assert len(edits) <= 1 and (edits == []) == (text == expected)
    if edits:
        # the edit stays inside the block, so the caret and the undo history elsewhere are untouched
        b = scan(text).block(header)
        start = sum(len(l.text) + len(l.eol) for l in scan(text).lines[:header - 1])
        assert start <= edits[0].start <= edits[0].end <= start + sum(len(l.text) + len(l.eol) for l in b.lines)
    endings = [l.eol for l in scan(expected).lines[:-1]]
    assert len(set(endings)) <= 1   # one line ending throughout


def test_the_edit_is_only_what_changed():
    text = PLOT + "  xview: 0 .. 1\n  grid: off\n"
    assert run(text, 1, [("set", "xview", "0 .. 2")]) == [Edit(text.index(".. 1\n  grid") + 3, text.index(".. 1\n  grid") + 4, "2")]


def test_a_line_that_is_not_a_block_is_refused():
    ed = BlockEditor("z = 1\n" + PLOT, 1)
    assert ed.kind is None and ed.edits() == []
    with pytest.raises(ValueError):
        ed.set("grid", "off")
    assert BlockEditor(PLOT, 1).kind == "plot" and BlockEditor(SOLVE, 2).kind == "solver"


def test_offsets_reach_the_page_in_utf16_units():
    text = "𝑥 = 1\n" + PLOT          # 𝑥 is two code units in JavaScript
    edits = run(text, 2, [("set", "grid", "off")])
    wire = to_json(text, edits)
    assert wire == [{"from": edits[0].start + 1, "to": edits[0].end + 1, "insert": edits[0].insert}]
    assert from_json(text, wire) == edits


def test_newline_is_the_files():
    assert newline("a\r\nb\n") == "\r\n" and newline("a\nb\r\n") == "\n" and newline("a") == "\n"
