# Settings

Open **Settings** from the header. It holds:

- **Reference:** the list of keys.
- **Greek letters:** the table behind Ctrl+G.
- **Global units:** units available in every sheet (see [Units](Units)). Nothing is stored unless every definition is valid.
- **Theme:** colors (including the color global variables are marked in), fonts and paper style. Presets: LENS blueprint (default), Engineering paper, White paper, Dark. The default monospace font is OCR-A. A saved theme whose text is unreadable on its paper is discarded at load, with a popup saying so.

## Where things are stored

| Setting | Stored |
|---|---|
| Greek table, global units | on the machine running LENS, in `settings.json`, so they are the same in every browser and for the command line |
| Theme, output view, wrapper, split position, line wrapping, the Math keys, Mark globals and Suggest checkboxes, and the unsaved worksheet text | in the browser (`localStorage`), per browser |

A Greek table saved in the browser by an earlier build is copied to the server the first time the page loads.

## The settings file

| System | Location |
|---|---|
| Linux | `$XDG_CONFIG_HOME/laconic/settings.json`, or `~/.config/laconic/settings.json` |
| macOS | `~/Library/Application Support/laconic/settings.json` |
| Windows | `%APPDATA%\laconic\settings.json` |

`LENS_CONFIG_DIR` overrides the directory. The file is JSON, written atomically, and a missing or unreadable file means defaults.
