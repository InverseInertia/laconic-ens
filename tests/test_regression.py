"""!regression: the block, the fit and its units, what it defines for the lines below, its errors,
the exports; and the collapsing of large matrices in documents (static/matrixview.js does the
pane's, against the same vectors)."""
import json
from pathlib import Path

import pytest

from laconic import evaluate
from laconic.blockedit import apply
from laconic.exports import collapse_matrices, export
from laconic.latex import snippet
from laconic.rename import rename

POINTS = """D = [0, 1, 2, 3; 1, 3, 9, 19] * 'm
!regression a, b, c
  data: D
  r2: R2
y = a + b*2'm + c*(2'm)^2
"""

FALL = """t = [0, 1, 2, 3] * 's
s = [0, 4.9, 19.6, 44.1] * 'm
!regression p, q, r
  data: t, s
"""


def rows(text):
    return evaluate(text).results


def kinds(text):
    return [(r.kind, r.error) for r in rows(text)]


def by_line(text, n):
    return rows(text)[n - 1]


# ---- the fit -------------------------------------------------------------------------------------
def test_a_quadratic_through_points_defines_its_coefficients_and_r2():
    r = rows(POINTS)
    b = r[1]
    assert b.kind == "regression" and b.end == 4 and [x.kind for x in r[2:4]] == ["solveropt", "solveropt"]
    assert b.regression.degree == 2 and b.regression.points == 4 and b.regression.r2 == pytest.approx(1.0)
    assert b.text.startswith("a = 1 m; b = 0; c = 2 1/m; R2 = 1  (degree 2, 4 points)")
    assert r[4].text == "y = 9 m"            # 1 + 0*2 + 2*4, the points' own y at x = 2
    assert "R2 = 1" in b.text


def test_each_coefficient_carries_the_units_of_y_over_x_to_its_power():
    b = by_line(FALL, 3)
    assert "q = " in b.text and "m/s" in b.text and "r = 4.9 m/s²" in b.text
    assert by_line(FALL + "g = 2*r\n", 5).text == "g = 9.8 m/s²"


def test_a_noisy_fit_reports_r2_below_one():
    b = by_line("x = [1, 2, 3, 4, 5]\ny = [2.1, 3.9, 6.2, 7.8, 10.1]\n!regression k0, k1\n  data: x, y\n  r2: fit\n"
                "fit\n", 3)
    assert 0.99 < b.regression.r2 < 1
    assert by_line("x = [1, 2, 3, 4, 5]\ny = [2.1, 3.9, 6.2, 7.8, 10.1]\n!regression k0, k1\n  data: x, y\n"
                   "  r2: fit\nfit\n", 6).text.startswith("0.99")


def test_one_name_holds_every_coefficient_as_a_vector_when_x_has_no_units():
    text = "x = [0, 1, 2, 3]\ny = [1, 3, 9, 19] * 'N\n!regression p\n  data: x, y\n  degree: 2\nidx(p, 3)\n"
    r = rows(text)
    assert r[2].kind == "regression" and r[5].text == "2 N"
    assert r"{p}_{1} + {p}_{2}" in r[2].regression.model


@pytest.mark.parametrize("x, shape", [("[0, 1, 2, 3]", "row"), ("[0; 1; 2; 3]", "column")])
def test_the_vector_of_coefficients_lies_as_the_x_values_do(x, shape):
    text = f"x = {x}\ny = [1, 3, 9, 19]\n!regression p\n  data: x, y\n  degree: 2\np\n"
    r = rows(text)
    row = r"\begin{bmatrix} 1 & 0 & 2 \end{bmatrix}"
    column = r"\begin{bmatrix} 1 \\ 0 \\ 2 \end{bmatrix}"
    assert (row if shape == "row" else column) in r[2].latex and r[5].latex.endswith(row if shape == "row" else column)
    assert r[5].text == ("[[1 0 2]]" if shape == "row" else "[[1]\n [0]\n [2]]")
    points = rows("D = [0, 1, 2, 3; 1, 3, 9, 19]\n!regression p\n  data: D\n  degree: 2\np\n")
    assert points[4].latex.endswith(row)


def test_a_column_or_row_vector_and_offset_temperatures_work():
    text = "t = [0; 60; 120] * 's\nT = [20'degC, 30'degC, 40'degC]\n!regression T0, k\n  data: t, T\nk\n"
    r = rows(text)
    assert r[2].kind == "regression", r[2].error
    assert r[4].text == "0.1667 K/s"


def test_the_polynomial_is_shown_in_the_names_the_data_came_from():
    m = by_line(FALL, 3).regression.model
    assert m.startswith("s = p + q\\,t + r\\,{t}^{2}")
    assert by_line(POINTS, 2).regression.model.startswith("y = a")


def test_the_fit_follows_its_data_and_is_out_of_date_with_it():
    text = ("u = 1\n!root u\n  equation: u = 2\nx = [0, 1, 2] * u\n!regression a, b\n  data: x, [1, 2, 3]\n"
            "z = b\n")
    r = rows(text)
    assert r[4].kind == "regression" and r[4].stale and r[6].stale


