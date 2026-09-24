from __future__ import annotations

import datetime as dt
import decimal
import uuid
from array import array
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Final, Literal, NamedTuple, cast

from parallax.core.deep_fetch import RelationshipViewKey
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
from parallax.snapshot.materialize._views import SourceLevel, SourceViewLayout, ViewSchema

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
    "release_page_rows",
    "root_last_uses",
]

_NO_VIEWS: Final[tuple[()]] = ()
_ATOMIC_WITNESS_TYPES: Final = (
    type(None),
    bool,
    int,
    float,
    str,
    bytes,
    decimal.Decimal,
    dt.date,
    dt.time,
    dt.datetime,
    uuid.UUID,
)


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


class LogicalKey(NamedTuple):
    """The page-wide identity of one logical Entity state."""

    family: EntityIdentity
    primary_key: object
    coordinates: tuple[object, ...] = ()


class EntityState(NamedTuple):
    """One judged positional payload shared by Root Views in a Page."""

    member_row: tuple[object, ...]
    findings: tuple[StoredDataIssueInput, ...]


type _Decoder = Callable[[], tuple[tuple[object, ...], tuple[StoredDataIssueInput, ...]]]


class SparseIssues:
    __slots__ = ("_count", "_values")

    def __init__(self, count: int, values: dict[int, tuple[StoredDataIssueInput, ...]]) -> None:
        self._count = count
        self._values = values

    def __len__(self) -> int:
        return self._count

    def __getitem__(self, projection: int) -> tuple[StoredDataIssueInput, ...]:
        return self._values.get(projection, ())

    def release(self, projection: int) -> None:
        self._values.pop(projection, None)

    def clear(self) -> None:
        self._values.clear()
        self._count = 0


class SparseEdges:
    __slots__ = ("_count", "_values")

    def __init__(self, count: int, values: dict[int, list[object]]) -> None:
        self._count = count
        self._values = values

    def __len__(self) -> int:
        return self._count

    def __getitem__(self, projection: int) -> Sequence[object]:
        return self._values.get(projection, _NO_VIEWS)

    def release(self, projection: int) -> None:
        self._values.pop(projection, None)

    def clear(self) -> None:
        self._values.clear()
        self._count = 0


class DecoderRows:
    __slots__ = ("_count", "_values", "_witnesses")

    def __init__(
        self,
        count: int,
        values: dict[int, _Decoder | None],
        witnesses: Sequence[object],
    ) -> None:
        self._count = count
        self._values = values
        self._witnesses = witnesses

    def __len__(self) -> int:
        return self._count

    def __getitem__(self, projection: int) -> _Decoder | tuple[object, ...] | None:
        if projection in self._values:
            return self._values[projection]
        witness = self._witnesses[projection]
        return cast("tuple[object, ...]", witness) if isinstance(witness, tuple) else None

    def __setitem__(self, projection: int, value: _Decoder | None) -> None:
        self._values[projection] = value

    def release(self, projection: int) -> None:
        self._values.pop(projection, None)

    def clear(self) -> None:
        self._values.clear()
        self._witnesses = ()
        self._count = 0


