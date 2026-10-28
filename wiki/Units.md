# Units

## Default SI display

A computed result is shown in the simplest coherent SI unit, with a familiar name when there is one: kg·m/s² becomes N, kg·m²/s² becomes J, and so on. The named units are:

```
N  J  W  Pa  Hz  C  V  Ω  F  H  S  Wb  T
N/m  m/N  N·m²  Pa·s  W/m²  W/m³  W/(m·K)  J/K  J/(kg·K)  J/(mol·K)  J·s  W/(m²·K⁴)  V/m  F/m  H/m
```

Anything else stays in reduced base units (`m²/s²`, `kg/m³`). Where one dimension has several common names, the first wins:

- energy and torque are both kg·m²/s², shown as **J** (use `-> 'N * 'm` to keep a torque)
- 1/s is shown as **Hz**, or as **rad/s** after `!freq rad` (see [Frequencies](#frequencies-hz-and-rads))
- kg/s² is shown as **N/m**, and s²/kg as **m/N**

**Not reduced:** an explicit `->` conversion, and a line that is only one typed-in quantity (`E = 200'GPa` stays `200 GPa`). `10'kN / 5'mm` has two numbers, so it is a calculation and comes out as `2000000 N/m`.

Angles keep their radians (`asin(0.5)` gives `0.5236 rad`). degF becomes degC, and degC stays. `!noassume` turns the reduction off, so `10'kN * 2'm` shows `20 kN⋅m` instead of `20000 J`; `!assume` restores it.

The pound is `'lbm` (mass) and `'lbf` (force). Pint's own `lb` is removed because it reads as either.

The hour prints as `hr` (`60 km/hr`, `2 hr`), in the results, the PDF and the LaTeX export, because `h` is the symbol of Planck's constant. Type `'h` or `'hr`; both are the hour. Units with a symbol of their own keep it: `kWh`, `Wh`, `mph`.

## The units dialog

**Units** in the header lists every unit LENS knows. Type in the search box to match a unit's name or description (`bar`, `gas`, `pound square`: every word must match), and click a tag to show only the units that have it. Click a unit to insert it at the caret; Ctrl+Z takes it back.

The standard tags are *common*, *constants*, *length*, *area*, *volume*, *mass*, *time*, *speed*, *force*, *pressure*, *energy*, *temperature*, *thermodynamics*, *chemistry*, *electrical*, *imperial* and *currency*. Most take every unit of a dimension (*pressure* holds Pa, bar, psi, inHg and the rest); *common*, *constants*, *thermodynamics*, *chemistry* and *imperial* are hand-picked lists. Global units from Settings come first, under *global units*.

**+ tag** on a unit adds a tag of your own, new or existing (a standard name works too). Your tags show with a dashed outline, and × takes one off a unit; a tag left on no unit goes. They are kept in `settings.json` (see [Settings](Settings)), so they follow you across browsers.

## Physical constants

Physical constants are units, typed with a quote like any other: `'R`, `'k_B`, `'c`. Because they are units, they never take a variable's name, so a sheet can set `R = 5'ohm` and still use `'R`, and a thermodynamics sheet that forgets to define `h` gets an error, not Planck's constant.

```
p = 2'mol * 'R * 300'K / 1'm^3   4989 Pa
E = 'h_P * 'c / 500'nm           3.973e-19 J
n = 2'mol * 'N_A                 1.204e24
```

A line that uses a constant shows its value, even a single typed quantity (`3'mol * 'R` is `24.94 J/K`, not `3 R·mol`). Each constant's suggestion shows what it is and its value in SI, so typing `'gas` or `'boltz` finds it. The **Units** dialog lists them all under the *constants* tag.

| Type | Constant | Value |
|---|---|---|
| `'R` | universal gas constant | 8.31446261815 J/(mol·K) |
| `'N_A` | Avogadro constant | 6.02214076×10²³ /mol |
| `'Av` | Avogadro's number, a plain count (no unit) | 6.02214076×10²³ |
| `'k_B` (or `'k`) | Boltzmann constant | 1.380649×10⁻²³ J/K |
| `'c` | speed of light in vacuum | 299792458 m/s |
| `'h_P` | Planck constant, shown as *h* (`'h` is the hour, shown as hr) | 6.62607015×10⁻³⁴ J·s |
| `'hbar` (or `'ħ`) | reduced Planck constant, h/2π, typeset ħ | 1.05457181765×10⁻³⁴ J·s |
| `'e` | elementary charge | 1.602176634×10⁻¹⁹ C |
| `'sigma` | Stefan–Boltzmann constant | 5.67037441918×10⁻⁸ W/(m²·K⁴) |
| `'G_N` | Newtonian constant of gravitation (`'G` is the gauss) | 6.6743×10⁻¹¹ m³/(kg·s²) |
| `'g_0` | standard gravity | 9.80665 m/s² |
| `'eps_0`, `'mu_0` | vacuum permittivity and permeability | 8.85418781879×10⁻¹² F/m, 1.25663706127×10⁻⁶ H/m |
| `'m_e`, `'m_p` | electron and proton mass | 9.1093837139×10⁻³¹ kg, 1.67262192595×10⁻²⁷ kg |

The values are CODATA's, as Pint has them. To ask for another constant, open an issue; [Development](Development) says how to add one.

## Frequencies: Hz and rad/s

SI writes the hertz and the radian per second both as 1/s, because the radian has no dimension. So by default LENS treats them as one unit: `50'Hz -> 'rad/'s` is `50 rad/s`, `3000'rpm -> 'Hz` is `314.2 Hz`, and a result in 1/s, even an angular frequency such as `sqrt(k/m)`, is shown in Hz. A `->` between Hz and an angle per time shows a note saying so.

To have the 2π put in, say what the sheet's frequencies are with `!freq` above them:

| Command | 1/s results are shown as | `->` between Hz and rad/s |
|---|---|---|
| `!freq hz` | Hz (cycles per second) | 1 Hz = 2π rad/s |
| `!freq rad` | rad/s (angular frequency) | 1 Hz = 2π rad/s |
| `!freq si` (the default) | Hz | 1 Hz = 1 rad/s, as SI has it |

Below `!freq hz` or `!freq rad`, Hz is cycles per second and an angle per time (`'rad/'s`, `'rpm`, `'deg/'s`, `'cycle/'s`) is an angular frequency, so `->` between the two multiplies or divides by 2π:

```
!freq rad
f = 50'Hz
w = f -> 'rad/'s               314.2 rad/s
n = 3000'rpm -> 'Hz            50 Hz
wn = sqrt(40'N/'m / 10'kg)     2 rad/s
fn = wn -> 'Hz                 0.3183 Hz
```

- A result with Hz in its units stays in Hz, so `2*f` is `100 Hz` below `!freq rad` too. Only a result in plain 1/s, with neither Hz nor an angle in it (`sqrt(k/m)`, `1/T`, `v/r`), takes the unit `!freq` names, and `->` reads it the same way: as cycles per second below `!freq hz` and as rad/s below `!freq rad`.
- `->` puts in the 2π itself, so write `w = f -> 'rad/'s`, not `2*pi*f -> 'rad/'s`, which counts it twice. A line that does that shows a warning. `2*pi*f` on its own is still `314.2 Hz`, since a number cannot tell LENS that the cycles became radians.
- Conversions within one kind (`'Hz -> 'kHz`, `'rad/'s -> 'rpm`) are as before.
- Plots read `!freq` too: below `!freq rad` a y axis in 1/s is labelled rad/s.

## Temperatures

`'degC`, `'degF` and `'degRe` are offset units: 0 °C is 273.15 K, not 0 K. A number written right before one is a temperature: `T = 35'degF` is 35 °F, and `T -> 'degC` is 1.667 °C. A temperature difference has a unit of its own, `'delta_degC` or `'delta_degF`, and adding one to a temperature gives a temperature (`20'degC + 5'delta_degC` is `25 °C`).

`*` and `/` (and `.*`, `./`) read an offset unit as an absolute temperature in kelvin, so `35 * 'degF` is 35 × 255.93 K = 8957 K, not 35 °F, and `10'W/'degC` is per 274.15 K, not per degree. The line still runs, with a warning that says so and suggests `35'degF` for a temperature or `'delta_degF` for a difference (write `10'W/'delta_degC`). The same goes for a variable holding a temperature (`T * 2`). The warning appears on the line that runs the arithmetic: a function's definition shows none, and a line that calls it shows the warning with the function's name (`In f(): ...`). A plot or solver block shows it once on its header. A conversion such as `-> 'degF` never warns.

## Strain and other unit ratios

A unit divided by itself would cancel to a plain number, but a strain is read in mm/mm or in/in. So a unit typed over itself stays a ratio: `'mm/'mm`, `'in/'in`, `'m/'m`.

```
e = 0.002'mm/'mm                     0.002 mm/mm
e = 0.5'mm / 200'mm -> 'mm/'mm       0.0025 mm/mm
e = 0.5'in / 200'in -> 'in/'in       0.0025 in/in
s = e * 200'GPa                      5e8 Pa
```

- A ratio is worth exactly 1, so it can be converted into another ratio (`e -> 'in/'in`) and multiplies like a plain number.
- Like `'%`, a result whose only unit is a ratio keeps it (`2 * e` is `0.005 mm/mm`), with or without `!noassume`. Anything else drops it: `e * 200'GPa` is a stress, and `e^2` is a plain number.
- Only a unit typed over the same typed unit makes a ratio. `0.5'mm / 200'mm` computes a value, so it is a plain `0.0025` until you convert it with `-> 'mm/'mm`, and `L / 'mm` still strips a length to a number of millimetres.
- Two different units never cancel, so `-> 'um/'m` (microstrain) already works: `2500 µm/m`.
- In the export a ratio is siunitx's `\per`: `\qty{0.002}{\milli\meter\per\milli\meter}`.

## Percent and currencies

`'%` is a dimensionless unit worth 0.01: `20'% * 50'N` is `10 N`, and `0.05 -> '%` is `5 %`. A result whose only unit is `'%` keeps it (`5'% + 2'%` is `7 %`). Anything else drops it (`50'% * 50'%` is `0.25`). `5%` without the apostrophe is an error that shows the right spelling. In the export it is siunitx's `\percent`.

A currency is a unit named by its ISO 4217 code, such as `'USD`, `'EUR` or `'GBP`. Each currency is a dimension of its own. Exchange rates change, so LENS never converts between currencies: `3'USD + 2'EUR` is an error. Write the rate as a variable:

```
rate = 1.08'USD/'EUR
cost = rate * 250'EUR          270 USD
energy = 0.12'USD/'kWh * 3'MJ  0.1 USD
```

- A result with a currency keeps the units it was typed in, so `0.12'USD/'kWh * 2` is `0.24 USD/kWh`, not reduced to base units. Units of the same kind still cancel.
- Prefixes work: `'kUSD` is a thousand dollars.
- `$` and other currency symbols are not units, because several currencies share them.
- The export declares each currency it uses with `\DeclareSIUnit`.
- Codes: `USD` `EUR` `GBP` `JPY` `CNY` `CAD` `AUD` `NZD` `CHF` `HKD` `SGD` `SEK` `NOK` `DKK` `PLN` `CZK` `HUF` `KRW` `TWD` `INR` `BRL` `MXN` `ZAR` `TRY` `ILS` `AED` `SAR`. Other currencies are not built in yet, and a custom unit cannot add one, because a custom unit cannot create a new dimension. Open an issue to have one added.

## Custom units

A line that starts with a unit and an equals sign defines that unit for the sheet:

```
'smoot = 1.7018'm
'ksmoot = 1000'smoot           may build on earlier units
d = 3'smoot -> 'm              5.105 m
```

- The right-hand side is numbers and units only (no variables) and must be positive.
- A definition applies to the whole sheet, above or below the line, so a block of definitions can sit at the end.
- Names use ASCII letters, digits and `_`, starting with a letter.
- A name that already means something is an error, and the message says what: `'m` is the metre, and `'dsmoot` would read as deci-smoot.
- Offset units such as `'degC` cannot be used in a definition. A custom unit cannot define a new base dimension.
- `!clear` does not remove units.

## Global units

Defined once per machine under **Settings → Units** and available in every sheet, in the web UI and on the command line. They live in the [settings file](Settings).

## Portability

Save and Export carry the definitions a sheet depends on, so a copy opens correctly on another machine.

- **Save (`.lens`)** appends the global units the sheet uses, and the units those are defined in terms of, in a marked block at the end (`#@ unit definitions ...` to `#@ end ...`). Units the sheet already defines are not repeated, so saving twice does not stack blocks.
- **Export (`.tex`)** writes a `\DeclareSIUnit` line per custom unit in the preamble. Names that are not letters only get a letters-only macro (`psi_g` becomes `\psiUnderg`). Built-in units that siunitx does not define, such as `'ft`, `'psi` and `'g0`, are declared the same way (`\foot`, `\poundForcePerSquareInch`, `\standardGravity`). siunitx's own `\hour` prints `h`, so the export declares `\hour` again as `hr`.
- **Opening** a sheet on a machine with its own global of the same name is fine if the sizes agree. If they differ, the definition line shows an error naming the machine's value; rename the unit in the sheet or change the global.
