"""Plugins in the real page (Chromium, through Playwright), with the pipenet plugin from this
checkout's plugins/ folder: the frame, what it writes into the sheet and what the sheet sends it.
Skipped when Playwright or a browser is not available, like test_ui.py."""
import pytest

pytest.importorskip("playwright.sync_api")
from uihelpers import reset, value  # noqa: E402

SHEET = "!plugin pipenet\nQ = A * ones(cols(A), 1) * 'gal/'min -> 'gal/'min\n!pluginvar Q\n"


def show(page, text):
    reset(page, text)
    page.evaluate("document.querySelector('#src').dispatchEvent(new Event('input'))")


def opened(page):
    page.wait_for_selector(".plugin-box button:has-text('Open'):not([disabled])")
    page.wait_for_function("document.querySelector('.plugin-status').textContent.startsWith('Pipe network')")
    page.click(".plugin-box button:has-text('Open')")
    page.wait_for_selector("#pluginDlg[open] .plugin-frame:not([hidden])")
    return page.frame_locator("#pluginFrames .plugin-frame")


def test_the_plugin_writes_its_network_into_its_block_and_shows_the_sheets_values(page):
    show(page, SHEET)
    frame = opened(page)
    frame.locator("#example").click()
    page.wait_for_function("document.querySelector('#src').value.includes('#@ state')")
    text = value(page)
    assert text.startswith("!plugin pipenet\n  A = [1, 0, 0, 0, 0, 0, 0, 0; ")
    for name in ("L! = [", "D_h! = [", "N_fit! = [", "K_extra! = [", "A_r = [", "L_r! = [", "D_r! = [", "N_fit_r! = [",
                 "K_extra_r! = [", "exchangers! = [", "speeds! = [", "fit_method! = 1"):
        assert f"\n  {name}" in text
    # the sheet runs on what it wrote, and Q comes back to the frame, one value per segment
    frame.locator("#segments th:has-text('Q gal/min')").wait_for()
    assert frame.locator("#segments tbody tr").count() == 15
    assert frame.locator("#segments tbody tr").first.locator("td").last.inner_text() == "1"
    assert frame.locator("#msgs").inner_text().startswith("One source, 8 sinks, 15 segments")
    page.click("#pluginDlg .close")
    page.wait_for_selector(".plugin-box img.plugin-preview")   # the row shows the plugin's picture


def test_a_network_drawn_with_the_mouse_reaches_the_sheet(page):
    show(page, SHEET)
    frame = opened(page)
    box = frame.locator("#canvas").bounding_box()
    cell = 56   # pipenet.js CELL; an empty grid starts at row 0, column 0
    at = lambda r, c: (box["x"] + (c + 0.5) * cell, box["y"] + (r + 0.5) * cell)
    frame.locator("#palette button[title='Source, E']").click()
    page.mouse.click(*at(2, 1))
    frame.locator("#palette button[title='Sink, W']").click()
    page.mouse.click(*at(2, 5))
    frame.locator("button[data-tool=draw]").click()
    page.mouse.move(*at(2, 1))
    page.mouse.down()
    for c in range(2, 6):
        page.mouse.move(*at(2, c), steps=3)
    page.mouse.up()
    page.wait_for_function("document.querySelector('#src').value.includes('  A = [1]\\n')")
    assert "  L! = [40] * 'ft\n" in value(page)    # four squares of 10 ft
    assert "  L_r! = [40] * 'ft\n" in value(page)  # and the return the same
    frame.locator("#segments th:has-text('Q gal/min')").wait_for()


def test_an_edit_to_the_state_in_the_sheet_reaches_the_plugin(page):
    show(page, SHEET)
    frame = opened(page)
    frame.locator("#example").click()
    page.wait_for_function("document.querySelector('#src').value.includes('#@ state')")
    assert frame.locator("#empty").is_hidden()
    show(page, '!plugin pipenet\n  #@ state {"v":1,"cells":{}}\n')
    frame.locator("#empty").wait_for(state="visible")


def test_the_frame_is_sandboxed_from_the_page(page):
    show(page, SHEET)
    opened(page)
    assert page.evaluate("document.querySelector('.plugin-frame').contentDocument") is None
    assert page.get_attribute(".plugin-frame", "sandbox") == "allow-scripts"


