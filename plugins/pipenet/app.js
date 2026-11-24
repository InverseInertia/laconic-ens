/* The pipenet plugin's page: the grid editor around pipenet.js, and the messages to and from LENS
 * (laconic/static/plugins.js). Every change is saved into the plugin's block: the layout as its
 * `#@ state` line, and the network as the lines the sheet calculates with: A, L!, D_h!, N_fit!,
 * K_extra! for the supply, A_r, L_r!, D_r!, N_fit_r!, K_extra_r! for the return, exchangers!,
 * pumps!, fit_method! and the pump's Δp_target. The sheet's `!pluginvar` values come back and are drawn on the pipes.
 *
 * With the return laid out on its own, the grid has two layers, as a circuit board has two sides:
 * the supply and the return. The tools work on the layer in front (Supply | Return, or F), and the
 * other is drawn faded behind it. The source and the sinks are on both.
 *
 * A background image (a planset) can be put behind the grid, moved, and scaled from two points a
 * known distance apart, so the pipes can be traced over it. The sheet holds where it is (state.bg);
 * the picture itself is kept in this browser by LENS (lens:keep, lens:recall). */
(function () {
  'use strict';
  const P = window.PipeNet;
  const $ = (s) => document.querySelector(s);
  const canvas = $('#canvas');

  let state = P.blank(), net = P.network(state), inputs = [], overridden = [];
  // The sheet's solver, from its block's `status: solver_state` sent with !pluginvar: 1 up to date,
  // 0 out of date, -1 not run, -2 an error in the block. null when the sheet does not send it.
  let solverState = null;
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
  // The background's picture, as a data: URL, for the key it was recalled or placed under
  // (data null: LENS has nothing under that key in this browser). `measure`: the two points of a scale.
  let bg = { key: null, data: null, asked: null }, measure = null, pan = null, space = false;
  // Copy settings: the sink whose exchanger, circulator, valve and extra K the sinks clicked take.
  let copyFrom = null;
  // A sink's settings changed in the inspector go to it alone, or to it and every sink set up like it.
  let applyAll = false;
  const ZOOM_MIN = 0.1, ZOOM_MAX = 4;

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
    if (m && m.type === 'lens:recalled') {
      if (m.key === bg.asked) { bg = { key: m.key, data: typeof m.data === 'string' ? m.data : null, asked: null }; refresh(); }
      return;
    }
    if (!m || m.type !== 'lens:update') return;
    if (m.theme) applyTheme(m.theme);
    inputs = Array.isArray(m.inputs) ? m.inputs : [];
    const st = inputs.find((v) => v.name === 'solver_state' && !Array.isArray(v.names));
    solverState = st && typeof st.mag === 'number' ? Math.round(st.mag) : null;
    inputs = inputs.filter((v) => v !== st);   // a state, not a value to draw
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
  let shownBounds = null, lastPlaced = {};
  function refresh(fresh = false) {
    net = P.network(state);
    if (selected && !cells()[selected]) selected = null;
    if (tool === 'copy' && !(state.cells[copyFrom] && state.cells[copyFrom].t === 'sink')) { tool = 'select'; copyFrom = null; }
    const old = fresh ? null : shownBounds;
    const want = extent();
    const b = old ? grow(old, want) : want;
    // at least as large as the view, so growing up or left can always be scrolled back
    const main = $('main'), side = P.CELL * zoom;
    b.c1 = Math.max(b.c1, b.c0 + Math.ceil(main.clientWidth / side) - 1);
    b.r1 = Math.max(b.r1, b.r0 + Math.ceil(main.clientHeight / side) - 1);
    shownBounds = b;
    const shown = !!(state.bg && bg.key === state.bg.key && bg.data);
    // the balloons start from where they were, so the picture holds still while it is edited
    const placed = {};
    const svg = P.draw(state, net, { theme: svgTheme(), selected, inputs, bounds: b, layer: front(), effort: drag ? 30 : 300,
      prev: lastPlaced, placed, key: 'html', underlay: shown });
    lastPlaced = placed;
    sinkKey();
    const doc = new DOMParser().parseFromString(svg, 'image/svg+xml').documentElement;
    canvas.replaceChildren(...[...doc.childNodes].map((n) => document.importNode(n, true)));
    for (const a of ['viewBox', 'font-family']) canvas.setAttribute(a, doc.getAttribute(a));
    canvas.setAttribute('width', doc.getAttribute('width') * zoom);
    canvas.setAttribute('height', doc.getAttribute('height') * zoom);
    $('#zoomLevel').textContent = Math.round(zoom * 100) + '%';
    background(shown);
    if (measure) markers();
    if (old) {
      main.scrollLeft += (old.c0 - b.c0) * P.CELL * zoom;
      main.scrollTop += (old.r0 - b.r0) * P.CELL * zoom;
    }
    $('#empty').hidden = Object.keys(state.cells).length > 0 || !!state.bg;
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
    document.body.dataset.tool = tool;
    // copying settings: an orange banner over the grid, so a click on a sink is not taken for anything else
    solveBanner();
    const banner = $('#copyBanner');
    banner.hidden = !(tool === 'copy' && state.cells[copyFrom]);
    if (!banner.hidden) {
      $('#copyText').textContent = `Copying ${sinkName(copyFrom)}'s settings (${describe(state.cells[copyFrom])}): every sink you click takes them.`;
    }
    if (state.ret === 'separate') document.body.dataset.two = ''; else delete document.body.dataset.two;
    showSets();
    $('#method').value = String(state.method);
    setNum($('#dpv'), state.dp.v); $('#dpu').value = state.dp.u;
    $('#hold').value = state.hold;
    $('#solver').value = String(state.solver);
    setNum($('#qv'), state.q.v); $('#qu').value = state.q.u;
    $('#qRow').hidden = state.hold !== 'flow';
    $('#dpRow').hidden = state.hold !== 'dp';
    messages(); inspector(); tables(); bgPanel();
    schedulePreview();
  }

  // What the grid must cover: the tiles and the background image.
  function extent() {
    const b = P.bounds(state), g = P.backdrop(state);
    return g ? grow(b, { r0: g.r0 - 1, c0: g.c0 - 1, r1: g.r1 + 1, c1: g.c1 + 1 }) : b;
  }

  const grow = (a, b) => ({ r0: Math.min(a.r0, b.r0), c0: Math.min(a.c0, b.c0), r1: Math.max(a.r1, b.r1), c1: Math.max(a.c1, b.c1) });
  function setNum(el, v) { if (document.activeElement !== el) el.value = v; }

  // The point under the pointer in squares, not whole ones (column, row), from the grid's corner.
  function pointAt(ev) {
    const r = canvas.getBoundingClientRect(), b = shownBounds, side = r.width / (b.c1 - b.c0 + 1);
    return [(ev.clientX - r.left) / side + b.c0, (ev.clientY - r.top) / side + b.r0];
  }

  function cellAt(ev) {
    const r = canvas.getBoundingClientRect(), b = shownBounds;
    const scale = r.width / ((b.c1 - b.c0 + 1) * P.CELL);
    const c = Math.floor((ev.clientX - r.left) / scale / P.CELL) + b.c0;
    const row = Math.floor((ev.clientY - r.top) / scale / P.CELL) + b.r0;
    return P.key(row, c);
  }

  // ---- the grid's pointer ------------------------------------------------------------------
  canvas.addEventListener('pointerdown', (ev) => {
    // The middle button, or the left with Space held, scrolls the view by dragging it.
    if (ev.button === 1 || (ev.button === 0 && space)) {
      ev.preventDefault();
      canvas.setPointerCapture(ev.pointerId);
      const main = $('main');
      pan = { x: ev.clientX, y: ev.clientY, left: main.scrollLeft, top: main.scrollTop };
      document.body.dataset.panning = '';
      return;
    }
    if (ev.button !== 0) return;
    if (tool === 'copy') {
      const k = cellAt(ev), from = state.cells[copyFrom], to = state.cells[k];
      if (from && to && to.t === 'sink' && k !== copyFrom) edit(() => P.copySink(from, to));
      return;
    }
    if (tool === 'measure') {
      const pt = pointAt(ev);
      measure = !measure || measure.b ? { a: pt, b: null } : { ...measure, b: pt };
      refresh();
      if (measure.b) $('#bgDist') && $('#bgDist').focus();
      return;
    }
    if (tool === 'move') {
      if (!state.bg) return;
      canvas.setPointerCapture(ev.pointerId);
      drag = { before: JSON.stringify(state), from: pointAt(ev), x: state.bg.x, y: state.bg.y, moved: false, image: true };
      return;
    }
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
    if (pan) {
      const main = $('main');
      main.scrollLeft = pan.left - (ev.clientX - pan.x);
      main.scrollTop = pan.top - (ev.clientY - pan.y);
      return;
    }
    if (!drag) return;
    if (drag.image) {
      // only the picture moves while dragging; the drawing catches up when the drag ends
      const [x, y] = pointAt(ev);
      state.bg.x = drag.x + x - drag.from[0];
      state.bg.y = drag.y + y - drag.from[1];
      drag.moved = true;
      background(true);
      return;
    }
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
    if (pan) { pan = null; delete document.body.dataset.panning; return; }
    if (!drag) return;
    const d = drag;
    drag = null;
    if (!d.moved && (tool === 'draw' || tool === 'select')) selected = cells()[d.last] ? d.last : null;
    commit(d.before);
  };
  canvas.addEventListener('pointerup', endDrag);
  canvas.addEventListener('pointercancel', endDrag);

  // ---- tools and keys ----------------------------------------------------------------------
  for (const btn of document.querySelectorAll('[data-tool]')) btn.onclick = () => { tool = btn.dataset.tool; measure = null; copyFrom = null; refresh(); };
  $('#copyDone').onclick = () => endCopy();
  // The key to the marks of sinks set up alike, pinned to the bottom left of the grid as it is seen, so
  // it is in sight however the grid is scrolled (the row's picture draws it in its own corner instead).
  function sinkKey() {
    const box = $('#sinkKey'), key = net.errors.length ? [] : P.sinkKey(state, net, inputs);
    box.hidden = !key.length;
    if (!key.length) { box.replaceChildren(); return; }
    const t = svgTheme();
    box.replaceChildren(...key.map((e) => {
      const mark = new DOMParser().parseFromString(`<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 18 18">${P.tourMark(e.mark, 0, 0, t.text, t.paper)}</svg>`, 'image/svg+xml').documentElement;
      return el('div', { class: 'key-row', title: e.sinks.join(', ') }, document.importNode(mark, true),
        el('span', {}, e.text), el('span', { class: 'key-sinks' }, e.sinks.join(', ')));
    }));
  }

  // A banner over the grid while the sheet's values drawn here wait on its solver: from the solver's
  // state when the sheet sends it (solver_state), else from the values' own out-of-date flags.
  function solveBanner() {
    const say = solverState === null ? (inputs.some((v) => v.stale) ? 0 : 1) : solverState;
    const text = {
      0: "Waiting on the solver: the sheet's values drawn here are from before the last change, until it solves this layout. If it cannot, its row in the sheet says why.",
      [-1]: "The sheet's solver has not run on this layout yet: the values drawn here are its starting values. Run it from its row in the sheet, or turn on its Auto.",
      [-2]: "The sheet's solver block has an error, so the values drawn here are not solved: its row in the sheet says what.",
    }[say];
    const box = $('#solveBanner');
    box.hidden = !text;
    box.dataset.state = String(say);
    if (text) $('#solveText').textContent = text;
  }

  function endCopy() { tool = 'select'; if (copyFrom && state.cells[copyFrom]) selected = copyFrom; copyFrom = null; refresh(); }
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
  // Zoom to `z`, keeping the point at (clientX, clientY) where it is: the middle of the view for the
  // buttons, the pointer for Ctrl + the wheel (and a touchpad's pinch, which the browser sends as that).
  function zoomTo(z, clientX, clientY) {
    const main = $('main'), r = main.getBoundingClientRect();
    if (clientX === undefined) { clientX = r.left + main.clientWidth / 2; clientY = r.top + main.clientHeight / 2; }
    const ox = clientX - r.left, oy = clientY - r.top, b = shownBounds, side = P.CELL * zoom;
    const col = (main.scrollLeft + ox) / side + b.c0, row = (main.scrollTop + oy) / side + b.r0;
    zoom = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z));
    refresh();
    const nb = shownBounds, ns = P.CELL * zoom;
    main.scrollLeft = (col - nb.c0) * ns - ox;
    main.scrollTop = (row - nb.r0) * ns - oy;
  }
  $('#zoomOut').onclick = () => zoomTo(zoom / 1.25);
  $('#zoomIn').onclick = () => zoomTo(zoom * 1.25);
  $('#zoom100').onclick = () => zoomTo(1);
  $('main').addEventListener('wheel', (ev) => {
    if (!ev.ctrlKey && !ev.metaKey) return;
    ev.preventDefault();
    const d = ev.deltaMode === 1 ? ev.deltaY * 16 : ev.deltaY;
    zoomTo(zoom * Math.exp(-d * 0.0015), ev.clientX, ev.clientY);
  }, { passive: false });
  // Fit: the tiles and the background image, in the view.
  $('#zoomFit').onclick = () => {
    const box = $('main'), bb = extent(), w = (bb.c1 - bb.c0 + 1) * P.CELL, h = (bb.r1 - bb.r0 + 1) * P.CELL;
    zoom = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.min(box.clientWidth / w, box.clientHeight / h)));
    refresh(true);
    box.scrollLeft = (bb.c0 - shownBounds.c0) * P.CELL * zoom;
    box.scrollTop = (bb.r0 - shownBounds.r0) * P.CELL * zoom;
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

  document.addEventListener('keyup', (ev) => { if (ev.key === ' ') { space = false; delete document.body.dataset.space; } });
  window.addEventListener('blur', () => { space = false; delete document.body.dataset.space; });
  document.addEventListener('keydown', (ev) => {
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName)) return;
    const k = ev.key.toLowerCase();
    if (k === ' ') { ev.preventDefault(); space = true; document.body.dataset.space = ''; return; }
    if (k === 'escape' && measure) { measure = null; refresh(); return; }
    if (k === 'escape' && tool === 'copy') { endCopy(); return; }
    if ((ev.ctrlKey || ev.metaKey) && (k === '=' || k === '+')) { ev.preventDefault(); zoomTo(zoom * 1.25); return; }
    if ((ev.ctrlKey || ev.metaKey) && k === '-') { ev.preventDefault(); zoomTo(zoom / 1.25); return; }
    if ((ev.ctrlKey || ev.metaKey) && k === '0') { ev.preventDefault(); zoomTo(1); return; }
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
  $('#hold').onchange = (e) => edit(() => { state.hold = e.target.value; });
  $('#solver').replaceChildren(...P.SOLVERS.map(([n, name, what]) => Object.assign(document.createElement('option'), { value: String(n), textContent: name, title: what })));
  $('#solver').onchange = (e) => edit(() => { state.solver = +e.target.value; });
  $('#qu').replaceChildren(...P.Q_UNITS.map(([u]) => Object.assign(document.createElement('option'), { value: u, textContent: u })));
  $('#qv').onchange = (e) => { const x = positive(e.target.value); if (x) edit(() => { state.q.v = x; }); else refresh(); };
  $('#qu').onchange = (e) => edit(() => { state.q.u = e.target.value; });
  // On the drawing: a checkbox for each set of data the balloons can show, the plugin's own (segment
  // numbers, pipe sizes, lengths, bores, each sink's curves) and each of the sheet's !pluginvar values.
  const BUILT_IN = [['numbers', 'Segment numbers'], ['size', 'Pipe size'], ['L', 'Length'], ['D', 'D_h (bore)'],
    ['hx', 'Exchanger curve'], ['pump', 'Circulator'], ['valve', 'Regulating valve']];
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
  // ...`, `!pluginvar pumps: ...`), else by number. A number past the names is kept, and said so.
  function curvePick(label, names, value, set, none = false) {
    const least = none ? 0 : 1;
    if (!names) return field(label + (none ? ' (number, 0 for none)' : ' (number)'), value, '1', (v) => edit(() => { const x = Math.round(parseFloat(v)); if (x >= least) set(x); }));
    const pick = el('select', { 'aria-label': label });
    if (none) pick.append(el('option', { value: '0' }, 'None'));
    pick.append(...names.map((n, i) => el('option', { value: String(i + 1) }, n)));
    if (value > names.length) pick.append(el('option', { value: String(value) }, `${value}: not named in the sheet`));
    pick.value = String(value);
    pick.onchange = () => edit(() => set(+pick.value));
    return el('label', { class: 'f stack' }, label, pick);
  }

  // "S3" for a sink: its name, else its number
  const sinkName = (k) => (state.cells[k] && state.cells[k].name) || 'S' + ((net.sinks.findIndex((s) => s.key === k) + 1) || '?');

  // A sink's settings in words, by the sheet's names where it gives them.
  function describe(pad) {
    const names = P.curveNames(inputs), name = (list, n, none) => (n === 0 && none ? none : (list && list[n - 1]) || `curve ${n}`);
    return [`exchanger ${name(names.exchangers, pad.x)}`, `circulator ${name(names.pumps, pad.s, 'none')}`,
      pad.v ? `valve Cv ${P.fmt(pad.v)}` : 'no valve', ...(pad.k ? [`extra K ${P.fmt(pad.k)}`] : [])].join(', ');
  }

  function inspector() {
    const box = $('#inspector');
    if (tool === 'copy' && state.cells[copyFrom]) {
      const from = state.cells[copyFrom];
      box.replaceChildren(
        el('p', {}, `Click sinks to give them ${sinkName(copyFrom)}'s settings: ${describe(from)}.`),
        el('div', { class: 'row-btns' },
          el('button', { onclick: () => edit(() => { for (const t of Object.values(state.cells)) if (t.t === 'sink' && t !== from) P.copySink(from, t); }) }, 'To every sink'),
          el('button', { onclick: endCopy }, 'Done (Esc)')));
      return;
    }
    const t = selected && cells()[selected];
    if (!t) { box.replaceChildren(el('p', { class: 'hint' }, 'Click a tile with Select (or click without dragging while drawing).')); return; }
    const [r, c] = P.at(selected), seg = P.segmentAt(walked(), selected), pad = state.cells[selected];
    const sh = P.shape(t), parts = [], prefix = front() === 'r' ? 'R' : '';
    const where = state.ret === 'separate' ? (front() === 'r' ? ' on the return' : ' on the supply') : '';
    parts.push(el('div', { class: 'kv' },
      el('span', {}, 'Tile'), el('span', {}, `${sh} at row ${r}, column ${c}${where}`),
      ...(seg && seg.row !== undefined ? [el('span', {}, 'Segment'), el('span', {}, `${prefix}${seg.row + 1}: ${P.fmt(seg.L)} ${state.units.L} long, ${P.sizeName(state, seg.nps)} (${P.fmt(seg.D)} ${state.units.D}), ${fittings(seg.n)}${seg.K ? `, extra K ${P.fmt(seg.K)}` : ''}`)] : [])));
    if (seg && seg.row !== undefined) {
      // a segment's length as a whole (blank: back to the length of its squares)
      const lengthField = field(`Segment length (${state.units.L})`, Number(seg.L.toPrecision(6)),
        String(seg.tiles.length * state.cell), (v) => {
          const x = v.trim() === '' ? null : positive(v);
          if (v.trim() !== '' && !x) { refresh(); return; }
          const before = JSON.stringify(state);
          if (!P.setSegmentLength(cells(), seg, x, state.cell)) { refresh(); return; }   // not possible: as it was
          commit(before);
        });
      parts.push(lengthField);
    } else if (t.t === 'pipe' || t.t === 'sink') {
      parts.push(field(`Length (${state.units.L})`, t.L, String(state.cell), (v) => edit(() => { const x = positive(v); if (x) t.L = x; else delete t.L; })));
    }
    if (t.t === 'pipe') {
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
      // Its settings: exchanger, circulator, valve, extra K. With sinks set up like it, a switch says
      // whether a change goes to this sink alone or to all of them (outlined in orange while it does).
      const alike = P.twins(state), mine = alike[selected];
      const same = mine === undefined ? [] : Object.keys(alike).filter((k) => k !== selected && alike[k] === mine);
      const all = applyAll && same.length > 0;
      const each = (fn) => { for (const k of all ? [selected, ...same] : [selected]) fn(state.cells[k], cells()[k]); };
      const group = el('div', { class: 'sink-settings' + (all ? ' all' : '') });
      if (same.length) {
        const sw = (on, label, title) => el('button', { 'aria-pressed': String(all === on), title,
          onclick: () => { applyAll = on; inspector(); } }, label);
        group.append(el('div', { class: 'tools apply', role: 'group', 'aria-label': 'Change' },
          sw(false, 'This sink', 'A change here goes to this sink alone'),
          sw(true, `All ${same.length + 1} alike`, `A change here goes to this sink and ${same.map(sinkName).join(', ')}`)));
      }
      const names = P.curveNames(inputs);
      group.append(
        curvePick('Exchanger curve', names.exchangers, pad.x, (x) => each((p) => { p.x = x; })),
        curvePick('Circulator', names.pumps, pad.s, (x) => each((p) => { p.s = x; }), true),
        field('Regulating valve Cv (blank: none)', pad.v, 'none', (v) => edit(() => {
          const x = parseFloat(v);
          each((p) => { if (isFinite(x) && x > 0) p.v = x; else delete p.v; });
        })),
        field('Extra K (a valve, from its datasheet)', t.k, '0', (v) => edit(() => {
          const x = parseFloat(v);
          each((p, u) => { if (isFinite(x) && x > 0) u.k = x; else delete u.k; });
        })));
      if (all) group.append(el('p', { class: 'warn-all' }, `Changes go to ${same.length + 1} sinks: this one and ${same.map(sinkName).join(', ')}.`));
      parts.push(group);
      parts.push(el('p', { class: 'hint' }, same.length
        ? `Set up like ${same.map(sinkName).join(', ')} (the mark at their corner).`
        : 'Set up like no other sink.'));
      parts.push(el('div', { class: 'row-btns' },
        el('button', { title: 'Then click the sinks that should have this exchanger, circulator, valve and extra K',
          onclick: () => { copyFrom = selected; tool = 'copy'; refresh(); } }, 'Copy settings to…')));
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
    // holding a flow, the pump's pressure difference is found: below zero, the circulators alone push more
    const pump = inputs.find((v) => v.name === 'Δp_pump' && typeof v.mag === 'number');
    const throttle = state.hold === 'flow' && pump && pump.mag < 0 && !pump.stale ? [{ cls: 'err',
      msg: `The main pump's pressure difference comes out below zero (${P.fmt(pump.mag, pump.unit)}): the circulators alone push more than the target flow, so the pump would have to hold the flow back. Raise the target flow, or take circulators off spurs.` }] : [];
    const list = [...replaced, ...throttle, ...net.errors.map((e) => ({ ...e, cls: 'err' })), ...net.warnings.map((w) => ({ ...w, cls: 'warn' }))];
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
      const shead = el('tr', {}, el('th', {}, 'Sink'), el('th', {}, 'exchanger'), el('th', {}, 'circulator'), el('th', { title: 'regulating valve Cv' }, 'valve Cv'),
        ...vals.sinks.map((v) => el('th', {}, v.name + (v.unit ? ` ${v.unit}` : ''))));
      const srows = net.sinks.map((s, j) => el('tr', { class: selected === s.key ? 'sel' : '', onclick: () => { selected = s.key; refresh(); } },
        el('td', {}, `${j + 1} ${s.name}`), el('td', { class: 'name' }, P.curveName(names.exchangers, s.x)),
        el('td', { class: 'name' }, P.curveName(names.pumps, s.s)), el('td', {}, s.v ? P.fmt(s.v) : '–'),
        ...vals.sinks.map((v) => el('td', { class: v.stale ? 'stale' : '' }, P.fmt(v.values[j])))));
      $('#sinks').replaceChildren(el('table', {}, el('thead', {}, shead), el('tbody', {}, ...srows)));
    }
    const notes = [];
    if (vals.legend.length) notes.push(vals.legend.map((v) => `${v.name} = ${P.fmt(v.values[0], v.unit)}`).join(', '));
    if (vals.unplaced.length) notes.push(`Not drawn (not one per segment or per sink): ${vals.unplaced.join(', ')}`);
    if (!inputs.length) notes.push('Add `!pluginvar Q, Δp` below the calculation to see the sheet\'s values here.');
    $('#about').textContent = notes.join('. ');
  }

  // ---- the background image -----------------------------------------------------------------
  // The picture behind the grid: an <img> under the drawing, so it is not drawn again with every
  // change. It is recalled from LENS the first time its key is seen.
  function background(shown) {
    const img = $('#bg'), g = state.bg;
    if (g && bg.key !== g.key && bg.asked !== g.key) { bg.asked = g.key; post({ type: 'lens:recall', key: g.key }); }
    img.hidden = !shown;
    if (!shown) { img.removeAttribute('src'); return; }
    if (img.getAttribute('src') !== bg.data) img.src = bg.data;
    const b = shownBounds, side = P.CELL * zoom;
    Object.assign(img.style, { left: (g.x - b.c0) * side + 'px', top: (g.y - b.r0) * side + 'px',
      width: g.w * side + 'px', height: g.w * g.ar * side + 'px', opacity: g.o });
  }

  // The two points of a scale, and the line between them, on the drawing.
  function markers() {
    const b = shownBounds, X = (p) => (p[0] - b.c0) * P.CELL, Y = (p) => (p[1] - b.r0) * P.CELL, ns = 'http://www.w3.org/2000/svg';
    const add = (tag, attrs) => { const e = document.createElementNS(ns, tag); for (const [a, v] of Object.entries(attrs)) e.setAttribute(a, v); canvas.append(e); };
    const color = css('err');
    if (measure.b) add('line', { x1: X(measure.a), y1: Y(measure.a), x2: X(measure.b), y2: Y(measure.b), stroke: color, 'stroke-width': 2 / zoom, 'stroke-dasharray': `${6 / zoom} ${4 / zoom}` });
    for (const p of [measure.a, measure.b].filter(Boolean)) {
      add('circle', { cx: X(p), cy: Y(p), r: 6 / zoom, fill: 'none', stroke: color, 'stroke-width': 2 / zoom });
      add('line', { x1: X(p) - 10 / zoom, y1: Y(p), x2: X(p) + 10 / zoom, y2: Y(p), stroke: color, 'stroke-width': 1 / zoom });
      add('line', { x1: X(p), y1: Y(p) - 10 / zoom, x2: X(p), y2: Y(p) + 10 / zoom, stroke: color, 'stroke-width': 1 / zoom });
    }
  }

  // A key for a picture: a hash of its data, so the same picture placed again is kept once.
  function keyFor(data) {
    let h1 = 0x811c9dc5, h2 = 0x01000193;
    for (let i = 0; i < data.length; i++) {
      const c = data.charCodeAt(i);
      h1 = Math.imul(h1 ^ c, 0x01000193) >>> 0;
      h2 = Math.imul(h2 ^ c, 0x5bd1e995) >>> 0;
    }
    return `img-${h1.toString(16)}${h2.toString(16)}-${data.length.toString(36)}`;
  }

  // Place a picture: a new one goes at the top left of the view, as wide as the view; one placed over
  // another (an updated planset, or the same one on a computer that did not have it) takes its place
  // and its size, so the pipes still line up with it.
  function place(file) {
    if (!file) return;
    if (!/^image\//.test(file.type)) { say(`${file.name} is not an image. Save a PDF's page as PNG or JPEG first.`); return; }
    const reader = new FileReader();
    reader.onerror = () => say(`Could not read ${file.name}.`);
    reader.onload = () => {
      const data = reader.result, img = new Image();
      img.onerror = () => say(`${file.name} could not be shown as an image.`);
      img.onload = () => {
        const key = keyFor(data), ar = img.naturalHeight / img.naturalWidth || 1, main = $('main'), side = P.CELL * zoom, b = shownBounds;
        post({ type: 'lens:keep', key, data });
        bg = { key, data, asked: null };
        edit(() => {
          const old = state.bg;
          state.bg = old ? { ...old, key, name: file.name, ar }
            : { key, name: file.name, x: main.scrollLeft / side + b.c0, y: main.scrollTop / side + b.r0, w: main.clientWidth / side, ar, o: 0.5 };
        });
        tool = 'move';
        refresh();
      };
      img.src = data;
    };
    reader.readAsDataURL(file);
  }
  let note = '';
  const say = (msg) => { note = msg; bgPanel(); };
  $('#bgPlace').onclick = () => $('#bgFile').click();
  $('#bgFile').onchange = (e) => { place(e.target.files[0]); e.target.value = ''; };
  const main = $('main');
  main.addEventListener('dragover', (ev) => { if ([...ev.dataTransfer.types].includes('Files')) ev.preventDefault(); });
  main.addEventListener('drop', (ev) => { const f = ev.dataTransfer.files[0]; if (f) { ev.preventDefault(); place(f); } });
  $('#bgRemove').onclick = () => { measure = null; if (tool === 'move' || tool === 'measure') tool = 'draw'; edit(() => { delete state.bg; }); };
  // the picture follows the slider as it moves; the sheet gets the opacity when it is let go
  $('#bgO').oninput = (e) => { $('#bg').style.opacity = +e.target.value / 100; };
  $('#bgO').onchange = (e) => { if (state.bg) edit(() => { state.bg.o = +e.target.value / 100; }); };
  $('#bgW').onchange = (e) => {
    const x = positive(e.target.value);
    if (x && state.bg) edit(() => { state.bg.w = x / state.cell; }); else refresh();
  };
  // Scale from two points: the picture grows or shrinks about the first so the two are as far apart
  // on the grid as the distance given (in squares of the square length).
  function applyScale() {
    const d = positive($('#bgDist').value);
    if (!d || !measure || !measure.b || !state.bg) return;
    const [ax, ay] = measure.a, [bx, by] = measure.b, now = Math.hypot(bx - ax, by - ay);
    if (!(now > 0)) return;
    const f = d / state.cell / now;
    measure = null;
    tool = 'move';
    edit(() => { const g = state.bg; g.x = ax + (g.x - ax) * f; g.y = ay + (g.y - ay) * f; g.w *= f; });
  }

  function bgPanel() {
    const g = state.bg, has = !!g, here = has && bg.key === g.key && bg.data;
    $('#bgRemove').disabled = !has;
    $('#bgEdit').hidden = !has;
    $('#bgPlace').textContent = has ? 'Replace image…' : 'Place image…';
    $('#bgPlace').title = has ? 'Put another picture in its place, at its size (an updated planset)' : 'Put a picture behind the grid (PNG, JPEG, SVG, WebP), or drop one on the grid';
    let hint = note;
    if (has && bg.key === g.key && !bg.data) hint = `${g.name} is not kept in this browser. Replace image… with it to put it back where it was.`;
    else if (!hint && has) hint = here ? `${g.name}. Move: drag it. Scale: click two points a known distance apart.` : `Loading ${g.name}…`;
    $('#bgNote').textContent = hint;
    note = '';
    if (!has) return;
    setNum($('#bgW'), +(g.w * state.cell).toPrecision(6));
    $('#bgWUnit').textContent = `Width (${state.units.L})`;
    if (document.activeElement !== $('#bgO')) $('#bgO').value = Math.round(g.o * 100);
    const box = $('#bgMeasure');
    if (tool !== 'measure') { box.replaceChildren(); return; }
    if (!measure || !measure.b) {
      box.replaceChildren(el('p', { class: 'hint' }, measure ? 'Now click the second point.' : 'Click the first of two points a known distance apart on the picture (the ends of a dimension, a grid line to the next).'));
      return;
    }
    if ($('#bgDist')) return;   // the field is up: leave what is being typed alone
    const input = el('input', { id: 'bgDist', type: 'number', min: '0', step: 'any', placeholder: 'distance' });
    input.onkeydown = (e) => { if (e.key === 'Enter') applyScale(); if (e.key === 'Escape') { measure = null; refresh(); } };
    box.replaceChildren(el('label', { class: 'f stack' }, `Distance between the points (${state.units.L})`,
      el('span', { class: 'pair' }, input, el('button', { onclick: applyScale }, 'Scale'))));
  }

  window.addEventListener('resize', () => refresh());   // the frame is sized when its dialog opens
  refresh();
  post({ type: 'lens:ready' });
})();
