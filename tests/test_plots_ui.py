"""The mouse side of plots, driven in the real page (Chromium, through Playwright) with real
pointer events. Skipped when Playwright or a browser is not available, like test_ui.py."""
import re
import struct

import pytest

pytest.importorskip("playwright.sync_api")
from uihelpers import reset, value  # noqa: E402

SRC = "!plot sin(x), x = 0 .. 10\n"
VIEWS = re.compile(r"^\s+([xy])view: (\S+) \.\. (\S+)$", re.M)


def show(page, text=SRC):
    page.evaluate("t => { const s = document.querySelector('#src'); s.value = t; s.dispatchEvent(new Event('input')); }", text)
    page.wait_for_selector(".pl-area")
    page.wait_for_timeout(250)     # the page re-evaluates 120 ms after an edit


def views(page):
    return {m.group(1): (float(m.group(2)), float(m.group(3))) for m in VIEWS.finditer(value(page))}


def box(page, name="pl-area"):
    return page.locator("." + name).bounding_box()


def center(b):
    return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2


def drag(page, b, dx, dy, at=None):
    x, y = at or center(b)
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx / 2, y + dy / 2, steps=4)
    page.mouse.move(x + dx, y + dy, steps=4)
    page.mouse.up()
    page.wait_for_timeout(500)


def ctrl_wheel(page, delta):
    page.keyboard.down("Control")
    page.mouse.wheel(0, delta)
    page.keyboard.up("Control")
    page.wait_for_timeout(800)     # d3 reports the end of a wheel gesture after it goes quiet


def test_a_plot_is_drawn_with_its_option_lines_folded_in(page):
    show(page, SRC + "  title: Sine\n  grid: off\n")
    assert page.locator(".row.plot").count() == 1
    assert page.locator(".row.plotopt").count() == 0 and page.locator(".row.error").count() == 0
    assert page.locator(".plot-wrap svg.lens-plot").count() == 1 and page.get_by_role("button", name="PNG").is_visible()


def test_dragging_pans_and_writes_the_view_into_the_editor(page):
    show(page)
    b = box(page)
    drag(page, b, -b["width"] / 10, 0)                 # a tenth of the width to the left
    x = views(page)["x"]
    assert x[0] == pytest.approx(1.0, abs=0.05) and x[1] == pytest.approx(11.0, abs=0.05)
    assert "y" not in views(page)                       # only what moved is written
    # the picture was redrawn from the text, not left as a moved copy
    assert page.evaluate("document.querySelector('.pl-view').getAttribute('transform')") is None
    assert page.locator(".plot-tools button", has_text="Reset view").count() == 1


def test_the_picture_follows_the_pointer_during_a_drag(page):
    show(page)
    b = box(page)
    x, y = center(b)
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x - 80, y - 20, steps=6)
    transform = page.evaluate("document.querySelector('.pl-view').getAttribute('transform')")
    nums = [float(v) for v in re.findall(r"-?[\d.]+", transform)]
    assert nums[4] == pytest.approx(-80, abs=1) and nums[5] == pytest.approx(-20, abs=1)    # a pure translation
    assert page.evaluate("getComputedStyle(document.querySelector('.pl-grid')).opacity") == "0"
    assert "view" not in value(page)                     # nothing is written until the gesture ends
    page.mouse.up()
    page.wait_for_timeout(500)
    assert "xview" in value(page)
    assert page.evaluate("getComputedStyle(document.querySelector('.pl-grid')).opacity") == "1"


def test_ctrl_z_undoes_a_pan(page):
    show(page)
    drag(page, box(page), -60, 0)
    assert "xview" in value(page)
    page.keyboard.press("Control+z")
    page.wait_for_timeout(400)
    assert "view" not in value(page)


def test_ctrl_wheel_zooms_about_the_pointer_and_a_plain_wheel_does_not(page):
    show(page)
    b = box(page)
    x, y = center(b)
    page.mouse.move(x, y)
    page.mouse.wheel(0, -300)
    page.wait_for_timeout(500)
    assert "view" not in value(page)                     # the results stay free to scroll
    ctrl_wheel(page, -100)                              # one notch
    lo, hi = views(page)["x"]
    assert (hi - lo) == pytest.approx(10 / 1.32, rel=0.03)
    assert (lo + hi) / 2 == pytest.approx(5, abs=0.15)  # centred on the pointer, which is mid-plot
    ctrl_wheel(page, 100)
    assert "view" in value(page)


