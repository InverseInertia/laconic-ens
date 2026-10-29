# Matrices

Matrix work runs on numpy arrays with the unit carried alongside. Indexes count from 1. Every entry of a matrix shares one dimension; entries in other units of that dimension are converted.

```
A = [2, -1; -1, 2]             commas within a row, semicolons between rows
F = [10; 5] * 'kN              a unit on its own is 1 of that unit
x = solve(A, F)
A * B                          matrix product (scaling if one side is scalar)
A .* B     A ./ B              elementwise
```

## Functions

| Function | Result |
|---|---|
| `idx(A, i)` | Element `i` of a vector, or row `i` of a matrix. Typeset as a subscript `A_i` |
| `elem(A, i, j)` | Row `i`, column `j`. Typeset `A_i,j`. Both can be nested: `idx(elem(A, 1, 2), 3)` |
| `row(A, i)` `col(A, j)` | A row as a row vector, a column as a column vector |
| `rows(A)` `cols(A)` `length(A)` | Sizes |
| `det` `inv` `pinv` `transpose` `trace` `rank` `cond` `norm` | Usual meaning |
| `solve(A, b)` `lstsq(A, b)` | Square solve, least-squares solve for any shape |
| `chol(A)` | Lower-triangular `L` with `A = L * transpose(L)` |
| `eigvals(A)` `eigvecs(A)` `svdvals(A)` | Real eigenvalues (ascending), unit eigenvectors as columns, singular values |
| `dot(a, b)` `cross(a, b)` `kron(A, B)` | Products |
| `diag(v)` `diag(A)` | Vector to diagonal matrix, matrix to its diagonal |
| `identity(n)` `zeros(r, c)` `ones(r, c)` | Constant matrices (`zeros(n)` is square) |
| `hstack(A, B, ...)` `vstack(A, B, ...)` | Join side by side or one above the other |
| `sum` `mean` `min` `max` | Over every entry |

Entries may be complex (see [Complex Numbers](Complex-Numbers)), and `eigvals` and `eigvecs` return complex eigenvalues and eigenvectors when the matrix has them. `min` and `max` need real entries.

To fit a polynomial to points held in a matrix (an x row and a y row, one column per point), use a `!regression` block; see [Solving and Optimizing](Solving-and-Optimizing#regression).

## Loops

A `!loop` block runs the lines indented under it once for each whole number from the first value to the last, both included. Use it for a sum over an index, or to build a vector or matrix entry by entry.

```
S = 0
M = zeros(3, 3)                     the matrix a loop fills is made first, at its size
!loop i = 1 .. 3                    the index and its range; 1 .. 0 runs no times
  S = S + i^2                       a line assigns a name, reading what the passes before left
  !loop j = 1 .. i                  a loop inside a loop, indented under it; it can read i
    elem(M, i, j) = 1/(i + j - 1)   an entry: elem(M, i, j) = ..., or idx(v, i) = ... for a vector's
S                                   14: below the block, each name holds its last value
M                                   the lower triangle of the 3 × 3 Hilbert matrix
```

| | |
|---|---|
| lines | each line assigns a name (`S = S + i`), sets an entry of a vector or matrix that exists above the block (`idx(v, i) = x`, `elem(M, i, j) = x`, or a matrix's whole row, `idx(M, i) = [a, b]`), or is another `!loop` with its lines indented under it. Comments may go between them |
| the range | `!loop i = a .. b` counts up from `a` to `b` in steps of 1; both are plain whole numbers, and may be expressions of names above or of an outer loop's index (`!loop j = 1 .. i`) |
| below the block | every name the block assigned holds its value after the last pass, and is shown on the block's row with the steps. The index is gone again (a variable it hid is back), and a vector or matrix above the block keeps its old value on the lines above |
| units | an entry is in the dimension of its matrix; a matrix of zeros, as `zeros()` makes, takes the units of the first entry put in it |
| errors | a line that fails says so, with the index values it failed at (`at i = 2, j = 3`), and the names the block assigns are marked out of date below it |

The block is worked out every time the sheet runs, so it stops after 10,000 lines (all passes together) to keep the sheet quick: for a whole vector at once, `sum(v .* v)` and the other matrix operators are much faster than a loop. The row typesets the block as steps, `for i = 1, …, 3` with `S ← S + i²` under it, then the values it left, and the exports print it the same way.

## Large matrices

A matrix with more than 8 rows or columns is shown collapsed in the results pane: its first 3 and last 2 rows and columns, with ⋮, ⋯ and ⋱ standing for the rest. The button under it (**Show all 2 × 120**) shows it whole, and **Collapse** puts it back; the choice holds for that line while you edit. Only the display changes: the value is the whole matrix.

The LaTeX, Markdown and PDF exports print large matrices collapsed the same way, so a page of data does not run off the page. A single line's LaTeX snippet (the LaTeX view and its Copy button) keeps the matrix whole.

## Indexing keys

Ctrl+[ wraps the term on the left (or the highlight) in `idx( , )`, and Ctrl+Shift+[ in `elem( , , )`, with the caret in the first index slot.

## Pasting tables

Pasting a table turns it into a matrix. Accepted sources: cells copied from Excel or Sheets, an Obsidian or other Markdown pipe table, comma separated rows, or a column of numbers.

- Padding, non-breaking spaces and CRLF are ignored.
- `1,234`, `1 234`, `1,5`, `(5)`, `50%`, `$1,200` and a typographic minus are read as numbers.
- A header row or label column of text is dropped, and empty cells become 0.
- One unit shared by every cell is factored out (`10 kN` cells give `[...] * 'kN`).
- Tables with text cells or mixed units paste as plain text, and so does Ctrl+Shift+V.
- The status line says what was dropped. The **Math keys** checkbox turns table paste off.
