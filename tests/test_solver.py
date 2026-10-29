"""!root, !minimize and !maximize: parsing, the input hash and the valid/out-of-date status, the
numerics (scipy), the stored result line, and the out-of-date marking of everything downstream."""
import json
import re

import pytest

pytest.importorskip("scipy")

from laconic import document, evaluate, snippet
from laconic import solver
from laconic.blockedit import apply
from laconic.rename import rename
from laconic import solvesession


def renamed(text, old, new, confirm=False):
    """`rename`'s edits, made."""
    edits, n = rename(text, old, new, confirm)
    return apply(text, edits), n

ROOT = """x = 1'm
y = 1'm
!root x, y
  equation: x^2 + y^2 = 4'm^2
  equation: x = y
z = x * 2
"""


def rows(text):
    return evaluate(text).results


def block(text, kind="solver"):
    return next(r for r in rows(text) if r.kind == kind)


def solved(text, line=None, **kw):
    """The text with the first block solved and its result written in."""
    line = line or next(r.n for r in rows(text) if r.kind in ("solver", "error") and r.source.lstrip().startswith("!"))
    out = solvesession.solve(text, line, log=lambda m: None, **kw)
    assert out["ok"], out["message"]
    return written(text, solver.write_result, line, out["record"])


def written(text, writer, *a):
    """The text with a writer's edits made."""
    return apply(text, writer(text, *a))


def stored_line(text):
    return next(l for l in text.split("\n") if l.lstrip().startswith("#@ result"))


# ---- status ------------------------------------------------------------------------------------
def test_an_unsolved_block_shows_its_starting_values_and_is_out_of_date_downstream():
    r = rows(ROOT)
    b = next(x for x in r if x.kind == "solver")
    assert b.solver.status == "none" and b.stale
    assert [v["name"] for v in b.solver.values] == ["x", "y"]
    assert "1 m" in b.text
    z = next(x for x in r if x.kind == "assign" and x.lhs == "z")
    assert z.stale and "2 m" in z.text          # computed from the starting value, and flagged


def test_solving_stores_a_result_that_makes_the_block_and_everything_below_current():
    text = solved(ROOT)
    r = rows(text)
    b = next(x for x in r if x.kind == "solver")
    assert b.solver.status == "valid" and not b.stale
    assert "1.414 m" in b.text
    z = next(x for x in r if x.kind == "assign" and x.lhs == "z")
    assert not z.stale and "2.828 m" in z.text
    assert not any(x.kind == "error" for x in r)


def test_the_result_is_one_indented_meta_line_at_the_end_of_the_block():
    text = solved(ROOT).split("\n")
    i = next(k for k, l in enumerate(text) if l.startswith("!root"))
    assert text[i + 3].startswith("  #@ result {") and text[i + 4] == "z = x * 2"
    rec = json.loads(text[i + 3].split("result ", 1)[1])
    assert rec["kind"] == "root" and len(rec["hash"]) == 12 and rec["method"] == "hybr"
    assert rec["values"][0]["unit"] == "meter" and rec["values"][0]["mag"] == pytest.approx(2 ** 0.5)


def test_writing_a_result_twice_replaces_it():
    text = solved(solved(ROOT))
    assert text.count("#@ result") == 1


@pytest.mark.parametrize("edit", [
    lambda t: t.replace("4'm^2", "5'm^2"),                 # an equation
    lambda t: t.replace("y = 1'm", "y = 1.5'm"),           # a starting value
    lambda t: t.replace("  equation: x = y\n", "  equation: x = y\n  method: lm\n"),
    lambda t: t.replace("x = 1'm", "x = 1'm\nk = 2"),       # unrelated: must NOT go stale (checked below)
])
def test_changing_what_the_solver_reads_makes_the_result_out_of_date(edit):
    text = solved(ROOT)
    status = block(edit(text)).solver.status
    assert status == ("valid" if "k = 2" in edit(text) else "stale")


