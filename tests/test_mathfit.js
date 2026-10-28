// Run with: node tests/test_mathfit.js
// When a formula is fitted to the width it has (static/mathfit.js), the rule the results pane and
// the PDF export share. The drawing is tested in Chromium: test_ui.py and test_pdfdoc.py.
const assert = require('assert');
const F = require('../laconic/static/mathfit.js');
let n = 0;
const eq = (a, b, label) => { assert.deepStrictEqual(a, b, label); n++; };

eq(F.choose(300, 400), 'fit', 'a formula that fits is left alone');
eq(F.choose(400, 400), 'fit', 'so is one exactly as wide as its room');
eq(F.choose(500, 400), 'shrink', 'a little too wide is shrunk');
eq(F.choose(400 / F.MIN_ZOOM, 400), 'shrink', 'down to the smallest zoom');
eq(F.choose(400 / F.MIN_ZOOM + 1, 400), 'wrap', 'much too wide is wrapped');
eq(F.MIN_ZOOM, 0.7, 'the smallest zoom');

console.log(`${n} math fit checks passed`);
