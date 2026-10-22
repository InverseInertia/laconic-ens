"""What the editor can suggest: units, functions, constants and commands."""
from functools import lru_cache

from .evaluator import CONSTANTS, Evaluator, registry

COMMANDS = [
    ("clear", "remove all non-global variables"),
    ("clearf", "remove all non-global functions"),
    ("noassume", "keep typed units in results"),
    ("assume", "reduce results to SI again"),
    ("trigdeg", "trig functions use degrees"),
    ("trigrad", "trig functions use radians"),
    ("short", "show only final results, no steps"),
    ("long", "show steps again"),
    ("plot", "plot functions: !plot f(x), x = 0 .. 1"),
    ("plotspec", "set a plot option for the plots below, e.g. !plotspec grid: off"),
]

# Signature shown next to each function. Anything missing shows just its name.
_SIGNATURES = {
    "sqrt": "sqrt(x)", "abs": "abs(x)", "floor": "floor(x)", "ceil": "ceil(x)",
    "heaviside": "heaviside(x)", "step": "step(x)", "heav": "heav(x)", "sin": "sin(angle)", "cos": "cos(angle)", "tan": "tan(angle)",
    "asin": "asin(x)", "acos": "acos(x)", "atan": "atan(x)", "exp": "exp(x)", "ln": "ln(x)",
    "log10": "log10(x)", "det": "det(A)", "inv": "inv(A)", "transpose": "transpose(A)",
    "norm": "norm(x)", "identity": "identity(n)", "solve": "solve(A, b)",
    "idx": "idx(A, i)", "elem": "elem(A, i, j)", "row": "row(A, i)", "col": "col(A, j)",
    "rows": "rows(A)", "cols": "cols(A)", "length": "length(A)", "trace": "trace(A)",
    "rank": "rank(A)", "cond": "cond(A)", "pinv": "pinv(A)", "diag": "diag(A)",
    "zeros": "zeros(rows, cols)", "ones": "ones(rows, cols)", "lstsq": "lstsq(A, b)",
    "chol": "chol(A)", "eigvals": "eigvals(A)", "eigvecs": "eigvecs(A)", "svdvals": "svdvals(A)",
    "dot": "dot(a, b)", "cross": "cross(a, b)", "kron": "kron(A, B)",
    "hstack": "hstack(A, B, ...)", "vstack": "vstack(A, B, ...)",
    "sum": "sum(A)", "mean": "mean(A)", "min": "min(A)", "max": "max(A)",
    "props": 'props("D", "T", T, "P", p, "Water")',
}

# Offered first, and the ones that get SI prefixes spelled out (kN, mm, GPa).
_COMMON = ("m s kg g A K mol cd N Pa J W Hz C V ohm F H S Wb T L Wh bar eV rad deg degC degF "
           "mm cm km kN MN GPa MPa kPa kW MW kJ MJ mA mV kV us ms min h day in ft yd mi lbm lbf psi ksi").split()
_PREFIXABLE = "m g s A K mol N Pa J W Hz C V ohm F H S Wb T L Wh bar eV".split()
_PREFIXES = "T G M k c m u n p".split()


@lru_cache(maxsize=1)
def _units():
    ureg = registry()
    names = getattr(ureg, "_units", None) or {}
    seen, out = set(), []

    def add(text, detail, common):
        if text not in seen:
            seen.add(text)
            out.append([text, detail, int(common)])

    for key in sorted(names, key=lambda k: (len(k), k)):
        try:
            add(key, ureg.get_name(key), key in _COMMON)
        except Exception:
            continue
    for base in _PREFIXABLE:
        for p in _PREFIXES:
            text = p + base
            if text in seen:
                continue
            try:
                add(text, str(ureg.parse_units(text)), text in _COMMON)
            except Exception:
                continue
    return out


def vocabulary(global_units=()):
    """Everything the editor completes from, for this instance."""
    funcs = sorted(n[3:] for n in dir(Evaluator) if n.startswith("fn_"))
    return {
        "units": _units(),
        "globalUnits": [[n, d] for n, d in global_units],
        "functions": [[f, _SIGNATURES.get(f, f)] for f in funcs],
        "constants": sorted(CONSTANTS),
        "commands": [list(c) for c in COMMANDS],
    }
