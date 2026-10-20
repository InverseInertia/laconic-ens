# Vendored d3 modules

`d3.min.js` is the prebuilt UMD file of each module below, concatenated in dependency order.
Each file attaches to the global `d3`, so the page needs no module loader. Nothing here is edited.

| Module | Version | License |
|---|---|---|
| d3-array | 3.2.4 | ISC |
| d3-color | 3.1.0 | ISC |
| d3-dispatch | 3.0.1 | ISC |
| d3-ease | 3.0.1 | BSD-3-Clause |
| d3-format | 3.1.0 | ISC |
| d3-interpolate | 3.0.1 | ISC |
| d3-selection | 3.0.0 | ISC |
| d3-time | 3.1.0 | ISC |
| d3-time-format | 4.1.0 | ISC |
| d3-timer | 3.0.1 | ISC |
| d3-drag | 3.0.0 | ISC |
| d3-scale | 4.0.2 | ISC |
| d3-transition | 3.0.1 | ISC |
| d3-zoom | 3.0.0 | ISC |

Used: d3-zoom (pan and zoom), d3-scale (pixel and data conversion), d3-selection (events). The rest are
their dependencies. To rebuild, `npm pack` each module at the version above and concatenate
`package/dist/<module>.min.js` in the order of the table.
