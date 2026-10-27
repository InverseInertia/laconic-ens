"""The unit catalogue: what LENS knows about the unit families Pint alone does not
handle the way a worksheet wants. Each family's policy sits here in one place:
its dimension, how the export spells it, how `si.reduce_si` treats a result in
it, the editor's detail text and the hint or error that names it. Other modules
ask the catalogue instead of keeping lists of their own.

The families:

- currencies: ISO 4217 codes, each a dimension of its own
- percent: Pint's dimensionless `percent`, kept on a result that is only percent
- physical constants ('R, 'k_B, 'h_P), typed as units so they never take a variable's name
- constants with subscripted symbols (g_0, m_e, N_A, µ_0)
- Pint units siunitx lacks, which the export declares itself
- offset temperatures ('degC, 'degF, 'degRe), which mean something else after * or /"""
import re
from functools import lru_cache

# ISO 4217 codes. Each is a dimension of its own: exchange rates change, so 'USD + 'EUR is an
# error and a rate is an ordinary variable (rate = 1.08'USD/'EUR). Symbols such as $ are not
# units, because several currencies share them.
CURRENCIES = {
    "USD": "US dollar", "EUR": "euro", "GBP": "pound sterling", "JPY": "Japanese yen",
    "CNY": "Chinese yuan", "CAD": "Canadian dollar", "AUD": "Australian dollar",
    "NZD": "New Zealand dollar", "CHF": "Swiss franc", "HKD": "Hong Kong dollar",
    "SGD": "Singapore dollar", "SEK": "Swedish krona", "NOK": "Norwegian krone",
    "DKK": "Danish krone", "PLN": "Polish zloty", "CZK": "Czech koruna", "HUF": "Hungarian forint",
    "KRW": "South Korean won", "TWD": "New Taiwan dollar", "INR": "Indian rupee",
    "BRL": "Brazilian real", "MXN": "Mexican peso", "ZAR": "South African rand",
    "TRY": "Turkish lira", "ILS": "Israeli shekel", "AED": "UAE dirham", "SAR": "Saudi riyal",
}

# Physical constants, typed as units: 'R, 'k_B, 'h_P. As units they never take a variable's name,
# so a sheet can set R = 5'ohm and still use 'R. Each entry is the spelling a sheet types, what it is,
# and the Pint definition that adds the spelling, or None when Pint already has it. The values are
# Pint's (CODATA). The editor suggests every entry with its value; a line that uses one shows its
# value in SI. To add a constant, add a line here.
CONSTANTS = [
    ("R", "universal gas constant", None),
    ("N_A", "Avogadro constant", None),
    ("Av", "Avogadro's number, a plain count", "Av = avogadro_number"),
    ("k_B", "Boltzmann constant", None),
    ("c", "speed of light in vacuum", None),
    ("h_P", "Planck constant", "@alias planck_constant = h_P"),   # 'h is the hour
    ("hbar", "reduced Planck constant", None),
    ("e", "elementary charge", None),
    ("sigma", "Stefan-Boltzmann constant", None),
    ("G_N", "Newtonian constant of gravitation", "G_N = gravitational_constant"),   # 'G is the gauss
    ("g_0", "standard gravity", None),
    ("eps_0", "vacuum permittivity", None),
    ("mu_0", "vacuum permeability", None),
    ("m_e", "electron mass", None),
    ("m_p", "proton mass", None),
]

# What siunitx v3 defines itself, of the macro names Pint's siunitx format emits.
# Any other Pint unit (foot, standard_gravity, ...) needs a \DeclareSIUnit of its own.
_SIUNITX = set("""
    quecto ronto yocto zepto atto femto pico nano micro milli centi deci deca hecto kilo
    mega giga tera peta exa zetta yotta ronna quetta kibi mebi gibi tebi pebi exbi zebi yobi
    ampere candela kelvin kilogram gram meter metre mole second becquerel degreeCelsius
    coulomb farad gray hertz henry joule katal lumen lux newton ohm pascal radian siemens
    sievert steradian tesla volt watt weber day hour minute hectare liter litre tonne
    arcminute arcsecond degree electronvolt dalton neper bel decibel astronomicalunit percent
    per square squared cubic cubed tothe raiseto""".split())
# Pint names whose siunitx macro is spelt differently.
_SIUNITX_ALIASES = {"electron_volt": "electronvolt", "astronomical_unit": "astronomicalunit",
                    "metric_ton": "tonne"}


# Offset temperature units by Pint name, with the spelling a sheet types. `35'degF` builds a
# temperature of 35 °F, but `*` and `/` read 'degF as an absolute temperature, 1 °F = 255.9 K.
OFFSET_TEMPERATURES = {"degree_Celsius": "degC", "degree_Fahrenheit": "degF", "degree_Reaumur": "degRe"}


