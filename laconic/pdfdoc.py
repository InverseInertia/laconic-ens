"""Line results -> a plain, page-broken HTML document, and that document -> a PDF.

The document is one column of blocks, one block per line result: headings, comment paragraphs,
calculations (KaTeX, one row per stage aligned at the equals signs), plots (inline SVG) and
errors. Laconic does no typesetting of its own: each block is marked as a unit that may not be
split, headings stay with what follows them, and a calculation wider than the page is shrunk or
wrapped to fit. A Chromium-family browser lays out the pages and prints them (`--print-to-pdf`).

The math is the live view's flavour, as in the Markdown export; run the sheet without siunitx."""
import html
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from . import browser
from .markdown import plain_math

STATIC = Path(__file__).parent / "static"

_STYLE = """
@page { margin: 18mm 16mm 20mm;
  @bottom-left { content: "%(title)s"; font: 8pt "IBM Plex Sans", sans-serif; color: #777; }
  @bottom-right { content: "Page " counter(page) " of " counter(pages); font: 8pt "IBM Plex Sans", sans-serif; color: #777; } }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; font: 10.5pt/1.45 "IBM Plex Sans", sans-serif; color: #111; background: #fff; }
/* On screen, a sheet as wide as the printed column (A4 less the margins; Letter is a little wider),
   so the formulas are fitted to the width they print at, and the tab shows the page's margins. */
@media screen {
  html { background: #e4e4e4; }
  body { width: 178mm; margin: 8mm auto; padding: 18mm 16mm 20mm; box-shadow: 0 1px 4px rgba(0,0,0,.25); }
}
h1 { font-size: 17pt; font-weight: 500; margin: 0 0 4mm; padding-bottom: 2mm; border-bottom: 1px solid #999; }
h2 { font-size: 13pt; font-weight: 500; margin: 6mm 0 2mm; break-after: avoid; page-break-after: avoid; }
p { margin: 1.5mm 0; }
.block { break-inside: avoid; page-break-inside: avoid; margin: 1.5mm 0; }
.calc { display: flex; gap: 4mm; align-items: flex-start; }
.ln { flex: none; width: 7mm; padding-top: 0.5em; text-align: right; font: 7.5pt "IBM Plex Mono", monospace; color: #999; }
.math { flex: 1; min-width: 0; overflow: hidden; }
.math .katex-display { margin: 0; text-align: left; }
.math .katex-display > .katex { text-align: left; }
.wrapped .wrow { margin: 1mm 0 1mm 6mm; text-indent: -6mm; }
.wrapped .wrow .base { margin: 0.35em 0; }   /* room between wrapped lines of fractions */
.note { font-size: 9pt; color: #8a5a00; margin-left: 11mm; }
.callout { border-left: 3px solid; padding: 1mm 3mm; font-size: 9.5pt; }
.callout.error { border-color: #b3261e; background: #fbeaea; }
.callout.warning { border-color: #b8860b; background: #fdf5e0; }
.callout b { display: block; }
.plot { text-align: center; }
.plot svg { max-width: 100%%; height: auto; }
"""

# Render every formula, then fit any that is wider than the column, by the same rule as the
# results pane (static/mathfit.js): a little too wide is shrunk; much too wide is set again as one
# wrapped row per stage, and shrunk only if a piece still does not fit. zoom (unlike transform)
# changes the layout box, so the page breaks are worked out from the fitted size. Once the fonts
# are in, every formula is measured and fitted again.
_SCRIPT = """
for (const el of document.querySelectorAll(".math"))
  MathFit.set(el, el.dataset.tex, JSON.parse(el.dataset.rows), {katex: {throwOnError: false, output: "html"}});
MathFit.fitAll(document);
document.fonts.ready.then(() => MathFit.fitAll(document, true));
"""


def _esc(s):
    return html.escape(s, quote=True)


def _math(n, rows, note="", flat=None):
    """A calculation: `rows` aligned at their `&`, or, in a column too narrow for them, `flat`
    wrapped one per row (by default the same rows without the alignment mark)."""
    rows = [plain_math(r) for r in rows]
    tex = rows[0].replace("&", "", 1) if len(rows) == 1 else "\\begin{aligned}" + " \\\\ ".join(rows) + "\\end{aligned}"
    flat = json.dumps([plain_math(r) for r in flat] if flat is not None else [r.replace("&", "", 1) for r in rows])
    out = (f'<div class="block"><div class="calc"><span class="ln">{n}</span>'
           f'<div class="math" data-tex="{_esc(tex)}" data-rows="{_esc(flat)}"></div></div>')
    return out + (f'<div class="note">{_esc(note)}</div>' if note else "") + "</div>"


def _callout(kind, title, body=""):
    return f'<div class="block callout {kind}"><b>{_esc(title)}</b>{_esc(body)}</div>'


