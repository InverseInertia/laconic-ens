"""`!slider` blocks (#178): the block as the sheet reads it, the variable it defines for the lines below,
where the slider stands, the errors, the text a drag writes (slider.py and /api/slideredit), and the
block in Rename and the exports."""
import pytest

from laconic import server
from laconic.blockedit import BlockEditor, apply, from_json
from laconic.exports import export
from laconic.rename import rename
from laconic.sheet import run
from laconic.sheettext import scan
from laconic.slider import Setting, number

SHEET = "!slider L = 2'm\n  range: 0'm .. 10'm\n  step: 0.5'm\nA = 3*L\n"


@pytest.fixture(autouse=True)
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("LENS_CONFIG_DIR", str(tmp_path))


def errors(rs):
    return {r.n: r.error for r in rs if r.error}


def drag(text, position, line=1):
    """The text after the slider on `line` is moved to `position`, as the page does it."""
    res = server.slider_edit(server.SliderEditBody(text=text, line=line, position=position))
    assert res["ok"], res
    return apply(text, from_json(text, res["edits"]))


# ---- reading and running the block -----------------------------------------------------------

def test_the_header_assigns_the_value_for_the_lines_below():
    rs = run(SHEET)
    assert not errors(rs)
    assert [r.kind for r in rs] == ["slider", "solveropt", "solveropt", "assign"]
    assert rs[0].text == "L = 2 m" and rs[0].latex == r"L = 2\,\mathrm{m}" and rs[0].end == 3
    assert rs[3].text == "A = 6 m"
    s = rs[0].slider
    assert (s.name, s.value, s.low, s.high, s.step, s.scale, s.unit) == ("L", 2, 0, 10, 0.5, "linear", "m")
    assert (s.ticks, s.position, s.labels) == (20, pytest.approx(0.2), ["0 m", "10 m"])


def test_the_range_is_read_in_the_units_of_the_value():
    s = run("!slider d = 250'mm\n  range: 0 .. 1'm\n")[0].slider
    assert (s.low, s.high, s.unit, s.labels) == (0, 1000, "mm", ["0 mm", "1000 mm"])
    s = run("w = 3'm\n!slider x = 1.5'm\n  range: w/3 .. 2*w\n")[1].slider   # the ends may be expressions
    assert (s.low, s.high) == (1, 6)
    s = run("!slider n = 3\n  range: 1 .. 5\n")[0].slider                  # a number without units
    assert (s.unit, s.labels, s.position) == ("", ["1", "5"], 0.5)


def test_the_scales_place_the_slider():
    log = run("!slider f = 100'Hz\n  range: 10'Hz .. 10000'Hz\n  scale: log\n")[0].slider
    assert (log.scale, log.position) == ("log", pytest.approx(1 / 3))
    cube = run("!slider t = 1\n  range: 0 .. 8\n  scale: pow 3\n")[0].slider
    assert (cube.scale, cube.power, cube.position) == ("pow", 3, pytest.approx(0.5))


def test_a_value_outside_the_range_is_kept_and_warned_about():
    rs = run(SHEET.replace("2'm", "12'm"))
    assert rs[0].kind == "slider" and rs[3].text == "A = 36 m"
    assert rs[0].slider.position == 1 and not rs[0].slider.inside
    assert rs[0].warning == "L is outside the slider's range, 0 m .. 10 m, so the slider stands at its high end"
    assert "low end" in run(SHEET.replace("2'm", "-1'm"))[0].warning


def test_a_global_and_its_warning_work_as_for_an_assignment():
    rs = run("~g = 1\n!slider g = 2\n  range: 0 .. 5\ny = ~g")
    assert rs[1].kind == "slider" and rs[1].warning.startswith("Changes the global ~g")
    assert rs[3].text == "y = 2"
    assert [(d["name"], d["global"]) for d in rs[1].symbols["defines"]] == [("g", True)]


