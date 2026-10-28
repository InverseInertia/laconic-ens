/* Where each of the page's settings is kept.
 *
 * Display preferences (the keys settings.PREFS lists, which the server writes into the page) live
 * in the server's settings.json, so they are the same whatever port the page is on; the server
 * also writes their values into the page, so they can be read before anything draws. Everything
 * else (the sheet text, the split) lives in this browser under "lens:"; older builds used
 * "calcsheet:" and "laconic:", read as a fallback. Preferences an older build kept in the browser
 * are sent up once, when the store is made, so nothing is lost. Runs under Node for tests.
 *
 *   store({keys, values, storage, send})  the page's store:
 *     get(k, d)    the value of k, or d when there is none
 *     set(k, v)    a preference goes to the server, anything else to the browser
 *     remove(k)    forget a browser setting, under every prefix
 *     flush()      send what is waiting now, even while a save is on its way (the page is closing)
 *
 *   keys      the preference keys; values: their stored values
 *   storage   getItem / setItem / removeItem, as localStorage (any of them may throw)
 *   send      (changes) => Promise: stores {key: value} on the server
 *
 * One save at a time; what changes meanwhile goes in the next, so a color picker, which saves the
 * theme on every move, sends a few requests rather than hundreds.
 */
(function (root) {
  'use strict';

  const PREFIX = 'lens:';
  const PREFIXES = [PREFIX, 'calcsheet:', 'laconic:'];

  function store({ keys, values, storage, send }) {
    const prefs = { ...values };
    let pending = {}, busy = false;

    function flush() {
      if (busy || !Object.keys(pending).length) return;
      const changes = pending;
      pending = {}; busy = true;
      let sent;   // sent now, not in a later task, so a save made as the page closes still goes
      try { sent = Promise.resolve(send(changes)); } catch (e) { sent = Promise.reject(e); }
      sent.catch(() => {}).finally(() => { busy = false; flush(); });
    }
    function savePref(k, v) { prefs[k] = v; pending[k] = v; flush(); }

    function stored(k) {
      for (const prefix of PREFIXES) {
        try {
          const raw = storage.getItem(prefix + k);
          if (raw === null || raw === undefined) continue;
          try { return { value: JSON.parse(raw) }; } catch { return { value: raw }; }
        } catch {}
      }
      return null;
    }

    const s = {
      get(k, d) {
        if (keys.includes(k) && k in prefs) return prefs[k];
        const b = stored(k);
        return b ? b.value : d;
      },
      set(k, v) {
        if (keys.includes(k)) { savePref(k, v); return; }
        try { storage.setItem(PREFIX + k, JSON.stringify(v)); } catch {}
      },
      remove(k) {
        for (const prefix of PREFIXES) try { storage.removeItem(prefix + k); } catch {}
      },
      flush() { busy = false; flush(); },
    };

    for (const k of keys) {
      if (k in prefs) continue;
      const b = stored(k);
      if (b && b.value !== null) savePref(k, b.value);
    }
    return s;
  }

  const api = { PREFIX, store };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Prefs = api;
})(typeof window !== 'undefined' ? window : globalThis);
