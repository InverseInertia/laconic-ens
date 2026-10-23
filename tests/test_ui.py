"""Drives the real page in Chromium (Playwright). Skipped when Playwright or a
browser is not available."""
import pytest

pytest.importorskip("playwright.sync_api")
from uihelpers import reset, value  # noqa: E402


def select(page, a, b):
    page.evaluate("([a, b]) => document.querySelector('#src').setSelectionRange(a, b)", [a, b])


def test_unit_suggestions_and_tab_accept(page):
    reset(page, "w = 12")
    page.keyboard.type("'kN")
    page.wait_for_selector("#ac:not([hidden])")
    assert "kN" in page.inner_text("#ac")
    page.keyboard.type(" ")
    page.wait_for_selector("#ac", state="hidden")
    reset(page, "x = 5")
    page.keyboard.type("'kil")
    page.wait_for_selector("#ac:not([hidden])")
    page.keyboard.press("Tab")
    assert value(page).startswith("x = 5'k")


def test_enter_ends_the_line_unless_you_chose(page):
    reset(page, "delta_max = 3\nx = ")
    page.keyboard.type("delt")
    page.wait_for_selector("#ac:not([hidden])")
    page.keyboard.press("Enter")
    assert value(page) == "delta_max = 3\nx = delt\n"
    reset(page, "delta_max = 3\nx = ")
    page.keyboard.type("delt")
    page.wait_for_selector("#ac:not([hidden])")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    assert value(page) == "delta_max = 3\nx = delta_max"


def test_function_suggestion_puts_the_caret_inside_brackets(page):
    reset(page, "x = ")
    page.keyboard.type("sqr")
    page.wait_for_selector("#ac:not([hidden])")
    page.keyboard.press("Tab")
    assert value(page) == "x = sqrt()"
    assert page.evaluate("document.querySelector('#src').selectionStart") == len("x = sqrt(")


def test_highlight_then_fraction_and_brackets(page):
    reset(page, "x = a+b")
    select(page, 4, 7)
    page.keyboard.type("/")
    assert value(page) == "x = (a+b) / ()"
    reset(page, "x = 12'kN + a")
    select(page, 5, 6)           # the "2": snaps to the whole quantity
    page.keyboard.type("(")
    assert value(page) == "x = (12'kN) + a"


def test_ctrl_space_wraps_the_selection_in_a_function(page):
    reset(page, "x = a+b")
    select(page, 4, 7)
    page.keyboard.press("Control+Space")
    page.wait_for_selector("#ac:not([hidden])")
    page.keyboard.type("sin")
    page.keyboard.press("Enter")
    assert value(page) == "x = sin(a+b)"


def test_alt_up_grows_and_alt_down_shrinks(page):
    reset(page, "M = w * L^2 / 8 + c")
    select(page, 9, 9)
    sel = lambda: page.evaluate("document.querySelector('#src').value.slice(document.querySelector('#src').selectionStart, document.querySelector('#src').selectionEnd)")
    page.keyboard.press("Alt+ArrowUp")
    assert sel() == "L^2"
    page.keyboard.press("Alt+ArrowUp")
    assert sel() == "w * L^2 / 8"
    page.keyboard.press("Alt+ArrowDown")
    assert sel() == "L^2"


def test_double_click_selects_the_whole_quantity(page):
    reset(page, "x = 12'kN + a")
    box = page.evaluate("(() => { const r = document.querySelector('#src').getBoundingClientRect(); return [r.left, r.top]; })()")
    # 14px OCR-A, 10px per character (0.715em), 16px padding, 28px rows, 12px top padding
    page.mouse.dblclick(box[0] + 16 + 10 * 5.5, box[1] + 12 + 14)
    assert page.evaluate("document.querySelector('#src').value.slice(document.querySelector('#src').selectionStart, document.querySelector('#src').selectionEnd)") == "12'kN"


def test_global_units_and_server_side_greek(page, server):
    page.click("#settingsBtn")
    page.click("#unitAdd")
    inputs = page.locator("#unitRows .u-row input")
    inputs.nth(0).fill("smoot")
    inputs.nth(1).fill("1.7018'm")
    page.click("#unitSave")
    page.wait_for_selector("#status:has-text('Saved 1 global unit')")
    page.click("#settingsDlg .close")
    reset(page, "L = 3'smoot -> 'm")
    page.keyboard.type("\n")
    page.wait_for_function("document.querySelector('#out').innerText.includes('5.105')")
    # saving carries the definition along
    text = page.evaluate("async () => (await (await fetch('/api/save', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text: \"L = 3'smoot\"})})).text())")
    assert "'smoot = 1.7018'm" in text
    # the Greek table is stored on the server
    page.click("#settingsBtn")
    page.click("#greekAdd")
    ins = page.locator("#greekRows .g-row").last.locator("input")
    ins.nth(0).fill("j")
    ins.nth(1).fill("ϑ")
    page.wait_for_timeout(600)
    cfg = page.evaluate("async () => (await (await fetch('/api/settings')).json())")
    assert cfg["greek"]["j"] == "ϑ" and cfg["units"][0]["name"] == "smoot"


