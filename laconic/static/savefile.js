/* Save and Open policy for worksheet files.
 *
 * Decides, without touching the page or the browser: whether a save reuses the
 * file the sheet came from or asks for a new one, what it is called, and when
 * it falls back to a download (no File System Access API, or a refused picker).
 * The page supplies the effects through an adapter and applies the outcome.
 * Runs under Node for tests.
 *
 *   stem(title)               file stem for a sheet title ("sheet" when blank)
 *   buttonTitle(handle)       tooltip for the Save button
 *   opened(fileName, handle)  {name, handle} for a file just opened
 *   save(as, io)              runs a save; resolves to its outcome
 *
 * io (the adapter):
 *   title              the sheet's name field
 *   current            the file handle of the sheet, or null
 *   permission(h)      resolves to "granted" or another state
 *   pick(suggested)    resolves to a new handle; null when the browser has no picker
 *   render()           resolves to the text to save (with unit definitions), or throws
 *   source             the editor text, used when render fails
 *   write(h, text)     writes the file
 *   download(name, text)
 *
 * Outcome: {kind: "saved", handle, name, message} | {kind: "downloaded", name}
 *        | {kind: "cancelled"} | {kind: "failed", message}
 */
(function (root) {
  'use strict';

  const EXT = /\.\w+$/;
  const stem = (title) => ((title || '').trim() || 'sheet').replace(EXT, '');

  const buttonTitle = (handle) => (handle ? `Save to ${handle.name} (Ctrl+S)` : 'Save the worksheet (Ctrl+S)');

  // A .cs or .txt file is only read; saving it writes a new .lens file instead of overwriting it.
  const opened = (fileName, handle = null) =>
    ({ name: fileName.replace(EXT, ''), handle: handle && /\.lens$/i.test(fileName) ? handle : null });

  async function save(as, io) {
    // Get the handle and its permission first: both need the click's user activation, which
    // rendering the text could outlast.
    let handle = as ? null : io.current;
    if (handle && (await io.permission(handle)) !== 'granted') handle = null;
    if (!handle && io.pick) {
      try {
        handle = await io.pick(stem(io.title) + '.lens');
      } catch (e) {
        if (e && e.name === 'AbortError') return { kind: 'cancelled' };
      }
    }
    let text = io.source;
    try { const t = await io.render(); if (typeof t === 'string') text = t; } catch {}
    if (!handle) {
      const name = stem(io.title) + '.lens';
      await io.download(name, text);
      return { kind: 'downloaded', name };
    }
    try {
      await io.write(handle, text);
    } catch (e) {
      return { kind: 'failed', message: `Could not save ${handle.name}: ${e.message}` };
    }
    return { kind: 'saved', handle, name: handle.name.replace(EXT, ''), message: `Saved ${handle.name}` };
  }

  const api = { stem, buttonTitle, opened, save };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.SaveFile = api;
})(typeof window !== 'undefined' ? window : globalThis);
