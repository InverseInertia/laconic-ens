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
                 "K_extra_r! = [", "exchangers! = [", "pumps! = [", "fit_method! = 1"):
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
    edited = value(page).replace("FIT_Hooper = [800, 0.40;", "FIT_Hooper = [700, 0.40;").replace("ε_Crane = 0.046 'mm\n", "")
    show(page, edited)
    page.click(".plugin-box button:has-text('Open')")
    frame.locator("#drift").wait_for(state="visible")
    text = frame.locator("#drift").inner_text()
    assert "Changed: FIT_Hooper" in text and "Missing: ε_Crane" in text
    page.once("dialog", lambda d: d.accept())
    frame.locator("#drift button:has-text('Open the original sheet')").click()
    page.wait_for_function("document.querySelector('#src').value.includes(\"ε_Crane = 0.046 'mm\")")
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
    assert frame.locator("#canvas g.back").count() == 1                                 # the supply behind, as a ghost
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
    assert next(l for l in after.split("\n") if l.startswith("  L_r! = ")).startswith("  L_r! = [30; 40; 20; 40; 50; 40; 50; 40; 20; 80;")   # R10 set to 80 as a whole
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


def test_the_pumps_target_pressure_difference_is_set_in_the_plugin(page):
    show(page, SHEET)
    frame = opened(page)
    frame.locator("#example").click()
    page.wait_for_function("document.querySelector('#src').value.includes(\"  Δp_target = 0.1 'psi\\n\")")
    frame.locator("#dpu").select_option("kPa")
    frame.locator("#dpv").fill("2.5")
    frame.locator("#dpv").press("Enter")
    page.wait_for_function("document.querySelector('#src').value.includes(\"  Δp_target = 2.5 'kPa\\n\")")


def test_a_target_set_again_in_the_sheet_is_named_and_the_plugins_reaches_the_solver(page):
    """A sheet from before the plugin wrote Δp_target kept its own line below the block, which replaced
    the plugin's value, so the solver never saw a change. The plugin now names that line; without it,
    a change in the plugin makes the solver's inputs, and so its hash, change."""
    original = page.evaluate("fetch('/api/plugins/pipenet/template').then((r) => r.text())")
    old = original.replace("# The pump's target pressure difference, Δp_target, comes from the plugin's block above.\n",
                           "Δp_target = 0.1 'psi\n")
    show(page, old)
    frame = opened(page)
    frame.locator("#msgs li.err:has-text('Δp_target is set again on line')").wait_for()
    page.click("#pluginDlg .close")
    show(page, original)
    page.click(".plugin-box button:has-text('Open')")
    frame.locator("#segments tbody tr").first.wait_for()
    page.wait_for_function("last.some((r) => r.solver)")
    before = page.evaluate("last.find((r) => r.solver).solver.hash")
    frame.locator("#dpv").fill("0.5")
    frame.locator("#dpv").press("Enter")
    page.wait_for_function(f"last.some((r) => r.solver && r.solver.hash !== {before!r})")


def test_the_drawing_shows_the_sets_ticked_and_sinks_pick_curves_by_name(page):
    original = page.evaluate("fetch('/api/plugins/pipenet/template').then((r) => r.text())")
    show(page, original)
    frame = opened(page)
    frame.locator("#showSets label:has-text('∀!')").wait_for()
    canvas = frame.locator("#canvas")
    assert "Δp_paths" in canvas.inner_html() and "D_h 4.03 in" not in canvas.inner_html()
    frame.locator("#showSets label:has-text('D_h') input").check()
    frame.locator("#showSets label:has-text('Δp_paths') input").uncheck()
    page.wait_for_function("document.querySelector('#src').value.includes('\"show\":{\"numbers\":true,\"size\":false,\"L\":false,\"D\":true')")
    assert "D_h 4.03 in" in canvas.inner_html() and "Δp_paths" not in canvas.inner_html()
    assert '"hide":["Δp_paths"]' in value(page)
    # a sink's exchanger is picked by the name the sheet gives it
    frame.locator("#sinks tbody tr").first.click()
    pick = frame.locator("#inspector select[aria-label='Exchanger curve']")
    assert pick.locator("option").all_inner_texts() == ["HBH060", "HBH009", "HBH006"]
    pick.select_option(label="HBH009")
    page.wait_for_function("document.querySelector('#src').value.match(/  exchangers! = \\[2;/)")
    frame.locator("#sinks tbody tr").first.locator("td:nth-child(2):text-is('HBH009')").wait_for()


