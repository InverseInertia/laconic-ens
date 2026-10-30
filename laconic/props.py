"""Material property lookup through CoolProp, imported on first use to keep startup fast."""
import re
from functools import lru_cache

import pint

INSTALL_HINT = "props needs CoolProp. Install it with `pip install CoolProp`"


class PropsError(Exception):
    pass


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


# Humid air keys for haprops, as HAPropsSI takes them: name -> (SI unit, what it is, usable as an
# input). Per kg is per kg of dry air unless the key ends in "ha" (per kg of humid air).
HA_KEYS = {
    "T": ("K", "dry-bulb temperature", True),
    "B": ("K", "wet-bulb temperature", True),
    "D": ("K", "dew-point temperature", True),
    "P": ("Pa", "pressure", True),
    "R": ("", "relative humidity, 0 to 1", True),
    "W": ("", "humidity ratio, kg water per kg dry air", True),
    "H": ("J/kg", "enthalpy per kg dry air", True),
    "Hha": ("J/kg", "enthalpy per kg humid air", True),
    "S": ("J/kg/K", "entropy per kg dry air", True),
    "Sha": ("J/kg/K", "entropy per kg humid air", False),
    "V": ("m^3/kg", "volume per kg dry air", True),
    "Vha": ("m^3/kg", "volume per kg humid air", True),
    "Y": ("", "water mole fraction", True),
    "P_w": ("Pa", "partial pressure of water", True),
    "C": ("J/kg/K", "specific heat per kg dry air", False),
    "Cha": ("J/kg/K", "specific heat per kg humid air", False),
    "CV": ("J/kg/K", "specific heat at constant volume per kg dry air", False),
    "CVha": ("J/kg/K", "specific heat at constant volume per kg humid air", False),
    "M": ("Pa*s", "viscosity", False),
    "K": ("W/m/K", "conductivity", False),
    "Z": ("", "compressibility factor", False),
}
# CoolProp's other names for the same keys.
HA_ALIASES = {"Tdb": "T", "T_db": "T", "Twb": "B", "T_wb": "B", "WetBulb": "B", "Tdp": "D", "T_dp": "D",
              "DewPoint": "D", "RH": "R", "RelHum": "R", "Omega": "W", "HumRat": "W", "Hda": "H",
              "Enthalpy": "H", "Sda": "S", "Entropy": "S", "Vda": "V", "psi_w": "Y", "cp": "C", "cp_ha": "Cha",
              "cv": "CV", "cv_ha": "CVha", "Visc": "M", "mu": "M", "k": "K", "Conductivity": "K"}


def _ha_unit(key):
    k = HA_ALIASES.get(key, key)
    if k not in HA_KEYS:
        raise PropsError(f"Unknown humid air property '{key}'. Use a key such as T, B, D, P, R, W, H, V")
    return HA_KEYS[k][0]


def haprops(ureg, out, *args):
    """haprops("W", "T", T, "P", p, "R", rh) -> humidity ratio. Mirrors CoolProp's HAPropsSI: the
    output key and three state inputs, one of them the pressure. Inputs are converted to SI, and the
    result carries the key's SI unit."""
    if len(args) != 6:
        raise PropsError('haprops(output, in1, value1, in2, value2, in3, value3), e.g. '
                         'haprops("W", "T", T, "P", p, "R", 0.5)')
    if not isinstance(out, str) or any(not isinstance(a, str) for a in args[0::2]):
        raise PropsError('Property names are text in quotes, e.g. haprops("W", "T", T, "P", p, "R", 0.5)')
    cp = _coolprop()
    call = [out]
    for key, val in zip(args[0::2], args[1::2]):
        unit = _ha_unit(key)
        if isinstance(val, str):
            raise PropsError(f"'{key}' needs a value, not text")
        try:
            si = val.to(ureg.parse_units(unit)) if unit else val.to("dimensionless")
        except pint.errors.DimensionalityError:
            raise PropsError(f"'{key}' needs a value in {unit or 'no unit'}, got {val.units}") from None
        if getattr(si.magnitude, "ndim", 0) != 0:
            raise PropsError("haprops takes scalars")
        call += [key, float(si.magnitude)]
    unit = _ha_unit(out)
    try:
        value = cp.HAPropsSI(*call)
    except Exception as e:
        raise PropsError(_clean(e)) from None
    return ureg.Quantity(value, ureg.parse_units(unit) if unit else ureg.dimensionless)
