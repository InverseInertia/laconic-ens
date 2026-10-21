# LENS: Laconic Engineering Notebook System

Laconic (LENS for short) is a units-aware worksheet on top of Pint. Type one expression per
line, see typeset results update as you edit, and copy LaTeX snippets or export a document.

    pip install -e .[dev]
    lens --serve --app                # web UI in a Chromium app window
    lens --serve --open               # or in your default browser
    lens examples/beam.lens           # print results in the terminal
    lens examples/beam.lens --tex beam.tex
    lens examples/plots.lens --plots figures    # each plot as an SVG file

`python -m laconic` works too. Worksheets are plain text files, conventionally `.lens`.
The web page serves KaTeX 0.16.11 and IBM Plex fonts from `laconic/static/`, so it works offline.
The exported .tex needs siunitx v3 or newer.

## Syntax

    # comment                      ## section heading
    L = 4.5'm                      a unit starts with an apostrophe
    w = 12'kN / 'm                 every unit in a compound gets its own apostrophe
    M = w * L^2 / 8 -> 'kN * 'm    `->` converts units
    A = [2, -1; -1, 2]             matrix: commas within a row, semicolons between rows
    F = [10; 5] * 'kN              a unit on its own is 1 of that unit
    x = solve(A, b)                also inv, det, transpose, norm, identity
    A * B                          matrix product (scaling if one side is scalar)
    A .* B     A ./ B              elementwise
    f(x, y) = x^2 + y              user function
    T = 20'degC -> 'degF           offset units work
    σ_max = 3                      Greek letters and subscripts in names
    'smoot = 1.7018'm              define a unit (see Custom units)
    ~g = 9.81'm / 's^2             global variable (see below)
    !clear                         remove all non-global variables
    !clearf                        remove all non-global functions
    !noassume / !assume            keep typed units / back to SI results
    !trigdeg / !trigrad            bare numbers in trig functions are degrees / radians (default)
    x` = 2   F! = 5   a@ = 1       dot, arrow and hat over a variable
    !plot M(x), x = 0'm .. L       plot a function (see Plots)

Rename a variable or function everywhere with the Rename button or F2 (the caret's name is filled in).
Units, comments and commands are untouched, and a name already in use is refused.

Functions: sqrt abs floor ceil heaviside (aliases step, heav; 0 below zero, 1 at zero and above) sin cos tan asin acos atan exp ln log10 det inv transpose norm solve identity.
Constants: pi, e.

A unit is `'` followed by a Pint unit name (`'kN`, `'mm`, `'degC`, `'°C`, `'ohm`). A bare name is
always a variable, so `m` can be a mass while `'m` is the metre. Only a number followed by units
may be written without `*`, so `3 x` is an error and `3*x` is right.

## Default SI display

A computed result is shown in the simplest coherent SI unit, with a familiar name when there is
one: kg·m/s² becomes N, kg·m²/s² becomes J, and so on. These are the named units:

    N  J  W  Pa  Hz  C  V  Ω  F  H  S  Wb  T
    N/m  m/N  N·m²  Pa·s  W/m²  W/m³  W/(m·K)  J/K  J/(kg·K)  V/m  F/m  H/m

Anything else stays in reduced base units (`m²/s²`, `kg/m³`). Where one dimension has several
common names, the most common wins:

- energy and torque are both kg·m²/s², shown as **J** (use `-> 'N * 'm` to keep a torque)
- 1/s is shown as **Hz**
- kg/s² is shown as **N/m**, and s²/kg as **m/N**

Not reduced: an explicit `->` conversion, and a line that is only one typed-in quantity
(`E = 200'GPa` stays `200 GPa`). `10'kN / 5'mm` has two numbers, so it is a calculation and
comes out as `2000000 N/m`. Angles keep their radians (`asin(0.5)` gives `0.5236 rad`), degF
becomes degC, and degC stays.

## Accents over variables

A mark typed right after a name puts an accent over it in the typeset view and the export:

| Mark | Accent | Example | LaTeX |
|---|---|---|---|
| backtick | dot (two backticks: double dot) | ``v` `` | `\dot{v}` |
| `!` | arrow | `F!` | `\vec{F}` |
| `@` | hat | `a@` | `\hat{a}` |

Marks can be combined (``v`! `` is `\vec{\dot{v}}`). With a subscript the mark goes at the end and sits
over the base letter: `F_x!` is `\vec{F}_{x}`. `x`, `x!` and `x@` are three different variables.

