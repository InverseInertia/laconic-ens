/* Paste-as-matrix for the worksheet editor.
 *
 * Pure functions, like editing.js: they take clipboard text and return data or
 * an edit {from, to, insert, caret, message}; the page owns the paste event.
 * They run under Node for tests.
 *
 *   parseTable(text)   the table found in the text: {kind, rows} or null
 *   toMatrix(text)     {matrix, rows, cols, kind, notes} | {reject} | null
 *   pasteEdit(text, clip, s, e, {textLine})   the edit for a paste, or null
 *
 * Understood: Excel / Sheets (tab separated, quoted cells), Obsidian and other
 * Markdown pipe tables, comma separated rows, and a single column of numbers.
 * A header row and a label column are dropped; the same unit on every cell is
 * factored out (`[..] * 'kN`); empty cells become 0. null means the text is
 * not a table, so the browser pastes it as usual. {reject} means it looked
 * like one but cannot be a matrix (text cells, mixed units).
 */
(function (root) {
  'use strict';

  // ---- splitting into cells -------------------------------------------------
  const lines = (t) => t.replace(/\r\n?/g, '\n').replace(/\n+$/, '').split('\n');

  // Excel quotes a cell that holds a tab, a newline or a quote, and doubles the quotes inside.
  function parseTsv(text) {
    const t = text.replace(/\r\n?/g, '\n');
    const rows = [];
    let row = [], cell = '', quoted = false, i = 0, fresh = true;
    for (; i < t.length; i++) {
      const c = t[i];
      if (quoted) {
        if (c === '"' && t[i + 1] === '"') { cell += '"'; i++; }
        else if (c === '"') quoted = false;
        else cell += c;
      } else if (c === '"' && fresh) { quoted = true; fresh = false; }
      else if (c === '\t') { row.push(cell); cell = ''; fresh = true; }
      else if (c === '\n') { row.push(cell); rows.push(row); row = []; cell = ''; fresh = true; }
      else { cell += c; fresh = false; }
    }
    if (cell !== '' || row.length) { row.push(cell); rows.push(row); }
    return rows;
  }

  const SEPARATOR_RE = /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/;
  function splitPipes(line) {
    let s = line.trim();
    if (s.startsWith('|')) s = s.slice(1);
    if (s.endsWith('|') && !s.endsWith('\\|')) s = s.slice(0, -1);
    const cells = [];
    let cur = '';
    for (let i = 0; i < s.length; i++) {
      if (s[i] === '\\' && s[i + 1] === '|') { cur += '|'; i++; }
      else if (s[i] === '|') { cells.push(cur); cur = ''; }
      else cur += s[i];
    }
    cells.push(cur);
    return cells;
  }

  function parseTable(text) {
    if (typeof text !== 'string' || !text.trim()) return null;
    const ls = lines(text);
    // Markdown: a separator line (|---|:-:|) under the header, or every line piped.
    const piped = ls.filter((l) => l.trim());
    const sep = piped.findIndex((l, i) => i > 0 && l.includes('-') && SEPARATOR_RE.test(l) && (l.includes('|') || piped[0].includes('|')));
    if (piped.length >= 2 && piped.every((l) => l.includes('|')) && (sep === 1 || piped.every((l) => l.trim().startsWith('|')))) {
      const rows = piped.filter((l, i) => !(i === sep)).map(splitPipes);
      return { kind: 'markdown', rows, header: sep === 1 };
    }
    if (text.includes('\t')) {
      const rows = parseTsv(text);
      if (rows.length && rows.some((r) => r.length > 1) ) return { kind: 'excel', rows };
    }
    const rows = ls.filter((l) => l.trim());
    // Comma separated: two or more lines with the same number of commas.
    if (rows.length >= 2 && rows.every((l) => l.includes(',') && !/[=()[\]]/.test(l))) {
      const n = rows[0].split(',').length;
      if (n > 1 && rows.every((l) => l.split(',').length === n)) return { kind: 'csv', rows: rows.map((l) => l.split(',')) };
    }
    // One value per line.
    if (rows.length >= 2 && rows.every((l) => cellValue(l, true))) return { kind: 'column', rows: rows.map((l) => [l]) };
    return null;
  }

  // ---- reading one cell -----------------------------------------------------
  const SP = '[ \\u00a0\\u202f]';
  const NUM = '([+-]?(?:\\d{1,3}(?:,\\d{3})+(?!\\d)|\\d{1,3}(?:' + SP + '\\d{3})+(?!\\d)|\\d+)(?:[.,]\\d+)?(?:[eE][+-]?\\d+)?|[+-]?[.,]\\d+(?:[eE][+-]?\\d+)?)';
  const NUM_RE = new RegExp('^' + NUM + '\\s*(.*)$');
  const NAME = '[A-Za-z°µμΩ][\\w°µμΩ]*';
  const UNIT_RE = new RegExp('^' + NAME + '(?:\\^-?\\d+)?(?:\\s*[/*·]\\s*' + NAME + '(?:\\^-?\\d+)?)*$');

  function cleanCell(s) {
    return s.replace(/ | /g, ' ')
      .replace(/[−–]/g, '-')          // typographic minus
      .replace(/\[\[([^\]|]*\|)?([^\]]*)\]\]/g, '$2') // [[wiki|links]]
      .replace(/(\*\*|__|~~|==|`|\$)/g, '')    // bold, strike, highlight, code, $math$
      .replace(/^[*_]|[*_]$/g, '')
      .trim();
  }

  // {num, unit} for a numeric cell, {empty: true} for a blank one, else null.
  // `bare` refuses units, for deciding whether a single line is a number.
  function cellValue(raw, bare) {
    let s = cleanCell(raw);
    if (s === '' || /^(-|—|n\/?a|nan)$/i.test(s)) return bare ? null : { empty: true };
    let neg = false;
    const acct = /^\((.*)\)$/.exec(s);                // (5) is -5
    if (acct) { s = acct[1]; neg = true; }
    s = s.replace(/^[$€£¥]\s*/, '');
    const m = NUM_RE.exec(s);
    if (!m) return null;
    let n = m[1];
    if (/^[+-]?\d{1,3}(,\d{3})+(?!\d)/.test(n)) n = n.replace(/,/g, '');
    else n = n.replace(/[ ]/g, '').replace(',', '.');
    n = n.replace(/^\+/, '').replace(/^(-?)\./, '$10.').replace(/\.(?=[eE]|$)/, '');
    let unit = m[2].trim();
    if (neg) n = n.startsWith('-') ? n.slice(1) : '-' + n;
    if (unit === '%') {
      n = String(Number((Number(n) / 100).toPrecision(12)));
      unit = '';
    }
    if (unit && (bare || !UNIT_RE.test(unit))) return null;
    return { num: n, unit };
  }

  const toLensUnit = (u) => u.replace(/\s+/g, '').replace(/·/g, '*').replace(new RegExp(NAME, 'g'), "'$&").replace(/\*/g, ' * ').replace(/\//g, ' / ');

  // ---- table to matrix ------------------------------------------------------
  function toMatrix(text) {
    const tbl = parseTable(text);
    if (!tbl) return null;
    let rows = tbl.rows.map((r) => r.map((c) => c.trim()));
    const notes = [];
    const width = Math.max(...rows.map((r) => r.length));
    if (width * rows.length < 2) return null;
    const ragged = rows.some((r) => r.length < width);
    rows = rows.map((r) => r.concat(Array(width - r.length).fill('')));
    let vals = rows.map((r) => r.map((c) => cellValue(c)));
    const numeric = (v) => v && !v.empty;
    const anyNumeric = (vs) => vs.some((r) => r.some(numeric));

    // Header row: all text, with numbers underneath. (Markdown headers always count.)
    if (vals.length > 1 && !vals[0].some(numeric) && (tbl.header || anyNumeric(vals.slice(1)))) {
      rows = rows.slice(1); vals = vals.slice(1); notes.push('header row dropped');
    }
    // Label column: all text, with numbers beside it.
    if (width > 1 && vals.every((r) => !numeric(r[0])) && anyNumeric(vals.map((r) => r.slice(1)))) {
      rows = rows.map((r) => r.slice(1)); vals = vals.map((r) => r.slice(1)); notes.push('label column dropped');
    }
    if (!anyNumeric(vals)) return tbl.kind === 'column' ? null : { reject: 'No numbers in the table' };
    if (vals.some((r) => r.some((v) => v === null))) return { reject: 'The table has text cells, so it was pasted as text' };

    const units = new Set();
    vals.forEach((r) => r.forEach((v) => { if (numeric(v)) units.add(v.unit); }));
    if (units.size > 1) return { reject: 'The cells have different units, so it was pasted as text' };
    const unit = [...units][0] || '';

    const blanks = vals.reduce((n, r) => n + r.filter((v) => v.empty).length, 0);
    if (blanks || ragged) notes.push((blanks || 'missing') + (blanks ? ' empty cell' + (blanks > 1 ? 's' : '') : ' cells') + ' set to 0');
    const body = vals.map((r) => r.map((v) => (v.empty ? '0' : v.num)).join(', ')).join('; ');
    const matrix = '[' + body + ']' + (unit ? ' * ' + toLensUnit(unit) : '');
    return { matrix, rows: vals.length, cols: vals[0].length, kind: tbl.kind, notes };
  }

  // ---- the edit -------------------------------------------------------------
  const KINDS = { excel: 'Excel', markdown: 'Markdown', csv: 'CSV', column: 'column' };
  function freeName(t) {
    const used = new Set();
    for (const m of t.matchAll(/^\s*(~?[\p{L}_∀](?:_∞|[\p{L}\p{N}_∀])*)[`!@&]*\s*=(?!=)/gmu)) used.add(m[1].replace(/^~/, ''));
    for (const c of 'ABCDEFGHIJKLMNOPQRSTUVWXYZ') if (!used.has(c)) return c;
    return 'M';
  }

  function pasteEdit(text, clip, s, e, opts) {
    opts = opts || {};
    if (opts.textLine) return null;
    const r = toMatrix(clip);
    if (!r) return null;
    if (r.reject) return { message: r.reject };
    const ls = text.lastIndexOf('\n', s - 1) + 1;
    let le = text.indexOf('\n', e); if (le < 0) le = text.length;
    const blank = !text.slice(ls, s).trim() && !text.slice(e, le).trim();
    const out = (blank ? freeName(text) + ' = ' : '') + r.matrix;
    const from = blank ? ls : s;
    const msg = r.rows + '×' + r.cols + ' matrix from ' + KINDS[r.kind] + (r.notes.length ? ' (' + r.notes.join(', ') + ')' : '');
    return { from, to: e, insert: out, caret: from + out.length, message: msg };
  }

  const api = { parseTable, toMatrix, pasteEdit };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Paste = api;
})(typeof window !== 'undefined' ? window : globalThis);
