/* Plugins (#153, laconic/plugins.py): the pages that `!plugin name` blocks open.

   Each plugin runs in a frame sandboxed to scripts only (`sandbox="allow-scripts"`, and the server's
   Content-Security-Policy on its files), so it has no way into LENS but the messages below. The
   frames live in the plugin dialog for as long as their blocks are in the sheet; the dialog shows
   one of them at a time, and a block's row in the results shows the picture its plugin last sent.

     page -> plugin  {type: "lens:update", state, inputs, outputs, theme}
                     `state` is what the plugin last saved in its block's `#@ state` line, and is
                     left out when the sheet has not been run since the plugin's last write (so a
                     late answer cannot undo what the plugin just did); `inputs` are the values of
                     every `!pluginvar` line, [{name, unit, shape, mag}]; `outputs` the names its
                     block's lines define
     plugin -> page  {type: "lens:ready"}      ready for its first update
                     {type: "lens:write", state, outputs: {name: "expression"}}
                                               write these into its block (/api/pluginwrite)
                     {type: "lens:preview", svg}  the picture for its row, shown as an image

   Pure functions, also run under Node (tests/test_plugins.js):
     blocks(rows)   the plugin blocks among the eval rows: [{key, line, name, state, outputs}]; `key`
                    is the name and how many blocks of that name come before it (`pipenet#0`), so
                    a block keeps its frame when lines are added above it
     inputs(rows)   the values every `!pluginvar` row sends, in order (a later one of the same name wins)
     check(msg)     a message from a plugin, checked and cleaned, or null
     imageUrl(svg)  the data: URL a preview is shown from

   The page is the host: Plugins.init({text, edit, say, dialog, frames, title}) where
   `edit(text, edits)` makes server edits against `text` (false when the sheet has changed since). */