## Global variables and commands

A name that starts with `~` is global: `~g = 9.81'm / 's^2`, used as `~g`. `!clear` on its own
line removes every variable above it that is not global; user functions are kept. `!clearf` does
the same for user functions, and a function whose name starts with `~` (`~f(x) = x^2`) is global
and survives it. Evaluation is
top to bottom, so a global is available only below its definition. Using a variable that was
cleared says so: `'m' was removed by !clear`.

`!noassume` keeps computed results in the units that come out of the arithmetic instead of
reducing them to SI, for every line below it: `10'kN * 2'm` shows `20 kN⋅m` rather than
`20000 J`. An explicit `->` still converts. `!assume` restores the default.

## Custom units

A line that starts with a unit and an equals sign defines that unit for the sheet:

    'smoot = 1.7018'm
    'ksmoot = 1000'smoot           may build on earlier units
    d = 3'smoot -> 'm              5.105 m

The right-hand side is numbers and units only (no variables), and must be a positive size. A
definition applies to the whole sheet, above or below the line, so a block of definitions can sit
at the end. Names use ASCII letters, digits and `_`. A name that already means something is an
error, and the message says what it means: `'m` is the metre, and `'dsmoot` would read as
deci-smoot. Offset units such as `'degC` cannot be used in a definition. `!clear` does not remove
units.

**Global units** are defined once per instance under the **Units** button and are available in
every sheet, in the web UI and on the command line. They live in the settings file (below).

**Portability.** Save and Export carry the definitions a sheet depends on, so a copy opens correctly
on another instance:

- Save (`.lens`) appends the global units the sheet uses, and the units those are defined in terms of,
  inside a marked block at the end: `#@ unit definitions ...` / `'smoot = 1.7018'm` / `#@ end ...`.
  Units the sheet already defines itself are not repeated, so saving a sheet twice does not stack
  blocks.
- Export (`.tex`) writes a `\DeclareSIUnit` line per custom unit in the preamble, so siunitx can
  typeset them. Names that are not letters only get a letters-only macro (`psi_g` becomes `\psiUnderg`).
- Opening a sheet on an instance that has its own global of the same name is fine if the sizes agree.
  If they differ, the definition line shows an error naming the instance's value; rename the unit in
  the sheet or change the global.

## Plots

A `!plot` line draws one or more functions of one variable over a range. It is a command, so `plot` stays
available as an ordinary name. Indented `key: value` lines under it set the details:

    !plot M(x), V(x), x = 0'm .. L
      title: Bending moment and shear
      ylabel: M (kN·m)
      xlim: 0'm .. 3.2'm
      color 2: red
      note: "max" at (L / 2, M(L / 2))

The expressions can use any variable and function above them. They are sampled point by point
(`samples`, default 400), so units are checked at every point and a result in kN·m is shown in
kN·m. Several expressions share one y axis and must have compatible units; give them separate
plots otherwise. Where an expression is undefined (`1/x` at 0, `sqrt` of a negative) the line
breaks there, and a line that jumps from beyond one limit to beyond the other (a pole) is not
joined across the picture. `gaps: error` turns an undefined point into an error instead.

