"""Draws a plot spec (see plotspec.py) as SVG.

This is the only renderer for the picture: the browser shows its output, the
SVG export is its output, and the command line writes its output. The browser's
mouse handling sits on top of it (static/plotview.js) and never draws.

Layout is computed here from the spec alone, and the geometry the mouse code needs
(plot rectangle, axis limits and scales) is written into a `data-lens-plot`
attribute."""
import base64
import html
import json
import math
import re
from functools import lru_cache
from pathlib import Path

INK, SOFT, GRID, PAPER = "#17253d", "#4b5a72", "#d9e0d3", "#ffffff"
FONT = '"IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif'
FS, TICK_FS, TITLE_FS = 12, 11, 14
# The margins hold a fixed budget of LABEL_CHARS characters for the tick labels, so while the
# numbers on an axis fit in it the frame stays put however a pan or zoom changes them (and the
# pointer stays on the axis strip being scrolled). A label that needs more makes the margin
# grow to fit it, and the frame moves with it.
LABEL_CHARS = 6
SUB_RE = re.compile(r"_(\{[^}]*\}|[A-Za-z0-9]+)")
_DASH = {"solid": "", "dashed": "6 4", "dotted": "1 4"}


def esc(s):
    return html.escape(str(s), quote=True)


def markup(text, size):
    """Escaped SVG text with `_sub` and `_{sub}` as lowered, smaller runs."""
    out, pos = [], 0
    for m in SUB_RE.finditer(text):
        out.append(esc(text[pos:m.start()]))
        d = size * 0.25
        out.append(f'<tspan dy="{d:.1f}" font-size="{size * 0.75:.1f}">{esc(m.group(1).strip("{}"))}</tspan>'
                   f'<tspan dy="{-d:.1f}"></tspan>')
        pos = m.end()
    out.append(esc(text[pos:]))
    return "".join(out)


def text_width(text, size):
    """Rough width, for sizing margins. Plex Sans averages a little over half an em."""
    plain = SUB_RE.sub(lambda m: "." * max(1, round(len(m.group(1).strip("{}")) * 0.75)), text)
    return len(plain) * size * 0.56


def _decimals(step):
    """Decimal places that write `step` exactly (0.25 needs 2); tolerance is relative, so 1e-11 is not 0."""
    for d in range(9):
        x = step * 10 ** d
        if abs(x - round(x)) <= 1e-6 * x:
            return d
    return 8


def _sci(v, p):
    m, e = f"{v:.{p}e}".split("e")
    return f"{m}e{int(e)}"


def _short(v):
    """1, 2.5, 1e3: three significant digits, with e-notation only when needed."""
    s = f"{v:.3g}"
    return f"{s.split('e')[0]}e{int(s.split('e')[1])}" if "e" in s else s


def format_ticks(values, step):
    """One notation for a whole axis: fixed point when every label fits in LABEL_CHARS, else
    scientific with as few digits as tell the ticks apart."""
    nd = _decimals(step)
    fixed = ["0" if v == 0 else f"{v:.{nd}f}" for v in values]
    if nd <= 6 and all(len(t) <= LABEL_CHARS for t in fixed):
        return fixed
    # More digits make wider labels, which is better than printing the same label on every tick
    # (a range like 1e9 .. 1e9+5); the margin grows to fit them.
    for p in range(10):
        sci = ["0" if v == 0 else _sci(v, p) for v in values]
        if all(abs(float(t) - v) <= abs(step) * 1e-3 for t, v in zip(sci, values)):
            return sci
    return sci


def nice_step(span, target=6):
    raw = span / target
    mag = 10 ** math.floor(math.log10(raw))
    return next(m * mag for m in (1, 2, 5, 10) if m * mag >= raw)


def linear_ticks(lo, hi, step=None):
    if step is None or (hi - lo) / step > 200:
        step = nice_step(hi - lo)
    k0, k1 = math.ceil(lo / step - 1e-9), math.floor(hi / step + 1e-9)
    values = [k * step for k in range(k0, k1 + 1)]
    return step, [{"v": v, "label": t, "major": True} for v, t in zip(values, format_ticks(values, step))]


def log_ticks(lo, hi):
    a, b = math.floor(math.log10(lo)), math.ceil(math.log10(hi))
    out = []
    if b - a >= 2:
        for k in range(a, b + 1):
            for m in range(1, 10):
                v = m * 10.0 ** k
                if lo * (1 - 1e-9) <= v <= hi * (1 + 1e-9):
                    tick = {"v": v, "major": m == 1, "label": f"10_{{{k}}}" if m == 1 else ""}
                    out.append({**tick, "power": k} if m == 1 else tick)
        return out
    for k in range(a, b + 1):                     # under two decades: label 1, 2, 5 of each
        for m in range(1, 10):
            v = m * 10.0 ** k
            if lo * (1 - 1e-9) <= v <= hi * (1 + 1e-9):
                out.append({"v": v, "major": m in (1, 2, 5), "label": _short(v) if m in (1, 2, 5) else ""})
    return out


