/* Autocomplete for the worksheet editor: what to suggest at the caret.
 *
 * Pure functions, like editing.js: they take the text and caret and return data
 * or an edit {from, to, insert, caret}; the page owns the popup. They run under
 * Node for tests.
 *
 *   context(text, caret, {force})        what is being typed, or null for no popup
 *   candidates(ctx, vocab, text, extras) ranked suggestions; your variables and functions
 *                                        come from extras.symbols, the last symbol table
 *   accept(text, ctx, candidate)         the edit that inserts one
 *
 * The open list, {ctx, items, index, moved, wrap: [from, to] | null, query, stale}, and what keys
 * do to it, are here too; the page draws it and passes `env` = {vocab, symbols}:
 *   open(text, s, e, {force, enabled, fresh}, env)
 *       the list for the caret (its items may be none), null for no list, or {props: true} when
 *       vocab.props must be fetched first. `stale`: names came from the symbol table of other text
 *       (`fresh` false), so ask again once this text's arrives
 *   wrapping(text, wrap, query, index, env)  Ctrl+Space over a highlight: functions to wrap it in
 *   key(list, key, mods, text, env)  what a key does: {use} whether it is spent on the list, and
 *       one of {list} (the list after it), {accept}, {close} or {message}
 *   pick(text, list)                 the edit for the chosen item, or null
 *
 * Besides names, units and commands it completes, from vocab.solver: the option keys, `method:`
 * and `autorun:` values and unknown names of a `!root` / `!minimize` / `!maximize` block; and,
 * from vocab.props (fetched separately, it needs CoolProp), the quoted keys and fluid of props().
 */
