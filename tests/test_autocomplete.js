// Run with: node tests/test_autocomplete.js
const assert = require('assert');
const A = require('../laconic/static/autocomplete.js');
let n = 0;
const eq = (a, b, label) => { assert.deepStrictEqual(a, b, label); n++; };

const vocab = {
  units: [['m', 'meter', 1], ['mm', 'millimeter', 1], ['min', 'minute', 1], ['mile', 'mile', 0], ['kN', 'kilonewton', 1],
          ['N', 'newton', 1], ['GPa', 'gigapascal', 1], ['kg', 'kilogram', 1], ['metre', 'meter', 0], ['k', 'boltzmann_constant', 0]],
  globalUnits: [['smoot', "1.7018'm"]],
  functions: [['sin', 'sin(angle)'], ['sqrt', 'sqrt(x)'], ['solve', 'solve(A, b)']],
  constants: ['e', 'pi'],
  commands: [['clear', 'remove all non-global variables'], ['assume', 'back to SI'], ['noassume', 'keep typed units']],
};
// "text|" with the caret marked
function at(src, opts) {
  const pos = src.indexOf('|'), text = src.replace('|', '');
  return { text, pos, ctx: A.context(text, pos, opts) };
}
function pick(src, opts, extras) {
  const { text, ctx } = at(src, opts);
  return A.candidates(ctx, vocab, text, extras).map((c) => c.insert);
}

// --- when to open --------------------------------------------------------------
eq(at("w = 12'k|").ctx.kind, 'unit', 'after an apostrophe');
eq(at("w = 12'|").ctx.query, '', 'an apostrophe alone opens the unit list');
eq(at("w = 12'kN / 'm|").ctx.start, "w = 12'kN / '".length, 'second unit in a compound');
eq(at('x = si|').ctx.kind, 'name', 'a name of two letters');
eq(at('x = s|').ctx, null, 'one letter is too little');
eq(at('x = s|', { force: true }).ctx.kind, 'name', 'Ctrl+Space forces it');
eq(at('x = |', { force: true }).ctx.query, '', 'forced with nothing typed');
eq(at('x = |').ctx, null, 'nothing typed, nothing offered');
eq(at('x = 12|').ctx, null, 'numbers are not completed');
eq(at('x = 1e|').ctx, null, 'a number with an exponent is not a name');
eq(at('x = 4.|').ctx, null, 'after a decimal point');
eq(at('# a note si|').ctx, null, 'comments');
eq(at('si|n = 3').ctx, null, 'the name being defined on the left of =');
eq(at("'sm|oot = 2'm").ctx, null, 'the unit being defined');
eq(at('f(x, ab|) = x').ctx, null, 'function parameters');
eq(at("x = si|n(a)").ctx.end, 'x = sin'.length, 'the whole word is replaced');
eq(at('!cl|').ctx.kind, 'command', 'after !');
eq(at('!clear x|').ctx, null, 'no commands after the first word');
eq(at('x = ~ab|').ctx.tilde, true, 'a typed ~ restricts to globals');
eq(at('x = ~ab|').ctx.start, 'x = '.length, 'and is replaced with the name');

// --- what to offer ---------------------------------------------------------------
eq(pick("w = 12'm|"), ['m', 'mm', 'min', 'mile', 'metre'], 'units by prefix, common first');
eq(pick("w = 12'|").slice(0, 3), ['smoot', 'N', 'm'], 'an empty query lists your own units, then the common ones');
eq(pick("w = 12'sm|"), ['smoot'], 'your own unit');
eq(pick("w = 12'newt|"), ['N', 'kN'], 'by description, then inside a description');
eq(pick("w = 12'kil|"), ['kN', 'kg'], 'by description, shorter first');
eq(pick("w = 12'mm|"), [], 'a unit that is already complete offers nothing');
eq(pick("w = 12'GPA|"), ['GPa'], 'ignoring case');
eq(pick("w = 12'xyz|"), [], 'no match');
eq(pick("w = 12'k|"), ['kN', 'kg', 'k'], 'common units before an exact match on something obscure');
eq(pick("'zap = 3'm\nw = 12'za|"), ['zap'], 'a unit defined in this sheet');
eq(pick("w = 12'za|\n'zap = 3'm"), ['zap'], 'even when it is defined below');

