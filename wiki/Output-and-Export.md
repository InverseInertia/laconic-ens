# Output and Export

## Display commands

These change only how a result is printed. Values are stored as floats and the evaluator never rounds.

| Command | Effect |
|---|---|
| `!sigfigs n` | n significant figures (default 4), trailing zeros dropped: `2.5` |
| `!sigfigsbig n` | n significant figures with trailing zeros kept: `2.500` |
| `!decplace n` | n decimal places |
| `!short` / `!long` | final result only / full steps |
| `!adnauseum` | every intermediate result and unit cancellation, until `!long` or `!short` |

The last of `!sigfigs`, `!sigfigsbig` and `!decplace` wins. Plain notation is used between 1e-4 and 1e7, scientific notation outside. Typed-in numbers always show 12 significant figures, so a line that is only a typed-in number or quantity (`L = 12345.678'm`) shows it as typed; the setting rounds what the sheet computes. Matrices use the same formatter. `!sigfigs` and `!sigfigsbig` take 1 to 15, `!decplace` 0 to 15. See [Units](Units) for `!assume` and `!noassume`.

Each calculation line shows up to three stages: the symbolic form, the form with values substituted, and the result.

### All the working

Below `!adnauseum`, a line shows every step between the substituted form and the result. The expression is worked out one level at a time, innermost first, each stage replacing the operations whose operands are already numbers with what they give. Before a product or quotient whose units cancel, a stage shows the numbers and the units apart with the cancelled units struck through, and when the result is shown in other units than the arithmetic gave, the arithmetic's units are written out in SI base units and cancelled down:

```
F = 10'kN
L = 3'm
!adnauseum
W = F*L       W = F·L = 10 kN·3 m = 30 kN·m = 30000 (kg·m/s²)·m = 30000 kg·m²/s² = 30000 J
v = 5'm/'s
d = v * 2's   d = v·2 s = 5 m/s·2 s = 5·2 (m·s̶)/(s̶) = 10 m
```

`!long` returns to the three stages and `!short` to the result alone. The LaTeX export loads the `cancel` package when a line strikes a unit through.

Blank lines are for keeping the sheet text readable, so the results pane and the exports leave them out: the results are laid out to be read already.

Every command and every plot, solver, regression or symbolic solve block is headed in the results by the `!` line it was called with, the same way for every kind, with what a one-line command did after an arrow. These marks are for reading the page; the exports leave them out.

## Hiding lines

`!hide` hides the lines below it, up to the next `!show` (or the end of the sheet). They still run, so the names they define are there for the lines after them, but neither the results pane nor any export shows them: use it for working you need but do not want in the printout.

```
!hide
k = 0.5 * rho * Cd * A        working, not shown
!plot k*v^2, v = 0 .. 30      not drawn either
!show
F = k * v^2                   shown, using k
```

- The `!hide` and `!show` lines themselves still show in the results pane, marked like any command, so you can see where the hidden part is. The exports leave them out, as they leave out every command (the LaTeX document keeps them as `%` comments).
- Everything between is hidden: calculations, plots, regressions, comments and headings, and other commands.
- **Errors are never hidden**: a line under `!hide` that fails shows its error in the results pane and in the exports, so a broken line is not lost.
- **A solver block that needs running is not hidden**: a `!root`, `!minimize` or `!maximize` block under `!hide` shows while its result is out of date or was never run, so you can press Run (and an export marks it out of date rather than leaving it out). Once its result is current it is hidden like any other line.
- The exports leave out exactly what the results pane does.

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
| Export → PDF | opens the browser's print dialog on a plain, printable copy of the results, where **Save as PDF** saves it: broken into pages: headings, comments, each calculation with its line number, plots and errors, in one column. A calculation never splits across pages and a heading stays with what follows it. A calculation a little too wide for the page is shrunk; one much too wide is wrapped after `+` and `=`, the same way as in the results pane. It is a quick, readable printout, not a typeset document; use the LaTeX export for that |
| Plot SVG / PNG | the picture exactly as drawn (see [Plots](Plots)) |
| `lens file.lens --tex out.tex` | the same `.tex` from the command line |
| `lens file.lens --md out.md` | the same Markdown note from the command line |
| `lens file.lens --pdf out.pdf` | the same PDF from the command line, printed by a headless browser |

The LaTeX export needs siunitx v3 or newer for `\qty`, `\unit` and, for complex values, `\complexqty`. The Markdown export uses the live view's math (`\mathrm{kN}`), which Obsidian's MathJax renders without extra packages.

In the app, **Export → PDF** prints from the page itself: the printable document is laid out in a hidden frame (no new tab, so no pop-up permission), its formulas are fitted to the printed column once its fonts are in, and then the browser's print dialog opens. The **Export** button reads *Exporting PDF…* until it does. The document sets its own page margins and footer (the sheet's title, and *Page n of m*), which in Chrome and Edge also replace the browser's own header and footer; keep **Margins** on *Default* in the dialog. In other browsers the footer may be missing, and the browser's header and footer can be turned off in the dialog.

The command line has no page, so `--pdf` prints with Chrome, Chromium or Edge running headless, found on `PATH` (and in the usual install folders on Windows); set `LENS_CHROMIUM` to a browser's path to pick one. Without one it stops with an error. Both print the same document, so the pages match.