class JudgedStates(Mapping[LogicalKey, list[tuple[int, EntityState]]]):
    """Dense logical-node-indexed state groups with a mapping inspection view."""

    __slots__ = ("_claims", "_groups", "_keys")

    def __init__(
        self,
        keys: tuple[LogicalKey | None, ...],
        claims: Sequence[int | tuple[int, ...]],
    ) -> None:
        self._keys = list(keys)
        self._claims = claims if isinstance(claims, list) else list(claims)
        self._groups: list[EntityState | list[tuple[int, EntityState]] | None] = [None] * len(keys)

    def singleton(self, logical: int) -> EntityState | None:
        group = self._groups[logical]
        return group if isinstance(group, EntityState) else None

    def set_singleton(self, logical: int, state: EntityState) -> None:
        self._groups[logical] = state

    def group(self, logical: int) -> list[tuple[int, EntityState]]:
        group = self._groups[logical]
        if group is None:
            group = []
            self._groups[logical] = group
        if isinstance(group, EntityState):  # pragma: no cover - claim shape is fixed
            raise ValueError("a singleton judged state has no witness-distinct group")
        return group

    def _mapping_value(self, logical: int) -> list[tuple[int, EntityState]] | None:
        group = self._groups[logical]
        if group is None:
            return None
        if isinstance(group, EntityState):
            claim = self._claims[logical]
            if not isinstance(claim, int):  # pragma: no cover - claim shape is fixed
                raise ValueError("a grouped claim cannot hold singleton state")
            return [(claim, group)]
        return group

    def __getitem__(self, key: LogicalKey) -> list[tuple[int, EntityState]]:
        for logical, candidate in enumerate(self._keys):
            if candidate == key and (group := self._mapping_value(logical)):
                return group
        raise KeyError(key)

    def __iter__(self) -> Iterator[LogicalKey]:
        return (
            key
            for key, group in zip(self._keys, self._groups, strict=True)
            if key is not None and group is not None
        )

    def __len__(self) -> int:
        return sum(group is not None for group in self._groups)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Mapping):
            return False
        comparable = cast("Mapping[object, object]", other)
        return dict(self.items()) == dict(comparable.items())

    def release(self) -> None:
        self._groups.clear()
        self._keys.clear()
        self._claims.clear()

    def release_logical(self, logical: int) -> None:
        self._groups[logical] = None
        self._keys[logical] = None
        self._claims[logical] = 0


@dataclass(frozen=True, slots=True)
class PageRows:
    """One sealed Page's arrays, all indexed by projection.

    ``view_rows`` are positional against ``schema``: projection ``i``'s row is
    laid out by the source layout its own ``sources[i]`` and layout resolve to,
    so a reader translating one into a Root View row asks the schema for the
    translation rather than carrying a key beside every value.
    ``overwritten_edges`` keeps earlier arms from overlapping positions beside
    the parent projection; they are traversed for root-local continuation merging
    but never replace the last value retained in ``view_rows``.

    ``sources`` and ``source_ordinals`` retain each projection's physical
    provider position. Canonical witness selection may reorder projections for
    comparison, but it never rewrites the provenance a conflict reports.

    Reached only through :func:`page_rows`, which is what makes
    :class:`Page` opaque to the result holders that carry one.
    """

    layouts: Sequence[EntityLayout]
    member_rows: Sequence[tuple[object, ...]]
    issues: SparseIssues
    logical_ids: Sequence[int]
    keys: Sequence[LogicalKey | None]
    sources: Sequence[SourceLevel]
    view_rows: Sequence[Sequence[object]]
    overwritten_edges: SparseEdges
    schema: ViewSchema
    roots: tuple[int, ...]
    pin: Pin
    judged_states: JudgedStates
    decoders: DecoderRows
    observer: object | None = None
    witnesses: Sequence[object] = ()
    source_ordinals: Sequence[int] = ()
    claims: Sequence[int | tuple[int, ...]] = ()


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
        return self._rows.pin

    @property
    def root_count(self) -> int:
        """The number of result positions this Page carries."""
        return len(self._rows.roots)

    @property
    def judged_states(self) -> Mapping[LogicalKey, list[tuple[int, EntityState]]]:
        return self._rows.judged_states

    @property
    def observer(self) -> object | None:
        return self._rows.observer


def page_rows(page: object) -> PageRows:
    """``page``'s sealed arrays — the internal read a Root View is granted."""
    if not isinstance(page, Page):
        raise TypeError("a Root View requires a finished Page")
    return page._rows  # pyright: ignore[reportPrivateUsage] - the one seam this scope reads a finished page through


def release_page_rows(page: Page) -> None:
    """Release projection-sized Page storage after atomic roots detach from it."""
    rows = page_rows(page)
    for values in (
        rows.layouts,
        rows.member_rows,
        rows.issues,
        rows.logical_ids,
        rows.keys,
        rows.sources,
        rows.view_rows,
        rows.witnesses,
    ):
        if isinstance(values, list):
            values.clear()
    rows.issues.clear()
    rows.overwritten_edges.clear()
    rows.decoders.clear()
    rows.judged_states.release()


