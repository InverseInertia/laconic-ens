# Output and Export

## Display commands

These change only how a result is printed. Values are stored as floats and the evaluator never rounds.

| Command | Effect |
|---|---|
| `!sigfigs n` | n significant figures (default 4), trailing zeros dropped: `2.5` |
| `!sigfigsbig n` | n significant figures with trailing zeros kept: `2.500` |
| `!decplace n` | n decimal places |
| `!short` / `!long` | final result only / full steps |

The last of `!sigfigs`, `!sigfigsbig` and `!decplace` wins. Plain notation is used between 1e-4 and 1e7, scientific notation outside. Typed-in numbers always show 12 significant figures. Matrices use the same formatter. `!sigfigs` and `!sigfigsbig` take 1 to 15, `!decplace` 0 to 15. See [Units](Units) for `!assume` and `!noassume`.

Each calculation line shows up to three stages: the symbolic form, the form with values substituted, and the result.

## Typeset and LaTeX views

The **Typeset / LaTeX** switch in the header chooses how results are shown. Typeset renders the math. LaTeX shows the source for each line in the export flavor (siunitx units), with a Copy button per line.

The wrapper menu next to the switch chooses how a calculation is wrapped:

| Wrapper | Result |
|---|---|
| Inline (default) | bare math, `a = b = c`, for pasting inside `$...$` or `\(...\)` |
| `\[ \]` | `\[ a = b = c \]` |
| `\begin{align*}` | an `align*` block with one row per stage |

Headings and comments become `\subsection*{}` and plain text, and commands such as `!clear` become a `%` comment. Choices are remembered in the browser. On a narrow or vertical screen the results sit above the editor.

## Files

| Action | Result |
|---|---|
| Save | the `.lens` source, with needed global unit definitions appended (see [Units](Units)) |
| Export LaTeX | a complete `.tex` document with `align*` blocks, `\DeclareSIUnit` lines for custom units, and `pgfplots` when a sheet has plots |
| Plot SVG / PNG | the picture exactly as drawn (see [Plots](Plots)) |
| `lens file.lens --tex out.tex` | the same `.tex` from the command line |

The export needs siunitx v3 or newer for `\qty` and `\unit`.
