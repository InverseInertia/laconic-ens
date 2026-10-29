"""Rename a variable, function or custom unit everywhere it appears in a worksheet.
Works on the source text, token by token, so comments, commands and numbers like
`1e5` are left alone. Names and units are separate: renaming `m` leaves `'m` (the
metre) alone, and renaming `'smoot` leaves a variable `smoot` alone. The result is one
Edit (blockedit.py) per use, against the text it was given."""
from .blockedit import Edit, newline
from .evaluator import CONSTANTS, UNIT_NAME_RE, Evaluator
from .functions import FUNCTIONS
from .sheettext import is_name, scan


class RenameError(ValueError):
    pass


class RenameWarning(RenameError):
    """The rename is possible but touches something standard; repeat with
    `confirm=True` to go ahead."""


def _builtins():
    return set(FUNCTIONS) | set(CONSTANTS)


def _tokens(text, kind):
    """Every token of `kind` in the sheet's expressions. Under a `plot` only its limits and note
    positions are expressions; a title is text and is never renamed. In a solver block the
    unknowns, equations, objective, constraints and bounds are, and the stored result is not."""
    return (t.text for line in scan(text).lines for t in line.tokens(kind))


def _names(text):
    return _tokens(text, "name")


def _defined_in_sheet(text, name):
    return any(line.block is None and line.definition and line.definition.kind == "unitdef"
               and line.definition.name == name for line in scan(text).lines)


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
    edits, count = _substitute(text, "unit", "'" + old, "'" + new)
    if not (new in used or ev.is_unit(new)):
        edits.insert(0, Edit(0, 0, f"'{new} = 1'{old}" + newline(text)))
    return edits, count


def _substitute(text, kind, old, new):
    edits, at = [], 0
    for line in scan(text).lines:
        for t in line.tokens(kind):
            # the ~ marks a definition as global and stays where it is
            if (t.bare if kind == "name" else t.text) == old:
                a = t.end - len(t.bare) if kind == "name" else t.start
                edits.append(Edit(at + a, at + t.end, new))
        at += len(line.text) + len(line.eol)
    return edits, len(edits)


def rename(text, old, new, confirm=False):
    """Returns (edits, count). Raises RenameError when the rename is not safe:
    a malformed name, a built-in, or a name the sheet already uses. A leading `'`
    on `old` renames a unit (the quote on `new` is optional); replacing a standard unit
    raises RenameWarning unless `confirm` is set."""
    old, new = old.strip(), new.strip()
    if not old.startswith("'"):
        old, new = old.lstrip("~$"), new.lstrip("~$")   # a global (or symbol) and its later uses are one name
    if old.startswith("'"):
        return _rename_unit(text, old[1:], new.removeprefix("'"), confirm)
    if not is_name(old):
        raise RenameError(f"'{old}' is not a valid name")
    if not is_name(new):
        raise RenameError(f"'{new}' is not a valid name")
    if old == new:
        raise RenameError("The new name is the same as the old one")
    if old in _builtins():
        raise RenameError(f"'{old}' is built in and cannot be renamed")
    if new in _builtins():
        raise RenameError(f"'{new}' is built in; choose another name")
    used = {n.lstrip("~$") for n in _names(text)}
    if old not in used:
        raise RenameError(f"'{old}' does not appear in the sheet")
    if new in used:
        raise RenameError(f"'{new}' is already used in the sheet")
    return _substitute(text, "name", old, new)
