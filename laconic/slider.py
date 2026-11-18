"""`!slider`: a variable set with a slider in the results, written as it is in the sheet.

    !slider x = 2'm               the header assigns the value, as `x = 2'm` does: a number, with units
      range: 0'm .. 10'm          required: the slider's ends, in units that agree with the value's
      step: 0.1'm                 optional: the value snaps to low + k*step; without it the slider is
                                  continuous (to its own resolution)
      scale: linear               linear (the default), log (needs a range above zero) or pow n: how
                                  the slider's travel maps onto the range (position^n for pow n)

The sheet text is the only record of the value. Dragging the slider asks the server for the number
at the new position (`value_at`, snapped to the step and rounded to as many digits as the slider can
tell apart) and writes it over the number in the header (`drag`, through the block editor), keeping
its units; the sheet then runs again from the text, like any other edit.

Like a regression it reads as a solver block (sheettext), so its option lines, Rename and the
editor's suggestions work the same; it is worked out every time the sheet runs and stores nothing.
A value outside the range keeps the value typed, with a warning, and the slider shows the nearest end."""
import math
import re
from dataclasses import dataclass, field

from .blockedit import BlockEditor
from .evaluator import EvalError
from .nodes import Neg, Num, is_literal
from .parser import ParseError, parse_expr
from .sheettext import NUMBER, definition

KEYS = ("range", "step", "scale")
KEY_NOTES = {"range": "the slider's ends, low .. high, in the value's units: 0'm .. 10'm",
             "step": "the value snaps to low + a whole number of steps; without one the slider is continuous",
             "scale": "linear (the default), log, or pow n: how the slider's travel maps onto the range"}
SCALES = {"linear": "even steps along the range",
          "log": "each stretch of the slider multiplies the value by the same factor; needs a range above zero",
          "pow": "pow n: the value goes as position^n, finer at the low end for n > 1"}
TICKS = 1000          # positions of a continuous slider
MAX_TICKS = 10000     # a stepped linear slider has one position per step, up to this many
USAGE = "!slider reads `!slider x = 2'm`: a name and a number, then an indented `range: low .. high` line"

# The number a header's value starts with, and its sign: the part a drag rewrites.
_NUMBER_RE = re.compile(rf"^(-?)[ \t]*({NUMBER})")
_HEADER_RE = re.compile(r"^([ \t]*!slider[ \t]+[^=]*?=[ \t]*)(.*?)[ \t]*$")


class SliderError(Exception):
    pass


@dataclass
class SliderBlock:
    line: int
    end: int
    name: str = ""
    body: str = ""           # the value as typed: `2'm`
    value: object = None     # its node
    low: object = None       # the range's nodes
    high: object = None
    range_line: int = None
    step: object = None
    step_line: int = None
    scale: str = "linear"
    power: float = 1.0
    errors: dict = field(default_factory=dict)      # option line number -> message
    problem: str = ""

    def nodes(self):
        return [n for n in (self.value, self.low, self.high, self.step) if n is not None]

    def option_nodes(self):
        return [n for n in (self.low, self.high, self.step) if n is not None]


