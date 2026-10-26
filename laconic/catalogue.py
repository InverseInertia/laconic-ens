"""The unit catalogue: what LENS knows about the unit families Pint alone does not
handle the way a worksheet wants. Each family's policy sits here in one place:
its dimension, how the export spells it, how `si.reduce_si` treats a result in
it, the editor's detail text and the hint or error that names it. Other modules
ask the catalogue instead of keeping lists of their own.

The families:

- currencies: ISO 4217 codes, each a dimension of its own
- percent: Pint's dimensionless `percent`, kept on a result that is only percent
- constants with subscripted symbols (g_0, m_e, N_A, µ_0)
- Pint units siunitx lacks, which the export declares itself"""
import re

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


def define(ureg):
    """Add the units Pint lacks to a fresh registry."""
    for code in CURRENCIES:
        ureg.define(f"{code} = [{code}]")


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
    return f"{CURRENCIES[name]} (currency)" if name in CURRENCIES else None


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