def axis_ticks(ax):
    lo, hi = ax["lim"]
    if ax["scale"] == "log":
        return log_ticks(lo, hi)
    return linear_ticks(lo, hi, ax.get("step"))[1]


def label_chars(t):
    """Width of a tick label in characters (10^k is the 10 and a smaller exponent)."""
    return 2 + 0.75 * len(str(t["power"])) if "power" in t else len(t["label"])


def room(ticks):
    """Pixels a column of tick labels needs: the budget, or more when a label is wider."""
    return max([LABEL_CHARS] + [label_chars(t) for t in ticks]) * TICK_FS * 0.56


def tick_markup(t):
    """10^k as a raised exponent; any other label as is."""
    if "power" in t:
        return f'10<tspan dy="{-TICK_FS * 0.4:.1f}" font-size="{TICK_FS * 0.75:.1f}">{t["power"]}</tspan>'
    return esc(t["label"])


def _scale(ax, p0, p1):
    lo, hi = ax["lim"]
    if ax["scale"] == "log":
        a, b = math.log10(lo), math.log10(hi)
        return lambda v: p0 + (math.log10(v) - a) / (b - a) * (p1 - p0)
    return lambda v: p0 + (v - lo) / (hi - lo) * (p1 - p0)


def _clamp(v):
    return max(-1e5, min(1e5, v))


@lru_cache(maxsize=1)
def font_css():
    """Plex Sans embedded, so a saved SVG looks the same on a machine without it."""
    d = Path(__file__).parent / "static" / "fonts"
    faces = []
    for weight in (400, 500):
        data = base64.b64encode((d / f"ibm-plex-sans-latin-{weight}-normal.woff2").read_bytes()).decode()
        faces.append('@font-face{font-family:"IBM Plex Sans";font-style:normal;font-weight:%d;'
                     'src:url(data:font/woff2;base64,%s) format("woff2")}' % (weight, data))
    return "".join(faces)


