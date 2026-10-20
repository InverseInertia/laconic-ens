/* Mouse handling for a plot that the server drew (laconic/plotsvg.py).

   This file never draws the picture. While a drag or zoom is in progress it
   transforms the picture already on screen, so the view follows the pointer.
   When the gesture ends it reports the new axis range through `onPatch`, the
   page writes it into the worksheet as `xview:` / `yview:` lines, and the plot
   is redrawn from the text like any other edit. The text stays the only record.
   `xview` sits over any `xlim` the author wrote, so a reset removes only what the
   mouse added and returns to the author's view (or to automatic limits).

   Gestures (pan, zoom) come from d3-zoom, scales from d3-scale (static/vendor/d3).
   - drag in the plot: pan both axes
   - Ctrl + wheel, or a trackpad pinch, in the plot: zoom both axes about the pointer.
     A plain wheel is left alone so the results can still scroll
   - the same on the strip under or beside the axis: that axis only
   - double-click: back to the author's view (the strips reset just their axis)
   - hover: reads off the nearest point of the curve */
const PlotView = (() => {
  const NS = "http://www.w3.org/2000/svg";
  const num = (v) => String(Number(v.toPrecision(4)));
  const el = (tag, attrs = {}) => {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    return e;
  };

  // The scale for an axis as it was drawn (or as a gesture has moved it), pixels <-> data.
  const scaleFor = (axis, r0, r1, lim) =>
    (axis.scale === "log" ? d3.scaleLog() : d3.scaleLinear()).domain(lim).range([r0, r1]);

  // Where a point drawn at pixel p on `drawn` lands on `next`: an affine map a*p + b.
  function affine(drawn, next, r0, r1) {
    const f = (p) => next(drawn.invert(p));
    const p0 = f(r0), p1 = f(r1);
    const a = (p1 - p0) / (r1 - r0);
    return { a, b: p0 - a * r0 };
  }

  const moved = (a, b) => Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]) > 1e-9 * Math.abs(a[1] - a[0]);

  /* wrap: element holding the <svg>. plot: the spec the server drew it from.
     onPatch(patch) -> Promise<boolean>: writes the option changes into the text. */
  function attach(wrap, plot, onPatch) {
    const svg = wrap.querySelector("svg.lens-plot");
    if (!svg || !window.d3) return;
    const meta = JSON.parse(svg.dataset.lensPlot);
    const [L, T, W, H] = meta.box;
    const svgH = Number(svg.getAttribute("height"));
    const view = svg.querySelector(".pl-view");
    const grid = svg.querySelector(".pl-grid");

    const drawn = { x: scaleFor(meta.x, L, L + W, meta.x.lim), y: scaleFor(meta.y, T + H, T, meta.y.lim) };
    let cur = { x: meta.x.lim.slice(), y: meta.y.lim.slice() };   // limits a new gesture starts from
    let next = null;                                              // limits the gesture in progress has reached
    let resetting = false;

    const hit = (cls, x, y, w, h, cursor, tip) => {
      const r = el("rect", { class: "pl-hit " + cls, x, y, width: w, height: h, fill: "transparent" });
      r.style.cursor = cursor;
      if (tip) r.append(Object.assign(el("title"), { textContent: tip }));
      svg.append(r);
      return r;
    };
    const area = hit("pl-area", L, T, W, H, "grab",
      "Drag to pan. Ctrl + wheel to zoom. Double-click to reset the view");
    const xstrip = hit("pl-xaxis", L, T + H, W, Math.max(svgH - T - H, 0), "ew-resize",
      "Drag or Ctrl + wheel to change the x range. Double-click to reset it");
    const ystrip = hit("pl-yaxis", 0, T, L, H, "ns-resize",
      "Drag or Ctrl + wheel to change the y range. Double-click to reset it");

    // ---- pan and zoom ----
    function preview(t, mode) {
      const nx = mode === "y" ? cur.x : t.rescaleX(scaleFor(meta.x, L, L + W, cur.x)).domain();
      const ny = mode === "x" ? cur.y : t.rescaleY(scaleFor(meta.y, T + H, T, cur.y)).domain();
      next = { x: nx, y: ny };
      const ax = affine(drawn.x, scaleFor(meta.x, L, L + W, nx), L, L + W);
      const ay = affine(drawn.y, scaleFor(meta.y, T + H, T, ny), T + H, T);
      view.setAttribute("transform", `matrix(${ax.a} 0 0 ${ay.a} ${ax.b} ${ay.b})`);
      grid.style.opacity = 0;   // the tick labels do not move until the redraw, so grid lines that did would mislead
    }

    const zooms = [];
    function commit() {
      if (!next) return;
      const patch = {};
      if (moved(next.x, cur.x)) patch.xview = next.x;
      if (moved(next.y, cur.y)) patch.yview = next.y;
      const before = cur;
      if (Object.keys(patch).length) cur = next;
      next = null;
      resetting = true;                      // each overlay keeps its own transform; start the next gesture from identity
      zooms.forEach(([node, z]) => d3.select(node).call(z.transform, d3.zoomIdentity));
      resetting = false;
      if (!Object.keys(patch).length) return;
      Promise.resolve(onPatch(patch)).then((ok) => {
        if (ok === false) { cur = before; view.removeAttribute("transform"); grid.style.opacity = ""; }
      });
    }

    const bind = (node, mode) => {
      const x = Number(node.getAttribute("x")), y = Number(node.getAttribute("y"));
      const z = d3.zoom()
        .scaleExtent([1 / 100, 100])
        .extent([[x, y], [x + Number(node.getAttribute("width")), y + Number(node.getAttribute("height"))]])
        // d3's default is tuned for a trackpad pinch (small deltas with Ctrl held) and is ten times
        // too fast for a mouse wheel, where one notch is a delta of about 100.
        .wheelDelta((ev) => -ev.deltaY * (ev.deltaMode === 1 ? 0.12 : ev.deltaMode ? 1 :
          (ev.ctrlKey && Math.abs(ev.deltaY) < 40 ? 0.02 : 0.004)))
        .filter((ev) => ev.type === "wheel" ? (ev.ctrlKey || ev.metaKey) : (ev.type !== "dblclick" && !ev.button))
        .on("start", () => hideHover())
        .on("zoom", (ev) => { if (!resetting) preview(ev.transform, mode); })
        .on("end", () => { if (!resetting) commit(); });
      d3.select(node).call(z);
      zooms.push([node, z]);
    };
    bind(area, "xy"); bind(xstrip, "x"); bind(ystrip, "y");

    const reset = (keys) => onPatch(Object.fromEntries(keys.map((k) => [k, null])));
    area.addEventListener("dblclick", () => reset(["xview", "yview"]));
    xstrip.addEventListener("dblclick", () => reset(["xview"]));
    ystrip.addEventListener("dblclick", () => reset(["yview"]));

    // ---- hover read-out ----
    const tip = el("g", { "pointer-events": "none", class: "pl-hover" });
    const vline = el("line", { stroke: "#17253d", "stroke-width": 1, "stroke-dasharray": "3 3", y1: T, y2: T + H });
    const dot = el("circle", { r: 4, fill: "#fff", stroke: "#17253d", "stroke-width": 1.5 });
    const box = el("rect", { fill: "#fff", "fill-opacity": 0.94, stroke: "#17253d", "stroke-width": 1 });
    const label = el("text", { "font-size": 12 });
    tip.append(vline, dot, box, label);
    tip.style.display = "none";
    svg.append(tip);
    function hideHover() { tip.style.display = "none"; }

    area.addEventListener("pointerleave", hideHover);
    area.addEventListener("pointermove", (ev) => {
      if (ev.buttons || next) return hideHover();
      const [px, py] = d3.pointer(ev, svg);
      const xv = drawn.x.invert(px);
      let best = null;
      for (const s of plot.series) {
        const i = d3.bisectCenter(s.x, xv);
        for (const k of [i, i - 1, i + 1]) {
          if (k < 0 || k >= s.x.length || s.y[k] === null) continue;
          const d = Math.abs(drawn.y(s.y[k]) - py);
          if (!best || d < best.d) best = { d, s, x: s.x[k], y: s.y[k] };
          break;
        }
      }
      if (!best) return hideHover();
      const cx = drawn.x(best.x), cy = drawn.y(best.y);
      const u = (unit) => (unit ? " " + unit : "");
      label.textContent = `${plot.var} = ${num(best.x)}${u(plot.x.unit)},  ${plot.series.length > 1 ? best.s.label : "y"} = ${num(best.y)}${u(plot.y.unit)}`;
      vline.setAttribute("x1", cx); vline.setAttribute("x2", cx);
      dot.setAttribute("cx", cx); dot.setAttribute("cy", cy);
      tip.style.display = "";
      const bb = label.getBBox();
      const bx = Math.min(Math.max(cx + 10, L + 2), L + W - bb.width - 14);
      const by = cy - 12 - bb.height > T ? cy - 12 - bb.height : cy + 12;
      box.setAttribute("x", bx); box.setAttribute("y", by);
      box.setAttribute("width", bb.width + 8); box.setAttribute("height", bb.height + 4);
      label.setAttribute("x", bx + 4); label.setAttribute("y", by + bb.height - 2);
    });
  }

  return { attach };
})();
if (typeof module !== "undefined") module.exports = PlotView;
