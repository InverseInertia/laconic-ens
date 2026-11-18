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
    paras = [e.lines for e in elements(evaluate(text).results) if isinstance(e, Paragraph)]
    assert paras == [[[("text", "a")], [("text", "b")], [("text", "c")]], [[("text", "d")]]]
    kept = elements(evaluate(text).results, commands=True)    # the .tex file keeps the command
    assert kinds(kept) == ["Paragraph", "Source", "Paragraph", "Math", "Paragraph"] and kept[1] == Source(4, "!clear")


def test_lines_hidden_by_hide_are_left_out_as_on_the_page():
    text = "# a\n!hide\n# b\nx = 2\n!plot x*t, t = 0 .. 1\nnope +\n!show\ny = x + 1"
    els = elements(evaluate(text).results)
    assert kinds(els) == ["Paragraph", "Error", "Math"] and els[0].lines == [[("text", "a")]] and els[1].n == 6
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
    assert isinstance(solver, Math) and solver.out_of_date
    assert solver.rows == ["x^{2} &= 4", "x &= 1"] and solver.flat == ["x^{2} = 4", "x = 1"]
    assert y.note == "Reads an out-of-date solver result." and not y.out_of_date


def test_a_solver_block_shows_what_it_solves_above_its_values():
    """#182: the equations, or the objective with its constraints and bounds, then the values."""
    text = ("d = 1\n!minimize d\n  objective: (d - 2)^2\n  constraint: d >= 0.5\n  bounds d: 0 .. 3\n"
            "  method: SLSQP\n  #@ result {\"hash\": \"0\"}")
    m = elements(evaluate(text).results)[1]
    assert m.rows[:3] == ["\\text{minimize}\\quad & \\left(d - 2\\right)^{2}", "d &\\ge 0.5", "0 \\le d &\\le 3"]
    assert m.rows[3].startswith("d &= ")
    assert m.inline.startswith("\\text{minimize}\\quad  \\left(d - 2\\right)^{2},\\; d \\ge 0.5")
    assert "\\Rightarrow" in m.inline
    root = elements(evaluate("x = 1\ny = 1\n!root x, y\n  equation: x + y = 3\n  equation: x - y").results)[2]
    assert root.rows[:2] == ["x + y &= 3", "x - y &= 0"]
    assert "x + 1 &= 3" in export("x = 1\n!root x\n  equation: x + 1 = 3", "md")


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


INLINE = "~g = 9.81'm/'s^2\nm = 2'kg\n## Weight `W = m*g`\n# so `F = m*g/2 + 5'kN`, `!plot` is code and one ` stays\n"


def test_inline_math_in_a_comment_is_typeset_as_written_and_not_worked_out():
    els = elements(evaluate(INLINE).results)
    heading, para = els[2], els[3]
    assert heading == Heading("Weight `W = m*g`", [("text", "Weight "), ("math", r"W = m \cdot \htmlData{global=g}{g}")])
    assert para.lines == [[("text", "so "), ("math", r"F = \frac{m \cdot \htmlData{global=g}{g}}{2} + 5\,\mathrm{kN}"),
                           ("text", ", "), ("code", "!plot"), ("text", " is code and one ` stays")]]


def test_inline_math_reads_names_but_defines_nothing_and_warns_of_nothing():
    rs = evaluate("# `x = 3`, `f(t) = t^2`, `sqrt(nosuch)` and `'kN`\ny = x").results
    assert [k for k, _ in rs[0].parts] == ["math", "text", "math", "text", "math", "text", "math"]
    assert rs[0].parts[2] == ("math", r"f\left(t\right) = t^{2}") and rs[0].parts[4] == ("math", r"\sqrt{\mathrm{nosuch}}")
    assert not rs[0].warning and rs[1].kind == "error"    # the comment's x = 3 defined nothing
    assert evaluate("# plain `` and one ` here").results[0].parts is None   # no inline math: plain text


def test_inline_math_in_each_format():
    tex = export(INLINE, "tex")
    assert r"\subsection*{Weight $W = m \cdot g$}" in tex
    assert (r"so $F = \frac{m \cdot g}{2} + \qty{5}{\kilo\newton}$, \texttt{!plot} is code and one "
            r"\textasciigrave{} stays\par") in tex
    md = export(INLINE, "md")
    assert "## Weight $W = m \\cdot g$" in md
    assert "so $F = \\frac{m \\cdot g}{2} + 5\\,\\mathrm{kN}$, `!plot` is code and one \\` stays" in md
    html = export(INLINE, "html")
    assert '<h2>Weight <span class="imath" data-tex="W = m \\cdot g"></span></h2>' in html
    assert '<code>!plot</code> is code and one ` stays</p>' in html and 'querySelectorAll(".imath")' in html
