/* Pipe network: the model behind the pipenet plugin. Pure functions; runs under Node
 * (tests/test_pipenet.js) and in the plugin's page (app.js).
 *
 * A layout is a grid of tiles. Each tile has the sides it connects on, as a bit mask of
 * N=1, E=2, S=4, W=8, and a type:
 *
 *   pipe     its shape follows from its sides: two opposite are a straight, two adjacent an elbow,
 *            three a tee, all four a crossover (two pipes crossing without meeting); one side is a
 *            dead end, which is an error
 *   source   the pump: one side, where the supply leaves it
 *   sink     a load at the end of a branch (a coil, an exchanger): one side, where the supply reaches it
 *
 * The state the plugin keeps in its block's `#@ state` line:
 *
 *   {v: 1, units: {L: "ft", D: "in"}, cell: 10, D: 4, ret: true, method: 1, labels: "values", cells: {"r,c": tile}}
 *   method: how the sheet works out fitting losses: 1 Crane TP-410, 2 Hooper 2-K, 3 Darby 3-K (METHODS)
 *   labels: what the drawing shows beside the pipes: "values" (the sheet's), "numbers" or "none"
 *   tile: {t: "pipe"|"source"|"sink", p: sides, L?: length of this tile, d?: diameter,
 *          k?: extra loss coefficient K on this tile (a valve, from its datasheet), name?,
 *          x?: exchanger curve, s?: pump speed}
 *
 * `analyze(state)` walks the tree from the source. The water splits only at tees, so the network is
 * a set of segments, each the pipe from one junction to the next: a segment that ends at a sink is
 * that sink's spur, any other ends at a tee. Segments are numbered as the sheet's vectors are: the
 * spurs first, in the order of their sinks, then the rest from the source outwards. Sinks are
 * numbered in the order the walk reaches them, so the sinks of a branch are numbered together.
 *
 *   A      the upstream matrix: one row per segment, one column per sink, 1 where the segment carries
 *          that sink's water. With the spurs first, its top is the identity
 *   L      each segment's length: the sum of its tiles' lengths (a tile is `cell` long unless it says)
 *   D      each segment's diameter (that of its first tile, or the default)
 *   n      each segment's fittings, counted by kind (FITTINGS): 90° elbows, tees the flow passes
 *          straight through (runs), and tees the flow turns through (branches). A segment owns the
 *          tee it leaves through, so a tee counts once on each segment that leaves it: as a run on the
 *          one straight on, as a branch on the others. The sheet turns the counts into K with the
 *          coefficient table of the method chosen
 *   K      each segment's extra loss coefficients (`k` on its tiles), added to the fittings' as they are
 *   With `ret`, L, n and K are doubled: the return pipe runs beside the supply and matches it.
 *
 * `outputs(state, analysis)` gives the sheet lines; `draw(...)` the picture, as SVG text.
 */
