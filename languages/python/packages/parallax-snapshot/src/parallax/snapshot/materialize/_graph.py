"""The sealed Snapshot graph: compact positional rows, and the builder that seals them.

One projection is a reference to its exact Entity's member layout plus one
``member_values`` tuple read against it — Attributes in the layout's order first,
then top-level Value Object occurrences — plus one relationship view row, the
source level that produced it, one dense graph-local logical-node ID, and, only
where stored data contradicted the model, its issues. Nothing wraps a cell: what
a row holds at a position is the decoded value itself.

The view row is positional too, against the
:class:`~parallax.snapshot.materialize._views.ViewSchema` the execution planned:
its width is what the levels below that projection's own source attach, so a
fan-back names a view and the builder resolves the slot, and no key travels
beside a value.

Absence stops being spelled by omission, because a positional row has no way to
omit. :data:`~parallax.core.entity._construction_input.ABSENT` carries it — the one
sentinel the common runtime owns beside the member layouts a row is read
against, re-exported here because this is where the Snapshot's absence algebra
is stated — and the four spellings stay mutually distinct at every depth:

===============================  =========================================
``ABSENT``                       absent or unloaded, and what an
                                 undecodable cell becomes beside its issue
``None``                         an explicit null
``()``                           loaded empty, a Many with zero occurrences
                                 included
``value_tuple``                  one Value Object record, in its own
                                 declaration order
``tuple[value_tuple, ...]``      a Many occurrence, order preserved
``int`` / ``tuple[int, ...]``    a to-one / to-many edge, by projection index
===============================  =========================================

Edges and roots are exact nonnegative built-in ``int`` projection indexes, and
:class:`GraphBuilder` refuses ``bool``, a non-``int``, a negative, and an
out-of-range index where the edge is recorded — so a graph that exists is a graph
whose references resolve, and no whole-graph validation pass stands between
building one and merging it.

:meth:`GraphBuilder.seal` transfers the accumulated arrays into an opaque
:class:`SnapshotGraph` and invalidates the builder in one step, so nothing
observes a half-published graph and nothing writes to a published one. The
per-family key map the builder assigns logical identity through is discarded
there: identity is computed once, while building, and a merge consumes the dense
IDs without re-extracting or re-hashing a key.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, cast

from parallax.core.document_codec import DocumentPathSegment
from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._layout import EntityLayout
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    MemberIdentity,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)
from parallax.core.temporal_read import Pin
from parallax.snapshot.materialize._views import (
    RelationshipViewKey,
    SourceLevel,
    SourceViewLayout,
    ViewSchema,
)

__all__ = [
    "ABSENT",
    "GraphBuilder",
    "GraphRows",
    "InvalidRootInput",
    "RelationshipViewKey",
    "SnapshotGraph",
    "StoredDataIssueCode",
    "StoredDataIssueInput",
    "graph_rows",
]


type StoredDataIssueCode = Literal[
    "stored-data-required-member-absent",
    "stored-data-required-member-null",
    "stored-data-one-wrong-kind",
    "stored-data-many-wrong-kind",
    "stored-data-leaf-undecodable",
    "stored-data-attribute-null",
    "stored-data-family-tag-unknown",
    "stored-data-primary-key-null",
    "stored-data-primary-key-undecodable",
]
"""The closed internal stored-data issue vocabulary for snapshot reads."""

_INVALID_KEY_CODES: Final[frozenset[StoredDataIssueCode]] = frozenset(
    {"stored-data-primary-key-null", "stored-data-primary-key-undecodable"}
)
"""The codes that leave a projection with no usable graph-local identity."""


@dataclass(frozen=True, slots=True)
class StoredDataIssueInput:
    """One classified stored-state contradiction with logical provenance.

    ``path`` keeps declared member names distinct from integer array positions.
    """

    code: StoredDataIssueCode
    entity: EntityIdentity
    member: AttributeIdentity | ValueObjectIdentity | ValueObjectAttributeIdentity | None = None
    path: tuple[DocumentPathSegment, ...] = ()


@dataclass(frozen=True, slots=True)
class InvalidRootInput:
    """One non-hydrating result root with no constructible projection behind it."""

    ordinal: int
    issues: tuple[StoredDataIssueInput, ...]

    def __post_init__(self) -> None:
        if self.ordinal < 0:
            raise ValueError("an invalid root ordinal is nonnegative")
        if not self.issues:
            raise ValueError("an invalid root carries at least one stored-data issue")


@dataclass(frozen=True, slots=True)
class GraphRows:
    """One sealed graph's arrays, all indexed by projection.

    ``view_rows`` are positional against ``schema``: projection ``i``'s row is
    laid out by the source layout its own ``sources[i]`` and layout resolve to,
    so a reader translating one into a merged row asks the schema for the
    translation rather than carrying a key beside every value.

    Reached only through :func:`graph_rows`, which is what makes
    :class:`SnapshotGraph` opaque to the result holders that carry one.
    """

    layouts: tuple[EntityLayout, ...]
    member_rows: tuple[tuple[object, ...], ...]
    issues: tuple[tuple[StoredDataIssueInput, ...], ...]
    logical_ids: tuple[int, ...]
    sources: tuple[SourceLevel, ...]
    view_rows: tuple[tuple[object, ...], ...]
    schema: ViewSchema
    roots: tuple[int | InvalidRootInput, ...]
    pin: Pin


class SnapshotGraph:
    """One materialization's whole graph: every projection, the roots in result
    order, and the whole-graph pin every projection was read at.

    Opaque, and opaque publicly rather than only by convention: a result holder
    carrying one can read no row, layout, edge, identity, or issue off it, and
    has nothing to read one with. The merge that consumes it lives beside it in
    this scope and reads the sealed arrays through :func:`graph_rows`, which is
    never exported.

    :attr:`pin` is the one exception, and it is one because the whole-graph pin
    is a fact about the RESULT rather than about the representation: a Snapshot
    publishes it, so a result holder reads it off the graph it holds rather than
    off a second copy travelling beside one.

    A root whose primary key is null or undecodable is an
    :class:`InvalidRootInput` in ``roots``, retaining its result ordinal without
    claiming a constructible projection.
    """

    __slots__ = ("_rows",)

    def __init__(self, rows: GraphRows) -> None:
        self._rows = rows

    @property
    def pin(self) -> Pin:
        """The whole-graph pin every projection of this graph was read at."""
        return self._rows.pin


def graph_rows(graph: SnapshotGraph) -> GraphRows:
    """``graph``'s sealed arrays — the internal read a merge and an importing
    builder take, and the whole of what either is granted."""
    return graph._rows  # pyright: ignore[reportPrivateUsage] - the one seam this scope reads a sealed graph through


class GraphBuilder:
    """One materialization's accumulation arrays and graph-local identity scope.

    Two roles, and the second is a deliberate concession rather than an
    accumulating surface. It **accumulates**: a converted row is appended with
    :meth:`add`, an already-sealed row is carried over with
    :meth:`import_projection`, a level's fan-back is recorded with
    :meth:`write_view`, and :meth:`seal` publishes the lot. It also **answers**
    four questions about rows it already holds — :meth:`member_value`,
    :meth:`concrete_of`, :meth:`resolve`, and :meth:`issues_of` — because a read
    level gathers its keys, filters its parents, resolves a back-reference, and
    decides what a write observes against exactly those rows, and until sealing
    nothing else holds them. Nothing beyond that fan-out may reach for the four.

    Graph-local identity resolution promises projection reuse within one builder
    and never beyond it, so the builder is the unit a caller chooses: a ``find``
    gives its whole result one, and a milestone-set read gives each milestone its
    own. The FIRST projection registered for a logical key is the one a later
    back-reference resolves to.

    Relationship views accumulate beside the rows rather than inside them,
    because a parent's views are only known once its child level lands and the
    parent's raw row is long gone by then. What a row can receive is fixed the
    moment it is added: ``schema`` lays out its slots from the source level that
    produced it and the Entity it resolved to, so a fan-back names a view and the
    builder resolves the position, and nothing downstream orders a view again.
    """

    __slots__ = (
        "_first",
        "_identity",
        "_issues",
        "_layouts",
        "_logical_ids",
        "_member_rows",
        "_schema",
        "_sealed",
        "_slots",
        "_sources",
        "_views",
    )

    def __init__(self, schema: ViewSchema) -> None:
        self._schema = schema
        self._layouts: list[EntityLayout] = []
        self._member_rows: list[tuple[object, ...]] = []
        self._issues: list[tuple[StoredDataIssueInput, ...]] = []
        self._logical_ids: list[int] = []
        self._sources: list[SourceLevel] = []
        self._slots: list[SourceViewLayout] = []
        self._views: list[list[object]] = []
        self._identity: dict[tuple[EntityIdentity, object], int] = {}
        self._first: list[int] = []
        self._sealed = False

    # ----------------------------------------------------------------------- #
    # Accumulate.                                                               #
    # ----------------------------------------------------------------------- #

    def add(
        self,
        source: SourceLevel,
        layout: EntityLayout,
        member_values: tuple[object, ...],
        issues: tuple[StoredDataIssueInput, ...] = (),
    ) -> int:
        """Append one converted projection of ``source`` and answer its index.

        ``source`` is the plan level that produced the row, which together with
        the layout's own Entity decides the view row this projection carries: a
        fixed-width row of ``ABSENT`` slots, each one a level below ``source``
        will write.

        The logical-node ID is assigned here, through the layout's own key rule,
        so identity is computed once for the life of the graph. Duplicates of one
        row within one Entity family share an ID; a projection whose key did not
        decode takes an ID of its own and keeps its diagnosis, so it merges with
        nothing — not even a second read of the identical unreadable row.
        """
        self._require_open()
        slots = self._schema.source(source, layout)
        projection = len(self._layouts)
        self._layouts.append(layout)
        self._member_rows.append(member_values)
        self._issues.append(issues)
        self._sources.append(source)
        self._slots.append(slots)
        self._views.append([ABSENT] * len(slots.slots))
        self._logical_ids.append(self._logical(layout, member_values, issues, projection))
        return projection

    def import_projection(self, source: SourceLevel, graph: SnapshotGraph, projection: int) -> int:
        """Carry one sealed projection's row into this builder, by reference.

        Its layout, member row, and issues are the ones the sealed graph already
        holds — nothing is decoded twice — while its logical-node ID is
        RE-DERIVED here, exactly as a converted row's is. That keeps one way an
        ID comes into existence: remapping the source graph's own IDs would work
        only by accident, because a staging graph holding many milestones at once
        already collapses two milestones of one row onto one ID while their
        partitions must not share one.

        Its view row is NOT carried: ``source`` names where the row lands in THIS
        builder's own plan, so the importing graph lays out what the imported row
        can receive rather than inheriting a width from the graph it left.
        """
        rows = graph_rows(graph)
        return self.add(
            source,
            rows.layouts[projection],
            rows.member_rows[projection],
            rows.issues[projection],
        )

    def write_view(self, projection: int, view: RelationshipViewKey, value: object) -> None:
        """Record one relationship view on an already-added projection.

        ``value`` is ``None`` for loaded-null, a projection index for a loaded
        to-one, and a tuple of them — empty included — for a loaded to-many. A
        slot never written stays :data:`ABSENT`, which is unloaded — what a
        path-root guard leaves behind when it excludes a parent from a level.

        Named by view rather than by position, so a fan-back never learns about
        slots: the projection's own source layout resolves one. Two levels may
        legitimately write one view — a guarded path and its broad sibling are
        distinct hops with the same view key — and the last write is the one the
        slot retains, exactly as the fetch plan's own order decided.

        Raises :class:`ValueError` for a view no level below this projection's
        own source attaches, which is a fan-back writing against a plan the
        schema was not built from.
        """
        self._require_open()
        _require_edge(value, len(self._layouts))
        slot = self._slots[projection].index_of.get(view)
        if slot is None:
            raise ValueError(
                f"no level below source {self._sources[projection]} attaches "
                f"{view.narrowed_view or view.relationship.name!r} to "
                f"{self._layouts[projection].concrete.canonical}"
            )
        self._views[projection][slot] = value

    def seal(self, roots: tuple[int, ...], pin: Pin) -> SnapshotGraph:
        """Publish this builder's arrays as one sealed graph, roots in result order.

        The builder is invalidated in the same step, and the key map it assigned
        identity through is discarded with it: what a sealed graph carries is
        what a merge reads, and nothing observes a half-published graph or writes
        to a published one.

        A root whose own key did not decode becomes an :class:`InvalidRootInput`
        carrying its result ordinal and its issues, which is how a result
        position survives a projection nothing can be constructed from.
        """
        self._require_open()
        count = len(self._layouts)
        for root in roots:
            _require_index(root, count, "a root")
        rows = GraphRows(
            layouts=tuple(self._layouts),
            member_rows=tuple(self._member_rows),
            issues=tuple(self._issues),
            logical_ids=tuple(self._logical_ids),
            sources=tuple(self._sources),
            view_rows=tuple(tuple(row) for row in self._views),
            schema=self._schema,
            roots=tuple(
                InvalidRootInput(ordinal, self._issues[root])
                if _keyless(self._issues[root])
                else root
                for ordinal, root in enumerate(roots)
            ),
            pin=pin,
        )
        self._sealed = True
        self._layouts = []
        self._member_rows = []
        self._issues = []
        self._logical_ids = []
        self._sources = []
        self._slots = []
        self._views = []
        self._identity = {}
        self._first = []
        return SnapshotGraph(rows)

    # ----------------------------------------------------------------------- #
    # Read back, for the read executor's fan-out helpers alone.                 #
    # ----------------------------------------------------------------------- #

    def member_value(self, projection: int, member: MemberIdentity) -> object:
        """``projection``'s value at ``member``, by position.

        Answers :data:`ABSENT` for a member this projection's read did not carry
        and for one its Entity does not lay out at all, which is what
        distinguishes an unloaded correlation member from one stored null — a
        gathered key skips both, but they are no longer the same answer.
        """
        self._require_open()
        position = self._layouts[projection].index_of.get(member)
        return ABSENT if position is None else self._member_rows[projection][position]

    def concrete_of(self, projection: int) -> EntityIdentity:
        """The exact Entity ``projection``'s own compiled read resolved it to."""
        self._require_open()
        return self._layouts[projection].concrete

    def issues_of(self, projection: int) -> tuple[StoredDataIssueInput, ...]:
        """Every issue classified for ``projection``, without deduplication."""
        self._require_open()
        return self._issues[projection]

    def resolve(self, family: EntityIdentity, key: object) -> int | None:
        """The first projection registered under ``(family, key)``, if any — how a
        back-reference level reaches an ancestor it issues no query for."""
        self._require_open()
        logical = self._identity.get((family, key))
        return None if logical is None else self._first[logical]

    # ----------------------------------------------------------------------- #
    # Internals.                                                                #
    # ----------------------------------------------------------------------- #

    def _logical(
        self,
        layout: EntityLayout,
        member_values: tuple[object, ...],
        issues: tuple[StoredDataIssueInput, ...],
        projection: int,
    ) -> int:
        if _keyless(issues):
            return self._fresh(projection)
        key = (layout.family, layout.key_of(member_values))
        existing = self._identity.get(key)
        if existing is not None:
            return existing
        logical = self._fresh(projection)
        self._identity[key] = logical
        return logical

    def _fresh(self, projection: int) -> int:
        logical = len(self._first)
        self._first.append(projection)
        return logical

    def _require_open(self) -> None:
        if self._sealed:
            raise ValueError(
                "this graph builder sealed its arrays into a SnapshotGraph and holds nothing"
            )


def _keyless(issues: tuple[StoredDataIssueInput, ...]) -> bool:
    """Whether ``issues`` leave a projection with no usable graph-local identity."""
    return any(issue.code in _INVALID_KEY_CODES for issue in issues)


def _require_edge(value: object, count: int) -> None:
    """Refuse a relationship view value no sealed graph could resolve."""
    if value is None:
        return
    if isinstance(value, tuple):
        for element in cast("tuple[object, ...]", value):
            _require_index(element, count, "a to-many relationship view")
        return
    _require_index(value, count, "a to-one relationship view")


def _require_index(value: object, count: int, holder: str) -> None:
    if type(value) is not int:
        raise ValueError(
            f"{holder} names a projection by an exact built-in int, and {value!r} is not one"
        )
    if not 0 <= value < count:
        raise ValueError(
            f"{holder} names projection {value}, outside this graph's {count} projections"
        )
