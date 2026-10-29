// Run with: node tests/test_editing.js
const assert = require('assert');
const E = require('../laconic/static/editing.js');

// A tiny editor: state = {t, s, e}. Keys are single characters, or
// {key, ctrl, alt} objects, or the strings 'ArrowRight' / 'Backspace' / 'Enter'.
function start(src) {
  const i = src.indexOf('|');
  return { t: src.replace('|', ''), s: i, e: i };
}
function applyEdit(st, r) {
  if (r.select) return { ...st, s: r.select[0], e: r.select[1] };
  if (r.caretOnly !== undefined) return { ...st, s: r.caretOnly, e: r.caretOnly };
  if (r.insert === undefined) return st; // message only
  const t = st.t.slice(0, r.from) + r.insert + st.t.slice(r.to);
  return { t, s: r.caret, e: r.caret };
}
function press(st, k, ctx = {}) {
  const spec = typeof k === 'string' ? { key: k } : k;
  const mods = { ctrl: !!spec.ctrl, alt: !!spec.alt, shift: false, meta: false };
  let r = null;
  if (spec.key.length === 1 && !spec.ctrl && !spec.alt) r = E.charAction(spec.key, st.t, st.s, st.e, ctx);
  else r = E.keyAction(spec.key, mods, st.t, st.s, st.e, ctx);
  if (r) return applyEdit(st, r);
  // default browser behaviour
  if (spec.key.length === 1 && !spec.ctrl && !spec.alt) return applyEdit(st, { from: st.s, to: st.e, insert: spec.key, caret: st.s + 1 });
  if (spec.key === 'Enter') return applyEdit(st, { from: st.s, to: st.e, insert: '\n', caret: st.s + 1 });
  if (spec.key === 'ArrowRight') return { ...st, s: st.s + 1, e: st.s + 1 };
  if (spec.key === 'Backspace') {
    const from = st.e > st.s ? st.s : st.s - 1;
    return applyEdit(st, { from, to: st.e, insert: '', caret: from });
  }
  return st;
}
function sim(src, keys, ctx) {
  let st = start(src);
  for (const k of (typeof keys === 'string' ? [...keys] : keys)) st = press(st, k, ctx);
  return st.t.slice(0, st.s) + '|' + st.t.slice(st.s);
}
const ctrl = (key) => ({ key, ctrl: true });
let n = 0;
function eq(actual, expected, label) { assert.strictEqual(actual, expected, label); n++; }
function deq(actual, expected, label) { assert.deepStrictEqual(actual, expected, label); n++; }
function selEdit(t, s, e, fn) { const r = fn(t, s, e); return t.slice(0, r.from) + r.insert + t.slice(r.to); }

// --- slash: fraction -----------------------------------------------------------
eq(sim('x = a|', '/'), 'x = a / (|)', 'fraction with empty denominator');
eq(sim('x = a|', ['/', 'b', 'ArrowRight']), 'x = a / b|', 'denominator exits and drops parens');
eq(sim('x = a|', ['/', 'b', '+', 'c', 'ArrowRight']), 'x = a / (b + c)|', 'compound denominator keeps parens');
eq(sim('x = (a+b)|', '/'), 'x = (a+b) / (|)', 'parenthesised numerator');
eq(sim('x = f(a, b)|', '/'), 'x = f(a, b) / (|)', 'call is one term');
eq(sim('x = a^2|', '/'), 'x = a^2 / (|)', 'numerator includes its exponent');
eq(sim("x = 12 'kN|", '/'), "x = 12 'kN / (|)", 'number plus unit with a space');
eq(sim("w = 12'kN|", ['/', "'", 'm', 'ArrowRight']), "w = 12'kN / 'm|", 'unit fraction');
eq(sim("r = 5'%|", ['/', '2', 'ArrowRight']), "r = 5'% / 2|", "'% belongs to the numerator (#41)");
eq(sim('x = a|b', '/'), 'x = a / b|', 'term on the right becomes the denominator');
eq(sim('x = a|(b+c)', '/'), 'x = a / (b+c)|', 'bracketed term on the right');
eq(sim('x = |', '/'), 'x = (|) / ()', 'no left term');
eq(sim('x = a |', '/'), 'x = a / (|)', 'a space before the caret is absorbed');
eq(sim('x = ~g|', '/'), 'x = ~g / (|)', 'global name is one term');
eq(selEdit('x = a+b', 4, 7, (t, s, e) => E.charAction('/', t, s, e, {})), 'x = (a+b) / ()', 'selection wrapped as numerator');
eq(E.charAction('/', 'x = a+b', 4, 7, {}).caret, 'x = (a+b) / ('.length, 'caret in denominator');

// --- backslash: radical ----------------------------------------------------------
eq(sim('y = |', '\\'), 'y = sqrt(|)', 'empty radical');
eq(sim('y = |', ['\\', 'x', '+', '1', 'ArrowRight']), 'y = sqrt(x + 1)|', 'type into radical, Right leaves it');
eq(selEdit('y = a+b', 4, 7, (t, s, e) => E.charAction('\\', t, s, e, {})), 'y = sqrt(a+b)', 'selection wrapped in sqrt');
eq(sim('y = a|', [ctrl('/')]), 'y = a / |', 'Ctrl+/ types a spaced literal slash');
eq(sim('y = |', [ctrl('\\')]), 'y = \\|', 'Ctrl+\\ types a literal backslash');