def test_things_that_do_not_change_the_answer_do_not_make_it_stale():
    text = solved(ROOT)
    for edit in (lambda t: t.replace("equation: x = y", "equation:   x   =   y"),     # whitespace
                 lambda t: t + "\nw = 3\n",                                              # a line elsewhere
                 lambda t: t.replace("!root x, y\n", "!root x, y\n  # note to self\n"),  # a comment
                 lambda t: t.replace("!root x, y\n", "!root x, y\n  timeout: 20\n"),     # how it is supervised
                 lambda t: t.replace("!root x, y\n", "!root x, y\n  autorun: on\n")):
        assert block(edit(text)).solver.status == "valid"


def test_the_hash_follows_variables_and_functions_the_block_reaches():
    text = """a = 4'm^2
f(t) = t^2
x = 1'm
!root x
  equation: f(x) = a
"""
    done = solved(text)
    assert block(done).solver.status == "valid"
    assert block(done.replace("a = 4'm^2", "a = 9'm^2")).solver.status == "stale"      # a variable
    assert block(done.replace("f(t) = t^2", "f(t) = 2 * t^2")).solver.status == "stale"    # a function body
    other = done.replace("f(t) = t^2", "g(t) = 7\nf(t) = t^2")
    assert block(other).solver.status == "valid"


def test_a_second_block_that_reads_the_first_goes_out_of_date_with_it():
    text = """x = 1'm
!root x
  equation: x = 2'm
y = 1'm
!root y
  equation: y = 3 * x
"""
    one = solved(text, 2)
    both = solved(one, next(r.n for r in rows(one) if r.kind == "solver" and r.solver.unknowns == ["y"]))
    assert [r.solver.status for r in rows(both) if r.kind == "solver"] == ["valid", "valid"]
    changed = both.replace("x = 2'm", "x = 5'm")
    st = [(r.solver.status, r.solver.tainted) for r in rows(changed) if r.kind == "solver"]
    assert st == [("stale", False), ("valid", True)]         # the second still holds its answer, but it reads a stale x


def test_outdated_values_reach_plots_and_functions_called_later():
    text = ROOT + "f(t) = t * x\nu = f(2)\n!plot f(t), t = 0 .. 1\n"
    r = rows(text)
    assert next(x for x in r if x.kind == "assign" and x.lhs == "u").stale    # through the function body
    assert next(x for x in r if x.kind == "plot").stale
    done = rows(solved(text))
    assert not any(x.stale for x in done)


def test_assigning_a_fresh_value_clears_the_out_of_date_mark():
    text = ROOT + "x = 7'm\nq = x + 1'm\n"
    r = rows(text)
    assert next(x for x in r if x.kind == "assign" and x.lhs == "q").stale is False


def test_a_stored_result_that_no_longer_fits_is_ignored():
    text = solved(ROOT)
    wrong = re.sub(r'"unit":"meter"', '"unit":"second"', text)
    assert block(wrong).solver.status == "none"
    junk = re.sub(r"#@ result .*", "#@ result {not json", text)
    b = block(junk.replace("{not json", "{not json}"))
    assert b.solver.status == "none" and "could not be read" in b.solver.note


# ---- problems the block reports before anything runs -----------------------------------------------
def err(text):
    """Every error the sheet shows, joined (a bad option line also puts a note on the header)."""
    return " | ".join(r.error for r in rows(text) if r.kind == "error")


def test_block_level_problems_are_reported_on_the_header():
    assert "starting value" in err("!root x\n  equation: x = 1")
    assert "needs at least one" in err("x = 1\n!root x\n")
    assert "needs an `objective:`" in err("x = 1\n!minimize x\n  bounds: 0 .. 1\n")
    assert "reads `!root x, y`" in err("!root\n  equation: 1 = 1")
    assert "listed twice" in err("x = 1\n!root x, x\n  equation: x = 1\n  equation: x = 2")
    assert "2 equations for 1 unknown" in err("x = 1\n!root x\n  equation: x = 1\n  equation: x = 2")
    assert "Incompatible units" in err("x = 1'm\n!root x\n  equation: x = 2")
    assert "not defined" in err("x = 1\n!root x\n  equation: x = q")


def test_a_bad_option_line_is_reported_on_its_own_line():
    r = rows("x = 1\n!root x\n  equation: x = 1\n  colour: red\n  tol: soon\n")
    bad = {x.n: x.error for x in r if x.kind == "error" and x.n > 2}
    assert "Unknown option 'colour'" in bad[4] and "tol needs a number" in bad[5]
    assert next(x for x in r if x.n == 2).error == "2 option lines below need fixing"


