/* Plugins (#153, laconic/plugins.py): the pages that `!plugin name` blocks open.

   Each plugin runs in a frame sandboxed to scripts only (`sandbox="allow-scripts"`, and the server's
   Content-Security-Policy on its files), so it has no way into LENS but the messages below. The
   frames live in the plugin dialog for as long as their blocks are in the sheet; the dialog shows
   one of them at a time, and a block's row in the results shows the picture its plugin last sent.

     page -> plugin  {type: "lens:theme", theme}  the page's colours and fonts changed (Settings)
                     {type: "lens:update", state, inputs, outputs, theme}
                     `state` is what the plugin last saved in its block's `#@ state` line, and is
                     left out when the sheet has not been run since the plugin's last write (so a
                     late answer cannot undo what the plugin just did); `inputs` are the values of
                     every `!pluginvar` line, [{name, unit, shape, mag}]; `outputs` the names its
                     block's lines define; `overridden` [{name, line}] the lines outside its block that
                     define one of them again, replacing the plugin's value; `theme` the page's THEME
                     variables, without their `--`
     plugin -> page  {type: "lens:ready"}      ready for its first update
                     {type: "lens:write", state, outputs: {name: "expression"}}
                                               write these into its block (/api/pluginwrite)
                     {type: "lens:preview", svg}  the picture for its row, shown as an image
                     {type: "lens:open-template"}  open the sheet the plugin ships, in place of this
                                               one (the page asks the user first)
     page -> plugin  {type: "lens:check", missing, changed}  for a plugin that ships a sheet, after
                     each run: what of that sheet this one lacks or has changed (plugins.differences)

   Pure functions, also run under Node (tests/test_plugins.js):
     blocks(rows)   the plugin blocks among the eval rows: [{key, line, name, state, outputs}]; `key`
                    is the name and how many blocks of that name come before it (`pipenet#0`), so
                    a block keeps its frame when lines are added above it
     inputs(rows)   the values every `!pluginvar` row sends, in order (a later one of the same name wins)
     check(msg)     a message from a plugin, checked and cleaned, or null
     imageUrl(svg)  the data: URL a preview is shown from

   Settings → Plugins is drawn by settings(box): installed plugins (Update, Remove), the source's
   others (Install), an install by name, and Install from a folder (a plugin on this computer, sent
   to /api/pluginupload); install(name), installFolder(files) and remove(name) do the work.
     folderFiles(list)  a picked folder's name and its own files, by file name (pure)

   The page is the host: Plugins.init({text, edit, say, dialog, frames, title, auto, openSheet}) where
   `edit(text, edits)` makes server edits against `text` (false when the sheet has changed since). */
