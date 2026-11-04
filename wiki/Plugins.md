# Plugins

A plugin is a page of its own that a sheet opens with `!plugin name`. It does something easier with the mouse than in text, such as laying out a pipe network, and writes what it made into the sheet as ordinary lines. The sheet calculates with those lines, and `!pluginvar` sends results back for the plugin to show.

```
!plugin pipenet                                the plugin's block
  A = [1, 0; 0, 1; 1, 1]                       lines the plugin writes: ordinary assignments
  L! = [40; 60; 60] * 'ft
  #@ state {"v":1,"cells":{...}}               what the plugin keeps of its own (its layout)
Q = A * Q_spur                                 the sheet calculates with them
!pluginvar Q, Δp                               and sends these back to the plugin
```

The block's row in the results shows the plugin's picture, with **Open** (the plugin in a large window) and **Reload** (fetch the plugin again). Close the window to get back to the sheet; the plugin keeps running, and its picture follows the sheet.

- **What the plugin writes is the sheet's.** Its `name = value` lines run like any assignment. They show in the results, export as math, and work in `lens --solve` and on a machine that has never fetched the plugin. You can read them, but the plugin rewrites them on its next change, so change the layout in the plugin.
- **Don't define its names again.** A line below the block that defines one of the names the plugin writes replaces the plugin's value for the lines after it, so a change made in the plugin would not reach them. Such a line gets a warning in the results (shown even under `!hide`), and the plugin names it too.
- **The state line** (`#@ state {...}`) is the plugin's own record, so it opens as you left it. Undo in the editor undoes a plugin's change, and the plugin follows.
- **`!pluginvar a, b`** sends the values of `a` and `b`, as they are on that line, to every plugin in the sheet. Put it below the calculation. A value that reads an out-of-date solver result is sent marked as such.

## Where plugins come from

A plugin is fetched the first time a sheet with its `!plugin` line is opened in the page, and kept in the `plugins` folder beside the settings file. Nothing is fetched when a sheet is calculated, exported or run from the command line. **Reload** fetches it again. Plugins live in the [`plugins/`](https://github.com/InverseInertia/laconic-ens/tree/main/plugins) folder of the LENS repository, which lists them in `index.json`.

**Settings → Plugins** lists the plugins installed on this machine (with **Update** and **Remove**) and the others the repository offers (with **Install**), and installs one by name.

**Install from a folder…** (in the same place) installs a plugin you have on this computer: pick its folder, the one holding its `manifest.json`. Use it for a plugin that is not on GitHub's `main` yet, such as one on a branch you are running or one you are writing. `lens --install-plugin DIR` does the same from the command line. A plugin installed this way is never fetched over: **Reload** and **Update** leave it as it is, and installing it from its folder again replaces it. Turn off **Download a plugin when a sheet asks for it** and a sheet never downloads anything: a block whose plugin is not installed says so and offers **Install**, which downloads it because you asked.

A plugin runs in a sandbox: it cannot reach LENS, your files, other sites or the rest of the sheet. All it can do is write its own block's lines (checked by LENS before they go in), send the picture its row shows, and read the `!pluginvar` values.

`LENS_PLUGIN_SOURCE` points LENS at another place to fetch plugins from: a folder (read in place, every time) or an `https://` address that holds one folder per plugin. A source checkout of LENS uses its own `plugins/` folder.

## Pipe network (`!plugin pipenet`)

Lays out a fluid loop for a sheet that solves it for equal pressure drops, so you can arrange the pipes without writing the network's matrices by hand.

**Its sheet.** The plugin comes with the sheet it is made for (`pipenet.lens` in the plugin): a hydronic loop with eight loads, solved for the flows that give every path the same pressure drop. Once the plugin is installed, open it from Help → Examples ("Pipe network"), Settings → Plugins (**Open its sheet**), or the plugin's **Open the original sheet**. After each run LENS compares the sheet with it, and the plugin warns under **Check** when a line of it is changed or missing (a coefficient table edited, a definition deleted), naming each. That is fine when you meant it; otherwise open the original and copy the lines back. Lines you add, comments, and the lines the plugin writes are not compared.

**Laying it out.** The grid grows as you build toward its edges.

- **Shapes**: every straight, elbow, tee and crossover in every orientation, a source (the pump) and a sink (a load: a coil, an exchanger), each facing each way. Pick one and click squares to put it down; click a tile of the same shape to turn it.
- **Draw**: drag from square to square to lay pipe. The tiles take their shape from the pipes that meet in them: a straight, an elbow, a tee where a pipe branches off, a crossover where one runs straight across another without joining it. Drag from the source or onto a sink to connect it.
- **Select** a tile to set its length, an extra loss coefficient K (a valve, from its datasheet) and its segment's pipe: the network's, another size from the table, or a bore of its own. A sink also takes a name, an exchanger curve number and a pump speed. **R** turns the selected tile and **Del** removes it. **Erase** removes tiles by clicking or dragging.
- **Network** settings: the length unit and the length of a square; the **Pipe size** (nominal, ⅛″ to 24″) and **Schedule** (40 or 80), or a bore of your own; the diameter unit; the **Return pipe** (below); and **Fitting losses**, the method the sheet uses (below).

**Pipe sizes.** A segment's `D_h` is its pipe's inside diameter: Schedule 40 or 80 pipe of the nominal size chosen, from the wall thicknesses of ASME B36.10M. PVC Schedule 40 and 80 pipe (ASTM D1785) has the same outside diameters and walls, so the same bores. The schedule is the network's; the size is the network's unless a segment picks its own.

**Supply and return.** With **Return pipe: Same as supply**, the return runs beside the supply and matches it: you lay out the supply, and the plugin writes the return's lines as copies of it. Choose **Laid out on its own** for a return that differs (another route, other lengths, other sizes, a reverse return). The grid then has two sides, as a circuit board does. **Supply | Return** (or **F**) chooses the side the tools work on, and the other side is drawn behind it as thin dashed lines, for reference. The source and the sinks are on both sides, in the same squares; each side connects to them on its own side of the tile (the pump's discharge on the supply, its suction on the return), and taking one away takes it off both. The return starts as a copy of the supply, so you change only where they differ. Its segments are numbered R1, R2, … in the same way as the supply's, and get a table of their own. A sink the return does not reach is an error.