// --- period: subscript ----------------------------------------------------------
eq(sim('M|', ['.', 'm', 'a', 'x']), 'M_max|', 'subscript after a name');
eq(sim('x = |', '4.5'), 'x = 4.5|', 'decimal after digits stays a period');
eq(sim('x = |', '.5'), 'x = .5|', 'leading period');
eq(sim("x = 3'kN|", '.'), "x = 3'kN.|", 'period after a unit stays literal');
eq(sim('a|', '..'), 'a_.|', 'no double subscript');
eq(sim('x1|', '.'), 'x1_|', 'name with digits still takes a subscript');
eq(sim('σ|', '.max'), 'σ_max|', 'greek name takes a subscript');
eq(sim('~g|', '.x'), '~g_x|', 'global name takes a subscript');
eq(sim('A|', ['.', '*', 'B']), 'A .* B|', 'A.* becomes a spaced elementwise multiply');
eq(sim('A|', ['.', '/', 'B']), 'A ./ B|', 'A./ via the slash key');
eq(sim('A|', ['.', ctrl('/'), 'B']), 'A ./ B|', 'A./ via Ctrl+/');
eq(sim('x = a_|', ['/']), 'x = a ./ |', 'underscore then slash is elementwise divide');

// --- caret: exponent ------------------------------------------------------------
eq(sim('y = x|', '^'), 'y = x^(|)', 'exponent slot');
eq(sim('y = x|', ['^', '2', 'ArrowRight']), 'y = x^2|', 'simple exponent drops parens');
eq(sim('y = x|', ['^', 'n', '+', '1', 'ArrowRight']), 'y = x^(n + 1)|', 'compound exponent keeps parens');
eq(sim('y = x|', ['^', '-', '1', 'ArrowRight']), 'y = x^-1|', 'negative exponent');
eq(sim('y = x|', ['^', '2', ')']), 'y = x^2|', 'typing ) leaves the slot too');
eq(sim('y = |', '^'), 'y = ^|', 'no base means literal caret');
eq(sim("y = 'm|", ['^', '2', 'ArrowRight']), "y = 'm^2|", 'unit exponent');
eq(sim('y = (a+b)|', '^'), 'y = (a+b)^(|)', 'bracket as base');

// --- Backspace removes empty slots ---------------------------------------------
eq(sim('y = x|', ['^', 'Backspace']), 'y = x|', 'backspace removes empty exponent');
eq(sim('y = a|', ['/', 'Backspace']), 'y = a|', 'backspace removes empty denominator and its slash');
eq(sim('y = (a+b)|', ['/', 'Backspace']), 'y = (a+b)|', 'same after a bracket');
eq(sim('y = |', ['\\', 'Backspace']), 'y = |', 'backspace removes empty radical');
eq(sim('y = |', ['\\', 'x', 'Backspace']), 'y = sqrt(|)', 'backspace in a filled slot deletes one char');

// --- automatic spacing around operators ----------------------------------------
eq(sim('x|', ['=', '3']), 'x = 3|', '= is spaced');
eq(sim('y = a|', ['+', 'b']), 'y = a + b|', '+ is spaced');
eq(sim('y = a|', ['-', 'b']), 'y = a - b|', 'binary - is spaced');
eq(sim('y = a|', ['*', 'b']), 'y = a * b|', '* is spaced');
eq(sim("y = 'kN|", ['*', "'", 'm']), "y = 'kN * 'm|", 'unit product is spaced');
eq(sim('y = a|', ['*', 'b', '+', 'c', '-', 'd']), 'y = a * b + c - d|', 'a whole expression');
eq(sim('y = |', ['-', '3']), 'y = -3|', 'unary minus after =');
eq(sim('y = (|)', ['-']), 'y = (-|)', 'unary minus after (');
eq(sim('A = [|]', ['-', '1']), 'A = [-1|]', 'unary minus after [');
eq(sim('A = [1, |]', ['-']), 'A = [1, -|]', 'unary minus after a comma');
eq(sim('y = a|', ['*', '-', 'b']), 'y = a * -b|', 'unary minus after *');
eq(sim('y = x|', ['^', '-', '1']), 'y = x^(-1|)', 'unary minus inside an exponent slot');
eq(sim('y = |', ['-', 'a']), 'y = -a|', 'unary minus before a name');
eq(sim('y = 8.5e|', ['-', '3']), 'y = 8.5e-3|', 'minus in scientific notation stays tight');
eq(sim('y = 2E|', ['+', '4']), 'y = 2E+4|', 'plus in scientific notation stays tight');
eq(sim('y = rate|', ['-', '1']), 'y = rate - 1|', 'a name ending in e is not an exponent');
eq(sim('M = x|', ['-', '>', "'", 'k', 'N']), "M = x -> 'kN|", '-> becomes a spaced arrow');
eq(sim('M = x|', ['-']), 'M = x - |', 'the minus before the arrow is spaced first');
eq(sim("y = 3'm|", ['-', '2', "'", 'm']), "y = 3'm - 2'm|", 'minus after a unit');
eq(sim('y = a|', ['+'], { enabled: false }), 'y = a+|', 'switch turns spacing off');
eq(sim('# a|', ['+']), '# a+|', 'comments are left alone');
eq(sim('# a|', ['=']), '# a=|', 'comments keep a plain =');

