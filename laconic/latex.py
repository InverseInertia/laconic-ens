"""AST -> LaTeX. Prints the same tree the evaluator ran, so the output layout
(symbolic, substituted, result) is decided here and nowhere else.

Two unit styles: KaTeX-friendly `\\mathrm{kN}` for the live preview, and
siunitx `\\qty{..}{..}` for the exported .tex file."""
import itertools
import re

import numpy as np

from . import catalogue
from .commands import SheetMode
from .exports import Error, Figure, Heading, Paragraph, Source, element, elements
from .evaluator import _TINY, CONSTANTS, EvalError
from .functions import FUNCTIONS
from .nodes import (BinOp, Call, Convert, Implicit, Matrix, Name, Neg, Num, Polar,
                    Str, UnitLit, is_literal)

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
    A subscript that is ∞ or the whole word inf is infinity: T_inf -> T_{\\infty}.
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
        out += "_{" + ",".join("\\infty" if s == "inf" else _word(s) for s in subs) + "}"
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


# Unit symbols in the .tex preamble go through pdflatex, which wants macros for these
# (ℎ is Pint's symbol for Planck's constant, an italic h).
_DECL_GLYPHS = {c: v + " " if v.startswith("\\") else v
                for c, v in {**_GREEK_CHARS, "µ": "\\mu", "∞": "\\infty", "ℎ": "\\mathit{h}"}.items()}


