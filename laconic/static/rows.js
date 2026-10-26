/* The row model: what the results pane shows for one eval row. The rows are LineResult.to_json()
 * (laconic/lineresult.py); this file is the page's one reader of their common fields, and the
 * per-kind table below is the one place that says what each line kind shows. index.html only
 * turns a model into DOM. Runs under Node for tests.
 *
 *   model(row, {view})  null for a line shown inside its block's row (a plot's or solver's
 *                       option lines), else {line, end, cls, body, warning, stale, copy}:
 *     line, end    the lines the row owns (a block header owns its block)
 *     cls          the row's class names
 *     body         {type: "text", text}             plain text
 *                  {type: "tex", tex}               typeset math
 *                  {type: "error", source, message} the line as typed and what is wrong
 *                  {type: "plot"} | {type: "solver"} drawn from the row's own payload
 *                  {type: "snippet", text, solver}  the LaTeX view; `solver`: add its controls
 *     warning      shown under the body, or ""
 *     stale        uses a solver result that is out of date
 *     copy         the LaTeX a Copy button copies, or null
 *   at(models, n)      the model whose row shows line n: the row of that line, else the block's
 *                      row that owns it, else null
 */
(function (root) {
  'use strict';

  const text = (r) => ({ type: 'text', text: r.text });
  const calc = (r) => (r.latex ? { type: 'tex', tex: r.latex } : { type: 'text', text: '' });

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
      body: snip ? { type: 'snippet', text: r.snippet, solver: !!r.solver } : make(r),
      warning: r.warning || '',
      stale: !!r.stale,
      copy: snip ? r.snippet : null,
    };
  }

  function at(models, n) {
    return models.find((m) => m.line === n) || models.find((m) => m.line <= n && n <= m.end) || null;
  }

  const api = { model, at };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Rows = api;
})(typeof window !== 'undefined' ? window : globalThis);
