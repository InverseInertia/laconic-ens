// Run with: node tests/test_layout.js
const assert = require('assert');
const L = require('../laconic/static/layout.js');
let n = 0;
function eq(a, b, label) { assert.deepStrictEqual(a, b, label); n++; }

// Starting: Auto goes by the width; with Auto off the stored view holds.
eq(L.initial({}, false), { auto: true, view: 'side', switches: 0, ask: false }, 'defaults: auto, wide window, side by side');
eq(L.initial({ auto: true, view: 'side' }, true).view, 'stacked', 'auto stacks a narrow window whatever was stored');
eq(L.initial({ auto: false, view: 'stacked' }, false).view, 'stacked', 'auto off keeps the stored view on a wide window');
eq(L.initial({ auto: false, view: 'side' }, true).view, 'side', 'auto off keeps the stored view on a narrow window');
eq(L.initial({ auto: false, view: 'sideways' }, false).view, 'side', 'an unknown stored view falls back to side by side');
eq(L.initial({ auto: null }, false).auto, true, 'a missing Auto setting means on');

// Crossing the width.
let s = L.initial({}, false);
s = L.crossed(s, true);
eq([s.view, s.switches], ['stacked', 1], 'narrowing stacks and counts');
s = L.crossed(s, false);
eq([s.view, s.switches], ['side', 2], 'widening goes back and counts');
const off = L.initial({ auto: false, view: 'side' }, false);
eq(L.crossed(off, true), off, 'auto off: crossing changes nothing');

// Picking by hand holds until the next crossing.
s = L.choose(L.initial({}, false), 'stacked');
eq(s.view, 'stacked', 'Alt+L on a wide window stacks');
eq(L.crossed(s, true).switches, 0, 'narrowing into the view already shown is not a switch');
eq(L.crossed(L.crossed(s, true), false).view, 'side', 'the next crossing goes by the width again');
eq(L.choose(s, 'nonsense').view, 'side', 'choose without a valid view flips it');
eq(L.other('side'), 'stacked', 'other');

// Turning Auto on goes by the width; turning it off keeps what is shown.
s = L.choose(L.initial({ auto: false, view: 'side' }, true), 'stacked');
eq(L.setAuto(s, false, true).view, 'stacked', 'auto off keeps the view');
eq(L.setAuto(L.initial({ auto: false, view: 'stacked' }, false), true, false).view, 'side', 'auto on snaps to the width');

// The offer to stop switching comes once, on the ASK_AFTER-th switch.
s = L.initial({}, false);
const asks = [];
for (let i = 0; i < 2 * L.ASK_AFTER; i++) { s = L.crossed(s, i % 2 === 0); asks.push(s.ask); }
eq(asks.filter(Boolean).length, 1, 'asked once');
eq(asks.indexOf(true), L.ASK_AFTER - 1, 'asked on the ASK_AFTER-th switch');
eq(L.choose(L.crossed(L.initial({}, false), true), 'side').ask, false, 'a hand choice never asks');

console.log(`layout: ${n} checks passed`);
