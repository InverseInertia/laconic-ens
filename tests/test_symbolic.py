"""Symbolic math (issue #123): symbols declared with $, expressions over them, !symsolve."""
import subprocess
import sys

import pytest

from laconic.latex import document
from laconic.markdown import plain_math
from laconic.rename import rename
from laconic.sheet import evaluate, run
from laconic.vocab import vocabulary


def rows(src, tags=False):
    """The sheet's rows, with the page's \\htmlData tags (globals, symbols) taken out of their
    math unless `tags`, so the math reads as it prints; test_symbols_are_tagged checks the tags."""
    out = run(src)
    if not tags:
        for r in out:
            r.lhs, r.stages = plain_math(r.lhs), [plain_math(t) for t in r.stages]
    return out


def last(src):
    return rows(src)[-1]


# ---- declaring symbols -------------------------------------------------------------------------
def test_a_declaration_defines_symbols():
    r = rows("$a, $b\ny = a*b")
    assert (r[0].kind, r[0].text, r[0].error) == ("symdef", "symbols a, b", "")
    defs = r[0].symbols["defines"]
    assert [(d["name"], d["symbol"], d["value"]) for d in defs] == [("a", True, "symbol"), ("b", True, "symbol")]
    assert r[0].symbols["uses"] == [[0, 2, defs[0]["id"]], [4, 2, defs[1]["id"]]]   # the $ is part of the use
    assert r[1].symbols["defines"][0]["symbol"] is False                          # y holds an expression
    assert r[1].text == "y = a*b"


def test_one_symbol_reads_symbol():
    assert rows("$x")[0].text == "symbol x"


@pytest.mark.parametrize("src, msg", [
    ("$x = 2", "A symbol has no value"),
    ("$a, b", "'b' is not a symbol. Declare symbols as `$a, $b`"),
    ("$~g", "A global's ~ comes first: ~$g"),
    ("$a, $a", "declared twice"),
    ("$x\ny = $x + 1", "$x declares a symbol, which is done on a line of its own"),
])
def test_declaration_errors(src, msg):
    r = last(src)
    assert r.kind == "error" and msg in r.error


def test_a_global_symbol_is_global_and_kept_by_clear():
    r = rows("~$g\n$x\nh = g*x\n!clear\nk = g + 1\nx")
    assert r[0].text == "symbol ~g" and r[0].symbols["defines"][0]["global"]
    assert r[2].latex == r"h = g \cdot x"
    assert r[3].text == "Cleared x, h. Kept global ~g"
    assert r[4].text == "k = g + 1"
    assert r[5].kind == "error" and "removed by !clear" in r[5].error


def test_declaring_a_global_again_without_the_tilde_warns():
    r = rows("~$s\n$s")
    assert r[1].warning == "Changes the global ~s, defined on line 1. Write ~$s if that is meant"


def test_a_name_used_without_tilde_cannot_become_a_global_symbol():
    assert "already a non-global variable" in last("x = 1\n~$x").error


# ---- symbolic expressions ----------------------------------------------------------------------
def test_an_expression_over_symbols_is_symbolic():
    r = rows("$a, $b, $c, $x\nq = a*x^2 + b*x + c\nq")
    assert r[1].text == "q = a*x^2 + b*x + c"
    assert r[1].latex == r"q = a \cdot x^{2} + b \cdot x + c"
    assert (r[2].kind, r[2].text) == ("expr", "a*x^2 + b*x + c")


def test_numbers_stay_exact_and_decimals_print_as_the_sheet_prints():
    assert last("$x\nx/2 + sqrt(2)*x").text == "x/2 + sqrt(2)*x"
    assert last("$x\n0.25*x").text == "0.25*x"
    assert last("!sigfigs 2\n$x\nx*1.23456").text == "1.2*x"


def test_a_dimensionless_variable_goes_in_as_its_number():
    r = last("k = 3\n$a\nr = k*a")
    assert r.text == "r = 3*a"
    assert r.stages == [r"k \cdot a", r"3 \cdot a"]


def test_a_number_with_units_cannot_go_into_a_symbolic_result():
    r = last("L = 2'm\n$a\nbad = L*a")
    assert r.kind == "error"
    assert r.error == ("L (2 m) has units, and a symbolic result cannot carry units. "
                       "Declare L a symbol too ($L), or give the symbols values above this line")
    assert "props() has them" in last('$q\nprops("D", "T", 300\'K, "P", 1\'atm, "Water") * q').error
    assert "matrix" in last("$q\nexp(q) * [1, 2]").error
    assert "-> (a symbolic result has no units to convert) takes numbers only" in last("$q\nq -> 'm").error


