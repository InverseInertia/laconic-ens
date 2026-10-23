# Material Properties

`props` calls [CoolProp](http://www.coolprop.org): about 130 pure fluids, mixtures, humid air, and incompressible brines and coolants. It mirrors CoolProp's `PropsSI`: the output key, up to two state inputs as key and value pairs, then the fluid. Text goes in double quotes, which is the only place a sheet uses them.

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

CoolProp is a regular dependency and adds about 5 MB to the standalone binary. It is imported on first use, so sheets without `props` start fast.
