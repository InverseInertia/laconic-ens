/* The editor's view of the sheet: the text the textarea shows, which can differ from the sheet text
 * in two ways, and the map between the two. Pure functions; runs under Node.
 *
 *   Folds (#154): a heading folds the lines down to the next heading of its level or higher, and
 *   any other line folds the lines indented further under it (a block's option lines, a loop's
 *   steps). The folded lines are shown as one placeholder at the end of the line that opens them,
 *   "  ⋯ 3 lines". On a folded line, each vector or matrix literal folds to [⋯] as well.
 *
 *   Matrix rows (#155): with wrapping on, a matrix literal is shown one row per line after each
 *   `;`, its rows lined up under the first, as MATLAB writes them. A vector of one column
 *   ([1; 2; 3]) is left on its line. The line breaks are the view's only: the sheet keeps one line.
 *
 *   regions(text)          Map: line number -> last line of the lines it folds, for every line that
 *                          folds something (line numbers from 1, as the editor numbers them)
 *   literals(line)         the vector and matrix literals on one line of text, outermost only:
 *                          [{open, close, semis, column}] (columns; `column`: one element per row)
 *   foldable(text)         Set of the line numbers a fold can be put on
 *   layout(text, opts)     the view of `text`, opts {folds: Set of line numbers, rows: bool}:
 *                          {view, toView(m, before), toModel(v), added(v), lines, folds}; `added`:
 *                          whether view character v is part of a row break; `lines` is one
 *                          {n, v0, v1} per line the view shows (v1: its end, before the newline),
 *                          `folds` one {n, v0, v1} per placeholder
 *   edit(L, view, caret, dir)  the edit to the sheet text that turns L.view into `view`, the
 *                          textarea's text after the user typed (`caret`: its caret then; `dir`: -1
 *                          for a Backspace, 1 for a Delete): {from, to, insert}, or {unfold: n}
 *                          when the edit reaches into a folded placeholder, or null for none
 *   shift(folds, text, e)  the folds after edit `e` to `text`: lines below it move with it, and a
 *                          line the edit removed loses its fold
 *   History                undo and redo of the sheet text, for when the view is not the text and
 *                          the browser's own undo cannot be used
 */
