"""`!loop`: a block whose indented lines run once for each whole number in a range.

    S = 0
    M = zeros(3, 3)
    !loop i = 1 .. 3              the index and its range, both ends included
      S = S + i^2                 a name: what it holds after the last pass is visible below
      !loop j = 1 .. i            a loop inside: its lines are indented under it
        elem(M, i, j) = 1/(i + j - 1)    an entry of a matrix (idx(v, i) for a vector's)

Each line either assigns a name or sets an entry of a vector or matrix that already exists, as
`zeros(3, 3)` makes one. The lines read what the passes before them left; below the block, every
name the block assigned holds its last value, and the index is gone. The block is worked out
every time the sheet runs, like a regression, and stores nothing.

Like a plot, the block is read by sheettext (its lines are `loopline`s); this module reads the
nested structure out of their indentation and runs it against the evaluator."""
import re
from dataclasses import dataclass, field

import numpy as np

from .evaluator import EvalError, _array
from .nodes import Call, Name
from .parser import ParseError, parse_expr
from .sheettext import IDENT, NAME

MAX_LINES = 10_000      # lines and passes run in one block, all together: the sheet runs on every keystroke
_HEAD_RE = re.compile(rf"^({IDENT})\s*=\s*(.+?)\s*\.\.\s*(.+)$")
_ASSIGN_RE = re.compile(rf"^({NAME})\s*=(?!=)\s*(.+)$")
_ENTRY_RE = re.compile(r"^(idx|elem)\s*\((.*)\)\s*=(?!=)\s*(.+)$")
HEADER_HINT = "A loop reads `!loop i = 1 .. n`: the index, then the first and last values"
LINE_HINT = "A line in a loop assigns a name, `S = S + i`, or an entry, `idx(v, i) = ...` or `elem(M, i, j) = ...`"


class LoopError(Exception):
    pass


@dataclass
class Loop:
    """A `!loop` line, the top one or one inside it, and the steps it runs each pass."""
    n: int
    index: str = ""
    lo: object = None       # the range's ends, as expressions read on each pass of the loop around it
    hi: object = None
    steps: list = field(default_factory=list)


@dataclass
class Assign:
    n: int
    name: str
    expr: object


@dataclass
class Entry:
    """`idx(v, i) = x` or `elem(M, i, j) = x`."""
    n: int
    func: str
    name: str
    at: tuple               # the index expressions
    expr: object


@dataclass
class LoopBlock:
    top: Loop
    errors: dict = field(default_factory=dict)      # line number -> message
    problem: str = ""

    def nodes(self):
        """Every expression in the block."""
        out, todo = [], [self.top]
        while todo:
            s = todo.pop()
            if isinstance(s, Loop):
                out += [x for x in (s.lo, s.hi) if x is not None]
                todo += s.steps
            elif isinstance(s, Entry):
                out += [*s.at, s.expr]
            else:
                out.append(s.expr)
        return out

    def names(self):
        """The names the block assigns, in the order they are first assigned."""
        out, todo = [], [self.top]
        while todo:
            s = todo.pop(0)
            if isinstance(s, Loop):
                todo[:0] = s.steps
            elif s.name not in out:
                out.append(s.name)
        return out

    def indexes(self):
        out, todo = [], [self.top]
        while todo:
            s = todo.pop()
            if isinstance(s, Loop):
                out.append(s.index)
                todo += s.steps
        return out


def _header(loop, args):
    m = _HEAD_RE.match(args.strip())
    if not m:
        raise LoopError(HEADER_HINT)
    loop.index, loop.lo, loop.hi = m.group(1), parse_expr(m.group(2)), parse_expr(m.group(3))