def test_a_plugin_that_does_not_exist_says_so_and_the_sheet_still_runs(page):
    show(page, "!plugin nosuchplugin\n  x = 2\ny = x + 1\n")
    page.wait_for_function("document.querySelector('.plugin-status.err')?.textContent.includes(\"no plugin 'nosuchplugin'\")")
    assert "3" in page.inner_text(".row[data-line='3'] .body")


@pytest.fixture()
def from_github(tmp_path, monkeypatch):
    """Plugins fetched from a stand-in GitHub that serves this checkout's plugins/ folder, kept in an
    empty folder of their own, with automatic downloads off."""
    from laconic import plugins, settings
    monkeypatch.setenv("LENS_PLUGIN_SOURCE", "https://example.org/plugins")
    monkeypatch.setattr(plugins, "cache_dir", lambda: tmp_path / "kept")
    monkeypatch.setattr(plugins, "fetcher",
                        lambda url, timeout=None: (plugins.CHECKOUT / url.removeprefix("https://example.org/plugins/")).read_bytes())
    settings.save_prefs({"autoPlugins": False})
    yield
    settings.save_prefs({"autoPlugins": None})


def test_with_downloads_off_a_block_offers_install_and_settings_lists_and_removes_it(page, from_github):
    page.reload()
    page.wait_for_function("document.querySelector('#src').value.length > 0")
    show(page, SHEET)
    page.wait_for_function("document.querySelector('.plugin-status.err')?.textContent.includes('automatic downloads are off')")
    page.click(".plugin-box button:has-text('Install')")
    page.wait_for_function("document.querySelector('.plugin-status').textContent.startsWith('Pipe network')")
    page.click("#settingsBtn")
    assert not page.is_checked("#autoPlugins")
    page.wait_for_selector("#pluginSettings .plugin-item:has-text('Pipe network') button:has-text('Remove')")
    page.wait_for_selector("#pluginSettings :text('All the available plugins are installed.')")
    page.click("#pluginSettings .plugin-item button:has-text('Remove')")
    page.wait_for_selector("#pluginSettings :text('No plugins installed.')")
    page.wait_for_selector("#pluginSettings .plugin-item:has-text('Pipe network') button:has-text('Install')")
    page.check("#autoPlugins")
    for _ in range(50):   # the preference reaches the server
        if page.evaluate("fetch('/api/plugins').then((r) => r.json()).then((j) => j.auto)"):
            break
        page.wait_for_timeout(100)
    else:
        raise AssertionError("turning automatic downloads on did not reach the server")


def test_a_plugin_not_on_github_is_installed_from_its_folder(page, tmp_path, monkeypatch):
    """A branch's plugin that GitHub's main does not have yet: Install from a folder takes it from disk."""
    from laconic import plugins

    def nothing(url, timeout=None):
        raise OSError("HTTP Error 404: Not Found")
    monkeypatch.setenv("LENS_PLUGIN_SOURCE", "https://example.org/plugins")
    monkeypatch.setattr(plugins, "cache_dir", lambda: tmp_path / "kept")
    monkeypatch.setattr(plugins, "fetcher", nothing)
    page.reload()
    page.wait_for_function("document.querySelector('#src').value.length > 0")
    show(page, SHEET)
    page.wait_for_function("document.querySelector('.plugin-status.err')?.textContent.includes(\"no plugin 'pipenet'\")")
    page.click("#settingsBtn")
    page.wait_for_selector("#pluginSettings :text('No plugins installed.')")
    with page.expect_file_chooser() as fc:
        page.click("#pluginSettings button:has-text('Install from a folder')")
    fc.value.set_files(str(plugins.CHECKOUT / "pipenet"))
    page.wait_for_selector("#pluginSettings .plugin-item:has-text('from a folder') button:has-text('Remove')")
    assert page.locator("#pluginSettings .plugin-item button:has-text('Update')").count() == 0
    page.click("#settingsDlg .close")
    page.wait_for_function("document.querySelector('.plugin-status').textContent.startsWith('Pipe network')")


