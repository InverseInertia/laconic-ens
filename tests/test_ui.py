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
    page.keyboard.press("Control+z")                     # one step takes the whole rename back
    assert value(page) == "L = 4.5'm\nA = L * 2"


def test_server_edits_for_a_text_that_has_changed_are_not_made(page):
    reset(page, "x = 1")
    assert page.evaluate("applyEdits('x = 2', [{from: 4, to: 5, insert: '3'}])") is False
    assert value(page) == "x = 1"
    assert page.evaluate("applyEdits('x = 1', [{from: 4, to: 5, insert: '3'}])") is True
    assert value(page) == "x = 3"


@pytest.mark.parametrize("text,caret,name", [
    ("σ_max = 3", 2, "σ_max"),          # the page reads names with the server's lexer, Greek included
    ("p = 5'%", 7, "'%"),
    ("F = 12'kN", 6, "'kN"),             # between the number and its unit, the unit is the name
    ('t = "L"', 6, ""),                  # text is not a name
])
def test_f2_reads_the_name_at_the_caret_like_the_server(page, text, caret, name):
    reset(page, text)
    select(page, caret, caret)
    page.keyboard.press("F2")
    page.wait_for_selector("#renameDlg[open]")
    assert page.input_value("#renameOld") == name
    page.keyboard.press("Escape")


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


def test_version_is_shown_next_to_the_title_and_in_help(page):
    from laconic._version import label
    assert page.inner_text("#version") == label()
    page.click("#helpBtn")
    page.wait_for_selector("#helpDlg[open]")
    assert page.inner_text("#helpVersion").startswith(f"LENS {label()} ")
    assert page.get_attribute("#helpVersion a", "href").endswith("/releases")
    page.click("#helpDlg .close")
    # On a phone the header drops it to keep the toolbar room; Help still has it.
    page.set_viewport_size({"width": 400, "height": 800})
    assert not page.is_visible("#version")
    page.set_viewport_size({"width": 1200, "height": 800})
    assert page.is_visible("#version")


def test_help_shows_on_first_open_only(page, server):
    import json
    from laconic import settings
    path = settings.config_dir() / "settings.json"
    data = json.loads(path.read_text()); data["welcomed"] = False; path.write_text(json.dumps(data))
    page.reload()
    page.wait_for_selector("#helpDlg[open]")
    assert page.is_visible("#helpLogo svg, #helpLogo img")
    assert page.get_attribute("a.wiki >> nth=0", "href").startswith("https://github.com/inverseinertia/laconic-ens/wiki")
    page.reload()
    page.wait_for_function("document.querySelector('#src').value.length > 0")
    page.wait_for_timeout(300)
    assert not page.evaluate("document.querySelector('#helpDlg').open")


def test_help_opens_bundled_example(page):
    page.click("#helpBtn")
    page.wait_for_selector("#exampleList li button")
    page.once("dialog", lambda d: d.accept())
    page.click("#exampleList li button >> nth=0")
    page.wait_for_selector("#helpDlg", state="hidden")
    assert "Simply supported beam" in page.input_value("#src") or "beam" in page.input_value("#name")


# Fake File System Access API: each handle records what was written to it in window.written.
FAKE_FS = """() => {
  window.written = []; window.picks = 0;
  const handle = (name, text) => ({
    name, getFile: async () => new File([text], name),
    requestPermission: async () => "granted",
    createWritable: async () => { let buf = ""; return {
      write: async (t) => { buf += t; }, close: async () => { window.written.push([name, buf]); } }; },
  });
  window.showOpenFilePicker = async () => [handle("beam.lens", "x = 2")];
  window.showSaveFilePicker = async () => { window.picks++; return handle("copy.lens", ""); };
}"""


