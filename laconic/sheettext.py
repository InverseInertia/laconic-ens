"""Worksheet text: what each line is, which block owns it, where its expressions are, and the
name, unit, number and string tokens in them. Nothing here parses an expression or evaluates
anything; this is the one place that reads the shape of the text.

    sheet = scan(text)
    sheet.lines[0].kind          "assign", "plot", "solveropt", ...
    sheet.owner(5)               the plot or solver Block that line 5 belongs to, or None
    sheet.line(5).tokens("name") the names in its expressions, with their columns

A plot owns the `key: value` lines indented under it; a solver block owns every indented,
non-blank line under it. Lines are numbered from 1 and split on "\\n" only, so the numbers are
the editor's; a "\\r" before the "\\n" belongs to the line's `eol`, not its text.

The lexer patterns (NAME, UNIT, NUMBER, STRING) are the grammar's terminals as well. The
editor's own lexers in static/ are held to this one by tests/sheettext_vectors.json."""
import re
from dataclasses import dataclass, field

# A name may hold ∞ as a whole subscript (`v_∞`, `T_∞_0`), the free-stream mark; ∞ on its own is
# the constant, and not a name.
IDENT = r"[^\W\d](?:_∞|\w)*"
NAME = rf"~?{IDENT}[`!@]*"
UNIT = r"'(?:(?:[^\W\d]|°)[\w°]*|%)"
# A trailing i or j makes the number imaginary: 4i, 2.5e3j. `2in` is still a number and a name.
NUMBER = r"(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?(?:[ij](?!\w))?"
STRING = r'"[^"\n]*"'

_TOKEN = re.compile(rf"(?P<text>{STRING})|(?P<unit>{UNIT})|(?P<num>{NUMBER})|(?P<name>{NAME})")
_NAME_RE = re.compile(rf"{NAME}\Z")

_FUNC_RE = re.compile(
    rf"^(~?{IDENT})\s*\(\s*({IDENT}(?:\s*,\s*{IDENT})*)\s*\)\s*=(?!=)\s*(.+)$")
_UNITDEF_RE = re.compile(r"^'([^\W\d]\w*)\s*=(?!=)\s*(.+)$")
_ASSIGN_RE = re.compile(rf"^({NAME})\s*=(?!=)\s*(.+)$")

_PLOT_RE = re.compile(r"^!plot[ \t]+(\S.*)$")
_SOLVER_RE = re.compile(r"^!(root|minimize|maximize|regression)(?:[ \t]+(.*\S))?[ \t]*$")
_PLOT_OPT_RE = re.compile(r"^[ \t]+([A-Za-z]\w*)(?:[ \t]+(\d+))?[ \t]*:[ \t]*(.*?)[ \t]*$")
_SOLVER_OPT_RE = re.compile(rf"^[ \t]+([A-Za-z]\w*)(?:[ \t]+({NAME}))?[ \t]*:[ \t]*(.*?)[ \t]*$")
_RESULT_RE = re.compile(r"^[ \t]+#@[ \t]*result[ \t]+(\{.*\})[ \t]*$")

# Option values that are expressions. Everything else under a block (titles, colours, methods)
# is text, so a rename leaves it alone. The editor turns its math keys off in the prose among it
# (static/editing.js isTextAt; tests/sheettext_vectors.json holds the two together).
PLOT_LIMIT_KEYS = ("xlim", "ylim", "xview", "yview")
SOLVER_EXPR_KEYS = ("equation", "objective", "constraint", "bounds", "data", "r2")


@dataclass(frozen=True)
class Token:
    kind: str     # "name", "unit", "num", or "text" (a quoted string)
    start: int    # column in the line
    text: str

    @property
    def end(self):
        return self.start + len(self.text)

    @property
    def bare(self):
        """A name without its ~, a unit without its quote."""
        return self.text.lstrip("~") if self.kind == "name" else self.text.removeprefix("'")


def tokenize(s, start=0, end=None):
    """The tokens of s[start:end], left to right. Operators, brackets and anything else
    that is not a token are skipped."""
    end = len(s) if end is None else end
    return [Token(m.lastgroup, m.start(), m.group()) for m in _TOKEN.finditer(s, start, end)]


def is_name(s):
    """A variable or function name: letters, digits and _, an optional ~ in front and
    ` ! @ after."""
    return bool(_NAME_RE.match(s))


@dataclass(frozen=True)
class Definition:
    """What a line of code defines. `name` is as written (a global keeps its ~); a unit's
    name has no quote. `body` is the expression source after the `=`."""
    kind: str     # "assign", "funcdef" or "unitdef"
    name: str
    params: tuple
    body: str


def definition(s):
    """The Definition on a stripped line of code, or None for a bare expression."""
    if m := _UNITDEF_RE.match(s):
        return Definition("unitdef", m.group(1), (), m.group(2))
    if m := _FUNC_RE.match(s):
        return Definition("funcdef", m.group(1), tuple(p.strip() for p in m.group(2).split(",")), m.group(3))
    if m := _ASSIGN_RE.match(s):
        return Definition("assign", m.group(1), (), m.group(2))
    return None


@dataclass(frozen=True)
class Option:
    """A `key: value` line under a plot (`color 2: red`) or solver (`bounds x: 0 .. 1`).
    `arg` is the series number or name before the colon, or None."""
    key: str
    arg: str
    value: str
    arg_span: tuple    # (start, end) columns, or None
    value_span: tuple


def _option(m):
    if not m:
        return None
    return Option(m.group(1), m.group(2), m.group(3), m.span(2) if m.group(2) else None, m.span(3))


