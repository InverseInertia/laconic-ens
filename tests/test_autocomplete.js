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
  commands: [['clear', 'remove all non-global variables'], ['assume', 'back to SI'], ['noassume', 'keep typed units'], ['trigdeg', 'trig in degrees'], ['trigrad', 'trig in radians']],
};
// A symbol table as the server sends it (laconic/symbols.py); which names a line sees is tested there.
const sym = (id, name, line, more) => ({ id, name, kind: 'variable', line, until: null, global: false, value: '', params: [], ...more });
const TABLE = [
  sym(0, 'delta_max', 1, { value: '3' }),
  sym(1, 'grav', 2, { global: true, value: '9.81 m/s²' }),
  sym(2, 'gx', 3),
  sym(3, 'KE', 4, { kind: 'function', params: ['m', 'v'] }),
  sym(4, 'Lmax', 5, { value: '4.5 m' }),
  sym(5, 'L', 6, { value: '4.5 m' }),
  sym(6, 'abc', 7, { until: 8 }),
  sym(7, 'sin', 8, { kind: 'function', params: ['x'] }),
];
// "text|" with the caret marked
function at(src, opts) {
  const pos = src.indexOf('|'), text = src.replace('|', '');
  return { text, pos, ctx: A.context(text, pos, opts) };
}
function pick(src, opts, extras) {
  const { text, ctx } = at(src, opts);
  return A.candidates(ctx, vocab, text, { symbols: TABLE, ...extras }).map((c) => c.insert);
}
// the caret on line `n` of a sheet the fixture table describes
const below = (n, typed) => '\n'.repeat(n - 1) + typed;

// --- no popup inside the text of a plot option -------------------------------------
eq(at('!plot f(x), x = 0 .. 1\n  title: Mom|').ctx, null, 'no suggestions in a plot title');
eq(at('  ylabel: Mom|').ctx, null, 'no suggestions in an axis label');
eq(at('  label 2: Mom|').ctx, null, 'no suggestions in a series label');
eq(at('  xlim: 0 .. mo|').ctx !== null, true, 'suggestions still work in a limit');
// a !plot statement holds expressions, unlike other commands
eq(at('!plot mom|ent(x), x = 0 .. 1').ctx.kind, 'name', 'names are suggested in a plot statement, even before the =');
eq(at("!plot M(x), x = 0 .. 2'|").ctx.kind, 'unit', 'units are suggested in the range of a plot statement');
eq(at('!cl|').ctx.kind, 'command', 'other commands still complete as commands');
eq(at('!plotspec gr|').ctx, null, 'no suggestions in a !plotspec option');

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

eq(pick(below(9, 'x = de|')), ['delta_max'], 'a variable from the table');
eq(pick(below(1, 'x = de|')), [], 'only those the line sees');
eq(pick(below(9, 'x = gr|'), { force: true }), ['~grav'], 'a global found without its tilde, inserted with it');
eq(pick(below(9, 'x = ~g|'), { force: true }), ['~grav'], 'typing ~ shows only globals');
eq(pick(below(9, 'x = ab|')), [], 'not one the table says was cleared');
eq(pick(below(9, 'x = K|'), { force: true }), ['KE'], 'your function');
eq(pick(below(9, 'x = si|')), ['sin'], 'your function hides the built-in of the same name');
eq(pick('x = de|', {}, { symbols: undefined }), [], 'no table yet, no names of yours');
eq(pick('x = so|'), ['solve'], 'built-in function');
eq(pick('x = s|', { force: true }), ['sin', 'sqrt', 'solve'], 'functions ordered by length, then name');
eq(pick('x = p|', { force: true }), ['pi'], 'constants');
eq(pick('!cl|'), ['clear'], 'commands');
eq(pick('!a|'), ['assume'], 'commands by prefix');
eq(pick('!no|'), ['noassume'], 'commands');
eq(pick(below(9, 'x = L|'), { force: true }), ['L', 'Lmax'], 'variables');
eq(pick(below(9, 'x = Lmax|')), [], 'a name that is already complete offers nothing');
eq(A.candidates(at(below(9, 'x = Lma|')).ctx, vocab, below(9, 'x = Lma'), { symbols: TABLE })[0].detail, '4.5 m', 'value shown');
eq(A.candidates(at("w = 12'|").ctx, vocab, "w = 12'").length, 8, 'at most eight');

