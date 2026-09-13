"""Shared Snapshot page state and root-local publication (m-snapshot-read).

The two-layer read seam below the developer surface: a sealed, index-addressed
**Page** of compact positional rows, and the per-row conversion and Root View
that produce and consume it.

- :mod:`~parallax.snapshot.materialize._page` fixes the compact positional row,
  the absent/null/empty spellings, page-local Entity State, index-addressed
  edges, and the finishing step that transfers a builder's arrays into one Page.
- :mod:`~parallax.snapshot.materialize._views` fixes the relationship view slots
  a projection can receive, per source level and resolved concrete Entity, for
  one whole execution — and the Root View union each logical node's row is laid out
  by, with the translation from a source row into it.
- :mod:`~parallax.snapshot.materialize._convert` turns one SQL-materialized
  row's transformed values plus its level context and classified provenance into
  one projection. SQL row transforms classify and decode projected Entity-document
  members first; conversion owns the remaining member-identity translation and
  Value Object occurrence reduction. It is the ONLY place a physical column, a
  storage key, or a Document Path becomes a member identity.
- :mod:`~parallax.snapshot.materialize._prepared` binds one compiled read to one
  cataloged model and is what every read lane uses: it derives each level that
  read can resolve once, and materializes and converts a row against
  the one its own resolved Entity names. It is reached by module rather than
  through this interface, as conversion is — a lane composes it exactly where it
  compiles, and nothing outside this package composes one at all.
- :mod:`~parallax.snapshot.materialize._root` compares duplicate Payload
  Witnesses, borrows shared Entity State, and builds one root-local deterministic
  allocation order and relationship-view union.
- :mod:`~parallax.snapshot.materialize._classify` attributes those issues to the
  result root whose requested include tree reaches them, and settles the
  construction scope that attribution implies.
- :mod:`~parallax.snapshot.materialize._invalid` holds the public record a
  classified root publishes in place of itself, and the missing-value sentinel
  its evidence spells a genuinely absent stored member with.
- :mod:`~parallax.snapshot.materialize._evidence` translates and freezes a
  judging row's rejected stored value in one walk, on its way from the seam that
  judged it into that record.
- :mod:`~parallax.snapshot.materialize._wire` turns one Root View into a finite tree
  of frozen plain values keyed by declared member name — the second public
  materializer, a peer of the typed one rather than a wrapper of it. It consumes
  the same root classification, so both publish the same verdicts.

The Page and Root View stay representation-neutral. The sibling typed and Wire
publishers compose a Root View with Entity Graph Construction or the frozen Wire
tree respectively, so both consume the same judged state and classification.

It never imports ``m-sql`` / ``m-dialect``: `familyVariant` materialization and
each row's resolved concrete Entity are `m-sql`-owned, and a compiled read
reaches this scope structurally — bound once into a prepared read whose levels
are derived before its first row — so this scope only ever sees rows whose keys
are already the projected physical ones. That is a structural fact rather than a
habit: `m-snapshot-read`'s own edge to `m-execution-lifecycle` — which reaches
`m-sql` — belongs to the separate
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
)
from parallax.snapshot.materialize._invalid import (
    MISSING_STORED_VALUE,
    InvalidData,
    InvalidDataError,
    StoredDataIssue,
)
from parallax.snapshot.materialize._page import (
    InvalidRootInput,
    Page,
    PageBuilder,
    PageRows,
    RelationshipViewKey,
    StoredDataIssueCode,
    StoredDataIssueInput,
    page_edges,
    page_rows,
)
from parallax.snapshot.materialize._publication import (
    require_publishable,
)
from parallax.snapshot.materialize._root import (
    SNAPSHOT_PROJECTION_CONFLICT,
    RootView,
    SnapshotConsistencyError,
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
    "MISSING_STORED_VALUE",
    "SNAPSHOT_DECODING_FAILED",
    "SNAPSHOT_PROJECTION_CONFLICT",
    "ClassifiedRoot",
    "ConformingRoot",
    "GraphClassification",
    "InvalidData",
    "InvalidDataError",
    "InvalidRootInput",
    "Page",
    "PageBuilder",
    "PageRows",
    "RelationshipViewKey",
    "RootClassification",
    "RootView",
    "SnapshotConsistencyError",
    "SnapshotDecodingError",
    "StoredDataIssue",
    "StoredDataIssueCode",
    "StoredDataIssueInput",
    "UnwindTree",
    "WireEntity",
    "WireValue",
    "classify_roots",
    "hydrates",
    "opened_wire_entity",
    "page_edges",
    "page_rows",
    "require_publishable",
    "source_hint_of",
    "unwind_tree",
    "wire_roots",
]
