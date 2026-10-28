// Run with: node tests/test_rows.js
// The row model: what the results pane shows for each eval row. The shape of the rows themselves
// is pinned by test_lineresult.py, which also runs this module over rows the server really sent.
const assert = require('assert');
const R = require('../laconic/static/rows.js');
let n = 0;
const eq = (a, b, label) => { assert.deepStrictEqual(a, b, label); n++; };

const row = (kind, extra = {}) => ({ n: 1, end: 1, kind, source: '', text: '', latex: '', error: '', warning: '',
  stale: false, symbols: { defines: [], uses: [] }, ...extra });
const body = (r, view) => R.model(r, { view }).body;

// --- what each kind shows ---------------------------------------------------------------------
eq(body(row('assign', { latex: 'x = 2' })), { type: 'tex', tex: 'x = 2', rows: ['x = 2'] }, 'a calculation is typeset');
eq(body(row('assign', { latex: 'x = 1 + 1 = 2', latex_rows: ['x = 1 + 1', '= 2'] })).rows, ['x = 1 + 1', '= 2'],
  'with its stages, one per row, for a narrow pane');
eq(body(row('unitdef', { latex: '1 = 2' })).type, 'tex', 'so is a unit definition');
eq(body(row('heading', { text: 'Loads' })), { type: 'text', text: 'Loads' }, 'a heading shows its text');
eq(body(row('comment', { text: 'n' })), { type: 'text', text: 'n' }, 'so does a comment');
eq(body(row('blank')), { type: 'text', text: '' }, 'a blank line shows nothing');
eq(body(row('command', { source: '!sigfigs 3  ', text: 'sigfigs 3' })),
  { type: 'text', text: '!sigfigs 3  →  sigfigs 3' }, 'a command shows itself and what it did');
eq(body(row('error', { source: '  x = +', error: 'Bad' })), { type: 'error', source: 'x = +', message: 'Bad' },
  'an error shows the line and the message');
eq(body(row('plot', { plot: {} })), { type: 'plot' }, 'a plot draws from its payload');
eq(body(row('solver', { solver: {} })), { type: 'solver' }, 'so does a solver block');
eq(R.model(row('plotopt'), {}), null, 'a plot option line has no row of its own');
eq(R.model(row('solveropt'), {}), null, 'nor has a solver option line');

// --- the common parts -------------------------------------------------------------------------
const plot = R.model(row('plot', { n: 4, end: 6, stale: true, warning: 'w', plot: {} }), {});
eq([plot.line, plot.end], [4, 6], 'a block row owns its block');
eq(plot.cls, 'row plot stale', 'class names: the kind, and stale');
eq([plot.warning, plot.stale, plot.copy], ['w', true, null], 'warning and stale mark; no Copy');

// --- the LaTeX view ---------------------------------------------------------------------------
const snip = R.model(row('assign', { latex: 'x = 2', snippet: 'x = 2' }), { view: 'latex' });
eq([snip.cls, snip.body, snip.copy], ['row snip', { type: 'snippet', text: 'x = 2', solver: false }, 'x = 2'],
  'a snippet, with Copy');
eq(body(row('solver', { snippet: 'S', solver: {} }), 'latex').solver, true, 'a solver snippet keeps its controls');
eq(body(row('error', { snippet: '% bad', error: 'Bad' }), 'latex').type, 'error', 'an error is shown, not its snippet');
eq(body(row('blank', { snippet: null }), 'latex').type, 'text', 'a line without a snippet shows as usual');
eq(body(row('assign', { latex: 'x = 2', snippet: 'x = 2' }), 'typeset').type, 'tex', 'only in the LaTeX view');

// --- the row that shows a line ----------------------------------------------------------------
const shown = [{ line: 1, end: 1 }, { line: 2, end: 5 }, { line: 4, end: 4 }, { line: 6, end: 6 }];
eq(R.at(shown, 1).line, 1, 'a line with a row of its own');
eq(R.at(shown, 3).line, 2, 'an option line: its block');
eq(R.at(shown, 4).line, 4, 'a wrong option line has its own row');
eq(R.at(shown, 9), null, 'past the end');

// --- the common fields, for code that reads rows --------------------------------------------
const solver = row('solver', { n: 3, end: 4, source: '  !root x  ', stale: true, solver: {} });
eq([R.line(solver), R.head(solver), R.stale(solver), R.stale(row('assign'))], [3, '!root x', true, false], 'line, head, stale');
const rs = [row('assign', { n: 1, source: 'x = 1' }), row('assign', { n: 2, source: 'y = x' })];
eq(R.current(rs, ['x = 1', 'y = x + 1', 'z = 2']), [rs[0], null, null], 'a row only while its line reads the same');

console.log(`${n} row model checks passed`);
