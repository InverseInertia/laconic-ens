"""AST -> LaTeX. Prints the same tree the evaluator ran, so the output layout
(symbolic, substituted, result) is decided here and nowhere else.

Two unit styles: KaTeX-friendly `\\mathrm{kN}` for the live preview, and
siunitx `\\qty{..}{..}` for the exported .tex file."""
import re

import numpy as np

from .evaluator import CONSTANTS
from .nodes import (BinOp, Call, Convert, Implicit, Matrix, Name, Neg, Num,
                    UnitLit)

# Precedence levels. A child is wrapped in parentheses when its level is lower
# than the level the parent requires.
ADD, MUL, NEG, POW, ATOM = 1, 2, 3, 4, 5

GREEK = {g: "\\" + g for g in (
    "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi "
    "pi rho sigma tau upsilon phi chi psi omega").split()}
GREEK.update({g: "\\" + g for g in
              "Gamma Delta Theta Lambda Xi Pi Sigma Phi Psi Omega".split()})
GREEK["varepsilon"] = "\\varepsilon"


def name_latex(name):
    """sigma_max -> \\sigma_{\\mathrm{max}}, x1 -> x_{1}, width -> \\mathrm{width}."""
    name = name.lstrip("~")  # the global marker is source-only
    parts = name.split("_")
    base, subs = parts[0], [p for p in parts[1:] if p]
    m = re.fullmatch(r"([A-Za-z])(\d+)", base)
    if m and not subs:
        base, subs = m.group(1), [m.group(2)]
    out = _word(base)
    if subs:
        out += "_{" + ",".join(_word(s) for s in subs) + "}"
    return out


_GREEK_CHARS = {
    "α": "\\alpha", "β": "\\beta", "γ": "\\gamma", "δ": "\\delta", "ε": "\\epsilon",
    "ζ": "\\zeta", "η": "\\eta", "θ": "\\theta", "ι": "\\iota", "κ": "\\kappa",
    "λ": "\\lambda", "μ": "\\mu", "ν": "\\nu", "ξ": "\\xi", "ο": "o", "π": "\\pi",
    "ρ": "\\rho", "σ": "\\sigma", "τ": "\\tau", "υ": "\\upsilon", "φ": "\\phi",
    "ϕ": "\\varphi", "χ": "\\chi", "ψ": "\\psi", "ω": "\\omega", "ς": "\\varsigma",
    "Γ": "\\Gamma", "Δ": "\\Delta", "Θ": "\\Theta", "Λ": "\\Lambda", "Ξ": "\\Xi",
    "Π": "\\Pi", "Σ": "\\Sigma", "Φ": "\\Phi", "Ψ": "\\Psi", "Ω": "\\Omega",
    "Υ": "\\Upsilon", "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I",
    "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Χ": "X",
}


def _glyph(c):
    return _GREEK_CHARS.get(c, c)


def _word(w):
    if w in GREEK:
        return GREEK[w]
    if len(w) == 1 or w.isdigit():
        return _glyph(w)
    inner = "".join(_glyph(c) + (" " if _glyph(c).startswith("\\") else "") for c in w).rstrip()
    return "\\mathrm{" + inner + "}"


