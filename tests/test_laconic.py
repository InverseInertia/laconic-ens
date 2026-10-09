from laconic import document, run


def last(text):
    return [r for r in run(text) if r.kind != "blank"][-1]


def test_units_and_conversion():
    r = last("m = 10'kg\na = 9.81'm/'s^2\nF = m*a -> 'N")
    assert r.kind == "assign" and r.text.startswith("F = 98.1")


def test_variable_m_and_unit_m_coexist():
    r = last("m = 80'kg\nL = 4.5'm\nv = 12'm/'s")
    assert r.kind == "assign" and "12" in r.text


def test_number_then_variable_is_an_error():
    r = last("x = 3\n3 x")
    assert r.kind == "error" and "Write 3*x" in r.error


def test_bare_unit_name_is_not_a_unit():
    r = last("L = 2 + m")
    assert r.kind == "error" and "Units need an apostrophe" in r.error


def test_dimension_mismatch_does_not_stop_later_lines():
    res = run("a = 1'm + 1's\nb = 2")
    assert res[0].kind == "error" and res[1].kind == "assign"


def test_matrix_solve_units():
    res = run("K = [2,-1;-1,2] * 1000'kN/'m\nF = [10;5] * 'kN\nu = solve(K, F) -> 'mm")
    assert res[-1].kind == "assign"
    assert "8.333" in res[-1].latex


def test_matmul_vs_elementwise():
    assert "3 \\\\ 7" in last("[1,2;3,4]*[1;1]").latex
    assert "1 & 4" in last("[1,2;3,4] .* [1,2;3,4]").latex


def test_offset_units():
    assert "68" in last("20'degC -> 'degF").latex
    assert "68" in last("20'°C -> 'degF").latex


def test_user_function_and_scope():
    r = last("f(x, y) = x^2 + y\nf(3, 1)")
    assert "10" in r.latex


def test_function_may_use_a_later_variable():
    res = run("g(x) = x*k\nk = 3\ng(2)")
    assert res[0].kind == "funcdef" and "6" in res[-1].latex


def test_literal_lines_show_only_value():
    assert last("w = 12'kN/'m").latex.count("=") == 1


def test_stages_for_calculation():
    r = last("a = 2'm\nb = 3'm\nc = a*b")
    assert len(r.stages) == 3 and r.stages[0] == r"a \cdot b"


def test_parenthesization():
    assert r"\left(2\,\mathrm{m}\right)^{2}" in last("a = 2'm\nb = a^2").latex


def test_greek_and_subscripts():
    assert r"\sigma_{\mathrm{max}}" in last("sigma_max = 3").latex
    assert r"\sigma_{\mathrm{max}}" in last("σ_max = 3").latex
    r = last("α = 2\nβ = α*3")
    assert r"\beta = \alpha \cdot 3" in r.latex


def test_mixed_greek_name():
    assert r"\mathrm{\Delta x}" in last("Δx = 3").latex


def test_siunitx_export():
    tex = document(run("a = 2'm\nF = 5*'kN*a/'m", siunitx=True))
    assert r"\qty{" in tex and r"\begin{align*}" in tex and tex.rstrip().endswith(r"\end{document}")
    assert "\\unit{" in tex


def test_errors_are_specific():
    assert "singular" in last("inv([1,2;2,4])").error.lower()
    assert "not defined" in last("zzz + 1").error
    assert last("1/0").kind == "error"


def test_snippets_are_what_the_document_contains():
    from laconic import snippet
    res = run("## Title\n# note\nL = 2'm\nW = 3*L\n\nbad = 1 +", siunitx=True)
    snips = [snippet(r, "align") for r in res]
    assert snips[4] is None                       # blank line
    doc = document(res)
    assert all(s in doc for s in snips if s)
    assert snips[0] == r"\subsection*{Title}" and snips[1] == r"note\par"
    assert snips[3].startswith("\\begin{align*}\nW &= ") and snips[3].endswith("\\end{align*}")
    assert snips[5].startswith("% line 6:")


