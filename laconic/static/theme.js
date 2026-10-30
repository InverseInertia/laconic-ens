/* The page theme: fonts, text size, colors and editor paper, as data and pure functions.
 * The page owns the form and applies what these return; the server keeps the theme with the
 * other display preferences (laconic/settings.py).
 * Runs under Node for tests.
 *
 *   FONTS_SANS, FONTS_MONO   [label, CSS font-family] choices, chosen by index
 *   COLOR_FIELDS             [key, label] for each theme color
 *   PRESETS                  named color sets
 *   BACKGROUNDS              editor paper styles
 *   SIZES                    text size choices, in percent of the standard size
 *   defaults()               a fresh copy of the default theme
 *   contrast(a, b)           WCAG contrast ratio of two #rrggbb colors
 *   fromSaved(saved)         {theme, note}: a stored theme, validated; note says why it was reset
 *   presetOf(colors)         the preset with exactly these colors, or "custom"
 *   warning(colors)          the warning shown while text and paper are too close, or ""
 *   onInk(colors)            the color for text on an ink background
 *   highlight(colors)        {fill, text}: the chosen suggestion's fill, which must stand out from the paper, and its text
 *   cssVars(theme)           {"--name": value} for the document root (--fs is the text size as a scale)
 *   toYaml(theme)            the theme as a YAML snippet, to copy and share
 *   fromYaml(text, current)  {theme, error}: a pasted YAML snippet over the current theme
 */
