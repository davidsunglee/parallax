"""``parallax.snapshot.materialize`` enforcement scope (the row-to-graph half of
m-snapshot-read).

The two-layer read seam below the developer surface: an immutable **Snapshot
Graph Input** carrier layer, and the per-row conversion and projection merge that
produce and consume it.

- :mod:`~parallax.snapshot.materialize._input` fixes the carriers and their order
  semantics, plus graph-local identity and the validation a merge may assume.
- :mod:`~parallax.snapshot.materialize._convert` turns one SQL-materialized
  row's transformed values plus its level context and classified provenance into
  one node input. SQL row transforms classify and decode projected Entity-document
  members first; conversion owns the remaining member-identity translation and
  Value Object occurrence reduction. It is the ONLY place a physical column, a
  storage key, or a Document Path becomes a member identity.
- :mod:`~parallax.snapshot.materialize._merge` collapses duplicate projections
  into one deterministic allocation order, holding integers and references only;
  classified issues ride each winning logical node without deduplication.
- :mod:`~parallax.snapshot.materialize._classify` attributes those issues to the
  result roots whose requested include trees reach them, and settles the
  construction scope that attribution implies.
- :mod:`~parallax.snapshot.materialize._invalid` holds the public record a
  classified root publishes in place of itself.
- :mod:`~parallax.snapshot.materialize._wire` turns one merge into a finite tree
  of frozen plain values keyed by declared member name — the second public
  materializer, a peer of the typed one rather than a wrapper of it. It consumes
  the same root classification, so both publish the same verdicts.

Nothing here constructs an Entity: this scope is granted the shared carrier
algebra (``parallax.core.entity._graph_input``) and nothing else of the Entity
frontend, so the layering between graph input and graph construction is
structurally enforced rather than asserted. Its consumers —
``parallax.snapshot.handle._materializer`` and the wire materializer above —
each compose it with what their own result form needs.

It never imports ``m-sql`` / ``m-dialect``: `familyVariant` materialization and
each row's resolved concrete Entity are `m-sql`-owned, carried by the compiled
read itself and handed here as a level's own context, so this scope only ever
sees rows whose keys are already the projected physical ones. That is a
structural fact rather than a habit: `m-snapshot-read`'s own edge to
`m-execution-lifecycle` — which reaches `m-sql` — belongs to the separate
:mod:`~parallax.snapshot._read_result` scope, so no grant of this one reaches
SQL generation.
"""

from __future__ import annotations

from parallax.snapshot.materialize._classify import (
    ClassifiedRoot,
    ConformingRoot,
    GraphClassification,
    RootClassification,
    classify_roots,
    hydrates,
)
from parallax.snapshot.materialize._convert import (
    SNAPSHOT_DECODING_FAILED,
    LevelContext,
    MergeScope,
    SnapshotDecodingError,
    convert_row,
    observable_columns,
)
from parallax.snapshot.materialize._input import (
    InvalidRootInput,
    LogicalKey,
    RelationshipViewKey,
    SnapshotGraphInput,
    SnapshotNodeInput,
    SnapshotNodeRef,
    SnapshotRelationshipViewInput,
    StoredDataIssueCode,
    StoredDataIssueInput,
    attribute_value,
    has_invalid_key,
    logical_key,
    validate_graph_input,
)
from parallax.snapshot.materialize._invalid import (
    InvalidData,
    InvalidDataError,
    StoredDataIssue,
)
from parallax.snapshot.materialize._merge import (
    GraphMerge,
    MergedNode,
    MergedRelationshipView,
    merge_graph_input,
)
from parallax.snapshot.materialize._publication import (
    require_publishable,
)
from parallax.snapshot.materialize._wire import (
    EMPTY_UNWIND,
    FAMILY_VARIANT_KEY,
    UnwindTree,
    WireEntity,
    WireValue,
    opened_wire_entity,
    source_hint_of,
    unwind_tree,
    wire_roots,
)

__all__ = [
    "EMPTY_UNWIND",
    "FAMILY_VARIANT_KEY",
    "SNAPSHOT_DECODING_FAILED",
    "ClassifiedRoot",
    "ConformingRoot",
    "GraphClassification",
    "GraphMerge",
    "InvalidData",
    "InvalidDataError",
    "InvalidRootInput",
    "LevelContext",
    "LogicalKey",
    "MergeScope",
    "MergedNode",
    "MergedRelationshipView",
    "RelationshipViewKey",
    "RootClassification",
    "SnapshotDecodingError",
    "SnapshotGraphInput",
    "SnapshotNodeInput",
    "SnapshotNodeRef",
    "SnapshotRelationshipViewInput",
    "StoredDataIssue",
    "StoredDataIssueCode",
    "StoredDataIssueInput",
    "UnwindTree",
    "WireEntity",
    "WireValue",
    "attribute_value",
    "classify_roots",
    "convert_row",
    "has_invalid_key",
    "hydrates",
    "logical_key",
    "merge_graph_input",
    "observable_columns",
    "opened_wire_entity",
    "require_publishable",
    "source_hint_of",
    "unwind_tree",
    "validate_graph_input",
    "wire_roots",
]
