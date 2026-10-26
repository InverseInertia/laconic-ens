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

## Commands

**Command**: a line starting with `!` that changes how the lines below it run or are shown (`!clear`, `!trigdeg`, `!sigfigs 5`, `!plotspec grid: off`). Each is one entry in the command registry.

**Command registry** (`laconic/commands.py`, `COMMANDS`): the one place a command is declared, with its name, argument rule, summary, help row and effect. The dispatcher, the "Unknown command" message, the editor's command suggestions and the page's help rows are generated from it.

**Argument rule**: what may follow a command's name: nothing (`!clear`), a whole number in a range (`!sigfigs n`), the rest of the line (`!plotspec`), or a statement that starts a block.

**Statement**: a command that begins a plot or solver block (`!plot`, `!root`, `!minimize`, `!maximize`). It is listed in the registry for suggestions and help, but its lines are run by `plotspec.py` and `solver.py`.

**Sheet mode** (`SheetMode`): the state commands change as a sheet runs top to bottom: angle unit, assume (reduce to SI), short (final result only), display precision (significant figures, decimal places, trailing zeros), plot defaults, and the names removed by `!clear` / `!clearf`. Each run starts with a fresh one; only commands write it, and the evaluator, `Fmt` and the plot builder read it.
