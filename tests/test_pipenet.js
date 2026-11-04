// Run with: node tests/test_pipenet.js
// The pipenet plugin's model (plugins/pipenet/pipenet.js): tile shapes, the walk from the source,
// the upstream matrix and segment vectors it writes into the sheet, and the editing helpers.
const assert = require('assert');
const P = require('../plugins/pipenet/pipenet.js');
let n = 0;
const eq = (a, b, label) => { assert.deepStrictEqual(a, b, label); n++; };
const { N, E, S, W } = P;

// A state from strokes: each a list of tiles to join, then sources and sinks by tile.
function net(strokes, source, sinks, extra = {}) {
  const s = Object.assign(P.blank(), extra);
  for (const ks of strokes) for (let i = 1; i < ks.length; i++) assert.ok(P.connect(s, ks[i - 1], ks[i]), `${ks[i - 1]} to ${ks[i]}`);
  if (source) P.place(s, source, { t: 'source', p: 0, auto: true });
  for (const k of sinks || []) P.place(s, k, { t: 'sink', p: 0, auto: true });
  return s;
}
const row = (r, c0, c1) => { const out = []; for (let c = c0; c <= c1; c++) out.push(`${r},${c}`); return out; };
const col = (c, r0, r1) => { const out = []; for (let r = r0; r <= r1; r++) out.push(`${r},${c}`); return out; };

// --- shapes -----------------------------------------------------------------------------------
eq([N | S, E | W, N | E, N | E | S, N | E | S | W, W].map((p) => P.shape({ t: 'pipe', p })),
  ['straight', 'straight', 'elbow', 'tee', 'cross', 'stub'], 'a pipe takes its shape from its sides');
eq(P.rotate(N | E), E | S, 'turning goes clockwise');
eq(P.rotate(P.rotate(P.rotate(P.rotate(N | E | S)))), N | E | S, 'four turns are none');
eq(P.PALETTE.filter((t) => t.t === 'pipe').map((t) => P.shape(t)),
  ['straight', 'straight', 'elbow', 'elbow', 'elbow', 'elbow', 'tee', 'tee', 'tee', 'tee', 'cross'],
  'the palette has every pipe shape in every orientation');
eq(P.PALETTE.filter((t) => t.t !== 'pipe').length, 8, 'and a source and a sink facing each way');

// --- one pipe, one sink -------------------------------------------------------------------------
{
  const s = net([row(0, 0, 3)], '0,0', ['0,3']);
  const a = P.analyze(s);
  eq(a.errors, [], 'a straight run from the source to a sink is a network');
  eq(a.A, [[1]], 'of one segment, the spur');
  eq(P.outputs(s, P.network(s)), { A: '[1]', 'L!': "[30] * 'ft", 'D_h!': "[4.026] * 'in", 'N_fit!': '[0, 0, 0]', 'K_extra!': '[0]',
    A_r: '[1]', 'L_r!': "[30] * 'ft", 'D_r!': "[4.026] * 'in", 'N_fit_r!': '[0, 0, 0]', 'K_extra_r!': '[0]',
    'exchangers!': '[1]', 'speeds!': '[2]', 'fit_method!': '1', Δp_target: "0.1 'psi" },
    "three tiles of 10 ft of 4\" Sch 40; the return the same as the supply, as lines of its own");
  s.method = 3;
  eq(P.outputs(s, P.network(s))['fit_method!'], '3', 'the method chosen goes to the sheet');
  s.dp = { v: 25, u: 'kPa' };
  eq(P.outputs(s, P.network(s))['Δp_target'], "25 'kPa", "and the pump's target pressure difference");
  eq(P.normalize({ dp: { v: -1, u: 'atm' } }).dp, { v: 0.1, u: 'psi' }, 'a target that is not one falls back to 0.1 psi');
}

// --- a tee: the trunk splits into two spurs ---------------------------------------------------------
{
  // source 0,0 -> tee at 0,3 -> on to the sink at 0,5; branch down to the sink at 3,3, with an elbow
  const s = net([row(0, 0, 5), col(3, 0, 2), ['2,3', '2,4'], col(4, 2, 3)], '0,0', ['0,5', '3,4'], { ret: false });
  const a = P.analyze(s);
  eq(a.errors, [], 'a tee splits the flow');
  eq(a.sinks.map((x) => x.key), ['0,5', '3,4'], 'sinks are numbered straight on first');
  eq(a.order.map((id) => a.segments[id].tiles), [['0,4', '0,5'], ['1,3', '2,3', '2,4', '3,4'], ['0,1', '0,2', '0,3']],
    'segments: the spurs in the order of their sinks, then the trunk');
  eq(a.A, [[1, 0], [0, 1], [1, 1]], 'the upstream matrix: the identity, then the trunk that carries both');
  const o = P.outputs(s, P.network(s));
  eq(o['L!'], "[20; 40; 30] * 'ft", 'lengths by tile');
  eq(o['A_r'], o['A'], 'the return is the supply again');
  eq(o['N_fit!'], '[0, 1, 0; 2, 0, 1; 0, 0, 0]', 'fittings counted by kind: elbows, tee runs, tee branches (two elbows on the branch)');
}

