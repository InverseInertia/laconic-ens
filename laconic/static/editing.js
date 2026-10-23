/* Math hotkeys for the worksheet editor.
 *
 * Everything here is a pure function: it takes the text and the selection and
 * returns one edit, or null to let the browser handle the key normally.
 * An edit is {from, to, insert, caret}: replace text[from:to] with `insert`
 * and put the caret at `caret` in the new text. Two other results exist:
 * {caretOnly} moves the caret, {select: [from, to]} changes the selection and
 * {message} reports something without editing.
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
  // Lines that hold text and not math: comments, and the title, label and note text under a plot.
  const TEXT_OPTION = /^\s+(title|xlabel|ylabel|label|note)(\s+\d+)?\s*:/;
  const isComment = (t, ls) => {
    const line = t.slice(ls, lineEndOf(t, ls));
    return line.trimStart().startsWith('#') || TEXT_OPTION.test(line);
  };
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

  // ---- selections ---------------------------------------------------------
  // Whatever the user highlights, the edit applies to whole terms: `1` inside
  // `12'kN` means the quantity, `x` in `x^2` means the power, half a bracket
  // pair means the pair, and a function name means the call.

  function openBefore(t, pos, ls) {
    let depth = 0;
    for (let j = pos - 1; j >= ls; j--) {
      const c = t[j];
      if (c === ')' || c === ']') depth++;
      else if (c === '(' || c === '[') { if (depth === 0) return j; depth--; }
    }
    return -1;
  }

  function tokenStart(t, e, ls) {
    let s = e;
    while (s > ls && isTok(t[s - 1])) s--;
    return s;
  }

  // The smallest run of whole terms that covers [s, e), or null when there is
  // nothing to select (blank, or more than one line).
  function snap(t, s, e) {
    const ls = lineStartOf(t, s), le = lineEndOf(t, s);
    while (s < e && t[s] === ' ') s++;
    while (e > s && t[e - 1] === ' ') e--;
    if (e <= s || e > le) return null;
    for (let n = 0; n < 24; n++) {
      const s0 = s, e0 = e;
      // unbalanced brackets: pull in the partner
      let open = 0, stray = 0;
      for (let j = s; j < e; j++) {
        const c = t[j];
        if (c === '(' || c === '[') open++;
        else if (c === ')' || c === ']') { if (open > 0) open--; else stray++; }
      }
      if (stray) {
        let need = stray, j = s - 1;
        for (; j >= ls && need > 0; j--) {
          if (t[j] === ')' || t[j] === ']') need++;
          else if (t[j] === '(' || t[j] === '[') need--;
        }
        if (need > 0) return null;
        s = j + 1;
      }
      if (open) {
        let need = open, j = e;
        for (; j < le && need > 0; j++) {
          if (t[j] === '(' || t[j] === '[') need++;
          else if (t[j] === ')' || t[j] === ']') need--;
        }
        if (need > 0) return null;
        e = j;
      }
      // a cut through the middle of a name, number or unit
      while (s > ls && isTok(t[s - 1]) && isTok(t[s])) s--;
      while (e < le && isTok(t[e - 1]) && isTok(t[e])) e++;
      // 1e-3 is one number
      if (/^[+-]$/.test(t[s - 1] || '')) {
        const ts = tokenStart(t, s - 1, ls);
        if (/^\d[\d.]*[eE]$/.test(t.slice(ts, s - 1))) s = ts;
      }
      if (/^[+-]$/.test(t[e] || '') && /\d/.test(t[e + 1] || '') && /^\d[\d.]*[eE]$/.test(t.slice(tokenStart(t, e, ls), e))) {
        e++;
        while (e < le && isTok(t[e])) e++;
      }
      // `12 'kN`: number and unit are one term even with a space between
      if (isTok(t[e - 1])) {
        const ts = tokenStart(t, e, ls);
        let k = e;
        while (k < le && t[k] === ' ') k++;
        if (k > e && t[k] === "'" && /[\d.]/.test(t[ts])) { e = k; while (e < le && isTok(t[e])) e++; }
      }
      if (t[s] === "'") {
        let k = s;
        while (k > ls && t[k - 1] === ' ') k--;
        if (k < s && isTok(t[k - 1])) {
          const ts = tokenStart(t, k, ls);
          if (/[\d.]/.test(t[ts])) s = ts;
        }
      }
      // a function: name and arguments go together
      if (t[e] === '(' && isIdent(t[e - 1])) { const m = matchFwd(t, e, le); if (m >= 0) e = m + 1; }
      if (t[s] === '(' && s > ls && isIdent(t[s - 1])) while (s > ls && isIdent(t[s - 1])) s--;
      // exponents belong to their base: x|^2 and x^|2 both mean x^2
      while (t[e] === '^') {
        const e2 = atomAfter(t, e + 1, le);
        if (e2 <= e + 1) break;
        e = e2;
      }
      const hat = t[s - 1] === '^' ? s - 1 : t[s - 1] === '-' && t[s - 2] === '^' ? s - 2 : -1;
      if (hat > ls) { const b = termBefore(t, hat, ls); if (b < hat) s = b; }
      if (s === s0 && e === e0) break;
    }
    return [s, e];
  }

  // Split points at bracket depth 0 inside [a, b): level 1 is a binary + or -,
  // level 2 is , ; = and ->. A product lies between any two; a sum between level 2 ones.
  function splits(t, a, b) {
    const out = [];
    let depth = 0;
    for (let j = a; j < b; j++) {
      const c = t[j];
      if (c === '(' || c === '[') depth++;
      else if (c === ')' || c === ']') depth--;
      else if (depth === 0) {
        if (c === ',' || c === ';' || c === '=') out.push({ i: j, end: j + 1, level: 2 });
        else if (c === '-' && t[j + 1] === '>') { out.push({ i: j, end: j + 2, level: 2 }); j++; }
        else if (c === '+' || c === '-') {
          const prev = prevNonSpace(t, j, a);
          let k = j;
          while (k > a && isTok(t[k - 1])) k--;
          if (prev !== null && !startsOperand.has(prev) && !/^\d[\d.]*[eE]$/.test(t.slice(k, j))) {
            out.push({ i: j, end: j + 1, level: 1 });
          }
        }
      }
    }
    return out;
  }

  const trimmed = (t, a, b) => {
    while (a < b && t[a] === ' ') a++;
    while (b > a && t[b - 1] === ' ') b--;
    return [a, b];
  };
  const grows = (r, s, e) => r[0] <= s && r[1] >= e && (r[0] < s || r[1] > e);

  // The next larger meaningful selection: term, product, sum, bracket contents,
  // bracket, then outwards, ending at the whole line. null when there is none.
  function grow(t, s, e) {
    const ls = lineStartOf(t, s), le = lineEndOf(t, s);
    if (e > le) return null;
    if (e > s) {
      const n = snap(t, s, e);
      if (n && (n[0] !== s || n[1] !== e)) return n;
      if (n) { s = n[0]; e = n[1]; }
    } else {
      let a = -1;
      if (s < le && (isTok(t[s]) || t[s] === '(' || t[s] === '[')) a = s;
      else if (s > ls && (isTok(t[s - 1]) || t[s - 1] === ')' || t[s - 1] === ']')) a = s - 1;
      if (a >= 0) { const n = snap(t, a, a + 1); if (n) return n; }
    }
    const contexts = [];
    for (let pos = s; ;) {
      const o = openBefore(t, pos, ls);
      if (o < 0) break;
      const c = matchFwd(t, o, le);
      if (c < e) break;
      contexts.push({ o, c });
      pos = o;
    }
    contexts.push(null);
    for (const ctx of contexts) {
      const [a, b] = ctx ? trimmed(t, ctx.o + 1, ctx.c) : trimmed(t, ls, le);
      const seps = splits(t, a, b);
      // first the run of operands between any split (a product), then between , ; = -> only (a sum)
      for (const minLevel of [1, 2]) {
        if (seps.some((x) => x.level >= minLevel && x.i >= s && x.end <= e)) continue; // the selection spans one
        let left = a, right = b;
        for (const x of seps) {
          if (x.level < minLevel) continue;
          if (x.end <= s) left = x.end;
          else if (x.i >= e) { right = x.i; break; }
        }
        const r = trimmed(t, left, right);
        if (grows(r, s, e)) return r;
      }
      if (grows([a, b], s, e)) return [a, b];
      if (ctx) {
        let from = ctx.o;
        if (t[from] === '(') while (from > ls && isIdent(t[from - 1])) from--;
        if (grows([from, ctx.c + 1], s, e)) return [from, ctx.c + 1];
      }
    }
    return null;
  }

  // A base for ^ that keeps its meaning: a bare name or number stays as it is,
  // anything else gets brackets. `12'kN` is bracketed so the power covers the
  // number as well as the unit.
  function asBase(t, s, e, ls) {
    const sel = t.slice(s, e);
    const single = termBefore(t, e, ls) === s;
    return single && (!sel.includes("'") || sel[0] === "'") ? sel : '(' + sel + ')';
  }

  // name(selection): wraps whole terms in a call and leaves the caret after it.
  function wrapWithCall(t, s, e, name) {
    const n = snap(t, s, e);
    if (!n) return null;
    const ins = name + '(' + t.slice(n[0], n[1]) + ')';
    return edit(n[0], n[1], ins, n[0] + ins.length);
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
    if (e > s) { const ins = asBase(t, s, e, ls) + '^()'; return edit(s, e, ins, s + ins.length - 1); }
    if (termBefore(t, s, ls) === s) return null;
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

  // The term a hotkey acts on: the (widened) selection, or the term left of the caret.
  function targetTerm(t, s, e, ls) {
    if (e > s) return snap(t, s, e);
    const from = termBefore(t, s, ls);
    return from === s ? null : [from, s];
  }

  // idx(term, ) or elem(term, ): the term becomes the array and the caret waits for the index.
  // For elem, typing `i,` adds the space and the caret moves on to the column.
  function indexCall(t, s, e, ls, name) {
    const n = targetTerm(t, s, e, ls);
    if (!n) return null;
    const head = name + '(' + t.slice(n[0], n[1]) + ', ';
    return edit(n[0], n[1], head + ')', n[0] + head.length);
  }

  function transpose(t, s, e, ls) {
    const n = targetTerm(t, s, e, ls);
    if (!n) return null;
    const [from, to] = n;
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

  // Keys that wrap a highlighted region instead of replacing it.
  const WRAPPERS = new Set(['/', '\\', '^', '(', '[', '|']);

  // ---- entry points -------------------------------------------------------
  // Printable characters (call from `beforeinput`).
  function charAction(ch, t, s, e, ctx) {
    if (ctx && ctx.enabled === false) return null;
    const ls = lineStartOf(t, s), le = lineEndOf(t, e);
    if (isComment(t, ls)) return null;
    // Inside quotes (a props() key or fluid such as "1-Butene") the text is not math.
    if (((t.slice(ls, s).match(/"/g) || []).length % 2) === 1) return null;
    if (e > s && WRAPPERS.has(ch)) {
      const n = snap(t, s, e); // act on whole terms, however the text was highlighted
      if (!n) {
        if (t.slice(s, e).trim() === '') return null; // spaces: an ordinary replace
        // Do not let a stray key overwrite several lines or half a bracket pair.
        return { message: t.slice(s, e).includes('\n') ? 'Highlight one line or less to wrap it' : 'Brackets in the highlight do not match' };
      }
      [s, e] = n;
      if (ch === '(' || ch === '[') return edit(s, e, ch + t.slice(s, e) + (ch === '(' ? ')' : ']'), e + 2);
      if (ch === '|') { const ins = 'abs(' + t.slice(s, e) + ')'; return edit(s, e, ins, s + ins.length); }
    }
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

    // Ctrl+[ takes the term as an array and opens one index: idx(A, i), shown A_i.
    // Ctrl+Shift+[ opens row and column: elem(A, i, j), shown A_i,j.
    if (mods.ctrl && !mods.alt && !mods.meta && !comment && (key === '[' || key === '{')) {
      return mods.shift || key === '{' ? indexCall(t, s, e, ls, 'elem') : indexCall(t, s, e, ls, 'idx');
    }
    if (mods.ctrl && !mods.alt && !mods.shift && !mods.meta) {
      if (k === 'g') return greek(t, s, e, (ctx && ctx.greek) || DEFAULT_GREEK);
      if (comment) return null;
      if (k === 'm') {
        if (e === s) return edit(s, s, '[]', s + 1);
        const n = snap(t, s, e);
        return n ? edit(n[0], n[1], '[' + t.slice(n[0], n[1]) + ']', n[1] + 2) : null;
      }
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
    // Alt+Up grows the selection by one term-aware step (Alt+Down, in the page, undoes a step).
    if (mods.alt && !mods.ctrl && !mods.shift && !mods.meta && key === 'ArrowUp' && !comment) {
      const g = grow(t, s, e);
      return g ? { select: g } : { message: 'Nothing larger to select' };
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
    snap, grow, wrapWithCall,
    isTextLine: isComment,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Editing = api;
})(typeof window !== 'undefined' ? window : globalThis);
