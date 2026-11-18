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
σ_max = 3   T_∞ = 300'K        Greek letters and subscripts in names
'smoot = 1.7018'm              define a unit (see Units)
~g = 9.81'm / 's^2             global variable (see below)
$a, $x   q = a*x^2            symbols, and an expression over them (see Symbolic Math)
x` = 2   F! = 5   a@ = 1       dot, arrow and hat over a variable
u& = 3                         bar over a variable
```

## Names and units

- A **unit** is `'` followed by a Pint unit name: `'kN`, `'mm`, `'degC`, `'°C`, `'ohm`.
- A bare name is always a variable, so `m` can be a mass while `'m` is the metre.
- Only a number followed by units may be written without `*`. `3 x` is an error; write `3*x`.
- Names may use Greek letters and subscripts (`σ_max`, `M_max`). A trailing digit becomes a subscript in the typeset view (`x1` is x₁). Spelled-out Greek names typeset as the letter (`sigma_max` is σ<sub>max</sub>), and ∀ (Ctrl+G after a `V`) is the struck-through V some fluid mechanics texts use for volume to keep V for velocity: `∀_cv = 0.2'm^3`.
- A subscript may be infinity, as in a free-stream `T_∞` or `v_∞`: type `T.8` then Ctrl+G, or spell it `T_inf`. Both show as T<sub>∞</sub> (`T_{\infty}`), but they are two different names, as `sigma` and `σ` are. Only a whole `inf` part counts (`x_info` stays as it is), and ∞ is allowed in a name only right after `_`: `∞` on its own is still the constant.
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
| `.f(...)` | call `f` on each element of equal-sized matrices: `.f(A, B)` is the matrix of `f(A_ij, B_ij)` (see [Matrices](Matrices#elementwise-functions)) |
| `∠` | polar complex number, `10'V∠30'deg` (Ctrl+<); binds between `*` and `+` |
| `->` | convert to the units on the right |

## Functions

`sqrt abs floor ceil sin cos tan asin acos atan exp ln log10`, the [complex](Complex-Numbers) `re im conj arg`, and `heaviside` (aliases `step`, `heav`: 0 below zero, 1 at zero and above), plus the [matrix functions](Matrices) and [`props` and `haprops`](Material-Properties).

Trig functions read a bare number as radians unless `!trigdeg` is active; `asin`, `acos` and `atan` return in the current angle unit.

User functions are defined as `f(x, y) = expression`. They see every variable defined above them. A parameter is written as any variable is, with its marks (`` f(V`) = ρ*V` ``) or as ∀.

For a sum over an index, or a vector or matrix built entry by entry, use a `!loop` block; see [Matrices](Matrices#loops).

## Accents over variables

A mark typed right after a name puts an accent over it in the typeset view and the export.

| Mark | Accent | Example | LaTeX |
|---|---|---|---|
| backtick | dot (two backticks: double dot) | ``v` `` | `\dot{v}` |
| `!` | arrow | `F!` | `\vec{F}` |
| `@` | hat | `a@` | `\hat{a}` |
| `&` | bar (a mean value) | `u&` | `\bar{u}` |

Marks combine (``v`! `` is `\vec{\dot{v}}`). With a subscript the mark goes at the end and sits over the base letter: `F_x!` is `\vec{F}_{x}`. `x`, `x!`, `x@` and `x&` are four different variables.

## Symbols

A `$` in front of a name declares it a symbol, on a line of its own: `$x`, or `$a, $b, $c`. An expression over symbols is worked out by sympy and shown as math, and `!symsolve x` solves equations for them. Later uses are the plain name, `x`. A symbol can be global too: `~$g`, the `~` first. See [Symbolic Math](Symbolic-Math).

## Global variables

A `~` on a definition makes the name global: `~g = 9.81'm / 's^2`. Every later use is the global one, written `~g`. With Math keys on, the editor adds the `~` for you: type `g` on a later line and the `~` appears as soon as the name is finished (a space, an operator, a bracket or Enter). The `~` is source-only and never typeset.

- A global and an ordinary variable can never share a name. Plain `g` after `~g` still means the global, so assigning `g = 12` changes it. That line gets a warning, since a missing `~` there is usually a slip. Defining `~g` for a name already used without `~` is an error.
- Globals are tinted in the editor and colored and underlined in the results. Hover one, in either place, to see the line that made it global. **Mark globals** in the header switches the marks in the results off; a note at the top of the results then says how many globals are unmarked. Warnings still show, and the LaTeX view and export are always plain.
- `!clear`, `!clearf` and `!clearsym` name the globals they kept: `Cleared a, b. Kept global ~g`.
- Evaluation is top to bottom, so a global is only available below its definition (units are the exception, see [Units](Units)).
- Functions work the same way: `~f(x) = x^2`, used as `f(2)`.

## Commands

A line starting with `!` is a command. It affects every line below it.

In the results, every `!` line is marked the same way, so you can see what was called as you scroll: the line as typed, in the code font under a dashed rule. A one-line command adds what it did (`!sigfigs 3  →  Results show 3 significant figures`); a plot, solver, regression or symbolic solve shows its `!plot ...`, `!root ...` line over its picture or values. The exports leave the marks out (the LaTeX document keeps one-line commands as `%` comments).

| Command | Effect |
|---|---|
| `!clear` | remove all non-global variables (functions are kept) |
| `!clearf` | remove all non-global functions |
| `!clearsym` | remove all non-global symbols (declared with `$`), keeping other variables |
| `!noassume` / `!assume` | keep results in the units the arithmetic produced / back to simplest SI |
| `!trigdeg` / `!trigrad` | bare numbers in trig functions are degrees / radians (default) |
| `!short` / `!long` | show only each line's final result / full steps again |
| `!adnauseum` | show all the working: every intermediate result and every unit cancellation, see [Output and Export](Output-and-Export#all-the-working) |
| `!hide` / `!show` | hide the results of the lines below / show them again; hidden lines still run, see [Output and Export](Output-and-Export#hiding-lines) |
| `!sigfigs n` / `!sigfigsbig n` | show n significant figures (default 4), without / with trailing zeros |
| `!decplace n` | show n decimal places |
| `!freq hz\|rad\|si` | Hz is cycles per second, so `->` between Hz and rad/s puts in the 2π, and 1/s results show in Hz / rad/s; `si` (default) keeps 1 Hz = 1 rad/s, see [Units](Units#frequencies-hz-and-rads) |
| `!rpn` / `!rpn off` | type the expressions below in reverse Polish (`F = m a *`) / in infix again (default), see [Reverse Polish input](#reverse-polish-input) |
| `!complex rect\|polar\|real` | show complex results as `3 + 4i` (default) or `5∠53.13°`, or make any complex result an error, see [Complex Numbers](Complex-Numbers) |
| `!plot ...` | draw a graph, see [Plots](Plots) |
| `!plotspec key: value` | default plot option for the plots below, see [Plots](Plots) |
| `!root`, `!minimize`, `!maximize` | solve equations or optimize, see [Solving and Optimizing](Solving-and-Optimizing) |

Using a name that `!clear` removed says so: `'m' was removed by !clear`. See [Output and Export](Output-and-Export) for what the display commands do.

## Reverse Polish input

`!rpn` on a line of its own makes the lines below it reverse Polish (RPN): values first, then what is done to them, every value and operator separated by spaces. `!rpn off` (or the end of the sheet) returns to infix; `!rpn on` is the same as `!rpn`. `!clear` leaves the mode alone. The results pane and every export show the lines in ordinary infix, so the input is quick and the output still reads as math.

```
m = 2'kg   a = 3'm/'s^2
!rpn
F = m a *                      F = m · a = 6 N
3'm 4'm +                      7 m
hyp(x, y) = x 2 ^ y 2 ^ + sqrt hyp(x, y) = √(x² + y²)
c = 3 4 hyp                    c = hyp(3, 4) = 5
v = 9.81'm/'s^2 'ft/'s^2 ->    convert: v -> 'ft/'s^2
A B hstack/2                   hstack(A, B)
x neg                          -x
!rpn off
```

- **What is RPN**: an assignment keeps its name on the left (`F = m a *`); its right side is RPN. A bare expression is RPN throughout. A function definition keeps its head, `f(x) = x 2 ^ 1 +`, and takes its body in RPN. Unit definitions, `$` symbol declarations, comments, headings, commands and every line a block owns (plot options, solver equations, a `!loop`'s lines) are read as usual.
- **Values**: a number written as anywhere in the sheet, units and all (`3'm`, `2.5e3'Pa`, `9.81'm/'s^2`, `-4`, `4i`, `∞`); a unit on its own (`'km`, for `->`); a quoted string (`"Water"`); a matrix, written as usual (`[1, 2; 3, 4]`, one value, its entries read as infix); or a name.
- **Operators** take two values: `+ - * / ^`, `.*` and `./` (elementwise), `∠` (polar: `5'V 30'deg ∠`) and `->` (convert the value below into the units on top: `x 'km ->`). `neg` is unary minus, so in RPN `neg` cannot be a variable's name.
- **Functions**: a user function, or a built-in that always takes the same number of arguments, is called by its name alone and takes that many values (`x sqrt`, `A i idx`, `3 4 hyp`). Any function can be given its number of values after a slash: `A B hstack/2`, `"Tcrit" "Water" props/2`, `n zeros/1`; that is the only way to call one that takes a varying number (`hstack`, `vstack`, `zeros`, `ones`, `props`, `haprops`). A period in front calls it on each element: `A B .f/2`.
- **Names**: a variable the line can see always means the variable, as does a function definition's parameter, so after `f = 10`, `f 1 +` is 11; `f/1` still calls the function `f`.
- **Errors** are the line's own: ``RPN: `+` needs two values, the stack has one`` when the stack runs short, `RPN: 2 values are left on the stack; an expression must leave exactly one` when it does not end with one value, and a note when a token is not RPN (`m*a`, `sqrt(2)`).
- Rename (F2) renames names on RPN lines too. On an RPN line the editor's math keys are off, since they write infix; see [Editor Shortcuts](Editor-Shortcuts#math-keys).

## Renaming

The Rename button or F2 renames a variable, function or custom unit everywhere (the name at the caret is pre-filled).

- Comments and commands are untouched; text under a plot (titles, labels) is never renamed.
- `m` and `'m` are different names. Built-in names and names already in use are refused.
- Only units the sheet itself defines can be renamed freely. Replacing a standard unit asks for confirmation and, if the new name is not an existing unit, adds a definition for you to adjust.

## Comments, headings, meta lines

- `# text` is a comment, `## text` a section heading (a `\subsection*` in the export).
- `#@ ...` lines are written by LENS (the saved unit block) and are not displayed as comments.
- The browser's spellchecker is on while the caret is on a comment, a heading or a plot's title, label or note, and off on calculations, so names and units are never marked. The editor is one text box, and the browser only checks words as you type them and drops every mark when spellcheck goes off: a misspelling is underlined while you write the line, and the marks go away when the caret moves to a calculation.
