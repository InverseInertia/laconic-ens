# Plots

A `!plot` line draws one or more functions of one variable over a range, and [points](#points) such as measurements. It is a command, so `plot` stays available as an ordinary name. Indented `key: value` lines under it set the details. Press `Enter` after the `!plot` line and the next line is indented for you; type a letter or two and the editor suggests the options, and then the values of those with a few choices (`grid: on`, `color: red`).

```
!plot M(x), V(x), x = 0'm .. L
  title: Bending moment and shear
  ylabel: M (kN·m)
  xlim: 0'm .. 3.2'm
  color 2: red
  note: "max" at (L / 2, M(L / 2))
```

The expressions can use any variable and function above them. They are sampled point by point (`samples`, default 400), so units are checked at every point and a result in kN·m is shown in kN·m. Several expressions share one y axis and must have compatible units; give incompatible ones separate plots.

Where an expression is undefined (`1/x` at 0, `sqrt` of a negative) the line breaks there. A line that jumps from beyond one limit to beyond the other (a pole) is not joined across the picture. `gaps: error` turns an undefined point into an error instead.

## Options

| Option | Meaning (default in brackets) |
|---|---|
| `title`, `xlabel`, `ylabel` | text. Axis labels are `name [unit]` unless set. `x_max` or `x_{max}` is a subscript. An empty value removes the label |
| `xlim`, `ylim` | the view you choose: `low .. high`, with units or plain numbers in the axis's display unit. Either end can be `auto` (automatic, 5% headroom) |
| `xview`, `yview` | same form, but written by the mouse. It sits over `xlim`/`ylim`; removing it goes back to them |
| `xunit`, `yunit` | the unit the axis is shown in, e.g. `'kN * 'm` (default: the typed range's unit for x, the simplest SI unit for y). [Points](#points) without units are read in it |
| `xscale`, `yscale` | `lin` or `log` (`lin`) |
| `xstep`, `ystep` | tick spacing in the display unit (automatic) |
| `grid` | `on` or `off` (`on`) |
| `legend` | `auto`, `off`, `top right`, `top left`, `bottom right`, `bottom left` (`auto`: top right when there are several series) |
| `size` | `width x height` in pixels, each 200 to 2400 (`520 x 320`) |
| `samples` | 10 to 5000 (`400`) |
| `gaps` | `break` or `error` (`break`) |
| `color`, `width`, `dash`, `marker`, `label` | per series. `color 2: red` is series 2; with no number it applies to every series. Colors are `#rrggbb`, `#rgb` or a name (`red`, `blue`, `green`, `orange`, `purple`, `sky`, `gray`, `black`, `navy`). `dash`: `solid`, `dashed`, `dotted`. `marker`: `none`, `circle`, `square` |
| `note` | `"text" at (x, y)`: a dot and a label at a point in data coordinates. Repeat the line for more |
| `points` | `D` or `x, y`: a set of points drawn as markers, read as `!regression` reads its `data:`, then optionally the units the points are in (`D, 's, 'mm`). Repeat the line for more; see [Points](#points) |

Options are checked as they are read. A bad one is reported on its own line and the plot is drawn without it (a bad `xview` falls back to `xlim`, then to automatic). A plot is limited to 100,000 points (series times samples) because it is redrawn on every edit.

## Points

Points are given as `!regression` takes its data: a matrix with an x row and a y row, one column per point, or two vectors of the same length (row or column), which may have units of their own.

```
t = [0, 1, 2, 3, 4, 5] * 's
v = [10, 6.07, 3.68, 2.23, 1.35, 0.82] * 'm/'s
!plot f(x), x = 0's .. 5's           a curve, with the measurements over it
  points: t, v
  label 2: measured

!plot t, v                           points alone: no range, the axes fit the points
!plot D                              or a matrix with an x row and a y row
```

Points without units, such as a matrix pasted from a spreadsheet, are read in the units the plot gives its axes, so plotting them over a curve with units needs `xunit:` and `yunit:` (or the one for the axis that has units):

```
D = [0, 1, 2, 3; 1.1, 2.9, 5.2, 7.1]        pasted, no units
!plot g(t), t = 0's .. 3's
  points: D
  xunit: 's                                  D's x row is in seconds
  yunit: 'm                                  and its y row in metres
```

Points in other units than the plot's take the units they are in after the data, x's then y's: `points: D, 'ms, 'mm` reads D's x row in milliseconds and its y row in millimetres, and they are drawn in the axes' units. `auto` leaves one as it is (`points: D, auto, 'mm`), and the header takes them too (`!plot D, 's, 'm`). Points that have units already are converted to the ones given.

Without either, a points line on an axis with units says what to add. Points that have units are converted to the axes' units as usual.

Each `points:` line is a series after the functions, numbered in order, so `color 2:`, `marker 2:` and `label 2:` style it. Points are drawn as markers with no line between them: a circle unless `marker: square`. Their values are converted to the axes' units, and a set whose units do not fit an axis is reported on its line. The label is the y vector's name, or the matrix's. A plot of points alone takes its axis names from the two vectors (`t [s]`, `v [m/s]`) and its x range from the points, with 5% to spare.

## Drawing

Plots are the slowest part of a sheet, so in the page they are drawn after the math: as you type, every calculation updates first, and the plots follow one at a time, the one nearest the line you are on first. Under each plot a status line says **⟳ Drawing…** (showing its last picture, dimmed) until it is drawn, then **✓ Up to date**. A plot whose lines and everything above it did not change comes back at once. The exports and the command line draw every plot as before.

## Defaults come in three layers

Each overrides the one before: the built-in values above, then a `!plotspec key: value` line (applies to every plot below it), then the option lines under a plot.

```
!plotspec grid: off
!plotspec size: 560 x 300
!plotspec reset                 clears them
```

`!plotspec` accepts `grid xscale yscale legend gaps size samples width dash marker`.

## The view and the mouse

The picture is drawn on the server from the worksheet text, and the mouse only edits that text.

- **Pan:** drag in the plot.
- **Zoom:** Ctrl + wheel (or a trackpad pinch) about the pointer. A plain wheel still scrolls the results.
- **One axis:** drag or zoom on the strip under or beside an axis.
- **Reset:** double-click (a strip resets only its axis), or the **Reset view** button, which appears only while the mouse has a view to remove.
- **Hover** reads off the nearest point.

When a gesture ends, the new range is written under the plot as `xview:` and `yview:` lines, only for what moved and rounded to the precision on screen. Ctrl+Z undoes it like any other edit. Deleting or rewriting those lines by hand works the same way. Reset removes only those lines, so it returns to your `xlim`/`ylim` if you wrote any.

An axis range has three layers: `xview` over `xlim` over automatic limits from the data. When a zoom narrows the view, the curve is sampled over the visible window again, so it stays smooth. The grid is hidden while you drag.

The text of titles, labels and notes is edited in the editor with the math keys off on those lines; a note's position, `at (x, y)`, is an expression and keeps them.

## Axis labels and the frame

The margins hold room for six characters of tick label. While the numbers on an axis fit in six (`-0.4`, `100`, `5e-11`, `-50000`) the frame is fixed by the size, title and axis labels, however a pan or zoom changes the numbers. Each axis uses one notation: fixed point while every label fits, else scientific with as few digits as tell the ticks apart.

A label needing more than six characters makes the margin grow, and the frame moves with it. That means the pointer can lose the axis strip when a zoom takes the labels back under six characters while the pointer is parked in the part of the strip that existed only to fit the wide ones. For a range that is tiny next to its position (`1e9 .. 1000000005`), telling ticks apart takes 13 characters and the margin grows to match; an axis offset note such as `+1e9` would avoid this and is not built.

## Exporting

- **SVG** and **PNG** buttons under the plot save the picture exactly as shown, with the font embedded (PNG at three times the size). `lens file.lens --plots DIR` writes the same SVGs without a browser.
- **LaTeX.** Export → LaTeX document (and the LaTeX view) writes the plot as a `pgfplots` figure from the same data, limits, scales, labels, colors and dash styles, with units through siunitx. TeX draws it with the document's fonts and its own tick placement, so it is a close match, not the same picture. Use the SVG when you need the exact one.
- **Save** keeps the units a plot uses with the sheet, like any other line.