def test_save_writes_back_to_the_opened_file(page):
    """#39, end to end: Open, Save writes back through the File System Access API, Save As
    renames the sheet. Which file a save goes to is tested in test_savefile.js."""
    page.evaluate(FAKE_FS)
    page.click("#open")
    page.wait_for_function("document.querySelector('#src').value === 'x = 2'")
    assert page.input_value("#name") == "beam"
    reset(page, "x = 3")
    page.keyboard.press("Control+s")
    page.wait_for_function("window.written.length === 1")
    assert page.evaluate("window.written[0]")[0] == "beam.lens" and "x = 3" in page.evaluate("window.written[0][1]")
    assert page.evaluate("window.picks") == 0
    page.click("#saveAs")
    page.wait_for_function("window.written.length === 2")
    assert page.evaluate("[window.picks, window.written[1][0]]") == [1, "copy.lens"]
    assert page.input_value("#name") == "copy"
    assert page.get_attribute("#save", "title") == "Save to copy.lens (Ctrl+S)"
    # Renaming the sheet means a new file.
    page.fill("#name", "other")
    assert page.get_attribute("#save", "title") == "Save the worksheet (Ctrl+S)"


def test_the_sheet_name_field_grows_to_fit_a_long_name(page):
    name = page.locator("#name")
    short = name.bounding_box()["width"]
    name.fill("Beam deflection under distributed load")
    box = name.bounding_box()
    assert box["width"] > short * 2
    fits = page.evaluate("(() => { const n = document.querySelector('#name'); return n.scrollWidth <= n.clientWidth; })()")
    assert fits


def test_globals_are_marked_and_get_their_tilde(page):
    reset(page, "~g = 5")
    page.evaluate("document.querySelector('#src').dispatchEvent(new Event('input'))")
    page.wait_for_selector("#out .row[data-line='1'] [data-global='g']")   # the evaluation is on screen
    page.keyboard.type("\ng = 12")
    assert value(page) == "~g = 5\n~g = 12"      # the ~ is added when the name ends
    assert page.get_attribute("#out [data-global]", "title") == "Global variable ~g, defined on line 1"
    page.wait_for_selector("#srcMarks mark >> nth=1")
    reset(page, "~g = 5\ng = 12")                # a deleted ~ shows a warning
    page.evaluate("document.querySelector('#src').dispatchEvent(new Event('input'))")
    page.wait_for_selector(".row .g-warn")
    assert "Changes the global ~g" in page.inner_text(".row .g-warn")
    page.uncheck("#markGlobals")
    assert page.inner_text("#globalsChip") == "~ 1 global not marked"
    assert page.evaluate("getComputedStyle(document.querySelector('#out [data-global]')).borderBottomStyle") == "none"
    page.click("#globalsChip")
    assert page.is_checked("#markGlobals") and page.is_hidden("#globalsChip")


def test_each_kind_of_line_shows_its_row(page):
    """What the results pane shows for each kind of line (static/rows.js, drawn by index.html)."""
    text = "## Loads\n!sigfigs 3\nx = 2'm\nnope +\n!plot x, x = 0 .. 1\n  grid: off\n  bad: 1\ny = 1\n!root y\n  equation: y^2 = 2"
    reset(page, text)
    page.evaluate("document.querySelector('#src').dispatchEvent(new Event('input'))")
    page.wait_for_selector(".row.solver .solver-tools")
    rows = page.eval_on_selector_all("#out .row", "rs => rs.map((r) => [+r.dataset.line, r.className.replace(' active', '')])")
    assert rows == [[1, "row heading"], [2, "row command"], [3, "row assign"], [4, "row error"], [5, "row plot"],
                    [7, "row error"], [8, "row assign"], [9, "row solver stale"]]
    assert page.inner_text(".row[data-line='1'] .body") == "Loads"
    assert page.text_content(".row[data-line='2'] .body") == "!sigfigs 3  →  Results show 3 significant figures"
    assert page.inner_text(".row[data-line='4'] .body .src") == "nope +"
    assert page.locator(".row[data-line='3'] .katex").count() == 1
    assert page.locator(".row[data-line='9'] .stale-mark").count() == 1
    at = text.index("  grid")
    select(page, at, at)
    page.evaluate("document.querySelector('#src').dispatchEvent(new Event('click'))")
    assert page.get_attribute(".row.active", "data-line") == "5"     # an option line: its plot's row
    select(page, len(text), len(text))
    page.evaluate("document.querySelector('#src').dispatchEvent(new Event('click'))")
    assert page.get_attribute(".row.active", "data-line") == "9"
    page.click("#viewLatex")
    page.wait_for_selector(".row.snip pre")
    assert page.locator(".row.snip .copy").count() == 6 and page.locator(".row.error .copy").count() == 0
    assert page.locator(".row.snip .solver-tools").count() == 1
    assert page.inner_text(".row[data-line='3'] pre").startswith("x =")
    page.click("#viewTypeset")


