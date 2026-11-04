"""Plugins (#153): `!plugin` blocks and `!pluginvar` lines in a sheet, the edits a plugin's write
makes, where plugins are fetched from and kept, and the endpoints that serve them."""
import json

import pytest

from laconic import plugins
from laconic.blockedit import apply
from laconic.exports import element
from laconic.sheet import evaluate, run


def kinds(text):
    return [(r.kind, r.error) for r in run(text)]


# ---- in the sheet --------------------------------------------------------------------------

def test_a_plugin_block_defines_the_names_its_lines_assign():
    rs = run("!plugin pipenet\n  A = [1, 0; 1, 1]\n  L! = [1; 2] * 'm\n  #@ state {\"v\": 1}\nB = 2 * L!")
    assert [r.kind for r in rs] == ["plugin", "assign", "assign", "pluginline", "assign"]
    assert rs[0].plugin.name == "pipenet" and rs[0].plugin.outputs == ["A", "L!"]
    assert rs[0].plugin.state == {"v": 1} and rs[0].end == 4
    assert rs[4].text.startswith("B = [[2]")


def test_a_plugin_block_works_without_a_state_line_or_any_lines():
    rs = run("!plugin pipenet\nx = 1")
    assert rs[0].kind == "plugin" and rs[0].plugin.state is None and rs[0].plugin.outputs == []
    assert rs[0].text == "plugin pipenet"


def test_a_plugin_block_keeps_its_comments_and_refuses_other_lines():
    rs = run("!plugin pipenet\n  # drawn by hand\n  1 + 1\n  A = 2")
    assert [r.kind for r in rs] == ["plugin", "comment", "error", "assign"]
    assert "name = value" in rs[2].error


def test_a_plugin_needs_a_proper_name():
    assert kinds("!plugin")[0] == ("error", "A plugin block reads `!plugin name`, e.g. `!plugin pipenet`")
    k, msg = kinds("!plugin Pipe/Net")[0]
    assert k == "error" and "not a plugin name" in msg


def test_an_unreadable_state_is_a_warning_and_the_plugin_starts_empty():
    r = run("!plugin pipenet\n  #@ state {oops}")[0]
    assert r.kind == "plugin" and r.plugin.state is None and "could not be read" in r.warning


def test_a_pluginvar_line_sends_the_values_as_they_are_there():
    rs = run("x = 2'ft\ny = x * 2\nM = [1, 2; 3, 4]\n!pluginvar x, y, M\nx = 3")
    v = rs[3].pluginvar.values
    assert v[0] == {"name": "x", "unit": "ft", "shape": [], "mag": 2.0}         # as the sheet holds it
    assert v[1] == {"name": "y", "unit": "m", "shape": [], "mag": pytest.approx(1.2192)}
    v = v[1:]
    assert v[1] == {"name": "M", "unit": "", "shape": [2, 2], "mag": [[1, 2], [3, 4]]}
    assert rs[3].text == "Sent to the plugins: x, y, M"


def test_a_pluginvar_line_says_what_it_cannot_send():
    assert kinds("!pluginvar")[0][0] == "error"
    assert kinds("!pluginvar 2*x")[0][0] == "error"
    assert kinds("!pluginvar y")[0] == ("error", "'y' is not defined")
    assert "complex" in kinds("z = 3 + 4i\n!pluginvar z")[1][1]
    assert kinds("$a\n!pluginvar a")[1][0] == "error"   # a symbol has no number to send


def test_a_pluginvar_line_is_marked_stale_with_an_out_of_date_solver_result():
    rs = run("x = 1\n!root x\n  equation: x = 2\n!pluginvar x")
    assert rs[3].kind == "pluginvar" and rs[3].stale


def test_a_rename_reaches_the_names_in_plugin_lines_and_pluginvar_lines():
    from laconic.rename import rename
    text = "!plugin pipenet\n  L! = [1; 2] * 'm\nQ = 2 * L!\n!pluginvar L!, Q"
    out = apply(text, rename(text, "L!", "Len")[0])
    assert out == "!plugin pipenet\n  Len = [1; 2] * 'm\nQ = 2 * Len\n!pluginvar Len, Q"


