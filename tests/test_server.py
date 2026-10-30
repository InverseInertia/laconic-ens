"""The API endpoints, called as plain functions (no HTTP client needed)."""
import json

import pytest

from laconic import server, settings
from laconic.opened import sheets
from laconic.commands import COMMANDS, help_rows
from laconic.server import GreekBody, Sheet, TagsBody, UnitRow, UnitsBody


@pytest.fixture(autouse=True)
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("LENS_CONFIG_DIR", str(tmp_path))
    yield tmp_path
    sheets.clear()


def put_units(*pairs):
    return server.put_units(UnitsBody(units=[UnitRow(name=n, definition=d) for n, d in pairs]))


def test_defaults_when_nothing_is_stored():
    assert server.get_settings() == {"welcomed": False, "greek": None, "units": [], "tags": {}, "prefs": {}}


def test_greek_table_is_stored_and_can_be_reset():
    assert server.put_greek(GreekBody(greek={"a": "ȧ"})) == {"ok": True}
    assert server.get_settings()["greek"] == {"a": "ȧ"}
    server.put_greek(GreekBody(greek=None))
    assert server.get_settings()["greek"] is None


def test_units_are_validated_before_anything_is_stored():
    bad = put_units(("smoot", "1.7018'm"), ("m", "2'ft"))
    assert bad["ok"] is False and bad["errors"][0] is None and "already a unit" in bad["errors"][1]
    assert server.get_settings()["units"] == []
    assert put_units((" smoot ", " 1.7018'm "))["ok"] is True
    assert server.get_settings()["units"] == [{"name": "smoot", "definition": "1.7018'm"}]


def test_stored_units_reach_every_endpoint():
    put_units(("smoot", "1.7018'm"))
    sheet = Sheet(text="d = 3'smoot -> 'm", title="t")
    assert "5.105" in server.evaluate(sheet)[0]["text"]
    assert "\\DeclareSIUnit{\\smoot}" in server.export(sheet)
    assert "'smoot = 1.7018'm" in server.save(sheet)
    assert server.vocab()["globalUnits"] == [["smoot", "1.7018'm"]]


def test_markdown_export_uses_the_live_math_flavour():
    out = server.export_md(Sheet(text="## Loads\nF = 2'kN", title="t"))
    assert out.startswith("# t\n\n## Loads\n\n$$\nF = 2\\,\\mathrm{kN}\n$$")


def test_vocabulary_has_what_the_editor_completes():
    v = server.vocab()
    units = {u[0]: u for u in v["units"]}
    assert units["kN"][1] == "kilonewton" and units["kN"][2] == 1 and "mm" in units and "GPa" in units
    assert ["sqrt", "sqrt(x)"] in v["functions"] and "pi" in v["constants"]
    assert v["commands"] == [[c.name, c.summary] for c in COMMANDS]


def test_the_page_carries_the_command_help_rows():
    page = server.index().body.decode()
    assert help_rows() in page and "<!-- command help" not in page


def test_the_page_shows_the_version_in_the_header_and_help(monkeypatch):
    page = server.index().body.decode()
    assert "{{version}}" not in page
    assert '<span class="version" id="version">dev</span>' in page   # a source checkout
    assert '<p class="version" id="helpVersion">LENS dev &middot;' in page
    monkeypatch.setattr(server, "version_label", lambda: "v0.2.0")
    assert 'id="version">v0.2.0</span>' in server.index().body.decode()


def _static(path, headers=()):
    """GET a file from the page's static files, as the browser would."""
    import asyncio
    scope = {"type": "http", "method": "GET", "path": path, "headers": [(k.encode(), v.encode()) for k, v in headers]}
    mount = next(r for r in server.app.routes if getattr(r, "path", None) == server.ASSETS)
    return asyncio.run(mount.app.get_response(path.removeprefix(server.ASSETS + "/"), scope))


def test_the_page_asks_for_its_files_under_the_version():
    """#119: after an update Chromium ran the cached scripts of the old version against the new
    page. The page names its files under a path with the version in it, and is itself never cached."""
    page = server.index()
    assert page.headers["cache-control"] == "no-cache"
    body = page.body.decode()
    assert server.ASSETS == "/static/dev"
    assert 'src="/static/dev/api.js"' in body and "`/static/dev/icons/" in body
    assert '"/static/' not in body.replace('"/static/dev/', "")


