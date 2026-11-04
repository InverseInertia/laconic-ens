"""Plugins (#153): a page a sheet opens with `!plugin name`, fetched the first time a sheet asks for it.

A plugin is a folder holding `manifest.json` and the files it lists (an HTML page, its scripts and
styles). The page runs it in a sandboxed frame with no access to LENS, the network or the user's
files; it talks to the page only by messages (static/plugins.js):

    page -> plugin   {type: "lens:update", state, inputs: [{name, unit, shape, mag}], outputs}
    plugin -> page   {type: "lens:ready"}
                     {type: "lens:write", state, outputs: {name: "expression"}}
                     {type: "lens:preview", svg}

A write becomes edits to the plugin's own block (`edits`, through the block editor): its `name =
value` lines and its `#@ state {...}` line. The sheet runs those lines as it runs any other, so it
needs no plugin to calculate, and the plugin needs no sheet to draw. `!pluginvar a, b` lines send
the sheet's values back.

Where plugins come from (`source()`):

- `LENS_PLUGIN_SOURCE`, a folder or an https:// address, when it is set;
- the `plugins/` folder of a source checkout (a `0+dev` version), so a plugin can be worked on in place;
- otherwise this repository's `plugins/` folder on GitHub. A fetched plugin is kept under the
  settings folder (`settings.config_dir() / "plugins"`) and fetched again only when asked to
  (`fetch(name, fresh=True)`, the page's Reload).

Nothing is fetched until a sheet with a `!plugin` line is opened in the page; evaluating a sheet,
exporting it or running it from the command line never fetches anything. With the `autoPlugins`
preference off (Settings → Plugins), a sheet does not fetch a plugin either: only installing it
does (`fetch(name, asked=True)`, from Settings or the block's Install button). Settings lists the
plugins kept here (`installed`), those the source offers (`available`, from its `index.json`), and
removes one (`remove`). The network is the `fetcher` seam, so the tests run without one."""
import json
import os
import re
import shutil
import tempfile
import threading
from pathlib import Path

from ._version import __version__

REPO = "InverseInertia/laconic-ens"
REMOTE = f"https://raw.githubusercontent.com/{REPO}/main/plugins"
CHECKOUT = Path(__file__).resolve().parent.parent / "plugins"
TIMEOUT = 15.0
MAX_FILE = 2_000_000          # bytes; a plugin is a page, not a dataset
_NAME = re.compile(r"[a-z][a-z0-9_-]{0,39}\Z")
_FILE = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,79}\Z")   # a file name: no folders, no leading dot
_TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json",
          ".svg": "image/svg+xml", ".png": "image/png", ".woff2": "font/woff2"}
_lock = threading.Lock()

# Served with every plugin file. The frame is sandboxed by the page as well (`sandbox="allow-scripts"`,
# so it has an origin of its own and cannot reach LENS's endpoints or storage); this keeps it so when
# a file is opened on its own, and stops it fetching anything, here or elsewhere.
CSP = ("sandbox allow-scripts; default-src 'none'; script-src 'self' 'unsafe-inline'; "
       "style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'")


class PluginError(Exception):
    pass


def valid_name(name):
    """A plugin's name: lower-case letters, digits, `-` and `_`, starting with a letter."""
    return bool(_NAME.match(name or ""))


def source():
    """Where plugins are fetched from: a folder (Path) or an https:// address (str)."""
    env = os.environ.get("LENS_PLUGIN_SOURCE")
    if env:
        return env.rstrip("/") if env.startswith(("https://", "http://")) else Path(env)
    if "dev" in __version__ and CHECKOUT.is_dir():
        return CHECKOUT
    return REMOTE


def cache_dir():
    from . import settings
    return settings.config_dir() / "plugins"


def _http(url, timeout=TIMEOUT):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "LENS plugin fetch"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise PluginError(f"{url} is larger than a plugin file may be")
    return data


fetcher = _http   # the network seam: url -> bytes


def _read(src, name, file):
    if isinstance(src, Path):
        path = src / name / file
        if not path.is_file():
            raise PluginError(f"There is no plugin '{name}' in {src}" if file == "manifest.json"
                              else f"The plugin '{name}' lists {file}, which is missing")
        return path.read_bytes()
    try:
        return fetcher(f"{src}/{name}/{file}")
    except PluginError:
        raise
    except Exception as e:
        if file == "manifest.json" and "404" in str(e):
            raise PluginError(f"There is no plugin '{name}'") from None
        raise PluginError(f"The plugin '{name}' could not be fetched: {e}") from None


