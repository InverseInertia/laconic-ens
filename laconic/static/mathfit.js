/* Fitting typeset math to the width it has: the one rule the results pane (index.html) and the
 * PDF export (laconic/pdfdoc.py) share.
 *
 * A formula that fits is left alone. One a little too wide (it fits at MIN_ZOOM or more) is shrunk.
 * One much too wide is set again as one row per stage, as inline math, where KaTeX breaks a row
 * after a relation or a binary operator (= and +), and a row that still does not fit is shrunk.
 * CSS zoom (unlike transform) changes the layout box, so what follows takes the fitted size and
 * the PDF's page breaks are worked out from it. Fitting again at another width (the pane was
 * resized) can go back to the formula as it was. The width is the .math element's: the results
 * pane leaves room to spare at its right (index.html), so the pane can narrow a little before the
 * next fit without a shrunk formula running past its row.
 *
 *   choose(natural, room)       pure: 'fit', 'shrink' or 'wrap' for a formula `natural` px wide
 *                               in `room` px. Runs under Node for tests.
 *   set(el, tex, rows, opts)    typeset `tex` (display math) in `el`, a .math element, and keep
 *                               `rows` (the wrapped layout, one string per row) for fitAll.
 *                               opts: {katex: KaTeX options, after: (el) => {} once el is drawn}
 *   fitAll(scope, fresh)        fit every .math under scope to its width. `fresh` draws each one
 *                               again first (its size changed: the fonts loaded).
 */
(function (root) {
  'use strict';

  const MIN_ZOOM = 0.7;

  function choose(natural, room) {
    if (natural <= room) return 'fit';
    return room / natural >= MIN_ZOOM ? 'shrink' : 'wrap';
  }

  function draw(el, tex, opts, display) {
    const k = root.katex;
    if (k) k.render(display ? tex : '\\displaystyle ' + tex, el, { ...opts.katex, displayMode: display });
    else el.textContent = tex;   // KaTeX is not loaded yet; the caller draws again once it is
  }

  // The formula as one display: what set() draws and what fitAll goes back to.
  function whole(el, measure) {
    const s = el._mathfit;
    el.classList.remove('wrapped');
    draw(el, s.tex, s.opts, true);
    s.mode = 'whole';
    if (measure) s.natural = null;   // its width is measured in the document, by fitAll
    if (s.opts.after) s.opts.after(el);
  }

  function wrapped(el) {
    const s = el._mathfit;
    el.classList.add('wrapped');
    el.textContent = '';
    for (const row of s.rows) {
      const d = el.appendChild(el.ownerDocument.createElement('div'));
      d.className = 'wrow';
      draw(d, row, s.opts, false);
    }
    s.mode = 'wrap';
    if (s.opts.after) s.opts.after(el);
  }

  function set(el, tex, rows, opts) {
    el._mathfit = { tex, rows: rows && rows.length ? rows : [tex], opts: opts || {} };
    whole(el, true);
  }

  // Each step reads the layout once for every formula, then writes, so a long sheet is laid out
  // a few times per fit, not once per formula.
  function fitAll(scope, fresh) {
    const els = [...scope.querySelectorAll('.math')].filter((el) => el._mathfit);
    if (fresh) for (const el of els) whole(el, true);
    const rooms = els.map((el) => el.clientWidth);   // 0: not shown, so left until it is
    const todo = els.filter((el, i) => rooms[i] && el._mathfit.natural == null);
    const first = (el) => el.firstElementChild;
    for (const el of todo) if (first(el)) Object.assign(first(el).style, { zoom: '', width: 'max-content' });
    for (const el of todo) el._mathfit.natural = first(el) ? first(el).scrollWidth : 0;
    for (const el of todo) if (first(el)) first(el).style.width = '';
    els.forEach((el, i) => {
      const s = el._mathfit, room = rooms[i];
      if (!room) return;
      const want = choose(s.natural, room) === 'wrap' ? 'wrap' : 'whole';
      if (want !== s.mode) { if (want === 'wrap') wrapped(el); else whole(el, false); }
      for (const k of el.children) k.style.zoom = '';
    });
    const widths = els.map((el) => [...el.children].map((k) => k.scrollWidth));
    els.forEach((el, i) => {
      const room = rooms[i];
      if (!room) return;
      // A pixel short of the room: the widths read are whole pixels and KaTeX's boxes end a fraction
      // of one past them, so fitted to the room exactly some ran past it and their row scrolled (#104).
      [...el.children].forEach((k, j) => { if (widths[i][j] > room) k.style.zoom = String((room - 1) / widths[i][j]); });
    });
  }

  const api = { MIN_ZOOM, choose, set, fitAll };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.MathFit = api;
})(typeof window !== 'undefined' ? window : globalThis);
