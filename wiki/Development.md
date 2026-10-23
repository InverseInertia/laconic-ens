# Development

## Setup

```
pip install -e .[dev]
python -m pytest -q
```

Python 3.10 or newer. Dependencies: pint, numpy, lark, fastapi, uvicorn, CoolProp.

## Tests

| Command | Covers |
|---|---|
| `python -m pytest -q` | all Python tests, plus the Node suites if `node` is installed |
| `node tests/test_editing.js` | math keys and selections |
| `node tests/test_autocomplete.js` | suggestions |
| `node tests/test_paste.js` | table paste |

| File | Covers |
|---|---|
| `test_laconic.py`, `test_units.py` | evaluation, LaTeX, custom units |
| `test_plots.py`, `test_props.py`, `test_rename.py`, `test_server.py`, `test_lifecycle.py` | one module each |
| `test_editing_node.py` | runs the Node suites from pytest |
| `test_ui.py`, `test_plots_ui.py` | the real page in Chromium (Playwright); the second uses real pointer events on plots |

Browser tests are skipped unless `playwright` is installed (`pip install playwright`; set `CHROMIUM_PATH` to use an existing browser). One test compiles an exported document with plots and is skipped unless `pdflatex` (with pgfplots and siunitx v3) is installed.

## Running the page while you work

```
lens --serve --open
```

Static files are served from `laconic/static/`; reload the page after editing JS or HTML. Restart for Python changes.

## Adding things

- **A built-in function:** add an `fn_name` method to `Evaluator` (it is picked up by suggestions and Rename's reserved-name list automatically). Add a signature to `_SIGNATURES` in `vocab.py`, LaTeX in `Printer.call` if it should typeset specially, and a row to [Matrices](Matrices) or [Worksheet Syntax](Worksheet-Syntax).
- **A command:** handle it in `_run_command` in `sheet.py` and list it in `COMMANDS` in `vocab.py`.
- **A plot option:** add it to the tables at the top of `plotopts.py`, resolve it in `plotspec.py`, and draw it in `plotsvg.py` and `plotpgf.py`.

## CI

`.github/workflows/build.yml` runs pytest on every push and pull request, then builds and smoke-tests the standalone programs. See [Releases and Packaging](Releases-and-Packaging).
