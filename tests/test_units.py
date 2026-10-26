import re

from laconic import document, evaluate, run, snippet
from laconic.evaluator import check_units

SMOOT = [("smoot", "1.7018'm")]


def kinds(text, **kw):
    return [(r.kind, r.error) for r in run(text, **kw) if r.kind not in ("blank", "comment")]


def last(text, **kw):
    return [r for r in run(text, **kw) if r.kind != "blank"][-1]


# ---- inline definitions ------------------------------------------------------------
def test_define_and_use_a_unit():
    r = last("'smoot = 1.7018'm\nd = 3'smoot -> 'm")
    assert r.kind == "assign" and r.text.startswith("d = 5.105")


def test_definition_line_shows_what_it_means():
    r = run("'smoot = 1.7018'm")[0]
    assert r.kind == "unitdef" and "1.702" in r.latex and r"\mathrm{smoot}" in r.latex


def test_units_apply_to_the_whole_sheet_wherever_defined():
    res = run("d = 3'smoot -> 'm\n'smoot = 1.7018'm")
    assert res[0].kind == "assign" and res[1].kind == "unitdef"


def test_definitions_can_build_on_each_other():
    r = last("'smoot = 1.7018'm\n'bigsmoot = 10'smoot\nx = 1'bigsmoot -> 'm")
    assert r.text.startswith("x = 17.02")


def test_dimensionless_unit():
    assert last("'dozen = 12\nn = 2'dozen -> 'dozen").kind == "assign"


def test_units_do_not_leak_between_runs():
    run("'smoot = 1.7018'm")
    r = last("d = 3'smoot")
    assert r.kind == "error" and "Unknown unit 'smoot'" in r.error


def test_unit_definition_errors():
    assert "already a unit" in last("'m = 2'ft").error
    assert "already a unit (millimeter)" in last("'mm = 2'ft").error
    assert "already a unit (decismoot)" in last("'smoot = 1.7018'm\n'dsmoot = 2'm").error
    assert "numbers and units" in last("x = 2\n'zork = x * 'm").error
    assert "Offset" in last("'zork = 5'degC").error
    assert "positive" in last("'zork = 0'm").error
    assert "single value" in last("'zork = [1, 2] * 'm").error
    assert "ASCII" in last("'µx = 2'm").error
    assert "Unknown unit" in last("'zork = 2'nosuch").error
    assert "already defined on line 1" in last("'zork = 2'm\n'zork = 3'm").error


def test_a_failed_definition_does_not_stop_the_sheet():
    assert kinds("'m = 2'ft\nx = 1") == [("error", "'m' is already a unit (meter)"), ("assign", "")]


def test_a_line_that_merely_starts_with_a_unit_is_still_an_expression():
    assert last("'kN * 2").kind == "expr"


# ---- instance-wide units -------------------------------------------------------------
def test_global_units_are_available_everywhere():
    r = last("d = 3'smoot -> 'm", global_units=SMOOT)
    assert r.kind == "assign" and r.text.startswith("d = 5.105")


def test_global_units_may_build_on_earlier_ones():
    g = SMOOT + [("bigsmoot", "10'smoot")]
    assert last("x = 1'bigsmoot -> 'm", global_units=g).text.startswith("x = 17.02")


def test_same_definition_as_a_global_is_accepted_and_a_different_one_is_not():
    assert last("'smoot = 1.7018'm\nx = 1'smoot", global_units=SMOOT).kind == "assign"
    assert last("'smoot = 170.18'cm\nx = 1'smoot", global_units=SMOOT).kind == "assign"  # same size, written differently
    r = run("'smoot = 2'm", global_units=SMOOT)[0]
    assert r.kind == "error" and "differs from this instance's own definition" in r.error


def test_a_broken_global_is_skipped_rather_than_breaking_every_sheet():
    r = last("x = 3'm", global_units=[("m", "2'ft"), ("smoot", "1.7018'm")])
    assert r.kind == "assign"


def test_check_units_reports_per_row():
    errs = check_units([("smoot", "1.7018'm"), ("shaku", "0.3'smoot"), ("m", "1'ft"), ("x", "y")])
    assert errs[0] is None and errs[1] is None and "already a unit" in errs[2] and errs[3]


# ---- carrying definitions along ------------------------------------------------------
def test_save_appends_only_the_global_units_the_sheet_uses():
    g = SMOOT + [("zap", "3'm")]
    ws = evaluate("x = 3'smoot", global_units=g)
    assert ws.needed == SMOOT
    text = ws.portable_text()
    assert text.startswith("x = 3'smoot\n") and "'smoot = 1.7018'm" in text and "zap" not in text
    assert text.rstrip().endswith("#@ end of unit definitions")


def test_units_used_by_a_global_definition_come_along():
    g = SMOOT + [("bigsmoot", "10'smoot")]
    ws = evaluate("x = 1'bigsmoot", global_units=g)
    assert [n for n, _ in ws.needed] == ["smoot", "bigsmoot"]


