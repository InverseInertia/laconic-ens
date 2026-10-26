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


def test_infinity_subscript():
    # free-stream T_∞, typed with Ctrl+G 8 or spelled out as inf
    assert r"v_{\infty} = 3" in last("v_∞ = 3").latex
    assert r"T_{\infty} \cdot 2" in last("T_inf = 3\nT_inf*2").latex
    assert last("T_∞ = 3\nT_∞ + 1").text == "4"
    assert r"\vec{v}_{\infty,0}" in last("v_∞_0! = 1").latex
    assert r"q_{\infty}" in last("q_∞(h) = 2*h").latex
    # only a whole `inf` part is infinity, and ∞ alone is still the constant
    assert r"x_{\mathrm{info}}" in last("x_info = 1").latex
    assert r"x_{\mathrm{infl}}" in last("x_infl = 1").latex
    assert r"\mathrm{inf}" in last("inf = 1").latex
    r = last("x = 2*∞")
    assert not r.error and r.text == "x = ∞"


def test_infinity_subscript_in_export():
    tex = document(run("T_∞ = 300'K\nT_inf = T_∞", siunitx=True))
    assert r"T_{\infty}" in tex and "∞" not in tex.split("\\begin{document}")[1]


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
    res = run("~g = 9.81'm/'s^2\nm = 10'kg\n!clear\nW = m*g\nv = g")
    assert res[2].kind == "command" and "m" in res[2].text
    assert res[3].kind == "error" and "'m' was removed by !clear" in res[3].error
    assert res[4].kind == "assign" and "9.81" in res[4].text


def test_a_global_and_a_plain_variable_never_share_a_name():
    res = run("~g = 5\ng = 7\n!clear\nv = g\nw = ~g")
    assert res[1].kind == "assign" and res[1].text == "~g = 7"   # assigns the global
    assert res[3].text == "v = 7" and res[4].text == "w = 7"
    res = run("g = 1\n~g = 2")
    assert res[1].kind == "error" and "non-global" in res[1].error
    res = run("f(x) = x\n~f(x) = 2*x")
    assert res[1].kind == "error" and "non-global" in res[1].error
    res = run("~f(x) = x\nf(x) = 2*x\n!clearf\na = f(3)")
    assert res[3].text == "a = 6"


def test_global_names_render_without_the_tilde():
    r = last("~g_x = 3")
    assert r"g_{x}" in r.latex and "~" not in r.latex


def test_globals_are_tagged_in_the_live_view_only():
    from laconic.sheet import evaluate
    live = evaluate("~g = 5\n~f(x) = x\ny = 2*g + f(1)").results
    assert live[0].latex.startswith(r"\htmlData{global=g}{g}")
    assert live[1].latex.startswith(r"\htmlData{global=f}{f}\left(x")
    assert live[2].latex.startswith(r"y = 2 \cdot \htmlData{global=g}{g} + \htmlData{global=f}{f}")
    assert "htmlData" not in evaluate("~g = 5\ny = 2*g", siunitx=True).results[1].latex


def test_a_plain_assignment_of_a_global_warns():
    res = run("~g = 5\ng = 12\n~g = 7\nx = g\n~f(x) = x\nf(x) = 2*x")
    assert res[1].warning == "Changes the global ~g, defined on line 1. Write ~g if that is meant"
    assert res[2].warning == res[3].warning == ""      # written with its ~, or only read
    assert res[5].warning.startswith("Changes the function ~f, defined on line 5")


def test_command_snippet_is_a_latex_comment():
    from laconic import snippet
    assert snippet(last("a = 1\n!clear"), "inline") == "% !clear"


def test_accent_marks_after_names():
    rs = run("x` = 2'm/'s\nx`` = 3'm/'s^2\nF_x! = 5'kN\nq@ = 1\nv`! = 4'm/'s\ny = x` * 2'm/'s")
    assert [r.lhs for r in rs[:5]] == [
        "\\dot{x}", "\\ddot{x}", "\\vec{F}_{x}", "\\hat{q}", "\\vec{\\dot{v}}"]
    assert rs[5].kind == "assign" and "\\dot{x}" in rs[5].stages[0]
    assert rs[0].text.startswith("x` = 2")


def test_accented_name_is_its_own_variable():
    r = last("x = 1\nx! = 2\nx! + x")
    assert r.kind == "expr" and r.text == "3"


def test_too_many_dots_is_an_error():
    assert run("x``` = 1")[0].kind == "error"


def test_floor_ceil_keep_units():
    assert last("floor(2.7'm)").text.endswith("2 m")
    assert last("ceil(2.1'm)").text.endswith("3 m")
    assert last("floor(-2.1)").text.endswith("-3")


def test_heaviside_and_aliases():
    for name in ("heaviside", "step", "heav"):
        assert last(f"{name}(-1'm)").text.endswith("0")
        assert last(f"{name}(0)").text.endswith("1")
        assert last(f"{name}(3)").text.endswith("1")