class Fmt:
    def __init__(self, ureg, siunitx=False, sig=4):
        self.ureg, self.siunitx, self.sig = ureg, siunitx, sig
        self._dimless = ureg.Unit("dimensionless")

    def _parts(self, x, sig):
        """(mantissa, exponent or None). Plain notation between 1e-4 and 1e7."""
        x = float(x)
        if x == 0:
            return "0", None
        s = f"{x:.{sig}g}"
        if "e" not in s:
            return s, None
        mant, exp = s.split("e")
        exp = int(exp)
        if -4 <= exp < 7:
            return format(float(s), "f").rstrip("0").rstrip("."), None
        return mant, exp

    def number(self, x, sig=None):
        mant, exp = self._parts(x, sig or self.sig)
        return mant if exp is None else f"{mant}\\times 10^{{{exp}}}"

    def unit_inline(self, units):
        """A unit standing alone in an expression."""
        u = self.unit(units)
        return f"\\unit{{{u}}}" if (self.siunitx and u) else u

    def _si_number(self, x, sig=None):
        mant, exp = self._parts(x, sig or self.sig)
        return mant if exp is None else f"{mant}e{exp}"

    def unit(self, units):
        if units == self._dimless:
            return ""
        if self.siunitx:
            m = re.fullmatch(r"\\si\[\]\{(.*)\}", format(units, "Lx"))
            return m.group(1) if m else ""
        return format(units, "~L")

    def quantity(self, q):
        """Latex for a scalar or matrix Quantity."""
        u = self.unit(q.units)
        mag = np.asarray(q.magnitude)
        if mag.ndim == 0:
            if self.siunitx and u:
                return f"\\qty{{{self._si_number(mag)}}}{{{u}}}"
            return self.number(mag) + (f"\\,{u}" if u else "")
        mag = np.atleast_2d(mag) if mag.ndim == 1 else mag
        mag = mag.T if np.ndim(q.magnitude) == 1 else mag  # 1-D arrays read as columns
        body = r" \\ ".join(" & ".join(self.number(v) for v in row) for row in mag)
        tex = "\\begin{bmatrix} " + body + " \\end{bmatrix}"
        if u:
            tex += f"\\,\\unit{{{u}}}" if self.siunitx else f"\\,{u}"
        return tex

    def plain(self, q):
        mag = np.asarray(q.magnitude)
        u = f"{q.units:~P}"
        if mag.ndim == 0:
            return f"{self._parts(mag, self.sig)[0] if self._parts(mag, self.sig)[1] is None else f'{float(mag):.{self.sig}g}'} {u}".strip()
        return np.array2string(mag, precision=self.sig) + (f" {u}" if u else "")


_FUNC_TEX = {"sin": r"\sin", "cos": r"\cos", "tan": r"\tan", "asin": r"\arcsin",
             "acos": r"\arccos", "atan": r"\arctan", "ln": r"\ln", "log10": r"\log_{10}"}


class Printer:
    def __init__(self, ev, fmt, subst=False, local=(), expand_matrices=False):
        self.ev, self.fmt, self.subst, self.local = ev, fmt, subst, set(local)
        self.expand_matrices = expand_matrices

    def tex(self, node):
        return self.p(node)[0]

    def child(self, node, need):
        s, prec = self.p(node)
        return f"\\left({s}\\right)" if prec < need else s

    def value(self, q):
        s = self.fmt.quantity(q)
        mag = np.asarray(q.magnitude)
        if mag.ndim == 0 and float(mag) < 0:
            return s, ADD
        if self.fmt.unit(q.units) or "\\times" in s:
            return s, MUL
        return s, ATOM

    def p(self, n):
        if isinstance(n, Num):
            s = self.fmt.number(n.value, sig=12)
            return s, (MUL if "\\times" in s else ATOM)
        if isinstance(n, Name):
            return self.name(n)
        if isinstance(n, UnitLit):
            return self.fmt.unit_inline(self.ev.ureg.parse_units(n.unit)), ATOM
        if isinstance(n, Neg):
            return "-" + self.child(n.operand, POW), NEG
        if isinstance(n, Implicit):
            return self.implicit(n)
        if isinstance(n, BinOp):
            return self.binop(n)
        if isinstance(n, Call):
            return self.call(n)
        if isinstance(n, Matrix):
            body = r" \\ ".join(" & ".join(self.tex(e) for e in row) for row in n.rows)
            return "\\begin{bmatrix} " + body + " \\end{bmatrix}", ATOM
        if isinstance(n, Convert):
            return self.p(n.expr)
        raise TypeError(f"Cannot print {type(n).__name__}")

    def name(self, n):
        name = n.name
        if name in self.local:
            return name_latex(name), ATOM
        if self.ev.is_var(name):
            if self.subst and (self.expand_matrices or np.ndim(self.ev.vars[name].magnitude) == 0):
                return self.value(self.ev.vars[name])
            return name_latex(name), ATOM
        if name in CONSTANTS:
            return ("\\pi" if name == "pi" else "e"), ATOM
        # Not defined yet (e.g. a function body that uses a later variable): keep it symbolic.
        return name_latex(name), ATOM

    def unit_tex(self, node):
        if isinstance(node, UnitLit):
            return self.fmt.unit(self.ev.ureg.parse_units(node.unit))
        base = self.unit_tex(node.left)
        if "\\frac" in base:
            base = f"\\left({base}\\right)"
        return f"{base}^{{{self.tex(node.right)}}}"

    def implicit(self, n):
        # Always rendered `number, thin space, unit`. Units never become variables here.
        if self.fmt.siunitx:
            q = self.ev.eval(n)
            u = self.fmt.unit(q.units)
            if u:
                return f"\\qty{{{self.fmt._si_number(n.number.value, 12)}}}{{{u}}}", MUL
        parts = [self.fmt.number(n.number.value, sig=12)]
        parts += [self.unit_tex(f) for f in n.factors]
        return "\\,".join(parts), MUL

    def binop(self, n):
        op = n.op
        if op in ("+", "-"):
            return f"{self.child(n.left, ADD)} {op} {self.child(n.right, ADD + 1)}", ADD
        if op in ("*", ".*", "./"):
            sym = {"*": r"\cdot", ".*": r"\odot", "./": r"\oslash"}[op]
            return f"{self.child(n.left, MUL)} {sym} {self.child(n.right, MUL)}", MUL
        if op == "/":
            return f"\\frac{{{self.tex(n.left)}}}{{{self.tex(n.right)}}}", POW
        if op == "^":
            return f"{self.child(n.left, ATOM)}^{{{self.tex(n.right)}}}", POW
        raise TypeError(op)

    def call(self, n):
        f, a = n.func, [self.tex(x) for x in n.args]
        if f in self.ev.funcs:
            return f"{name_latex(f)}\\left({', '.join(a)}\\right)", ATOM
        if f == "sqrt":
            return f"\\sqrt{{{a[0]}}}", ATOM
        if f == "abs":
            return f"\\left|{a[0]}\\right|", ATOM
        if f == "exp":
            return f"e^{{{a[0]}}}", POW
        if f == "inv":
            return f"{self.child(n.args[0], ATOM)}^{{-1}}", POW
        if f == "transpose":
            return f"{self.child(n.args[0], ATOM)}^{{T}}", POW
        if f == "det":
            return f"\\det\\left({a[0]}\\right)", ATOM
        if f == "norm":
            return f"\\left\\lVert {a[0]} \\right\\rVert", ATOM
        if f in _FUNC_TEX:
            return f"{_FUNC_TEX[f]}\\left({a[0]}\\right)", ATOM
        return f"\\mathrm{{{f}}}\\left({', '.join(a)}\\right)", ATOM