def _step(n, s):
    if m := _ENTRY_RE.match(s):
        target = parse_expr(f"{m.group(1)}({m.group(2)})")
        want = 2 if m.group(1) == "idx" else 3
        if not isinstance(target, Call) or len(target.args) != want or not isinstance(target.args[0], Name):
            raise LoopError(f"An entry is set as `idx(v, i) = ...` or `elem(M, i, j) = ...`, "
                            f"with the vector or matrix by its name")
        return Entry(n, m.group(1), target.args[0].name, target.args[1:], parse_expr(m.group(3)))
    if m := _ASSIGN_RE.match(s):
        if "$" in m.group(1):
            raise LoopError("A symbol is declared on a line of its own, outside the loop")
        return Assign(n, m.group(1), parse_expr(m.group(2)))
    raise LoopError(LINE_HINT)


def parse_block(handle):
    """The `!loop` block `handle` (a sheettext.Block). A line that does not read is reported on
    that line; the block runs only when every line reads."""
    b = LoopBlock(Loop(handle.header))
    try:
        _header(b.top, handle.args)
    except (LoopError, ParseError) as e:
        b.problem = str(e)
    # (indent of its steps, or None before its first step; the Loop), from the top loop inwards
    stack = [(None, b.top)]
    for line in handle.members:
        s, indent = line.text.strip(), line.indent
        if s.startswith("#"):
            continue
        while len(stack) > 1:
            level, loop = stack[-1]
            outer = stack[-2][0]
            if level is None and len(indent) <= len(outer):
                b.errors[loop.n] = "This loop has nothing to run: indent the lines it runs under it"
            elif level is None or len(indent) >= len(level):
                break
            stack.pop()
        level, loop = stack[-1]
        if level is None:
            stack[-1] = (indent, loop)
        elif indent != level:
            b.errors[line.n] = "This line's indent does not match the lines above it in the loop"
            continue
        try:
            if s.startswith("!loop"):
                inner = Loop(line.n)
                _header(inner, s[len("!loop"):])
                loop.steps.append(inner)
                stack.append((None, inner))
            elif s.startswith("!"):
                raise LoopError(f"Only another !loop can go inside a loop; {s.split()[0]} goes outside it")
            else:
                loop.steps.append(_step(line.n, s))
        except (LoopError, ParseError) as e:
            b.errors[line.n] = str(e)
    for level, loop in stack[1:]:
        if level is None:
            b.errors[loop.n] = "This loop has nothing to run: indent the lines it runs under it"
    if not b.problem and b.errors:
        b.problem = f"{len(b.errors)} line{'s' if len(b.errors) > 1 else ''} below need{'' if len(b.errors) > 1 else 's'} fixing"
    if not b.problem and not b.top.steps:
        b.problem = "The loop has nothing to run: indent the lines it runs under it"
    if not b.problem:
        clash = [s.name for s in _assigns(b.top) if s.name.lstrip("~") in b.indexes()]
        if clash:
            b.problem = f"{clash[0]} is a loop's index, which a line in the loop cannot change"
    return b


def _assigns(loop):
    for s in loop.steps:
        if isinstance(s, Loop):
            yield from _assigns(s)
        else:
            yield s


@dataclass
class Run:
    """What a block left: each name it assigned, with its value after the last pass, and the
    number of passes of the top loop."""
    values: dict            # name as written -> value
    passes: int


class StepError(Exception):
    """A step that failed, on its line, and the index values it failed at (`where`)."""
    def __init__(self, n, message, where=""):
        super().__init__(message + where)
        self.n, self.where = n, where


