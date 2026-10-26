# Context

Domain terms used in the code and the docs.

## Units

**Unit catalogue** (`laconic/catalogue.py`): the one module that knows about the unit families needing more than Pint gives. Other modules ask it rather than keeping their own lists.

**Unit family**: a group of units that share one policy in the catalogue: currencies, percent, constants with subscripted symbols, Pint units siunitx lacks.

**Currency**: a unit named by its ISO 4217 code ('USD, 'EUR). Each is a dimension of its own, so currencies never convert into each other; an exchange rate is an ordinary variable.

**Declared unit**: a unit the `.tex` export gives a `\DeclareSIUnit` of its own, because siunitx does not define it (a user-defined unit, a currency, 'ft, 'g0). `Fmt.declarations()` returns the lines for the units a document printed.
