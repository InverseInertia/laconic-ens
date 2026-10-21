import pytest

from laconic import props as P, run
from laconic.latex import snippet
from laconic.rename import rename

def last(text):
    return [r for r in run(text) if r.kind != "blank"][-1]


def test_density_of_water_converts_inputs_and_carries_si_unit():
    r = last('rho = props("D", "T", 20\'degC, "P", 1\'atm, "Water")')
    assert r.kind == "assign" and r.text.startswith("rho = 998.2") and "kg/m" in r.text


def test_fixed_fluid_property_needs_no_state():
    assert last('Tc = props("Tcrit", "Water")').text.startswith("Tc = 647.1")


def test_result_converts_and_dimensionless_inputs():
    assert last('props("T", "P", 1\'bar, "Q", 0, "Water") -> \'degC').text.startswith("99.6")


@pytest.mark.parametrize("line,msg", [
    ('props("D", "T", 300, "P", 1\'atm, "Water")', "'T' needs a value in K"),
    ('props("D", "T", 300\'K, "P", 1\'atm, "Nope")', "Nope"),
    ('props("Zzz", "Water")', "Unknown property 'Zzz'"),
    ('props("D", "T", 300\'K, "Water")', "props("),
    ('props("D", 5\'K, 300\'K, "P", 1\'atm, "Water")', "in quotes"),
])
def test_bad_calls_are_errors_on_their_line(line, msg):
    r = last(line)
    assert r.kind == "error" and msg in r.error


def test_text_outside_a_function_call_is_an_error():
    r = last('x = "Water"')
    assert r.kind == "error" and "argument to a function" in r.error


def test_user_function_cannot_take_text():
    r = last('f(x) = x\nf("a")')
    assert r.kind == "error" and "cannot take text" in r.error


def test_missing_coolprop_explains_itself(monkeypatch):
    monkeypatch.setattr(P, "_coolprop", lambda: (_ for _ in ()).throw(P.PropsError(P.INSTALL_HINT)))
    r = last('props("D", "T", 300\'K, "P", 1\'atm, "Water")')
    assert r.kind == "error" and "pip install CoolProp" in r.error


def test_latex_prints_text_arguments():
    tex = snippet(last('x = props("Tcrit", "Water")'))
    assert r"\mathrm{props}" in tex and r"\text{Tcrit}" in tex


def test_rename_leaves_text_alone():
    out, n = rename('Water = 1\nprops("Tcrit", "Water") * Water', "Water", "w")
    assert n == 2 and '"Water"' in out
