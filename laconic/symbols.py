"""The symbol table: which variables and functions each line of a sheet can see.

It is built once, while the sheet runs top to bottom (`sheet.evaluate` moves `line` and
records each definition that succeeds), and is the one place the scope rules live:

- a definition makes a name visible on the lines below it, until the name is defined
  again or `!clear` / `!clearf` removes it;
- a `~` on a definition makes the name global: from then on it is stored as `~name`,
  every use of the name means the global, and `!clear` / `!clearf` keep it;
- a `$` declares a symbol (`$x`, `~$g` for a global one): a variable whose value is a sympy
  Symbol, defined, cleared and made global like any other;
- a function's parameters are local to its line;
- a solver block defines its unknowns again on its header line, with the stored answer;
- a line that fails defines nothing.

It also holds what each key is bound to as the sheet runs: a variable's value, a function's
parameters and body, and whether a value comes from an out-of-date solver result (is stale).
A definition, a clear and a solver unknown's binding are one call each, so these never drift
apart from the scope rules:

    table.define("x", q, text="2 m", stale=False)    a variable defined on the current line
    table.define_function("f", ("x",), body)          a function
    table.clear(VARIABLE)                             !clear; !clearf with FUNCTION
    table.key("g")           "~g" once g is global: the key its value is stored under
    table.values, table.functions                     key -> value, key -> (params, body), read only
    table.tainted(nodes)     True if evaluating `nodes` reads a stale value
    table.visible(5)         the Symbols line 5 can read
    table.uses(line)         [column, length, symbol id] of each name on a sheettext Line

The page gets the table through the eval response (each row carries the symbols its line
defines and the uses on it); static/symbols.js reads it there."""
from dataclasses import dataclass
from types import MappingProxyType

from .nodes import refs

VARIABLE, FUNCTION = "variable", "function"


class ScopeError(ValueError):
    pass


@dataclass
class Symbol:
    """One definition of a name. `until` is the last line it is visible on (the line that
    defines the name again or clears it), or None when it lasts to the end of the sheet."""
    id: int
    name: str            # without its ~
    kind: str            # VARIABLE or FUNCTION
    line: int            # the line that defines it
    is_global: bool
    value: str = ""      # a variable's value, as the sheet prints it
    params: tuple = ()   # a function's parameters
    until: int = None
    symbol: bool = False # a symbol declared with $ (see symbolic.py), not a value

    @property
    def key(self):
        """The name its value is stored under: a global keeps its ~."""
        return "~" + self.name if self.is_global else self.name

    def visible_at(self, n):
        return self.line < n and (self.until is None or n <= self.until)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "kind": self.kind, "line": self.line, "until": self.until,
                "global": self.is_global, "value": self.value, "params": list(self.params), "symbol": self.symbol}


