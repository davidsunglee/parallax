# Distributions share the parallax namespace despite the PyPI squatter

The four distributions — `parallax-core` (common runtime), `parallax-snapshot`
(lifecycle extension), `parallax-postgres` (adapter), `parallax-conformance`
(development-only) — share the PEP 420 namespace package `parallax.*`, giving
separately installable artifacts one coherent import vocabulary
(`parallax.core`, `parallax.snapshot`, `parallax.postgres`) while satisfying
core's required artifact seams. All four distribution names were verified
free on PyPI.

The bare name `parallax` is taken by a dormant SSH fan-out tool (v1.0.6) that
owns the top-level `parallax` import package, so co-installing it with these
packages in one environment would break namespace resolution. We accept and
document that collision rather than adopting an uglier prefix
(`parallax-orm-*` imports were the alternative): co-installation of a dormant
SSH utility and this ORM is fringe, and distribution names do not collide —
only the import namespace would.
