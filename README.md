# LENS: Laconic Engineering Notebook System

Laconic (LENS for short) is a units-aware worksheet on top of Pint. Type one expression per
line, see typeset results update as you edit, and copy LaTeX snippets or export a document.
Worksheets are plain text files (`.lens`), so they work with git.

```
L = 4.5'm
w = 12'kN / 'm
M_max = w * L^2 / 8 -> 'kN * 'm      # 30.38 kN·m
```

Units carry an apostrophe (`'kN`), so a bare name is always a variable. The same engine drives the web
page, the LaTeX export and the command line. It also does matrices, fluid properties (CoolProp),
plots, and equation solving and optimization (scipy).

## Download and install

Ready-made programs for Windows and Linux are on the
[releases page](https://github.com/inverseinertia/laconic-ens/releases). They need no Python install.

- **Windows:** download `lens-windows-x64.exe` and double-click it. To open `.lens` files by
  double-clicking them, run `lens-windows-x64.exe --register-files` once (`--unregister-files` undoes it).
- **Linux:** download `lens-install-linux.sh` and run it (`sh lens-install-linux.sh`). It installs LENS for
  your user only (no root), adds it to your application menu and makes `.lens` files open in it.
  `sh lens-install-linux.sh --uninstall` removes it.
- **From source** (Python 3.10 or newer), for the command-line tool and for development:

      pip install -e .[dev]
      lens --serve --app                # web UI in a Chromium app window
      lens --serve --open               # or in your default browser
      lens laconic/examples/beam.lens           # print results in the terminal
      lens laconic/examples/beam.lens --tex beam.tex
      lens laconic/examples/beam.lens --md beam.md   # Markdown note for Obsidian
      lens laconic/examples/plots.lens --plots figures    # each plot as an SVG file
      lens laconic/examples/solve.lens --solve  # run solver blocks that are out of date

`python -m laconic` works too. The web page serves its fonts and KaTeX from the package, so it works
offline. Exported `.tex` needs siunitx v3 or newer.

## Documentation

The [wiki](https://github.com/inverseinertia/laconic-ens/wiki) is the reference:

| | |
|---|---|
| [Getting Started](https://github.com/inverseinertia/laconic-ens/wiki/Getting-Started) | install, run, command line |
| [Worksheet Syntax](https://github.com/inverseinertia/laconic-ens/wiki/Worksheet-Syntax) | names, operators, functions, commands |
| [Units](https://github.com/inverseinertia/laconic-ens/wiki/Units) | SI display, custom and global units |
| [Matrices](https://github.com/inverseinertia/laconic-ens/wiki/Matrices) · [Material Properties](https://github.com/inverseinertia/laconic-ens/wiki/Material-Properties) · [Plots](https://github.com/inverseinertia/laconic-ens/wiki/Plots) · [Solving and Optimizing](https://github.com/inverseinertia/laconic-ens/wiki/Solving-and-Optimizing) | the feature pages |
| [Output and Export](https://github.com/inverseinertia/laconic-ens/wiki/Output-and-Export) · [Editor Shortcuts](https://github.com/inverseinertia/laconic-ens/wiki/Editor-Shortcuts) · [Settings](https://github.com/inverseinertia/laconic-ens/wiki/Settings) | using the app |
| [Architecture](https://github.com/inverseinertia/laconic-ens/wiki/Architecture) · [Development](https://github.com/inverseinertia/laconic-ens/wiki/Development) · [Releases and Packaging](https://github.com/inverseinertia/laconic-ens/wiki/Releases-and-Packaging) · [Roadmap](https://github.com/inverseinertia/laconic-ens/wiki/Roadmap) | contributing |

The wiki's source is the [`wiki/`](wiki) folder. Edit it there in a pull request; a workflow publishes it
to the wiki when it reaches `main`, and edits made in the wiki itself are overwritten.

## Tests

    python -m pytest -q           # Python, plus the Node suites if node is installed

Browser tests need `playwright` and are skipped without it; see
[Development](https://github.com/inverseinertia/laconic-ens/wiki/Development).
