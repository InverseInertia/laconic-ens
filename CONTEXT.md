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

- **File handle**: the file a sheet was opened from or last saved to, as given by the browser's File System Access API. Only a `.lens` file gets one; a `.cs` or `.txt` file is read but never overwritten. Renaming the sheet drops it. See `laconic/static/savefile.js`.
- **Save / Save As**: Save writes to the file handle when there is one and the browser grants permission, and otherwise asks for a file. Save As always asks. Without the File System Access API, both download a copy.
- **Theme**: fonts, the color set and the editor paper style, kept in browser storage. See `laconic/static/theme.js`.
- **Preset**: a named color set (LENS blueprint, Engineering paper, White paper, Dark). Colors that match none are "Custom".
- **Readable theme**: one whose text and paper colors have a WCAG contrast ratio of at least 3:1. A stored theme that is not readable is replaced by the default colors on load, with a note.
- **Shortcut table**: the list of editor keys under Settings → Reference, kept as data in `laconic/static/shortcuts.js`, except the worksheet-command rows, which come from the command registry. `wiki/Editor-Shortcuts.md` describes the same keys at more length; a test checks it mentions every Ctrl and Alt shortcut.