def test_symbols_bind_late_and_are_worked_out_with_units():
    r = rows("$F, $m\nacc = F/m\nF = 10'N\nm = 2'kg\nz = acc\nw = acc -> 'ft/'s^2")
    assert r[1].text == "acc = F/m"
    assert r[4].text == "z = 5 m/s²"
    assert r[4].stages == [r"\mathrm{acc}", r"\frac{10\,\mathrm{N}}{2\,\mathrm{kg}}", r"5\,\frac{\mathrm{m}}{\mathrm{s}^{2}}"]
    assert r[5].text == "w = 16.4 ft/s²"


def test_an_expression_with_a_symbol_left_cannot_be_a_number():
    r = rows("$F, $m\nacc = F/m\nF = 10'N\nP = acc + 1")
    assert r[3].kind == "error"
    assert "F (10 N) has units" in r[3].error


def test_a_symbol_alone_where_a_number_is_needed():
    r = last("$x\n!plot x + 1'm, y = 0 .. 1")
    assert r.kind == "error" and "'x' is a symbol and has no value here" in r.error


def test_a_plot_over_a_symbol_draws_its_expression():
    r = last("$t\ny = t^2\n!plot y, t = 0 .. 1")
    assert r.kind == "plot" and r.plot is not None
    ys = r.plot.spec["series"][0]
    assert ys["label"]


def test_user_functions_take_symbols():
    r = rows("$t\nf(u) = u^2 + 1\ng = f(t)\nk = f(3)")
    assert r[2].text == "g = t^2 + 1"
    assert r[3].text == "k = 10"


def test_a_symbol_takes_a_parameter_of_its_name():
    assert last("$x\ny = x^2\nf(x) = y + 1\nf(3)").text == "10"


def test_trig_of_a_symbol_needs_radians():
    assert last("$x\nsin(x)").text == "sin(x)"
    assert last("$x\ncos(x)^2 + sin(x)^2").text == "sin(x)^2 + cos(x)^2"
    r = last("!trigdeg\n$x\nsin(x)")
    assert r.kind == "error" and "!trigdeg is on" in r.error
    assert last("!trigdeg\n$x\nsin(30)*x").text == "0.5*x"   # a number is still read in degrees


def test_imaginary_numbers_go_in():
    r = last("$s\nv = 4i * s + 1/3")
    assert r.text == "v = 4*i*s + 1/3"
    assert r.stages[-1] == r"4 \cdot \mathrm{i} \cdot s + \frac{1}{3}"


def test_greek_subscripts_and_marks_print_as_names_do():
    assert last("$σ_max, $v!\ny = σ_max*v!").stages[0] == r"\sigma_{\mathrm{max}} \cdot \vec{v}"
    assert last("$T_inf\ny = 2*T_inf").stages[-1] == r"2 \cdot T_{\infty}"


def test_short_shows_only_the_result():
    assert last("!short\nk = 2\n$a\nr = k*a").stages == [r"2 \cdot a"]