def test_exports_keep_the_plugin_lines_as_math_and_the_commands_as_source():
    rs = run("!plugin pipenet\n  A = 2\n  #@ state {}\n!pluginvar A")
    els = [element(r, commands=True) for r in rs]
    assert type(els[0]).__name__ == "Source" and type(els[1]).__name__ == "Math"
    assert els[2] is None and type(els[3]).__name__ == "Source"
    assert [element(r) for r in rs][0] is None


# ---- writing into the block ------------------------------------------------------------------

def test_a_write_replaces_its_lines_in_place_and_adds_new_ones_before_the_state():
    text = "!plugin pipenet\n  A = 1\n  # kept\n  #@ state {\"v\":1}\nx = A\n"
    out = apply(text, plugins.edits(text, 1, {"v": 2, "name": "ü"}, {"A": "[1; 2]", "B": "3 * 'm"}))
    assert out == ("!plugin pipenet\n  A = [1; 2]\n  # kept\n  B = 3 * 'm\n  #@ state {\"v\":2,\"name\":\"ü\"}\nx = A\n")


def test_a_write_into_an_empty_block_adds_its_lines_and_keeps_crlf():
    text = "!plugin pipenet\r\nx = 1\r\n"
    out = apply(text, plugins.edits(text, 1, {"v": 1}, {"A": "2"}))
    assert out == "!plugin pipenet\r\n  A = 2\r\n  #@ state {\"v\":1}\r\nx = 1\r\n"


def test_a_write_with_nothing_new_changes_nothing():
    text = "!plugin pipenet\n  A = 2\n  #@ state {\"v\":1}"
    assert plugins.edits(text, 1, {"v": 1}, {"A": "2"}) == []


@pytest.mark.parametrize("outputs", [{"~g": "1"}, {"2x": "1"}, {"A": "1\nB = 2"}, {"A": "[1; "}, {"A": ""}])
def test_a_write_takes_plain_names_and_one_line_of_math_only(outputs):
    with pytest.raises(plugins.PluginError):
        plugins.edits("!plugin pipenet\n", 1, None, outputs)


def test_a_write_needs_a_plugin_block():
    with pytest.raises(plugins.PluginError):
        plugins.edits("x = 1\n!plot x, x = 0 .. 1", 2, {}, {})
    with pytest.raises(plugins.PluginError):
        plugins.edits("!plugin pipenet\n", 1, ["not", "a", "dict"], {})


# ---- where plugins come from -------------------------------------------------------------------

