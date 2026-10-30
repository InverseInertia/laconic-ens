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
eq(body(row('assign', { latex: 'x = 2' })), { type: 'tex', tex: 'x = 2', rows: ['x = 2'], matrix: null }, 'a calculation is typeset');
eq(body(row('regression', { latex: 'a = 1' })).type, 'tex', 'so is a regression block');
eq(body(row('assign', { latex: 'x = 1 + 1 = 2', latex_rows: ['x = 1 + 1', '= 2'] })).rows, ['x = 1 + 1', '= 2'],
  'with its stages, one per row, for a narrow pane');
eq(body(row('unitdef', { latex: '1 = 2' })).type, 'tex', 'so is a unit definition');
eq(body(row('heading', { text: 'Loads' })), { type: 'text', text: 'Loads' }, 'a heading shows its text');
eq(body(row('symdef', { text: 'symbols a, b' })), { type: 'text', text: 'symbols a, b' }, 'a symbol declaration names its symbols');
eq(body(row('symsolve', { latex: 'x = 1' })).type, 'tex', 'a symbolic solve is typeset');
eq(body(row('comment', { text: 'n' })), { type: 'text', text: 'n' }, 'so does a comment');
eq(body(row('command', { source: '!sigfigs 3  ', text: 'sigfigs 3' })), { type: 'none' },
  'a command is all head: it shows itself and what it did');
eq(body(row('error', { source: '  x = +', error: 'Bad' })), { type: 'error', source: 'x = +', message: 'Bad' },
  'an error shows the line and the message');
eq(body(row('plot', { plot: {} })), { type: 'plot', pending: false }, 'a plot draws from its payload');
eq(body(row('plot', { pending: true })), { type: 'plot', pending: true }, 'or says it is not drawn yet');
eq(body(row('solver', { solver: {} })), { type: 'solver' }, 'so does a solver block');
eq(R.model(row('plotopt'), {}), null, 'a plot option line has no row of its own');
eq(R.model(row('solveropt'), {}), null, 'nor has a solver option line');
eq(R.model(row('loopline'), {}), null, 'nor has a line a loop runs');
eq(R.model(row('blank'), {}), null, 'nor has a blank line: the results pane leaves out the sheet\'s spacing (#143)');
eq(R.model(row('blank', { snippet: null }), { view: 'latex' }), null, 'in either view');

eq(R.model(row('assign', { latex: 'x = 2', hidden: true }), {}), null, 'a line under !hide has no row (#135)');
eq(R.model(row('plot', { plot: {}, hidden: true, snippet: 'S' }), { view: 'latex' }), null, 'in either view');
eq(R.model(row('command', { source: '!hide', text: 'hidden' }), {}).head.command, '!hide', '!hide itself shows as a command');

// --- the command indicator (#136) -------------------------------------------------------------
const head = (r, view) => R.model(r, { view }).head;
eq(head(row('command', { source: '!sigfigs 3  ', text: 'Results show 3' })), { command: '!sigfigs 3', effect: 'Results show 3' },
  'a command names itself and what it did');
for (const kind of ['plot', 'solver', 'regression', 'symsolve', 'loop']) {
  const r = row(kind, { source: '  !' + kind + ' a, b', latex: 'a = 1', plot: {}, solver: {} });
  eq(head(r), { command: '!' + kind + ' a, b', effect: '' }, `a ${kind} block names the command it was called with`);
  eq(head({ ...r, snippet: 'S' }, 'latex'), head(r), `in the LaTeX view too (${kind})`);
}
eq(head(row('command', { source: '!clear', text: 'Cleared', snippet: '% !clear' }), 'latex').command, '!clear',
  'a command keeps its indicator over its snippet');
for (const kind of ['assign', 'expr', 'heading', 'comment', 'error', 'symdef'])
  eq(head(row(kind, { source: '!plot nope' })), null, `no indicator on a ${kind} line`);

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
eq(body(row('comment', { text: 'n', snippet: null }), 'latex').type, 'text', 'a line without a snippet shows as usual');
eq(body(row('assign', { latex: 'x = 2', snippet: 'x = 2' }), 'typeset').type, 'tex', 'only in the LaTeX view');

// --- large matrices --------------------------------------------------------------------------
const wide = (k) => '\\begin{bmatrix} ' + Array.from({ length: k }, (_, i) => i + 1).join(' & ') + ' \\end{bmatrix}';
const big = row('assign', { n: 7, latex: 'D = ' + wide(12), latex_rows: ['D = ' + wide(12)] });
const shut = body(big);
eq(shut.tex, 'D = \\begin{bmatrix} 1 & 2 & 3 & \\cdots & 11 & 12 \\end{bmatrix}', 'a wide matrix shows its ends');
eq([shut.rows, shut.matrix], [[shut.tex], { size: '1 \u00d7 12', expanded: false }], 'and offers to show it whole');
const open = R.model(big, { expanded: new Set([7]) }).body;
eq([open.tex, open.matrix.expanded], [big.latex, true], 'an expanded line shows it whole');
eq(body(row('assign', { latex: wide(8) })).matrix, null, 'a matrix of 8 columns is shown whole');

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

// --- which pending plot is drawn first ---------------------------------------------------------
{
  const p = (n, end, extra = {}) => row('plot', { n, end, pending: true, ...extra });
  const rows = [p(2, 4), row('assign', { n: 5 }), p(10, 12), p(20, 21, { hidden: true }), p(30, 31), row('plot', { n: 40, end: 40, plot: {} })];
  eq(R.plotOrder(rows, 11), [10, 2, 30, 20], 'nearest the focused line first, hidden ones last, drawn ones not at all');
  eq(R.plotOrder(rows, 1), [2, 10, 30, 20], 'from the top');
  eq(R.plotOrder(rows, 3), [2, 10, 30, 20], 'a caret inside a plot\'s block is on it');
}

console.log(`${n} row model checks passed`);