class SymbolTable:
    def __init__(self):
        self.symbols = []          # every definition, in the order the sheet made them
        self.line = 0              # the line being run; set by sheet.evaluate
        self._live = {}            # (kind, name) -> the Symbol the current line sees
        self._first = {}           # (kind, name) -> the Symbol that made the name global
        self._by_name = {}         # name -> its Symbols
        self._values = {}          # variable key -> its value (a Quantity)
        self._bodies = {}          # function key -> (params, body)
        self._stale = set()        # variable keys whose value comes from an out-of-date solver result
        self.values = MappingProxyType(self._values)       # the evaluator's scope
        self.functions = MappingProxyType(self._bodies)

    # ---- resolving ----------------------------------------------------------------
    def key(self, name, kind=VARIABLE):
        """The key `name` (written with or without ~) is stored under at the current line.
        A name that has been made global resolves to the global. A symbol's `$` is no part of it."""
        bare = name.lstrip("~$")
        return "~" + bare if name.startswith("~") or (kind, bare) in self._first else bare

    def first_global(self, sym):
        """The Symbol that made `sym`'s name global, or None for a name that is not."""
        return self._first.get((sym.kind, sym.name))

    def visible(self, n):
        """The Symbols line `n` can read, one per name and kind."""
        return [s for s in self.symbols if s.visible_at(n)]

    def find(self, name, n, kind=None, defining=False):
        """The Symbol `name` (with or without ~) means on line `n`: with `defining`, the one
        that line defines, else the one it can see. `kind` is tried first, then the other."""
        bare = name.lstrip("~$")
        kinds = (kind, VARIABLE if kind == FUNCTION else FUNCTION) if kind else (VARIABLE, FUNCTION)
        for k in kinds:
            for s in self._by_name.get(bare, ()):
                if s.kind == k and (s.line == n if defining else s.visible_at(n)):
                    return s
        return None

    def uses(self, line):
        """[column, length, symbol id] of each name in a sheettext Line's expressions that
        means a symbol. The name a definition defines means the new symbol (or, if the line
        failed, the one it would have replaced); a function's parameters are local."""
        d, out = line.definition, []
        for i, t in enumerate(line.tokens("name")):
            if t.text in line.params:
                continue
            kind = FUNCTION if line.text[t.end:].lstrip().startswith("(") else VARIABLE
            s = None
            if d is not None and d.kind == "symdef":   # every name on a declaration is declared
                s = self.find(t.text, line.n, VARIABLE, defining=True)
            elif i == 0 and d is not None and d.kind in ("assign", "funcdef"):
                kind = FUNCTION if d.kind == "funcdef" else VARIABLE
                s = self.find(t.text, line.n, kind, defining=True)
            s = s or self.find(t.text, line.n, kind)
            if s is not None:
                out.append([t.start, len(t.text), s.id])
        return out

    def defined_on(self, n):
        return [s for s in self.symbols if s.line == n]

    # ---- what a key holds -----------------------------------------------------------
    def reach(self, nodes, local=()):
        """Walk `nodes` and the bodies of the user functions they call. Yields (kind, key, extra):
        ("var", key, None), ("unit", name, None) and ("func", key, (params, body))."""
        seen, todo = set(), [(n, frozenset(local)) for n in nodes]
        while todo:
            node, loc = todo.pop()
            names, calls, units = refs(node)
            for u in units:
                yield "unit", u, None
            for nm in names:
                if nm not in loc:
                    yield "var", self.key(nm), None
            for fn in calls:
                fk = self.key(fn, FUNCTION)
                if fk in self._bodies and fk not in seen:
                    seen.add(fk)
                    params, body = self._bodies[fk]
                    yield "func", fk, (params, body)
                    todo.append((body, frozenset(params)))

    def tainted(self, nodes, local=()):
        """True if evaluating `nodes` reads a value that came from an out-of-date solver."""
        return bool(self._stale) and any(k == "var" and key in self._stale for k, key, _ in self.reach(nodes, local))

    def is_stale(self, key):
        return key in self._stale

    # ---- defining -----------------------------------------------------------------
    def define(self, name, value, text="", stale=False, symbol=False):
        """Define the variable `name` on the current line as `value` (shown as `text`); `stale`
        when the value comes from an out-of-date solver result; `symbol` for a symbol declared
        with `$`, whose value is its sympy Symbol. Returns its Symbol."""
        sym = self._bind(name, VARIABLE, text)
        sym.symbol = symbol
        self._values[sym.key] = value
        (self._stale.add if stale else self._stale.discard)(sym.key)
        return sym

    def define_function(self, name, params, body):
        sym = self._bind(name, FUNCTION, params=params)
        self._bodies[sym.key] = (tuple(params), body)
        return sym

    def mark_stale(self, keys):
        """Mark values as not trustworthy without defining them again (a solver block that failed)."""
        self._stale |= set(keys)

    def trial(self, key, value):
        """Hold `value` under the variable `key` for a moment, with no new definition: a solver's
        trial values, put back to the starting value when it is done."""
        self._values[key] = value

    def _bind(self, name, kind=VARIABLE, value="", params=()):
        """Record a definition of `name` on the current line and return its Symbol. A `~`
        makes the name global; a name already in use without one cannot become global."""
        bare, tilde = name.lstrip("~$"), name.startswith("~")
        old = self._live.get((kind, bare))
        if tilde and (kind, bare) not in self._first and old is not None:
            raise ScopeError(f"'{bare}' is already a non-global {kind}. "
                             f"Define it with ~ the first time, or rename one of them")
        sym = Symbol(len(self.symbols), bare, kind, self.line,
                     tilde or (kind, bare) in self._first, value, tuple(params))
        if old is not None:
            old.until = self.line
        self._live[(kind, bare)] = sym
        if sym.is_global:
            self._first.setdefault((kind, bare), sym)
        self.symbols.append(sym)
        self._by_name.setdefault(bare, []).append(sym)
        return sym

    def clear(self, kind):
        """`!clear` (variables) or `!clearf` (functions) on the current line: every name of
        `kind` that is not global stops being visible, and what it held is dropped. Returns
        (removed keys, kept keys)."""
        gone, kept = [], []
        for (k, bare), s in list(self._live.items()):
            if k != kind:
                continue
            if s.is_global:
                kept.append(s.key)
            else:
                s.until = self.line
                del self._live[(k, bare)]
                gone.append(s.key)
        held = self._values if kind == VARIABLE else self._bodies
        for key in gone:
            held.pop(key, None)
        self._stale -= set(gone)
        return gone, kept
