"""Local web UI. One page, a few endpoints. The whole sheet is re-run on each
edit; for worksheet-sized documents that takes a few milliseconds. Settings
(Greek table, global units) live on the server, in `settings.py`."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import document, evaluate as evaluate_sheet, snippet
from . import settings
from .evaluator import check_units
from .lifecycle import lifecycle
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
