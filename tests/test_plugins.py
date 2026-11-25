"""Plugins (#153): `!plugin` blocks and `!pluginvar` lines in a sheet, the edits a plugin's write
makes, where plugins are fetched from and kept, and the endpoints that serve them."""
import json

import pytest

from laconic import plugins
from laconic.blockedit import apply
from laconic.exports import element
from laconic.sheet import evaluate, run



class Client:
    """The few calls these tests make of the server, over HTTP to the one conftest's `server` runs in this
    process (so what a test sets in the environment reaches it), with the standard library only: the
    project does not depend on an HTTP client package, as starlette's TestClient would need."""

    class Response:
        def __init__(self, status, headers, body):
            self.status_code, self.headers, self.content = status, {k.lower(): v for k, v in headers.items()}, body
            self.text = body.decode("utf-8", "replace")

        def json(self):
            return json.loads(self.text)

    def __init__(self, base):
        self.base = base

    def _go(self, method, path, json_body=None):
        import urllib.error
        import urllib.request
        data = None if json_body is None else json.dumps(json_body).encode()
        rq = urllib.request.Request(self.base + path, data=data, method=method,
                                    headers={"content-type": "application/json"} if data is not None else {})
        try:
            with urllib.request.urlopen(rq) as r:
                return self.Response(r.status, dict(r.headers), r.read())
        except urllib.error.HTTPError as e:
            return self.Response(e.code, dict(e.headers), e.read())

    def get(self, path):
        return self._go("GET", path)

    def post(self, path, json=None):
        return self._go("POST", path, {} if json is None else json)

    def delete(self, path):
        return self._go("DELETE", path)

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
    assert m["entry"] == "index.html" and set(m["files"]) == {"index.html", "pipenet.js", "app.js", "pipenet.lens"}


def test_the_pipenet_plugins_own_sheet_reads_and_is_solved():
    m = json.loads((plugins.CHECKOUT / "pipenet" / "manifest.json").read_text(encoding="utf-8"))
    assert m["template"] == "pipenet.lens" and "pipenet.lens" in m["files"]
    text = (plugins.CHECKOUT / "pipenet" / "pipenet.lens").read_text(encoding="utf-8")
    ws = evaluate(text)
    assert not [r for r in ws.results if r.kind == "error"]
    head = next(r for r in ws.results if r.plugin)
    assert head.plugin.outputs == ["A", "L!", "D_h!", "N_fit!", "K_extra!", "el_hx!", "el_pump!", "A_r", "L_r!", "D_r!", "N_fit_r!",
                                   "K_extra_r!", "el_hx_r!", "el_pump_r!", "exchangers!", "pumps!", "valves!", "fit_method!", "solver_method!", "hold_flow!", "∀_target",
                                   "Δp_target"]
    # It ships solved: a stored answer that satisfies its equations here. (Whether the stored result counts
    # as current depends on its inputs' hash, and values a library computes, CoolProp's or a fit's last
    # digits, can differ from one machine to another; the answer itself does not.)
    solver = next(r for r in ws.results if r.solver).solver
    assert solver.record is not None and solver.status in ("valid", "stale")
    residual = next(r for r in ws.results if r.text.startswith("Δp_residual = "))
    import re
    assert all(abs(float(x)) < 1e-6 for x in re.findall(r"-?\d+\.?\d*(?:e-?\d+)?", residual.text.split("=", 1)[1].replace("psi", "")))
    total = next(r for r in ws.results if r.text.startswith("∀_total = "))
    assert total.text == "∀_total = 110 gal/min"
    sent = next(r for r in ws.results if r.pluginvar and "mag" in r.pluginvar.values[0]).pluginvar.values
    assert [v["name"] for v in sent] == ["∀!", "ΣK_seg", "Δp_paths", "∀_r!", "ΣK_r", "Δp_r", "Δp_spur", "Δp_valve", "Δp_circ",
                                         "∀_total", "Δp_pump", "at_wall!", "el_wall!", "el_wall_r!", "solver_state"]
    assert sent[-1]["mag"] in (0, 1)       # the solver's state: solved, current here or not (see above)
    assert sent[0]["unit"] == "gal/min"


