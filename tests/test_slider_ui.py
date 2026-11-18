"""!slider in the real page (Chromium, through Playwright): dragging the slider rewrites the header's
number, the lines below follow while it moves, and one Ctrl+Z undoes a whole drag. Skipped when
Playwright or a browser is not available, like test_ui.py."""
import pytest

pytest.importorskip("playwright.sync_api")
from uihelpers import reset, value  # noqa: E402

SHEET = "!slider L = 2'm\n  range: 0'm .. 10'm\n  step: 0.5'm\nA = 3*L\n"
SLIDER = ".row[data-line='1'] .slider input[type=range]"
BELOW = ".row[data-line='4'] .body"


def show(page, text):
    reset(page, text)
    page.evaluate("document.querySelector('#src').dispatchEvent(new Event('input'))")
    page.wait_for_selector(SLIDER)
    page.wait_for_timeout(150)


def header(page):
    return value(page).split("\n")[0]


def at(page, fraction):
    """Where the slider's thumb stands at `fraction` of its travel, in page coordinates."""
    box = page.locator(SLIDER).bounding_box()
    thumb = 16   # Chromium's thumb is about this wide; the travel is the width less one thumb
    return box["x"] + thumb / 2 + fraction * (box["width"] - thumb), box["y"] + box["height"] / 2


def test_a_slider_row_shows_the_assignment_and_the_range(page):
    show(page, SHEET)
    row = page.locator(".row[data-line='1']")
    assert "slider" in row.get_attribute("class")
    assert "L=2m" in row.locator(".math").text_content() and "!slider L = 2'm" in row.locator(".cmd").inner_text()
    assert row.locator(".slider-end").all_inner_texts() == ["0 m", "10 m"]
    s = page.locator(SLIDER)
    assert (s.get_attribute("max"), s.input_value()) == ("20", "4")   # one position per step; 2 m is the 4th
    assert "=6m" in page.text_content(BELOW)
    assert page.locator(".row[data-line='2'], .row[data-line='3']").count() == 0   # options show in the header's row


def test_dragging_the_slider_rewrites_the_header_and_the_lines_below_follow(page):
    show(page, SHEET)
    x, y = at(page, 0.2)
    page.mouse.move(x, y)
    page.mouse.down()
    for k in range(1, 11):   # to the middle, a step at a time
        page.mouse.move(*at(page, 0.2 + 0.03 * k))
    # the drag is still on, and the sheet has followed it
    page.wait_for_function("document.querySelector('#src').value.startsWith(\"!slider L = 5'm\")")
    page.wait_for_function(f"document.querySelector(\"{BELOW}\").textContent.includes('=15m')")
    assert page.evaluate(f"document.activeElement === document.querySelector(\"{SLIDER}\")"), "the drag kept its slider"
    page.mouse.move(*at(page, 0.8))
    page.mouse.up()
    page.wait_for_function("document.querySelector('#src').value.startsWith(\"!slider L = 8'm\")")
    page.wait_for_function(f"document.querySelector(\"{BELOW}\").textContent.includes('=24m')")
    assert value(page) == SHEET.replace("2'm", "8'm", 1)
    # one Ctrl+Z in the editor undoes the whole drag
    page.focus("#src")
    page.keyboard.press("Control+z")
    page.wait_for_function("document.querySelector('#src').value.startsWith(\"!slider L = 2'm\")")
    assert value(page) == SHEET
    page.wait_for_function(f"document.querySelector(\"{BELOW}\").textContent.includes('=6m')")
    page.keyboard.press("Control+Shift+z")
    page.wait_for_function("document.querySelector('#src').value.startsWith(\"!slider L = 8'm\")")


def test_the_keys_move_the_slider_a_step_at_a_time(page):
    show(page, SHEET)
    page.focus(SLIDER)
    page.keyboard.press("ArrowRight")
    page.wait_for_function("document.querySelector('#src').value.startsWith(\"!slider L = 2.5'm\")")
    page.wait_for_function(f"document.querySelector(\"{BELOW}\").textContent.includes('=7.5m')")
    page.keyboard.press("ArrowRight")    # the slider kept the focus through the redraw
    page.wait_for_function("document.querySelector('#src').value.startsWith(\"!slider L = 3'm\")")
    page.keyboard.press("End")
    page.wait_for_function("document.querySelector('#src').value.startsWith(\"!slider L = 10'm\")")
    page.wait_for_function(f"document.querySelector(\"{BELOW}\").textContent.includes('=30m')")


def test_a_value_outside_the_range_is_kept_with_a_warning(page):
    show(page, SHEET.replace("2'm", "12'm"))
    row = page.locator(".row[data-line='1']")
    assert "outside the slider's range" in row.locator(".g-warn").inner_text()
    assert page.locator(SLIDER).input_value() == "20"
    assert "=36m" in page.text_content(BELOW)


def test_a_bad_option_is_an_error_on_its_line(page):
    reset(page, "!slider L = 2'm\n  range: 0's .. 10's\nA = 3*L\n")
    page.evaluate("document.querySelector('#src').dispatchEvent(new Event('input'))")
    page.wait_for_selector(".row.error[data-line='2']")
    assert "units of L" in page.inner_text(".row.error[data-line='2']")
    assert page.locator(SLIDER).count() == 0