# ---- a model -------------------------------------------------------------------------------------
DECAY = """t = [0, 1, 2, 3, 4, 5] * 's
v = [10, 6.07, 3.68, 2.23, 1.35, 0.82] * 'm/'s
!regression A, k
  model: f(t) = A*exp(-k*t)
  data: t, v
  r2: R2
f(2's)
"""


def test_a_model_is_fitted_with_units_worked_out_and_defines_its_function():
    r = rows(DECAY)
    assert r[2].kind == "regression", r[2].error
    assert r[2].text.startswith("A = 10 m/s; k = 0.5") and "(model, 6 points)" in r[2].text
    assert r[2].regression.degree is None and r[2].regression.r2 > 0.9999
    assert r[2].regression.model == r"f\left(t\right) = A \cdot e^{-k \cdot t}"
    assert r[6].text == "3.679 m/s"


def test_a_model_of_several_variables_reads_a_vector_or_a_matrix_row_for_each():
    vectors = ("x = [0, 1, 2, 3, 0, 1, 2, 3] * 'm\nz = [0, 0, 0, 0, 1, 1, 1, 1] * 's\n"
               "w = [1, 3, 5, 7, 4, 6, 8, 10] * 'N\n!regression a, b, c\n  model: w(x, z) = a + b*x + c*z\n"
               "  data: x, z, w\nb\nc\n")
    r = rows(vectors)
    assert r[3].kind == "regression", r[3].error
    assert (r[6].text, r[7].text) == ("2 N/m", "3 kg⋅m/s³")   # N/s, as the sheet shows it
    matrix = ("!regression a, b, c\n  model: w(x, z) = a + b*x + c*z\n"
              "  data: [0, 1, 2, 3, 0, 1, 2, 3; 0, 0, 0, 0, 1, 1, 1, 1; 1, 3, 5, 7, 4, 6, 8, 10]\nw(10, 10)\n")
    assert rows(matrix)[3].text == "51"


def test_a_value_above_the_block_is_where_the_fit_starts_and_keeps_its_units():
    text = ("x = [0, 1, 2, 3, 4, 5, 6] * 's\ny = [0, 0.84, 0.91, 0.14, -0.76, -0.96, -0.28] * 'm\n"
            "w = 0.9'rad/'s\n!regression A, w\n  model: f(t) = A*sin(w*t)\n  data: x, y\nw\n")
    r = rows(text)
    assert r[3].kind == "regression", r[3].error
    assert r[6].text == "1 rad/s"


def test_a_model_may_call_the_sheets_functions_and_use_its_names():
    text = ("g(u) = u^2\nh = 2'm\nx = [1, 2, 3, 4] * 'm\ny = [3, 6, 11, 18] * 'm\n"
            "!regression a, c\n  model: f(x) = a*g(x)/h + c\n  data: x, y\na\nc\n")
    r = rows(text)
    assert r[4].kind == "regression", r[4].error
    assert (r[7].text, r[8].text) == ("2", "2 m")


def test_a_model_the_units_walk_cannot_read_is_fitted_point_by_point():
    text = "!regression a, c\n  model: f(x) = a*idx([1, 2], 2)*x + c\n  data: [1, 2, 3; 3, 5, 7]\na\n"
    assert rows(text)[3].text == "1"


def test_a_large_model_fit_is_quick_enough_to_run_on_every_edit():
    import time
    xs = [k / 10 for k in range(300)]
    ys = [3 * 2.718281828 ** (-0.3 * x) + 0.5 for x in xs]
    text = (f"x = [{', '.join(map(str, xs))}]\ny = [{', '.join(f'{v:.6f}' for v in ys)}]\n"
            "!regression A, k, c\n  model: f(x) = A*exp(-k*x) + c\n  data: x, y\n")
    rows(text)
    t0 = time.perf_counter()
    r = rows(text)
    assert r[2].text.startswith("A = 3; k = 0.3; c = 0.5"), r[2].text
    assert time.perf_counter() - t0 < 0.5


def test_rename_reaches_the_model_line():
    edits, _ = rename(DECAY, "k", "λ")
    assert "  model: f(t) = A*exp(-λ*t)" in apply(DECAY, edits).split("\n")


