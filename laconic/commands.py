"""Sheet commands: the `!name` lines, and the sheet mode they change.

The registry (`COMMANDS`) is the one place a command is declared. Each entry has a
name, an argument rule, a short summary (offered by the editor), a help row (shown in
the page's key table) and its effect. The dispatcher (`run`), the "Unknown command"
message, the editor vocabulary and the help rows are all read from it, so a new
command is one entry here and nothing else.

The sheet mode (`SheetMode`) is what the commands change and the rest of a run reads:
the evaluator reads the angle unit and the cleared names, `Fmt` reads the precision,
`sheet.py` reads assume and short, `plotspec.py` reads the plot defaults. Nothing
outside this module writes it."""
import re
from dataclasses import dataclass, field

from .plotopts import PlotError, canon, parse_option
from .symbols import FUNCTION, VARIABLE


@dataclass
class SheetMode:
    """How the lines below the commands run so far are evaluated and shown."""
    angle: str = "radian"      # "degree" after !trigdeg: bare numbers in trig calls are degrees
    assume: bool = True        # False after !noassume: results keep their typed units
    short: bool = False        # True after !short: lines show only the final result, no steps
    sig: int = 4               # significant figures shown (!sigfigs, !sigfigsbig)
    places: int = None         # decimal places shown instead, after !decplace
    keep_zeros: bool = False   # !sigfigsbig: pad to exactly `sig` figures, 2.5 -> 2.500
    plotdefs: dict = field(default_factory=dict)   # !plotspec key: value, for the plots below
    cleared: set = field(default_factory=set)        # variables removed by !clear, for a clearer error
    cleared_funcs: set = field(default_factory=set)  # functions removed by !clearf


class CommandError(Exception):
    pass


# ---- argument rules ---------------------------------------------------------
# Each rule turns the text after the command name into the value its effect takes,
# or raises CommandError with the message the line shows.

@dataclass(frozen=True)
class NoArgs:
    hint = ""

    def parse(self, name, rest):
        if rest:
            raise CommandError(f"!{name} takes no arguments")


@dataclass(frozen=True)
class Whole:
    """A whole number from `lo` to `hi`."""
    lo: int
    hi: int
    hint = " n"

    def parse(self, name, rest):
        if not re.fullmatch(r"\d+", rest) or not self.lo <= int(rest) <= self.hi:
            raise CommandError(f"!{name} takes a whole number from {self.lo} to {self.hi}, e.g. `!{name} 3`")
        return int(rest)


@dataclass(frozen=True)
class Text:
    """The rest of the line, read by the effect itself."""
    hint = ""

    def parse(self, name, rest):
        return rest


@dataclass(frozen=True)
class Statement:
    """A command that starts a plot or solver block. Those lines are run by plotspec.py
    and solver.py; one that gets here is malformed, and gets `usage` as its error."""
    usage: str
    hint = ""

    def parse(self, name, rest):
        raise CommandError(self.usage)


# ---- effects ----------------------------------------------------------------
# effect(mode, ev, value) -> the text the command line shows

def _cleared(gone, kept):
    """`!clear` and `!clearf` name what they kept as well, since a global surviving one is easy to miss."""
    text = f"Cleared {', '.join(gone)}" if gone else "Nothing to clear"
    if kept:
        text += f". Kept global{'s' * (len(kept) > 1)} {', '.join(kept)}"
    return text


def _clear(mode, ev, _):
    gone, kept = ev.symbols.clear(VARIABLE)
    for n in gone:
        del ev.vars[n]
    mode.cleared.update(gone)
    ev.stale -= set(gone)
    return _cleared(gone, kept)


def _clearf(mode, ev, _):
    gone, kept = ev.symbols.clear(FUNCTION)
    for n in gone:
        del ev.funcs[n]
    mode.cleared_funcs.update(gone)
    return _cleared(gone, kept)


def _setter(attr, value, text):
    def effect(mode, ev, _):
        setattr(mode, attr, value)
        return text
    return effect


def _sigfigs(keep_zeros):
    def effect(mode, ev, n):
        mode.sig, mode.places, mode.keep_zeros = n, None, keep_zeros
        return f"Results show {n} significant figure{'s' * (n != 1)}" + (", trailing zeros kept" if keep_zeros else "")
    return effect


def _decplace(mode, ev, n):
    mode.places = n
    return f"Results show {n} decimal place{'s' * (n != 1)}"


def _plotspec(mode, ev, rest):
    """`!plotspec grid: off` sets an option for every plot below it; `!plotspec reset` clears them."""
    if rest == "reset":
        mode.plotdefs.clear()
        return "Plot options are back to the defaults"
    m = re.fullmatch(r"([A-Za-z]\w*)\s*:\s*(.*)", rest)
    try:
        if not m:
            raise PlotError("!plotspec reads `!plotspec key: value` or `!plotspec reset`")
        key, _, value = parse_option(m.group(1), None, m.group(2), sheet=True)
    except PlotError as e:
        raise CommandError(str(e)) from None
    mode.plotdefs[key] = value
    return f"Plots below: {key} {canon(key, value)}"


