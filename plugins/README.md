# LENS plugins

Each folder here is a plugin that a sheet opens with `!plugin <folder name>`. LENS fetches a plugin from this folder on GitHub (`main`) the first time a sheet asks for it, and keeps it; a source checkout serves it from here directly. See the wiki's [Plugins](https://github.com/InverseInertia/laconic-ens/wiki/Plugins) page for the manifest and the messages a plugin exchanges with LENS.

| Plugin | What it does |
|---|---|
| `pipenet` | Lays out a fluid loop on a grid (one source, any number of sinks, straights, elbows, tees and crossovers) and writes its upstream matrix and segment lengths, diameters and fittings into the sheet, then draws the sheet's flows and pressure drops on the pipes |