**What it writes.** The water splits only at tees, so the network is a set of **segments**, each the pipe between two junctions. A segment that ends at a sink is that sink's **spur**. Segments are numbered as the sheet's vectors are, with the spurs first in the order of their sinks, then the rest from the source outwards. The drawing shows each segment's number on its pipe.

| Line | What it is |
|---|---|
| `A` | the supply's upstream matrix: one row per segment, one column per sink, 1 where the segment carries that sink's water. With the spurs first, its top rows are the identity |
| `L!` | each supply segment's length |
| `D_h!` | each supply segment's inside diameter |
| `N_fit!` | each supply segment's fittings, counted by kind: one row per segment, columns 90° elbows, tees passed straight through (runs), tees' branches. A segment counts the tee it leaves through |
| `K_extra!` | each supply segment's extra loss coefficients, added to the fittings' as they are |
| `A_r`, `L_r!`, `D_r!`, `N_fit_r!`, `K_extra_r!` | the same for the return's segments. `A_r`'s columns are the same sinks in the same order as `A`'s. With the return the same as the supply, these are copies of the supply's lines |
| `exchangers!`, `speeds!` | each sink's exchanger curve number and pump speed |
| `fit_method!` | the fitting-loss method chosen: 1 Crane, 2 Hooper 2-K, 3 Darby 3-K |
| `Δp_target` | the pressure difference the pump's controller holds (Network → Pump target Δp, in psi, kPa, Pa, bar or ft of water), which sets the loop's total flow |

With these, `A * Q_spur` is the flow in every supply segment and `A_r * Q_spur` in every return segment, and each sink's path loses `transpose(A) * Δp_supply + transpose(A_r) * Δp_return` in its pipes, out and back.

**Fitting losses.** The sheet's **Fitting Losses** section holds each method's coefficients as a table, one row per kind of fitting in `N_fit!`'s order, so you can edit them for your fittings (the values given are for standard threaded fittings, r/D = 1). `ΣK(∀`, N, D, K_x)` gives each segment's K for the flows in the segments, for either side's fittings, diameters and extra K:

| Method | K for one fitting | Table |
|---|---|---|
| Crane TP-410 | (L/D)·f_T, with f_T the fully turbulent friction factor of clean commercial steel (ε = 0.046 mm), the pipe Crane's L/D values were measured in | `FIT_Crane`: L/D (30, 20, 60) |
| Hooper 2-K | K₁/Re + K∞·(1 + 1/D), D in inches | `FIT_Hooper`: K₁, K∞ |
| Darby 3-K | K₁/Re + Kᵢ·(1 + K_d/D^0.3), D in inches | `FIT_Darby`: K₁, Kᵢ, K_d |

