/* Math hotkeys for the worksheet editor.
 *
 * Everything here is a pure function: it takes the text and the selection and
 * returns one edit, or null to let the browser handle the key normally.
 * An edit is {from, to, insert, caret}: replace text[from:to] with `insert`
 * and put the caret at `caret` in the new text. Two other results exist:
 * {caretOnly} moves the caret, {select: [from, to]} changes the selection and
 * {message} reports something without editing.
 *
 * `merge` turns the edits the server sends (a plot view, a stored solver result, a rename)
 * into one such edit, and `applyEdits` makes them in the editor through an adapter:
 *   editor.text(), editor.caret()   the editor's text and caret
 *   editor.elsewhere()              the user is typing in another field (a dialog, the name box)
 *   editor.place(r)                 make edit r without taking the focus or joining the undo stack
 *   editor.apply(r)                 make edit r in the editor's undo stack
 * `nameAt` is the name or unit the rename dialog starts with (F2). `headerOf` and `blockAt` read
 * the blocks (`!plot`, `!root`, ...) as laconic/sheettext.py does, and `newline` is what Enter does
 * in one: the new line keeps the block's indent, with or without Math keys.
 *
 * The page applies edits; the same functions run under Node for tests.
 */
(function (root) {
  'use strict';
  const Symbols = typeof module !== 'undefined' && module.exports ? require('./symbols.js') : root.Symbols;

  // Mathcad-style Greek mapping. Capitals that look like Latin letters are left out.
  // 8 -> ∞ and V -> ∀ ride along: the free-stream subscript, and the struck-through V some fluid
  // mechanics texts use for volume.
  const DEFAULT_GREEK = {
    a: 'α', b: 'β', g: 'γ', d: 'δ', e: 'ε', z: 'ζ', h: 'η', q: 'θ', i: 'ι', k: 'κ',
    l: 'λ', m: 'μ', n: 'ν', x: 'ξ', o: 'ο', p: 'π', r: 'ρ', s: 'σ', t: 'τ', u: 'υ',
    f: 'φ', c: 'χ', y: 'ψ', w: 'ω',
    G: 'Γ', D: 'Δ', Q: 'Θ', L: 'Λ', X: 'Ξ', P: 'Π', S: 'Σ', F: 'Φ', Y: 'Ψ', W: 'Ω',
    8: '∞', V: '∀',
  };

  const IDENT_RE = /[\p{L}\p{N}_°∞∀]/u;   // ∞ for subscripts such as v_∞, ∀ for volume
  const SIMPLE_RE = /^-?[\p{L}\p{N}_.'°][\p{L}\p{N}_.'°%^]*$/u;
  const isIdent = (c) => c !== undefined && IDENT_RE.test(c);
  // % appears only in the unit '%, so it belongs to the term like a unit's letters; $ only in front
  // of a symbol being declared ($x), so it belongs to that name like a global's ~.
  const isTok = (c) => isIdent(c) || c === '.' || c === "'" || c === '~' || c === '$' || c === '%';

  // The worksheet lexer, the same as laconic/sheettext.py (tests/sheettext_vectors.json holds
  // them together): quoted text, units, numbers and names. Python's \w is Unicode, so the
  // classes are spelled out here.
  const W = '[\\p{L}\\p{N}_∀]', W0 = '[\\p{L}\\p{Nl}\\p{No}_∀]';
  const TOKEN_RE = new RegExp('("[^"\\n]*")' + `|('(?:(?:${W0}|°)(?:${W}|°)*|%))`
    + '|((?:\\p{Nd}+(?:\\.\\p{Nd}+)?|\\.\\p{Nd}+)(?:[eE][+-]?\\p{Nd}+)?' + `(?:[ij](?!${W}))?)` + `|(~?\\$?${W0}(?:_∞|${W})*[\`!@&]*)`, 'gu');
  const KINDS = ['text', 'unit', 'num', 'name'];
  // The tokens of one line: [{kind, start, text}], left to right.
  function tokens(line) {
    return [...line.matchAll(TOKEN_RE)].map((m) => ({ kind: KINDS[m.slice(1).findIndex((g) => g !== undefined)], start: m.index, text: m[0] }));
  }

  const lineStartOf = (t, p) => t.lastIndexOf('\n', p - 1) + 1;
  const lineEndOf = (t, p) => { const i = t.indexOf('\n', p); return i < 0 ? t.length : i; };
  // Where the text is prose, not math: outside laconic/sheettext.py's expression spans, as
  // tests/sheettext_vectors.json holds them together. Comment lines; under a plot, a title or label
  // and a note's text (its `at (x, y)` is math); under a solver, the method.
  const TEXT_OPTION = /^[ \t]+(title|xlabel|ylabel|label|note|method)(?:[ \t]+[^\s:]+)?[ \t]*:/;
  function isTextAt(t, p) {
    const ls = lineStartOf(t, p), line = t.slice(ls, lineEndOf(t, p));
    if (line.trimStart().startsWith('#')) return true;
    const m = TEXT_OPTION.exec(line);
    if (!m) return false;
    if (m[1] !== 'note') return true;
    const at = /"\s+at\s*\(/.exec(line), close = line.lastIndexOf(')');
    const from = at ? at.index + at[0].length : -1;
    return !(at && close > from && p - ls >= from && p - ls <= close);
  }
  // The browser may spellcheck the selection's lines when every one is prose: a comment or heading
  // (not a `#@` line LENS writes), or a plot's title, label or note. A solver's `method:` is a
  // name, not prose. The editor is one textarea, so its spellcheck follows the caret's lines.
  function isProse(t, s, e) {
    for (let ls = lineStartOf(t, s); ; ls = lineEndOf(t, ls) + 1) {
      const line = t.slice(ls, lineEndOf(t, ls)), m = TEXT_OPTION.exec(line), head = line.trimStart();
      if (!(head.startsWith('#') ? !head.startsWith('#@') : m && m[1] !== 'method')) return false;
      if (lineEndOf(t, ls) >= (e === undefined ? s : e)) return true;
    }
  }
  const edit = (from, to, insert, caret) => ({ from, to, insert, caret });

  // ---- blocks --------------------------------------------------------------
  // A block header (laconic/sheettext.py): `!plot ...` or a solver's `!root x, y` (also `!minimize`,
  // `!maximize`, `!regression`, `!symsolve`). headerOf(line) -> {kind, unknowns} or null, where
  // kind is the command, and a plot names no unknowns.
  const PLOT_HEAD = /^[ \t]*!plot[ \t]+\S/;
  const SOLVER_HEAD = /^[ \t]*!(root|minimize|maximize|regression|symsolve)(?:[ \t]+(.*?))?[ \t]*$/;
  const PLOT_OPT = /^[ \t]+[A-Za-z]\w*(?:[ \t]+\d+)?[ \t]*:/;
  function headerOf(line) {
    if (PLOT_HEAD.test(line)) return { kind: 'plot', unknowns: [] };
    const m = SOLVER_HEAD.exec(line);
    return m ? { kind: m[1], unknowns: (m[2] || '').split(',').map((x) => x.trim()).filter(Boolean) } : null;
  }
  // The block that the line starting at `ls` belongs to, as headerOf gives it, or null. A plot owns
  // the `key: value` lines indented under it; a solver block every indented, non-blank line. The line
  // being typed counts while it could still become one: only its indent, or the start of a key.
  function blockAt(t, ls) {
    const line = t.slice(ls, lineEndOf(t, ls));
    if (!/^[ \t]/.test(line)) return null;
    let plotty = PLOT_OPT.test(line) || /^[ \t]+(?:[A-Za-z]\w*(?:[ \t]+\d*)?)?$/.test(line);
    for (let p = ls; p > 0;) {
      const ps = lineStartOf(t, p - 1), l = t.slice(ps, p - 1);
      const h = headerOf(l);
      if (h) return h.kind === 'plot' && !plotty ? null : h;
      if (!/^[ \t]+\S/.test(l)) return null;
      plotty = plotty && PLOT_OPT.test(l);
      p = ps;
    }
    return null;
  }

  // Enter keeps a block going: after a block header, the new line takes the block's indent (that of
  // the line under the header, or two spaces); on an owned line, that line's indent. On a line that
  // is only its indent, Enter takes the indent away instead, leaving the block. Null elsewhere.
  function newline(t, s, e) {
    const ls = lineStartOf(t, s), le = lineEndOf(t, e), line = t.slice(ls, lineEndOf(t, s));
    const nl = (indent) => edit(s, e, '\n' + indent, s + 1 + indent.length);
    if (headerOf(line)) {
      if (t.slice(e, le).trim() !== '') return null;      // splitting a header: an ordinary new line
      const next = /^[ \t]+(?=\S)/.exec(le < t.length ? t.slice(le + 1, lineEndOf(t, le + 1)) : '');
      return nl(next ? next[0] : '  ');
    }
    const indent = /^[ \t]*/.exec(line)[0];
    if (!indent || s - ls < indent.length || !blockAt(t, ls)) return null;
    if (line.trim() === '' && s === e && s === le) return edit(ls, le, '', ls);
    return nl(indent);
  }

  // Two edits, `b` made on the text `a` left, as one edit on `t`, with b's caret.
  function chain(t, a, b) {
    const grow = a.insert.length - (a.to - a.from);
    const from = Math.min(a.from, b.from), end = Math.max(a.from + a.insert.length, b.to);
    const t2 = t.slice(0, a.from) + a.insert + t.slice(a.to);
    const t3 = t2.slice(0, b.from) + b.insert + t2.slice(b.to);
    return edit(from, end - grow, t3.slice(from, end + b.insert.length - (b.to - b.from)), b.caret);
  }

  // The server's edits (laconic/blockedit.py), all against `t` and not overlapping, as one edit
  // over the span they cover, so one Ctrl+Z takes back all of them. The caret stays with the text
  // it was in; inside text an edit replaced, it goes to where that edit starts. Null if nothing changes.
  function merge(t, edits, caret) {
    const es = [...edits].sort((a, b) => a.from - b.from);
    if (!es.length) return null;
    const from = es[0].from, to = es[es.length - 1].to;
    let insert = '', pos = from, moved = caret, grow = 0;
    for (const e of es) {
      insert += t.slice(pos, e.from) + e.insert;
      pos = e.to;
      if (caret >= e.to) moved = caret + grow + e.insert.length - (e.to - e.from);
      else if (caret > e.from) moved = e.from + grow;
      grow += e.insert.length - (e.to - e.from);
    }
    if (insert === t.slice(from, to)) return null;
    return edit(from, to, insert, moved);
  }

  // The server's edits against `base`, made in the editor as one edit, so one Ctrl+Z takes them
  // back. If the text changed while the server was working, the edits no longer fit: nothing is
  // made and this says false. An edit made while the user types somewhere else does not take the
  // focus, unless `asked` (an edit the user asked for in a dialog, such as a rename).
  function applyEdits(editor, base, edits, asked = false) {
    if (editor.text() !== base) return false;
    const r = merge(base, edits, editor.caret());
    if (!r) return true;
    if (!asked && editor.elsewhere()) editor.place(r);
    else editor.apply(r);
    return true;
  }

  // The name or unit at the selection, as the server's lexer reads it: the highlighted text when
  // it is one whole name or unit, else the one the caret is in or next to. "" on a comment line,
  // or where there is none.
  function nameAt(t, s, e) {
    const named = (tok) => tok.kind === 'name' || tok.kind === 'unit';
    const sel = t.slice(s, e);
    const whole = tokens(sel);
    if (sel && whole.length === 1 && whole[0].text === sel && named(whole[0])) return sel;
    const ls = lineStartOf(t, s), line = t.slice(ls, lineEndOf(t, s));
    if (line.trimStart().startsWith('#')) return '';
    const at = tokens(line).filter(named).find((tok) => s - ls >= tok.start && s - ls <= tok.start + tok.text.length);
    return at ? at.text : '';
  }

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

  // ---- globals -----------------------------------------------------------
  // A global is written with its ~ every time, so a plain one is a slip (the sheet warns when
  // one is assigned). When a name is finished, by typing something that cannot continue it, and
  // it is a global the line can see, the ~ goes in front. ctx.symbols is the last symbol table (symbols.js).
  const MARKS = '`!@&';
  const FUNC_HEAD = /^\s*~?[\p{L}_∀][\p{L}\p{N}_∀]*[`!@&]*\s*\([^)]*$/u;
  function globalStart(t, s, ctx) {
    const symbols = ctx && ctx.symbols;
    if (!symbols || !symbols.length || isIdent(t[s]) || MARKS.includes(t[s] || ' ')) return -1;
    const ls = lineStartOf(t, s);
    let a = s;
    while (a > ls && MARKS.includes(t[a - 1])) a--;
    const end = a;
    while (a > ls && isIdent(t[a - 1])) a--;
    if (a === end || !/[\p{L}_∀]/u.test(t[a])) return -1;               // no name, or a number such as 1e5
    if (a > ls && "~'.!$".includes(t[a - 1])) return -1;               // has its ~, a unit, after a point, a command, a symbol's $
    if (FUNC_HEAD.test(t.slice(ls, a))) return -1;                      // a function's own parameters
    const name = t.slice(a, s), line = t.slice(0, s).split('\n').length;
    return Symbols.visible(symbols, line).some((g) => g.global && g.name === name) ? a : -1;
  }
  // Runs `base` on the text with the ~ added, then returns the whole change as one edit on `t`,
  // so a single Ctrl+Z takes back both. `typed` is what the browser would insert if `base` does nothing.
  function withTilde(t, s, g, typed, base) {
    const tilde = edit(g, g, '~', s + 1), r = base(t.slice(0, g) + '~' + t.slice(g), s + 1);
    if (!r || (r.insert === undefined && r.caretOnly === undefined)) return chain(t, tilde, edit(s + 1, s + 1, typed, s + 1 + typed.length));
    if (r.insert !== undefined) return chain(t, tilde, r);
    return chain(t, tilde, edit(r.caretOnly, r.caretOnly, '', r.caretOnly));
  }
  const plainCtx = (ctx) => ({ ...ctx, symbols: null });

  // Keys that wrap a highlighted region instead of replacing it.
  const WRAPPERS = new Set(['/', '\\', '^', '(', '[', '|']);

  // ---- entry points -------------------------------------------------------
  // Printable characters (call from `beforeinput`).
  function charAction(ch, t, s, e, ctx) {
    if (ctx && ctx.enabled === false) return null;
    const ls = lineStartOf(t, s), le = lineEndOf(t, e);
    if (isTextAt(t, s)) return null;
    // Inside quotes (a props() key or fluid such as "1-Butene") the text is not math.
    if (((t.slice(ls, s).match(/"/g) || []).length % 2) === 1) return null;
    const g = e === s && !isTok(ch) && !MARKS.includes(ch) ? globalStart(t, s, ctx) : -1;
    if (g >= 0) return withTilde(t, s, g, ch, (t2, s2) => charAction(ch, t2, s2, s2, plainCtx(ctx)));
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

  // Tab and Shift+Tab: indent or unindent every line the caret or selection touches by one block
  // indent (two spaces). A selection ending at the start of a line leaves that line alone, and
  // blank lines in a multi-line selection are not indented. Unindenting takes up to two leading
  // spaces, or one tab. The selection stays on the same text; `sel` is the selection afterwards.
  function indentLines(t, s, e, out) {
    const ls = lineStartOf(t, s);
    const le = lineEndOf(t, e > s && t[e - 1] === '\n' ? e - 1 : e);
    const lines = t.slice(ls, le).split('\n');
    const shift = lines.map((line) => {
      if (!out) return lines.length > 1 && line.trim() === '' ? 0 : 2;
      return -(line[0] === '\t' ? 1 : /^ {0,2}/.exec(line)[0].length);
    });
    if (shift.every((d) => d === 0)) return { select: [s, e] };
    const insert = lines.map((line, i) => (shift[i] > 0 ? '  ' + line : line.slice(-shift[i]))).join('\n');
    // A position moves with its line's text; one inside removed indent lands at the line start.
    const moved = (p) => {
      if (p > le) return p + insert.length - (le - ls);
      let start = ls, i = 0, delta = 0;
      while (start + lines[i].length < p) { delta += shift[i]; start += lines[i].length + 1; i++; }
      const col = p - start;
      return p + delta + (shift[i] >= 0 ? shift[i] : -Math.min(col, -shift[i]));
    };
    const sel = [moved(s), moved(e)];
    return { from: ls, to: le, insert, caret: sel[1], sel };
  }

  // Control and navigation keys (call from `keydown`). `mods` = {ctrl, alt, shift, meta}.
  function keyAction(key, mods, t, s, e, ctx) {
    const plain = !mods.ctrl && !mods.alt && !mods.shift && !mods.meta;
    // Enter in a block keeps its indent, with Math keys on or off, on prose lines too.
    if (ctx && ctx.enabled === false) return plain && key === 'Enter' ? newline(t, s, e) : null;
    const ls = lineStartOf(t, s), le = lineEndOf(t, e);
    const comment = isTextAt(t, s);
    const k = key.length === 1 ? key.toLowerCase() : key;

    // Ctrl+[ takes the term as an array and opens one index: idx(A, i), shown A_i.
    // Ctrl+Shift+[ opens row and column: elem(A, i, j), shown A_i,j.
    if (mods.ctrl && !mods.alt && !mods.meta && !comment && (key === '[' || key === '{')) {
      return mods.shift || key === '{' ? indexCall(t, s, e, ls, 'elem') : indexCall(t, s, e, ls, 'idx');
    }
    // Ctrl+< (Ctrl+Shift+, on a US keyboard) types the polar angle sign: 5'V∠30'deg.
    if (mods.ctrl && !mods.alt && !mods.meta && !comment && (key === '<' || (mods.shift && key === ','))) {
      return edit(s, e, '∠', s + 1);
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
    const g = plain && !comment && key === 'Enter' && e === s ? globalStart(t, s, ctx) : -1;
    if (g >= 0) return withTilde(t, s, g, '\n', (t2, s2) => keyAction(key, mods, t2, s2, s2, plainCtx(ctx)));
    if (plain && !comment && key === 'Enter' && e === s && /^[)\]]+$/.test(t.slice(s, le))) {
      return newline(t, le, le) || edit(le, le, '\n', le + 1);
    }
    if (plain && key === 'Enter') return newline(t, s, e);
    if (plain && !comment) {
      if (key === 'ArrowRight' && e === s) return exitSlot(t, s, ls);
      if (key === 'Backspace') return backspace(t, s, e, ls, le);
    }
    return null;
  }

  const api = {
    DEFAULT_GREEK, charAction, keyAction, indentLines, newline, headerOf, blockAt, merge, applyEdits, nameAt,
    termBefore, termAfter, matchBack, matchFwd, enclosing,
    snap, grow, wrapWithCall, tokens, isTok,
    isTextAt, isProse,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Editing = api;
})(typeof window !== 'undefined' ? window : globalThis);
