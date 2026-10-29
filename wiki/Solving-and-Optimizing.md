# Solving and Optimizing

`!root`, `!minimize` and `!maximize` find unknowns with scipy (`scipy.optimize.root`, `brentq` and `minimize`). A block names the unknowns and lists its equations or objective on indented lines below it. The starting values are ordinary variables defined above the block, and they carry the units. `!regression` fits a polynomial to points; see [Regression](#regression).

```
x = 1'm                              starting values
y = 1'm
!root x, y
  equation: x^2 + y^2 = 4'm^2        as many equations as unknowns (a matrix counts every entry)
  equation: x = y
z = x * 2                            below the block, x and y hold the solution

d = 1'm
!minimize d                          !maximize works the same way
  objective: cost(d)                 one number, any unit
  constraint: d >= 0.5'm             <=, >= or =
  bounds d: 0'm .. 3'm               either end may be `auto`; `bounds: ...` when there is one unknown
  method: SLSQP
```

## Options

| Option | Meaning |
|---|---|
| `equation:` | `lhs = rhs`, or one expression that is zero. Both sides must have the same units. A matrix gives several equations |
| `objective:` | what to minimize or maximize |
| `constraint:` | `lhs <= rhs`, `>=` or `=`; several lines are allowed |
| `bounds name:` | limits on one unknown. On a `!root` with a single unknown they bracket the root and select `brentq`, which needs a sign change between them |
| `method:` | root: `hybr` (default), `lm` (also takes more equations than unknowns, as least squares), `broyden1`, `broyden2`, `krylov`, `brentq`. Optimization: `BFGS`, `L-BFGS-B`, `Nelder-Mead`, `Powell`, `TNC`, `SLSQP`, `trust-constr`, `COBYLA`. The default is `BFGS`, or `L-BFGS-B` with bounds, or `SLSQP` with constraints |
| `tol:` `maxiter:` | passed to scipy |
| `timeout:` | seconds before a run is killed (default 300) |
| `autorun:` | `on` re-solves automatically (see below); the Auto checkbox writes this line |

The solver works on plain numbers in the unit each unknown was started in, so `x = 1'm` and `x = 1000'mm` are the same problem at different scales. Start in the unit your answer is of a sensible size in.

The block is checked as you edit: an undefined name, a unit mismatch or the wrong number of equations is reported on the line, before anything runs. Rename (F2) changes names inside blocks like anywhere else.

## Running, and what is stored

Solvers can be slow, so evaluating a sheet **never runs one**. Under each block the output side shows the values and a control strip:

- **Run** solves in a separate worker process and writes the answer into the block as one line: `  #@ result {"hash":"54401af82124","method":"hybr","values":[...],...}`. It is plain text in the `.lens` file, so a saved sheet opens with its answers and Ctrl+Z undoes a run.
- **Interrupt** kills the worker, which is the only way to stop a calculation that is stuck inside one call. Nothing is stored. A run is also killed when it passes its `timeout:`, and when the inputs change while it is running (its answer would describe inputs that no longer exist).
- **Auto** (`autorun: on`) solves again about 0.7 s after the inputs stop changing. A run that fails or is interrupted is not repeated automatically for the same inputs.
- **Verify** solves again from the same starting values and compares with the stored answer (agreement to 1e-6 relative). It never changes the sheet, and says if the answer drifted, for example under a different scipy version.
- **Log** opens the full log: the method, every evaluation with the values tried, warnings, the reason a run stopped, and for a block opened from a file what its stored result says. A run that does not converge or hits an error (a division by zero while searching, an expression leaving its domain) says where and why.

## Is the stored result current?

The hash covers everything the block reads: its own lines (apart from `timeout:` and `autorun:`, comments and spacing), the starting values, every variable and user function its expressions reach, the units they use, and the trig angle mode, with numbers cut to 12 significant digits so another machine's rounding does not count. The status under the block is one of:

| Status | Meaning |
|---|---|
| ✓ Up to date | the stored result belongs to the current inputs |
| ⚠ Out of date | the inputs changed since the result was computed. The old values are still shown, dimmed |
| ○ Not run yet | no result. The unknowns hold their starting values |
| ⟳ Running | a worker is solving |
| ✕ Failed, ■ Interrupted | the last run did not store anything. Open the log |

Any line computed from an out-of-date block (and any plot) gets a ⚠ beside it, through variables and user functions alike, and a later block that reads an out-of-date unknown is flagged as built on stale values. Only a result that converged is ever stored. The LaTeX export prints the stored values, with a comment line above any block that is out of date.

## Regression

`!regression` fits a polynomial to points by least squares, or any function of one or more variables given as a [model](#fitting-a-model). It is written like the solver blocks, but a fit is quick and exact, so it is worked out every time the sheet runs: there is no Run button and nothing is stored in the block.

```
D = [0, 1, 2, 3; 1.1, 2.9, 5.2, 7.1] * 'm      a matrix of points, one column each: the x row, then the y row
!regression a, b, c                            the coefficients, lowest power first: y = a + b·x + c·x²
  data: D
  r2: R2                                       optional: a name for R², the coefficient of determination
h = a + b*2'm + c*(2'm)^2                      below the block, a, b, c and R2 hold the fit

t = [0, 1, 2, 3] * 's                          x and y in different units: give them as two vectors
s = [0.1, 4.8, 19.7, 44.0] * 'm
!regression s0, v0, g2
  data: t, s                                   s0 in m, v0 in m/s, g2 in m/s²

x = [1, 2, 3, 4, 5]
y = [2.1, 3.9, 6.2, 7.8, 10.1] * 'N
!regression p                                  one name: a vector of every coefficient (p_1 is the constant)
  data: x, y
  degree: 3
```

| Option | Meaning |
|---|---|
| `data:` | the points: a matrix with 2 rows (x, then y) and one column per point, or two vectors of the same length, `data: x, y` (row or column vectors). Every entry of a matrix shares one dimension, so x and y in different units need the two-vector form. A table pasted the other way up (one row per point) needs `transpose()` |
| `degree:` | the polynomial's degree, 0 to 20. With several names the degree is one less than their number, and `degree:` may be left out; with one name it is needed |
| `r2:` | a name for R² (1 − residual sum of squares / total sum of squares) |

The coefficient of xᵏ has the units of y / xᵏ, so the fit is the same whatever units the data is typed in. A single name holds every coefficient as one vector only when x has no units, since otherwise each coefficient has units of its own. That vector lies as the x values do: a row for a matrix's x row or a row vector, a column for a column vector. Offset temperatures (°C, °F) are fitted in kelvin. A term whose part of y is rounding error (the zero coefficient of an exact fit) is shown as 0.

The row shows the fitted polynomial in the names the data came from (`s = s0 + v0 t + g2 t²`), then each coefficient and R². A fit needs at least degree + 1 different x values; real, finite numbers only. Data that reads an out-of-date solver result makes the fit, and everything computed from it, out of date as well (⚠). The exports print the polynomial and one row per value. Rename (F2) reaches the names in the header, `data:`, `model:` and `r2:`.

### Fitting a model

A `model:` line fits any function instead of a polynomial, of one variable or several. It is written as a function definition: its parameters are the data's variables, and the header's names are the coefficients to fit, each of which must appear in it.

```
t = [0, 1, 2, 3, 4, 5] * 's
v = [10, 6.07, 3.68, 2.23, 1.35, 0.82] * 'm/'s
!regression A, k
  model: f(t) = A*exp(-k*t)                    A in m/s, k in 1/s, worked out from the model
  data: t, v
f(2's)                                         below the block, f is a function like any other

!regression a, b, c
  model: w(x, z) = a + b*x + c*z               several variables: one vector each, then y
  data: x, z, w                                or a matrix with an x row, a z row and a w row
```

| | |
|---|---|
| `data:` | one vector per variable in the model's order, then the y values (`data: x, z, w`); or a matrix with a row for each variable, then the y row, one column per point |
| units | each coefficient gets the units that make the model come out in y's units, worked out from the model: k in `exp(-k*t)` is in 1/s, A in m/s. A coefficient the model leaves free (`a*b*x`) is a plain number. A power whose exponent is fitted needs a base without units, `a*(x/1'm)^b` |
| start | the fit starts from each coefficient's value above the block, which keeps its units (`w = 0.9'rad/'s`), or from 1. A model that is not linear in its coefficients may need a start near the answer; the row says when the fit did not settle |

The model is fitted by least squares (`scipy.optimize.least_squares`), every time the sheet runs, so it takes at most 5000 points. It can use the sheet's names and call its functions; `degree:` is for a polynomial only. The row shows the model in the coefficients' names, then each coefficient and R².

## Command line

```
lens sheet.lens --solve      # run every block that is not up to date, top to bottom, and write the results into the file (every block with the same inputs gets the result)
lens sheet.lens              # print each block with its status
```

A solver run is a worker process started with `multiprocessing` (spawn). A script that imports `laconic.server` itself needs the usual `if __name__ == "__main__":` guard. The standalone programs handle this themselves.

`laconic/examples/solve.lens` is a worked sheet.
