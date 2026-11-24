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
- **Which version wrote it.** Each time a plugin writes, LENS records the plugin's version in the state line (`"by"`). Open the sheet with an older copy of the plugin (one installed from a folder is never fetched again) and the row says so, and the plugin shows the sheet but does not change it until it is updated: an older copy does not know every line a newer one writes, and would leave those out of date.
- **The state line** (`#@ state {...}`) is the plugin's own record, so it opens as you left it. Undo in the editor undoes a plugin's change, and the plugin follows.
- **`!pluginvar a, b`** sends the values of `a` and `b`, as they are on that line, to every plugin in the sheet. Put it below the calculation. A value that reads an out-of-date solver result is sent marked as such.
- **`!pluginvar list: f, g`** sends names instead: `f` and `g`, in that order, under the name `list`, each a variable or function defined above. It tells a plugin what the sheet's numbers pick: `!pluginvar exchangers: HX_A, HX_B` says exchanger curve 1 is `HX_A` and 2 is `HX_B`.

## Where plugins come from

A plugin is fetched the first time a sheet with its `!plugin` line is opened in the page, and kept in the `plugins` folder beside the settings file. Nothing is fetched when a sheet is calculated, exported or run from the command line. **Reload** fetches it again. Plugins live in the [`plugins/`](https://github.com/InverseInertia/laconic-ens/tree/main/plugins) folder of the LENS repository, which lists them in `index.json`.

**Settings → Plugins** lists the plugins installed on this machine (with **Update** and **Remove**) and the others the repository offers (with **Install**), and installs one by name.

**Install from a folder…** (in the same place) installs a plugin you have on this computer: pick its folder, the one holding its `manifest.json`. Use it for a plugin that is not on GitHub's `main` yet, such as one on a branch you are running or one you are writing. `lens --install-plugin DIR` does the same from the command line. A plugin installed this way is never fetched over: **Reload** and **Update** leave it as it is, and installing it from its folder again replaces it. Turn off **Download a plugin when a sheet asks for it** and a sheet never downloads anything: a block whose plugin is not installed says so and offers **Install**, which downloads it because you asked.

A plugin runs in a sandbox: it cannot reach LENS, your files, other sites or the rest of the sheet. All it can do is write its own block's lines (checked by LENS before they go in), send the picture its row shows, and read the `!pluginvar` values.

`LENS_PLUGIN_SOURCE` points LENS at another place to fetch plugins from: a folder (read in place, every time) or an `https://` address that holds one folder per plugin. A source checkout of LENS uses its own `plugins/` folder.

## Pipe network (`!plugin pipenet`)

Lays out a fluid loop for a sheet that solves it for equal pressure drops, so you can arrange the pipes without writing the network's matrices by hand.

**Its sheet.** The plugin comes with the sheet it is made for (`pipenet.lens` in the plugin): a hydronic loop with eight loads, solved for the flows that give every path the same pressure drop. Once the plugin is installed, open it from Help → Examples ("Pipe network"), Settings → Plugins (**Open its sheet**), or the plugin's **Open the original sheet**. After each run LENS compares the sheet with it, and the plugin warns under **Check** when a line of it is changed or missing (a coefficient table edited, a definition deleted), naming each. That is fine when you meant it; otherwise open the original and copy the lines back. Lines you add, comments, and the lines the plugin writes are not compared, nor are its data sections: the exchanger data and the pump data, each between a `# ---- … paste your own …` line and a `# ---- end …` line, are yours to replace, so a sheet with your own exchangers or pumps pasted in raises no warning as long as the calculation around them is the plugin's. The warning guards the calculation (the friction factor, `HX`, `PUMP`, the walls, the fitting methods, the solver) against an accidental edit.

**Laying it out.** The grid grows as you build toward its edges.

- **Shapes**: every straight, elbow, tee and crossover in every orientation, a source (the pump) and a sink (a load: a coil, an exchanger), each facing each way. Pick one and click squares to put it down; click a tile of the same shape to turn it.
- **Draw**: drag from square to square to lay pipe. The tiles take their shape from the pipes that meet in them: a straight, an elbow, a tee where a pipe branches off, a crossover where one runs straight across another without joining it. Drag from the source or onto a sink to connect it.
- **Select** a tile to set its segment's length (the pipe from one junction to the next, as a whole: it is spread over the segment's squares, and blank goes back to the length of its squares), an extra loss coefficient K (a valve, from its datasheet) and its segment's pipe: the network's, another size from the table, or a bore of its own. A sink also takes a name, an exchanger curve, a circulator (or none) and a regulating valve (its Cv, or none). **R** turns the selected tile and **Del** removes it. **Erase** removes tiles by clicking or dragging.
- **Sinks set up alike**: a sink's settings are its exchanger, its circulator, its regulating valve's Cv and its extra K (its name, place and length are its own). With a sink selected, **Copy settings to…** gives them to each sink you click next (**To every sink** to all of them; **Done** or Esc to stop); while it does, a banner in the theme's warning colour (orange on the blueprint) is pinned over the grid, so a click there is not taken for drawing. A sink set up like others has a switch over its settings: **This sink** (the default) changes it alone, **All N alike** changes it and every sink set up like it, with the settings outlined in the warning colour and the sinks it reaches named below them. Sinks whose settings are the same as another's carry a small mark over their icon's top left corner, the same mark for each sink of a group: a travelling salesman's tour of a 3 by 3 grid of points, a step to any neighbour, diagonals too. A group's mark follows from its settings, and the groups of one network get marks as unlike each other as the tours go. The inspector names the sinks a selected sink is set up like.
- **Network** settings: the length unit and the length of a square; the **Pipe size** (nominal, ⅛″ to 24″) and **Schedule** (40 or 80), or a bore of your own; the diameter unit; the **Return pipe** (below); and **Fitting losses**, the method the sheet uses (below).
- **View**: − and + zoom (Ctrl+− and Ctrl+=), **1:1** goes back to full size and **Fit** fits the layout and the background image in the window; Ctrl + the wheel, or a touchpad's pinch, zooms about the pointer, from 10% to 400%. Drag with the middle button, or with Space held, to move around.
- **Background**: **Place image…** (or drop a picture on the grid) puts a planset behind the grid, to trace the pipes over: PNG, JPEG, SVG or WebP (save a PDF's page as one of those first). **Move** drags it into line with the grid; **Scale** takes two points a known distance apart on it (the ends of a dimension) and the distance, and sizes the picture about the first point so the two are that far apart in squares of the square length. **Width** sets its size directly, and **Opacity** how strongly it shows. The sheet holds only where the picture is and how large; the picture itself is kept in this browser, so on another computer the plugin names it and **Replace image…** with the same file puts it back in place. Replacing a picture with an updated one keeps its place and size.

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
| `exchangers!`, `pumps!` | each sink's exchanger curve and circulator, by number (a circulator of 0 is none) |
| `valves!` | each sink's regulating valve, as its Cv (0 for none) |
| `fit_method!` | the fitting-loss method chosen: 1 Crane, 2 Hooper 2-K, 3 Darby 3-K |
| `solver_method!` | how the sheet's solver finds the flows (Network → Solver), by its number among the `!root` methods: 1 `hybr` (the default, quick on a smooth network), 2 `lm` (steadier when spurs sit against the end of their exchanger's or pump's data), 3 `broyden1`, 4 `broyden2`, 5 `krylov`. The sheet's `!root` reads it with `method: solver_method!` |
| `hold_flow!` | what the main pump's controller holds (Network → Pump holds): 1 the loop's total flow, its pressure difference following (the default); 0 its pressure difference, the flow following, as a pump run off a pressure sensor does |
| `∀_target` | the total flow it holds (Network → Pump target flow, in gal/min, L/s, L/min or m³/h) |
| `Δp_target` | the pressure difference it holds (Network → Pump target Δp, in psi, kPa, Pa, bar or ft of water) |

Either way the solver finds the spur flows and the pump's pressure difference, `Δp_main`, together: with every path taking that pressure difference, and either the flows adding up to `∀_target` or `Δp_main` equal to `Δp_target`. The sheet sends back `∀_total` and `Δp_pump`, shown in the drawing's corner. Holding a flow, a pressure difference below zero means the circulators alone push more than the target: the plugin says so under **Check**.

**Against a wall.** An exchanger's or pump's curve holds only between the least and greatest flow in its data, and past either end the solver meets a wall (see the sheet's `WALL`) that pushes it back inside. A spur whose answer still sits past an end is held there by the wall, so its flow is the wall's, not what the curve says: a small circulator that cannot overcome the trunk's loss, say, ends at the bottom of its exchanger's data. The sheet sends `at_wall!` (one per sink: 0 none, 1 against its exchanger's data, 2 its circulator's, 3 both), and the plugin names those spurs in a banner across the grid in the warning colour, lists each under **Check** (click to select it), and rings them on the drawing. Change the spur's circulator or exchanger, add a balancing valve, or change the main pump's target to bring it inside.

With these, `A * Q_spur` is the flow in every supply segment and `A_r * Q_spur` in every return segment, and each sink's path loses `transpose(A) * Δp_supply + transpose(A_r) * Δp_return` in its pipes, out and back.

**Fitting losses.** The sheet's **Fitting Losses** section holds each method's coefficients as a table, one row per kind of fitting in `N_fit!`'s order, so you can edit them for your fittings (the values given are for standard threaded fittings, r/D = 1). `ΣK(∀`, N, D, K_x)` gives each segment's K for the flows in the segments, for either side's fittings, diameters and extra K:

| Method | K for one fitting | Table |
|---|---|---|
| Crane TP-410 | (L/D)·f_T, with f_T the fully turbulent friction factor of clean commercial steel (ε = 0.046 mm), the pipe Crane's L/D values were measured in | `FIT_Crane`: L/D (30, 20, 60) |
| Hooper 2-K | K₁/Re + K∞·(1 + 1/D), D in inches | `FIT_Hooper`: K₁, K∞ |
| Darby 3-K | K₁/Re + Kᵢ·(1 + K_d/D^0.3), D in inches | `FIT_Darby`: K₁, Kᵢ, K_d |

Crane's K does not change with the flow, which suits fully turbulent flow; Hooper's and Darby's grow as the Reynolds number falls, which matters in the transitional range small loops often run in.

**What it shows.** A `!pluginvar` value with one entry per segment is drawn on the segments (`∀!`, the flow in each): on the return's when its name ends in `_r` (`∀_r!`, `Δp_r`), else on the supply's. One with an entry per sink goes beside the sinks (`Δp_spur`), and a single number in a corner. The values of the side in front are drawn, in balloons. Each balloon takes one of a set of spots around its pipe or sink (its usual one, or one of eight ways round at up to five distances), chosen together for all of them, as labels are placed on a map: as near its place as it can be, without overlapping another, covering a segment's number, the pump or a sink, or covering more pipe than it must, and without leader lines crossing. One away from its usual spot keeps a leader line to it, and none can end up further away than its furthest spot. While the layout is edited, a balloon stays where it was unless something now overlaps it, so the drawing holds still. Sinks set up alike leave the exchanger, circulator and valve they share out of their balloons: a key gives them once against each mark, pinned to the bottom left of the grid where it is in sight however the grid is scrolled (and in the corner of the row's picture). Pipe in use is drawn solid; pipe the source does not reach is drawn hollow, and listed under **Check** as one note. The tables on the right list them all. The sheet's `!root` has a `status: solver_state` line, and sends `solver_state` with the values, so the plugin knows how its solver stands: while it is out of date after a change, the values are drawn as they are, greyed in the tables, under a banner across the grid, **Waiting on the solver**, until it has solved the new layout (a failed run stores nothing, so the banner stays; the solver's row in the sheet says why). A solver never run, or a block with an error, has a banner of its own. A sheet that does not send `solver_state` gets the waiting banner from its values' out-of-date flags alone.