def _glyph(c):
    return "\\infty" if c == "∞" else _GREEK_CHARS.get(c, c)


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
    def __init__(self, ureg, siunitx=False, custom=(), mode=None):
        """`custom` maps the names of user-defined units to their definitions. In export
        mode each one, and each Pint unit siunitx lacks, gets a macro that `declarations`
        writes into the preamble.
        Results are rounded as the sheet `mode` says at the time they are printed
        (significant figures, decimal places, trailing zeros; see commands.SheetMode).
        This only changes what is printed: the evaluator never rounds."""
        self.ureg, self.siunitx = ureg, siunitx
        self.mode = mode or SheetMode()
        self.custom = custom
        self._macros = {}     # units this document declares: name -> macro
        self._builtin = {}    # the Pint units among them: name -> how they print
        self._dimless = ureg.Unit("dimensionless")

    def var(self, key):
        """A variable or function by its stored key. In the live view a global (`~g`) is
        tagged so the page can color and underline it; LaTeX snippets and the export stay plain."""
        tex = name_latex(key)
        if self.siunitx or not key.startswith("~"):
            return tex
        return f"\\htmlData{{global={key[1:]}}}{{{tex}}}"

    def _macro(self, name, spelling=None):
        if name not in self._macros:
            macro = _unit_macro(spelling or name)
            while macro in self._macros.values():
                macro += "X"
            self._macros[name] = macro
        return self._macros[name]

    def declarations(self):
        """The preamble's \\DeclareSIUnit lines for the units printed so far."""
        out = []
        for name, macro in self._macros.items():
            if name in self._builtin:
                out.append(rf"\DeclareSIUnit{{\{macro}}}{{\ensuremath{{{self._builtin[name]}}}}}  % {name}")
                continue
            out.append(f"% 1 {name} = {self.custom.get(name) or '?'}".replace("\n", " "))
            out.append(rf"\DeclareSIUnit{{\{macro}}}{{{escape(name)}}}")
        return out

    def _parts(self, x, sig):
        """(mantissa, exponent or None). Plain notation between 1e-4 and 1e7.
        An explicit `sig` (typed-in numbers are shown with 12) always counts significant
        figures; with sig=None the display setting applies, which may be decimal places."""
        x = float(x)
        mode = self.mode
        if sig is None and mode.places is not None:
            s = f"{x:.{mode.places}f}"
            return (s[1:] if s.startswith("-") and float(s) == 0 else s), None
        keep = mode.keep_zeros and sig is None   # typed-in numbers never get padded
        sig = sig or mode.sig
        if x == 0:
            return ("0." + "0" * (sig - 1) if keep and sig > 1 else "0"), None
        e = f"{x:.{sig - 1}e}"                   # rounded to sig figures
        mant, exp = e.split("e")
        exp = int(exp)
        if -4 <= exp < 7:
            s = f"{float(e):.{max(0, sig - 1 - exp)}f}"
            return (s if keep or "." not in s else s.rstrip("0").rstrip(".")), None
        return (mant if keep or "." not in mant else mant.rstrip("0").rstrip(".")), exp

    # ---- complex numbers ----------------------------------------------------
    # Shown as `3 + 4i` or, under `!complex polar`, `5∠53.13°` with the angle in the trig unit.
    # A part too small to show beside the other (_TINY of the whole) is left out.
    def _split(self, z):
        z = complex(z)
        tiny = _TINY * abs(z)
        return (0.0 if abs(z.real) <= tiny else z.real), (0.0 if abs(z.imag) <= tiny else z.imag)

    def _polar(self, z):
        """(magnitude, angle in the trig unit, the angle's LaTeX mark, its plain mark)."""
        angle = float(np.angle(complex(z)))
        if self.mode.angle == "degree":
            return abs(complex(z)), np.degrees(angle), "^\\circ", "°"
        return abs(complex(z)), angle, "\\,\\mathrm{rad}", " rad"

    def polar_form(self, q):
        return self.mode.complex == "polar" and np.iscomplexobj(q.magnitude)

    def imaginary(self, z, sig=12):
        """A typed-in imaginary number, `4i`, as typed: never polar, and `0i` stays."""
        s = self.number(z.imag, sig)
        return s + ("\\,\\mathrm{i}" if "\\times" in s else "\\mathrm{i}")

    def complex_number(self, z, sig=None):
        """LaTeX for a complex number."""
        if self.mode.complex == "polar":
            r, a, mark, _ = self._polar(z)
            return f"{self.number(r, sig)}\\angle {self.number(a, sig)}{mark}"
        re_, im = self._split(z)
        if im == 0:
            return self.number(re_, sig)
        imag = self.number(abs(im), sig)
        imag += "\\,\\mathrm{i}" if "\\times" in imag else "\\mathrm{i}"
        if re_ == 0:
            return ("-" if im < 0 else "") + imag
        return f"{self.number(re_, sig)} {'-' if im < 0 else '+'} {imag}"

    def _si_complex(self, z, sig=None):
        """`3+4i` as siunitx's \\complexnum reads it."""
        re_, im = self._split(z)
        if im == 0:
            return self._si_number(re_, sig)
        imag = self._si_number(abs(im), sig) + "i"
        if re_ == 0:
            return ("-" if im < 0 else "") + imag
        return f"{self._si_number(re_, sig)}{'-' if im < 0 else '+'}{imag}"

    def _plain_complex(self, z, spaced=True, sig=None):
        if self.mode.complex == "polar":
            r, a, _, mark = self._polar(z)
            return f"{self._plain_number(r, sig)}∠{self._plain_number(a, sig)}{mark}"
        re_, im = self._split(z)
        if im == 0:
            return self._plain_number(re_, sig)
        imag = self._plain_number(abs(im), sig) + "i"
        if re_ == 0:
            return ("-" if im < 0 else "") + imag
        sign = (" - " if im < 0 else " + ") if spaced else ("-" if im < 0 else "+")
        return self._plain_number(re_, sig) + sign + imag

    def number(self, x, sig=None):
        if np.iscomplexobj(x):
            return self.complex_number(x, sig)
        if np.isinf(x):
            return "\\infty" if x > 0 else "-\\infty"
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
            return re.sub(r"\\([A-Za-z_][A-Za-z0-9_]*)", lambda t: "\\" + self._si_macro(t.group(1)), m.group(1))
        return catalogue.subscripted(format(units, "~L"), units, self.ureg)

    def _si_macro(self, name):
        if name in self.custom:
            return self._macro(name)
        known = catalogue.siunitx_macro(name)
        if known:
            return known
        if name not in self._builtin:
            try:
                tex = catalogue.subscripted(format(self.ureg.Unit(name), "~L"), self.ureg.Unit(name), self.ureg)
            except Exception:   # Pint's prefix split can leave a fragment that is no unit
                tex = "\\mathrm{" + escape(name) + "}"
            self._builtin[name] = "".join(_DECL_GLYPHS.get(c, c) for c in tex)
        return self._macro(name, catalogue.declared_macro(name))

    def quantity(self, q, sig=None):
        """Latex for a scalar or matrix Quantity. `sig` as in `_parts`: a typed-in
        quantity is shown with 12 figures, so it reads as it was typed."""
        u = self.unit(q.units)
        mag = np.asarray(q.magnitude)
        if mag.ndim == 0 and np.iscomplexobj(mag):
            return self._complex_quantity(complex(mag), q.units, u, sig)
        if mag.ndim == 0:
            if self.siunitx and u and np.isfinite(mag):   # \qty cannot parse \infty
                return f"\\qty{{{self._si_number(mag, sig)}}}{{{u}}}"
            if self.siunitx and u:
                return f"{self.number(mag, sig)}\\,\\unit{{{u}}}"
            return self.number(mag, sig) + (f"\\,{u}" if u else "")
        mag = np.atleast_2d(mag) if mag.ndim == 1 else mag
        mag = mag.T if np.ndim(q.magnitude) == 1 else mag  # 1-D arrays read as columns
        body = r" \\ ".join(" & ".join(self.number(v, sig) for v in row) for row in mag)
        tex = "\\begin{bmatrix} " + body + " \\end{bmatrix}"
        if u:
            tex += f"\\,\\unit{{{u}}}" if self.siunitx else f"\\,{u}"
        return tex

    def _complex_quantity(self, z, units, u, sig=None):
        """A complex scalar with its unit: `(3 + 4i) V`, or `5 V∠53.13°` in polar form."""
        if self.mode.complex == "polar":
            r, a, mark, _ = self._polar(z)
            return f"{self.quantity(self.ureg.Quantity(r, units), sig)}\\angle {self.number(a, sig)}{mark}"
        re_, im = self._split(z)
        if im == 0:
            return self.quantity(self.ureg.Quantity(re_, units), sig)
        if not u:
            return self.complex_number(z, sig)
        if self.siunitx:
            return f"\\complexqty{{{self._si_complex(z, sig)}}}{{{u}}}"
        return f"\\left({self.complex_number(z, sig)}\\right)\\,{u}"

    def plain(self, q, sig=None):
        mag = np.asarray(q.magnitude)
        u = f"{q.units:~P}"
        if mag.ndim == 0 and np.iscomplexobj(mag):
            z = complex(mag)
            if self.mode.complex == "polar":
                r, a, _, mark = self._polar(z)
                return f"{self._plain_number(r, sig)} {u}".strip() + f"∠{self._plain_number(a, sig)}{mark}"
            text = self._plain_complex(z, sig=sig)
            return f"({text}) {u}" if u and " " in text else f"{text} {u}".strip()
        if mag.ndim == 0:
            return f"{self._plain_number(mag, sig)} {u}".strip()
        body = np.array2string(mag, formatter={"all": lambda x: self._plain_number(x, sig)}, separator=" ")
        return body + (f" {u}" if u else "")

    def _plain_number(self, x, sig=None):
        if np.iscomplexobj(x):
            return self._plain_complex(x, spaced=False, sig=sig)
        if np.isinf(x):
            return "∞" if x > 0 else "-∞"
        mant, exp = self._parts(x, sig)
        return mant if exp is None else f"{mant}e{exp}"


