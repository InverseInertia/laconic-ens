"""Builds a plot: samples each series, resolves the options against the defaults,
and returns a plain dict (the spec). The SVG renderer, the pgfplots writer and the
browser all read that dict, so a plot looks the same wherever it is drawn.

Samples are taken point by point rather than on an array: `*` between arrays is a
matrix product in this language, so a vectorised evaluation would be wrong.

Points (`points:` lines, or a header with no range) are read as `!regression` reads its data, and
drawn as markers with no line between them."""
import math

import numpy as np
import pint

from .evaluator import _TINY, EvalError
from .latex import name_latex
from .parser import parse_expr
from .plotopts import BUILTIN, PALETTE, PlotError, canon, split_points, split_top
from .regression import RegressionError, columns, in_unit
from .si import reduce_si

MAX_NOTES = 50
MAX_POINTS = 100_000   # series times samples; a redraw runs on every edit


def unit_source(ev, units):
    """A unit as it is written in a worksheet: `'kN * 'm / 's^2`. Empty when
    dimensionless. Symbols are used when they read back as the same unit."""
    items = list(ev.Q(1, units).unit_items())
    if not items:
        return ""
    for symbols in (True, False):
        def lit(name, exp):
            sym = ev.ureg.get_symbol(name) if symbols else name
            return "'" + sym + (f"^{exp:g}" if exp != 1 else "")
        pos = [(n, e) for n, e in items if e > 0]
        neg = [(n, e) for n, e in items if e < 0]
        if pos:
            s = " * ".join(lit(n, e) for n, e in pos)
            if neg:
                den = [lit(n, -e) for n, e in neg]
                s += " / " + (den[0] if len(den) == 1 else "(" + " * ".join(den) + ")")
        else:
            s = " * ".join(lit(n, e) for n, e in neg)
        try:
            if ev.eval(parse_expr(s)).units == units:
                return s
        except Exception:
            continue
    return ""


def _plain(src):
    """A source that is just a name, so it can label an axis."""
    return bool(src) and src.replace("_", "a").isalnum()


def unit_text(units):
    """`kN·m`, for axis labels."""
    s = f"{units:~P}"
    return "" if s in ("", "dimensionless") else s