def _manifest(data, name):
    try:
        m = json.loads(data)
    except ValueError:
        raise PluginError(f"The plugin '{name}' has a manifest that is not JSON") from None
    files = m.get("files") if isinstance(m, dict) else None
    entry = m.get("entry", "index.html") if isinstance(m, dict) else None
    if not isinstance(files, list) or not files or not all(isinstance(f, str) and _FILE.match(f) for f in files):
        raise PluginError(f"The plugin '{name}' has a manifest without a list of files")
    if entry not in files or Path(entry).suffix != ".html":
        raise PluginError(f"The plugin '{name}' names no page to open (its entry)")
    if any(Path(f).suffix not in _TYPES for f in files):
        raise PluginError(f"The plugin '{name}' lists a kind of file plugins cannot have")
    return m


def _local(name):
    """The folder a plugin is served from without fetching: the source itself when it is a folder."""
    src = source()
    return src / name if isinstance(src, Path) else cache_dir() / name


class NotInstalled(PluginError):
    """A sheet asked for a plugin that is not kept here while automatic downloads are off."""


def auto():
    """Whether a sheet may fetch a plugin it asks for (the `autoPlugins` preference, on by default)."""
    from . import settings
    return settings.load()["prefs"].get("autoPlugins") is not False


def fetch(name, fresh=False, asked=False):
    """The plugin's manifest (a dict, with `files` and `entry`), fetched first if need be. A plugin
    in a source folder is read in place, every time. Without `asked` (the user installing it), a
    plugin not kept here is fetched only while automatic downloads are on, else NotInstalled.
    Raises PluginError."""
    if not valid_name(name):
        raise PluginError(f"'{name}' is not a plugin name")
    src = source()
    if isinstance(src, Path):
        return _manifest(_read(src, name, "manifest.json"), name)
    with _lock:
        here = cache_dir() / name
        kept = None
        if (here / "manifest.json").is_file():
            try:
                kept = _manifest((here / "manifest.json").read_bytes(), name)
            except PluginError:
                pass   # a broken copy: fetch it again
        # one installed from a folder is never fetched over: there may be no such plugin to fetch
        if kept is not None and (not fresh or kept.get("origin") == "folder"):
            return kept
        if not asked and not (here / "manifest.json").is_file() and not auto():
            raise NotInstalled(f"The plugin '{name}' is not installed, and automatic downloads are off. "
                               "Install it here or under Settings → Plugins")
        m = _manifest(_read(src, name, "manifest.json"), name)
        return _keep(name, m, lambda f: _read(src, name, f))


