import pytest

from laconic import document, run


def last(text):
    return [r for r in run(text) if r.kind != "blank"][-1]


def test_units_and_conversion():
    r = last("m = 10'kg\na = 9.81'm/'s^2\nF = m*a -> 'N")
    assert r.kind == "assign" and r.text.startswith("F = 98.1")


def test_variable_m_and_unit_m_coexist():
    r = last("m = 80'kg\nL = 4.5'm\nv = 12'm/'s")
    assert r.kind == "assign" and "12" in r.text


def test_one_walk_finds_the_names_calls_and_units_of_an_expression():
    from laconic.nodes import refs
    from laconic.parser import parse_expr, parse_line
    r = refs(parse_expr("f(a, [b, 2'm; c^2, 'kN]) + 3 d 'mm"))
    assert r == ({"a", "b", "c", "d"}, {"f"}, {"m", "kN", "mm"})
    assert refs(parse_line("g(x) = x * h(y)")).calls == {"h"}


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
    assert str(reduce_si(u.Quantity(20, "degF*m"), u).units) == "kelvin * meter"   # only a lone °F
    assert str(reduce_si(u.Quantity(20, "degRe"), u).units) == "kelvin"


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


def test_a_bar_mark_puts_a_bar_over_the_name():
    rs = run("u& = 2'm/'s\nF_x& = 5'kN\nv&` = 1\nu = 3'm/'s\ny = u& + u")
    assert [r.lhs for r in rs[:3]] == ["\\bar{u}", "\\bar{F}_{x}", "\\dot{\\bar{v}}"]
    assert rs[4].text == "y = 5 m/s" and "\\bar{u} + u" in rs[4].stages[0]


def test_forall_is_the_struck_through_v_for_volume():
    rs = run("∀_cv = 2'm^3\n∀& = 1\n∀_cv\nforall = 3")
    assert rs[0].lhs == "\\forall_{\\mathrm{cv}}" and rs[1].lhs == "\\bar{\\forall}"
    assert rs[2].text == "2 m³"
    assert rs[3].lhs == "\\mathrm{forall}"   # the spelled-out word is an ordinary name


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


def test_a_liter_shows_as_capital_L_and_l_still_reads_as_one():
    r = last("V = 3'L")
    assert r.text == "V = 3 L" and r"\mathrm{L}" in r.latex
    assert last("V = 3'l").text == "V = 3 L"
    assert last("V = 2'mL").text == "V = 2 mL"
    assert last("V = 5'kL").text == "V = 5 kL"
    assert last("Q = 4'L/'min").text == "Q = 4 L/min"
    assert last("V = 1'L -> 'mL").text == "V = 1000 mL"


def test_a_typed_quantity_inside_an_expression_keeps_its_number_before_its_unit():
    # 0.72 kg/L, as its own line shows it, not \frac{0.72 kg}{L}
    r = last("m = 0.72'kg/'L * 20'L")
    assert r.latex.startswith(r"m = 0.72\,\frac{\mathrm{kg}}{\mathrm{L}} \cdot 20\,\mathrm{L} = ")
    r = run("m = 0.72'kg/'L * 20'L", siunitx=True)[0]
    assert r.latex.startswith(r"m = \qty{0.72}{\kilo\gram\per\liter} \cdot \qty{20}{\liter} = ")
    # two numbers is a calculation, still a fraction
    assert r"\frac{10\,\mathrm{kg}}{0.72\,\mathrm{L}}" in last("w = 10'kg/0.72'L").latex


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
    rs = run("a = 2.5\nb = 12345.678\nc = 0.00012\nd = 3e9\n!sigfigsbig 4\na\nb\nc\nd\na - a\n!sigfigs 4\na")
    shown = lambda r: r.text.split("= ")[-1]
    assert [shown(rs[i]) for i in (5, 6, 7, 8, 9, 11)] == ["2.500", "12350", "0.0001200", "3.000e9", "0.000", "2.5"]