// --- double spaces ------------------------------------------------------------
eq(sim('y = a|', [' ']), 'y = a |', 'a single space is allowed');
eq(sim('y = a|', [' ', ' ']), 'y = a |', 'the second space is ignored');
eq(sim('y = a|', ['+', ' ', 'b']), 'y = a + b|', 'a habitual space after an operator is ignored');
eq(sim('y = a|', [' ', '+', 'b']), 'y = a + b|', 'a space typed before an operator is not doubled');
eq(sim('y = a| + b', [' ']), 'y = a |+ b', 'typing a space before an existing one steps over it');
eq(sim('|', [' ', ' ']), '  |', 'indentation is left alone');
eq(sim('# a|', [' ', ' ']), '# a  |', 'comments keep their spacing');
eq(sim('A = [|]', ['1', ',', ' ', '2', ';', ' ', '3']), 'A = [1, 2; 3|]', 'space after , and ; is absorbed');
eq(sim('A = [1 |]', [' ']), 'A = [1 |]', 'second space in a bracket is ignored');
eq(sim('A = [1,|]', [' ']), 'A = [1, |]', 'space right after a bare comma is an ordinary space');

// --- Backspace over spaced operators --------------------------------------------
eq(sim('y = a + |', ['Backspace']), 'y = a|', 'operator and both spaces at line end');
eq(sim('y = a + |b', ['Backspace']), 'y = a |b', 'mid-line keeps one space so terms do not fuse');
eq(sim('x = |', ['Backspace']), 'x|', '= and its spaces');
eq(sim('A = [1 + |]', ['Backspace']), 'A = [1|]', 'before a closing bracket');
eq(sim("M = x -> |", ['Backspace']), 'M = x|', 'arrow in one press');
eq(sim('A = B .* |', ['Backspace']), 'A = B|', 'elementwise operator in one press');
eq(sim('y = a * |', ['Backspace', 'Backspace']), 'y = |', 'the next press deletes the next character');
eq(sim('y = -|', ['Backspace']), 'y = |', 'a sign is an ordinary delete');
eq(sim('y = a + |', ['Backspace'], { enabled: false }), 'y = a +|', 'switch turns it off');
eq(sim('# a + |', ['Backspace']), '# a +|', 'comments are left alone');

// --- Backspace over separators --------------------------------------------------
eq(sim('A = [1, |', ['Backspace']), 'A = [1|', 'comma and its space go together');
eq(sim('A = [1; |2]', ['Backspace']), 'A = [1|2]', 'semicolon and its space go together');
eq(sim('A = [1, |]', ['Backspace']), 'A = [1|]', 'before a closing bracket');
eq(sim('A = [|]', ['1', ',', 'Backspace']), 'A = [1|]', 'typed comma undone in one press');
eq(sim('A = [|]', ['1', ',', '2', ';', 'Backspace', 'Backspace']), 'A = [1, |]', 'second press deletes the next character');
eq(sim('A = [1,  |2]', ['Backspace']), 'A = [1, |2]', 'only one of two spaces');
eq(sim('A = [1,|2]', ['Backspace']), 'A = [1|2]', 'bare comma deleted normally');
eq(sim('A = [1 |2]', ['Backspace']), 'A = [1|2]', 'a lone space is an ordinary delete');
eq(sim('# a, |', ['Backspace']), '# a,|', 'comments are left alone');
eq(sim('A = [1, |', ['Backspace'], { enabled: false }), 'A = [1,|', 'switch turns it off');
eq(sim('x = 1\n, |', ['Backspace']), 'x = 1\n|', 'works at the start of a line');

// --- commas and semicolons ----------------------------------------------------
eq(sim('A = [|]', ['1', ',', '2', ';', '3', ',', '4']), 'A = [1, 2; 3, 4|]', 'comma and semicolon get a space');
eq(sim('A = |', [ctrl('m'), '1', ',', '2']), 'A = [1, 2|]', 'typing in a fresh array');
eq(sim('y = f(|', ['a', ',', 'b']), 'y = f(a, b|', 'commas in a call get a space too');
eq(sim('A = [1| 2]', [',']), 'A = [1, |2]', 'existing space is stepped over, not doubled');
eq(sim('A = [1|]', [',']), 'A = [1, |]', 'comma before a closing bracket');
eq(sim('A = [1, 2]|', [',']), 'A = [1, 2], |', 'comma outside brackets also gets a space');
eq(sim('# a|', [',']), '# a,|', 'comments keep a plain comma');
eq(sim('A = [1|]', [','], { enabled: false }), 'A = [1,|]', 'switch turns the spacing off');
eq(sim('A = [1|]', [ctrl(',')]), 'A = [1|]', 'Ctrl+, is not a hotkey');
eq(selEdit('x = a b', 5, 6, (t, s, e) => E.charAction(',', t, s, e, {})), 'x = a, b', 'selection replaced by comma and space');

