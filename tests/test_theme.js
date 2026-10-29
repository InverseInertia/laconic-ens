// Run with: node tests/test_theme.js
const assert = require('assert');
const T = require('../laconic/static/theme.js');
let n = 0;
function eq(a, b, label) { assert.deepStrictEqual(a, b, label); n++; }
function ok(v, label) { assert.ok(v, label); n++; }

// Contrast is the WCAG ratio.
eq(T.contrast('#000000', '#ffffff'), 21, 'black on white');
eq(T.contrast('#ffffff', '#000000'), 21, 'order does not matter');
eq(T.contrast('#777777', '#777777'), 1, 'same color');
ok(Math.abs(T.contrast('#777777', '#ffffff') - 4.48) < 0.01, 'grey on white');

// Every preset is readable, and has every color.
for (const [name, p] of Object.entries(T.PRESETS)) {
  ok(T.contrast(p.paper, p.text) >= T.MIN_CONTRAST, `${name} readable`);
  eq(Object.keys(p).sort(), T.COLOR_FIELDS.map(([k]) => k).sort(), `${name} has every color`);
}

// defaults() is a fresh copy each time.
const d = T.defaults();
d.colors.paper = '#000000';
eq(T.defaults().colors.paper, T.PRESETS['LENS blueprint'].paper, 'defaults not shared');
eq([d.sans, d.mono, d.bg], [0, 4, 'grid'], 'default fonts and paper');

// Loading a saved theme.
eq(T.fromSaved(null), { theme: T.defaults(), note: '' }, 'nothing saved');
eq(T.fromSaved('dark'), { theme: T.defaults(), note: '' }, 'not an object');
eq(T.fromSaved({ sans: 2, mono: 3, bg: 'dots', colors: T.PRESETS.Dark }).theme,
  { sans: 2, mono: 3, bg: 'dots', size: 100, colors: T.PRESETS.Dark }, 'valid theme kept');
eq(T.fromSaved({ size: 125 }).theme.size, 125, 'text size kept');
eq([T.fromSaved({ size: 37 }).theme.size, T.fromSaved({ size: '125' }).theme.size], [100, 100], 'a size not offered falls back to 100%');
{
  const t = T.fromSaved({ sans: 99, mono: 1.5, bg: 'stripes', colors: { paper: '#fff', grid: 'red', err: '#ABCDEF' } }).theme;
  eq([t.sans, t.mono, t.bg], [0, 4, 'grid'], 'bad fonts and paper fall back field by field');
  eq([t.colors.paper, t.colors.grid, t.colors.err], [T.PRESETS['LENS blueprint'].paper, T.PRESETS['LENS blueprint'].grid, '#ABCDEF'],
    'bad colors fall back one by one, good ones are kept');
}
{
  // Before text and ink were separate, ink was both.
  const saved = { colors: { paper: '#ffffff', ink: '#112233' } };
  const t = T.fromSaved(saved).theme;
  eq([t.colors.text, t.colors.ink], ['#112233', '#112233'], 'old theme: text from ink');
  eq(saved.colors.text, undefined, 'the stored object is not changed');
}
{
  // Unreadable text resets the colors, but not the fonts, and says why.
  const r = T.fromSaved({ mono: 3, colors: { paper: '#000000', text: '#111111' } });
  eq(r.theme.colors, T.defaults().colors, 'unreadable colors reset');
  eq(r.theme.mono, 3, 'fonts survive a color reset');
  ok(/unreadable/.test(r.note), 'note explains the reset');
}

// Presets, and the live warning.
eq(T.presetOf({ ...T.PRESETS.Dark }), 'Dark', 'preset found');
eq(T.presetOf({ ...T.PRESETS.Codec }), 'Codec', 'Codec preset found');
eq(T.presetOf({ ...T.PRESETS.Dark, paper: T.PRESETS.Dark.paper.toUpperCase() }), 'Dark', 'case of the hex digits ignored');
eq(T.presetOf({ ...T.PRESETS.Dark, err: '#ff0000' }), 'custom', 'one color off is custom');
eq(T.warning(T.PRESETS['White paper']), '', 'no warning when readable');
eq(T.warning({ paper: '#000000', text: '#111111' }),
  'Warning: text and paper are hard to tell apart (contrast 1.1:1, at least 3:1 is needed). On reload this theme is replaced by the default colors.',
  'warning names the ratio');

