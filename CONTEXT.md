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
: A header line (`!plot`, `!root`, `!minimize`, `!maximize`) and the indented lines it **owns**. A plot owns the `key: value` option lines under it; a solver block owns every indented, non-blank line under it, including comments and its stored result.

**Owner**
: The block a line belongs to (a header owns itself), or none.

**Option line**
: A `key: value` line owned by a block, with an optional argument before the colon: a series number under a plot (`color 2: red`), a name under a solver (`bounds x: 0 .. 1`).

**Stored result**
: The `#@ result {...}` line at the end of a solver block: the last answer and the hash of the inputs it was computed from.

**Expression span**
: The part of a line that holds an expression. A plot's limits and note positions are expressions; its title is text. Rename and global marking only look inside spans.

**Token**
: A name, unit, number or quoted text found by the worksheet lexer. A **name** may carry a `~` (global) in front and `` ` ``, `!`, `@` after; a **unit** is a quote and a unit name, or `'%`. The lexer patterns are also the grammar's terminals, and the editor's JS lexers are held to them by `tests/sheettext_vectors.json`.

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
: What a row can show, the same fields on every result and empty when the line has none: `text` (plain), `latex` (typeset), `error`, `warning` and `stale`.

**Block handle**
: On a block header's result, the sheettext **Block** it starts, whether the block drew or failed. `sheet.block_at(text, line)` finds a block by its header, and `sheet.solver_blocks(text)` finds every solver block. Both read the text to find the blocks and run the sheet only as far as they need (`evaluate(..., until=)`).

**Payload**
: The kind-specific part of a result, behind `r.plot` (`PlotPayload`: the spec, the picture, whether the mouse has `moved` the view) or `r.solver` (`SolverPayload`: status, hash, values, stored record). On every other line both are None, a failed block header included.

**Note**
: A warning the evaluator raises while it runs a line (`Evaluator.note`): the line works but may not do what was meant, such as `*` with an offset unit. Notes are cleared before each line, kept once each, and name the user function they come from; `sheet.py` joins them to the line's own **warning** (a block's go on its header). A failed line shows its error alone.

**Row**
: A line result as `/api/eval` sends it (`to_json()`): the common fields, plus `plot` or `solver` for those kinds and `snippet` in the LaTeX view. `tests/test_lineresult.py` pins its shape.

**Row model**
: What the results pane shows for one row: its lines, class names, a typed body (text, math, error, plot, solver or snippet), the warning, the stale mark and the Copy text. `static/rows.js` builds it from a row with one table from line kind to body; option lines map to no row of their own.

## Name scope (`symbols.py`)

**Symbol table**
: Which variables and functions each line of a sheet can see. Built once in `sheet.evaluate` as the sheet runs, and the one place the scope rules are applied: the `~` global marker, `!clear` / `!clearf`, local parameters, solver unknowns, and a failed line defining nothing. The evaluator only asks it for a name's key. Each eval row carries its line's part of it (`symbols`); `static/symbols.js` reads it there for the editor.

**Symbol**
: One successful definition of a name: its kind (variable or function), whether it is global, the line that defines it, the last line it is **visible** on, a variable's **value** as the sheet prints it and a function's parameters.

**Visible**
: A symbol is visible on the lines below its definition, up to and including the line that defines the name again or clears it (that line still reads the old one: `x = x + 1`).

**Key**
: The name a symbol's value is stored under: the bare name, or `~name` for a global. Once a name is global, every use of it, with or without the `~`, resolves to the global key.

**Use**
: A name on a line that means a symbol: the one its line defines, else the visible one. A function's parameters are local and mean none. The editor marks the uses of globals.

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

**Statement**: a command that begins a plot or solver block (`!plot`, `!root`, `!minimize`, `!maximize`). It is listed in the registry for suggestions and help, but its lines are run by `plotspec.py` and `solver.py`.

**Sheet mode** (`SheetMode`): the state commands change as a sheet runs top to bottom: angle unit, assume (reduce to SI), short (final result only), display precision (significant figures, decimal places, trailing zeros), plot defaults, and the names removed by `!clear` / `!clearf`. Each run starts with a fresh one; only commands write it, and the evaluator, `Fmt` and the plot builder read it.

## Units

**Unit catalogue** (`laconic/catalogue.py`): the one module that knows about the unit families needing more than Pint gives. Other modules ask it rather than keeping their own lists.

**Unit family**: a group of units that share one policy in the catalogue: currencies, percent, constants with subscripted symbols, Pint units siunitx lacks.

**Currency**: a unit named by its ISO 4217 code ('USD, 'EUR). Each is a dimension of its own, so currencies never convert into each other; an exchange rate is an ordinary variable.

**Declared unit**: a unit the `.tex` export gives a `\DeclareSIUnit` of its own, because siunitx does not define it (a user-defined unit, a currency, 'ft, 'g0). `Fmt.declarations()` returns the lines for the units a document printed.

## Front end

- **File handle**: the file a sheet was opened from or last saved to, as given by the browser's File System Access API. Only a `.lens` file gets one; a `.cs` or `.txt` file is read but never overwritten. Renaming the sheet drops it. See `laconic/static/savefile.js`. A sheet the program was started with (`lens --window FILE`, a double-clicked file) gets a stand-in handle that the server writes through (`/api/opened/save`).
- **Save / Save As**: Save writes to the file handle when there is one and the browser grants permission, and otherwise asks for a file. Save As always asks. Without the File System Access API, both download a copy.
- **Theme**: fonts, the color set and the editor paper style, kept in browser storage. See `laconic/static/theme.js`.
- **Preset**: a named color set (LENS blueprint, Engineering paper, White paper, Dark, Canoe Dark). Colors that match none are "Custom".
- **Readable theme**: one whose text and paper colors have a WCAG contrast ratio of at least 3:1. A stored theme that is not readable is replaced by the default colors on load, with a note.
- **Shortcut table**: the list of editor keys under Settings → Reference, kept as data in `laconic/static/shortcuts.js`, except the worksheet-command rows, which come from the command registry. `wiki/Editor-Shortcuts.md` describes the same keys at more length; a test checks it mentions every Ctrl and Alt shortcut.