@pytest.mark.parametrize("method, first", [(1, 0.3804), (2, 0.1559), (3, 0.3913)])
def test_each_fitting_loss_method_gives_the_segments_their_K(method, first):
    """Crane (L/D * f_T for steel), Hooper 2-K and Darby 3-K on the plugin's sheet, from its own tables."""
    text = (plugins.CHECKOUT / "pipenet" / "pipenet.lens").read_text(encoding="utf-8")
    text = text.replace("  fit_method! = 1\n", f"  fit_method! = {method}\n")
    ws = evaluate(text)
    import re
    k = next(r for r in ws.results if r.text.startswith("ΣK_seg"))
    assert k.kind == "assign" and float(re.search(r"\[\[([\d.]+)\]", k.text).group(1)) == pytest.approx(first, rel=2e-3)


def test_a_sheet_is_compared_with_the_plugins_own():
    original = "!plugin demo\n  A = 1\nT = 90'degF\nf(x) = 2*x\n!root y\n  equation: y = 2\n  #@ result {}\n!pluginvar y\n# a note\n"
    assert plugins.differences(original, original) == {"missing": [], "changed": []}
    same = "!plugin demo\n  A = 99\n  #@ state {}\n# other words\nT   =  90 'degF\nf(x) = 2 * x\n!root y\n  equation: y = 2\n!pluginvar y\nz = 5\n"
    assert plugins.differences(same, original) == {"missing": [], "changed": []}   # spacing, comments, results, additions
    edited = "T = 80'degF\n!root y\n  equation: y = 3\n"
    assert plugins.differences(edited, original) == {"missing": ["f", "!pluginvar y"], "changed": ["T", "!root y"]}


def test_a_sheets_data_sections_are_its_own_and_the_rest_is_checked():
    """Between `# ---- ...` and `# ---- end ...` is data the user replaces (other exchangers, other pumps,
    names of their own): not compared. Outside, the calculation is."""
    original = ("f(x) = 2*x\n# ---- Pump data: paste your own ----\nP = [1, 2]\nP_A = 1\n!pluginvar pumps: P_A\n"
                "# ---- end of the pump data ----\ng(x) = f(x) + idx(P, 1)\n")
    mine = ("f(x) = 2*x\n# ---- Pump data: mine ----\nP = [7, 8, 9]\nMINE = 1\n!pluginvar pumps: MINE\n"
            "# ---- end ----\ng(x) = f(x) + idx(P, 1)\n")
    assert plugins.differences(mine, original) == {"missing": [], "changed": []}
    assert plugins.differences(mine.replace("2*x", "3*x"), original) == {"missing": [], "changed": ["f"]}
    # a section whose end line was lost is no section: what follows it is still checked
    open_ended = mine.replace("# ---- end ----\n", "").replace("f(x) + idx", "f(x) - idx")
    assert plugins.differences(open_ended, original)["changed"] == ["g"]


def test_the_plugins_sheet_keeps_its_data_in_sections_and_its_calculation_outside():
    """The exchangers and pumps are data sections; HX, PUMP, the walls and the solver are not."""
    text = (plugins.CHECKOUT / "pipenet" / "pipenet.lens").read_text(encoding="utf-8")
    parts = plugins._parts(text)
    names = {k[1] for k in parts if k[0] == "def"}
    assert {"HX", "HX_c", "HX_curve", "PUMP", "PUMP_c", "PUMP_curve", "PUMP_sel", "WALL", "clamp", "residual"} <= names
    assert not names & {"HXD_HBH060", "HX_C", "HX_q", "HBH060", "PUMP_C", "PUMP_q", "GRUND_43100A", "GRUND_C1016T"}