// CSS variables.
{
  const v = T.cssVars({ sans: 3, mono: 0, bg: 'plain', colors: T.PRESETS.Dark });
  eq(v['--sans'], T.FONTS_SANS[3][1], 'sans font');
  eq(v['--mono'], T.FONTS_MONO[0][1], 'mono font');
  eq(v['--paper'], '#1e2127', 'color variable');
  eq(v['--logo-acc'], T.PRESETS.Dark.err, 'logo accent is the error color');
  eq(v['--paper-deep'], 'color-mix(in srgb, #1e2127 94%, #d9dde3)', 'derived color');
  eq(v['--fs'], '1', 'a theme saved before text sizes is at 100%');
  eq(T.cssVars({ ...T.defaults(), size: 150 })['--fs'], '1.5', 'text size as a scale');
}

// YAML snippets.
{
  const t = { sans: 3, mono: 1, bg: 'dots', size: 125, colors: { ...T.PRESETS['Chalcedony Dark'] } };
  const y = T.toYaml(t);
  ok(/^name: Chalcedony Dark$/m.test(y), 'snippet names its preset');
  ok(/^  sans: Georgia \(serif\)$/m.test(y), 'fonts by label');
  ok(/^  paper: '#000000'$/m.test(y), 'colors quoted, so # is not a comment');
  ok(/^text-size: 125%$/m.test(y), 'text size in percent');
  eq(T.fromYaml(y, T.defaults()), { theme: t, error: '' }, 'round trip');
  const d = T.defaults();
  eq(T.fromYaml('colors:\n  err: #ABCDEF  # bright\n', d).theme.colors, { ...d.colors, err: '#abcdef' }, 'unquoted hex, comments, left-out fields kept');
  eq(T.fromYaml('fonts:\n  mono: "courier"\n', d).theme.mono, 3, 'font labels ignore case');
  ok(/unknown sans font "Comic"/.test(T.fromYaml('fonts:\n  sans: Comic\n', d).error), 'bad font rejected');
  ok(/unknown color "lime"/.test(T.fromYaml('colors:\n  lime: "#00ff00"\n', d).error), 'bad color name rejected');
  ok(/hard to tell apart/.test(T.fromYaml("colors:\n  paper: '#000000'\n  text: '#111111'\n", d).error), 'unreadable rejected');
  eq(T.fromYaml('text-size: 90\n', d).theme.size, 90, 'text size with or without %');
  ok(/unknown text size "95%"/.test(T.fromYaml('text-size: 95%\n', d).error), 'a size not offered rejected');
  ok(/no fonts, background, text size or colors/.test(T.fromYaml('name: x\n', d).error), 'empty snippet rejected');
  ok(/line 1/.test(T.fromYaml('hello\n', d).error), 'garbage rejected');
  eq(d, T.defaults(), 'current theme not changed');
}

// Text on ink (a pressed or hovered button) takes whichever of paper and text reads better.
eq(Object.fromEntries(Object.entries(T.PRESETS).map(([n, p]) => [n, T.onInk(p) === p.paper ? 'paper' : 'text'])),
  { ...Object.fromEntries(Object.keys(T.PRESETS).map((n) => [n, 'paper'])), Codec: 'text' }, 'paper on ink, but text on Codec');
ok(Object.values(T.PRESETS).every((p) => T.contrast(p.ink, T.onInk(p)) >= T.MIN_CONTRAST), 'readable on every preset');
eq(T.onInk({ paper: '#777777', text: '#808080', ink: '#7a7a7a' }), '#000000', 'neither readable: black or white');
eq(T.cssVars({ ...T.defaults(), colors: T.PRESETS.Codec })['--on-ink'], T.PRESETS.Codec.text, 'as a CSS variable');

// Symbols are bright cyan on every preset.
eq(Object.values(T.PRESETS).map((p) => p.symbol), Object.values(T.PRESETS).map(() => '#00e5ff'), 'cyan symbols everywhere');

// A theme saved before symbols had a color gets its preset's symbol color, so it is still that preset.
{
  const { symbol, ...old } = T.PRESETS['Dark'];
  const t = T.fromSaved({ colors: old }).theme;
  eq(t.colors.symbol, symbol, 'old Dark theme gets Dark symbol color');
  eq(T.presetOf(t.colors), 'Dark', 'and is still the Dark preset');
  const custom = T.fromSaved({ colors: { ...old, err: '#123456' } }).theme;
  eq(custom.colors.symbol, T.defaults().colors.symbol, 'a custom one gets the default symbol color');
}

console.log(`theme: ${n} checks passed`);
