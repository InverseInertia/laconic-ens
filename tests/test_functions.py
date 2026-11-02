"""The function registry: a built-in declared once reaches the evaluator, the suggestions, Rename
and the LaTeX printer."""
import pytest

from laconic import evaluate
from laconic.evaluator import Evaluator
from laconic.functions import FUNCTIONS, Builtin
from laconic.rename import RenameError, rename
from laconic.vocab import vocabulary


def test_every_builtin_is_an_evaluator_method_with_a_signature():
    for name, b in FUNCTIONS.items():
        assert b.name == name and b.signature.startswith(name + "(")
        assert getattr(Evaluator, b.impl.__name__) is b.impl and b.impl.__name__.startswith("fn_")


def test_an_alias_is_the_same_function_under_its_own_name():
    assert FUNCTIONS["step"].impl is FUNCTIONS["heav"].impl is FUNCTIONS["heaviside"].impl
    assert FUNCTIONS["step"].signature == "step(x)"
    assert evaluate("y = step(-1)").results[0].latex == "y = \\operatorname{H}\\left(-1\\right) = 0"


@pytest.fixture
def twice(monkeypatch):
    """A built-in added the way a new one is: one registry entry."""
    monkeypatch.setitem(FUNCTIONS, "twice", Builtin("twice", lambda ev, x: x * 2, "twice(x)",
                                                    tex=r"2{0:mul}", binds="mul"))


def test_one_entry_reaches_everything(twice):
    r = evaluate("a = 1 + 2\ny = twice(a + 1)").results[1]
    assert r.text == "y = 8" and r.latex == "y = 2\\left(a + 1\\right) = 2\\left(3 + 1\\right) = 8"
    assert ["twice", "twice(x)"] in vocabulary()["functions"]
    with pytest.raises(RenameError, match="built in"):
        rename("q = twice(1)", "twice", "thrice")


def test_a_form_for_some_number_of_arguments_only():
    assert evaluate("v = [1; 2]\ny = idx(v, 2)").results[1].latex.startswith("y = {v}_{2}")
    assert "\\mathrm{idx}\\left(v, x, 1\\right)" in evaluate("v = [1; 2]\nf(x) = idx(v, x, 1)").results[1].latex


def test_a_user_function_name_takes_the_marks_a_variable_name_does():
    """#160: V@(x), ~f!(n) and g`(t) define functions, as V@ = ... defines a variable."""
    rs = evaluate("V@(x) = 2*x\ny = V@(3)\n~f!(n) = n + 1\nz = f!(1)\ng`(t) = t^2\nw = g`(3)").results
    assert [r.kind for r in rs] == ["funcdef", "assign"] * 3 and not any(r.error for r in rs)
    assert [rs[i].text for i in (1, 3, 5)] == ["y = 6", "z = 2", "w = 9"]
    assert rs[1].latex == "y = \\hat{V}\\left(3\\right) = 6"
    assert rename("V@(x) = 2*x\ny = V@(3)", "V@", "W@")[1] == 2
