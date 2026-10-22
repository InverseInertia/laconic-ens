// Run with: node tests/test_paste.js
const assert = require('assert');
const P = require('../laconic/static/paste.js');
let n = 0;
function eq(a, b, label) { assert.strictEqual(a, b, label); n++; }
const m = (t) => { const r = P.toMatrix(t); return r && (r.matrix || 'REJECT:' + r.reject); };

// The user's sample: numeric first row above the separator, padded cells, thousands commas.
const sample = `| 110      | 174            | 107,000         |
| -------- | -------------- | --------------- |
| 110      | 184            | 67,000          |
| 110      | 192            | 73,000          |
| 110      | 176            | 68,000          |`;
const want = '[110, 174, 107000; 110, 184, 67000; 110, 192, 73000; 110, 176, 68000]';
eq(m(sample), want, 'markdown sample keeps numeric first row');
eq(m(sample.replace(/\n/g, '\r\n') + '\r\n'), want, 'CRLF and trailing newline');
eq(m(sample.split('\n').map((l) => '   ' + l + '   ').join('\n')), want, 'indented lines, trailing spaces');
eq(m(sample.replace(/ /g, ' ')), want, 'non-breaking spaces everywhere');
eq(m(sample.replace(/^\| /gm, '').replace(/ \|$/gm, '')), want, 'no outer pipes');
eq(m(sample.replace(/\|/g, ' | ').replace(/ +/g, ' ')), want, 'ragged spacing');
eq(m(sample.replace(/\|/g, '\t').replace(/^\t|\t$/gm, '').split('\n').filter((l, i) => i !== 1).join('\n')), want, 'same data as Excel TSV');
eq(m('110\t174\t107,000\r\n110\t184\t67,000\r\n'), '[110, 174, 107000; 110, 184, 67000]', 'Excel CRLF');
eq(m(' 110 \t 174\t\n 110\t184\t'), '[110, 174, 0; 110, 184, 0]', 'padded cells, trailing tab -> blank column kept as zeros');

// headers and labels
eq(m('| Case | L | P |\n|:--|--:|:-:|\n| a | 1 | 2 |\n| b | 3 | 4 |'), '[1, 2; 3, 4]', 'header + label column dropped');
eq(m('x\ty\n1\t2\n3\t4'), '[1, 2; 3, 4]', 'Excel header dropped');
// numbers
eq(m('1\t-2.5\n+3\t.5'), '[1, -2.5; 3, 0.5]', 'signs and leading dot');
eq(m('1\t−2\n(3)\t1e-3'), '[1, -2; -3, 1e-3]', 'unicode minus, accounting negative, exponent');
eq(m('1,5\t2,25\n3\t4'), '[1.5, 2.25; 3, 4]', 'decimal comma');
eq(m('1 234\t5\n6\t7'), '[1234, 5; 6, 7]', 'space thousands');
eq(m('50%\t$1,200\n1\t2'), '[0.5, 1200; 1, 2]', 'percent and currency');
eq(m('**1**\t[[x|2]]\n$3$\t`4`'), '[1, 2; 3, 4]', 'markdown decoration stripped');
// units
eq(m('10 kN\t5 kN\n3 kN\t4 kN'), "[10, 5; 3, 4] * 'kN", 'common unit factored out');
eq(m('10 kN/m\t5 kN/m'), "[10, 5] * 'kN / 'm", 'compound unit');
eq(m('10 kN\t5 m'), 'REJECT:The cells have different units, so it was pasted as text', 'mixed units rejected');
eq(m('a\tb\n1\tfoo'), 'REJECT:The table has text cells, so it was pasted as text', 'text cell rejected');
// shapes
eq(m('1\t2\t3'), '[1, 2, 3]', 'row vector');
eq(m('1\n2\n3'), '[1; 2; 3]', 'column vector');
eq(m('1,2\n3,4'), '[1, 2; 3, 4]', 'csv');
eq(m('"1"\t"2\t3"\n4\t5'), 'REJECT:The table has text cells, so it was pasted as text', 'quoted cell with a tab is text');
// not tables
for (const t of ['x = 5', 'A = [1, 2; 3, 4]', '42', 'f(a, b) = a + b\ng = 2', '# a | b', '1, 2', '']) eq(P.toMatrix(t), null, 'not a table: ' + t);

// the edit
let r = P.pasteEdit('A = 1\n', '1\t2\n3\t4', 6, 6, {});
eq(r.insert, 'B = [1, 2; 3, 4]', 'blank line gets a free name');
r = P.pasteEdit('K = ', '1\t2', 4, 4, {});
eq(r.insert, '[1, 2]', 'after = only the matrix'); eq(r.caret, 10, 'caret after matrix');
eq(P.pasteEdit('# note ', '1\t2', 7, 7, { textLine: true }), null, 'comment lines are left alone');
eq(P.pasteEdit('x', 'hello', 1, 1, {}), null, 'plain text untouched');
console.log(n + ' paste checks passed');