def test_nothing_is_appended_when_it_is_not_needed_or_already_in_the_text():
    assert evaluate("x = 3'm", global_units=SMOOT).portable_text() == "x = 3'm"
    t = "'smoot = 1.7018'm\nx = 3'smoot"
    assert evaluate(t, global_units=SMOOT).portable_text() == t


def test_a_saved_copy_works_on_an_instance_without_the_unit_and_on_one_with_it():
    saved = evaluate("x = 3'smoot -> 'm", global_units=SMOOT).portable_text()
    for units in (None, SMOOT):
        res = run(saved, global_units=units)
        assert [r.kind for r in res if r.kind == "error"] == []
        assert [r for r in res if r.kind == "assign"][0].text.startswith("x = 5.105")
    # opening and saving again does not stack up definitions
    assert evaluate(saved, global_units=SMOOT).portable_text() == saved


def test_the_marker_lines_are_not_shown_as_comments():
    res = run(evaluate("x = 3'smoot", global_units=SMOOT).portable_text())
    assert [r.kind for r in res if r.kind == "meta"] == ["meta", "meta"]
    assert snippet(res[-1]) is None


# ---- LaTeX export ---------------------------------------------------------------------
def test_export_declares_custom_units_for_siunitx():
    ws = evaluate("'psi_g = 6894.76'Pa\np = 3'psi_g\nd = 2'smoot", siunitx=True, global_units=SMOOT)
    tex = document(ws.results, declarations=ws.declarations)
    assert r"\DeclareSIUnit{\psiUnderg}{psi\_g}" in tex and r"\DeclareSIUnit{\smoot}{smoot}" in tex
    assert r"\qty{3}{\psiUnderg}" in tex and r"\qty{2}{\smoot}" in tex
    assert tex.index(r"\DeclareSIUnit") < tex.index(r"\begin{document}")


def test_export_without_custom_units_has_no_declarations():
    ws = evaluate("x = 3'kN", siunitx=True)
    assert ws.declarations == [] and r"\DeclareSIUnit" not in document(ws.results, declarations=ws.declarations)


def test_export_declares_pint_units_siunitx_lacks():
    # #38: 'g0 came out as \standard_gravity, which is not a macro name at all
    ws = evaluate("a = 11.76'm/'s^2 -> 'g0\nb = 2'psi\nc = 3'mg0*'ft", siunitx=True)
    tex = document(ws.results, declarations=ws.declarations)
    assert r"\qty{1.199}{\standardGravity}" in tex and r"\qty{2}{\poundForcePerSquareInch}" in tex
    assert r"\milli\standardGravity" in tex
    assert r"\DeclareSIUnit{\standardGravity}{\ensuremath{\mathrm{g}_{\mathrm{0}}}}" in tex
    assert r"\DeclareSIUnit{\foot}{\ensuremath{\mathrm{ft}}}" in tex
    assert tex.count(r"\DeclareSIUnit{\standardGravity}") == 1


def test_export_uses_siunitx_spellings_and_declares_nothing_it_knows():
    ws = evaluate("a = 2'eV\nb = 3'au\nc = 4't\nd = 5'km/'h\ne = 6'degC\nf = 7'percent", siunitx=True)
    tex = "\n".join(r.latex for r in ws.results)
    assert all(m in tex for m in (r"\electronvolt", r"\astronomicalunit", r"\tonne", r"\kilo\meter\per\hour",
                                  r"\degreeCelsius", r"\percent"))
    assert ws.declarations == []


def test_every_exported_unit_macro_is_a_name_latex_accepts():
    units = "g0 psi ksi ft inch lbf Btu kWh atm mmHg rpm m_e N_A mu_0 sq_ft Phi_0 R_inf hp"
    ws = evaluate("\n".join(f"x{i} = 1'{u}" for i, u in enumerate(units.split())), siunitx=True)
    for r in ws.results:
        assert r.kind == "assign", r.error
        assert re.fullmatch(r"(\\[A-Za-z]+)+", re.search(r"\\qty\{1\}\{(.*)\}", r.latex).group(1))


def test_preview_subscripts_constant_symbols():
    assert last("a = 1'g0").latex.endswith(r"1\,\mathrm{g}_{\mathrm{0}}")
    assert r"\frac{\mathrm{N}_{\mathrm{A}}}{\mathrm{m}_{\mathrm{e}}^{2}}" in last("a = 1'N_A/'m_e^2").latex
    assert r"\mathrm{mg}_{\mathrm{0}}" in last("a = 1'mg0").latex
    assert r"\mathrm{sq\_ft}" in last("a = 1'sq_ft").latex    # a word, not a subscript


def test_preview_uses_plain_names():
    assert r"\mathrm{smoot}" in last("d = 2'smoot", global_units=SMOOT).latex


def test_unit_definition_snippet():
    r = run("'smoot = 1.7018'm", siunitx=True)[0]
    assert snippet(r, "inline").startswith(r"1\,\unit{\smoot} = \qty{1.702}{\meter}")