class Builder:
    def __init__(self, ev, fmt, parse):
        self.ev, self.fmt, self.parse = ev, fmt, parse
        self.errors = []   # (line, message) for options that were ignored

    # ---- evaluation helpers ---------------------------------------------------
    def scalar(self, src):
        q = self.ev.eval(self.parse(src))
        if np.ndim(q.magnitude) != 0:
            raise EvalError(f"'{src}' must be a single value")
        return q

    def soft(self, line, fn, fallback=None):
        """Run an option's evaluation. A failure marks that option's line and the plot
        carries on without it."""
        try:
            return fn()
        except (EvalError, PlotError, RegressionError, pint.errors.PintError, ValueError, ZeroDivisionError) as e:
            msg = f"Incompatible units: {e}" if isinstance(e, pint.errors.DimensionalityError) else str(e)
            self.errors.append((line, msg))
            return fallback

    def unit_option(self, line, src, current, free=False):
        """The unit an `xunit:` or `yunit:` line gives, which `current` must convert to. With
        `free`, an axis that so far has only points without units takes any unit."""
        def run():
            q = self.scalar(src)
            if q.magnitude != 1:
                raise PlotError("A unit option is a unit such as 'mm, not a quantity")
            if not (free and self._dimless(current)):
                self.ev.Q(1, current).to(q.units)
            return q.units
        return self.soft(line, run, None)

    def in_unit(self, q, disp):
        """A limit or note position as a number in the axis's display unit. A bare number
        is taken to be in that unit already."""
        v = float(q.magnitude) if q.dimensionless and not self._dimless(disp) else float(q.to(disp).magnitude)
        if not math.isfinite(v):
            raise PlotError("A limit or a note position must be a finite number")
        return v

    def _dimless(self, u):
        return not list(self.ev.Q(1, u).unit_items())

    def limits(self, line, value, disp):
        def run():
            out = []
            for src in value:
                out.append(None if src is None else self.in_unit(self.scalar(src), disp))
            if None not in out and out[0] >= out[1]:
                raise PlotError("A limit goes from low to high")
            return tuple(out)
        return self.soft(line, run, (None, None))

    def points(self, srcs):
        """The x and y quantities of one set of points, sorted by x, and a name for each axis. Units
        after the data (`D, 's, 'mm`) are the ones the points are in: values without units take
        them, values with units are converted (see regression.in_unit)."""
        srcs, units = split_points(srcs)
        x, y = columns(self.ev, [self.ev.eval(self.parse(src)) for src in srcs], key="points")[0]
        if len(units) > 0 and units[0] != "auto":
            x = in_unit(self.ev, x, self.scalar(units[0]), "x", "the points' x unit")
        if len(units) > 1 and units[1] != "auto":
            y = in_unit(self.ev, y, self.scalar(units[1]), "y", "the points' y unit")
        for q, what in ((x, "x"), (y, "y")):
            if np.iscomplexobj(q.magnitude):
                raise PlotError(f"The {what} values are complex; plot their re(), im(), abs() or arg()")
        order = np.argsort(np.asarray(x.magnitude, dtype=float), kind="stable")
        names = srcs if len(srcs) == 2 and all(_plain(s) for s in srcs) else ["x", srcs[0]]
        return self.ev.Q(np.asarray(x.magnitude, dtype=float)[order], x.units), \
            self.ev.Q(np.asarray(y.magnitude, dtype=float)[order], y.units), names

    # ---- sampling ---------------------------------------------------------------
    def point(self, node, scope, gaps, var, xv):
        """One sample of a series: a quantity, or None for a gap. A vector of functions (`[f(x), g(x)]`,
        or a function that gives one) gives a vector, its undefined entries NaN (see `expand`)."""
        try:
            q = self.ev.eval(node, scope)
            if np.ndim(q.magnitude) != 0:
                return self.entries(q, var, xv)
            m = q.magnitude
            if np.iscomplexobj(m):
                if abs(m.imag) > _TINY * abs(m):
                    raise EvalError(f"The expression is complex at {var} = {xv:.4g}. "
                                    "Plot its re(), im(), abs() or arg() instead")
                q = self.ev.Q(m.real, q.units)
                m = m.real
            if not math.isfinite(float(m)):
                raise ZeroDivisionError
            return q
        except (ZeroDivisionError, FloatingPointError, OverflowError):
            if gaps == "error":
                raise EvalError(f"The expression is undefined at {var} = {xv:.4g}. "
                                "Use `gaps: break` to leave a gap there") from None
            return None

    def entries(self, q, var, xv):
        m = np.asarray(q.magnitude)
        if m.ndim > 2 or (m.ndim == 2 and 1 not in m.shape):
            raise EvalError("A plotted expression gives a single value or a vector of them (one series each), "
                            "not a matrix")
        m = m.ravel()
        if np.iscomplexobj(m):
            if np.any(np.abs(m.imag) > _TINY * np.abs(m)):
                raise EvalError(f"The expression is complex at {var} = {xv:.4g}. Plot its re(), im(), abs() or arg() instead")
            m = m.real
        return self.ev.Q(np.where(np.isfinite(m), m, np.nan).astype(float), q.units)

    @staticmethod
    def expand(src, samples):
        """A series' samples -> [(label, samples)], one per entry when it gave vectors: a literal
        `[f(x), g(x)]` is labelled by its entries, anything else `F(x)_1`, `F(x)_2`, ..."""
        sizes = {q.magnitude.size for q in samples if q is not None and np.ndim(q.magnitude)}
        if not sizes:
            return [(src, samples)]
        if len(sizes) > 1 or any(q is not None and not np.ndim(q.magnitude) for q in samples):
            raise EvalError(f"'{src}' gives vectors of different lengths along the range; each entry is one series")
        (width,) = sizes
        body = src.strip()
        parts = split_top(body[1:-1].replace(";", ",")) if body.startswith("[") and body.endswith("]") else []
        labels = parts if len(parts) == width and all(parts) else [f"{src}_{k + 1}" for k in range(width)]
        out = []
        for k, label in enumerate(labels):
            col = [None if q is None or not math.isfinite(float(q.magnitude[k])) else q[k] for q in samples]
            out.append((label, col))
        return out

    def build(self, line, series_src, var, lo_src, hi_src, opts, header_points=None):
        """`header_points`: the sources of the points a header with no range plots (`!plot t, s`)."""
        ev = self.ev
        cfg = {**BUILTIN, **ev.mode.plotdefs}
        block, per, notes, at, idxline, point_opts = {}, {}, [], {}, {}, []
        for ln, key, idx, val in opts:
            at[key] = ln
            if idx is not None:
                idxline[idx] = ln
            if key == "note":
                notes.append((ln, val))
            elif key == "points":
                point_opts.append((ln, val))
            elif idx is None:
                block[key] = val
            else:
                per.setdefault(idx, {})[key] = val

        def get(key, i, default=None):
            return per.get(i + 1, {}).get(key, block.get(key, cfg.get(key, default)))

        # ---- points: (line, x, y, axis names, source, series number from 0); the header's have no
        # line. They are numbered after the functions, in order, whether or not they could be read.
        sets = []
        if header_points is not None:
            try:
                sets.append((None, *self.points(header_points), ", ".join(header_points), 0))
            except (EvalError, RegressionError, pint.errors.PintError) as e:
                raise EvalError(f"A plot reads `!plot f(x), x = low .. high`; read as points, `{', '.join(header_points)}` "
                                f"fails: {e}") from None
        for k, (ln, srcs) in enumerate(point_opts, len(series_src) + len(sets)):
            got = self.soft(ln, lambda: self.points(srcs))
            if got:
                sets.append((ln, *got, ", ".join(srcs), k))
        count = len(series_src) + (header_points is not None) + len(point_opts)

        # ---- the range and the x axis ----
        xlog = get("xscale", 0) == "log"
        if header_points is None:
            lo, hi = self.scalar(lo_src), self.scalar(hi_src)
            if lo.dimensionless and lo.magnitude == 0 and not hi.dimensionless:
                lo = ev.Q(0, hi.units)
            elif hi.dimensionless and hi.magnitude == 0 and not lo.dimensionless:
                hi = ev.Q(0, lo.units)
            try:
                hi = hi.to(lo.units)
            except pint.errors.DimensionalityError:
                raise EvalError(f"The ends of the range have different units ({lo.units:~P} and {hi.units:~P})") from None
            xdisp = lo.units
        else:
            var, xdisp = sets[0][3][0], sets[0][1].units
        xgiven = "xunit" in block and self.unit_option(at["xunit"], block["xunit"], xdisp, header_points is not None)
        xdisp = xgiven or xdisp
        sets = self.in_axis(sets, 1, xdisp, "x", bool(xgiven))
        if header_points is not None:
            px = np.concatenate([s[1] for s in sets])
            px = px[px > 0] if xlog else px
            if xlog and px.size == 0:
                raise EvalError("A log x axis needs points above zero")
            x0, x1 = self.auto_y(px, xlog, 0), self.auto_y(px, xlog, 1)
        else:
            x0, x1 = float(lo.to(xdisp).magnitude), float(hi.to(xdisp).magnitude)
        if not (math.isfinite(x0) and math.isfinite(x1)) or x0 >= x1:
            raise EvalError("A plot range goes from low to high")
        if xlog and x0 <= 0:
            raise EvalError("A log x axis needs a range above zero")
        xlim = self.window("x", block, at, xdisp, [x0, x1], xlog)

        # ---- sample over what is visible, so a zoomed view stays smooth ----
        w0, w1 = max(x0, xlim[0]), min(x1, xlim[1])
        n = int(get("samples", 0))
        if w1 > w0:
            xs = np.geomspace(w0, w1, n) if xlog else np.linspace(w0, w1, n)
        else:
            xs = np.array([])
        nodes = [self.parse(s) for s in series_src]
        if n * len(nodes) > MAX_POINTS:
            raise EvalError(f"{len(nodes)} series of {n} samples is too many points to draw on every edit "
                            f"(at most {MAX_POINTS}). Lower samples")
        scope = dict(ev.vars)
        gaps = get("gaps", 0)
        raw = [[] for _ in nodes]
        with np.errstate(all="ignore"):
            for xv in xs:
                scope[var] = ev.Q(float(xv), xdisp)
                for k, node in enumerate(nodes):
                    raw[k].append(self.point(node, scope, gaps, var, float(xv)))
        # A vector of functions is a series per entry, numbered in order, before the points.
        split = [part for src, qs in zip(series_src, raw) for part in self.expand(src, qs)]
        extra = len(split) - len(series_src)
        series_src, raw = [label for label, _ in split], [qs for _, qs in split]
        if n * len(raw) > MAX_POINTS:
            raise EvalError(f"{len(raw)} series of {n} samples is too many points to draw on every edit "
                            f"(at most {MAX_POINTS}). Lower samples")
        sets = [st[:5] + (st[5] + extra,) for st in sets]
        count += extra

        # ---- the y axis ----
        first = next((q for qs in raw for q in qs if q is not None), None)
        only_points = first is None and bool(sets)
        if only_points:
            first = sets[0][2][0]
        if first is None:
            ydisp = ev.Q(1).units
        else:
            ydisp = reduce_si(first, ev.ureg, ev.mode.freq).units if ev.mode.assume else first.units
        ygiven = "yunit" in block and self.unit_option(at["yunit"], block["yunit"],
                                                       first.units if first is not None else ydisp, only_points)
        ydisp = ygiven or ydisp
        ys = []
        for qs in raw:
            good = [q for q in qs if q is not None]
            arr = np.full(len(qs), np.nan)
            if good:
                try:
                    if all(q.units == good[0].units for q in good):
                        vals = ev.Q(np.array([q.magnitude for q in good], dtype=float), good[0].units).to(ydisp).magnitude
                    else:
                        vals = np.array([q.to(ydisp).magnitude for q in good], dtype=float)
                except pint.errors.DimensionalityError:
                    raise EvalError(f"The series have different units ({good[0].units:~P} and {ydisp:~P}). "
                                    "Plot them separately") from None
                arr[[i for i, q in enumerate(qs) if q is not None]] = vals
            ys.append(arr)
        sets = self.in_axis(sets, 2, ydisp, "y", bool(ygiven))
        ys += [np.array(s[2], dtype=float) for s in sets]
        ylog = get("yscale", 0) == "log"
        if ylog:
            for a in ys:
                a[a <= 0] = np.nan
        finite = np.concatenate([a[np.isfinite(a)] for a in ys]) if ys else np.array([])
        explicit = "ylim" in block or "yview" in block
        if ylog and finite.size == 0 and not explicit:
            raise EvalError("A log y axis needs values above zero")
        y_auto = [1.0, 10.0] if ylog and finite.size == 0 else [self.auto_y(finite, ylog, 0), self.auto_y(finite, ylog, 1)]
        ylim = self.window("y", block, at, ydisp, y_auto, ylog)

        # ---- labels, series, notes ----
        xu, yu = unit_text(xdisp), unit_text(ydisp)
        labels = [get("label", i, series_src[i]) for i in range(len(raw))]
        labels += [get("label", i, names[1]) for _, _, _, names, _, i in sets]
        xauto, yauto = "xlabel" not in block, "ylabel" not in block
        xlabel = block["xlabel"] if not xauto else (f"{var} [{xu}]" if xu else var)
        if not yauto:
            ylabel = block["ylabel"]
        elif len(labels) == 1:
            ylabel = f"{labels[0]} [{yu}]" if yu else labels[0]
        else:
            ylabel = f"[{yu}]" if yu else ""
        legend = get("legend", 0)
        legend = ("top right" if count > 1 else None) if legend == "auto" else (None if legend == "off" else legend)
        series = []
        for i, arr in enumerate(ys[:len(raw)]):
            sx, sy = self.break_poles([float(v) for v in xs],
                                      [None if not math.isfinite(v) else float(v) for v in arr], ylim)
            series.append({
                "label": labels[i], "src": series_src[i],
                "color": get("color", i, PALETTE[i % len(PALETTE)]),
                "width": get("width", i), "dash": get("dash", i), "marker": get("marker", i),
                "x": sx, "y": sy, "line": True,
            })
        for k, (_, x, _, _, src, i) in enumerate(sets):   # points: markers, one per point, never joined
            arr, marker = ys[len(raw) + k], get("marker", i)
            series.append({
                "label": labels[len(raw) + k], "src": src,
                "color": get("color", i, PALETTE[i % len(PALETTE)]),
                "width": get("width", i), "dash": get("dash", i), "marker": "circle" if marker == "none" else marker,
                "x": [float(v) for v in x], "y": [None if not math.isfinite(v) else float(v) for v in arr],
                "line": False,
            })
        out_notes = []
        for ln, (text, xs_, ys_) in notes[:MAX_NOTES]:
            pos = self.soft(ln, lambda: (self.in_unit(self.scalar(xs_), xdisp), self.in_unit(self.scalar(ys_), ydisp)))
            if pos:
                out_notes.append({"text": text, "x": pos[0], "y": pos[1]})
        for idx in per:
            if idx > count:
                self.errors.append((idxline[idx], f"There is no series {idx}; this plot has {count}"))

        def axis(name, disp, lim, scale, step_key):
            step = block.get(step_key)
            return {"lim": [float(lim[0]), float(lim[1])], "scale": scale, "step": step,
                    "unit": unit_text(disp), "unit_tex": self.fmt.unit_inline(disp),
                    "unit_src": unit_source(ev, disp), "view": f"{name}view" in block}

        return {
            "line": line, "var": var, "var_tex": name_latex(var), "siunitx": self.fmt.siunitx,
            "title": block.get("title", ""), "size": list(get("size", 0)), "grid": get("grid", 0) == "on",
            "legend": legend,
            "x": {**axis("x", xdisp, xlim, "log" if xlog else "lin", "xstep"), "label": xlabel, "auto_label": xauto},
            "y": {**axis("y", ydisp, ylim, "log" if ylog else "lin", "ystep"), "label": ylabel, "auto_label": yauto},
            "series": series, "notes": out_notes,
            "inherited": {k: canon(k, v) for k, v in cfg.items()},
        }

    def in_axis(self, sets, k, disp, axis, given=False):
        """`sets` with part k (x or y) as plain numbers in the axis's unit. Values without units
        are read in the axis's unit when the plot gives it (`xunit:`, `yunit:`), as a matrix pasted
        without units needs. A set that does not fit the axis is reported on its line and left out;
        the header's is the plot's error."""
        out = []
        for s in sets:
            q = s[k]
            try:
                if q.dimensionless and (given or self._dimless(disp)):
                    v = q.to("dimensionless").magnitude
                else:
                    v = q.to(disp).magnitude
            except pint.errors.DimensionalityError:
                msg = f"The {axis} values are in {q.units:~P}, and the {axis} axis is in {disp:~P}"
                if q.dimensionless:
                    unit = unit_source(self.ev, disp) or f"{disp:~P}"
                    data, units = split_points(split_top(s[4]))
                    units = (units + ["auto", "auto"])[:2]
                    units[k - 1] = unit
                    while units and units[-1] == "auto":
                        units.pop()
                    msg = (f"The {axis} values have no units, and the {axis} axis is in {disp:~P}: give "
                           f"`{axis}unit: {unit}` to read them in it, or the units they are in after them, "
                           f"`points: {', '.join(data + units)}`")
                if s[0] is None:
                    raise EvalError(msg) from None
                self.errors.append((s[0], msg))
                continue
            out.append(s[:k] + (np.asarray(v, dtype=float),) + s[k + 1:])
        return out

    def window(self, name, block, at, disp, auto, log):
        """An axis's limits in three layers: `xview` (what the mouse set) over `xlim` (what the
        author wrote) over automatic. A layer that is wrong is reported on its line and skipped."""
        lim = list(auto)
        for key in (f"{name}lim", f"{name}view"):
            if key not in block:
                continue
            got = self.limits(at[key], block[key], disp)
            if log and any(v is not None and v <= 0 for v in got):
                self.errors.append((at[key], "A log axis needs positive limits"))
                continue
            cand = [lim[k] if got[k] is None else got[k] for k in (0, 1)]
            if cand[0] >= cand[1]:
                self.errors.append((at[key], "A limit goes from low to high"))
                continue
            lim = cand
        return lim

    @staticmethod
    def break_poles(xs, ys, lim):
        """Put a gap where a curve jumps from beyond one y limit to beyond the other, as 1/x does
        at 0. Left alone, every renderer would draw a line straight across the picture."""
        ox, oy = xs[:1], ys[:1]
        for k in range(1, len(xs)):
            a, b = ys[k - 1], ys[k]
            if a is not None and b is not None and ((a > lim[1] and b < lim[0]) or (a < lim[0] and b > lim[1])):
                ox.append((xs[k - 1] + xs[k]) / 2)
                oy.append(None)
            ox.append(xs[k])
            oy.append(b)
        return ox, oy

    @staticmethod
    def auto_y(finite, log, side):
        """5% of headroom above and below the data (a fifth of a decade on a log axis)."""
        if finite.size == 0:
            return (0.0, 1.0)[side]
        lo, hi = float(finite.min()), float(finite.max())
        if log:
            a, b = math.log10(lo), math.log10(hi)
            pad = max((b - a) * 0.05, 0.1 if a == b else 0)
            return 10 ** ((a - pad, b + pad)[side])
        if lo == hi:
            pad = abs(lo) * 0.1 or 1.0
        else:
            pad = (hi - lo) * 0.05
        return (lo - pad, hi + pad)[side]