def test_a_sink_takes_no_circulator_and_a_regulating_valve(page):
    original = page.evaluate("fetch('/api/plugins/pipenet/template').then((r) => r.text())")
    show(page, original)
    frame = opened(page)
    frame.locator("#sinks tbody tr").first.click()
    frame.locator("#inspector select[aria-label='Circulator']").select_option(label="None")
    page.wait_for_function("document.querySelector('#src').value.match(/  pumps! = \\[0;/)")
    valve = frame.locator("#inspector label:has-text('Regulating valve Cv') input")
    valve.fill("12.5")
    valve.press("Enter")
    page.wait_for_function("document.querySelector('#src').value.match(/  valves! = \\[12\\.5;/)")
    frame.locator("#sinks tbody tr").first.locator("td:nth-child(3):text-is('none')").wait_for()


def test_an_older_plugin_than_wrote_the_sheet_says_so_and_does_not_write(page):
    """A copy installed from a folder is never fetched again; one older than the copy that last wrote
    the block left that block's newer lines as they were (pumps!, valves!: the wrong length), so it
    may not write until it is updated. LENS stamps each write with the plugin's version."""
    original = page.evaluate("fetch('/api/plugins/pipenet/template').then((r) => r.text())")
    assert '"by":"1.4.2"' in original
    newer = original.replace('"by":"1.4.2"', '"by":"9.0.0"')
    show(page, newer)
    page.wait_for_function("document.querySelector('.plugin-status.err')?.textContent.includes('last written by Pipe network 9.0.0')")
    page.wait_for_selector(".plugin-box button:has-text('Open'):not([disabled])")
    page.click(".plugin-box button:has-text('Open')")
    frame = page.frame_locator("#pluginFrames .plugin-frame")
    frame.locator("#segments tbody tr").first.wait_for()
    frame.locator("#dpv").fill("0.5")
    frame.locator("#dpv").press("Enter")
    page.wait_for_timeout(1200)
    assert "  Δp_target = 0.02 'psi" in value(page)          # not written
    page.click("#pluginDlg .close")
    show(page, original)                                       # its own version: it writes, and stamps it
    import json
    from pathlib import Path
    version = json.loads((Path(__file__).parent.parent / "plugins/pipenet/manifest.json").read_text())["version"]
    page.wait_for_function(f"document.querySelector('.plugin-status')?.textContent.startsWith('Pipe network {version}')")
    page.click(".plugin-box button:has-text('Open')")
    frame.locator("#dpv").fill("0.5")
    frame.locator("#dpv").press("Enter")
    page.wait_for_function("document.querySelector('#src').value.includes(\"  Δp_target = 0.5 'psi\")")
    assert f'"by":"{version}"' in value(page)


def test_a_segments_length_is_set_as_a_whole(page):
    show(page, SHEET)
    frame = opened(page)
    frame.locator("#example").click()
    page.wait_for_function("document.querySelector('#src').value.includes('#@ state')")
    before = next(l for l in value(page).split("\n") if l.startswith("  L! = "))
    frame.locator("#segments tbody tr").nth(8).click()                 # segment 9: the trunk off the pump
    field = frame.locator("#inspector label:has-text('Segment length') input")
    assert field.input_value() == "20"                                 # two squares of 10 ft
    field.fill("300")
    field.press("Enter")
    page.wait_for_function(f"!document.querySelector('#src').value.includes({before!r})")
    after = next(l for l in value(page).split("\n") if l.startswith("  L! = "))
    old, new = (l.split("[")[1].split("]")[0].split("; ") for l in (before, after))
    assert new[8] == "300" and [x for i, x in enumerate(new) if i != 8] == [x for i, x in enumerate(old) if i != 8]
    frame.locator("#segments tbody tr").nth(8).locator("td:nth-child(2):text-is('300')").wait_for()


