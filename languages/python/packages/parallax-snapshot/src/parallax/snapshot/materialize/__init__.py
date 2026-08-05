"""``parallax.snapshot.materialize`` enforcement scope (m-snapshot-read).

The two-layer read seam below the developer surface: an immutable **Snapshot
Graph Input** carrier layer, and the per-row conversion and projection merge that
produce and consume it.

- :mod:`~parallax.snapshot.materialize._input` fixes the carriers and their order
  semantics, plus graph-local identity and the validation a merge may assume.
- :mod:`~parallax.snapshot.materialize._convert` turns one driver row plus its
  level context into one node input. It is the ONLY place a physical column, a
  storage key, or a Document Path becomes a member identity, which is what lets a
  caller convert one row at a time: a materialized row is reachable only until
  its conversion, and no consumer here reaches back into the raw result set the
  driver answered a level's statement with.
- :mod:`~parallax.snapshot.materialize._merge` collapses duplicate projections
  into one deterministic allocation order, holding integers and references only.

Nothing here constructs an Entity: this scope is granted the shared carrier
algebra (``parallax.core.entity._graph_input``) and nothing else of the Entity
frontend, so the layering between graph input and graph construction is
structurally enforced rather than asserted. Its consumer —
``parallax.snapshot.handle._materializer`` — composes the two.

It never imports ``m-sql`` / ``m-dialect``: `familyVariant` materialization and
each row's resolved concrete Entity are `m-sql`-owned, carried by the compiled
read itself and handed here as a level's own context, so this scope only ever
sees rows whose keys are already the projected physical ones.
"""

from __future__ import annotations

from parallax.snapshot.materialize._convert import (
    SNAPSHOT_DECODING_FAILED,
    LevelContext,
    MergeScope,
    SnapshotDecodingError,
    convert_row,
    observable_columns,
)
from parallax.snapshot.materialize._input import (
    LogicalKey,
    RelationshipViewKey,
    SnapshotGraphInput,
    SnapshotNodeInput,
    SnapshotNodeRef,
    SnapshotRelationshipViewInput,
    attribute_value,
    logical_key,
    validate_graph_input,
)
from parallax.snapshot.materialize._merge import (
    GraphMerge,
    MergedNode,
    MergedRelationshipView,
    merge_graph_input,
)

__all__ = [
    "SNAPSHOT_DECODING_FAILED",
    "GraphMerge",
    "LevelContext",
    "LogicalKey",
    "MergeScope",
    "MergedNode",
    "MergedRelationshipView",
    "RelationshipViewKey",
    "SnapshotDecodingError",
    "SnapshotGraphInput",
    "SnapshotNodeInput",
    "SnapshotNodeRef",
    "SnapshotRelationshipViewInput",
    "attribute_value",
    "convert_row",
    "logical_key",
    "merge_graph_input",
    "observable_columns",
    "validate_graph_input",
]
