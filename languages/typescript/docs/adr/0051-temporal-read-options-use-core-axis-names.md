# Temporal read options use core axis names

TypeScript temporal reads express point-in-time dimensions in `find` options with `asOf: { processing, business }`. These names match the core temporal axes, avoid confusion with write transaction timestamps, and let omitted axes keep the core default of reading the current row.

Temporal range scans use `range: { processing?: { start, end }, business?: { start, end } }`, with `start` inclusive and `end` exclusive. `asOf`, `range`, and `history` are mutually exclusive per axis, so callers cannot request a point, a range, and full history for the same temporal axis in one read.