// --- arrays and transpose -------------------------------------------------------
eq(sim('A = |', [ctrl('m')]), 'A = [|]', 'Ctrl+M inserts an array');
eq(sim('A = [|]', ['Backspace']), 'A = |', 'backspace removes empty array');
eq(sim('A = [1;2]|', [ctrl('t')]), 'A = transpose([1;2])|', 'Ctrl+T wraps the term');
eq(sim('A = [1;2]|', [ctrl('t'), ctrl('t')]), 'A = [1;2]|', 'second Ctrl+T unwraps');
eq(sim('B = A|', [{ key: 't', alt: true }]), 'B = transpose(A)|', 'Alt+T alias');
eq(sim('B = ~A|', [ctrl('t')]), 'B = transpose(~A)|', 'global names transpose whole');
eq(sim('B = |', [ctrl('t')]), 'B = |', 'nothing to transpose');
eq(selEdit('B = A*C', 4, 7, (t, s, e) => E.keyAction('t', { ctrl: true }, t, s, e, {})), 'B = transpose(A*C)', 'selection is transposed');

// --- indexing: Ctrl+[ and Ctrl+Shift+[ ----------------------------------------------
eq(sim('x = A|', [ctrl('[')]), 'x = idx(A, |)', 'Ctrl+[ opens one index');
eq(sim('x = A|', [{ key: '{', ctrl: true, shift: true }]), 'x = elem(A, |)', 'Ctrl+Shift+[ opens row and column');
eq(sim('x = A|', [{ key: '{', ctrl: true, shift: true }, 'i', ',', 'j']), 'x = elem(A, i, j|)', 'typing both indexes');
eq(sim('x = idx(A, 1)|', [ctrl('[')]), 'x = idx(idx(A, 1), |)', 'indexes nest');
eq(sim('x = |', [ctrl('[')]), 'x = |', 'nothing to index');
eq(selEdit('x = A*C', 4, 7, (t, s, e) => E.keyAction('[', { ctrl: true }, t, s, e, {})), 'x = idx(A*C, )', 'selection is indexed');
eq(sim('# A|', [ctrl('[')]), '# A|', 'comments are left alone');

// --- Enter at the end of a bracket ----------------------------------------------
eq(sim('A = [1, 2|]', ['Enter']), 'A = [1, 2]\n|', 'Enter finishes the line instead of splitting before ]');
eq(sim('y = f(g(x|))', ['Enter']), 'y = f(g(x))\n|', 'several closers');
eq(sim('y = x^(n+1|)', ['Enter']), 'y = x^(n+1)\n|', 'open slot is left as typed');
eq(sim('y = a|+ b', ['Enter']), 'y = a\n|+ b', 'normal Enter elsewhere splits the line');
eq(sim('# [a|]', ['Enter']), '# [a\n|]', 'comments are left alone');

// --- Greek ----------------------------------------------------------------------
eq(sim('x = a|', [ctrl('g')]), 'x = α|', 'a -> alpha');
eq(sim('x = a|', [ctrl('g'), ctrl('g')]), 'x = a|', 'second Ctrl+G reverts');
eq(sim("v = 5'V|", [ctrl('<'), '3', '0']), "v = 5'V∠30|", 'Ctrl+< types the polar angle sign');
eq(applyEdit(start("v = 5|"), E.keyAction(',', { ctrl: true, shift: true, alt: false, meta: false }, 'v = 5', 5, 5, {})).t, 'v = 5∠', 'Ctrl+Shift+, does too');
eq(E.keyAction('<', { ctrl: true, shift: true, alt: false, meta: false }, '# a', 3, 3, {}), null, 'not in a comment');
eq(sim('x = D|', [ctrl('g')]), 'x = Δ|', 'capital delta');
eq(sim('sigma = s|', [ctrl('g')]), 'sigma = σ|', 'only the preceding character');
eq(sim('x = 5|', [ctrl('g')]), 'x = 5|', 'no mapping, no change');
eq(sim('x = 8|', [ctrl('g')]), 'x = ∞|', '8 -> infinity');
eq(sim('x = 8|', [ctrl('g'), ctrl('g')]), 'x = 8|', 'infinity reverts to 8');
eq(sim('V|', [ctrl('g'), '.', 'c', 'v']), '∀_cv|', 'V -> forall, a name that takes a subscript');
eq(sim('x = ∀|', [ctrl('g')]), 'x = V|', 'forall reverts to V');
eq(sim('T|', ['.', '8', ctrl('g'), ' ', '=', ' ', '3']), 'T_∞ = 3|', 'free-stream subscript: T.8 Ctrl+G');
eq(sim('v_∞|', '.0'), 'v_∞_0|', 'a name ending in ∞ takes a subscript');
assert.ok(E.keyAction('g', { ctrl: true }, 'x = 5', 5, 5, {}).message.includes('5')); n++;
eq(sim('x = a|', [ctrl('g')], { greek: { a: 'ȧ' } }), 'x = ȧ|', 'custom table is used');
eq(sim('x = b|', [ctrl('g')], { greek: { a: 'ȧ' } }), 'x = b|', 'custom table replaces the default');

// --- text lines under a plot ----------------------------------------------------
eq(sim('!plot f(x), x = 0 .. 1\n  title: M|', '/'), '!plot f(x), x = 0 .. 1\n  title: M/|', 'slash is literal in a plot title');
eq(sim('  ylabel: a|', '.'), '  ylabel: a.|', 'period is literal in an axis label');
eq(sim('  label 2: a|', '^'), '  label 2: a^|', 'caret is literal in a series label');
eq(sim('  note: "a|"', '/'), '  note: "a/|"', 'slash is literal in a note');
eq(sim('  xlim: a|', '/'), '  xlim: a / (|)', 'math keys still work in a limit');
eq(E.isTextAt('title = 3', 2), false, 'an unindented line is not an option');
eq(sim('  note: "a" at (L|, 2)', '/'), '  note: "a" at (L / (|), 2)', 'a note\'s position is math');
eq(sim('!minimize d\n  method: L|', '-'), '!minimize d\n  method: L-|', 'a solver method is text');
eq(sim('!minimize d\n  objective: d|', '/'), '!minimize d\n  objective: d / (|)', 'a solver objective is math');
// Where the text is prose is checked against the server's expression spans in test_sheettext.js.