@pytest.mark.parametrize("text,line,message", [
    ("!slider", 1, "!slider reads `!slider x = 2'm`"),
    ("!slider L", 1, "!slider reads"),
    ("!slider L = 2*w\n  range: 0 .. 1", 1, "!slider sets a number"),
    ("!slider L = 2'm", 1, "!slider needs a `range:` line"),
    ("!slider L = 2'm\n  range: 0'm", 2, "range reads `low .. high`"),
    ("!slider L = 2'm\n  range: 0's .. 10's", 2, "The range must be in the units of L (m)"),
    ("!slider L = 2'm\n  range: 10'm .. 0'm", 2, "the first end is the lower"),
    ("!slider L = 2'm\n  range: 0'm .. 10'm\n  scale: log", 2, "A log scale needs a range above zero"),
    ("!slider L = 2'm\n  range: 0'm .. 10'm\n  scale: pow 0", 3, "pow takes a number above zero"),
    ("!slider L = 2'm\n  range: 0'm .. 10'm\n  scale: cubic", 3, "scale is linear, log or pow n"),
    ("!slider L = 2'm\n  range: 0'm .. 10'm\n  step: -1'm", 3, "step is above zero"),
    ("!slider L = 2'm\n  range: 0'm .. 10'm\n  step: 1's", 3, "The step must be in the units of L"),
    ("!slider L = 2'm\n  range: 0'm .. 10'm\n  colour: red", 3, "Unknown option 'colour'. Under !slider: range, step, scale"),
    ("!slider L = 2'm\n  range: 0'm .. 10'm\n  range: 0'm .. 1'm", 3, "range is given twice"),
    ("!slider L = 2'm\n  range: 0'm .. nope", 2, "nope"),
])
def test_bad_blocks_and_options_are_errors_on_their_lines(text, line, message):
    rs = run(text + "\nA = 3*L")
    assert message in rs[line - 1].error
    if line > 1:
        assert rs[0].kind == "error" and "option line below needs fixing" in rs[0].error
    assert "L" in rs[-1].error   # nothing is defined by a slider that does not read


def test_a_comment_under_the_block_is_its_own():
    rs = run("!slider L = 2'm\n  # the span\n  range: 0'm .. 10'm\nA = L")
    assert not errors(rs) and rs[0].end == 3


# ---- what a drag writes --------------------------------------------------------------------------

def test_a_drag_writes_the_number_and_keeps_the_units():
    assert drag(SHEET, 0.5).splitlines()[0] == "!slider L = 5'm"
    assert drag(SHEET, 0.33).splitlines()[0] == "!slider L = 3.5'm"     # to the nearest step
    assert drag(SHEET, 1).splitlines()[0] == "!slider L = 10'm"
    assert drag(SHEET, 0).splitlines()[0] == "!slider L = 0'm"
    assert drag(SHEET, 5).splitlines()[0] == "!slider L = 10'm"          # a position past the end is the end
    assert drag(SHEET, 0.5).splitlines()[1:] == SHEET.splitlines()[1:]   # nothing else changes


def test_a_drag_keeps_the_line_as_typed_around_the_number():
    text = "x = 1\r\n  !slider   v_0 = -12.5e-3 'm/'s   \r\n    range: -0.02'm/'s .. 0\r\n    scale: pow 3\r\ny = v_0\r\n"
    out = drag(text, 0.5, line=2)
    assert out.split("\r\n")[1] == "  !slider   v_0 = -0.0175 'm/'s   "
    assert drag(text, 1, line=2).split("\r\n")[1] == "  !slider   v_0 = 0 'm/'s   "
    assert out.count("\r\n") == text.count("\r\n")


def test_a_continuous_slider_writes_as_many_digits_as_it_can_tell_apart():
    text = "!slider x = 0.3\n  range: 0 .. 1\n"
    assert drag(text, 0.4567).splitlines()[0] == "!slider x = 0.457"
    log = "!slider f = 100'Hz\n  range: 10'Hz .. 10000'Hz\n  scale: log\n"
    assert drag(log, 0.5).splitlines()[0] == "!slider f = 316'Hz"
    assert drag(log, 0).splitlines()[0] == "!slider f = 10'Hz"