def test_wrap_modes():
    from laconic import snippet
    r = run("a = 2'm\nb = a*a", siunitx=True)[1]
    inline, display, align = (snippet(r, w) for w in ("inline", "display", "align"))
    assert inline == r.latex and "begin" not in inline and "\\[" not in inline
    assert display == "\\[ " + r.latex + " \\]"
    assert align.startswith("\\begin{align*}\nb &= ") and align.count("\\\\") == len(r.stages) - 1
    assert snippet(r) == inline                    # inline is the default


def test_latex_view_uses_export_flavour_and_wrap_setting():
    from laconic.server import Sheet, evaluate
    text = "L = 2'm\nA = L*L"
    typeset = evaluate(Sheet(text=text))
    inline = evaluate(Sheet(text=text, view="latex"))
    align = evaluate(Sheet(text=text, view="latex", wrap="align"))
    assert "snippet" not in typeset[0] and r"\mathrm{m}" in typeset[1]["latex"]
    assert r"\qty{2}{\meter}" in inline[1]["snippet"] and "begin" not in inline[1]["snippet"]
    assert "\\begin{align*}" in align[1]["snippet"]


# ---- default SI display --------------------------------------------------------
def shown(text):
    return last(text).text


def test_force_energy_power_pressure_get_named_units():
    assert shown("m = 10'kg\na = 9.81'm/'s^2\nF = m*a") == "F = 98.1 N"
    assert shown("F = 5'N\nd = 2'm\nW = F*d") == "W = 10 J"            # ambiguous with N*m: J wins
    assert shown("W = 10'J\nt = 2'min\nP = W/t").startswith("P = 0.08333 W")
    assert shown("F = 100'N\nA = 2'm^2\np = F/A") == "p = 50 Pa"
    assert shown("n = 3\nt = 2'min\nf = n/t").endswith("Hz")


def test_compound_si_units():
    assert shown("F = 10'kN\nd = 5'mm\nk = F/d") == "k = 2000000 N/m"
    assert shown("a = 5'm\nb = 2'mm\nr = a/b") == "r = 2500"            # dimensionless
    assert shown("x = 3'ft\ny = x*2") == "y = 1.829 m"
    assert shown("v = 3'm/'s\nq = v*v") == "q = 9 m\u00b2/s\u00b2"          # no named unit: stays reduced


def test_angles_keep_their_radians():
    assert shown("asin(0.5)") == "0.5236 rad"
    assert "rad" in shown("w = 2'rpm\nx = w*3")


def test_explicit_conversion_and_typed_quantities_are_left_alone():
    assert shown("E = 200'GPa") == "E = 200 GPa"
    assert shown("w = 12'kN / 'm") == "w = 12 kN/m"
    assert shown("F = 2'kN\nM = F*3'm -> 'kN*'m") == "M = 6 kN\u22c5m"
    assert shown("k = 10'kN / 5'mm") == "k = 2000000 N/m"                # two numbers: a calculation


def test_reduce_si_on_temperatures():
    from laconic.evaluator import registry
    from laconic.si import reduce_si
    u = registry()
    assert str(reduce_si(u.Quantity(68, "degF"), u).units) == "degree_Celsius"
    assert reduce_si(u.Quantity(20, "degC"), u).magnitude == 20


# ---- globals and !clear --------------------------------------------------------
def test_global_survives_clear_and_plain_variables_do_not():
    res = run("~g = 9.81'm/'s^2\nm = 10'kg\n!clear\nW = m*~g\nv = ~g")
    assert res[2].kind == "command" and "m" in res[2].text
    assert res[3].kind == "error" and "'m' was removed by !clear" in res[3].error
    assert res[4].kind == "assign" and "9.81" in res[4].text


def test_clear_reports_what_it_removed_and_keeps_functions():
    res = run("f(x) = 2*x\na = 1\nb = 2\n!clear\nf(3)\n!clear")
    assert res[3].text == "Cleared a, b"
    assert "6" in res[4].latex                       # user functions are not variables
    assert res[5].text == "Nothing to clear"


def test_unknown_command_and_arguments():
    assert "Unknown command" in last("!wipe").error
    assert "no arguments" in last("!clear a").error


def test_global_names_render_without_the_tilde():
    r = last("~g_x = 3")
    assert r"g_{x}" in r.latex and "~" not in r.latex


def test_command_snippet_is_a_latex_comment():
    from laconic import snippet
    assert snippet(last("a = 1\n!clear"), "inline") == "% !clear"