def run(block, ev, describe=str):
    """Run the block against the evaluator's variables, without changing them. Raises StepError
    naming the line that failed and the pass it failed on (`describe` words an exception)."""
    scope, values, copied, here = dict(ev.vars), {}, set(), []
    count = [0]

    def tick(n):
        """Count a line or a pass (a pass of a loop whose lines are all loops that run no times costs
        time too) and stop the block past MAX_LINES."""
        count[0] += 1
        if count[0] > MAX_LINES:
            raise StepError(n, f"The loop ran more than {MAX_LINES:,} lines, so it was stopped, since "
                               "the sheet runs on every keystroke. For a whole vector or matrix at "
                               "once, use its operators (v .* v, sum(v))", where())

    def bounds(loop):
        ends = []
        for x in (loop.lo, loop.hi):
            q = ev.eval(x, scope)
            if np.ndim(q.magnitude) or not q.dimensionless or np.iscomplexobj(q.magnitude):
                raise EvalError("A loop's first and last values are plain whole numbers")
            v = float(q.to("dimensionless").magnitude)
            if v != int(v):
                raise EvalError(f"A loop counts in whole numbers; {v:g} is not one")
            ends.append(int(v))
        return ends

    def entry(s):
        key = ev.vkey(s.name)
        if key not in scope and s.name not in scope:
            raise EvalError(f"{s.name} is not defined: make it before the loop, such as {s.name} = zeros(3, 1)")
        key = s.name if s.name in scope else key
        A, x = scope[key], ev.settle(ev.eval(s.expr, scope))
        m = np.asarray(A.magnitude)
        if m.ndim == 0:
            raise EvalError(f"{s.name} holds one value, not a vector or matrix: make it with zeros()")
        at = [ev.eval(i, scope) for i in s.at]
        if key not in copied:          # the value above the block stays as it was
            m = _array(m).copy()
            copied.add(key)
        if np.iscomplexobj(x.magnitude) and not np.iscomplexobj(m):
            m = m.astype(complex)
        if x.dimensionality != A.dimensionality:
            if np.any(m):
                raise EvalError(f"{s.name} is in {A.units:~P}, and this value is in {x.units:~P}: "
                                f"every entry of a matrix has the same dimension")
            A = ev.Q(m, x.units)       # an all-zero matrix takes the units of what is put in it
        v = np.asarray(x.to(A.units).magnitude)
        if s.func == "elem":
            if m.ndim == 1:
                m = m.reshape(-1, 1)
            r = ev._index(at[0], m.shape[0], "elem", "row")
            c = ev._index(at[1], m.shape[1], "elem", "column")
            if v.ndim:
                raise EvalError("elem(M, i, j) = holds one value")
            m[r, c] = v
        elif m.ndim == 1 or 1 in m.shape:
            flat = m.reshape(-1)
            if v.ndim:
                raise EvalError("idx(v, i) = holds one value; for a matrix's row, idx(M, i) = a row vector")
            flat[ev._index(at[0], flat.size, "idx", "index")] = v
        else:
            r = ev._index(at[0], m.shape[0], "idx", "row")
            if v.size != m.shape[1]:
                raise EvalError(f"idx(M, i) = sets row i, which has {m.shape[1]} entries; this value has {v.size}")
            m[r] = v.reshape(-1)
        scope[key] = ev.Q(m, A.units)
        return key

    def steps(loop):
        try:
            lo, hi = bounds(loop)
        except Exception as e:
            raise StepError(loop.n, describe(e), where()) from None
        held = scope.get(loop.index)        # a name the index hides, back after the loop
        passes = 0
        for k in range(lo, hi + 1):
            scope[loop.index] = ev.Q(float(k))
            here.append(f"{loop.index} = {k}")
            passes += 1
            if not any(not isinstance(s, Loop) for s in loop.steps):
                tick(loop.n)
            for s in loop.steps:
                if isinstance(s, Loop):
                    steps(s)
                    continue
                tick(s.n)
                try:
                    if isinstance(s, Entry):
                        key = entry(s)
                    else:
                        key = ev.vkey(s.name)
                        scope[key] = ev.settle(ev.check_finite(ev.eval(s.expr, scope), s.expr))
                except Exception as e:
                    raise StepError(s.n, describe(e), where()) from None
                values[s.name] = scope[key]
            here.pop()
        if held is None:
            scope.pop(loop.index, None)
        else:
            scope[loop.index] = held
        return passes

    def where():
        return f" (at {', '.join(here)})" if here else ""

    return Run(values, steps(block.top))
