"""Local web UI. One page, a few endpoints. The whole sheet is re-run on each
edit; for worksheet-sized documents that takes a few milliseconds. Settings
(Greek table, global units, display preferences) live on the server, in `settings.py`."""
import json
import secrets
import subprocess
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import evaluate as evaluate_sheet, snippet
from .exports import export as export_sheet
from .sheet import block_at, solver_blocks
from . import settings, unittags
from .blockedit import to_json
from ._version import label as version_label
from .commands import help_rows
from .evaluator import check_units
from .lifecycle import lifecycle
from .plotopts import PlotError, apply_patch
from .rename import RenameError, RenameWarning, rename
from .solver import SolverError, set_option, write_result
from .solverjobs import Busy, jobs
from .vocab import props_vocabulary, vocabulary

app = FastAPI(title="laconic")
STATIC = Path(__file__).parent / "static"
HELP_MARKER = "      <!-- command help: rows generated from commands.COMMANDS by server.py -->"
VERSION_MARKER = "{{version}}"  # in index.html; replaced with the program's version (_version.py)
PREFS_MARKER = "{{prefs}}"      # in index.html; replaced with the stored display preferences (settings.py)
EXAMPLES = Path(__file__).parent / "examples"  # shipped with the program, so always there to open
OPENED = None   # Path of the worksheet the program was started with (`lens --window FILE`), set by __main__
OPEN_WINDOW = None  # set by __main__ when serving: opens a window on a path of this server ("/?sheet=...")
HANDED = {}     # token -> Path: sheets other launches handed to this server, each in a window of its own


class Client(BaseModel):
    id: str


class WindowBody(BaseModel):
    path: str | None = None    # the sheet to open; None for a window with no file


class Sheet(BaseModel):
    text: str
    title: str | None = None
    view: str = "typeset"  # or "latex"
    wrap: str = "inline"   # latex view: inline, display or align


class RenameBody(BaseModel):
    text: str
    old: str
    new: str
    confirm: bool = False


class PlotEditBody(BaseModel):
    text: str
    line: int                                           # the plot's `plot` line, 1-based
    patch: dict[str, str | list[float] | None]          # option -> new value; None removes it


class PlotImageBody(BaseModel):
    text: str
    line: int


class SolveStartBody(BaseModel):
    text: str
    line: int                  # the `!root`, `!minimize` or `!maximize` line, 1-based
    mode: str = "run"          # or "verify": run again and compare with the stored result


class SolveStoreBody(BaseModel):
    text: str
    record: dict               # what a finished job returned


class SolveEditBody(BaseModel):
    text: str
    line: int
    autorun: bool


class TextBody(BaseModel):
    text: str


class GreekBody(BaseModel):
    greek: dict[str, str] | None = None  # None: back to the built-in table


class PrefsBody(BaseModel):
    prefs: dict[str, Any]   # key -> new value; None removes it


class UnitRow(BaseModel):
    name: str
    definition: str


class UnitsBody(BaseModel):
    units: list[UnitRow]


class TagsBody(BaseModel):
    tags: dict[str, list[str]]   # tag -> the units it is on


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    # In the page, not fetched, so the theme and the rest are there before the page first draws.
    # "<" escaped, so no value can close the script element it sits in.
    prefs = json.dumps(settings.load()["prefs"]).replace("<", "\\u003c")
    return HTMLResponse(page.replace(HELP_MARKER, help_rows()).replace(VERSION_MARKER, version_label())
                        .replace(PREFS_MARKER, prefs))


def _run(sheet, siunitx):
    return evaluate_sheet(sheet.text, siunitx=siunitx, global_units=settings.global_units())


@app.post("/api/eval")
def evaluate(sheet: Sheet):
    results = _run(sheet, sheet.view == "latex").results
    if any(r.solver for r in results):
        threading.Thread(target=jobs.warm, daemon=True).start()   # so the first Run does not wait for imports
    if sheet.view == "latex":
        # Export flavour (siunitx), so the snippets paste straight into a document.
        # The exported .tex file always uses align* blocks.
        return [{**r.to_json(), "snippet": snippet(r, sheet.wrap)} for r in results]
    return [r.to_json() for r in results]


@app.post("/api/export", response_class=PlainTextResponse)
def export(sheet: Sheet):
    return _export(sheet, "tex")


@app.post("/api/export/md", response_class=PlainTextResponse)
def export_md(sheet: Sheet):
    """The sheet as a Markdown note in Obsidian's style (see markdown.py)."""
    return _export(sheet, "md")