// --- a tee entered through its stem: both ways out are branches ------------------------------------------
{
  const s = net([col(1, 0, 2), row(2, 0, 2)], '0,1', ['2,0', '2,2'], { ret: false });
  const a = P.analyze(s);
  eq(a.errors, [], 'a bullhead tee');
  eq(P.outputs(s, P.network(s))['N_fit!'], '[0, 0, 1; 0, 0, 1; 0, 0, 0]', 'both ways out of a bullhead tee are branches');
}

// --- a crossover lets two pipes pass without joining ----------------------------------------------------------
{
  // the source feeds east along row 1, and a branch from it loops up and over to cross row 1 going south
  const s = net([row(1, 0, 4), ['1,1', '0,1'], row(0, 1, 3), col(3, 0, 3)], '1,0', ['1,4', '3,3'], { ret: false });
  eq(P.shape(s.cells['1,3']), 'cross', 'drawing across a straight makes a crossover');
  const a = P.analyze(s);
  eq(a.errors, [], 'the crossing pipes do not meet');
  eq(a.sinks.length, 2, 'both sinks are reached');
  eq(a.A, [[1, 0], [0, 1], [1, 1]], 'and the crossover joins nothing');
}

// --- what is wrong with a layout ---------------------------------------------------------------------
eq(P.analyze(P.blank()).errors.map((e) => e.msg), ['Place a source (the pump) to start the network'], 'no source');
{
  const s = net([row(0, 0, 2)], '0,0', []);
  eq(P.analyze(s).errors.map((e) => [e.key, /Dead end/.test(e.msg)]), [['0,2', true]], 'a dead end');
  const t = net([row(0, 0, 2)], '0,0', ['0,2']);
  delete t.cells['0,1'];
  t.cells['0,1'] = { t: 'pipe', p: N | S };
  eq(P.analyze(t).errors.map((e) => [e.key, /stops here/.test(e.msg)]), [['0,0', true]], 'a pipe leading into a tile with no opening');
}
{
  // a ring: from the source east, then around back into the trunk
  const s = net([row(0, 0, 3), col(3, 0, 2), row(2, 1, 3), col(1, 0, 2)], '0,0', []);
  assert.ok(P.analyze(s).errors.some((e) => /loops/.test(e.msg)), 'a loop is refused');
  n++;
}
{
  const s = net([row(0, 0, 2), row(3, 0, 2)], '0,0', ['0,2']);
  const a = P.analyze(s);
  eq(a.errors, [], 'tiles off the network are no error');
  eq(a.warnings.map((w) => w.key).sort(), ['3,0', '3,1', '3,2'], 'but each is pointed out');
  s.cells['5,5'] = { t: 'source', p: E };
  eq(P.analyze(s).errors.length, 2, 'two sources are refused');
}
eq(P.analyze(net([row(0, 0, 2), col(2, 0, 2)], '0,0', [])).errors.some((e) => /Dead end/.test(e.msg)), true, 'no sink: a dead end');

// --- per-tile settings --------------------------------------------------------------------------
{
  const s = net([row(0, 0, 3)], '0,0', ['0,3'], { units: { L: 'm', D: 'mm' }, cell: 2.5, D: 50 });
  s.cells['0,1'].L = 120; s.cells['0,2'].k = 340; s.cells['0,1'].d = 80; s.cells['0,3'].x = 2; s.cells['0,3'].s = 3;
  const o = P.outputs(s, P.network(s));
  eq([o['L!'], o['D_h!'], o['K_extra!'], o['exchangers!'], o['speeds!']],
    ["[125] * 'm", "[80] * 'mm", '[340]', '[2]', '[3]'], 'a tile can set its length, extra K and the diameter; a sink its curve and speed');
}

// --- reading a state ----------------------------------------------------------------------------
eq(P.normalize(null), P.blank(), 'nothing is an empty layout');
eq(P.normalize({ cells: { '0,0': { t: 'pipe', p: 99 }, 'x': { t: 'pipe', p: 1 }, '1,1': { t: 'pump', p: 1 } }, cell: -3, units: { L: 'parsec' } }),
  { ...P.blank(), cells: { '0,0': { t: 'pipe', p: 3 } } }, 'odd tiles and settings are dropped');