def test_static_files_are_checked_with_the_server_each_time():
    """#119: no Last-Modified for a browser to guess a lifetime from; an ETag that changes with
    the version, and a 304 while it matches."""
    first = _static(server.ASSETS + "/api.js")
    assert first.status_code == 200 and first.headers["cache-control"] == "no-cache"
    assert "last-modified" not in first.headers
    etag = first.headers["etag"]
    assert etag.startswith('"dev-')
    again = _static(server.ASSETS + "/api.js", [("if-none-match", etag)])
    assert again.status_code == 304 and again.headers["etag"] == etag
    stale = _static(server.ASSETS + "/api.js", [("if-none-match", etag.replace("dev-", "v0.4.2-"))])
    assert stale.status_code == 200


def test_version_label():
    from laconic._version import label
    assert label("0+dev") == "dev" and label("0.2.0") == "v0.2.0"


def test_the_package_version_is_read_from_the_version_module():
    # The release build stamps laconic/_version.py; pyproject.toml must take the version from it.
    import re
    tomllib = pytest.importorskip("tomllib")  # Python 3.11+
    from pathlib import Path
    root = Path(__file__).parent.parent
    project = tomllib.loads((root / "pyproject.toml").read_text())
    assert "version" not in project["project"] and "version" in project["project"]["dynamic"]
    assert project["tool"]["setuptools"]["dynamic"]["version"] == {"attr": "laconic._version.__version__"}
    # The workflow's sed rewrites exactly this line.
    assert re.search(r'^__version__ = "[^"]*"$', (root / "laconic" / "_version.py").read_text(), re.M)


def test_settings_survive_a_broken_file(config):
    (config / "settings.json").write_text("{not json")
    assert server.get_settings() == {"welcomed": False, "greek": None, "units": [], "tags": {}, "prefs": {}}
    assert settings.global_units() == []


def test_saving_one_setting_keeps_the_other():
    server.put_greek(GreekBody(greek={"a": "ȧ"}))
    put_units(("smoot", "1.7018'm"))
    server.put_greek(GreekBody(greek={"b": "ḃ"}))
    cfg = server.get_settings()
    assert cfg["greek"] == {"b": "ḃ"} and cfg["units"][0]["name"] == "smoot"


def test_vocabulary_has_solver_options_and_methods():
    v = server.vocab()["blocks"]
    assert [k for k, _ in v["root"]["keys"]][:2] == ["equation", "bounds"]
    assert "objective" in [k for k, _ in v["minimize"]["keys"]]
    assert [m for m, _ in v["root"]["choices"]["method"]] == ["hybr", "lm", "broyden1", "broyden2", "krylov", "brentq"]
    assert "SLSQP" in [m for m, _ in v["maximize"]["choices"]["method"]] and all(d for _, d in v["minimize"]["choices"]["method"])
    assert [c for c, _ in v["root"]["choices"]["autorun"]] == ["on", "off"]
    assert v["root"]["args"] == {"bounds": "unknown"} and "bounds" in v["root"]["math"] and "method" not in v["root"]["math"]


def test_vocabulary_describes_every_block_from_the_tables_it_is_parsed_with():
    """One entry per block command sheettext knows, each key with a note, as the parsers take them (#137)."""
    from laconic import plotopts, regression, solver, symsolve
    from laconic.sheettext import _SOLVER_RE
    v = server.vocab()["blocks"]
    assert set(v) == {"plot", *_SOLVER_RE.pattern.split("(")[1].split(")")[0].split("|")}
    keys = {kind: [k for k, _ in b["keys"]] for kind, b in v.items()}
    assert set(keys["plot"]) == set(plotopts.KEYS) and keys["regression"] == list(regression.KEYS)
    assert keys["symsolve"] == list(symsolve.KEYS) and keys["minimize"] == list(solver.KEYS["minimize"])
    for b in v.values():
        assert all(note for _, note in b["keys"])
        assert set(b["choices"]) | set(b["math"]) | set(b["args"]) <= {k for k, _ in b["keys"]}
    plot = v["plot"]
    assert [c for c, _ in plot["choices"]["grid"]] == ["on", "off"] and "red" in dict(plot["choices"]["color"])
    assert {"xlim", "points", "note", "xunit"} <= set(plot["math"]) and "title" not in plot["math"]
    assert plot["args"]["color"] == "series"
    # every kind of plot option is listed
    assert set(plotopts.CHOICES) | set(plotopts.TEXT) | set(plotopts.NUMBERS) | set(plotopts.SERIES_KEYS) \
        | set(plotopts.LIMIT_KEYS) <= set(plotopts.KEYS)


def test_props_vocabulary_lists_keys_and_fluids():
    v = server.vocab_props()
    keys = {k[0]: k for k in v["keys"]}
    assert keys["T"][1:] == ["Temperature", "K", True, False]
    assert keys["Tcrit"][4] is True and keys["Cpmass"][3] is False and keys["Prandtl"][2] == ""
    names = [f[0] for f in v["fluids"]]
    assert names[:2] == ["Water", "Air"] and "R134a" in names and "INCOMP::MEG[0.3]" in names
    assert "H2O" in dict(v["fluids"])["Water"]


