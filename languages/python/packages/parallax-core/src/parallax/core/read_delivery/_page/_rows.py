from __future__ import annotations

import datetime as dt
import decimal
import uuid
from array import array
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Final, Literal, NamedTuple, Protocol, cast

from parallax.core.base import UnknownFamilyTag
from parallax.core.deep_fetch import RelationshipViewKey
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
from parallax.core.read_delivery._page._views import SourceLevel, SourceViewLayout, ViewSchema
from parallax.core.temporal_read import Edge, Pin, TemporalReadError, TemporalShape, milestone_edge

__all__ = [
    "ABSENT",
    "EntityState",
    "InvalidRootInput",
    "Page",
    "PageBuilder",
    "PageRows",
    "PageSchedule",
    "RowKey",
    "StoredDataIssueCode",
    "StoredDataIssueInput",
    "attribute_state",
    "dedupe_issues",
    "entity_state",
    "exact_stored_equal",
    "layout_order_key",
    "page_edges",
    "page_rows",
    "page_schedule",
    "push_edges",
    "reach_into",
    "release_finished_rows",
    "release_page_rows",
    "same_stored_values",
    "shared_entity_state",
    "stored_order_key",
    "with_identity_findings",
]

_NO_VIEWS: Final[tuple[()]] = ()
_ATOMIC_STORED_TYPES: Final = (
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
"""The closed internal stored-data issue vocabulary for read delivery."""


@dataclass(frozen=True, slots=True)
class StoredDataIssueInput:
    """One classified stored-state contradiction with logical provenance.

    ``path`` keeps declared member names distinct from integer array positions.
    ``stored_value`` is the already-frozen evidence of what was rejected, frozen
    where conversion translated the finding: nothing downstream re-reads or
    re-freezes it. Fetched rows of one logical row with exactly equal stored
    values share the Page-owned Entity State and its issue record; states with
    distinct stored values under one row key remain separate. The retained
    record is what every seam above shares by reference.
    """

    code: StoredDataIssueCode
    entity: EntityIdentity
    member: AttributeIdentity | ValueObjectIdentity | ValueObjectAttributeIdentity | None = None
    path: tuple[DocumentPathSegment, ...] = ()
    stored_value: object = field(kw_only=True)


@dataclass(frozen=True, slots=True)
class InvalidRootInput:
    """One non-hydrating result root with no constructible fetched row behind it."""

    ordinal: int
    issues: tuple[StoredDataIssueInput, ...]

    def __post_init__(self) -> None:
        if self.ordinal < 0:
            raise ValueError("an invalid root ordinal is nonnegative")
        if not self.issues:
            raise ValueError("an invalid root carries at least one stored-data issue")


class RowKey(NamedTuple):
    """The Page-wide identity of one logical row."""

    family: EntityIdentity
    primary_key: object
    coordinates: tuple[object, ...] = ()


class EntityState(NamedTuple):
    """One judged positional payload shared by every reader of a Page."""

    member_row: tuple[object, ...]
    findings: tuple[StoredDataIssueInput, ...]


class PayloadDecoder(Protocol):
    """Judges a deferred fetched row's payload from the inputs its Page retains:
    its ``stored_values``, the ``routed_values`` recording registered, the
    ``classifiable`` member mask (``None`` where the row carried every member),
    the findings its correlations raised when recorded, and its unrecognized
    family tag. One decoder serves every fetched row of its level."""

    def decode_payload(
        self,
        stored_values: tuple[object, ...],
        routed_values: tuple[object, ...],
        classifiable: int | None,
        correlation_findings: tuple[StoredDataIssueInput, ...],
        unknown_family_tag: UnknownFamilyTag | None,
        *,
        occurrences: bool = True,
    ) -> tuple[tuple[object, ...], tuple[StoredDataIssueInput, ...]]: ...


class SparseIssues:
    __slots__ = ("_count", "_values")

    def __init__(self, count: int, values: dict[int, tuple[StoredDataIssueInput, ...]]) -> None:
        self._count = count
        self._values = values

    def __len__(self) -> int:
        return self._count

    def __getitem__(self, fetched_row: int) -> tuple[StoredDataIssueInput, ...]:
        return self._values.get(fetched_row, ())

    def release(self, fetched_row: int) -> None:
        self._values.pop(fetched_row, None)

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

    def __getitem__(self, fetched_row: int) -> Sequence[object]:
        return self._values.get(fetched_row, _NO_VIEWS)

    def release(self, fetched_row: int) -> None:
        self._values.pop(fetched_row, None)

    def clear(self) -> None:
        self._values.clear()
        self._count = 0


class DecoderRows:
    """Each deferred fetched row's payload judgment.

    A fetched row registered with its member row answers its own stored values.
    A deferred one is judged by its level's shared decoder from the stored
    values and routed member row the Page holds for it, plus the sparse inputs
    registered beside them, each ``None`` where no fetched row registered one.
    A judgment is :meth:`pending` until :meth:`settle` or :meth:`release` drops
    its decoder and inputs. A keyless fetched row's is never settled, since
    every root reaching it judges it again, so the Page keeps its stored values
    and routed row until release. A fetched row judged when it was recorded has
    no judgment here at all.
    """

    __slots__ = (
        "_classifiable",
        "_correlation_findings",
        "_count",
        "_member_rows",
        "_stored_values",
        "_unknown_family_tags",
        "_values",
    )

    def __init__(
        self,
        count: int,
        values: dict[int, PayloadDecoder | None],
        stored_values: Sequence[object],
        member_rows: Sequence[tuple[object, ...]],
        classifiable: dict[int, int] | None,
        correlation_findings: dict[int, tuple[StoredDataIssueInput, ...]] | None,
        unknown_family_tags: dict[int, UnknownFamilyTag] | None,
    ) -> None:
        self._count = count
        self._values = values
        self._stored_values = stored_values
        self._member_rows = member_rows
        self._classifiable = classifiable
        self._correlation_findings = correlation_findings
        self._unknown_family_tags = unknown_family_tags

    def __len__(self) -> int:
        return self._count

    def pending(self, fetched_row: int) -> bool:
        """Whether ``fetched_row`` still has a deferred payload to judge."""
        return self._values.get(fetched_row) is not None

    def decode(
        self, fetched_row: int, *, occurrences: bool = True
    ) -> tuple[tuple[object, ...], tuple[StoredDataIssueInput, ...]]:
        """``fetched_row``'s member row and payload findings, its Value Object
        occurrences left pending without ``occurrences``."""
        if fetched_row in self._values:
            decoder = self._values[fetched_row]
        else:
            stored = self._stored_values[fetched_row]
            decoder = cast("tuple[object, ...]", stored) if isinstance(stored, tuple) else None
        if decoder is None:  # pragma: no cover - a judged keyed fetched row is read from its state
            raise ValueError("a released fetched row decoder has no unjudged state")
        if isinstance(decoder, tuple):
            return decoder, ()
        masks = self._classifiable
        findings = self._correlation_findings
        tags = self._unknown_family_tags
        return decoder.decode_payload(
            cast("tuple[object, ...]", self._stored_values[fetched_row]),
            self._member_rows[fetched_row],
            None if masks is None else masks.get(fetched_row),
            () if findings is None else findings.get(fetched_row, ()),
            None if tags is None else tags.get(fetched_row),
            occurrences=occurrences,
        )

    def settle(self, fetched_row: int) -> None:
        """Retire ``fetched_row``'s judgment once its state no longer needs one."""
        self._values[fetched_row] = None
        if self._classifiable:
            self._classifiable.pop(fetched_row, None)
        if self._correlation_findings:
            self._correlation_findings.pop(fetched_row, None)
        if self._unknown_family_tags:
            self._unknown_family_tags.pop(fetched_row, None)

    def release(self, fetched_row: int) -> None:
        self._values.pop(fetched_row, None)
        if self._classifiable:
            self._classifiable.pop(fetched_row, None)
        if self._correlation_findings:
            self._correlation_findings.pop(fetched_row, None)
        if self._unknown_family_tags:
            self._unknown_family_tags.pop(fetched_row, None)

    def clear(self) -> None:
        self._values.clear()
        self._classifiable = None
        self._correlation_findings = None
        self._unknown_family_tags = None
        self._stored_values = ()
        self._member_rows = ()
        self._count = 0


type RecordedState = EntityState | tuple[object, ...]
"""A judgment recording made: its Entity State, or the member row alone where
the judgment found nothing — a row with no findings is its own state, so the
Page holds no second object for it."""


class JudgedStates:
    """Dense logical-row-indexed judged Entity States: one for a logical row of
    one fetched row, and one per distinct stored values for a logical row of
    several.

    A logical row recorded already judged holds its :data:`RecordedState` from
    the moment it was recorded; any other gains one when it is first judged."""

    __slots__ = ("_fetched_rows_by_logical_row", "_groups")

    def __init__(
        self,
        fetched_rows_by_logical_row: Sequence[int | tuple[int, ...]],
        states: list[RecordedState | list[tuple[int, EntityState]] | None],
    ) -> None:
        self._fetched_rows_by_logical_row = (
            fetched_rows_by_logical_row
            if isinstance(fetched_rows_by_logical_row, list)
            else list(fetched_rows_by_logical_row)
        )
        self._groups = states

    @property
    def by_logical_row(self) -> Sequence[RecordedState | list[tuple[int, EntityState]] | None]:
        """Each logical row's held judgment, read in place: an
        :class:`EntityState` or a bare member row exactly where a logical row
        of one fetched row holds one."""
        return self._groups

    def singleton(self, logical: int) -> EntityState | None:
        group = self._groups[logical]
        if type(group) is tuple:
            return EntityState(group, ())
        return group if isinstance(group, EntityState) else None

    def set_singleton(self, logical: int, state: EntityState) -> None:
        self._groups[logical] = state

    def group(self, logical: int) -> list[tuple[int, EntityState]]:
        group = self._groups[logical]
        if group is None:
            group = []
            self._groups[logical] = group
        if not isinstance(group, list):  # pragma: no cover - logical row shape is fixed
            raise ValueError("a singleton judged state has no group of distinct stored values")
        return group

    def release(self) -> None:
        self._groups.clear()
        self._fetched_rows_by_logical_row.clear()

    def release_logical(self, logical: int) -> None:
        self._groups[logical] = None
        self._fetched_rows_by_logical_row[logical] = 0


@dataclass(frozen=True, slots=True)
class PageRows:
    """One sealed Page's arrays, all indexed by fetched row.

    ``view_rows`` are positional against ``schema``: fetched row ``i``'s row is
    laid out by the source layout its own ``sources[i]`` and layout resolve to,
    so a reader translating one into a Root View row asks the schema for the
    translation rather than carrying a key beside every value. The schema also
    says what each slot holds: a back-reference slot holds ``None``, a logical
    row, or a tuple of coordinate-distinct logical rows, and every other slot
    holds fetched rows. A back-reference is never followed for reachability or
    lifetime.
    ``overwritten_edges`` keeps earlier relationship values from overlapping
    positions beside the parent fetched row; they are traversed for root-local
    continuation merging but never replace the last value retained in
    ``view_rows``.

    ``logical_rows`` maps each fetched row to its logical row, and
    ``fetched_rows_by_logical_row`` maps back: one fetched row, or every
    fetched row with that row key in level and ordinal order. ``stored_values``
    holds what a logical row of several fetched rows compares; a fetched row
    recorded already judged holds none.

    ``sources`` and ``source_ordinals`` retain each fetched row's physical
    provider position. Canonical selection among stored values may reorder
    fetched rows for comparison, but it never rewrites the provenance a
    conflict reports.

    Reached only through :func:`page_rows`, which is what makes
    :class:`Page` opaque to the result holders that carry one.
    """

    layouts: Sequence[EntityLayout]
    member_rows: Sequence[tuple[object, ...]]
    issues: SparseIssues
    logical_rows: Sequence[int]
    keys: Sequence[RowKey | None]
    sources: Sequence[SourceLevel]
    view_rows: Sequence[Sequence[object]]
    overwritten_edges: SparseEdges
    schema: ViewSchema
    roots: tuple[int, ...]
    pin: Pin
    judged_states: JudgedStates
    decoders: DecoderRows
    observer: object | None = None
    stored_values: Sequence[object] = ()
    source_ordinals: Sequence[int] = ()
    fetched_rows_by_logical_row: Sequence[int | tuple[int, ...]] = ()

    def axis_start(self, fetched_row: int, attribute: AttributeIdentity, /) -> object:
        """``fetched_row``'s stored value at one As-Of Axis start, read from its
        row key's coordinates, which align with its layout's
        ``temporal_starts``."""
        layout = self.layouts[fetched_row]
        coordinates = cast("RowKey", self.keys[fetched_row]).coordinates
        return coordinates[layout.temporal_starts.index(layout.index_of[attribute])]

    def axis_end(self, fetched_row: int, attribute: AttributeIdentity, /) -> object:
        """``fetched_row``'s stored value at one As-Of Axis end, read at that
        Attribute's position in its member row."""
        return self.member_rows[fetched_row][self.layouts[fetched_row].index_of[attribute]]


class Page:
    """One materialization's Page: every fetched row, the roots in result order,
    and the Page pin every fetched row was read at.

    Opaque, and opaque publicly rather than only by convention: a result holder
    carrying one can read no row, layout, edge, identity, or issue off it, and
    has nothing to read one with. Its readers — Page-owned judgement here, and the
    lifecycle publication granted this scope — read the sealed arrays through
    :func:`page_rows`, which no package facade exports.

    :attr:`pin` is the one exception, and it is one because the Page pin
    is a fact about the RESULT rather than about the representation: a lifecycle
    publishes it, so a result holder reads it off the Page it holds rather than
    off a second copy travelling beside one.

    A root whose primary key is null or undecodable is an
    :class:`InvalidRootInput` in ``roots``, retaining its result ordinal without
    a row key behind it.
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
    def observer(self) -> object | None:
        return self._rows.observer


def page_rows(page: object) -> PageRows:
    """``page``'s sealed arrays — the internal read its judged-state readers are granted."""
    if not isinstance(page, Page):
        raise TypeError("reading Page rows requires a finished Page")
    return page._rows  # pyright: ignore[reportPrivateUsage] - the one seam this scope reads a finished page through


def same_stored_values(rows: PageRows, left: int, right: int) -> bool:
    """Whether two fetched rows carry the same stored values: the same resolved
    concrete and member layout, and exactly equal provider-normalized values."""
    left_layout = rows.layouts[left]
    right_layout = rows.layouts[right]
    stored = rows.stored_values
    return (
        left_layout.concrete == right_layout.concrete
        and left_layout.members == right_layout.members
        and (stored[left] is stored[right] or exact_stored_equal(stored[left], stored[right]))
    )


def shared_entity_state(rows: PageRows, fetched_row: int) -> EntityState | None:
    """The Entity State already judged for ``fetched_row``, if any.

    A logical row of one fetched row holds at most one. A logical row of
    several holds one per distinct stored values, and ``fetched_row`` shares
    only the one whose stored values are :func:`same_stored_values` as its own.
    """
    logical = rows.logical_rows[fetched_row]
    if isinstance(rows.fetched_rows_by_logical_row[logical], int):
        return rows.judged_states.singleton(logical)
    return next(
        (
            state
            for stored, state in rows.judged_states.group(logical)
            if same_stored_values(rows, fetched_row, stored)
        ),
        None,
    )


def entity_state(rows: PageRows, fetched_row: int) -> EntityState:
    """``fetched_row``'s Page-owned Entity State, judging its payload on first need.

    A fetched row recorded already judged answers the state it was recorded
    with. Otherwise a keyed fetched row shares the state already judged for its
    logical row: the one state of a logical row of one fetched row, or the
    state with equal stored values among several. A keyless fetched row shares
    nothing, so every request judges it again. The identity findings recording
    registered join the payload findings once.
    """
    if rows.keys[fetched_row] is None:
        recorded = rows.judged_states.by_logical_row[rows.logical_rows[fetched_row]]
        if type(recorded) is EntityState:
            return recorded
        if type(recorded) is tuple:
            return EntityState(recorded, ())
        return _judge_entity_state(rows, fetched_row)
    held = shared_entity_state(rows, fetched_row)
    if held is not None:
        _notify(rows.observer, "states_shared")
        return held
    state = _judge_entity_state(rows, fetched_row)
    logical = rows.logical_rows[fetched_row]
    if isinstance(rows.fetched_rows_by_logical_row[logical], int):
        rows.judged_states.set_singleton(logical, state)
        if isinstance(rows.stored_values, list):
            rows.stored_values[fetched_row] = None
    else:
        rows.judged_states.group(logical).append((fetched_row, state))
    return state


def attribute_state(rows: PageRows, fetched_row: int) -> EntityState:
    """``fetched_row``'s Attributes judged as its Entity State would judge them,
    each Value Object occurrence the row carried left pending.

    Such a partial state is shared with nothing and cached nowhere: no other
    reader of the Page can observe it."""
    member_row, findings = rows.decoders.decode(fetched_row, occurrences=False)
    return EntityState(member_row, _with_identity_findings(rows, fetched_row, findings))


def _judge_entity_state(rows: PageRows, fetched_row: int) -> EntityState:
    member_row, findings = rows.decoders.decode(fetched_row)
    if rows.keys[fetched_row] is not None:
        rows.decoders.settle(fetched_row)
    _notify(rows.observer, "states_decoded")
    return EntityState(member_row, _with_identity_findings(rows, fetched_row, findings))


def _with_identity_findings(
    rows: PageRows, fetched_row: int, findings: tuple[StoredDataIssueInput, ...]
) -> tuple[StoredDataIssueInput, ...]:
    return with_identity_findings(findings, rows.issues[fetched_row])


def with_identity_findings(
    payload_findings: tuple[StoredDataIssueInput, ...],
    identity_findings: tuple[StoredDataIssueInput, ...],
) -> tuple[StoredDataIssueInput, ...]:
    """One judgment's findings: its payload findings, then the identity findings
    recording registered, each kept once."""
    if not payload_findings:
        return identity_findings
    if identity_findings:
        return dedupe_issues((*payload_findings, *identity_findings))
    return payload_findings


def _notify(observer: object | None, name: str) -> None:
    if observer is not None:
        getattr(observer, name)()


def release_page_rows(page: Page) -> None:
    """Release fetched-row-sized Page storage after atomic roots detach from it."""
    rows = page_rows(page)
    for values in (
        rows.layouts,
        rows.member_rows,
        rows.issues,
        rows.logical_rows,
        rows.keys,
        rows.sources,
        rows.view_rows,
        rows.stored_values,
    ):
        if isinstance(values, list):
            values.clear()
    rows.issues.clear()
    rows.overwritten_edges.clear()
    rows.decoders.clear()
    rows.judged_states.release()


class PageSchedule(NamedTuple):
    """How one publication over a Page judges its roots' states and releases
    its rows.

    ``last_uses`` is each fetched row's and each logical row's last reaching
    root position, present exactly when release at last use applies.
    ``defers_states`` judges each root's states only after that root's fetched
    rows of one logical row compare, except the states of proved levels, which
    were judged as their rows were recorded. ``PageSchedule(None, False)``
    releases only the member rows a root reached.
    """

    last_uses: tuple[array[int], array[int]] | None
    defers_states: bool


_RAW_ROWS: Final = PageSchedule(None, False)


def page_schedule(
    page: Page, carries_write_evidence: Callable[[EntityIdentity], bool], *, atomic: bool
) -> PageSchedule:
    """``page``'s schedule for one publication of its roots.

    A non-atomic publication drops its Page whole, so it neither defers states
    nor releases at last use. An atomic one defers the states recording left
    unjudged exactly when every root's family carries write evidence, which
    holds vacuously for no roots, and releases at last use when it defers or the
    Page holds a logical row of several fetched rows. Scheduling judges no state.
    """
    if not atomic:
        return _RAW_ROWS
    rows = page_rows(page)
    layouts = rows.layouts
    defers_states = all(carries_write_evidence(layouts[root].concrete) for root in rows.roots)
    if defers_states or any(
        not isinstance(fetched, int) for fetched in rows.fetched_rows_by_logical_row
    ):
        return PageSchedule(_last_uses(rows), defers_states)
    return PageSchedule(None, defers_states)


def _last_uses(rows: PageRows) -> tuple[array[int], array[int]]:
    typecode = "h" if len(rows.roots) <= 32_768 else "i"
    fetched_row_last = array(typecode, [-1]) * len(rows.layouts)
    logical_last = array(typecode, [-1]) * len(rows.fetched_rows_by_logical_row)
    logical_rows = rows.logical_rows
    fetched_rows_by_logical_row = rows.fetched_rows_by_logical_row
    reached: list[int] = []
    for position, root in enumerate(rows.roots):
        reach_into(rows, root, reached)
        for fetched_row in reached:
            fetched_row_last[fetched_row] = position
            logical = logical_rows[fetched_row]
            logical_last[logical] = position
            fetched = fetched_rows_by_logical_row[logical]
            if not isinstance(fetched, int):
                for sibling in fetched:
                    fetched_row_last[sibling] = position
    return fetched_row_last, logical_last


def reach_into(rows: PageRows, root: int, reached: list[int]) -> None:
    """Refill ``reached`` with ``root``'s reach in fetched-row preorder, each
    fetched row once, following :func:`push_edges`. A root with no view row and
    no overwritten edge reaches only itself, with no walk."""
    reached.clear()
    if not rows.view_rows[root] and not rows.overwritten_edges[root]:
        reached.append(root)
        return
    seen: set[int] = set()
    pending = [root]
    while pending:
        fetched_row = pending.pop()
        if fetched_row in seen:
            continue
        seen.add(fetched_row)
        reached.append(fetched_row)
        push_edges(rows, fetched_row, pending)


def release_finished_rows(
    page: Page, schedule: PageSchedule, position: int, reached: Sequence[int]
) -> None:
    """Release the Page storage the root at ``position`` has finished with
    among the fetched rows it ``reached``.

    Every reached member row goes, except a keyless fetched row's still-pending
    one, whose payload a later root judges again. With last uses, a fetched row
    no later root reaches releases all its storage, and a logical row's state
    goes once the last root sharing it has been judged. Releasing again changes
    nothing.
    """
    rows = page_rows(page)
    member_rows = rows.member_rows
    if not isinstance(member_rows, list):  # pragma: no cover - a sealed Page holds lists
        return
    keys = cast("list[RowKey | None]", rows.keys)
    decoders = rows.decoders
    last_uses = schedule.last_uses
    if last_uses is None:
        for fetched_row in reached:
            if keys[fetched_row] is not None or not decoders.pending(fetched_row):
                member_rows[fetched_row] = ()
        return
    fetched_row_last, logical_last = last_uses
    view_rows = cast("list[Sequence[object]]", rows.view_rows)
    stored_values = cast("list[object]", rows.stored_values)
    logical_rows = cast("list[int]", rows.logical_rows)
    for fetched_row in reached:
        if fetched_row_last[fetched_row] != position:
            if keys[fetched_row] is not None or not decoders.pending(fetched_row):
                member_rows[fetched_row] = ()
            continue
        member_rows[fetched_row] = ()
        logical = logical_rows[fetched_row]
        rows.issues.release(fetched_row)
        keys[fetched_row] = None
        view_rows[fetched_row] = ()
        rows.overwritten_edges.release(fetched_row)
        stored_values[fetched_row] = None
        decoders.release(fetched_row)
        logical_rows[fetched_row] = 0
        if logical_last[logical] == position:
            rows.judged_states.release_logical(logical)
            logical_last[logical] = -1


def push_edges(rows: PageRows, fetched_row: int, pending: list[int]) -> None:
    """Push the fetched rows ``fetched_row``'s view row and overwritten edges
    reach, so that they pop in slot order and then in overwrite order. A
    back-reference slot is never followed: it names logical rows other fetched
    rows already reach."""
    for value in reversed(rows.overwritten_edges[fetched_row]):
        if isinstance(value, tuple):
            pending.extend(reversed(cast("tuple[int, ...]", value)))
        elif value is not None:
            pending.append(cast("int", value))
    row = rows.view_rows[fetched_row]
    if not row:
        return
    view_layout = rows.schema.root_view_layout(rows.layouts[fetched_row])
    targets = view_layout.targets[rows.sources[fetched_row]]
    for slot in reversed(range(len(row))):
        if targets[slot] is not None:
            continue
        value = row[slot]
        if isinstance(value, tuple):
            pending.extend(reversed(cast("tuple[int, ...]", value)))
        elif value is not None and value is not ABSENT:
            pending.append(cast("int", value))


def page_edges(page: Page, shape: TemporalShape | None) -> Iterator[Edge | None]:
    """Each root's own As-Of edge in result order, or absence where it has none.

    ``shape`` is the target family's Temporal Shape for a MILESTONE-SET read,
    and ``None`` for every read at one instant — whose roots stand at the Page's
    own pin and have no edge of their own to be published at.

    Absent, too, for a milestone root whose axis starts did not decode. Such a
    root is published at the page's own pin and the delivery continues past it:
    what a delivery advances by is the coordinate the database evaluated, not
    anything this root's stored data turned out to be.
    """
    rows = page_rows(page)
    for root in rows.roots:
        if shape is None:
            yield None
            continue
        yield _root_edge(shape, rows, root)


def _root_edge(shape: TemporalShape, rows: PageRows, root: int) -> Edge | None:
    if rows.keys[root] is None:  # pragma: no cover - a temporal result root with no key has no edge
        return None
    try:
        return milestone_edge(shape, rows, root)
    except TemporalReadError:
        return None


class PageBuilder:
    """One materialization's accumulation arrays and Page-local identity scope.

    Two roles, and the second is a deliberate concession rather than an
    accumulating surface. It **accumulates**: a fetched row is appended with
    :meth:`add_fetched_row`, a level's fan-back is recorded with
    :meth:`write_view`, and :meth:`finish` publishes the lot. It also
    **answers** two questions about rows it already holds —
    :meth:`member_value` and :meth:`concrete_of` — because a read level gathers
    its keys and filters its parents against exactly those rows, and until
    finishing nothing else holds them. Nothing beyond that fan-out may reach for
    the two.

    Page-local identity merges fetched rows into logical rows within one
    builder and never beyond it, so the builder is the unit a caller chooses:
    eager and milestone-set reads each give their whole flat result one Page.
    Only a level ``schema`` says may repeat rows merges; every fetched row of
    any other level is its own logical row. A back-reference, recorded with
    :meth:`write_reference`, retains logical rows, not a page-global fetched
    row winner.

    Relationship views accumulate beside the rows rather than inside them,
    because a parent's views are only known once its child level lands and the
    parent's raw row is long gone by then. What a row can receive is fixed the
    moment it is added: ``schema`` lays out its slots from the source level that
    produced it and the Entity it resolved to, so a fan-back names a view and the
    builder resolves the position, and nothing downstream orders a view again.
    """

    __slots__ = (
        "_classifiable",
        "_correlation_findings",
        "_decoders",
        "_fetched_rows_by_logical_row",
        "_identity",
        "_issues",
        "_keys",
        "_last_layout",
        "_last_repeats",
        "_last_slots",
        "_last_source",
        "_layouts",
        "_logical_rows",
        "_member_rows",
        "_observer",
        "_overwritten_edges",
        "_schema",
        "_sealed",
        "_slots",
        "_sources",
        "_states",
        "_stored_values",
        "_unknown_family_tags",
        "_views",
    )

    def __init__(self, schema: ViewSchema, observer: object | None = None) -> None:
        self._schema = schema
        self._observer = observer
        self._layouts: list[EntityLayout] = []
        self._member_rows: list[tuple[object, ...]] = []
        self._issues: dict[int, tuple[StoredDataIssueInput, ...]] = {}
        self._logical_rows: list[int] = []
        self._keys: list[RowKey | None] = []
        self._last_layout: EntityLayout | None = None
        self._last_slots: SourceViewLayout | None = None
        self._last_source: SourceLevel | None = None
        self._last_repeats = False
        self._sources: list[SourceLevel] = []
        self._slots: list[SourceViewLayout] = []
        self._views: list[list[object] | tuple[()]] = []
        self._overwritten_edges: dict[int, list[object]] = {}
        self._identity: dict[EntityIdentity, dict[object, int | tuple[int, ...]]] = {}
        self._fetched_rows_by_logical_row: list[int | list[int]] = []
        self._states: list[RecordedState | list[tuple[int, EntityState]] | None] = []
        self._decoders: dict[int, PayloadDecoder | None] = {}
        self._classifiable: dict[int, int] = {}
        self._correlation_findings: dict[int, tuple[StoredDataIssueInput, ...]] = {}
        self._unknown_family_tags: dict[int, UnknownFamilyTag] = {}
        self._stored_values: list[object] = []
        self._sealed = False

    # Runs once per fetched row, so its branches stay inline rather than behind
    # per-row calls.
    def add_fetched_row(  # noqa: C901
        self,
        source: SourceLevel,
        layout: EntityLayout,
        key: RowKey | None,
        stored_values: object,
        member_row: tuple[object, ...],
        identity_issues: tuple[StoredDataIssueInput, ...],
        judgment: PayloadDecoder | RecordedState | None,
    ) -> int:
        """Append one fetched row and answer its index.

        A keyed fetched row of a level the schema says may repeat rows joins
        the logical row its ``key`` names; every other fetched row is a new
        logical row, so it shares with nothing — not even a second fetched row
        of the identical unreadable row. A Root View compares the
        ``stored_values`` of every fetched row of one logical row before judging
        its payload, then shares one Page-owned Entity State among equal ones.

        ``judgment`` is how the payload is judged: ``None`` where ``member_row``
        already is it, the decoder that judges it later from ``stored_values``,
        ``member_row`` and any :meth:`add_payload_inputs`, or the
        :data:`RecordedState` recording already judged, held by the new logical
        row it alone can be. Raises :class:`ValueError` for a judged fetched row
        of a level that may repeat rows, whose comparison must precede its
        judgment.
        """
        if self._sealed:
            self._require_open()
        if source == self._last_source and layout is self._last_layout:
            slots = cast("SourceViewLayout", self._last_slots)
            repeats = self._last_repeats
        else:
            slots = self._schema.source(source, layout)
            repeats = self._schema.may_repeat_rows(source)
            self._last_source = source
            self._last_layout = layout
            self._last_slots = slots
            self._last_repeats = repeats
        fetched_row = len(self._layouts)
        if repeats and key is not None:
            logical = self._merged_logical_row(key, fetched_row)
            fetched = self._fetched_rows_by_logical_row[logical]
            if fetched != fetched_row:
                if isinstance(fetched, int):
                    key = self._keys[fetched]
                    self._fetched_rows_by_logical_row[logical] = [fetched, fetched_row]
                else:
                    key = self._keys[fetched[0]]
                    fetched.append(fetched_row)
        else:
            logical = self._new_logical_row(fetched_row)
        if judgment is not None:
            if type(judgment) is EntityState or type(judgment) is tuple:
                if repeats:
                    raise ValueError(
                        "a fetched row of a level that may repeat rows is compared before "
                        "it is judged"
                    )
                self._states[logical] = judgment
                if self._observer is not None:
                    _notify(self._observer, "states_decoded")
            else:
                self._decoders[fetched_row] = cast("PayloadDecoder", judgment)
        self._layouts.append(layout)
        self._member_rows.append(member_row)
        if identity_issues:
            self._issues[fetched_row] = identity_issues
        self._sources.append(source)
        self._slots.append(slots)
        self._views.append(
            cast("list[object]", [ABSENT] * len(slots.slots)) if slots.slots else _NO_VIEWS
        )
        self._logical_rows.append(logical)
        self._keys.append(key)
        self._stored_values.append(stored_values)
        return fetched_row

    def add_payload_inputs(
        self,
        fetched_row: int,
        classifiable: int | None,
        correlation_findings: tuple[StoredDataIssueInput, ...],
        unknown_family_tag: UnknownFamilyTag | None,
    ) -> None:
        """Retain what a deferred payload judgment needs beyond the fetched
        row's stored values and routed row, each only where set: the members
        the row carried for classification where it did not carry them all, the
        findings its correlations raised when recorded, and its unrecognized
        family tag."""
        self._require_open()
        if classifiable is not None:
            self._classifiable[fetched_row] = classifiable
        if correlation_findings:
            self._correlation_findings[fetched_row] = correlation_findings
        if unknown_family_tag is not None:
            self._unknown_family_tags[fetched_row] = unknown_family_tag

    def write_view(self, fetched_row: int, view: RelationshipViewKey, value: object) -> None:
        """Record one relationship view on an already-added fetched row.

        ``value`` is ``None`` for loaded-null, a fetched row index for a loaded
        to-one, or a tuple of them — empty included — for a loaded to-many.
        A slot never written stays :data:`ABSENT`, which is unloaded — what a
        path-root guard leaves behind when it excludes a parent from a level.

        Named by view rather than by position, so a fan-back never learns about
        slots: the fetched row's own source layout resolves one. Two levels may
        legitimately write one view — a guarded path and its broad sibling are
        distinct hops with the same view key. Delivery keeps the last write, as
        the fetch plan ordered it, while earlier edges remain reachable so their
        continuations can merge into the same root-local logical row.

        Raises :class:`ValueError` for a view no level below this fetched row's
        own source attaches, which is a fan-back writing against a plan the
        schema was not built from.
        """
        self._require_open()
        _require_edge(value, len(self._layouts))
        slot = self._slot(fetched_row, view)
        row = cast("list[object]", self._views[fetched_row])
        existing = row[slot]
        if existing is not ABSENT:
            self._overwritten_edges.setdefault(fetched_row, []).append(existing)
        row[slot] = value

    def write_reference(
        self,
        fetched_row: int,
        view: RelationshipViewKey,
        family: EntityIdentity,
        member: MemberIdentity,
    ) -> None:
        """Record the logical rows ``fetched_row``'s ``member`` names in
        ``family`` on a back-reference slot, for the Root View to resolve among
        its own reached nodes.

        A null or unloaded ``member`` names nothing and records loaded-null.
        Raises :class:`ValueError` when ``member`` names no logical row this
        Page merged — a back-reference revisits an ancestor already recorded,
        at a level whose rows the schema merges — or when ``view``'s slot holds
        fetched rows rather than logical rows.
        """
        self._require_open()
        slot = self._slot(fetched_row, view)
        row = cast("list[object]", self._views[fetched_row])
        layout = self._layouts[fetched_row]
        if self._schema.root_view_layout(layout).targets[self._sources[fetched_row]][slot] is None:
            raise ValueError(
                f"{view.narrowed_view or view.relationship.name!r} on "
                f"{layout.concrete.canonical} holds fetched rows, not back-reference logical rows"
            )
        key = self.member_value(fetched_row, member)
        if key is None or key is ABSENT:
            row[slot] = None
            return
        by_key = self._identity.get(family)
        entry = None if by_key is None else by_key.get(key)
        if entry is None:
            raise ValueError(
                f"back-reference {view.relationship.name!r}: no already-recorded "
                f"{family.canonical} logical row for key {key!r} on this Page"
            )
        row[slot] = entry

    def _slot(self, fetched_row: int, view: RelationshipViewKey) -> int:
        slot = self._slots[fetched_row].index_of.get(view)
        if slot is None:
            raise ValueError(
                f"no level below source {self._sources[fetched_row]} attaches "
                f"{view.narrowed_view or view.relationship.name!r} to "
                f"{self._layouts[fetched_row].concrete.canonical}"
            )
        row = self._views[fetched_row]
        if isinstance(row, tuple):  # pragma: no cover - a resolved slot implies a nonempty row
            raise ValueError("a view slot cannot belong to an empty source layout")
        return slot

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
        which is how a position survives a fetched row nothing can construct from.
        """
        self._require_open()
        count = len(self._layouts)
        for root in roots:
            _require_index(root, count, "a root")
        source_ordinals = _physical_fetched_row_ordinals(self._sources)
        fetched_rows_by_logical_row = [
            fetched
            if isinstance(fetched, int)
            else tuple(
                sorted(
                    fetched,
                    key=lambda fetched_row: (
                        self._sources[fetched_row],
                        source_ordinals[fetched_row],
                    ),
                )
            )
            for fetched in self._fetched_rows_by_logical_row
        ]
        rows = PageRows(
            layouts=self._layouts,
            member_rows=self._member_rows,
            issues=SparseIssues(count, self._issues),
            logical_rows=self._logical_rows,
            keys=self._keys,
            sources=self._sources,
            view_rows=self._views,
            overwritten_edges=SparseEdges(count, self._overwritten_edges),
            schema=self._schema,
            roots=roots,
            pin=pin,
            judged_states=JudgedStates(fetched_rows_by_logical_row, self._states),
            observer=self._observer,
            stored_values=self._stored_values,
            source_ordinals=source_ordinals,
            fetched_rows_by_logical_row=fetched_rows_by_logical_row,
            decoders=DecoderRows(
                count,
                self._decoders,
                self._stored_values,
                self._member_rows,
                self._classifiable or None,
                self._correlation_findings or None,
                self._unknown_family_tags or None,
            ),
        )
        self._sealed = True
        self._layouts = []
        self._member_rows = []
        self._issues = {}
        self._logical_rows = []
        self._keys = []
        self._sources = []
        self._slots = []
        self._views = []
        self._overwritten_edges = {}
        self._identity = {}
        self._last_layout = None
        self._last_slots = None
        self._last_source = None
        self._last_repeats = False
        self._fetched_rows_by_logical_row = []
        self._states = []
        self._decoders = {}
        self._classifiable = {}
        self._correlation_findings = {}
        self._unknown_family_tags = {}
        self._stored_values = []
        return Page(rows)

    def member_value(self, fetched_row: int, member: MemberIdentity) -> object:
        """``fetched_row``'s value at ``member``, by position.

        Answers :data:`ABSENT` for a member this fetched row's read did not
        carry and for one its Entity does not lay out at all, which is what
        distinguishes an unloaded correlation member from one stored null — a
        gathered key skips both, but they are no longer the same answer.
        """
        self._require_open()
        position = self._layouts[fetched_row].index_of.get(member)
        return ABSENT if position is None else self._member_rows[fetched_row][position]

    def concrete_of(self, fetched_row: int) -> EntityIdentity:
        """The exact Entity ``fetched_row``'s own compiled read resolved it to."""
        self._require_open()
        return self._layouts[fetched_row].concrete

    def write_to_one(
        self, fetched_row: int, view: RelationshipViewKey, candidates: Sequence[int]
    ) -> None:
        """Carry the stored values of every fetched row of the selected logical
        target into root-local conflict judgment without changing selection
        among distinct targets."""
        if not candidates:
            self.write_view(fetched_row, view, None)
            return
        first = candidates[0]
        logical = self._logical_rows[first]
        for candidate in reversed(candidates[1:]):
            if self._logical_rows[candidate] == logical:
                self.write_view(fetched_row, view, candidate)
        self.write_view(fetched_row, view, first)

    def _new_logical_row(self, fetched_row: int) -> int:
        logical = len(self._fetched_rows_by_logical_row)
        self._fetched_rows_by_logical_row.append(fetched_row)
        self._states.append(None)
        return logical

    def _merged_logical_row(self, key: RowKey, fetched_row: int) -> int:
        """The logical row ``key`` names, else a new one for ``fetched_row``.

        A primary key's entry is the value :meth:`write_reference` shares, so a
        coordinate-distinct logical row replaces it with a longer tuple rather
        than changing what an earlier back-reference already recorded.
        """
        by_key = self._identity.get(key.family)
        if by_key is None:
            by_key = self._identity[key.family] = {}
        entry = by_key.get(key.primary_key)
        if entry is None:
            logical = by_key[key.primary_key] = self._new_logical_row(fetched_row)
            return logical
        coordinates = key.coordinates
        if isinstance(entry, int):
            if self._coordinates_of(entry) == coordinates:
                return entry
            logical = self._new_logical_row(fetched_row)
            by_key[key.primary_key] = (entry, logical)
            return logical
        for merged in entry:
            if self._coordinates_of(merged) == coordinates:
                return merged
        logical = self._new_logical_row(fetched_row)
        by_key[key.primary_key] = (*entry, logical)
        return logical

    def _coordinates_of(self, logical: int) -> tuple[object, ...]:
        fetched = self._fetched_rows_by_logical_row[logical]
        first = fetched if isinstance(fetched, int) else fetched[0]
        return cast("RowKey", self._keys[first]).coordinates

    def _require_open(self) -> None:
        if self._sealed:
            raise ValueError("this page builder finished its arrays into a Page and holds nothing")


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
            f"{holder} names a fetched row by an exact built-in int, and {value!r} is not one"
        )
    if not 0 <= value < count:
        raise ValueError(
            f"{holder} names fetched row {value}, outside this Page's {count} fetched rows"
        )


def _physical_fetched_row_ordinals(sources: Sequence[SourceLevel]) -> array[int]:
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
    """The concrete and exact member layout that interpret stored values."""
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


# One branch per stored value kind. It runs per stored-values comparison and again per nested
# value, so the branches stay inline rather than behind a per-kind call.
def exact_stored_equal(left: object, right: object) -> bool:  # noqa: C901
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
            if type(one) in _ATOMIC_STORED_TYPES:
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
