"""Plots: the `plot` statement and its option lines, sampling, the writer that edits the
option lines, the SVG and pgfplots output, and the pieces around them (rename, save, CLI)."""
import json
import math
import re
import xml.dom.minidom
import shutil
import subprocess
import sys

import pytest
from fastapi import HTTPException

from laconic import document, evaluate, run, server, snippet
from laconic.plotopts import PlotError, apply_patch, parse_option, parse_plot, split_top
from laconic.plotsvg import axis_ticks, render_svg
from laconic.rename import RenameError, rename

BEAM = "L = 4.5'm\nw = 12'kN/'m\nM(x) = w*x*(L-x)/2\n"


def plots(text, **kw):
    return [r for r in evaluate(text, **kw).results if r.kind == "plot"]


def plot(text, **kw):
    (r,) = plots(text, **kw)
    return r.plot


def kinds(text):
    return [r.kind for r in run(text)]


# ---- syntax -----------------------------------------------------------------------

def test_plot_statement_splits_series_and_range():
    assert parse_plot("plot M(x), V(x), x = 0'm .. L") == (["M(x)", "V(x)"], "x", "0'm", "L")
    assert parse_plot("plot f(a, b), t = 1.5 .. 2") == (["f(a, b)"], "t", "1.5", "2")
    with pytest.raises(PlotError):
        parse_plot("plot sin(x)")


def test_split_top_ignores_commas_inside_brackets():
    assert split_top("f(a, b), [1, 2], c") == ["f(a, b)", "[1, 2]", "c"]


def test_a_variable_called_plot_is_still_a_variable():
    assert kinds("plot = 3\nplot") == ["assign", "expr"]


def test_option_lines_belong_to_the_plot_above():
    assert kinds("plot x, x = 0 .. 1\n  title: A\n  grid: off\n\nx = 2") == \
        ["plot", "plotopt", "plotopt", "blank", "assign"]
    r = run("plot x, x = 0 .. 1\n  title: A\n  grid: off")[0]
    assert r.end == 3


def test_an_indented_ordinary_line_ends_the_block():
    assert kinds("plot x, x = 0 .. 1\n  y = 2") == ["plot", "assign"]


def test_option_values_are_checked():
    for key, value, message in [("grid", "maybe", "on, off"), ("samples", "3", "between"), ("size", "5 x 5", "size reads"),
                                ("color", "chartreuse", "color is"), ("xlim", "3", "low .. high"),
                                ("note", "no quotes", "note reads"), ("width", "x", "number")]:
        with pytest.raises(PlotError, match=message):
            parse_option(key, None, value)
    assert parse_option("legend", None, "Top-Right")[2] == "top right"
    assert parse_option("color", 2, "#abc") == ("color", 2, "#aabbcc")
    with pytest.raises(PlotError, match="whole plot"):
        parse_option("title", 2, "x")


def test_a_bad_option_is_reported_on_its_own_line_and_the_plot_still_draws():
    res = run("plot x, x = 0 .. 1\n  grid: maybe\n  title: Fine")
    assert [r.kind for r in res] == ["plot", "error", "plotopt"]
    assert res[1].n == 2 and "on, off" in res[1].error
    assert res[0].plot["title"] == "Fine" and res[0].plot["grid"] is True


def test_unknown_option_lists_the_known_ones():
    res = run("plot x, x = 0 .. 1\n  colour: red")
    assert res[1].kind == "error" and "Unknown plot option 'colour'" in res[1].error and "color" in res[1].error


# ---- sampling and units -------------------------------------------------------------

def test_samples_are_evaluated_with_units():
    p = plot(BEAM + "plot M(x), x = 0'm .. L")
    s = p["series"][0]
    assert len(s["x"]) == 400 and s["x"][0] == 0 and s["x"][-1] == pytest.approx(4.5)
    mid = min(range(400), key=lambda i: abs(s["x"][i] - 2.25))
    assert s["y"][mid] == pytest.approx(30375, rel=1e-3)         # N*m, reduced to joules like any result
    assert p["y"]["unit"] == "J" and p["x"]["unit"] == "m"
    assert p["x"]["label"] == "x [m]" and p["y"]["label"] == "M(x) [J]"