def _keep(name, m, read, origin=None):
    """Keep plugin `name` (manifest `m`, each listed file's bytes from `read`) in the cache, replacing
    any copy only once every file is in hand. `origin`: "folder" for one installed from a folder."""
    here = cache_dir() / name
    here.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{name}-", dir=here.parent))
    m = {k: v for k, v in m.items() if k != "origin"}
    if origin:
        m["origin"] = origin
    try:
        for f in m["files"]:
            data = read(f)
            if len(data) > MAX_FILE:
                raise PluginError(f"{f} is larger than a plugin file may be")
            (tmp / f).write_bytes(data)
        (tmp / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
        if here.exists():
            shutil.rmtree(here)
        tmp.rename(here)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
    return m


def install_files(files, name=None):
    """Install a plugin from its files, {file name: bytes} with its `manifest.json` among them (a folder
    the user picked, or `install_folder`). Its name is the manifest's `name`, else `name` (the
    folder's). It is kept as any fetched plugin is, marked as installed from a folder, so it is
    never fetched over. Returns its manifest. Raises PluginError."""
    if "manifest.json" not in files:
        raise PluginError("That folder has no manifest.json, so it is not a plugin")
    try:
        given = json.loads(files["manifest.json"])
    except ValueError:
        raise PluginError("That folder's manifest.json is not JSON") from None
    name = given.get("name") if isinstance(given, dict) and given.get("name") else name
    if not valid_name(name):
        raise PluginError(f"'{name}' is not a plugin name: lower-case letters, digits, - and _, starting with a letter")
    if isinstance(source(), Path):
        raise PluginError(f"Plugins are read from the folder {source()}: put the plugin's folder there instead")
    m = _manifest(files["manifest.json"], name)
    missing = [f for f in m["files"] if f not in files]
    if missing:
        raise PluginError(f"The plugin '{name}' lists {', '.join(missing)}, which the folder does not have")
    with _lock:
        return _keep(name, m, lambda f: files[f], origin="folder")


def install_folder(path):
    """Install the plugin in folder `path` (`lens --install-plugin DIR`). Returns its manifest."""
    path = Path(path)
    if not (path / "manifest.json").is_file():
        raise PluginError(f"{path} has no manifest.json, so it is not a plugin folder")
    files = {f.name: f.read_bytes() for f in path.iterdir() if f.is_file() and _FILE.match(f.name)}
    files["manifest.json"] = (path / "manifest.json").read_bytes()
    return install_files(files, name=path.name)


def _summary(m, name):
    return {"name": name, "title": m.get("title", name), "version": str(m.get("version", "")),
            "description": m.get("description", ""), "origin": m.get("origin", "")}


def installed():
    """The plugins kept here, by name: [{name, title, version, description}]. For a folder source,
    the plugins in that folder (they are read in place, so there is nothing else to keep)."""
    src = source()
    root = src if isinstance(src, Path) else cache_dir()
    out = []
    if root.is_dir():
        for d in sorted(root.iterdir()):
            if not valid_name(d.name) or not (d / "manifest.json").is_file():
                continue
            try:
                out.append(_summary(_manifest((d / "manifest.json").read_bytes(), d.name), d.name))
            except PluginError:
                continue
    return out


def available():
    """The plugins the source offers, from its `index.json`: [{name, title, version, description}].
    Raises PluginError when it cannot be read (offline)."""
    src = source()
    if isinstance(src, Path):
        return installed()
    try:
        data = json.loads(fetcher(f"{src}/index.json"))
    except PluginError:
        raise
    except Exception as e:
        raise PluginError(f"The list of plugins could not be fetched: {e}") from None
    items = data.get("plugins") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise PluginError("The list of plugins could not be read")
    return [_summary(p, p["name"]) for p in items if isinstance(p, dict) and valid_name(p.get("name"))]


def remove(name):
    """Forget a plugin kept here; a sheet that asks for it fetches it again (if downloads are on)."""
    if not valid_name(name):
        raise PluginError(f"'{name}' is not a plugin name")
    if isinstance(source(), Path):
        raise PluginError(f"Plugins are read from the folder {source()}, so there is nothing kept to remove")
    here = cache_dir() / name
    if not here.is_dir():
        raise PluginError(f"The plugin '{name}' is not installed")
    with _lock:
        shutil.rmtree(here)


def file(name, path):
    """(bytes, content type) of one file of a plugin that was fetched, or PluginError. Only the
    files its manifest lists are served."""
    if not valid_name(name) or not _FILE.match(path or ""):
        raise PluginError("No such plugin file")
    here = _local(name)
    try:
        m = _manifest((here / "manifest.json").read_bytes(), name)
    except OSError:
        raise PluginError(f"The plugin '{name}' has not been fetched") from None
    if path not in m["files"] and path != "manifest.json":
        raise PluginError("No such plugin file")
    try:
        return (here / path).read_bytes(), _TYPES.get(Path(path).suffix, "application/json")
    except OSError:
        raise PluginError("No such plugin file") from None


def _expression(name, expr):
    """Check one output line a plugin wants written: a variable name and an expression that parses."""
    from .parser import parse_expr
    from .sheettext import is_name
    if not isinstance(name, str) or not is_name(name) or name.startswith("~"):
        raise PluginError(f"A plugin may define plain variable names only, not {name!r}")
    if not isinstance(expr, str) or not expr.strip() or "\n" in expr or "\r" in expr or len(expr) > 200_000:
        raise PluginError(f"The plugin gave {name} a value that is not one line")
    try:
        parse_expr(expr)
    except Exception as e:
        raise PluginError(f"The plugin gave {name} a value that does not read: {e}") from None
    return expr.strip()


def edits(text, line, state=None, outputs=None):
    """The edits that write a plugin's `state` (a dict) and `outputs` ({name: expression}, in order)
    into its block on `line`: each name's line replaced where it is or added, the state line last.
    Raises PluginError for a line that is no plugin block or an output that is not a line of math."""
    from .blockedit import BlockEditor
    ed = BlockEditor(text, line)
    if ed.kind != "plugin":
        raise PluginError(f"Line {line} is not a plugin block")
    for name, expr in (outputs or {}).items():
        ed.assign(name, _expression(name, expr))
    if state is not None:
        if not isinstance(state, dict):
            raise PluginError("A plugin's state is a JSON object")
        ed.store_state(state)
    return ed.edits()