(function (root) {
  'use strict';
  const Symbols = typeof module !== 'undefined' && module.exports ? require('./symbols.js') : root.Symbols;
  const Editing = typeof module !== 'undefined' && module.exports ? require('./editing.js') : root.Editing;

  const WORD = /[\p{L}\p{N}_°∞]/u;
  const NAME_START = '[\\p{L}_](?:_∞|[\\p{L}\\p{N}_])*';
  const FUNC_RE = new RegExp('^(~?' + NAME_START + ')\\s*\\(([^)]*)\\)\\s*=(?!=)', 'u');
  const ASSIGN_RE = new RegExp('^(~?' + NAME_START + '[`!@&]*)\\s*=(?!=)', 'u');
  const UNITDEF_RE = /^'([A-Za-z][A-Za-z0-9_]*)\s*=(?!=)\s*(.+)$/;
  const MAX = 8;
  const SOLVER_HEAD = /^\s*!(root|minimize|maximize|regression|symsolve)\b(.*)$/;
  const SYMDEF_RE = /^~?\$/;

  // What a trimmed line defines: {kind: 'unitdef' | 'funcdef' | 'assign' | 'symdef', name, params}, or null.
  // A symbol declaration (`$a, $b`) defines every name on it; `name` is the first, as written.
  // As laconic/sheettext.py's definition() for whole lines (tests/sheettext_vectors.json), but a
  // line being typed counts before its body or with half its parameters.
  function definition(s) {
    if (SYMDEF_RE.test(s)) {
      const names = Editing.tokens(s).filter((t) => t.kind === 'name').map((t) => t.text);
      return { kind: 'symdef', name: names.length ? names[0] : s, params: [], names };
    }
    let m = UNITDEF_RE.exec(s);
    if (m) return { kind: 'unitdef', name: m[1], params: [], body: m[2] };
    m = FUNC_RE.exec(s);
    if (m) return { kind: 'funcdef', name: m[1], params: m[2].split(',').map((p) => p.trim()).filter(Boolean) };
    m = ASSIGN_RE.exec(s);
    return m ? { kind: 'assign', name: m[1], params: [] } : null;
  }

  const lineStartOf = (t, p) => t.lastIndexOf('\n', p - 1) + 1;
  const lineEndOf = (t, p) => { const i = t.indexOf('\n', p); return i < 0 ? t.length : i; };

  // Units this sheet defines, wherever the definition sits (definitions apply to the whole sheet).
  function unitDefs(text) {
    const out = [];
    text.split('\n').forEach((l, i) => {
      const d = definition(l.trim());
      if (d && d.kind === 'unitdef') out.push({ name: d.name, definition: d.body.trim(), line: i + 1 });
    });
    return out;
  }

  // The solver block that the line starting at `ls` belongs to: {kind, unknowns}, or null.
  // A block is its header and the indented, non-blank lines under it (the line being typed may
  // still be only its indent).
  function solverBlock(t, ls) {
    if (!/^[ \t]/.test(t.slice(ls, lineEndOf(t, ls)))) return null;
    let p = ls;
    while (p > 0) {
      const ps = lineStartOf(t, p - 1), l = t.slice(ps, p - 1);
      const m = SOLVER_HEAD.exec(l);
      if (m) return { kind: m[1], unknowns: m[2].split(',').map((x) => x.trim()).filter(Boolean) };
      if (!/^[ \t]+\S/.test(l)) return null;
      p = ps;
    }
    return null;
  }

  // Inside a quoted argument of props(...) at `pos` (the line runs from `ls`, the quote opened at `q`):
  // which argument it is, and the first argument's text. Null for any other string.
  function propsArg(t, ls, q) {
    let depth = 0, arg = 0, quoted = false, i = q - 1;
    for (; i >= ls; i--) {
      const c = t[i];
      if (c === '"') quoted = !quoted;
      else if (quoted) continue;
      else if (c === ')' || c === ']') depth++;
      else if (c === '(' || c === '[') { if (depth === 0) break; depth--; }
      else if (c === ',' && depth === 0) arg++;
    }
    if (i < ls || t[i] !== '(' || !/(^|[^\p{L}\p{N}_])props\s*$/u.test(t.slice(ls, i))) return null;
    const first = /^\s*"([^"]*)"/.exec(t.slice(i + 1));
    return { arg, output: first ? first[1] : '' };
  }

  // What is being typed at `pos`:
  //   {kind: 'unit'|'name'|'command'|'prop'|'option'|'choice', start, end, query, tilde, ...}
  // `start..end` is the token to replace (the whole word, even if the caret is inside it).
  // With no `force`, popups only appear for a unit after ', a command after !,
  // or a name of two or more characters.
  function context(t, pos, opts) {
    const force = !!(opts && opts.force);
    const ls = lineStartOf(t, pos), le = lineEndOf(t, pos);
    const line = t.slice(ls, le);
    // Nothing in prose, except a solver's method, which has its choices.
    if (Editing.isTextAt(t, pos) && !/^[ \t]+method[ \t]*:/.test(line)) return null;
    // Inside quotes: only props() has anything to offer (its keys and the fluid).
    const quotes = (line.slice(0, pos - ls).match(/"/g) || []).length;
    if (quotes % 2) {
      const q = line.lastIndexOf('"', pos - ls - 1) + ls;
      const pa = propsArg(t, ls, q);
      if (!pa) return null;
      const close = t.indexOf('"', pos);
      const closed = close >= 0 && close <= le;
      return { kind: 'prop', start: q + 1, end: closed ? close : pos, query: t.slice(q + 1, pos), closed, arg: pa.arg, output: pa.output };
    }
    let s = pos;
    while (s > ls && WORD.test(t[s - 1])) s--;
    let e = pos;
    while (e < le && WORD.test(t[e])) e++;
    const query = t.slice(s, pos);
    const before = t.slice(ls, s), after = t.slice(e, le);

    const isPlot = /^\s*!plot\s/.test(line);   // a plot statement holds expressions, unlike other commands
    // A solver header names its unknowns: variables defined above.
    if (SOLVER_HEAD.test(line) && !/^\s*!$/.test(before)) {
      // A regression's header names new variables, the coefficients it defines: nothing to offer.
      if (/^[\d.]/.test(query) || (!force && query.length < 2) || SOLVER_HEAD.exec(line)[1] === 'regression') return null;
      return { kind: 'name', start: s, end: e, query, tilde: false, only: ['variable'] };
    }
    const block = solverBlock(t, ls);
    if (block) {
      const colon = line.indexOf(':');
      if (colon < 0 || pos - ls <= colon) {
        // The option key, or after `bounds ` the unknown it limits.
        if (/^[ \t]+bounds[ \t]+$/.test(before)) {
          return { kind: 'choice', start: s, end: e, query, choices: block.unknowns.map((u) => [u, 'unknown']), suffix: ': ' };
        }
        if (!/^[ \t]+$/.test(before) || (!force && !query)) return null;
        return { kind: 'option', start: s, end: e, query, block };
      }
      const key = line.slice(0, colon).trim().split(/\s+/)[0];
      if (key === 'method' || key === 'autorun') {
        let vs = ls + colon + 1;
        while (vs < pos && /[ \t]/.test(t[vs])) vs++;
        let ve = le;
        while (ve > vs && /[ \t]/.test(t[ve - 1])) ve--;
        return { kind: 'choice', start: vs, end: Math.max(ve, pos), query: t.slice(vs, pos), key, block };
      }
      if (!['equation', 'objective', 'constraint', 'bounds', 'data', 'r2'].includes(key)) return null;
    }
    if (line.trimStart().startsWith('!') && !isPlot) {
      if (!/^\s*!$/.test(before)) return null;
      return { kind: 'command', start: s, end: e, query, tilde: false };
    }
    if (/^[\d.]/.test(query)) return null;                     // a number
    if (t[s - 1] === '.' && /[\d]/.test(t[s - 2] || '')) return null;
    // The left of = is a name being defined (or a unit, or a function's parameters): nothing to complete.
    // (An equation or constraint in a solver block has = on its right too, and is an expression.)
    if (!isPlot && !block && !before.includes('=') && after.includes('=')) return null;
    if (t[s - 1] === "'") return { kind: 'unit', start: s, end: e, query, tilde: false };
    const tilde = t[s - 1] === '~';
    if (t[s - 1] === '$') return null;                         // a symbol being declared: a new name
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

  // extras: {symbols} is the symbol table (symbols.js) the variables and functions come from, with
  // the value shown next to a variable; {max} raises the limit of eight and {kinds} keeps only some kinds.
  function candidates(ctx, vocab, text, extras) {
    if (!ctx) return [];
    const q = ctx.query, found = [];
    const add = (c, rankOf, text2, detail) => {
      const t = tier(text2, detail, q);
      if (t >= 0) found.push({ ...c, tier: t, rank: rankOf });
    };
    if (ctx.kind === 'prop') {
      const pv = vocab.props;
      if (!pv) return [];
      const fixed = new Set(pv.keys.filter((k) => k[4]).map((k) => k[0]));
      // props(output, in1, value1, in2, value2, fluid), or props(fixed output, fluid)
      const what = ctx.arg === 0 ? 'output' : ctx.arg === 5 || (ctx.arg === 1 && fixed.has(ctx.output)) ? 'fluid'
        : ctx.arg === 1 || ctx.arg === 3 ? 'input' : null;
      if (what === 'fluid') {
        pv.fluids.forEach(([name, detail], i) => add({ kind: 'fluid', insert: name, label: name, detail }, i, name, detail));
      } else if (what) {
        pv.keys.forEach(([key, desc, unit, input, isFixed], i) => {
          if (what === 'input' && !input) return;
          add({ kind: 'property', insert: key, label: key, detail: desc + (unit ? ` [${unit}]` : '') + (isFixed ? ', no state needed' : '') }, i, key, desc);
        });
      }
    } else if (ctx.kind === 'option') {
      const sv = vocab.solver || { keys: {} };
      for (const [key, detail] of sv.keys[ctx.block.kind] || []) {
        // several unknowns: a bounds line names one, so offer one per unknown
        if (key === 'bounds' && ctx.block.unknowns.length > 1) {
          for (const u of ctx.block.unknowns) add({ kind: 'option', insert: `bounds ${u}`, label: `bounds ${u}`, detail, suffix: ': ' }, 0, 'bounds', detail);
        } else add({ kind: 'option', insert: key, label: key, detail, suffix: ': ' }, 0, key, detail);
      }
      // keep the block's own order (equation first), not alphabetical
      found.forEach((c, i) => { c.rank = i; });
    } else if (ctx.kind === 'choice') {
      const sv = vocab.solver || { methods: {}, choices: {} };
      const list = ctx.choices || (ctx.key === 'method' ? sv.methods[ctx.block.kind === 'root' ? 'root' : 'optimize'] : sv.choices[ctx.key]) || [];
      list.forEach(([name, detail], i) => add({ kind: ctx.key || 'unknown', insert: name, label: name, detail, suffix: ctx.suffix }, i, name, detail));
    } else if (ctx.kind === 'command') {
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
      const funcs = new Set();
      for (const sym of Symbols.visible(extras && extras.symbols, line)) {
        const name = (sym.global ? '~' : '') + sym.name;
        if (ctx.tilde && !sym.global) continue;
        if (sym.kind === 'function') {
          funcs.add(name);
          add({ kind: 'function', insert: name, label: name + '(' + sym.params.join(', ') + ')', detail: 'your function', call: true }, 1, sym.name, '');
        } else add({ kind: 'variable', insert: name, label: name, detail: sym.value || 'variable' }, 0, sym.name, '');
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
    const kinds = (extras && extras.kinds) || ctx.only;
    const out = found.filter((c) => !kinds || kinds.includes(c.kind)).slice(0, (extras && extras.max) || MAX);
    // Nothing to offer when the only suggestion is exactly what is typed, except in a props string that
    // is still open: there accepting closes it, and the detail shows what the key means and its unit.
    if (out.length === 1 && out[0].insert === text.slice(ctx.start, ctx.end) && !(ctx.kind === 'prop' && !ctx.closed)) return [];
    return out;
  }

  // The edit that completes `ctx` with `cand`. A function gets brackets with the
  // caret inside, unless the word is already followed by one.
  function accept(t, ctx, cand) {
    if (ctx.kind === 'prop') {   // the whole string's text, closed, caret after the quote
      const insert = cand.insert + (ctx.closed ? '' : '"');
      return { from: ctx.start, to: ctx.end, insert, caret: ctx.start + cand.insert.length + 1 };
    }
    if (cand.suffix) {           // `key: ` (or `bounds x: `), unless the colon is already there
      const has = /^\s*:/.test(t.slice(ctx.end, lineEndOf(t, ctx.end)));
      const insert = cand.insert + (has ? '' : cand.suffix);
      return { from: ctx.start, to: ctx.end, insert, caret: ctx.start + insert.length };
    }
    const le = lineEndOf(t, ctx.end);
    const hasParen = t[ctx.end] === '(' && ctx.end < le;
    if (cand.call && !hasParen) {
      return { from: ctx.start, to: ctx.end, insert: cand.insert + '()', caret: ctx.start + cand.insert.length + 1 };
    }
    return { from: ctx.start, to: ctx.end, insert: cand.insert, caret: ctx.start + cand.insert.length };
  }

  // ---- the open list ------------------------------------------------------------------
  function open(t, s, e, opts, env) {
    const force = !!opts.force;
    if ((!opts.enabled && !force) || s !== e) return null;
    const ctx = context(t, s, { force });
    if (!ctx) return null;
    if (ctx.kind === 'prop' && !env.vocab.props) return { props: true };
    const items = candidates(ctx, env.vocab, t, { symbols: env.symbols });
    return { ctx, items, index: 0, moved: false, wrap: null, query: '', stale: ctx.kind === 'name' && !opts.fresh };
  }

  function wrapping(t, wrap, query, index, env) {
    const ctx = { kind: 'name', start: wrap[0], end: wrap[0], query, tilde: false };
    const items = candidates(ctx, { functions: env.vocab.functions, constants: [], units: [], commands: [] }, t,
      { max: 24, kinds: ['function'], symbols: env.symbols });
    return { ctx, items, index: Math.min(index, Math.max(items.length - 1, 0)), moved: true, wrap, query, stale: false };
  }

  // Arrows choose; Tab accepts, and Enter once an item was chosen (else it ends the line). While
  // wrapping, typed characters filter the functions.
  function key(list, k, mods, t, env) {
    if (mods.ctrl || mods.meta) return { use: false };
    if (mods.alt) return { use: false, close: true };
    const n = list.items.length;
    const requery = (query) => {
      const next = wrapping(t, list.wrap, query, 0, env);
      return !next.items.length && query ? { use: true, message: 'No function starts with that' } : { use: true, list: next };
    };
    if (list.wrap) {
      if (k.length === 1) return requery(list.query + k);
      if (k === 'Backspace') return requery(list.query.slice(0, -1));
    }
    if (k === 'ArrowDown') return { use: true, list: { ...list, index: (list.index + 1) % n, moved: true } };
    if (k === 'ArrowUp') return { use: true, list: { ...list, index: (list.index + n - 1) % n, moved: true } };
    if (k === 'Tab' && !mods.shift) return { use: true, accept: true };
    if (k === 'Enter' && (list.moved || list.wrap)) return { use: true, accept: true };
    if (k === 'Escape') return { use: true, close: true };
    if (['Enter', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'PageUp', 'PageDown'].includes(k)) return { use: false, close: true };
    return { use: false };
  }

  function pick(t, list) {
    const c = list.items[list.index];
    return list.wrap ? Editing.wrapWithCall(t, list.wrap[0], list.wrap[1], c.insert) : accept(t, list.ctx, c);
  }

  const api = { unitDefs, definition, solverBlock, context, candidates, accept, open, wrapping, key, pick };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Autocomplete = api;
})(typeof window !== 'undefined' ? window : globalThis);