def test_a_sheet_without_symbols_never_imports_sympy():
    code = ("import sys; sys.path.insert(0, '.'); from laconic.sheet import run; "
            "run('x = 1\\n!symsolve\\ny = x + 1'); print('sympy' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


# ---- !symsolve ---------------------------------------------------------------------------------
QUADRATIC = "$a, $b, $c, $x\nq = a*x^2 + b*x + c\n!symsolve x\n  equation: q = 0\n"


def test_one_solution_is_held_below_the_block():
    r = rows("$m, $a, $F\n!symsolve a\n  equation: F = m*a\ny = a")
    assert (r[1].kind, r[1].text, r[1].latex, r[1].warning) == ("symsolve", "a = F/m", r"a = \frac{F}{m}", "")
    assert r[2].kind == "solveropt"
    assert r[3].text == "y = F/m"


def test_several_solutions_are_listed_and_the_unknown_stays_a_symbol():
    r = rows(QUADRATIC + "y = x")
    assert r[2].text.startswith("(1) x = -b/(2*a) - sqrt(")
    assert "(2) x = -b/(2*a) + sqrt(" in r[2].text
    assert r[2].latex.startswith(r"\begin{gathered} \text{(1)}\quad x = ")
    assert r[2].warning == "2 solutions, so x stays a symbol below. Add `pick: 1` (or another number) to use one"
    assert r[4].text == "y = x"


def test_pick_chooses_a_solution():
    r = rows(QUADRATIC + "  pick: 2\ny = x")
    assert r[2].warning == ""
    assert r[5].text.startswith("y = -b/(2*a) + sqrt(")


def test_pick_out_of_range_is_an_error_on_its_line():
    r = rows(QUADRATIC + "  pick: 3")
    assert r[2].kind == "error" and r[2].error == "There are only 2 solutions"
    assert r[4].kind == "error" and r[4].error == "There are only 2 solutions"


def test_a_solution_without_symbols_is_a_number():
    r = rows("$x\n!symsolve x\n  equation: x^2 = 4\n  pick: 2\ny = x + 1")
    assert r[1].text == "(1) x = -2; (2) x = 2"
    assert r[4].text == "y = 3"
    assert r[4].symbols["defines"][0]["symbol"] is False


def test_symbols_are_tagged():
    """The page colors symbols and globals from these tags: a symbol, a global symbol as both,
    a global as global only, and a symbol given a value is a plain variable from then on."""
    r = rows("~$g, $x\n~h = 2\ny = g*x*h\nx = 3\nz = x + 1", tags=True)
    assert r[2].lhs == "y" and r[2].stages[0] == (r"\htmlData{global=g,symbol=g}{g} \cdot \htmlData{symbol=x}{x} "
                                                  r"\cdot \htmlData{global=h}{h}")
    assert r[4].stages[0] == "x + 1"
    assert "htmlData" not in evaluate("$x\ny = 2*x", siunitx=True).results[1].latex


def test_a_system_of_equations():
    r = rows("$x, $y, $a\n!symsolve x, y\n  equation: x + y = a\n  equation: x - y = 1\nz = x*y")
    assert r[1].text == "x = a/2 + 1/2, y = a/2 - 1/2"
    assert r[1].latex == r"x = \frac{a}{2} + \frac{1}{2},\; y = \frac{a}{2} - \frac{1}{2}"
    assert r[4].text == "z = (a/2 - 1/2)*(a/2 + 1/2)"


def test_a_global_unknown():
    r = rows("~$g, $h\n!symsolve g\n  equation: g*h = 2\ny = g")
    assert r[1].latex == r"g = \frac{2}{h}"
    assert r[3].text == "y = 2/h"


def test_dimensionless_numbers_go_into_the_equations():
    r = rows("k = 4\n$x\n!symsolve x\n  equation: k*x = 2")
    assert r[2].text == "x = 1/2"


@pytest.mark.parametrize("src, header, line_errors", [
    ("x = 1\n!symsolve x\n  equation: x = 2",
     "'x' is not a symbol here. Declare it as a symbol above the block: $x", {}),
    ("!symsolve x\n  equation: x = 2", "'x' is not defined. Declare it as a symbol above the block: $x", {}),
    ("$x, $a\n!symsolve x\n  equation: a = 2", "An equation below needs fixing",
     {3: "This equation has none of the unknowns in it"}),
    ("$x\n!symsolve x\n  equation: 3 = 3", "An equation below needs fixing",
     {3: "This equation holds whatever the unknowns are"}),
    ("$x\n!symsolve x\n  equation: x <= 1", "1 option line below needs fixing",
     {3: "!symsolve solves equations, `lhs = rhs`; it has no inequalities"}),
    ("$x\n!symsolve x\n  method: hybr", "1 option line below needs fixing",
     {3: "Unknown option 'method'. Under !symsolve: equation, pick"}),
    ("$x\n!symsolve x\n  equation: x = 1\n  pick: 0", "1 option line below needs fixing",
     {4: "pick is a solution's number, from 1: `pick: 2`"}),
    ("$x\n!symsolve x\n  equation: exp(x) = 0", "No solution: sympy finds none for x", {}),
    ("$x\n!symsolve x", "!symsolve needs at least one `equation:` line under it", {}),
    ("$x\n!symsolve x, x\n  equation: x = 1", "A name is listed twice", {}),
    ("$x\n!symsolve\n  equation: x = 1", "!symsolve reads `!symsolve x, y`", {}),
    ("L = 2'm\n$x\n!symsolve x\n  equation: x = L", "An equation below needs fixing",
     {4: "L (2 m) has units, and a symbolic result cannot carry units"}),
])
def test_symsolve_errors(src, header, line_errors):
    r = run(src)
    head = next(x for x in r if x.block is not None)
    assert head.kind == "error" and head.error.startswith(header)
    for n, msg in line_errors.items():
        assert r[n - 1].kind == "error" and r[n - 1].error.startswith(msg)


def test_a_solved_formula_is_worked_out_with_units_once_its_symbols_have_values():
    r = rows("$m, $a, $F\n!symsolve a\n  equation: F = m*a\nm = 2'kg\nF = 10'N\nacc = a")
    assert r[-1].text == "acc = 5 m/s²"


def test_symsolve_needs_no_run_and_is_not_a_solver_block():
    from laconic.sheet import solver_blocks
    from laconic import solvesession
    from laconic.solver import SolverError
    text = "$x\n!symsolve x\n  equation: x = 1"
    assert solver_blocks(text) == []
    with pytest.raises(SolverError, match="needs no Run"):
        solvesession.block(text, 2)


# ---- the numeric solver and symbolic values -----------------------------------------------------
def test_a_numeric_solver_cannot_start_from_a_symbol():
    r = rows("$q\n!root q\n  equation: q = 2")
    assert r[1].error == ("'q' is symbolic; the solver needs a number to start from. "
                          "Define q = 1 above the block, or solve for it with !symsolve")


def test_a_numeric_solver_reads_a_formula_and_its_hash_follows_the_values():
    def block(k):
        return run(f"$p, $k\nP = k*p^2\nk = {k}\np = 3'm\n!root p\n  equation: P = 4'm^2")[4]
    a, b = block(1), block(2)
    assert a.kind == "solver" and b.kind == "solver"
    assert a.solver.hash != b.solver.hash


# ---- around the sheet ---------------------------------------------------------------------------
def test_the_latex_document_keeps_the_declaration_and_typesets_the_results():
    ws = evaluate("$m, $a, $F\n!symsolve a\n  equation: F = m*a\nm = 2'kg\nF = 10'N\nacc = a", siunitx=True)
    tex = document(ws.results)
    assert "% $m, $a, $F" in tex
    assert r"&a = \frac{F}{m}" in tex
    assert r"&= \frac{\qty{10}{\newton}}{\qty{2}{\kilo\gram}}" in tex


def test_rename_keeps_the_dollar_and_the_tilde():
    edits, n = rename("~$ab, $c\ny = ab*c\n!symsolve c\n  equation: y = 1", "~$ab", "w")
    assert n == 2 and [(e.start, e.end, e.insert) for e in edits] == [(2, 4, "w"), (13, 15, "w")]


def test_the_editor_is_offered_symsolve_and_its_options():
    v = vocabulary()
    assert "symsolve" in [c for c, _ in v["commands"]]
    assert [k for k, _ in v["solver"]["keys"]["symsolve"]] == ["equation", "pick"]


def test_the_eval_endpoint_sends_symbolic_rows(tmp_path, monkeypatch):
    import json
    from laconic import server
    from laconic.server import Sheet
    monkeypatch.setenv("LENS_CONFIG_DIR", str(tmp_path))
    rows = json.loads(json.dumps(server.evaluate(Sheet(text="$x\n!symsolve x\n  equation: 2*x = 1"))))
    assert [r["kind"] for r in rows] == ["symdef", "symsolve", "solveropt"]
    assert rows[1]["text"] == "x = 1/2" and rows[1]["end"] == 3
    assert rows[0]["symbols"]["defines"][0]["symbol"] is True


def test_a_result_printed_as_typed_is_not_repeated():
    assert last("$t\ny = t^2 * exp(-t)").stages == [r"t^{2} \cdot e^{-t}"]


def test_the_example_sheet_runs_without_errors():
    from pathlib import Path
    import laconic
    text = (Path(laconic.__file__).parent / "examples" / "symbolic.lens").read_text(encoding="utf-8")
    rs = run(text)
    assert [r.error for r in rs if r.kind == "error"] == []
    assert any(r.text == "L_2s = 0.994 m" for r in rs)
    assert any(r.text == "x_2 = 2" for r in rs)
