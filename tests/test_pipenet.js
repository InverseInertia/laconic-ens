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
  eq(P.outputs(s, a), { A: '[1]', 'L!': "[60] * 'ft", 'D_h!': "[4] * 'in", 'K_fT!': '[0]', 'exchangers!': '[1]', 'speeds!': '[2]' },
    'three tiles of 10 ft, doubled for the return');
  s.ret = false;
  eq(P.outputs(s, a)['L!'], "[30] * 'ft", 'or not');
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
  const o = P.outputs(s, a);
  eq(o['L!'], "[20; 40; 30] * 'ft", 'lengths by tile');
  eq(o['K_fT!'], '[20; 120; 0]', 'a tee passed straight through is 20, its branch 60, an elbow 30 (two here)');
}

// --- a tee entered through its stem: both ways out are branches ------------------------------------------
{
  const s = net([col(1, 0, 2), row(2, 0, 2)], '0,1', ['2,0', '2,2'], { ret: false });
  const a = P.analyze(s);
  eq(a.errors, [], 'a bullhead tee');
  eq(P.outputs(s, a)['K_fT!'], '[60; 60; 0]', 'both ways out of a bullhead tee are branches');
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
  const s = net([row(0, 0, 3)], '0,0', ['0,3'], { ret: false, units: { L: 'm', D: 'mm' }, cell: 2.5, D: 50 });
  s.cells['0,1'].L = 120; s.cells['0,2'].k = 340; s.cells['0,1'].d = 80; s.cells['0,3'].x = 2; s.cells['0,3'].s = 3;
  const o = P.outputs(s, P.analyze(s));
  eq([o['L!'], o['D_h!'], o['K_fT!'], o['exchangers!'], o['speeds!']],
    ["[125] * 'm", "[80] * 'mm", '[340]', '[2]', '[3]'], 'a tile can set its length, extra fittings and the diameter; a sink its curve and speed');
}

// --- reading a state ----------------------------------------------------------------------------
eq(P.normalize(null), P.blank(), 'nothing is an empty layout');
eq(P.normalize({ cells: { '0,0': { t: 'pipe', p: 99 }, 'x': { t: 'pipe', p: 1 }, '1,1': { t: 'pump', p: 1 } }, cell: -3, units: { L: 'parsec' } }),
  { ...P.blank(), cells: { '0,0': { t: 'pipe', p: 3 } } }, 'odd tiles and settings are dropped');
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
  const p = P.placed([v('Q', [3, 1], [[1], [2], [3]]), v('dp', [2, 1], [[4], [5]]), v('t', [], 7), v('M', [2, 2], [[1, 2], [3, 4]]), v('w', [1, 3], [[1, 2, 3]])], a);
  eq([p.segments.map((x) => x.name), p.sinks.map((x) => x.name), p.legend.map((x) => x.name), p.unplaced],
    [['Q', 'w'], ['dp'], ['t'], ['M']], 'one per segment on the segments, one per sink on the sinks, one number in the legend');
  const svg = P.draw(s, a, { inputs: [v('Q', [3, 1], [[1.234], [2], [3]])] });
  assert.ok(svg.startsWith('<svg') && svg.includes('Q 1.23 u') && svg.endsWith('</svg>'), 'the picture shows the values');
  assert.ok(!P.draw(s, a, { inputs: [v('Q', [3, 1], [[1], [2], [3]])], grid: false }).includes('<line x1="0"'), 'the preview has no grid');
  s.labels = 'none';
  assert.ok(!P.draw(s, a, { inputs: [v('Q', [3, 1], [[1.234], [2], [3]])] }).includes('1.23'), 'or no values');
  assert.ok(!P.draw({ ...P.blank(), cells: { '0,0': { t: 'sink', p: W, name: '<b>' } } }, P.analyze(P.blank())).includes('<b>'), 'text is escaped');
  n += 4;
}
eq([P.fmt(1234.5, 'Pa'), P.fmt(0.000012), P.fmt(null), P.fmt(0)], ['1230 Pa', '1.20e-5', '–', '0'], 'values to three figures');

console.log(`pipenet: ${n} checks passed`);
