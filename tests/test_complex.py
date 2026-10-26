"""Complex numbers: the imaginary literal (4i, 4j), the polar sign (5∠30'deg), the
!complex display modes, and the places that stay real on purpose."""
from laconic import document, run, snippet


def rows(text, **kw):
    return [r for r in run(text, **kw) if r.kind not in ("blank", "comment", "command")]


def last(text, **kw):
    return rows(text, **kw)[-1]


def shown(r):
    return r.text.split("= ")[-1]


# ---- writing them ----------------------------------------------------------------
def test_imaginary_literal_with_i_or_j():
    assert shown(last("z = 3 + 4i")) == "3 + 4i"
    assert shown(last("3 - 4j")) == "3 - 4i"
    assert shown(last("2.5e3i")) == "2500i"


def test_a_number_and_a_name_starting_with_i_are_not_imaginary():
    assert "cannot follow a number" in last("2in").error


def test_imaginary_quantity_with_a_unit():
    assert shown(last("Z = 3'ohm + 4i'ohm")) == "(3 + 4i) Ω"
    assert shown(last("V = (2 + 1i)*'V")) == "(2 + 1i) V"


def test_polar_sign_reads_the_angle_unit():
    assert shown(last("10'V∠30'deg")) == "(8.66 + 5i) V"
    assert shown(last("!trigdeg\n2∠90")) == "2i"
    assert shown(last("2∠(pi/2)")) == "2i"


def test_polar_sign_binds_looser_than_product():
    assert shown(last("1 + 2*1∠0")) == "3"


def test_polar_sign_needs_an_angle_and_real_sides():
    assert "must be an angle" in last("5∠3'm").error
    assert "must be real" in last("(1i)∠0").error


def test_offset_units_cannot_be_complex():
    assert "offset unit" in last("4i'degC").error
    assert "offset unit" in last("5'degC∠30'deg").error


# ---- arithmetic -------------------------------------------------------------------
def test_euler():
    assert shown(last("e^(1i*pi)")) == "-1"
    assert shown(last("exp(1i*pi/2)")) == "1i"


def test_imaginary_parts_that_cancel_leave_a_real_number():
    assert shown(last("(1 + 1i)*(1 - 1i)")) == "2"
    assert shown(last("x = (1i)^2\nfloor(x)")) == "-1"


def test_a_typed_imaginary_number_is_one_term():
    r = last("4i^2")
    assert shown(r) == "-16" and r"\left(4\mathrm{i}\right)^{2}" in r.latex


def test_real_input_stays_real_with_a_hint():
    assert "Add 0i" in last("sqrt(-4)").error
    assert "Add 0i" in last("(-8)^(1/3)").error
    assert "Add 0i" in last("ln(-1)").error
    assert shown(last("sqrt(-4 + 0i)")) == "2i"
    assert shown(last("ln(-1 + 0i)")) == "3.142i"


def test_complex_functions():
    r = rows("z = 3 + 4i\nre(z)\nim(z)\nconj(z)\nabs(z)\n!trigdeg\narg(z)")
    assert [shown(x) for x in r[1:]] == ["3", "4", "3 - 4i", "5", "53.13 deg"]
    assert r"\operatorname{Re}" in r[1].latex and r"\overline{" in r[3].latex


def test_ordering_functions_refuse_complex():
    for f in ("floor", "ceil", "min", "max", "heaviside"):
        assert "needs a real argument" in last(f"{f}(1 + 1i)").error, f


def test_complex_matrices_and_eigenvalues():
    assert last("[1 + 1i, 2]").text == "[[1+1i 2]]"
    assert last("eigvals([0, -1; 1, 0])").text == "[[-1i]\n [1i]]"
    assert last("eigvals([2, 1; 1, 2])").text == "[[1]\n [3]]"


# ---- !complex --------------------------------------------------------------------
def test_polar_display_follows_the_trig_unit():
    r = rows("z = 3 + 4i\n!complex polar\nz\nv = 3'V + 4i'V\n!trigdeg\nz\nv\nw = 2*v")
    assert [shown(x) for x in r[1:]] == ["5∠0.9273 rad", "5 V∠0.9273 rad", "5∠53.13°", "5 V∠53.13°",
                                         "10 V∠53.13°"]
    assert r"5\,\mathrm{V}\angle 53.13^\circ" in r[4].latex


def test_real_mode_refuses_complex_results_only():
    r = rows("z = 3 + 4i\n!complex real\nz\nabs(z)\nexp(1i*pi)\nw = sqrt(-1 + 0i)")
    assert "allows only real results" in r[1].error
    assert shown(r[2]) == "5" and shown(r[3]) == "-1"   # rounding noise in the imaginary part is dropped
    assert "allows only real results" in r[4].error


def test_naming_a_variable_i_or_j_warns_unless_real():
    r = rows("i = 3\n~j = 1\nk = 2\n!complex real\ni = 4")
    assert "imaginary unit" in r[0].warning and "1i" in r[0].warning
    assert "imaginary unit" in r[1].warning and "1j" in r[1].warning
    assert r[2].warning == "" and r[3].warning == ""


# ---- plots, solvers, export ------------------------------------------------------
def test_a_complex_plot_says_what_to_plot_instead():
    r = run("!plot 1i*x, x = 0 .. 1")[0]
    assert "complex" in r.error and "re()" in r.error


def test_a_real_plot_keeps_its_gaps():
    r = run("!plot sqrt(x), x = -1 .. 1\n  gaps: break")[0]
    assert not r.error


def test_solver_refuses_complex():
    from laconic.sheet import solve_block
    out = solve_block("x = 1\n!root x\n  equation: x + 1i = 2", 2, log=lambda m: None)
    assert not out["ok"] and "real numbers" in out["message"]
    out = solve_block("x = 1i\n!root x\n  equation: x = 2", 2, log=lambda m: None)
    assert not out["ok"] and "is complex" in out["message"]


def test_siunitx_export():
    r = last("Z = 3'ohm + 4i'ohm", siunitx=True)
    assert r"\complexqty{3+4i}{\ohm}" in r.latex
    assert r"\complexqty{4i}{\ohm}" in r.latex   # the typed-in 4i'ohm
