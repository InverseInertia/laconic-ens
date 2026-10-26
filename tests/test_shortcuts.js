// Run with: node tests/test_shortcuts.js
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const S = require('../laconic/static/shortcuts.js');
let n = 0;
function eq(a, b, label) { assert.deepStrictEqual(a, b, label); n++; }
function ok(v, label) { assert.ok(v, label); n++; }
const row = S.rowHtml;

// Key cells.
eq(row({ keys: ['Ctrl+Shift+['], text: 'x' }), '<tr><td><kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>[</kbd></td><td>x</td></tr>\n', 'a combination is one kbd per key');
eq(row({ keys: ['=', '+'], inline: true, text: 'x' }), '<tr><td><kbd>=</kbd> <kbd>+</kbd></td><td>x</td></tr>\n', 'a lone + is the plus key');
eq(row({ keys: ['Ctrl+T', 'Alt+T'], text: 'x' }), '<tr><td><kbd>Ctrl</kbd>+<kbd>T</kbd><br><kbd>Alt</kbd>+<kbd>T</kbd></td><td>x</td></tr>\n', 'alternatives on separate lines');
eq(row({ keys: ['→', ')'], or: true, text: 'x' }), '<tr><td><kbd>→</kbd> or <kbd>)</kbd></td><td>x</td></tr>\n', 'or');
eq(row({ keys: ['Alt+Up'], text: 'x' }), '<tr><td><kbd>Alt</kbd>+<kbd>&uarr;</kbd></td><td>x</td></tr>\n', 'Up shows as an arrow');
eq(row({ code: "'a = 1'm < 2", text: 'x' }), "<tr><td><code>'a = 1'm &lt; 2</code></td><td>x</td></tr>\n", 'code is escaped');
eq(row({ label: 'Double-click', text: 'x' }), '<tr><td>Double-click</td><td>x</td></tr>\n', 'plain label');

// Whole table: titled sections get a heading row.
const html = S.tableHtml();
eq((html.match(/<tr>/g) || []).length, S.SECTIONS.reduce((k, s) => k + s.rows.length + (s.title ? 1 : 0), 0), 'one row per entry and heading');
ok(html.includes('<tr><td colspan="2"><strong>Highlighted text</strong></td></tr>'), 'section heading');
ok(S.SECTIONS.some((s) => s.id === 'commands' && s.rows.every((r) => r.keys.every((k) => k.startsWith('!')))), 'commands are their own section');

// Every Ctrl / Alt shortcut in the app is written up in the wiki page too.
const wiki = fs.readFileSync(path.join(__dirname, '..', 'wiki', 'Editor-Shortcuts.md'), 'utf8');
for (const c of S.combos().filter((k) => /^(Ctrl|Alt|Shift)\+/.test(k))) ok(wiki.includes('`' + c) || wiki.includes(c + '`'), `${c} is in wiki/Editor-Shortcuts.md`);

console.log(`shortcuts: ${n} checks passed`);
