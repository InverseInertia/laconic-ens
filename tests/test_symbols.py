"""The symbol table, at its interface: what each line of a sheet can see, as evaluate() builds it."""
import pytest

from laconic import solver
from laconic.blockedit import apply
from laconic import solvesession
from laconic.nodes import BinOp, Call, Name, Num
from laconic.sheet import evaluate
from laconic.symbols import FUNCTION, VARIABLE, SymbolTable


def visible(text, n):
    """Keys of the variables and functions line `n` sees, as (sorted variables, sorted functions)."""
    syms = evaluate(text).symbols.visible(n)
    return (sorted(s.key for s in syms if s.kind == "variable"),
            sorted(s.key for s in syms if s.kind == "function"))


@pytest.mark.parametrize("text, line, variables, functions", [
    # definitions are seen below their line, not on it or above
    ("a = 1\nb = 2\nf(x) = x\n", 4, ["a", "b"], ["f"]),
    ("a = 1\nb = 2", 2, ["a"], []),
    ("x = 1\nx = x + 1", 2, ["x"], []),
    # a ~ makes a name global; every later definition of it stays global
    ("~g = 9.81\ngx = 1\n", 3, ["gx", "~g"], []),
    ("~g = 1\ng = 2\n", 3, ["~g"], []),
    ("~f(x) = x\nf(x) = 2*x\n", 3, [], ["~f"]),
    # !clear removes the variables that are not global; !clearf the functions
    ("abc = 1\n!clear\n", 3, [], []),
    ("~abc = 1\n!clear\n", 3, ["~abc"], []),
    ("~abc = 1\nabc = 2\n!clear\n", 4, ["~abc"], []),
    ("a = 1\nf(x) = x\n!clear\n", 4, [], ["f"]),
    ("a = 1\nf(x) = x\n~h(x) = x\n!clearf\n", 5, ["a"], ["~h"]),
    ("a = 1\n!clear\na = 2\n", 4, ["a"], []),
    # a function's parameters are local to its line
    ("f(t, u) = t*u\n", 2, [], ["f"]),
    # a solver block's unknowns are defined again by its header
    ("x = 1\n!root x\n  equation: x^2 = 2\n", 3, ["x"], []),
    # a line that fails defines nothing
    ("a = 1\nb = nope\nf(x) = \n", 4, ["a"], []),
    ("g = 1\n~g = 2\n", 3, ["g"], []),
])
def test_what_a_line_sees(text, line, variables, functions):
    assert visible(text, line) == (variables, functions)


def test_each_symbol_records_its_line_value_and_lifetime():
    syms = evaluate("L = 4.5'm\n~g = 9.81'm/'s^2\nL = 2*L\n!clear\nf(a, b) = a + b").symbols.symbols
    got = [(s.key, s.kind, s.line, s.until, s.value, s.params) for s in syms]
    assert got == [("L", "variable", 1, 3, "4.5 m", ()),
                   ("~g", "variable", 2, None, "9.81 m/s²", ()),
                   ("L", "variable", 3, 4, "9 m", ()),
                   ("f", "function", 5, None, "", ("a", "b"))]


def test_a_solver_unknown_holds_the_stored_answer():
    text = "x = 1\n!root x\n  equation: x^2 = 4\ny = x\n"
    out = solvesession.solve(text, 2, log=lambda msg: None)
    ws = evaluate(apply(text, solver.write_result(text, 2, out["record"])))
    x = [s for s in ws.symbols.visible(ws.results[-1].n) if s.name == "x"]
    assert [(s.line, s.value) for s in x] == [(2, "2")]


def test_rows_carry_their_part_of_the_table():
    rows = evaluate("~g = 5\ny = g\nh(g) = g").results
    assert [d["name"] for d in rows[0].symbols["defines"]] == ["g"]
    assert rows[0].symbols["defines"][0]["global"] is True
    assert rows[1].symbols["defines"][0] | {"id": 0} == {"id": 0, "name": "y", "kind": "variable", "line": 2,
                                                         "until": None, "global": False, "value": "5", "params": []}
    assert rows[2].symbols["defines"][0]["params"] == ["g"]


def test_uses_resolve_each_name_to_the_symbol_it_means():
    text = "x = g\n~g = 5\ny = g + ~g + 'g\n# g\nh(g) = g\n!plot g*x, x = 0 .. 1\n  title: g"
    ws = evaluate(text)
    gid = next(s.id for s in ws.symbols.symbols if s.key == "~g")
    hid = next(s.id for s in ws.symbols.symbols if s.key == "h")
    assert [r.symbols["uses"] for r in ws.results] == [
        [],                              # g is not defined yet; the line fails
        [[0, 2, gid]],                   # the name being defined
        [[4, 1, gid], [8, 2, gid]],      # with or without its ~; 'g is a unit (and the line fails)
        [],                              # comments are text
        [[0, 1, hid]],                   # the parameter g is local
        [[6, 1, gid]],                   # x in a plot is the plot's own variable
        [],                              # a plot title is text
    ]


def test_a_function_name_means_the_function():
    ws = evaluate("f = 2\nf(x) = x\ny = f(f)")
    by_id = {s.id: s for s in ws.symbols.symbols}
    assert [by_id[u[2]].kind for u in ws.results[2].symbols["uses"]] == ["variable", "function", "variable"]


# ---- what each key holds -----------------------------------------------------------------------------
def test_a_definition_holds_its_value_and_a_clear_drops_it():
    t = SymbolTable()
    t.line = 1
    t.define("a", 1, stale=True)
    t.define("~g", 2)
    t.define_function("f", ("x",), BinOp("+", Name("x"), Name("a")))
    assert dict(t.values) == {"a": 1, "~g": 2} and t.functions["f"][0] == ("x",)
    assert t.tainted([Call("f", (Num(1),))])            # through the function's body
    assert not t.tainted([Name("g")]) and not t.tainted([Name("a")], local=("a",))
    t.line = 2
    assert t.clear(VARIABLE) == (["a"], ["~g"])
    assert dict(t.values) == {"~g": 2} and not t.is_stale("a")
    t.line = 3
    t.clear(FUNCTION)
    assert dict(t.functions) == {}


def test_defining_a_name_again_sets_whether_it_is_stale():
    t = SymbolTable()
    t.define("x", 1, stale=True)
    t.mark_stale(["y"])
    assert t.is_stale("x") and t.is_stale("y")
    t.define("x", 2)
    assert not t.is_stale("x") and t.values["x"] == 2


def test_values_are_written_only_through_the_table():
    with pytest.raises(TypeError):
        SymbolTable().values["x"] = 1
