# Solving and Optimizing

`!root`, `!minimize` and `!maximize` find unknowns with scipy (`scipy.optimize.root`, `brentq` and `minimize`). A block names the unknowns and lists its equations or objective on indented lines below it. The starting values are ordinary variables defined above the block, and they carry the units.

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

## Command line

```
lens sheet.lens --solve      # run every block that is not up to date, top to bottom, and write the results into the file
lens sheet.lens              # print each block with its status
```

A solver run is a worker process started with `multiprocessing` (spawn). A script that imports `laconic.server` itself needs the usual `if __name__ == "__main__":` guard. The standalone programs handle this themselves.

`examples/solve.lens` is a worked sheet.
