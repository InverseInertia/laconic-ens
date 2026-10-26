# Worksheet Syntax

One statement per line. An error on a line never stops the lines after it; a later line that needs a failed variable reports that on its own.

## At a glance

```
# comment                      ## section heading
L = 4.5'm                      a unit starts with an apostrophe
w = 12'kN / 'm                 every unit in a compound gets its own apostrophe
M = w * L^2 / 8 -> 'kN * 'm    -> converts units
A = [2, -1; -1, 2]             matrix: commas within a row, semicolons between rows
f(x, y) = x^2 + y              user function
T = 20'degC -> 'degF           offset units work
z = 3 + 4i   v = 10'V∠30'deg   complex numbers (see Complex Numbers)
σ_max = 3                      Greek letters and subscripts in names
'smoot = 1.7018'm              define a unit (see Units)
~g = 9.81'm / 's^2             global variable (see below)
x` = 2   F! = 5   a@ = 1       dot, arrow and hat over a variable
```

## Names and units

- A **unit** is `'` followed by a Pint unit name: `'kN`, `'mm`, `'degC`, `'°C`, `'ohm`.
- A bare name is always a variable, so `m` can be a mass while `'m` is the metre.
- Only a number followed by units may be written without `*`. `3 x` is an error; write `3*x`.
- Names may use Greek letters and subscripts (`σ_max`, `M_max`). A trailing digit becomes a subscript in the typeset view (`x1` is x₁).
- A number ending in `i` or `j` is imaginary: `4i`, `2.5j`. See [Complex Numbers](Complex-Numbers).
- Constants: `pi`, `e`, and `∞` (Ctrl+G after an `8`). A result may be infinite only when the line uses `∞`, so `1/0` is still an error; `∞ - ∞` and `0*∞` are too.

## Operators

| Operator | Meaning |
|---|---|
| `+ -` | add, subtract (units must agree) |
| `*` | multiply; **matrix product** when both sides are matrices, scaling when one is a scalar |
| `/` | divide (not by a matrix: use `solve` or `inv`) |
| `^` | power; matrix powers need whole exponents |
| `.*` `./` | elementwise |
| `∠` | polar complex number, `10'V∠30'deg` (Ctrl+<); binds between `*` and `+` |
| `->` | convert to the units on the right |

## Functions

`sqrt abs floor ceil sin cos tan asin acos atan exp ln log10`, the [complex](Complex-Numbers) `re im conj arg`, and `heaviside` (aliases `step`, `heav`: 0 below zero, 1 at zero and above), plus the [matrix functions](Matrices) and [`props`](Material-Properties).

Trig functions read a bare number as radians unless `!trigdeg` is active; `asin`, `acos` and `atan` return in the current angle unit.

User functions are defined as `f(x, y) = expression`. They see every variable defined above them.

## Accents over variables

A mark typed right after a name puts an accent over it in the typeset view and the export.

| Mark | Accent | Example | LaTeX |
|---|---|---|---|
| backtick | dot (two backticks: double dot) | ``v` `` | `\dot{v}` |
| `!` | arrow | `F!` | `\vec{F}` |
| `@` | hat | `a@` | `\hat{a}` |

Marks combine (``v`! `` is `\vec{\dot{v}}`). With a subscript the mark goes at the end and sits over the base letter: `F_x!` is `\vec{F}_{x}`. `x`, `x!` and `x@` are three different variables.

## Global variables

A `~` on a definition makes the name global: `~g = 9.81'm / 's^2`. Every later use is the global one, written `~g`. With Math keys on, the editor adds the `~` for you: type `g` on a later line and the `~` appears as soon as the name is finished (a space, an operator, a bracket or Enter). The `~` is source-only and never typeset.

- A global and an ordinary variable can never share a name. Plain `g` after `~g` still means the global, so assigning `g = 12` changes it. That line gets a warning, since a missing `~` there is usually a slip. Defining `~g` for a name already used without `~` is an error.
- Globals are tinted in the editor and colored and underlined in the results. Hover one, in either place, to see the line that made it global. **Mark globals** in the header switches the marks in the results off; a note at the top of the results then says how many globals are unmarked. Warnings still show, and the LaTeX view and export are always plain.
- `!clear` and `!clearf` name the globals they kept: `Cleared a, b. Kept global ~g`.
- Evaluation is top to bottom, so a global is only available below its definition (units are the exception, see [Units](Units)).
- Functions work the same way: `~f(x) = x^2`, used as `f(2)`.

## Commands

A line starting with `!` is a command. It affects every line below it.

| Command | Effect |
|---|---|
| `!clear` | remove all non-global variables (functions are kept) |
| `!clearf` | remove all non-global functions |
| `!noassume` / `!assume` | keep results in the units the arithmetic produced / back to simplest SI |
| `!trigdeg` / `!trigrad` | bare numbers in trig functions are degrees / radians (default) |
| `!short` / `!long` | show only each line's final result / full steps again |
| `!sigfigs n` / `!sigfigsbig n` | show n significant figures (default 4), without / with trailing zeros |
| `!decplace n` | show n decimal places |
| `!complex rect\|polar\|real` | show complex results as `3 + 4i` (default) or `5∠53.13°`, or make any complex result an error, see [Complex Numbers](Complex-Numbers) |
| `!plot ...` | draw a graph, see [Plots](Plots) |
| `!plotspec key: value` | default plot option for the plots below, see [Plots](Plots) |
| `!root`, `!minimize`, `!maximize` | solve equations or optimize, see [Solving and Optimizing](Solving-and-Optimizing) |

Using a name that `!clear` removed says so: `'m' was removed by !clear`. See [Output and Export](Output-and-Export) for what the display commands do.

## Renaming

The Rename button or F2 renames a variable, function or custom unit everywhere (the name at the caret is pre-filled).

- Comments and commands are untouched; text under a plot (titles, labels) is never renamed.
- `m` and `'m` are different names. Built-in names and names already in use are refused.
- Only units the sheet itself defines can be renamed freely. Replacing a standard unit asks for confirmation and, if the new name is not an existing unit, adds a definition for you to adjust.

## Comments, headings, meta lines

- `# text` is a comment, `## text` a section heading (a `\subsection*` in the export).
- `#@ ...` lines are written by LENS (the saved unit block) and are not displayed as comments.
