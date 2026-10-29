# Settings

Open **Settings** from the header. It holds:

- **Reference:** the list of keys.
- **Layout:** side by side (editor left, results right) or stacked (results on top, editor below). Alt+L switches between them at any time. With **Switch automatically when the window is narrow** on (the default), the page stacks when the window is 760 px wide or less and goes back to side by side when it widens; a view picked by hand holds until the next such switch. Turn it off and the view you pick always stays. If the layout switches itself six times in one session, a small note in the corner offers to turn automatic switching off: **Layout settings** opens this section, **Don't ask again** stops the note for good, and it can simply be ignored.
- **Updates:** with **Check for a new release when LENS starts** on (the default), LENS asks GitHub once each time it starts whether a newer release is out, in the background, and if there is one shows a small button with the new version beside the version in the header. Clicking it shows the release's notes and an **Update** button that runs the installer (see [Getting Started](Getting-Started#updating)). Offline, nothing is shown. Turn it off and LENS never asks.
- **Extended characters:** the table behind Ctrl+G: Greek letters, and other characters such as ∞ and ∀.
- **Global units:** units available in every sheet (see [Units](Units)). Nothing is stored unless every definition is valid.
- **Theme:** colors (including the colors global variables and symbols are marked in; symbols are bright cyan in every preset), fonts, text size and paper style. **Text size** (80% to 200%) scales the editor's and the results' text and the rows they line up on; the toolbar and dialogs keep their size. Presets: LENS blueprint (default), Engineering paper, White paper, Dark, Canoe Dark, Chalcedony Dark, Codec. **Share as YAML** exports the theme as a YAML snippet (copied to the clipboard) and imports one pasted back in; a snippet with an unknown field or unreadable colors is refused with a popup saying why. The default monospace font is OCR-A. A saved theme whose text is unreadable on its paper is discarded at load, with a popup saying so.

## Where things are stored

| Setting | Stored |
|---|---|
| Extended characters, global units, your unit tags (Units dialog) | on the machine running LENS, in `settings.json`, so they are the same in every browser and for the command line |
| Theme, output view, wrapper, line wrapping, layout and automatic switching, the Math keys, Mark globals and Suggest checkboxes, the update check | on the machine running LENS, in `settings.json`, so they are the same in every browser and whatever port LENS runs on. Values an older build kept in the browser are moved there the first time the page opens |
| Split position and the unsaved worksheet text | in the browser (`localStorage`), per browser and per port |

An extended-character table saved in the browser by an earlier build is copied to the server the first time the page loads.

## The settings file

| System | Location |
|---|---|
| Linux | `$XDG_CONFIG_HOME/laconic/settings.json`, or `~/.config/laconic/settings.json` |
| macOS | `~/Library/Application Support/laconic/settings.json` |
| Windows | `%APPDATA%\laconic\settings.json` |

`LENS_CONFIG_DIR` overrides the directory. The file is JSON, written atomically, and a missing or unreadable file means defaults.