# ---- errors --------------------------------------------------------------------------------------
@pytest.mark.parametrize("text, message", [
    ("!regression\n  data: [1, 2; 3, 4]", "!regression reads"),
    ("!regression a, a\n  data: [1, 2; 3, 4]", "listed twice"),
    ("!regression a, b", "needs a `data:` line"),
    ("!regression p\n  data: [1, 2; 3, 4]", "Give the degree"),
    ("!regression a, b\n  data: [1, 2; 3, 4]\n  degree: 2", "degree 1, but `degree:` says 2"),
    ("!regression a, b, c\n  data: [1, 2; 3, 4]", "at least 3 different x values"),
    ("!regression a, b\n  data: [1, 2, 3]", "this is 1×3"),
    ("!regression a, b\n  data: [1, 2; 3, 4; 5, 6]", "this is 3×2; use transpose()"),
    ("!regression a, b\n  data: [1, 2], [1, 2, 3]", "2 x values and 3 y values"),
    ("!regression p\n  data: [1, 2, 3] * 's, [1, 2, 3]\n  degree: 1", "Name each one: `!regression p0, p1`"),
    ("!regression a, b\n  data: [1, 2; 3, 4i]", "complex"),
    ("!regression a, b\n  data: [1, 2; 3, 4]\n  r2: a", "already a coefficient"),
    ("!regression a, b\n  data: [1, 2], [1, 2], [1, 2]", "For more variables, give a `model:`"),
    ("!regression a, c\n  model: f(x) = a*x\n  data: [1, 2; 2, 4]", "c does not appear in the model"),
    ("!regression a\n  model: f(x) = a*x\n  data: [1, 2; 2, 4]\n  degree: 1", "degree: is for a polynomial"),
    ("!regression a, x\n  model: f(x) = a*x\n  data: [1, 2; 2, 4]", "'x' is a coefficient and one of"),
    ("!regression a\n  model: f(x, z) = a*x*z\n  data: [1, 2; 2, 4], [1, 2]", "2 variables, so data is a matrix with 3"),
    ("!regression a\n  model: f(x, z) = a*x*z\n  data: [1, 2; 2, 4]", "a row for x, z, then the f row"),
    ("!regression a, b\n  model: f(x) = a + b*x\n  data: [1; 2]", "2 coefficients need at least 2 points"),
    ("!regression a, b\n  model: f(x) = a*x^b\n  data: [1, 2, 3] * 'm, [1, 2, 3]", "divide the base by its unit"),
    ("!regression a\n  model: f(x) = a + x\n  data: [1, 2, 3] * 'm, [1, 2, 3] * 's", "units do not work out"),
    ("!regression a\n  model: f(x) = 1/(a - x)\n  data: [1, 2; 2, 4]", "cannot be worked out at every point"),
])
def test_what_is_wrong_is_said_on_the_header(text, message):
    r = rows(text)[0]
    assert r.kind == "error" and message in r.error, r.error


@pytest.mark.parametrize("line, message", [
    ("  method: hybr", "Unknown option 'method'. Under !regression: data, degree, model, r2"),
    ("  degree: 1.5", "degree is a whole number"),
    ("  r2: 2x", "r2 names the variable"),
    ("  data: [1, 2; 3, 4]", "data is given twice"),
    ("  model: a + b*x", "model reads `y(x) = a + b*exp(k*x)`"),
    ('  #@ result {"hash": "x"}', "stores no result"),
])
def test_a_bad_option_line_is_reported_on_that_line(line, message):
    r = rows(f"!regression a, b\n  data: [1, 2; 3, 4]\n{line}\n")
    assert r[0].kind == "error" and "1 option line below needs fixing" in r[0].error
    assert r[2].kind == "error" and message in r[2].error, r[2].error


def test_a_coefficient_is_not_defined_when_the_fit_fails():
    assert "'a' is not defined" in rows("!regression a, b\n  data: [1; 2]\na\n")[2].error


def test_a_regression_needs_no_solving():
    from laconic.solvesession import solve
    from laconic.sheet import solver_blocks
    assert solver_blocks(POINTS) == []
    assert "needs no solving" in solve(POINTS, 2, log=lambda m: None)["message"]


# ---- editing -------------------------------------------------------------------------------------
def test_rename_reaches_the_header_and_the_data_and_r2_lines():
    for old, new, line in (("D", "pts", "  data: pts"), ("a", "a0", "!regression a0, b, c"), ("R2", "fit", "  r2: fit")):
        edits, _ = rename(POINTS, old, new)
        assert line in apply(POINTS, edits).split("\n"), old
    assert "y = a0 + b" in apply(POINTS, rename(POINTS, "a", "a0")[0])


# ---- exports -------------------------------------------------------------------------------------
def test_exports_show_the_polynomial_then_each_value():
    md = export(POINTS, "md")
    assert "y &= a + b\\,x + c\\,{x}^{2}" in md and "R_{2} &= 1" in md
    tex = export(POINTS, "tex")
    assert "\\begin{align*}\ny &= a + b\\,x" in tex
    assert snippet(rows(POINTS)[1]).startswith("y = a + b")


# ---- large matrices ------------------------------------------------------------------------------
VECTORS = json.loads((Path(__file__).with_name("matrix_vectors.json")).read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda c: c["tex"][:40])
def test_documents_collapse_a_large_matrix_as_the_pane_does(case):
    assert collapse_matrices(case["tex"]) == case["collapsed"]


def test_a_document_collapses_a_large_matrix_but_a_snippet_keeps_it_whole():
    text = "M = ones(2, 40) * 'm\n"
    for fmt in ("tex", "md", "html"):
        out = export(text, fmt)
        assert "\\cdots" in out and out.count(" & ") < 20, fmt
    assert snippet(rows(text)[0]).count(" & ") == 2 * 39
