/* The page's one client of the server (laconic/server.py): every request goes through here.
 *
 * The server answers a refusal in one of two ways, and this file is where the difference is kept:
 * an endpoint that can turn down what it was asked (a rename, a plot edit, saving units or tags)
 * answers 200 with {ok: false, error, ...}, which the caller reads like any other answer; a request
 * for something missing or impossible (no such job, no file to save to, a solver that cannot start)
 * is an HTTP error with {detail}, which json() and text() throw as an Error with that message.
 * A request that never reaches the server throws Error("Could not reach the server").
 * Runs under Node for tests, with a stand-in fetch.
 *
 *   json(path, body, method)     the answer's JSON. A body is sent as JSON; method: POST with a
 *                                body, GET without
 *   text(path, body, method)     the answer as text
 *   request(path, body, method)  the Response itself, whatever its status (a PDF that may not print)
 *   send(path, body, method)     a save that outlives the page (keepalive); PUT unless told.
 *                                Resolves to the Response; rejects only when unreachable
 *   beacon(path, body)           navigator.sendBeacon with a JSON body, for a page going away
 */
(function (root) {
  'use strict';

  const UNREACHABLE = 'Could not reach the server';

  async function request(path, body, method, keepalive = false) {
    const init = { method: method || (body === undefined ? 'GET' : 'POST') };
    if (body !== undefined) {
      init.headers = { 'Content-Type': 'application/json' };
      init.body = JSON.stringify(body);
    }
    if (keepalive) init.keepalive = true;
    try {
      return await root.fetch(path, init);
    } catch {
      throw new Error(UNREACHABLE);
    }
  }

  // An HTTP error as an Error: the server's `detail` when it gave one as text.
  async function refused(res) {
    let detail = null;
    try { detail = (await res.json()).detail; } catch {}
    return new Error(typeof detail === 'string' && detail ? detail : `Request failed (${res.status})`);
  }

  async function json(path, body, method) {
    const res = await request(path, body, method);
    if (!res.ok) throw await refused(res);
    return res.json();
  }

  async function text(path, body, method) {
    const res = await request(path, body, method);
    if (!res.ok) throw await refused(res);
    return res.text();
  }

  const send = (path, body, method = 'PUT') => request(path, body, method, true);

  const beacon = (path, body) =>
    root.navigator.sendBeacon(path, new Blob([JSON.stringify(body)], { type: 'application/json' }));

  const api = { UNREACHABLE, json, text, request: (path, body, method) => request(path, body, method), send, beacon };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Api = api;
})(typeof window !== 'undefined' ? window : globalThis);
