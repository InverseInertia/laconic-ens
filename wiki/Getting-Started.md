# Getting Started

## Ready-made programs

Windows and Linux programs are on the [releases page](https://github.com/inverseinertia/laconic-ens/releases). They need no Python install.

- **Windows:** download `lens-windows-x64.exe` and double-click it.
- **Linux:** download the installer script from the release and run it with `sh`. It fetches the program and icon from the latest release if they are not beside it, installs them for your user only (no root), adds LENS to your application menu, and removes any earlier install first.
  - Remove it again with `sh <installer> --uninstall`.
  - To install a program you already downloaded, keep `lens-linux-x64` and `lens-icon.png` in the same folder as the script.

Double-clicking the program opens the UI in an app window. It quits a few seconds after the window closes.

## From source

Needs Python 3.10 or newer.

```
pip install -e .[dev]
lens --serve --app                          # web UI in a Chromium app window
lens --serve --open                         # or in your default browser
lens examples/beam.lens                     # print results in the terminal
lens examples/beam.lens --tex beam.tex      # LaTeX document
lens examples/plots.lens --plots figures    # each plot as an SVG file
```

`python -m laconic` works too. `--port` changes the port (default 8765).

## Good to know

- The page serves KaTeX and the fonts from `laconic/static/`, so it works offline.
- Exported `.tex` files need siunitx v3 or newer (and `pgfplots` when a sheet has plots).
- Worksheets are UTF-8 text, conventionally `.lens`. The `examples/` folder has two to start from.
- In a normal browser tab Ctrl+T and Ctrl+N belong to the browser, so use Alt+T. `--app` opens a tab-less Chromium window, which may let Ctrl+T through (untested).
