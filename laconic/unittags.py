"""The tags the units browser filters by: a standard list kept here, and the user's own tags,
kept in the settings file (`settings.py`).

A standard tag is a list of entries. An entry in brackets is a Pint dimension and takes every
unit of that dimension ("[pressure]": Pa, bar, psi, ...); any other entry is one unit as a sheet
spells it ('degC is "degC"). To add a standard tag, or a unit to one, edit `STANDARD_TAGS`.

    browse(global_units, user_tags)   what the page's units dialog shows"""
from functools import lru_cache

from . import catalogue, vocab
from .evaluator import registry

STANDARD_TAGS = {
    "common": list(vocab._COMMON),   # the units the editor offers first
    "constants": [s for s, _, _ in catalogue.CONSTANTS],
    "length": ["[length]"],
    "area": ["[area]"],
    "volume": ["[volume]"],
    "mass": ["[mass]"],
    "time": ["[time]"],
    "speed": ["[velocity]", "[acceleration]"],
    "force": ["[force]"],
    "pressure": ["[pressure]"],
    "energy": ["[energy]", "[power]"],
    "temperature": ["[temperature]"],
    "thermodynamics": ["[temperature]", "[entropy]", "J", "kJ", "MJ", "cal", "Btu", "W", "kW", "hp",
                       "Pa", "kPa", "MPa", "bar", "atm", "psi", "R", "k_B", "sigma"],
    "chemistry": ["[substance]", "N_A", "Av", "R", "k_B", "Da", "u", "M", "ppm", "L", "mL", "eV", "e",
                  "m_e", "m_p", "atm", "bar"],
    "electrical": ["[current]", "[charge]", "[electric_potential]", "[resistance]", "[capacitance]",
                   "[inductance]", "[magnetic_flux]", "[magnetic_field]", "e", "eps_0", "mu_0"],
    "imperial": ["in", "ft", "yd", "mi", "lbm", "lbf", "oz", "ozf", "slug", "kip", "psi", "ksi", "Btu", "hp",
                 "degF", "degR", "delta_degF", "gal", "mph"],
    "currency": list(catalogue.CURRENCIES),
}
GLOBAL_TAG = "global units"   # the units defined under Settings, on every sheet of this instance


@lru_cache(maxsize=1)
def _standard():
    """unit -> its standard tags, over every unit the editor knows."""
    ureg = registry()
    units = vocab._units()
    dims = {}
    for name, _, _ in units:
        try:
            dims[name] = ureg.Quantity(1, name).dimensionality
        except Exception:
            continue
    out = {name: [] for name, _, _ in units}
    for tag, entries in STANDARD_TAGS.items():
        for entry in entries:
            if entry.startswith("["):
                want = ureg.get_dimensionality(entry)
                hits = [n for n, d in dims.items() if d == want]
            else:
                hits = [entry] if entry in out else []
            for n in hits:
                if tag not in out[n]:
                    out[n].append(tag)
    return out


def browse(global_units=(), user_tags=None):
    """{"tags": the standard tags in order, "userTags": {tag: [unit, ...]}, "units": [[name,
    detail, [standard tags]], ...]}. The page adds the user's tags to each unit itself, so a tag
    added in the dialog shows at once. Global units come first, tagged GLOBAL_TAG."""
    std = _standard()
    rows = [[n, "= " + d, [GLOBAL_TAG]] for n, d in global_units]
    rows += [[name, detail, std[name]] for name, detail, _ in vocab._units()]
    return {"tags": list(STANDARD_TAGS) + ([GLOBAL_TAG] if global_units else []),
            "userTags": user_tags or {}, "units": rows}


def clean(tags):
    """The user's tags as they are stored: names trimmed and at most 40 characters, each unit
    once, and no empty tag. Raises ValueError for a tag with no name."""
    out = {}
    for tag, units in tags.items():
        name = " ".join(tag.split())
        if not name:
            raise ValueError("A tag needs a name")
        if len(name) > 40:
            raise ValueError(f"Tag '{name[:40]}...' is longer than 40 characters")
        kept = out.setdefault(name, [])
        for u in units:
            u = u.strip().removeprefix("'")
            if u and u not in kept:
                kept.append(u)
        if not kept:
            del out[name]
    return out