def test_method_must_suit_the_problem():
    base = "x = 1\n!minimize x\n  objective: x^2\n"
    assert "does not take bounds" in err(base + "  bounds: 0 .. 1\n  method: BFGS\n")
    assert "does not take constraints" in err(base + "  constraint: x >= 0\n  method: Powell\n")
    assert "only <= and >=" in err(base + "  constraint: x = 0\n  method: COBYLA\n")
    assert "brentq needs" in err("x = 1\n!root x\n  equation: x = 0\n  method: brentq\n")


def test_constraints_need_a_relation_and_equations_cannot_be_inequalities():
    assert "needs <=, >= or =" in err("x = 1\n!minimize x\n  objective: x^2\n  constraint: x\n")
    assert "inequalities belong" in err("x = 1\n!root x\n  equation: x <= 1\n")
    assert "Only one of" in err("x = 1\n!root x\n  equation: x = 1 = 2\n")


# ---- the numerics ----------------------------------------------------------------------------------
def test_root_in_two_unknowns_keeps_the_units_of_the_start():
    out = solvesession.solve(ROOT, 3, log=lambda m: None)
    assert out["ok"]
    assert [v["unit"] for v in out["record"]["values"]] == ["meter", "meter"]
    assert out["record"]["resid"] < 1e-9


def test_a_bracketed_scalar_root_uses_brentq():
    out = solvesession.solve("x = 1\n!root x\n  equation: cos(x) = x\n  bounds: 0 .. 1\n", 2, log=lambda m: None)
    assert out["record"]["method"] == "brentq"
    assert out["record"]["values"][0]["mag"] == pytest.approx(0.7390851332, abs=1e-9)


def test_a_bracket_without_a_sign_change_says_so():
    out = solvesession.solve("x = 1\n!root x\n  equation: x^2 = -1\n  bounds: 0 .. 1\n", 2, log=lambda m: None)
    assert not out["ok"] and "same sign at both ends" in out["message"]


def test_a_matrix_unknown_is_solved_entry_by_entry():
    text = "v = [1; 1]\n!root v\n  equation: [2, 0; 0, 4] * v = [6; 8]\n"
    out = solvesession.solve(text, 2, log=lambda m: None)
    assert out["ok"] and sum(out["record"]["values"][0]["mag"], []) == pytest.approx([3.0, 2.0])
    assert block(written(text, solver.write_result, 2, out["record"])).solver.status == "valid"


def test_least_squares_with_lm_takes_extra_equations():
    text = "x = 1\n!root x\n  method: lm\n  equation: x = 1\n  equation: x = 3\n"
    out = solvesession.solve(text, 2, log=lambda m: None)
    assert out["record"]["values"][0]["mag"] == pytest.approx(2.0, abs=1e-6)


def test_minimize_with_bounds_stops_at_the_bound():
    text = "d = 1'm\n!minimize d\n  objective: (d - 2'm)^2 / 'm^2 + 3\n  bounds d: 0'm .. 1.5'm\n"
    out = solvesession.solve(text, 2, log=lambda m: None)
    assert out["record"]["values"][0]["mag"] == pytest.approx(1.5, abs=1e-6)
    assert out["record"]["obj"]["mag"] == pytest.approx(3.25)
    assert block(written(text, solver.write_result, 2, out["record"])).text.endswith("minimum = 3.25")


def test_maximize_reports_the_maximum():
    text = "d = 1'm\n!maximize d\n  objective: 5 - (d - 2'm)^2 / 'm^2\n"
    out = solvesession.solve(text, 2, log=lambda m: None)
    assert out["record"]["values"][0]["mag"] == pytest.approx(2.0, abs=1e-5)
    assert out["record"]["obj"]["mag"] == pytest.approx(5.0)