def plot_option(s):
    """`s` read as an option line under a plot, or None. Only these lines belong to a plot."""
    return _option(_PLOT_OPT_RE.match(s))


@dataclass
class Line:
    n: int              # 1-based
    text: str           # without its line ending
    eol: str            # "\n", "\r\n", or "" on a last line with none
    kind: str           # blank heading meta comment command unitdef funcdef assign expr plot plotopt solver solveropt
    block: int = None   # header line of the plot or solver block that owns this line (the header owns itself)
    spans: tuple = ()   # (start, end) of each part that holds expressions
    option: Option = None   # under a block: the parsed option line
    result: str = None      # under a solver: the JSON of a stored `#@ result` line
    comment: bool = False   # a `#` line (comment, heading or meta), also when a block owns it
    definition: Definition = None

    @property
    def indent(self):
        return self.text[:len(self.text) - len(self.text.lstrip(" \t"))]

    @property
    def params(self):
        """A function definition's parameters; they are local to the line."""
        d = self.definition
        return d.params if d and d.kind == "funcdef" else ()

    def tokens(self, kind=None):
        """The tokens inside the line's expressions, optionally only those of one kind."""
        return [t for a, b in self.spans for t in tokenize(self.text, a, b) if kind in (None, t.kind)]

    def uses(self, names):
        """[column, length] of each use of one of `names` (written without ~) on the line, its ~
        included. A function's parameters are local, so they never count."""
        return [[t.start, len(t.text)] for t in self.tokens("name")
                if t.text not in self.params and t.bare in names]


@dataclass
class Block:
    """A `!plot` or a solver header and the lines it owns."""
    kind: str           # "plot" or "solver"
    command: str        # "plot", "root", "minimize", "maximize" or "regression"
    args: str           # what follows the command on the header line
    lines: list = field(default_factory=list)   # the header Line, then the owned lines

    @property
    def header(self):
        return self.lines[0].n

    @property
    def end(self):
        """Number of its last line."""
        return self.lines[-1].n

    @property
    def members(self):
        return self.lines[1:]


@dataclass
class Sheet:
    lines: list
    blocks: dict        # header line number -> Block

    def line(self, n):
        return self.lines[n - 1]

    def block(self, header):
        """The Block whose header is on line `header`, or None."""
        return self.blocks.get(header)

    def owner(self, n):
        """The Block that line `n` belongs to, header included, or None."""
        return self.blocks.get(self.lines[n - 1].block) if 1 <= n <= len(self.lines) else None


def _split(text):
    parts = text.split("\n")
    if parts[-1] == "":
        parts.pop()
    out = []
    for k, p in enumerate(parts):
        last = k == len(parts) - 1 and not text.endswith("\n")
        if p.endswith("\r") and not last:
            out.append((p[:-1], "\r\n"))
        else:
            out.append((p, "" if last else "\n"))
    return out


def _kind(s):
    """The kind of a stripped line outside any block."""
    if not s:
        return "blank"
    if s.startswith("'") and "=" in s:
        return "unitdef"      # starts like one; the parser decides whether it is
    if _SOLVER_RE.match(s):
        return "solver"
    if _PLOT_RE.match(s):
        return "plot"
    if s.startswith("##"):
        return "heading"
    if s.startswith("#@"):
        return "meta"
    if s.startswith("#"):
        return "comment"
    if s.startswith("!"):
        return "command"
    d = definition(s)
    return d.kind if d else "expr"


def _header_spans(text):
    m = re.match(r"[ \t]*!\w+", text)
    return ((m.end(), len(text)),)


def _plot_spans(text, o):
    if o.key in PLOT_LIMIT_KEYS:
        return (o.value_span,)
    if o.key == "note":
        at, close = re.search(r'"\s+at\s*\(', text), text.rfind(")")
        return ((at.end(), close),) if at and close > at.end() else ()
    return ()


def _solver_spans(o):
    if o is None or o.key not in SOLVER_EXPR_KEYS:
        return ()
    return ((o.arg_span,) if o.key == "bounds" and o.arg_span else ()) + (o.value_span,)


def scan(text):
    """Read `text` into a Sheet: one Line per line, and the blocks."""
    lines, blocks, cur = [], {}, None
    for n, (t, eol) in enumerate(_split(text), 1):
        s = t.strip()
        line = Line(n, t, eol, _kind(s))
        line.comment = line.kind in ("heading", "meta", "comment")
        if cur and cur.kind == "solver" and t[:1] in (" ", "\t") and s:
            m = _RESULT_RE.match(t)
            line.result = m.group(1) if m else None
            line.option = None if m else _option(_SOLVER_OPT_RE.match(t))
            line.spans = _solver_spans(line.option)
        elif cur and cur.kind == "plot" and (o := plot_option(t)):
            line.option, line.spans = o, _plot_spans(t, o)
        else:
            cur = None
            if line.kind in ("solver", "plot"):
                m = (_SOLVER_RE if line.kind == "solver" else _PLOT_RE).match(s)
                if line.kind == "solver":
                    cur = Block("solver", m.group(1), m.group(2) or "")
                else:
                    cur = Block("plot", "plot", m.group(1))
                blocks[n] = cur
                line.spans = _header_spans(t)
            elif line.kind not in ("blank", "heading", "meta", "comment", "command"):
                line.spans = ((0, len(t)),)
        if cur:
            if cur.lines and line.kind != "unitdef":   # a unit definition is one wherever it is
                line.kind = cur.kind + "opt"
            line.block = cur.lines[0].n if cur.lines else n
            cur.lines.append(line)
        if line.kind in ("unitdef", "funcdef", "assign", "expr"):
            line.definition = definition(s)
        lines.append(line)
    return Sheet(lines, blocks)
