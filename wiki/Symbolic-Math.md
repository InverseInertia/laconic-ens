# Symbolic Math

Besides numbers with units, a sheet can work with **symbols**: names that stand for themselves, evaluated by [sympy](https://www.sympy.org). Declare them with a `$`, write expressions over them, and solve equations for them with `!symsolve`. The results are typeset like any other line, on the page and in the LaTeX export.

```
$a, $b, $c, $x                 declare symbols
q = a*x^2 + b*x + c            q holds the expression, shown as math
!symsolve x                    solve for x: two solutions, both listed
  equation: q = 0
  pick: 2                      below the block, x holds the second
$m, $acc, $F
!symsolve acc
  equation: F = m*acc          acc = F/m below the block
m = 2'kg
F = 10'N
a_1 = acc                      every symbol has a value now: 5 m/s²
```

`laconic/examples/symbolic.lens` is a worked sheet.

## Declaring symbols

A line made of `$` names declares them: `$x`, or several at once, `$a, $b, $c`, each with its own `$`. A declared name is a variable whose value is the symbol itself; it is visible below its line, `!clear` removes it, and Rename (F2) renames it, like any other variable. `!clearsym` removes only the symbols, and keeps global symbols and every other variable: a symbol that has been given a value is an ordinary variable by then, so it is kept too.

- **Global symbols.** `~$g` declares a global symbol, the `~` first: `!clear` keeps it and every later use means it, as for [global variables](Worksheet-Syntax#global-variables).
- **Uses are plain names.** The `$` is written only on the declaration. Everywhere else write `x` (or `~g`); `$x` inside an expression is an error that says so.
- **A symbol has no value.** `$x = 2` is an error. To give a symbol a value, assign it on a later line, `x = 2`; below that line `x` is the number.
- Names work as everywhere else: `$σ_max` is σ<sub>max</sub>, `$v!` is a vector v, `$T_inf` is T<sub>∞</sub>.

Symbols are shown in their own color, the theme's **Symbols** color (Settings → Theme): tinted in the editor and colored in the results. Only globals are underlined, so a global symbol is in the symbol color and underlined. Hovering a symbol names the line that declared it. Suggestions list your symbols with *symbol* beside them.

## Expressions over symbols

A line whose expression reaches a symbol, directly, through a variable that holds an expression, or through a user function, is worked out by sympy. When symbols are left in the result, the line shows it as math and an assignment stores the expression:

| Typed | Shows |
|---|---|
| `q = a*x^2 + b*x + c` | q = a·x² + b·x + c |
| `x/2 + sqrt(2)*x` | x/2 + √2·x: numbers stay exact |
| `k = 3` then `r = k*a` | r = k·a = 3·a: a variable that is a plain number goes in as that number |
| `f(u) = u^2 + 1` then `f(t)` | t² + 1 |
| `4i * s` | 4·i·s |

Functions sympy knows go in as functions: `sqrt abs floor ceil heaviside sin cos tan asin acos atan exp ln log10 re im conj arg`.

### Numbers, units and late binding

A symbolic result has **no units**. So:

- A number without units (typed, or a variable holding one) goes in as that number. Decimals keep the sheet's display precision when shown.
- A number **with** units, a matrix, a `->` conversion or a call sympy does not know (`props`, the matrix functions) cannot go into a symbolic result. The line says so, for example `L (2 m) has units, and a symbolic result cannot carry units. Declare L a symbol too ($L), or give the symbols values above this line`.

Symbols **bind late**. When a stored expression is used, each symbol in it takes the value of the variable of that name where it is used. So once every symbol in an expression has a value, the expression is a number, worked out with Pint, **units and all**:

```
$F, $m
acc = F/m                 acc = F/m
F = 10'N
m = 2'kg
z = acc                   z = acc = 10 N / 2 kg = 5 m/s²
w = acc -> 'ft/'s^2       16.4 ft/s²
```

The middle stage shows the expression with the values put in. The same works wherever the sheet needs a number: a plot over a symbol draws its expression (`$t`, `y = t^2`, `!plot y, t = 0 .. 1`), a numeric `!root` can read a derived formula, and a user function's parameter named like a symbol gives it its value inside the function.

A symbol still without a value where a number is needed is an error: `'x' is a symbol and has no value here`.

### Angles

Symbolic trig works in radians. Below `!trigdeg`, a trig function of a symbol is an error (`sin() of a symbol works in radians, and !trigdeg is on`); a trig function of a plain number is still read in degrees there.

## Solving: `!symsolve`

```
!symsolve x, y            the symbols to solve for, declared above with $
  equation: x + y = a     lhs = rhs, or one expression that is zero
  equation: x - y = 1     as many equations as you need
  pick: 1                 which solution the unknowns hold below, when there are several
```

The block is solved by `sympy.solve` every time the sheet runs, like a [regression](Solving-and-Optimizing#regression): there is no Run button and nothing is stored in the file. Its row lists the solutions, numbered when there are several.

- **One solution:** below the block each unknown holds it, as after `!root`. A solution with no symbols left in it is a number (`x^2 = 4` with `pick: 2` gives `x = 2`).
- **Several solutions:** the unknowns stay symbols below the block, and the row says so. Add `pick: n` to use solution n.
- **No solution:** the block is an error, `No solution: sympy finds none for x`. Some equations are beyond sympy; the error then says that sympy cannot solve it.
- Each unknown must be a symbol where the block is. An unknown a block above has already solved holds that answer, so declare it again (`$x`) to solve for it once more.
- Equations take dimensionless numbers like any symbolic expression, and no units. `<=` and `>=` are not allowed.

Rename, suggestions and the option keys work as in the other blocks. `pick:` is the only option besides `equation:`.

## In the export

Symbolic results print in the LaTeX, Markdown and PDF exports the way they look on the page; the solutions of a block with several are a `gathered` environment, one per row. A declaration line is kept as a comment in the `.tex` file (`% $a, $b`), like a command.

## Limits

- Symbols have no assumptions (real, positive), so sympy keeps the general answer: `sqrt(x^2)` stays as it is, and `x^2 = -1` has the solutions ±i.
- Results are what sympy gives, without a separate simplify step.
- A solve sympy finds hard can take a while, and it runs as you type. Its answer is kept for the same equations, so other edits do not solve it again.
- There are no symbolic matrices, derivatives or integrals yet.