def test_zoom_keeps_the_curve_smooth(page):
    show(page, "!plot sin(x), x = 0 .. 100\n  xlim: 10 .. 10.5\n  samples: 50\n")
    pts = page.evaluate("document.querySelector('.pl-view path').getAttribute('d').split('L').length")
    assert pts >= 50


def test_the_axis_strips_move_only_their_axis(page):
    show(page)
    xs = box(page, "pl-xaxis")
    drag(page, xs, -50, 0, at=(xs["x"] + xs["width"] / 2, xs["y"] + 8))
    assert set(views(page)) == {"x"}
    ys = box(page, "pl-yaxis")
    drag(page, ys, 0, 30, at=(ys["x"] + ys["width"] / 2, ys["y"] + ys["height"] / 2))
    assert set(views(page)) == {"x", "y"}
    ys = box(page, "pl-yaxis")
    page.mouse.dblclick(ys["x"] + 10, ys["y"] + ys["height"] / 2)
    page.wait_for_timeout(500)
    assert set(views(page)) == {"x"}                     # a double-click on one strip resets just that axis


def test_double_click_and_the_reset_button_remove_the_mouse_view(page):
    show(page)
    drag(page, box(page), -60, 15)
    assert set(views(page)) == {"x", "y"}
    b = box(page)
    page.mouse.dblclick(b["x"] + 40, b["y"] + 40)
    page.wait_for_timeout(500)
    assert "view" not in value(page)
    drag(page, box(page), 40, 0)
    page.get_by_role("button", name="Reset view").click()
    page.wait_for_timeout(500)
    assert "view" not in value(page)


def test_a_log_axis_is_panned_in_log_space(page):
    show(page, "!plot 1/x^2, x = 0.1 .. 100\n  xscale: log\n  yscale: log\n")
    b = box(page)
    drag(page, b, -b["width"] / 3, 0)                   # a third of the width, which is a third of the decades
    lo, hi = views(page)["x"]
    assert hi / lo == pytest.approx(1000, rel=0.02)     # the span in decades is unchanged
    assert lo == pytest.approx(0.1 * 10, rel=0.05)      # and it moved one decade


def test_hover_reads_off_the_nearest_point(page):
    show(page, "!plot sin(x), x = 0 .. 10\n  yunit: 'rad\n")
    b = box(page)
    page.mouse.move(b["x"] + b["width"] * 0.157, b["y"] + b["height"] / 2)
    page.mouse.move(b["x"] + b["width"] * 0.1571, b["y"] + b["height"] / 2)
    page.wait_for_timeout(100)
    text = page.evaluate("document.querySelector('.pl-hover text').textContent")
    m = re.match(r"x = ([\d.]+),  y = ([\d.-]+)", text)
    assert m and float(m.group(1)) == pytest.approx(1.57, abs=0.1) and float(m.group(2)) == pytest.approx(1, abs=0.01)
    page.mouse.move(5, 5)
    assert page.evaluate("getComputedStyle(document.querySelector('.pl-hover')).display") == "none"


def test_a_refused_edit_puts_the_picture_back(page):
    show(page)
    page.route("**/api/plotedit", lambda route: route.fulfill(json={"ok": False, "error": "nope"}))
    drag(page, box(page), -60, 0)
    assert "view" not in value(page)
    assert page.evaluate("document.querySelector('.pl-view').getAttribute('transform')") is None
    assert "nope" in page.inner_text("#status")


def test_svg_and_png_downloads_are_the_picture_as_shown(page):
    show(page, SRC + "  title: Sine\n")
    with page.expect_download() as d:
        page.get_by_role("button", name="SVG").click()
    svg = open(d.value.path(), encoding="utf-8").read()
    assert d.value.suggested_filename.endswith(".svg") and svg.startswith("<?xml") and "Sine" in svg and "font/woff2" in svg
    with page.expect_download() as d:
        page.get_by_role("button", name="PNG").click()
    png = open(d.value.path(), "rb").read()
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", png[16:24]) == (520 * 3, 320 * 3)


