"""What the editor can suggest: units, functions, constants and commands."""
from functools import lru_cache

from .evaluator import CONSTANTS, Evaluator, registry

COMMANDS = [
    ("clear", "remove all non-global variables"),
    ("noassume", "keep typed units in results"),
    ("assume", "reduce results to SI again"),
    ("trigdeg", "trig functions use degrees"),
    ("trigrad", "trig functions use radians"),
]

# Signature shown next to each function. Anything missing shows just its name.
_SIGNATURES = {
    "sqrt": "sqrt(x)", "abs": "abs(x)", "sin": "sin(angle)", "cos": "cos(angle)", "tan": "tan(angle)",
    "asin": "asin(x)", "acos": "acos(x)", "atan": "atan(x)", "exp": "exp(x)", "ln": "ln(x)",
    "log10": "log10(x)", "det": "det(A)", "inv": "inv(A)", "transpose": "transpose(A)",
    "norm": "norm(x)", "identity": "identity(n)", "solve": "solve(A, b)",
}

# Offered first, and the ones that get SI prefixes spelled out (kN, mm, GPa).
_COMMON = ("m s kg g A K mol cd N Pa J W Hz C V ohm F H S Wb T L Wh bar eV rad deg degC degF "
           "mm cm km kN MN GPa MPa kPa kW MW kJ MJ mA mV kV us ms min h day in ft yd mi lb lbf psi ksi").split()
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
