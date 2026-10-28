"""Sheet commands, tested at the registry/sheet interface: one row per command in
commands.COMMANDS. A new command needs a row here and nothing in the vocab or help tests."""
import pytest

from laconic import run
from laconic.commands import COMMANDS, Choice, NoArgs, Statement, Text, Whole, help_rows


def shown(r):
    return r.text.split("= ")[-1]


# name: (sheet, line number of the command, the text it shows, a check on the lines after it)
CASES = {
    "clear": ("f(x) = 2*x\n~g = 1\na = 2\n!clear\na\nf(3)\n~h = 3\n!clear", 4, "Cleared a. Kept global ~g",
              lambda rs: "removed by !clear" in rs[4].error and rs[5].text == "6"
              and rs[7].text == "Nothing to clear. Kept globals ~g, ~h"),
    "clearf": ("f(x) = x^2\n~g(x) = 2*x\n!clearf\ng(3)\nf(2)", 3, "Cleared f. Kept global ~g",
               lambda rs: rs[3].text == "6" and "removed by !clearf" in rs[4].error),
    "noassume": ("F = 10'kN\n!noassume\nM = F*2'm\nN = M -> 'N*'m", 2, "Units are kept as typed unless converted with ->",
                 lambda rs: rs[2].text.startswith("M = 20 kN") and rs[3].text.startswith("N = 20000 ")),
    "assume": ("!noassume\n!assume\nM = 10'kN*2'm", 2, "Units are reduced to SI again",
               lambda rs: rs[2].text == "M = 20000 J"),
    "trigdeg": ("!trigdeg\nsin(30)\nasin(0.5)\nsin(pi/6'rad)", 1, "Trig functions take and return degrees",
                lambda rs: shown(rs[1]) == "0.5" and shown(rs[2]) == "30 deg" and shown(rs[3]) == "0.5"),
    "trigrad": ("!trigdeg\n!trigrad\nsin(pi/6)\nasin(0.5)", 2, "Trig functions take and return radians",
                lambda rs: shown(rs[2]) == "0.5" and "rad" in rs[3].text),
    "short": ("w = 12'kN/'m\n!short\nM = w*(4.5'm)^2/8\nv = [1; 2]*'kN", 2, "Showing final results only, without steps",
              lambda rs: len(rs[2].stages) == 1 and rs[2].text == "M = 30380 J" and len(rs[3].stages) == 1),
    "long": ("w = 12'kN/'m\n!short\n!long\nM = w*(4.5'm)^2/8", 3, "Showing steps again",
             lambda rs: len(rs[3].stages) == 3),
    "sigfigs": ("x = 1/3\n!sigfigs 6\nx\n!sigfigs 1\nx", 2, "Results show 6 significant figures",
                lambda rs: shown(rs[2]) == "0.333333" and rs[3].text == "Results show 1 significant figure"),
    "sigfigsbig": ("a = 2.5\n!sigfigsbig 4\na", 2, "Results show 4 significant figures, trailing zeros kept",
                   lambda rs: shown(rs[2]) == "2.500"),
    "decplace": ("x = 1/3\n!decplace 2\nx\n[1/3, 2]\ny = x*3\n!sigfigs 4\nx", 2, "Results show 2 decimal places",
                 lambda rs: shown(rs[2]) == "0.33" and rs[3].text == "[[0.33 2.00]]" and shown(rs[4]) == "1.00"
                 and shown(rs[6]) == "0.3333"),
    "complex": ("z = 3 + 4i\n!complex polar\nz\n!complex real\nz\nabs(z)", 2,
                "Complex results are shown as magnitude∠angle",
                lambda rs: shown(rs[2]) == "5∠0.9273 rad" and "allows only real results" in rs[4].error
                and shown(rs[5]) == "5"),
    "freq": ("!freq rad\nw = sqrt(4'N/'m / 1'kg)\nw -> 'Hz\n!freq si\n50'Hz -> 'rad/'s", 1,
             "Hz is cycles per second, 1 Hz = 2π rad/s; a 1/s result is shown in rad/s",
             lambda rs: rs[1].text == "w = 2 rad/s" and shown(rs[2]) == "0.3183 Hz"
             and rs[3].text == "Hz and rad/s are both 1/s again, 1 Hz = 1 rad/s" and shown(rs[4]) == "50 rad/s"),
    "plotspec": ("!plotspec grid: off\n!plotspec reset", 1, "Plots below: grid off",
                 lambda rs: rs[1].text == "Plot options are back to the defaults"),
    # Statements: their lines are run by plotspec.py and solver.py, never by the dispatcher.
    "plot": ("!plot x, x = 0 .. 1", 1, None, lambda rs: rs[0].kind == "plot"),
    "root": ("x = 1\n!root x\n  equation: x = 2", 2, None, lambda rs: rs[1].kind == "solver"),
    "minimize": ("x = 1\n!minimize x\n  objective: (x - 2)^2", 2, None, lambda rs: rs[1].kind == "solver"),
    "maximize": ("x = 1\n!maximize x\n  objective: -(x - 2)^2", 2, None, lambda rs: rs[1].kind == "solver"),
}

# A bad line for each argument rule, and what its error says.
BAD = {
    NoArgs: (lambda c: f"!{c.name} x", lambda c: f"!{c.name} takes no arguments"),
    Whole: (lambda c: f"!{c.name} {c.args.hi + 1}",
            lambda c: f"!{c.name} takes a whole number from {c.args.lo} to {c.args.hi}, e.g. `!{c.name} 3`"),
    Text: (lambda c: f"!{c.name} nonsense", lambda c: f"!{c.name} reads"),
    Choice: (lambda c: f"!{c.name} nonsense", lambda c: f"!{c.name} takes one of {', '.join(c.args.options)}"),
    Statement: (lambda c: f"!{c.name}", lambda c: c.args.usage),
}


def test_every_command_has_a_case():
    assert set(CASES) == {c.name for c in COMMANDS}


@pytest.mark.parametrize("command", COMMANDS, ids=lambda c: c.name)
def test_command(command):
    sheet, n, text, after = CASES[command.name]
    rs = run(sheet)
    if text is not None:
        assert (rs[n - 1].kind, rs[n - 1].text) == ("command", text)
    assert after(rs)
    if command.name in ("root", "minimize", "maximize"):
        return                      # a bare `!root` is still a solver block, reported by solver.py
    line, error = (f(command) for f in BAD[type(command.args)])
    r = run(line)[0]
    assert r.kind == "error" and error in r.error


def test_unknown_command_lists_every_command():
    assert run("!wipe")[0].error == "Unknown command '!wipe'. Available: " + ", ".join(f"!{c.name}" for c in COMMANDS)


def test_mode_starts_fresh_for_each_sheet():
    run("!trigdeg\n!short\n!sigfigs 2\n!plotspec grid: off")
    rs = run("x = 1/3\nasin(1)")
    assert shown(rs[0]) == "0.3333" and "rad" in rs[1].text and len(rs[1].stages) > 1


def test_help_rows_group_commands_that_share_a_text():
    rows = help_rows()
    assert "<kbd>!noassume</kbd> <kbd>!assume</kbd>" in rows
    assert "<kbd>!sigfigs n</kbd> <kbd>!sigfigsbig n</kbd> <kbd>!decplace n</kbd>" in rows
    assert rows.count("<tr>") == len({c.help for c in COMMANDS if c.help})
