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
])
def test_what_is_wrong_is_said_on_the_header(text, message):
    r = rows(text)[0]
    assert r.kind == "error" and message in r.error, r.error


@pytest.mark.parametrize("line, message", [
    ("  method: hybr", "Unknown option 'method'. Under !regression: data, degree, r2"),
    ("  degree: 1.5", "degree is a whole number"),
    ("  r2: 2x", "r2 names the variable"),
    ("  data: [1, 2; 3, 4]", "data is given twice"),
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
