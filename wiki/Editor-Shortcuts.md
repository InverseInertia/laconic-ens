# Editor Shortcuts

The editor is a plain text box with extra keys that edit the source. **Settings → Reference** lists the keys inside the app; that list comes from `laconic/static/shortcuts.js`, and a test checks that every Ctrl and Alt shortcut in it is also described here.

## Math keys

These are off on comment lines and on the text lines under a plot (title, labels, notes). The **Math keys** checkbox switches them all off.

| Key | Effect |
|---|---|
| `/` | Fraction. Left term is the numerator, a term on the right (if any) the denominator, otherwise `a / ()` with the caret inside. After `A.` it gives `A ./ ` |
| `\` | Radical, `sqrt()`, or wraps the selection |
| `.` | Subscript after a name (`M.max` gives `M_max`). Decimal point after a number or unit |
| `^` | Exponent slot, `x^()` |
| `→` or `)` | Leave a slot. One simple term loses its parentheses: `x^(2)` becomes `x^2` |
| `= + - * -> .* ./` | Spaces are added around them. A sign (`-3`, `x^-1`) and `1e-3` stay tight |
| space | A second space in a row is ignored (indentation is left alone) |
| `,` `;` | A space is added after them. In an array `,` separates columns and `;` rows |
| `Backspace` | In an empty slot, removes the slot with its `^`, `/` or `sqrt`. After `, `, `; ` or a spaced operator, removes it with its spaces in one press |
| `Ctrl+M` | Array `[]`, or wraps the selection |
| `Ctrl+T` or `Alt+T` | Transpose the term on the left or the selection. Press again to undo |
| `Ctrl+G` | Greek letter for the character before the caret. Press again to revert |
| `Ctrl+[` , `Ctrl+Shift+[` | Wrap in `idx( , )` / `elem( , , )` |
| `Ctrl+/`, `Ctrl+\` | A literal `/` (spaced) or `\`, with no fraction or radical slot |
| `Enter` | With only closing brackets left on the line, finishes the line |
| `g` then space, operator, `(`, `)` or `Enter` | When `g` is a global from an earlier line, adds its `~`: `~g`. Not in a unit (`'g`), a function's own parameters or a comment |
| `Ctrl+Space` | Opens suggestions by hand. With text highlighted: pick a function to wrap it in |
| `Alt+Up`, `Alt+Down` | Grow the selection by one term-aware step, or step back |
| `Alt+Z` | Turn text wrapping in the editor on or off |
| `F2` | Rename the name at the caret everywhere |
| `Ctrl+S`, `Ctrl+Shift+S`, `Ctrl+O` | Save, Save As, Open |

Division is typed with the fraction key: `a`, `/`, then the denominator. Browsers reserve Ctrl+T and Ctrl+N, so use Alt+T in a normal tab.

## Highlighted text

With text highlighted, `/` `^` `\` `(` `[` `|` and Ctrl+M apply to the highlighted region instead of replacing it: `/` makes it the numerator, `^` the base of a power, `\` a square root, `(` and `[` wrap it in brackets, `|` takes `abs()`, and Ctrl+T transposes it. Brackets are added only when the region is more than one term.

The edit always applies to **whole terms**, however the text was highlighted. A term is a name, a number with its unit, a call, or a bracketed group, together with its exponents.

| Highlighted | Treated as |
|---|---|
| `2` in `12'kN` | `12'kN` |
| `x` in `x^2`, or the `2` | `x^2` |
| `sin` in `sin(a)` | `sin(a)` |
| `(a)` in `sin(a)` | `sin(a)` |
| `b)` in `f(a, b)` | `f(a, b)` |

So `^` on `1` inside `12'kN` gives `(12'kN)^()`. Highlighting spaces only is an ordinary replace, and a highlight across lines or with unmatched brackets is left alone with a message.

**Selecting by term:** double-click selects the whole term under the pointer. `Alt+Up` grows the selection one step at a time: term, product (`w * L^2 / 8`), sum (`... + c`), bracket contents, bracket with its function name, then the whole line, with `=`, `->`, `,` and `;` as boundaries. `Alt+Down` steps back. Selecting with the mouse or Shift+arrows is never snapped.

With text highlighted, `Ctrl+Space` offers functions to wrap it in: highlight `a+b`, press Ctrl+Space, type `sin`, press `Enter`, and you get `sin(a+b)`.

## Suggestions

Suggestions appear as you type, from the **Suggest** box in the header.

| After | Offers |
|---|---|
| `'` | units: your own and the machine's first, then common units (`kN`, `mm`, `GPa`) and everything Pint knows, matched by symbol or full name (`newt` finds `N`) |
| `!` | commands |
| two letters of a name | variables defined above (with their current value), your functions, built-in functions, `pi` and `e` |
| an indented line under `!root`, `!minimize`, `!maximize` | the block's options (`equation`, `objective`, `bounds x`, `method`, ...), inserted with their colon |
| `method:` / `autorun:` in a solver block | the methods that block kind takes, each with what it is for / `on`, `off` |
| the unknowns in `!root x, y` | variables defined above |
| `"` inside `props(` | the property keys (state inputs only where an input goes, with each key's meaning and SI unit) or, in the fluid's place, the CoolProp fluids, matched by alias too (`h2o` finds `Water`) |

`Tab` accepts, `Up`/`Down` choose, `Esc` closes. `Enter` accepts only after you have moved with the arrows, so it still ends the line when you just kept typing. A function is inserted with brackets and the caret inside, unless the word is already followed by `(`. A global is inserted with its `~`, whether or not you typed one. The props list loads the first time it is needed (CoolProp takes a few seconds to import), and Math keys leave text inside quotes alone, so `"1-Butene"` keeps its hyphen. The name left of `=`, function parameters and comment lines get no suggestions.

## Greek table

Ctrl+G uses a Mathcad-style table, editable under Settings → Greek: a→α, b→β, g→γ, d→δ, e→ε, z→ζ, h→η, q→θ, i→ι, k→κ, l→λ, m→μ, n→ν, x→ξ, o→ο, p→π, r→ρ, s→σ, t→τ, u→υ, f→φ, c→χ, y→ψ, w→ω, and `G D Q L X P S F Y W` for Γ Δ Θ Λ Ξ Π Σ Φ Ψ Ω. It also maps 8→∞. A table you edited before ∞ was added does not have that row: add it, or press Reset to defaults.