def make(folder, name="demo", files=None, manifest=None):
    files = files if files is not None else {"index.html": "<p>hi</p>", "app.js": "1"}
    d = folder / name
    d.mkdir(parents=True)
    for f, body in files.items():
        (d / f).write_text(body, encoding="utf-8")
    m = manifest if manifest is not None else {"title": "Demo", "version": "1.0", "entry": "index.html", "files": list(files)}
    (d / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    return d


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("LENS_CONFIG_DIR", str(tmp_path / "cfg"))
    return tmp_path


def test_names(cfg):
    assert plugins.valid_name("pipenet") and plugins.valid_name("pipe-net_2")
    assert not any(plugins.valid_name(n) for n in ("", "Pipenet", "2net", "../x", "a/b", "x" * 41))


def test_a_folder_source_is_read_in_place(cfg, monkeypatch):
    make(cfg / "src")
    monkeypatch.setenv("LENS_PLUGIN_SOURCE", str(cfg / "src"))
    assert plugins.fetch("demo")["title"] == "Demo"
    assert plugins.file("demo", "app.js") == (b"1", "text/javascript")
    assert not (cfg / "cfg" / "plugins").exists()


def test_a_remote_plugin_is_fetched_once_kept_and_fetched_again_when_asked(cfg, monkeypatch):
    make(cfg / "web")
    asked = []

    def fetch(url, timeout=None):
        asked.append(url)
        path = cfg / "web" / url.removeprefix("https://example.org/p/")
        if not path.is_file():
            raise OSError("HTTP Error 404: Not Found")
        return path.read_bytes()
    monkeypatch.setenv("LENS_PLUGIN_SOURCE", "https://example.org/p")
    monkeypatch.setattr(plugins, "fetcher", fetch)
    assert plugins.fetch("demo")["entry"] == "index.html"
    assert asked == [f"https://example.org/p/demo/{f}" for f in ("manifest.json", "index.html", "app.js")]
    assert (cfg / "cfg" / "plugins" / "demo" / "app.js").read_text() == "1"
    plugins.fetch("demo")
    assert len(asked) == 3                      # kept: not fetched again
    (cfg / "web" / "demo" / "app.js").write_text("2")
    plugins.fetch("demo", fresh=True)
    assert plugins.file("demo", "app.js")[0] == b"2"
    with pytest.raises(plugins.PluginError, match="There is no plugin 'nope'"):
        plugins.fetch("nope")


def test_a_failed_fetch_keeps_the_copy_there_was(cfg, monkeypatch):
    make(cfg / "web")
    monkeypatch.setenv("LENS_PLUGIN_SOURCE", "https://example.org/p")
    monkeypatch.setattr(plugins, "fetcher", lambda url, timeout=None: (cfg / "web" / url.removeprefix("https://example.org/p/")).read_bytes())
    plugins.fetch("demo")

    def offline(url, timeout=None):
        raise OSError("offline")
    monkeypatch.setattr(plugins, "fetcher", offline)
    with pytest.raises(plugins.PluginError, match="could not be fetched"):
        plugins.fetch("demo", fresh=True)
    assert plugins.fetch("demo")["title"] == "Demo"
    assert plugins.file("demo", "index.html")[0] == b"<p>hi</p>"


@pytest.mark.parametrize("manifest", [{"files": []}, {"files": ["index.html"], "entry": "app.js"},
                                       {"files": ["../x.html"]}, {"files": ["index.html", "run.exe"]}, ["index.html"]])
def test_a_manifest_must_list_its_files_and_page(cfg, monkeypatch, manifest):
    make(cfg / "src", files={"index.html": "x"}, manifest=manifest)
    monkeypatch.setenv("LENS_PLUGIN_SOURCE", str(cfg / "src"))
    with pytest.raises(plugins.PluginError):
        plugins.fetch("demo")


def test_only_the_listed_files_are_served(cfg, monkeypatch):
    d = make(cfg / "src")
    (d / "secret.js").write_text("no")
    monkeypatch.setenv("LENS_PLUGIN_SOURCE", str(cfg / "src"))
    for bad in ("secret.js", "../demo/app.js", ".hidden", ""):
        with pytest.raises(plugins.PluginError):
            plugins.file("demo", bad)


def test_the_pipenet_plugin_in_this_checkout_is_a_valid_plugin(monkeypatch):
    monkeypatch.setenv("LENS_PLUGIN_SOURCE", str(plugins.CHECKOUT))
    m = plugins.fetch("pipenet")
    assert m["entry"] == "index.html" and set(m["files"]) == {"index.html", "pipenet.js", "app.js"}


def test_the_pipenet_example_sheet_reads_and_is_solved():
    from pathlib import Path
    text = (Path(plugins.__file__).parent / "examples" / "pipenet.lens").read_text(encoding="utf-8")
    ws = evaluate(text)
    assert not [r for r in ws.results if r.kind == "error"]
    head = next(r for r in ws.results if r.plugin)
    assert head.plugin.outputs == ["A", "L!", "D_h!", "K_fT!", "exchangers!", "speeds!"]
    assert next(r for r in ws.results if r.solver).solver.current
    sent = next(r for r in ws.results if r.pluginvar).pluginvar.values
    assert [v["name"] for v in sent] == ["∀!", "Δp_paths", "Δp_spur"] and sent[0]["unit"] == "gal/min"


# ---- the endpoints -------------------------------------------------------------------------

@pytest.fixture()
def client(cfg, monkeypatch):
    from fastapi.testclient import TestClient
    from laconic.server import app
    make(cfg / "src")
    monkeypatch.setenv("LENS_PLUGIN_SOURCE", str(cfg / "src"))
    return TestClient(app)


def test_the_manifest_endpoint(client):
    assert client.get("/api/plugins/demo").json() == {"ok": True, "name": "demo", "title": "Demo", "version": "1.0",
                                                     "url": "/plugins/demo/index.html"}
    r = client.get("/api/plugins/nope").json()
    assert r["ok"] is False and "no plugin 'nope'" in r["error"]


def test_plugin_files_are_sandboxed_and_only_listed_ones_are_served(client):
    r = client.get("/plugins/demo/index.html")
    assert r.status_code == 200 and r.text == "<p>hi</p>" and r.headers["content-type"].startswith("text/html")
    assert r.headers["content-security-policy"].startswith("sandbox allow-scripts;")
    assert "connect-src" not in r.headers["content-security-policy"]   # default-src 'none' covers it
    assert client.get("/plugins/demo/nothere.js").status_code == 404
    assert client.get("/plugins/demo/..%2F..%2Fsettings.json").status_code == 404


def test_the_write_endpoint_answers_edits(client):
    text = "!plugin demo\nx = 1"
    r = client.post("/api/pluginwrite", json={"text": text, "line": 1, "state": {"a": 1}, "outputs": {"A": "2"}}).json()
    assert r["ok"] and r["edits"] == [{"from": 12, "to": 12, "insert": "\n  A = 2\n  #@ state {\"a\":1}"}]
    r = client.post("/api/pluginwrite", json={"text": text, "line": 2, "outputs": {"A": "2"}}).json()
    assert r == {"ok": False, "error": "Line 2 is not a plugin block"}


# ---- installing, removing and automatic downloads --------------------------------------------

@pytest.fixture()
def remote(cfg, monkeypatch):
    """A stand-in GitHub serving the folder `web`, with an index of its plugins."""
    make(cfg / "web")
    (cfg / "web" / "index.json").write_text(json.dumps({"plugins": [
        {"name": "demo", "title": "Demo", "version": "1.0", "description": "A demo"}, {"name": "Bad/name"}]}))
    asked = []

    def fetch(url, timeout=None):
        asked.append(url)
        path = cfg / "web" / url.removeprefix("https://example.org/p/")
        if not path.is_file():
            raise OSError("HTTP Error 404: Not Found")
        return path.read_bytes()
    monkeypatch.setenv("LENS_PLUGIN_SOURCE", "https://example.org/p")
    monkeypatch.setattr(plugins, "fetcher", fetch)
    return asked


def test_with_automatic_downloads_off_a_sheet_fetches_nothing_but_installing_does(remote):
    from laconic import settings
    settings.save_prefs({"autoPlugins": False})
    assert not plugins.auto()
    with pytest.raises(plugins.NotInstalled, match="automatic downloads are off"):
        plugins.fetch("demo")
    assert remote == []
    assert plugins.fetch("demo", asked=True)["title"] == "Demo"
    assert plugins.fetch("demo")["title"] == "Demo"      # kept: a sheet may use it now
    settings.save_prefs({"autoPlugins": None})
    assert plugins.auto()


def test_the_installed_and_available_plugins_and_removing_one(remote):
    assert plugins.installed() == []
    assert plugins.available() == [{"name": "demo", "title": "Demo", "version": "1.0", "description": "A demo", "origin": ""}]
    plugins.fetch("demo")
    assert [p["name"] for p in plugins.installed()] == ["demo"]
    plugins.remove("demo")
    assert plugins.installed() == []
    with pytest.raises(plugins.PluginError, match="not installed"):
        plugins.remove("demo")


def test_nothing_is_removed_from_a_folder_source(cfg, monkeypatch):
    make(cfg / "src")
    monkeypatch.setenv("LENS_PLUGIN_SOURCE", str(cfg / "src"))
    assert [p["name"] for p in plugins.installed()] == ["demo"] == [p["name"] for p in plugins.available()]
    with pytest.raises(plugins.PluginError, match="nothing kept to remove"):
        plugins.remove("demo")
    assert (cfg / "src" / "demo").is_dir()


def test_the_list_of_plugins_says_so_when_it_cannot_be_had(remote, monkeypatch):
    def offline(url, timeout=None):
        raise OSError("offline")
    monkeypatch.setattr(plugins, "fetcher", offline)
    with pytest.raises(plugins.PluginError, match="could not be fetched"):
        plugins.available()


def test_the_index_of_this_checkouts_plugins_matches_their_manifests():
    index = json.loads((plugins.CHECKOUT / "index.json").read_text(encoding="utf-8"))["plugins"]
    found = sorted(d.name for d in plugins.CHECKOUT.iterdir() if (d / "manifest.json").is_file())
    assert [p["name"] for p in index] == found
    for p in index:
        m = json.loads((plugins.CHECKOUT / p["name"] / "manifest.json").read_text(encoding="utf-8"))
        assert {k: m[k] for k in ("name", "title", "version", "description")} == p


def test_the_settings_endpoints(remote):
    from fastapi.testclient import TestClient
    from laconic import settings
    from laconic.server import app
    c = TestClient(app)
    assert c.get("/api/plugins").json() == {"auto": True, "folder": None, "installed": []}
    assert c.get("/api/pluginindex").json()["plugins"][0]["name"] == "demo"
    settings.save_prefs({"autoPlugins": False})
    r = c.get("/api/plugins/demo").json()
    assert r["ok"] is False and r["notInstalled"] is True
    assert c.post("/api/plugins/demo/install").json() == {"ok": True, "name": "demo", "title": "Demo", "version": "1.0"}
    assert c.get("/api/plugins/demo").json()["ok"] is True
    assert [p["name"] for p in c.get("/api/plugins").json()["installed"]] == ["demo"]
    assert c.delete("/api/plugins/demo").json() == {"ok": True}
    assert c.delete("/api/plugins/demo").json()["ok"] is False
    assert c.post("/api/plugins/nope/install").json()["ok"] is False
    settings.save_prefs({"autoPlugins": None})


# ---- installing from a folder (a plugin that is not on GitHub) ----------------------------------

def test_a_plugin_folder_is_installed_and_never_fetched_over(remote, cfg):
    d = make(cfg / "mine", name="local")
    m = plugins.install_folder(d)
    assert m["origin"] == "folder" and (cfg / "cfg" / "plugins" / "local" / "app.js").read_text() == "1"
    assert [(p["name"], p["origin"]) for p in plugins.installed()] == [("local", "folder")]
    assert plugins.fetch("local", fresh=True)["title"] == "Demo"     # Reload: kept, not looked for on GitHub
    assert not any("local" in u for u in remote)
    plugins.remove("local")
    assert plugins.installed() == []


def test_a_plugin_folder_takes_the_manifests_name_and_must_be_whole(remote, cfg):
    d = make(cfg / "mine", name="folder-name", manifest={"name": "real", "entry": "index.html", "files": ["index.html", "app.js"]})
    plugins.install_folder(d)
    assert [p["name"] for p in plugins.installed()] == ["real"]
    (d / "app.js").unlink()
    with pytest.raises(plugins.PluginError, match="lists app.js, which the folder does not have"):
        plugins.install_folder(d)
    with pytest.raises(plugins.PluginError, match="no manifest.json"):
        plugins.install_folder(cfg / "mine")
    bad = make(cfg / "mine", name="Bad Name", manifest={"entry": "index.html", "files": ["index.html"]})
    with pytest.raises(plugins.PluginError, match="not a plugin name"):
        plugins.install_folder(bad)


def test_the_command_line_installs_a_plugin_folder(remote, cfg, capsys, monkeypatch):
    import sys
    from laconic.__main__ import main
    d = make(cfg / "mine", name="local")
    monkeypatch.setattr(sys, "argv", ["lens", "--install-plugin", str(d)])
    main()
    assert "installed Demo (local)" in capsys.readouterr().out
    assert [p["name"] for p in plugins.installed()] == ["local"]
    monkeypatch.setattr(sys, "argv", ["lens", "--install-plugin", str(cfg / "nowhere")])
    with pytest.raises(SystemExit, match="no manifest.json"):
        main()


def test_the_upload_endpoint(remote):
    import base64
    from fastapi.testclient import TestClient
    from laconic.server import app
    c = TestClient(app)
    b64 = lambda s: base64.b64encode(s.encode()).decode()
    files = {"manifest.json": b64(json.dumps({"title": "Up", "entry": "index.html", "files": ["index.html"]})), "index.html": b64("<p>")}
    assert c.post("/api/pluginupload", json={"name": "up", "files": files}).json() == {"ok": True, "name": "up", "title": "Up", "version": ""}
    assert c.get("/api/plugins/up").json()["ok"] is True
    assert c.get("/plugins/up/index.html").text == "<p>"
    r = c.post("/api/pluginupload", json={"name": "up", "files": {"index.html": b64("x")}}).json()
    assert r["ok"] is False and "no manifest.json" in r["error"]
    assert c.post("/api/pluginupload", json={"name": "up", "files": {"manifest.json": "%%%"}}).json()["ok"] is False


def test_a_folder_source_takes_no_installs(cfg, monkeypatch):
    make(cfg / "src")
    monkeypatch.setenv("LENS_PLUGIN_SOURCE", str(cfg / "src"))
    with pytest.raises(plugins.PluginError, match="put the plugin's folder there"):
        plugins.install_folder(make(cfg / "mine", name="other"))