def parse_block(handle):
    """The `!slider` block `handle` (a sheettext.Block), as regression.parse_block reads its own."""
    b = SliderBlock(handle.header, handle.end)
    d = definition(handle.args.strip()) if handle.args else None
    if d is None or d.kind != "assign":
        b.problem = USAGE
        return b
    b.name, b.body = d.name, d.body.strip()
    try:
        b.value = parse_expr(b.body)
    except ParseError as e:
        b.problem = str(e)
        return b
    sign = _NUMBER_RE.match(b.body)
    bare = isinstance(b.value, Num) or (isinstance(b.value, Neg) and isinstance(b.value.operand, Num))
    if not (is_literal(b.value) or bare) or not sign or sign.group(2)[-1:] in ("i", "j"):
        b.problem = f"!slider sets a number, with its units if it has any: `!slider {b.name} = 2'm`, not {b.body}"
        return b
    for line in handle.members:
        n, o = line.n, line.option
        if line.result is None and line.text.strip().startswith("#"):
            continue
        try:
            if line.result is not None:
                raise EvalError("!slider stores no result; remove this line")
            if not o:
                raise EvalError("Option lines read `key: value`")
            if o.key not in KEYS:
                raise EvalError(f"Unknown option '{o.key}'. Under !slider: " + ", ".join(KEYS))
            if o.arg:
                raise EvalError(f"{o.key} does not take a name before the colon")
            if not o.value:
                raise EvalError(f"{o.key} needs a value")
            if o.key == "range":
                if b.range_line is not None:
                    raise EvalError("range is given twice")
                parts = o.value.split("..")
                if len(parts) != 2 or not all(p.strip() for p in parts):
                    raise EvalError("range reads `low .. high`: 0'm .. 10'm")
                b.low, b.high = parse_expr(parts[0].strip()), parse_expr(parts[1].strip())
                b.range_line = n
            elif o.key == "step":
                if b.step_line is not None:
                    raise EvalError("step is given twice")
                b.step, b.step_line = parse_expr(o.value), n
            else:
                words = o.value.split()
                if words[0] not in SCALES or (words[0] == "pow") != (len(words) == 2) or len(words) > 2:
                    raise EvalError("scale is linear, log or pow n (such as pow 2)")
                if words[0] == "pow":
                    try:
                        p = float(words[1])
                    except ValueError:
                        p = -1
                    if not (p > 0 and math.isfinite(p)):
                        raise EvalError("pow takes a number above zero: `scale: pow 2`")
                    b.power = p
                b.scale = words[0]
        except (EvalError, ParseError) as e:
            b.errors[n] = str(e)
    if b.errors:
        count = len(b.errors)
        b.problem = f"{count} option line{'s' * (count != 1)} below need{'s' * (count == 1)} fixing"
    elif b.range_line is None:
        b.problem = f"!slider needs a `range:` line under it: `range: 0 .. 10`, in the units of {b.name}"
    return b


@dataclass
class Setting:
    """A slider's numbers, all in the units of the value as typed (`unit`), and its scale."""
    value: float
    low: float
    high: float
    step: float = None
    scale: str = "linear"
    power: float = 1.0

    @property
    def ticks(self):
        """How many positions the slider has: one per step for a stepped linear slider (when that
        is not too many), else TICKS."""
        if self.step and self.scale == "linear":
            n = (self.high - self.low) / self.step
            if n <= MAX_TICKS and abs(n - round(n)) < 1e-9 * max(1, n):
                return max(1, round(n))
        return TICKS

    def to_value(self, p):
        """The value at position p, 0 at the low end and 1 at the high end, before snapping."""
        p = min(max(p, 0.0), 1.0)
        lo, hi = self.low, self.high
        if self.scale == "log":
            return lo * (hi / lo) ** p
        if self.scale == "pow":
            return lo + (hi - lo) * p ** self.power
        return lo + (hi - lo) * p

    def position(self, v):
        """Where the slider stands for value v, from 0 to 1; a value outside the range stands at the
        nearer end."""
        lo, hi = self.low, self.high
        if v <= lo:
            return 0.0
        if v >= hi:
            return 1.0
        if self.scale == "log":
            return math.log(v / lo) / math.log(hi / lo)
        f = (v - lo) / (hi - lo)
        return f ** (1 / self.power) if self.scale == "pow" else f

    def value_at(self, p):
        """The number the header takes at position p (from 0 to 1): snapped to the step and rounded
        to the digits the slider can tell apart there, as text."""
        p = min(max(p, 0.0), 1.0)
        v = self.to_value(p)
        if self.step:   # whole steps from the low end, up to the last one inside the range
            last = math.floor((self.high - self.low) / self.step + 1e-9)
            k = min(max(round((v - self.low) / self.step), 0), last)
            return number(self.low + k * self.step, _resolution(self.step, self.low))
        d = 1 / self.ticks
        res = abs(self.to_value(min(p + d, 1)) - self.to_value(max(p - d, 0))) / 2
        return number(v, res or abs(self.high - self.low) / self.ticks)