Crane's K does not change with the flow, which suits fully turbulent flow; Hooper's and Darby's grow as the Reynolds number falls, which matters in the transitional range small loops often run in.

**What it shows.** A `!pluginvar` value with one entry per segment is drawn on the segments (`∀!`, the flow in each): on the return's when its name ends in `_r` (`∀_r!`, `Δp_r`), else on the supply's. One with an entry per sink goes beside the sinks (`Δp_spur`), and a single number in a corner. The values of the side in front are drawn, in balloons: where two would overlap (or cover a segment's number, the pump or a sink) they push each other apart, and one moved from its place keeps a leader line to it. Pipe in use is drawn solid; pipe the source does not reach is drawn hollow, and listed under **Check** as one note. The tables on the right list them all. **On the drawing** chooses values, numbers only, or nothing.

**Check.** Each side must be a tree from the one source. An open end, a dead end, a loop or a pipe running back into the source is pointed out on the drawing and listed under **Check**, and the sheet's lines are left as they were until it is fixed. Tiles not connected to the source are left out, with a note.

## Writing a plugin

A plugin is a folder named for it (lower-case letters, digits, `-` and `_`) holding `manifest.json` and the files it lists:

```json
{"name": "pipenet", "title": "Pipe network", "version": "1.1.0",
 "entry": "index.html", "files": ["index.html", "pipenet.js", "app.js", "pipenet.lens"],
 "template": "pipenet.lens"}
```

`template`, if given, is a sheet the plugin ships (one of its files, a `.lens`): LENS offers it among the examples and in Settings, opens it when the plugin asks, and after each run tells the plugin which of its lines the sheet has changed or lost (`lens:check`).

Add it to `plugins/index.json` (its name, title, version and description, as in the manifest; a test holds the two together) so Settings offers it. The files may be HTML, JavaScript, CSS, JSON, SVG, PNG, WOFF2 or `.lens`, with no folders, and at most 2 MB each. The page is opened in a frame with `sandbox="allow-scripts"`, under a Content-Security-Policy that allows its own scripts and styles and no requests. To look like LENS, a plugin takes its colours from `theme` (LENS's theme variables without their `--`: `paper`, `paper-deep`, `grid`, `text`, `text-soft`, `ink`, `on-ink`, `rule`, `err`, `global`, `symbol`, `hit`, `hl`, `on-hl`, `sans`, `mono`), and its fonts from `<link rel="stylesheet" href="/static/fonts/fonts.css">`, which LENS serves to plugin frames. The pipenet plugin sets them as CSS variables of the same names, so its styles read like LENS's own. It talks to LENS with `postMessage`:

| Message | Meaning |
|---|---|
| plugin → `{type: "lens:ready"}` | send it the first update |
| LENS → `{type: "lens:update", state, inputs, outputs, theme}` | after each run of the sheet. `state` is the block's state line (null when it has none), left out when the sheet has not run since the plugin's last write. `inputs` are the `!pluginvar` values, `[{name, unit, shape, mag, stale}]` (`mag` in `unit`: a number or nested rows). `outputs` are the names the block's lines define, `overridden` (`[{name, line}]`) the lines outside the block that define one of them again, and `theme` the page's colours and fonts |
| LENS → `{type: "lens:theme", theme}` | the theme changed in Settings: the same `theme` as in an update, at once |
| LENS → `{type: "lens:check", missing, changed}` | for a plugin with a `template`, after each run: what of that sheet this one lacks (`missing`) or defines differently (`changed`), each a list of names and `!` lines. Spacing, comments, stored results, lines the sheet adds and the plugin's own block are not compared |
| plugin → `{type: "lens:open-template"}` | open the plugin's sheet in place of this one (LENS asks the user first) |
| plugin → `{type: "lens:write", state, outputs: {name: "expression"}}` | write its state line, and a line `name = expression` for each output, in place, or added in order. Names are plain variable names; each expression is one line of LENS math |
| plugin → `{type: "lens:preview", svg}` | the picture its row shows, as SVG text (shown as an image, so scripts in it do not run) |
