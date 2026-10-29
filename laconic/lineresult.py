"""One line's result: what running a sheet hands to everything that shows it or acts on it.

Every result answers one small interface, whatever its kind:

    r.n, r.end, r.lines, r.owns(n)   the lines it owns: its own line, or a block header through
                                     the block's last line
    r.kind, r.source                 the line kind (or "error") and the line as typed
    r.text, r.latex, r.error,        its display parts, each empty when the line has none
    r.warning, r.stale
    r.latex_rows                     `latex` broken one stage per row, for a narrow layout
    r.hidden                         below `!hide`: the line ran, but no row or export shows it
    r.block                          its block handle: the sheettext Block a header starts, else None
    r.symbols                        its part of the symbol table (see symbols.py)

What only one kind has is its payload, behind `r.plot` (PlotPayload), `r.solver`
(SolverPayload), `r.regression` (RegressionPayload) or `r.loop` (LoopPayload); each is None on
every other line, a block header that failed included.

`r.to_json()` is the row `/api/eval` sends. Its shape is pinned by tests/test_lineresult.py,
so a change to it is a deliberate one; static/rows.js is the page's reader of it."""
from dataclasses import asdict, dataclass, field

from .plotsvg import render_svg


@dataclass
class PlotPayload:
    """A plot that drew: the spec it was drawn from (see plotspec.py) and the picture."""
    spec: dict
    svg: str

    @property
    def axes(self):
        """Each axis's settings, as a pan or zoom needs them (see plotopts.apply_patch)."""
        return {"x": self.spec["x"], "y": self.spec["y"]}

    @property
    def inherited(self):
        """The text form of what each option would be without a line of its own."""
        return self.spec["inherited"]

    @property
    def moved(self):
        """A view set with the mouse (`xview:` or `yview:`) is in force."""
        return bool(self.spec["x"]["view"] or self.spec["y"]["view"])

    def image(self, uid):
        """The picture as a complete SVG file."""
        return render_svg(self.spec, uid=uid, standalone=True)

    def to_json(self):
        return {"svg": self.svg, "spec": self.spec, "moved": self.moved}


@dataclass
class SolverPayload:
    """A solver block as the sheet read it, without solving: the stored result checked against
    the hash of the block's current inputs (see sheet._run_solver)."""
    kind: str               # root, minimize or maximize
    unknowns: list
    hash: str               # of everything the block reads; a stored result fits only this hash
    status: str             # valid (the stored result fits), stale (it does not) or none (never run)
    tainted: bool           # reads a value from a solver above whose result is out of date
    autorun: bool
    method: str
    timeout: float
    values: list            # {name, lhs, rhs, latex} for each unknown, then the optimum
    summary: str = ""
    note: str = ""          # why a stored result could not be read
    record: dict = None     # the stored result, when there is one that reads

    @property
    def current(self):
        """Its values can be trusted: the stored result fits and nothing above is out of date."""
        return self.status == "valid" and not self.tainted

    def to_json(self):
        return asdict(self)


@dataclass
class RegressionPayload:
    """A `!regression` block that fitted (see sheet._run_regression): what it defines, and how well
    the polynomial fits. It is worked out every time the sheet runs, so it is never out of date
    by itself; the row is `stale` when its data reads an out-of-date solver result."""
    names: list             # the coefficient names, lowest power first (or one vector's name)
    degree: int             # None for a `model:`
    points: int
    r2: float
    model: str              # the fitted polynomial or model, typeset: y = a + b x + ...
    values: list            # {name, lhs, rhs, latex} for each coefficient, then R²

    def to_json(self):
        return {"names": self.names, "degree": self.degree, "points": self.points, "r2": self.r2}


@dataclass
class LoopPayload:
    """A `!loop` block that ran (see sheet._run_loop): the block typeset as steps, one per row, and
    what each name it assigned holds after the last pass. The page shows it as the row's math, so
    nothing of it goes into the row JSON."""
    code: list              # `&\textbf{for}\ i = 1, \ldots, 3`, then each step indented under its loop
    values: list            # {name, lhs, rhs, latex} for each name the block assigned
    passes: int             # of the top loop


@dataclass
class LineResult:
    n: int
    source: str
    kind: str               # a line kind from sheettext, or "error"
    lhs: str = ""           # a calculation: the left side and the stages of the right side
    stages: list = field(default_factory=list)
    text: str = ""          # the plain-text form
    error: str = ""
    warning: str = ""       # shown under the result: the line works but may not do what was meant
    stale: bool = False     # reads a value from a solver whose result is out of date
    hidden: bool = False    # below !hide: it ran, but the results pane and the exports leave it out
    block: object = None    # a block header: the sheettext Block it starts, drawn or failed
    payload: object = None  # PlotPayload, SolverPayload, RegressionPayload or LoopPayload
    symbols: dict = None    # this line's part of the symbol table

    @property
    def end(self):
        """Number of the last line this result owns."""
        return self.block.end if self.block else self.n

    @property
    def lines(self):
        return range(self.n, self.end + 1)

    def owns(self, line):
        return self.n <= line <= self.end

    @property
    def plot(self):
        return self.payload if isinstance(self.payload, PlotPayload) else None

    @property
    def solver(self):
        return self.payload if isinstance(self.payload, SolverPayload) else None

    @property
    def regression(self):
        return self.payload if isinstance(self.payload, RegressionPayload) else None

    @property
    def loop(self):
        return self.payload if isinstance(self.payload, LoopPayload) else None

    @property
    def latex(self):
        parts = [p for p in ([self.lhs] if self.lhs else []) + self.stages if p]
        return " = ".join(parts)

    @property
    def latex_rows(self):
        """`latex` one stage per row, as a layout too narrow for it wraps it: `lhs = first stage`,
        then `= next stage` and so on. Joined with spaces they are `latex` again."""
        parts = [p for p in ([self.lhs] if self.lhs else []) + self.stages if p]
        if self.lhs and len(parts) > 1:
            parts[:2] = [f"{parts[0]} = {parts[1]}"]
        return [p if i == 0 else f"= {p}" for i, p in enumerate(parts)]

    def to_json(self):
        row = {"n": self.n, "end": self.end, "kind": self.kind, "source": self.source,
               "text": self.text, "latex": self.latex, "latex_rows": self.latex_rows, "error": self.error, "warning": self.warning,
               "stale": self.stale, "hidden": self.hidden, "symbols": self.symbols}
        if self.plot:
            row["plot"] = self.plot.to_json()
        if self.solver:
            row["solver"] = self.solver.to_json()
        if self.regression:
            row["regression"] = self.regression.to_json()
        return row
