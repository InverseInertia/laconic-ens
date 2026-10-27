# Getting Started

## Ready-made programs

Windows and Linux programs are on the [releases page](https://github.com/inverseinertia/laconic-ens/releases). They need no Python install. Each file name carries the release's version, written `<version>` below (for example `lens-0.2.0-windows-x64-setup.exe`).

- **Windows:** download `lens-<version>-windows-x64-setup.exe` and run it. The wizard installs LENS for your user only (no administrator) in `%LOCALAPPDATA%\Programs\LENS`, adds it to the Start menu (and, if you tick the box, the desktop), makes `.lens` files open in LENS with an icon of their own (a box you can untick), and puts the example worksheets in an `examples` folder there, with a Start menu entry for them.
  - Running the installer of a newer release updates LENS in place; it closes a running LENS first.
  - Remove it under Settings → Apps (or Add or remove programs). Your settings in `%APPDATA%\laconic` are kept.
  - Windows may warn that the installer is from an unknown publisher, since it is not code-signed: choose **More info → Run anyway**.
- **Linux:** download `lens-install-linux.sh` from the [latest release](https://github.com/inverseinertia/laconic-ens/releases/latest/download/lens-install-linux.sh) and run it with `sh lens-install-linux.sh`. It looks up the latest release on GitHub, downloads its program and icons, installs them for your user only (no root), adds LENS to your application menu, makes `.lens` files open in LENS with an icon of their own, and removes any earlier install first. Run it again at any time to update to the latest release.
  - `sh lens-install-linux.sh --release 0.3.5` installs that release instead; `--version` prints the installer's own version.
  - Remove it again with `sh lens-install-linux.sh --uninstall`. That also removes the app window's browser profile (below).
  - To install a program you already downloaded, keep `lens-<version>-linux-x64.tar.gz`, `lens-<version>-icon.png` and `lens-<version>-file-icon.png` from the same release in the same folder as the script. If GitHub can't be reached, the script installs the newest release it finds there.

Double-clicking the program opens the UI in an app window. It quits a few seconds after the window closes. On Linux the window is a Chromium app window running in a browser profile of its own, kept in `~/.cache/laconic-lens/browser`, so the panel and window list show it as LENS with the LENS icon rather than as another browser window; it does not share the extensions, logins or history of your everyday browser. With no Chromium-family browser installed, LENS opens in a tab of your default browser instead, and that tab shows as the browser. Double-clicking a `.lens` file (once set up as above) opens that sheet, and **Save** writes back to it.

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