def test_a_plugins_sheet_is_offered_with_the_examples_and_checked(cfg, monkeypatch, server):
    monkeypatch.setenv("LENS_PLUGIN_SOURCE", str(plugins.CHECKOUT))
    c = Client(server)
    assert {"name": "pipenet", "title": "Pipe network", "plugin": "pipenet"} in c.get("/api/examples").json()
    assert c.get("/api/plugins/pipenet").json()["template"] is True
    text = c.get("/api/plugins/pipenet/template").text
    assert text.startswith("## Pipe network\n")
    assert c.post("/api/plugins/pipenet/check", json={"text": text}).json() == {"ok": True, "missing": [], "changed": []}
    r = c.post("/api/plugins/pipenet/check", json={"text": text.replace("FIT_Darby = [800,", "FIT_Darby = [900,")}).json()
    assert r["changed"] == ["FIT_Darby"]
    assert c.get("/api/plugins/nope/template").status_code == 404


# ---- the endpoints -------------------------------------------------------------------------

@pytest.fixture()
def client(cfg, monkeypatch, server):
    make(cfg / "src")
    monkeypatch.setenv("LENS_PLUGIN_SOURCE", str(cfg / "src"))
    return Client(server)


def test_the_manifest_endpoint(client):
    assert client.get("/api/plugins/demo").json() == {"ok": True, "name": "demo", "title": "Demo", "version": "1.0",
                                                     "url": "/plugins/demo/index.html", "template": False}
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
    assert plugins.available() == [{"name": "demo", "title": "Demo", "version": "1.0", "description": "A demo", "origin": "", "template": False}]
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


def test_the_settings_endpoints(remote, server):
    from laconic import settings
    c = Client(server)
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


def test_the_upload_endpoint(remote, server):
    import base64
    c = Client(server)
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


def test_the_fonts_may_be_borrowed_by_a_sandboxed_plugin_frame(server):
    c = Client(server)
    assert c.get("/static/fonts/ibm-plex-sans-latin-400-normal.woff2").headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-origin" not in c.get("/static/rows.js").headers


def test_the_plugins_sheet_solves_a_return_laid_out_on_its_own():
    """Its layout has a return of its own (another route, 4" where the supply's spurs are 2"): solved from
    nothing, each path is its supply, its exchanger and its return."""
    import re
    text = (plugins.CHECKOUT / "pipenet" / "pipenet.lens").read_text(encoding="utf-8")
    assert '"ret":"separate"' in text
    text = re.sub(r"\n  #@ result [^\n]*", "", text)
    from laconic.solvesession import solve_all
    solved = solve_all(text, log=lambda m: None)
    ws = evaluate(solved, plots=False)
    assert next(r for r in ws.results if r.solver).solver.current
    sent = {v["name"]: v for r in ws.results if r.pluginvar for v in r.pluginvar.values}
    flat = lambda v: [x[0] for x in v["mag"]]
    assert sum(flat(sent["∀!"])[:8]) == pytest.approx(sum(flat(sent["∀_r!"])[:8]))   # the same water out and back
    residual = next(r for r in ws.results if r.text.startswith("Δp_residual"))
    assert all(abs(float(x)) < 1e-3 for x in re.findall(r"-?\d+\.?\d*(?:e-?\d+)?", residual.text.split("=", 1)[1].replace("psi", "")))


def test_the_plugins_sheet_ships_only_published_exchanger_data():
    """Its exchangers are ClimateMaster's, from a public design guide, to paste other data over; the SWEP
    curves are not for redistribution and must not come back."""
    text = (plugins.CHECKOUT / "pipenet" / "pipenet.lens").read_text(encoding="utf-8")
    assert "SWEP" not in text
    assert "HXD_HBH060 = [7.5, 11.3, 15.0; 2.251, 5.108, 9.784]" in text     # 5.2, 11.8, 22.6 ft over 2.31
    assert "# ---- Exchanger data: paste your own over the lines from here" in text