def test_the_numbers_a_slider_writes():
    st = Setting(2, 0, 10, 0.25)
    assert [st.value_at(p) for p in (0, 0.1, 0.33, 0.999, 1)] == ["0", "1", "3.25", "10", "10"]
    odd = Setting(1, 0, 1, 0.3)   # the high end is not a whole number of steps away: the last step inside
    assert (odd.value_at(1), odd.ticks) == ("0.9", 1000)
    assert Setting(5, 1, 7, 2).value_at(0.4) == "3"    # steps count from the low end
    assert number(2.34567, 0.01) == "2.35" and number(-0.0, 0.1) == "0" and number(123456.7, 100) == "123500"
    assert number(3e-7, 1e-9) == "3e-07"
    st = Setting(1, 1, 100, scale="log")
    assert st.position(st.to_value(0.3)) == pytest.approx(0.3)
    st = Setting(1, -2, 2, scale="pow", power=2)
    assert (st.to_value(0.5), st.position(-1)) == (-1, pytest.approx(0.5))


def test_the_edit_endpoint_refuses_a_line_that_is_not_a_slider():
    res = server.slider_edit(server.SliderEditBody(text=SHEET, line=4, position=0.5))
    assert res == {"ok": False, "error": "Line 4 is not a slider that reads"}
    bad = "!slider L = 2'm\n  range: 0's .. 1's\n"
    assert not server.slider_edit(server.SliderEditBody(text=bad, line=1, position=0.5))["ok"]


def test_the_edit_endpoint_counts_offsets_as_the_page_does():
    text = "# 𝔸 wide\n" + SHEET   # a character outside the BMP is two UTF-16 units
    res = server.slider_edit(server.SliderEditBody(text=text, line=2, position=0.5))
    assert res["edits"] == [{"from": 22, "to": 23, "insert": "5"}]


def test_the_block_editor_can_rewrite_a_header():
    ed = BlockEditor(SHEET, 1)
    ed.header("!slider L = 7'm")
    ed.set("step", "1'm")
    assert apply(SHEET, ed.edits()) == "!slider L = 7'm\n  range: 0'm .. 10'm\n  step: 1'm\nA = 3*L\n"
    assert len(ed.edits()) == 1


# ---- the block elsewhere -----------------------------------------------------------------------

def test_the_sheet_reads_it_as_a_solver_block_that_needs_no_solving():
    from laconic import solvesession
    from laconic.sheet import solver_blocks
    from laconic.solver import SolverError
    b = scan(SHEET).block(1)
    assert (b.kind, b.command, b.end) == ("solver", "slider", 3)
    assert solver_blocks(SHEET) == []
    with pytest.raises(SolverError, match="nothing to solve"):
        solvesession.block(SHEET, 1)


def test_rename_reaches_the_header_and_the_options():
    text = "w = 4'm\n!slider L = 2'm\n  range: 0'm .. w\n  step: w/8\nA = 3*L\n"
    edits, n = rename(text, "L", "span")
    out = apply(text, edits)
    assert out.splitlines()[1] == "!slider span = 2'm" and out.splitlines()[4] == "A = 3*span" and n == 2
    edits, n = rename(text, "w", "width")
    assert apply(text, edits).splitlines()[2:4] == ["  range: 0'm .. width", "  step: width/8"] and n == 3
    assert drag(out, 0.5, line=2).splitlines()[1] == "!slider span = 2'm"   # 0.5 of 0 .. 4 m is 2 m


def test_the_exports_print_only_the_assignment():
    tex = export(SHEET, "tex")
    assert "L &= \\qty{2}{\\meter}" in tex and "slider" not in tex and "range" not in tex
    md = export(SHEET, "md")
    assert "L = 2\\,\\mathrm{m}" in md and "slider" not in md and "range" not in md
    html = export(SHEET, "html")
    assert 'data-tex="L = 2\\,\\mathrm{m}"' in html and "<input" not in html and "range:" not in html


def test_the_vocabulary_offers_its_options_and_scales():
    v = server.vocab()["blocks"]["slider"]
    assert [k for k, _ in v["keys"]] == ["range", "step", "scale"]
    assert [c for c, _ in v["choices"]["scale"]] == ["linear", "log", "pow"]
    assert set(v["math"]) == {"range", "step"} and v["args"] == {}
    assert "slider" in [c for c, _ in server.vocab()["commands"]]