// --- which lines the browser may spellcheck -------------------------------------
const sheet = '## Beam\n# a coment\nx = 3\n#@ units\n!plot x, x = 0 .. 1\n  title: Deflection';
const at = (s) => sheet.indexOf(s);
eq(E.isProse(sheet, at('Beam')), true, 'a heading is spellchecked');
eq(E.isProse(sheet, at('coment')), true, 'a comment is spellchecked');
eq(E.isProse(sheet, at('x = 3') + 2), false, 'a calculation is not');
eq(E.isProse(sheet, at('units')), false, 'nor a #@ line LENS writes');
eq(E.isProse(sheet, at('Deflection')), true, 'a plot title is text');
eq(E.isProse('!root x\n  method: brentq', 12), false, "a solver's method is a name, not prose");
eq(E.isProse(sheet, 0, at('coment')), true, 'a selection over prose lines only');
eq(E.isProse(sheet, 0, at('x = 3') + 1), false, 'a selection that reaches a calculation');

// --- comments and the off switch ------------------------------------------------
eq(sim('# see a|', '/'), '# see a/|', 'slash is literal in comments');
eq(sim('# a|', '.'), '# a.|', 'period is literal in comments');
eq(sim('# a|', ['\\']), '# a\\|', 'backslash is literal in comments');
eq(sim('# a|', [ctrl('g')]), '# α|', 'Greek still works in comments');
eq(sim('x = a|', '/', { enabled: false }), 'x = a/|', 'switch turns everything off');
eq(sim('x = a|', [ctrl('g')], { enabled: false }), 'x = a|', 'switch turns Greek off too');

// --- only the current line is considered ----------------------------------------
eq(sim('f(x = 1\ny = a|', '/'), 'f(x = 1\ny = a / (|)', 'brackets do not span lines');
eq(sim('# note [\ny = a|', ','), '# note [\ny = a, |', 'an open bracket on another line does not matter');

// --- highlighted text ---------------------------------------------------------
// `a[b]c` marks the highlighted region. press() on a selection: charAction gets (s, e).
function selPress(src, key, ctx = {}) {
  const s = src.indexOf('['), e = src.indexOf(']') - 1;
  const t = src.replace('[', '').replace(']', '');
  const r = typeof key === 'string' && key.length === 1 ? E.charAction(key, t, s, e, ctx)
    : E.keyAction(key.key, { ctrl: !!key.ctrl, alt: !!key.alt, shift: false, meta: false }, t, s, e, ctx);
  if (!r) return null;
  if (r.message) return 'message: ' + r.message;
  if (r.select) return t.slice(0, r.select[0]) + '[' + t.slice(r.select[0], r.select[1]) + ']' + t.slice(r.select[1]);
  const out = t.slice(0, r.from) + r.insert + t.slice(r.to);
  return out.slice(0, r.caret) + '|' + out.slice(r.caret);
}
eq(selPress("x = [a+b]", '('), 'x = (a+b)|', '( wraps the selection');
eq(selPress("x = [a+b]", '['), 'x = [a+b]|', '[ wraps the selection');
eq(selPress("x = [a+b]", '|'), 'x = abs(a+b)|', '| takes the absolute value');
eq(selPress("x = [a+b]", '/'), 'x = (a+b) / (|)', 'fraction over a sum');
eq(selPress("x = [a] + b", '/'), 'x = a / (|) + b', 'fraction over one name');
eq(selPress("x = [a+b]", '^'), 'x = (a+b)^(|)', 'power of a sum');
eq(selPress("x = [a] + b", '^'), 'x = a^(|) + b', 'power of a name');
eq(selPress("x = [a+b]", '\\'), 'x = sqrt(a+b)|', 'radical');
eq(selPress("x = [a+b]", { key: 'm', ctrl: true }), 'x = [a+b]|', 'Ctrl+M wraps in an array');
eq(selPress("x = [A*C]", { key: 't', ctrl: true }), 'x = transpose(A*C)|', 'transpose');

