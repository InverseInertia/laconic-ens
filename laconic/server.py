"""Local web UI. One page, two endpoints. The whole sheet is re-run on each
edit; for worksheet-sized documents that takes a few milliseconds."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import document, run, snippet
from .lifecycle import lifecycle

app = FastAPI(title="laconic")
STATIC = Path(__file__).parent / "static"


class Client(BaseModel):
    id: str


class Sheet(BaseModel):
    text: str
    title: str | None = None
    view: str = "typeset"  # or "latex"
    wrap: str = "inline"   # latex view: inline, display or align


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.post("/api/eval")
def evaluate(sheet: Sheet):
    if sheet.view == "latex":
        # Export flavour (siunitx), so the snippets paste straight into a document.
        # The exported .tex file always uses align* blocks.
        return [{**r.to_dict(), "snippet": snippet(r, sheet.wrap)} for r in run(sheet.text, siunitx=True)]
    return [r.to_dict() for r in run(sheet.text)]


@app.post("/api/export", response_class=PlainTextResponse)
def export(sheet: Sheet):
    return document(run(sheet.text, siunitx=True), title=sheet.title)


@app.post("/api/ping")
def ping(c: Client):
    lifecycle.ping(c.id)


@app.post("/api/bye")
def bye(c: Client):
    lifecycle.bye(c.id)