(function (root) {
  'use strict';

  const FONTS_SANS = [
    ['IBM Plex Sans', '"IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif'],
    ['System UI', 'system-ui, -apple-system, "Segoe UI", sans-serif'],
    ['Helvetica / Arial', 'Helvetica, Arial, sans-serif'],
    ['Georgia (serif)', 'Georgia, "Times New Roman", serif'],
    ['Verdana', 'Verdana, Geneva, sans-serif'],
  ];
  const FONTS_MONO = [
    ['IBM Plex Mono', '"IBM Plex Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace'],
    ['System monospace', 'ui-monospace, "SF Mono", Menlo, Consolas, "DejaVu Sans Mono", monospace'],
    ['Consolas / Menlo', 'Consolas, Menlo, "DejaVu Sans Mono", monospace'],
    ['Courier', '"Courier New", Courier, monospace'],
    ['OCR-A', '"OCR-A", "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace'],
  ];
  const COLOR_FIELDS = [['paper', 'Paper'], ['text', 'Text'], ['ink', 'Ink'], ['grid', 'Grid lines'], ['rule', 'Rules'], ['err', 'Errors'], ['global', 'Globals'], ['symbol', 'Symbols']];
  const PRESETS = {
    'LENS blueprint': { paper: '#00386b', text: '#c2deff', ink: '#348fff', grid: '#0a4d88', rule: '#1f6fc4', err: '#ff8f00', global: '#7ee0c3', symbol: '#00e5ff' },
    'Engineering paper': { paper: '#e6eedf', text: '#17253d', ink: '#17253d', grid: '#c3d2bd', rule: '#9db39a', err: '#a8231b', global: '#1d6b55', symbol: '#00e5ff' },
    'White paper': { paper: '#fbfbf8', text: '#1b1b1b', ink: '#1b1b1b', grid: '#dcdcd4', rule: '#b5b5aa', err: '#b3261e', global: '#0f6e6a', symbol: '#00e5ff' },
    'Dark': { paper: '#1e2127', text: '#d9dde3', ink: '#d9dde3', grid: '#2c313a', rule: '#444b57', err: '#ff7b72', global: '#6fd3b8', symbol: '#00e5ff' },
    'Canoe Dark': { paper: '#120a02', text: '#f5cca3', ink: '#ff4d00', grid: '#2e1a05', rule: '#ff4d00', err: '#ff1100', global: '#7ee0c3', symbol: '#00e5ff' },
    'Chalcedony Dark': { paper: '#000000', text: '#1d5ec1', ink: '#1b5cc1', grid: '#323339', rule: '#1b5cc1', err: '#e33129', global: '#361086', symbol: '#00e5ff' },
    'Codec': { paper: '#050d0d', text: '#8fe3c8', ink: '#0f2a28', grid: '#2c5a55', rule: '#4fd1b5', err: '#e8321e', global: '#ffb347', symbol: '#00e5ff' },
  };
  const BACKGROUNDS = ['grid', 'lines', 'dots', 'plain'];
  // The editor's and the results' text, and the rows they line up on, scale together.
  const SIZES = [80, 90, 100, 110, 125, 150, 175, 200];
  // Below this ratio text is hard to read on its paper.
  const MIN_CONTRAST = 3;

  const defaults = () => ({ sans: 0, mono: 4, bg: 'grid', size: 100, colors: { ...PRESETS['LENS blueprint'] } });

  function contrast(a, b) {
    const lum = (h) => {
      const [r, g, bl] = [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
        .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
      return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
    };
    const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
  }

  const isColor = (v) => typeof v === 'string' && /^#[0-9a-f]{6}$/i.test(v);

  // Each stored field is kept only if it is valid; anything else keeps its default.
  function fromSaved(saved) {
    const theme = defaults();
    if (!saved || typeof saved !== 'object') return { theme, note: '' };
    if (Number.isInteger(saved.sans) && FONTS_SANS[saved.sans]) theme.sans = saved.sans;
    if (Number.isInteger(saved.mono) && FONTS_MONO[saved.mono]) theme.mono = saved.mono;
    if (BACKGROUNDS.includes(saved.bg)) theme.bg = saved.bg;
    if (SIZES.includes(saved.size)) theme.size = saved.size;
    const colors = saved.colors && typeof saved.colors === 'object' ? { ...saved.colors } : {};
    // Themes saved before text and ink were separate colors only have an ink, which was both.
    if (typeof colors.text !== 'string') colors.text = colors.ink;
    for (const [k] of COLOR_FIELDS) if (isColor(colors[k])) theme.colors[k] = colors[k];
    const jeb = Array.isArray(saved.jeb) ? COLOR_FIELDS.map(([k]) => k).filter((k) => saved.jeb.includes(k)) : [];
    if (jeb.length) theme.jeb = jeb;
    // Themes saved before symbols had a color get their preset's, else the default's.
    if (!isColor(colors.symbol)) {
      const like = Object.values(PRESETS).find((p) => COLOR_FIELDS.every(([k]) => k === 'symbol' || p[k].toLowerCase() === theme.colors[k].toLowerCase()));
      if (like) theme.colors.symbol = like.symbol;
    }
    // A saved palette whose text can't be read on its paper (all black, say) would leave the page
    // unusable and the Settings dialog unreachable by eye, so it falls back to the default colors.
    if (contrast(theme.colors.paper, theme.colors.text) < MIN_CONTRAST) {
      theme.colors = defaults().colors;
      return { theme, note: 'Your saved theme colors were unreadable (text too close to paper), so they were reset to the default theme.' };
    }
    return { theme, note: '' };
  }

  const sameColors = (a, b) => COLOR_FIELDS.every(([k]) => a[k].toLowerCase() === b[k].toLowerCase());
  const presetOf = (colors) => Object.keys(PRESETS).find((n) => sameColors(PRESETS[n], colors)) ?? 'custom';

  function warning(colors) {
    const ratio = contrast(colors.paper, colors.text);
    return ratio < MIN_CONTRAST
      ? `Warning: text and paper are hard to tell apart (contrast ${ratio.toFixed(1)}:1, at least ${MIN_CONTRAST}:1 is needed). On reload this theme is replaced by the default colors.`
      : '';
  }

  // Pressed and hovered buttons are filled with ink. Their text is the paper color, or the theme's
  // text color where that reads better (Codec's ink is nearly its paper); if neither can be read,
  // black or white.
  function onInk(colors) {
    const best = [colors.paper, colors.text].sort((a, b) => contrast(colors.ink, b) - contrast(colors.ink, a))[0];
    if (contrast(colors.ink, best) >= MIN_CONTRAST) return best;
    return contrast(colors.ink, '#000000') >= contrast(colors.ink, '#ffffff') ? '#000000' : '#ffffff';
  }

  // The chosen suggestion is filled with ink where ink stands out from the paper; where it does not
  // (Codec), with the rule or text color, whichever is first to; else whichever of them stands out most.
  // Its text is then the paper or text color that reads better on that fill, as on ink.
  function highlight(colors) {
    const options = [colors.ink, colors.rule, colors.text];
    const fill = options.find((c) => contrast(c, colors.paper) >= MIN_CONTRAST)
      ?? [...options].sort((a, b) => contrast(b, colors.paper) - contrast(a, colors.paper))[0];
    return { fill, text: onInk({ ...colors, ink: fill }) };
  }

  function cssVars(theme) {
    const c = theme.colors;
    const vars = { '--sans': FONTS_SANS[theme.sans][1], '--mono': FONTS_MONO[theme.mono][1], '--fs': String((theme.size ?? 100) / 100) };
    for (const [k] of COLOR_FIELDS) vars['--' + k] = c[k];
    vars['--paper-deep'] = `color-mix(in srgb, ${c.paper} 94%, ${c.text})`;
    vars['--text-soft'] = `color-mix(in srgb, ${c.text} 75%, ${c.paper})`;
    vars['--on-ink'] = onInk(c);
    const hl = highlight(c);
    vars['--hl'] = hl.fill;
    vars['--on-hl'] = hl.text;
    vars['--hit'] = `color-mix(in srgb, ${c.text} 8%, transparent)`;
    // The logo is recolored from the theme: its blues are ink, text and rule, its accent is the error color.
    for (const [k, v] of Object.entries({
      hi: `color-mix(in srgb, ${c.ink} 55%, ${c.text})`, lo: `color-mix(in srgb, ${c.paper} 94%, ${c.text})`, mid: c.ink, light: c.text, dark: c.rule,
      acc: c.err, grey: `color-mix(in srgb, ${c.text} 75%, ${c.paper})`, line: `color-mix(in srgb, ${c.paper} 35%, black)`,
    })) vars['--logo-' + k] = v;
    return vars;
  }

  // A snippet names fonts by their label, so it still means the same font if the lists are reordered.
  function toYaml(theme) {
    const preset = presetOf(theme.colors);
    return [
      '# LENS theme',
      `name: ${preset === 'custom' ? 'Custom' : preset}`,
      'fonts:',
      `  sans: ${FONTS_SANS[theme.sans][0]}`,
      `  mono: ${FONTS_MONO[theme.mono][0]}`,
      `background: ${theme.bg}`,
      `text-size: ${theme.size ?? 100}%`,
      'colors:',
      ...COLOR_FIELDS.map(([k]) => `  ${k}: '${theme.jeb?.includes(k) ? '#jeb' : theme.colors[k]}'`),
      '',
    ].join('\n');
  }

  // Reads the snippet toYaml writes: comments, `key: value` lines and one level of nesting. A
  // value may be quoted or not; an unquoted `#rrggbb` is taken as the color, not as a comment.
  function parseYaml(text) {
    const out = {};
    let section = null;
    for (const [i, raw] of String(text).split(/\r?\n/).entries()) {
      if (/^\s*(#|$)/.test(raw)) continue;
      const m = /^(\s*)([A-Za-z_][\w-]*)\s*:\s*(.*)$/.exec(raw);
      if (!m) throw new Error(`line ${i + 1} is not \`key: value\`: ${raw.trim()}`);
      const [, indent, key] = m;
      let value = m[3];
      const q = /^(['"])(.*)\1\s*(#.*)?$/.exec(value);
      if (q) value = q[2];
      else if (/^#[0-9a-f]{6}\b/i.test(value)) value = value.slice(0, 7);
      else value = value.replace(/\s+#.*$/, '').trim();
      if (!indent) {
        if (value === '') { section = key; out[key] = {}; } else { section = null; out[key] = value; }
      } else if (section) out[section][key] = value;
      else throw new Error(`line ${i + 1} is indented but belongs to no section: ${raw.trim()}`);
    }
    return out;
  }

  // Fields the snippet leaves out keep the current theme's values; a field it gets wrong, or text
  // that can't be read on its paper, rejects the whole snippet so nothing half-applies.
  function fromYaml(text, current) {
    let y;
    try { y = parseYaml(text); } catch (e) { return { theme: null, error: `Not a theme snippet: ${e.message}.` }; }
    const theme = { ...(current || defaults()), colors: { ...(current || defaults()).colors } };
    const bad = [];
    const fonts = y.fonts && typeof y.fonts === 'object' ? y.fonts : {};
    const font = (list, label, field) => {
      if (label === undefined) return;
      const i = list.findIndex(([name]) => name.toLowerCase() === String(label).toLowerCase());
      if (i < 0) bad.push(`unknown ${field} font "${label}"`); else theme[field] = i;
    };
    font(FONTS_SANS, fonts.sans, 'sans');
    font(FONTS_MONO, fonts.mono, 'mono');
    if (y.background !== undefined) {
      if (BACKGROUNDS.includes(y.background)) theme.bg = y.background;
      else bad.push(`unknown background "${y.background}" (one of ${BACKGROUNDS.join(', ')})`);
    }
    if (y['text-size'] !== undefined) {
      const size = Number(String(y['text-size']).replace(/\s*%$/, ''));
      if (SIZES.includes(size)) theme.size = size;
      else bad.push(`unknown text size "${y['text-size']}" (one of ${SIZES.map((n) => n + '%').join(', ')})`);
    }
    const colors = y.colors && typeof y.colors === 'object' ? y.colors : {};
    const jeb = new Set(theme.jeb ?? []);
    for (const [k, v] of Object.entries(colors)) {
      if (!COLOR_FIELDS.some(([f]) => f === k)) bad.push(`unknown color "${k}"`);
      else if (String(v).toLowerCase() === '#jeb') jeb.add(k);
      else if (!isColor(v)) bad.push(`${k} is not a #rrggbb color: ${v}`);
      else { theme.colors[k] = v.toLowerCase(); jeb.delete(k); }
    }
    if (jeb.size) theme.jeb = COLOR_FIELDS.map(([k]) => k).filter((k) => jeb.has(k)); else delete theme.jeb;
    if (!y.fonts && y.background === undefined && y['text-size'] === undefined && !y.colors) return { theme: null, error: 'Not a theme snippet: it has no fonts, background, text size or colors.' };
    if (bad.length) return { theme: null, error: `Theme not imported: ${bad.join('; ')}.` };
    if (contrast(theme.colors.paper, theme.colors.text) < MIN_CONTRAST) {
      return { theme: null, error: `Theme not imported: ${warning(theme.colors).replace(/^Warning: /, '').replace(/ On reload.*$/, '')}` };
    }
    return { theme, error: '' };
  }

  // jeb_
  function jebColor(ms) {
    const h = (ms / 30000) % 1 * 6, x = Math.round(255 * (1 - Math.abs(h % 2 - 1)));
    const [r, g, b] = [[255, x, 0], [x, 255, 0], [0, 255, x], [0, x, 255], [x, 0, 255], [255, 0, x]][Math.floor(h)];
    return '#' + [r, g, b].map((v) => v.toString(16).padStart(2, '0')).join('');
  }

  const api = { FONTS_SANS, FONTS_MONO, COLOR_FIELDS, PRESETS, BACKGROUNDS, SIZES, MIN_CONTRAST, defaults, contrast, fromSaved, presetOf, warning, onInk, highlight, cssVars, toYaml, fromYaml, jebColor };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Theme = api;
})(typeof window !== 'undefined' ? window : globalThis);