eq(P.normalize({ ret: true }).ret, 'same', 'a return that matches the supply, the old way of saying so');
eq(P.normalize({ cells: { '0,0': { t: 'sink', p: 8, name: 'A' } } }).rcells, { '0,0': { t: 'sink', p: 0 } }, 'a pad is on both layers');
eq(P.normalize({ cells: { '0,0': { t: 'sink', p: 8, name: 'AHU-1' } } }).cells['0,0'], { t: 'sink', p: 8, name: 'AHU-1', x: 1, s: 2 },
  'a sink gets its curve and speed');

// --- editing ------------------------------------------------------------------------------------
{
  const s = net([row(0, 0, 2)], null, []);
  eq(P.connect(s, '0,0', '1,1'), false, 'only neighbours connect');
  P.erase(s, '0,1');
  eq(s.cells, {}, 'erasing a tile takes its sides off its neighbours, and a pipe left with none goes');
  P.place(s, '0,0', { t: 'source', p: E });
  P.place(s, '4,4', { t: 'source', p: E });
  eq(Object.keys(s.cells), ['4,4'], 'there is one source: placing it again moves it');
}

// --- the sheet's values on the drawing ------------------------------------------------------------
{
  const s = net([row(0, 0, 5), col(3, 0, 2), ['2,3', '2,4'], col(4, 2, 3)], '0,0', ['0,5', '3,4']);
  const a = P.analyze(s);
  const v = (name, shape, mag) => ({ name, unit: 'u', shape, mag });
  const nt = P.network(s);
  const p = P.placed([v('Q', [3, 1], [[1], [2], [3]]), v('dp', [2, 1], [[4], [5]]), v('t', [], 7), v('M', [2, 2], [[1, 2], [3, 4]]),
    v('w', [1, 3], [[1, 2, 3]]), v('Q_r!', [3, 1], [[1], [2], [3]])], nt);
  eq([p.segments.map((x) => x.name), p.rsegments.map((x) => x.name), p.sinks.map((x) => x.name), p.legend.map((x) => x.name), p.unplaced],
    [['Q', 'w'], ['Q_r!'], ['dp'], ['t'], ['M']],
    'one per segment on the segments (a name ending in _r on the return\'s), one per sink on the sinks, one number in the legend');
  const svg = P.draw(s, nt, { inputs: [v('Q', [3, 1], [[1.234], [2], [3]])] });
  assert.ok(svg.startsWith('<svg') && svg.includes('Q 1.23 u') && svg.endsWith('</svg>'), 'the picture shows the values');
  assert.ok(!P.draw(s, nt, { inputs: [v('Q', [3, 1], [[1], [2], [3]])], grid: false }).includes('<line x1="0"'), 'the preview has no grid');
  s.labels = 'none';
  assert.ok(!P.draw(s, nt, { inputs: [v('Q', [3, 1], [[1.234], [2], [3]])] }).includes('1.23'), 'or no values');
  const lone = P.normalize({ cells: { '0,0': { t: 'sink', p: W, name: '<b>' } } });
  assert.ok(!P.draw(lone, P.network(lone)).includes('<b>'), 'text is escaped');
  n += 4;
}
eq([P.fmt(1234.5, 'Pa'), P.fmt(0.000012), P.fmt(null), P.fmt(0)], ['1230 Pa', '1.20e-5', '–', '0'], 'values to three figures');

