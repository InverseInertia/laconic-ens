# LENS: domain language

Short definitions of the terms the code and its reviews use. Code lives in `laconic/`; the module that owns a term is named after it.

## Worksheet text (`sheettext.py`)

**Sheet text**
: The worksheet as the user typed it. Everything else (results, plots, the stored solver answers) is derived from it or written back into it. `sheettext.scan(text)` is the one reader of its shape.

**Line**
: One line of sheet text, numbered from 1 as the editor numbers it. It carries its **kind**, its **owner**, its **expression spans** and its line ending (`eol`) separately from its text.

**Line kind**
: What a line is: `blank`, `heading` (`##`), `meta` (`#@`), `comment` (`#`), `command` (`!clear`), `unitdef`, `funcdef`, `assign`, `expr`, a block header (`plot`, `solver`) or a line a block owns (`plotopt`, `solveropt`). A unit definition stays `unitdef` wherever it is, because units are defined before the sheet runs.

**Block**
: A header line (`!plot`, `!root`, `!minimize`, `!maximize`, `!regression`) and the indented lines it **owns**. A plot owns the `key: value` option lines under it; a solver block owns every indented, non-blank line under it, including comments and its stored result. A `!regression` block is read as a solver block (its lines are owned and parsed the same way) but is run by `regression.py`.

**Owner**
: The block a line belongs to (a header owns itself), or none.

**Option line**
: A `key: value` line owned by a block, with an optional argument before the colon: a series number under a plot (`color 2: red`), a name under a solver (`bounds x: 0 .. 1`).

**Stored result**
: The `#@ result {...}` line at the end of a solver block: the last answer and the hash of the inputs it was computed from.

**Expression span**
: The part of a line that holds an expression. A plot's limits and note positions are expressions; its title is text. Rename and global marking only look inside spans.

**Token**
: A name, unit, number or quoted text found by the worksheet lexer. A **name** may carry a `~` (global) in front and `` ` ``, `!`, `@` after, and `∞` as a whole subscript (`v_∞`); a **unit** is a quote and a unit name, or `'%`. The lexer patterns are also the grammar's terminals, and the editor's JS lexers are held to them by `tests/sheettext_vectors.json`.

**Definition**
: What a code line defines: a variable (`x = ...`), a function (`f(x) = ...`, whose **parameters** are local to the line) or a unit (`'u = ...`).

**Global**
: A name defined with a leading `~`. It survives `!clear`, and the editor marks each use of it.

## Line results (`lineresult.py`)

**Line result** (`LineResult`)
: What running one line gives: everything that shows a line or acts on it reads it. Every result, whatever its kind, answers one small interface: the lines it **owns**, its **display parts**, its **block handle** and its part of the symbol table. What only one kind has is its **payload**.

**Owned lines**
: A result owns its own line; a block header's result owns the whole block, header to last line (`n` .. `end`). A block's option lines still get results of their own, but the page shows them inside the header's row unless one is wrong.

**Display parts**
: What a row can show, the same fields on every result and empty when the line has none: `text` (plain), `latex` (typeset; `latex_rows` is the same broken one stage per row, for a layout too narrow for it), `error`, `warning` and `stale`.

**Block handle**
: On a block header's result, the sheettext **Block** it starts, whether the block drew or failed. `sheet.block_at(text, line)` finds a block by its header, and `sheet.solver_blocks(text)` finds every solver block. Both read the text to find the blocks and run the sheet only as far as they need (`evaluate(..., until=)`).

**Payload**
: The kind-specific part of a result, behind `r.plot` (`PlotPayload`: the spec, the picture, whether the mouse has `moved` the view) `r.solver` (`SolverPayload`: status, hash, values, stored record) or `r.regression` (`RegressionPayload`: degree, points, R², the polynomial, values). On every other line each is None, a failed block header included.

**Regression block**
: `!regression a, b, c` with a `data:` line: a least-squares polynomial through points, the columns of a 2-row matrix (x row, y row) or two vectors. The header names the coefficients, lowest power first, or one name holds them all as a vector (with `degree:`). It is fitted every time the sheet runs, so it has no stored result and no Run; it defines its names (and the `r2:` name) like an assignment.

**Collapsed matrix**
: A matrix with more than 8 rows or columns, shown by its first 3 and last 2 rows and columns with ⋮, ⋯ and ⋱ between: in the results pane until the row's button shows it whole (`static/matrixview.js`), and always in a document (`exports.collapse_matrices`). A line's LaTeX snippet keeps it whole.