def test_the_plugin_takes_the_pages_colours_and_fonts_and_follows_a_new_theme(page):
    show(page, SHEET)
    opened(page)
    frame = next(f for f in page.frames if "/plugins/pipenet/" in f.url)
    paper = lambda: page.evaluate("getComputedStyle(document.body).backgroundColor")
    frame.wait_for_function(f"getComputedStyle(document.body).backgroundColor === {paper()!r}")
    frame.wait_for_function("document.fonts.check('13px \"IBM Plex Sans\"')")   # LENS's own fonts, though sandboxed
    page.click("#pluginDlg .close")
    page.click("#settingsBtn")
    page.select_option("#preset", label="White paper")
    page.click("#settingsDlg .close")
    frame.wait_for_function(f"getComputedStyle(document.body).backgroundColor === {paper()!r}")
    page.evaluate("localStorage.clear()")


def test_the_plugin_warns_of_its_sheet_changed_and_opens_the_original(page):
    original = page.evaluate("fetch('/api/plugins/pipenet/template').then((r) => r.text())")
    show(page, original)
    frame = opened(page)
    frame.locator("#segments tbody tr").first.wait_for()
    page.wait_for_timeout(300)
    assert frame.locator("#drift").is_hidden()                    # the plugin's own sheet, as it ships
    # the method is the user's: the plugin writes it
    frame.locator("#method").select_option("3")
    page.wait_for_function("document.querySelector('#src').value.includes('  fit_method! = 3\\n')")
    page.click("#pluginDlg .close")
    edited = value(page).replace("FIT_Hooper = [800, 0.40;", "FIT_Hooper = [700, 0.40;").replace("Δp_target = 0.1 'psi\n", "")
    show(page, edited)
    page.click(".plugin-box button:has-text('Open')")
    frame.locator("#drift").wait_for(state="visible")
    text = frame.locator("#drift").inner_text()
    assert "Changed: FIT_Hooper" in text and "Missing: Δp_target" in text
    page.once("dialog", lambda d: d.accept())
    frame.locator("#drift button:has-text('Open the original sheet')").click()
    page.wait_for_function("document.querySelector('#src').value.includes(\"Δp_target = 0.1 'psi\")")
    assert value(page) == original
    page.click(".plugin-box button:has-text('Open')")
    frame.locator("#drift").wait_for(state="hidden")


def test_the_return_is_laid_out_on_a_side_of_its_own(page):
    show(page, SHEET)
    frame = opened(page)
    frame.locator("#example").click()
    page.wait_for_function("document.querySelector('#src').value.includes('#@ state')")
    assert frame.locator("#sides").is_hidden()                  # one layout, the return the same
    frame.locator("#ret").select_option("separate")
    frame.locator("#sides").wait_for(state="visible")
    assert frame.locator("button[data-layer=r]").get_attribute("aria-pressed") == "true"   # the return in front
    assert frame.locator("#canvas g[opacity='0.3']").count() == 1                       # the supply faded behind
    # lengthen one return tile: only the return's lengths change
    before = value(page)
    supply = next(l for l in before.split("\n") if l.startswith("  L! = "))
    old_r = next(l for l in before.split("\n") if l.startswith("  L_r! = "))
    frame.locator("#rsegments tbody tr").nth(9).click()             # R10: the first trunk segment of the return
    field = frame.locator("#inspector input").first
    field.fill("80")
    field.press("Enter")
    page.wait_for_function(f"!document.querySelector('#src').value.includes({old_r!r})")
    after = value(page)
    assert next(l for l in after.split("\n") if l.startswith("  L! = ")) == supply
    assert next(l for l in after.split("\n") if l.startswith("  L_r! = ")).startswith("  L_r! = [30; 40; 20; 40; 50; 40; 50; 40; 20; 100;")
    assert '"ret":"separate"' in after
    frame.locator("#retHead").wait_for(state="visible")             # the return's segments, in a table of their own


def test_a_pipe_size_is_picked_from_the_schedule(page):
    show(page, SHEET)
    frame = opened(page)
    frame.locator("#example").click()
    page.wait_for_function("document.querySelector('#src').value.includes(\"D_h! = [4.026;\")")
    frame.locator("#sch").select_option("80")
    page.wait_for_function("document.querySelector('#src').value.includes(\"D_h! = [3.826;\")")
    frame.locator("#size").select_option("6")
    page.wait_for_function("document.querySelector('#src').value.includes(\"D_h! = [5.761;\")")