_BINDS = {"add": ADD, "mul": MUL, "neg": NEG, "pow": POW, "atom": ATOM}


class _Arg:
    """A call's argument as a built-in's LaTeX form uses it (see functions.py): `{0}` as
    printed, `{0:atom}` in parentheses unless it binds at least that tightly."""
    def __init__(self, printer, node, tex):
        self.printer, self.node, self.tex = printer, node, tex

    def __format__(self, binds):
        return self.printer.child(self.node, _BINDS[binds]) if binds else self.tex


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
        if mag.ndim == 0 and np.iscomplexobj(mag):
            re_, im = self.fmt._split(mag)
            if self.fmt.polar_form(q) or (re_ and im):
                return s, ADD
            return s, (ADD if (re_ or im) < 0 else MUL)
        if mag.ndim == 0 and float(mag) < 0:
            return s, ADD
        if self.fmt.unit(q.units) or "\\times" in s:
            return s, MUL
        return s, ATOM

    def p(self, n):
        if isinstance(n, Num) and isinstance(n.value, complex):
            # `4i` reads as one number, so `4i^2` is shown as (4i)^2, which is what it computes
            return self.fmt.imaginary(n.value), POW
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
        if isinstance(n, Polar):
            return f"{self.child(n.magnitude, MUL)}\\angle {self.child(n.angle, MUL)}", ADD
        raise TypeError(f"Cannot print {type(n).__name__}")

    def name(self, n):
        name = n.name
        if name in self.local:
            return name_latex(name), ATOM
        if self.ev.is_var(name):
            if self.subst and (self.expand_matrices or np.ndim(self.ev.vars[self.ev.vkey(name)].magnitude) == 0):
                return self.value(self.ev.vars[self.ev.vkey(name)])
            return self.fmt.var(self.ev.vkey(name)), ATOM
        if name in CONSTANTS:
            return {"pi": "\\pi", "e": "e", "∞": "\\infty"}[name], ATOM
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
        v = n.number.value
        if self.fmt.siunitx:
            q = self.ev.eval(n)
            u = self.fmt.unit(q.units)
            if u and isinstance(v, complex):
                return f"\\complexqty{{{self.fmt._si_number(v.imag, 12)}i}}{{{u}}}", MUL
            if u:
                return f"\\qty{{{self.fmt._si_number(v, 12)}}}{{{u}}}", MUL
        parts = [self.fmt.imaginary(v) if isinstance(v, complex) else self.fmt.number(v, sig=12)]
        parts += [self.unit_tex(f) for f in n.factors]
        return "\\,".join(parts), MUL

    def literal(self, n):
        """A typed-in quantity such as `0.72'kg/'L`, shown as its line's result shows it:
        the number, then the whole unit, not a fraction with the number on top."""
        q = self.ev.eval(n)
        mag, u = q.magnitude, self.fmt.unit(q.units)
        if np.ndim(mag) or np.iscomplexobj(mag) or not u or catalogue.holds_constant(q, self.ev.ureg):
            return None
        if self.fmt.siunitx:
            return f"\\qty{{{self.fmt._si_number(mag, 12)}}}{{{u}}}", (ADD if mag < 0 else MUL)
        return f"{self.fmt.number(mag, sig=12)}\\,{u}", (ADD if mag < 0 else MUL)

    def binop(self, n):
        op = n.op
        if op in ("+", "-"):
            return f"{self.child(n.left, ADD)} {op} {self.child(n.right, ADD + 1)}", ADD
        if op in ("*", ".*", "./"):
            sym = {"*": r"\cdot", ".*": r"\odot", "./": r"\oslash"}[op]
            return f"{self.child(n.left, MUL)} {sym} {self.child(n.right, MUL)}", MUL
        if op == "/" and is_literal(n) and (lit := self.literal(n)):
            return lit
        if op == "/":
            return f"\\frac{{{self.tex(n.left)}}}{{{self.tex(n.right)}}}", POW
        if op == "^":
            return f"{self.child(n.left, ATOM)}^{{{self.tex(n.right)}}}", POW
        raise TypeError(op)

    def call(self, n):
        f, a = n.func, [self.tex(x) for x in n.args]
        if self.ev.fkey(f) in self.ev.funcs:
            return f"{self.fmt.var(self.ev.fkey(f))}\\left({', '.join(a)}\\right)", ATOM
        b = FUNCTIONS.get(f)
        if b and b.tex and b.args in (None, len(a)):
            return b.tex.format(*(_Arg(self, x, t) for x, t in zip(n.args, a))), _BINDS[b.binds]
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
    e = element(r, commands=True)
    return None if e is None else _tex(e, wrap)


