/* The row model: what the results pane shows for one eval row. The rows are LineResult.to_json()
 * (laconic/lineresult.py); this file is the page's one reader of their common fields, and the
 * per-kind table below is the one place that says what each line kind shows. index.html only
 * turns a model into DOM. Runs under Node for tests.
 *
 *   model(row, {view, expanded})  null for a line shown inside its block's row (a plot's or
 *                       solver's option lines), else {line, end, cls, body, warning, stale, copy}.
 *                       `expanded`: a Set of the lines whose large matrices are shown whole:
 *     line, end    the lines the row owns (a block header owns its block)
 *     cls          the row's class names
 *     body         {type: "text", text}             plain text
 *                  {type: "tex", tex, rows, matrix} typeset math, and the same one stage per row
 *                                                   for a pane too narrow for it (mathfit.js). A
 *                                                   matrix too large to read is collapsed to its
 *                                                   corners (matrixview.js) unless the line is
 *                                                   expanded; `matrix` is then {size, expanded}
 *                                                   for the button that toggles it, else null
 *                  {type: "error", source, message} the line as typed and what is wrong
 *                  {type: "plot"} | {type: "solver"} drawn from the row's own payload
 *                  {type: "snippet", text, solver}  the LaTeX view; `solver`: add its controls
 *     warning      shown under the body, or ""
 *     stale        uses a solver result that is out of date
 *     copy         the LaTeX a Copy button copies, or null
 *   at(models, n)      the model whose row shows line n: the row of that line, else the block's
 *                      row that owns it, else null
 *
 * And the common fields, for code that works on rows rather than models (solverview.js, plots,
 * the editor's marks):
 *   line(row)          the line it is for (a block's header line)
 *   head(row)          that line as typed, trimmed
 *   stale(row)         it uses a solver result that is out of date
 *   current(rows, lines)  for each line of the editor's text (lines[i] is line i + 1), its row
 *                      while the line still reads as it did when the row was made, else null
 */
(function (root) {
  'use strict';

  const text = (r) => ({ type: 'text', text: r.text });
  const MV = root.MatrixView || (typeof require === 'function' ? require('./matrixview.js') : null);

  function calc(r, opts) {
    if (!r.latex) return { type: 'text', text: '' };
    const rows = r.latex_rows || [r.latex];
    const small = MV.collapse(r.latex);
    if (!small.sizes.length) return { type: 'tex', tex: r.latex, rows, matrix: null };
    const expanded = !!(opts && opts.expanded && opts.expanded.has(r.n));
    const matrix = { size: MV.label(small.sizes), expanded };
    if (expanded) return { type: 'tex', tex: r.latex, rows, matrix };
    return { type: 'tex', tex: small.tex, rows: rows.map((x) => MV.collapse(x).tex), matrix };
  }

  // line kind -> its body, or null when the line has no row of its own. Other kinds are calculations.
  const BODY = {
    blank: () => ({ type: 'text', text: '' }),
    heading: text,
    comment: text,
    meta: text,
    command: (r) => ({ type: 'text', text: r.source.trim() + '  →  ' + r.text }),
    error: (r) => ({ type: 'error', source: r.source.trim(), message: r.error }),
    plot: () => ({ type: 'plot' }),
    solver: () => ({ type: 'solver' }),
    plotopt: null,
    solveropt: null,
  };

  function model(r, opts) {
    const make = Object.prototype.hasOwnProperty.call(BODY, r.kind) ? BODY[r.kind] : calc;
    if (make === null) return null;
    const snip = !!(opts && opts.view === 'latex' && r.snippet && r.kind !== 'error');
    return {
      line: r.n,
      end: r.end,
      cls: (snip ? 'row snip' : 'row ' + r.kind) + (r.stale ? ' stale' : ''),
      body: snip ? { type: 'snippet', text: r.snippet, solver: !!r.solver } : make(r, opts),
      warning: r.warning || '',
      stale: !!r.stale,
      copy: snip ? r.snippet : null,
    };
  }

  function at(models, n) {
    return models.find((m) => m.line === n) || models.find((m) => m.line <= n && n <= m.end) || null;
  }

  const line = (r) => r.n;
  const head = (r) => r.source.trim();
  const stale = (r) => !!r.stale;

  function current(rows, lines) {
    const byLine = new Map(rows.map((r) => [r.n, r]));
    return lines.map((l, i) => { const r = byLine.get(i + 1); return r && r.source === l ? r : null; });
  }

  const api = { model, at, line, head, stale, current };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Rows = api;
})(typeof window !== 'undefined' ? window : globalThis);