def render_svg(spec, uid=0, standalone=False):
    """The SVG for one plot. `uid` keeps clip-path ids unique when several plots share
    a page. `standalone` makes a complete file: XML header and embedded font, and none
    of the attributes the browser's mouse code reads."""
    W, H = spec["size"]
    x, y = spec["x"], spec["y"]
    xt, yt = axis_ticks(x), axis_ticks(y)
    title = spec["title"]
    left = 12 + (FS + 6 if y["label"] else 0) + room(yt) + 10
    right = 8 + room(xt) / 2
    top = 10 + (TITLE_FS + 10 if title else 0)
    bottom = 6 + (FS + 8 if x["label"] else 0) + TICK_FS + 10
    L, T = left, top
    bw, bh = max(W - left - right, 40), max(H - top - bottom, 40)
    X, Y = _scale(x, L, L + bw), _scale(y, T + bh, T)
    xlog, ylog = x["scale"] == "log", y["scale"] == "log"

    meta = {"box": [L, T, bw, bh], "x": {"lim": x["lim"], "scale": x["scale"]},
            "y": {"lim": y["lim"], "scale": y["scale"]}}
    root = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
            f'class="lens-plot" role="img" aria-label="{esc(title or y["label"] or "plot")}" '
            f'font-family=\'{esc(FONT)}\' font-size="{FS}" fill="{INK}"')
    if not standalone:
        root += f' data-lens-plot="{esc(json.dumps(meta))}"'
    out = [root + ">"]
    if standalone:
        out.insert(0, '<?xml version="1.0" encoding="UTF-8"?>')
        out.append(f"<style>{font_css()}</style>")
    clip = f"lens-clip-{uid}"
    out.append(f'<rect width="{W}" height="{H}" fill="{PAPER}"/>')
    out.append(f'<defs><clipPath id="{clip}"><rect x="{L}" y="{T}" width="{bw}" height="{bh}"/></clipPath></defs>')

    # Everything inside the frame that moves when the view moves. The mouse code
    # transforms `.pl-view` while a drag is in progress, so the clip is on its parent.
    view = []
    fixed = 'vector-effect="non-scaling-stroke"'   # lines keep their width while the view is scaled
    if spec["grid"]:
        for t in xt:
            if t["major"]:
                px = X(t["v"])
                view.append(f'<line {fixed} x1="{px:.2f}" y1="{T}" x2="{px:.2f}" y2="{T + bh}"/>')
        for t in yt:
            if t["major"]:
                py = Y(t["v"])
                view.append(f'<line {fixed} x1="{L}" y1="{py:.2f}" x2="{L + bw}" y2="{py:.2f}"/>')
    out.append(f'<g clip-path="url(#{clip})"><g class="pl-view">')
    out.append(f'<g class="pl-grid" stroke="{GRID}" stroke-width="1">' + "".join(view) + "</g>")
    for s in spec["series"]:
        d, pen, dots = [], False, []
        for a, b in zip(s["x"], s["y"]):
            if b is None or (ylog and b <= 0) or (xlog and a <= 0):
                pen = False
                continue
            px, py = _clamp(X(a)), _clamp(Y(b))
            d.append(f"{'L' if pen else 'M'}{px:.2f} {py:.2f}")
            pen = True
            if s["marker"] == "circle":
                dots.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="2.6"/>')
            elif s["marker"] == "square":
                dots.append(f'<rect x="{px - 2.4:.2f}" y="{py - 2.4:.2f}" width="4.8" height="4.8"/>')
        dash = _DASH[s["dash"]]
        cap = "round" if s["dash"] == "dotted" else "butt"
        out.append(f'<path d="{"".join(d)}" fill="none" stroke="{s["color"]}" stroke-width="{s["width"]:g}" '
                   f'stroke-linejoin="round" stroke-linecap="{cap}" {fixed}'
                   + (f' stroke-dasharray="{dash}"' if dash else "") + "/>")
        if dots:
            out.append(f'<g fill="{s["color"]}">{"".join(dots)}</g>')
    out.append("</g></g>")

    out.append(f'<rect x="{L}" y="{T}" width="{bw}" height="{bh}" fill="none" stroke="{INK}" stroke-width="1.2"/>')
    ticks = []
    for t in xt:
        px = X(t["v"])
        ticks.append(f'<line x1="{px:.2f}" y1="{T + bh}" x2="{px:.2f}" y2="{T + bh + (5 if t["major"] else 3)}"/>')
        if t["label"]:
            ticks.append(f'<text x="{px:.2f}" y="{T + bh + 6 + TICK_FS:.1f}" text-anchor="middle" '
                         f'stroke="none">{tick_markup(t)}</text>')
    for t in yt:
        py = Y(t["v"])
        ticks.append(f'<line x1="{L}" y1="{py:.2f}" x2="{L - (5 if t["major"] else 3)}" y2="{py:.2f}"/>')
        if t["label"]:
            ticks.append(f'<text x="{L - 8}" y="{py:.2f}" dy="0.35em" text-anchor="end" '
                         f'stroke="none">{tick_markup(t)}</text>')
    out.append(f'<g stroke="{INK}" stroke-width="1" font-size="{TICK_FS}" fill="{SOFT}">{"".join(ticks)}</g>')
    if x["label"]:
        out.append(f'<text x="{L + bw / 2:.1f}" y="{H - 6}" text-anchor="middle">{markup(x["label"], FS)}</text>')
    if y["label"]:
        out.append(f'<text transform="translate({FS + 2},{T + bh / 2:.1f}) rotate(-90)" text-anchor="middle">'
                   f'{markup(y["label"], FS)}</text>')
    if title:
        out.append(f'<text x="{L + bw / 2:.1f}" y="{TITLE_FS + 6}" text-anchor="middle" font-size="{TITLE_FS}" '
                   f'font-weight="500">{markup(title, TITLE_FS)}</text>')

    for n in spec["notes"]:
        if (xlog and n["x"] <= 0) or (ylog and n["y"] <= 0):
            continue
        px, py = X(n["x"]), Y(n["y"])
        if L <= px <= L + bw and T <= py <= T + bh:
            out.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="3.5" fill="{INK}"/>'
                       f'<text x="{px + 7:.2f}" y="{py - 6:.2f}">{markup(n["text"], FS)}</text>')

    if spec["legend"]:
        labels = [s["label"] for s in spec["series"]]
        lw = max(text_width(t, FS) for t in labels) + 44
        lh = 8 + 18 * len(labels)
        v, h = spec["legend"].split()
        lx = L + bw - lw - 8 if h == "right" else L + 8
        ly = T + 8 if v == "top" else T + bh - lh - 8
        out.append(f'<g class="pl-legend"><rect x="{lx:.1f}" y="{ly:.1f}" width="{lw:.1f}" height="{lh}" '
                   f'fill="{PAPER}" fill-opacity="0.9" stroke="{GRID}"/>')
        for k, s in enumerate(spec["series"]):
            cy = ly + 8 + 18 * k + 9
            dash = _DASH[s["dash"]]
            out.append(f'<line x1="{lx + 8:.1f}" y1="{cy:.1f}" x2="{lx + 30:.1f}" y2="{cy:.1f}" stroke="{s["color"]}" '
                       f'stroke-width="{s["width"]:g}"' + (f' stroke-dasharray="{dash}"' if dash else "") + "/>"
                       f'<text x="{lx + 36:.1f}" y="{cy:.1f}" dy="0.35em">{markup(s["label"], FS)}</text>')
        out.append("</g>")
    out.append("</svg>")
    return "".join(out) + ("\n" if standalone else "")
