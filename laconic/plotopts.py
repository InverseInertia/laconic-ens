"""Plot options: the indented `key: value` lines under a `!plot` statement, the
sheet-wide `!plotspec` command, and the patch that rewrites those lines (through the
block editor). A change made by dragging in the UI is a few plain lines in the worksheet,
and the worksheet alone is enough to redraw the same graph.

    !plot M(x), x = 0'm .. L
      title: Bending moment
      xlim: 0'm .. 3.2'm
      points: D             measured points, as !regression reads them: an x row and a y row

    !plot t, s              points alone: two vectors, or a matrix with an x row and a y row

Nothing here evaluates anything; expression-valued options (limits, units,
notes) stay as source text until the plot is built."""
import math
import re

from .blockedit import BlockEditor
from .sheettext import IDENT, PLOT_LIMIT_KEYS

PALETTE = ("#0072b2", "#d55e00", "#009e73", "#cc79a7", "#e69f00", "#56b4e9")

# The built-in layer. A `!plotspec` command overrides it for the plots below, and
# options under a plot override both.
BUILTIN = {
    "grid": "on", "xscale": "lin", "yscale": "lin", "legend": "auto", "gaps": "break",
    "size": (520, 320), "samples": 400, "width": 1.8, "dash": "solid", "marker": "none",
}

CHOICES = {
    "grid": ("on", "off"),
    "xscale": ("lin", "log"), "yscale": ("lin", "log"),
    "dash": ("solid", "dashed", "dotted"),
    "marker": ("none", "circle", "square"),
    "gaps": ("break", "error"),
    "legend": ("auto", "off", "top right", "top left", "bottom right", "bottom left"),
}
TEXT = ("title", "xlabel", "ylabel", "label")
NUMBERS = {"samples": (int, 10, 5000), "width": (float, 0.5, 12.0),
           "xstep": (float, 0.0, None), "ystep": (float, 0.0, None)}
SERIES_KEYS = ("color", "width", "dash", "marker", "label")
SHEET_KEYS = ("grid", "xscale", "yscale", "legend", "gaps", "size", "samples", "width", "dash", "marker")
# Every option a plot takes, in the order the editor offers them, with what it is for.
KEY_NOTES = {
    "title": "the plot's title",
    "xlabel": "the x axis label; empty removes it",
    "ylabel": "the y axis label; empty removes it",
    "xlim": "low .. high, the x range shown; either end may be auto",
    "ylim": "low .. high, the y range shown; either end may be auto",
    "points": "a matrix with an x row and a y row, or two vectors: x, y; then optionally their units: D, 's, 'mm",
    "color": "a series' color: #rrggbb or a name; `color 2:` for series 2",
    "label": "a series' name in the legend; `label 2:` for series 2",
    "dash": "a series' line: solid, dashed or dotted",
    "marker": "a series' marker: none, circle or square",
    "width": "a series' line width",
    "legend": "where the legend goes, or off",
    "grid": "on or off",
    "xunit": "the unit the x axis is shown in, e.g. 'mm",
    "yunit": "the unit the y axis is shown in, e.g. 'kN * 'm",
    "xscale": "lin or log",
    "yscale": "lin or log",
    "xstep": "x tick spacing, in the axis's unit",
    "ystep": "y tick spacing, in the axis's unit",
    "note": '"text" at (x, y): a labelled dot',
    "size": "width x height in pixels",
    "samples": "points per function (default 400)",
    "gaps": "break or error where a function is undefined",
    "xview": "the x range the mouse set (over xlim)",
    "yview": "the y range the mouse set (over ylim)",
}
KEYS = tuple(KEY_NOTES)
LIMIT_KEYS = PLOT_LIMIT_KEYS   # `lim` is the view the author chose, `view` what the mouse set over it
# Option values the editor completes with names and units (the rest are text, numbers or CHOICES).
MATH_KEYS = LIMIT_KEYS + ("points", "note", "xunit", "yunit")

COLORS = {"black": "#000000", "gray": "#7f7f7f", "grey": "#7f7f7f", "red": "#d55e00", "blue": "#0072b2",
          "green": "#009e73", "orange": "#e69f00", "purple": "#cc79a7", "sky": "#56b4e9",
          "navy": "#17253d"}

