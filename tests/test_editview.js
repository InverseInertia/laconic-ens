// Run with: node tests/test_editview.js
// The editor's view of the sheet: folds (#154), matrix rows (#155), and the map back to the text.
const assert = require('assert');
const EV = require('../laconic/static/editview.js');
let n = 0;
const eq = (a, b, label) => { assert.deepStrictEqual(a, b, label); n++; };

// ---- what folds -----------------------------------------------------------------------
const sheet = '## Beam\nL = 2\n!plot x, x = 0 .. L\n  title: t\n  grid: on\n\n## Next\ny = 1\n';
eq([...EV.regions(sheet)], [[1, 5], [3, 5], [7, 8]], 'a heading to the next, a block over its indented lines');
eq([...EV.regions('## A\n### B\nx\n## C\ny')], [[1, 3], [2, 3], [4, 5]], 'a heading takes in lower ones');
eq([...EV.regions('a\n\n')], [], 'nothing to fold');
eq(EV.literals('A = [1, 2; 3, 4]'), [{open: 4, close: 15, semis: [9], column: false}], 'a matrix');
eq(EV.literals('v = [1; 2; 3]')[0].column, true, 'a column vector');
eq(EV.literals('w = [f(1, 2); 3]')[0].column, true, 'commas inside a call are not columns');
eq(EV.literals('x = idx([1, 2], 1) + "[a; b]"').length, 1, 'only literals, and not in strings');
eq(EV.literals('# [1; 2]'), [], 'not in comments');
eq(EV.literals('x = [5]'), [], 'one element folds to nothing shorter');
eq([...EV.foldable('v = [1; 2]\n## H\nx')], [2, 1], 'a vector line can fold');

// ---- the view ---------------------------------------------------------------------------
let L = EV.layout(sheet, {folds: new Set([3])});
eq(L.view, '## Beam\nL = 2\n!plot x, x = 0 .. L  ⋯ 2 lines\n\n## Next\ny = 1\n', 'a folded block');
eq(L.lines.map((l) => l.n), [1, 2, 3, 6, 7, 8, 9], 'the lines the view shows');
eq(L.toModel(L.view.indexOf('\n\n## Next')), sheet.indexOf('\n\n## Next'), 'after the placeholder: the end of the block');
eq(L.toView(sheet.indexOf('  title')), L.view.indexOf('\n\n## Next'), 'inside the fold: after the placeholder');
eq(L.toView(sheet.indexOf('\n  title')), L.view.indexOf('  ⋯'), 'the end of the folded line: before it');
L = EV.layout(sheet, {folds: new Set([1, 3])});
eq(L.view, '## Beam  ⋯ 4 lines\n\n## Next\ny = 1\n', 'a folded heading hides a fold inside it');

const m = 'A = [1, 2; 3, 4]\nv = [1; 2; 3]\n';
L = EV.layout(m, {rows: true});
eq(L.view, 'A = [1, 2;\n     3, 4]\nv = [1; 2; 3]\n', 'matrix rows lined up; the column vector left alone');
eq(L.identity, false, 'not the text');
eq(L.toModel(L.view.indexOf('3, 4')), m.indexOf('3, 4'), 'a row maps back');
eq(L.toView(m.indexOf('3, 4')), L.view.indexOf('3, 4'), 'the caret before a row goes to its start');
eq(L.toView(m.indexOf(' 3, 4'), true), L.view.indexOf(';') + 1, 'and before, to the end of the row above');
eq([L.added(L.view.indexOf(';') + 1), L.added(L.view.indexOf('3, 4'))], [true, false], 'which characters the view adds');
eq(EV.layout(m).view, m, 'rows off');
L = EV.layout(m, {folds: new Set([1, 2]), rows: true});
eq(L.view, 'A = [⋯]\nv = [⋯]\n', 'folded literals, vectors too');
eq(EV.layout('B = [1, 2; 3, 4; 5, 6]', {rows: true}).view, 'B = [1, 2;\n     3, 4;\n     5, 6]', 'three rows');

// ---- edits in the view, back to the text -------------------------------------------------
L = EV.layout(m, {rows: true});
let v = L.view.replace('3, 4', '3, 45');
eq(EV.edit(L, v, v.indexOf('45') + 2), {from: m.indexOf('4]') + 1, to: m.indexOf('4]') + 1, insert: '5', dir: 0,
  viewFrom: L.view.indexOf('4]') + 1, viewTo: L.view.indexOf('4]') + 1}, 'typing in a row');
v = L.view.replace(';\n     3', ';\n    3');   // Backspace in the row's indent
let e = EV.edit(L, v, v.indexOf('3, 4'), -1);
eq([e.from, e.to, e.insert], [m.indexOf(' 3, 4') + 1, m.indexOf(' 3, 4') + 1, ''], 'the indent is not the text');
e = EV.widen(m, e);
eq(m.slice(0, e.from) + e.insert + m.slice(e.to), 'A = [1, 2, 3, 4]\nv = [1; 2; 3]\n', 'so Backspace joins the rows');
e = EV.widen(m, {from: m.indexOf(' 3, 4') + 1, to: m.indexOf(' 3, 4') + 1, insert: '', dir: 1});
eq(m.slice(0, e.from) + e.insert + m.slice(e.to), 'A = [1, 2, 3, 4]\nv = [1; 2; 3]\n', 'and so does Delete');
L = EV.layout(sheet, {folds: new Set([3])});
const ph = L.view.indexOf('  ⋯');
eq(EV.edit(L, L.view.slice(0, ph + 3) + 'x' + L.view.slice(ph + 3), ph + 4), {unfold: 3}, 'typing in a placeholder opens it');
v = L.view.slice(0, ph) + 'y' + L.view.slice(ph);
e = EV.edit(L, v, ph + 1);
eq([e.from, e.insert], [sheet.indexOf('\n  title'), 'y'], 'typing just before it is on the folded line');

eq([...EV.shift(new Set([1, 3, 7]), sheet, {from: 8, to: 8, insert: 'a\nb\n'})], [1, 5, 9], 'folds move down');
eq([...EV.shift(new Set([1, 3]), sheet, {from: 7, to: 14, insert: ''})], [1], 'a removed line loses its fold');

// ---- history -------------------------------------------------------------------------------
const h = new EV.History();
h.record({text: ''}, {from: 0, to: 0, insert: 'a'}, true);
h.record({text: 'a'}, {from: 1, to: 1, insert: 'b'}, true);
h.record({text: 'ab'}, {from: 2, to: 2, insert: 'X'}, false);
eq(h.undo({text: 'abX'}), {text: 'ab'}, 'a hotkey edit is its own step');
eq(h.undo({text: 'ab'}), {text: ''}, 'typing is one step');
eq(h.redo({text: ''}), {text: 'ab'}, 'redo');
eq(h.undo({text: 'ab'}), {text: ''}, 'undo again');
eq(h.undo({text: ''}), null, 'nothing more');

console.log(`editview: ${n} checks passed`);
