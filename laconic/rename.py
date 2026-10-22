"""Rename a variable, function or custom unit everywhere it appears in a worksheet.
Works on the source text, token by token, so comments, commands and numbers like
`1e5` are left alone. Names and units are separate: renaming `m` leaves `'m` (the
metre) alone, and renaming `'smoot` leaves a variable `smoot` alone."""
import re

from .evaluator import CONSTANTS, Evaluator
from .plotopts import OPT_RE, expr_spans, is_plot_line

NAME = r"~?[^\W\d]\w*[`!@]*"
_TOKEN = re.compile(
    r"(?P<text>\"[^\"\n]*\")"
    r"|(?P<unit>'(?:[^\W\d]|°)[\w°]*)"
    r"|(?P<num>(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?)"
    rf"|(?P<name>{NAME})")
_VALID = re.compile(rf"^{NAME}$")
_UNIT_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")


class RenameError(ValueError):
    pass


def _builtins():
    return {n[3:] for n in dir(Evaluator) if n.startswith("fn_")} | set(CONSTANTS)


def _scan(text):
    """(line, spans) for each line, where spans are the parts that hold expressions.
    Under a `plot` only its limits, units and note positions are expressions; a title
    is text and is never renamed."""
    in_plot = False
    for line in text.splitlines(keepends=True):
        yield line, expr_spans(line, in_plot)
        in_plot = is_plot_line(line) or (in_plot and bool(OPT_RE.match(line)))


def _tokens(text, kind):
    for line, spans in _scan(text):
        for a, b in spans:
            for m in _TOKEN.finditer(line, a, b):
                if m.lastgroup == kind:
                    yield m.group()


def _names(text):
    return _tokens(text, "name")


def _rename_unit(text, old, new):
    """`old` and `new` are unit names without the quote. Only a unit the sheet itself
    defines can be renamed; built-in and instance-wide units live outside the text."""
    if not _UNIT_NAME.match(old):
        raise RenameError(f"'{old} is not a valid unit name")
    if not _UNIT_NAME.match(new):
        raise RenameError(f"'{new} is not a valid unit name: use ASCII letters, digits and _, starting with a letter")
    if old == new:
        raise RenameError("The new name is the same as the old one")
    used = {u[1:] for u in _tokens(text, "unit")}
    if old not in used:
        raise RenameError(f"'{old} does not appear in the sheet")
    if not any(re.match(rf"\s*'{re.escape(old)}\s*=", line[a:b])
               for line, spans in _scan(text) for a, b in spans):
        raise RenameError(f"'{old} is not defined in this sheet, so it cannot be renamed")
    if new in used or Evaluator().is_unit(new):
        raise RenameError(f"'{new} is already a unit; choose another name")
    return _substitute(text, "unit", "'" + old, "'" + new)


def _substitute(text, kind, old, new):
    count = 0

    def sub(m):
        nonlocal count
        if m.lastgroup == kind and m.group() == old:
            count += 1
            return new
        return m.group()

    out = []
    for line, spans in _scan(text):
        pos = 0
        for a, b in spans:
            out += [line[pos:a], _TOKEN.sub(sub, line[a:b])]
            pos = b
        out.append(line[pos:])
    return "".join(out), count


def rename(text, old, new):
    """Returns (new_text, count). Raises RenameError when the rename is not safe:
    a malformed name, a built-in, or a name the sheet already uses. A leading `'`
    on `old` renames a unit the sheet defines (the quote on `new` is optional)."""
    old, new = old.strip(), new.strip()
    if old.startswith("'"):
        return _rename_unit(text, old[1:], new.removeprefix("'"))
    if not _VALID.match(old):
        raise RenameError(f"'{old}' is not a valid name")
    if not _VALID.match(new):
        raise RenameError(f"'{new}' is not a valid name")
    if old == new:
        raise RenameError("The new name is the same as the old one")
    if old in _builtins():
        raise RenameError(f"'{old}' is built in and cannot be renamed")
    if new in _builtins():
        raise RenameError(f"'{new}' is built in; choose another name")
    used = set(_names(text))
    if old not in used:
        raise RenameError(f"'{old}' does not appear in the sheet")
    if new in used:
        raise RenameError(f"'{new}' is already used in the sheet")
    return _substitute(text, "name", old, new)