def test_pound_mass_is_lbm_and_lb_is_gone():
    assert last("3'kg -> 'lbm").text == "6.614 lbm"
    assert last("5'lb").error
    assert last("1'lbf -> 'N").text.startswith("4.448")


def test_infinity_is_a_constant():
    assert last("x = ∞").text == "x = ∞"
    r = last("x = -∞*2'm")
    assert r.text == "x = -∞ m" and r.latex.endswith(r"= -\infty\,\mathrm{m}")
    assert last("x = 1/∞").text == "x = 0"
    assert last("x = ∞\ny = x + 1").text == "y = ∞"
    assert r"\infty\,\unit{\meter}" in run("x = ∞*3'm", siunitx=True)[-1].latex  # \qty cannot parse it


def test_only_a_typed_in_infinity_may_give_an_infinite_result():
    assert "not finite" in last("x = exp(1000)").error
    assert "not finite" in last("x = ∞ - ∞").error
    assert last("x = 1/0").error


def test_a_year_shows_as_yr_and_a_still_reads_as_one():
    r = last("t = 2.5'yr")
    assert r.text == "t = 2.5 yr" and r"\mathrm{yr}" in r.latex
    assert last("t = 3'a").text == "t = 3 yr"
    assert last("t = 365.25'd -> 'year").text == "t = 1 yr"


def test_index_functions_count_from_one_and_print_as_subscripts():
    r = last("A = [1,2,3;4,5,6]\nelem(A, 2, 3)")
    assert r.text == "6" and "{A}_{2,\\,3}" in r.latex
    r = last("v = [10;20;30]\ni = 2\nidx(v, i)")
    assert r.text == "20" and "{v}_{i} = {v}_{2}" in r.latex
    assert last("A = [1,2;3,4]\nidx(A, 2)").latex.endswith("\\begin{bmatrix} 3 & 4 \\end{bmatrix}")


def test_indexes_nest_and_keep_units():
    r = last("A = [1,2;3,4] * 1'm\nelem(idx(A, 2), 1, 2)")
    assert r.text == "4 m" and "{{A}_{2}}_{1,\\,2}" in r.latex


def test_index_out_of_range_is_an_error():
    assert "out of range" in last("elem([1,2;3,4], 3, 1)").error
    assert "out of range" in last("idx([1;2], 0)").error


def test_matrix_functions():
    assert last("trace([1,2;3,4])").text == "5"
    assert last("rank([1,2;2,4])").text == "1"
    assert last("dot([1;2;3], [4;5;6])").text == "32"
    assert last("cross([1;0;0], [0;1;0])").latex.endswith("\\begin{bmatrix} 0 \\\\ 0 \\\\ 1 \\end{bmatrix}")
    assert last("rows(zeros(2, 3))").text == "2" and last("cols(zeros(2, 3))").text == "3"
    assert last("eigvals([2,0;0,3])").latex.endswith("\\begin{bmatrix} 2 \\\\ 3 \\end{bmatrix}")
    assert "1 & 1" in last("hstack([1;2], [1;2])").latex
    assert last("max([1,5;3,2])").text == "5"


def test_sigfigsbig_keeps_trailing_zeros():
    rs = run("a = 2.5\nb = 12345.678\nc = 0.00012\nd = 3e9\n!sigfigsbig 4\na\nb\nc\nd\n0\n!sigfigs 4\na")
    shown = lambda r: r.text.split("= ")[-1]
    assert [shown(rs[i]) for i in (5, 6, 7, 8, 9, 11)] == ["2.500", "12350", "0.0001200", "3.000e9", "0.000", "2.5"]


def test_browser_env_restores_library_path_when_frozen(monkeypatch):
    """#37: a browser started from the PyInstaller build must not see the bundle's
    LD_LIBRARY_PATH (Firefox fails to start with it)."""
    import sys
    from laconic import __main__ as cli
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEI123")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/opt/lib")
    env = cli._browser_env()
    assert env["LD_LIBRARY_PATH"] == "/opt/lib" and "LD_LIBRARY_PATH_ORIG" not in env
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG")
    assert "LD_LIBRARY_PATH" not in cli._browser_env()
    monkeypatch.setattr(sys, "frozen", False)
    assert cli._browser_env()["LD_LIBRARY_PATH"] == "/tmp/_MEI123"


def test_launch_passes_clean_env_and_reports_failure(monkeypatch, capsys):
    import sys
    from laconic import __main__ as cli
    calls = []

    def fake_popen(cmd, **kw):
        calls.append((cmd, kw["env"]))
        raise OSError("no display")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEI123")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    monkeypatch.setattr(cli.shutil, "which", lambda exe: "/usr/bin/" + exe)
    monkeypatch.setattr(cli.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: False)
    cli._launch("http://127.0.0.1:1", app=False)
    assert calls[0][0] == ["xdg-open", "http://127.0.0.1:1"]
    assert "LD_LIBRARY_PATH" not in calls[0][1]
    assert "open http://127.0.0.1:1 by hand" in capsys.readouterr().out
