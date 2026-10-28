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
| `node tests/test_sheettext.js` | the editor's lexer against the shared vectors |
| `node tests/test_savefile.js` | which file Save and Save As write, and the download fallback |
| `node tests/test_theme.js` | theme loading, contrast check, presets |
| `node tests/test_shortcuts.js` | the shortcut table, and that the wiki lists its Ctrl/Alt keys |
| `node tests/test_layout.js` | when the page stacks or goes side by side, and when it offers to stop switching |
| `node tests/test_rows.js` | the row model: what the results pane shows for each kind of line |
| `node tests/test_mathfit.js` | when a formula too wide for its room is shrunk or wrapped (the drawing is tested in Chromium) |
| `node tests/test_unitbrowser.js` | the units dialog: search, tag filters, adding and removing your tags |
| `python tests/stress/run_solver_stress.py` | about 35 heavy solver cases (Rosenbrock up to 100 variables, a 1000-equation system, CoolProp inside residuals, Hock-Schittkowski 71, timeouts) through the worker process |

| File | Covers |
|---|---|
| `test_laconic.py`, `test_units.py` | evaluation, LaTeX, custom units |
| `test_plots.py`, `test_props.py`, `test_rename.py`, `test_server.py`, `test_lifecycle.py` | one module each |
| `test_sheettext.py`, `sheettext_vectors.json` | line kinds, blocks, spans and tokens; the vectors are shared with `test_sheettext.js` |
| `test_lineresult.py` | the line result interface, the block lookups, and the contract on the `/api/eval` row shape (it also runs `rows.js` over real rows) |
| `test_editing_node.py` | runs the Node suites from pytest |
| `test_solver.py`, `test_solverjobs.py` | solver blocks and the worker process |
| `test_install_linux.py` | `packaging/install-linux.sh` run in a throwaway home folder with a stand-in program and a stand-in `curl` serving fake releases: the launcher it writes, what `--uninstall` removes, installing and updating to the latest release, `--release`, what it does offline or when a download fails, stopping a LENS still running from the install folder, and installer 1.0.0 updating through `packaging/v1-bridge.sh` |
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
- **A field on the eval rows:** add it to `LineResult` (or to a payload, if only one kind has it) and to `to_json`, update the expected shape in `test_lineresult.py`, and read it in `rows.js` (or the payload's own reader: `plotview.js`, `solverview.js`).
- **A physical constant:** add a line to `CONSTANTS` in `catalogue.py`: the spelling a sheet types, what it is, and `None` when Pint already knows that spelling (`'R`, `'c`). For a spelling Pint lacks, the third item is the Pint definition that adds it: `"@alias planck_constant = h_P"` for another name of a Pint constant, or `"Av = avogadro_number"` for a new unit with its own symbol. The editor's suggestions, the *constants* tag in the units dialog and the "show its value" rule pick it up from there. Add its row to the table in [Units](Units), and its value to `test_the_constants_have_their_codata_values` in `tests/test_units.py`.
- **A standard unit tag:** add it to `STANDARD_TAGS` in `unittags.py`, as a list of unit spellings and Pint dimensions in brackets (`"[pressure]"`); the order there is the order of the dialog's tag buttons. Add a unit to an existing tag the same way. List the tag in [Units](Units).
- **A unit that needs special handling** (its own dimension, a reduction rule, an export spelling, an error or hint): add it to the unit catalogue, `catalogue.py`. A currency is one entry in `CURRENCIES`.

## The Linux installer's version

`packaging/install-linux.sh` has a version of its own, numbered apart from LENS's: the `INSTALLER_VERSION="X.Y.Z"` line near its top, the one place it is written (`--version` prints it, and it shows in the installer's output). The script looks up the latest LENS release on GitHub when it runs, so it no longer needs a new copy for each LENS release, and its version changes only when the script does.

- Bump `INSTALLER_VERSION` in the same PR as any change to the script: the major number for a change in its options, in where it installs or in the release files it reads, the minor for a new feature, the patch for a fix. A test checks the line is there and that `--version` prints it.
- The release file name carries the major number (`lens-install-linux-v2.sh` for 2.x.y): a new major version gets a new name in the `release` job of `build.yml` and in the docs, so a link to an older installer cannot fetch one that no longer matches the release files.
- After that PR merges, tag the merge commit `installer-vX.Y.Z` (`git tag installer-v1.1.0 && git push origin installer-v1.1.0`). The tag only marks which script that version is: the `build` workflow runs on `v*` tags, so it ignores it, and `release_notes.py` skips it when it finds the previous release for the compare link.
- Copies of an older major version keep working through a bridge: installer 1.x downloads `lens-<version>-linux-x64`, the single-file program releases no longer have, so each release attaches `packaging/v1-bridge.sh` under that name, with the release's version stamped in. Installer 1.x installs it as the program and runs it with `--export-examples`; it then runs installer 2 for that release, which replaces it with the real program, and runs the program with the same arguments (#101). `tests/install-linux-1.0.0.sh` is installer 1.0.0 as v0.3.6 shipped it, for the test of that path. A new major version that changes the release files needs a bridge of its own.
- Each LENS release attaches the script as it is on the tagged commit, unstamped, as `lens-install-linux-v2.sh`. The name carries no LENS version, so `https://github.com/inverseinertia/laconic-ens/releases/latest/download/lens-install-linux-v2.sh` is always the newest installer.

## CI

- `.github/workflows/build.yml` runs pytest on every push and pull request, then builds and smoke-tests the standalone programs. See [Releases and Packaging](Releases-and-Packaging).
- `.github/workflows/changelog.yml` fails a pull request that changes `laconic/` or `packaging/` without adding to `## Unreleased` in `CHANGELOG.md`, unless it is labelled `no changelog`.
- `.github/workflows/wiki.yml` publishes `wiki/` to the GitHub wiki when it changes on `main`. Edit the pages in `wiki/`, never in the wiki itself.

The browser tests need `playwright`; with a preinstalled browser, set `CHROMIUM_PATH` to its executable.
