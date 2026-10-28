// Run with: node tests/test_api.js
const assert = require('assert');
const Api = require('../laconic/static/api.js');
let n = 0;
function eq(a, b, label) { assert.deepStrictEqual(a, b, label); n++; }

// A stand-in server: each request is logged; `answer` gives the status and body for a path.
const log = [];
function serve(answer) {
  globalThis.fetch = async (path, init) => {
    log.push([path, init]);
    const a = answer(path, init);
    if (a === 'down') throw new TypeError('Failed to fetch');
    const [status, body] = a;
    return {
      ok: status >= 200 && status < 300, status,
      json: async () => JSON.parse(body),
      text: async () => body,
    };
  };
}
const rejects = async (p) => { try { await p; } catch (e) { return e.message; } return null; };

(async () => {
  // A body goes as JSON by POST; no body is a GET; a method can be given.
  serve(() => [200, '{"ok": true}']);
  eq(await Api.json('/api/rename', { old: 'a' }), { ok: true }, 'answer');
  eq(log.pop(), ['/api/rename', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"old":"a"}' }], 'POST with JSON');
  await Api.json('/api/vocab');
  eq(log.pop(), ['/api/vocab', { method: 'GET' }], 'GET without a body');
  await Api.json('/api/tags', { tags: {} }, 'PUT');
  eq(log.pop()[1].method, 'PUT', 'method given');

  // A refusal the endpoint answers ({ok: false, error}, status 200) is the caller's to read.
  serve(() => [200, '{"ok": false, "error": "Line 3 is not a plot that draws"}']);
  eq(await Api.json('/api/plotedit', {}), { ok: false, error: 'Line 3 is not a plot that draws' }, 'ok false is an answer');

  // An HTTP error throws its detail, or the status when it has none.
  serve(() => [409, '{"detail": "Another solver is running"}']);
  eq(await rejects(Api.json('/api/solve/start', {})), 'Another solver is running', 'detail thrown');
  eq(await rejects(Api.text('/api/plotimage', {})), 'Another solver is running', 'text throws the same way');
  serve(() => [500, 'Internal Server Error']);
  eq(await rejects(Api.json('/api/eval', {})), 'Request failed (500)', 'no detail: the status');
  serve(() => [422, '{"detail": [{"msg": "field required"}]}']);
  eq(await rejects(Api.json('/api/eval', {})), 'Request failed (422)', 'a detail that is not text: the status');

  // request() hands back the Response whatever its status (the PDF export falls back on a 501).
  serve(() => [501, '{"detail": "no browser"}']);
  eq((await Api.request('/api/export/pdf', {})).status, 501, 'request does not throw');

  // A server that cannot be reached.
  serve(() => 'down');
  eq(await rejects(Api.json('/api/vocab')), Api.UNREACHABLE, 'unreachable');
  eq(await rejects(Api.request('/api/eval', {})), Api.UNREACHABLE, 'request throws only when unreachable');

  // send(): a PUT that outlives the page.
  serve(() => [200, '{"ok": true}']);
  await Api.send('/api/prefs', { prefs: { view: 'latex' } });
  eq(log.pop(), ['/api/prefs', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: '{"prefs":{"view":"latex"}}', keepalive: true }], 'send');
  await Api.send('/api/welcomed');
  eq(log.pop(), ['/api/welcomed', { method: 'PUT', keepalive: true }], 'send without a body');

  // beacon(): a JSON body for sendBeacon.
  const beacons = [];
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { sendBeacon: (path, blob) => { beacons.push([path, blob]); return true; } } });
  Api.beacon('/api/bye', { id: 'x' });
  eq([beacons[0][0], beacons[0][1].type, await beacons[0][1].text()], ['/api/bye', 'application/json', '{"id":"x"}'], 'beacon');

  console.log(`api: ${n} checks passed`);
})().catch((e) => { console.error(e); process.exit(1); });