(function (root) {
  'use strict';

  // A plain variable name, as sheettext.is_name reads one (no ~ or $): a letter (or ∀), then letters,
  // digits, _ and ∞, then any of ` ! @ &. The server checks it again before it writes anything.
  const NAME = /^[\p{L}_∀][\p{L}\p{N}_∞∀]*[`!@&]*$/u;
  const MAX_SVG = 2000000;

  // The page's theme variables a plugin is given (index.html :root, theme.js): colours and fonts.
  const THEME = ['--paper', '--paper-deep', '--grid', '--text', '--text-soft', '--ink', '--on-ink', '--rule', '--err',
    '--global', '--symbol', '--hit', '--hl', '--on-hl', '--sans', '--mono'];

  function blocks(rows) {
    const seen = new Map();
    return rows.filter((r) => r.kind === 'plugin' && r.plugin).map((r) => {
      const k = seen.get(r.plugin.name) || 0;
      seen.set(r.plugin.name, k + 1);
      return { key: `${r.plugin.name}#${k}`, line: r.n, name: r.plugin.name, state: r.plugin.state, outputs: r.plugin.outputs,
               overridden: r.plugin.overridden || [] };
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
    if (msg.type === 'lens:open-template') return { type: 'lens:open-template' };
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
    for (const v of THEME) out[v.slice(2)] = cs.getPropertyValue(v).trim();
    return out;
  }

  // The theme changed (Settings): every plugin gets it at once, in a message of its own, so a plugin
  // is never handed an older state along with it.
  function retheme() {
    const t = theme();
    for (const e of entries.values())
      if (e.ready && e.frame && e.frame.contentWindow) e.frame.contentWindow.postMessage({ type: 'lens:theme', theme: t }, '*');
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
    e.notInstalled = !m.ok && !!m.notInstalled;
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
      const update = { inputs: vals, outputs: b.outputs, overridden: b.overridden };
      if (startedAt > e.wroteAt) update.state = b.state;   // older rows than its last write: keep its own
      e.last = update;
      send(e);
      checkSheet(e);
    }
  }

  // A plugin that ships its own sheet is told after each run which of that sheet's lines this one has
  // changed or lost (/api/plugins/{name}/check), so it can warn of a line deleted by accident.
  async function checkSheet(e) {
    if (!e.manifest || !e.manifest.template || !e.ready) return;
    const text = host.text(), mine = (e.checking = (e.checking || 0) + 1);
    let res;
    try { res = await Api.json(`/api/plugins/${encodeURIComponent(e.name)}/check`, { text }); } catch { return; }
    if (mine !== e.checking || !res.ok || !e.frame || !e.frame.contentWindow) return;
    e.frame.contentWindow.postMessage({ type: 'lens:check', missing: res.missing, changed: res.changed }, '*');
  }

  // Open a plugin's own sheet in place of this one, as an example opens (the page asks first).
  async function openTemplate(name) {
    let text;
    try { text = await Api.text(`/api/plugins/${encodeURIComponent(name)}/template`); }
    catch (err) { host.say(err.message); return; }
    host.openSheet(text, name);
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
    if (msg.type === 'lens:ready') { e.ready = true; send(e); paint(e); checkSheet(e); }
    else if (msg.type === 'lens:open-template') openTemplate(e.name);
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

  // ---- installing and removing (a block's Install button, and Settings → Plugins) --------------
  // Installing is the user's own request, so it fetches whether or not sheets may (`autoPlugins`).
  async function install(name) {
    let res;
    try { res = await Api.json(`/api/plugins/${encodeURIComponent(name)}/install`, {}); }
    catch (err) { res = { ok: false, error: err.message }; }
    if (!res.ok) { host.say(res.error); return false; }
    manifests.delete(name);
    for (const e of entries.values()) if (e.name === name) { e.preview = null; load(e, false); }
    host.say(`Installed ${res.title}${res.version ? ' ' + res.version : ''}`);
    return true;
  }

  // The files of a folder the user picked (an <input webkitdirectory>'s files, each with its
  // `webkitRelativePath`, "pipenet/app.js"): the folder's name and its own files, not those in folders below.
  function folderFiles(list) {
    const files = new Map();
    let name = null;
    for (const f of list) {
      const parts = (f.webkitRelativePath || f.name).split('/');
      if (parts.length > 2) continue;
      if (parts.length === 2) name = parts[0];
      files.set(parts[parts.length - 1], f);
    }
    return { name, files };
  }

  const base64 = async (file) => {
    const bytes = new Uint8Array(await file.arrayBuffer());
    let s = '';
    for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return btoa(s);
  };

  // Install the plugin in a folder the user picked: its manifest and the files it lists go to the
  // server, which checks them and keeps the plugin (a plugin not on GitHub, or one being written).
  async function installFolder(list) {
    const { name, files } = folderFiles(list);
    const man = files.get('manifest.json');
    if (!man) { host.say('That folder has no manifest.json, so it is not a plugin'); return false; }
    let listed = [];
    try { listed = JSON.parse(await man.text()).files || []; } catch { host.say("That folder's manifest.json is not JSON"); return false; }
    const body = { name, files: {} };
    for (const f of ['manifest.json', ...listed]) if (typeof f === 'string' && files.has(f)) body.files[f] = await base64(files.get(f));
    let res;
    try { res = await Api.json('/api/pluginupload', body); } catch (err) { res = { ok: false, error: err.message }; }
    if (!res.ok) { host.say(res.error); return false; }
    manifests.delete(res.name);
    for (const e of entries.values()) if (e.name === res.name) { e.preview = null; load(e, false); }
    host.say(`Installed ${res.title || res.name}${res.version ? ' ' + res.version : ''} from a folder`);
    return true;
  }

  // A removed plugin keeps running in a sheet already showing it, until the page is loaded again.
  async function remove(name) {
    let res;
    try { res = await Api.json(`/api/plugins/${encodeURIComponent(name)}`, undefined, 'DELETE'); }
    catch (err) { res = { ok: false, error: err.message }; }
    if (!res.ok) { host.say(res.error); return false; }
    manifests.delete(name);
    host.say(`Removed the ${name} plugin`);
    return true;
  }

  // Settings → Plugins: the plugins kept on this machine, with Update and Remove; the ones the
  // plugin source offers, with Install; and a name to install by hand. `box` is filled afresh.
  async function settings(box) {
    const list = el('div', 'plugin-list'), offer = el('div', 'plugin-list');
    let mine;
    try { mine = await Api.json('/api/plugins'); }
    catch (err) { box.replaceChildren(el('p', 'note', `The plugins could not be listed: ${err.message}`)); return; }
    host.auto.checked = mine.auto;
    host.auto.disabled = !!mine.folder;
    const have = new Set(mine.installed.map((p) => p.name));
    const item = (p, buttons) => {
      const row = el('div', 'plugin-item');
      const text = el('div', 'plugin-about');
      text.append(el('strong', '', p.title || p.name),
        el('span', 'plugin-meta', ` ${p.name}${p.version ? ' · ' + p.version : ''}${p.origin === 'folder' ? ' · from a folder' : ''}`));
      if (p.description) text.append(el('div', 'plugin-desc', p.description));
      row.append(text, ...buttons);
      return row;
    };
    const again = () => settings(box);
    const btn = (label, fn) => { const b = el('button', '', label); b.onclick = async () => { b.disabled = true; await fn(); again(); }; return b; };
    if (mine.folder) list.append(el('p', 'note', `Plugins are read from the folder ${mine.folder}, as they are there: nothing is downloaded, kept or removed.`));
    if (!mine.installed.length) list.append(el('p', 'note', 'No plugins installed.'));
    for (const p of mine.installed)
      list.append(item(p, [...(p.template ? [btn('Open its sheet', () => openTemplate(p.name))] : []),
        ...(mine.folder ? [] : [...(p.origin === 'folder' ? [] : [btn('Update', () => install(p.name))]), btn('Remove', () => remove(p.name))])]));
    const by = el('div', 'set-acts');
    const name = el('input'); name.placeholder = 'plugin name'; name.setAttribute('aria-label', 'Plugin name to install');
    const go = btn('Install', () => install(name.value.trim()));
    name.onkeydown = (ev) => { if (ev.key === 'Enter') go.click(); };
    by.append(name, go);
    if (!mine.folder) {
      const pick = el('input'); pick.type = 'file'; pick.hidden = true; pick.webkitdirectory = true; pick.id = 'pluginFolder';
      pick.onchange = async () => { if (pick.files.length && await installFolder(pick.files)) again(); };
      const choose = el('button', '', 'Install from a folder…');
      choose.title = 'Install a plugin kept on this computer: pick its folder, the one with its manifest.json';
      choose.onclick = () => pick.click();
      by.append(choose, pick);
    }
    box.replaceChildren(el('h4', '', 'Installed'), list, el('h4', '', 'Available'), offer, by);
    if (mine.folder) { offer.append(el('p', 'note', 'The same as above.')); return; }
    offer.append(el('p', 'note', 'Looking for plugins…'));
    let index;
    try { index = await Api.json('/api/pluginindex'); } catch (err) { index = { ok: false, error: err.message }; }
    if (!box.contains(offer)) return;
    if (!index.ok) { offer.replaceChildren(el('p', 'note', index.error)); return; }
    const more = index.plugins.filter((p) => !have.has(p.name));
    offer.replaceChildren(...(more.length ? more.map((p) => item(p, [btn('Install', () => install(p.name))]))
      : [el('p', 'note', 'All the available plugins are installed.')]));
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
    const again = el('button', '', e && e.notInstalled ? 'Install' : e && e.error ? 'Try again' : 'Reload');
    again.title = e && e.notInstalled ? `Download the ${name} plugin and keep it` : 'Fetch the plugin again';
    again.onclick = (ev) => { ev.stopPropagation(); if (e && e.notInstalled) install(name); else reload(key); };
    tools.append(openBtn, again, say);
    box.append(tools);
  }

  function paint(e) {
    for (const box of document.querySelectorAll(`.plugin-box[data-key="${CSS.escape(e.key)}"]`)) fill(box, e, null);
  }

  const api = { THEME, blocks, inputs, check, imageUrl, folderFiles, init, after, build, open, reload, retheme, install, installFolder, remove, settings, openTemplate,
    get current() { return current; } };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Plugins = api;
})(typeof window !== 'undefined' ? window : globalThis);