(function (root) {
  'use strict';

  const indent = (s) => /^[ \t]*/.exec(s)[0].length;
  const level = (s) => { const m = /^\s*(#{2,})/.exec(s); return m ? m[1].length : 0; };

  function regions(text) {
    const lines = text.split('\n'), out = new Map();
    for (let i = 0; i < lines.length; i++) {
      const s = lines[i];
      if (!s.trim()) continue;
      let end = i;
      const lv = level(s);
      if (lv) {
        for (let j = i + 1; j < lines.length; j++) {
          const l = level(lines[j]);
          if (l && l <= lv) break;
          if (lines[j].trim()) end = j;
        }
      } else {
        const ind = indent(s);
        for (let j = i + 1; j < lines.length; j++) {
          if (!lines[j].trim()) continue;
          if (indent(lines[j]) <= ind) break;
          end = j;
        }
      }
      if (end > i) out.set(i + 1, end + 1);
    }
    return out;
  }

  function literals(line) {
    if (/^\s*#/.test(line)) return [];
    const out = [];
    let depth = 0, cur = null, commas = 0;   // depth: brackets and parentheses inside the literal
    for (let k = 0; k < line.length; k++) {
      const c = line[k];
      if (c === '"') { const e = line.indexOf('"', k + 1); if (e < 0) break; k = e; continue; }
      if (!cur) {
        if (c === '[') { cur = {open: k, close: -1, semis: [], column: true}; commas = 0; depth = 1; }
        continue;
      }
      if (c === '[' || c === '(') depth++;
      else if (c === ']' || c === ')') {
        depth--;
        if (depth === 0) {
          cur.close = k;
          cur.column = commas === 0;
          if (cur.semis.length || commas) out.push(cur);
          cur = null;
        }
      } else if (depth === 1) {
        if (c === ';') cur.semis.push(k);
        else if (c === ',') commas++;
      }
    }
    return out;
  }

  function foldable(text) {
    const set = new Set(regions(text).keys());
    text.split('\n').forEach((l, i) => { if (literals(l).length) set.add(i + 1); });
    return set;
  }

  const plural = (n) => `  ⋯ ${n} line${n === 1 ? '' : 's'}`;

  function layout(text, opts = {}) {
    const folds = opts.folds || new Set(), rows = !!opts.rows;
    const regs = folds.size ? regions(text) : new Map();
    const M = text.length;
    const vA = new Int32Array(M + 1), vB = new Int32Array(M + 1);
    const vm = [], added = [];   // added[v]: view character v is a row break the view adds
    const view = [];
    let V = 0, lineStart = 0;   // lineStart: where the current view line starts
    const shown = [], placeholders = [];

    const emitText = (a, b) => {
      for (let k = a; k < b; k++) {
        if (k !== a) vB[k] = V;
        vA[k] = V; vm[V] = k;
        const c = text[k];
        view.push(c); V++;
        if (c === '\n') lineStart = V;
      }
      vB[b] = V; vA[b] = V;
    };
    const emitVirt = (at, s) => {
      for (let k = 0; k < s.length; k++) { vm[V + k] = at; added[V + k] = true; }
      view.push(s); V += s.length;
      const nl = s.lastIndexOf('\n');
      if (nl >= 0) lineStart = V - s.length + nl + 1;
      vA[at] = V;
    };
    const emitHide = (a, b, s) => {
      vA[a] = vB[a] = V;
      for (let k = a + 1; k < b; k++) { vB[k] = V; vA[k] = V + s.length; }
      for (let k = 0; k < s.length; k++) vm[V + k] = a;
      view.push(s); V += s.length;
      vA[b] = vB[b] = V;
    };

    const lines = text.split('\n');
    const starts = [];
    for (let i = 0, o = 0; i < lines.length; i++) { starts.push(o); o += lines[i].length + 1; }
    let i = 0;
    while (i < lines.length) {
      const n = i + 1, ls = starts[i], le = ls + lines[i].length;
      const folded = folds.has(n);
      const v0 = V;
      let m = ls;
      for (const lit of literals(lines[i])) {
        if (folded) {
          emitText(m, ls + lit.open + 1);
          emitHide(ls + lit.open + 1, ls + lit.close, '⋯');
          placeholders.push({n, v0: V - 1, v1: V});
          m = ls + lit.close;
        } else if (rows && !lit.column && lit.semis.length) {
          emitText(m, ls + lit.open);
          const col = V - lineStart + 1;
          emitText(ls + lit.open, ls + lit.open + 1);
          m = ls + lit.open + 1;
          for (const s of lit.semis) {
            emitText(m, ls + s + 1);
            let e = ls + s + 1;
            while (e < le && (text[e] === ' ' || text[e] === '\t')) e++;
            if (e > ls + s + 1) emitHide(ls + s + 1, e, '');
            emitVirt(e, '\n' + ' '.repeat(col));
            m = e;
          }
        }
      }
      emitText(m, le);
      let last = i;
      if (folded && regs.has(n)) {
        const end = regs.get(n) - 1, ee = starts[end] + lines[end].length;
        const s = plural(end - i);
        emitHide(le, ee, s);
        placeholders.push({n, v0: V - s.length, v1: V});
        last = end;
      }
      shown.push({n, v0, v1: V});
      const nextStart = starts[last] + lines[last].length;
      if (last + 1 < lines.length) emitText(nextStart, nextStart + 1);
      i = last + 1;
    }
    vm[V] = M;
    const out = view.join('');
    return {
      view: out,
      identity: out === text,
      toView: (m, before = false) => (before ? vB : vA)[Math.max(0, Math.min(M, m))],
      toModel: (v) => vm[Math.max(0, Math.min(V, v))],
      added: (v) => !!added[v],
      lines: shown,
      folds: placeholders,
    };
  }

  function edit(L, view, caret, dir = 0) {
    const old = L.view;
    if (old === view) return null;
    let s = 0;
    const smax = Math.min(old.length, view.length - Math.min(caret, view.length));
    while (s < smax && old[old.length - 1 - s] === view[view.length - 1 - s]) s++;
    let p = 0;
    const pmax = Math.min(old.length - s, view.length - s);
    while (p < pmax && old[p] === view[p]) p++;
    const oEnd = old.length - s, insert = view.slice(p, view.length - s);
    for (const f of L.folds) {
      if ((p < f.v1 && oEnd > f.v0) || (p > f.v0 && p <= f.v1)) return {unfold: f.n};
    }
    let from = L.toModel(p), to = L.toModel(oEnd);
    if (to < from) to = from;
    return {from, to, insert, dir, viewFrom: p, viewTo: oEnd};
  }

  // A deletion that removed only what the view adds (a row break) acts on the text beyond it, past
  // the spaces the view hid: across a row break it joins the two rows into one, as deleting a line
  // break between rows does in MATLAB ([1, 2; 3, 4] becomes [1, 2, 3, 4]); otherwise it deletes
  // the next character in its direction.
  function widen(text, e) {
    if (!e || e.insert || e.from !== e.to || !e.dir) return e;
    const space = (c) => c === ' ' || c === '\t';
    let a = e.from, b = e.from;
    while (a > 0 && space(text[a - 1])) a--;
    while (b < text.length && space(text[b])) b++;
    if (text[a - 1] === ';') return {...e, from: a - 1, to: b, insert: ', '};
    if (e.dir < 0) return a > 0 ? {...e, from: a - 1, to: e.from} : null;
    return b < text.length ? {...e, to: b + 1} : null;
  }

  const count = (s) => (s.match(/\n/g) || []).length;

  function shift(folds, text, e) {
    const line = count(text.slice(0, e.from)) + 1;
    const removed = count(text.slice(e.from, e.to)), added = count(e.insert);
    const out = new Set();
    for (const n of folds) {
      if (n <= line) out.add(n);
      else if (n > line + removed) out.add(n + added - removed);
    }
    return out;
  }

  // Undo and redo over the sheet text. Typing one character after another, on from where the
  // last left off, is one step, as in the browser's own undo.
  class History {
    constructor() { this.undos = []; this.redos = []; this.lastTyped = null; }
    record(before, e, typed) {
      const joins = typed && this.lastTyped !== null && e.from === this.lastTyped && e.to === e.from
        && e.insert.length === 1 && e.insert !== '\n';
      if (!joins) this.undos.push(before);
      this.redos = [];
      this.lastTyped = typed && e.to === e.from && e.insert.length === 1 && e.insert !== '\n' ? e.from + 1 : null;
    }
    undo(current) { this.lastTyped = null; const s = this.undos.pop(); if (s) this.redos.push(current); return s || null; }
    redo(current) { this.lastTyped = null; const s = this.redos.pop(); if (s) this.undos.push(current); return s || null; }
    clear() { this.undos = []; this.redos = []; this.lastTyped = null; }
  }

  const api = {regions, literals, foldable, layout, edit, widen, shift, History};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.EditView = api;
})(typeof window !== 'undefined' ? window : globalThis);