def test_yunit_and_xunit_convert_the_display():
    p = plot(BEAM + "plot M(x), x = 0'm .. L\n  yunit: 'kN * 'm\n  xunit: 'mm")
    assert p["y"]["unit"] == "kN⋅m" and p["x"]["unit"] == "mm"
    assert p["x"]["lim"] == [0, pytest.approx(4500)]
    assert max(p["series"][0]["y"]) == pytest.approx(30.375, rel=1e-3)
    assert p["y"]["unit_src"] == "'kN * 'm"


def test_a_zero_without_units_takes_the_unit_of_the_other_end():
    assert plot("plot x, x = 0 .. 2'm")["x"]["unit"] == "m"


def test_unit_mismatches_are_errors():
    assert "different units" in run("plot x, x = 0'm .. 1'kg")[0].error
    res = run("plot 1'm * x, 1'kg * x, x = 0 .. 1")
    assert res[0].kind == "error" and "Plot them separately" in res[0].error


def test_a_bad_unit_option_is_reported_and_ignored():
    res = run("plot 1'm * x, x = 0 .. 1\n  yunit: 'kg")
    assert [r.kind for r in res] == ["plot", "error"] and res[0].plot["y"]["unit"] == "m"


def test_user_functions_and_variables_are_visible_to_a_plot():
    p = plot("a = 3\nf(t) = a*t\nplot f(x), x = 0 .. 2")
    assert p["series"][0]["y"][-1] == pytest.approx(6)


def test_dimensionless_plot_has_plain_labels():
    p = plot("plot sin(x), x = 0 .. 6")
    assert p["x"]["label"] == "x" and p["y"]["label"] == "sin(x)" and p["x"]["unit_src"] == ""


def test_undefined_names_fail_on_the_plot_line():
    r = run("plot q(x), x = 0 .. 1")[0]
    assert r.kind == "error" and "Unknown function 'q'" in r.error
    assert "is not defined" in run("plot a*x, x = 0 .. 1")[0].error


def test_matrix_results_are_refused():
    assert "single value" in run("plot [1, 2], x = 0 .. 1")[0].error


def test_range_must_increase_and_log_needs_positive():
    assert "low to high" in run("plot x, x = 5 .. 1")[0].error
    assert "above zero" in run("plot x, x = -1 .. 1\n  xscale: log")[0].error


def test_gaps_where_the_expression_is_undefined():
    p = plot("plot sqrt(x), x = -1 .. 1\n  samples: 11")
    ys = p["series"][0]["y"]
    assert ys[0] is None and ys[-1] == pytest.approx(1)
    r = run("plot 1/x, x = -1 .. 1\n  gaps: error\n  samples: 11")[0]
    assert r.kind == "error" and "undefined at x = 0" in r.error


def test_a_pole_does_not_join_its_two_branches():
    p = plot("plot 1/x, x = -2 .. 2\n  ylim: -10 .. 10")
    xs, ys = p["series"][0]["x"], p["series"][0]["y"]
    assert xs == sorted(xs)
    assert None in ys                                           # a gap was inserted
    gap = ys.index(None)
    assert ys[gap - 1] < -10 and ys[gap + 1] > 10


def test_sampling_follows_the_visible_window():
    p = plot("plot sin(x), x = 0 .. 100\n  xlim: 10 .. 11\n  samples: 50")
    xs = p["series"][0]["x"]
    assert len(xs) == 50 and xs[0] == 10 and xs[-1] == 11


def test_log_axes_sample_geometrically_and_drop_nonpositive_values():
    p = plot("plot x - 5, x = 1 .. 100\n  xscale: log\n  yscale: log\n  samples: 20")
    s = p["series"][0]
    assert s["x"][1] / s["x"][0] == pytest.approx(s["x"][2] / s["x"][1])
    assert s["y"][0] is None and p["y"]["lim"][0] > 0


def test_explicit_limits_and_steps():
    p = plot("plot x, x = 0 .. 10\n  xlim: 2 .. auto\n  ylim: -1 .. 20\n  xstep: 2")
    assert p["x"]["lim"] == [2, 10] and p["y"]["lim"] == [-1, 20] and p["x"]["step"] == 2
    assert p["x"]["view"] and p["y"]["view"]


def test_limits_given_in_the_wrong_order_or_unit_are_reported():
    res = run("plot x, x = 0'm .. 10'm\n  xlim: 5'm .. 2'm")
    assert res[1].kind == "error" and res[0].plot["x"]["lim"] == [0, 10]
    res = run("plot x, x = 0'm .. 10'm\n  xlim: 0'kg .. 1'kg")
    assert res[1].kind == "error" and "Incompatible" in res[1].error