def test_math_keys_leave_the_text_of_a_title_alone(page):
    reset(page, "!plot sin(x), x = 0 .. 10\n  title: ")
    page.keyboard.type("M/EI")
    assert value(page).endswith("title: M/EI")
    page.keyboard.press("Enter")
    page.keyboard.type("  xlim: a/")
    assert value(page).endswith("xlim: a/()") or value(page).endswith("xlim: a / ()")     # math keys still work in a limit


def test_clicking_the_picture_does_not_jump_the_editor_but_the_row_does(page):
    show(page, "a = 1\n" + SRC + "  title: T\n")
    page.evaluate("document.querySelector('#src').setSelectionRange(0, 0)")
    page.locator(".plot-wrap svg").click(position={"x": 5, "y": 5})
    assert page.evaluate("document.querySelector('#src').selectionStart") == 0
    page.locator(".row.plot .no").click()
    assert page.evaluate("document.querySelector('#src').selectionStart") > 0


def test_dragging_a_plot_makes_it_the_focused_line(page):
    """The page keeps the focused line's row in view; a pan must not scroll back to the old caret (#83)."""
    show(page, SRC + "".join(f"a{i} = {i}\n" for i in range(60)))
    page.evaluate("const s = document.querySelector('#src'); s.setSelectionRange(s.value.length - 1, s.value.length - 1)")
    page.evaluate("document.querySelector('#src').dispatchEvent(new Event('keyup'))")    # the last row is focused
    assert page.evaluate("document.querySelector('#out').scrollTop") > 0
    page.locator(".row.plot").scroll_into_view_if_needed()
    b = box(page)
    drag(page, b, -b["width"] / 10, 0)
    assert "x" in views(page)
    assert page.evaluate("document.querySelector('#src').value.slice(0, document.querySelector('#src').selectionStart).split('\\n').length") == 1
    assert "active" in page.locator(".row.plot").get_attribute("class")
    assert page.locator(".row.plot").evaluate(
        "r => { const a = r.getBoundingClientRect(), o = r.closest('#out').getBoundingClientRect(); return a.bottom > o.top && a.top < o.bottom; }")


def test_the_caret_on_an_option_line_marks_the_plot_row(page):
    show(page, SRC + "  title: T\n  grid: off\n")
    page.evaluate("document.querySelector('#src').setSelectionRange(document.querySelector('#src').value.length - 3, document.querySelector('#src').value.length - 3)")
    page.evaluate("document.querySelector('#src').dispatchEvent(new Event('keyup'))")
    assert "active" in page.locator(".row.plot").get_attribute("class")


def test_reset_goes_back_to_the_authors_limits_not_to_automatic(page):
    """The default view is whatever the text says without an xview/yview line: the author's xlim and
    ylim if there are any, else automatic. Nothing else is stored, and the mouse never touches those."""
    show(page, SRC + "  xlim: 2 .. 8\n  ylim: -3 .. 3\n")
    assert page.locator(".plot-tools button", has_text="Reset view").count() == 0      # nothing for the mouse to undo
    drag(page, box(page), -60, 20)
    assert set(views(page)) == {"x", "y"} and "xlim: 2 .. 8" in value(page) and "ylim: -3 .. 3" in value(page)
    b = box(page)
    page.mouse.dblclick(b["x"] + 40, b["y"] + 40)
    page.wait_for_timeout(500)
    assert "view" not in value(page) and "xlim: 2 .. 8" in value(page) and "ylim: -3 .. 3" in value(page)
    first = page.evaluate("[...document.querySelectorAll('.pl-xaxis ~ g text, svg text')].map(t => t.textContent).join(' ')")
    assert page.locator(".plot-tools button", has_text="Reset view").count() == 0
    assert "2" in first and "8" in first


def y_label_chars(page):
    return page.evaluate("Math.max(...[...document.querySelectorAll('svg.lens-plot text[text-anchor=end]')].map(t => t.textContent.length))")


