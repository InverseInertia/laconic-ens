# Changelog

What changed in each release of LENS, newest first. The release job publishes a tag's section as
the body of its GitHub release (`packaging/release_notes.py`).

Every pull request that changes what a user sees or does adds a line under **Unreleased**, in the
group it belongs to (New, Changes or Fixes), naming its PR or issue. Pushing a release tag
renames **Unreleased** to the tag's heading and starts a new, empty **Unreleased** above it.

## Unreleased

### New
- Added herobrine
- **Show all the working with `!adnauseum`**: below it, each line shows every intermediate result, worked out innermost first, and every unit that cancels, struck through, with the result's units written out in SI base units and cancelled down when they differ from the arithmetic's. `!long` or `!short` ends it. (#146)

## [v0.5.1](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.5.1) (2026-10-30)

### New
- **Plot a vector of functions**: `!plot [f(x), g(x)], x = 0 .. 1`, or a function that gives a vector such as `F(x) = [x, x^2, x^3]`, draws one curve per entry, labelled by the entry (`f(x)`) or by its number (`F(x)_2`) and numbered with the other series for `color 2:` and the rest. (#144)
- **Humid air properties**: `haprops` gives the properties of moist air from CoolProp's `HAPropsSI`, such as the humidity ratio `w = haprops("W", "T", 25'degC, "P", 1'atm, "R", 0.5)`, the wet bulb (`"B"`), dew point (`"D"`), enthalpy and volume per kg of dry air. It takes the output key and three state inputs, one of them the pressure, converts their units as `props` does, and typing `"` inside it suggests the keys. See the wiki's Material Properties page. (#142)
- **Regression units and functions, and fits plotted over their points**: under `!regression`, `xunit:` and `yunit:` give data without units, such as a matrix pasted from a spreadsheet, its units, so the coefficients come out in theirs (with one name for every coefficient, `yunit:` is the unit of the vector), and `function: f(t)` makes the fitted polynomial a function you can call and plot below the block. A plot's `points:` without units are now read in the plot's `xunit:` and `yunit:`, so the points can be drawn over a fitted curve with units; without them, the line says which to add. Points in other units than the plot's can say so after the data, x's unit then y's: `points: D, 'ms, 'mm` (`auto` skips one). (#141)

### Changes
- **Plots are drawn after the math**: as you type, every calculation updates first and the plots follow one at a time, the one nearest the line you are on first. Under each plot a status line says whether it is still drawing (showing its last picture, dimmed) or up to date, and a plot whose lines and everything above them did not change comes back at once. (#141)
- **Blank lines no longer show in the results**: the empty lines you leave in the sheet to keep it readable are left out of the results pane, as the exports already left them out. (#143)

### Fixes
- **The Rename dialog takes extended characters and subscripts**: in F2's name fields, Ctrl+G now turns the letter before the caret into its extended character (`s` into σ) and a period after a name types the subscript underscore (`σ.max` gives `σ_max`), as in the editor, so a name can be renamed to one with Greek letters. (#139)

## [v0.5.0](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.5.0) (2026-10-29)

### New
- **Spellcheck in comments and headings**: while you type a comment, heading or plot title line, the browser's spellchecker underlines misspelt words, until the caret moves to a calculation; it stays off while you edit calculations, so names and units are not marked. On Linux, LENS also switches spellcheck on in its app window's own browser profile, with a dictionary for your language, since that profile does not have your browser's settings. (#121)
- **Changelog in Help**: the bottom of the Help window lists what changed in each release, and the **Changelog** link beside the version at the top jumps to it. (#122)
- **Symbolic math**: declare symbols with a `$` on a line of their own (`$m, $a, $F`; `~$g` for a global one), and an expression over them, such as `p = m*a`, is worked out by sympy and shown as math. A `!symsolve a` block with `equation: F = m*a` lines solves for symbols as you type, and below it `a` holds `F/m` (with several solutions, `pick: 2` chooses one). Once the symbols have values (`m = 2'kg`, `F = 10'N`), `acc = a` works out to `5 m/s²`, units and all; a number with units cannot go into a result that is still symbolic, and the line says so. Symbols are shown in their own theme color, bright cyan unless you change it (Settings → Theme → Symbols), in the editor and the results, and hovering one names its declaration; only globals are underlined, so a global symbol is in the symbol color and underlined. `!clearsym` removes the non-global symbols and keeps other variables. The LaTeX, Markdown and PDF exports typeset the results. See the wiki's Symbolic Math page. (#123)
- **Regression with any model, in one or more variables**: a `model:` line under `!regression` fits that function instead of a polynomial, such as `model: f(t) = A*exp(-k*t)` with `!regression A, k`, or `model: w(x, z) = a + b*x + c*z` with `data: x, z, w` (one vector per variable, then y, or a matrix with a row for each). Each coefficient gets the units that make the model come out in y's units; the fit starts from a coefficient's value above the block, when it has one, and below the block the model is a function you can call or plot, `f(2's)`. (#128)
- **Loops**: a `!loop i = 1 .. n` block runs the lines indented under it once for each i, for a sum over an index or a matrix built entry by entry. A line assigns a name (`S = S + i^2`) or an entry of a vector or matrix made above (`idx(v, i) = ...`, `elem(M, i, j) = ...`), and a `!loop` inside it, indented further, runs for each pass (`!loop j = 1 .. i`). Below the block each name holds its last value; the row shows the block as steps (`for i = 1, …, n`, `S ← S + i²`) and the values it left, and the exports print it the same way. A line that fails says at which index values. (#131)
- **Points on plots**: a `points:` line under a plot draws a set of points as markers over its curves, given as `!regression` takes its data: `points: D` (a matrix with an x row and a y row) or `points: t, s` (two vectors, units and all). A plot header with no range, `!plot t, s` or `!plot D`, plots points alone, with axes fitted to them. Points are styled like any series (`color 2: red`, `marker 2: square`) and export to SVG, PNG and LaTeX. (#127)
- **Text size**: Settings → Theme → Text size makes the editor's and the results' text larger or smaller, from 80% to 200%, keeping the lines of the two side by side. It is part of the theme, so Reset theme and the YAML snippet include it. (#140)
- **Update from inside LENS**: when a newer release is out, a small button with its version appears beside the version in the header. Click it for the release's notes and an **Update** button: on Windows it downloads and starts the new setup wizard, and on Linux it runs the installer kept in the LENS folder and opens LENS again when it is done. LENS asks GitHub once when it starts and stays quiet offline; Settings → Updates turns the check off. The Linux installer now keeps a copy of itself in the install folder for this, so updates from inside LENS work once you have installed with this release's installer. (#134)
- **`!hide` and `!show`**: the lines below `!hide` still run and define their names, but their results, plots and comments are left out of the results pane and the LaTeX, Markdown and PDF exports until `!show`, so working you need can stay out of the printout. Errors are never hidden, and a solver block that needs running stays in sight until its result is current. (#135)

### Changes
- **Every command is marked in the results**: plots, `!root`/`!minimize`/`!maximize`, `!regression`, `!symsolve` and `!loop` blocks are now headed in the results by the `!` line they were called with, in the same style as one-line commands such as `!long` and `!short`, so you can see which commands ran as you scroll. The exports still leave these marks out. (#136)
- **The editor scrolls past the last line**: as in most code editors, you can scroll half a page beyond the end of the sheet, so the line you are typing at the bottom of a long sheet can sit in the middle of the screen. (#129)
- **∀ for volume is now typed as the ∀ character**: press Ctrl+G after a `V` (again to go back), and the worksheet keeps the ∀ itself, as in `∀_cv = 0.2'm^3`. A name spelled `forall` is an ordinary name again; replace it with ∀ to keep the symbol. A table you edited earlier (Settings → Extended characters) needs a `V`→`∀` row, or Reset to defaults. (#125)
- **Greek letters is now Extended characters**: the Ctrl+G table in Settings is called Extended characters, since it holds ∞ and ∀ as well as Greek letters. The table itself is unchanged. (#140)

### Fixes
- **A vector of regression coefficients keeps its orientation**: with one name and `degree:`, `!regression p` gave a vector that was shown as a column in the results and as a row in its plain text, whatever the data. It now lies as the data does: a row for a matrix's x row or a row vector of x values, a column for a column vector, everywhere it is shown and when used below. (#126)
- **Function parameters are spelled like any variable**: a parameter with a mark, such as `` SWEP_B26W(V`) = ... `` or `f(x!) = ...`, was a syntax error, and the function was then unknown to every line below. A parameter may now carry the `` ` ! @ & `` marks, as well as be ∀ (`f(∀) = 2*∀`). A number directly before a name in a function's body (`f(∀) = 2∀`) now says to write `2*∀`, where it showed an internal error. (#132)
- **Pressed buttons and suggestions are readable on every theme**: on Codec, the pressed Typeset or LaTeX button, a hovered button and the chosen suggestion had dark text on a dark fill, and the chosen suggestion's fill could hardly be told from the list. Their text now takes the theme's paper or text color, whichever stands out more from the fill, and the suggestion list's highlight and border use the rule or text color wherever the ink would not stand out from the paper. (#140)
- **Typing a block works the same under every block command**: under `!plot`, the editor now suggests the plot's options as you type an indented line (`title`, `xlim`, `color`, `points`, ...), and the values of those with a few choices (`grid: on`, `xscale: log`, `color: red`), as it already did under `!root`, `!minimize`, `!maximize`, `!regression` and `!symsolve`; it no longer offers variable names in a plot's numbers and sizes. Pressing Enter after any block header, `!loop` included, or after one of its indented lines, now indents the new line to match (a loop inside a loop two spaces further), and Enter on a line that is only that indent removes it to leave the block. (#137)

## [v0.4.5](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.4.5) (2026-10-28)

### Fixes
- **After an update the app window works again**: in the Chromium app window, an update could leave the button icons missing, Help not opening and every button except Save doing nothing, because the browser kept running the previous version's scripts against the new page. LENS now names its files by version and has the browser check them with LENS each time, so an update takes effect at once. If an update before this one left the window broken, this update fixes it too. (#119)

## [v0.4.4](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.4.4) (2026-10-28)

### New
- **Hz or rad/s**: `!freq hz` or `!freq rad` says what a sheet's frequencies are. Below either, Hz is cycles per second, so `50'Hz -> 'rad/'s` is `314.2 rad/s`, `3000'rpm -> 'Hz` is `50 Hz` and `314.2'rad/'s -> 'Hz` is `50 Hz`, and a result in 1/s such as `sqrt(k/m)` is shown in Hz or in rad/s as you chose. Without it, Hz and rad/s stay the same unit as in SI (1 Hz = 1 rad/s), and a conversion between them shows a note saying so. (#115)
- **Codec** theme preset: mint text on near-black paper, with amber globals. Pick it in Settings → Theme. (#112)
- **A bar over a variable**: type `&` after a name, as with the dot, arrow and hat marks: `u&` is ū, `F_x&` is F̄ₓ, and it combines with the others (``v&` `` is a dotted v̄). `u&` is a variable of its own, apart from `u`. (#111)
- **∀ for volume**: a name spelled `forall` typesets as ∀, the struck-through V some fluid mechanics texts use for volume so that V can stay velocity, with subscripts and marks like any name (`forall_cv`). (#111)
- **Strain units**: a unit typed over itself, such as `'mm/'mm` or `'in/'in`, now stays a unit ratio instead of cancelling to a plain number, with or without `!noassume`. Write `0.002'mm/'mm`, or convert a computed strain with `-> 'mm/'mm`; it shows as `0.0025 mm/mm` and drops out when multiplied by another unit (`e * 200'GPa` is a stress). (#114)
- **Polynomial regression**: a `!regression a, b, c` block with `data: D` fits y = a + b·x + c·x² by least squares to points given as a matrix with an x row and a y row (one column per point), or as two vectors, `data: t, s`. Each coefficient gets the units of y / xᵏ, the names hold the fit for the lines below, `r2: R2` names R², and one name with `degree: 3` holds every coefficient as a vector. The fit is worked out as you type, with no Run button, and the row shows the fitted polynomial. (#113)
- **Large matrices are shown collapsed**: a matrix with more than 8 rows or columns shows its first and last few with ⋯ and ⋮ between, and a **Show all** button under it shows it whole. The LaTeX, Markdown and PDF exports print it collapsed too; a line's LaTeX snippet keeps it whole. (#113)

### Changes
- **Export → PDF is quicker**: it now opens the print dialog straight away, where **Save as PDF** saves the same pages as before, instead of starting a hidden copy of Chrome or Edge for every export, which took up to ten seconds. `lens FILE --pdf` still writes the PDF directly. (#118)

### Fixes
- **The reduced Planck constant `'hbar`** (or `'ħ`) typesets as ħ (`\hbar`) on the page and in the LaTeX export, where it used to show as a text glyph that KaTeX warned about and pdflatex could not print. (#111)
- A long equation shrunk to fit the results pane no longer keeps a scroll bar under it at some pane widths, so the bar no longer comes and goes while you resize the window or the split. Math now leaves a little room at the right of the pane, so a pane narrowed during a resize does not show a scroll bar before the equation is shrunk to the new width. (#104)

## [v0.4.3](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.4.3) (2026-10-28)

### New
- **LENS is open source under the MIT License.** The Windows and Linux installs now include it as `LICENSE.txt`, next to `THIRD-PARTY-NOTICES.txt` with the licenses of the Python libraries bundled with LENS. (#116)

### Changes
- Math keys and suggestions now work in a plot note's position, `at (x, y)`, and math keys are off on a solver's `method:` line, matching what the sheet treats as math. (#116)
- A failed plot image export, or a failed save back to the file LENS was opened with, now shows the server's message instead of raw JSON or "undefined". (#116)

### Fixes
- Resetting the Greek table no longer brings back a copy an older version left in the browser. (#116)
- Help no longer says the theme is kept per browser; settings are stored on this machine for every browser. (#116)
- `lens FILE --solve` stores an answer in every solver block with the same inputs, as the page does. The second of two identical blocks no longer stays NOT SOLVED. (#116)

## [v0.4.2](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.4.2) (2026-10-28)

### Changes
- **Scroll bars follow your theme**: the scroll bars under long lines of math, in the editor and in dialogs take their colors from the theme (its Rules color on a slightly deeper paper) instead of the browser's defaults, for every preset and for custom and shared themes. (#99)

### Fixes
- In a narrow window, where the toolbar wraps onto several rows, the Export menu opens fully inside the window instead of mostly off its left edge, and it stays inside if you resize the window while it is open. (#103)
- **Export → PDF shows that it is working and never asks to allow pop-ups.** The Export button reads *Exporting PDF…* until the PDF is ready; clicking again meanwhile does nothing. When LENS cannot print the PDF itself, the print dialog opens on the same page (choose **Save as PDF**) instead of in a pop-up window the browser could block, and later exports go straight to it. A Chromium build that stalled the PDF print until it timed out now prints normally. (#102)
- **No scroll bar flicker when a long equation is shrunk to fit.** Making the results pane narrower (the window, the split or the layout) no longer flashes a scroll bar under an equation for a moment while it is shrunk to the new width. (#104)

## [v0.4.1](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.4.1) (2026-10-28)

### Fixes
- **Linux: updating from v0.3.6 works again.** The `lens-install-linux.sh` you got with v0.3.6 or earlier looked for a single-file program that releases no longer have, so running it again failed to update, even after removing LENS. From the next release it installs that release with the new installer, and `lens-install-linux-v2.sh` still works as before. The installer also stops a LENS left running from the old install, which would otherwise open in place of the new one, so the menu kept showing the old version. (#101)

## [v0.4.0](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.4.0) (2026-10-27)

### New
- **Chalcedony Dark** theme preset: blue on black. (#100)
- **Share themes as YAML**: Settings → Theme → Share as YAML exports your theme as a YAML snippet, copied to the clipboard, and imports a snippet pasted back in. Fields the snippet leaves out keep their current values, and a snippet with an unknown or invalid field, or unreadable colors, is refused with a note saying why. (#100)
- **Windows installer**: `lens-<version>-windows-x64-install-wizard.exe` is a setup wizard. It installs LENS for your user (no administrator) with a Start menu entry, an optional desktop shortcut, the example worksheets, and `.lens` files opening in LENS with their own icon. Running a newer one updates LENS, and Settings → Apps removes it. It replaces the single `lens-<version>-windows-x64.exe`, which had to unpack itself every time it started. (#97)

### Changes
- **The hour prints as `hr`** (`2 hr`, `60 km/hr`) in results, the PDF and the LaTeX export, so it is no longer confused with Planck's constant, which is shown as *h*. Typing `'h` or `'hr` still gives the hour, and `kWh`, `Wh` and `mph` keep their symbols. The LaTeX export also compiles with `'h_P` in it. (#89)
- **The Linux program is now a folder** (released as `lens-<version>-linux-x64.tar.gz`), so it no longer unpacks itself to a temporary folder each time it starts, which took over a second. `lens-install-linux-v2.sh` installs it as before; download the installer again (version 2.0.0), since earlier copies look for the old single file. (#97)
- **LENS opens faster**: the window opens while LENS is still loading instead of about two seconds later, and the first result no longer waits for the unit tables to be built. A second launch, or double-clicking a `.lens` file while LENS is running, hands over to the running LENS sooner. (#97)

### Fixes
- A line that only gives a typed-in number or quantity, such as `L = 12345.678'm` or `x = 3.14159`, shows the number as you typed it instead of rounding it to the sheet's significant figures (`12350 m`, or `3.14159 = 3.142`). The copied text and the value shown for the variable keep it too. Results of calculations are still rounded. (#96)
- On Linux, the LENS window shows as LENS, with the LENS icon, in the dock, panel and Alt+Tab list again, instead of as your browser. LENS now opens its window with a browser installed from your distribution's packages before a flatpak or snap one (whose windows the desktop always shows as that browser), opens it through XWayland on Wayland, and keeps a separate profile for each browser. (#93)
- Long calculations in the results pane no longer get a scrollbar: like the PDF export, one a little too wide is shrunk to fit and one much too wide is wrapped one stage per row, and they are fitted again when you resize the pane or the window. (#94)

## [v0.3.6](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.3.6) (2026-10-27)

### New
- **Tab indents** the line, or every highlighted line, by two spaces, and **Shift+Tab** unindents, instead of moving the focus out of the editor. Press Esc first to leave the editor with Tab. (#88)
- **Physical constants** are units you type with a quote: `'R`, `'N_A`, `'Av` (Avogadro's number, unitless), `'k_B`, `'c`, `'h_P` (Planck; `'h` is the hour), `'hbar`, `'e`, `'sigma`, `'G_N`, `'g_0`, `'eps_0`, `'mu_0`, `'m_e`, `'m_p`. They never take a variable's name, the editor's suggestion shows what each is and its value (so `'gas` or `'boltz` finds it), and a line that uses one shows its value in SI (`3'mol * 'R` is `24.94 J/K`). Results in J/(mol·K), J·s and W/(m²·K⁴) are shown in those units. (#86)
- **Units dialog**: the **Units** button lists every unit, with a search over names and descriptions and tags to filter by (constants, thermodynamics, chemistry, pressure, imperial and more). Click a unit to insert it. Add tags of your own to any unit; they are kept in `settings.json`. (#86)
- **Choose the layout**: Alt+L switches between side-by-side and stacked views, and Settings → Layout picks one. Narrow windows still stack by themselves, unless you turn off **Switch automatically when the window is narrow**; if the layout keeps switching itself while you resize, a small note offers to turn that off. (#87)

### Changes
- **The Linux installer installs the latest release**: `lens-install-linux.sh` (one name in every release) looks up the newest LENS release when it runs and downloads it, so running it again updates LENS. `--release 0.3.5` installs a given release, and without a connection it installs the newest release whose files are beside it. The installer now has a version of its own, shown by `--version`. (#84)

### Fixes
- Dragging or zooming a plot makes its line the focused line, so the results no longer jump back to the line the caret was on. (#83)

## [v0.3.5](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.3.5) (2026-10-27)

### Changes
- **Any Chromium-family browser** is found for the app window and PDF export: the default browser when it is Chromium-based, Brave, Vivaldi and Opera, flatpak and snap installs, Windows install folders and App Paths, and macOS app bundles. If one browser won't start, LENS tries the next before falling back to a plain tab. (#72, #77, #82)
- The liter prints as `L` (`mL`, `kL`); `l` is still read as a liter. A typed quantity inside a larger expression prints its number before its unit (`0.72 kg/L`), as it does on its own line. (#74, #80)

### Fixes
- The toolbar wraps at every window width, so Save As and Export no longer run off the right edge. (#73, #78)
- Rename always goes into the editor's undo stack, so Ctrl+Z takes it back. (#75, #79)
- Larger app icons (192 px and 512 px) and a web manifest for the app window. (#82)

## [v0.3.4](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.3.4) (2026-10-26)

### New
- **Export to PDF**: `lens file.lens --pdf out.pdf` or Export → PDF prints a plain, page-broken copy of the results through headless Chrome/Chromium/Edge (`LENS_CHROMIUM` picks the browser). Without a usable browser it opens a printable page sized to the A4 column. (#64, #69, #71)

### Changes
- **One LENS at a time**: launching LENS while it's already running opens a new window on the existing instance instead of starting a second server on another port. After LENS closes, it reclaims its usual port. (#69)
- **Display preferences are saved in `settings.json`**: theme, view, line wrapping and the Math keys, Mark globals and Suggest options carry over across ports and browsers. Values from older builds are migrated once. (#70)

## [v0.3.3](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.3.3) (2026-10-26)

### New
- **∞ in subscripts**: names such as `T_∞` and `v_∞` are allowed, and a subscript spelled `inf` typesets as ∞. (#65, #68)

### Fixes
- Linux: the LENS window gets its own window class, so Cinnamon, GNOME and KDE show the LENS icon for the running window instead of the browser's. (#66, #67)

## [v0.3.2](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.3.2) (2026-10-26)

### New
- **Complex numbers**: `4i` / `4j` literals and the polar form `r∠θ` (Ctrl+< types ∠). `!complex rect|polar|real` picks the display or forbids complex results. Adds `re`, `im`, `conj` and `arg`; `eigvals`/`eigvecs` return complex results. Real sheets stay real: `sqrt` of a negative is still an error that suggests adding `0i`. (#57, #62)
- **Version shown** beside the title and in Help, with a link to the releases. (#58, #61)
- **Offset temperature warning**: `35 * 'degF` now warns that it multiplies by 1 °F read as an absolute temperature, and suggests `35'degF` or `'delta_degF`. (#60, #63)

### Changes
- Release files include the version, e.g. `lens-0.3.2-linux-x64`. The attached Linux installer downloads the files of its own release. (#55, #59)
- Help brought in line with the wiki.

## [v0.3.1](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.3.1) (2026-10-26)

### New
- **Canoe Dark** theme preset. (#56)

## [v0.3.0](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.3.0) (2026-10-26)

### New
- **Markdown export for Obsidian**: `lens file.lens --md out.md` or Export → Markdown writes the sheet as a note with `$$` math blocks, embedded SVG plots and error callouts. The header's export buttons are now one Export menu. (#50, #53)
- **Open .lens files by double-clicking**: the Linux installer registers a `.lens` file type with its own icon; on Windows, `lens --register-files` adds the association. `lens --window FILE` / `lens --serve FILE` open a sheet, and Save writes back to it. (#49, #53)

### Fixes
- Linux installer: the launcher points at the icon by absolute path, so it shows on desktops that don't rescan the icon theme. (#47)
- Plot, solver and rename edits keep CRLF line endings and the block's indent, and are refused if the text changed while the server was working (instead of reverting your typing).
- Rename now handles `'%`, and F2 on a Greek name (`σ_max`) picks the whole name.
- The "Unknown command" error lists `!sigfigsbig`.

### Internal
- Architecture refactor into deeper modules, with behavior unchanged: unit catalogue, command registry and sheet mode, worksheet-text scanner shared with the editor via test vectors, block editor, symbol table, line-result protocol, and front-end `theme.js`, `savefile.js`, `shortcuts.js` and `rows.js`. New CONTEXT.md glossary and wiki architecture pages. (#51)

## [v0.2.2](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.2.2) (2026-10-26)

### New
- **Percent and currency units**: `'%` is a dimensionless unit; currencies are named by ISO 4217 code (`'USD`, `'EUR`, `'GBP`, ...), each its own dimension, so they never convert into each other silently. (#41, #46)
- **∞ constant** (Ctrl+G after 8). Infinite results are allowed only when the line uses ∞, so `1/0` still reports an error. (#43)
- **Global variables are marked** in the editor and results (new theme color, hover shows where the global came from). Math keys add the `~` automatically, and a plain assignment to a global warns. (#35, #48)
- **Save / Save As**: Open keeps the file handle, so Save (Ctrl+S) writes back to the opened file; Save As (Ctrl+Shift+S) picks a new location. (#39, #45)

### Fixes
- Linux build: the browser now launches correctly from the frozen program (library path leak); if no browser starts, LENS prints the address to open. (#37, #45)
- Constant unit symbols such as `g_0`, `m_e` and `N_A` print as subscripts; Pint units siunitx lacks are declared in the LaTeX export. (#38, #44)
- Years display as `yr` instead of `a`. (#42)
- The sheet name field sizes to its text. (#40)
- Added the screenshot the wiki home page links to. (#34)

## [v0.2.1](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.2.1) (2026-10-23)

### New
- **Welcome dialog** on first run, matching the wiki home page. Example worksheets are bundled with the program. (#32)
- **Save** opens a Save As dialog where the browser supports it, and falls back to a download elsewhere. (#31)

### Docs
- Wiki home page wording. (#33)

## [v0.2.0](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.2.0) (2026-10-23)

### New
- **Solving and optimization**: `!root`, `!minimize` and `!maximize` blocks, solved with scipy. (#29)
  - Run, Auto (`autorun: on`), Interrupt, Verify and Log controls under each block; results are written into the sheet as a `#@ result` line, so Ctrl+Z undoes them.
  - Evaluating a sheet never runs a solver. Each block is marked valid, out of date or not run, and lines and plots that depend on an out-of-date block are flagged.
  - Runs happen in a separate worker process, so a stuck calculation can be interrupted or time out.
  - Rename follows names into blocks; LaTeX export of solver values; `lens file --solve` on the command line.
- **Suggestions** for solver options, methods and unknowns, and for `props()` output keys, state inputs and fluids (with aliases such as `h2o` → Water). Math keys leave quoted text alone.

### Fixes
- Solver `timeout:` counts from when the worker takes the job (it used to include a 30 s start-up allowance).
- L-BFGS-B and TNC get an evaluation budget that lets larger problems converge; `brentq` defaults to 1000 steps and explains a bracket that does not close.
- Faster input hashing for large matrices (~0.5 s → ~0.1 s per keystroke for a 1000×1000 input).

### Docs and maintenance
- README rewritten as an overview that links to the new GitHub wiki; wiki pages are published from `wiki/` on main.
- Code, test and docs cleanup; solver stress harness. (#30)
- Linux installer script renamed to `lens-install-linux.sh`.

## [v0.1.7b](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.1.7b) (2026-10-23)

### New
- **Linux installer**: `install-linux.sh` installs LENS per user with a desktop launcher and icon, replacing an earlier install; `--uninstall` removes it. It is attached to the release with `lens-icon.png`.
- OCR-A is the default monospace font (bundled); the Laconic logo is the app icon.

### Docs
- README: download and install directions moved below the abstract.

PR: #28

## [v0.1.7](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.1.7) (2026-10-23)

### New
- **Paste tables as matrices**: pasting Excel, Markdown/Obsidian or CSV tables inserts a matrix literal. Handles quoted cells, thousands and decimal commas, percents, accounting negatives, header and label rows, and a shared unit. Ctrl+Shift+V pastes plain text. (#21)
- **Help dialog** (header button or F1): a short tour of units, math keys, matrices, plots, material properties, export and settings. (#23)
- **Display precision**: `!sigfigs`, `!sigfigsbig` (keeps trailing zeros) and `!decplace`. Matrices use significant figures too. (#25)
- **Rename** warns before replacing a standard unit and lets you swap it for another or a new unit. (#22)
- **Standard alert popup**, used for theme resets. (#24)

### Changes
- `~` marks a global definition; later uses resolve to the global automatically. A global and a plain variable can no longer share a name. (#26)
- Redesigned header: icon buttons for Save, Open, Settings and Rename, KaTeX \LaTeX logo on Export and the view toggle, and the LENS logo in the header, browser tab and packaged executable. (#23, #27)
- Settings is one continuous dialog, with colors as a list. Theme ink is split into text and ink colors.
- **LENS blueprint** is the new default theme; the old green preset is now "Engineering paper". (#24)

### Fixes
- Saved theme colors with unreadable contrast fall back to the defaults, with a warning at load. (#24)
- Significant-figure rounding of large numbers. (#25)

## [v0.1.6](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.1.6) (2026-10-22)

### New
- **`!short` / `!long`**: `!short` shows only the final result of each line (with its units) until `!long` restores the full display. (#16)
- **Matrix indexing and functions**: `idx`/`elem` subscript indexing, numpy matrix functions, and Ctrl+[ / Ctrl+Shift+[ shortcuts. (#18)
- **Rename** now handles custom units defined in the sheet. (#17)

### Changes
- Keys, Greek and Units buttons moved into the Settings dialog. (#16)
- The pound mass is now `lbm`; the ambiguous `lb` is gone.

### Fixes
- `.gitignore` ignores `build/` and `.venv/` correctly. (#20)

## [v0.1.5](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.1.5) (2026-10-21)

### New
- **Material properties**: `props()` looks up fluid properties through CoolProp. String literals are now allowed as built-in function arguments. CoolProp ships in the standard build (about 5 MB larger). (#15)

## [v0.1.4](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.1.4) (2026-10-21)

### New
- `floor`, `ceil` and the Heaviside step function (`step`, `heav` aliases). (#14)

### Docs
- README wording fixes.

## [v0.1.3](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.1.3) (2026-10-21)

### New
- **Plots**: `!plot f(x), x = lo .. hi` draws functions of one variable from the worksheet text. Indented `key: value` lines set title, labels, limits, units, scales, ticks, grid, legend, size, series styles and notes; `!plotspec key: value` sets defaults for every plot below.
  - Mouse pan (drag), zoom (Ctrl+wheel), reset (double-click) and hover readout. Gestures are written back as `xview:` / `yview:` lines, so Ctrl+Z undoes them and the text alone redraws the picture.
  - SVG/PNG export, pgfplots figures in the LaTeX export, and `lens file.lens --plots DIR` on the command line.
  - A fixed plot frame with a six-character tick-label budget, so zooming doesn't move the axes under the pointer.
- **`!clearf`** removes user functions, keeping `~global` ones.
- **`!trigdeg` / `!trigrad`** set the angle unit for trig functions.
- **Theme settings dialog**, **Alt+Z** text wrapping, and a draggable editor/output split.

PR: #13

## [v0.1.2](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.1.2) (2026-10-20)

### New
- **Rename symbol**: rename a variable or function everywhere in the sheet (Rename button or F2). The rename is token-aware, skips comments, commands, units and numbers, refuses built-ins and name collisions, and is undoable with Ctrl+Z. (#7)

## [v0.1.1](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.1.1) (2026-10-20)

### New
- **Autocomplete**: a suggestion popup for units (after `'`), commands (after `!`) and variables, functions and constants. Tab accepts; Enter accepts only after arrow navigation; Ctrl+Space opens it by hand.
- **Term-aware selections**: `/ ^ \ ( [ |` and Ctrl+M/T apply to the selection, widened to whole terms. Double-click selects a term, Alt+Up/Down grows and shrinks the selection, and Ctrl+Space with a selection wraps it in a chosen function.
- **Custom units**: `'smoot = 1.7018'm` defines a unit for the sheet. Global units and the Greek table live in a server-side settings file, edited from the Units and Greek dialogs. Save appends the global units a sheet uses; the .tex export declares custom units with `\DeclareSIUnit`.

### Fixes
- Server tests call the API endpoints directly, so CI no longer needs an extra test dependency.

PR: #6

## [v0.1.0](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.1.0) (2026-10-20)

First release of LENS (Laconic Engineering Notebook System): a units-aware worksheet on top of Pint, with live typeset results, LaTeX snippets and export, and plain-text `.lens` worksheets. Standalone builds for Linux and Windows are attached.

### Highlights
- **Units-aware worksheet**: one expression per line, units marked with an apostrophe (`'kN`), results typeset live as you edit.
- **`!noassume` / `!assume`**: keep results in the units the arithmetic produced instead of reducing them to SI (an explicit `->` still converts). (#2)
- **Accent marks on names**: a backtick puts a dot over a variable (two for a double dot), `!` an arrow and `@` a hat. Marked names are separate variables. (#3)
- **Self-hosted assets**: KaTeX and IBM Plex fonts are bundled, so the app no longer loads anything from CDNs. (#1)

### Build and CI
- Fixed the CI install by listing the `laconic` package explicitly. (#4)
- Fixed the release job so binaries are collected and attached correctly. (#5)