**Note**
: A warning the evaluator raises while it runs a line (`Evaluator.note`): the line works but may not do what was meant, such as `*` with an offset unit. Notes are cleared before each line, kept once each, and name the user function they come from; `sheet.py` joins them to the line's own **warning** (a block's go on its header). A failed line shows its error alone.

**Row**
: A line result as `/api/eval` sends it (`to_json()`): the common fields, plus `plot` or `solver` for those kinds and `snippet` in the LaTeX view. `tests/test_lineresult.py` pins its shape.

**Row model**
: What the results pane shows for one row: its lines, class names, a typed body (text, math, error, plot, solver or snippet; math with a **collapsed matrix** carries the toggle that shows it whole), the warning, the stale mark and the Copy text. `static/rows.js` builds it from a row with one table from line kind to body; option lines map to no row of their own.

## Name scope (`symbols.py`)

**Symbol table**
: Which variables and functions each line of a sheet can see. Built once in `sheet.evaluate` as the sheet runs, and the one place the scope rules are applied: the `~` global marker, `!clear` / `!clearf`, local parameters, solver unknowns, and a failed line defining nothing. It also holds each key's current value or function body and whether it is stale, so defining a name, clearing it and binding a solver unknown are one call each. The evaluator only asks it for a name's key and value. Each eval row carries its line's part of it (`symbols`); `static/symbols.js` reads it there for the editor.

**Symbol**
: One successful definition of a name: its kind (variable or function), whether it is global, the line that defines it, the last line it is **visible** on, a variable's **value** as the sheet prints it and a function's parameters.

**Visible**
: A symbol is visible on the lines below its definition, up to and including the line that defines the name again or clears it (that line still reads the old one: `x = x + 1`).

**Key**
: The name a symbol's value is stored under: the bare name, or `~name` for a global. Once a name is global, every use of it, with or without the `~`, resolves to the global key.

**Use**
: A name on a line that means a symbol: the one its line defines, else the visible one. A function's parameters are local and mean none. The editor marks the uses of globals.

**Stale value**
: A value read from a solver result that is out of date. The symbol table answers whether an expression reads one (`tainted`), and a line that does is shown stale.