// highlighting only part of a term still means the whole term
eq(selPress("x = 1[2]'kN + a", '/'), "x = 12'kN / (|) + a", 'half a number takes its unit');
eq(selPress("x = 12'[kN] + a", '/'), "x = 12'kN / (|) + a", 'the unit alone takes its number');
eq(selPress("x = 12 '[kN]", '/'), "x = 12 'kN / (|)", 'a space between number and unit');
eq(selPress("x = [1]2'kN", '^'), "x = (12'kN)^(|)", 'a power covers the number as well as its unit');
eq(selPress("x = [x]^2 + y", '/'), 'x = x^2 / (|) + y', 'the base takes its exponent');
eq(selPress("x = x^[2] + y", '/'), 'x = x^2 / (|) + y', 'the exponent takes its base');
eq(selPress("x = x^-[2]", '/'), 'x = x^-2 / (|)', 'a negative exponent takes its base');
eq(selPress("x = [s]in(a) + y", '('), 'x = (sin(a))| + y', 'a function name takes its arguments');
eq(selPress("x = sin[(a)] + y", '('), 'x = (sin(a))| + y', 'brackets take their function name');
eq(selPress("x = f(a, [b)] + y", '/'), 'x = f(a, b) / (|) + y', 'a stray ) pulls in its partner');
eq(selPress("x = [(a + b] + c) * d", '('), 'x = ((a + b + c))| * d', 'a stray ( pulls in its partner');
eq(selPress("x = [ a ] + b", '('), 'x =  (a)|  + b', 'surrounding spaces stay outside the brackets');
eq(selPress("x = ~[g]", '/'), 'x = ~g / (|)', 'global marker is part of the name');
eq(selPress("x = a_[m]ax", '/'), 'x = a_max / (|)', 'subscripts are part of the name');
eq(selPress("x = a [ ] b", '('), null, 'a blank selection is left to the browser');
eq(selPress("x = [a\ny = b]", '('), 'message: Highlight one line or less to wrap it', 'a selection across lines is not overwritten');
eq(selPress("x = [(a + b] + c", '('), 'message: Brackets in the highlight do not match', 'unmatched brackets are not overwritten');
eq(selPress("# [a+b]", '('), null, 'comments are left alone');
eq(selPress("x = [a+b]", '(', { enabled: false }), null, 'switch turns it off');

// wrapping with a function
const wrap = (src, name) => { const s = src.indexOf('['), e = src.indexOf(']') - 1; const t = src.replace('[', '').replace(']', ''); const r = E.wrapWithCall(t, s, e, name); return r && (t.slice(0, r.from) + r.insert + t.slice(r.to)); };
eq(wrap('x = [a+b] * c', 'sin'), 'x = sin(a+b) * c', 'a function applied to the selection');
eq(wrap('x = 1[2]\'m', 'sqrt'), "x = sqrt(12'm)", 'the function takes the whole quantity');

// growing the selection
function growTo(src, times) { // the caret is marked with |
  const caret = src.indexOf('|');
  const t = src.replace('|', '');
  let s = caret, e = caret;
  const seen = [];
  for (let i = 0; i < times; i++) {
    const r = E.keyAction('ArrowUp', { alt: true, ctrl: false, shift: false, meta: false }, t, s, e, {});
    if (!r || !r.select) break;
    [s, e] = r.select; seen.push(t.slice(s, e));
  }
  return seen;
}
assert.deepStrictEqual(growTo("M = w * L^2 / 8 + c|", 9), ['c', 'w * L^2 / 8 + c', 'M = w * L^2 / 8 + c'], 'grow: name, sum, line'); n++;
assert.deepStrictEqual(growTo("M = w * L^|2 / 8 + c", 9), ['L^2', 'w * L^2 / 8', 'w * L^2 / 8 + c', 'M = w * L^2 / 8 + c'], 'grow: power, product, sum, line'); n++;
assert.deepStrictEqual(growTo("x = sin(a + b|) * c", 9), ['b', 'a + b', 'sin(a + b)', 'sin(a + b) * c', 'x = sin(a + b) * c'], 'grow through a call'); n++;
assert.deepStrictEqual(growTo("x = f(a, b|, c)", 9), ['b', 'a, b, c', 'f(a, b, c)', 'x = f(a, b, c)'], 'grow through arguments'); n++;
assert.deepStrictEqual(growTo("x = 12|'kN", 9), ["12'kN", "x = 12'kN"], 'grow over a quantity'); n++;
assert.deepStrictEqual(growTo("x = 1e-|3 + a", 9), ['1e-3', '1e-3 + a', 'x = 1e-3 + a'], 'minus in 1e-3 is not a split'); n++;
assert.deepStrictEqual(growTo("F = [10; 5|] * 'kN", 9), ['5', '10; 5', '[10; 5]', "[10; 5] * 'kN", "F = [10; 5] * 'kN"], 'grow in an array'); n++;
assert.deepStrictEqual(growTo("a = b|", 9), ['b', 'a = b'], 'two sides of ='); n++;
assert.deepStrictEqual(growTo("x = a -> b|", 9), ['b', 'x = a -> b'], 'conversion target'); n++;
eq(E.keyAction('ArrowUp', { alt: true }, '# note', 3, 3, {}), null, 'comments are left alone');
eq(E.keyAction('ArrowUp', { alt: true }, 'x = 1', 0, 5, {}).message, 'Nothing larger to select', 'whole line is the top');

// Text in quotes (props keys and fluids) is not math
eq(E.charAction('-', 'r = props("D", "T", T, "P", p, "1', 33, 33, {}), null, 'a hyphen in a fluid name stays a hyphen');
eq(E.charAction('.', 'r = props("D", "T", T, "P", p, "INCOMP::MEG[0', 44, 44, {}), null, 'a dot stays a dot');
eq(E.charAction('-', 'r = props("D", "T", T', 21, 21, {}) !== null, true, 'outside the quotes it is math again');

