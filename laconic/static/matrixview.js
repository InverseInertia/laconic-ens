/* Large matrices in the results pane: a matrix with more than LIMIT rows or columns is shown by
 * its corners (the first HEAD and last TAIL rows and columns, with ⋮, ⋯ and ⋱ between), and the
 * row offers to show it whole. The rule is the documents' too: laconic/exports.py collapses the
 * same way, and tests/matrix_vectors.json holds the two to it. Pure functions; runs under Node.
 *
 *   collapse(tex)   {tex, sizes}: `tex` with each large matrix collapsed, and the [rows, columns]
 *                   of each one collapsed (empty when nothing was). A matrix with another inside
 *                   it is left whole.
 *   label(sizes)    what the row's button says about them: "2 × 120", or "2 matrices"
 */
(function (root) {
  'use strict';

  const LIMIT = 8, HEAD = 3, TAIL = 2;
  const BMATRIX = /\\begin\{bmatrix\}((?:(?!\\begin\{)[\s\S])*?)\\end\{bmatrix\}/g;

  const keep = (items, filler) => (items.length <= LIMIT ? items : [...items.slice(0, HEAD), filler, ...items.slice(-TAIL)]);

  function collapse(tex) {
    const sizes = [];
    const out = tex.replace(BMATRIX, (whole, body) => {
      const rows = body.trim().split(/\s*\\\\\s*/).map((r) => r.trim().split(/\s*&\s*/));
      const width = Math.max(...rows.map((r) => r.length));
      if (rows.length <= LIMIT && width <= LIMIT) return whole;
      sizes.push([rows.length, width]);
      const cols = rows.map((r) => keep(r, '\\cdots'));
      const kept = keep(cols, keep(Array(width).fill('\\vdots'), '\\ddots'));
      return '\\begin{bmatrix} ' + kept.map((r) => r.join(' & ')).join(' \\\\ ') + ' \\end{bmatrix}';
    });
    return { tex: out, sizes };
  }

  function label(sizes) {
    return sizes.length === 1 ? `${sizes[0][0]} × ${sizes[0][1]}` : `${sizes.length} matrices`;
  }

  const api = { collapse, label, LIMIT };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.MatrixView = api;
})(typeof window !== 'undefined' ? window : globalThis);