**Solve session** (`solvesession.py`)
: Finds the solver blocks that need solving, runs or verifies one through a **runner** (in this process, or the worker's `Jobs.run`), and stores the result in every block whose inputs hash the same. The page and `lens --solve` both go through it.

**Export element** (`exports.py`)
: What a line result becomes in any export: a heading, paragraph, error, figure or math rows. The `.tex`, Markdown and PDF writers only render elements.

## Editing the text (`blockedit.py`)

**Edit**
: Replace `text[from:to]` with `insert`. The server answers every change to the sheet text with a short list of edits against the text it was sent, never a whole new text. On the wire, offsets count UTF-16 code units, as the page's strings do.

**Block editor** (`BlockEditor`)
: The one writer of the lines a block owns. It sets, removes or replaces an option line, stores a result (always last), and appends other block-owned lines, keeping the block's **indent** and the file's **line ending**, and returns at most one minimal edit.

**Block indent**
: The indent of a block's first owned line, or two spaces for a block with none. New lines take it; a rewritten line keeps its own.

**File line ending**
: The ending of the file's first line (`\r\n` or `\n`). A line the server adds ends that way, so a CRLF file stays CRLF.

**Stale edit**
: An edit for a text the editor no longer holds (the user typed while the server worked). The page does not make it: a plot or rename says so, and a solver store asks again, since it finds its block by hash.

## Commands

**Command**: a line starting with `!` that changes how the lines below it run or are shown (`!clear`, `!trigdeg`, `!sigfigs 5`, `!plotspec grid: off`). Each is one entry in the command registry.

**Command registry** (`laconic/commands.py`, `COMMANDS`): the one place a command is declared, with its name, argument rule, summary, help row and effect. The dispatcher, the "Unknown command" message, the editor's command suggestions and the page's help rows are generated from it.

**Argument rule**: what may follow a command's name: nothing (`!clear`), a whole number in a range (`!sigfigs n`), the rest of the line (`!plotspec`), or a statement that starts a block.

**Function registry** (`laconic/functions.py`, `FUNCTIONS`): the one place a built-in function is declared, by `@builtin` on its `Evaluator.fn_*` method: its signature, LaTeX form and other names. Evaluation, suggestions, Rename and the LaTeX printer read it.

**Statement**: a command that begins a plot or solver block (`!plot`, `!root`, `!minimize`, `!maximize`, `!regression`). It is listed in the registry for suggestions and help, but its lines are run by `plotspec.py`, `solver.py` and `regression.py`.

**Sheet mode** (`SheetMode`): the state commands change as a sheet runs top to bottom: angle unit, assume (reduce to SI), short (final result only), display precision (significant figures, decimal places, trailing zeros), plot defaults, and the names removed by `!clear` / `!clearf`. Each run starts with a fresh one; only commands write it, and the evaluator, `Fmt` and the plot builder read it.

## Complex numbers

**Imaginary literal**: a number with a trailing `i` or `j` (`4i`, `2.5e3j`). It is part of the NUMBER token, so the lexer, the grammar and the editor read `4i` as one number; `2in` is still a number and a name. There is no bare `i`.

**Polar sign**: `∠` between a real magnitude and an angle, `10'V∠30'deg`. The angle reads like a trig argument. It binds between products and sums. The editor types it with Ctrl+<.

**Complex value**: a quantity with a complex magnitude. A sheet becomes complex only when one goes in: a negative real under `sqrt`, `ln` or a fractional power is still NaN (so plots keep their gaps), and the line's error says to add `0i`. A line's value whose imaginary parts are all zero is made real again (`Evaluator.settle`).

**Complex display** (`SheetMode.complex`, set by `!complex`): `rect` (`3 + 4i`, the default), `polar` (`5∠53.13°`, the angle in the trig unit) or `real`, where a complex line result is an error. `Fmt` hides a part smaller than 10⁻¹² of the whole. A typed imaginary literal is always shown as typed.

## Units

**Unit catalogue** (`laconic/catalogue.py`): the one module that knows about the unit families needing more than Pint gives. Other modules ask it rather than keeping their own lists.

**Unit family**: a group of units that share one policy in the catalogue: currencies, percent, physical constants, constants with subscripted symbols, Pint units siunitx lacks.

**Currency**: a unit named by its ISO 4217 code ('USD, 'EUR). Each is a dimension of its own, so currencies never convert into each other; an exchange rate is an ordinary variable.

**Physical constant**: a constant of nature typed as a unit ('R, 'k_B, 'h_P), listed in `CONSTANTS` in the catalogue. Being a unit, it never takes a variable's name. The editor's suggestion for one gives what it is and its value, so a search for `gas` or `boltz` finds it. A quantity typed with one is never shown as typed: it stands for a value, so its line shows that value in SI.

**Unit tag**: a label the units dialog filters by. A **standard tag** is defined in `laconic/unittags.py` as a list of units and Pint dimensions (`"[pressure]"` takes every pressure unit); a **user tag** is one the user put on units in the dialog, stored in `settings.json` as `{tag: [unit, ...]}`. See `laconic/static/unitbrowser.js`.

**Declared unit**: a unit the `.tex` export gives a `\DeclareSIUnit` of its own, because siunitx does not define it (a user-defined unit, a currency, 'ft, 'g0). `Fmt.declarations()` returns the lines for the units a document printed.

## Front end

- **File handle**: the file a sheet was opened from or last saved to, as given by the browser's File System Access API. Only a `.lens` file gets one; a `.cs` or `.txt` file is read but never overwritten. Renaming the sheet drops it. See `laconic/static/savefile.js`. A sheet the program was started with (`lens --window FILE`, a double-clicked file) gets a stand-in handle that the server writes through (`/api/opened/save`).
- **Save / Save As**: Save writes to the file handle when there is one and the browser grants permission, and otherwise asks for a file. Save As always asks. Without the File System Access API, both download a copy.
- **Theme**: fonts, the color set and the editor paper style, kept with the other display preferences in the settings file (`settings.PREFS`). See `laconic/static/theme.js`.
- **Preset**: a named color set (LENS blueprint, Engineering paper, White paper, Dark, Canoe Dark, Chalcedony Dark). Colors that match none are "Custom".
- **Readable theme**: one whose text and paper colors have a WCAG contrast ratio of at least 3:1. A stored theme that is not readable is replaced by the default colors on load, with a note.
- **Version** (`laconic/_version.py`): the program's version, written there and nowhere else. `0+dev` in the repository, shown as `dev`; a release build stamps it with the tag's version, shown as `v0.2.0` beside the title and in Help.
- **Layout**: side by side (editor left, results right) or stacked (results on top). With automatic switching on, crossing the narrow width (760 px) switches it; Alt+L or Settings → Layout picks one by hand, which holds until the next crossing, or for good with automatic switching off. See `laconic/static/layout.js`.
- **Shortcut table**: the list of editor keys under Settings → Reference, kept as data in `laconic/static/shortcuts.js`, except the worksheet-command rows, which come from the command registry. `wiki/Editor-Shortcuts.md` describes the same keys at more length; a test checks it mentions every Ctrl and Alt shortcut.
