"""The export elements every format renders, and the one entry point that runs a sheet for a format."""
from laconic import evaluate, export
from laconic.exports import Error, Figure, Heading, Math, Paragraph, Source, elements


def kinds(els):
    return [type(e).__name__ for e in els]


def test_one_element_per_line_shown():
    els = elements(evaluate("## A\nx = 2'm\ny = nosuch\nf(t) = t\n!plot f(t), t = 0 .. 1\n  title: T").results)
    assert kinds(els) == ["Heading", "Math", "Error", "Math", "Figure"]
    assert els[0] == Heading("A") and els[2] == Error(3, "'nosuch' is not defined")
    assert isinstance(els[4], Figure) and els[4].n == 5


def test_comment_lines_run_on_unless_something_shown_comes_between():
    text = "# a\n\n# b\n!clear\n# c\nx = 1\n# d"
    assert [e.lines for e in elements(evaluate(text).results) if isinstance(e, Paragraph)] == [["a", "b", "c"], ["d"]]
    kept = elements(evaluate(text).results, commands=True)    # the .tex file keeps the command
    assert kinds(kept) == ["Paragraph", "Source", "Paragraph", "Math", "Paragraph"] and kept[1] == Source(4, "!clear")


def test_lines_hidden_by_hide_are_left_out_as_on_the_page():
    text = "# a\n!hide\n# b\nx = 2\n!plot x*t, t = 0 .. 1\nnope +\n!show\ny = x + 1"
    els = elements(evaluate(text).results)
    assert kinds(els) == ["Paragraph", "Error", "Math"] and els[0].lines == ["a"] and els[1].n == 6
    kept = elements(evaluate(text).results, commands=True)    # !hide and !show are commands like any other
    assert [e.text for e in kept if isinstance(e, Source)] == ["!hide", "!show"]
    md = export(text, "md")
    assert md.count("$$") == 2 and "y &= x + 1" in md and "<svg" not in md and "[!error] Line 6" in md


def test_a_calculation_is_its_stages_one_per_row():
    m = elements(evaluate("M = 2 * 3'm").results)[0]
    assert m.rows == ["M &= 2 \\cdot 3\\,\\mathrm{m}", "&= 6\\,\\mathrm{m}"]
    assert m.flat == ["M = 2 \\cdot 3\\,\\mathrm{m}", "= 6\\,\\mathrm{m}"] and m.inline == "M = 2 \\cdot 3\\,\\mathrm{m} = 6\\,\\mathrm{m}"
    assert elements(evaluate("3 + 4").results)[0].rows == ["&3 + 4", "&= 7"]


def test_solver_values_and_their_notes():
    els = elements(evaluate("x = 1\n!root x\n  equation: x^2 = 4\ny = x * 2").results)
    solver, y = els[1], els[2]
    assert isinstance(solver, Math) and solver.out_of_date and solver.rows == ["x &= 1"] and solver.flat == ["x = 1"]
    assert y.note == "Reads an out-of-date solver result." and not y.out_of_date


def test_each_format_gets_its_flavour():
    assert "\\qty{2}{\\meter}" in export("x = 2'm", "tex", title="t")
    assert export("x = 2'm", "md") == "$$\nx = 2\\,\\mathrm{m}\n$$\n"
    assert "data-tex=\"x = 2\\,\\mathrm{m}\"" in export("x = 2'm", "html")


def test_runs_are_shared_by_flavour():
    runs = {}
    export("x = 1", "md", runs=runs)
    live = runs[False]
    export("x = 1", "html", runs=runs)
    assert runs == {False: live}
    export("x = 1", "tex", runs=runs)
    assert set(runs) == {False, True}
