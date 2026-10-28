"""Builds a plot: samples each series, resolves the options against the defaults,
and returns a plain dict (the spec). The SVG renderer, the pgfplots writer and the
browser all read that dict, so a plot looks the same wherever it is drawn.

Samples are taken point by point rather than on an array: `*` between arrays is a
matrix product in this language, so a vectorised evaluation would be wrong."""
import math

import numpy as np
import pint

from .evaluator import _TINY, EvalError
from .latex import name_latex
from .parser import parse_expr
from .plotopts import BUILTIN, PALETTE, PlotError, canon
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
        except (EvalError, PlotError, pint.errors.PintError, ValueError, ZeroDivisionError) as e:
            msg = f"Incompatible units: {e}" if isinstance(e, pint.errors.DimensionalityError) else str(e)
            self.errors.append((line, msg))
            return fallback

    def unit_option(self, line, src, current):
        def run():
            q = self.scalar(src)
            if q.magnitude != 1:
                raise PlotError("A unit option is a unit such as 'mm, not a quantity")
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

    # ---- sampling ---------------------------------------------------------------
    def point(self, node, scope, gaps, var, xv):
        try:
            q = self.ev.eval(node, scope)
            if np.ndim(q.magnitude) != 0:
                raise EvalError("A plotted expression must give a single value, not a matrix")
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

    def build(self, line, series_src, var, lo_src, hi_src, opts):
        ev = self.ev
        cfg = {**BUILTIN, **ev.mode.plotdefs}
        block, per, notes, at, idxline = {}, {}, [], {}, {}
        for ln, key, idx, val in opts:
            at[key] = ln
            if idx is not None:
                idxline[idx] = ln
            if key == "note":
                notes.append((ln, val))
            elif idx is None:
                block[key] = val
            else:
                per.setdefault(idx, {})[key] = val

        def get(key, i, default=None):
            return per.get(i + 1, {}).get(key, block.get(key, cfg.get(key, default)))

        # ---- the range and the x axis ----
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
        if "xunit" in block:
            xdisp = self.unit_option(at["xunit"], block["xunit"], xdisp) or xdisp
        x0, x1 = float(lo.to(xdisp).magnitude), float(hi.to(xdisp).magnitude)
        if not (math.isfinite(x0) and math.isfinite(x1)) or x0 >= x1:
            raise EvalError("A plot range goes from low to high")
        xlog = get("xscale", 0) == "log"
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

        # ---- the y axis ----
        first = next((q for qs in raw for q in qs if q is not None), None)
        if first is None:
            ydisp = ev.Q(1).units
        else:
            ydisp = reduce_si(first, ev.ureg, ev.mode.freq).units if ev.mode.assume else first.units
        if "yunit" in block and first is not None:
            ydisp = self.unit_option(at["yunit"], block["yunit"], first.units) or ydisp
        elif "yunit" in block:
            ydisp = self.unit_option(at["yunit"], block["yunit"], ydisp) or ydisp
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
        labels = [get("label", i, series_src[i]) for i in range(len(nodes))]
        xauto, yauto = "xlabel" not in block, "ylabel" not in block
        xlabel = block["xlabel"] if not xauto else (f"{var} [{xu}]" if xu else var)
        if not yauto:
            ylabel = block["ylabel"]
        elif len(nodes) == 1:
            ylabel = f"{labels[0]} [{yu}]" if yu else labels[0]
        else:
            ylabel = f"[{yu}]" if yu else ""
        legend = get("legend", 0)
        legend = ("top right" if len(nodes) > 1 else None) if legend == "auto" else (None if legend == "off" else legend)
        series = []
        for i, arr in enumerate(ys):
            sx, sy = self.break_poles([float(v) for v in xs],
                                      [None if not math.isfinite(v) else float(v) for v in arr], ylim)
            series.append({
                "label": labels[i], "src": series_src[i],
                "color": get("color", i, PALETTE[i % len(PALETTE)]),
                "width": get("width", i), "dash": get("dash", i), "marker": get("marker", i),
                "x": sx, "y": sy,
            })
        out_notes = []
        for ln, (text, xs_, ys_) in notes[:MAX_NOTES]:
            pos = self.soft(ln, lambda: (self.in_unit(self.scalar(xs_), xdisp), self.in_unit(self.scalar(ys_), ydisp)))
            if pos:
                out_notes.append({"text": text, "x": pos[0], "y": pos[1]})
        for idx in per:
            if idx > len(nodes):
                self.errors.append((idxline[idx], f"There is no series {idx}; this plot has {len(nodes)}"))

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
