# Context

Domain terms used in the code and docs. Short entries; each stands on its own.

## Front end

- **File handle**: the file a sheet was opened from or last saved to, as given by the browser's File System Access API. Only a `.lens` file gets one; a `.cs` or `.txt` file is read but never overwritten. Renaming the sheet drops it. See `laconic/static/savefile.js`.
- **Save / Save As**: Save writes to the file handle when there is one and the browser grants permission, and otherwise asks for a file. Save As always asks. Without the File System Access API, both download a copy.
- **Theme**: fonts, the color set and the editor paper style, kept in browser storage. See `laconic/static/theme.js`.
- **Preset**: a named color set (LENS blueprint, Engineering paper, White paper, Dark). Colors that match none are "Custom".
- **Readable theme**: one whose text and paper colors have a WCAG contrast ratio of at least 3:1. A stored theme that is not readable is replaced by the default colors on load, with a note.
- **Shortcut table**: the list of editor keys under Settings → Reference, kept as data in `laconic/static/shortcuts.js`. `wiki/Editor-Shortcuts.md` describes the same keys at more length; a test checks it mentions every Ctrl and Alt shortcut.
