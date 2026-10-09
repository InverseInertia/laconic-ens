# LENS: Laconic Engineering Notebook System

Laconic (LENS for short) is a units-aware worksheet on top of Pint. Type one expression per
line, see typeset results update as you edit, and copy LaTeX snippets or export a document.

    pip install -e .[dev]
    lens --serve --app                # web UI in a Chromium app window
    lens --serve --open               # or in your default browser
    lens examples/beam.lens           # print results in the terminal
    lens examples/beam.lens --tex beam.tex

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
    ~g = 9.81'm / 's^2             global variable (see below)
    !clear                         remove all non-global variables

Functions: sqrt abs sin cos tan asin acos atan exp ln log10 det inv transpose norm solve identity.
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

## Global variables and commands

A name that starts with `~` is global: `~g = 9.81'm / 's^2`, used as `~g`. `!clear` on its own
line removes every variable above it that is not global; user functions are kept. Evaluation is
top to bottom, so a global is available only below its definition. Using a variable that was
cleared says so: `'m' was removed by !clear`.

## Output view

The Typeset / LaTeX switch in the header chooses how results are shown. Typeset renders the
math. LaTeX shows the source for each line in the export flavour (siunitx units), with a Copy
button per line. The wrapper menu next to the switch chooses how a calculation is wrapped:

| Wrapper | Result |
| --- | --- |
| Inline (default) | bare math, `a = b = c`, for pasting inside `$...$` or `\(...\)` |
| `\[ \]` | `\[ a = b = c \]` |
| `\begin{align*}` | an `align*` block with one row per stage |

Headings and comments appear as `\subsection*{}` and plain text, and `!clear` as a `%` comment.
The Export LaTeX button always writes a complete document with `align*` blocks. Choices are
remembered in the browser. On a narrow or vertical screen the results sit above the editor.

## Math keys

These edit the source text. They are off on comment lines and can be switched off with the
Math keys box. The Keys button lists them in the app.

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

Division is typed with the fraction key: `a`, `/`, then the denominator.

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
    laconic/sheet.py         runs a worksheet line by line, including commands
    laconic/server.py        FastAPI app
    laconic/static/          index.html (UI), editing.js (math keys, pure functions)

## Tests

    python -m pytest -q           # Python, plus the Node suite if node is installed
    node tests/test_editing.js    # the math keys on their own

## Standalone builds

`pip install pyinstaller && pyinstaller packaging/lens.spec` produces a single `dist/lens` (`lens.exe` on Windows) that needs no Python install. PyInstaller does not cross-compile, so build on each target OS. Double-click it to start the UI in an app window, and it quits a few seconds after the window is closed; pass arguments to use the CLI (which keeps running until you stop it). The `build` GitHub Actions workflow builds both, smoke-tests them, and attaches them to a release when you push a `v*` tag.

## Not built yet

Symbolic math, plotting, solve blocks, dark mode,
long-equation line breaking inside a single stage, and globals that are usable above their
definition.
