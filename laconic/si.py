"""Default display units: reduce a computed result to coherent SI and give it
a familiar derived-unit name when there is one.

Where one dimension has several common names, the first entry in _PREFERRED
wins. That is how the ambiguous cases are settled: energy and torque are both
kg m^2/s^2 and come out as J; 1/s comes out as Hz. An explicit `->` conversion
overrides all of this."""
from functools import lru_cache

_BASE = ("kilogram", "meter", "second", "ampere", "kelvin", "mole", "candela")

# Priority order. Earlier entries claim a dimension first.
_PREFERRED = [
    "N", "J", "W", "Pa", "Hz", "C", "V", "ohm", "F", "H", "S", "Wb", "T",
    "N/m", "m/N", "N*m**2", "Pa*s", "W/m**2", "W/m**3", "W/(m*K)", "J/K", "J/(kg*K)",
    "V/m", "F/m", "H/m",
]


def _key(items):
    """Dimension key from base-unit exponents, or None if something other than
    an SI base unit is present (e.g. radian)."""
    if any(name not in _BASE for name in items):
        return None
    return tuple(round(float(items.get(b, 0)), 9) for b in _BASE)


@lru_cache(maxsize=None)
def _table(ureg):
    table = {}
    for target in _PREFERRED:
        key = _key(dict(ureg.Quantity(1, target).to_base_units().unit_items()))
        table.setdefault(key, target)
    return table


def reduce_si(q, ureg):
    """Return q expressed in the simplest coherent SI unit."""
    names = [n for n, _ in q.unit_items()]
    if not names:
        return q
    # Temperatures: degC stays, degF becomes degC. Kelvin is already SI.
    if "degree_Fahrenheit" in names and len(names) == 1:
        return q.to("degC")
    if "degree_Celsius" in names:
        return q
    r = q.to_base_units()
    items = dict(r.unit_items())
    if not items:                      # dimensionless, e.g. m/mm
        return ureg.Quantity(r.magnitude)
    if "radian" in items:              # angles and rad/s keep their radians
        return r
    target = _table(ureg).get(_key(items))
    return r.to(target) if target else r
