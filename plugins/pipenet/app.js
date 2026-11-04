/* The pipenet plugin's page: the grid editor around pipenet.js, and the messages to and from LENS
 * (laconic/static/plugins.js). Every change is saved into the plugin's block: the layout as its
 * `#@ state` line, and the network as the A, L!, D_h!, K_fT!, exchangers! and speeds! lines the
 * sheet calculates with. The sheet's `!pluginvar` values come back and are drawn on the pipes. */
(function () {
  'use strict';
  const P = window.PipeNet;
  const $ = (s) => document.querySelector(s);
  const canvas = $('#canvas');

  let state = P.blank(), analysis = P.analyze(state), inputs = [];
  let tool = 'draw', selected = null, theme = {};
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
      post({ type: 'lens:write', state, outputs: P.outputs(state, analysis) });
    }, 250);
  }

  function schedulePreview() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(() => {
      if (!Object.keys(state.cells).length) return;
      post({ type: 'lens:preview', svg: P.draw(state, analysis, { theme: svgTheme(), grid: false, inputs }) });
    }, 400);
  }

  // ---- messages from LENS ------------------------------------------------------------------
  window.addEventListener('message', (ev) => {
    if (ev.source !== window.parent) return;
    const m = ev.data;
    if (m && m.type === 'lens:theme' && m.theme) { applyTheme(m.theme); refresh(); return; }
    if (!m || m.type !== 'lens:update') return;
    if (m.theme) applyTheme(m.theme);
    inputs = Array.isArray(m.inputs) ? m.inputs : [];
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
  const svgTheme = () => ({ paper: css('paper'), text: css('text'), ink: css('ink'), rule: css('rule'), err: css('err'),
    grid: css('grid'), sans: css('sans'), soft: css('text-soft'), hi: css('global') });

  // ---- drawing ------------------------------------------------------------------------------
  // The grid only grows while the page is open, and when it grows up or to the left the view is
  // scrolled by as much, so the tiles stay under the pointer. A new layout from the sheet starts afresh.
  let shownBounds = null;
  function refresh(fresh = false) {
    analysis = P.analyze(state);
    if (selected && !state.cells[selected]) selected = null;
    const old = fresh ? null : shownBounds;
    const b = old ? grow(old, P.bounds(state)) : P.bounds(state);
    // at least as large as the view, so growing up or left can always be scrolled back
    const main = $('main'), side = P.CELL * zoom;
    b.c1 = Math.max(b.c1, b.c0 + Math.ceil(main.clientWidth / side) - 1);
    b.r1 = Math.max(b.r1, b.r0 + Math.ceil(main.clientHeight / side) - 1);
    shownBounds = b;
    const svg = P.draw(state, analysis, { theme: svgTheme(), selected, inputs, bounds: b });
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
    $('#ret').checked = state.ret;
    $('#labels').value = state.labels;
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
    if (tool === 'erase') { P.erase(state, k); refresh(); }
    else if (tool.startsWith('shape')) {
      const item = P.PALETTE[+tool.slice(5)], old = state.cells[k];
      if (old && old.t === item.t && P.shape(old) === P.shape(item)) {
        old.p = P.rotate(old.p);
        if (old.t !== 'pipe') { /* a source or sink keeps one side */ }
      } else P.place(state, k, item);
      selected = k;
      refresh();
    }
  });

  canvas.addEventListener('pointermove', (ev) => {
    if (!drag) return;
    const k = cellAt(ev);
    if (k === drag.last) return;
    drag.moved = true;
    if (tool === 'erase') { P.erase(state, k); drag.last = k; refresh(); return; }
    if (tool !== 'draw') return;
    // one square at a time, so a quick stroke still lays every square between
    let [r, c] = P.at(drag.last);
    const [r2, c2] = P.at(k);
    while (r !== r2 || c !== c2) {
      const from = P.key(r, c);
      if (c !== c2) c += Math.sign(c2 - c); else r += Math.sign(r2 - r);
      P.connect(state, from, P.key(r, c));
    }
    drag.last = k;
    refresh();
  });

  const endDrag = () => {
    if (!drag) return;
    const d = drag;
    drag = null;
    if (!d.moved && (tool === 'draw' || tool === 'select')) selected = state.cells[d.last] ? d.last : null;
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
    btn.innerHTML = P.draw(mini, { segments: [], sinks: [], errors: [], warnings: [], order: [] },
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
  $('#clear').onclick = () => { edit(() => { state.cells = {}; selected = null; }); refresh(true); };
  $('#example').onclick = () => { edit(() => { state.cells = example(); }); refresh(true); };

  document.addEventListener('keydown', (ev) => {
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName)) return;
    const k = ev.key.toLowerCase();
    if ((ev.ctrlKey || ev.metaKey) && k === 'z') { ev.preventDefault(); ev.shiftKey ? redo() : undo(); }
    else if ((ev.ctrlKey || ev.metaKey) && k === 'y') { ev.preventDefault(); redo(); }
    else if (k === 'r' && selected && state.cells[selected]) edit(() => { const t = state.cells[selected]; t.p = P.rotate(t.p); });
    else if ((k === 'delete' || k === 'backspace') && selected) edit(() => { P.erase(state, selected); selected = null; });
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
  $('#ret').onchange = (e) => edit(() => { state.ret = e.target.checked; });
  $('#labels').onchange = (e) => edit(() => { state.labels = e.target.value; });

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

  function inspector() {
    const box = $('#inspector'), t = selected && state.cells[selected];
    if (!t) { box.replaceChildren(el('p', { class: 'hint' }, 'Click a tile with Select (or click without dragging while drawing).')); return; }
    const [r, c] = P.at(selected), seg = P.segmentAt(analysis, selected);
    const sh = P.shape(t), parts = [];
    parts.push(el('div', { class: 'kv' },
      el('span', {}, 'Tile'), el('span', {}, `${sh} at row ${r}, column ${c}`),
      ...(seg && seg.row !== undefined ? [el('span', {}, 'Segment'), el('span', {}, `${seg.row + 1}: ${P.fmt(seg.L)} ${state.units.L} long, ${P.fmt(seg.D)} ${state.units.D}, fittings ${P.fmt(seg.K)}·f_T`)] : [])));
    if (t.t !== 'source') {
      parts.push(field(`Length (${state.units.L})`, t.L, String(state.cell), (v) => edit(() => { const x = positive(v); if (x) t.L = x; else delete t.L; })));
      parts.push(field('Extra fittings (L/D)', t.k, '0', (v) => edit(() => { const x = parseFloat(v); if (isFinite(x) && x > 0) t.k = x; else delete t.k; })));
      parts.push(field(`Segment diameter (${state.units.D})`, seg ? seg.D : t.d, String(state.D), (v) => edit(() => {
        const x = positive(v), tiles = seg ? seg.tiles : [selected];
        for (const k of tiles) { const u = state.cells[k]; if (!u || u.t === 'source') continue; if (x) u.d = x; else delete u.d; }
      })));
    }
    if (t.t === 'sink') {
      parts.push(field('Name', t.name, 'S' + ((analysis.sinks.findIndex((s) => s.key === selected) + 1) || ''), (v) => edit(() => { if (v.trim()) t.name = v.trim().slice(0, 40); else delete t.name; }), 'text'));
      parts.push(field('Exchanger curve', t.x, '1', (v) => edit(() => { const x = Math.round(parseFloat(v)); if (x >= 1) t.x = x; })));
      parts.push(field('Pump speed', t.s, '2', (v) => edit(() => { const x = Math.round(parseFloat(v)); if (x >= 1) t.s = x; })));
    }
    parts.push(el('div', { class: 'row-btns' },
      el('button', { onclick: () => edit(() => { t.p = P.rotate(t.p); }) }, 'Turn (R)'),
      el('button', { onclick: () => edit(() => { P.erase(state, selected); selected = null; }) }, 'Remove (Del)')));
    box.replaceChildren(...parts);
  }

  function messages() {
    const list = [...analysis.errors.map((e) => ({ ...e, cls: 'err' })), ...analysis.warnings.map((w) => ({ ...w, cls: 'warn' }))];
    const ul = $('#msgs');
    if (!list.length) {
      const n = analysis.sinks.length;
      ul.replaceChildren(el('li', { class: 'warn' }, n ? `One source, ${n} sink${n > 1 ? 's' : ''}, ${analysis.order.length} segments: written to the sheet.` : 'Nothing yet.'));
      return;
    }
    ul.replaceChildren(...list.slice(0, 30).map((m) => el('li', { class: m.cls, onclick: () => { if (m.key) { selected = m.key; tool = 'select'; refresh(); } } },
      (m.key ? `(${m.key.replace(',', ', ')}) ` : '') + m.msg)));
  }

  function tables() {
    const vals = P.placed(inputs, analysis), a = analysis;
    const ok = !a.errors.length && a.sinks.length;
    const twice = state.ret ? 2 : 1;
    if (!ok) { $('#segments').replaceChildren(); $('#sinks').replaceChildren(); }
    else {
      const head = el('tr', {}, el('th', {}, '#'), el('th', {}, `L ${state.units.L}`), el('th', {}, `D ${state.units.D}`), el('th', {}, 'L/D fit'),
        ...vals.segments.map((v) => el('th', {}, v.name + (v.unit ? ` ${v.unit}` : ''))));
      const rows = a.order.map((id, i) => {
        const s = a.segments[id];
        const tr = el('tr', { class: selected && s.tiles.includes(selected) ? 'sel' : '', onclick: () => { selected = s.tiles[0]; refresh(); } },
          el('td', {}, String(i + 1) + (s.sink ? ` → ${a.sinks.find((k) => k.seg === id).name}` : '')),
          el('td', {}, P.fmt(s.L * twice)), el('td', {}, P.fmt(s.D)), el('td', {}, P.fmt(s.K * twice)),
          ...vals.segments.map((v) => el('td', { class: v.stale ? 'stale' : '' }, P.fmt(v.values[i]))));
        return tr;
      });
      $('#segments').replaceChildren(el('table', {}, el('thead', {}, head), el('tbody', {}, ...rows)));
      const shead = el('tr', {}, el('th', {}, 'Sink'), el('th', {}, 'curve'), el('th', {}, 'speed'),
        ...vals.sinks.map((v) => el('th', {}, v.name + (v.unit ? ` ${v.unit}` : ''))));
      const srows = a.sinks.map((s, j) => el('tr', { class: selected === s.key ? 'sel' : '', onclick: () => { selected = s.key; refresh(); } },
        el('td', {}, `${j + 1} ${s.name}`), el('td', {}, String(s.x)), el('td', {}, String(s.s)),
        ...vals.sinks.map((v) => el('td', { class: v.stale ? 'stale' : '' }, P.fmt(v.values[j])))));
      $('#sinks').replaceChildren(el('table', {}, el('thead', {}, shead), el('tbody', {}, ...srows)));
    }
    const notes = [];
    if (vals.legend.length) notes.push(vals.legend.map((v) => `${v.name} = ${P.fmt(v.values[0], v.unit)}`).join(', '));
    if (vals.unplaced.length) notes.push(`Not drawn (not one per segment or per sink): ${vals.unplaced.join(', ')}`);
    if (!inputs.length) notes.push('Add `!pluginvar Q, Δp` below the calculation to see the sheet\'s values here.');
    $('#about').textContent = notes.join('. ');
  }

  // ---- an example to start from: a trunk with three branches each way, eight loads ------------
  function example() {
    const s = P.blank(), path = (ks) => { for (let i = 1; i < ks.length; i++) P.connect(s, ks[i - 1], ks[i]); };
    const line = (r0, c0, r1, c1) => {
      const ks = [];
      for (let r = r0, c = c0; ; ) {
        ks.push(P.key(r, c));
        if (r === r1 && c === c1) return ks;
        if (c !== c1) c += Math.sign(c1 - c); else r += Math.sign(r1 - r);
      }
    };
    P.place(s, '2,0', { t: 'source', p: P.E });
    path(line(2, 0, 2, 20));
    for (const c of [2, 8, 14]) {
      path(line(2, c, 0, c)); path(line(0, c, 0, c + 2));                  // up, then along
      path(line(2, c + 3, 5, c + 3)); path(line(5, c + 3, 5, c + 5));      // down, then along
    }
    path(line(3, 17, 3, 19));
    for (const k of ['0,4', '5,7', '0,10', '5,13', '0,16', '3,19', '5,19', '2,20']) P.place(s, k, { t: 'sink', p: 0, auto: true });
    return s.cells;
  }

  window.addEventListener('resize', () => refresh());   // the frame is sized when its dialog opens
  refresh();
  post({ type: 'lens:ready' });
})();