def test_f2_renames_the_name_at_the_caret(page):
    reset(page, "L = 4.5'm\nA = L * 2")
    select(page, 1, 1)
    page.keyboard.press("F2")
    page.wait_for_selector("#renameDlg[open]")
    assert page.input_value("#renameOld") == "L"
    page.fill("#renameNew", "span")
    page.keyboard.press("Enter")
    page.wait_for_selector("#renameDlg", state="hidden")
    assert value(page) == "span = 4.5'm\nA = span * 2"


def test_alt_z_toggles_wrapping(page):
    reset(page, "x = 1")
    assert not page.evaluate("document.querySelector('#src').classList.contains('wrapped')")
    page.keyboard.press("Alt+z")
    assert page.evaluate("getComputedStyle(document.querySelector('#src')).whiteSpace") == "pre-wrap"
    page.reload()
    page.wait_for_function("document.querySelector('#src').value.length > 0")
    assert page.evaluate("document.querySelector('#src').classList.contains('wrapped')")
    page.focus("#src")
    page.keyboard.press("Alt+z")
    assert page.evaluate("getComputedStyle(document.querySelector('#src')).whiteSpace") == "pre"
    assert value(page)  # the key never types a character


def test_split_can_be_dragged(page):
    box = page.locator("#split").bounding_box()
    before = page.locator("#src").bounding_box()["width"]
    y = box["y"] + 100
    page.mouse.move(box["x"] + box["width"] / 2, y)
    page.mouse.down()
    page.mouse.move(box["x"] + 200, y, steps=5)
    page.mouse.up()
    after = page.locator("#src").bounding_box()["width"]
    assert after > before + 150
    page.reload()
    page.wait_for_function("document.querySelector('#src').value.length > 0")
    assert abs(page.locator("#src").bounding_box()["width"] - after) < 2
    page.locator("#split").dblclick()
    assert abs(page.locator("#src").bounding_box()["width"] - before) < 2


def test_theme_settings(page):
    page.click("#settingsBtn")
    page.wait_for_selector("#settingsDlg[open]")
    page.select_option("#preset", "Dark")
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(30, 33, 39)"
    page.select_option("#bgStyle", "plain")
    assert page.evaluate("getComputedStyle(document.querySelector('#src')).backgroundImage") == "none"
    page.select_option("#fontMono", "3")
    assert "Courier" in page.evaluate("getComputedStyle(document.querySelector('#src')).fontFamily")
    page.reload()
    page.wait_for_function("document.querySelector('#src').value.length > 0")
    assert page.evaluate("document.documentElement.dataset.bg") == "plain"
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(30, 33, 39)"
    page.click("#settingsBtn")
    page.click("#themeReset")
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(0, 56, 107)"


PASTE = """
(t) => { const s = document.querySelector('#src'); const dt = new DataTransfer(); dt.setData('text/plain', t);
  s.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true})); }
"""


def test_pasted_table_becomes_matrix(page):
    reset(page, "x = 1\n")
    page.evaluate(PASTE, "| 110      | 174            | 107,000         |\n| -------- | -------------- | --------------- |\n| 110      | 184            | 67,000          |\n")
    assert value(page) == "x = 1\nA = [110, 174, 107000; 110, 184, 67000]"
    reset(page, "# note ")
    page.evaluate(PASTE, "1\t2\n3\t4")
    assert value(page) == "# note "


def test_help_dialog_opens_and_links_to_keys(page):
    page.click("#helpBtn")
    page.wait_for_selector("#helpDlg[open]")
    assert "Welcome to LENS" in page.inner_text("#helpTitle")
    page.click("#helpKeys")
    page.wait_for_selector("#keysDlg[open]")
    page.click("#keysDlg .close")
    page.click("#helpDlg .close")
    page.wait_for_selector("#helpDlg", state="hidden")
    page.keyboard.press("F1")
    page.wait_for_selector("#helpDlg[open]")
