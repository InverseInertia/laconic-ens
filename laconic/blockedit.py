"""Edits to the sheet text, and the block editor: the one writer of the lines a block owns.

The server never sends back a whole new sheet. A change (a view the mouse set on a plot, a stored
solver result, a rename) is a short list of Edits against the text the page sent, and the page
applies them as one undoable change (`Editing.merge` in static/editing.js).

    ed = BlockEditor(text, header)       the plot or solver block whose header is on that line
    ed.set("xview", "0 .. 2")            an option line, replaced where it is or added
    ed.set("color", "red", arg="2")      `color 2: red`
    ed.remove("autorun")                 every `autorun:` line
    ed.store_result(record)              the `#@ result` line, replacing any earlier one
    ed.append("# checked by hand")       any other block-owned line
    ed.edits()                           -> [Edit], as small as possible, against `text`

The editor keeps the block's indent (that of its first owned line, or two spaces) and the file's
line endings, and keeps the stored result last. It checks nothing about the values it writes;
plotopts.py and solver.py do that."""
import json
from dataclasses import dataclass

from .sheettext import scan


@dataclass(frozen=True)
class Edit:
    """Replace text[start:end] with `insert`. Offsets count code points, as Python strings do."""
    start: int
    end: int
    insert: str


def apply(text, edits):
    """`text` with `edits` (against `text`, not overlapping) made."""
    out, pos = [], 0
    for e in sorted(edits, key=lambda e: e.start):
        out += [text[pos:e.start], e.insert]
        pos = e.end
    return "".join(out) + text[pos:]


def _units(s):
    return len(s.encode("utf-16-le")) // 2


def to_json(text, edits):
    """The page's form of `edits`: `{from, to, insert}`, offsets in UTF-16 code units, as a
    JavaScript string counts them (a character outside the BMP counts two)."""
    return [{"from": _units(text[:e.start]), "to": _units(text[:e.end]), "insert": e.insert} for e in edits]


def from_json(text, edits):
    """The inverse of `to_json`."""
    at, u = {}, 0
    for i, ch in enumerate(text):
        at[u] = i
        u += 2 if ord(ch) > 0xFFFF else 1
    at[u] = len(text)
    return [Edit(at[e["from"]], at[e["to"]], e["insert"]) for e in edits]


def newline(text):
    """The line ending the file uses: that of its first line, or "\\n"."""
    i = text.find("\n")
    return "\r\n" if i > 0 and text[i - 1] == "\r" else "\n"


def _arg(a):
    """A series number written `02` is series 2."""
    return str(int(a)) if a is not None and a.isdigit() else a


@dataclass
class _Member:
    text: str
    eol: str            # its own line ending, "" on a last line with none
    key: str = None     # of an option line
    arg: str = None
    result: bool = False


class BlockEditor:
    """Collects changes to the lines of one plot or solver block; `edits()` says what they come to.
    `kind` is "plot" or "solver", or None when `header` does not start a block, in which case
    every change raises ValueError."""

    def __init__(self, text, header):
        self.text = text
        sheet = scan(text)
        self.block = b = sheet.block(header)
        self.kind = b.kind if b else None
        if not b:
            return
        at = sum(len(l.text) + len(l.eol) for l in sheet.lines[:b.header - 1])
        self._start = at + len(b.lines[0].text)       # the edited region: the header's ending to the
        self._end = at + sum(len(l.text) + len(l.eol) for l in b.lines) - len(b.lines[-1].eol)   # last line's text
        self._eol = b.lines[0].eol or newline(text)
        self._members = [_Member(l.text, l.eol, l.option.key if l.option else None,
                                 _arg(l.option.arg) if l.option else None, l.result is not None)
                         for l in b.members]
        self.indent = b.members[0].indent if b.members else "  "

    def _check(self):
        if not self.block:
            raise ValueError("Not a block")

    def _matching(self, key, arg):
        return [m for m in self._members if m.key == key and m.arg == _arg(arg) and not m.result]

    def _add(self, text, **kw):
        self._members.append(_Member(self.indent + text, self._eol, **kw))

    def _drop(self, gone):
        self._members = [m for m in self._members if not any(m is g for g in gone)]

    def set(self, key, value, arg=None):
        """Write `key arg: value`: over the first line with that key and argument (keeping its
        indent), removing any others, or as a new line."""
        self._check()
        label = key if arg is None else f"{key} {arg}"
        same = self._matching(key, arg)
        if not same:
            self._add(f"{label}: {value}", key=key, arg=_arg(arg))
            return
        first = same[0]
        first.text = first.text[:len(first.text) - len(first.text.lstrip(" \t"))] + f"{label}: {value}"
        self._drop(same[1:])

    def remove(self, key, arg=None):
        """Remove every `key arg:` line."""
        self._check()
        self._drop(self._matching(key, arg))

    def store_result(self, record):
        """Store `record` (a dict, written as compact JSON) as the block's result, last."""
        self._check()
        self._drop([m for m in self._members if m.result])
        self._add("#@ result " + json.dumps(record, separators=(",", ":")), result=True)

    def append(self, line):
        """Add a line the block owns (a comment, an option written by hand), indented like the rest."""
        self._check()
        self._add(line)

    def edits(self):
        """The changes so far, as at most one Edit against the text. The last line's ending lies
        outside the edit, so a file without a final newline still has none."""
        if not self.block:
            return []
        old = self.text[self._start:self._end]
        order = [m for m in self._members if not m.result] + [m for m in self._members if m.result]
        # each line is preceded by the ending of the one before it; a missing one is the file's
        endings = [self.block.lines[0].eol] + [m.eol for m in order]
        new = "".join((e or self._eol) + m.text for e, m in zip(endings, order))
        if old == new:
            return []
        n = min(len(old), len(new))
        a = 0
        while a < n and old[a] == new[a]:
            a += 1
        b = 0
        while b < n - a and old[-1 - b] == new[-1 - b]:
            b += 1
        return [Edit(self._start + a, self._end - b, new[a:len(new) - b])]
