"""``parallax.snapshot.materialize`` enforcement scope (the row-to-graph half of
m-snapshot-read).

The two-layer read seam below the developer surface: a sealed, index-addressed
**Snapshot Graph** of compact positional rows, and the per-row conversion and
projection merge that produce and consume it.

- :mod:`~parallax.snapshot.materialize._graph` fixes the compact positional row,
  the absent/null/empty spellings, graph-local identity, the index-addressed
  edges a graph boundary refuses anything else at, and the sealing that turns a
  builder's arrays into one opaque graph.
- :mod:`~parallax.snapshot.materialize._views` fixes the relationship view slots
  a projection can receive, per source level and resolved concrete Entity, for
  one whole execution — and the merged union each logical node's row is laid out
  by, with the translation from a source row into it.
- :mod:`~parallax.snapshot.materialize._convert` turns one SQL-materialized
  row's transformed values plus its level context and classified provenance into
  one projection. SQL row transforms classify and decode projected Entity-document
  members first; conversion owns the remaining member-identity translation and
  Value Object occurrence reduction. It is the ONLY place a physical column, a
  storage key, or a Document Path becomes a member identity.
- :mod:`~parallax.snapshot.materialize._merge` collapses duplicate projections
  into one deterministic allocation order and answers each consumer by index,
  holding integers and references only; classified issues ride each winning
  logical node without deduplication.
- :mod:`~parallax.snapshot.materialize._classify` attributes those issues to the
  result roots whose requested include trees reach them, and settles the
  construction scope that attribution implies.
- :mod:`~parallax.snapshot.materialize._invalid` holds the public record a
  classified root publishes in place of itself.
- :mod:`~parallax.snapshot.materialize._wire` turns one merge into a finite tree
  of frozen plain values keyed by declared member name — the second public
  materializer, a peer of the typed one rather than a wrapper of it. It consumes
  the same root classification, so both publish the same verdicts.

Nothing here constructs an Entity: this scope is granted the exact-model member
layouts (``parallax.core.entity._layout``) and the construction-input sentinels
(``parallax.core.entity._construction_input``) and nothing else of the Entity
frontend, so the layering between a materialized row and graph construction is
structurally enforced rather than asserted. A row reaches this scope already
laid out and leaves it as one, and of the sentinel scope this one takes the
absence sentinel alone. Its consumers —
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
    SnapshotDecodingError,
    observable_columns,
)
from parallax.snapshot.materialize._graph import (
    InvalidRootInput,
    RelationshipViewKey,
    SnapshotGraph,
    StoredDataIssueCode,
    StoredDataIssueInput,
)
from parallax.snapshot.materialize._invalid import (
    InvalidData,
    InvalidDataError,
    StoredDataIssue,
)
from parallax.snapshot.materialize._merge import (
    GraphMerge,
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
    "RelationshipViewKey",
    "RootClassification",
    "SnapshotDecodingError",
    "SnapshotGraph",
    "StoredDataIssue",
    "StoredDataIssueCode",
    "StoredDataIssueInput",
    "UnwindTree",
    "WireEntity",
    "WireValue",
    "classify_roots",
    "hydrates",
    "merge_graph_input",
    "observable_columns",
    "opened_wire_entity",
    "require_publishable",
    "source_hint_of",
    "unwind_tree",
    "wire_roots",
]