def root_last_uses(page: Page) -> tuple[array[int], array[int]]:
    """Return each projection's and logical state's last reaching root position."""
    rows = page_rows(page)
    typecode = "h" if len(rows.roots) <= 32_768 else "i"
    projection_last = array(typecode, [-1]) * len(rows.layouts)
    logical_last = array(typecode, [-1]) * len(rows.claims)
    for position, root in enumerate(rows.roots):
        pending = [root]
        seen: set[int] = set()
        while pending:
            projection = pending.pop()
            if projection in seen:
                continue
            seen.add(projection)
            projection_last[projection] = position
            logical = rows.logical_ids[projection]
            logical_last[logical] = position
            claim = rows.claims[logical]
            if not isinstance(claim, int):
                for witness in claim:
                    projection_last[witness] = position
            for value in (
                *rows.view_rows[projection],
                *rows.overwritten_edges[projection],
            ):
                if isinstance(value, tuple):
                    pending.extend(cast("tuple[int, ...]", value))
                elif value is not None and value is not ABSENT:
                    pending.append(cast("int", value))
    return projection_last, logical_last


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
        "_claims",
        "_decoders",
        "_first",
        "_identity",
        "_issues",
        "_keys",
        "_last_layout",
        "_last_slots",
        "_last_source",
        "_layouts",
        "_logical_ids",
        "_member_rows",
        "_observer",
        "_overwritten_edges",
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
        self._issues: dict[int, tuple[StoredDataIssueInput, ...]] = {}
        self._logical_ids: list[int] = []
        self._keys: list[LogicalKey | None] = []
        self._last_layout: EntityLayout | None = None
        self._last_slots: SourceViewLayout | None = None
        self._last_source: SourceLevel | None = None
        self._sources: list[SourceLevel] = []
        self._slots: list[SourceViewLayout] = []
        self._views: list[list[object] | tuple[()]] = []
        self._overwritten_edges: dict[int, list[object]] = {}
        self._identity: dict[LogicalKey, int] = {}
        self._first: list[int] = []
        self._claims: list[int | list[int]] = []
        self._decoders: dict[int, _Decoder | None] = {}
        self._witnesses: list[object] = []
        self._sealed = False

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

        The logical-node ID is assigned here from the already decoded identity
        positions and the layout's key rule. Duplicates within one Entity family
        share an ID; a projection whose key did not decode takes an ID of its own
        and keeps its diagnosis, so it shares with nothing — not even a second
        read of the identical unreadable row.

        This is the adapter for rows whose conversion is already complete: it
        derives identity from the supplied members and records the same tuple as
        both raw witness and deferred result. Identity-first provider reads call
        :meth:`add_claim` directly. In both paths a Root View compares every claim
        for the logical node before invoking a decoder, then shares one Page-owned
        Entity State among equal witnesses.
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
        decode: Callable[[], tuple[tuple[object, ...], tuple[StoredDataIssueInput, ...]]]
        | tuple[object, ...],
    ) -> int:
        """Append an identity claim without judging its payload."""
        self._require_open()
        if source == self._last_source and layout is self._last_layout:
            slots = cast("SourceViewLayout", self._last_slots)
        else:
            slots = self._schema.source(source, layout)
            self._last_source = source
            self._last_layout = layout
            self._last_slots = slots
        projection = len(self._layouts)
        existing = None if key is None else self._identity.get(key)
        if existing is None:
            logical = self._fresh(projection)
            if key is not None:
                self._identity[key] = logical
        else:
            logical = existing
            key = self._keys[self._first[logical]]
            claims = self._claims[logical]
            if isinstance(claims, int):
                self._claims[logical] = [claims, projection]
            else:
                claims.append(projection)
        self._layouts.append(layout)
        self._member_rows.append(raw_member_values)
        if identity_issues:
            self._issues[projection] = identity_issues
        if callable(decode):
            self._decoders[projection] = decode
        self._sources.append(source)
        self._slots.append(slots)
        self._views.append(
            cast("list[object]", [ABSENT] * len(slots.slots)) if slots.slots else _NO_VIEWS
        )
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
        distinct hops with the same view key. Delivery keeps the last write, as
        the fetch plan ordered it, while earlier edges remain reachable so their
        continuations can merge into the same root-local logical node.

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
        row = self._views[projection]
        if isinstance(row, tuple):  # pragma: no cover - a resolved slot implies a nonempty row
            raise ValueError("a view slot cannot belong to an empty source layout")
        existing = row[slot]
        if existing is not ABSENT:
            self._overwritten_edges.setdefault(projection, []).append(existing)
        row[slot] = value

    def finish(self, roots: tuple[int, ...], pin: Pin) -> Page:
        """Publish this builder's arrays as one sealed Page, roots in result order.

        The builder is invalidated in the same step, and every array it
        accumulated into is dropped with it, including the key map it assigned
        identity through: what a sealed Page carries is what a Root View reads,
        and nothing observes a
        half-published Page or writes to a published one, and a caller holding
        the sealed builder holds none of what it published.

        A root whose own key did not decode remains at its result ordinal; the
        Root View later publishes the corresponding :class:`InvalidRootInput`,
        which is how a position survives a projection nothing can construct from.
        """
        self._require_open()
        count = len(self._layouts)
        for root in roots:
            _require_index(root, count, "a root")
        source_ordinals = _physical_occurrence_ordinals(self._sources)
        sealed_claims = [
            claim
            if isinstance(claim, int)
            else tuple(
                sorted(
                    claim,
                    key=lambda projection: (
                        self._sources[projection],
                        source_ordinals[projection],
                    ),
                )
            )
            for claim in self._claims
        ]
        rows = PageRows(
            layouts=self._layouts,
            member_rows=self._member_rows,
            issues=SparseIssues(count, self._issues),
            logical_ids=self._logical_ids,
            keys=self._keys,
            sources=self._sources,
            view_rows=self._views,
            overwritten_edges=SparseEdges(count, self._overwritten_edges),
            schema=self._schema,
            roots=roots,
            pin=pin,
            judged_states=JudgedStates(
                tuple(self._keys[first] for first in self._first), sealed_claims
            ),
            observer=self._observer,
            witnesses=self._witnesses,
            source_ordinals=source_ordinals,
            claims=sealed_claims,
            decoders=DecoderRows(count, self._decoders, self._witnesses),
        )
        self._sealed = True
        self._layouts = []
        self._member_rows = []
        self._issues = {}
        self._logical_ids = []
        self._keys = []
        self._sources = []
        self._slots = []
        self._views = []
        self._overwritten_edges = {}
        self._identity = {}
        self._first = []
        self._last_layout = None
        self._last_slots = None
        self._last_source = None
        self._claims = []
        self._decoders = {}
        self._witnesses = []
        return Page(rows)

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

    def _fresh(self, projection: int) -> int:
        logical = len(self._first)
        self._first.append(projection)
        self._claims.append(projection)
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