def _resolution(step, low):
    """The finest digit a stepped value needs: that of the step, or of the low end it counts from."""
    def finest(x):
        if x == 0:
            return math.inf
        s = f"{abs(x):.12g}"
        if "e" in s:
            mant, exp = s.split("e")
            places = len(mant.split(".")[1]) if "." in mant else 0
            return 10.0 ** (int(exp) - places)
        return 10.0 ** -(len(s.split(".")[1]) if "." in s else 0)
    return min(finest(step), finest(low))


def number(v, res):
    """`v` written to the digit of `res` (the smallest difference that matters), without trailing
    zeros: number(2.34567, 0.01) is "2.35"."""
    if not math.isfinite(v):
        return f"{v}"
    places = -math.floor(math.log10(res)) if res > 0 else 12
    places = min(max(places, -300), 15)
    v = round(v, places)
    if v == 0:
        return "0"
    if abs(v) >= 1e9 or abs(v) < 1e-5:
        digits = max(1, math.floor(math.log10(abs(v))) + places + 1)
        return f"{v:.{min(digits, 15)}g}"
    s = f"{v:.{max(places, 0)}f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def setting(block, ev):
    """The block's Setting against the evaluator as the header finds it, and the value as a
    quantity. Raises SliderError with the line to blame: (line, message)."""
    q = ev.eval(block.value)
    mag = q.magnitude
    if hasattr(mag, "ndim") and mag.ndim > 0:
        raise SliderError(block.line, "!slider sets a single number, not a matrix")
    if isinstance(mag, complex):
        raise SliderError(block.line, "!slider sets a real number")
    unit = q.units

    def convert(node, line, what):
        try:
            v = ev.eval(node)
        except Exception as e:
            raise SliderError(line, e) from None
        if hasattr(v.magnitude, "ndim") and v.magnitude.ndim > 0:
            raise SliderError(line, f"The {what} is a single number")
        if v.dimensionless and v.magnitude == 0:   # 0 is 0 in any unit: `range: 0 .. 10'm`
            v = ev.Q(0, unit)
        if v.dimensionality != q.dimensionality:
            shown = f"{unit:~P}" or "no units"
            raise SliderError(line, f"The {what} must be in the units of {block.name} ({shown})")
        m = v.to(unit).magnitude
        if isinstance(m, complex) or not math.isfinite(m):
            raise SliderError(line, f"The {what} is a real number")
        return float(m)
    lo = convert(block.low, block.range_line, "range")
    hi = convert(block.high, block.range_line, "range")
    if not lo < hi:
        raise SliderError(block.range_line, "range goes from low to high: the first end is the lower")
    if block.scale == "log" and lo <= 0:
        raise SliderError(block.range_line, "A log scale needs a range above zero")
    step = None
    if block.step is not None:
        step = convert(block.step, block.step_line, "step")
        if step <= 0:
            raise SliderError(block.step_line, "step is above zero")
        if step > hi - lo:
            raise SliderError(block.step_line, "step is larger than the range")
    return Setting(float(mag), lo, hi, step, block.scale, block.power), q


def with_number(header, number_text):
    """The `!slider` header line `header` with `number_text` written over its value's number (and
    sign), keeping its units and everything else as typed; None when it has no number to replace."""
    m = _HEADER_RE.match(header)
    n = m and _NUMBER_RE.match(m.group(2))
    if not n:
        return None
    start = m.start(2)
    return header[:start] + number_text + header[start + n.end():]


def drag(text, line, payload, position):
    """The edits to `text` that stand the slider on `line` (its SliderPayload `payload`, as the sheet
    last read it) at `position`, from 0 to 1: the header's number rewritten, its units kept."""
    st = Setting(payload.value, payload.low, payload.high, payload.step, payload.scale, payload.power)
    ed = BlockEditor(text, line)
    head = with_number(ed.block.lines[0].text, st.value_at(position)) if ed.block else None
    if head is None:
        raise SliderError(line, f"Line {line} is not a !slider with a number to set")
    ed.header(head)
    return ed.edits()
