"""Rename a variable, function or custom unit everywhere it appears in a worksheet.
Works on the source text, token by token, so comments, commands and numbers like
`1e5` are left alone. Names and units are separate: renaming `m` leaves `'m` (the
metre) alone, and renaming `'smoot` leaves a variable `smoot` alone."""
import re

from .evaluator import CONSTANTS, UNIT_NAME_RE, Evaluator
from . import solver
from .plotopts import OPT_RE, expr_spans, is_plot_line

NAME = r"~?[^\W\d]\w*[`!@]*"
_TOKEN = re.compile(
    r"(?P<text>\"[^\"\n]*\")"
    r"|(?P<unit>'(?:[^\W\d]|°)[\w°]*)"
    r"|(?P<num>(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?)"
    rf"|(?P<name>{NAME})")
_VALID = re.compile(rf"^{NAME}$")


class RenameError(ValueError):
    pass


class RenameWarning(RenameError):
    """The rename is possible but touches something standard; repeat with
    `confirm=True` to go ahead."""


def _builtins():
    return {n[3:] for n in dir(Evaluator) if n.startswith("fn_")} | set(CONSTANTS)


def _scan(text):
    """(line, spans) for each line, where spans are the parts that hold expressions.
    Under a `plot` only its limits, units and note positions are expressions; a title
    is text and is never renamed. In a solver block the unknowns, equations, objective,
    constraints and bounds are, and the stored result is not."""
    in_plot = in_solver = False
    for line in text.splitlines(keepends=True):
        if solver.is_solver_line(line):
            in_plot, in_solver = False, True
            yield line, solver.expr_spans(line, False)
        elif in_solver and solver.is_block_line(line):
            yield line, solver.expr_spans(line, True)
        else:
            in_solver = False
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


_PARAMS = re.compile(rf"\s*{NAME}\s*\(([^)]*)\)\s*=(?!=)")


def global_spans(text):
    """For each line, a function from the names global there to the [column, length] of
    each use of one on that line, its ~ included. The editor marks these. A function's
    parameters are local to its line, so they are never marked."""
    for line, spans in _scan(text):
        m = _PARAMS.match(line)
        local = {p.strip() for p in m.group(1).split(",")} if m else set()
        toks = [(t.start(), t.group()) for a, b in spans for t in _TOKEN.finditer(line, a, b)
                if t.lastgroup == "name" and t.group() not in local]
        yield lambda names, toks=toks: [[c, len(t)] for c, t in toks if t.lstrip("~") in names]


def _defined_in_sheet(text, name):
    return any(re.match(rf"\s*'{re.escape(name)}\s*=", line[a:b])
               for line, spans in _scan(text) for a, b in spans)


def _rename_unit(text, old, new, confirm):
    """`old` and `new` are unit names without the quote. A unit the sheet defines is
    renamed with its definition. A standard unit lives outside the text, so replacing
    it needs `confirm`: every use is swapped for `new`, which is either another
    existing unit or a new one, defined at the top of the sheet as equal to the old unit for the user to
    adjust."""
    if not UNIT_NAME_RE.match(old):
        raise RenameError(f"'{old} is not a valid unit name")
    if not UNIT_NAME_RE.match(new):
        raise RenameError(f"'{new} is not a valid unit name: use ASCII letters, digits and _, starting with a letter")
    if old == new:
        raise RenameError("The new name is the same as the old one")
    used = {u[1:] for u in _tokens(text, "unit")}
    if old not in used:
        raise RenameError(f"'{old} does not appear in the sheet")
    ev = Evaluator()
    if _defined_in_sheet(text, old):
        if new in used or ev.is_unit(new):
            raise RenameError(f"'{new} is already a unit; choose another name")
        return _substitute(text, "unit", "'" + old, "'" + new)
    if not confirm:
        raise RenameWarning(
            f"'{old} is a standard unit, not one defined in this sheet. Replacing it swaps "
            f"every use for '{new}"
            + ("" if new in used or ev.is_unit(new)
               else f" and adds a definition of '{new} for you to adjust")
            + ". Rename again to confirm.")
    out, count = _substitute(text, "unit", "'" + old, "'" + new)
    if not (new in used or ev.is_unit(new)):
        out = f"'{new} = 1'{old}\n" + out
    return out, count


def _substitute(text, kind, old, new):
    count = 0

    def sub(m):
        nonlocal count
        if m.lastgroup != kind:
            return m.group()
        tok = m.group()
        if kind == "name":   # the ~ marks a definition as global and stays where it is
            if tok.lstrip("~") != old:
                return tok
            count += 1
            return tok[:len(tok) - len(tok.lstrip("~"))] + new
        if tok == old:
            count += 1
            return new
        return tok

    out = []
    for line, spans in _scan(text):
        pos = 0
        for a, b in spans:
            out += [line[pos:a], _TOKEN.sub(sub, line[a:b])]
            pos = b
        out.append(line[pos:])
    return "".join(out), count


def rename(text, old, new, confirm=False):
    """Returns (new_text, count). Raises RenameError when the rename is not safe:
    a malformed name, a built-in, or a name the sheet already uses. A leading `'`
    on `old` renames a unit (the quote on `new` is optional); replacing a standard unit
    raises RenameWarning unless `confirm` is set."""
    old, new = old.strip(), new.strip()
    if not old.startswith("'"):
        old, new = old.lstrip("~"), new.lstrip("~")   # a global and its later uses are one name
    if old.startswith("'"):
        return _rename_unit(text, old[1:], new.removeprefix("'"), confirm)
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
    used = {n.lstrip("~") for n in _names(text)}
    if old not in used:
        raise RenameError(f"'{old}' does not appear in the sheet")
    if new in used:
        raise RenameError(f"'{new}' is already used in the sheet")
    return _substitute(text, "name", old, new)
