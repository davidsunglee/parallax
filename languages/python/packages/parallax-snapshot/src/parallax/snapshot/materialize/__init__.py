"""``parallax.snapshot.materialize`` enforcement scope (the row-to-graph half of
m-snapshot-read).

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
- :mod:`~parallax.snapshot.materialize._neutral` turns one merge into class-free
  nodes and views — the second materializer, a peer of the typed one rather than
  a wrapper of it.

Nothing here constructs an Entity: this scope is granted the shared carrier
algebra (``parallax.core.entity._graph_input``) and nothing else of the Entity
frontend, so the layering between graph input and graph construction is
structurally enforced rather than asserted. Its consumers —
``parallax.snapshot.handle._materializer`` and the neutral materializer above —
each compose it with what their own result form needs.

It never imports ``m-sql`` / ``m-dialect``: `familyVariant` materialization and
each row's resolved concrete Entity are `m-sql`-owned, carried by the compiled
read itself and handed here as a level's own context, so this scope only ever
sees rows whose keys are already the projected physical ones. That is a
structural fact rather than a habit: `m-snapshot-read`'s own edge to
`m-execution-log` — which reaches `m-sql` — belongs to the separate
:mod:`~parallax.snapshot._read_result` scope, so no grant of this one reaches
SQL generation.
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
from parallax.snapshot.materialize._neutral import (
    NeutralGraph,
    NeutralGraphs,
    NeutralNode,
    NeutralNodeView,
    NeutralReadOutput,
    NeutralRelationshipView,
    NeutralRows,
    NeutralValue,
    ObservationKeying,
    neutral_graph,
    neutral_graphs,
    neutral_rows,
)

__all__ = [
    "SNAPSHOT_DECODING_FAILED",
    "GraphMerge",
    "LevelContext",
    "LogicalKey",
    "MergeScope",
    "MergedNode",
    "MergedRelationshipView",
    "NeutralGraph",
    "NeutralGraphs",
    "NeutralNode",
    "NeutralNodeView",
    "NeutralReadOutput",
    "NeutralRelationshipView",
    "NeutralRows",
    "NeutralValue",
    "ObservationKeying",
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
    "neutral_graph",
    "neutral_graphs",
    "neutral_rows",
    "observable_columns",
    "validate_graph_input",
]
