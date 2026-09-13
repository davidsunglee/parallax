"""The sealed Snapshot Page: compact positional rows, and the builder that seals them.

One projection is a reference to its exact Entity's member layout plus one
``member_values`` tuple read against it — Attributes in the layout's order first,
then top-level Value Object occurrences — plus one relationship view row, the
source level that produced it, one dense Page-local logical-node ID, and, only
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
:class:`PageBuilder` refuses ``bool``, a non-``int``, a negative, and an
out-of-range index where the edge is recorded — so a Page that exists is a Page
whose references resolve, and no whole-Page validation pass stands between
building and sealing it.

:meth:`PageBuilder.finish` transfers the accumulated arrays into an opaque
:class:`Page` and invalidates the builder in one step, so nothing
observes a half-published Page and nothing writes to a published one. The
per-family key map the builder assigns logical identity through is discarded
there: identity is computed once, while building, and each Root View consumes the dense
IDs without re-extracting or re-hashing a key.

A Page is also where result scope is expressed. A Root View selects one root
without copying any page-owned array. :func:`page_edges` supplies the milestone
each root of a scan stands at, or its absence for a root at the Page's own pin.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Final, Literal, cast

from parallax.core.document_codec import DocumentPathSegment
from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._layout import EntityLayout
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    EntityMetadata,
    MemberIdentity,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)
from parallax.core.temporal_read import Edge, Pin, TemporalReadError, milestone_edge_of
from parallax.snapshot.materialize._views import (
    RelationshipViewKey,
    SourceLevel,
    SourceViewLayout,
    ViewSchema,
)

__all__ = [
    "ABSENT",
    "EntityState",
    "InvalidRootInput",
    "LogicalKey",
    "Page",
    "PageBuilder",
    "PageRows",
    "RelationshipViewKey",
    "StoredDataIssueCode",
    "StoredDataIssueInput",
    "dedupe_issues",
    "exact_stored_equal",
    "page_edges",
    "page_rows",
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
"""The codes that leave a projection with no usable Page-local identity."""


@dataclass(frozen=True, slots=True)
class StoredDataIssueInput:
    """One classified stored-state contradiction with logical provenance.

    ``path`` keeps declared member names distinct from integer array positions.
    ``stored_value`` is the already-frozen evidence of what was rejected, frozen
    where conversion translated the finding: nothing downstream re-reads or
    re-freezes it. Exact equal witnesses share the Page-owned Entity State and
    its issue record; witness-distinct states under one logical key remain
    separate. The retained record is what every seam above shares by reference.
    """

    code: StoredDataIssueCode
    entity: EntityIdentity
    member: AttributeIdentity | ValueObjectIdentity | ValueObjectAttributeIdentity | None = None
    path: tuple[DocumentPathSegment, ...] = ()
    stored_value: object = field(kw_only=True)


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
class LogicalKey:
    """The page-wide identity of one logical Entity state."""

    family: EntityIdentity
    primary_key: object
    coordinates: tuple[object, ...] = ()


@dataclass(frozen=True, slots=True)
class EntityState:
    """One judged positional payload shared by Root Views in a Page."""

    member_row: tuple[object, ...]
    findings: tuple[StoredDataIssueInput, ...]


@dataclass(frozen=True, slots=True)
class PageRows:
    """One sealed Page's arrays, all indexed by projection.

    ``view_rows`` are positional against ``schema``: projection ``i``'s row is
    laid out by the source layout its own ``sources[i]`` and layout resolve to,
    so a reader translating one into a Root View row asks the schema for the
    translation rather than carrying a key beside every value.

    Reached only through :func:`page_rows`, which is what makes
    :class:`Page` opaque to the result holders that carry one.
    """

    layouts: tuple[EntityLayout, ...]
    member_rows: tuple[tuple[object, ...], ...]
    issues: tuple[tuple[StoredDataIssueInput, ...], ...]
    logical_ids: tuple[int, ...]
    keys: tuple[LogicalKey | None, ...]
    sources: tuple[SourceLevel, ...]
    view_rows: tuple[tuple[object, ...], ...]
    schema: ViewSchema
    roots: tuple[int, ...]
    pin: Pin
    judged_states: dict[LogicalKey, list[tuple[int, EntityState]]]
    observer: object | None = None
    witnesses: tuple[object, ...] = ()
    source_ordinals: tuple[int, ...] = ()
    claims: tuple[int | tuple[int, ...], ...] = ()
    decoders: tuple[
        Callable[[], tuple[tuple[object, ...], tuple[StoredDataIssueInput, ...]]], ...
    ] = ()


class Page:
    """One materialization's Page: every occurrence, the roots in result order,
    and the Page pin every occurrence was read at.

    Opaque, and opaque publicly rather than only by convention: a result holder
    carrying one can read no row, layout, edge, identity, or issue off it, and
    has nothing to read one with. The Root View that consumes it lives beside it
    in this scope and reads the sealed arrays through :func:`page_rows`, which is
    never exported.

    :attr:`pin` is the one exception, and it is one because the Page pin
    is a fact about the RESULT rather than about the representation: a Snapshot
    publishes it, so a result holder reads it off the Page it holds rather than
    off a second copy travelling beside one.

    A root whose primary key is null or undecodable is an
    :class:`InvalidRootInput` in ``roots``, retaining its result ordinal without
    claiming a constructible projection.
    """

    __slots__ = ("_rows",)

    def __init__(self, rows: PageRows) -> None:
        self._rows = rows

    @property
    def pin(self) -> Pin:
        """The Page pin every occurrence was read at."""
        return self._rows.pin

    @property
    def root_count(self) -> int:
        """The number of result positions this Page carries."""
        return len(self._rows.roots)

    @property
    def judged_states(self) -> dict[LogicalKey, list[tuple[int, EntityState]]]:
        """The witness-distinct states judged so far for this Page."""
        return self._rows.judged_states

    @property
    def observer(self) -> object | None:
        """The aggregate-only observer for this delivery, when installed."""
        return self._rows.observer


def page_rows(page: object) -> PageRows:
    """``page``'s sealed arrays — the internal read a Root View is granted."""
    if not isinstance(page, Page):
        raise TypeError("a Root View requires a finished Page")
    return page._rows  # pyright: ignore[reportPrivateUsage] - the one seam this scope reads a finished page through


