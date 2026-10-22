"""Local web UI. One page, a few endpoints. The whole sheet is re-run on each
edit; for worksheet-sized documents that takes a few milliseconds. Settings
(Greek table, global units) live on the server, in `settings.py`."""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import document, evaluate as evaluate_sheet, snippet
from . import settings
from .evaluator import check_units
from .lifecycle import lifecycle
from .plotopts import PlotError, apply_patch
from .plotsvg import render_svg
from .rename import RenameError, RenameWarning, rename
from .vocab import vocabulary

app = FastAPI(title="laconic")
STATIC = Path(__file__).parent / "static"


class Client(BaseModel):
    id: str


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


class GreekBody(BaseModel):
    greek: dict[str, str] | None = None  # None: back to the built-in table


class UnitRow(BaseModel):
    name: str
    definition: str


class UnitsBody(BaseModel):
    units: list[UnitRow]


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


def _run(sheet, siunitx):
    return evaluate_sheet(sheet.text, siunitx=siunitx, global_units=settings.global_units())


@app.post("/api/eval")
def evaluate(sheet: Sheet):
    if sheet.view == "latex":
        # Export flavour (siunitx), so the snippets paste straight into a document.
        # The exported .tex file always uses align* blocks.
        return [{**r.to_dict(), "snippet": snippet(r, sheet.wrap)} for r in _run(sheet, True).results]
    return [r.to_dict() for r in _run(sheet, False).results]


@app.post("/api/export", response_class=PlainTextResponse)
def export(sheet: Sheet):
    ws = _run(sheet, True)
    return document(ws.results, title=sheet.title, declarations=ws.declarations)


@app.post("/api/save", response_class=PlainTextResponse)
def save(sheet: Sheet):
    """The worksheet source, with the unit definitions it needs appended."""
    return _run(sheet, False).portable_text()


@app.post("/api/rename")
def rename_symbol(body: RenameBody):
    """Every use of a variable or function name, renamed. Nothing changes on error."""
    try:
        text, count = rename(body.text, body.old, body.new, body.confirm)
    except RenameWarning as e:
        return {"ok": False, "warning": str(e)}
    except RenameError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "text": text, "count": count}


def _plot_at(text, line):
    results = evaluate_sheet(text, global_units=settings.global_units()).results
    r = results[line - 1] if 1 <= line <= len(results) else None
    return r if r is not None and r.kind == "plot" else None


@app.post("/api/plotedit")
def plot_edit(body: PlotEditBody):
    """Option lines of one plot, rewritten to say what the mouse just did (a pan, a zoom,
    a reset). Returns the new source text; the page applies it to the editor, and the
    plot is then redrawn from the text like any other edit. Nothing changes on error."""
    r = _plot_at(body.text, body.line)
    if r is None:
        return {"ok": False, "error": f"Line {body.line} is not a plot that draws"}
    try:
        text = apply_patch(body.text, body.line, body.patch,
                           {"x": r.plot["x"], "y": r.plot["y"]}, r.plot["inherited"])
    except PlotError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "text": text}


@app.post("/api/plotimage")
def plot_image(body: PlotImageBody):
    """The plot as a complete SVG file, exactly as the page draws it."""
    r = _plot_at(body.text, body.line)
    if r is None:
        raise HTTPException(404, f"Line {body.line} is not a plot that draws")
    return Response(render_svg(r.plot, uid=body.line, standalone=True), media_type="image/svg+xml")


@app.get("/api/settings")
def get_settings():
    return settings.load()


@app.get("/api/vocab")
def vocab():
    return vocabulary(settings.global_units())


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
