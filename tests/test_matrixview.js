// Run with: node tests/test_matrixview.js
// Large matrices in the results pane, against the vectors tests/test_regression.py holds
// laconic/exports.py to, so the pane and the documents collapse a matrix the same way.
const assert = require('assert');
const MV = require('../laconic/static/matrixview.js');
const V = require('./matrix_vectors.json');
let n = 0;
const eq = (a, b, label) => { assert.deepStrictEqual(a, b, label); n++; };

for (const { tex, collapsed, sizes } of V.cases) {
  const got = MV.collapse(tex);
  eq(got.tex, collapsed, tex);
  eq(got.sizes, sizes, `sizes of ${tex}`);
}
eq(MV.label([[2, 120]]), '2 × 120', 'one matrix: its size');
eq(MV.label([[2, 120], [9, 9]]), '2 matrices', 'several: how many');

console.log(`matrixview: ${n} checks passed`);
