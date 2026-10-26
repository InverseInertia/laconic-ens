/* The keyboard shortcut table shown under Settings → Reference.
 *
 * The one list of the editor's keys: the page renders it, and a Node test checks
 * that every modifier shortcut here is also written up in wiki/Editor-Shortcuts.md.
 * Runs under Node for tests.
 *
 *   SECTIONS          [{title?, rows}], in display order
 *   combos()          every key combination in the table, as plain text ("Ctrl+Shift+[")
 *   rowHtml(row)      one <tr>
 *   tableHtml()       the <tr> rows of the table
 *
 * A row is {keys, text} where keys are combinations written as "Ctrl+M" (Up and Down
 * show as arrows) and `or` joins them with " or " instead of a line break; or
 * {code, text} for a code sample; or {label, text} for a plain label. text is HTML.
 * The `commands` section holds the worksheet commands, so it can be replaced on its own.
 */
(function (root) {
  'use strict';

  const SECTIONS = [
    { id: 'mathkeys', rows: [
      { keys: ['/'], text: 'Fraction. Takes the term on the left as numerator and the term on the right, if any, as denominator. <code>a/</code> gives <code>a/(&nbsp;)</code>. After <code>A.</code> it gives <code>A./</code>' },
      { keys: ['\\'], text: 'Radical. <code>sqrt(&nbsp;)</code>, or wraps the selection' },
      { keys: ['.'], text: 'Subscript after a name. <code>M.max</code> gives <code>M_max</code>. After a number it stays a decimal point' },
      { keys: ['^'], text: 'Exponent slot. <code>x^(&nbsp;)</code>' },
      { keys: ['→', ')'], or: true, text: 'Leave a slot. If it holds one simple term the parentheses go away: <code>x^(2)</code> becomes <code>x^2</code>' },
      { keys: ['Enter'], text: 'With only closing brackets left on the line, finishes the line instead of splitting it' },
      { keys: ['Backspace'], text: 'In an empty slot, removes the slot and its <code>^</code>, <code>/</code> or <code>sqrt</code>. After <code>, </code> or <code>; </code>, removes the separator and its space together' },
      { keys: ['Ctrl+M'], text: 'Array. <code>[&nbsp;]</code>, or wraps the selection' },
      { keys: [',', ';'], inline: true, text: 'A space is added after them automatically. In an array, <code>,</code> separates columns and <code>;</code> separates rows' },
      { keys: ['Ctrl+T', 'Alt+T'], text: 'Transpose the term on the left or the selection. Press again to undo. Browsers reserve Ctrl+T for a new tab, so use Alt+T in a normal tab' },
      { keys: ['Ctrl+[', 'Ctrl+Shift+['], text: 'Index the term on the left or the selection. Ctrl+[ gives <code>idx(A, i)</code>, typeset <code>A<sub>i</sub></code>: one element of a vector, or one row of a matrix. Ctrl+Shift+[ gives <code>elem(A, i, j)</code>, typeset <code>A<sub>i,j</sub></code>: row and column. The caret lands in the index slot. Counting starts at 1. Indexes can be indexed too: <code>idx(elem(A, 1, 2), 3)</code>' },
      { keys: ['Ctrl+G'], text: 'Greek letter for the character before the caret. Press again to go back. Edit the mapping under Greek' },
      { keys: ['Ctrl+/', 'Ctrl+\\'], text: 'Type a literal <code>/</code> or <code>\\</code> with no fraction or radical slot' },
      { keys: ['=', '+', '-', '*'], inline: true, text: 'Spaces are added around them (and around <code>-&gt;</code>, <code>.*</code>, <code>./</code> and fractions), and a second space is ignored. A sign (<code>-3</code>, <code>x^-1</code>) and <code>1e-3</code> stay tight. Backspace removes a spaced operator in one press' },
      { keys: ['`', '!', '@'], inline: true, text: 'After a variable name: <code>x`</code> puts a dot over it (<code>x``</code> two dots), <code>F!</code> an arrow, <code>a@</code> a hat. <code>F_x!</code> marks the F and keeps the subscript. Each marked name is a separate variable' },
      { keys: ['~'], text: 'A <code>~</code> on a variable or function definition makes the name global. Typing the name again on a later line adds its <code>~</code> as soon as the name is finished, so globals always read <code>~g</code>. Globals are tinted in the editor and colored and underlined in the results (the Mark globals box turns that off); hover one to see where it was defined. An assignment written without the <code>~</code> still changes the global, with a warning. Globals survive <code>!clear</code> / <code>!clearf</code>' },
    ] },
    { id: 'commands', rows: [
      { keys: ['!clearf'], text: 'On its own line, removes every non-global function above it' },
      { keys: ['!clear'], text: 'On its own line, removes every non-global variable above it' },
      { keys: ['!noassume', '!assume'], inline: true, text: 'Below <code>!noassume</code>, results keep the units that come out of the arithmetic (<code>kN*m</code>, not <code>J</code>) unless you convert with <code>-&gt;</code>. <code>!assume</code> returns to SI' },
      { keys: ['!short', '!long'], inline: true, text: 'Below <code>!short</code>, each line shows only its final result, with its unit but no intermediate steps. <code>!long</code> restores the full display' },
      { keys: ['!sigfigs n', '!sigfigsbig n', '!decplace n'], inline: true, text: 'Choose how many significant figures (4 by default; <code>!sigfigsbig</code> keeps trailing zeros, <code>2.500</code>) or decimal places results are displayed with. The last one given wins. Only the display is rounded; every calculation uses the full value' },
      { keys: ['!trigdeg', '!trigrad'], inline: true, text: 'Set the angle unit for <code>sin</code>, <code>cos</code>, <code>tan</code> on bare numbers, and for <code>asin</code>, <code>acos</code>, <code>atan</code> results. Radians by default; explicit units such as <code>30\'deg</code> always work' },
    ] },
    { id: 'units', rows: [
      { keys: ["'"], text: "Starts a unit: <code>12'kN/'m</code>. Bare names are always variables" },
      { code: "'smoot = 1.7018'm", text: "Defines a unit for this sheet. It works on every line, above or below. Units used by many sheets can be defined under Units, and are then copied into any file you save or export that uses them" },
    ] },
    { id: 'selection', title: 'Highlighted text', rows: [
      { keys: ['/', '^', '\\', '(', '[', '|'], inline: true, text: "Apply to the highlighted region: fraction numerator, base of a power, square root, brackets, array brackets, <code>abs()</code>. A highlight that cuts through a term is widened to the whole term first: <code>1</code> inside <code>12'kN</code> means the whole quantity, <code>x</code> in <code>x^2</code> means <code>x^2</code>, half a bracket pair means the pair" },
      { keys: ['Ctrl+Space'], text: 'With text highlighted: pick a function to wrap it in (<code>sin(&hellip;)</code>). Type to filter, <kbd>Enter</kbd> or <kbd>Tab</kbd> to apply. With nothing highlighted: opens suggestions by hand' },
      { label: 'Double-click', text: 'Selects the whole term under the pointer' },
      { keys: ['Alt+Z'], text: 'Turn text wrapping in the editor on or off' },
      { keys: ['Alt+Up', 'Alt+Down'], text: 'Grow the selection one step at a time: term, product, sum, brackets, outwards to the whole line. Alt+&darr; steps back' },
    ] },
    { id: 'suggestions', title: 'Suggestions', rows: [
      { keys: ['Tab'], text: "Accepts the highlighted suggestion. <kbd>&uarr;</kbd> <kbd>&darr;</kbd> choose, <kbd>Esc</kbd> closes. <kbd>Enter</kbd> accepts only after you have chosen with the arrows, otherwise it ends the line as usual. Suggestions appear after <code>'</code> (units), after <code>!</code> (commands), and after two letters of a name" },
    ] },
  ];

  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const KEY_NAMES = { Up: '&uarr;', Down: '&darr;' };
  // "Ctrl+Shift+[" is three keys; a lone "+" is the plus key.
  const kbd = (combo) => combo.split(/(?<=.)\+(?=.)/).map((k) => `<kbd>${KEY_NAMES[k] || esc(k)}</kbd>`).join('+');

  function keysHtml(row) {
    if (row.code !== undefined) return `<code>${esc(row.code)}</code>`;
    if (row.label !== undefined) return esc(row.label);
    return row.keys.map(kbd).join(row.or ? ' or ' : row.inline ? ' ' : '<br>');
  }

  const rowHtml = (r) => `<tr><td>${keysHtml(r)}</td><td>${r.text}</td></tr>\n`;
  const tableHtml = () => SECTIONS.map((s) =>
    (s.title ? `<tr><td colspan="2"><strong>${esc(s.title)}</strong></td></tr>\n` : '') + s.rows.map(rowHtml).join('')).join('');

  const combos = () => SECTIONS.flatMap((s) => s.rows.flatMap((r) => r.keys || []));

  const api = { SECTIONS, combos, rowHtml, tableHtml };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Shortcuts = api;
})(typeof window !== 'undefined' ? window : globalThis);
