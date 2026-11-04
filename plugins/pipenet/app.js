/* The pipenet plugin's page: the grid editor around pipenet.js, and the messages to and from LENS
 * (laconic/static/plugins.js). Every change is saved into the plugin's block: the layout as its
 * `#@ state` line, and the network as the lines the sheet calculates with: A, L!, D_h!, N_fit!,
 * K_extra! for the supply, A_r, L_r!, D_r!, N_fit_r!, K_extra_r! for the return, exchangers!,
 * speeds!, fit_method! and the pump's Δp_target. The sheet's `!pluginvar` values come back and are drawn on the pipes.
 *
 * With the return laid out on its own, the grid has two layers, as a circuit board has two sides:
 * the supply and the return. The tools work on the layer in front (Supply | Return, or F), and the
 * other is drawn faded behind it. The source and the sinks are on both. */
(function () {
  'use strict';
  const P = window.PipeNet;
  const $ = (s) => document.querySelector(s);
  const canvas = $('#canvas');

  let state = P.blank(), net = P.network(state), inputs = [], overridden = [];
  let tool = 'draw', selected = null, theme = {}, layer = 's';

  // The layer in front: the return only while it is laid out on its own.
  const front = () => (state.ret === 'separate' ? layer : 's');
  const cells = () => (front() === 'r' ? state.rcells : state.cells);
  const walked = () => (front() === 'r' ? net.r : net.s);
  const onFront = (fn) => P.onLayer(state, front(), fn);
  // Take a tile away from the layer in front; a pad (the source, a sink) from both layers.
  function eraseAt(k) {
    const t = cells()[k];
    if (t && t.t !== 'pipe') { P.erase(P.side(state, 's'), k); P.erase(P.side(state, 'r'), k); }
    else onFront((v) => P.erase(v, k));
  }
  let past = [], future = [];
  let drag = null, writeTimer = 0, previewTimer = 0, heard = false, zoom = 1;

  const post = (msg) => window.parent.postMessage(msg, '*');

  // ---- saving -----------------------------------------------------------------------------
  function commit(before) {
    if (before !== JSON.stringify(state)) {
      past.push(before);
      if (past.length > 200) past.shift();
      future = [];
      scheduleWrite();
    }
    refresh();
  }

  function scheduleWrite() {
    clearTimeout(writeTimer);
    writeTimer = setTimeout(() => {
      writeTimer = 0;
      post({ type: 'lens:write', state, outputs: P.outputs(state, net) });
    }, 250);
  }

  function schedulePreview() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(() => {
      if (!Object.keys(state.cells).length) return;
      post({ type: 'lens:preview', svg: P.draw(state, net, { theme: svgTheme(), grid: false, inputs, layer: 's' }) });
    }, 400);
  }

  // ---- messages from LENS ------------------------------------------------------------------
  window.addEventListener('message', (ev) => {
    if (ev.source !== window.parent) return;
    const m = ev.data;
    if (m && m.type === 'lens:theme' && m.theme) { applyTheme(m.theme); refresh(); return; }
    if (m && m.type === 'lens:check') { drift(m); return; }
    if (!m || m.type !== 'lens:update') return;
    if (m.theme) applyTheme(m.theme);
    inputs = Array.isArray(m.inputs) ? m.inputs : [];
    overridden = Array.isArray(m.overridden) ? m.overridden : [];
    // The state the sheet holds, unless this page has a change of its own on the way or in hand.
    if ('state' in m && !writeTimer && !drag) {
      const next = P.normalize(m.state);
      if (JSON.stringify(next) !== JSON.stringify(state)) {
        if (heard) { past.push(JSON.stringify(state)); future = []; }
        state = next;
        heard = true;
        refresh(true);
        return;
      }
    }
    heard = true;
    refresh();
  });

  function applyTheme(t) {
    theme = t;
    for (const [k, v] of Object.entries(t)) if (v && /^[\w-]+$/.test(k) && !/[;{}<>]/.test(v)) document.documentElement.style.setProperty('--' + k, v);
  }
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue('--' + v).trim();
  const svgTheme = () => ({ paper: css('paper'), text: css('text'), ink: css('ink'), ret: css('symbol'), rule: css('rule'), err: css('err'),
    grid: css('grid'), sans: css('sans'), soft: css('text-soft'), hi: css('global') });

  // ---- drawing ------------------------------------------------------------------------------
  // The grid only grows while the page is open, and when it grows up or to the left the view is
  // scrolled by as much, so the tiles stay under the pointer. A new layout from the sheet starts afresh.
  let shownBounds = null;
  function refresh(fresh = false) {
    net = P.network(state);
    if (selected && !cells()[selected]) selected = null;
    const old = fresh ? null : shownBounds;
    const b = old ? grow(old, P.bounds(state)) : P.bounds(state);
    // at least as large as the view, so growing up or left can always be scrolled back
    const main = $('main'), side = P.CELL * zoom;
    b.c1 = Math.max(b.c1, b.c0 + Math.ceil(main.clientWidth / side) - 1);
    b.r1 = Math.max(b.r1, b.r0 + Math.ceil(main.clientHeight / side) - 1);
    shownBounds = b;
    const svg = P.draw(state, net, { theme: svgTheme(), selected, inputs, bounds: b, layer: front(), rounds: drag ? 40 : 600 });
    const doc = new DOMParser().parseFromString(svg, 'image/svg+xml').documentElement;
    canvas.replaceChildren(...[...doc.childNodes].map((n) => document.importNode(n, true)));
    for (const a of ['viewBox', 'font-family']) canvas.setAttribute(a, doc.getAttribute(a));
    canvas.setAttribute('width', doc.getAttribute('width') * zoom);
    canvas.setAttribute('height', doc.getAttribute('height') * zoom);
    $('#zoomLevel').textContent = Math.round(zoom * 100) + '%';
    if (old) {
      main.scrollLeft += (old.c0 - b.c0) * P.CELL * zoom;
      main.scrollTop += (old.r0 - b.r0) * P.CELL * zoom;
    }
    $('#empty').hidden = Object.keys(state.cells).length > 0;
    for (const btn of document.querySelectorAll('[data-tool]')) btn.setAttribute('aria-pressed', String(btn.dataset.tool === tool));
    for (const btn of document.querySelectorAll('#palette button')) btn.setAttribute('aria-pressed', String(tool === 'shape' + btn.dataset.i));
    $('#undo').disabled = !past.length; $('#redo').disabled = !future.length;
    $('#unitL').value = state.units.L; $('#unitD').value = state.units.D;
    setNum($('#cell'), state.cell); setNum($('#dia'), state.D);
    $('#ret').value = state.ret;
    if (document.activeElement !== $('#size')) sizeOptions($('#size'), []);   // the bores follow the schedule and unit
    $('#size').value = state.nps || 'custom'; $('#sch').value = state.sch;
    $('#diaRow').hidden = !!state.nps;
    $('#sides').hidden = state.ret !== 'separate';
    for (const btn of document.querySelectorAll('[data-layer]')) btn.setAttribute('aria-pressed', String(btn.dataset.layer === front()));
    document.body.dataset.layer = front();
    if (state.ret === 'separate') document.body.dataset.two = ''; else delete document.body.dataset.two;
    showSets();
    $('#method').value = String(state.method);
    setNum($('#dpv'), state.dp.v); $('#dpu').value = state.dp.u;
    messages(); inspector(); tables();
    schedulePreview();
  }

  const grow = (a, b) => ({ r0: Math.min(a.r0, b.r0), c0: Math.min(a.c0, b.c0), r1: Math.max(a.r1, b.r1), c1: Math.max(a.c1, b.c1) });
  function setNum(el, v) { if (document.activeElement !== el) el.value = v; }

  function cellAt(ev) {
    const r = canvas.getBoundingClientRect(), b = shownBounds;
    const scale = r.width / ((b.c1 - b.c0 + 1) * P.CELL);
    const c = Math.floor((ev.clientX - r.left) / scale / P.CELL) + b.c0;
    const row = Math.floor((ev.clientY - r.top) / scale / P.CELL) + b.r0;
    return P.key(row, c);
  }

  // ---- the grid's pointer ------------------------------------------------------------------
  canvas.addEventListener('pointerdown', (ev) => {
    if (ev.button !== 0) return;
    canvas.setPointerCapture(ev.pointerId);
    const k = cellAt(ev);
    drag = { before: JSON.stringify(state), last: k, moved: false };
    if (tool === 'erase') { eraseAt(k); refresh(); }
    else if (tool.startsWith('shape')) {
      const item = P.PALETTE[+tool.slice(5)], old = cells()[k];
      if (old && old.t === item.t && P.shape(old) === P.shape(item)) old.p = P.rotate(old.p);
      else onFront((v) => P.place(v, k, item));
      selected = k;
      refresh();
    }
  });

  canvas.addEventListener('pointermove', (ev) => {
    if (!drag) return;
    const k = cellAt(ev);
    if (k === drag.last) return;
    drag.moved = true;
    if (tool === 'erase') { eraseAt(k); drag.last = k; refresh(); return; }
    if (tool !== 'draw') return;
    // one square at a time, so a quick stroke still lays every square between
    let [r, c] = P.at(drag.last);
    const [r2, c2] = P.at(k);
    while (r !== r2 || c !== c2) {
      const from = P.key(r, c);
      if (c !== c2) c += Math.sign(c2 - c); else r += Math.sign(r2 - r);
      const to = P.key(r, c);
      onFront((v) => P.connect(v, from, to));
    }
    drag.last = k;
    refresh();
  });

  const endDrag = () => {
    if (!drag) return;
    const d = drag;
    drag = null;
    if (!d.moved && (tool === 'draw' || tool === 'select')) selected = cells()[d.last] ? d.last : null;
    commit(d.before);
  };
  canvas.addEventListener('pointerup', endDrag);
  canvas.addEventListener('pointercancel', endDrag);

  // ---- tools and keys ----------------------------------------------------------------------
  for (const btn of document.querySelectorAll('[data-tool]')) btn.onclick = () => { tool = btn.dataset.tool; refresh(); };
  P.PALETTE.forEach((item, i) => {
    const btn = document.createElement('button');
    btn.dataset.i = i;
    btn.title = `${item.label}, ${P.bits(item.p).map((d) => P.NAMES[d]).join('-')}`;
    const mini = { ...P.blank(), cells: { '0,0': { t: item.t, p: item.p } } };
    const none = { segments: [], sinks: [], errors: [], warnings: [], order: [] };
    btn.innerHTML = P.draw(mini, { same: true, s: none, r: none, sinks: [], errors: [], warnings: [] },
      { grid: false, bounds: { r0: 0, c0: 0, r1: 0, c1: 0 }, theme: { paper: 'transparent', ink: 'currentColor' } });
    btn.onclick = () => { tool = 'shape' + i; refresh(); };
    $('#palette').append(btn);
  });

  function edit(fn) { const before = JSON.stringify(state); fn(); commit(before); }
  function undo() { if (!past.length) return; future.push(JSON.stringify(state)); state = JSON.parse(past.pop()); scheduleWrite(); refresh(); }
  function redo() { if (!future.length) return; past.push(JSON.stringify(state)); state = JSON.parse(future.pop()); scheduleWrite(); refresh(); }
  const zoomBy = (f) => { zoom = Math.min(2, Math.max(0.4, Math.round(zoom * f * 10) / 10)); refresh(); };
  $('#zoomOut').onclick = () => zoomBy(1 / 1.25);
  $('#zoomIn').onclick = () => zoomBy(1.25);
  $('#zoomFit').onclick = () => {
    const box = $('main'), bb = P.bounds(state), w = (bb.c1 - bb.c0 + 1) * P.CELL, h = (bb.r1 - bb.r0 + 1) * P.CELL;
    zoom = Math.min(2, Math.max(0.4, Math.floor(Math.min(box.clientWidth / w, box.clientHeight / h) * 10) / 10));
    refresh(true);
  };
  $('#undo').onclick = undo;
  $('#redo').onclick = redo;
  $('#clear').onclick = () => { edit(() => { state.cells = {}; state.rcells = {}; selected = null; }); refresh(true); };
  $('#example').onclick = () => {
    edit(() => { state.cells = P.example(); state.rcells = {}; P.syncPads(state, 's'); if (state.ret === 'separate') P.copySupply(state); });
    refresh(true);
  };
  // Supply | Return: which layer the tools work on; the other is drawn faded behind it.
  function flip(to) {
    layer = to || (layer === 's' ? 'r' : 's');
    selected = null;
    refresh();
  }
  for (const btn of document.querySelectorAll('[data-layer]')) btn.onclick = () => flip(btn.dataset.layer);

  document.addEventListener('keydown', (ev) => {
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName)) return;
    const k = ev.key.toLowerCase();
    if ((ev.ctrlKey || ev.metaKey) && k === 'z') { ev.preventDefault(); ev.shiftKey ? redo() : undo(); }
    else if ((ev.ctrlKey || ev.metaKey) && k === 'y') { ev.preventDefault(); redo(); }
    else if (k === 'r' && selected && cells()[selected]) edit(() => { const t = cells()[selected]; t.p = P.rotate(t.p); });
    else if ((k === 'delete' || k === 'backspace') && selected) edit(() => { eraseAt(selected); selected = null; });
    else if (k === 'f' && state.ret === 'separate') flip();
    else if (k === 'd') { tool = 'draw'; refresh(); }
    else if (k === 's') { tool = 'select'; refresh(); }
    else if (k === 'e') { tool = 'erase'; refresh(); }
  });

  // ---- the network's settings --------------------------------------------------------------
  const positive = (v) => { const x = parseFloat(v); return isFinite(x) && x > 0 ? x : null; };
  $('#unitL').onchange = (e) => edit(() => { state.units.L = e.target.value; });
  $('#unitD').onchange = (e) => edit(() => { state.units.D = e.target.value; });
  $('#cell').onchange = (e) => { const x = positive(e.target.value); if (x) edit(() => { state.cell = x; }); else refresh(); };
  $('#dia').onchange = (e) => { const x = positive(e.target.value); if (x) edit(() => { state.D = x; }); else refresh(); };
  // The return laid out on its own starts as a copy of the supply, to change where they differ.
  $('#ret').onchange = (e) => {
    edit(() => {
      state.ret = e.target.value;
      if (state.ret === 'separate' && !Object.values(state.rcells).some((t) => t.t === 'pipe')) P.copySupply(state);
    });
    if (state.ret === 'separate') flip('r');
  };
  $('#size').onchange = (e) => edit(() => { state.nps = e.target.value === 'custom' ? null : e.target.value; });
  $('#sch').onchange = (e) => edit(() => { state.sch = e.target.value; });
  $('#method').onchange = (e) => edit(() => { state.method = +e.target.value; });
  $('#dpu').replaceChildren(...P.DP_UNITS.map((u) => Object.assign(document.createElement('option'), { value: u, textContent: u.replace('_', ' ') })));
  $('#dpv').onchange = (e) => { const x = parseFloat(e.target.value); if (isFinite(x) && x >= 0) edit(() => { state.dp.v = x; }); else refresh(); };
  $('#dpu').onchange = (e) => edit(() => { state.dp.u = e.target.value; });
  // On the drawing: a checkbox for each set of data the balloons can show, the plugin's own (segment
  // numbers, pipe sizes, lengths, bores, each sink's curves) and each of the sheet's !pluginvar values.
  const BUILT_IN = [['numbers', 'Segment numbers'], ['size', 'Pipe size'], ['L', 'Length'], ['D', 'D_h (bore)'],
    ['hx', 'Exchanger curve'], ['pump', 'Pump curve']];
  function showSets() {
    const box = $('#showSets');
    if (box.contains(document.activeElement)) return;
    const check = (label, on, set) => {
      const input = el('input', { type: 'checkbox' });
      input.checked = on;
      input.onchange = () => edit(() => set(input.checked));
      return el('label', {}, input, label);
    };
    const sheetSets = [...new Set(inputs.filter((v) => !Array.isArray(v.names)).map((v) => v.name))];
    box.replaceChildren(
      ...BUILT_IN.map(([k, label]) => check(label, state.show[k], (on) => { state.show[k] = on; })),
      ...(sheetSets.length ? [el('div', { class: 'sub' }, "The sheet's values")] : []),
      ...sheetSets.map((n) => check(n, !state.show.hide.includes(n), (on) => {
        state.show.hide = state.show.hide.filter((x) => x !== n).concat(on ? [] : [n]);
      })));
  }

  // The pipe sizes, nominal size and the bore in the schedule chosen, for the size lists.
  const sizeOptions = (select, extra) => {
    select.replaceChildren(...extra.map(([v, t]) => el('option', { value: v }, t)),
      ...P.PIPE_SIZES.map(([n]) => el('option', { value: n }, `${n}"  (${P.fmt(P.bore(state, n))} ${state.units.D})`)),
      el('option', { value: 'custom' }, 'Other: a bore of its own'));
  };

  // ---- the panels on the right -------------------------------------------------------------
  const el = (tag, attrs = {}, ...kids) => {
    const e = document.createElement(tag);
    for (const [a, v] of Object.entries(attrs)) if (a.startsWith('on')) e[a] = v; else if (v !== undefined && v !== null) e.setAttribute(a, v);
    e.append(...kids);
    return e;
  };
  const field = (label, value, placeholder, set, type = 'number') => {
    const input = el('input', { type, value: value === undefined ? '' : value, placeholder, step: 'any', min: type === 'number' ? '0' : undefined });
    input.onchange = () => set(input.value);
    return el('label', { class: 'f' }, label, input);
  };

  // A sink's exchanger or pump curve: picked by the names the sheet gives them (`!pluginvar exchangers:
  // ...`, `!pluginvar speeds: ...`), else by number. A number past the names is kept, and said so.
  function curvePick(label, names, value, set) {
    if (!names) return field(label + ' (number)', value, '1', (v) => edit(() => { const x = Math.round(parseFloat(v)); if (x >= 1) set(x); }));
    const pick = el('select', { 'aria-label': label });
    pick.append(...names.map((n, i) => el('option', { value: String(i + 1) }, n)));
    if (value > names.length) pick.append(el('option', { value: String(value) }, `${value}: not named in the sheet`));
    pick.value = String(value);
    pick.onchange = () => edit(() => set(+pick.value));
    return el('label', { class: 'f stack' }, label, pick);
  }

  function inspector() {
    const box = $('#inspector'), t = selected && cells()[selected];
    if (!t) { box.replaceChildren(el('p', { class: 'hint' }, 'Click a tile with Select (or click without dragging while drawing).')); return; }
    const [r, c] = P.at(selected), seg = P.segmentAt(walked(), selected), pad = state.cells[selected];
    const sh = P.shape(t), parts = [], prefix = front() === 'r' ? 'R' : '';
    const where = state.ret === 'separate' ? (front() === 'r' ? ' on the return' : ' on the supply') : '';
    parts.push(el('div', { class: 'kv' },
      el('span', {}, 'Tile'), el('span', {}, `${sh} at row ${r}, column ${c}${where}`),
      ...(seg && seg.row !== undefined ? [el('span', {}, 'Segment'), el('span', {}, `${prefix}${seg.row + 1}: ${P.fmt(seg.L)} ${state.units.L} long, ${P.sizeName(state, seg.nps)} (${P.fmt(seg.D)} ${state.units.D}), ${fittings(seg.n)}${seg.K ? `, extra K ${P.fmt(seg.K)}` : ''}`)] : [])));
    if (t.t === 'pipe' || t.t === 'sink') {
      parts.push(field(`Length (${state.units.L})`, t.L, String(state.cell), (v) => edit(() => { const x = positive(v); if (x) t.L = x; else delete t.L; })));
      parts.push(field('Extra K (a valve, from its datasheet)', t.k, '0', (v) => edit(() => { const x = parseFloat(v); if (isFinite(x) && x > 0) t.k = x; else delete t.k; })));
    }
    if (seg) {
      // the segment's pipe: every pipe tile of it on this layer takes the size
      const tiles = seg.tiles.filter((k) => cells()[k] && cells()[k].t === 'pipe');
      const first = tiles.length ? cells()[tiles[0]] : {};
      const pick = el('select', { 'aria-label': 'Segment pipe size' });
      sizeOptions(pick, [['net', `The network's: ${P.sizeName(state, state.nps)}`]]);
      pick.value = first.nps || (first.d ? 'custom' : 'net');
      const setAll = (fn) => edit(() => { for (const k of tiles) { const u = cells()[k]; delete u.nps; delete u.d; fn(u); } });
      pick.onchange = () => setAll((u) => {
        if (pick.value === 'custom') u.d = seg.D;
        else if (pick.value !== 'net') u.nps = pick.value;
      });
      parts.push(el('label', { class: 'f stack' }, 'Segment pipe', pick));
      if (first.d) parts.push(field(`Segment bore (${state.units.D})`, first.d, String(seg.D), (v) => { const x = positive(v); if (x) setAll((u) => { u.d = x; }); }));
    }
    if (t.t === 'sink' && pad) {
      parts.push(field('Name', pad.name, 'S' + ((net.sinks.findIndex((s) => s.key === selected) + 1) || ''), (v) => edit(() => { if (v.trim()) pad.name = v.trim().slice(0, 40); else delete pad.name; }), 'text'));
      const names = P.curveNames(inputs);
      parts.push(curvePick('Exchanger curve', names.exchangers, pad.x, (x) => { pad.x = x; }));
      parts.push(curvePick('Pump curve', names.speeds, pad.s, (x) => { pad.s = x; }));
    }
    parts.push(el('div', { class: 'row-btns' },
      el('button', { onclick: () => edit(() => { t.p = P.rotate(t.p); }) }, 'Turn (R)'),
      el('button', { onclick: () => edit(() => { eraseAt(selected); selected = null; }) }, 'Remove (Del)')));
    box.replaceChildren(...parts);
  }

  function messages() {
    // A line of the sheet that defines one of the plugin's names again replaces what the plugin writes.
    const replaced = overridden.map((o) => ({ cls: 'err',
      msg: `${o.name} is set again on line ${o.line} of the sheet, which replaces the plugin's value: a change here does not reach the calculation. Delete that line.` }));
    const list = [...replaced, ...net.errors.map((e) => ({ ...e, cls: 'err' })), ...net.warnings.map((w) => ({ ...w, cls: 'warn' }))];
    const ul = $('#msgs');
    if (!list.length) {
      const n = net.sinks.length, segs = net.s.order.length;
      const said = state.ret === 'separate' ? `${segs} supply and ${net.r.order.length} return segments` : `${segs} segments, the return the same`;
      ul.replaceChildren(el('li', { class: 'warn' }, n ? `One source, ${n} sink${n > 1 ? 's' : ''}, ${said}: written to the sheet.` : 'Nothing yet.'));
      return;
    }
    ul.replaceChildren(...list.slice(0, 30).map((m) => el('li', { class: m.cls, onclick: () => {
      if (!m.key) return;
      if (state.ret === 'separate') layer = m.layer;
      selected = m.key; tool = 'select'; refresh();
    } }, (m.key ? `(${m.key.replace(',', ', ')}) ` : '') + m.msg)));
  }

  // The sheet against this plugin's own (pipenet.lens), as LENS compares them after each run: a small
  // warning naming what was changed or deleted, so a line lost by accident does not go unnoticed.
  function drift(m) {
    const box = $('#drift'), missing = Array.isArray(m.missing) ? m.missing : [], changed = Array.isArray(m.changed) ? m.changed : [];
    box.hidden = !missing.length && !changed.length;
    if (box.hidden) { box.replaceChildren(); return; }
    const list = (words, names) => {
      const p = el('div', {}, words + ' ');
      names.slice(0, 12).forEach((n, i) => p.append(...(i ? [', '] : []), el('code', {}, n)));
      if (names.length > 12) p.append(` and ${names.length - 12} more`);
      return p;
    };
    box.replaceChildren(el('strong', {}, '⚠ This sheet differs from the plugin\'s own'),
      ...(changed.length ? [list('Changed:', changed)] : []), ...(missing.length ? [list('Missing:', missing)] : []),
      el('div', { class: 'hint' }, 'Fine if you meant it. Otherwise copy the lines back from the original.'),
      el('button', { onclick: () => post({ type: 'lens:open-template' }) }, 'Open the original sheet'));
  }

  // "2 elbows, 1 branch" for a segment's fitting counts (N_fit!'s row, before the return doubles it).
  function fittings(n) {
    const words = [['elbow', 'elbows'], ['tee run', 'tee runs'], ['tee branch', 'tee branches']];
    const said = n.map((x, i) => (x ? `${x} ${words[i][x === 1 ? 0 : 1]}` : '')).filter(Boolean);
    return said.length ? said.join(', ') : 'no fittings';
  }

  // One layer's segments as a table: number, length, pipe, fittings, extra K, and the sheet's values.
  function segmentTable(a, values, prefix, own) {
    const head = el('tr', {}, el('th', {}, '#'), el('th', {}, `L ${state.units.L}`), el('th', { title: 'pipe size, or the bore of a pipe of its own' }, 'Pipe'),
      el('th', { title: '90° elbows' }, 'Ell'), el('th', { title: 'tees passed straight through' }, 'Run'),
      el('th', { title: "tees' branches" }, 'Br'), el('th', { title: 'extra K' }, 'K+'),
      ...values.map((v) => el('th', {}, v.name + (v.unit ? ` ${v.unit}` : ''))));
    const rows = a.order.map((id, i) => {
      const s = a.segments[id];
      return el('tr', { class: own && selected && s.tiles.includes(selected) ? 'sel' : '', onclick: () => {
        if (state.ret === 'separate') layer = prefix ? 'r' : 's';
        selected = s.tiles[0]; refresh();
      } },
        el('td', {}, `${prefix}${i + 1}` + (s.sink ? ` → ${net.sinks.find((k) => k.key === s.sink).name}` : '')),
        el('td', {}, P.fmt(s.L)), el('td', { title: `${P.fmt(s.D)} ${state.units.D}` }, s.nps ? `${s.nps}"` : P.fmt(s.D)),
        ...s.n.map((x) => el('td', {}, String(x))), el('td', {}, P.fmt(s.K)),
        ...values.map((v) => el('td', { class: v.stale ? 'stale' : '' }, P.fmt(v.values[i]))));
    });
    return el('table', {}, el('thead', {}, head), el('tbody', {}, ...rows));
  }

  function tables() {
    const vals = P.placed(inputs, net);
    const ok = !net.errors.length && net.sinks.length, apart = state.ret === 'separate';
    $('#retHead').hidden = $('#rsegments').hidden = !apart;
    $('#segHead').textContent = apart ? 'Supply segments' : 'Segments';
    if (!ok) { $('#segments').replaceChildren(); $('#rsegments').replaceChildren(); $('#sinks').replaceChildren(); }
    else {
      $('#segments').replaceChildren(segmentTable(net.s, vals.segments, '', front() === 's'));
      $('#rsegments').replaceChildren(apart ? segmentTable(net.r, vals.rsegments, 'R', front() === 'r') : '');
      const names = P.curveNames(inputs);
      const shead = el('tr', {}, el('th', {}, 'Sink'), el('th', {}, 'exchanger'), el('th', {}, 'pump'),
        ...vals.sinks.map((v) => el('th', {}, v.name + (v.unit ? ` ${v.unit}` : ''))));
      const srows = net.sinks.map((s, j) => el('tr', { class: selected === s.key ? 'sel' : '', onclick: () => { selected = s.key; refresh(); } },
        el('td', {}, `${j + 1} ${s.name}`), el('td', { class: 'name' }, P.curveName(names.exchangers, s.x)),
        el('td', { class: 'name' }, P.curveName(names.speeds, s.s)),
        ...vals.sinks.map((v) => el('td', { class: v.stale ? 'stale' : '' }, P.fmt(v.values[j])))));
      $('#sinks').replaceChildren(el('table', {}, el('thead', {}, shead), el('tbody', {}, ...srows)));
    }
    const notes = [];
    if (vals.legend.length) notes.push(vals.legend.map((v) => `${v.name} = ${P.fmt(v.values[0], v.unit)}`).join(', '));
    if (vals.unplaced.length) notes.push(`Not drawn (not one per segment or per sink): ${vals.unplaced.join(', ')}`);
    if (!inputs.length) notes.push('Add `!pluginvar Q, Δp` below the calculation to see the sheet\'s values here.');
    $('#about').textContent = notes.join('. ');
  }

  window.addEventListener('resize', () => refresh());   // the frame is sized when its dialog opens
  refresh();
  post({ type: 'lens:ready' });
})();