def _physical_occurrence_ordinals(sources: Sequence[SourceLevel]) -> array[int]:
    ordinals: dict[SourceLevel, int] = {}
    positions = array("I")
    for source in sources:
        ordinal = ordinals.get(source, 0)
        positions.append(ordinal)
        ordinals[source] = ordinal + 1
    return positions


def layout_order_key(
    layout: EntityLayout,
) -> tuple[tuple[str, str], tuple[str, ...]]:
    """The concrete and exact member layout that interpret a Payload Witness."""
    return layout.concrete.sort_key, tuple(stored_order_key(member) for member in layout.members)


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
    if type(left) in (str, bytes, bytearray, int, float, bool, type(None)):
        return left == right
    if isinstance(left, tuple):
        left_tuple = cast("tuple[object, ...]", left)
        other_tuple = cast("tuple[object, ...]", right)
        if len(left_tuple) != len(other_tuple) or left_tuple != other_tuple:
            return False
        for one, two in zip(left_tuple, other_tuple, strict=True):
            if type(one) is not type(two):
                return False
            if type(one) in _ATOMIC_WITNESS_TYPES:
                continue
            if (
                is_dataclass(one)
                or isinstance(one, Mapping)
                or (isinstance(one, Sequence) and not isinstance(one, (str, bytes, bytearray)))
            ) and not exact_stored_equal(cast("object", one), two):
                return False
        return True
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
