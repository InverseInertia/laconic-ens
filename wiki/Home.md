# LENS: Laconic Engineering Notebook System

LENS (package name `laconic`) is a units-aware worksheet built on [Pint](https://pint.readthedocs.io). You type one expression per line and see typeset results update as you edit. You can copy LaTeX snippets or export a whole document.

```
L = 4.5'm
w = 12'kN / 'm
M_max = w * L^2 / 8 -> 'kN * 'm        # M_max = 30.38 kN·m
```

## Where to start

| I want to... | Read |
|---|---|
| Install LENS or run it from source | [Getting Started](Getting-Started) |
| Learn the language | [Worksheet Syntax](Worksheet-Syntax) |
| Define my own units | [Units](Units) |
| Work with matrices and tables | [Matrices](Matrices) |
| Look up fluid or material data | [Material Properties](Material-Properties) |
| Draw graphs | [Plots](Plots) |
| Control how results look, export LaTeX | [Output and Export](Output-and-Export) |
| Type faster in the editor | [Editor Shortcuts](Editor-Shortcuts) |
| Change settings or find the settings file | [Settings](Settings) |
| Contribute or understand the code | [Architecture](Architecture) and [Development](Development) |
| See what is not built yet | [Roadmap](Roadmap) |

## Design in three lines

- Worksheets are plain text files (`.lens`), so they diff and merge in git.
- Units are marked with an apostrophe (`'kN`), so a bare name is always a variable.
- One evaluator and one plot spec feed the web page, the LaTeX export and the command line, so all three agree.