(function (root) {
  'use strict';

  const N = 1, E = 2, S = 4, W = 8;
  const DIRS = [N, E, S, W];
  const DR = { [N]: -1, [E]: 0, [S]: 1, [W]: 0 };
  const DC = { [N]: 0, [E]: 1, [S]: 0, [W]: -1 };
  const OPP = { [N]: S, [E]: W, [S]: N, [W]: E };
  const CW = { [N]: E, [E]: S, [S]: W, [W]: N };
  const NAMES = { [N]: 'N', [E]: 'E', [S]: 'S', [W]: 'W' };
  // The kinds of fitting counted, in the order of N_fit!'s columns and of the sheet's coefficient
  // tables' rows; and the methods the sheet offers for turning the counts into K (fit_method!).
  const FITTINGS = ['elbow', 'run', 'branch'];
  const ELBOW = 0, RUN = 1, BRANCH = 2;
  const METHODS = { 1: 'Crane TP-410: K = (L/D)·f_T', 2: 'Hooper 2-K', 3: 'Darby 3-K' };

  const key = (r, c) => `${r},${c}`;
  const at = (k) => k.split(',').map(Number);
  const bits = (p) => DIRS.filter((d) => p & d);
  const step = (k, d) => { const [r, c] = at(k); return key(r + DR[d], c + DC[d]); };
  const rotate = (p) => DIRS.reduce((m, d) => (p & d ? m | CW[d] : m), 0);

  function shape(tile) {
    if (!tile) return null;
    if (tile.t !== 'pipe') return tile.t;
    const b = bits(tile.p);
    if (b.length === 4) return 'cross';
    if (b.length === 3) return 'tee';
    if (b.length === 2) return OPP[b[0]] === b[1] ? 'straight' : 'elbow';
    return b.length === 1 ? 'stub' : 'empty';
  }

  function blank() {
    return { v: 1, units: { L: 'ft', D: 'in' }, cell: 10, D: 4, ret: true, method: 1, labels: 'values', cells: {} };
  }

  // A state as given, with anything missing or odd replaced by the default, and tiles cleaned.
  function normalize(s) {
    const b = blank();
    if (!s || typeof s !== 'object') return b;
    const num = (x, d) => (typeof x === 'number' && isFinite(x) && x > 0 ? x : d);
    const out = {
      v: 1,
      units: { L: ['ft', 'm', 'in', 'mm'].includes(s.units && s.units.L) ? s.units.L : b.units.L,
               D: ['in', 'mm', 'ft', 'm'].includes(s.units && s.units.D) ? s.units.D : b.units.D },
      cell: num(s.cell, b.cell), D: num(s.D, b.D), ret: s.ret !== false,
      method: [1, 2, 3].includes(s.method) ? s.method : b.method,
      labels: ['values', 'numbers', 'none'].includes(s.labels) ? s.labels : b.labels, cells: {},
    };
    for (const [k, t] of Object.entries(s.cells || {})) {
      if (!/^-?\d+,-?\d+$/.test(k) || !t || !['pipe', 'source', 'sink'].includes(t.t)) continue;
      const p = (t.p | 0) & 15;
      const tile = { t: t.t, p };
      if (num(t.L, 0)) tile.L = t.L;
      if (num(t.d, 0)) tile.d = t.d;
      if (typeof t.k === 'number' && isFinite(t.k) && t.k >= 0) tile.k = t.k;
      if (t.t === 'sink') {
        if (typeof t.name === 'string') tile.name = t.name.slice(0, 40);
        tile.x = Math.max(1, Math.round(num(t.x, 1)));
        tile.s = Math.max(1, Math.round(num(t.s, 2)));
      }
      out.cells[k] = tile;
    }
    return out;
  }

  // ---- the walk -------------------------------------------------------------------------
  function analyze(state) {
    const cells = state.cells, errors = [], warnings = [];
    const sources = Object.keys(cells).filter((k) => cells[k].t === 'source');
    const result = { segments: [], sinks: [], order: [], A: [], errors, warnings, seen: new Set(), source: null };
    const fail = (k, msg) => errors.push({ key: k, msg });
    if (!sources.length) { fail(null, 'Place a source (the pump) to start the network'); return finish(result, state); }
    if (sources.length > 1) { for (const k of sources) fail(k, 'There can be only one source'); return finish(result, state); }
    const src = sources[0];
    result.source = src;
    result.seen.add(src + '|*');
    if (bits(cells[src].p).length !== 1) { fail(src, 'The source connects on one side'); return finish(result, state); }

    const segs = result.segments;
    const tileLen = (k) => (cells[k].L !== undefined ? cells[k].L : state.cell);
    const newSeg = (parent, from, out, kind) => {
      const n = [0, 0, 0];
      if (kind !== null) n[kind] = 1;
      const s = { id: segs.length, parent, from, out, tiles: [], L: 0, n, K: 0, D: null, sink: null, children: [], ends: null };
      segs.push(s);
      if (parent !== null) segs[parent].children.push(s.id);
      return s;
    };

    // Follow the pipe from tile `from` out of its side `out`, as segment `seg`.
    const walk = (seg, from, out) => {
      for (let guard = 0; guard < 100000; guard++) {
        const k = step(from, out), tile = cells[k], into = OPP[out];
        if (!tile || !(tile.p & into)) { fail(from, 'The pipe stops here: it leads into ' + (tile ? 'a tile with no opening on that side' : 'an empty square')); return; }
        const sh = shape(tile);
        const lane = sh === 'cross' ? (into === N || into === S ? 'v' : 'h') : '*';
        if (result.seen.has(k + '|' + lane)) { fail(k, 'The pipe runs into itself here: the network must be a tree, with no loops'); return; }
        result.seen.add(k + '|' + lane);
        seg.tiles.push(k);
        seg.L += tileLen(k);
        if (tile.k) seg.K += tile.k;
        if (seg.D === null && tile.t !== 'source') seg.D = tile.d || null;
        else if (tile.d && seg.D !== null && tile.d !== seg.D && !seg.mixed) {
          seg.mixed = true;
          warnings.push({ key: k, msg: `Segment ${seg.id + 1} has more than one diameter; the first one is used` });
        }
        if (sh === 'sink') { seg.sink = k; return; }
        if (sh === 'source') { fail(k, 'The pipe runs back into the source'); return; }
        if (sh === 'stub') { fail(k, 'Dead end: this pipe connects on one side only'); return; }
        if (sh === 'straight' || sh === 'cross') { from = k; out = OPP[into]; continue; }
        if (sh === 'elbow') { from = k; out = bits(tile.p).find((d) => d !== into); seg.n[ELBOW] += 1; continue; }
        // a tee: the segment ends, and one starts down each other side
        const outs = bits(tile.p).filter((d) => d !== into);
        const straight = OPP[into];
        const runs = outs.includes(straight);
        seg.ends = k;
        const rank = (d) => (d === straight ? 0 : d === CW[straight] ? 1 : 2);   // straight on, then right, then left
        for (const d of outs.slice().sort((p, q) => rank(p) - rank(q))) walk(newSeg(seg.id, k, d, runs && d === straight ? RUN : BRANCH), k, d);
        return;
      }
    };
    const first = newSeg(null, src, bits(cells[src].p)[0], null);
    walk(first, src, first.out);
    return finish(result, state);
  }

  function finish(res, state) {
    const cells = state.cells;
    for (const k of Object.keys(cells)) {
      const sh = shape(cells[k]);
      const lanes = sh === 'cross' ? ['v', 'h'] : ['*'];
      if (lanes.every((l) => !res.seen.has(k + '|' + l)) && res.source !== null && !res.errors.length)
        res.warnings.push({ key: k, msg: 'Not connected to the source, so it is left out' });
    }
    if (res.errors.length) return res;
    const segs = res.segments;
    // sinks, in the order the walk reached them (depth first, straight on before the branches)
    const pre = [];
    const visit = (id) => { pre.push(id); for (const c of segs[id].children) visit(c); };
    if (segs.length) visit(0);
    const spurs = pre.filter((id) => segs[id].sink !== null);
    if (!spurs.length) { res.errors.push({ key: null, msg: 'Place a sink at the end of a pipe: nothing uses the water yet' }); return res; }
    res.order = spurs.concat(pre.filter((id) => segs[id].sink === null));
    res.sinks = spurs.map((id, j) => {
      const t = cells[segs[id].sink];
      return { key: segs[id].sink, seg: id, name: t.name || `S${j + 1}`, x: t.x || 1, s: t.s || 2 };
    });
    const row = new Map(res.order.map((id, i) => [id, i]));
    for (const s of segs) s.row = row.get(s.id);
    res.A = res.order.map(() => res.sinks.map(() => 0));
    res.sinks.forEach((sink, j) => {
      for (let id = sink.seg; id !== null; id = segs[id].parent) res.A[row.get(id)][j] = 1;
    });
    for (const s of segs) if (s.D === null) s.D = state.D;
    return res;
  }

  // ---- what goes into the sheet -----------------------------------------------------------
  function num(x) {
    if (!isFinite(x)) return '0';
    const r = Number(x.toPrecision(6));
    return String(r).replace(/e\+?/, 'e');
  }
  const column = (xs) => '[' + xs.map(num).join('; ') + ']';

  // {name: expression} for the block's lines, or {} when the network has an error.
  function outputs(state, a) {
    if (a.errors.length || !a.sinks.length) return {};
    const segs = a.order.map((id) => a.segments[id]), twice = state.ret ? 2 : 1;
    return {
      A: '[' + a.A.map((r) => r.join(', ')).join('; ') + ']',
      'L!': `${column(segs.map((s) => s.L * twice))} * '${state.units.L}`,
      'D_h!': `${column(segs.map((s) => s.D))} * '${state.units.D}`,
      'N_fit!': '[' + segs.map((s) => s.n.map((x) => num(x * twice)).join(', ')).join('; ') + ']',
      'K_extra!': column(segs.map((s) => s.K * twice)),
      'exchangers!': column(a.sinks.map((s) => s.x)),
      'speeds!': column(a.sinks.map((s) => s.s)),
      'fit_method!': String(state.method),
    };
  }

  // ---- values from the sheet --------------------------------------------------------------
  // Each `!pluginvar` value laid on the drawing: a vector as long as the segments goes on the
  // segments, one as long as the sinks on the sinks, a single number in the legend.
  function placed(inputs, a) {
    const out = { segments: [], sinks: [], legend: [], unplaced: [] };
    const nSeg = a.order.length, nSink = a.sinks.length;
    for (const v of inputs || []) {
      const flat = flatten(v.mag);
      if (flat === null) { out.unplaced.push(v.name); continue; }
      const item = { name: v.name, unit: v.unit, values: flat, stale: !!v.stale };
      if (flat.length === 1 && !(v.shape && v.shape.length)) out.legend.push(item);
      else if (flat.length === nSeg && nSeg) out.segments.push(item);
      else if (flat.length === nSink && nSink) out.sinks.push(item);
      else if (flat.length === 1) out.legend.push(item);
      else out.unplaced.push(v.name);
    }
    return out;
  }

  function flatten(m) {
    if (typeof m === 'number' || m === null) return [m];
    if (!Array.isArray(m)) return null;
    if (m.every((x) => typeof x === 'number' || x === null)) return m;
    if (m.every((r) => Array.isArray(r) && r.length === 1)) return m.map((r) => r[0]);
    if (m.length === 1 && Array.isArray(m[0])) return m[0];
    return null;
  }

  function fmt(x, unit) {
    if (x === null || x === undefined || !isFinite(x)) return '–';
    const a = Math.abs(x);
    const t = a !== 0 && (a >= 1e5 || a < 1e-3) ? x.toExponential(2) : Number(x.toPrecision(3)).toString();
    return unit ? `${t} ${unit}` : t;
  }

  // ---- the picture ------------------------------------------------------------------------
  const CELL = 56;

  function bounds(state, pad = 2) {
    const ks = Object.keys(state.cells).map(at);
    if (!ks.length) return { r0: 0, c0: 0, r1: 7, c1: 11 };
    let r0 = Math.min(...ks.map((k) => k[0])) - pad, r1 = Math.max(...ks.map((k) => k[0])) + pad;
    let c0 = Math.min(...ks.map((k) => k[1])) - pad, c1 = Math.max(...ks.map((k) => k[1])) + pad;
    if (r1 - r0 < 7) r1 = r0 + 7;
    if (c1 - c0 < 11) c1 = c0 + 11;
    return { r0, c0, r1, c1 };
  }

  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  /* The layout as SVG text. opts: {theme: {paper, text, ink, rule, err, grid, sans, soft, hi}, selected: a tile
     key, grid: draw the grid (the editor) or not (the preview), inputs: the !pluginvar values}. */
  function draw(state, a, opts = {}) {
    const th = Object.assign({ paper: '#ffffff', text: '#1d2b3a', ink: '#1f5fa8', rule: '#9fb4c8', err: '#c62828',
      grid: '#e3eaf1', sans: 'sans-serif', soft: '#5b7086', hi: '#e08a00' }, opts.theme || {});
    const grid = opts.grid !== false;
    const b = opts.bounds || (grid ? bounds(state) : bounds(state, 1));
    const W_ = (b.c1 - b.c0 + 1) * CELL, H_ = (b.r1 - b.r0 + 1) * CELL;
    const x = (c) => (c - b.c0) * CELL, y = (r) => (r - b.r0) * CELL;
    const out = [`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W_} ${H_}" width="${W_}" height="${H_}" font-family="${esc(th.sans)}">`,
      `<rect width="${W_}" height="${H_}" fill="${esc(th.paper)}"/>`];
    if (grid) {
      for (let r = b.r0; r <= b.r1 + 1; r++) out.push(`<line x1="0" y1="${y(r)}" x2="${W_}" y2="${y(r)}" stroke="${esc(th.grid)}" stroke-width="1"/>`);
      for (let c = b.c0; c <= b.c1 + 1; c++) out.push(`<line x1="${x(c)}" y1="0" x2="${x(c)}" y2="${H_}" stroke="${esc(th.grid)}" stroke-width="1"/>`);
    }
    const bad = new Set(a.errors.map((e) => e.key).filter(Boolean));
    const loose = new Set(a.warnings.filter((w) => /Not connected/.test(w.msg)).map((w) => w.key));
    const segOf = new Map();
    for (const s of a.segments) for (const k of s.tiles) if (!segOf.has(k)) segOf.set(k, s);
    const selSeg = opts.selected ? segOf.get(opts.selected) : null;
    const h = CELL / 2, pw = 7;

    for (const [k, tile] of Object.entries(state.cells)) {
      const [r, c] = at(k), cx = x(c) + h, cy = y(r) + h;
      const seg = segOf.get(k);
      let color = loose.has(k) ? th.rule : th.ink;
      if (selSeg && seg === selSeg) color = th.hi;   // the selected tile's segment, in the theme's accent
      if (bad.has(k)) out.push(`<rect x="${x(c) + 2}" y="${y(r) + 2}" width="${CELL - 4}" height="${CELL - 4}" fill="none" stroke="${esc(th.err)}" stroke-width="2" stroke-dasharray="4 3"/>`);
      if (opts.selected === k) out.push(`<rect x="${x(c) + 1}" y="${y(r) + 1}" width="${CELL - 2}" height="${CELL - 2}" fill="none" stroke="${esc(th.hi)}" stroke-width="2"/>`);
      const sh = shape(tile);
      const arm = (d, len = h) => `<line x1="${cx}" y1="${cy}" x2="${cx + DC[d] * len}" y2="${cy + DR[d] * len}" stroke="${esc(color)}" stroke-width="${pw}" stroke-linecap="butt"/>`;
      if (sh === 'cross') {
        out.push(`<line x1="${cx}" y1="${y(r)}" x2="${cx}" y2="${y(r) + CELL}" stroke="${esc(color)}" stroke-width="${pw}"/>`);
        const hop = 11;
        out.push(`<path d="M ${x(c)} ${cy} H ${cx - hop} A ${hop} ${hop} 0 0 1 ${cx + hop} ${cy} H ${x(c) + CELL}" fill="none" stroke="${esc(th.paper)}" stroke-width="${pw + 6}"/>`);
        out.push(`<path d="M ${x(c)} ${cy} H ${cx - hop} A ${hop} ${hop} 0 0 1 ${cx + hop} ${cy} H ${x(c) + CELL}" fill="none" stroke="${esc(color)}" stroke-width="${pw}"/>`);
      } else if (sh === 'source') {
        for (const d of bits(tile.p)) out.push(arm(d));
        out.push(`<circle cx="${cx}" cy="${cy}" r="${h - 9}" fill="${esc(th.paper)}" stroke="${esc(color)}" stroke-width="3"/>`);
        const d = bits(tile.p)[0] || E, tr = h - 14;   // the pump's triangle points the way the water goes
        const px = DC[d], py = DR[d], qx = -py, qy = px;
        out.push(`<path d="M ${cx + px * tr} ${cy + py * tr} L ${cx - px * tr * 0.6 + qx * tr * 0.8} ${cy - py * tr * 0.6 + qy * tr * 0.8} L ${cx - px * tr * 0.6 - qx * tr * 0.8} ${cy - py * tr * 0.6 - qy * tr * 0.8} Z" fill="${esc(color)}"/>`);
      } else if (sh === 'sink') {
        for (const d of bits(tile.p)) out.push(arm(d));
        const s = h - 10;
        out.push(`<rect x="${cx - s}" y="${cy - s}" width="${2 * s}" height="${2 * s}" fill="${esc(th.paper)}" stroke="${esc(color)}" stroke-width="3"/>`);
        out.push(`<path d="M ${cx - s + 4} ${cy + 6} l 5 -12 l 5 12 l 5 -12 l 5 12 l 5 -12" fill="none" stroke="${esc(color)}" stroke-width="2"/>`);
      } else {
        for (const d of bits(tile.p)) out.push(arm(d));
        if (bits(tile.p).length > 1) out.push(`<circle cx="${cx}" cy="${cy}" r="${pw / 2}" fill="${esc(color)}"/>`);
        if (sh === 'stub') out.push(`<path d="M ${cx - 7} ${cy - 7} l 14 14 m 0 -14 l -14 14" stroke="${esc(th.err)}" stroke-width="3"/>`);
      }
    }

    // numbers and values: each segment at its middle tile, each sink beside it
    const vals = placed(opts.inputs, a);
    const label = (lx, ly, lines, anchor = 'start') => {
      const lh = 13, w = Math.max(...lines.map((l) => l.text.length)) * 6.4 + 8, x0 = anchor === 'start' ? lx : lx - w;
      out.push(`<rect x="${x0}" y="${ly - 11}" width="${w}" height="${lines.length * lh + 4}" rx="3" fill="${esc(th.paper)}" fill-opacity="0.88" stroke="${esc(th.rule)}" stroke-width="0.8"/>`);
      lines.forEach((l, i) => out.push(`<text x="${x0 + 4}" y="${ly + i * lh}" font-size="11" font-weight="${l.bold ? 600 : 400}" fill="${esc(l.soft ? th.soft : th.text)}">${esc(l.text)}</text>`));
    };
    // Each segment's number sits on its middle tile; its values, if shown, beside it, away from the pipe.
    const show = state.labels || 'values';
    if (!a.errors.length && show !== 'none') {
      for (const s of a.segments) {
        if (!s.tiles.length || s.row === undefined) continue;
        const own = s.tiles.length > 1 ? s.tiles.slice(0, -1) : s.tiles;   // not the tee or sink it ends at
        const mid = own[Math.floor((own.length - 1) / 2)];
        const [r, c] = at(mid), cx = x(c) + h, cy = y(r) + h;
        const lines = show === 'values' ? vals.segments.map((v) => ({ text: `${v.name} ${fmt(v.values[s.row], v.unit)}`, soft: v.stale })) : [];
        if (lines.length) {
          const vertical = !(state.cells[mid].p & (E | W));
          if (vertical) label(cx + 14, cy - (lines.length * 13) / 2 + 9, lines);
          else label(cx - 8, cy + 26, lines);
        }
        out.push(`<circle cx="${cx}" cy="${cy}" r="10" fill="${esc(th.paper)}" stroke="${esc(th.ink)}" stroke-width="2"/>`);
        out.push(`<text x="${cx}" y="${cy + 4}" font-size="11" font-weight="600" text-anchor="middle" fill="${esc(th.text)}">${s.row + 1}</text>`);
      }
      a.sinks.forEach((sink, j) => {
        const [r, c] = at(sink.key);
        const lines = [{ text: sink.name, bold: true }];
        if (show === 'values') for (const v of vals.sinks) lines.push({ text: `${v.name} ${fmt(v.values[j], v.unit)}`, soft: v.stale });
        if (state.cells[sink.key].p === E) label(x(c) + 2, y(r) + 14, lines, 'end');   // the pipe comes from the right
        else label(x(c) + CELL - 2, y(r) + 14, lines);
      });
    }
    if (vals.legend.length) {
      const lines = vals.legend.map((v) => ({ text: `${v.name} = ${fmt(v.values[0], v.unit)}`, soft: v.stale }));
      label(8, 18, lines);
    }
    out.push('</svg>');
    return out.join('');
  }

  // ---- editing --------------------------------------------------------------------------
  // Connect two neighbouring tiles, making pipe where there was none. A source or sink keeps one
  // side: the new one.
  function connect(state, k1, k2) {
    const [r1, c1] = at(k1), [r2, c2] = at(k2);
    const d = DIRS.find((x) => r1 + DR[x] === r2 && c1 + DC[x] === c2);
    if (!d) return false;
    const join = (k, side) => {
      const t = state.cells[k] || (state.cells[k] = { t: 'pipe', p: 0 });
      if (t.t === 'pipe') t.p |= side; else t.p = side;
    };
    join(k1, d);
    join(k2, OPP[d]);
    return true;
  }

  // Take a tile away; its neighbours lose their sides towards it.
  function erase(state, k) {
    if (!state.cells[k]) return false;
    delete state.cells[k];
    for (const d of DIRS) {
      const n = state.cells[step(k, d)];
      if (n && n.p & OPP[d]) { n.p &= ~OPP[d]; if (n.t === 'pipe' && !n.p) delete state.cells[step(k, d)]; }
    }
    return true;
  }

  // Put a tile of a palette shape down: {t, p}. A source or sink facing nowhere in particular
  // faces a neighbour whose pipe points at it, if there is one. Placing a second source moves it.
  function place(state, k, tile) {
    if (tile.t === 'source') for (const [o, t] of Object.entries(state.cells)) if (t.t === 'source' && o !== k) delete state.cells[o];
    const old = state.cells[k] || {};
    const t = { t: tile.t, p: tile.p };
    for (const f of ['L', 'd', 'k']) if (old[f] !== undefined) t[f] = old[f];
    if (tile.t === 'sink') { t.x = old.x || 1; t.s = old.s || 2; if (old.name) t.name = old.name; }
    if (tile.auto && tile.t !== 'pipe') {
      const d = DIRS.find((x) => { const n = state.cells[step(k, x)]; return n && n.p & OPP[x]; });
      if (d) t.p = d;
    }
    state.cells[k] = t;
  }

  // The segment a tile belongs to (the first, for a crossover), or null.
  function segmentAt(a, k) {
    return a.segments.find((s) => s.tiles.includes(k)) || null;
  }

  // ---- an example to start from: a trunk with three branches each way, eight loads ------------
  function example() {
    const s = blank(), path = (ks) => { for (let i = 1; i < ks.length; i++) connect(s, ks[i - 1], ks[i]); };
    const line = (r0, c0, r1, c1) => {
      const ks = [];
      for (let r = r0, c = c0; ; ) {
        ks.push(key(r, c));
        if (r === r1 && c === c1) return ks;
        if (c !== c1) c += Math.sign(c1 - c); else r += Math.sign(r1 - r);
      }
    };
    place(s, '2,0', { t: 'source', p: E });
    path(line(2, 0, 2, 20));
    for (const c of [2, 8, 14]) {
      path(line(2, c, 0, c)); path(line(0, c, 0, c + 2));                  // up, then along
      path(line(2, c + 3, 5, c + 3)); path(line(5, c + 3, 5, c + 5));      // down, then along
    }
    path(line(3, 17, 3, 19));
    for (const k of ['0,4', '5,7', '0,10', '5,13', '0,16', '3,19', '5,19', '2,20']) place(s, k, { t: 'sink', p: 0, auto: true });
    return s.cells;
  }

  // The palette: every shape in every orientation.
  const PALETTE = [
    { t: 'pipe', p: N | S, label: 'Straight' }, { t: 'pipe', p: E | W, label: 'Straight' },
    { t: 'pipe', p: N | E, label: 'Elbow' }, { t: 'pipe', p: E | S, label: 'Elbow' }, { t: 'pipe', p: S | W, label: 'Elbow' }, { t: 'pipe', p: W | N, label: 'Elbow' },
    { t: 'pipe', p: N | E | S, label: 'Tee' }, { t: 'pipe', p: E | S | W, label: 'Tee' }, { t: 'pipe', p: S | W | N, label: 'Tee' }, { t: 'pipe', p: W | N | E, label: 'Tee' },
    { t: 'pipe', p: N | E | S | W, label: 'Crossover' },
    { t: 'source', p: E, label: 'Source' }, { t: 'source', p: S, label: 'Source' }, { t: 'source', p: W, label: 'Source' }, { t: 'source', p: N, label: 'Source' },
    { t: 'sink', p: W, label: 'Sink' }, { t: 'sink', p: N, label: 'Sink' }, { t: 'sink', p: E, label: 'Sink' }, { t: 'sink', p: S, label: 'Sink' },
  ];

  const api = { N, E, S, W, DIRS, OPP, NAMES, CELL, FITTINGS, METHODS, key, at, bits, step, rotate, shape,
    blank, normalize, analyze, outputs, placed, flatten, fmt, bounds, draw, connect, erase, place, segmentAt, PALETTE, example };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.PipeNet = api;
})(typeof window !== 'undefined' ? window : globalThis);