def test_examples_are_served_from_the_package(config):
    names = [e["name"] for e in server.list_examples()]
    assert {"beam", "plots", "solve", "symbolic"} <= set(names)
    assert "L = 4.5'm" in server.get_example("beam").body.decode()
    with pytest.raises(Exception):
        server.get_example("../settings")


def test_welcomed_flag_is_remembered(config):
    assert server.get_settings()["welcomed"] is False
    server.put_welcomed()
    assert server.get_settings()["welcomed"] is True


def test_opened_sheet_is_served_and_saved_back(tmp_path):
    assert server.get_opened() == {}
    sheet = tmp_path / "beam.lens"
    sheet.write_text("x = 2\n", encoding="utf-8")
    sheets.start(sheet)
    got = server.get_opened()
    assert got["file"] == "beam.lens" and got["text"] == "x = 2\n" and got["writable"] is True
    assert server.save_opened(server.TextBody(text="x = 3\r\n")) == {"ok": True}
    assert sheet.read_bytes() == b"x = 3\r\n"


def test_an_opened_txt_file_is_read_but_never_written(tmp_path):
    sheet = tmp_path / "old.txt"
    sheet.write_text("x = 2", encoding="utf-8")
    sheets.start(sheet)
    assert server.get_opened()["writable"] is False
    with pytest.raises(server.HTTPException):
        server.save_opened(server.TextBody(text="y"))
    assert sheet.read_text() == "x = 2"


def test_hello_names_the_program():
    assert server.hello()["app"] == "lens"


def test_a_handed_over_sheet_opens_in_a_window_of_its_own(tmp_path):
    """Another launch hands its sheet to this server: the new window reads and saves that sheet,
    while a window without ?sheet= still has the one the program was started with."""
    start, other = tmp_path / "start.lens", tmp_path / "other.lens"
    start.write_text("a = 1\n", encoding="utf-8")
    other.write_text("b = 2\n", encoding="utf-8")
    opened = []
    sheets.start(start)
    sheets.serve(opened.append)
    assert server.open_window(server.WindowBody(path=str(other))) == {"ok": True}
    token = opened[0].removeprefix("/?sheet=")
    assert token and server.get_opened(token)["text"] == "b = 2\n"
    server.save_opened(server.TextBody(text="b = 3\n"), token)
    assert other.read_text(encoding="utf-8") == "b = 3\n"
    assert server.get_opened()["file"] == "start.lens"
    assert server.get_opened("not-a-token") == {}


def test_a_handed_over_launch_without_a_sheet_opens_an_empty_window(tmp_path):
    opened = []
    sheets.start(tmp_path / "start.lens")
    sheets.serve(opened.append)
    server.open_window(server.WindowBody())
    assert opened == ["/?sheet="]
    assert server.get_opened("") == {}


def test_a_server_that_opens_no_windows_says_so():
    with pytest.raises(server.HTTPException):
        server.open_window(server.WindowBody())


def test_display_preferences_are_merged_and_written_into_the_page():
    """Kept on the server so a LENS on another port, or another browser, looks the same."""
    server.put_prefs(server.PrefsBody(prefs={"view": "latex", "theme": {"bg": "plain"}}))
    server.put_prefs(server.PrefsBody(prefs={"view": None, "wrapText": True, "nonsense": 1}))
    assert server.get_settings()["prefs"] == {"theme": {"bg": "plain"}, "wrapText": True}
    assert '<script type="application/json" id="prefs">{"theme": {"bg": "plain"}, "wrapText": true}</script>' \
        in server.index().body.decode()


def test_the_page_gets_the_preference_keys_from_the_settings_module():
    """One list (settings.PREFS) says which settings the page keeps on the server."""
    keys = json.dumps(list(settings.PREFS))
    assert f'<script type="application/json" id="prefKeys">{keys}</script>' in server.index().body.decode()


def test_a_stored_preference_cannot_close_the_script_it_is_written_into():
    server.put_prefs(server.PrefsBody(prefs={"view": "</script><script>alert(1)</script>"}))
    page = server.index().body.decode()
    assert "</script><script>alert(1)" not in page and "\\u003c/script>" in page


