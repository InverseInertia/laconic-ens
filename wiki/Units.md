# Units

## Default SI display

A computed result is shown in the simplest coherent SI unit, with a familiar name when there is one: kg·m/s² becomes N, kg·m²/s² becomes J, and so on. The named units are:

```
N  J  W  Pa  Hz  C  V  Ω  F  H  S  Wb  T
N/m  m/N  N·m²  Pa·s  W/m²  W/m³  W/(m·K)  J/K  J/(kg·K)  V/m  F/m  H/m
```

Anything else stays in reduced base units (`m²/s²`, `kg/m³`). Where one dimension has several common names, the first wins:

- energy and torque are both kg·m²/s², shown as **J** (use `-> 'N * 'm` to keep a torque)
- 1/s is shown as **Hz**
- kg/s² is shown as **N/m**, and s²/kg as **m/N**

**Not reduced:** an explicit `->` conversion, and a line that is only one typed-in quantity (`E = 200'GPa` stays `200 GPa`). `10'kN / 5'mm` has two numbers, so it is a calculation and comes out as `2000000 N/m`.

Angles keep their radians (`asin(0.5)` gives `0.5236 rad`). degF becomes degC, and degC stays. `!noassume` turns the reduction off, so `10'kN * 2'm` shows `20 kN⋅m` instead of `20000 J`; `!assume` restores it.

The pound is `'lbm` (mass) and `'lbf` (force). Pint's own `lb` is removed because it reads as either.

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
- **Export (`.tex`)** writes a `\DeclareSIUnit` line per custom unit in the preamble. Names that are not letters only get a letters-only macro (`psi_g` becomes `\psiUnderg`).
- **Opening** a sheet on a machine with its own global of the same name is fine if the sizes agree. If they differ, the definition line shows an error naming the machine's value; rename the unit in the sheet or change the global.
