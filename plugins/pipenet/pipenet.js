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
 *   {v: 1, units: {L: "ft", D: "in"}, cell: 10, D: 4, ret: "same", method: 1, labels: "values",
 *    cells: {"r,c": tile}, rcells: {"r,c": tile}}
 *   ret: "same", the return pipe runs beside the supply and matches it, so its lines are the supply's;
 *        or "separate", the return is a layout of its own, `rcells`, drawn on a second layer
 *   cells: the supply layer, rcells: the return layer. The source and the sinks are pads on both
 *        layers, as a through-hole is on both sides of a circuit board: the same squares, but each
 *        layer connects to them on its own side. A sink's name, curve and speed are kept on the
 *        supply layer's pad only (syncPads keeps the pads of the two layers in the same squares)
 *   method: how the sheet works out fitting losses: 1 Crane TP-410, 2 Hooper 2-K, 3 Darby 3-K (METHODS)
 *   dp: the pressure difference the pump holds, {v, u} (u one of DP_UNITS), written as Δp_target
 *   labels: what the drawing shows beside the pipes: "values" (the sheet's), "numbers" or "none"
 *   nps, sch: the network's pipe, a nominal size (PIPE_SIZES) or null for a diameter D of its own, and
 *        its schedule, "40" or "80"
 *   tile: {t: "pipe"|"source"|"sink", p: sides, L?: length of this tile, nps?: its pipe size, d?: or diameter,
 *          k?: extra loss coefficient K on this tile (a valve, from its datasheet), name?,
 *          x?: exchanger curve, s?: pump speed}
 *
 * `analyze(layer)` walks one layer's tree from the source: the supply out from the pump's discharge
 * to the sinks, the return out from its suction to the sinks (its water flows the other way, but a
 * tee is still a run on the straight leg and a branch on the other, so the walk is the same).
 * `network(state)` walks both and lines the return's sinks up with the supply's. The water splits only at tees, so the network is
 * a set of segments, each the pipe from one junction to the next: a segment that ends at a sink is
 * that sink's spur, any other ends at a tee. Segments are numbered as the sheet's vectors are: the
 * spurs first, in the order of their sinks, then the rest from the source outwards. Sinks are
 * numbered in the order the walk reaches them, so the sinks of a branch are numbered together.
 *
 *   A      the upstream matrix: one row per segment, one column per sink, 1 where the segment carries
 *          that sink's water. With the spurs first, its top is the identity
 *   L      each segment's length: the sum of its tiles' lengths (a tile is `cell` long unless it says)
 *   D      each segment's inside diameter: of the pipe size its first pipe tile names (`nps`, in the
 *          network's schedule `sch`, from PIPE_SIZES), or a diameter of its own (`d`), else the network's
 *   n      each segment's fittings, counted by kind (FITTINGS): 90° elbows, tees the flow passes
 *          straight through (runs), and tees the flow turns through (branches). A segment owns the
 *          tee it leaves through, so a tee counts once on each segment that leaves it: as a run on the
 *          one straight on, as a branch on the others. The sheet turns the counts into K with the
 *          coefficient table of the method chosen
 *   K      each segment's extra loss coefficients (`k` on its tiles), added to the fittings' as they are
 *   Each layer gives its own set: A, L!, D_h!, N_fit!, K_extra! for the supply, A_r, L_r!, D_r!,
 *   N_fit_r!, K_extra_r! for the return, whose columns are the same sinks in the same order. With
 *   `ret: "same"` the return's are copies of the supply's.
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

  // Schedule pipe: nominal size (NPS), and the inside diameter in inches of Schedule 40 and 80 pipe,
  // from the wall thicknesses of ASME B36.10M. PVC Schedule 40 and 80 pipe (ASTM D1785) has the same
  // outside diameters and walls, so the same bores. A segment's D_h is its pipe's inside diameter.
  const SCHEDULES = ['40', '80'];
  // The units the pump's target pressure difference (Δp_target) may be given in, as LENS spells them.
  const DP_UNITS = ['psi', 'kPa', 'Pa', 'bar', 'ft_H2O'];
  const PIPE_SIZES = [
    ['1/8', 0.269, 0.215], ['1/4', 0.364, 0.302], ['3/8', 0.493, 0.423], ['1/2', 0.622, 0.546],
    ['3/4', 0.824, 0.742], ['1', 1.049, 0.957], ['1-1/4', 1.380, 1.278], ['1-1/2', 1.610, 1.500],
    ['2', 2.067, 1.939], ['2-1/2', 2.469, 2.323], ['3', 3.068, 2.900], ['3-1/2', 3.548, 3.364],
    ['4', 4.026, 3.826], ['5', 5.047, 4.813], ['6', 6.065, 5.761], ['8', 7.981, 7.625],
    ['10', 10.020, 9.562], ['12', 11.938, 11.374], ['14', 13.124, 12.500], ['16', 15.000, 14.312],
    ['18', 16.876, 16.124], ['20', 18.812, 17.938], ['24', 22.624, 21.562],
  ];
  const SIZE = new Map(PIPE_SIZES.map(([n, s40, s80]) => [n, { '40': s40, '80': s80 }]));
  const PER_INCH = { in: 1, mm: 25.4, ft: 1 / 12, m: 0.0254 };

  // A pipe's inside diameter in the state's diameter unit: of its nominal size `nps` in the network's
  // schedule, or `d` as given (a pipe the table does not have).
  const bore = (state, nps, d) => (nps && SIZE.has(nps) ? SIZE.get(nps)[state.sch] * PER_INCH[state.units.D] : d);
  // What a tile says of its pipe, or null: its nominal size, or a diameter of its own.
  const tileSize = (state, t) => (t.nps ? { nps: t.nps, D: bore(state, t.nps) } : t.d ? { nps: null, D: t.d } : null);
  const sizeName = (state, nps) => (nps ? `${nps}" Sch ${state.sch}` : 'custom');

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
    return { v: 1, units: { L: 'ft', D: 'in' }, cell: 10, D: 4, nps: '4', sch: '40', ret: 'same', method: 1, dp: { v: 0.1, u: 'psi' },
      labels: 'values', cells: {}, rcells: {} };
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
      cell: num(s.cell, b.cell), D: num(s.D, b.D), ret: s.ret === 'separate' ? 'separate' : 'same',
      nps: s.nps === null ? null : SIZE.has(s.nps) ? s.nps : b.nps, sch: SCHEDULES.includes(s.sch) ? s.sch : b.sch,
      method: [1, 2, 3].includes(s.method) ? s.method : b.method,
      dp: { v: s.dp && typeof s.dp.v === 'number' && isFinite(s.dp.v) && s.dp.v >= 0 ? s.dp.v : b.dp.v,
            u: s.dp && DP_UNITS.includes(s.dp.u) ? s.dp.u : b.dp.u },
      labels: ['values', 'numbers', 'none'].includes(s.labels) ? s.labels : b.labels, cells: {}, rcells: {},
    };
    const clean = (cells, into, supply) => {
      for (const [k, t] of Object.entries(cells || {})) {
        if (!/^-?\d+,-?\d+$/.test(k) || !t || !['pipe', 'source', 'sink'].includes(t.t)) continue;
        const p = (t.p | 0) & 15;
        const tile = { t: t.t, p };
        if (num(t.L, 0)) tile.L = t.L;
        if (typeof t.nps === 'string' && SIZE.has(t.nps)) tile.nps = t.nps;
        else if (num(t.d, 0)) tile.d = t.d;
        if (typeof t.k === 'number' && isFinite(t.k) && t.k >= 0) tile.k = t.k;
        if (t.t === 'sink' && supply) {
          if (typeof t.name === 'string') tile.name = t.name.slice(0, 40);
          tile.x = Math.max(1, Math.round(num(t.x, 1)));
          tile.s = Math.max(1, Math.round(num(t.s, 2)));
        }
        into[k] = tile;
      }
    };
    clean(s.cells, out.cells, true);
    clean(s.rcells, out.rcells, false);
    syncPads(out, 's');
    return out;
  }

  // One layer of a state, as the walk and the editing functions take one: the state with `cells`
  // the layer's tiles ("s" supply, "r" return). Its cells are the state's own, so edits reach it.
  function side(state, layer) {
    return layer === 'r' ? { ...state, cells: state.rcells } : state;
  }

  const isPad = (t) => !!t && t.t !== 'pipe';

  // Make the pads of the other layer stand where `from`'s are: one taken away there goes, one put
  // down there appears (facing a neighbouring pipe that points at it, else connected nowhere yet),
  // and one that is there keeps its own side. Pipes are left alone, unless a pad now stands on one.
  function syncPads(state, from) {
    const src = from === 'r' ? state.rcells : state.cells, dst = from === 'r' ? state.cells : state.rcells;
    for (const [k, t] of Object.entries(dst)) if (isPad(t) && (!src[k] || src[k].t !== t.t)) delete dst[k];
    for (const [k, t] of Object.entries(src)) {
      if (!isPad(t) || (dst[k] && dst[k].t === t.t)) continue;
      const d = DIRS.find((x) => { const n = dst[step(k, x)]; return n && n.p & OPP[x]; });
      dst[k] = { t: t.t, p: d || 0 };
      if (t.t === 'sink' && dst === state.cells) { dst[k].x = 1; dst[k].s = 2; }
    }
  }

  // Both layers walked: {same, s, r, Ar, sinks, errors, warnings}. `s` and `r` are each layer's walk
  // (the same one when the return matches the supply); `Ar` is the return's upstream matrix with its
  // columns in the supply's sink order. Errors and warnings carry the layer they are on.
  function network(state) {
    const s = analyze(side(state, 's'));
    const tag = (layer, word) => (m) => ({ ...m, layer, msg: word + m.msg });
    const net = { same: state.ret !== 'separate', s, r: s, Ar: s.A, sinks: s.sinks,
      errors: s.errors.map(tag('s', '')), warnings: s.warnings.map(tag('s', '')) };
    if (net.same) return net;
    const r = analyze(side(state, 'r'));
    net.r = r;
    const src = r.source && state.rcells[r.source];
    if (src && !src.p) r.errors.splice(0, r.errors.length, { key: r.source, msg: "Draw the return pipe into the source: the pump's suction" });
    net.errors.push(...r.errors.map(tag('r', 'Return: ')));
    net.warnings.push(...r.warnings.map(tag('r', 'Return: ')));
    if (net.errors.length) return net;
    const col = new Map(r.sinks.map((k, j) => [k.key, j]));
    for (const sink of s.sinks) if (!col.has(sink.key)) net.errors.push({ key: sink.key, layer: 'r', msg: `Return: ${sink.name} has no return pipe` });
    if (!net.errors.length) net.Ar = r.A.map((row) => s.sinks.map((k) => row[col.get(k.key)]));
    return net;
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
      const s = { id: segs.length, parent, from, out, tiles: [], L: 0, n, K: 0, D: null, nps: null, sink: null, children: [], ends: null };
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
        const size = tile.t === 'pipe' ? tileSize(state, tile) : null;
        if (!seg.sized && tile.t === 'pipe') {
          seg.sized = true;   // its first pipe tile says the segment's size, or leaves it the network's
          if (size) { seg.D = size.D; seg.nps = size.nps; }
        } else if (size && seg.sized && !seg.mixed && Math.abs(size.D - (seg.D === null ? bore(state, state.nps, state.D) : seg.D)) > 1e-9) {
          seg.mixed = true;
          warnings.push({ key: k, msg: "This segment has more than one pipe size; its first tile's is used" });
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
    // The tiles the walk never reached, as one warning (`keys`: every one of them; `key`: the first).
    const loose = Object.keys(cells).filter((k) => {
      const lanes = shape(cells[k]) === 'cross' ? ['v', 'h'] : ['*'];
      return lanes.every((l) => !res.seen.has(k + '|' + l));
    });
    if (loose.length && res.source !== null && !res.errors.length)
      res.warnings.push({ key: loose[0], keys: loose, msg: loose.length === 1 ? 'Not connected to the source, so it is left out'
        : `${loose.length} tiles are not connected to the source, so they are left out` });
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
    for (const s of segs) if (s.D === null) { s.D = bore(state, state.nps, state.D); s.nps = state.nps; }
    return res;
  }

  // ---- what goes into the sheet -----------------------------------------------------------
  function num(x) {
    if (!isFinite(x)) return '0';
    const r = Number(x.toPrecision(6));
    return String(r).replace(/e\+?/, 'e');
  }
  const column = (xs) => '[' + xs.map(num).join('; ') + ']';

  // {name: expression} for the block's lines (of `network(state)`). While the network has an error, only
  // the settings that do not depend on it (the method, the pump's target) are written; the rest stay
  // as they were until it is fixed.
  function outputs(state, net) {
    const settings = { 'fit_method!': String(state.method), Δp_target: `${num(state.dp.v)} '${state.dp.u}` };
    if (net.errors.length || !net.sinks.length) return settings;
    const lines = (a, A, names) => {
      const segs = a.order.map((id) => a.segments[id]);
      return {
        [names[0]]: '[' + A.map((r) => r.join(', ')).join('; ') + ']',
        [names[1]]: `${column(segs.map((s) => s.L))} * '${state.units.L}`,
        [names[2]]: `${column(segs.map((s) => s.D))} * '${state.units.D}`,
        [names[3]]: '[' + segs.map((s) => s.n.map(num).join(', ')).join('; ') + ']',
        [names[4]]: column(segs.map((s) => s.K)),
      };
    };
    return {
      ...lines(net.s, net.s.A, ['A', 'L!', 'D_h!', 'N_fit!', 'K_extra!']),
      ...lines(net.r, net.Ar, ['A_r', 'L_r!', 'D_r!', 'N_fit_r!', 'K_extra_r!']),
      'exchangers!': column(net.sinks.map((s) => s.x)),
      'speeds!': column(net.sinks.map((s) => s.s)),
      ...settings,
    };
  }

  // ---- values from the sheet --------------------------------------------------------------
  // Each `!pluginvar` value laid on the drawing: one whose name ends in `_r` (∀_r!, Δp_r) and is as
  // long as the return's segments on the return's segments, any other as long as the supply's on the
  // supply's; one as long as the sinks on the sinks; a single number in the legend.
  const RETURN_NAME = /_r[`!@&]*$/;
  function placed(inputs, net) {
    const out = { segments: [], rsegments: [], sinks: [], legend: [], unplaced: [] };
    const nSeg = net.s.order.length, nRet = net.r.order.length, nSink = net.sinks.length;
    for (const v of inputs || []) {
      const flat = flatten(v.mag);
      if (flat === null) { out.unplaced.push(v.name); continue; }
      const item = { name: v.name, unit: v.unit, values: flat, stale: !!v.stale };
      const ret = RETURN_NAME.test(v.name);
      if (flat.length === 1 && !(v.shape && v.shape.length)) out.legend.push(item);
      else if (ret && flat.length === nRet && nRet) out.rsegments.push(item);
      else if (!ret && flat.length === nSeg && nSeg) out.segments.push(item);
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
    const ks = Object.keys(state.cells).concat(Object.keys(state.rcells || {})).map(at);
    if (!ks.length) return { r0: 0, c0: 0, r1: 7, c1: 11 };
    let r0 = Math.min(...ks.map((k) => k[0])) - pad, r1 = Math.max(...ks.map((k) => k[0])) + pad;
    let c0 = Math.min(...ks.map((k) => k[1])) - pad, c1 = Math.max(...ks.map((k) => k[1])) + pad;
    if (r1 - r0 < 7) r1 = r0 + 7;
    if (c1 - c0 < 11) c1 = c0 + 11;
    return { r0, c0, r1, c1 };
  }

  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  /* The layout as SVG text, from the state and its `network`. opts: {theme: {paper, text, ink, ret,
     rule, err, grid, sans, soft, hi}, layer: the layer in front ("s" or "r"; the other is drawn faded
     behind it, as the far side of a circuit board is), selected: a tile key on that layer, grid: draw
     the grid (the editor) or not (the preview), inputs: the !pluginvar values, rounds: how long `spread`
     may work at the balloons (less while the mouse drags)}. */
  function draw(state, net, opts = {}) {
    const th = Object.assign({ paper: '#ffffff', text: '#1d2b3a', ink: '#1f5fa8', ret: '#00838f', rule: '#9fb4c8', err: '#c62828',
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
    const front = !net.same && opts.layer === 'r' ? 'r' : 's';
    const h = CELL / 2, pw = 7;

    // One layer's tiles, in its colour; `selected` only on the layer in front. The layer behind is a
    // `ghost`: thin dashed centre lines and no pads, so it reads as a reference, not as pipe. A pipe on
    // the layer in front that the source does not reach is drawn hollow: an outline with no water in it.
    const tiles = (cells, layer, color0, selected, ghost = false) => {
      const a = layer === 'r' ? net.r : net.s;
      const bad = new Set(net.errors.filter((e) => e.layer === layer).map((e) => e.key).filter(Boolean));
      const loose = new Set(net.warnings.filter((w) => w.layer === layer && w.keys).flatMap((w) => w.keys));
      const segOf = new Map();
      for (const s of a.segments) for (const k of s.tiles) if (!segOf.has(k)) segOf.set(k, s);
      const selSeg = selected ? segOf.get(selected) : null;
      for (const [k, tile] of Object.entries(cells)) {
        const [r, c] = at(k), cx = x(c) + h, cy = y(r) + h;
        const seg = segOf.get(k);
        const sh = shape(tile);
        if (ghost) {
          if (tile.t !== 'pipe') continue;   // the pads are drawn with the layer in front
          for (const d of bits(tile.p))
            out.push(`<line x1="${cx}" y1="${cy}" x2="${cx + DC[d] * h}" y2="${cy + DR[d] * h}" stroke="${esc(color0)}" stroke-width="3" stroke-dasharray="6 4" stroke-linecap="butt"/>`);
          continue;
        }
        const hollow = loose.has(k);
        let color = hollow ? th.rule : color0;
        if (selSeg && seg === selSeg) color = th.hi;   // the selected tile's segment, in the theme's accent
        if (bad.has(k)) out.push(`<rect x="${x(c) + 2}" y="${y(r) + 2}" width="${CELL - 4}" height="${CELL - 4}" fill="none" stroke="${esc(th.err)}" stroke-width="2" stroke-dasharray="4 3"/>`);
        if (selected === k) out.push(`<rect x="${x(c) + 1}" y="${y(r) + 1}" width="${CELL - 2}" height="${CELL - 2}" fill="none" stroke="${esc(th.hi)}" stroke-width="2"/>`);
        const arm = (d, len = h) => {
          const line = (stroke, width) => `<line x1="${cx}" y1="${cy}" x2="${cx + DC[d] * len}" y2="${cy + DR[d] * len}" stroke="${esc(stroke)}" stroke-width="${width}" stroke-linecap="butt"/>`;
          return hollow && tile.t === 'pipe' ? line(color, pw) + line(th.paper, pw - 4) : line(color, pw);
        };
        if (sh === 'cross') {
          out.push(`<line x1="${cx}" y1="${y(r)}" x2="${cx}" y2="${y(r) + CELL}" stroke="${esc(color)}" stroke-width="${pw}"/>`);
          const hop = 11;
          out.push(`<path d="M ${x(c)} ${cy} H ${cx - hop} A ${hop} ${hop} 0 0 1 ${cx + hop} ${cy} H ${x(c) + CELL}" fill="none" stroke="${esc(th.paper)}" stroke-width="${pw + 6}"/>`);
          out.push(`<path d="M ${x(c)} ${cy} H ${cx - hop} A ${hop} ${hop} 0 0 1 ${cx + hop} ${cy} H ${x(c) + CELL}" fill="none" stroke="${esc(color)}" stroke-width="${pw}"/>`);
        } else if (sh === 'source') {
          for (const d of bits(tile.p)) out.push(arm(d));
          out.push(`<circle cx="${cx}" cy="${cy}" r="${h - 9}" fill="${esc(th.paper)}" stroke="${esc(color)}" stroke-width="3"/>`);
          // the pump's triangle points the way the water leaves it: out on the supply, in on the return
          const side0 = bits(tile.p)[0] || E, d = layer === 'r' ? OPP[side0] : side0, tr = h - 14;
          const px = DC[d], py = DR[d], qx = -py, qy = px;
          out.push(`<path d="M ${cx + px * tr} ${cy + py * tr} L ${cx - px * tr * 0.6 + qx * tr * 0.8} ${cy - py * tr * 0.6 + qy * tr * 0.8} L ${cx - px * tr * 0.6 - qx * tr * 0.8} ${cy - py * tr * 0.6 - qy * tr * 0.8} Z" fill="${esc(color)}"/>`);
        } else if (sh === 'sink') {
          for (const d of bits(tile.p)) out.push(arm(d));
          const s = h - 10;
          out.push(`<rect x="${cx - s}" y="${cy - s}" width="${2 * s}" height="${2 * s}" fill="${esc(th.paper)}" stroke="${esc(color)}" stroke-width="3"/>`);
          out.push(`<path d="M ${cx - s + 4} ${cy + 6} l 5 -12 l 5 12 l 5 -12 l 5 12 l 5 -12" fill="none" stroke="${esc(color)}" stroke-width="2"/>`);
        } else {
          for (const d of bits(tile.p)) out.push(arm(d));
          if (bits(tile.p).length > 1 && !hollow) out.push(`<circle cx="${cx}" cy="${cy}" r="${pw / 2}" fill="${esc(color)}"/>`);
          if (sh === 'stub') out.push(`<path d="M ${cx - 7} ${cy - 7} l 14 14 m 0 -14 l -14 14" stroke="${esc(th.err)}" stroke-width="3"/>`);
        }
      }
    };
    if (!net.same) {   // the far side, as a dashed ghost, behind
      const back = front === 's' ? 'r' : 's';
      out.push('<g class="back" opacity="0.6">');
      tiles(back === 'r' ? state.rcells : state.cells, back, back === 'r' ? th.ret : th.ink, null, true);
      out.push('</g>');
    }
    tiles(front === 'r' ? state.rcells : state.cells, front, front === 'r' ? th.ret : th.ink, opts.selected);

    // numbers and values: each segment of the layer in front at its middle tile, each sink beside it.
    // The values are balloons: each wants to sit beside its pipe or sink, and where they would overlap
    // (each other, a segment's number, a pad) `spread` pushes them apart; one pushed away from its
    // place keeps a leader line to it.
    const vals = placed(opts.inputs, net);
    const LH = 13, balloons = [], obstacles = [];
    const balloon = (ax, ay, px, py, lines, anchor = 'start') => {
      const w = Math.max(...lines.map((l) => l.text.length)) * 6.4 + 10, hgt = lines.length * LH + 6;
      const x0 = anchor === 'start' ? px : px - w;
      balloons.push({ ax, ay, px: x0, py: py - 12, x: x0, y: py - 12, w, h: hgt, lines });
    };
    const show = state.labels || 'values';
    if (!net.errors.length && show !== 'none') {
      const a = front === 'r' ? net.r : net.s, cells = front === 'r' ? state.rcells : state.cells;
      const own = front === 'r' && !net.same ? vals.rsegments : vals.segments, prefix = front === 'r' && !net.same ? 'R' : '';
      for (const s of a.segments) {
        if (!s.tiles.length || s.row === undefined) continue;
        const mine = s.tiles.length > 1 ? s.tiles.slice(0, -1) : s.tiles;   // not the tee or sink it ends at
        const mid = mine[Math.floor((mine.length - 1) / 2)];
        const [r, c] = at(mid), cx = x(c) + h, cy = y(r) + h;
        const lines = show === 'values' ? own.map((v) => ({ text: `${v.name} ${fmt(v.values[s.row], v.unit)}`, soft: v.stale })) : [];
        if (lines.length) {
          const vertical = !(cells[mid].p & (E | W));
          if (vertical) balloon(cx, cy, cx + 16, cy - (lines.length * LH) / 2 + 9, lines);
          else balloon(cx, cy, cx - 8, cy + 28, lines);
        }
        const rr = prefix ? 12 : 10;
        obstacles.push({ x: cx - rr - 2, y: cy - rr - 2, w: 2 * rr + 4, h: 2 * rr + 4 });
        out.push(`<circle cx="${cx}" cy="${cy}" r="${rr}" fill="${esc(th.paper)}" stroke="${esc(front === 'r' ? th.ret : th.ink)}" stroke-width="2"/>`);
        out.push(`<text x="${cx}" y="${cy + 4}" font-size="${prefix ? 10 : 11}" font-weight="600" text-anchor="middle" fill="${esc(th.text)}">${prefix}${s.row + 1}</text>`);
      }
      for (const [k, t] of Object.entries(cells)) {
        if (t.t === 'pipe') continue;
        const [r, c] = at(k);
        obstacles.push({ x: x(c) + 8, y: y(r) + 8, w: CELL - 16, h: CELL - 16 });
      }
      net.sinks.forEach((sink, j) => {
        const [r, c] = at(sink.key), cy = y(r) + h;
        const lines = [{ text: sink.name, bold: true }];
        if (show === 'values') for (const v of vals.sinks) lines.push({ text: `${v.name} ${fmt(v.values[j], v.unit)}`, soft: v.stale });
        if (cells[sink.key] && cells[sink.key].p === E) balloon(x(c) + 8, cy, x(c) + 2, y(r) + 14, lines, 'end');   // the pipe comes from the right
        else balloon(x(c) + CELL - 8, cy, x(c) + CELL - 2, y(r) + 14, lines);
      });
    }
    if (vals.legend.length) {
      const lines = vals.legend.map((v) => ({ text: `${v.name} = ${fmt(v.values[0], v.unit)}`, soft: v.stale }));
      const w = Math.max(...lines.map((l) => l.text.length)) * 6.4 + 10;
      obstacles.push({ x: 6, y: 4, w: w + 4, h: lines.length * LH + 10 });
      balloons.push({ ax: null, px: 8, py: 6, x: 8, y: 6, w, h: lines.length * LH + 6, lines, fixed: true });
    }
    spread(balloons, obstacles, W_, H_, opts.rounds || 600);
    for (const bl of balloons) {   // leader lines first, under every balloon
      if (bl.ax === null || bl.ax === undefined) continue;
      const nx = Math.max(bl.x, Math.min(bl.ax, bl.x + bl.w)), ny = Math.max(bl.y, Math.min(bl.ay, bl.y + bl.h));
      if (Math.hypot(bl.x - bl.px, bl.y - bl.py) < 4) continue;
      out.push(`<line x1="${bl.ax}" y1="${bl.ay}" x2="${nx}" y2="${ny}" stroke="${esc(th.soft)}" stroke-width="1"/>`);
      out.push(`<circle cx="${bl.ax}" cy="${bl.ay}" r="2.5" fill="${esc(th.soft)}"/>`);
    }
    for (const bl of balloons) {
      out.push(`<rect x="${bl.x}" y="${bl.y}" width="${bl.w}" height="${bl.h}" rx="5" fill="${esc(th.paper)}" fill-opacity="0.94" stroke="${esc(th.rule)}" stroke-width="0.8"/>`);
      bl.lines.forEach((l, i) => out.push(`<text x="${bl.x + 5}" y="${bl.y + 13 + i * LH}" font-size="11" font-weight="${l.bold ? 600 : 400}" fill="${esc(l.soft ? th.soft : th.text)}">${esc(l.text)}</text>`));
    }
    out.push('</svg>');
    return out.join('');
  }

  /* Push overlapping balloons apart, in place. Each is {x, y, w, h} where it is, {px, py} where it
     would be, and `fixed` if it may not move. Overlapping balloons are pushed apart along the way they
     overlap least, half each; a balloon over an obstacle (a box: a segment's number, a pad) is pushed off
     it; a weak spring pulls each back to where it would be; and all stay inside the picture. Stops when
     nothing overlaps, or after `rounds`. Returns how many pairs still overlap. */
  function spread(items, obstacles = [], W = Infinity, H = Infinity, rounds = 600) {
    const GAP = 3;
    const all = items.concat(obstacles.map((o) => ({ ...o, fixed: true, obstacle: true })));
    const over = (a, b) => [Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x) + GAP, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y) + GAP];
    const clamp = (a) => {
      a.x = Math.max(2, Math.min(W - a.w - 2, a.x));
      a.y = Math.max(2, Math.min(H - a.h - 2, a.y));
    };
    const hits = () => {   // what still overlaps, counted afresh (obstacles may overlap each other)
      let n = 0;
      for (let i = 0; i < all.length; i++)
        for (let j = i + 1; j < all.length; j++) {
          if (all[i].fixed && all[j].fixed) continue;
          const [ox, oy] = over(all[i], all[j]);
          if (ox > GAP && oy > GAP) n++;
        }
      return n;
    };
    for (const a of items) if (!a.fixed) clamp(a);   // inside the picture, whatever else
    let left = hits();
    for (let round = 0; round < rounds && left; round++) {
      for (const a of items) {   // back towards its place, a little, before the pushing
        if (a.fixed) continue;
        a.x += (a.px - a.x) * 0.02;
        a.y += (a.py - a.y) * 0.02;
      }
      // A pair is moved apart along the way it overlaps least; past a third of the rounds, a pair that
      // still overlaps tries the other way too, so two balloons caught between others get out.
      const both = round > rounds / 3 && round % 2;
      for (let i = 0; i < all.length; i++) {
        for (let j = i + 1; j < all.length; j++) {
          const a = all[i], b = all[j];
          if (a.fixed && b.fixed) continue;
          const [ox, oy] = over(a, b);
          if (ox <= 0 || oy <= 0) continue;
          const sa = a.fixed ? 0 : b.fixed ? 1 : 0.55, sb = b.fixed ? 0 : a.fixed ? 1 : 0.55;
          const alongX = both ? ox >= oy : ox < oy;
          const d = alongX ? (a.x + a.w / 2 < b.x + b.w / 2 ? -1 : 1) * ox : (a.y + a.h / 2 < b.y + b.h / 2 ? -1 : 1) * oy;
          if (alongX) { a.x += d * sa; b.x -= d * sb; } else { a.y += d * sa; b.y -= d * sb; }
        }
      }
      for (const a of items) if (!a.fixed) clamp(a);
      left = hits();
    }
    return left;
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
    for (const f of ['L', 'd', 'k', 'nps']) if (old[f] !== undefined) t[f] = old[f];
    if (tile.t === 'sink') { t.x = old.x || 1; t.s = old.s || 2; if (old.name) t.name = old.name; }
    if (tile.auto && tile.t !== 'pipe') {
      const d = DIRS.find((x) => { const n = state.cells[step(k, x)]; return n && n.p & OPP[x]; });
      if (d) t.p = d;
    }
    state.cells[k] = t;
  }

  // Edit one layer of a state with `fn(view)` (connect, erase, place on `side(state, layer)`), then
  // keep the pads of the other layer in step. Taking a pad away takes it off both layers.
  function onLayer(state, layer, fn) {
    const view = side(state, layer);
    const result = fn(view);
    syncPads(state, layer === 'r' ? 'r' : 's');
    return result;
  }

  // Start the return as a copy of the supply (when the return becomes a layout of its own).
  function copySupply(state) {
    state.rcells = {};
    for (const [k, t] of Object.entries(state.cells)) {
      const c = { t: t.t, p: t.p };
      for (const f of ['L', 'd', 'k', 'nps']) if (t.t === 'pipe' && t[f] !== undefined) c[f] = t[f];
      state.rcells[k] = c;
    }
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
    blank, normalize, side, syncPads, network, onLayer, copySupply, analyze, outputs, placed, flatten, fmt, bounds, draw,
    connect, erase, place, segmentAt, PALETTE, example, RETURN_NAME, PIPE_SIZES, SCHEDULES, DP_UNITS, bore, sizeName, spread };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.PipeNet = api;
})(typeof window !== 'undefined' ? window : globalThis);