def _png(path, w=200, h=100):
    """A plain grey PNG, w by h."""
    import struct
    import zlib
    raw = b"".join(b"\x00" + b"\x80" * w for _ in range(h))
    chunk = lambda kind, data: struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    return path


def _bg(page):
    import json
    line = next(l for l in value(page).split("\n") if l.startswith("  #@ state "))
    return json.loads(line[len("  #@ state "):]).get("bg")


def test_a_planset_is_placed_behind_the_grid_moved_scaled_and_recalled(page, tmp_path):
    show(page, SHEET)
    frame = opened(page)
    frame.locator("#bgFile").set_input_files(str(_png(tmp_path / "plan.png")))
    page.wait_for_function("document.querySelector('#src').value.includes('\"plan.png\"')")
    g = _bg(page)
    assert g["ar"] == 0.5 and g["o"] == 0.5 and g["key"].startswith("img-")
    assert "data:" not in value(page)                       # the picture is not in the sheet
    frame.locator("#bg:not([hidden])").wait_for()
    # Move: dragging the picture moves it by as many squares
    box = frame.locator("#canvas").bounding_box()
    cell = 56
    page.mouse.move(box["x"] + 100, box["y"] + 100)
    page.mouse.down()
    page.mouse.move(box["x"] + 100 + 2 * cell, box["y"] + 100 + cell, steps=4)
    page.mouse.up()
    page.wait_for_function(f"!document.querySelector('#src').value.includes('\"x\":{g['x']},')")
    moved = _bg(page)
    assert (round(moved["x"] - g["x"], 6), round(moved["y"] - g["y"], 6)) == (2, 1)
    # Scale: two points three squares apart are said to be 60 ft (six squares of 10 ft): twice as large
    frame.locator("button[data-tool=measure]").click()
    page.mouse.click(box["x"] + 3 * cell, box["y"] + 3 * cell)
    page.mouse.click(box["x"] + 6 * cell, box["y"] + 3 * cell)
    frame.locator("#bgDist").fill("60")
    frame.locator("#bgDist").press("Enter")
    page.wait_for_function(f"!document.querySelector('#src').value.includes('\"w\":{moved['w']},')")
    scaled = _bg(page)
    assert round(scaled["w"] / moved["w"], 6) == 2
    # about the first point: the one point the scale leaves where it was, on a corner of a square
    ax, ay = 2 * moved["x"] - scaled["x"], 2 * moved["y"] - scaled["y"]
    assert (round(ax, 6) % 1, round(ay, 6) % 1) == (0, 0)
    assert abs(float(frame.locator("#bgW").input_value()) - scaled["w"] * 10) < 1e-3   # the width in ft
    # The page opened again on the same sheet recalls the picture from the browser
    text = value(page)
    page.reload()
    page.wait_for_function("document.querySelector('#src').value.length > 0")
    show(page, text)
    frame = opened(page)
    frame.locator("#bg:not([hidden])").wait_for()
    assert frame.locator("#bg").evaluate("i => i.src.startsWith('data:image/png')")


def test_a_planset_not_kept_in_this_browser_says_so(page):
    show(page, '!plugin pipenet\n  #@ state {"v":1,"cells":{},"bg":{"key":"img-nothere-1","name":"plan.png","x":0,"y":0,"w":10,"ar":1,"o":0.5}}\n')
    frame = opened(page)
    frame.locator("#bgNote:has-text('plan.png is not kept in this browser')").wait_for()
    assert frame.locator("#bg").is_hidden()


def test_ctrl_and_the_wheel_zoom_about_the_pointer(page):
    show(page, SHEET)
    frame = opened(page)
    frame.locator("#example").click()
    assert frame.locator("#zoomLevel").inner_text() == "100%"
    box = frame.locator("#canvas").bounding_box()
    x, y = box["x"] + 5.5 * 56, box["y"] + 3.5 * 56            # the middle of row 3, column 5
    page.mouse.move(x, y)
    page.keyboard.down("Control")
    page.mouse.wheel(0, -300)
    page.keyboard.up("Control")
    frame.locator("#zoomLevel:not(:text-is('100%'))").wait_for()
    # the point under the pointer is still under it: the middle of row 3, column 5
    after = frame.locator("#canvas").bounding_box()
    side = after["width"] / (box["width"] / 56)               # a square's size now
    assert side > 56
    assert (round((x - after["x"]) / side, 2), round((y - after["y"]) / side, 2)) == (5.5, 3.5)
    frame.locator("#zoomOut").click()
    frame.locator("#zoom100").click()
    assert frame.locator("#zoomLevel").inner_text() == "100%"


