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
- **The state line** (`#@ state {...}`) is the plugin's own record, so it opens as you left it. Undo in the editor undoes a plugin's change, and the plugin follows.
- **`!pluginvar a, b`** sends the values of `a` and `b`, as they are on that line, to every plugin in the sheet. Put it below the calculation. A value that reads an out-of-date solver result is sent marked as such.

## Where plugins come from

A plugin is fetched the first time a sheet with its `!plugin` line is opened in the page, and kept in the `plugins` folder beside the settings file. Nothing is fetched when a sheet is calculated, exported or run from the command line. **Reload** fetches it again. Plugins live in the [`plugins/`](https://github.com/InverseInertia/laconic-ens/tree/main/plugins) folder of the LENS repository, which lists them in `index.json`.

**Settings → Plugins** lists the plugins installed on this machine (with **Update** and **Remove**) and the others the repository offers (with **Install**), and installs one by name. Turn off **Download a plugin when a sheet asks for it** and a sheet never downloads anything: a block whose plugin is not installed says so and offers **Install**, which downloads it because you asked.

A plugin runs in a sandbox: it cannot reach LENS, your files, other sites or the rest of the sheet. All it can do is write its own block's lines (checked by LENS before they go in), send the picture its row shows, and read the `!pluginvar` values.

`LENS_PLUGIN_SOURCE` points LENS at another place to fetch plugins from: a folder (read in place, every time) or an `https://` address that holds one folder per plugin. A source checkout of LENS uses its own `plugins/` folder.

## Pipe network (`!plugin pipenet`)

Lays out a fluid loop for a sheet that solves it for equal pressure drops, so you can arrange the pipes without writing the network's matrices by hand. The **Pipe network** example (Open → Examples) is a hydronic loop with eight loads, solved for the flows that give every path the same pressure drop.

**Laying it out.** The grid grows as you build toward its edges.

- **Shapes**: every straight, elbow, tee and crossover in every orientation, a source (the pump) and a sink (a load: a coil, an exchanger), each facing each way. Pick one and click squares to put it down; click a tile of the same shape to turn it.
- **Draw**: drag from square to square to lay pipe. The tiles take their shape from the pipes that meet in them: a straight, an elbow, a tee where a pipe branches off, a crossover where one runs straight across another without joining it. Drag from the source or onto a sink to connect it.
- **Select** a tile to set its length, extra fittings (as equivalent L/D, such as a valve) and its segment's diameter; a sink also takes a name, an exchanger curve number and a pump speed. **R** turns the selected tile and **Del** removes it. **Erase** removes tiles by clicking or dragging.
- **Network** settings: the length and diameter units, the length of a square, the default diameter, and whether the return pipe matches the supply (it doubles each length and each fitting).

**What it writes.** The water splits only at tees, so the network is a set of **segments**, each the pipe between two junctions. A segment that ends at a sink is that sink's **spur**. Segments are numbered as the sheet's vectors are, with the spurs first in the order of their sinks, then the rest from the source outwards. The drawing shows each segment's number on its pipe.

| Line | What it is |
|---|---|
| `A` | the upstream matrix: one row per segment, one column per sink, 1 where the segment carries that sink's water. With the spurs first, its top rows are the identity |
| `L!` | each segment's length (doubled for the return) |
| `D_h!` | each segment's diameter |
| `K_fT!` | each segment's fittings as equivalent lengths in diameters (Crane TP-410): 30 for each elbow, 20 for a tee passed straight through, 60 for a tee's branch, plus any extra (doubled for the return). `ΣK! = K_fT! .* .f_T(D_h!)` gives the loss coefficients |
| `exchangers!`, `speeds!` | each sink's exchanger curve number and pump speed |

With these, `A * Q_spur` is the flow in every segment, and `transpose(A) * Δp_segment` the pressure drop along every path from the source to a sink.

**What it shows.** A `!pluginvar` value with one entry per segment is drawn on the segments (`∀!`, the flow in each), one with an entry per sink beside the sinks (`Δp_spur`), and a single number in a corner. The tables on the right list them all. **On the drawing** chooses values, numbers only, or nothing.

**Check.** The network must be a tree from the one source. An open end, a dead end, a loop or a pipe running back into the source is pointed out on the drawing and listed under **Check**, and the sheet's lines are left as they were until it is fixed. Tiles not connected to the source are left out, with a note.

## Writing a plugin

A plugin is a folder named for it (lower-case letters, digits, `-` and `_`) holding `manifest.json` and the files it lists:

```json
{"name": "pipenet", "title": "Pipe network", "version": "1.0.0",
 "entry": "index.html", "files": ["index.html", "pipenet.js", "app.js"]}
```

Add it to `plugins/index.json` (its name, title, version and description, as in the manifest; a test holds the two together) so Settings offers it. The files may be HTML, JavaScript, CSS, JSON, SVG, PNG or WOFF2, with no folders, and at most 2 MB each. The page is opened in a frame with `sandbox="allow-scripts"`, under a Content-Security-Policy that allows its own scripts and styles and no requests. It talks to LENS with `postMessage`:

| Message | Meaning |
|---|---|
| plugin → `{type: "lens:ready"}` | send it the first update |
| LENS → `{type: "lens:update", state, inputs, outputs, theme}` | after each run of the sheet. `state` is the block's state line (null when it has none), left out when the sheet has not run since the plugin's last write. `inputs` are the `!pluginvar` values, `[{name, unit, shape, mag, stale}]` (`mag` in `unit`: a number or nested rows). `outputs` are the names the block's lines define, and `theme` the page's colours and fonts |
| plugin → `{type: "lens:write", state, outputs: {name: "expression"}}` | write its state line, and a line `name = expression` for each output, in place, or added in order. Names are plain variable names; each expression is one line of LENS math |
| plugin → `{type: "lens:preview", svg}` | the picture its row shows, as SVG text (shown as an image, so scripts in it do not run) |