@app.post("/api/export/pdf")
def export_pdf(sheet: Sheet):
    """The sheet as a PDF, printed by a headless Chromium (see pdfdoc.py). 501 when there is no
    such browser or it fails; the page then prints /api/export/print with the browser's own dialog."""
    try:
        return Response(_export(sheet, "pdf", timeout=30), media_type="application/pdf")
    except (RuntimeError, subprocess.TimeoutExpired) as e:   # NoBrowser is a RuntimeError
        raise HTTPException(501, str(e))


@app.post("/api/export/print", response_class=HTMLResponse)
def export_print(sheet: Sheet):
    """The printable document, opening the print dialog by itself."""
    return _export(sheet, "html", assets="/static", autoprint=True)


def _export(sheet, fmt, **opts):
    """The sheet as `fmt`, in the flavour of math that format needs (see exports.py)."""
    return export_sheet(sheet.text, fmt, title=sheet.title, global_units=settings.global_units(), **opts)


@app.post("/api/save", response_class=PlainTextResponse)
def save(sheet: Sheet):
    """The worksheet source, with the unit definitions it needs appended."""
    return _run(sheet, False).portable_text()


@app.post("/api/rename")
def rename_symbol(body: RenameBody):
    """Every use of a variable or function name, renamed: one edit per use. Nothing changes on error."""
    try:
        edits, count = rename(body.text, body.old, body.new, body.confirm)
    except RenameWarning as e:
        return {"ok": False, "warning": str(e)}
    except RenameError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "edits": to_json(body.text, edits), "count": count}


def _plot_at(text, line):
    """The PlotPayload of the plot on `line`, or None when no plot draws there."""
    r = block_at(text, line, settings.global_units())
    return r and r.plot


@app.post("/api/plotedit")
def plot_edit(body: PlotEditBody):
    """Option lines of one plot, rewritten to say what the mouse just did (a pan, a zoom,
    a reset). Returns the edits to the text; the page applies them to the editor, and the
    plot is then redrawn from the text like any other edit. Nothing changes on error."""
    plot = _plot_at(body.text, body.line)
    if plot is None:
        return {"ok": False, "error": f"Line {body.line} is not a plot that draws"}
    try:
        edits = apply_patch(body.text, body.line, body.patch, plot.axes, plot.inherited)
    except PlotError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "edits": to_json(body.text, edits)}


@app.post("/api/plotimage")
def plot_image(body: PlotImageBody):
    """The plot as a complete SVG file, exactly as the page draws it."""
    plot = _plot_at(body.text, body.line)
    if plot is None:
        raise HTTPException(404, f"Line {body.line} is not a plot that draws")
    return Response(plot.image(uid=body.line), media_type="image/svg+xml")


# ---- solver blocks ---------------------------------------------------------------------------------
# Evaluating a sheet never runs a solver. The page starts a job, polls it, and when it has finished
# asks for the result to be written into the block (/store), which returns the edits to the text.
@app.post("/api/solve/start")
def solve_start(body: SolveStartBody):
    if body.mode not in ("run", "verify"):
        raise HTTPException(400, "mode is run or verify")
    try:
        job = jobs.start(body.text, body.line, body.mode, settings.global_units())
    except Busy as e:
        raise HTTPException(409, str(e)) from None
    except SolverError as e:
        raise HTTPException(400, str(e)) from None
    return {"job": job.id}


@app.get("/api/solve/{job_id}")
def solve_poll(job_id: str, since: int = 0):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "No such job")
    return job.view(max(since, 0))


@app.post("/api/solve/{job_id}/interrupt")
def solve_interrupt(job_id: str):
    job = jobs.interrupt(job_id)
    if job is None:
        raise HTTPException(404, "No such job")
    return job.view(0)


@app.post("/api/solvestore")
def solve_store(body: SolveStoreBody):
    """Write a finished result into every block whose inputs hash to the record's hash. If the
    sheet was edited while the job ran, no block matches and nothing is written."""
    h = body.record.get("hash")
    hits = [r.n for r in solver_blocks(body.text, settings.global_units()) if r.solver.hash == h]
    if not hits:
        return {"ok": False, "error": "The inputs changed while the solver was running, so its result was not stored"}
    edits = [e for n in hits for e in write_result(body.text, n, body.record)]   # all against body.text
    return {"ok": True, "edits": to_json(body.text, edits), "lines": hits}


