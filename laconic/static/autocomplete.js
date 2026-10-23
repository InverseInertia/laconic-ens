/* Autocomplete for the worksheet editor: what to suggest at the caret.
 *
 * Pure functions, like editing.js: they take the text and caret and return data
 * or an edit {from, to, insert, caret}; the page owns the popup. They run under
 * Node for tests.
 *
 *   context(text, caret, {force})        what is being typed, or null for no popup
 *   candidates(ctx, vocab, text, extras) ranked suggestions
 *   accept(text, ctx, candidate)         the edit that inserts one
 */
(function (root) {
  'use strict';

  const WORD = /[\p{L}\p{N}_°]/u;
  const NAME_START = '[\\p{L}_][\\p{L}\\p{N}_]*';
  const FUNC_RE = new RegExp('^(~?' + NAME_START + ')\\s*\\(([^)]*)\\)\\s*=(?!=)', 'u');
  const ASSIGN_RE = new RegExp('^(~?' + NAME_START + '[`!@]*)\\s*=(?!=)', 'u');
  const UNITDEF_RE = /^'([A-Za-z][A-Za-z0-9_]*)\s*=(?!=)\s*(.+)$/;
  const MAX = 8;

  const lineStartOf = (t, p) => t.lastIndexOf('\n', p - 1) + 1;
  const lineEndOf = (t, p) => { const i = t.indexOf('\n', p); return i < 0 ? t.length : i; };

  // Variables and functions defined on the lines above `line` (1-based), following
  // !clear the way the evaluator does.
  function scan(text, line) {
    const vars = new Map(), funcs = new Map(), gv = new Set(), gf = new Set();
    // A ~ on a definition makes the name global; later definitions of it stay global.
    const key = (name, globals) => { const bare = name.replace(/^~/, ''); if (name !== bare) globals.add(bare); return globals.has(bare) ? '~' + bare : bare; };
    const lines = text.split('\n');
    for (let i = 0; i < Math.min(line - 1, lines.length); i++) {
      const s = lines[i].trim();
      if (!s || s[0] === '#' || s[0] === "'") continue;
      if (s[0] === '!') {
        if (/^!clear\s*$/.test(s)) for (const n of [...vars.keys()]) if (n[0] !== '~') vars.delete(n);
        if (/^!clearf\s*$/.test(s)) for (const n of [...funcs.keys()]) if (n[0] !== '~') funcs.delete(n);
        continue;
      }
      let m = FUNC_RE.exec(s);
      if (m) { funcs.set(key(m[1], gf), { params: m[2].split(',').map((p) => p.trim()).filter(Boolean), line: i + 1 }); continue; }
      m = ASSIGN_RE.exec(s);
      if (m) vars.set(key(m[1], gv), { line: i + 1 });
    }
    return { vars, funcs };
  }

  // Units this sheet defines, wherever the definition sits (definitions apply to the whole sheet).
  function unitDefs(text) {
    const out = [];
    text.split('\n').forEach((l, i) => {
      const m = UNITDEF_RE.exec(l.trim());
      if (m) out.push({ name: m[1], definition: m[2].trim(), line: i + 1 });
    });
    return out;
  }

  // What is being typed at `pos`:
  //   {kind: 'unit'|'name'|'command', start, end, query, tilde}
  // `start..end` is the token to replace (the whole word, even if the caret is inside it).
  // With no `force`, popups only appear for a unit after ', a command after !,
  // or a name of two or more characters.
  function context(t, pos, opts) {
    const force = !!(opts && opts.force);
    const ls = lineStartOf(t, pos), le = lineEndOf(t, pos);
    const line = t.slice(ls, le);
    if (line.trimStart().startsWith('#') || /^\s+(title|xlabel|ylabel|label|note)(\s+\d+)?\s*:/.test(line)) return null;
    let s = pos;
    while (s > ls && WORD.test(t[s - 1])) s--;
    let e = pos;
    while (e < le && WORD.test(t[e])) e++;
    const query = t.slice(s, pos);
    const before = t.slice(ls, s), after = t.slice(e, le);

    const isPlot = /^\s*!plot\s/.test(line);   // a plot statement holds expressions, unlike other commands
    if (line.trimStart().startsWith('!') && !isPlot) {
      if (!/^\s*!$/.test(before)) return null;
      return { kind: 'command', start: s, end: e, query, tilde: false };
    }
    if (/^[\d.]/.test(query)) return null;                     // a number
    if (t[s - 1] === '.' && /[\d]/.test(t[s - 2] || '')) return null;
    // The left of = is a name being defined (or a unit, or a function's parameters): nothing to complete.
    if (!isPlot && !before.includes('=') && after.includes('=')) return null;
    if (t[s - 1] === "'") return { kind: 'unit', start: s, end: e, query, tilde: false };
    const tilde = t[s - 1] === '~';
    if (!force && query.length < 2) return null;
    return { kind: 'name', start: tilde ? s - 1 : s, end: e, query, tilde };
  }

  // Tiers: 0 exact, 1 prefix, 2 prefix ignoring case, 3 and 4 matches in the description.
  function tier(text, detail, q) {
    if (!q) return 0;
    const lt = text.toLowerCase(), lq = q.toLowerCase();
    if (text === q) return 0;
    if (text.startsWith(q)) return 1;
    if (lt.startsWith(lq)) return 2;
    if (detail && detail.toLowerCase().startsWith(lq)) return 3;
    if (q.length >= 3 && detail && detail.toLowerCase().includes(lq)) return 4;
    return -1;
  }

  // Among the prefix matches (tiers 0 to 2) the kind of thing decides first, so `'k` offers kN and kg
  // before the Boltzmann constant; an exact match only breaks ties.
  const group = (c) => Math.max(c.tier, 2);
  const order = (a, b) => group(a) - group(b) || a.rank - b.rank || a.tier - b.tier || a.insert.length - b.insert.length || (a.insert < b.insert ? -1 : 1);

  // extras: {values: {name: "4.5 m"}} shows the current value next to a variable;
  // {max} raises the limit of eight and {kinds} keeps only some kinds.
  function candidates(ctx, vocab, text, extras) {
    if (!ctx) return [];
    const q = ctx.query, found = [];
    const add = (c, rankOf, text2, detail) => {
      const t = tier(text2, detail, q);
      if (t >= 0) found.push({ ...c, tier: t, rank: rankOf });
    };
    if (ctx.kind === 'command') {
      for (const [name, detail] of vocab.commands || []) add({ kind: 'command', insert: name, label: '!' + name, detail }, 0, name, detail);
    } else if (ctx.kind === 'unit') {
      const seen = new Set();
      const own = new Map(unitDefs(text).map((u) => [u.name, u.definition]));
      for (const [name, def] of vocab.globalUnits || []) if (!own.has(name)) own.set(name, def);
      for (const [name, def] of own) {
        seen.add(name);
        add({ kind: 'unit', insert: name, label: name, detail: '= ' + def, custom: true }, 0, name, def);
      }
      for (const [name, detail, common] of vocab.units || []) {
        if (seen.has(name)) continue;
        add({ kind: 'unit', insert: name, label: name, detail }, common ? 1 : 2, name, detail);
      }
    } else {
      const line = text.slice(0, ctx.start).split('\n').length;
      const { vars, funcs } = scan(text, line);
      const values = (extras && extras.values) || {};
      for (const name of vars.keys()) {
        if (ctx.tilde && name[0] !== '~') continue;
        add({ kind: 'variable', insert: name.replace(/^~/, ''), label: name, detail: values[name] || 'variable' }, 0, name.replace(/^~/, ''), '');
      }
      for (const [name, f] of funcs) {
        if (ctx.tilde && name[0] !== '~') continue;
        add({ kind: 'function', insert: name.replace(/^~/, ''), label: name + '(' + f.params.join(', ') + ')', detail: 'your function', call: true }, 1, name.replace(/^~/, ''), '');
      }
      for (const [name, sig] of vocab.functions || []) {
        if (ctx.tilde || funcs.has(name)) continue;
        add({ kind: 'function', insert: name, label: sig, detail: 'function', call: true }, 2, name, '');
      }
      for (const name of vocab.constants || []) {
        if (ctx.tilde) continue;
        add({ kind: 'constant', insert: name, label: name, detail: 'constant' }, 3, name, '');
      }
    }
    found.sort(order);
    const kinds = extras && extras.kinds;
    const out = found.filter((c) => !kinds || kinds.includes(c.kind)).slice(0, (extras && extras.max) || MAX);
    // Nothing to offer when the only suggestion is exactly what is typed.
    if (out.length === 1 && out[0].insert === text.slice(ctx.start, ctx.end)) return [];
    return out;
  }

  // The edit that completes `ctx` with `cand`. A function gets brackets with the
  // caret inside, unless the word is already followed by one.
  function accept(t, ctx, cand) {
    const le = lineEndOf(t, ctx.end);
    const hasParen = t[ctx.end] === '(' && ctx.end < le;
    if (cand.call && !hasParen) {
      return { from: ctx.start, to: ctx.end, insert: cand.insert + '()', caret: ctx.start + cand.insert.length + 1 };
    }
    return { from: ctx.start, to: ctx.end, insert: cand.insert, caret: ctx.start + cand.insert.length };
  }

  const api = { scan, unitDefs, context, candidates, accept };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Autocomplete = api;
})(typeof window !== 'undefined' ? window : globalThis);