{
  const s = P.blank(); s.cells = P.example();
  const a = P.analyze(s);
  eq([a.errors, a.sinks.length, a.order.length], [[], 8, 15], 'the example: eight sinks, fifteen segments');
  eq(P.normalize({ method: 7 }).method, 1, 'an unknown method is Crane');
}
// --- the return laid out on its own (two layers) -----------------------------------------------------
{
  // supply: source 0,0 east to a tee at 0,3, on to sink 0,5 and down to sink 2,3
  const s = net([row(0, 0, 5), col(3, 0, 2)], '0,0', ['0,5', '2,3']);
  s.ret = 'separate';
  P.copySupply(s);
  eq(P.network(s).errors, [], 'the return starts as a copy of the supply');
  // the return leaves the pump's other side and reaches the two sinks another way: a reverse return
  P.onLayer(s, 'r', (v) => { for (const k of Object.keys(v.cells)) if (v.cells[k].t === 'pipe') delete v.cells[k]; });
  // down from the pump, along row 4, up through a tee at 3,3 to sink 2,3 (straight on) and round to 0,5
  const strokes = [['0,0', '1,0', '2,0', '3,0', '4,0', '4,1', '4,2', '4,3', '3,3', '2,3'], ['3,3', '3,4', '3,5', '2,5', '1,5', '0,5']];
  for (const ks of strokes) for (let i = 1; i < ks.length; i++) P.onLayer(s, 'r', (v) => P.connect(v, ks[i - 1], ks[i]));
  eq([s.rcells['0,0'].p, s.cells['0,0'].p], [S, E], "a pad connects on each layer's own side");
  const nt = P.network(s);
  eq(nt.errors, [], 'the return is walked as a tree of its own');
  eq(nt.sinks.map((k) => k.key), ['0,5', '2,3'], 'the sinks are numbered on the supply');
  eq(nt.r.sinks.map((k) => k.key), ['2,3', '0,5'], 'the return reaches them in its own order');
  const o = P.outputs(s, nt);
  eq([o.A, o.A_r], ['[1, 0; 0, 1; 1, 1]', '[0, 1; 1, 0; 1, 1]'], "so the return's matrix has its columns put in the supply's order");
  eq([o['L!'], o['L_r!'], o['N_fit_r!']], ["[20; 20; 30] * 'ft", "[10; 50; 80] * 'ft", '[0, 1, 0; 1, 0, 1; 2, 0, 0]'],
    'each layer has its own lengths and fittings');
  // a return pipe taken away: the supply keeps its own, and the return no longer reaches 0,5
  const supplyBefore = JSON.stringify(s.cells);
  P.onLayer(s, 'r', (v) => P.erase(v, '1,5'));
  eq(JSON.stringify(s.cells), supplyBefore, 'erasing a pipe on the return leaves the supply alone');
  const bad = P.network(s);
  assert.ok(bad.errors.length && bad.errors.every((e) => e.layer === 'r' && e.msg.startsWith('Return: ')), "the return's errors say they are the return's");
  n++;
  eq(P.outputs(s, bad), {}, 'and nothing is written while the return is broken');
  // taking a pad away on one layer takes it off both
  P.onLayer(s, 'r', (v) => { delete v.cells['0,5']; });
  eq([!!s.cells['0,5'], !!s.rcells['0,5']], [false, false], 'a pad taken away on one layer goes from both');
  const drawn = P.draw(s, P.network(s), { layer: 'r' });
  assert.ok(drawn.includes('<g opacity="0.3">'), 'the layer behind is drawn faded');
  n++;
}

{
  // the return cut off before a sink: it is still on the return layer, but nothing reaches it
  const s = net([row(0, 0, 5), col(3, 0, 2)], '0,0', ['0,5', '2,3']);
  s.ret = 'separate';
  P.copySupply(s);
  P.onLayer(s, 'r', (v) => P.erase(v, '1,3'));
  eq(P.network(s).errors.map((e) => [e.key, e.layer, e.msg]), [['2,3', 'r', 'Return: S2 has no return pipe']], 'a sink the return does not reach');
}

// --- pipe sizes --------------------------------------------------------------------------------
{
  eq(P.PIPE_SIZES.length, 23, 'schedule pipe from 1/8" to 24"');
  const s = net([row(0, 0, 3)], '0,0', ['0,3']);
  eq(P.outputs(s, P.network(s))['D_h!'], "[4.026] * 'in", "4\" Sch 40's bore, by default");
  s.sch = '80';
  eq(P.outputs(s, P.network(s))['D_h!'], "[3.826] * 'in", "or Sch 80's");
  s.units.D = 'mm';
  eq(P.outputs(s, P.network(s))['D_h!'], "[97.1804] * 'mm", 'in the unit chosen');
  s.cells['0,1'].nps = '1-1/2';
  eq(P.outputs(s, P.network(s))['D_h!'], "[38.1] * 'mm", "a segment's first pipe tile can name its own size");
  s.nps = null; delete s.cells['0,1'].nps; s.D = 52.5;
  eq(P.outputs(s, P.network(s))['D_h!'], "[52.5] * 'mm", 'or a bore of its own');
  eq([P.sizeName(s, '2'), P.sizeName(s, null)], ['2" Sch 80', 'custom'], 'sizes by name');
  eq(P.normalize({ nps: '7', sch: '160', cells: { '0,0': { t: 'pipe', p: 3, nps: 'x' } } }).cells['0,0'], { t: 'pipe', p: 3 },
    'an unknown size is dropped');
}

console.log(`pipenet: ${n} checks passed`);