def page_edges(page: Page, declaring: EntityMetadata | None) -> Iterator[Edge | None]:
    """Each root's own As-Of edge in result order, or absence where it has none.

    ``declaring`` is the Entity whose declaration carries the family's axes for a
    MILESTONE-SET read, and ``None`` for every read at one instant — whose roots
    stand at the Page's own pin and have no edge of their own to be published
    at.

    Absent, too, for a milestone root whose axis starts did not decode. Such a
    root is published at the page's own pin and the delivery continues past it:
    what a delivery advances by is the coordinate the database evaluated, not
    anything this root's stored data turned out to be.
    """
    rows = page_rows(page)
    for root in rows.roots:
        if declaring is None:
            yield None
            continue
        yield _root_edge(declaring, rows, root)


def _root_edge(declaring: EntityMetadata, rows: PageRows, root: int) -> Edge | None:
    layout = rows.layouts[root]
    key = rows.keys[root]
    if key is None:  # pragma: no cover - a temporal result root with no key has no edge
        return None
    try:
        return milestone_edge_of(
            declaring,
            {
                cast("AttributeIdentity", layout.members[position]): value
                for position, value in zip(layout.temporal_starts, key.coordinates, strict=True)
                if value is not ABSENT
            },
        )
    except TemporalReadError:
        return None


