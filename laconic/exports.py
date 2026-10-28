"""What a sheet exports as, whatever the format.

Each line result yields at most one element: a heading, a paragraph, an error, a figure, a
calculation (`Math`) or, for the .tex file only, a command kept as its source. Which lines are
left out and which comment lines run on as one paragraph are decided here, once; the .tex
(`latex.document`, `latex.snippet`), Markdown (`markdown.markdown`) and HTML/PDF (`pdfdoc.page`)
writers only render the elements.

`export(text, fmt, ...)` is the one entry point that runs a sheet for a format: it knows which
flavour of math each format needs (siunitx for .tex, the live view's for the rest).

This module stays cheap to import (the writers import it); the sheet and the writers are
loaded when `export` runs."""
from dataclasses import dataclass, field

# What the Markdown and PDF writers say about a solver block whose result cannot be trusted.
OUT_OF_DATE = ("Out of date", "This solver result is out of date or was never run; the values may be starting values.")
STALE = "Reads an out-of-date solver result."


@dataclass
class Heading:
    text: str


@dataclass
class Paragraph:
    lines: list             # comment lines, one per worksheet line, run on as one paragraph


@dataclass
class Error:
    n: int
    message: str


@dataclass
class Figure:
    n: int
    plot: object            # the PlotPayload


@dataclass
class Math:
    """A calculation or a solver block's values. `rows` are aligned at their `&`, one stage
    (or one unknown) per row; `flat` is the same without the alignment mark, for a layout too
    narrow for it; `inline` is the whole on one line."""
    n: int
    rows: list
    inline: str
    flat: list = None
    note: str = ""          # shown under it: the line's warning, or that it reads a stale result
    out_of_date: bool = False   # a solver block whose result cannot be trusted

    def __post_init__(self):
        if self.flat is None:
            self.flat = [r.replace("&", "", 1) for r in self.rows]


@dataclass
class Source:
    """A command, kept as the line typed (the .tex file writes it as a comment)."""
    n: int
    text: str


def aligned(lhs, stages):
    """`lhs = s0 = s1 ...` one stage per row, aligned at the equals signs."""
    return [f"{lhs} &= {stages[0]}" if lhs else f"&{stages[0]}"] + [f"&= {s}" for s in stages[1:]]


def element(r, commands=False):
    """The element one line result yields, or None for a line no export shows. A command is
    kept as a `Source` only with `commands`."""
    if r.kind == "heading":
        return Heading(r.text)
    if r.kind == "comment":
        return Paragraph([r.text])
    if r.kind == "error":
        return Error(r.n, r.error)
    if r.kind == "command":
        return Source(r.n, r.source.strip()) if commands else None
    if r.plot:
        return Figure(r.n, r.plot)
    if r.solver:
        vals = r.solver.values
        return Math(r.n, [aligned(v["lhs"], [v["rhs"]])[0] for v in vals], r",\; ".join(v["latex"] for v in vals),
                    out_of_date=not r.solver.current)
    if r.kind in ("assign", "expr", "funcdef", "unitdef"):
        return Math(r.n, aligned(r.lhs, r.stages), r.latex, flat=r.latex_rows,
                    note=r.warning or (STALE if r.stale else ""))
    return None


def elements(results, commands=False):
    """The sheet's elements in order. Comment lines with nothing shown between them (blank
    lines, and commands unless they are kept) run on as one paragraph."""
    out = []
    for r in results:
        e = element(r, commands)
        if isinstance(e, Paragraph) and out and isinstance(out[-1], Paragraph):
            out[-1].lines += e.lines
        elif e is not None:
            out.append(e)
    return out


# Each format and whether its math is siunitx (the .tex file) or the live view's flavour.
FORMATS = {"tex": True, "md": False, "html": False, "pdf": False}


def run(text, fmt, global_units=None, runs=None):
    """The sheet run in the flavour `fmt` needs. `runs`, a dict shared between calls on the same
    text, keeps each flavour's run so it is made once."""
    from .sheet import evaluate
    siunitx = FORMATS[fmt]
    runs = {} if runs is None else runs
    if siunitx not in runs:
        runs[siunitx] = evaluate(text, siunitx=siunitx, global_units=global_units)
    return runs[siunitx]


def export(text, fmt, title=None, global_units=None, runs=None, **opts):
    """The sheet `text` as `fmt`: "tex" (a complete document), "md" (an Obsidian note), "html"
    (the printable page; `assets`, `autoprint` as pdfdoc.page takes them) or "pdf" (that page
    printed, as bytes; `timeout`). A PDF needs a Chromium-family browser: pdfdoc.NoBrowser
    (a RuntimeError) when there is none."""
    ws = run(text, fmt, global_units, runs)
    if fmt == "tex":
        from .latex import document
        return document(ws.results, title=title, declarations=ws.declarations)
    if fmt == "md":
        from .markdown import markdown
        return markdown(ws.results, title=title)
    from . import pdfdoc
    if fmt == "html":
        return pdfdoc.page(ws.results, title=title, **opts)
    return pdfdoc.pdf(pdfdoc.page(ws.results, title=title), **opts)
