# Complex Numbers

A number with a trailing `i` or `j` is imaginary, and `∠` builds a complex number from a magnitude and an angle. Complex values carry units like any other value, so phasors and impedances work directly.

```
z = 3 + 4i                     rectangular: i or j after a number
Z = 3'ohm + 4i'ohm             a unit after the imaginary number, as after any number
V = (2 + 1i)*'V                a unit on a bracketed value needs a *
v = 10'V∠30'deg                polar: magnitude ∠ angle (Ctrl+<)
I = v / Z
e^(1i*pi)                      gives -1
```

## Writing them

- `4i`, `4j`, `2.5e3i` and `1i` are imaginary numbers. The letter must come straight after the digits and end the number: `2in` is still the number 2 followed by the name `in`, which is an error.
- There is no bare `i`: write `1i`. A variable named `i` or `j` is allowed, but its line warns that it reads like the imaginary unit (unless `!complex real` is on).
- `4i^2` is `(4i)^2 = -16`, because `4i` is one number. The typeset view shows the brackets.
- `r∠θ` is r·e^(iθ). The angle is read like a trig argument: a bare number is in radians, or degrees after `!trigdeg`, and `30'deg` always works. `∠` binds less tightly than `*` and `/` and more tightly than `+` and `-`, so `2*5∠30'deg` has magnitude 10 and `3 + 5∠30'deg` adds 3 to the phasor. Both sides must be real.
- In the editor, **Ctrl+<** types `∠` (Ctrl+Shift+, on a US keyboard).
- An offset unit such as `'degC` cannot be complex.

## Real stays real

A sheet becomes complex only when a complex number goes in. `sqrt(-4)`, `ln(-1)` and `(-8)^(1/3)` are errors that say how to get the complex result: add `0i`, as in `sqrt(-4 + 0i)`, which gives `2i`. Plots of `sqrt(x)` over negative `x` still leave gaps there.

A result whose imaginary parts all cancel exactly is real again: `(1 + 1i)*(1 - 1i)` is `2`, and `floor` of it works.

## Functions

| Function | Result |
|---|---|
| `re(z)` `im(z)` | real and imaginary parts, with z's unit |
| `abs(z)` | magnitude |
| `arg(z)` | angle, in the current angle unit (radians, or degrees after `!trigdeg`) |
| `conj(z)` | complex conjugate |

Arithmetic, powers (including a complex exponent on a dimensionless base), `sqrt`, `exp`, `ln`, `log10`, the trig functions and the matrix functions accept complex values. `eigvals` and `eigvecs` return complex eigenvalues instead of failing. Functions that order or round numbers (`floor`, `ceil`, `min`, `max`, `heaviside`) and indexes refuse complex arguments.

## Display: `!complex`

| Command | Effect |
|---|---|
| `!complex rect` | the default: `3 + 4i`, `(3 + 4i) V` |
| `!complex polar` | magnitude and angle: `5∠53.13°` after `!trigdeg`, `5∠0.9273 rad` otherwise, and `5 V∠53.13°` with a unit |
| `!complex real` | only real results are allowed: a line whose result is complex is an error. An imaginary part that is only rounding noise (below 10⁻¹² of the value, as in `exp(1i*pi)`) is dropped |

An imaginary number you typed, such as `4i`, is shown as typed whatever the mode. A part too small to show next to the other (10⁻¹² of the value) is left out of the display but kept in the value.

## Plots, solvers and export

- A plotted expression must be real. A complex one is an error that suggests plotting its `re()`, `im()`, `abs()` or `arg()`.
- The solvers work with real numbers. A complex starting value or a complex equation is an error. To solve for a complex unknown, split it into two real ones.
- The LaTeX export writes complex quantities with siunitx's `\complexqty{3+4i}{\ohm}` (siunitx v3), and polar values as `\qty{5}{\volt}\angle 53.13^\circ`.