def test_typed_in_values_are_shown_as_typed():
    """#96: the sheet's figures round what it computes, not a number or quantity typed on its own."""
    rs = run("L = 12345.678'm\nx = 3.14159265\n-2.718281828\nv = 3.14159'm/'s\n2*x")
    assert [r.text for r in rs] == ["L = 12345.678 m", "x = 3.14159265", "-2.718281828",
                                    "v = 3.14159 m/s", "6.283"]
    assert rs[0].stages == ["12345.678\\,\\mathrm{m}"]
    assert rs[1].stages == ["3.14159265"]


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


def test_app_window_gets_the_launchers_wm_class_on_linux(monkeypatch, tmp_path):
    """#66: the desktop matches a window to its launcher (and icon) by WM_CLASS. The app
    window must carry the launcher's StartupWMClass, from a browser process of its own."""
    import sys
    from laconic import __main__ as cli
    calls = []
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    for var in ("WAYLAND_DISPLAY", "XDG_SESSION_TYPE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(cli.browser, "candidates", lambda: iter(["/usr/bin/google-chrome"]))
    monkeypatch.setattr(cli, "_spawn", lambda cmd: calls.append(cmd) or True)
    cli._launch("http://127.0.0.1:1", app=True)
    cmd = calls[0]
    assert "--class=lens" in cmd and cmd[-1] == "--app=http://127.0.0.1:1"
    assert f"--user-data-dir={tmp_path / 'laconic-lens' / 'browser-google-chrome'}" in cmd
    assert not any(a.startswith("--ozone-platform") for a in cmd)
    monkeypatch.setattr(sys, "platform", "win32")
    assert cli._app_args("http://x", "chrome.exe") == ["--app=http://x"]


def test_app_window_on_wayland_goes_through_xwayland(monkeypatch, tmp_path):
    """#93: on Wayland Chromium names an app window "chrome-127.0.0.1__-Default" whatever
    --class says, so no launcher matches it. With XWayland there, the window opens through it
    and keeps --class=lens; with no X server, or from a sandboxed browser, it does not."""
    import sys
    from laconic import __main__ as cli
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(cli.browser.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("DISPLAY", ":0")
    args = cli._app_args("http://x", "/usr/bin/google-chrome")
    assert "--ozone-platform=x11" in args and "--class=lens" in args and args[-1] == "--app=http://x"
    monkeypatch.delenv("WAYLAND_DISPLAY")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert "--ozone-platform=x11" in cli._app_args("http://x", "/usr/bin/google-chrome")
    assert "--ozone-platform=x11" not in cli._app_args("http://x", "/snap/bin/chromium")
    flat = tmp_path / ".local/share/flatpak/exports/bin/com.brave.Browser"
    assert "--ozone-platform=x11" not in cli._app_args("http://x", str(flat))
    monkeypatch.delenv("DISPLAY")   # Wayland with no XWayland
    assert "--ozone-platform=x11" not in cli._app_args("http://x", "/usr/bin/google-chrome")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")   # plain X11: --class works as it is
    assert "--ozone-platform=x11" not in cli._app_args("http://x", "/usr/bin/google-chrome")


def test_app_window_prefers_a_native_browser_to_a_sandboxed_one(monkeypatch, tmp_path):
    """#93: Cinnamon and GNOME tie a flatpak or snap browser's windows to that browser, before
    looking at WM_CLASS, so a native browser comes first for the app window, even when the
    sandboxed one is the default. A sandboxed browser is still used when it is the only one."""
    import sys
    from laconic import __main__ as cli
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(cli.browser.Path, "home", lambda: tmp_path)
    flat = str(tmp_path / ".local/share/flatpak/exports/bin/com.brave.Browser")
    wrapper = tmp_path / "usr/bin/chromium-browser"   # Ubuntu's: a script that runs the snap
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text('#!/bin/sh\nexec /snap/bin/chromium "$@"\n')
    native = tmp_path / "usr/bin/vivaldi"
    native.write_text("")
    found = [flat, "/snap/bin/chromium", str(wrapper), str(native)]
    monkeypatch.setattr(cli.browser, "candidates", lambda: iter(found))
    assert list(cli.browser.app_candidates()) == [str(native), flat, "/snap/bin/chromium", str(wrapper)]
    assert cli.browser.find() == flat   # the PDF export still takes the first one found
    calls = []
    monkeypatch.setattr(cli, "_spawn", lambda cmd: calls.append(cmd[0]) or True)
    cli._launch("http://127.0.0.1:1", app=True)
    assert calls == [str(native)]
    monkeypatch.setattr(cli.browser, "candidates", lambda: iter([flat]))
    cli._launch("http://127.0.0.1:1", app=True)
    assert calls[-1] == flat


def test_each_browser_gets_a_profile_of_its_own(monkeypatch, tmp_path):
    """#93: a window opened with a profile another browser (or an older LENS) is running hands
    the page to that process, and takes its identity rather than --class. Each browser has its
    own profile; a snap reached through a wrapper script keeps its profile inside the snap."""
    from laconic import browser
    monkeypatch.setattr(browser.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    real = tmp_path / "opt/google/chrome/google-chrome"
    real.parent.mkdir(parents=True)
    real.write_text("")
    link = tmp_path / "bin/google-chrome-stable"
    link.parent.mkdir()
    link.symlink_to(real)
    assert browser.profile_dir(link) == tmp_path / "cache/laconic-lens/browser-google-chrome"
    assert browser.profile_dir("/usr/bin/brave-browser") == tmp_path / "cache/laconic-lens/browser-brave-browser"
    wrapper = tmp_path / "bin/chromium-browser"
    wrapper.write_text('#!/bin/sh\n# Ubuntu\nexec /snap/bin/chromium.chromium "$@"\n')
    assert browser.sandbox(wrapper) == ("snap", "chromium")
    assert browser.profile_dir(wrapper) == tmp_path / "snap/chromium/common/laconic-lens"
    assert browser.sandbox(real) is None and browser.sandbox(tmp_path / "missing") is None


def _no_browsers(monkeypatch, tmp_path, platform, default=None):
    """browser.find on `platform` with nothing installed, `default` the default browser's
    .desktop name (none when None) and an empty home."""
    import sys
    from laconic import browser
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.delenv("LENS_CHROMIUM", raising=False)
    monkeypatch.setattr(browser.shutil, "which", lambda exe: None)
    monkeypatch.setattr(browser.subprocess, "run",
                        lambda *a, **k: browser.subprocess.CompletedProcess(a, 0, (default or "") + "\n", ""))
    monkeypatch.setattr(browser, "_windows_default", lambda: None)
    monkeypatch.setattr(browser.Path, "home", lambda: tmp_path)
    return browser


def test_find_browser_takes_any_chromium_family_browser(monkeypatch, tmp_path):
    """#72: Brave (or Vivaldi, Opera...) alone is enough for the app window and the PDF."""
    browser = _no_browsers(monkeypatch, tmp_path, "linux")
    assert browser.find() is None
    monkeypatch.setattr(browser.shutil, "which", lambda exe: "/usr/bin/brave" if exe == "brave" else None)
    assert browser.find() == "/usr/bin/brave"


def test_find_browser_prefers_the_default_browser(monkeypatch, tmp_path):
    """With Chrome and Brave both installed and Brave the default, LENS opens Brave."""
    browser = _no_browsers(monkeypatch, tmp_path, "linux", default="brave-browser.desktop")
    monkeypatch.setattr(browser.shutil, "which", lambda exe: "/usr/bin/" + exe)
    assert browser.find() == "/usr/bin/brave-browser"
    # A .desktop name LENS does not know: its Exec line names the program.
    browser = _no_browsers(monkeypatch, tmp_path, "linux", default="brave-custom.desktop")
    monkeypatch.setattr(browser.shutil, "which", lambda exe: "/usr/bin/" + exe)
    apps = tmp_path / "share" / "applications"
    apps.mkdir(parents=True)
    (apps / "brave-custom.desktop").write_text("[Desktop Entry]\nExec=/opt/brave.com/brave/brave-browser-stable %U\n")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    assert browser.find() == "/usr/bin/brave-browser-stable"
    # A default that is not Chromium-family is passed over.
    browser = _no_browsers(monkeypatch, tmp_path, "linux", default="firefox.desktop")
    monkeypatch.setattr(browser.shutil, "which", lambda exe: "/usr/bin/" + exe)
    assert browser.find() == "/usr/bin/google-chrome"


def test_find_browser_flatpak_windows_and_macos(monkeypatch, tmp_path):
    browser = _no_browsers(monkeypatch, tmp_path, "linux")
    flat = tmp_path / ".local/share/flatpak/exports/bin/com.brave.Browser"
    flat.parent.mkdir(parents=True)
    flat.write_text("")
    assert browser.find() == str(flat)
    assert browser.profile_dir(flat) == tmp_path / ".var/app/com.brave.Browser/cache/laconic-lens"
    assert browser.profile_dir("/snap/bin/brave") == tmp_path / "snap/brave/common/laconic-lens"

    browser = _no_browsers(monkeypatch, tmp_path, "win32")
    exe = tmp_path / "pf" / "BraveSoftware/Brave-Browser/Application/brave.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "pf"))
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert browser.find() == str(exe)

    browser = _no_browsers(monkeypatch, tmp_path, "darwin")
    app = tmp_path / "Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
    app.parent.mkdir(parents=True)
    app.write_text("")
    assert browser.find() == str(app)


def _windows_with(monkeypatch, tmp_path, registry=None):
    """browser.find on Windows with nothing installed, Program Files and AppData under tmp_path
    and `registry` ({(hive, key, name): value}) as the registry."""
    from laconic import browser
    windows_default = browser._windows_default
    browser = _no_browsers(monkeypatch, tmp_path, "win32")
    monkeypatch.setattr(browser, "_windows_default", windows_default)
    monkeypatch.setattr(browser, "_registry", lambda hive, key, name="": (registry or {}).get((hive, key, name)))
    for var, d in (("PROGRAMFILES", "pf"), ("PROGRAMFILES(X86)", "pf86"), ("LOCALAPPDATA", "local")):
        monkeypatch.setenv(var, str(tmp_path / d))
    return browser


def _install(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    return str(path)


def test_find_browser_on_windows_reads_app_paths(monkeypatch, tmp_path):
    """A browser installed outside Program Files and AppData is found where the registry's
    App Paths says it is; a stale App Paths entry is passed over."""
    brave = _install(tmp_path / "D" / "Brave" / "brave.exe")
    app_paths = r"Software\Microsoft\Windows\CurrentVersion\App Paths"
    browser = _windows_with(monkeypatch, tmp_path, {("HKLM", app_paths + r"\brave.exe", ""): f'"{brave}"',
                                                     ("HKCU", app_paths + r"\chrome.exe", ""): str(tmp_path / "gone.exe")})
    assert browser.find() == brave


def test_find_browser_on_windows_opera_and_the_default(monkeypatch, tmp_path):
    """Opera's per-user install is found, before the Edge every Windows has; the default
    browser's ProgId comes before both."""
    browser = _windows_with(monkeypatch, tmp_path)
    edge = _install(tmp_path / "pf86" / "Microsoft/Edge/Application/msedge.exe")
    opera = _install(tmp_path / "local" / "Programs/Opera/opera.exe")
    assert list(browser.candidates()) == [opera, edge]
    choice = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice"
    browser = _windows_with(monkeypatch, tmp_path, {("HKCU", choice, "ProgId"): "MSEdgeHTM"})
    assert list(browser.candidates()) == [edge, opera]
    browser = _windows_with(monkeypatch, tmp_path, {("HKCU", choice, "ProgId"): "OperaStable"})
    assert browser.find() == opera


def test_app_window_tries_the_next_browser_when_one_will_not_start(monkeypatch, tmp_path):
    import sys
    from laconic import __main__ as cli
    calls = []
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setattr(cli.browser, "candidates", lambda: iter(["/usr/bin/broken", "/usr/bin/brave"]))
    monkeypatch.setattr(cli, "_spawn", lambda cmd: calls.append(cmd[0]) or cmd[0] != "/usr/bin/broken")
    cli._launch("http://127.0.0.1:1", app=True)
    assert calls == ["/usr/bin/broken", "/usr/bin/brave"]


def test_page_links_the_app_window_icons():
    """#72: an app window takes its window and taskbar icon from the page's PNG icons."""
    import json
    from laconic import pdfdoc
    page = (pdfdoc.STATIC / "index.html").read_text(encoding="utf-8")
    manifest = json.loads((pdfdoc.STATIC / "manifest.json").read_text(encoding="utf-8"))
    assert '<link rel="manifest" href="/static/manifest.json">' in page
    for icon in manifest["icons"]:
        assert (pdfdoc.STATIC / icon["src"].removeprefix("/static/")).is_file()
        assert icon["type"] != "image/png" or f'href="{icon["src"]}"' in page


def test_package_names_load_on_first_use():
    """The launcher and `--serve` import the package before Pint is needed; its names still work,
    and `markdown` stays the function even after the submodule is imported elsewhere."""
    import laconic
    from laconic import pdfdoc  # noqa: F401  (imports laconic.markdown the module)
    from laconic import markdown, run
    assert callable(markdown) and laconic.markdown is markdown
    assert run("1 + 1")[0].text.endswith("2")
    with pytest.raises(AttributeError):
        laconic.nothing_here


def test_serve_socket_listens_before_the_server_starts():
    """A browser started at once connects and waits in the queue; a taken port is an error."""
    import socket
    from laconic import __main__ as cli
    sock = cli._listen(0)
    try:
        port = sock.getsockname()[1]
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
        with pytest.raises(OSError):
            cli._listen(port)
    finally:
        sock.close()


def test_app_window_profile_has_spellcheck_on(monkeypatch, tmp_path):
    """#121 spellchecks comments and headings, but the app window's profile on Linux is LENS's
    own, with none of the user's settings: LENS turns spellcheck on in it, with a dictionary for
    the user's language, and leaves a profile where it was already set alone."""
    import json
    from laconic import browser
    for var in ("LC_ALL", "LC_MESSAGES"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LANG", "en_GB.UTF-8")
    prefs = tmp_path / "Default" / "Preferences"
    browser.spellcheck_on(tmp_path)
    assert json.loads(prefs.read_text()) == {"browser": {"enable_spellchecking": True},
                                             "spellcheck": {"dictionaries": ["en-GB"]}}
    prefs.write_text(json.dumps({"browser": {"enable_spellchecking": False}, "x": 1}))
    browser.spellcheck_on(tmp_path)   # turned off from the window's menu: stays off
    assert json.loads(prefs.read_text())["browser"]["enable_spellchecking"] is False
    prefs.write_text(json.dumps({"spellcheck": {"dictionaries": ["de-DE"]}, "x": 1}))
    browser.spellcheck_on(tmp_path)   # the browser's other settings and dictionaries are kept
    assert json.loads(prefs.read_text()) == {"browser": {"enable_spellchecking": True}, "x": 1,
                                             "spellcheck": {"dictionaries": ["de-DE"]}}
    prefs.write_text("{not json")
    browser.spellcheck_on(tmp_path)   # a profile it cannot read is not touched
    assert prefs.read_text() == "{not json"
    monkeypatch.setenv("LANG", "C.UTF-8")
    assert browser._dictionary() == "en-US"
    monkeypatch.setenv("LC_ALL", "de_DE.UTF-8")
    assert browser._dictionary() == "de-DE"