| Option | Meaning (default in brackets) |
|---|---|
| `title`, `xlabel`, `ylabel` | text; the axis labels are `name [unit]` unless set. `x_max` or `x_{max}` is a subscript. An empty value removes the label |
| `xlim`, `ylim` | the view you choose: `low .. high`, with units or plain numbers in the axis's display unit. Either end can be `auto` (automatic, with 5% headroom) |
| `xview`, `yview` | the same form, but written by the mouse (see Mouse). It sits over `xlim`/`ylim`, and removing it goes back to them |
| `xunit`, `yunit` | the unit the axis is shown in, e.g. `'kN * 'm` (the typed range's unit for x, the simplest SI unit for y) |
| `xscale`, `yscale` | `lin` or `log` (`lin`) |
| `xstep`, `ystep` | tick spacing in the display unit (automatic) |
| `grid` | `on` or `off` (`on`) |
| `legend` | `auto`, `off`, `top right`, `top left`, `bottom right`, `bottom left` (`auto`: top right when there are several series) |
| `size` | `width x height` in pixels (`520 x 320`) |
| `samples` | 10 to 5000 (`400`) |
| `gaps` | `break` or `error` (`break`) |
| `color`, `width`, `dash`, `marker`, `label` | per series. `color 2: red` is series 2; with no number the setting applies to every series. Colors are `#rrggbb` or a name (`red`, `blue`, `green`, `orange`, `purple`, `sky`, `gray`, `black`, `navy`). `dash` is `solid`, `dashed` or `dotted`; `marker` is `none`, `circle` or `square` |
| `note` | `"text" at (x, y)`: a dot and a label at a point, in data coordinates. Repeat the line for more |

**Defaults.** Three layers, each overriding the one before: the built-in values above, then a
`!plotspec key: value` line, which applies to every plot below it (`!plotspec grid: off`,
`!plotspec size: 560 x 300`; `!plotspec reset` clears them), then the option lines under a plot.

**The view.** An axis range has three layers too: `xview` (what the mouse set), over `xlim` (what you wrote),
over automatic limits computed from the data. The default view is therefore whatever the text says with no
`xview` or `yview` line, and nothing else is stored anywhere. Reset view removes only those lines, so it
goes back to your `xlim`/`ylim` if you wrote any, and the Reset view button appears only while the mouse has
a view to remove.

**Mouse.** The picture is drawn on the server from the worksheet text, and the mouse only edits that
text. Drag in a plot to pan; Ctrl + wheel (or a trackpad pinch) zooms about the pointer; a plain wheel
still scrolls the results. Dragging or zooming on the strip under or beside an axis moves just that
axis. Double-click resets (a strip resets only its axis), and so does the Reset view button. Hovering
reads off the nearest point. When a gesture ends, the new range is written under the plot as
`xview:` and `yview:` lines, only for what moved and rounded to the precision on screen, and Ctrl+Z undoes
it like any other edit. Deleting those lines by hand, or writing different ones, works the same way:
the worksheet alone redraws the picture. The page doesn't redraw the ticks until the gesture ends, so
the grid is hidden while you drag.

**The frame and the numbers on the axes.** The margins hold room for six characters of tick label, so
while the numbers on an axis fit in six (`-0.4`, `100`, `5e-11`, `-1e-10`, `-50000`) the plot area's edges
are fixed by the size, the title and whether there are axis labels, however a pan or zoom changes the
numbers. The pointer stays on the axis strip you are scrolling. Each axis uses one notation: fixed point
while every label fits in six characters, else scientific (`2e-6`, `-1.5e-6`) with as few digits as tell the
ticks apart. A label that needs more than six characters makes the margin grow to fit it (a range like
`1.5e-6 .. 2.5e-6` shows `-1.5e-6`, seven), and the frame moves with it. So the pointer can lose the strip
when a zoom takes the labels back under six characters while the pointer is parked in the part of the strip
that only existed to fit the wide ones. Everyday engineering ranges (1e-3 to 1e3 in position) fit in six
characters about nine times in ten. For a range that is tiny next to its position, like `1e9 .. 1000000005`,
telling the ticks apart takes 13 characters and the margin grows to match; an axis offset note such as `+1e9`
would avoid that and is not built.

When a zoom narrows the view, the curve is sampled over the visible window again, so it stays smooth.
Editing the text of a title, label or note is done in the editor; the math keys are off on those lines.

**Exporting.** Each plot has three ways out:

- **SVG** and **PNG** buttons under the plot save the picture exactly as shown, with the font
  embedded (PNG at three times the size). `lens file.lens --plots DIR` writes the same SVGs without a browser.
- **LaTeX.** Export LaTeX (and the LaTeX view) writes the plot as a `pgfplots` figure built from the
  same data, limits, scales, labels, colors and dash styles, with units through siunitx. TeX draws
  it with the document's fonts and its own tick placement, so it is a close match and not the same
  picture; use the SVG when you need the exact one. The exported document loads `pgfplots` when it
  has a plot.

Save keeps the units a plot uses with the sheet, like any other line. Options are checked as they are
read: a bad one is reported on its own line and the plot is drawn without it (a bad `xview` falls back to
`xlim`, then to automatic).

## Settings on this machine

The Greek table (Ctrl+G) and the global units are stored by the server in a JSON file, so they are
the same in every browser and for `lens file.lens`:

| System | Location |
|---|---|
| Linux | `$XDG_CONFIG_HOME/laconic/settings.json`, or `~/.config/laconic/settings.json` |
| macOS | `~/Library/Application Support/laconic/settings.json` |
| Windows | `%APPDATA%\laconic\settings.json` |

`LENS_CONFIG_DIR` overrides the directory. A Greek table saved in the browser by an earlier build is
copied to the server the first time the page loads. The Units dialog stores nothing unless every
definition is valid.

## Output view

The Typeset / LaTeX switch in the header chooses how results are shown. Typeset renders the
math. LaTeX shows the source for each line in the export flavour (siunitx units), with a Copy
button per line. The wrapper menu next to the switch chooses how a calculation is wrapped:

| Wrapper | Result |
| --- | --- |
| Inline (default) | bare math, `a = b = c`, for pasting inside `$...$` or `\(...\)` |
| `\[ \]` | `\[ a = b = c \]` |
| `\begin{align*}` | an `align*` block with one row per stage |

Headings and comments appear as `\subsection*{}` and plain text, and commands such as `!clear` as a `%` comment.
The Export LaTeX button always writes a complete document with `align*` blocks. Choices are
remembered in the browser. On a narrow or vertical screen the results sit above the editor.

## Math keys

These edit the source text. They are off on comment lines and can be switched off with the
Math keys box. The Keys button lists them in the app. They are also off on the text lines under a plot (title, labels, notes).

| Key | Effect |
| --- | --- |
| `/` | Fraction. Left term is the numerator, a term on the right (if any) the denominator, otherwise `a / ()` with the caret inside. After `A.` it gives `A ./ ` |
| `\` | Radical, `sqrt()`, or wraps the selection |
| `.` | Subscript after a name (`M.max` gives `M_max`). Decimal point after a number or unit |
| `^` | Exponent slot, `x^()` |
| `→` or `)` | Leave a slot. One simple term loses its parentheses: `x^(2)` becomes `x^2` |
| `= + - * -> .* ./` | Spaces are added around them. A sign (`-3`, `x^-1`) and `1e-3` stay tight |
| space | A second space in a row is ignored (indentation is left alone) |
| `,` `;` | A space is added after them. In an array `,` separates columns and `;` rows |
| `Backspace` | In an empty slot, removes the slot with its `^`, `/` or `sqrt`. After `, `, `; ` or a spaced operator, removes it with its spaces in one press |
| `Ctrl+M` | Array `[]`, or wraps the selection |
| `Ctrl+T` or `Alt+T` | Transpose the term on the left or the selection. Press again to undo |
| `Ctrl+G` | Greek letter for the character before the caret. Press again to revert |
| `Ctrl+/`, `Ctrl+\` | A literal `/` (spaced) or `\`, with no fraction or radical slot |
| `Enter` | With only closing brackets left on the line, finishes the line |
| `Ctrl+Space` | Opens suggestions by hand. With text highlighted: pick a function to wrap it in |
| `Alt+Up`, `Alt+Down` | Grow the selection by one term-aware step, or step back |

Division is typed with the fraction key: `a`, `/`, then the denominator.

## Highlighted text

With text highlighted, `/` `^` `\` `(` `[` `|` and Ctrl+M apply to the highlighted region instead of
replacing it: `/` makes it the numerator, `^` the base of a power, `\` a square root, `(` and `[`
wrap it in brackets, `|` takes `abs()`, and Ctrl+T transposes it. Brackets are added only when the
region is more than one term.

The edit always applies to **whole terms**, however the text was highlighted. A term is a name, a
number with its unit, a call, or a bracketed group, together with its exponents:

| Highlighted | Treated as |
|---|---|
| `2` in `12'kN` | `12'kN` |
| `x` in `x^2`, or the `2` | `x^2` |
| `sin` in `sin(a)` | `sin(a)` |
| `(a)` in `sin(a)` | `sin(a)` |
| `b)` in `f(a, b)` | `f(a, b)` |

So `^` on `1` inside `12'kN` gives `(12'kN)^()`, with the power over the number as well as the unit.
Highlighting spaces only is an ordinary replace, and a highlight across lines or with unmatched
brackets is left alone with a message rather than overwritten.

**Selecting by term:** double-click selects the whole term under the pointer. `Alt+Up` grows the
selection one step at a time: term, product (`w * L^2 / 8`), sum (`... + c`), bracket contents,
bracket with its function name, and outwards to the whole line, with `=`, `->`, `,` and `;` as the
boundaries between steps. `Alt+Down` steps back. Highlighting with the mouse or Shift+arrows is never
changed; the widening happens when you press a key.

With text highlighted, `Ctrl+Space` offers functions to wrap it in. Type to filter, `Enter` applies:
highlight `a+b`, press Ctrl+Space, type `sin`, and `Enter` gives `sin(a+b)`.

## Suggestions

Suggestions appear as you type, from the **Suggest** box in the header:

| After | Offers |
|---|---|
| `'` | units: your own and the instance's first, then common units (`kN`, `mm`, `GPa`) and everything Pint knows, matched by symbol or full name (`newt` finds `N`) |
| `!` | commands |
| two letters of a name | variables defined above (with their current value), your functions, built-in functions, `pi` and `e` |

`Tab` accepts, `Up`/`Down` choose, `Esc` closes. `Enter` accepts only after you have moved with the arrows,
so it still ends the line when you just kept typing. A function is inserted with brackets and the caret
inside, unless the word is already followed by `(`. The name on the left of `=` (a new variable, a
unit being defined, function parameters) and comment lines get no suggestions. `Ctrl+Space` opens the
list by hand, even for a single letter.

The Greek table behind Ctrl+G is editable under the Greek button and is stored in the browser.
Mathcad-style defaults: a→α, b→β, g→γ, d→δ, e→ε, z→ζ, h→η, q→θ, i→ι, k→κ, l→λ, m→μ, n→ν,
x→ξ, o→ο, p→π, r→ρ, s→σ, t→τ, u→υ, f→φ, c→χ, y→ψ, w→ω, and G D Q L X P S F Y W for the capitals
Γ Δ Θ Λ Ξ Π Σ Φ Ψ Ω.

Browsers reserve Ctrl+T (new tab) and Ctrl+N, so in a normal tab use Alt+T. `--app` opens a
tab-less Chromium window, which may let Ctrl+T through; that has not been tested.

## Layout

    laconic/parser.py        Lark grammar -> AST (nodes.py)
    laconic/evaluator.py     AST -> Pint quantities
    laconic/si.py            default SI display units
    laconic/latex.py         AST -> LaTeX (symbolic, substituted, result), snippets, .tex document
    laconic/plotopts.py      plot option lines: parsing, defaults, and the writer that edits them in the source
    laconic/plotspec.py      samples a plot and resolves its options into one plain dict (the spec)
    laconic/plotsvg.py       spec -> SVG, the only renderer of the picture (UI, exports and CLI use it)
    laconic/plotpgf.py       spec -> pgfplots figure for the .tex export
    laconic/sheet.py         runs a worksheet line by line, including commands and unit definitions
    laconic/settings.py      per-user settings file: Greek table, global units
    laconic/vocab.py         what the editor suggests: units, functions, constants, commands
    laconic/server.py        FastAPI app
    laconic/static/          index.html (UI), editing.js (math keys, selections), autocomplete.js
                             (what to suggest; both are pure functions), plotview.js (mouse on plots)
    laconic/static/vendor/   KaTeX, and d3-zoom with d3-scale and their dependencies (see vendor/d3/README.md)

## Tests

    python -m pytest -q           # Python, plus the Node suite if node is installed
    node tests/test_editing.js    # the math keys and selections on their own
    node tests/test_autocomplete.js

`tests/test_ui.py` and `tests/test_plots_ui.py` drive the real page in Chromium (the second with real pointer
events on plots) and are skipped unless `playwright` is installed
(`pip install playwright`; set `CHROMIUM_PATH` to use a browser you already have). One test compiles an
exported document with plots and is skipped unless `pdflatex` (with pgfplots and siunitx v3) is installed.

## Standalone builds

`pip install pyinstaller && pyinstaller packaging/lens.spec` produces a single `dist/lens` (`lens.exe` on Windows) that needs no Python install. PyInstaller does not cross-compile, so build on each target OS. Double-click it to start the UI in an app window, and it quits a few seconds after the window is closed; pass arguments to use the CLI (which keeps running until you stop it). The `build` GitHub Actions workflow builds both, smoke-tests them, and attaches them to a release when you push a `v*` tag.

## Not built yet

Symbolic math, solve blocks, dark mode,
long-equation line breaking inside a single stage, and globals that are usable above their
definition (units are, see Custom units). Custom units cannot define a new base dimension or an
offset scale,. Selecting with
the mouse is not snapped to terms; use double-click or `Alt+Up`.

Plots are functions of one variable only. Not built: plotting arrays or measured data, box-zoom, dragging
legends, notes and labels with the mouse, an offset note for ranges far narrower than their position, minor grid lines, per-instance plot styles (colors and fonts for
every sheet), and PDF output of the picture (use SVG or PNG; a `.tex` export that includes the picture
as a file instead of a pgfplots figure would need a zip).