def test_constraints_change_the_answer():
    text = ("x = 1\ny = 1\n!minimize x, y\n  objective: x^2 + y^2\n  constraint: x + y = 2\n"
            "  constraint: x >= 1.5\n")
    out = solvesession.solve(text, 3, log=lambda m: None)
    assert out["record"]["method"] == "SLSQP"
    assert out["record"]["values"][0]["mag"] == pytest.approx(1.5, abs=1e-5)
    assert out["record"]["values"][1]["mag"] == pytest.approx(0.5, abs=1e-5)


def test_a_run_that_does_not_converge_stores_nothing():
    text = "x = 1\n!root x\n  equation: x^2 = -1\n  maxiter: 5\n"
    out = solvesession.solve(text, 2, log=lambda m: None)
    assert out["ok"] is False and out["record"] is None and out["message"]


def test_leaving_the_domain_is_explained():
    text = "x = 1\n!minimize x\n  objective: ln(x)\n  method: Nelder-Mead\n"
    out = solvesession.solve(text, 2, log=lambda m: None)
    assert not out["ok"] and "not finite" in out["message"] and "x =" in out["message"]


def test_the_objective_must_be_a_single_number():
    assert "single number" in err("v = [1; 2]\n!minimize v\n  objective: v\n")


def test_the_log_says_what_happened():
    lines = []
    solvesession.solve(ROOT, 3, log=lines.append)
    assert lines[0].startswith("!root x, y") and any(l.startswith("converged") for l in lines)
    assert any("result: x = 1.41421 m" in l for l in lines)


def test_solving_leaves_the_sheet_untouched():
    out = solvesession.solve(ROOT, 3, log=lambda m: None)
    assert out["hash"] == block(ROOT).solver.hash    # what a run computes is what the sheet checks


def test_verify_compares_with_the_stored_result():
    text = solved(ROOT)
    out = solvesession.solve(text, 3, log=lambda m: None, mode="verify")
    assert out["verify"]["same"] is True and out["verify"]["diff"] < 1e-9
    tampered = re.sub(r'"mag":1\.41421356\d*', '"mag":1.5', text, count=1)
    assert block(tampered).solver.status == "valid"          # the hash covers inputs, not the answer
    out = solvesession.solve(tampered, 3, log=lambda m: None, mode="verify")
    assert out["verify"]["same"] is False and out["verify"]["diff"] > 1e-3
    out = solvesession.solve(ROOT, 3, log=lambda m: None, mode="verify")
    assert out["verify"]["same"] is None and "no current stored result" in out["verify"]["note"]


# ---- the text ------------------------------------------------------------------------------------
def test_autorun_is_a_line_in_the_block_and_turning_it_on_keeps_the_result():
    text = solved(ROOT)
    on = written(text, solver.set_option, 3, "autorun", "on")
    assert block(on).solver.autorun is True and block(on).solver.status == "valid"
    assert written(on, solver.set_option, 3, "autorun", None) == text


def test_a_result_stored_in_a_crlf_file_reads_back():
    crlf = ROOT.replace("\n", "\r\n")
    done = written(crlf, solver.write_result, 3, solvesession.solve(crlf, 3, log=lambda m: None)["record"])
    assert block(done).solver.status == "valid"


def test_writing_to_a_line_that_is_not_a_block_is_refused():
    with pytest.raises(solver.SolverError):
        solver.write_result(ROOT, 1, {"hash": "x"})


def test_rename_follows_a_variable_into_blocks_and_leaves_the_stored_result_alone():
    text = solved(ROOT)
    out, count = renamed(text, "x", "a")
    assert "!root a, y" in out and "equation: a^2 + y^2" in out and "equation: a = y" in out and "z = a * 2" in out
    assert stored_line(out) == stored_line(text)
    assert block(out).solver.status == "stale"      # the text changed, so it is checked again


# ---- the other outputs --------------------------------------------------------------------------------
def test_latex_snippets_and_export_carry_the_values_and_a_note_when_out_of_date():
    text = solved(ROOT)
    r = block(text)
    assert r"x &= 1.414" in snippet(r, "align") and r"\begin{align*}" in snippet(r, "align")
    assert snippet(r, "inline").count("1.414") == 2 and "%" not in snippet(r, "inline")
    stale = block(text.replace("4'm^2", "5'm^2"))
    assert snippet(stale, "inline").startswith(f"% line {stale.n}: solver result is out of date")
    tex = document(evaluate(text, siunitx=True).results)
    assert "1.414" in tex and "#@" not in tex and "equation:" not in tex


