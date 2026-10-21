"""Material property lookup. CoolProp is optional and imported on first use, so a
lite install (or binary) never loads it and `props` explains what is missing."""
import re
from functools import lru_cache

import pint

INSTALL_HINT = ("props needs CoolProp, which this build does not include. "
                "Install it with `pip install laconic[coolprop]` or use the full build")


class PropsError(Exception):
    pass


def available():
    try:
        _coolprop()
        return True
    except PropsError:
        return False


@lru_cache(maxsize=1)
def _coolprop():
    try:
        import CoolProp.CoolProp as cp
    except ImportError:
        raise PropsError(INSTALL_HINT) from None
    return cp


@lru_cache(maxsize=None)
def _unit_text(key):
    """CoolProp's SI unit for a parameter key, as text Pint can read ('' if dimensionless)."""
    cp = _coolprop()
    try:
        text = cp.get_parameter_information(cp.get_parameter_index(key), "units")
    except Exception:
        raise PropsError(f"Unknown property '{key}'. Use a CoolProp key such as D, T, P, H, S, Cpmass, V, L, Tcrit") from None
    return "" if text in ("-", "mol/mol") else text.replace("-", "*")


def _clean(msg):
    return re.sub(r"\s+", " ", str(msg)).strip()


def props(ureg, out, *args):
    """props("D", "T", T, "P", p, "Water") -> density. Mirrors CoolProp's PropsSI, but takes
    quantities and returns one: inputs are converted to SI, and the result carries CoolProp's SI unit.
    A fixed property of the fluid needs no state: props("Tcrit", "Water")."""
    if len(args) not in (1, 5):
        raise PropsError('props(output, in1, value1, in2, value2, fluid) or props(output, fluid)')
    cp = _coolprop()
    fluid = args[-1]
    call = [out]
    if not isinstance(out, str) or not isinstance(fluid, str) or any(not isinstance(a, str) for a in args[0:-1:2]):
        raise PropsError('Property names and the fluid are text in quotes, e.g. props("D", "T", T, "P", p, "Water")')
    for key, val in zip(args[0:-1:2], args[1:-1:2]):
        unit = _unit_text(key)
        try:
            si = val.to(ureg.parse_units(unit)) if unit else val.to("dimensionless")
        except pint.errors.DimensionalityError:
            raise PropsError(f"'{key}' needs a value in {unit or 'no unit'}, got {val.units}") from None
        if getattr(si.magnitude, "ndim", 0) != 0:
            raise PropsError("props takes scalars")
        call += [key, float(si.magnitude)]
    call.append(fluid)
    unit = _unit_text(out)
    try:
        value = cp.PropsSI(*call)
    except Exception as e:
        raise PropsError(_clean(e)) from None
    return ureg.Quantity(value, ureg.parse_units(unit) if unit else ureg.dimensionless)