def test_the_frame_does_not_move_when_the_y_numbers_change_width(page):
    """Zoom on the y axis with the pointer left where it is. The numbers go from '-1e5' down through
    '-0.4' and back; while they fit the six-character budget the strip must stay under the pointer."""
    show(page, "!plot 100000*sin(x), x = 0 .. 10\n")
    first = box(page)
    ys = box(page, "pl-yaxis")
    px, py = ys["x"] + ys["width"] / 2, ys["y"] + ys["height"] / 2
    page.mouse.move(px, py)
    seen = set()
    for delta in (-1500, -1500, -1500, 2500, 2500, 2500, 2500):         # in by 64x three times, then back out
        page.keyboard.down("Control")
        page.mouse.wheel(0, delta)
        page.keyboard.up("Control")
        page.wait_for_timeout(900)
        chars = y_label_chars(page)
        seen.add(chars)
        assert chars <= 6, f"this walk is meant to stay inside the budget, but a label has {chars} characters"
        assert box(page) == first, f"the plot area moved after wheel {delta}"
        under = page.evaluate("([x, y]) => document.elementFromPoint(x, y).getAttribute('class') || ''", [px, py])
        assert "pl-yaxis" in under, f"the pointer left the y axis strip after wheel {delta} (over '{under}')"
    assert len(seen) > 2                                                  # the labels really did change width
    assert set(views(page)) == {"y"}                                      # only the y axis was ever touched


def test_wider_labels_grow_the_margin_without_colliding_or_leaving_the_picture(page):
    show(page, "!plot sin(x), x = 0 .. 10\n")
    floor = box(page)
    show(page, "!plot sin(x), x = 0 .. 10\n  yview: 1.0000001e9 .. 1.0000005e9\n")
    grown = box(page)
    assert y_label_chars(page) > 6 and grown["x"] > floor["x"] + 20 and grown["width"] > 150
    rects = page.evaluate("""() => {
        const sv = document.querySelector('svg.lens-plot').getBoundingClientRect();
        const r = (t) => { const b = t.getBoundingClientRect(); return [b.left - sv.left, b.right - sv.left]; };
        return {ticks: [...document.querySelectorAll('svg.lens-plot text[text-anchor=end]')].map(r),
                label: r(document.querySelector('svg.lens-plot text[transform]'))};
    }""")
    assert all(lo >= 0 for lo, _ in rects["ticks"])                       # inside the picture
    assert all(lo >= rects["label"][1] for lo, _ in rects["ticks"])       # and clear of the y label


def test_tick_labels_stay_inside_the_picture_at_scientific_scales(page):
    show(page, "!plot sin(x), x = 0 .. 10\n  yview: -1.234e-10 .. 5.6e-11\n  xview: -4.5e17 .. 6e17\n")
    width = page.evaluate("Number(document.querySelector('svg.lens-plot').getAttribute('width'))")
    inside = page.evaluate("""() => [...document.querySelectorAll('svg.lens-plot text:not(.pl-hover text)')].every((t) => {
        const b = t.getBoundingClientRect(), s = document.querySelector('svg.lens-plot').getBoundingClientRect();
        return b.left >= s.left - 0.5 && b.right <= s.right + 0.5;
    })""")
    assert inside and width > 0


def labels(page):
    page.wait_for_selector("#ac:not([hidden])")
    return page.eval_on_selector_all("#ac .ac-item .lbl", "els => els.map(e => e.textContent)")


def test_typing_plot_options_indents_and_suggests_keys_and_values(page):
    """#137: a plot's option lines are typed as a solver's are, with its own keys and values."""
    reset(page, "!plot sin(x), x = 1 .. 10")
    page.keyboard.press("Enter")
    page.keyboard.type("co")
    assert labels(page) == ["color"]
    page.keyboard.press("Tab")
    page.keyboard.type("re")
    assert labels(page) == ["red"]
    page.keyboard.press("Tab")
    page.keyboard.press("Enter")
    page.keyboard.press("Control+Space")                  # every key, in the table's order
    assert labels(page)[:3] == ["title", "xlabel", "ylabel"]
    page.keyboard.type("xs")
    assert labels(page) == ["xscale", "xstep"]
    page.keyboard.press("Tab")
    page.keyboard.press("Control+Space")
    assert labels(page) == ["lin", "log"]
    page.keyboard.type("lo")
    page.keyboard.press("Tab")
    assert value(page) == "!plot sin(x), x = 1 .. 10\n  color: red\n  xscale: log"
    page.wait_for_selector(".pl-area")
    page.wait_for_timeout(250)
    assert not page.query_selector(".row.error") and "#d55e00" in page.inner_html(".plot-wrap")   # drawn in red
