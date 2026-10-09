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

// --- Enter at the end of a bracket ----------------------------------------------
eq(sim('A = [1, 2|]', ['Enter']), 'A = [1, 2]\n|', 'Enter finishes the line instead of splitting before ]');
eq(sim('y = f(g(x|))', ['Enter']), 'y = f(g(x))\n|', 'several closers');
eq(sim('y = x^(n+1|)', ['Enter']), 'y = x^(n+1)\n|', 'open slot is left as typed');
eq(sim('y = a|+ b', ['Enter']), 'y = a\n|+ b', 'normal Enter elsewhere splits the line');
eq(sim('# [a|]', ['Enter']), '# [a\n|]', 'comments are left alone');

// --- Greek ----------------------------------------------------------------------
eq(sim('x = a|', [ctrl('g')]), 'x = α|', 'a -> alpha');
eq(sim('x = a|', [ctrl('g'), ctrl('g')]), 'x = a|', 'second Ctrl+G reverts');
eq(sim('x = D|', [ctrl('g')]), 'x = Δ|', 'capital delta');
eq(sim('sigma = s|', [ctrl('g')]), 'sigma = σ|', 'only the preceding character');
eq(sim('x = 5|', [ctrl('g')]), 'x = 5|', 'no mapping, no change');
assert.ok(E.keyAction('g', { ctrl: true }, 'x = 5', 5, 5, {}).message.includes('5')); n++;
eq(sim('x = a|', [ctrl('g')], { greek: { a: 'ȧ' } }), 'x = ȧ|', 'custom table is used');
eq(sim('x = b|', [ctrl('g')], { greek: { a: 'ȧ' } }), 'x = b|', 'custom table replaces the default');

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

console.log(`${n} editing checks passed`);
