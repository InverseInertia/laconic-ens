// Run with: node tests/test_sheettext.js
// Holds the editor's lexer and line shapes to laconic/sheettext.py, through the vectors that
// tests/test_sheettext.py checks the Python side against.
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const E = require('../laconic/static/editing.js');
const A = require('../laconic/static/autocomplete.js');

const V = JSON.parse(fs.readFileSync(path.join(__dirname, 'sheettext_vectors.json'), 'utf8'));
let n = 0;
const eq = (a, b, label) => { assert.deepStrictEqual(a, b, label); n++; };

for (const { line, tokens } of V.tokens) {
  eq(E.tokens(line).map((t) => [t.kind, t.start, t.text]), tokens, line);
  // Term selection walks over the same characters. Aside: a name's ` ! @ marks, and an exponent's
  // sign, which editing.js keeps with its number on its own (see sign()).
  for (const [kind, , text] of tokens) {
    if (kind === 'text') continue;
    for (const c of text.replace(/[`!@]+$/u, '').replace(/([eE])[+-]/u, '$1')) assert.ok(E.isTok(c), `${c} in ${text} (${line})`);
  }
}

for (const { line, def } of V.definitions) {
  const d = A.definition(line);
  eq(d && [d.kind, d.name, d.params], def, line);
}

for (const { text, line, block } of V.solver_blocks) {
  let ls = 0;
  for (let i = 1; i < line; i++) ls = text.indexOf('\n', ls) + 1;
  eq(A.solverBlock(text, ls), block, `${text} @${line}`);
}

for (const { text, caret, prose } of V.text_at) eq(E.isTextAt(text, caret), prose, `${text} @${caret}`);

for (const { text, caret, name } of V.names_at) eq(E.nameAt(text, caret, caret), name, `${text} @${caret}`);

console.log(`sheettext: ${n} checks passed`);
