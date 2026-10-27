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

The **Typeset / LaTeX** switch in the header chooses how results are shown. Typeset renders the math, with global variables colored and underlined unless **Mark globals** is off (see [Worksheet Syntax](Worksheet-Syntax#global-variables)). A calculation too wide for the results pane is fitted to it as in the PDF export: a little too wide is shrunk, much too wide is wrapped one stage per row (and after `+` and `=` within a stage), and it is fitted again when the pane is resized. LaTeX shows the source for each line in the export flavor (siunitx units), with a Copy button per line.

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
| Export → LaTeX document | a complete `.tex` document with `align*` blocks, `\DeclareSIUnit` lines for custom units and for built-in units siunitx lacks (`ft`, `psi`, `g0`), and `pgfplots` when a sheet has plots |
| Export → Markdown note | a `.md` note for Obsidian: headings stay headings, comments become plain text, each calculation becomes a `$$` block (one row per stage, aligned at the equals signs), plots are embedded as SVG images and errors as callouts. Commands such as `!clear` and plot or solver options are left out |
| Export → PDF | a plain PDF of the results, broken into pages: headings, comments, each calculation with its line number, plots and errors, in one column. A calculation never splits across pages and a heading stays with what follows it. A calculation a little too wide for the page is shrunk; one much too wide is wrapped after `+` and `=`, the same way as in the results pane. It is a quick, readable printout, not a typeset document; use the LaTeX export for that |
| Plot SVG / PNG | the picture exactly as drawn (see [Plots](Plots)) |
| `lens file.lens --tex out.tex` | the same `.tex` from the command line |
| `lens file.lens --md out.md` | the same Markdown note from the command line |
| `lens file.lens --pdf out.pdf` | the same PDF from the command line |

The LaTeX export needs siunitx v3 or newer for `\qty`, `\unit` and, for complex values, `\complexqty`. The Markdown export uses the live view's math (`\mathrm{kN}`), which Obsidian's MathJax renders without extra packages.

The PDF is printed by Chrome, Chromium or Edge running headless, found on `PATH` (and in the usual install folders on Windows). Set `LENS_CHROMIUM` to a browser's path to pick one. Without one, **Export → PDF** in the app opens the printable page in a new tab with the browser's print dialog, where **Save as PDF** gives the same document; the command line stops with an error.
