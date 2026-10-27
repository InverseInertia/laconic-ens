// Run with: node tests/test_unitbrowser.js
const assert = require('assert');
const U = require('../laconic/static/unitbrowser.js');
let n = 0;
function eq(a, b, label) { assert.deepStrictEqual(a, b, label); n++; }

const data = {
  tags: ['common', 'constants', 'pressure', 'thermodynamics'],
  units: [
    ['Pa', 'pascal', ['common', 'pressure', 'thermodynamics']],
    ['psi', 'pound_force_per_square_inch', ['common', 'pressure']],
    ['R', 'universal gas constant, 8.31446261815 J/K/mol', ['constants', 'thermodynamics']],
    ['k_B', 'Boltzmann constant, 1.380649e-23 J/K', ['constants']],
  ],
};
const names = (rows) => rows.map((r) => r[0]);

// Searching: every word of the query, in the name or the description, any case; a leading quote is ignored.
eq(names(U.filter(data, {}, '', null)), ['Pa', 'psi', 'R', 'k_B'], 'no query, no tag: every unit');
eq(names(U.filter(data, {}, 'gas', null)), ['R'], 'gas finds R by its description');
eq(names(U.filter(data, {}, 'BOLTZ', null)), ['k_B'], 'any case');
eq(names(U.filter(data, {}, "'psi", null)), ['psi'], 'a quote in front is ignored');
eq(names(U.filter(data, {}, 'pound square', null)), ['psi'], 'every word must match');
eq(names(U.filter(data, {}, 'pound gas', null)), [], 'no unit has both words');

// Filtering by tag, standard or the user's own.
eq(names(U.filter(data, {}, '', 'constants')), ['R', 'k_B'], 'a standard tag');
eq(names(U.filter(data, {}, 'gas', 'constants')), ['R'], 'tag and query together');
const mine = { 'heat transfer': ['k_B', 'Pa'] };
eq(names(U.filter(data, mine, '', 'heat transfer')), ['Pa', 'k_B'], "the user's tag, in list order");

// The tag list: the standard ones in order, then the user's alphabetically, each once.
eq(U.tagList(data, { zeta: ['Pa'], alpha: ['R'], pressure: ['R'] }),
  ['common', 'constants', 'pressure', 'thermodynamics', 'alpha', 'zeta'], 'tag list');
eq(U.tagsOf(data.units[3], mine), ['constants', 'heat transfer'], "a unit's tags, standard first");
eq(U.tagsOf(data.units[2], { constants: ['R'] }), ['constants', 'thermodynamics'], 'a tag shown once');

// Adding and removing tags returns a new object and leaves the old one alone.
const t1 = U.addTag({}, '  heat   transfer ', 'R');
eq(t1, { 'heat transfer': ['R'] }, 'a tag name is trimmed and its spaces collapsed');
eq(U.addTag(t1, 'heat transfer', 'R'), t1, 'tagging twice changes nothing');
eq(U.addTag(t1, 'heat transfer', 'Pa'), { 'heat transfer': ['R', 'Pa'] }, 'a second unit');
eq(U.addTag(t1, '   ', 'Pa'), t1, 'a blank tag is not added');
const t2 = U.addTag(t1, 'mine', 'psi');
eq(U.removeTag(t2, 'mine', 'psi'), t1, 'a tag left with no units goes');
eq(U.removeTag(t2, 'heat transfer', 'Pa'), t2, 'removing a unit the tag lacks changes nothing');
eq(U.removeTag(t2, 'nope', 'Pa'), t2, 'an unknown tag changes nothing');
eq(t1, { 'heat transfer': ['R'] }, 'the original is untouched');

console.log(`unitbrowser: ${n} checks passed`);
