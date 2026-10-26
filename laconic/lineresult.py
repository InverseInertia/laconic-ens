"""One line's result: what running a sheet hands to everything that shows it or acts on it.

Every result answers one small interface, whatever its kind:

    r.n, r.end, r.lines, r.owns(n)   the lines it owns: its own line, or a block header through
                                     the block's last line
    r.kind, r.source                 the line kind (or "error") and the line as typed
    r.text, r.latex, r.error,        its display parts, each empty when the line has none
    r.warning, r.stale
    r.block                          its block handle: the sheettext Block a header starts, else None
    r.symbols                        its part of the symbol table (see symbols.py)

What only one kind has is its payload, behind `r.plot` (PlotPayload) or `r.solver`
(SolverPayload); both are None on every other line, a block header that failed included.

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
    block: object = None    # a block header: the sheettext Block it starts, drawn or failed
    payload: object = None  # PlotPayload or SolverPayload
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
    def latex(self):
        parts = [p for p in ([self.lhs] if self.lhs else []) + self.stages if p]
        return " = ".join(parts)

    def to_json(self):
        row = {"n": self.n, "end": self.end, "kind": self.kind, "source": self.source,
               "text": self.text, "latex": self.latex, "error": self.error, "warning": self.warning,
               "stale": self.stale, "symbols": self.symbols}
        if self.plot:
            row["plot"] = self.plot.to_json()
        if self.solver:
            row["solver"] = self.solver.to_json()
        return row
