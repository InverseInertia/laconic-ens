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

Complex eigenvalues are reported as an error, not returned.

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