def test_a_line_that_defines_a_plugins_name_again_is_warned_and_named_to_the_plugin():
    """A sheet older than the plugin writing Δp_target kept its own Δp_target line below the block, which
    replaced the plugin's value: a change made in the plugin never reached the solver."""
    rs = run("!plugin pipenet\n  Δp_target = 0.5 'psi\n  #@ state {}\ny = 2\nΔp_target = 0.1 'psi\n!hide\nΔp_target = 0.2 'psi\n!show\nz = Δp_target")
    assert rs[0].plugin.overridden == [{"name": "Δp_target", "line": 5}, {"name": "Δp_target", "line": 7}]
    assert "written by the pipenet plugin (line 1)" in rs[4].warning and "Delete this line" in rs[4].warning
    assert rs[6].warning and not rs[6].hidden          # shown even under !hide, so it is not missed
    assert rs[3].warning == "" and rs[1].warning == ""   # the block's own line and other lines are fine
    assert rs[8].text == "z = 1379 Pa"                 # 0.2 psi: the last line wins


def test_a_pluginvar_line_can_send_a_list_of_names():
    rs = run("f(x) = x\ng(x) = 2*x\nq = 3\n!pluginvar curves: f, g, q\n!pluginvar curves: f, nope\n!pluginvar curves:")
    assert rs[3].pluginvar.values == [{"name": "curves", "names": ["f", "g", "q"]}]
    assert rs[3].text == "Sent to the plugins: curves, the names f, g, q"
    assert (rs[4].kind, rs[4].error) == ("error", "'nope' is not defined")
    assert rs[5].kind == "error"


def test_the_plugins_sheet_names_its_exchanger_and_pump_curves():
    text = (plugins.CHECKOUT / "pipenet" / "pipenet.lens").read_text(encoding="utf-8")
    sent = [v for r in evaluate(text).results if r.pluginvar for v in r.pluginvar.values if "names" in v]
    assert sent == [{"name": "exchangers", "names": ["HBH060", "HBH009", "HBH006"]},
                    {"name": "pumps", "names": ["GRUND_43100A", "GRUND_43100B", "GRUND_43100C", "GRUND_2699A", "GRUND_2699B",
                                                "GRUND_2699C", "GRUND_1542A", "GRUND_C1016T"]}]


def test_the_plugins_sheet_holds_each_curve_to_its_data_with_walls():
    """A fit holds only between the least and the greatest flow in its data. Past either end the solver's
    HX and PUMP carry on from the end of the fit at WALL (100 psi per gal/min), the way that pushes the
    flow back inside; the curves plotted (HX_curve, GRUND_...) stop at the data."""
    from laconic.parser import parse_expr
    from laconic.sheet import evaluator_at
    text = (plugins.CHECKOUT / "pipenet" / "pipenet.lens").read_text(encoding="utf-8")
    ev = evaluator_at(text, len(text.split("\n")))
    psi = lambda src: ev.eval(parse_expr(src)).to("psi").magnitude
    # the HBH060's three points, 7.5 to 15 gal/min, and a quadratic through them
    assert [psi(f"HX({q}'gal/'min, HBH060)") for q in (7.5, 11.3, 15)] == pytest.approx([2.251, 5.108, 9.784], abs=1e-6)
    assert psi("HX(16'gal/'min, HBH060)") == pytest.approx(9.784 + 100)       # above: the drop climbs
    assert psi("HX(6.5'gal/'min, HBH060)") == pytest.approx(2.251 - 100)      # below: it falls
    assert psi("HX_curve(16'gal/'min, HBH060)") == 0
    # the C1016T, 0.05 to 2.05 gal/min: its head falls past the end and climbs below the start
    end, start = psi("PUMP(2.05'gal/'min, 8)"), psi("PUMP(0.05'gal/'min, 8)")
    assert psi("PUMP(3.05'gal/'min, 8)") == pytest.approx(end - 100)
    assert psi("PUMP(0'gal/'min, 8)") == pytest.approx(start + 5)
    assert psi("GRUND_C1016T(3'gal/'min)") == 0 and psi("GRUND_C1016T(1'gal/'min)") > 0


