/* Which way the editor and the results are laid out: side by side, or stacked (results on top,
 * editor below).
 *
 * With Auto on (the default), the page stacks when the window is NARROW px wide or less and goes
 * back to side by side when it widens, each time the window crosses that width. Alt+L or the
 * Settings menu picks a view by hand: with Auto on it holds until the next crossing, with Auto off
 * it holds for good. If Auto switches the view ASK_AFTER times in one session, the page offers,
 * once, to turn it off. Runs under Node for tests.
 *
 *   initial({auto, view}, narrow)   the state a page starts in
 *   crossed(state, narrow)          the window crossed NARROW: the new state
 *   choose(state, view)             the user picked a view (Alt+L, Settings)
 *   setAuto(state, on, narrow)      the Auto box changed; turning it on goes by the width again
 *
 * A state is {auto, view, switches, ask}; ask is true on the one state that should show the offer.
 */
(function (root) {
  'use strict';

  const NARROW = 760;
  const ASK_AFTER = 6;
  const VIEWS = ['side', 'stacked'];

  const byWidth = (narrow) => (narrow ? 'stacked' : 'side');
  const other = (view) => (view === 'stacked' ? 'side' : 'stacked');

  function initial(prefs, narrow) {
    const auto = prefs.auto !== false;
    const view = auto ? byWidth(narrow) : VIEWS.includes(prefs.view) ? prefs.view : 'side';
    return { auto, view, switches: 0, ask: false };
  }

  function crossed(state, narrow) {
    const view = byWidth(narrow);
    if (!state.auto || view === state.view) return { ...state, ask: false };
    const switches = state.switches + 1;
    return { ...state, view, switches, ask: switches === ASK_AFTER };
  }

  const choose = (state, view) => ({ ...state, view: VIEWS.includes(view) ? view : other(state.view), ask: false });

  const setAuto = (state, on, narrow) => ({ ...state, auto: on, view: on ? byWidth(narrow) : state.view, ask: false });

  const api = { NARROW, ASK_AFTER, VIEWS, other, initial, crossed, choose, setAuto };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Layout = api;
})(typeof window !== 'undefined' ? window : globalThis);
