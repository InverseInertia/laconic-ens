# Getting Started

## Ready-made programs

Windows and Linux programs are on the [releases page](https://github.com/inverseinertia/laconic-ens/releases). They need no Python install. Each file name carries the release's version, written `<version>` below (for example `lens-0.2.0-windows-x64.exe`).

- **Windows:** download `lens-<version>-windows-x64.exe` and double-click it.
  - To open `.lens` files by double-clicking them, with a file icon of their own, run `lens-<version>-windows-x64.exe --register-files` once from a command prompt. It changes settings for your user only (no administrator) and names the program by where it is, so run it again after moving the program. `--unregister-files` undoes it.
- **Linux:** download `lens-<version>-install-linux.sh` from the release and run it with `sh lens-<version>-install-linux.sh`. It fetches the program and icons of the same release if they are not beside it, installs them for your user only (no root), adds LENS to your application menu, makes `.lens` files open in LENS with an icon of their own, and removes any earlier install first.
  - Remove it again with `sh lens-<version>-install-linux.sh --uninstall`.
  - To install a program you already downloaded, keep `lens-<version>-linux-x64`, `lens-<version>-icon.png` and `lens-<version>-file-icon.png` from the same release in the same folder as the script.

Double-clicking the program opens the UI in an app window. It quits a few seconds after the window closes. Double-clicking a `.lens` file (once set up as above) opens that sheet, and **Save** writes back to it.

## From source

Needs Python 3.10 or newer. The dependencies include CoolProp and scipy.

```
pip install -e .[dev]
lens --serve --app                          # web UI in a Chromium app window
lens --serve --open                         # or in your default browser
lens laconic/examples/beam.lens                     # print results in the terminal
lens laconic/examples/beam.lens --tex beam.tex      # LaTeX document
lens laconic/examples/plots.lens --plots figures    # each plot as an SVG file
lens laconic/examples/solve.lens --solve            # run solver blocks that are out of date and store the results
```

`python -m laconic` works too. `--port` changes the port (default 8765).

## Good to know

- The page serves KaTeX and the fonts from `laconic/static/`, so it works offline.
- Exported `.tex` files need siunitx v3 or newer (and `pgfplots` when a sheet has plots).
- Worksheets are UTF-8 text, conventionally `.lens`. The examples (`laconic/examples/`) are bundled with the program: open them from the Welcome dialog, or copy them out with `lens --export-examples DIR`. The Linux installer also puts them in its install folder.
- **Save** (Ctrl+S) writes back to the file you opened or last saved, and **Save As** (Ctrl+Shift+S) asks for a new one. Renaming the sheet in the name box also makes the next Save ask. This needs the File System Access API (Chrome, Edge and other Chromium browsers); Firefox and Safari download a copy on every save instead. After a page reload the sheet text is restored but not its file, so the first Save asks again.
- If no browser window appears after `--open`, `--app` or starting the packaged app, open the address printed in the terminal by hand.
- In a normal browser tab Ctrl+T and Ctrl+N belong to the browser, so use Alt+T. `--app` opens a tab-less Chromium window, which may let Ctrl+T through (untested).
