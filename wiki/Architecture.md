# Architecture

## Data flow

```
worksheet text
   │  sheettext.py    line kinds, blocks, expression spans, tokens
   │  sheet.py        runs each line in order
   ▼
parser.py ──► nodes.py (AST) ──► evaluator.py ──► Pint quantities ──► si.py (display units)
                    │
                    └──────────► latex.py (same AST) ──► symbolic / substituted / result strings
                                                              │
plot lines ─► plotopts.py (options) ─► plotspec.py (samples, resolves) ─► spec dict
                                                              │
                                      ┌───────────────────────┼──────────────────────┐
                                  plotsvg.py              plotpgf.py             browser (plotview.js
                                  (the only SVG)          (.tex export)           adds mouse only)
```

Two ideas hold it together:

- **One tree, two consumers.** The evaluator and the LaTeX printer walk the same AST, so the layout of a result (symbolic, substituted, result) is decided in `latex.py` and nowhere else.
- **One spec, three outputs.** `plotspec.py` turns a plot's source into a plain dict. The SVG renderer, the pgfplots writer and the page all read that dict. The mouse never draws; it only rewrites the option lines in the worksheet text, and the plot is redrawn from the text.

The whole sheet is re-run on every edit (a few milliseconds at worksheet size), so there is no incremental state to get out of sync.

## Python modules (`laconic/`)

| Module | Role |
|---|---|
| `sheettext.py` | The shape of the worksheet text: each line's kind, the plot or solver block that owns it, its expression spans, and the name/unit/number tokens in them. One deep module behind `scan(text)`; the sheet, rename, plot and solver modules read lines and blocks through it. Its lexer patterns are the grammar's terminals too. Terms are defined in `CONTEXT.md` |
| `parser.py` | Lark LALR grammar for expressions. Assignment, function and unit definitions are split off first (`sheettext.definition`), which avoids a grammar clash between `f(x) = ...` and the call `f(x)` |
| `nodes.py` | Frozen dataclasses for the AST |
| `evaluator.py` | AST to Pint quantities. Built-in functions are the `fn_*` methods; every value (scalar or matrix) is a Quantity |
| `si.py` | Reduces a result to simplest coherent SI with a familiar name |
| `catalogue.py` | The unit catalogue: currencies, percent, subscripted constant symbols and the siunitx spellings, with each family's dimension, reduction, export macro, editor text and error hint |
| `latex.py` | AST to LaTeX in two flavors (KaTeX preview, siunitx export); number formatting (`Fmt`, which also hands back the `\DeclareSIUnit` lines for the units a document printed); `snippet` and `document` |
| `sheet.py` | Runs a worksheet line by line, dispatching on the line kinds from `sheettext`: commands, unit definitions, plots, results, portable save text |
| `commands.py` | The command registry (every `!` command: name, argument rule, summary, help row, effect) and the sheet mode the commands change. Suggestions, help rows and the unknown-command message are generated from it |
| `plotopts.py` | Plot option parsing, defaults, and the writer that edits option lines in the source |
| `plotspec.py` | Samples a plot and resolves options into the spec |
| `plotsvg.py` | Spec to SVG |
| `plotpgf.py` | Spec to pgfplots |
| `solver.py` | `!root` / `!minimize` / `!maximize`: block parsing, the input hash, the scipy calls, the stored `#@ result` line |
| `solverjobs.py` | The worker process that runs a solve, so it can be interrupted |
| `props.py` | CoolProp lookup, imported on first use |
| `rename.py` | Rename of names and units, over the tokens `sheettext` finds in expression spans |
| `vocab.py` | What the editor suggests: units, functions, constants, commands |
| `settings.py` | The per-user settings file (Greek table, global units) |
| `server.py` | FastAPI app |
| `lifecycle.py` | Tracks open pages so the packaged app exits after its window closes |
| `__main__.py` | The `lens` command line |

## Front end (`laconic/static/`)

| File | Role |
|---|---|
| `index.html` | The page: layout, styles, theme, dialogs, and the glue script |
| `editing.js` | Math keys and term-aware selection, as pure functions (`{from, to, insert, caret}` edits) |
| `autocomplete.js` | What to suggest, as pure functions |
| `paste.js` | Table paste to matrix, pure functions |
| `plotview.js` | Pan and zoom on plots; writes `xview`/`yview` back through the server |
| `solverview.js` | The Run / Interrupt / Verify / Log strip under solver blocks |
| `vendor/` | KaTeX, and d3-zoom with d3-scale and dependencies (see `vendor/d3/README.md`) |
| `fonts/` | IBM Plex and OCR-A, self-hosted |
| `example.lens` | The sheet the page opens with |

The example worksheets live in `laconic/examples/` and are served by `/api/examples`.

The pure-function JS files also load under Node, which is how they are tested without a browser.

The editor keeps its own lexer (`Editing.tokens`, `isTok`) and definition and solver-block readers (`Autocomplete.definition`, `solverBlock`), since it reads text as it is typed. They are adapters of `sheettext.py` across the HTTP seam: `tests/sheettext_vectors.json` is run by both `test_sheettext.py` and `test_sheettext.js`, so a change to one side that the other lacks fails a test.

## HTTP API

| Endpoint | Purpose |
|---|---|
| `GET /` | the page, with the command help rows filled in from the registry |
| `POST /api/eval` | run a sheet; `view: "latex"` adds a snippet per line |
| `POST /api/export` | complete `.tex` document |
| `POST /api/save` | source with needed unit definitions appended |
| `POST /api/rename` | rename a name or unit; returns new text or a warning/error |
| `POST /api/plotedit` | rewrite one plot's option lines for a pan, zoom or reset |
| `POST /api/plotimage` | one plot as a standalone SVG |
| `POST /api/solve/start`, `GET /api/solve/{job}`, `POST /api/solve/{job}/interrupt` | start, poll and interrupt a solver job |
| `POST /api/solvestore`, `POST /api/solveedit` | write a finished result into its block; toggle `autorun:` |
| `GET /api/settings`, `GET /api/vocab`, `GET /api/vocab/props` | settings, editor vocabulary, props keys and fluids (loaded lazily because it imports CoolProp) |
| `PUT /api/greek`, `PUT /api/units` | store settings (units only if all valid) |
| `POST /api/ping`, `POST /api/bye` | page lifecycle for the packaged app |

## Conventions

- Errors are per line: `sheet.py` turns any exception into an `error` result for that line and carries on.
- A fresh Pint registry costs a noticeable fraction of a second, so one is shared. A sheet that defines units gets a private copy (Pint cannot undefine a unit).
- Display rounding is only ever applied when printing, in `Fmt`.
- Evaluating a sheet never runs a solver. It hashes the block's inputs and compares them with the stored `#@ result` line; running happens on request in a worker process and the answer is written back into the worksheet text.