def _tex(e, wrap):
    """The LaTeX for one export element (see exports.py)."""
    if isinstance(e, Heading):
        return rf"\subsection*{{{escape(e.text)}}}"
    if isinstance(e, Paragraph):
        return "\n".join(escape(line) + r"\par" for line in e.lines)
    if isinstance(e, Error):
        return f"% line {e.n}: {e.message}"
    if isinstance(e, Source):
        return f"% {e.text}"
    if isinstance(e, Figure):
        from .plotpgf import pgfplots   # imported late: plotpgf uses this module's escape()
        return pgfplots(e.plot.spec)
    note = f"% line {e.n}: solver result is out of date or not run; values shown may be starting values\n" if e.out_of_date else ""
    if wrap == "align":
        return note + "\\begin{align*}\n" + " \\\\\n".join(e.rows) + "\n\\end{align*}"
    return note + (f"\\[ {e.inline} \\]" if wrap == "display" else e.inline)


def document(results, title=None, declarations=()):
    """Full .tex document. Each calculation becomes an align* block with one
    row per stage, so long lines break at the equals signs instead of overflowing.
    `declarations` are the \\DeclareSIUnit lines from `Fmt.declarations`."""
    out = [r"\documentclass[11pt]{article}",
           r"\usepackage[margin=2.5cm]{geometry}",
           r"\usepackage{amsmath,amssymb}",
           r"\usepackage{siunitx}  % siunitx v3 or newer (\qty, \unit)",
           r"\sisetup{per-mode=symbol, inter-unit-product=\ensuremath{{\cdot}}}",
           r"\setlength{\parindent}{0pt}"]
    els = elements(results, commands=True)
    if any(isinstance(e, Figure) for e in els):
        out += [r"\usepackage{pgfplots}", r"\pgfplotsset{compat=newest}"]
    out += list(declarations)
    out.append(r"\begin{document}")
    if title:
        out.append(rf"\section*{{{escape(title)}}}")
    out += [_tex(e, "align") for e in els]
    out.append(r"\end{document}")
    return "\n".join(out) + "\n"