def test_the_plugins_sheet_takes_regulating_valves_instead_of_or_beside_circulators():
    """The prospective layout: no circulators, a regulating valve on each spur, and a larger main pump."""
    import re
    from laconic.parser import parse_expr
    from laconic.sheet import evaluator_at
    from laconic.solvesession import solve_all
    text = (plugins.CHECKOUT / "pipenet" / "pipenet.lens").read_text(encoding="utf-8")
    ev = evaluator_at(text, len(text.split("\n")))
    q = lambda src: ev.eval(parse_expr(src))
    sg = q("SG_w").magnitude
    assert q("VALVE(20'gal/'min, 10)").to("psi").magnitude == pytest.approx(sg * 4)    # SG (Q/Cv)^2
    assert q("VALVE(20'gal/'min, 0)").magnitude == 0 and q("PUMP_sel(20'gal/'min, 0)").magnitude == 0
    assert (q("PUMP_sel(20'gal/'min, 3)") - q("GRUND_43100C(20'gal/'min)")).magnitude == 0
    n = len(re.search(r"\n  pumps! = \[([^\n]*)\]", text).group(1).split(";"))
    text = re.sub(r"\n  pumps! = \[[^\n]*", "\n  pumps! = [" + "; ".join(["0"] * n) + "]", text)
    text = re.sub(r"\n  valves! = \[[^\n]*", "\n  valves! = [" + "; ".join(["15"] * n) + "]", text)
    # (8 psi: within the HBH060's data, 7.5 to 15 gal/min; more would push every spur against its wall)
    text = re.sub(r"\n  Δp_target = [^\n]*", "\n  Δp_target = 8 'psi", text)
    text = text.replace("\n  hold_flow! = 1\n", "\n  hold_flow! = 0\n")      # the larger pump holds its pressure difference
    text = re.sub(r"\n  #@ result [^\n]*", "", text)
    ws = evaluate(solve_all(text, log=lambda m: None), plots=False)
    assert next(r for r in ws.results if r.solver).solver.current
    sent = {v["name"]: [x[0] for x in v["mag"]] for r in ws.results if r.pluginvar for v in r.pluginvar.values
            if "mag" in v and isinstance(v["mag"], list)}
    assert sent["Δp_circ"] == [0] * n and all(dp > 0.5 for dp in sent["Δp_valve"])


def test_the_plugins_sheet_takes_in_line_resistances_and_pumps_on_any_segment():
    """el_hx! and el_pump!: a resistance on a segment takes pressure from the path through it, an in-line
    pump adds it; with the pump holding a total flow, the others take up what the one spur loses or gains."""
    import re
    from laconic.solvesession import solve
    text = re.sub(r"\n  #@ result [^\n]*", "", (plugins.CHECKOUT / "pipenet" / "pipenet.lens").read_text(encoding="utf-8"))
    n = len(re.search(r"\n  el_hx! = \[([^\n]*)\]", text).group(1).split(";"))
    line = next(i for i, l in enumerate(text.split("\n"), 1) if l.startswith("!root"))

    def flows(name, first):
        t = re.sub(r"\n  " + re.escape(name) + r" = \[[^\n]*", "\n  " + name + " = [" + "; ".join([first] + ["0"] * (n - 1)) + "]", text)
        rec = solve(t, line, log=lambda *a: None)
        assert rec["ok"], rec["message"]
        return [x[0] * 15850.32 for x in rec["record"]["values"][0]["mag"]]
    plain, resisted, pumped = flows("el_hx!", "0"), flows("el_hx!", "1"), flows("el_pump!", "1")
    assert resisted[0] < plain[0] - 1 and all(r > p for r, p in zip(resisted[1:], plain[1:]))
    assert pumped[0] > plain[0] + 0.5
    assert sum(plain) == pytest.approx(110, rel=1e-6) and sum(resisted) == pytest.approx(110, rel=1e-6)