// A global typed without its ~ gets one when the name is finished
// the symbol table of the last evaluation (laconic/symbols.py): ~g and ~F! on line 1, ~f on line 2
const glob = (id, name, line, kind = 'variable') => ({ id, name, kind, line, until: null, global: true, value: '', params: [] });
const G = { symbols: [glob(0, 'g', 1), glob(1, 'F!', 1), glob(2, 'f', 2, 'function')] };
eq(sim('~g = 5\nx = g|', ' ', G), '~g = 5\nx = ~g |', 'a space finishes the name');
eq(sim('~g = 5\nx = g|', '*2', G), '~g = 5\nx = ~g * 2|', 'an operator does too, with its usual spacing');
eq(sim('~g = 5\ng|', ' = 3', G), '~g = 5\n~g = 3|', 'assigning a global');
eq(sim('~g = 5\nx = 2*g|', ['Enter'], G), '~g = 5\nx = 2*~g\n|', 'Enter finishes the name');
eq(sim('~g = 5\n~f(x) = x\ny = f|', '(2)', G), '~g = 5\n~f(x) = x\ny = ~f(2)|', 'a global function');
eq(sim('~F! = 1\nx = F!|', ' ', G), '~F! = 1\nx = ~F! |', 'a name with a mark');
eq(sim('~g = 5\nx = gr|', ' ', G), '~g = 5\nx = gr |', 'a longer name is not the global');
eq(sim('~g = 5\nx = g|', '.', G), '~g = 5\nx = g_|', 'a subscript continues the name');
eq(sim('~g = 5\nx = ~g|', ' ', G), '~g = 5\nx = ~g |', 'one ~ is enough');
eq(sim("~g = 5\nx = 2'g|", ' ', G), "~g = 5\nx = 2'g |", 'a unit is not a name');
eq(sim('~g = 5\nh(g|', ')', G), '~g = 5\nh(g)|', 'a function parameter is local');
eq(sim('g|\n~g = 5', ' ', G), 'g |\n~g = 5', 'only below the line that makes it global');
eq(sim('# about g|', ' ', G), '# about g |', 'comments are left alone');
eq(sim('~g = 5\nx = g|', ' ', { ...G, enabled: false }), '~g = 5\nx = g |', 'off with the Math keys');
const r = E.charAction(' ', '~g = 5\nx = g', 12, 12, G);
eq(`${r.from} ${r.to} ${r.insert}`, '11 12 ~g ', 'one edit, so one Ctrl+Z takes it back');

// Edits from the server, all against one text, go in as one edit; the caret stays with its text
function merged(src, edits) {
  const st = start(src), r = E.merge(st.t, edits, st.s);
  if (!r) return null;
  const t = applyEdit(st, r);
  return t.t.slice(0, t.s) + '|' + t.t.slice(t.s);
}
eq(merged('ab|cdef', [{ from: 4, to: 5, insert: 'XY' }]), 'ab|cdXYf', 'caret before the edit stays');
eq(merged('abcd|ef', [{ from: 0, to: 1, insert: '' }, { from: 2, to: 2, insert: '+' }]), 'b+cd|ef', 'caret after edits moves with its text');
eq(merged('abc|def', [{ from: 2, to: 5, insert: 'Z' }]), 'ab|Zf', 'caret inside a replaced part goes to its start');
eq(merged('abc|def', [{ from: 5, to: 6, insert: '!' }, { from: 0, to: 0, insert: '>' }]), '>abc|de!', 'edits in any order');
eq(merged('ab|c', []), null, 'no edits, no change');
eq(merged('ab|c', [{ from: 1, to: 2, insert: 'b' }]), null, 'an edit that changes nothing');
const m = E.merge('a = 1\nb = a\n', [{ from: 0, to: 1, insert: 'c' }, { from: 10, to: 11, insert: 'c' }], 0);
eq(`${m.from} ${m.to} ${JSON.stringify(m.insert)}`, '0 11 "c = 1\\nb = c"', 'one edit over the span the edits cover');

// applyEdits: the server's edits made in the editor, through an adapter that logs how.
function editorOn(text, caret, elsewhere = false) {
  const log = [];
  return {
    log,
    text: () => text, caret: () => caret, elsewhere: () => elsewhere,
    place: (r) => log.push(['place', r.from, r.to, r.insert]),
    apply: (r) => log.push(['apply', r.from, r.to, r.insert]),
  };
}
{
  const ed = editorOn('x = 1', 0);
  deq([E.applyEdits(ed, 'x = 2', [{ from: 4, to: 5, insert: '3' }]), ed.log], [false, []], 'edits for a text that has changed are not made');
  deq([E.applyEdits(ed, 'x = 1', [{ from: 4, to: 5, insert: '3' }]), ed.log], [true, [['apply', 4, 5, '3']]], 'edits for this text join the undo stack');
  ed.log.length = 0;
  deq([E.applyEdits(ed, 'x = 1', [{ from: 4, to: 5, insert: '1' }]), ed.log], [true, []], 'nothing to change is still a success');
  const busy = editorOn('L = 1\nA = L', 0, true);
  E.applyEdits(busy, 'L = 1\nA = L', [{ from: 0, to: 1, insert: 'w' }, { from: 10, to: 11, insert: 'w' }]);
  deq(busy.log, [['place', 0, 11, 'w = 1\nA = w']], 'typing elsewhere: placed without taking the focus, as one edit');
  busy.log.length = 0;
  E.applyEdits(busy, 'L = 1\nA = L', [{ from: 0, to: 1, insert: 'w' }], true);
  deq(busy.log, [['apply', 0, 1, 'w']], 'an edit the user asked for takes the focus wherever it is');
}

