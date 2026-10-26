// Run with: node tests/test_savefile.js
const assert = require('assert');
const S = require('../laconic/static/savefile.js');
let n = 0;
function eq(a, b, label) { assert.deepStrictEqual(a, b, label); n++; }

// A fake browser: handles are {name}; every effect is logged in order, so the tests can
// check both what was written where and that the permission and picker came first.
function browser({ current = null, permission = 'granted', picker = true, pickName = 'copy.lens', pickError = null,
  render = (src) => src + '\n# saved', writeError = null } = {}) {
  const log = [];
  const io = {
    title: 'beam', current, source: 'x = 3',
    permission: async (h) => { log.push(['permission', h.name]); return permission; },
    pick: picker ? async (suggested) => { log.push(['pick', suggested]); if (pickError) throw pickError; return { name: pickName }; } : null,
    render: async () => { log.push(['render']); return render(io.source); },
    write: async (h, text) => { log.push(['write', h.name, text]); if (writeError) throw writeError; },
    download: async (name, text) => { log.push(['download', name, text]); },
  };
  return { io, log };
}
const abort = Object.assign(new Error('cancelled'), { name: 'AbortError' });

(async () => {
  // Save reuses the opened file without asking where.
  {
    const { io, log } = browser({ current: { name: 'beam.lens' } });
    const r = await S.save(false, io);
    eq(r.kind, 'saved', 'save to the current file');
    eq([r.name, r.message], ['beam', 'Saved beam.lens'], 'name and message from the file');
    eq(log, [['permission', 'beam.lens'], ['render'], ['write', 'beam.lens', 'x = 3\n# saved']], 'no picker, server text written');
  }
  // Save As always asks, even with a current file.
  {
    const { io, log } = browser({ current: { name: 'beam.lens' } });
    const r = await S.save(true, io);
    eq([r.kind, r.handle.name, r.name], ['saved', 'copy.lens', 'copy'], 'save as writes the picked file');
    eq(log[0], ['pick', 'beam.lens'], 'save as goes straight to the picker, suggesting the title');
  }
  // No file yet: Save asks.
  {
    const { io, log } = browser();
    await S.save(false, io);
    eq(log.map((e) => e[0]), ['pick', 'render', 'write'], 'first save picks, then renders, then writes');
  }
  // Permission refused: ask for a new file instead of writing the old one.
  {
    const { io, log } = browser({ current: { name: 'beam.lens' }, permission: 'denied' });
    const r = await S.save(false, io);
    eq([r.kind, r.handle.name], ['saved', 'copy.lens'], 'refused permission falls back to the picker');
    eq(log.map((e) => e[0]), ['permission', 'pick', 'render', 'write'], 'permission and picker come before render');
  }
  // Cancelling the picker saves nothing.
  {
    const { io, log } = browser({ pickError: abort });
    eq(await S.save(false, io), { kind: 'cancelled' }, 'cancelled picker');
    eq(log.length, 1, 'nothing rendered or written after a cancel');
  }
  // A picker that fails for another reason falls back to a download.
  {
    const { io, log } = browser({ pickError: new Error('SecurityError') });
    eq(await S.save(false, io), { kind: 'downloaded', name: 'beam.lens' }, 'picker failure downloads');
    eq(log.at(-1), ['download', 'beam.lens', 'x = 3\n# saved'], 'download carries the rendered text');
  }
  // No File System Access API: every save is a download, and the current file is ignored.
  {
    const { io, log } = browser({ picker: false });
    io.title = '  ';
    eq(await S.save(true, io), { kind: 'downloaded', name: 'sheet.lens' }, 'blank title downloads as sheet.lens');
    eq(log.map((e) => e[0]), ['render', 'download'], 'no picker, no permission');
  }
  // Render failure (server down, or an error status) saves the editor text as it is.
  {
    const { io, log } = browser({ current: { name: 'a.lens' }, render: () => { throw new Error('offline'); } });
    await S.save(false, io);
    eq(log.at(-1), ['write', 'a.lens', 'x = 3'], 'render throws: source text');
    const b = browser({ current: { name: 'a.lens' }, render: () => null });
    await S.save(false, b.io);
    eq(b.log.at(-1), ['write', 'a.lens', 'x = 3'], 'render gives nothing: source text');
  }
  // A failed write reports and keeps the file unchanged.
  {
    const { io } = browser({ current: { name: 'a.lens' }, writeError: new Error('disk full') });
    eq(await S.save(false, io), { kind: 'failed', message: 'Could not save a.lens: disk full' }, 'write failure');
  }

  // Names.
  eq(S.stem('beam.lens'), 'beam', 'stem drops the extension');
  eq(S.stem(''), 'sheet', 'empty title');
  eq(S.stem(undefined), 'sheet', 'no title');
  eq(S.stem(' notes '), 'notes', 'trimmed');
  eq(S.buttonTitle(null), 'Save the worksheet (Ctrl+S)', 'button title without a file');
  eq(S.buttonTitle({ name: 'beam.lens' }), 'Save to beam.lens (Ctrl+S)', 'button title names the file');

  // Opening: only a .lens file is written back to.
  const h = { name: 'x' };
  eq(S.opened('beam.lens', h), { name: 'beam', handle: h }, '.lens keeps its handle');
  eq(S.opened('BEAM.LENS', h), { name: 'BEAM', handle: h }, 'extension case');
  eq(S.opened('old.cs', h), { name: 'old', handle: null }, '.cs is read only');
  eq(S.opened('notes.txt', h), { name: 'notes', handle: null }, '.txt is read only');
  eq(S.opened('beam.lens'), { name: 'beam', handle: null }, 'no handle (file input)');

  console.log(`savefile: ${n} checks passed`);
})().catch((e) => { console.error(e); process.exit(1); });
