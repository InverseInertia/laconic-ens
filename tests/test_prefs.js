// Run with: node tests/test_prefs.js
const assert = require('assert');
const P = require('../laconic/static/prefs.js');
let n = 0;
function eq(a, b, label) { assert.deepStrictEqual(a, b, label); n++; }

const KEYS = ['theme', 'view', 'mathkeys'];

// A browser's storage as a Map; `broken` makes every call throw, as blocked storage does.
function storage(entries = {}, broken = false) {
  const m = new Map(Object.entries(entries));
  const guard = (f) => (...a) => { if (broken) throw new Error('SecurityError'); return f(...a); };
  return {
    map: m,
    getItem: guard((k) => (m.has(k) ? m.get(k) : null)),
    setItem: guard((k, v) => { m.set(k, String(v)); }),
    removeItem: guard((k) => { m.delete(k); }),
  };
}
// A server whose saves wait until released: sent holds each save's changes, in order.
function server() {
  const sent = [], waiting = [];
  return {
    sent,
    send: (changes) => new Promise((ok) => { sent.push(changes); waiting.push(ok); }),
    release: async () => { waiting.shift()(); for (let i = 0; i < 5; i++) await Promise.resolve(); },
  };
}

(async () => {
  // Preferences come from the server's values; other settings from the browser, as JSON.
  {
    const st = storage({ 'lens:text': '"x = 1"', 'lens:view': '"latex"' }), sv = server();
    const s = P.store({ keys: KEYS, values: { view: 'typeset' }, storage: st, send: sv.send });
    eq(s.get('view', null), 'typeset', 'a preference is the server\'s, not the browser\'s');
    eq(s.get('text', null), 'x = 1', 'other settings are the browser\'s');
    eq(s.get('splitH', 0.5), 0.5, 'default when there is none');
    eq(sv.sent, [], 'nothing to send: the server has view, and text is not a preference');
  }
  // Older builds' prefixes are read as a fallback, in order; a value that is not JSON comes back as text.
  {
    const st = storage({ 'calcsheet:text': 'plain', 'laconic:splitH': '0.3', 'calcsheet:splitH': '0.4' });
    const s = P.store({ keys: KEYS, values: {}, storage: st, send: server().send });
    eq([s.get('text'), s.get('splitH')], ['plain', 0.4], 'lens:, then calcsheet:, then laconic:');
  }
  // Setting: a preference goes to the server, anything else to the browser under lens:.
  {
    const st = storage(), sv = server();
    const s = P.store({ keys: KEYS, values: {}, storage: st, send: sv.send });
    s.set('view', 'latex');
    s.set('text', 'y = 2');
    eq(s.get('view'), 'latex', 'a preference set reads back at once');
    eq([sv.sent, [...st.map]], [[{ view: 'latex' }], [['lens:text', '"y = 2"']]], 'one save, one browser entry');
  }
  // One save at a time: what changes meanwhile goes in the next, merged.
  {
    const sv = server();
    const s = P.store({ keys: KEYS, values: {}, storage: storage(), send: sv.send });
    s.set('theme', { bg: 'a' });
    s.set('theme', { bg: 'b' });
    s.set('view', 'latex');
    s.set('theme', { bg: 'c' });
    eq(sv.sent, [{ theme: { bg: 'a' } }], 'the rest waits for the first save');
    await sv.release();
    eq(sv.sent[1], { theme: { bg: 'c' }, view: 'latex' }, 'then goes as one, with the last values');
    await sv.release();
    eq(sv.sent.length, 2, 'nothing more to send');
  }
  // A failed save does not stop the next one.
  {
    let calls = 0;
    const s = P.store({ keys: KEYS, values: {}, storage: storage(), send: () => { calls++; return Promise.reject(new Error('down')); } });
    s.set('view', 'latex');
    s.set('view', 'typeset');
    for (let i = 0; i < 5; i++) await Promise.resolve();
    eq(calls, 2, 'the waiting change goes after a failure');
  }
  // flush() sends what is waiting now, even while a save is on its way (the page is closing).
  {
    const sv = server();
    const s = P.store({ keys: KEYS, values: {}, storage: storage(), send: sv.send });
    s.set('view', 'latex');
    s.set('mathkeys', false);
    s.flush();
    eq(sv.sent, [{ view: 'latex' }, { mathkeys: false }], 'flushed without waiting');
  }
  // Preferences an older build kept in the browser are sent up once, when the store is made.
  {
    const st = storage({ 'lens:mathkeys': 'false', 'laconic:theme': '{"bg": "plain"}', 'lens:view': '"latex"' }), sv = server();
    const s = P.store({ keys: KEYS, values: { view: 'typeset' }, storage: st, send: sv.send });
    await sv.release();
    eq(sv.sent, [{ theme: { bg: 'plain' } }, { mathkeys: false }], 'sent up; view is on the server already');
    eq([s.get('mathkeys'), s.get('view')], [false, 'typeset'], 'read from the store at once');
  }
  // remove() forgets a browser setting under every prefix.
  {
    const st = storage({ 'lens:greek': '{}', 'calcsheet:greek': '{}', 'lens:text': '"t"' });
    const s = P.store({ keys: KEYS, values: {}, storage: st, send: server().send });
    s.remove('greek');
    eq([s.get('greek', null), [...st.map.keys()]], [null, ['lens:text']], 'removed everywhere');
  }
  // Storage that throws (blocked, private mode) leaves the browser settings empty and breaks nothing.
  {
    const sv = server();
    const s = P.store({ keys: KEYS, values: { view: 'latex' }, storage: storage({}, true), send: sv.send });
    s.set('text', 'x');
    s.remove('text');
    eq([s.get('text', 'none'), s.get('view')], ['none', 'latex'], 'blocked storage');
  }

  console.log(`prefs: ${n} checks passed`);
})().catch((e) => { console.error(e); process.exit(1); });