// --- accepting ----------------------------------------------------------------
function accepting(src, i = 0, opts) {
  const { text, ctx } = at(src, opts);
  const c = A.candidates(ctx, vocab, text, { symbols: TABLE })[i];
  const r = A.accept(text, ctx, c);
  const out = text.slice(0, r.from) + r.insert + text.slice(r.to);
  return out.slice(0, r.caret) + '|' + out.slice(r.caret);
}
eq(accepting("w = 12'k|"), "w = 12'kN|", 'a unit');
eq(accepting('x = so|'), 'x = solve(|)', 'a function gets brackets with the caret inside');
eq(accepting('x = so|(a, b)'), 'x = solve|(a, b)', 'unless it already has them');
eq(accepting('x = so|lv(a)'), 'x = solve|(a)', 'the rest of the word is replaced');
eq(accepting(below(9, 'x = del|')), below(9, 'x = delta_max|'), 'a variable');
eq(accepting(below(9, 'x = ~g|'), 0, { force: true }), below(9, 'x = ~grav|'), 'a global is inserted with its ~');
eq(accepting(below(9, 'x = gr|'), 0, { force: true }), below(9, 'x = ~grav|'), 'even when the ~ was not typed');
eq(accepting('!cl|'), '!clear|', 'a command');

// --- unit definitions in the text ----------------------------------------------
eq(A.unitDefs("# c\n'zap = 3'm\nx = 1\n  'a_b = 1/12").map((u) => u.name), ['zap', 'a_b'], 'unit definitions');

// --- solver blocks -------------------------------------------------------------------------
vocab.solver = {
  keys: { root: [['equation', 'lhs = rhs'], ['bounds', 'low .. high'], ['method', 'which solver'], ['autorun', 'on/off']],
          minimize: [['objective', 'f'], ['constraint', 'c'], ['bounds', 'low .. high'], ['method', 'which solver']] },
  methods: { root: [['hybr', 'default'], ['lm', 'least squares'], ['brentq', 'bracketed']],
             optimize: [['BFGS', 'default'], ['Nelder-Mead', 'simplex'], ['L-BFGS-B', 'bounds'], ['SLSQP', 'constraints']] },
  choices: { autorun: [['on', 'auto'], ['off', 'manual']] },
};
const ROOT = 'x1 = 1\nx2 = 2\n!root x1, x2\n';
eq(pick(ROOT + '  m|'), ['method'], 'option keys under a block');
eq(pick('x = 1\n!root x\n  equation: x = 1\n  |', { force: true }), ['equation', 'bounds', 'method', 'autorun'], 'all keys by hand, in the block\'s order');
eq(at(ROOT + '  |').ctx, null, 'no popup on a bare indent');
eq(pick(ROOT + '  bo|'), ['bounds x1', 'bounds x2'], 'several unknowns: one bounds line per unknown');
eq(pick('d = 1\n!minimize d\n  bo|'), ['bounds'], 'one unknown: plain bounds');
eq(pick('d = 1\n!minimize d\n  ob|'), ['objective'], 'minimize has its own keys');
eq(accepting(ROOT + '  me|'), ROOT + '  method: |', 'a key is inserted with its colon');
eq(accepting(ROOT + '  me|: lm'), ROOT + '  method|: lm', 'not a second colon');
eq(pick(ROOT + '  bounds |', { force: true }), ['x1', 'x2'], 'after bounds, the unknowns');
eq(accepting(ROOT + '  bounds x|'), ROOT + '  bounds x1: |', 'and its colon');
eq(pick(ROOT + '  method: |'), ['hybr', 'lm', 'brentq'], 'root methods');
eq(pick('d = 1\n!minimize d\n  objective: d^2\n  method: |'), ['BFGS', 'Nelder-Mead', 'L-BFGS-B', 'SLSQP'], 'optimizer methods');
eq(pick('d = 1\n!maximize d\n  method: l-|'), ['L-BFGS-B'], 'a method with a hyphen, ignoring case');
eq(accepting('d = 1\n!minimize d\n  method: Nel|der'), 'd = 1\n!minimize d\n  method: Nelder-Mead|', 'the whole value is replaced');
eq(pick(ROOT + '  autorun: |'), ['on', 'off'], 'autorun values');
eq(at(ROOT + '  tol: 1|').ctx, null, 'nothing for a number option');
// ROOT's table: the header defines its unknowns again
const UNKNOWNS = { symbols: [sym(0, 'x1', 1, { until: 3 }), sym(1, 'x2', 2, { until: 3 }), sym(2, 'x1', 3), sym(3, 'x2', 3)] };
eq(pick(ROOT + '  equation: x|1 = x2', { force: true }, UNKNOWNS), ['x1', 'x2'], 'the left of an equation is an expression');
eq(pick('x1 = 1\n!minimize x1\n  constraint: x| <= 3', { force: true }, UNKNOWNS), ['x1', 'x2'], 'and of a constraint');
const HEAD = { symbols: [sym(0, 'aa', 1), sym(1, 'ab', 2), sym(2, 'f', 2, { kind: 'function', params: ['t'] })] };
eq(pick('aa = 1\nab = 2\n!root a|', { force: true }, HEAD), ['aa', 'ab'], 'variables in the header');
eq(pick('aa = 1\nf(t) = t\n!root aa, f|', { force: true }, HEAD), [], 'only variables: functions cannot be unknowns');
eq(at('!ro|').ctx.kind, 'command', 'the command word is still a command');
eq(at('x = 1\n!root x\n  equation: x = 1\n  #@ result {"a|').ctx, null, 'nothing in the stored result');
eq(at('x = 1\n!root x\n  equation: x = 1\ny = x|x', { force: true }).ctx.kind, 'name', 'after the block, back to normal lines');
eq(at('x = 1\n!root x\n  equation: x = 1\nzz|w = 3').ctx, null, '... where the left of = is a definition again');