def define(ureg):
    """Add the units Pint lacks to a fresh registry."""
    for code in CURRENCIES:
        ureg.define(f"{code} = [{code}]")
    for _, _, definition in CONSTANTS:
        if definition:
            ureg.define(definition)


@lru_cache(maxsize=8)
def _constant_units(ureg):
    return frozenset(ureg.get_name(spelling) for spelling, _, _ in CONSTANTS)


def holds_constant(q, ureg):
    """True if a quantity's units include one of the physical constants. Such a quantity
    stands for a value, so it is never shown as typed: 3'mol * 'R is 24.94 J/K."""
    return any(name in _constant_units(ureg) for name, _ in q.unit_items())


def _is_money(name):
    return name in CURRENCIES or name[-3:] in CURRENCIES   # USD, kUSD


def reduce(q, ureg):
    """A result in percent or a currency in the form it is shown in, or None when
    no family here claims it and the plain SI reduction applies."""
    if dict(q.unit_items()) == {"percent": 1}:   # 5'% + 2'% stays 7 %; '% * 'N or '%^2 drops it
        return q
    money = [n for n, _ in q.unit_items() if _is_money(n)]
    if not money:
        return None
    # A price keeps the units it was typed in: in base units 'USD/'kWh would be USD s²/(kg m²).
    # Only units of one kind cancel ('USD/'kWh * 'MJ is USD).
    r = q.to_reduced_units()
    cash = ureg.Unit("*".join(f"{n}**{e}" for n, e in r.unit_items() if n in money))
    return r.to(cash) if (r / ureg.Quantity(1, cash)).dimensionless else r


def detail(name):
    """The editor's description of a unit, or None to use Pint's name for it."""
    if name in CURRENCIES:
        return f"{CURRENCIES[name]} (currency)"
    return next((what for spelling, what, _ in CONSTANTS if spelling == name), None)


def syntax_hint(rest):
    """How to write what a syntax error stopped at, when it is a unit written without its '."""
    if rest.startswith("%"):
        return ". Percent is a unit: write 5'%"
    if rest.startswith("$"):
        return ". Currencies are units named by their ISO code: write 5'USD, 'EUR, 'GBP"
    return ""


def mismatch(dims):
    """The error for adding or converting across dimensions `dims` (names without
    brackets), or None when no family here has a better one than Pint's."""
    money = list(dict.fromkeys(d for d in dims if d in CURRENCIES))
    if len(money) > 1:
        return (f"Incompatible units: {money[0]} and {money[1]} are different currencies. "
                f"Multiply by an exchange rate variable, e.g. rate = 1.08'{money[0]}/'{money[1]}")
    return None


def offset_note(ureg, *qs):
    """The warning on `*` or `/` with an operand in an offset temperature unit, or "" when
    neither has one. The arithmetic still runs (Pint converts to kelvin first)."""
    for q in qs:
        for name, _ in q.unit_items():
            typed = OFFSET_TEMPERATURES.get(name)
            if typed:
                k = ureg.Quantity(1, name).to("kelvin").magnitude
                return (f"* and / read '{typed} as an absolute temperature, 1 '{typed} = {k:.5g} K. "
                        f"For a temperature, put the number before the unit: 35'{typed}. "
                        f"For a temperature difference, use 'delta_{typed}")
    return ""


def siunitx_macro(name):
    """The macro siunitx itself defines for the Pint unit `name`, or None when the
    export has to declare one (see `declared_macro`)."""
    if name in _SIUNITX_ALIASES:
        return _SIUNITX_ALIASES[name]
    return name if name in _SIUNITX else None


def declared_macro(name):
    """The spelling of a \\DeclareSIUnit macro for a Pint unit siunitx lacks.
    camelCase reads better than psiUnderg for a name the user did not choose."""
    return re.sub(r"_(.)", lambda t: t.group(1).upper(), name)


def subscripted(tex, units, ureg):
    """Pint prints the symbol g_0 as \\mathrm{g\\_0}, a literal underscore. A
    one-letter symbol with a short tail (g_0, m_e, N_A, µ_0) is a subscripted
    constant, so print it as one; sq_ft and the like keep their underscore."""
    for name in units._units:
        try:
            base = ureg.parse_unit_name(name)[0][1]
            bsym, sym = ureg.get_symbol(base), ureg.get_symbol(name)
        except Exception:
            continue
        m = re.fullmatch(r"(.)_(.{1,3})", bsym)
        if m:
            psym = sym[:len(sym) - len(bsym)]
            tex = tex.replace(f"\\mathrm{{{psym}{m.group(1)}\\_{m.group(2)}}}",
                              f"\\mathrm{{{psym}{m.group(1)}}}_{{\\mathrm{{{m.group(2)}}}}}")
    return tex