(function (root) {
  'use strict';

  // A plain variable name, as sheettext.is_name reads one (no ~ or $): a letter (or ∀), then letters,
  // digits, _ and ∞, then any of ` ! @ &. The server checks it again before it writes anything.
  const NAME = /^[\p{L}_∀][\p{L}\p{N}_∞∀]*[`!@&]*$/u;
  const MAX_SVG = 2000000;

  function blocks(rows) {
    const seen = new Map();
    return rows.filter((r) => r.kind === 'plugin' && r.plugin).map((r) => {
      const k = seen.get(r.plugin.name) || 0;
      seen.set(r.plugin.name, k + 1);
      return { key: `${r.plugin.name}#${k}`, line: r.n, name: r.plugin.name, state: r.plugin.state, outputs: r.plugin.outputs };
    });
  }

  function inputs(rows) {
    const out = new Map();
    for (const r of rows) {
      if (r.kind !== 'pluginvar' || !r.pluginvar) continue;
      for (const v of r.pluginvar.values) { out.delete(v.name); out.set(v.name, { ...v, stale: !!r.stale }); }
    }
    return [...out.values()];
  }

  function check(msg) {
    if (!msg || typeof msg !== 'object' || typeof msg.type !== 'string') return null;
    if (msg.type === 'lens:ready') return { type: 'lens:ready' };
    if (msg.type === 'lens:preview') {
      const svg = msg.svg;
      if (typeof svg !== 'string' || svg.length > MAX_SVG || !/^\s*(<\?xml[^>]*>\s*)?<svg[\s>]/.test(svg)) return null;
      return { type: 'lens:preview', svg };
    }
    if (msg.type === 'lens:write') {
      const state = msg.state === undefined ? null : msg.state;
      if (state !== null && (typeof state !== 'object' || Array.isArray(state))) return null;
      const outputs = {};
      const given = msg.outputs || {};
      if (typeof given !== 'object' || Array.isArray(given)) return null;
      for (const [name, expr] of Object.entries(given)) {
        if (!NAME.test(name) || typeof expr !== 'string' || /[\r\n]/.test(expr) || !expr.trim()) return null;
        outputs[name] = expr.trim();
      }
      return { type: 'lens:write', state, outputs };
    }
    return null;
  }

  const imageUrl = (svg) => 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);

  // ---- the page's side: frames, messages, the dialog --------------------------------------------
  const entries = new Map();   // key -> {key, name, line, frame, ready, manifest, error, preview, last, wroteAt, outputs}
  const manifests = new Map(); // name -> Promise of the manifest answer
  let host = null, current = null;

  function init(h) {
    host = h;
    root.addEventListener('message', onMessage);
  }

  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  };

  function theme() {
    const cs = getComputedStyle(document.body), out = {};
    for (const v of ['--paper', '--paper-deep', '--grid', '--text', '--text-soft', '--ink', '--on-ink', '--rule', '--err', '--sans', '--mono'])
      out[v.slice(2)] = cs.getPropertyValue(v).trim();
    return out;
  }

  function manifest(name, fresh) {
    if (fresh || !manifests.has(name)) {
      manifests.set(name, Api.json(`/api/plugins/${encodeURIComponent(name)}${fresh ? '?fresh=1' : ''}`, undefined, 'GET')
        .catch((e) => ({ ok: false, error: e.message })));
    }
    return manifests.get(name);
  }

  function frameFor(e) {
    const f = document.createElement('iframe');
    f.setAttribute('sandbox', 'allow-scripts');
    f.setAttribute('referrerpolicy', 'no-referrer');
    f.title = e.manifest.title || e.name;
    f.className = 'plugin-frame';
    f.dataset.key = e.key;
    f.hidden = current !== e.key;
    f.src = e.manifest.url;
    host.frames.append(f);
    return f;
  }

  async function load(e, fresh) {
    e.error = ''; e.ready = false;
    if (e.frame) { e.frame.remove(); e.frame = null; }
    const m = await manifest(e.name, fresh);
    if (entries.get(e.key) !== e) return;
    if (!m.ok) { e.error = m.error; paint(e); return; }
    e.manifest = m;
    e.frame = frameFor(e);
    paint(e);
  }

  function send(e) {
    if (!e.ready || !e.frame || !e.frame.contentWindow || !e.last) return;
    e.frame.contentWindow.postMessage({ type: 'lens:update', ...e.last, theme: theme() }, '*');
  }

  // After each run of the sheet: `rows` came from the text as it was at `startedAt` (performance.now()).
  function after(rows, startedAt = Infinity) {
    const found = blocks(rows), vals = inputs(rows), keep = new Set(found.map((b) => b.key));
    for (const [key, e] of entries) if (!keep.has(key)) { if (e.frame) e.frame.remove(); entries.delete(key); }
    for (const b of found) {
      let e = entries.get(b.key);
      if (!e || e.name !== b.name) {
        e = { key: b.key, name: b.name, line: b.line, frame: null, ready: false, manifest: null, error: '', preview: null, last: null, wroteAt: -Infinity };
        entries.set(b.key, e);
        load(e, false);
      }
      e.line = b.line;
      e.outputs = b.outputs;
      const update = { inputs: vals, outputs: b.outputs };
      if (startedAt > e.wroteAt) update.state = b.state;   // older rows than its last write: keep its own
      e.last = update;
      send(e);
    }
  }

  async function write(e, msg) {
    for (let tries = 0; tries < 3; tries++) {
      const text = host.text();
      let res;
      try {
        res = await Api.json('/api/pluginwrite', { text, line: e.line, state: msg.state, outputs: msg.outputs });
      } catch (err) { host.say(`The ${e.name} plugin could not write to the sheet: ${err.message}`); return; }
      if (!res.ok) { host.say(`The ${e.name} plugin could not write to the sheet: ${res.error}`); return; }
      if (host.edit(text, res.edits)) { e.wroteAt = performance.now(); return; }
      // the sheet changed meanwhile: ask again against the new text (the block is found by its line)
    }
  }

  function onMessage(ev) {
    let e = null;
    for (const x of entries.values()) if (x.frame && ev.source === x.frame.contentWindow) e = x;
    if (!e) return;
    const msg = check(ev.data);
    if (!msg) return;
    if (msg.type === 'lens:ready') { e.ready = true; send(e); paint(e); }
    else if (msg.type === 'lens:preview') { e.preview = imageUrl(msg.svg); paint(e); }
    else if (msg.type === 'lens:write') write(e, msg);
  }

  function open(key) {
    const e = entries.get(key);
    if (!e) return;
    current = key;
    for (const x of entries.values()) if (x.frame) x.frame.hidden = x.key !== key;
    host.title.textContent = e.manifest ? `${e.manifest.title}` : e.name;
    if (!host.dialog.open) host.dialog.showModal();
    if (e.frame) e.frame.focus();
  }

  function reload(key) {
    const e = entries.get(key);
    if (e) { e.preview = null; load(e, true); }
  }

  // The body of a `!plugin` row: the plugin's picture, what it is doing, and Open.
  function build(r, rows) {
    const b = blocks(rows || [r]).find((x) => x.line === r.n);
    const key = b ? b.key : `${r.plugin.name}#0`;
    const box = el('div', 'plugin-box');
    box.dataset.key = key;
    fill(box, entries.get(key), r);
    return box;
  }

  function fill(box, e, r) {
    box.replaceChildren();
    const name = r ? r.plugin.name : e.name, key = box.dataset.key;
    if (e && e.preview) {
      const img = el('img', 'plugin-preview');
      img.src = e.preview; img.alt = `The ${name} plugin's drawing`;
      img.onclick = (ev) => { ev.stopPropagation(); open(key); };
      box.append(img);
    }
    const tools = el('div', 'plugin-tools');
    const say = el('span', 'plugin-status' + (e && e.error ? ' err' : ''),
      !e ? 'Starting…' : e.error ? e.error : !e.manifest ? `Fetching the ${name} plugin…` : !e.ready ? 'Loading…'
        : e.manifest.version ? `${e.manifest.title} ${e.manifest.version}` : e.manifest.title);
    const openBtn = el('button', '', 'Open');
    openBtn.disabled = !e || !e.frame;
    openBtn.onclick = (ev) => { ev.stopPropagation(); open(key); };
    const again = el('button', '', e && e.error ? 'Try again' : 'Reload');
    again.title = 'Fetch the plugin again';
    again.onclick = (ev) => { ev.stopPropagation(); reload(key); };
    tools.append(openBtn, again, say);
    box.append(tools);
  }

  function paint(e) {
    for (const box of document.querySelectorAll(`.plugin-box[data-key="${CSS.escape(e.key)}"]`)) fill(box, e, null);
  }

  const api = { blocks, inputs, check, imageUrl, init, after, build, open, reload, get current() { return current; } };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Plugins = api;
})(typeof window !== 'undefined' ? window : globalThis);
