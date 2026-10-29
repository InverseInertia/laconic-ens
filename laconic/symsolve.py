"""`!symsolve`: the block that solves equations for symbols, as it is written. The solving is
symbolic.py's (sympy); this module only reads the block, so the editor's vocabulary can name its
options without importing sympy.

    $a, $b, $x
    !symsolve x               the symbols to solve for, declared above with $
      equation: a*x + b = 0   lhs = rhs, or one expression that is zero; as many as needed
      pick: 1                 which solution the unknowns hold below, when there are several

Like a regression it reads as a solver block (sheettext), so its option lines, Rename and the
editor's suggestions work the same; it is worked out every time the sheet runs and stores nothing."""
from dataclasses import dataclass, field

from .evaluator import EvalError
from .parser import ParseError, parse_expr
from .sheettext import is_name

KEYS = ("equation", "pick")
KEY_NOTES = {"equation": "lhs = rhs, or one expression that is zero; as many as you like",
             "pick": "which solution the unknowns hold below the block, when there are several"}


@dataclass
class SolveBlock:
    line: int
    end: int
    unknowns: list = field(default_factory=list)
    equations: list = field(default_factory=list)   # (line, lhs node, rhs node or None)
    pick: int = None
    pick_line: int = None
    errors: dict = field(default_factory=dict)      # option line number -> message
    problem: str = ""

    def nodes(self):
        return [n for _, a, b in self.equations for n in (a, b) if n is not None]


def parse_block(handle):
    """The `!symsolve` block `handle` (a sheettext.Block), as regression.parse_block reads its own."""
    from .solver import SolverError, split_relation
    b = SolveBlock(handle.header, handle.end)
    names = [p.strip() for p in handle.args.split(",")] if handle.args else []
    if not names or not all(is_name(n) for n in names):
        b.problem = "!symsolve reads `!symsolve x, y`: the symbols to solve for, then indented `equation:` lines"
        return b
    if len({n.lstrip("~") for n in names}) != len(names):
        b.problem = "A name is listed twice"
        return b
    b.unknowns = names
    for line in handle.members:
        n, o = line.n, line.option
        if line.result is None and line.text.strip().startswith("#"):
            continue
        try:
            if line.result is not None:
                raise EvalError("!symsolve is worked out as the sheet runs and stores no result; remove this line")
            if not o:
                raise EvalError("Option lines read `key: value`")
            if o.key not in KEYS:
                raise EvalError(f"Unknown option '{o.key}'. Under !symsolve: " + ", ".join(KEYS))
            if o.arg:
                raise EvalError(f"{o.key} does not take a name before the colon")
            if not o.value:
                raise EvalError(f"{o.key} needs a value")
            if o.key == "equation":
                lhs, op, rhs = split_relation(o.value)
                if op not in (None, "="):
                    raise EvalError("!symsolve solves equations, `lhs = rhs`; it has no inequalities")
                b.equations.append((n, parse_expr(lhs), parse_expr(rhs) if rhs else None))
            else:
                if b.pick is not None:
                    raise EvalError("pick is given twice")
                if not o.value.isdigit() or int(o.value) < 1:
                    raise EvalError("pick is a solution's number, from 1: `pick: 2`")
                b.pick, b.pick_line = int(o.value), n
        except (EvalError, ParseError, SolverError) as e:
            b.errors[n] = str(e)
    if b.errors:
        count = len(b.errors)
        b.problem = f"{count} option line{'s' * (count != 1)} below need{'s' * (count == 1)} fixing"
    elif not b.equations:
        b.problem = "!symsolve needs at least one `equation:` line under it"
    return b