def test_the_cli_solves_what_is_out_of_date_and_writes_the_file(tmp_path, capsys):
    from laconic.__main__ import _solve_all
    path = tmp_path / "s.lens"
    path.write_text(ROOT, encoding="utf-8")
    text = _solve_all(path, ROOT, [])
    assert path.read_text(encoding="utf-8") == text
    assert block(text).solver.status == "valid"
    assert _solve_all(path, text, []) == text           # nothing left to do, nothing rewritten


TWINS = """x = 1'm
!root x
  equation: x^2 = 4'm^2
a = x
x = 1'm
!root x
  equation: x^2 = 4'm^2
b = x
"""


def test_the_cli_stores_a_result_in_every_block_with_the_same_inputs(tmp_path, monkeypatch, capsys):
    # Two blocks that hash the same get one answer, as the page's store gives them.
    from laconic.__main__ import main
    path = tmp_path / "twins.lens"
    path.write_text(TWINS, encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["lens", str(path), "--solve"])
    main()
    out = capsys.readouterr().out
    assert "NOT SOLVED" not in out and out.count("(solved)") == 2
    assert [r.solver.status for r in rows(path.read_text(encoding="utf-8")) if r.solver] == ["valid", "valid"]


# ---- heavier cases (found by stress testing) ---------------------------------------------------------
def test_a_flat_multiple_root_still_closes_its_bracket():
    out = solvesession.solve("x = 1\n!root x\n  equation: x^3 = 0\n  bounds: -1 .. 2\n", 2, log=lambda m: None)
    assert out["ok"] and abs(out["record"]["values"][0]["mag"]) < 1e-6
    out = solvesession.solve("x = 1\n!root x\n  equation: x^3 = 0\n  bounds: -1 .. 2\n  maxiter: 5\n", 2, log=lambda m: None)
    assert not out["ok"] and "did not close within 5 steps" in out["message"]


def rosenbrock(n, method):
    return (f"S1 = hstack(identity({n - 1}), zeros({n - 1}, 1))\nS2 = hstack(zeros({n - 1}, 1), identity({n - 1}))\n"
            f"x = -1.2 * ones({n}, 1)\n!minimize x\n  objective: sum(100 * (S2 * x - (S1 * x) .* (S1 * x))"
            f" .* (S2 * x - (S1 * x) .* (S1 * x)) + (1 - S1 * x) .* (1 - S1 * x))\n  method: {method}\n")


def test_tnc_gets_an_evaluation_budget_that_fits_finite_differences():
    # scipy's own TNC default (10 n evaluations) stops a 20-variable problem after a few gradients.
    out = solvesession.solve(rosenbrock(20, "TNC"), 4, log=lambda m: None)
    assert out["ok"], out["message"]
    assert max(abs(v - 1) for v in sum(out["record"]["values"][0]["mag"], [])) < 1e-3


def test_a_large_matrix_input_hashes_quickly_and_ignores_last_bit_noise():
    import time
    from laconic.evaluator import registry
    Q = registry().Quantity
    assert solver._qdigest(Q(0.1 + 0.2, "m")) == solver._qdigest(Q(0.3, "m"))
    assert solver._qdigest(Q(0.3, "m")) != solver._qdigest(Q(0.3000001, "m"))
    assert solver._qdigest(Q(0.3, "m")) != solver._qdigest(Q(0.3, "s"))
    import numpy as np
    big = Q(np.random.default_rng(1).normal(size=(1000, 1000)), "N")
    t0 = time.monotonic()
    solver._qdigest(big)
    assert time.monotonic() - t0 < 0.5


def test_hide_hides_a_solver_block_only_while_its_result_is_current():
    """A block under !hide that is out of date or never run stays in sight, so it can be run."""
    text = "!hide\ny = 1\n!root y\n  equation: y^2 = 4\nz = y\n"
    assert [r.hidden for r in rows(text)] == [False, True, False, True, True]
    done = rows(solved(text))
    assert done[2].solver.current and done[2].hidden and done[5].hidden