# ---- the registry -----------------------------------------------------------

@dataclass(frozen=True)
class Command:
    name: str
    args: object       # an argument rule: NoArgs, Whole, Text or Statement
    summary: str       # one line, shown by the editor's suggestions
    effect: object = None
    help: str = ""     # the page's help row (HTML); commands with the same text share a row


_CLEAR_HELP = "On its own line, removes every non-global variable above it"
_CLEARF_HELP = "On its own line, removes every non-global function above it"
_ASSUME_HELP = ("Below <code>!noassume</code>, results keep the units that come out of the arithmetic "
                "(<code>kN*m</code>, not <code>J</code>) unless you convert with <code>-&gt;</code>. "
                "<code>!assume</code> returns to SI")
_TRIG_HELP = ("Set the angle unit for <code>sin</code>, <code>cos</code>, <code>tan</code> on bare numbers, "
              "and for <code>asin</code>, <code>acos</code>, <code>atan</code> results. Radians by default; "
              "explicit units such as <code>30'deg</code> always work")
_SHORT_HELP = ("Below <code>!short</code>, each line shows only its final result, with its unit but no "
               "intermediate steps. <code>!long</code> restores the full display")
_PRECISION_HELP = ("Choose how many significant figures (4 by default; <code>!sigfigsbig</code> keeps trailing "
                   "zeros, <code>2.500</code>) or decimal places results are displayed with. The last one given "
                   "wins. Only the display is rounded; every calculation uses the full value")

COMMANDS = (
    Command("clear", NoArgs(), "remove all non-global variables", _clear, _CLEAR_HELP),
    Command("clearf", NoArgs(), "remove all non-global functions", _clearf, _CLEARF_HELP),
    Command("noassume", NoArgs(), "keep typed units in results",
            _setter("assume", False, "Units are kept as typed unless converted with ->"), _ASSUME_HELP),
    Command("assume", NoArgs(), "reduce results to SI again",
            _setter("assume", True, "Units are reduced to SI again"), _ASSUME_HELP),
    Command("trigdeg", NoArgs(), "trig functions use degrees",
            _setter("angle", "degree", "Trig functions take and return degrees"), _TRIG_HELP),
    Command("trigrad", NoArgs(), "trig functions use radians",
            _setter("angle", "radian", "Trig functions take and return radians"), _TRIG_HELP),
    Command("short", NoArgs(), "show only final results, no steps",
            _setter("short", True, "Showing final results only, without steps"), _SHORT_HELP),
    Command("long", NoArgs(), "show steps again",
            _setter("short", False, "Showing steps again"), _SHORT_HELP),
    Command("sigfigs", Whole(1, 15), "display n significant figures (default 4): !sigfigs 5",
            _sigfigs(False), _PRECISION_HELP),
    Command("sigfigsbig", Whole(1, 15), "like !sigfigs, but keeps trailing zeros: 2.500",
            _sigfigs(True), _PRECISION_HELP),
    Command("decplace", Whole(0, 15), "display n decimal places instead: !decplace 2",
            _decplace, _PRECISION_HELP),
    Command("plot", Statement("A plot reads `!plot f(x), x = low .. high`"),
            "plot functions: !plot f(x), x = 0 .. 1"),
    Command("plotspec", Text(), "set a plot option for the plots below, e.g. !plotspec grid: off", _plotspec),
    Command("root", Statement("A solver block reads `!root x, y`"),
            "solve equations for unknowns: !root x, y, then indented equation: lines"),
    Command("minimize", Statement("A solver block reads `!minimize x`"),
            "find the unknowns that minimize an objective: !minimize x"),
    Command("maximize", Statement("A solver block reads `!maximize x`"),
            "find the unknowns that maximize an objective: !maximize x"),
)
BY_NAME = {c.name: c for c in COMMANDS}


def run(line, mode, ev):
    """Run one `!name args` line against `mode` (and, for !clear and !clearf, the
    evaluator's names). Returns the text the line shows; raises CommandError."""
    words = line.strip()[1:].split(None, 1)
    name = words[0] if words else ""
    command = BY_NAME.get(name)
    if command is None:
        raise CommandError(f"Unknown command '!{name}'. Available: " + ", ".join("!" + c.name for c in COMMANDS))
    value = command.args.parse(name, words[1].strip() if len(words) > 1 else "")
    return command.effect(mode, ev, value)


def help_rows():
    """The page's help table rows, one per run of commands that share a help text."""
    rows = []
    for c in COMMANDS:
        if not c.help:
            continue
        key = f"<kbd>!{c.name}{c.args.hint}</kbd>"
        if rows and rows[-1][1] == c.help:
            rows[-1][0].append(key)
        else:
            rows.append(([key], c.help))
    return "\n".join(f"      <tr><td>{' '.join(keys)}</td><td>{text}</td></tr>" for keys, text in rows)
