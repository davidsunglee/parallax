"""The Scenario's accepted reads, and the one import that reaches them.

This package decides WHEN an accepted read executes and WHICH reader it receives;
what the read then observes is the Object Query oracle's, unchanged. Exactly two
things cross: a step index and a reader. Nothing comes back — the rows, Include
buckets, graph state, and reuse a step publishes are retained inside the oracle
and read only by the later steps that name them.

Every module of this package that needs those reads imports them from here, so
the collaboration has one importer rather than one per phase.
"""

from __future__ import annotations

from ..object_query_oracle import ScenarioReads

__all__ = ["ScenarioReads"]
