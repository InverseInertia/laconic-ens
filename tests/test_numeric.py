"""The solver's fast path (laconic/numeric.py): expressions compiled to plain numbers in SI base units
give what the usual evaluation gives, and anything they cannot do is refused, not guessed."""
import numpy as np
import pytest

from laconic import numeric, solvesession
from laconic.parser import parse_expr
from laconic.sheet import evaluator_at

SHEET = """M = [10, 20, 30; 40, 50, 60]
A = [1, 2; 3, 4]
q = [0.5; 1.5; 2.5] * 'gal / 'min
k = [2; 1; 2]
p = 3 'psi
rho = 998 'kg / 'm^3
f(x, n) = (pick(M, n, 1) + x / ('gal / 'min) * pick(M, n, 3)) * 'Pa + rho * (x / (1 'in)^2)^2
g(x) = max([x / ('gal / 'min), 1]) * 'psi
h(x) = sqrt(abs(x) * 1 'gal / 'min) + clip(x, 1 'gal / 'min, 2 'gal / 'min) * heaviside(x - 1 'gal / 'min)
"""
CASES = [".f(q, k)", ".g(q)", ".h(q)", "transpose(A) * [1; 2] * p", "A^2 * p", "sum(q) * 2 + q",
         "-p / rho -> 'm^2 / 's^2", "[p, 2 * p; 3 'kPa, p] * 2", "where(k - 1.5, q, 2 * q)", "exp(-sum(k) / 5) * p"]


@pytest.fixture(scope="module")
def ev():
    return evaluator_at(SHEET, len(SHEET.split("\n")))


@pytest.mark.parametrize("expr", CASES)
def test_compiled_expressions_give_what_the_evaluator_gives(ev, expr):
    node = parse_expr(expr)
    want = np.asarray(ev.eval(node).to_base_units().magnitude, dtype=float)
    got = numeric.compile(node, ev, [])({})
    assert np.allclose(got, want, rtol=1e-12, atol=0)


def test_an_unknown_comes_in_as_its_si_magnitude(ev):
    fn = numeric.compile(parse_expr("2 * q + 1 'gal / 'min"), ev, [ev.vkey("q")])
    q_si = np.array([[1.0], [2.0]]) * 6.30901964e-5
    assert np.allclose(fn({ev.vkey("q"): q_si}), 2 * q_si + 6.30901964e-5)


@pytest.mark.parametrize("expr", ['props("D", "T", 300 ' + "'K" + ', "P", 1 ' + "'atm" + ', "Water")', "20 'degC + p / p * 1 'delta_degC", "2i * p"])
def test_what_it_cannot_do_is_refused(ev, expr):
    with pytest.raises(numeric.Unsupported):
        numeric.compile(parse_expr(expr), ev, [])


def test_a_solve_on_the_fast_path_finds_what_the_usual_one_finds():
    """The pipe network sheet: its stored answer is found again, and its log is the same evaluation by evaluation."""
    from pathlib import Path
    import json
    import re
    text = (Path(__file__).parent.parent / "plugins/pipenet/pipenet.lens").read_text(encoding="utf-8")
    stored = json.loads(re.search(r"\n  #@ result ([^\n]*)", text).group(1))
    text = re.sub(r"\n  #@ result [^\n]*", "", text)
    line = next(i for i, l in enumerate(text.split("\n"), 1) if l.startswith("!root"))
    rec = solvesession.solve(text, line, log=lambda *a: None)
    a = np.array(stored["values"][0]["mag"], dtype=float).ravel()
    b = np.array(rec["record"]["values"][0]["mag"], dtype=float).ravel()
    assert rec["ok"] and np.allclose(a, b, rtol=1e-10)


def test_a_solve_with_offset_units_keeps_to_the_usual_evaluation():
    text = "T = 20 'degC\n!root T\n  equation: T - 30 'degC\n"
    rec = solvesession.solve(text, 2, log=lambda *a: None)
    assert rec["ok"] and abs(rec["record"]["values"][0]["mag"] - 30) < 1e-9