# ---- units dialog ------------------------------------------------------------------
def test_the_units_dialog_lists_every_unit_with_its_standard_tags():
    b = server.unit_browse()
    assert b["tags"][:2] == ["common", "constants"] and "thermodynamics" in b["tags"] and b["userTags"] == {}
    rows = {r[0]: r for r in b["units"]}
    assert len(rows) > 1000
    assert {"constants", "thermodynamics", "chemistry"} <= set(rows["R"][2]) and "gas" in rows["R"][1]
    assert {"common", "pressure", "imperial"} <= set(rows["psi"][2])
    assert "pressure" in rows["inHg"][2]          # tagged by its dimension, not by name
    assert rows["USD"][2] == ["common", "currency"]


def test_global_units_head_the_list_with_a_tag_of_their_own():
    put_units(("smoot", "1.7018'm"))
    b = server.unit_browse()
    assert b["units"][0] == ["smoot", "= 1.7018'm", ["global units"]] and b["tags"][-1] == "global units"


def test_the_users_tags_are_cleaned_and_kept_in_the_settings_file(config):
    res = server.put_tags(TagsBody(tags={"  heat   transfer ": ["'W", "W", "Pa"], "empty": [" "]}))
    assert res == {"ok": True, "tags": {"heat transfer": ["W", "Pa"]}}
    assert server.get_settings()["tags"] == {"heat transfer": ["W", "Pa"]}
    assert '"heat transfer"' in (config / "settings.json").read_text(encoding="utf-8")
    assert server.unit_browse()["userTags"] == {"heat transfer": ["W", "Pa"]}
    assert server.put_tags(TagsBody(tags={})) == {"ok": True, "tags": {}}
    assert server.get_settings()["tags"] == {}


def test_a_tag_without_a_name_or_too_long_is_refused_and_nothing_is_stored():
    server.put_tags(TagsBody(tags={"mine": ["W"]}))
    assert server.put_tags(TagsBody(tags={"  ": ["W"]}))["ok"] is False
    assert "40" in server.put_tags(TagsBody(tags={"x" * 41: ["W"]}))["error"]
    assert server.get_settings()["tags"] == {"mine": ["W"]}


def test_a_damaged_tags_entry_in_the_settings_file_is_ignored(config):
    (config / "settings.json").write_text('{"tags": {"ok": ["W", 3], "bad": "W"}}', encoding="utf-8")
    assert settings.load()["tags"] == {"ok": ["W"]}
    (config / "settings.json").write_text('{"tags": ["W"]}', encoding="utf-8")
    assert settings.load()["tags"] == {}


# ---- plots drawn after the math -------------------------------------------------------------
PLOTS = "x0 = 2\n!plot x0*t, t = 0 .. 1\n  color: red\n  bogus: 1\ny = 3\n!plot t^2, t = 0 .. 1\n  ylim: nope .. 2\n"


def test_eval_can_leave_plots_pending_and_still_reports_their_option_lines():
    rows = server.evaluate(Sheet(text=PLOTS, plots=False))
    assert [(r["n"], r["kind"], r.get("pending", False)) for r in rows][:2] == [(1, "assign", False), (2, "plot", True)]
    assert "plot" not in rows[1] and rows[3]["kind"] == "error" and "bogus" in rows[3]["error"]
    assert rows[6]["kind"] == "plotopt"                          # an option that fails only when drawn waits
    assert "pending" not in server.evaluate(Sheet(text=PLOTS))[1]   # other clients get plots drawn


def test_api_plot_draws_one_plot_with_its_option_lines():
    rows = server.plot(server.PlotBody(text=PLOTS, line=6))
    assert [r["n"] for r in rows] == [6, 7] and "svg" in rows[0]["plot"] and "pending" not in rows[0]
    assert rows[1]["kind"] == "error" and "'nope' is not defined" in rows[1]["error"]
    tex = server.plot(server.PlotBody(text=PLOTS, line=6, view="latex"))
    assert "pgfplots" in tex[0]["snippet"] or "axis" in tex[0]["snippet"]
    with pytest.raises(server.HTTPException):
        server.plot(server.PlotBody(text=PLOTS, line=5))


def test_api_plot_keeps_what_it_drew_until_something_it_reads_changes(monkeypatch):
    server._drawn.clear()
    calls = []
    real = server.evaluate_sheet
    monkeypatch.setattr(server, "evaluate_sheet", lambda *a, **k: calls.append(1) or real(*a, **k))
    server.plot(server.PlotBody(text=PLOTS, line=2))
    server.plot(server.PlotBody(text=PLOTS + "z = 9\n", line=2))          # below it: the same plot
    assert len(calls) == 1
    server.plot(server.PlotBody(text=PLOTS.replace("x0 = 2", "x0 = 3"), line=2))
    server.plot(server.PlotBody(text=PLOTS + "'smoot = 2'm\n", line=2))   # a unit is defined for the whole sheet
    assert len(calls) == 3
