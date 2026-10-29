"""A plot spec as a pgfplots figure, for the exported .tex.

It is built from the same spec as the SVG, so the data, limits, scales, labels,
colours and dash styles agree. TeX draws it with the document's own fonts and
tick placement, so it is a close match and not the same picture. For the exact
picture use the SVG export. The document needs `pgfplots` (the exported .tex
loads it)."""

from .latex import _GREEK_CHARS, escape
from .plotsvg import SUB_RE

_LEGEND = {"top right": "north east", "top left": "north west",
           "bottom right": "south east", "bottom left": "south west"}
_MARK = {"circle": "*", "square": "square*"}


def tex_text(s):
    """Plain label text for TeX: Greek letters as math, `_sub` as a subscript, the rest escaped."""
    out, pos = [], 0

    def plain(t):
        return "".join(f"${_GREEK_CHARS[c]}$" if c in _GREEK_CHARS and _GREEK_CHARS[c].startswith("\\") else escape(c)
                       for c in t)
    for m in SUB_RE.finditer(s):
        out.append(plain(s[pos:m.start()]))
        out.append(r"\textsubscript{" + plain(m.group(1).strip("{}")) + "}")
        pos = m.end()
    out.append(plain(s[pos:]))
    return "".join(out)


def _label(ax, name):
    if not ax["auto_label"]:
        return tex_text(ax["label"])
    u = ax["unit_tex"]
    if u and not (u.startswith("\\unit")):   # the preview flavour of units needs math mode
        u = f"${u}$"
    return (name + (f" ({u})" if u else "")) if name else (f"({u})" if u else "")


def _num(v):
    return f"{v:.6g}"


def _color(c):
    return "{rgb,255:red,%d;green,%d;blue,%d}" % (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16))


def pgfplots(spec):
    """The tikzpicture for one plot."""
    W, H = spec["size"]
    x, y = spec["x"], spec["y"]
    y_name = tex_text(spec["series"][0]["label"]) if len(spec["series"]) == 1 else ""
    opts = [f"width={W / 96 * 2.54:.2f}cm", f"height={H / 96 * 2.54:.2f}cm",
            f"xmin={_num(x['lim'][0])}", f"xmax={_num(x['lim'][1])}",
            f"ymin={_num(y['lim'][0])}", f"ymax={_num(y['lim'][1])}",
            "unbounded coords=jump", "scale only axis"]
    if x["scale"] == "log":
        opts.append("xmode=log")
    if y["scale"] == "log":
        opts.append("ymode=log")
    if x.get("step") and x["scale"] == "lin":
        opts.append(f"xtick distance={_num(x['step'])}")
    if y.get("step") and y["scale"] == "lin":
        opts.append(f"ytick distance={_num(y['step'])}")
    if spec["grid"]:
        opts.append("grid=major")
    if spec["title"]:
        opts.append(f"title={{{tex_text(spec['title'])}}}")
    if x["label"]:
        opts.append(f"xlabel={{{_label(x, '$' + spec['var_tex'] + '$')}}}")
    if y["label"]:
        opts.append(f"ylabel={{{_label(y, y_name)}}}")
    if spec["legend"]:
        opts.append(f"legend pos={_LEGEND[spec['legend']]}")
    else:
        opts.append("legend style={draw=none}")

    lines = ["% Drawn by pgfplots from the worksheet's plot data. For the exact picture shown in",
             "% the app, export the plot as SVG or PNG instead.",
             r"\begin{center}", r"\begin{tikzpicture}", r"\begin{axis}[" + ",\n  ".join([""] + opts) + "\n]"]
    for s in spec["series"]:
        style = [f"color={_color(s['color'])}", f"line width={s['width'] * 0.75:.2f}pt", s["dash"],
                 f"mark={_MARK[s['marker']]}, mark size=1.2pt" if s["marker"] != "none" else "mark=none"]
        if not s.get("line", True):   # points: markers only
            style.append("only marks")
        pts = " ".join(f"({_num(a)},{'nan' if b is None else _num(b)})" for a, b in zip(s["x"], s["y"]))
        lines.append(r"\addplot[" + ", ".join(style) + "] coordinates {\n" + pts + "\n};")
        if spec["legend"]:
            lines.append(rf"\addlegendentry{{{tex_text(s['label'])}}}")
    for n in spec["notes"]:
        lines.append(rf"\node[anchor=south west, font=\small] at (axis cs:{_num(n['x'])},{_num(n['y'])}) "
                     rf"{{{tex_text(n['text'])}}};")
        lines.append(rf"\fill (axis cs:{_num(n['x'])},{_num(n['y'])}) circle (1.5pt);")
    lines += [r"\end{axis}", r"\end{tikzpicture}", r"\end{center}"]
    return "\n".join(lines)