def test_a_sinks_settings_are_copied_to_others_and_sinks_alike_are_marked(page):
    import json
    show(page, SHEET)
    frame = opened(page)
    frame.locator("#example").click()
    page.wait_for_function("document.querySelector('#src').value.includes('#@ state')")
    frame.locator("#segments th:has-text('Q gal/min')").wait_for()     # the sheet has run on it
    marks = lambda: frame.locator("#canvas g.twin").count()
    assert marks() == 8                                    # the example's sinks start alike
    # S1 takes exchanger 2: it is like no other now
    frame.locator("#sinks tbody tr").first.click()
    field = frame.locator("#inspector label:has-text('Exchanger curve') input")
    field.fill("2")
    field.press("Enter")
    page.wait_for_function("document.querySelector('#src').value.match(/  exchangers! = \\[2; 1;/)")
    frame.locator("#inspector p:has-text('Set up like no other sink')").wait_for()
    assert marks() == 7
    # Copy settings to…, then click S2's tile
    frame.locator("#inspector button:has-text('Copy settings to')").click()
    frame.locator("#inspector p:has-text('Click sinks to give them S1')").wait_for()
    banner = frame.locator("#copyBanner > div")
    assert banner.is_visible() and "Copying S1's settings" in banner.inner_text()
    assert banner.evaluate("d => getComputedStyle(d).backgroundColor") == \
        frame.locator("body").evaluate("_ => { const d = document.createElement('div'); d.style.color = 'var(--err)'; document.body.append(d); const c = getComputedStyle(d).color; d.remove(); return c; }")
    state = json.loads(next(l for l in value(page).split("\n") if l.startswith("  #@ state "))[len("  #@ state "):])
    s2, (r0, c0) = frame.locator("body").evaluate(
        "(_, s) => { const P = PipeNet, st = P.normalize(s), b = P.bounds(st); return [P.network(st).sinks[1].key, [b.r0, b.c0]]; }", state)
    r, c = map(int, s2.split(","))
    frame.locator("main").evaluate(f"m => {{ m.scrollLeft = {(c - c0) * 56 - 100}; m.scrollTop = {(r - r0) * 56 - 100}; }}")
    box = frame.locator("#canvas").bounding_box()
    page.mouse.click(box["x"] + (c - c0 + 0.5) * 56, box["y"] + (r - r0 + 0.5) * 56)
    page.wait_for_function("document.querySelector('#src').value.match(/  exchangers! = \\[2; 2; 1;/)")
    assert marks() == 8                                    # S1 and S2 alike, the other six alike
    page.keyboard.press("Escape")
    frame.locator("#inspector p:has-text('Set up like S2')").wait_for()
    assert banner.is_hidden()
    # the switch: a change to S1 alone, then to S1 and every sink set up like it (S2)
    exch = lambda: frame.locator("#inspector label:has-text('Exchanger curve') input")
    assert frame.locator("#inspector .apply button[aria-pressed=true]").inner_text() == "This sink"
    exch().fill("3")
    exch().press("Enter")
    page.wait_for_function("document.querySelector('#src').value.match(/  exchangers! = \\[3; 2; 1;/)")
    frame.locator("#sinks tbody tr").first.click()                      # S1 is like no other now: no switch
    assert frame.locator("#inspector .apply").count() == 0
    exch().fill("2")
    exch().press("Enter")                                               # alike with S2 again
    page.wait_for_function("document.querySelector('#src').value.match(/  exchangers! = \\[2; 2; 1;/)")
    frame.locator("#inspector .apply button:has-text('All 2 alike')").click()
    frame.locator("#inspector .sink-settings.all").wait_for()
    frame.locator("#inspector .warn-all:has-text('Changes go to 2 sinks')").wait_for()
    exch().fill("3")
    exch().press("Enter")
    page.wait_for_function("document.querySelector('#src').value.match(/  exchangers! = \\[3; 3; 1;/)")
    # To every sink
    frame.locator("#inspector button:has-text('Copy settings to')").click()
    frame.locator("#inspector button:has-text('To every sink')").click()
    page.wait_for_function("document.querySelector('#src').value.includes('  exchangers! = [3; 3; 3; 3; 3; 3; 3; 3]')")


