"""Rename a variable or function everywhere it appears in a worksheet. Works on
the source text, token by token, so comments, commands, units (`'m` is the metre,
`m` is a variable) and numbers like `1e5` are left alone."""
import re

from .evaluator import CONSTANTS, Evaluator

NAME = r"~?[^\W\d]\w*[`!@]*"
_TOKEN = re.compile(
    r"(?P<unit>'(?:[^\W\d]|°)[\w°]*)"
    r"|(?P<num>(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?)"
    rf"|(?P<name>{NAME})")
_VALID = re.compile(rf"^{NAME}$")


class RenameError(ValueError):
    pass


def _builtins():
    return {n[3:] for n in dir(Evaluator) if n.startswith("fn_")} | set(CONSTANTS)


def _code(line):
    """True for lines that hold an expression or definition."""
    s = line.strip()
    return bool(s) and not s.startswith(("#", "!"))


def _names(text):
    for line in text.splitlines():
        if _code(line):
            for m in _TOKEN.finditer(line):
                if m.lastgroup == "name":
                    yield m.group()


def rename(text, old, new):
    """Returns (new_text, count). Raises RenameError when the rename is not safe:
    a malformed name, a built-in, or a name the sheet already uses."""
    old, new = old.strip(), new.strip()
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

    count = 0

    def sub(m):
        nonlocal count
        if m.lastgroup == "name" and m.group() == old:
            count += 1
            return new
        return m.group()

    out = []
    for line in text.splitlines(keepends=True):
        out.append(_TOKEN.sub(sub, line) if _code(line) else line)
    return "".join(out), count