def test_constant_series_still_gets_a_usable_axis():
    lo, hi = plot("plot 3 + 0*x, x = 0 .. 1")["y"]["lim"]
    assert lo < 3 < hi


def test_limits_and_notes_must_be_finite_so_the_page_can_always_be_sent():
    res = run("plot x, x = 0 .. 1\n  xlim: 0 .. exp(1000)")
    assert res[0].kind == "plot" and res[1].kind == "error" and "finite" in res[1].error
    res = run("plot x, x = 0 .. 1\n  note: \"n\" at (exp(1000), 0)")
    assert res[0].plot["notes"] == [] and "finite" in res[1].error
    rows = server.evaluate(server.Sheet(text="plot x, x = 0 .. 1\n  ylim: -exp(1000) .. 1"))      # serialises
    assert rows[0]["kind"] == "plot"


def test_a_plot_that_would_take_too_long_is_refused():
    r = run("plot " + ", ".join(["x"] * 30) + ", x = 0 .. 1\n  samples: 5000")[0]
    assert r.kind == "error" and "too many points" in r.error
    assert run("plot " + ", ".join(["x"] * 20) + ", x = 0 .. 1\n  samples: 5000")[0].kind == "plot"


def test_notes_are_placed_in_data_coordinates():
    p = plot(BEAM + "plot M(x), x = 0'm .. L\n  yunit: 'kN * 'm\n  note: \"max\" at (L/2, M(L/2))")
    (n,) = p["notes"]
    assert n["text"] == "max" and n["x"] == pytest.approx(2.25) and n["y"] == pytest.approx(30.375)


def test_series_options_by_number_and_for_all():
    p = plot("plot x, 2*x, x = 0 .. 1\n  width: 3\n  color 2: red\n  dash 2: dashed\n  label 1: first")
    a, b = p["series"]
    assert (a["width"], b["width"]) == (3, 3) and b["color"] == "#d55e00" and b["dash"] == "dashed"
    assert (a["label"], b["label"]) == ("first", "2*x") and p["legend"] == "top right"
    assert a["color"] != b["color"]
    assert "There is no series 3" in run("plot x, x = 0 .. 1\n  color 3: red")[1].error


def test_legend_is_automatic_only_for_several_series():
    assert plot("plot x, x = 0 .. 1")["legend"] is None
    assert plot("plot x, x = 0 .. 1\n  legend: bottom left")["legend"] == "bottom left"
    assert plot("plot x, 2*x, x = 0 .. 1\n  legend: off")["legend"] is None


# ---- defaults ------------------------------------------------------------------------

def test_plot_command_sets_defaults_for_the_plots_below():
    res = run("plot x, x = 0 .. 1\n!plot grid: off\n!plot size: 400 x 250\nplot x, x = 0 .. 1\n  grid: on\nplot x, x = 0 .. 1")
    ps = [r.plot for r in res if r.kind == "plot"]
    assert [p["grid"] for p in ps] == [True, True, False]
    assert [p["size"] for p in ps] == [[520, 320], [400, 250], [400, 250]]
    assert ps[2]["inherited"]["grid"] == "off"


def test_plot_reset_and_command_errors():
    res = run("!plot grid: off\n!plot reset\nplot x, x = 0 .. 1")
    assert res[0].kind == "command" and res[2].plot["grid"] is True
    assert run("!plot title: x")[0].kind == "error"            # per-plot only
    assert run("!plot color 2: red")[0].kind == "error"
    assert run("!plot")[0].kind == "error"


# ---- the writer ------------------------------------------------------------------------

AXES = {"x": {"unit_src": "'m", "scale": "lin"}, "y": {"unit_src": "'kN * 'm", "scale": "lin"}}
TEXT = "plot f(x), x = 0 .. 1\n  title: T\n\nz = 1"


def patch(text, p, line=1, inherited=None, axes=AXES):
    return apply_patch(text, line, p, axes, inherited or {})


def test_limits_are_written_with_units_and_rounded():
    out = patch(TEXT, {"xlim": [0.5000000001, 3.2000000002], "ylim": [-1.5187, 31.8935]})
    assert "  xlim: 0.5'm .. 3.2'm" in out and "  ylim: -1.52'kN * 'm .. 31.89'kN * 'm" in out
    assert out.endswith("\n\nz = 1") and out.index("xlim") < out.index("\n\nz")


