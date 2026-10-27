from importlib import import_module

# markdown is cheap, and loading it here keeps the name the function rather than the submodule.
from .markdown import markdown

# The rest pull in Pint, NumPy and Lark, about half a second: load them on first use, so the
# launcher can hand a window to a running LENS, and the server can start the browser, without
# waiting for them.
_LAZY = {"LineResult": "lineresult", "Worksheet": "sheet", "evaluate": "sheet", "run": "sheet",
         "document": "latex", "snippet": "latex"}


def __getattr__(name):
    if name not in _LAZY:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f".{_LAZY[name]}", __name__), name)
    globals()[name] = value
    return value


__all__ = ["run", "evaluate", "document", "snippet", "markdown", "LineResult", "Worksheet"]