def test_a_sheet_the_program_was_started_with_opens_and_saves_back(page, tmp_path, monkeypatch):
    """#49: `lens --window sheet.lens` (a double-clicked file) opens that sheet, and Save writes it."""
    from laconic import server
    sheet = tmp_path / "beam.lens"
    sheet.write_text("x = 2\n", encoding="utf-8")
    monkeypatch.setattr(server, "OPENED", sheet)
    page.reload()
    page.wait_for_function("document.querySelector('#src').value.startsWith('x = 2')")
    assert page.input_value("#name") == "beam"
    assert page.get_attribute("#save", "title") == "Save to beam.lens (Ctrl+S)"
    reset(page, "x = 3\n")
    page.keyboard.press("Control+s")
    for _ in range(50):
        if sheet.read_bytes() != b"x = 2\n":
            break
        page.wait_for_timeout(100)
    assert sheet.read_bytes() == b"x = 3\n"
    # A reload keeps the edits rather than reading the file again.
    reset(page, "x = 4")
    page.evaluate("localStorage.setItem('lens:text', JSON.stringify('x = 4'))")
    page.reload()
    page.wait_for_function("document.querySelector('#src').value.length > 0")
    assert page.input_value("#src") == "x = 4"
    assert page.get_attribute("#save", "title") == "Save to beam.lens (Ctrl+S)"


def test_a_window_handed_over_by_another_launch_opens_and_saves_its_own_sheet(page, server, tmp_path, monkeypatch):
    """A second launch hands its sheet to the running LENS, which opens it on the same port
    (so the window has this browser's presets) and saves back to that sheet, not the first one."""
    from laconic import server as app_module
    first, second = tmp_path / "first.lens", tmp_path / "second.lens"
    first.write_text("a = 1\n", encoding="utf-8")
    second.write_text("b = 2\n", encoding="utf-8")
    opened = []
    monkeypatch.setattr(app_module, "OPENED", first)
    monkeypatch.setattr(app_module, "OPEN_WINDOW", opened.append)
    app_module.open_window(app_module.WindowBody(path=str(second)))
    page.goto(server + opened[0])
    page.wait_for_function("document.querySelector('#src').value.startsWith('b = 2')")
    assert page.input_value("#name") == "second"
    reset(page, "b = 3\n")
    page.keyboard.press("Control+s")
    for _ in range(50):
        if second.read_bytes() != b"b = 2\n":
            break
        page.wait_for_timeout(100)
    assert second.read_bytes() == b"b = 3\n"
    assert first.read_bytes() == b"a = 1\n"


def test_export_menu_downloads_latex_and_markdown(page):
    reset(page, "## Loads\nF = 2'kN")
    page.fill("#name", "loads")
    assert page.is_hidden("#exportList")
    for item, name, part in (("#export", "loads.tex", "\\documentclass"), ("#exportMd", "loads.md", "## Loads")):
        page.click("#exportBtn")
        with page.expect_download() as d:
            page.click(item)
        assert d.value.suggested_filename == name
        assert part in open(d.value.path(), encoding="utf-8").read()
        assert page.is_hidden("#exportList")
    page.click("#exportBtn")
    page.click("#out")
    assert page.is_hidden("#exportList")
