# Releases and Packaging

## Standalone builds

```
pip install pyinstaller pillow
pyinstaller packaging/lens.spec        # produces dist/lens (lens.exe on Windows)
```

PyInstaller does not cross-compile, so build on each target OS. The result needs no Python install.

| File | Role |
|---|---|
| `packaging/lens.spec` | PyInstaller spec |
| `packaging/launcher.py` | entry point of the frozen build: with no arguments it starts the server on a free port in an app window and quits when the window closes; with arguments it is the normal CLI |
| `packaging/smoke.py` | starts the built program and checks the page, vendored assets, an evaluation and a plot SVG |
| `packaging/icon.png` | executable icon on Windows and macOS (rendered from `laconic/static/logo.svg`) |
| `packaging/install-linux.sh` | per-user Linux installer with menu entry and `--uninstall` |

The logo source is `laconic/static/logo.svg` (header and browser tab).

## The `build` workflow

| Job | When | Does |
|---|---|---|
| `test` | every push and PR | `pytest` on Ubuntu, Python 3.12 |
| `binary` | after `test` | builds Windows and Linux (Ubuntu 22.04, for older glibc) programs and smoke-tests them |
| `release` | on a `v*` tag | attaches the programs, the installer and the icon to a GitHub release |

## Cutting a release

Push a tag such as `v0.2.0`. The release job publishes `lens-windows-x64.exe`, `lens-linux-x64`, the installer script and `lens-icon.png`.
