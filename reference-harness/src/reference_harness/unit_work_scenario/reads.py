"""The Scenario's accepted reads, and the one import that reaches them.

This package decides WHEN an accepted read executes and WHICH reader it receives;
what the read then observes is the Object Query oracle's, unchanged. Exactly two
things cross: a step index and a reader. Nothing comes back — the rows, Include
buckets, graph state, and reuse a step publishes are retained inside the oracle
and read only by the later steps that name them.

The collaboration is package-private on the oracle's side — offered under no name
in its interface — and single-importer on this one: this is the only module in
the harness that imports the oracle's Scenario module, so whatever else needs
those reads — another phase of this package, or a test asserting the seam — asks
here rather than reaching past it.
"""

from __future__ import annotations

from ..object_query_oracle.scenario import ScenarioReads

__all__ = ["ScenarioReads"]