def test_an_existing_line_is_replaced_in_place_and_none_removes_it():
    once = patch(TEXT, {"xlim": [1, 2]})
    twice = patch(once, {"xlim": [3, 4]})
    assert twice.count("xlim") == 1 and "3'm .. 4'm" in twice
    assert "xlim" not in patch(twice, {"xlim": None})
    assert patch(TEXT, {"xlim": None}) == TEXT


def test_a_value_equal_to_its_default_removes_the_line():
    on = patch(TEXT, {"grid": "off"})
    assert "  grid: off" in on
    assert "grid" not in patch(on, {"grid": "on"}, inherited={"grid": "on"})
    assert "  grid: on" in patch(TEXT, {"grid": "on"}, inherited={"grid": "off"})


def test_log_axis_limits_have_no_fixed_decimals():
    axes = {"x": {"unit_src": "", "scale": "log"}, "y": {"unit_src": "", "scale": "lin"}}
    assert patch(TEXT, {"xlim": [0.2578123, 257.8123]}, axes=axes).endswith("xlim: 0.2578 .. 257.8\n\nz = 1")
    with pytest.raises(PlotError, match="positive"):
        patch(TEXT, {"xlim": [-1, 5]}, axes=axes)


def test_the_writer_refuses_bad_input_and_changes_nothing():
    for bad in ({"xlim": [1, 1]}, {"xlim": [float("nan"), 2]}, {"bogus": "1"}, {"grid": "maybe"}, {"xlim": 5}):
        with pytest.raises(PlotError):
            patch(TEXT, bad)
    with pytest.raises(PlotError, match="not a plot"):
        patch(TEXT, {"grid": "off"}, line=4)


def test_series_options_are_written_with_their_number():
    out = patch(TEXT, {"color 2": "red", "dash": "dotted"})
    assert "  color 2: red" in out and "  dash: dotted" in out


def test_what_the_writer_wrote_draws_the_limits_it_was_given():
    for lo, hi in [(0.5, 3.2), (-1.5187, 31.8935), (1e-3, 2.5e-3), (12345.6, 98765.4)]:
        base = BEAM + "plot M(x), x = 0'm .. L\n  yunit: 'kN * 'm"
        p = plot(base)
        text = apply_patch(base, 4, {"ylim": [lo, hi]}, {"x": p["x"], "y": p["y"]}, p["inherited"])
        got = plot(text)["y"]["lim"]
        assert got[0] == pytest.approx(lo, rel=1e-3, abs=1e-3 * (hi - lo))
        assert got[1] == pytest.approx(hi, rel=1e-3, abs=1e-3 * (hi - lo))


def test_a_drag_round_trips_through_the_text_with_units():
    base = BEAM + "plot M(x), x = 0'm .. L\n  yunit: 'kN * 'm\n  xunit: 'mm"
    p = plot(base)
    text = apply_patch(base, 4, {"xlim": [1000.0, 3500.0]}, {"x": p["x"], "y": p["y"]}, p["inherited"])
    assert "xlim: 1000'mm .. 3500'mm" in text
    q = plot(text)
    assert q["x"]["lim"] == [1000, 3500] and q["series"][0]["x"][0] == 1000


# ---- the picture -----------------------------------------------------------------------

def test_ticks_are_nice_and_inside_the_limits():
    ax = {"lim": [0.0, 4.5], "scale": "lin", "step": None}
    assert [t["label"] for t in axis_ticks(ax)] == ["0", "1", "2", "3", "4"]
    ax = {"lim": [-0.832, 0.836], "scale": "lin", "step": None}
    assert [t["label"] for t in axis_ticks(ax)] == ["-0.5", "0", "0.5"]
    ax = {"lim": [0.01, 100.0], "scale": "log", "step": None}
    assert [t["power"] for t in axis_ticks(ax) if "power" in t] == [-2, -1, 0, 1, 2]
    assert len(axis_ticks({"lim": [0, 1], "scale": "lin", "step": 1e-9})) <= 21     # an absurd step is ignored


def test_the_svg_is_deterministic_and_escapes_text():
    src = "plot sin(x), x = 0 .. 6\n  title: <script>alert(1)</script> & \"q\"\n  xlabel: a_{b<c}"
    p = plot(src)
    svg = render_svg(p, uid=7)
    assert svg == render_svg(plot(src), uid=7)
    assert "<script" not in svg and "&lt;script&gt;" in svg and "&amp;" in svg
    assert 'id="lens-clip-7"' in svg and "url(#lens-clip-7)" in svg
    assert svg.count("<svg") == 1 and 'data-lens-plot="' in svg


