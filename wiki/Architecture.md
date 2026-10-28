# Architecture

## Data flow

```
worksheet text
   │  sheettext.py    line kinds, blocks, expression spans, tokens
   │  sheet.py        runs each line in order
   │  lineresult.py   one LineResult per line: owned lines, display parts, block handle,
   │                  symbols, and a plot or solver payload
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

- **One tree, two consumers.** The evaluator and the LaTeX printer walk the same AST, so the stages of a result (symbolic, substituted, result) are decided in `latex.py` and nowhere else.
- **One element stream, three writers.** `exports.py` turns each line result into one export element (heading, paragraph, error, figure, math rows) and decides once which lines are left out and which comments run on. The `.tex`, Markdown and PDF writers only render elements.
- **One spec, three outputs.** `plotspec.py` turns a plot's source into a plain dict. The SVG renderer, the pgfplots writer and the page all read that dict. The mouse never draws; it only rewrites the option lines in the worksheet text, and the plot is redrawn from the text.

- **One result interface.** Each line's `LineResult` (`lineresult.py`) answers the same small interface, whatever its kind: the lines it owns, its display parts, its block handle and its symbols. A plot's or solver's data sits behind it as a typed payload (`r.plot`, `r.solver`). The LaTeX writer, the CLI and the endpoints read results through it, and the page reads the JSON rows through one module (`rows.js`). The row shape is pinned by a contract test.

- **One writer of block lines.** Every change the server makes to the text (an option the mouse set, a stored solver result, a rename) goes back to the page as edits against the text it was sent, never a whole new text. The block editor (`blockedit.py`) writes every line a plot or solver block owns, and the page applies every server edit through one adapter (`Editing.applyEdits`, through the page's editor adapter).

The whole sheet is re-run on every edit (a few milliseconds at worksheet size), so there is no incremental state to get out of sync.

## Python modules (`laconic/`)

| Module | Role |
|---|---|
| `sheettext.py` | The shape of the worksheet text: each line's kind, the plot or solver block that owns it, its expression spans, and the name/unit/number tokens in them. One deep module behind `scan(text)`; the sheet, rename, plot and solver modules read lines and blocks through it. Its lexer patterns are the grammar's terminals too. Terms are defined in `CONTEXT.md` |
| `blockedit.py` | Edits to the sheet text (`Edit`, `apply`, the UTF-16 wire form) and the block editor: set, remove or replace an option line, store a result (kept last), append a block-owned line. It keeps the block's indent and the file's line endings, and returns at most one minimal edit. `plotopts` and `solver` write through it; `rename` returns its `Edit`s and the save text takes its `newline` |
| `parser.py` | Lark LALR grammar for expressions. Assignment, function and unit definitions are split off first (`sheettext.definition`), which avoids a grammar clash between `f(x) = ...` and the call `f(x)` |
| `nodes.py` | Frozen dataclasses for the AST, and the one walk of it (`walk`, and `refs`: the names, calls and units an expression reads) |
| `evaluator.py` | AST to Pint quantities. Built-in functions are the `fn_*` methods, each declared to the function registry by `@builtin`; every value (scalar or matrix) is a Quantity. A name's key and value come from the symbol table |
| `functions.py` | The function registry: each built-in declared once (signature, LaTeX form, aliases) by `@builtin` on its `Evaluator.fn_*` method. The evaluator, suggestions, Rename and the LaTeX printer read it |
| `symbols.py` | The symbol table: which variables and functions each line sees, with each definition's line, lifetime, value and parameters, and each key's current value or function body and whether it is stale. One deep module behind `define`, `define_function`, `clear`, `key`, `visible`, `uses` and `tainted`, holding the scope rules (`~` globals, `!clear`/`!clearf`, local parameters, solver unknowns, failed lines). Built as the sheet runs; each eval row carries its part |
| `si.py` | Reduces a result to simplest coherent SI with a familiar name, asking the catalogue how each unit family reduces |
| `catalogue.py` | The unit catalogue: currencies, percent, unit ratios (`'mm/'mm`), physical constants, subscripted constant symbols and the siunitx spellings, and offset temperatures, with each family's dimension, reduction, export macro, editor text and error hint |
| `latex.py` | AST to LaTeX in two flavors (KaTeX preview, siunitx export); number formatting (`Fmt`, which also hands back the `\DeclareSIUnit` lines for the units a document printed); `snippet` and `document`, which render export elements. A built-in's LaTeX form comes from the function registry |
| `exports.py` | What a sheet exports as: one element per line result, with what is left out and which comments run on decided once; `export(text, fmt, ...)`, the one entry point, runs the sheet in the flavour each format needs (siunitx for `.tex`, the live view's for Markdown, HTML and PDF). The server and the CLI export through it |
| `sheet.py` | Runs a worksheet line by line, dispatching on the line kinds from `sheettext`: commands, unit definitions, plots, results, portable save text. Records each definition in the symbol table. `block_at` and `solver_blocks` find blocks by the text and run the sheet only as far as those blocks (`evaluate(..., until=)`); `evaluator_at` gives the evaluator as a line finds it |
| `lineresult.py` | The line result: the interface every result answers (owned lines, display parts, block handle, symbols), the plot and solver payloads behind it, and the row JSON `/api/eval` sends (`to_json`, pinned by `tests/test_lineresult.py`) |
| `commands.py` | The command registry (every `!` command: name, argument rule, summary, help row, effect) and the sheet mode the commands change. Suggestions, help rows and the unknown-command message are generated from it |
| `plotopts.py` | Plot option parsing, defaults, and the patch a pan, zoom or reset makes to the option lines (written through the block editor) |
| `plotspec.py` | Samples a plot and resolves options into the spec |
| `plotsvg.py` | Spec to SVG |
| `plotpgf.py` | Spec to pgfplots |
| `solver.py` | `!root` / `!minimize` / `!maximize`: block parsing, the input hash, the scipy calls, the stored `#@ result` line (written through the block editor) |
| `solvesession.py` | The solve session: which blocks need solving, running one behind a runner seam (in-process `solve`, or the worker's `Jobs.run`), run or verify, and storing a result in every block whose inputs hash the same. The server, the worker and `lens --solve` call it |
| `solverjobs.py` | The worker process that runs a solve, so it can be interrupted; `Jobs.run` is its runner for the solve session |
| `symbolic.py` | Symbolic math through sympy (imported only when a sheet declares a symbol): the sympy expression built from the AST, numbers with units held as stand-ins so Pint does their arithmetic, late binding of symbols to the values where they are used, the sympy-to-Pint walk for an expression whose symbols all have values, the sympy LaTeX and plain printers with the sheet's names and numbers, and the `!symsolve` solve |
| `symsolve.py` | `!symsolve`: block parsing only (no sympy), so the editor's vocabulary can list its options. Run by `sheet.py` every time the sheet runs; the block is read by `sheettext` as a solver block |
| `regression.py` | `!regression`: block parsing and the least-squares polynomial fit, with each coefficient's units. Run by `sheet.py` every time the sheet runs (no stored result); the block is read by `sheettext` as a solver block |
| `props.py` | CoolProp lookup, imported on first use |
| `rename.py` | Rename of names and units, over the tokens `sheettext` finds in expression spans |
| `vocab.py` | What the editor suggests: units, functions, constants, commands |
| `unittags.py` | The units dialog's tags: the standard tag list (units and Pint dimensions) and the cleaning of the user's tags before they are stored |
| `settings.py` | The per-user settings file (Greek table, global units, the user's unit tags, the page's display preferences including the theme, and whether the welcome was shown) |
| `server.py` | FastAPI app. It writes the preference keys (`settings.PREFS`) into the page |
| `opened.py` | The sheets this server's windows are opened on (the start file, and sheets another launch handed over, by token), and which may be written back (`.lens` only) |
| `markdown.py` | Export elements to a Markdown note in Obsidian's style: `$$` math in the live preview's flavour, plots as embedded SVG |
| `pdfdoc.py` | Export elements to a plain, page-broken HTML document. The page prints it from a hidden frame with the browser's print dialog; the CLI's `--pdf` prints it with a headless Chromium-family browser |
| `browser.py` | Finds a Chromium-family browser for the app window and the CLI's PDF export, the user's default first; `LENS_CHROMIUM` overrides |
| `instance.py` | One LENS at a time on the same port: a second launch hands its window (and sheet) to the running one |
| `fileassoc.py` | `lens --register-files` / `--unregister-files`: the `.lens` file type on Windows, under `HKEY_CURRENT_USER` |
| `lifecycle.py` | Tracks open pages so the packaged app exits after its window closes |
| `__main__.py` | The `lens` command line. `--serve` opens the server's socket and starts the browser before importing the server (about a second), so the browser's first request waits in the socket's queue rather than LENS waiting for anything, and builds the unit registry in the background before the page asks for a result. The package's `__init__` loads its heavy names on first use for the same reason |
| `_version.py` | The program's version, the one place it is written; the release build stamps it from the tag |

## Front end (`laconic/static/`)

| File | Role |
|---|---|
| `index.html` | The page: layout, styles, dialogs, and the glue script that wires the modules below to the DOM and browser APIs; it holds no logic of its own that a module could. `render()` draws each row model's body through a small table of body types |
| `rows.js` | The row model: what the results pane shows for each eval row, from one table of line kind to body, and which row shows a given line. The page's one reader of the rows' common fields (`line`, `head`, `stale`, `current` for other modules) |
| `mathfit.js` | Fitting typeset math to its width: leave it, shrink it, or wrap it one stage per row (`latex_rows`). The results pane and the PDF export (`pdfdoc.py`) both use it |
| `editing.js` | Math keys and term-aware selection, as pure functions (`{from, to, insert, caret}` edits); `merge` turns the server's edits into one such edit, and `applyEdits` makes them through the page's editor adapter; `nameAt` is the name F2 fills in; `isTextAt` says where the text is prose (outside `sheettext`'s expression spans) |
| `api.js` | The page's one client of the server: JSON and text requests, keepalive saves and beacons. An `{ok: false, error}` answer is the caller's to read; an HTTP error throws its `detail` |
| `prefs.js` | Where each setting is kept: the display preferences (the keys the server writes into the page) on the server, the rest in browser storage, with older builds' prefixes read once. The page passes a storage adapter |
| `autocomplete.js` | What to suggest, as pure functions. Your variables and functions come from the last symbol table. Also the open list: when it opens, what each key does, Ctrl+Space wrapping |
| `symbols.js` | Reads the symbol table out of the eval rows: what a line sees, the globals, the marks on a line (globals, and symbols declared with `$`). An adapter of `symbols.py`; it applies no scope rule of its own |
| `paste.js` | Table paste to matrix, pure functions |
| `unitbrowser.js` | The units dialog: which units a search and a tag list, and adding and removing the user's tags, as pure functions |
| `savefile.js` | Save file policy: reuse the open file or ask, the file name, the download fallback. The page passes an adapter over the File System Access API |
| `theme.js` | Theme data (fonts, presets), the contrast check, loading a stored theme, the CSS variables to set |
| `layout.js` | Side by side or stacked: switching at the narrow width, Alt+L and the Settings choice, and when to offer to stop switching. The page draws it as `body.stacked` |
| `shortcuts.js` | The keyboard shortcut table, as data; the page renders it under Settings → Reference, with the command rows `server.py` fills in from `commands.py` |
| `plotview.js` | Pan and zoom on plots; writes `xview`/`yview` back through the server. Reads the plot payload's spec |
| `solverview.js` | The Run / Interrupt / Verify / Log strip under solver blocks. Reads the solver payload |
| `matrixview.js` | Large matrices in the results pane: a matrix of more than 8 rows or columns collapsed to its corners, by the rule `exports.collapse_matrices` uses for documents (`tests/matrix_vectors.json` holds the two together). `rows.js` asks it; the page draws the button that shows the matrix whole |
| `vendor/` | KaTeX, and d3-zoom with d3-scale and dependencies (see `vendor/d3/README.md`) |
| `fonts/` | IBM Plex and OCR-A, self-hosted |
| `example.lens` | The sheet the page opens with |

The example worksheets live in `laconic/examples/` and are served by `/api/examples`.

The pure-function JS files also load under Node, which is how they are tested without a browser.

The editor never works out scope itself. Autocomplete, the `~` that Math keys add to a global and the global and symbol marks all read the symbol table of the last evaluation (`symbols.js`); between a keystroke and the next response they use the last table.

The editor keeps its own lexer (`Editing.tokens`, `isTok`) and definition and solver-block readers (`Autocomplete.definition`, `solverBlock`), its prose rule (`Editing.isTextAt`) and the name F2 fills in (`Editing.nameAt`), since it reads text as it is typed. They are adapters of `sheettext.py` across the HTTP seam: `tests/sheettext_vectors.json` is run by both `test_sheettext.py` and `test_sheettext.js`, so a change to one side that the other lacks fails a test.

## HTTP API

| Endpoint | Purpose |
|---|---|
| `GET /` | the page, with the command help rows filled in from the registry and the version (`_version.py`) in the header and Help |
| `POST /api/eval` | run a sheet; one row per line (`LineResult.to_json`): `n`, `end`, `kind`, `source`, the display parts `text`, `latex` (and `latex_rows`, the same one stage per row), `error`, `warning`, `stale`, its part of the symbol table (`symbols: {defines, uses}`), and `plot: {svg, spec, moved}` or `solver: {...}` on those kinds; `view: "latex"` adds a `snippet` per line |
| `POST /api/export` | complete `.tex` document |
| `POST /api/export/md`, `POST /api/export/pdf`, `POST /api/export/print` | Markdown note; PDF printed by a headless browser (501 without a Chromium-family browser; the app does not use it); the printable document, which the app's Export → PDF prints from a hidden frame |
| `POST /api/save` | source with needed unit definitions appended |
| `POST /api/rename` | rename a name or unit; returns edits (one per use) or a warning/error |
| `POST /api/plotedit` | edits to one plot's option lines for a pan, zoom or reset (runs the sheet only as far as the plot) |
| `POST /api/plotimage` | one plot as a standalone SVG |
| `POST /api/solve/start`, `GET /api/solve/{job}`, `POST /api/solve/{job}/interrupt` | start, poll and interrupt a solver job |
| `POST /api/solvestore`, `POST /api/solveedit` | edits that write a finished result into its block; toggle `autorun:` |
| `GET /api/unitbrowse`, `PUT /api/tags` | every unit with its standard tags, the user's tags and the global units, for the units dialog; store the user's tags |
| `GET /api/settings`, `GET /api/vocab`, `GET /api/vocab/props` | settings, editor vocabulary, props keys and fluids (loaded lazily because it imports CoolProp) |
| `PUT /api/greek`, `PUT /api/units`, `PUT /api/prefs`, `PUT /api/welcomed` | store settings (units only if all valid), the display preferences, and that the welcome was shown |
| `GET /api/opened`, `POST /api/opened/save` | the worksheet the window was opened on (`lens --window FILE`), and writing it back to that file |
| `GET /api/examples`, `GET /api/examples/{name}` | the example worksheets in `laconic/examples/` |
| `POST /api/ping`, `POST /api/bye` | page lifecycle for the packaged app |
| `GET /api/hello`, `POST /api/window` | how another launch recognizes a running LENS and hands it the window (`instance.py`) |

Endpoints that change the text return `{"ok": true, "edits": [{"from", "to", "insert"}, ...]}`: edits against the text in the request, not overlapping, with offsets in UTF-16 code units as JavaScript counts them. The page makes them only if its text is still the one it sent.

## Conventions

- Errors are per line: `sheet.py` turns any exception into an `error` result for that line and carries on.
- Warnings are per line too: the evaluator collects **notes** for the line being run (`Evaluator.note`), and `sheet.py` clears them before each line and joins them to that line's `warning`. A line that failed shows only its error.
- A fresh Pint registry costs a noticeable fraction of a second, so one is shared. A sheet that defines units gets a private copy (Pint cannot undefine a unit).
- Display rounding is only ever applied when printing, in `Fmt`.
- Evaluating a sheet never runs a solver. It hashes the block's inputs and compares them with the stored `#@ result` line; running happens on request in a worker process and the answer is written back into the worksheet text.