class PageBuilder:
    """One materialization's accumulation arrays and Page-local identity scope.

    Two roles, and the second is a deliberate concession rather than an
    accumulating surface. It **accumulates**: an already-decoded row is appended
    with :meth:`add`, an identity-first occurrence with :meth:`add_claim`, a
    level's fan-back is recorded with :meth:`write_view`, and :meth:`finish`
    publishes the lot. It also **answers** three questions about rows it already
    holds — :meth:`member_value`, :meth:`concrete_of`, and :meth:`resolve` —
    because a read level gathers its keys, filters its parents, and resolves a
    back-reference against exactly those rows, and until finishing nothing else
    holds them. Nothing beyond that fan-out may reach for the three.

    Page-local identity resolution promises projection reuse within one builder
    and never beyond it, so the builder is the unit a caller chooses: eager and
    milestone-set reads each give their whole flat result one Page. The FIRST
    projection registered for a logical key is the one a later back-reference
    resolves to.

    Relationship views accumulate beside the rows rather than inside them,
    because a parent's views are only known once its child level lands and the
    parent's raw row is long gone by then. What a row can receive is fixed the
    moment it is added: ``schema`` lays out its slots from the source level that
    produced it and the Entity it resolved to, so a fan-back names a view and the
    builder resolves the position, and nothing downstream orders a view again.
    """

    __slots__ = (
        "_decoders",
        "_first",
        "_identity",
        "_issues",
        "_keys",
        "_layouts",
        "_logical_ids",
        "_member_rows",
        "_observer",
        "_schema",
        "_sealed",
        "_slots",
        "_sources",
        "_views",
        "_witnesses",
    )

    def __init__(self, schema: ViewSchema, observer: object | None = None) -> None:
        self._schema = schema
        self._observer = observer
        self._layouts: list[EntityLayout] = []
        self._member_rows: list[tuple[object, ...]] = []
        self._issues: list[tuple[StoredDataIssueInput, ...]] = []
        self._logical_ids: list[int] = []
        self._keys: list[LogicalKey | None] = []
        self._sources: list[SourceLevel] = []
        self._slots: list[SourceViewLayout] = []
        self._views: list[list[object]] = []
        self._identity: dict[LogicalKey, int] = {}
        self._first: list[int] = []
        self._decoders: list[
            Callable[[], tuple[tuple[object, ...], tuple[StoredDataIssueInput, ...]]]
        ] = []
        self._witnesses: list[object] = []
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
        so identity is computed once for the life of the Page. Duplicates of one
        row within one Entity family share an ID; a projection whose key did not
        decode takes an ID of its own and keeps its diagnosis, so it merges with
        nothing — not even a second read of the identical unreadable row.

        A projection repeating a judgment some earlier projection of its logical
        node already made carries that projection's own issue record, so one
        occurrence reached twice retains one frozen rejected value rather than
        two equal ones. This is the earliest point where sharing is possible: the
        logical node a row belongs to is not known until its members decode.
        """
        key = (
            None
            if _keyless(issues)
            else LogicalKey(
                layout.family,
                layout.key_of(member_values),
                tuple(member_values[position] for position in layout.temporal_starts),
            )
        )
        return self.add_claim(
            source,
            layout,
            key,
            member_values,
            member_values,
            issues,
            lambda: (member_values, issues),
        )

    def add_claim(
        self,
        source: SourceLevel,
        layout: EntityLayout,
        key: LogicalKey | None,
        witness: object,
        raw_member_values: tuple[object, ...],
        identity_issues: tuple[StoredDataIssueInput, ...],
        decode: Callable[[], tuple[tuple[object, ...], tuple[StoredDataIssueInput, ...]]],
    ) -> int:
        """Append an identity claim without judging its payload."""
        self._require_open()
        slots = self._schema.source(source, layout)
        projection = len(self._layouts)
        existing = None if key is None else self._identity.get(key)
        if existing is None:
            logical = self._fresh(projection)
            if key is not None:
                self._identity[key] = logical
        else:
            logical = existing
        self._layouts.append(layout)
        self._member_rows.append(raw_member_values)
        self._issues.append(identity_issues)
        self._decoders.append(decode)
        self._sources.append(source)
        self._slots.append(slots)
        self._views.append([ABSENT] * len(slots.slots))
        self._logical_ids.append(logical)
        self._keys.append(key)
        self._witnesses.append(witness)
        return projection

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

    def finish(self, roots: tuple[int, ...], pin: Pin) -> Page:
        """Publish this builder's arrays as one sealed Page, roots in result order.

        The builder is invalidated in the same step, and every array it
        accumulated into is dropped with it — the key map it assigned identity
        through and the pool it interned issue records against included: what a
        sealed Page carries is what a Root View reads, nothing observes a
        half-published Page or writes to a published one, and a caller holding
        the sealed builder holds none of what it published.

        A root whose own key did not decode becomes an :class:`InvalidRootInput`
        carrying its result ordinal and its issues, which is how a result
        position survives a projection nothing can be constructed from.
        """
        self._require_open()
        count = len(self._layouts)
        for root in roots:
            _require_index(root, count, "a root")
        claims: list[list[int]] = [[] for _ in self._first]
        for projection, logical in enumerate(self._logical_ids):
            claims[logical].append(projection)
        occurrence_positions = _canonical_occurrence_positions(self._sources, self._witnesses)
        rows = PageRows(
            layouts=tuple(self._layouts),
            member_rows=tuple(self._member_rows),
            issues=tuple(self._issues),
            logical_ids=tuple(self._logical_ids),
            keys=tuple(self._keys),
            sources=tuple(self._sources),
            view_rows=tuple(tuple(row) for row in self._views),
            schema=self._schema,
            roots=roots,
            pin=pin,
            judged_states={},
            observer=self._observer,
            witnesses=tuple(self._witnesses),
            source_ordinals=tuple(position[1] for position in occurrence_positions),
            claims=tuple(
                group[0]
                if len(group) == 1
                else tuple(sorted(group, key=occurrence_positions.__getitem__))
                for group in claims
            ),
            decoders=tuple(self._decoders),
        )
        self._sealed = True
        self._layouts = []
        self._member_rows = []
        self._issues = []
        self._logical_ids = []
        self._keys = []
        self._sources = []
        self._slots = []
        self._views = []
        self._identity = {}
        self._first = []
        self._decoders = []
        self._witnesses = []
        return Page(rows)

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

    def resolve(self, family: EntityIdentity, key: object) -> int | None:
        """The first projection registered under ``(family, key)``, if any — how a
        back-reference level reaches an ancestor it issues no query for."""
        self._require_open()
        logical = next(
            (
                value
                for identity, value in self._identity.items()
                if identity.family == family and identity.primary_key == key
            ),
            None,
        )
        return None if logical is None else self._first[logical]

    # ----------------------------------------------------------------------- #
    # Internals.                                                                #
    # ----------------------------------------------------------------------- #

    def _fresh(self, projection: int) -> int:
        logical = len(self._first)
        self._first.append(projection)
        return logical

    def _require_open(self) -> None:
        if self._sealed:
            raise ValueError("this page builder finished its arrays into a Page and holds nothing")


def _keyless(issues: tuple[StoredDataIssueInput, ...]) -> bool:
    """Whether ``issues`` leave a projection with no usable Page-local identity."""
    return any(issue.code in _INVALID_KEY_CODES for issue in issues)


def _require_edge(value: object, count: int) -> None:
    """Refuse a relationship view value no sealed Page could resolve."""
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
            f"{holder} names projection {value}, outside this Page's {count} projections"
        )


def _canonical_occurrence_positions(
    sources: Sequence[SourceLevel], witnesses: Sequence[object]
) -> tuple[tuple[SourceLevel, int], ...]:
    positions: list[tuple[SourceLevel, int]] = [(0, 0)] * len(sources)
    by_source: dict[SourceLevel, list[int]] = {}
    for projection, source in enumerate(sources):
        by_source.setdefault(source, []).append(projection)
    for source, projections in by_source.items():
        ordered = sorted(
            projections,
            key=lambda projection: (stored_order_key(witnesses[projection]), projection),
        )
        for ordinal, projection in enumerate(ordered):
            positions[projection] = (source, ordinal)
    return tuple(positions)


def stored_order_key(value: object) -> str:
    kind = f"{type(value).__module__}.{type(value).__qualname__}"
    if is_dataclass(value) and not isinstance(value, type):
        parts = tuple(
            _packed((item.name, stored_order_key(getattr(value, item.name))))
            for item in fields(value)
        )
        return _packed((kind, "dataclass", *parts))
    if isinstance(value, Mapping):
        items = sorted(
            _packed((stored_order_key(key), stored_order_key(item)))
            for key, item in cast("Mapping[object, object]", value).items()
        )
        return _packed((kind, "mapping", *items))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return _packed(
            (
                kind,
                "sequence",
                *(stored_order_key(item) for item in cast("Sequence[object]", value)),
            )
        )
    return _packed((kind, "scalar", repr(value)))


def _packed(parts: Sequence[str]) -> str:
    return "".join(f"{len(part)}:{part}" for part in parts)


def exact_stored_equal(left: object, right: object) -> bool:
    """Type-sensitive structural equality for provider-normalized stored values."""
    if type(left) is not type(right):
        return False
    if is_dataclass(left) and not isinstance(left, type):
        return all(
            exact_stored_equal(getattr(left, item.name), getattr(right, item.name))
            for item in fields(left)
        )
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        left_mapping = cast("Mapping[object, object]", left)
        right_mapping = cast("Mapping[object, object]", right)
        if len(left_mapping) != len(right_mapping) or left_mapping.keys() != right_mapping.keys():
            return False
        return all(
            exact_stored_equal(left_mapping[key], right_mapping[key]) for key in left_mapping
        )
    if isinstance(left, Sequence) and not isinstance(left, (str, bytes, bytearray)):
        values = cast("Sequence[object]", left)
        other = cast("Sequence[object]", right)
        return len(values) == len(other) and all(
            exact_stored_equal(one, two) for one, two in zip(values, other, strict=True)
        )
    return cast("object", left) == right


def dedupe_issues(
    issues: Sequence[StoredDataIssueInput],
) -> tuple[StoredDataIssueInput, ...]:
    """Remove equal issues in first-seen order without requiring hashable evidence."""
    unique: list[StoredDataIssueInput] = []
    for issue in issues:
        if not any(_same_issue(issue, held) for held in unique):
            unique.append(issue)
    return tuple(unique)


def _same_issue(left: StoredDataIssueInput, right: StoredDataIssueInput) -> bool:
    return (
        left.code == right.code
        and left.entity == right.entity
        and left.member == right.member
        and left.path == right.path
        and exact_stored_equal(left.stored_value, right.stored_value)
    )