**On the drawing** has a checkbox for each set the balloons can show: segment numbers, each segment's pipe size, length and D_h (its bore), each sink's exchanger curve and pump, and each of the sheet's `!pluginvar` values. They are kept in the plugin's state, so the row's picture shows the same.

**Exchangers and pumps.** A sink's exchanger and pump are numbers in the sheet (`exchangers!`, `pumps!`), which `HX` and `PUMP` turn into pressure differences. The plugin's sheet names them, in order, with `!pluginvar exchangers: ...` and `!pluginvar pumps: ...`, and the plugin then offers and shows them by those names; without the lists, they are picked by number.

- **Exchangers**: each has its own data, two rows (its flows in gal/min, then its pressure drops in psi at those flows, as a manufacturer's selection software or design guide gives them, three points or more), and a `!regression` of degree 2 through it. `HX_C` holds the fits' coefficients, one row per exchanger, and `HX_q` each one's least and greatest flow. The sheet ships with three ClimateMaster Compact (HBH/V) heat pumps from their public design guide, the HBH060, HBH009 and HBH006 with PSC blowers at 85 °F entering water, the largest first since a new sink takes exchanger 1. To use your own, paste them over the marked lines (the data, a `!regression` each, their rows of `HX_C` and `HX_q`, a number-name each, the `!pluginvar exchangers:` line and the plots); data that is not for redistribution keeps that copy of the sheet to yourself. The plugin will say those lines differ from its own sheet, which is expected.
- **Regulating valves**: a spur can have a regulating (balancing) valve as well as, or instead of, a circulator. Give its Cv (gal/min at 1 psi of water) when the sink is selected; it takes Δp = SG·(Q/Cv)² (`VALVE` in the sheet). With valves instead of circulators, the main pump supplies all the head: raise **Pump target Δp** to suit the larger pump. The **Regulating valve** checkbox shows each sink's Cv on the drawing, and `Δp_valve` is each valve's pressure drop.
- **Pumps** are Grundfos curves from their public product information: the 43-100 F's and the 26-99 FC's three speed settings, the 15-42 and the C1016T, each a pump of its own. `PUMP_C` holds each fit's coefficients, one row per pump, and `PUMP_q` each one's least and greatest flow. Add a pump with its points, a `!regression`, a row of each, and its name on the `!pluginvar pumps:` line.
- **Only within the data.** A fit holds between the least and the greatest flow in its data, and no further. Past either end, the `HX` and `PUMP` the solver uses carry on from the end of the fit as a steep wall, `WALL` (100 psi per gal/min): an exchanger's drop climbs above its data and falls below it, a pump's head falls above its data and climbs below it, so a flow outside is pushed back in rather than taken. The plots (`HX_curve`, the `GRUND_...` curves) stop at the data.

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
| LENS → `{type: "lens:check", missing, changed}` | for a plugin with a `template`, after each run: what of that sheet this one lacks (`missing`) or defines differently (`changed`), each a list of names and `!` lines. Spacing, comments, stored results, lines the sheet adds, the plugin's own block and data sections (from a comment `# ---- …` to the next `# ---- end …`, in either sheet; one with no `end` line is not a section) are not compared |
| plugin → `{type: "lens:open-template"}` | open the plugin's sheet in place of this one (LENS asks the user first) |
| plugin → `{type: "lens:write", state, outputs: {name: "expression"}}` | write its state line, and a line `name = expression` for each output, in place, or added in order. Names are plain variable names; each expression is one line of LENS math |
| plugin → `{type: "lens:preview", svg}` | the picture its row shows, as SVG text (shown as an image, so scripts in it do not run) |
| plugin → `{type: "lens:keep", key, data}` | keep a string too large for the sheet (a picture, as a `data:` URL) in this browser, under the plugin's name and `key` (letters, digits, `-`, `_`, `.`); `data: null` forgets it. Kept in IndexedDB, up to 60 MB each, and kept when the plugin is removed |
| plugin → `{type: "lens:recall", key}` | ask for what was kept under `key` |
| LENS → `{type: "lens:recalled", key, data}` | the answer: the string kept, or `null` (nothing under that key in this browser) |
