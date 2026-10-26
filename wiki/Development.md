# Development

## Setup

```
pip install -e .[dev]
python -m pytest -q
```

Python 3.10 or newer. Dependencies: pint, numpy, lark, fastapi, uvicorn, CoolProp, scipy.

## Tests

| Command | Covers |
|---|---|
| `python -m pytest -q` | all Python tests, plus the Node suites if `node` is installed |
| `node tests/test_editing.js` | math keys and selections |
| `node tests/test_autocomplete.js` | suggestions |
| `node tests/test_paste.js` | table paste |
| `python tests/stress/run_solver_stress.py` | about 35 heavy solver cases (Rosenbrock up to 100 variables, a 1000-equation system, CoolProp inside residuals, Hock-Schittkowski 71, timeouts) through the worker process |

| File | Covers |
|---|---|
| `test_laconic.py`, `test_units.py` | evaluation, LaTeX, custom units |
| `test_plots.py`, `test_props.py`, `test_rename.py`, `test_server.py`, `test_lifecycle.py` | one module each |
| `test_editing_node.py` | runs the Node suites from pytest |
| `test_solver.py`, `test_solverjobs.py` | solver blocks and the worker process |
| `test_ui.py`, `test_plots_ui.py`, `test_solver_ui.py` | the real page in Chromium (Playwright); the second uses real pointer events on plots. Fixtures are in `conftest.py`, shared helpers in `uihelpers.py` |

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
- **A unit that needs special handling** (its own dimension, a reduction rule, an export spelling, an error or hint): add it to the unit catalogue, `catalogue.py`. A currency is one entry in `CURRENCIES`.

## CI

- `.github/workflows/build.yml` runs pytest on every push and pull request, then builds and smoke-tests the standalone programs. See [Releases and Packaging](Releases-and-Packaging).
- `.github/workflows/wiki.yml` publishes `wiki/` to the GitHub wiki when it changes on `main`. Edit the pages in `wiki/`, never in the wiki itself.

The browser tests need `playwright`; with a preinstalled browser, set `CHROMIUM_PATH` to its executable.
