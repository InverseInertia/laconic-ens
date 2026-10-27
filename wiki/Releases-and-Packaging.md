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
| `packaging/launcher.py` | entry point of the frozen build: with no arguments, or `--window [FILE]`, it hands the window (with FILE open) to a LENS already running, or else starts the server in an app window, on the first free port from 8765 so the browser's stored presets carry over, and quits when the window closes (see `laconic/instance.py`); with other arguments it is the normal CLI. It calls `multiprocessing.freeze_support()` because the solver worker is a spawned copy of the executable |
| `packaging/smoke.py` | starts the built program and checks the page (and, given a second argument, the version it shows), vendored assets, an evaluation, a plot SVG and a solver run |
| `packaging/icon.png` | executable icon on Windows and macOS (rendered from `laconic/static/logo.svg`) |
| `packaging/file-icon.png`, `file-icon.ico` | icon of a `.lens` file, drawn by `packaging/make_file_icon.py` from `icon.png`; the PNG is attached to releases as `lens-<version>-file-icon.png`, the ICO is bundled into the Windows build for `--register-files` (`laconic/fileassoc.py`) |
| `packaging/install-linux.sh` | per-user Linux installer with menu entry, the `application/x-laconic-lens` file type for `.lens` files, and `--uninstall` (which also deletes `~/.cache/laconic-lens`, the app window's browser profile); the launcher's `StartupWMClass=lens` matches the `--class=lens` LENS gives its app window, which is how the panel and window list show the running window with the LENS icon; attached to every release, unchanged, as `lens-install-linux.sh`. It asks the GitHub API for the latest release when it runs (`--release VERSION` picks another) and downloads that release's files unless they are already beside it; offline it installs the newest `lens-<version>-*` files beside it, and with unversioned `lens-linux-x64`, `lens-icon.png` and `lens-file-icon.png` beside it (a build of your own) it installs those without asking GitHub. It writes the installed version to `~/.local/share/laconic-lens/version`, so a second run says whether it updates or reinstalls. It has its own version number, `INSTALLER_VERSION` (see [Development](Development#the-linux-installers-version)) |

The logo source is `laconic/static/logo.svg` (header and browser tab).

On Linux the frozen program puts its bundled libraries on `LD_LIBRARY_PATH`. A browser that inherits that variable can fail to start (Firefox, issue #37), so `_launch` in `laconic/__main__.py` starts the browser with the user's original value, which the bootloader saves in `LD_LIBRARY_PATH_ORIG`. Any other program the frozen build starts needs the same environment (`_browser_env`).

## The `build` workflow

| Job | When | Does |
|---|---|---|
| `test` | every push and PR | `pytest` on Ubuntu, Python 3.12 |
| `binary` | after `test` | on a tag, stamps the version into `laconic/_version.py`; builds Windows and Linux (Ubuntu 22.04, for older glibc) programs and smoke-tests them, including that the page shows that version |
| `release` | on a `v*` tag | attaches the programs, the installer (`lens-install-linux.sh`, not stamped) and the two icons to a GitHub release, with the tag's section of `CHANGELOG.md` as its notes |
| `changelog` | after `release` | on main, turns `## Unreleased` in `CHANGELOG.md` into the tag's section (`packaging/stamp_changelog.py`) and pushes that |

## Release notes

`CHANGELOG.md` is the running changelog. Each pull request that changes what a user sees adds a line under `## Unreleased`; the `changelog` workflow fails a PR that changes `laconic/` or `packaging/` without touching it, unless the PR is labelled `no changelog`. On a tag, `packaging/release_notes.py` takes the tag's section (or `Unreleased`, if the changelog has none for the tag yet), adds a compare link to the previous tag, and the release job uses that as the release body. After the release, the `changelog` job gives the tag its section on main: `packaging/stamp_changelog.py` moves the entries that were under `## Unreleased` on the tagged commit to `## [v0.2.0](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.2.0) (date)`, dated the day of the release, and leaves anything merged since the tag under a new `## Unreleased` above it. It pushes that to main as `github-actions[bot]`; a tag that is not on main, or a changelog that already has the tag's section, is left alone.

## Cutting a release

Push a tag such as `v0.2.0` on main (`git tag v0.2.0 && git push origin v0.2.0`). The `## Unreleased` entries become the release notes, and the `changelog` job then renames that section in `CHANGELOG.md` for you, so there is nothing to edit first. Pull main afterwards to get that commit. The release job puts the tag's version, without the `v`, in every file name, so downloads of different releases do not overwrite each other: `lens-0.2.0-windows-x64.exe`, `lens-0.2.0-linux-x64`, `lens-0.2.0-icon.png` and `lens-0.2.0-file-icon.png`. The installer is the exception: it is `lens-install-linux.sh` in every release, and installs whichever release is latest when it runs.

## The version

`laconic/_version.py` is the one place the version is written. A source checkout says `0+dev`, which the page shows as `dev`. On a tag, the `binary` job rewrites that line with the tag's version (`v0.2.0` gives `0.2.0`) before it installs and freezes the program, so the release file names, the package metadata (`pyproject.toml` reads the version from that module) and the page all agree. The page shows it as `v0.2.0` beside the LENS title (hidden on a phone-width screen) and under the title in Help. The server writes it into the page in place of the `{{version}}` marker in `index.html`. It is an ordinary module, so PyInstaller bundles it with the rest of `laconic`.

Never commit a stamped version: the line stays `0+dev` in the repository.
