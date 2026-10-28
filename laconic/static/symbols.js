/* The symbol table of the last evaluation, as laconic/symbols.py built it.
 *
 * Each row of the eval response carries its line's part of the table: `symbols.defines`,
 * the symbols the line defines ({id, name, kind, line, until, global, value, params}), and
 * `symbols.uses`, [column, length, symbol id] of each name on it that means one. The
 * scope rules (~ globals, !clear and !clearf, local parameters, solver unknowns, failed
 * lines) are applied there; this file only reads the result. Runs under Node for tests.
 *
 *   table(rows)            every symbol, in the order the sheet defined them
 *   visible(table, line)   the symbols line `line` sees: defined above it, and not since
 *                          defined again or cleared
 *   globals(table)         name -> the symbol that made it global
 *   marks(row, table)      [column, length, name] of each use of a global on the row's line
 *   symbolMarks(row, table)  [column, length, name] of each use of a symbol (declared with $)
 *
 * Between a keystroke and the next eval response the page keeps using the last table.
 */
(function (root) {
  'use strict';

  function table(rows) {
    const out = [];
    for (const r of rows || []) if (r.symbols) out.push(...r.symbols.defines);
    return out.sort((a, b) => a.id - b.id);
  }

  const visibleAt = (s, line) => s.line < line && (s.until == null || line <= s.until);
  const visible = (tbl, line) => (tbl || []).filter((s) => visibleAt(s, line));

  function globals(tbl) {
    const out = new Map();
    for (const s of tbl || []) if (s.global && !out.has(s.name)) out.set(s.name, s);
    return out;
  }

  function marks(row, tbl) {
    if (!row || !row.symbols) return [];
    const byId = new Map((tbl || []).map((s) => [s.id, s]));
    return row.symbols.uses.filter(([, , id]) => byId.has(id) && byId.get(id).global)
      .map(([c, len, id]) => [c, len, byId.get(id).name]);
  }

  function symbolMarks(row, tbl) {
    if (!row || !row.symbols) return [];
    const byId = new Map((tbl || []).map((s) => [s.id, s]));
    return row.symbols.uses.filter(([, , id]) => byId.has(id) && byId.get(id).symbol)
      .map(([c, len, id]) => [c, len, byId.get(id).name]);
  }

  const api = { table, visible, globals, marks, symbolMarks };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Symbols = api;
})(typeof window !== 'undefined' ? window : globalThis);