def block(r):
    """The HTML for one line result, or None for a line the document leaves out."""
    if r.kind == "heading":
        return f"<h2>{_esc(r.text)}</h2>"
    if r.kind == "comment":
        return f"<p>{_esc(r.text)}</p>"
    if r.kind == "error":
        return _callout("error", f"Line {r.n}", r.error)
    if r.plot:
        svg = re.sub(r"^<\?xml[^>]*\?>\s*", "", r.plot.image(uid=r.n))   # inline in HTML: no XML declaration
        return f'<div class="block plot">{svg}</div>'   # the picture carries its title
    if r.solver:
        math = _math(r.n, [f"{v['lhs']} &= {v['rhs']}" for v in r.solver.values])
        if not r.solver.current:
            math = _callout("warning", "Out of date",
                            "This solver result is out of date or was never run; the values may be starting values.") + math
        return math
    if r.kind in ("assign", "expr", "funcdef", "unitdef"):
        rows = [f"{r.lhs} &= {r.stages[0]}" if r.lhs else f"&{r.stages[0]}"]
        note = r.warning or ("Reads an out-of-date solver result." if r.stale else "")
        return _math(r.n, rows + [f"&= {s}" for s in r.stages[1:]], note, flat=r.latex_rows)
    return None


def page(results, title=None, assets=None):
    """The whole sheet as one HTML document. `assets` is the URL the package's static folder is
    served at; by default the folder itself, as a file:// URL, for printing on this machine.
    The page prints the served one itself, from a hidden frame, once its fonts are in."""
    assets = (assets or STATIC.as_uri()).rstrip("/")
    body, prev = ([f"<h1>{_esc(title)}</h1>"] if title else []), None
    for r in results:
        x = block(r)
        if x is None:
            continue
        if r.kind == "comment" and prev == "comment":
            body[-1] = body[-1][:-4] + "<br>" + x[3:]   # a comment over several lines stays one paragraph
        else:
            body.append(x)
        prev = r.kind
    footer = (title or "LENS worksheet").replace("\\", "\\\\").replace('"', '\\"')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{_esc(title or "LENS worksheet")}</title>
<link rel="stylesheet" href="{assets}/fonts/fonts.css">
<link rel="stylesheet" href="{assets}/vendor/katex/katex.min.css">
<script src="{assets}/vendor/katex/katex.min.js"></script>
<script src="{assets}/mathfit.js"></script>
<style>{_STYLE % {"title": footer}}</style></head>
<body>
{chr(10).join(body)}
<script>{_SCRIPT}</script>
</body></html>
"""


def find_chromium():
    """A Chromium-family browser to print with, or None (see browser.find)."""
    return browser.find()


class NoBrowser(RuntimeError):
    pass


# What the headless browser is started with, besides its profile and the files. It is a browser
# of its own for one page, so everything a browser does at startup for a person is left out:
# field trials (a test or unbranded build's built-in trial config can stall the command-line print
# until it is killed, #102), background fetches, component updates, sync and extensions.
# The virtual time budget is virtual: it lets the page's own timers and font callbacks (the
# second fit in _SCRIPT) run before the print, and costs no real time on an idle page.
FLAGS = ("--headless", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
         "--no-pdf-header-footer", "--disable-field-trial-config", "--disable-background-networking",
         "--disable-component-update", "--disable-sync", "--disable-extensions", "--mute-audio",
         "--virtual-time-budget=1000", "--allow-file-access-from-files")

# A healthy print takes about a second; this is only the most a stalled browser may cost before
# the page falls back to its own print dialog.
TIMEOUT = 20


def command(exe, src, out, profile):
    """The command line that prints file `src` to `out` with browser `exe` and a fresh `profile`."""
    cmd = [exe, *FLAGS, f"--user-data-dir={profile}", f"--print-to-pdf={out}", Path(src).as_uri()]
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        cmd.insert(1, "--no-sandbox")   # Chromium refuses to run as root with its sandbox
    return cmd


def pdf(doc, timeout=None):
    """`doc` (from page()) printed to PDF bytes by a headless Chromium."""
    from .__main__ import _browser_env
    exe = find_chromium()
    if not exe:
        raise NoBrowser("PDF export needs a Chromium-based browser (Chrome, Edge, Brave...); none was found "
                        "(set LENS_CHROMIUM to the browser's path)")
    # On Windows the browser can still hold its profile for a moment after it exits.
    with tempfile.TemporaryDirectory(prefix="lens-pdf-", ignore_cleanup_errors=True) as tmp:
        src, out = Path(tmp) / "sheet.html", Path(tmp) / "sheet.pdf"
        src.write_text(doc, encoding="utf-8")
        # A profile of its own, so a browser the user already has open does not take the job over.
        subprocess.run(command(exe, src, out, Path(tmp) / "profile"), stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, env=_browser_env(), timeout=timeout or TIMEOUT, check=False)
        if not out.is_file() or out.stat().st_size == 0:
            raise RuntimeError(f"{Path(exe).name} did not write a PDF")
        return out.read_bytes()
