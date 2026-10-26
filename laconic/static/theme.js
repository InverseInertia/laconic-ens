/* The page theme: fonts, colors and editor paper, as data and pure functions.
 * The page owns the form and localStorage; it applies what these return.
 * Runs under Node for tests.
 *
 *   FONTS_SANS, FONTS_MONO   [label, CSS font-family] choices, chosen by index
 *   COLOR_FIELDS             [key, label] for each theme color
 *   PRESETS                  named color sets
 *   BACKGROUNDS              editor paper styles
 *   defaults()               a fresh copy of the default theme
 *   contrast(a, b)           WCAG contrast ratio of two #rrggbb colors
 *   fromSaved(saved)         {theme, note}: a stored theme, validated; note says why it was reset
 *   presetOf(colors)         the preset with exactly these colors, or "custom"
 *   warning(colors)          the warning shown while text and paper are too close, or ""
 *   cssVars(theme)           {"--name": value} for the document root
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
  const COLOR_FIELDS = [['paper', 'Paper'], ['text', 'Text'], ['ink', 'Ink'], ['grid', 'Grid lines'], ['rule', 'Rules'], ['err', 'Errors'], ['global', 'Globals']];
  const PRESETS = {
    'LENS blueprint': { paper: '#00386b', text: '#c2deff', ink: '#348fff', grid: '#0a4d88', rule: '#1f6fc4', err: '#ff8f00', global: '#7ee0c3' },
    'Engineering paper': { paper: '#e6eedf', text: '#17253d', ink: '#17253d', grid: '#c3d2bd', rule: '#9db39a', err: '#a8231b', global: '#1d6b55' },
    'White paper': { paper: '#fbfbf8', text: '#1b1b1b', ink: '#1b1b1b', grid: '#dcdcd4', rule: '#b5b5aa', err: '#b3261e', global: '#0f6e6a' },
    'Dark': { paper: '#1e2127', text: '#d9dde3', ink: '#d9dde3', grid: '#2c313a', rule: '#444b57', err: '#ff7b72', global: '#6fd3b8' },
  };
  const BACKGROUNDS = ['grid', 'lines', 'dots', 'plain'];
  // Below this ratio text is hard to read on its paper.
  const MIN_CONTRAST = 3;

  const defaults = () => ({ sans: 0, mono: 4, bg: 'grid', colors: { ...PRESETS['LENS blueprint'] } });

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
    const colors = saved.colors && typeof saved.colors === 'object' ? { ...saved.colors } : {};
    // Themes saved before text and ink were separate colors only have an ink, which was both.
    if (typeof colors.text !== 'string') colors.text = colors.ink;
    for (const [k] of COLOR_FIELDS) if (isColor(colors[k])) theme.colors[k] = colors[k];
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

  function cssVars(theme) {
    const c = theme.colors;
    const vars = { '--sans': FONTS_SANS[theme.sans][1], '--mono': FONTS_MONO[theme.mono][1] };
    for (const [k] of COLOR_FIELDS) vars['--' + k] = c[k];
    vars['--paper-deep'] = `color-mix(in srgb, ${c.paper} 94%, ${c.text})`;
    vars['--text-soft'] = `color-mix(in srgb, ${c.text} 75%, ${c.paper})`;
    vars['--hit'] = `color-mix(in srgb, ${c.text} 8%, transparent)`;
    // The logo is recolored from the theme: its blues are ink, text and rule, its accent is the error color.
    for (const [k, v] of Object.entries({
      hi: `color-mix(in srgb, ${c.ink} 55%, ${c.text})`, lo: `color-mix(in srgb, ${c.paper} 94%, ${c.text})`, mid: c.ink, light: c.text, dark: c.rule,
      acc: c.err, grey: `color-mix(in srgb, ${c.text} 75%, ${c.paper})`, line: `color-mix(in srgb, ${c.paper} 35%, black)`,
    })) vars['--logo-' + k] = v;
    return vars;
  }

  const api = { FONTS_SANS, FONTS_MONO, COLOR_FIELDS, PRESETS, BACKGROUNDS, MIN_CONTRAST, defaults, contrast, fromSaved, presetOf, warning, cssVars };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Theme = api;
})(typeof window !== 'undefined' ? window : globalThis);