eq(pick('delta_max = 3\nx = de|'), ['delta_max'], 'a variable defined above');
eq(pick('x = de|\ndelta_max = 3'), [], 'not one defined below');
eq(pick('~g = 9.81\nx = g|', { force: true }), ['~g'], 'a global found without its tilde');
eq(pick('~gg = 9.81\ngx = 1\nx = ~g|', { force: true }), ['~gg'], 'typing ~ shows only globals');
eq(pick('abc = 1\n!clear\nx = ab|'), [], 'removed by !clear');
eq(pick('~abc = 1\n!clear\nx = ab|'), ['~abc'], 'globals survive !clear');
eq(pick('KE(m, v) = m*v\nx = K|', { force: true }), ['KE'], 'your function');
eq(pick('x = so|'), ['solve'], 'built-in function');
eq(pick('x = s|', { force: true }), ['sin', 'sqrt', 'solve'], 'functions ordered by length, then name');
eq(pick('x = p|', { force: true }), ['pi'], 'constants');
eq(pick('x = 3\nx2 = x|', { force: true }), [], 'a name that is already complete offers nothing');
eq(pick('!cl|'), ['clear'], 'commands');
eq(pick('!a|'), ['assume'], 'commands by prefix');
eq(pick('!no|'), ['noassume'], 'commands');
eq(A.candidates(at('L = 4.5\nx = L|', { force: true }).ctx, vocab, 'L = 4.5\nx = L', { values: { L: '4.5 m' } }), [], 'sole exact candidate');
eq(pick('Lmax = 4.5\nx = L|', { force: true }, { values: { Lmax: '4.5 m' } }), ['Lmax'], 'with a value');
eq(A.candidates(at('Lmax = 4.5\nx = L|', { force: true }).ctx, vocab, 'Lmax = 4.5\nx = L', { values: { Lmax: '4.5 m' } })[0].detail, '4.5 m', 'value shown');
eq(A.candidates(at("w = 12'|").ctx, vocab, "w = 12'").length, 8, 'at most eight');

// --- accepting ----------------------------------------------------------------
function accepting(src, i = 0, opts) {
  const { text, ctx } = at(src, opts);
  const c = A.candidates(ctx, vocab, text)[i];
  const r = A.accept(text, ctx, c);
  const out = text.slice(0, r.from) + r.insert + text.slice(r.to);
  return out.slice(0, r.caret) + '|' + out.slice(r.caret);
}
eq(accepting("w = 12'k|"), "w = 12'kN|", 'a unit');
eq(accepting('x = so|'), 'x = solve(|)', 'a function gets brackets with the caret inside');
eq(accepting('x = so|(a, b)'), 'x = solve|(a, b)', 'unless it already has them');
eq(accepting('x = so|lv(a)'), 'x = solve|(a)', 'the rest of the word is replaced');
eq(accepting('delta = 1\nx = de|'), 'delta = 1\nx = delta|', 'a variable');
eq(accepting('~gg = 1\nx = ~g|', 0, { force: true }), '~gg = 1\nx = ~gg|', 'a global replaces the typed ~');
eq(accepting('!cl|'), '!clear|', 'a command');

// --- scanning -----------------------------------------------------------------
eq([...A.scan('a = 1\nb = 2\nf(x) = x\n', 4).vars.keys()], ['a', 'b'], 'scan variables');
eq([...A.scan('a = 1\nb = 2\nf(x, y) = x\n', 4).funcs.get('f').params], ['x', 'y'], 'scan function params');
eq([...A.scan('a = 1\nb = 2\n', 2).vars.keys()], ['a'], 'only the lines above');
eq(A.unitDefs("# c\n'zap = 3'm\nx = 1\n  'a_b = 1/12").map((u) => u.name), ['zap', 'a_b'], 'unit definitions');

console.log(`${n} autocomplete checks passed`);