def test_the_svg_carries_the_geometry_the_mouse_code_needs():
    svg = render_svg(plot("plot sin(x), x = 0 .. 6"))
    meta = re.search(r'data-lens-plot="([^"]*)"', svg).group(1).replace("&quot;", '"')
    m = json.loads(meta)
    L, T, W, H = m["box"]
    assert L > 0 and T > 0 and W > 100 and H > 100 and m["x"]["lim"] == [0, 6] and m["y"]["scale"] == "lin"


def test_standalone_svg_is_a_complete_file_with_the_font_and_no_page_hooks():
    svg = render_svg(plot("plot sin(x), x = 0 .. 6"), standalone=True)
    assert svg.startswith('<?xml version="1.0"') and "font/woff2" in svg and "data-lens-plot" not in svg
    xml.dom.minidom.parseString(svg)     # well formed


def test_every_style_option_reaches_the_picture():
    svg = render_svg(plot("plot x, 2*x, x = 0 .. 1\n  color 2: #ff0000\n  dash 2: dashed\n  marker 1: circle\n"
                          "  title: T\n  grid: off\n  legend: bottom left"))
    assert 'stroke="#ff0000"' in svg and 'stroke-dasharray="6 4"' in svg and "<circle" in svg
    assert 'class="pl-legend"' in svg and svg.count("<line vector-effect") == 0     # no grid lines


# ---- pgfplots ----------------------------------------------------------------------------

def test_pgfplots_carries_the_same_data_limits_and_labels():
    src = BEAM + "plot M(x), x = 0'm .. L\n  yunit: 'kN * 'm\n  title: Moment M_max\n  samples: 30"
    (r,) = plots(src, siunitx=True)
    tex = snippet(r)
    assert r"\begin{axis}" in tex and "xmin=0" in tex and "xmax=4.5" in tex
    assert r"xlabel={$x$ (\unit{\meter})}" in tex and r"ylabel={M(x) (\unit{\kilo\newton\meter})}" in tex
    assert r"title={Moment M\textsubscript{max}}" in tex
    assert tex.count("(") >= 30 and "coordinates" in tex


def test_pgfplots_breaks_lines_with_nan_and_handles_log_and_legend():
    (r,) = plots("plot 1/x, 2/x, x = -2 .. 2\n  ylim: -10 .. 10", siunitx=True)
    tex = snippet(r)
    assert ",nan)" in tex and r"\addlegendentry{1/x}" in tex and "legend pos=north east" in tex
    (r,) = plots("plot x, x = 1 .. 100\n  xscale: log\n  yscale: log", siunitx=True)
    tex = snippet(r)
    assert "xmode=log" in tex and "ymode=log" in tex


def test_the_document_loads_pgfplots_only_when_it_needs_it():
    ws = evaluate("plot x, x = 0 .. 1", siunitx=True)
    assert r"\usepackage{pgfplots}" in document(ws.results)
    assert "pgfplots" not in document(evaluate("a = 1", siunitx=True).results)


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex not installed")
def test_the_exported_document_compiles(tmp_path):
    src = (BEAM + "plot M(x), x = 0'm .. L\n  yunit: 'kN * 'm\n  title: Moment M_max\n  note: \"max\" at (L/2, M(L/2))\n"
           "plot sin(x), cos(x), x = 0 .. 2*pi\n  dash 2: dashed\n  xstep: 1\n"
           "plot sin(x)/x, x = 0.01 .. 100\n  xscale: log\n  xlabel: f_c (Hz)\n"
           "plot 1/x, x = -2 .. 2\n  ylim: -10 .. 10\n  marker: square\n  samples: 40\n")
    ws = evaluate(src, siunitx=True)
    (tmp_path / "a.tex").write_text(document(ws.results, title="t", declarations=ws.declarations), encoding="utf-8")
    r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "a.tex"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-1500:]
    assert (tmp_path / "a.pdf").exists()


# ---- around the plot -----------------------------------------------------------------------

