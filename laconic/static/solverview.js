/* The output side of `!root`, `!minimize` and `!maximize` blocks (laconic/solver.py).

   Evaluating the sheet never runs a solver; each block arrives with a status computed from a hash
   of everything it reads: "valid" (the result stored in the block matches), "stale" (the inputs
   changed since) or "none" (never run). This file draws the values and the small control strip
   under them, and drives runs through /api/solve/*:

     Run        solve now; the answer is written into the block as a `#@ result` line
     Auto       the block's `autorun: on` line: re-solve a quiet moment after its inputs change
     Interrupt  kill the worker process (the only way to stop a frozen calculation)
     Verify     solve again from the same start and compare with the stored result
     Log        the solver's log, or what is stored when nothing has run in this page

   The page is the host: `host.text()` is the sheet, and `host.edit(text, edits)` makes the edits a
   server endpoint returned for `text`, or says false when the sheet has changed since.

   Runs are remembered here by hash, not by line, so editing above a block does not lose track
   of it. A run whose inputs change underneath it is stopped and its result discarded. */
const Solvers = (() => {
  const runs = new Map();   // hash -> {state, log, message, verified}; state: failed, interrupted, timeout, done
  const tried = new Set();  // hashes that Auto has already started once, so a failure never loops
  let active = null;        // {job, hash, line, mode, since, t0}
  let host = null, rows = [], timer = 0, logHash = null;
  const $ = (s) => document.querySelector(s);

  const GLYPH = {ok: "✓", warn: "⚠", run: "⟳", none: "○", fail: "✕", stop: "■"};
  const pretty = (n) => (n === null || n === undefined ? "?" : n === 0 ? "0" : Number(n).toExponential(1).replace("e+0", "e+").replace("e-0", "e-"));
  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  };

  function init(h) { host = h; }

  const api = (path, body, method) => Api.json(path, body, method);   // api.js: an HTTP error throws its detail

  // ---- what to say about a block ------------------------------------------------------------
  function status(r) {
    const s = r.solver, run = runs.get(s.hash);
    const warnUp = s.tainted ? " It also uses out-of-date values from above." : "";
    if (active && active.hash === s.hash) {
      const secs = ((Date.now() - active.t0) / 1000).toFixed(1);
      return {sym: GLYPH.run, cls: "run", text: (active.mode === "verify" ? "Verifying" : "Running") + `… ${secs} s`};
    }
    if (s.status === "valid") {
      if (run && run.state === "failed") return {sym: GLYPH.warn, cls: "warn", text: `Could not verify: ${run.message}`};
      const v = run && run.verified;
      if (v && v.same === true) return {sym: GLYPH.ok, cls: "ok", text: `Verified: running it again gives the same result (difference ${pretty(v.diff)})` + warnUp};
      if (v && v.same === false) return {sym: GLYPH.warn, cls: "warn", text: `Running it again differs from the stored result (relative difference ${pretty(v.diff)}). Run to replace it.`};
      return s.tainted ? {sym: GLYPH.warn, cls: "warn", text: "Solved, but it uses out-of-date values from above"}
                       : {sym: GLYPH.ok, cls: "ok", text: "Up to date"};
    }
    if (run && run.state === "failed") return {sym: GLYPH.fail, cls: "fail", text: `Failed: ${run.message}`};
    if (run && run.state === "interrupted") return {sym: GLYPH.stop, cls: "fail", text: "Interrupted. Nothing was stored"};
    if (run && run.state === "timeout") return {sym: GLYPH.fail, cls: "fail", text: "Stopped: over its time limit"};
    if (s.status === "stale") return {sym: GLYPH.warn, cls: "warn", text: "Out of date: the inputs changed since this result was computed." + warnUp};
    return {sym: GLYPH.none, cls: "none", text: "Not run yet. The values shown are the starting values." + warnUp};
  }

  function paint(tools) {
    const r = tools._row, s = r.solver, st = status(r), busy = !!active, mine = busy && active.hash === s.hash;
    tools.dataset.state = st.cls;
    tools.querySelector(".s-sym").textContent = st.sym;
    tools.querySelector(".s-text").textContent = st.text;
    const run = tools.querySelector(".s-run");
    run.disabled = busy;
    run.title = s.tainted ? "Some values above are out of date; run those blocks first (this one may still run)" :
      busy ? "Another solver is running" : "Solve now and store the result in the worksheet";
    tools.querySelector(".s-auto").checked = s.autorun;
    tools.querySelector(".s-stop").disabled = !mine;
    const ver = tools.querySelector(".s-verify");
    ver.disabled = busy || s.status !== "valid";
    ver.title = s.status === "valid" ? "Solve again from the same start and compare with the stored result"
                                     : "Only an up-to-date stored result can be verified";
    const sub = tools.parentElement && tools.parentElement.querySelector(".s-sub");
    if (sub) sub.textContent = s.summary || "";
  }

  function repaint() {
    for (const t of document.querySelectorAll(".solver-tools")) if (t._row) paint(t);
    if (logHash) fillLog();
  }

  // ---- building the block -----------------------------------------------------------------------
  function tools(r) {
    const s = r.solver;
    const box = el("div", "solver-tools");
    box._row = r;
    box.dataset.hash = s.hash;
    const stat = el("span", "s-status");
    stat.append(el("span", "s-sym"), el("span", "s-text"));
    stat.setAttribute("role", "status");
    const btn = (cls, text, title, fn) => {
      const b = el("button", cls, text);
      b.type = "button"; b.title = title;
      b.onclick = async (ev) => { ev.stopPropagation(); try { await fn(); } catch (e) { host.say(e.message || "Failed"); } };
      return b;
    };
    const auto = el("label", "s-autolbl");
    const cb = el("input"); cb.type = "checkbox"; cb.className = "s-auto";
    cb.title = "Re-solve automatically a moment after the inputs change. Stored in the block as `autorun: on`";
    cb.onclick = (ev) => ev.stopPropagation();
    cb.onchange = async () => {
      try { await setAuto(r, cb.checked); } catch (e) { host.say(e.message || "Failed"); }
    };
    auto.append(cb, " Auto");
    box.append(stat,
      btn("s-run", "Run", "", () => start(r, "run")),
      auto,
      btn("s-stop", "Interrupt", "Stop the running solver (kills it, so even a frozen calculation ends)", () => interrupt()),
      btn("s-verify", "Verify", "", () => start(r, "verify")),
      btn("s-log", "Log", "Open the solver log", () => openLog(r)));
    paint(box);
    return box;
  }

  /* The body of a solver row: header, the values, the control strip. */
  function build(r, {values = true} = {}) {
    const s = r.solver;
    const box = el("div", "solver-box" + (Rows.stale(r) ? " is-stale" : ""));
    box.append(el("div", "s-head", Rows.head(r)));
    if (values) {
      const vals = el("div", "s-values");
      for (const v of s.values) {
        const d = el("div", "s-val");
        host.typeset(d, v.latex);
        vals.append(d);
      }
      box.append(vals);
    }
    box.append(tools(r), el("div", "s-sub", s.summary || ""));
    return box;
  }

  // ---- running ---------------------------------------------------------------------------------
  async function start(r, mode, auto = false) {
    const s = r.solver;
    if (active) { host.say("Another solver is running"); return; }
    if (auto) tried.add(s.hash);
    const {job} = await api("/api/solve/start", {text: host.text(), line: Rows.line(r), mode});
    active = {job, hash: s.hash, line: Rows.line(r), mode, since: 0, t0: Date.now()};
    const prev = runs.get(s.hash);
    runs.set(s.hash, {state: "running", log: [], message: "", verified: mode === "verify" ? null : prev && prev.verified});
    repaint();
    tick();
  }

  async function tick() {
    const a = active;
    if (!a) return;
    const run = runs.get(a.hash);
    let v;
    try { v = await api(`/api/solve/${a.job}?since=${a.since}`, undefined, "GET"); }
    catch (e) { return conclude(a, run, "failed", `Lost contact with the solver: ${e.message}`); }
    if (active !== a) return;   // interrupted or replaced while the request was in flight
    run.log.push(...v.log);
    a.since = v.next;
    if (v.state === "running") { repaint(); setTimeout(tick, 250); return; }
    if (v.state === "done") return finishOk(a, run, v.outcome);
    conclude(a, run, v.state === "failed" ? "failed" : v.state, v.error || "");
  }

  function conclude(a, run, state, message) {
    if (active === a) active = null;
    run.state = state;
    run.message = state === "failed" ? (message || "the solver failed") : message;
    repaint();
    schedule();
  }

  async function finishOk(a, run, outcome) {
    if (a.mode === "verify") {
      active = null;
      run.state = "done";
      run.verified = outcome.verify || null;
      if (run.verified && run.verified.same === null) { run.state = "failed"; run.message = run.verified.note; }
      repaint(); schedule();
      return;
    }
    try {
      // Edits fit only the text they were made for, so if the sheet changed on the way, ask again.
      // The store matches blocks by their inputs' hash, so typing elsewhere does not lose the result.
      let res, stored = false;
      for (let tries = 0; tries < 3 && !stored; tries++) {
        const text = host.text();
        res = await api("/api/solvestore", {text, record: outcome.record});
        if (!res.ok) break;
        stored = host.edit(text, res.edits);
      }
      if (res.ok && !stored) res = {ok: false, error: "The sheet kept changing, so the result was not stored"};
      active = null;
      run.state = "done";
      if (res.ok) host.say("Solved and stored");
      else { run.state = "failed"; run.message = res.error; run.log.push(res.error); }
    } catch (e) {
      active = null; run.state = "failed"; run.message = e.message;
    }
    repaint(); schedule();
  }

  async function interrupt(why) {
    const a = active;
    if (!a) return;
    active = null;
    const run = runs.get(a.hash);
    try { const v = await api(`/api/solve/${a.job}/interrupt`, {}); run.log.push(v.log[v.log.length - 1]); } catch {}
    run.state = "interrupted";
    if (why) run.log.push(why);
    repaint();
    schedule();
  }

  async function setAuto(r, on) {
    const text = host.text();
    const res = await api("/api/solveedit", {text, line: Rows.line(r), autorun: on});
    if (!res.ok) throw new Error(res.error);
    if (!host.edit(text, res.edits)) throw new Error("The sheet changed meanwhile; try again");
  }

  // ---- after each evaluation: stop orphaned runs, start auto-run blocks --------------------------
  function after(newRows) {
    rows = newRows.filter((r) => r.solver);
    if (active && !rows.some((r) => r.solver.hash === active.hash)) interrupt("The inputs changed while this was running, so the run was discarded.");
    repaint();
    schedule();
  }

  function schedule() {
    clearTimeout(timer);
    if (active) return;
    const stamp = host.text();
    timer = setTimeout(() => {
      if (active || host.text() !== stamp) return;
      // The first block that is out of date and not waiting on one above it. Blocks above that
      // have no Auto are left for the user, and everything that reads them is skipped.
      const next = rows.find((r) => r.solver.autorun && r.solver.status !== "valid" && !r.solver.tainted && !tried.has(r.solver.hash));
      if (next) start(next, "run", true).catch((e) => host.say(e.message));
    }, 700);
  }

  // ---- the log dialog ------------------------------------------------------------------------------
  function logText(r) {
    const s = r.solver, run = runs.get(s.hash), st = status(r);
    const out = [`Line ${Rows.line(r)}: ${Rows.head(r)}`, `Status: ${st.text}`, `Inputs hash: ${s.hash}   Method: ${s.method}   Time limit: ${s.timeout} s`, ""];
    if (run && run.log.length) out.push(...run.log);
    else if (s.record) {
      out.push("Nothing has run in this page yet. What the worksheet stores for this block:", "",
        `  method ${s.record.method}, ${s.record.nfev} evaluations, scipy ${s.record.scipy}`,
        `  ${s.record.message}`, `  stored for inputs ${s.record.hash}`);
    } else out.push("Nothing has run yet. Press Run.");
    if (s.note) out.push("", `Note: ${s.note}`);
    if (run && run.message && run.state !== "done") out.push("", `${run.state}: ${run.message}`);
    return out.join("\n");
  }

  function fillLog() {
    const dlg = $("#solverLogDlg");
    if (!dlg || !dlg.open) { logHash = null; return; }
    const r = rows.find((x) => x.solver.hash === logHash);
    const pre = $("#solverLogText");
    const atEnd = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 8;
    pre.textContent = r ? logText(r) : "This block changed or was removed.";
    if (atEnd) pre.scrollTop = pre.scrollHeight;
  }

  function openLog(r) {
    logHash = r.solver.hash;
    $("#solverLogTitle").textContent = `Solver log · line ${Rows.line(r)}`;
    $("#solverLogDlg").showModal();
    fillLog();
  }

  return {init, build, tools, after, interrupt, status, logText,
          get active() { return active; }, get runs() { return runs; }};
})();
if (typeof module !== "undefined") module.exports = Solvers;
