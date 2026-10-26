# Context

Domain terms used in the code and the docs.

## Commands

**Command**: a line starting with `!` that changes how the lines below it run or are shown (`!clear`, `!trigdeg`, `!sigfigs 5`, `!plotspec grid: off`). Each is one entry in the command registry.

**Command registry** (`laconic/commands.py`, `COMMANDS`): the one place a command is declared, with its name, argument rule, summary, help row and effect. The dispatcher, the "Unknown command" message, the editor's command suggestions and the page's help rows are generated from it.

**Argument rule**: what may follow a command's name: nothing (`!clear`), a whole number in a range (`!sigfigs n`), the rest of the line (`!plotspec`), or a statement that starts a block.

**Statement**: a command that begins a plot or solver block (`!plot`, `!root`, `!minimize`, `!maximize`). It is listed in the registry for suggestions and help, but its lines are run by `plotspec.py` and `solver.py`.

**Sheet mode** (`SheetMode`): the state commands change as a sheet runs top to bottom: angle unit, assume (reduce to SI), short (final result only), display precision (significant figures, decimal places, trailing zeros), plot defaults, and the names removed by `!clear` / `!clearf`. Each run starts with a fresh one; only commands write it, and the evaluator, `Fmt` and the plot builder read it.