_RANGE_RE = re.compile(rf"^(.*),\s*({IDENT})\s*=\s*(.+?)\s*\.\.\s*(.+)$")
_NOTE_RE = re.compile(r'^"(.*)"\s+at\s*\((.*)\)$')
_SIZE_RE = re.compile(r"^(\d+)\s*[x×]\s*(\d+)$")


class PlotError(Exception):
    pass


def split_top(s):
    """Split on commas that are not inside brackets or parentheses."""
    out, depth, cur = [], 0, []
    for c in s:
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        if c == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
    out.append("".join(cur).strip())
    return out


def parse_plot(args):
    """`M(x), V(x), x = 0'm .. L`, what follows `!plot`, -> (series sources, variable, low, high,
    points). Without a range it is points alone, `D` or `t, s` (see `parse_points`): (), None, None,
    None and the points' sources."""
    m = _RANGE_RE.match(args)
    if not m:
        try:
            return (), None, None, None, parse_points(args)
        except PlotError:
            raise PlotError("A plot reads `!plot f(x), x = low .. high`, or `!plot D` or `!plot x, y` "
                            "for points") from None
    series = split_top(m.group(1))
    if not all(series):
        raise PlotError("A plot needs an expression before each comma")
    return series, m.group(2), m.group(3).strip(), m.group(4).strip(), None


def parse_points(v):
    """`D` (a matrix with an x row and a y row) or `x, y` (two vectors), then optionally the units
    the points are in, x's and y's (`D, 's, 'mm`; `auto` leaves one as it is) -> their sources."""
    parts = split_top(v)
    data, units = split_points(parts)
    if any(p.startswith("'") for p in data[1:]):
        raise PlotError("points takes at most two units, the x data's then the y data's: `points: D, 's, 'mm`")
    if not 1 <= len(data) <= 2 or len(units) > 2 or not all(parts):
        raise PlotError("points reads `points: D`, a matrix with an x row and a y row, or `points: x, y`, "
                        "two vectors, then optionally the units they are in: `points: D, 's, 'mm`")
    return parts


def split_points(parts):
    """A points line's sources -> (the data's, the units'): the units are the unit literals at the end,
    x's then y's, where `auto` stands for one not given."""
    k = len(parts)
    while k > 1 and len(parts) - k < 2 and (parts[k - 1].startswith("'") or parts[k - 1] == "auto"):
        k -= 1
    return parts[:k], parts[k:]


def _number(key, v):
    kind, lo, hi = NUMBERS[key]
    try:
        n = kind(float(v))
    except ValueError:
        raise PlotError(f"{key} needs a number") from None
    if not math.isfinite(n) or n < lo or (hi is not None and n > hi) or (key.endswith("step") and n <= 0):
        raise PlotError(f"{key} must be " + (f"between {lo:g} and {hi:g}" if hi is not None else f"above {lo:g}"))
    return n


def _limits(v):
    if v.lower() == "auto":
        return (None, None)
    parts = v.split("..")
    if len(parts) != 2 or not all(p.strip() for p in parts):
        raise PlotError("A limit reads `low .. high`; either end can be `auto`")
    return tuple(None if p.strip().lower() == "auto" else p.strip() for p in parts)


def parse_value(key, v):
    """The typed value of one option. Raises PlotError with a message for the line."""
    v = v.strip()
    if key in CHOICES:
        w = " ".join(v.lower().replace("-", " ").split())
        if w not in CHOICES[key]:
            raise PlotError(f"{key} is one of: " + ", ".join(CHOICES[key]))
        return w
    if key in TEXT:
        return v[1:-1] if len(v) >= 2 and v[0] == v[-1] == '"' else v
    if key in NUMBERS:
        return _number(key, v)
    if key == "size":
        m = _SIZE_RE.match(v)
        if not m or not all(200 <= int(g) <= 2400 for g in m.groups()):
            raise PlotError("size reads `width x height`, each between 200 and 2400 pixels")
        return (int(m.group(1)), int(m.group(2)))
    if key == "color":
        c = COLORS.get(v.lower(), v.lower())
        if re.fullmatch(r"#[0-9a-f]{3}", c):
            c = "#" + "".join(ch * 2 for ch in c[1:])
        if not re.fullmatch(r"#[0-9a-f]{6}", c):
            raise PlotError("color is #rrggbb or one of: " + ", ".join(sorted(COLORS)))
        return c
    if key in LIMIT_KEYS:
        return _limits(v)
    if key in ("xunit", "yunit"):
        if not v:
            raise PlotError(f"{key} needs a unit, e.g. 'kN * 'm")
        return v
    if key == "points":
        return parse_points(v)
    if key == "note":
        m = _NOTE_RE.match(v)
        parts = split_top(m.group(2)) if m else []
        if len(parts) != 2 or not all(parts):
            raise PlotError('A note reads `note: "text" at (x, y)`')
        return (m.group(1), parts[0], parts[1])
    raise PlotError(f"Unknown plot option '{key}'")


