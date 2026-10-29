"""What the editor can suggest: units, functions, constants and commands."""
from functools import lru_cache

from . import catalogue, regression, solver, symsolve
from .commands import COMMANDS
from .evaluator import CONSTANTS, registry
from .functions import FUNCTIONS
from .si import reduce_si

# Offered first, and the ones that get SI prefixes spelled out (kN, mm, GPa).
_COMMON = ("m s kg g A K mol cd N Pa J W Hz C V ohm F H S Wb T L Wh bar eV rad deg degC degF "
           "mm cm km kN MN GPa MPa kPa kW MW kJ MJ mA mV kV us ms min h day in ft yd mi lbm lbf psi ksi "
           "% USD EUR GBP").split()
_PREFIXABLE = "m g s A K mol N Pa J W Hz C V ohm F H S Wb T L Wh bar eV".split()
_PREFIXES = "T G M k c m u n p".split()


def _value(q, ureg):
    """A constant's value in SI, as the editor shows it: 8.31446261815 J/K/mol."""
    q = reduce_si(q, ureg)
    return f"{q.magnitude:.12g} {q.units:~P}".strip()


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
        if catalogue.is_ratio(key):   # mm/mm is typed as 'mm/'mm, not as a unit of its own
            continue
        try:
            detail = catalogue.detail(key) or ureg.get_name(key)
            if catalogue.is_constant(key):   # its description and value, so `gas` or `boltz` finds it
                detail = f"{detail}, {_value(ureg.Quantity(1, key), ureg)}"
            add(key, detail, key in _COMMON)
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
    return {
        "units": _units(),
        "globalUnits": [[n, d] for n, d in global_units],
        "functions": [[f, FUNCTIONS[f].signature] for f in sorted(FUNCTIONS)],
        "constants": sorted(CONSTANTS),
        "commands": [[c.name, c.summary] for c in COMMANDS],
        "solver": {
            "keys": {**{kind: [[k, solver.KEY_NOTES[k]] for k in keys] for kind, keys in solver.KEYS.items()},
                     "regression": [[k, regression.KEY_NOTES[k]] for k in regression.KEYS],
                     "symsolve": [[k, symsolve.KEY_NOTES[k]] for k in symsolve.KEYS]},
            "methods": {"root": [[m, solver.METHOD_NOTES[m]] for m in solver.ROOT_METHODS],
                        "optimize": [[m, solver.METHOD_NOTES[m]] for m in solver.MIN_METHODS]},
            "choices": {"autorun": [["on", "solve again after the inputs change"], ["off", "only when Run is pressed"]]},
        },
    }


# props() keys in the order they are offered: the common state and transport properties first.
PROPS_KEYS = ("T P D H S U Q Cpmass Cvmass V L A I Prandtl Z Gmass Hmolar Smolar Tcrit Pcrit rhocrit M "
              "Tmin Tmax Ttriple ptriple isobaric_expansion_coefficient Phase").split()


# Offered first when nothing is typed yet; the rest follow alphabetically.
COMMON_FLUIDS = ("Water", "Air", "Nitrogen", "Oxygen", "CarbonDioxide", "Ammonia", "R134a", "R410A", "R32",
                 "R1234yf", "Propane", "Methane", "Hydrogen", "Helium", "Argon")


@lru_cache(maxsize=1)
def props_vocabulary():
    """Keys and fluids for the strings inside props(...). Separate from vocabulary() because importing
    CoolProp takes a few seconds; the page asks for this only once a props string is being typed.
    keys: [key, description, SI unit, usable as a state input, fixed for a fluid (needs no state)]"""
    try:
        import CoolProp.CoolProp as cp
    except ImportError:
        return {"keys": [], "fluids": []}
    keys = []
    for k in PROPS_KEYS:
        try:
            i = cp.get_parameter_index(k)
            unit = cp.get_parameter_information(i, "units")
            keys.append([k, cp.get_parameter_information(i, "long"), "" if unit in ("-", "mol/mol") else unit,
                         cp.get_parameter_information(i, "IO") == "IO", bool(cp.is_trivial_parameter(i))])
        except Exception:
            continue
    fluids = []
    names = cp.get_global_param_string("FluidsList").split(",")
    common = [n for n in COMMON_FLUIDS if n in names]
    for name in common + sorted((n for n in names if n not in common), key=str.lower):
        try:
            raw = cp.get_fluid_param_string(name, "aliases").split(",")
        except Exception:
            raw = []
        seen, aliases = {name.lower()}, []
        for a in raw:      # CoolProp lists case variants (water, WATER); keep one of each
            if a and a.lower() not in seen:
                seen.add(a.lower())
                aliases.append(a)
        fluids.append([name, ", ".join(["pure fluid"] + aliases[:4])])
    for name in cp.get_global_param_string("incompressible_list_pure").split(","):
        if name:
            fluids.append(["INCOMP::" + name, "incompressible liquid"])
    for name in cp.get_global_param_string("incompressible_list_solution").split(","):
        if name:
            fluids.append([f"INCOMP::{name}[0.3]", "incompressible solution; [0.3] is the fraction, edit it"])
    return {"keys": keys, "fluids": fluids}