def test_rename_follows_a_name_into_a_plot_but_not_into_its_text():
    src = "k = 2\nplot k*x, x = 0 .. 1\n  title: k and x\n  ylabel: k\n  ylim: 0 .. k * 3\n  note: \"k\" at (k, k)\n"
    out, count = rename(src, "k", "gain")
    assert "plot gain*x" in out and "ylim: 0 .. gain * 3" in out and 'note: "k" at (gain, gain)' in out
    assert "title: k and x" in out and "ylabel: k" in out and out.startswith("gain = 2")
    assert count == 5
    out, _ = rename(src, "x", "t")
    assert "plot k*t, t = 0 .. 1" in out
    with pytest.raises(RenameError, match="does not appear"):
        rename("plot x, x = 0 .. 1", "plot", "p")        # `plot` is not a name in a plot statement


def test_units_a_plot_depends_on_travel_with_the_saved_sheet():
    ws = evaluate("plot x * 1'smoot, x = 0 .. 2\n  yunit: 'smoot", global_units=[("smoot", "1.7018'm")])
    assert ws.needed == [("smoot", "1.7018'm")] and "'smoot = 1.7018'm" in ws.portable_text()
    assert ws.results[0].kind == "plot"


def test_plot_command_is_a_comment_in_the_tex():
    ws = evaluate("!plot grid: off\nplot x, x = 0 .. 1", siunitx=True)
    assert "% !plot grid: off" in document(ws.results)


# ---- the server and the command line ---------------------------------------------------------

@pytest.fixture(autouse=True)
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("LENS_CONFIG_DIR", str(tmp_path / "cfg"))


def test_plot_rows_reach_the_page_with_their_picture():
    rows = server.evaluate(server.Sheet(text="plot sin(x), x = 0 .. 6\n  title: T"))
    assert [r["kind"] for r in rows] == ["plot", "plotopt"]
    assert rows[0]["svg"].startswith("<svg") and rows[0]["plot"]["title"] == "T" and rows[0]["end"] == 2
    assert all(isinstance(v, (int, float)) or v is None for v in rows[0]["plot"]["series"][0]["y"])


def test_plot_edit_endpoint_returns_new_text_and_refuses_what_it_cannot_do():
    text = BEAM + "plot M(x), x = 0'm .. L\n  yunit: 'kN * 'm\n"
    ok = server.plot_edit(server.PlotEditBody(text=text, line=4, patch={"xlim": [0.5, 3.2], "grid": "off"}))
    assert ok["ok"] and "xlim: 0.5'm .. 3.2'm" in ok["text"] and "grid: off" in ok["text"]
    assert server.plot_edit(server.PlotEditBody(text=text, line=1, patch={"grid": "off"}))["ok"] is False
    bad = server.plot_edit(server.PlotEditBody(text=text, line=4, patch={"xlim": [2, 2]}))
    assert bad["ok"] is False and "different" in bad["error"]
    # a plot that fails to draw cannot be edited from the picture
    assert server.plot_edit(server.PlotEditBody(text="plot q(x), x = 0 .. 1", line=1, patch={}))["ok"] is False


def test_plot_edit_elides_defaults_chosen_by_a_plot_command():
    text = "!plot grid: off\nplot x, x = 0 .. 1\n  grid: on\n"
    out = server.plot_edit(server.PlotEditBody(text=text, line=2, patch={"grid": "off"}))
    assert out["ok"] and "grid" not in out["text"].split("\n", 2)[2]


def test_plot_image_endpoint_serves_a_standalone_svg():
    r = server.plot_image(server.PlotImageBody(text="plot sin(x), x = 0 .. 6", line=1))
    assert r.media_type == "image/svg+xml" and b"font/woff2" in r.body
    with pytest.raises(HTTPException):
        server.plot_image(server.PlotImageBody(text="a = 1", line=1))


def test_command_line_writes_one_svg_per_plot(tmp_path, monkeypatch, capsys):
    from laconic.__main__ import main
    (tmp_path / "s.lens").write_text("plot x, x = 0 .. 1\n\nplot 2*x, x = 0 .. 1\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["lens", str(tmp_path / "s.lens"), "--plots", str(tmp_path / "out")])
    main()
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["s-line1.svg", "s-line3.svg"]
    assert (tmp_path / "out" / "s-line1.svg").read_text().startswith("<?xml")


def test_the_same_worksheet_draws_the_same_picture_twice():
    src = BEAM + "plot M(x), x = 0'm .. L\n  title: T\n  xlim: 1'm .. 4'm\n"
    a, b = plots(src)[0], plots(src)[0]
    assert a.svg == b.svg and a.plot == b.plot and math.isfinite(a.plot["y"]["lim"][0])