// nameAt with text highlighted (the caret cases are in sheettext_vectors.json, checked against the server's lexer).
eq(E.nameAt('F = w * L', 8, 9), 'L', 'a highlighted name');
eq(E.nameAt("F = 12'kN", 6, 9), "'kN", 'a highlighted unit');
eq(E.nameAt('F = w * L', 4, 9), 'w', 'a highlight that is not one name: the name at its start');

// Tab / Shift+Tab: the selection is marked [ ... ], a bare caret |.
function indented(src, out) {
  const s = src.includes('|') ? src.indexOf('|') : src.indexOf('[');
  const e = src.includes('|') ? s : src.indexOf(']') - 1;
  const t = src.replace(/[|[\]]/g, '');
  const r = E.indentLines(t, s, e, out);
  if (r.insert === undefined) return 'unchanged';
  const t2 = t.slice(0, r.from) + r.insert + t.slice(r.to);
  const [a, b] = r.sel;
  return a === b ? t2.slice(0, a) + '|' + t2.slice(a) : t2.slice(0, a) + '[' + t2.slice(a, b) + ']' + t2.slice(b);
}
eq(indented('x = |1', false), '  x = |1', 'Tab indents the whole line, the caret moves with its text');
eq(indented('a = 1\n  x = |1', true), 'a = 1\nx = |1', 'Shift+Tab unindents the line');
eq(indented(' |x = 1', true), '|x = 1', 'Shift+Tab takes one space when that is all there is');
eq(indented('  |  x = 1', true), '|  x = 1', 'a caret inside removed indent goes to the line start');
eq(indented('\tx = |1', true), 'x = |1', 'Shift+Tab takes a leading tab');
eq(indented('x = |1', true), 'unchanged', 'nothing to unindent');
eq(indented('a = [1\n\nb = 2]\nc = 3', false), '  a = [1\n\n  b = 2]\nc = 3', 'every line of a selection, blank lines left alone');
eq(indented('[a = 1\n]b = 2', false), '  [a = 1\n]b = 2', 'a selection ending at a line start leaves that line alone');
eq(indented('  [a = 1\n    b = 2]', true), '[a = 1\n  b = 2]', 'Shift+Tab over several lines');

// --- Enter keeps a block's indent, the same for every block (#137) --------------------------------
for (const head of ['!plot f(x), x = 0 .. 1', '!plot t, s', '!root x, y', '!minimize d', '!maximize q', '!regression a, b', '!symsolve x']) {
  eq(sim(head + '|', ['Enter']), head + '\n  |', `Enter after ${head} indents the new line`);
}
eq(sim('!plot f(x), x = 0 .. 1\n  title: A|', ['Enter']), '!plot f(x), x = 0 .. 1\n  title: A\n  |', 'after a plot option line (prose: math keys off there)');
eq(sim('!plot f(x), x = 0 .. 1\n  xlim: 0 .. 1|', ['Enter', 'Enter']), '!plot f(x), x = 0 .. 1\n  xlim: 0 .. 1\n|', 'Enter on a bare indent leaves the block');
eq(sim('x = 1\n!root x\n  equation: x^2 = 2|', ['Enter']), 'x = 1\n!root x\n  equation: x^2 = 2\n  |', 'after a solver option line');
eq(sim('!root x\n  # a note|', ['Enter']), '!root x\n  # a note\n  |', 'after a comment the block owns');
eq(sim('!regression a\n    data: D|', ['Enter']), '!regression a\n    data: D\n    |', 'the line\'s own indent');
eq(sim('!symsolve x|\n\tequation: x = 1', ['Enter']), '!symsolve x\n\t|\n\tequation: x = 1', 'after the header, the indent of the line under it');
eq(sim('!plot f(x), x = 0 .. 1\n  title: A|', ['Enter'], { enabled: false }), '!plot f(x), x = 0 .. 1\n  title: A\n  |', 'with Math keys off too');
eq(sim('A = [1, 2|]', ['Enter'], { enabled: false }), 'A = [1, 2\n|]', 'which leave other lines to the browser');
eq(sim('!root x\n  equation: f(x|)', ['Enter']), '!root x\n  equation: f(x)\n  |', 'finishing a line of closing brackets keeps the indent');
eq(sim('!plot f(x), x = 0|.. 1', ['Enter']), '!plot f(x), x = 0\n|.. 1', 'splitting a header is an ordinary Enter');
eq(sim('!plot f(x), x = 0 .. 1\n  y = 2|', ['Enter']), '!plot f(x), x = 0 .. 1\n  y = 2\n|', 'a line a plot does not own');
eq(sim('  x = 1|', ['Enter']), '  x = 1\n|', 'an indented line outside any block');
eq(sim('!plot f(x), x = 0 .. 1\n |  title: A', ['Enter']), '!plot f(x), x = 0 .. 1\n \n|  title: A', 'a caret inside the indent');
eq(sim('!root x\n  equation: x = 1\n  |\n  bounds x: 0 .. 1', ['Enter']), '!root x\n  equation: x = 1\n|\n  bounds x: 0 .. 1', 'a bare indent between owned lines');
eq(E.newline('x = 1', 5, 5), null, 'newline: nothing to do outside a block');
eq(E.headerOf('!plotspec grid: off'), null, '!plotspec starts no block');
eq(E.headerOf('!rooted'), null, 'nor a longer word');

console.log(`${n} editing checks passed`);
