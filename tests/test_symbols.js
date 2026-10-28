// Run with: node tests/test_symbols.js
// How the page reads the symbol table out of the eval rows. What the table holds is tested in test_symbols.py.
const assert = require('assert');
const S = require('../laconic/static/symbols.js');
let n = 0;
const eq = (a, b, label) => { assert.deepStrictEqual(a, b, label); n++; };

// rows as /api/eval sends them for "a = 1\n~g = 2\n!clear\ny = g + a"
const sym = (id, name, line, until, global) => ({ id, name, kind: 'variable', line, until, global, value: String(id), params: [] });
const ROWS = [
  { n: 1, symbols: { defines: [sym(0, 'a', 1, 3, false)], uses: [[0, 1, 0]] } },
  { n: 2, symbols: { defines: [sym(1, 'g', 2, null, true)], uses: [[0, 2, 1]] } },
  { n: 3, symbols: { defines: [], uses: [] } },
  { n: 4, symbols: { defines: [], uses: [[4, 1, 1]] } },
];
const T = S.table(ROWS);
eq(T.map((s) => s.id), [0, 1], 'every symbol, in order');
eq(S.table(undefined), [], 'no rows yet');
eq(S.visible(T, 1).map((s) => s.name), [], 'nothing above the first line');
eq(S.visible(T, 3).map((s) => s.name), ['a', 'g'], 'a !clear line still sees what it clears');
eq(S.visible(T, 4).map((s) => s.name), ['g'], 'below it only the global');
eq([...S.globals(T).keys()], ['g'], 'globals by name');
eq(S.globals(T).get('g').line, 2, 'with the line that made them global');
eq(S.marks(ROWS[3], T), [[4, 1, 'g']], 'marks: uses of globals only');
eq(S.marks(ROWS[0], T), [], 'not of other names');
eq(S.marks({ n: 9 }, T), [], 'a row without a table');

// "$x, ~$g\ny = x*g": a symbol and a global symbol (declared with $)
const SROWS = [
  { n: 1, symbols: { defines: [{ ...sym(0, 'x', 1, null, false), symbol: true }, { ...sym(1, 'g', 1, null, true), symbol: true }],
    uses: [[0, 2, 0], [4, 3, 1]] } },
  { n: 2, symbols: { defines: [sym(2, 'y', 2, null, false)], uses: [[0, 1, 2], [4, 1, 0], [6, 1, 1]] } },
];
const ST = S.table(SROWS);
eq(S.symbolMarks(SROWS[1], ST), [[4, 1, 'x'], [6, 1, 'g']], 'symbol marks: uses of symbols, global or not');
eq(S.symbolMarks(SROWS[0], ST), [[0, 2, 'x'], [4, 3, 'g']], 'a declaration marks its names, $ and all');
eq(S.marks(SROWS[1], ST), [[6, 1, 'g']], 'a global symbol is a global too');
eq(S.symbolMarks(ROWS[3], T), [], 'no symbols, no marks');

console.log(`${n} symbol table checks passed`);
