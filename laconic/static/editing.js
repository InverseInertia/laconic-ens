/* Math hotkeys for the worksheet editor.
 *
 * Everything here is a pure function: it takes the text and the selection and
 * returns one edit, or null to let the browser handle the key normally.
 * An edit is {from, to, insert, caret}: replace text[from:to] with `insert`
 * and put the caret at `caret` in the new text. Two other results exist:
 * {caretOnly} moves the caret, {message} reports something without editing.
 *
 * The page applies edits; the same functions run under Node for tests.
 */
(function (root) {
  'use strict';

  // Mathcad-style Greek mapping. Capitals that look like Latin letters are left out.
  const DEFAULT_GREEK = {
    a: 'α', b: 'β', g: 'γ', d: 'δ', e: 'ε', z: 'ζ', h: 'η', q: 'θ', i: 'ι', k: 'κ',
    l: 'λ', m: 'μ', n: 'ν', x: 'ξ', o: 'ο', p: 'π', r: 'ρ', s: 'σ', t: 'τ', u: 'υ',
    f: 'φ', c: 'χ', y: 'ψ', w: 'ω',
    G: 'Γ', D: 'Δ', Q: 'Θ', L: 'Λ', X: 'Ξ', P: 'Π', S: 'Σ', F: 'Φ', Y: 'Ψ', W: 'Ω',
  };

  const IDENT_RE = /[\p{L}\p{N}_°]/u;
  const SIMPLE_RE = /^-?[\p{L}\p{N}_.'°][\p{L}\p{N}_.'°^]*$/u;
  const isIdent = (c) => c !== undefined && IDENT_RE.test(c);
  const isTok = (c) => isIdent(c) || c === '.' || c === "'" || c === '~';

  const lineStartOf = (t, p) => t.lastIndexOf('\n', p - 1) + 1;
  const lineEndOf = (t, p) => { const i = t.indexOf('\n', p); return i < 0 ? t.length : i; };
  const isComment = (t, ls) => t.slice(ls, lineEndOf(t, ls)).trimStart().startsWith('#');
  const edit = (from, to, insert, caret) => ({ from, to, insert, caret });

  // ---- bracket helpers (always limited to one line) -----------------------
  function matchBack(t, i, ls) {
    let depth = 0;
    for (let j = i; j >= ls; j--) {
      const c = t[j];
      if (c === ')' || c === ']') depth++;
      else if (c === '(' || c === '[') { depth--; if (depth === 0) return j; }
    }
    return -1;
  }

  function matchFwd(t, i, le) {
    let depth = 0;
    for (let j = i; j < le; j++) {
      const c = t[j];
      if (c === '(' || c === '[') depth++;
      else if (c === ')' || c === ']') { depth--; if (depth === 0) return j; }
    }
    return -1;
  }

  function enclosing(t, pos, ls) {
    let depth = 0;
    for (let j = pos - 1; j >= ls; j--) {
      const c = t[j];
      if (c === ')' || c === ']') depth++;
      else if (c === '(' || c === '[') { if (depth === 0) return c; depth--; }
    }
    return null;
  }

  // ---- terms -----------------------------------------------------------
  // A "term" is one operand: a name, a number with its unit, a call, a bracketed
  // group, optionally followed by exponents. `a*b` is two terms.

  function atomBefore(t, i, ls) {
    if (i <= ls) return i;
    const c = t[i - 1];
    if (c === ')' || c === ']') {
      const o = matchBack(t, i - 1, ls);
      if (o < 0) return i;
      let s = o;
      if (c === ')') while (s > ls && isIdent(t[s - 1])) s--; // f(x), sqrt(x)
      return s;
    }
    if (isTok(c)) {
      let s = i;
      while (s > ls && isTok(t[s - 1])) s--;
      if (t[s] === "'") { // `12 'kN` with a space: pull in the number
        let k = s;
        while (k > ls && t[k - 1] === ' ') k--;
        if (k < s) {
          let n = k;
          while (n > ls && isTok(t[n - 1])) n--;
          if (n < k && /[\d.]/.test(t[n])) s = n;
        }
      }
      return s;
    }
    return i;
  }

  function termBefore(t, pos, ls) {
    let s = atomBefore(t, pos, ls);
    if (s === pos) return pos;
    for (;;) {
      let p = s;
      if (t[p - 1] === '-' && t[p - 2] === '^') p -= 1;
      if (t[p - 1] === '^' && p - 1 > ls) {
        const b = atomBefore(t, p - 1, ls);
        if (b === p - 1) break;
        s = b;
        continue;
      }
      break;
    }
    return s;
  }

  function atomAfter(t, i, le) {
    let j = i;
    if (t[j] === '-') j++;
    if (j >= le) return i;
    const c = t[j];
    let e;
    if (c === '(' || c === '[') {
      const m = matchFwd(t, j, le);
      if (m < 0) return i;
      e = m + 1;
    } else if (isTok(c)) {
      e = j;
      while (e < le && isTok(t[e])) e++;
      if (t[e] === '(') {
        const m = matchFwd(t, e, le);
        if (m >= 0) e = m + 1;
      } else if (/[\d.]/.test(t[j])) { // number, space, unit
        let k = e;
        while (k < le && t[k] === ' ') k++;
        if (k > e && t[k] === "'") { e = k; while (e < le && isTok(t[e])) e++; }
      }
    } else return i;
    return e;
  }

  function termAfter(t, pos, le) {
    let e = atomAfter(t, pos, le);
    if (e === pos) return pos;
    while (t[e] === '^') {
      const e2 = atomAfter(t, e + 1, le);
      if (e2 === e + 1) break;
      e = e2;
    }
    return e;
  }

  // ---- spacing ------------------------------------------------------------
  const startsOperand = new Set(['=', '+', '-', '*', '/', '^', '(', ',', ';', '[', '<', '>']);

  function prevNonSpace(t, pos, ls) {
    let j = pos;
    while (j > ls && t[j - 1] === ' ') j--;
    return j > ls ? t[j - 1] : null;
  }

  // Replace t[from:e] with `op`, one space on each side, without doubling
  // spaces that are already there.
  function spaced(t, from, e, op, ls) {
    const before = t.slice(ls, from);
    const lead = before.trim() === '' || before.endsWith(' ') ? '' : ' ';
    const hasTail = t[e] === ' ';
    return edit(from, e, lead + op + (hasTail ? '' : ' '), from + lead.length + op.length + 1);
  }

  // `+` and `-` are binary after an operand. After an operator, bracket or at the
  // start of a line they are signs, and inside 1e-3 they belong to the number.
  function sign(t, s, e, ls, op) {
    const prev = prevNonSpace(t, s, ls);
    if (prev === null || startsOperand.has(prev)) return null;
    let j = s;
    while (j > ls && isTok(t[j - 1])) j--;
    if (/^\d[\d.]*[eE]$/.test(t.slice(j, s))) return null;
    return spaced(t, s, e, op, ls);
  }

  // ---- individual actions ---------------------------------------------------
  function fraction(t, s, e, ls, le) {
    if (e > s) {
      const sel = t.slice(s, e);
      const num = termBefore(t, e, ls) === s ? sel : '(' + sel + ')';
      const ins = num + ' / ()';
      return edit(s, e, ins, s + ins.length - 1);
    }
    let end = s;
    while (end > ls && t[end - 1] === ' ') end--;      // `a |` still means a
    const st = termBefore(t, end, ls);
    if (st === end) return edit(s, s, '() / ()', s + 1);
    const num = t.slice(st, end);
    const en = termAfter(t, s, le);
    if (en > s) {
      const ins = num + ' / ' + t.slice(s, en);
      return edit(st, en, ins, st + ins.length);
    }
    const ins = num + ' / ()';
    return edit(st, s, ins, st + ins.length - 1);
  }

  function radical(t, s, e) {
    if (e > s) {
      const ins = 'sqrt(' + t.slice(s, e) + ')';
      return edit(s, e, ins, s + ins.length);
    }
    return edit(s, s, 'sqrt()', s + 5);
  }

  function subscript(t, s, e, ls) {
    if (e > s || t[s - 1] === '_') return null;
    let j = s;
    while (j > ls && isIdent(t[j - 1])) j--;
    if (j === s) return null;                  // nothing before the period
    if (/\p{N}/u.test(t[j])) return null;      // part of a number: decimal point
    if (t[j - 1] === "'") return null;         // part of a unit
    return edit(s, s, '_', s + 1);
  }

  function exponent(t, s, e, ls) {
    if (e > s || termBefore(t, s, ls) === s) return null;
    return edit(s, s, '^()', s + 2);
  }

  // Leaving a `^( )` or `/( )` slot. If the content is a single simple term the
  // parentheses are dropped: x^(2) -> x^2.
  function exitSlot(t, pos, ls) {
    if (t[pos] !== ')') return null;
    const o = matchBack(t, pos, ls);
    if (o < 1) return null;
    const afterSlash = t[o - 1] === ' ' && t[o - 2] === '/';
    if (t[o - 1] !== '^' && t[o - 1] !== '/' && !afterSlash) return null;
    const content = t.slice(o + 1, pos);
    if (!SIMPLE_RE.test(content)) return null;
    return edit(o, pos + 1, content, o + content.length);
  }

  function transpose(t, s, e, ls) {
    let from, to;
    if (e > s) { from = s; to = e; } else {
      from = termBefore(t, s, ls);
      to = s;
      if (from === s) return null;
    }
    const term = t.slice(from, to);
    if (term.startsWith('transpose(') && matchFwd(term, 9, term.length) === term.length - 1) {
      const inner = term.slice(10, -1);
      return edit(from, to, inner, from + inner.length);
    }
    const ins = 'transpose(' + term + ')';
    return edit(from, to, ins, from + ins.length);
  }

  function greek(t, s, e, table) {
    const ch = t[e - 1];
    if (!ch || e === 0) return { message: 'Nothing before the caret to convert' };
    if (table[ch]) return edit(e - 1, e, table[ch], e - 1 + table[ch].length);
    const back = Object.keys(table).find((k) => table[k] === ch);
    if (back) return edit(e - 1, e, back, e);
    return { message: `No Greek mapping for "${ch}"` };
  }

  function backspace(t, s, e, ls, le) {
    if (e > s) return null;
    // `, ` or `; ` right before the caret goes in one press: the separator and the
    // space that was added after it.
    if (t[s - 1] === ' ' && (t[s - 2] === ',' || t[s - 2] === ';') && s - 2 >= ls) {
      return edit(s - 2, s, '', s - 2);
    }
    // ` = `, ` + `, ` -> ` and friends: undo a spaced operator in one press.
    // Mid-line, the space in front is kept so the two terms do not fuse.
    const m = / (->|\.\*|\.\/|[=+*\/-]) $/.exec(t.slice(ls, s));
    if (m) {
      const start = ls + m.index;
      const tail = t.slice(s, le);
      return tail === '' || /^[)\]]/.test(tail) ? edit(start, s, '', start) : edit(start + 1, s, '', start + 1);
    }
    const a = t[s - 1], b = t[s];
    if (!((a === '(' && b === ')') || (a === '[' && b === ']'))) return null;
    let from = s - 1;
    if (a === '(') {
      const before = t.slice(ls, s - 1);
      if (before.endsWith('sqrt')) from = s - 5;
      else if (before.endsWith(' / ')) from = s - 4;
      else if (before.endsWith('^') || before.endsWith('/')) from = s - 2;
    }
    return edit(from, s + 1, '', from);
  }

  // ---- entry points -------------------------------------------------------
  // Printable characters (call from `beforeinput`).
  function charAction(ch, t, s, e, ctx) {
    if (ctx && ctx.enabled === false) return null;
    const ls = lineStartOf(t, s), le = lineEndOf(t, e);
    if (isComment(t, ls)) return null;
    const sel = e > s;
    switch (ch) {
      case '/': // after `A.` the period became a subscript underscore; `A_/` means `A ./ `
        if (!sel && t[s - 1] === '_' && isIdent(t[s - 2])) return spaced(t, s - 1, e, './', ls);
        return fraction(t, s, e, ls, le);
      case '\\': return radical(t, s, e);
      case '.': return subscript(t, s, e, ls);
      case '^': return exponent(t, s, e, ls);
      case ',':
      case ';': // always followed by one space; step over a space that is already there
        return t[e] === ' ' ? edit(s, e, ch, s + 2) : edit(s, e, ch + ' ', s + 2);
      case '*': // a. then * means the elementwise operator .*
        return !sel && t[s - 1] === '_' && isIdent(t[s - 2]) ? spaced(t, s - 1, e, '.*', ls) : spaced(t, s, e, '*', ls);
      case '=': return spaced(t, s, e, '=', ls);
      case '+': return sign(t, s, e, ls, '+');
      case '-': return sign(t, s, e, ls, '-');
      case '>': // `a - ` followed by > is the conversion arrow
        return !sel && t.slice(s - 3, s) === ' - ' ? edit(s - 2, s, '-> ', s + 1) : null;
      case ' ': // never two spaces in a row, except in indentation
        if (sel || t.slice(ls, s).trim() === '') return null;
        if (t[s - 1] === ' ') return { caretOnly: s };
        if (t[s] === ' ') return { caretOnly: s + 1 };
        return null;
      case ')':
      case ']':
        if (sel || t[s] !== ch || matchBack(t, s, ls) < 0) return null;
        return exitSlot(t, s, ls) || { caretOnly: s + 1 };
      default: return null;
    }
  }

  // Control and navigation keys (call from `keydown`). `mods` = {ctrl, alt, shift, meta}.
  function keyAction(key, mods, t, s, e, ctx) {
    if (ctx && ctx.enabled === false) return null;
    const ls = lineStartOf(t, s), le = lineEndOf(t, e);
    const comment = isComment(t, ls);
    const k = key.length === 1 ? key.toLowerCase() : key;
    const plain = !mods.ctrl && !mods.alt && !mods.shift && !mods.meta;

    if (mods.ctrl && !mods.alt && !mods.shift && !mods.meta) {
      if (k === 'g') return greek(t, s, e, (ctx && ctx.greek) || DEFAULT_GREEK);
      if (comment) return null;
      if (k === 'm') return e > s ? edit(s, e, '[' + t.slice(s, e) + ']', e + 2) : edit(s, s, '[]', s + 1);
      if (k === 't') return transpose(t, s, e, ls);
      if (key === '/') {
        return t[s - 1] === '_' && isIdent(t[s - 2]) && e === s ? spaced(t, s - 1, e, './', ls) : spaced(t, s, e, '/', ls);
      }
      if (key === '\\') return edit(s, e, '\\', s + 1);
    }
    // Ctrl+T is reserved by most browsers, so Alt+T does the same thing.
    if (mods.alt && !mods.ctrl && !mods.shift && !mods.meta && k === 't' && !comment) {
      return transpose(t, s, e, ls);
    }
    // Enter with only closing brackets left on the line finishes the line, so the
    // `]` that Ctrl+M added is not stranded on the next line.
    if (plain && !comment && key === 'Enter' && e === s && /^[)\]]+$/.test(t.slice(s, le))) {
      return edit(le, le, '\n', le + 1);
    }
    if (plain && !comment) {
      if (key === 'ArrowRight' && e === s) return exitSlot(t, s, ls);
      if (key === 'Backspace') return backspace(t, s, e, ls, le);
    }
    return null;
  }

  const api = {
    DEFAULT_GREEK, charAction, keyAction,
    termBefore, termAfter, matchBack, matchFwd, enclosing,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Editing = api;
})(typeof window !== 'undefined' ? window : globalThis);