_TEX_SPECIAL = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
                "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\^{}"}


def escape(text):
    return "".join(_TEX_SPECIAL.get(c, c) for c in text)


WRAPS = ("inline", "display", "align")


def snippet(r, wrap="inline"):
    """The LaTeX for one worksheet line. `wrap` chooses how a calculation is
    wrapped: "inline" is bare math for pasting into $...$ or \\(...\\),
    "display" is \\[ ... \\], "align" is an align* block with one row per stage.
    Returns None for blank lines."""
    if r.kind == "heading":
        return rf"\subsection*{{{escape(r.text)}}}"
    if r.kind == "comment":
        return escape(r.text) + r"\par"
    if r.kind == "error":
        return f"% line {r.n}: {r.error}"
    if r.kind == "command":
        return f"% {r.source.strip()}"
    if r.kind in ("assign", "expr", "funcdef"):
        if wrap == "align":
            rows = [f"{r.lhs} &= {r.stages[0]}" if r.lhs else f"&{r.stages[0]}"]
            rows += [f"&= {s}" for s in r.stages[1:]]
            return "\\begin{align*}\n" + " \\\\\n".join(rows) + "\n\\end{align*}"
        if wrap == "display":
            return "\\[ " + r.latex + " \\]"
        return r.latex
    return None


def document(results, title=None):
    """Full .tex document. Each calculation becomes an align* block with one
    row per stage, so long lines break at the equals signs instead of overflowing."""
    out = [r"\documentclass[11pt]{article}",
           r"\usepackage[margin=2.5cm]{geometry}",
           r"\usepackage{amsmath,amssymb}",
           r"\usepackage{siunitx}  % siunitx v3 or newer (\qty, \unit)",
           r"\sisetup{per-mode=symbol, inter-unit-product=\ensuremath{{\cdot}}}",
           r"\setlength{\parindent}{0pt}",
           r"\begin{document}"]
    if title:
        out.append(rf"\section*{{{escape(title)}}}")
    out += [x for x in (snippet(r, "align") for r in results) if x is not None]
    out.append(r"\end{document}")
    return "\n".join(out) + "\n"