// --- props() strings ---------------------------------------------------------------------------------
vocab.props = {
  keys: [['T', 'Temperature', 'K', true, false], ['P', 'Pressure', 'Pa', true, false], ['D', 'Mass density', 'kg/m^3', true, false],
         ['Cpmass', 'Mass specific constant pressure specific heat', 'J/kg/K', false, false], ['Tcrit', 'Temperature at the critical point', 'K', false, true]],
  fluids: [['Water', 'pure fluid, H2O, R718'], ['Air', 'pure fluid, R729'], ['1-Butene', 'pure fluid, Butene'], ['INCOMP::MEG[0.3]', 'incompressible solution']],
};
eq(pick('rho = props("|'), ['T', 'P', 'D', 'Cpmass', 'Tcrit'], 'the output: every key, opened by the quote');
eq(pick('rho = props("D", "|'), ['T', 'P', 'D'], 'a state input: only keys that can be inputs');
eq(pick('rho = props("D", "T", 300\'K, "|'), ['T', 'P', 'D'], 'the second input');
eq(pick('rho = props("D", "T", 300\'K, "P", p, "W|'), ['Water'], 'the fluid is the last argument');
eq(pick('Tc = props("Tcrit", "|'), ['Water', 'Air', '1-Butene', 'INCOMP::MEG[0.3]'], 'a fixed property takes the fluid next');
eq(pick('r = props("D", "T", T, "P", p, "h2o|'), ['Water'], 'fluids match their aliases');
eq(pick('r = props("D", "T", T, "P", p, "1-|'), ['1-Butene'], 'names with hyphens');
eq(pick('r = props("D", "T", T, "P", p, "INC|'), ['INCOMP::MEG[0.3]'], 'backend prefixes');
eq(pick('r = props("cp|'), ['Cpmass'], 'keys ignoring case');
eq(accepting('r = props("Cp|'), 'r = props("Cpmass"|', 'accepting closes the string');
eq(accepting('r = props("D|'), 'r = props("D"|', 'even when the key is already typed in full');
eq(pick('r = props("D|")'), [], 'but a closed string that already says it offers nothing');
eq(accepting('r = props("C|", "T", T, "P", p, "Water")'), 'r = props("Cpmass"|, "T", T, "P", p, "Water")', 'or replaces its text');
eq(at('x = props("D", "T", T|', { force: true }).ctx.kind, 'name', 'a value argument is an ordinary expression');
eq(at('x = foo("D|').ctx, null, 'nothing in strings elsewhere');
eq(at('x = props(min("D|').ctx, null, 'nor in a nested call');
eq(A.candidates(at('r = props("|').ctx, { ...vocab, props: undefined }, 'r = props("'), [], 'nothing until the props list has arrived');

console.log(`${n} autocomplete checks passed`);