def parse_option(key, index, value, sheet=False):
    """-> (key, index, typed value). `index` is a series number or None."""
    if key not in KEYS:
        raise PlotError(f"Unknown plot option '{key}'. Options: " + ", ".join(sorted(KEYS)))
    if index is not None and key not in SERIES_KEYS:
        raise PlotError(f"{key} applies to the whole plot, so it takes no series number")
    if index is not None and int(index) < 1:
        raise PlotError("Series are numbered from 1")
    if sheet and (key not in SHEET_KEYS or index is not None):
        raise PlotError("!plotspec sets " + ", ".join(SHEET_KEYS) + " for every plot below it")
    if value == "" and key not in TEXT:
        raise PlotError(f"{key} needs a value")
    return key, (int(index) if index else None), parse_value(key, value)


def canon(key, value):
    """The text form of a typed value, the same however it was typed."""
    if key == "size":
        return f"{value[0]} x {value[1]}"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _round_for(lo, hi, scale):
    """Round to about four digits of the span, so a drag writes 3.2 and not 3.2000000001."""
    span = abs(hi - lo)
    if scale == "log" or span == 0 or not math.isfinite(span):
        return lambda v: float(f"{v:.4g}")
    nd = 3 - math.floor(math.log10(span))
    return lambda v: round(v, nd)


def _num(v):
    s = f"{v:.12g}"
    return "0" if s == "-0" else s


def format_limits(lo, hi, unit_src, scale):
    r = _round_for(lo, hi, scale)
    return " .. ".join(_num(r(v)) + unit_src for v in (lo, hi))


def split_key(k):
    m = re.fullmatch(r"([A-Za-z]\w*)(?:\s+(\d+))?", k.strip())
    if not m:
        raise PlotError(f"'{k}' is not a plot option")
    return m.group(1), (int(m.group(2)) if m.group(2) else None)


def apply_patch(text, line, patch, axes, inherited):
    """The edits that rewrite the option lines of the plot on `line` (1-based) in `text`.

    `patch` maps an option name (`xview`, `color 2`) to None (remove the line), a
    string (written as typed, after checking it) or, for limits and views, `[low, high]`
    in the axis's display unit. `axes` gives each axis's `unit_src` and `scale`;
    `inherited` is the text form of what each option would be without a line.
    A value equal to its inherited one removes the line instead, so the source
    only says what differs from the defaults."""
    ed = BlockEditor(text, line)
    if ed.kind != "plot":
        raise PlotError(f"Line {line} is not a plot")
    for name, value in patch.items():
        key, index = split_key(name)
        if key in LIMIT_KEYS and isinstance(value, (list, tuple)):
            ax = axes[key[0]]
            lo, hi = value
            if not (math.isfinite(lo) and math.isfinite(hi)) or lo == hi:
                raise PlotError("A limit needs two different, finite numbers")
            if ax["scale"] == "log" and min(lo, hi) <= 0:
                raise PlotError("A log axis needs positive limits")
            value = format_limits(min(lo, hi), max(lo, hi), ax["unit_src"], ax["scale"])
        if value is not None:
            if not isinstance(value, str):
                raise PlotError(f"{name} needs text")
            parse_option(key, index, value)     # refuses a value the parser would refuse
            if key != "note" and inherited.get((key if index is None else f"{key} {index}")) == \
                    canon(key, parse_value(key, value)):
                value = None
        arg = None if index is None else str(index)
        if value is None:
            ed.remove(key, arg)
        else:
            ed.set(key, value, arg)
    return ed.edits()