@app.post("/api/solveedit")
def solve_edit(body: SolveEditBody):
    """Turn a block's `autorun:` line on or off. Returns the edits to the text."""
    try:
        edits = set_option(body.text, body.line, "autorun", "on" if body.autorun else None)
        return {"ok": True, "edits": to_json(body.text, edits)}
    except SolverError as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/settings")
def get_settings():
    return settings.load()


@app.put("/api/prefs")
def put_prefs(body: PrefsBody):
    settings.save_prefs(body.prefs)
    return {"ok": True}


@app.put("/api/welcomed")
def put_welcomed():
    settings.save_welcomed()
    return {"ok": True}


def _opened(sheet):
    """The file a window opened on: the program's own (no `sheet`), or one handed over by
    another launch. A window opened with `?sheet=` (empty) or an unknown token has none."""
    return OPENED if sheet is None else HANDED.get(sheet)


@app.get("/api/opened")
def get_opened(sheet: str | None = None):
    """The worksheet the window was opened on, or {} when there is none. `writable` is
    False for a .cs or .txt file, which is read but never overwritten (as in savefile.js)."""
    path = _opened(sheet)
    if path is None:
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return {"file": path.name, "error": f"Could not open {path.name}: {e}"}
    return {"file": path.name, "path": str(path), "text": text,
            "writable": path.suffix.lower() == ".lens"}


@app.post("/api/opened/save")
def save_opened(body: TextBody, sheet: str | None = None):
    """Writes the worksheet back to the file the window was opened on: the only file on
    disk the page can write to by name."""
    path = _opened(sheet)
    if path is None or path.suffix.lower() != ".lens":
        raise HTTPException(409, "no .lens file to save to")
    try:
        with open(path, "w", encoding="utf-8", newline="") as f:   # keep the text's line endings
            f.write(body.text)
    except OSError as e:
        return {"ok": False, "error": f"Could not save {path.name}: {e}"}
    return {"ok": True}


def _example_title(path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("##"):
            return line.lstrip("#").strip()
    return path.stem


@app.get("/api/examples")
def list_examples():
    return [{"name": p.stem, "title": _example_title(p)} for p in sorted(EXAMPLES.glob("*.lens"))]


@app.get("/api/examples/{name}")
def get_example(name: str):
    path = EXAMPLES / f"{name}.lens"
    if name not in {p.stem for p in EXAMPLES.glob("*.lens")}:
        raise HTTPException(404, "no such example")
    return PlainTextResponse(path.read_text(encoding="utf-8"))


@app.get("/api/vocab")
def vocab():
    return vocabulary(settings.global_units())


@app.get("/api/vocab/props")
def vocab_props():
    """Keys and fluids for props(...) strings. Imports CoolProp, so the page asks for it lazily."""
    return props_vocabulary()


@app.get("/api/unitbrowse")
def unit_browse():
    cfg = settings.load()
    return unittags.browse([(u["name"], u["definition"]) for u in cfg["units"]], cfg["tags"])


@app.put("/api/tags")
def put_tags(body: TagsBody):
    try:
        tags = unittags.clean(body.tags)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    settings.save_tags(tags)
    return {"ok": True, "tags": tags}


@app.put("/api/greek")
def put_greek(body: GreekBody):
    settings.save_greek(body.greek)
    return {"ok": True}


@app.put("/api/units")
def put_units(body: UnitsBody):
    """Nothing is stored unless every definition is valid, so the file never
    holds a unit that fails to load."""
    pairs = [(u.name.strip(), u.definition.strip()) for u in body.units]
    errors = check_units(pairs)
    if any(errors):
        return {"ok": False, "errors": errors}
    settings.save_units(pairs)
    return {"ok": True, "errors": errors}


@app.post("/api/ping")
def ping(c: Client):
    lifecycle.ping(c.id)


@app.post("/api/bye")
def bye(c: Client):
    lifecycle.bye(c.id)


@app.get("/api/hello")
def hello():
    """How another launch of LENS knows this server for one (instance.py)."""
    return {"app": "lens", "version": version_label()}


@app.post("/api/window")
def open_window(body: WindowBody):
    """Another launch of LENS found this one running and hands its window over: open one here,
    on the same port, so the page finds this browser's stored presets."""
    if OPEN_WINDOW is None:
        raise HTTPException(409, "this server does not open windows")
    if body.path:
        token = secrets.token_urlsafe(12)   # not guessable, so no other page can ask for the file
        HANDED[token] = Path(body.path).resolve()
    else:
        token = ""
    lifecycle.expect()
    OPEN_WINDOW(f"/?sheet={token}")
    return {"ok": True}
