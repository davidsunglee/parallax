from __future__ import annotations

from typing import Final

__all__ = [
    "SNAPSHOT_CLASS_BACKED_MODEL_REQUIRED",
    "SNAPSHOT_MATERIALIZATION_FAILED",
]


SNAPSHOT_CLASS_BACKED_MODEL_REQUIRED: Final = "snapshot-class-backed-model-required"
"""A modeled read was asked of a Database over a model that names no class.

A Snapshot answers Entity Class instances, so serving one needs a class-backed
:class:`~parallax.core.DomainModel` — one that composed Entity Classes and
therefore holds the index deciding which class a returned row instantiates.
Both connection doors refuse a value that is no Domain Model at all, before the
adapter is touched; a descriptor-backed model connects and is refused instead at
the read it cannot serve, still before any SQL.

The refusal is about materialization capability and never about identity or
ownership: any class-backed model serves, however many other Databases already
serve it."""


SNAPSHOT_MATERIALIZATION_FAILED: Final = "snapshot-materialization-failed"
"""Building the Entity graph failed after the read itself had succeeded.

Raised exactly once, at the materialization boundary, for a graph-construction
refusal, or a failure answering the node-indexed graph or its lifecycle states.
The original exception is the ``__cause__``, so the defect stays diagnosable
while callers branch on one stable code.

Everything upstream keeps its own classification: query, capability,
transaction, adapter, SQL, and neutral-decoding failures are never re-wrapped
here, because none of them is a failure to build a graph. No partial graph and
no Snapshot is published when this raises.
"""
