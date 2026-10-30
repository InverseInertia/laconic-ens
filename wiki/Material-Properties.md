# Material Properties

`props` calls [CoolProp](http://www.coolprop.org): about 130 pure fluids, mixtures, and incompressible brines and coolants, and `haprops` gives the properties of [humid air](#humid-air). It mirrors CoolProp's `PropsSI`: the output key, up to two state inputs as key and value pairs, then the fluid. Text goes in double quotes, which is the only place a sheet uses them.

```
rho  = props("D", "T", 20'degC, "P", 1'atm, "Water")       998.2 kg/m³
mu   = props("V", "T", 300'K, "P", 1'bar, "Air") -> 'uPa * 's
Tsat = props("T", "P", 5'bar, "Q", 0, "Water") -> 'degC    saturation temperature
Tc   = props("Tcrit", "Water")                              fixed properties need no state
```

## Rules

- Inputs are converted to CoolProp's SI units, so any compatible unit works (`'degC`, `'psi`, `'bar`). A bare number where a unit is needed is an error rather than a guess.
- The result carries the SI unit. Convert with `->`.
- Prefix the fluid for another backend (`"INCOMP::Water"`, `"HEOS::Water"`) or write a mixture (`"Methane[0.9]&Ethane[0.1]"`).

## Common keys

| Key | Property | Key | Property |
|---|---|---|---|
| `D` | density | `V` | viscosity |
| `T` | temperature | `L` | conductivity |
| `P` | pressure | `A` | speed of sound |
| `H` | enthalpy | `I` | surface tension |
| `S` | entropy | `Q` | quality |
| `U` | internal energy | `Prandtl` | Prandtl number |
| `Cpmass` | specific heat (const. pressure) | `Tcrit` `Pcrit` | critical point |
| `Cvmass` | specific heat (const. volume) | `M` | molar mass |

Any other CoolProp key works too.

## Humid air

`haprops` mirrors CoolProp's `HAPropsSI`: the output key, then three state inputs as key and value pairs, one of them the pressure. There is no fluid.

```
w   = haprops("W", "T", 25'degC, "P", 1'atm, "R", 0.5)            0.009926   humidity ratio
Twb = haprops("B", "T", 25'degC, "P", 1'atm, "R", 0.5) -> 'degC   17.88 °C   wet bulb
h   = haprops("H", "T", 25'degC, "P", 1'atm, "W", w)               per kg of dry air
```

| Key | Property | Key | Property |
|---|---|---|---|
| `T` | dry-bulb temperature | `H` | enthalpy per kg dry air (`Hha` per kg humid air) |
| `B` | wet-bulb temperature | `S` | entropy per kg dry air (`Sha`) |
| `D` | dew-point temperature | `V` | volume per kg dry air (`Vha`) |
| `P` | pressure | `C` | specific heat per kg dry air (`Cha`, `CV`, `CVha`) |
| `R` | relative humidity, 0 to 1 | `M` | viscosity |
| `W` | humidity ratio, kg water per kg dry air | `K` | conductivity |
| `Y` | water mole fraction | `Z` | compressibility factor |
| `P_w` | partial pressure of water | | |

CoolProp's other names work too (`Tdb`, `Twb`, `Tdp`, `RH`, `Omega`, `HumRat`, `Hda`, `Vda`, `cp`, `mu`, `k`). Relative humidity, the humidity ratio and the mole fraction are plain numbers, so `0.5` is 50 %.

CoolProp is a regular dependency and adds about 5 MB to the standalone binary. It is imported on first use, so sheets without `props` or `haprops` start fast.
