# Distributions share the parallax namespace despite the PyPI squatter

The five distributions — `parallax-core` (common runtime),
`parallax-descriptor` (descriptor interchange), `parallax-snapshot`
(lifecycle extension), `parallax-postgres` (adapter), and
`parallax-conformance` (development-only) — share the PEP 420 namespace package
`parallax.*`, giving separately installable artifacts one coherent import
vocabulary (`parallax.core`, `parallax.descriptor`, `parallax.snapshot`,
`parallax.postgres`) while satisfying core's required artifact seams. All five
distribution names were unoccupied on PyPI when selected.

The bare name `parallax` is taken by a dormant SSH fan-out tool (v1.0.6) that
owns the top-level `parallax` import package, so co-installing it with these
packages in one environment would break namespace resolution. We accept and
document that collision rather than adopting an uglier prefix
(`parallax-orm-*` imports were the alternative): co-installation of a dormant
SSH utility and this ORM is fringe, and distribution names do not collide —
only the import namespace would.
