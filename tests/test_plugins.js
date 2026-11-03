// Run with: node tests/test_plugins.js
// The page's side of plugins (laconic/static/plugins.js): which blocks the rows hold, what the
// `!pluginvar` rows send, and which messages from a plugin are taken.
const assert = require('assert');
const P = require('../laconic/static/plugins.js');
let n = 0;
const eq = (a, b, label) => { assert.deepStrictEqual(a, b, label); n++; };

const plugin = (line, name, state = null, outputs = []) => ({ n: line, end: line, kind: 'plugin', plugin: { name, state, outputs } });
const pvar = (line, values, stale = false) => ({ n: line, kind: 'pluginvar', stale, pluginvar: { values } });

// --- blocks -----------------------------------------------------------------------------------
eq(P.blocks([plugin(2, 'pipenet', { v: 1 }, ['A']), { n: 3, kind: 'assign' }, plugin(9, 'pipenet'), plugin(12, 'other')]).map((b) => [b.key, b.line]),
  [['pipenet#0', 2], ['pipenet#1', 9], ['other#0', 12]], 'each block is keyed by its name and how many of that name come before');
eq(P.blocks([plugin(2, 'pipenet', { v: 1 }, ['A'])])[0], { key: 'pipenet#0', line: 2, name: 'pipenet', state: { v: 1 }, outputs: ['A'] },
  'with its state and the names it defines');
eq(P.blocks([{ n: 1, kind: 'error', plugin: null }]), [], 'a block that failed is no plugin');

// --- inputs -----------------------------------------------------------------------------------
const q = { name: 'Q', unit: 'gal/min', shape: [2, 1], mag: [[1], [2]] };
eq(P.inputs([pvar(5, [q]), pvar(7, [{ ...q, mag: [[3], [4]] }, { name: 'x', unit: '', shape: [], mag: 1 }], true)]),
  [{ ...q, mag: [[3], [4]], stale: true }, { name: 'x', unit: '', shape: [], mag: 1, stale: true }],
  'every !pluginvar row, the later of a name winning, marked stale with its row');
eq(P.inputs([{ n: 1, kind: 'error' }]), [], 'nothing when no line sends anything');

// --- messages ---------------------------------------------------------------------------------
eq(P.check({ type: 'lens:ready' }), { type: 'lens:ready' }, 'ready');
eq(P.check({ type: 'lens:write', state: { a: 1 }, outputs: { A: ' [1; 2] ', 'L!': "3 * 'm", 'Δp': '1' } }),
  { type: 'lens:write', state: { a: 1 }, outputs: { A: '[1; 2]', 'L!': "3 * 'm", 'Δp': '1' } }, 'a write, trimmed');
eq(P.check({ type: 'lens:write', outputs: {} }), { type: 'lens:write', state: null, outputs: {} }, 'a write with no state');
for (const bad of [null, 'lens:ready', { type: 'lens:eval' }, { type: 'lens:write', state: [1] },
  { type: 'lens:write', outputs: { '~g': '1' } }, { type: 'lens:write', outputs: { A: '1\nB = 2' } },
  { type: 'lens:write', outputs: { A: 2 } }, { type: 'lens:write', outputs: ['A'] }, { type: 'lens:write', outputs: { A: ' ' } },
  { type: 'lens:preview', svg: '<script>alert(1)</script>' }, { type: 'lens:preview', svg: 3 }])
  eq(P.check(bad), null, `refused: ${JSON.stringify(bad)}`);
eq(P.check({ type: 'lens:preview', svg: '<svg xmlns="http://www.w3.org/2000/svg"></svg>' }).type, 'lens:preview', 'a picture');
assert.ok(P.imageUrl('<svg>#</svg>').startsWith('data:image/svg+xml;charset=utf-8,%3Csvg%3E%23'));
n++;

console.log(`plugins: ${n} checks passed`);