def test_the_plugin_says_when_its_values_wait_on_the_solver(page):
    """Every !pluginvar value says when it rests on a solver out of date: the plugin puts a banner over the
    grid from a change until the sheet's solver has run on it."""
    original = page.evaluate("fetch('/api/plugins/pipenet/template').then((r) => r.text())")
    show(page, original)
    page.wait_for_selector(".plugin-box button:has-text('Open'):not([disabled])")
    page.click(".plugin-box button:has-text('Open')")
    frame = page.frame_locator("#pluginFrames .plugin-frame")
    frame.locator("#segments tbody tr").first.wait_for()
    banner = frame.locator("#solveBanner")
    assert banner.is_hidden()                                          # solved as it comes
    frame.locator("body").evaluate("""() => { window.__shown = false;
        new MutationObserver(() => { if (!document.querySelector('#solveBanner').hidden) window.__shown = true; })
          .observe(document.querySelector('#solveBanner'), {attributes: true}); }""")
    frame.locator("#dpv").fill("0.05")
    frame.locator("#dpv").press("Enter")
    banner.locator("> div").wait_for(state="visible", timeout=60000)
    assert "Waiting on the solver" in banner.inner_text()
    banner.wait_for(state="hidden", timeout=120000)                    # autorun has solved it
    assert "Δp_target = 0.05 'psi" in value(page)


def test_the_plugin_reads_the_solvers_state_from_the_sheet(page):
    """The plugin's sheet sends `solver_state` (its !root's `status:` line): a solver never run, or a block
    in error, has a banner of its own; the state is not offered as a value to draw."""
    import re
    original = page.evaluate("fetch('/api/plugins/pipenet/template').then((r) => r.text())")
    assert "  status: solver_state\n" in original and original.rstrip().endswith(", solver_state")
    never = re.sub(r"\n  #@ result [^\n]*", "", original).replace("  autorun: on\n", "")
    show(page, never)
    page.wait_for_selector(".plugin-box button:has-text('Open'):not([disabled])")
    page.click(".plugin-box button:has-text('Open')")
    frame = page.frame_locator("#pluginFrames .plugin-frame")
    frame.locator("#solveBanner:has-text('has not run on this layout yet')").wait_for()
    assert frame.locator("#showSets label:has-text('solver_state')").count() == 0
    page.click("#pluginDlg .close")
    show(page, never.replace("  equation: residual(∀_des!)", "  equation: residual(∀_des!) + nothing_here"))
    page.click(".plugin-box button:has-text('Open')")
    frame.locator("#solveBanner[data-state='-2']:has-text('has an error')").wait_for()


def test_the_key_to_sinks_alike_stays_in_sight_and_their_balloons_leave_out_what_they_share(page):
    show(page, SHEET)
    frame = opened(page)
    frame.locator("#example").click()
    frame.locator("#segments th:has-text('Q gal/min')").wait_for()
    key = frame.locator("#sinkKey")
    assert key.is_hidden()                                             # nothing shared is drawn yet
    frame.locator("#showSets label:has-text('Exchanger curve') input").check()
    key.wait_for(state="visible")
    assert key.locator(".key-row").count() == 1 and "hx curve 1" in key.inner_text()   # the eight sinks are alike
    assert "hx curve" not in frame.locator("#canvas").evaluate("s => s.textContent")        # not in their balloons
    main = frame.locator("main").bounding_box()
    frame.locator("main").evaluate("m => { m.scrollLeft = m.scrollWidth; m.scrollTop = m.scrollHeight; }")
    box = key.bounding_box()
    assert main["x"] <= box["x"] and box["y"] + box["height"] <= main["y"] + main["height"]   # still in sight
