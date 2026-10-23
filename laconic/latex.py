"""AST -> LaTeX. Prints the same tree the evaluator ran, so the output layout
(symbolic, substituted, result) is decided here and nowhere else.

Two unit styles: KaTeX-friendly `\\mathrm{kN}` for the live preview, and
siunitx `\\qty{..}{..}` for the exported .tex file."""
import itertools
import re

import numpy as np

from .evaluator import CONSTANTS, EvalError
from .nodes import (BinOp, Call, Convert, Implicit, Matrix, Name, Neg, Num, Str,
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


_ACCENTS = {"!": "\\vec", "@": "\\hat"}
_DOTS = {1: "\\dot", 2: "\\ddot"}


def _accent(tex, marks):
    """Wrap tex in the accents typed after a name, innermost first. A run of
    backticks is one dot per backtick (one or two)."""
    for mark, run in itertools.groupby(marks):
        n = len(list(run))
        if mark == "`":
            if n not in _DOTS:
                raise EvalError("At most two dots fit over a variable")
            tex = f"{_DOTS[n]}{{{tex}}}"
        else:
            tex = f"{_ACCENTS[mark]}{{{tex}}}"
    return tex


def name_latex(name):
    """sigma_max -> \\sigma_{\\mathrm{max}}, x1 -> x_{1}, width -> \\mathrm{width}.
    Marks after the name go over the base symbol, with subscripts outside:
    v` -> \\dot{v}, F_x! -> \\vec{F}_{x}, a@ -> \\hat{a}."""
    name = name.lstrip("~")  # the global marker is source-only
    bare = name.rstrip("`!@")
    marks = name[len(bare):]
    parts = bare.split("_")
    base, subs = parts[0], [p for p in parts[1:] if p]
    m = re.fullmatch(r"([A-Za-z])(\d+)", base)
    if m and not subs:
        base, subs = m.group(1), [m.group(2)]
    out = _accent(_word(base), marks)
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


_DIGIT_WORDS = "Zero One Two Three Four Five Six Seven Eight Nine".split()


def _unit_macro(name):
    """siunitx macro names are letters only: psi_g -> psiUnderg, a2 -> aTwo."""
    return "".join("Under" if c == "_" else _DIGIT_WORDS[int(c)] if c.isdigit() else c for c in name)


class Fmt:
    def __init__(self, ureg, siunitx=False, sig=4, custom=(), places=None, keep_zeros=False):
        """`custom` holds the names of user-defined units. In export mode each one
        gets a siunitx macro, collected in `macros` (name -> macro) for the preamble.
        Results show `sig` significant figures, or `places` decimal places when that is
        set (!sigfigs, !sigfigsbig and !decplace each replace the others); `keep_zeros`
        (!sigfigsbig) pads to exactly `sig` figures, 2.5 -> 2.500. This only changes what is
        printed: the evaluator never rounds."""
        self.ureg, self.siunitx, self.sig, self.places = ureg, siunitx, sig, places
        self.keep_zeros = keep_zeros
        self.custom, self.macros = custom, {}
        self._dimless = ureg.Unit("dimensionless")

    def _macro(self, name):
        if name not in self.macros:
            macro = _unit_macro(name)
            while macro in self.macros.values():
                macro += "X"
            self.macros[name] = macro
        return self.macros[name]

    def _parts(self, x, sig):
        """(mantissa, exponent or None). Plain notation between 1e-4 and 1e7.
        An explicit `sig` (typed-in numbers are shown with 12) always counts significant
        figures; with sig=None the display setting applies, which may be decimal places."""
        x = float(x)
        if sig is None and self.places is not None:
            s = f"{x:.{self.places}f}"
            return (s[1:] if s.startswith("-") and float(s) == 0 else s), None
        keep = self.keep_zeros and sig is None   # typed-in numbers never get padded
        sig = sig or self.sig
        if x == 0:
            return ("0." + "0" * (sig - 1) if keep and sig > 1 else "0"), None
        e = f"{x:.{sig - 1}e}"                   # rounded to sig figures
        mant, exp = e.split("e")
        exp = int(exp)
        if -4 <= exp < 7:
            s = f"{float(e):.{max(0, sig - 1 - exp)}f}"
            return (s if keep or "." not in s else s.rstrip("0").rstrip(".")), None
        return (mant if keep or "." not in mant else mant.rstrip("0").rstrip(".")), exp

    def number(self, x, sig=None):
        mant, exp = self._parts(x, sig)
        return mant if exp is None else f"{mant}\\times 10^{{{exp}}}"

    def unit_inline(self, units):
        """A unit standing alone in an expression."""
        u = self.unit(units)
        return f"\\unit{{{u}}}" if (self.siunitx and u) else u

    def _si_number(self, x, sig=None):
        mant, exp = self._parts(x, sig)
        return mant if exp is None else f"{mant}e{exp}"

    def unit(self, units):
        if units == self._dimless:
            return ""
        if self.siunitx:
            m = re.fullmatch(r"\\si\[\]\{(.*)\}", format(units, "Lx"))
            if not m:
                return ""
            return re.sub(r"\\([A-Za-z_][A-Za-z0-9_]*)",
                          lambda t: "\\" + self._macro(t.group(1)) if t.group(1) in self.custom else t.group(0),
                          m.group(1))
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
            return f"{self._plain_number(mag)} {u}".strip()
        body = np.array2string(mag, formatter={"all": self._plain_number}, separator=" ")
        return body + (f" {u}" if u else "")

    def _plain_number(self, x):
        mant, exp = self._parts(x, None)
        return mant if exp is None else f"{mant}e{exp}"


_FUNC_TEX = {"sin": r"\sin", "cos": r"\cos", "tan": r"\tan", "asin": r"\arcsin",
             "acos": r"\arccos", "atan": r"\arctan", "ln": r"\ln", "log10": r"\log_{10}"}


_BINARY_TEX = {"dot": r"\cdot", "cross": r"\times", "kron": r"\otimes"}


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
        if isinstance(n, Str):
            return f"\\text{{{escape(n.value)}}}", ATOM
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
            if self.subst and (self.expand_matrices or np.ndim(self.ev.vars[self.ev.vkey(name)].magnitude) == 0):
                return self.value(self.ev.vars[self.ev.vkey(name)])
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
        if self.ev.fkey(f) in self.ev.funcs:
            return f"{name_latex(f)}\\left({', '.join(a)}\\right)", ATOM
        if f == "sqrt":
            return f"\\sqrt{{{a[0]}}}", ATOM
        if f == "abs":
            return f"\\left|{a[0]}\\right|", ATOM
        if f == "floor":
            return f"\\left\\lfloor {a[0]} \\right\\rfloor", ATOM
        if f == "ceil":
            return f"\\left\\lceil {a[0]} \\right\\rceil", ATOM
        if f in ("heaviside", "step", "heav"):
            return f"\\operatorname{{H}}\\left({a[0]}\\right)", ATOM
        if f == "props":
            return f"\\mathrm{{props}}\\left({', '.join(a)}\\right)", ATOM
        if f == "exp":
            return f"e^{{{a[0]}}}", POW
        if f == "inv":
            return f"{self.child(n.args[0], ATOM)}^{{-1}}", POW
        if f == "transpose":
            return f"{self.child(n.args[0], ATOM)}^{{T}}", POW
        # Indexing prints as a subscript; the base is braced so subscripts can stack: {A_{i}}_{j}.
        if f == "idx" and len(a) == 2:
            return f"{{{self.child(n.args[0], ATOM)}}}_{{{a[1]}}}", ATOM
        if f == "elem" and len(a) == 3:
            return f"{{{self.child(n.args[0], ATOM)}}}_{{{a[1]},\\,{a[2]}}}", ATOM
        if f == "trace":
            return f"\\operatorname{{tr}}\\left({a[0]}\\right)", ATOM
        if f in _BINARY_TEX and len(a) == 2:
            return f"{self.child(n.args[0], MUL)} {_BINARY_TEX[f]} {self.child(n.args[1], MUL)}", MUL
        if f == "pinv":
            return f"{self.child(n.args[0], ATOM)}^{{+}}", POW
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
    if r.kind == "plot":
        from .plotpgf import pgfplots   # imported late: plotpgf uses this module's escape()
        return pgfplots(r.plot)
    if r.kind == "solver":
        info, vals = r.solver, r.solver["values"]
        note = ""
        if info["status"] != "valid" or info["tainted"]:
            note = f"% line {r.n}: solver result is out of date or not run; values shown may be starting values\n"
        if wrap == "align":
            return note + "\\begin{align*}\n" + " \\\\\n".join(f"{v['lhs']} &= {v['rhs']}" for v in vals) + "\n\\end{align*}"
        body = r",\; ".join(v["latex"] for v in vals)
        return note + (f"\\[ {body} \\]" if wrap == "display" else body)
    if r.kind in ("assign", "expr", "funcdef", "unitdef"):
        if wrap == "align":
            rows = [f"{r.lhs} &= {r.stages[0]}" if r.lhs else f"&{r.stages[0]}"]
            rows += [f"&= {s}" for s in r.stages[1:]]
            return "\\begin{align*}\n" + " \\\\\n".join(rows) + "\n\\end{align*}"
        if wrap == "display":
            return "\\[ " + r.latex + " \\]"
        return r.latex
    return None


def document(results, title=None, declarations=()):
    """Full .tex document. Each calculation becomes an align* block with one
    row per stage, so long lines break at the equals signs instead of overflowing.
    `declarations` are the \\DeclareSIUnit lines for user-defined units."""
    out = [r"\documentclass[11pt]{article}",
           r"\usepackage[margin=2.5cm]{geometry}",
           r"\usepackage{amsmath,amssymb}",
           r"\usepackage{siunitx}  % siunitx v3 or newer (\qty, \unit)",
           r"\sisetup{per-mode=symbol, inter-unit-product=\ensuremath{{\cdot}}}",
           r"\setlength{\parindent}{0pt}"]
    if any(r.kind == "plot" for r in results):
        out += [r"\usepackage{pgfplots}", r"\pgfplotsset{compat=newest}"]
    out += list(declarations)
    out.append(r"\begin{document}")
    if title:
        out.append(rf"\section*{{{escape(title)}}}")
    out += [x for x in (snippet(r, "align") for r in results) if x is not None]
    out.append(r"\end{document}")
    return "\n".join(out) + "\n"
