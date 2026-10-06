from __future__ import annotations

import bisect
import datetime as dt
from array import array
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Final, Literal

from parallax.core.base import INFINITY, TemporalBound
from parallax.core.document_codec import PreparedEffectiveChange, prepare_effective_change
from parallax.core.inheritance import InheritanceEntityView
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityMetadata,
    ValueObjectIdentity,
)
from parallax.core.temporal_read import (
    Bitemporal,
    TimeInterval,
    TransactionTimeOnly,
    milestone_edge,
)
from parallax.core.temporal_write.coverage import (
    CARRIED_HEAD,
    CARRIED_TAIL,
    WITHIN,
    CoverageTransform,
    Successor,
)
from parallax.core.write_plan.keys import ObjectKey, ObservedStateKey, TemporalStateKey
from parallax.core.write_plan.materialized import PredecessorRows
from parallax.core.write_plan.observe import PredecessorRow, carries_cell
from parallax.core.write_plan.plan import (
    OPEN_BITEMPORAL_ENDS,
    TRANSACTION_TIME_ENDS,
    Derivation,
    Openings,
    OwnedEndpoint,
    Ownership,
    UnitEffects,
)
from parallax.core.write_plan.planned_rows import (
    PreparedAssignment,
    WritePlanningError,
    assigned_name,
    resolve_row,
    resolved_assignments,
)
from parallax.core.write_plan.steps import (
    FAILED_PRECONDITION,
    NEW_LINEAGE,
    SUPERSEDED,
    TERMINATED,
    UNGATED,
    CarriedFrom,
    ChangedFrom,
    CloseCause,
    ExactCount,
    Finite,
    InsertEntry,
    MaxPlusOne,
    MilestoneTarget,
    PlannedAssignments,
    PlannedClose,
    PlannedInsert,
    PlannedTemporalGuard,
    PlannedTemporalRemoval,
    PlannedTemporalRevision,
    PlannedValue,
    PlannedWrite,
    Shortfall,
    TemporalConcurrency,
    TemporalGate,
    TemporalUpperBound,
    Ungated,
    adopt_planned_assignments,
    adopt_planned_row,
    shortfall_for,
)
from parallax.core.write_plan.steps import INFINITY as OPEN_UPPER_BOUND

__all__ = [
    "Expansion",
    "ExpansionRole",
    "PredecessorExpansion",
    "PredecessorUse",
    "SettledGroup",
    "TemporalFacts",
    "bitemporal_ends",
    "entry_endpoint",
    "entry_ends",
    "opening",
    "openings",
]

type ExpansionRole = Literal["coverage", "starting", "validation"]
"""How a unit's driver asks one predecessor to be expanded: as coverage its
transform applies to, as coverage a caller's starting condition names, or as an
earlier observation it only validates and retires."""

type _ResolvedState = tuple[
    dict[AttributeIdentity, PlannedValue], dict[ValueObjectIdentity, object]
]


@dataclass(frozen=True, slots=True)
class TemporalFacts:
    """What one temporal unit settles about its target before any predecessor
    is in hand: the target, its compiled family-effective view, the Temporal
    Shape whose axes bound its intervals, and the attempt's resolved instant.

    Every field is a value a facet or the clock produced, never the producer,
    so a deferred range may retain them and still decide nothing later.
    """

    entity: EntityMetadata
    view: InheritanceEntityView
    shape: TransactionTimeOnly | Bitemporal
    instant: dt.datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class Expansion(UnitEffects):
    """One predecessor's planned steps — its own effect before the successors it
    opens — beside the effects their success publishes."""

    steps: tuple[PlannedWrite, ...]


_NOTHING: Final[Expansion] = Expansion(steps=())


class PredecessorExpansion:
    """The per-predecessor rules of one temporal unit: whether its transform
    reaches a predecessor, whether the predecessor stays unchanged, how it is
    closed and gated, how the attempt's ownership disposes of it, and which
    successors it opens.

    Built once per unit — a range binding or a Materialized Write Group — from
    the unit's settled facts and the attempt's ownership as it stands then.
    ``key_value`` is a range's one object key; a group reads each row's own.
    ``addressed`` holds the windows a range's callers addressed, ``gated`` and
    ``guards`` whether its closes gate and whether the database can prove an
    unchanged milestone by a guard, and ``derives`` whether a later unit of the
    flush relies on what it derives. Each canonical assignment mapping is
    resolved once per expansion, however many successors and gaps share it.
    Nothing returned retains the expansion or the ownership it read.
    """

    __slots__ = (
        "_addressed",
        "_derives",
        "_facts",
        "_gated",
        "_guards",
        "_key_attributes",
        "_key_values",
        "_ownership",
        "_resolved",
        "_transform",
    )

    def __init__(
        self,
        facts: TemporalFacts,
        transform: CoverageTransform,
        *,
        key_attribute: AttributeIdentity,
        key_value: object = None,
        gated: bool,
        guards: bool = False,
        addressed: tuple[TimeInterval | None, ...] = (),
        derives: bool = False,
        ownership: Ownership,
    ) -> None:
        self._facts = facts
        self._transform = transform
        self._key_attributes = (key_attribute,)
        self._key_values = (key_value,)
        self._gated = gated
        self._guards = guards
        self._addressed = addressed
        self._derives = derives
        self._ownership = ownership
        self._resolved: dict[int, _ResolvedState] = {}

    def expand(
        self,
        predecessor: PredecessorRow,
        *,
        role: ExpansionRole,
        state: ObservedStateKey,
        coverage: TimeInterval | None,
    ) -> Expansion:
        """``predecessor`` — the current row whose observed state is ``state``
        and whose Valid Time is ``coverage`` (``None`` without Valid Time) —
        expanded in its ``role``.

        A transform that does not reach the predecessor leaves it alone. A
        coverage predecessor it leaves exactly as it was is kept where that is
        proven (:func:`_preserved`). Otherwise the predecessor is closed —
        Superseded where a successor assigns, Terminated otherwise — and its
        nonempty successors opened, or the attempt's own row is revised or
        removed instead (:func:`_dispose`). A ``starting`` predecessor's gated
        close fails as its caller's precondition. A ``validation`` predecessor
        is retired as Terminated through the same disposal, opening nothing.
        """
        if role == "validation":
            closing = self.closing(predecessor, coverage, TERMINATED)
            return self._disposed(predecessor, state, coverage, closing, (), ())
        transform = self._transform
        if not transform.reaches(coverage):
            return _NOTHING
        successors = transform.successors_of(coverage)
        if role == "coverage":
            kept_as_is = self._kept_unchanged(predecessor, coverage, successors)
            if kept_as_is is not None:
                return kept_as_is
        if successors:
            predecessor = predecessor.with_bindable_document()
        inserts = tuple(self._successor(predecessor, successor) for successor in successors)
        cause = (
            SUPERSEDED
            if any(successor.assigned is not None for successor in successors)
            else TERMINATED
        )
        closing = self.closing(predecessor, coverage, cause, starting=role == "starting")
        return self._disposed(predecessor, state, coverage, closing, successors, inserts)

    def closing(
        self,
        predecessor: PredecessorRow,
        coverage: TimeInterval | None,
        cause: CloseCause,
        *,
        starting: bool = False,
    ) -> PlannedClose:
        """The close of ``predecessor`` at its own address, gated on its
        observed Transaction-Time start where the unit gates."""
        facts = self._facts
        gate: TemporalConcurrency = UNGATED
        if self._gated:
            start = facts.shape.transaction_time.start_attribute
            gate = TemporalGate(start_attribute=start, observed_start=predecessor.cell(start))
        return _planned_close(
            facts,
            key_attributes=self._key_attributes,
            key_values=self._key_values,
            observed_valid_end=None if coverage is None else coverage.end,
            cause=cause,
            gate=gate,
            on_shortfall=FAILED_PRECONDITION if starting and self._gated else None,
        )

    def assignments(self, assigned: Mapping[str, object]) -> _ResolvedState:
        """``assigned`` under its resolved member identities, resolved once per
        expansion. The answer is shared, so a caller opening a row from it
        copies what it stamps."""
        maps = self._resolved.get(id(assigned))
        if maps is None:
            facts = self._facts
            maps = resolve_row(facts.entity, facts.view, assigned, context="insert")
            self._resolved[id(assigned)] = maps
        return maps

    def settle_group(
        self, evidence: PredecessorRows, assignments: Sequence[PreparedAssignment]
    ) -> SettledGroup:
        """A Materialized Write Group's selected rows, every one a coverage
        predecessor of this expansion's one-segment transform, settled into
        the immutable backing its steps and effects are read from.

        ``assignments`` are the group's own, resolved here once for every row;
        a marker no opened row can express is refused before anything is
        settled. Selection already eliminated every row the assignments leave
        unchanged, so no row is judged unchanged again. Each row's disposition
        follows the same rules :meth:`expand` applies — reach, close, revision
        or removal of a row the attempt opened, and the nonempty successors —
        decided from the row's own cells without building any of its steps.
        An unowned Transaction-Time-Only group reads no row at all: every row
        takes the one disposition its mutation decides.

        With two or more assignments a selected row may still restore some of
        them, so the codec's effective-change comparison is prepared once here
        and a changed successor overlays only the members it answers as
        effective for that row (`m-unit-work` "Comparing an assigned member").
        """
        facts = self._facts
        attributes, value_objects = resolved_assignments(facts.entity, assignments, "insert")
        selection = evidence.selection
        change = (
            prepare_effective_change(
                selection.shape,
                {assigned_name(assignment): assignment.value for assignment in assignments},
                absent=evidence.absent,
            )
            if len(assignments) >= 2
            else None
        )
        shape = facts.shape
        transform = self._transform
        valid_positions = (
            (
                selection.position(shape.valid_time.start_attribute),
                selection.position(shape.valid_time.end_attribute),
            )
            if isinstance(shape, Bitemporal)
            else None
        )
        uniform, dispositions, offsets, length = _RowDisposal(
            facts=facts,
            transform=transform,
            ownership=self._ownership,
            owning=self._ownership.owns_any(facts.entity.identity),
            key_position=evidence.key_position,
            valid_positions=valid_positions,
            absent=evidence.absent,
            attributes=attributes,
            value_objects=value_objects,
            change=change,
        ).settle(evidence)
        return SettledGroup(
            facts=facts,
            transform=transform,
            key_attributes=self._key_attributes,
            cause=SUPERSEDED if transform.assigns else TERMINATED,
            gate_position=(
                selection.position(shape.transaction_time.start_attribute) if self._gated else None
            ),
            valid_positions=valid_positions,
            assigned_attributes=MappingProxyType(attributes),
            assigned_value_objects=MappingProxyType(value_objects),
            change=change,
            uniform=uniform,
            dispositions=dispositions,
            offsets=offsets,
            length=length,
        )

    def _kept_unchanged(
        self,
        predecessor: PredecessorRow,
        coverage: TimeInterval | None,
        successors: Sequence[Successor],
    ) -> Expansion | None:
        """How an unchanged coverage predecessor is kept, or ``None`` where it
        changes or its unchanged state cannot be proven."""
        if not (
            self._guards or not self._gated or self._ownership.owns(self._endpoint(coverage))
        ) or not self._unchanged(predecessor, coverage, successors):
            return None
        return _preserved(
            self._facts,
            self.closing(predecessor, coverage, SUPERSEDED),
            self._ownership,
            guards=self._guards,
        )

    def _unchanged(
        self,
        predecessor: PredecessorRow,
        coverage: TimeInterval | None,
        successors: Sequence[Successor],
    ) -> bool:
        """Whether ``successors`` leave ``predecessor`` as it was: together they
        cover all of it, each assigned member already holds its value there,
        and no caller-addressed window reaches it."""
        if any(_reaches(window, coverage) for window in self._addressed):
            return False
        if coverage is None:
            if len(successors) != 1:
                return False
        elif not _complete(successors, coverage):
            return False
        selection = self._facts.view.member_selection
        return all(
            successor.assigned is None or predecessor.holds(selection, successor.assigned)
            for successor in successors
        )

    def _successor(self, predecessor: PredecessorRow, successor: Successor) -> PlannedInsert:
        coverage = successor.valid_time_coverage
        if coverage is None:
            start = end = None
        else:
            start, end = coverage.start, coverage.end
        assigned = successor.assigned
        if assigned is None:
            return _successor_insert(self._facts, predecessor, start, end)
        attributes, value_objects = self.assignments(assigned)
        return _successor_insert(self._facts, predecessor, start, end, attributes, value_objects)

    def _disposed(
        self,
        predecessor: PredecessorRow,
        state: ObservedStateKey,
        coverage: TimeInterval | None,
        closing: PlannedClose,
        successors: Sequence[Successor],
        inserts: tuple[PlannedInsert, ...],
    ) -> Expansion:
        derived = (
            (self._derivation(state, coverage, closing, successors, inserts),)
            if self._derives
            else ()
        )
        return _dispose(self._facts, closing, inserts, predecessor, self._ownership, state, derived)

    def _derivation(
        self,
        state: ObservedStateKey,
        coverage: TimeInterval | None,
        closing: PlannedClose,
        successors: Sequence[Successor],
        inserts: Sequence[PlannedInsert],
    ) -> Derivation:
        """What a later unit needs of one predecessor's expansion: its state and
        coverage, its own address where the attempt owned it, and each
        nonempty row derived from it with the coverage it opens."""
        facts = self._facts
        own = _target_endpoint(facts, closing.target)
        rows: list[tuple[OwnedEndpoint, TimeInterval | None]] = []
        for successor, insert in zip(successors, inserts, strict=True):
            (entry,) = insert.entries
            endpoint = entry_endpoint(facts, entry)
            if endpoint is not None:
                rows.append((endpoint, successor.valid_time_coverage))
        return Derivation(
            original=state,
            valid_time_coverage=coverage,
            owned=own if self._ownership.owns(own) else None,
            rows=tuple(rows),
        )

    def _endpoint(self, coverage: TimeInterval | None) -> OwnedEndpoint:
        return OwnedEndpoint(
            self._facts.entity.identity,
            self._key_values,
            TRANSACTION_TIME_ENDS if coverage is None else bitemporal_ends(coverage.end),
        )


class PredecessorUse(Enum):
    """What materializing one group step needs of its row's predecessor:
    nothing, only its member cells, or its bindable document — for the last
    time where ``BINDABLE_LAST``, since no later step of the row needs it."""

    NONE = "none"
    MEMBERS = "members"
    BINDABLE = "bindable"
    BINDABLE_LAST = "bindable-last"


# One selected row's settled disposition, packed into one small integer: the
# successor positions it keeps (coverage's bits), what becomes of the row
# itself, the position an owned row keeps its address at, whether its
# successors continue an insertion, and whether the transform reaches it.
_POSITIONS: Final = (CARRIED_HEAD, WITHIN, CARRIED_TAIL)
_POSITION_BITS: Final = CARRIED_HEAD | WITHIN | CARRIED_TAIL
_CLOSE: Final = 0
_REMOVE: Final = 1 << 3
_REVISE: Final = 2 << 3
_KEEP: Final = 3 << 3
_DISPOSAL: Final = 3 << 3
_KEPT_SHIFT: Final = 5
_CONTINUES: Final = 1 << 8
_UNREACHED: Final = 1 << 9


def _kept_position(code: int) -> int:
    return (code >> _KEPT_SHIFT) & _POSITION_BITS


def _opened(code: int) -> int:
    """The successor positions a row opens: every one it keeps but the one an
    owned row keeps its address at."""
    return code & _POSITION_BITS & ~_kept_position(code)


def _affects(code: int) -> bool:
    """Whether the row itself is closed, removed, or revised — the one step of
    its own a row takes, and the change to its observed state."""
    return not code & _UNREACHED and code & _DISPOSAL != _KEEP


def _row_steps(code: int) -> int:
    return _affects(code) + _opened(code).bit_count()


def _nth_position(positions: int, nth: int) -> int:
    for position in _POSITIONS:
        if positions & position:
            if not nth:
                return position
            nth -= 1
    raise IndexError(nth)  # pragma: no cover - a located step lies within its row


@dataclass(frozen=True, slots=True)
class SettledGroup:
    """A Materialized Write Group's settled temporal expansion: the facts its
    rows share and the final disposition of every selected row, from which any
    one step, and the effects of all of them, are read on demand.

    A group whose rows all take one disposition holds it once as ``uniform``
    and maps a step index to its row arithmetically. Otherwise
    ``dispositions`` holds each row's, ``offsets`` where each row's steps
    begin, and ``length`` how many steps they total; a row taking no step keeps
    its place and is skipped by the lookup. Nothing here is a producer or the
    attempt's live ownership: what each row's disposition reads was decided
    when the group settled.
    """

    facts: TemporalFacts
    transform: CoverageTransform
    key_attributes: tuple[AttributeIdentity, ...]
    cause: CloseCause
    gate_position: int | None
    valid_positions: tuple[int, int] | None
    assigned_attributes: Mapping[AttributeIdentity, PlannedValue]
    assigned_value_objects: Mapping[ValueObjectIdentity, object]
    change: PreparedEffectiveChange | None
    uniform: int
    dispositions: array[int] | None
    offsets: array[int] | None
    length: int

    def __len__(self) -> int:
        return self.length

    def locate(self, index: int) -> tuple[int, int]:
        """The row the group's ``index``-th step belongs to, and that step's
        place among the row's own."""
        offsets = self.offsets
        if offsets is None:
            return divmod(index, _row_steps(self.uniform))
        row = bisect.bisect_right(offsets, index) - 1
        return row, index - offsets[row]

    def predecessor_use(self, row: int, place: int) -> PredecessorUse:
        """What the step at ``place`` of ``row`` needs of the row's
        predecessor (:meth:`locate`)."""
        code = self._code(row)
        if _affects(code) and place == 0:
            if code & _DISPOSAL == _REVISE:
                return PredecessorUse.MEMBERS
            return PredecessorUse.NONE
        if place == _row_steps(code) - 1:
            return PredecessorUse.BINDABLE_LAST
        return PredecessorUse.BINDABLE

    def step(
        self, evidence: PredecessorRows, row: int, place: int, predecessor: PredecessorRow | None
    ) -> PlannedWrite:
        """The step at ``place`` of ``row``, built from ``evidence`` and the
        ``predecessor`` its use (:meth:`predecessor_use`) asks for."""
        code = self._code(row)
        values = evidence.rows[row]
        if _affects(code):
            if place == 0:
                return self._effect(code, evidence.key(row), values, predecessor)
            place -= 1
        assert predecessor is not None  # every successor reads its predecessor
        return self._successor(_nth_position(_opened(code), place), values, predecessor)

    def effects(self, evidence: PredecessorRows) -> UnitEffects:
        """What every row's success publishes, as views over ``evidence`` and
        these dispositions that read them only when iterated."""
        return UnitEffects(
            changed=_GroupChanges(self, evidence),
            removed=_GroupRemovals(self, evidence),
            opened=Openings(
                fresh=_GroupOpenings(self, evidence, continued=False),
                continued=_GroupOpenings(self, evidence, continued=True),
            ),
        )

    def changed_states(self, evidence: PredecessorRows) -> Iterator[ObservedStateKey]:
        facts = self.facts
        entity = facts.entity.identity
        key_name = self.key_attributes[0].name
        for row in range(len(evidence)):
            if _affects(self._code(row)):
                yield TemporalStateKey(
                    ObjectKey(entity, ((key_name, evidence.key(row)),)),
                    milestone_edge(facts.shape, evidence, row),
                )

    def removals(self, evidence: PredecessorRows) -> Iterator[OwnedEndpoint]:
        if self.dispositions is None and self.uniform & _DISPOSAL != _REMOVE:
            return
        for row in range(len(evidence)):
            if self._code(row) & _DISPOSAL == _REMOVE:
                values = evidence.rows[row]
                yield self._endpoint(evidence.key(row), self._valid_end(values))

    def openings(self, evidence: PredecessorRows, *, continued: bool) -> Iterator[OwnedEndpoint]:
        if self.dispositions is None and bool(self.uniform & _CONTINUES) is not continued:
            return
        for row in range(len(evidence)):
            code = self._code(row)
            if bool(code & _CONTINUES) is not continued:
                continue
            values = evidence.rows[row]
            key = evidence.key(row)
            for position in _POSITIONS:
                if _opened(code) & position:
                    _start, end = self._extent(position, values)
                    yield self._endpoint(key, end)

    def _code(self, row: int) -> int:
        dispositions = self.dispositions
        return self.uniform if dispositions is None else dispositions[row]

    def _effect(
        self,
        code: int,
        key: object,
        values: tuple[object, ...],
        predecessor: PredecessorRow | None,
    ) -> PlannedWrite:
        facts = self.facts
        gate_position = self.gate_position
        closing = _planned_close(
            facts,
            key_attributes=self.key_attributes,
            key_values=(key,),
            observed_valid_end=self._valid_end(values),
            cause=self.cause,
            gate=(
                UNGATED
                if gate_position is None
                else TemporalGate(
                    start_attribute=facts.shape.transaction_time.start_attribute,
                    observed_start=values[gate_position],
                )
            ),
        )
        disposal = code & _DISPOSAL
        if disposal == _CLOSE:
            return closing
        if disposal == _REMOVE:
            return PlannedTemporalRemoval(
                entity=closing.entity,
                target=closing.target,
                concurrency=closing.concurrency,
                affected_rows=closing.affected_rows,
            )
        assert predecessor is not None  # a revision reads its predecessor's cells
        piece = self._successor(_kept_position(code), values, predecessor)
        assignments = _revision_assignments(facts, piece.entries[0], predecessor)
        assert assignments is not None  # settled as a revision that assigns
        return PlannedTemporalRevision(
            entity=closing.entity,
            target=closing.target,
            assignments=assignments,
            concurrency=closing.concurrency,
            affected_rows=closing.affected_rows,
        )

    def _successor(
        self, position: int, values: tuple[object, ...], predecessor: PredecessorRow
    ) -> PlannedInsert:
        start, end = self._extent(position, values)
        if position != WITHIN:
            return _successor_insert(self.facts, predecessor, start, end)
        change = self.change
        return _successor_insert(
            self.facts,
            predecessor,
            start,
            end,
            self.assigned_attributes,
            self.assigned_value_objects,
            effective=None if change is None else change.effective_positions(values),
        )

    def _extent(self, position: int, values: tuple[object, ...]) -> tuple[object, object]:
        valid = self.valid_positions
        if valid is None:
            return None, None
        return self.transform.successor_extent(position, values[valid[0]], values[valid[1]])

    def _valid_end(self, values: tuple[object, ...]) -> object | None:
        valid = self.valid_positions
        return None if valid is None else values[valid[1]]

    def _endpoint(self, key: object, valid_end: object | None) -> OwnedEndpoint:
        return OwnedEndpoint(
            self.facts.entity.identity,
            (key,),
            TRANSACTION_TIME_ENDS if valid_end is None else bitemporal_ends(valid_end),
        )


@dataclass(frozen=True, slots=True)
class _GroupChanges:
    group: SettledGroup
    evidence: PredecessorRows

    def __iter__(self) -> Iterator[ObservedStateKey]:
        return self.group.changed_states(self.evidence)


@dataclass(frozen=True, slots=True)
class _GroupRemovals:
    group: SettledGroup
    evidence: PredecessorRows

    def __iter__(self) -> Iterator[OwnedEndpoint]:
        return self.group.removals(self.evidence)


@dataclass(frozen=True, slots=True)
class _GroupOpenings:
    """The rows a group opens from the selected rows an admitted insertion
    opened when ``continued``, and from every other selected row when not."""

    group: SettledGroup
    evidence: PredecessorRows
    continued: bool

    def __iter__(self) -> Iterator[OwnedEndpoint]:
        return self.group.openings(self.evidence, continued=self.continued)


type _Dispositions = tuple[int, array[int] | None, array[int] | None, int]


@dataclass(frozen=True, slots=True)
class _RowDisposal:
    """What deciding a group's row dispositions reads, held only while the
    group settles: the attempt's live ``ownership`` among it."""

    facts: TemporalFacts
    transform: CoverageTransform
    ownership: Ownership
    owning: bool
    key_position: int
    valid_positions: tuple[int, int] | None
    absent: object
    attributes: Mapping[AttributeIdentity, PlannedValue]
    value_objects: Mapping[ValueObjectIdentity, object]
    change: PreparedEffectiveChange | None

    def settle(
        self, evidence: PredecessorRows
    ) -> tuple[int, array[int] | None, array[int] | None, int]:
        """Every row's disposition, as one ``uniform`` code where all rows
        share it, else dense dispositions and the offsets their steps start at;
        and the total step count. An unowned Transaction-Time-Only group reads
        no row."""
        if not self.owning and self.valid_positions is None:
            code = self.transform.successor_positions(None, None)
            assert code is not None  # one segment spans the whole axis
            return code, None, None, len(evidence) * _row_steps(code)
        first = _CLOSE
        dispositions: array[int] | None = None
        for index, values in enumerate(evidence.rows):
            code = self._disposition(values)
            if index == 0:
                first = code
            elif dispositions is not None:
                dispositions.append(code)
            elif code != first:
                dispositions = array("H", (first,)) * index
                dispositions.append(code)
        if dispositions is None:
            return first, None, None, len(evidence) * _row_steps(first)
        offsets = array("q")
        length = 0
        for code in dispositions:
            offsets.append(length)
            length += _row_steps(code)
        return _CLOSE, dispositions, offsets, length

    def _disposition(self, values: tuple[object, ...]) -> int:
        valid = self.valid_positions
        start = end = None
        if valid is not None:
            start, end = values[valid[0]], values[valid[1]]
            _require_valid_time(self.facts, start, end)
        positions = self.transform.successor_positions(start, end)
        if positions is None:
            return _UNREACHED
        if not self.owning:
            return positions
        facts = self.facts
        own = OwnedEndpoint(
            facts.entity.identity,
            (values[self.key_position],),
            TRANSACTION_TIME_ENDS if valid is None else bitemporal_ends(end),
        )
        ownership = self.ownership
        if not ownership.owns(own):
            return positions
        code = positions | (_CONTINUES if ownership.continues_insertion(own) else 0)
        kept = self._kept(positions, start, end)
        if kept is None:
            return code | _REMOVE
        revises = self._revises(values, kept, start, end)
        return code | (_REVISE if revises else _KEEP) | kept << _KEPT_SHIFT

    def _kept(self, positions: int, start: object, end: object) -> int | None:
        """The position whose successor keeps the row's own address — the one
        ending where the row ends — if one does (:func:`_kept`)."""
        for position in _POSITIONS:
            if (
                positions & position
                and self.transform.successor_extent(position, start, end)[1] == end
            ):
                return position
        return None

    def _revises(self, values: tuple[object, ...], kept: int, start: object, end: object) -> bool:
        """Whether revising the row in place into its successor at ``kept``
        assigns anything, stopping at the first member that does
        (:func:`_revision_assignments`)."""
        if self.valid_positions is not None:
            kept_start, _kept_end = self.transform.successor_extent(kept, start, end)
            if kept_start != start:
                return True
        facts = self.facts
        selection = facts.view.member_selection
        change = self.change
        # Only the changed successor overlays anything; a carried one is the
        # row's own cells.
        return kept == WITHIN and any(
            not carries_cell(selection, values, self.absent, member, value)
            for member, value in _overlaid(
                facts,
                self.attributes,
                self.value_objects,
                None if change is None else change.effective_positions(values),
            )
        )


def _overlaid(
    facts: TemporalFacts,
    attributes: Mapping[AttributeIdentity, PlannedValue],
    value_objects: Mapping[ValueObjectIdentity, object],
    effective: Iterable[int] | None,
) -> Iterator[tuple[AttributeIdentity | ValueObjectIdentity, object]]:
    """Each member a changed successor overlays on its predecessor's own cells
    (:func:`_successor_insert`) that a revision of the predecessor could
    assign: none of the address or the temporal bounds stamping writes."""
    stamped = _addressed(facts)
    if isinstance(facts.shape, Bitemporal):
        stamped = stamped | {facts.shape.valid_time.start_attribute}
    if effective is None:
        for attribute, value in attributes.items():
            if attribute not in stamped:
                yield attribute, value
        yield from value_objects.items()
        return
    bindings = facts.view.member_selection.bindings
    for position in effective:
        binding = bindings[position]
        if not isinstance(binding, AttributeMetadata):
            yield binding.identity, value_objects[binding.identity]
        elif binding.identity not in stamped:
            yield binding.identity, attributes[binding.identity]


def _require_valid_time(facts: TemporalFacts, start: object, end: object) -> None:
    """Refuse a selected Bitemporal row whose Valid-Time cells are no interval,
    which no close can address."""
    if not isinstance(start, dt.datetime):
        raise WritePlanningError(
            f"bitemporal close on {facts.entity.identity.name!r}: no observed Valid-Time start "
            "supplied — a selected row's successors begin from it"
        )
    if end is not INFINITY and not isinstance(end, dt.datetime):
        raise WritePlanningError(
            f"bitemporal close on {facts.entity.identity.name!r}: no observed Valid-Time end "
            "supplied — a Bitemporal milestone address needs one exclusive upper bound "
            "per As-Of Axis (m-temporal-write 'Address and gate are separate')"
        )


def _reaches(window: TimeInterval | None, coverage: TimeInterval | None) -> bool:
    """Whether a caller's ``window`` overlaps ``coverage`` — the whole axis
    where it is ``None`` on a Transaction-Time-Only object."""
    if window is None:
        return True
    assert coverage is not None  # one object's windows and coverage share its shape
    return coverage.overlaps(window)


def _complete(successors: Sequence[Successor], coverage: TimeInterval) -> bool:
    """Whether ``successors``, in order, cover exactly ``coverage``, each
    meeting the next."""
    if not successors:
        return False
    first = successors[0].valid_time_coverage
    last = successors[-1].valid_time_coverage
    assert first is not None and last is not None  # Bitemporal successors lie on Valid Time
    if first.start != coverage.start or last.end != coverage.end:
        return False
    previous = first
    for successor in successors[1:]:
        extent = successor.valid_time_coverage
        assert extent is not None  # Bitemporal successors lie on Valid Time
        if not previous.meets(extent):
            return False
        previous = extent
    return True


def _preserved(
    facts: TemporalFacts, closing: PlannedClose, ownership: Ownership, *, guards: bool
) -> Expansion | None:
    """How a write that leaves ``closing``'s milestone as it was keeps it, or
    ``None`` where its unchanged state cannot be proven without changing it.
    A kept milestone is no change, even where a guard proves it.

    A row the attempt opened is invisible to every other transaction, and under
    Locking the shared lock the attempt holds on the row keeps it as it was
    read, so neither needs a statement. Under Optimistic a milestone that
    existed before the attempt is proven by a guard on its observed
    Transaction-Time start, which only a database whose write count includes
    unchanged rows (``guards``) can report.
    """
    concurrency = closing.concurrency
    if ownership.owns(_target_endpoint(facts, closing.target)) or isinstance(concurrency, Ungated):
        return _NOTHING
    if not guards:
        return None
    guard = PlannedTemporalGuard(
        entity=closing.entity,
        target=closing.target,
        concurrency=concurrency,
        affected_rows=closing.affected_rows,
    )
    return Expansion(steps=(guard,))


def _successor_insert(
    facts: TemporalFacts,
    predecessor: PredecessorRow,
    valid_start: object,
    valid_end: object,
    assigned_attributes: Mapping[AttributeIdentity, PlannedValue] | None = None,
    assigned_value_objects: Mapping[ValueObjectIdentity, object] | None = None,
    *,
    effective: Iterable[int] | None = None,
) -> PlannedInsert:
    """One successor of ``predecessor`` over ``[valid_start, valid_end)`` —
    ignored without Valid Time — as its own Planned Insert.

    A successor starts from its predecessor's own cells, so every member it does
    not change is the predecessor's cell object — the identity lowering patches
    by. Without assignments it is carried (:class:`CarriedFrom`); otherwise it
    is changed (:class:`ChangedFrom`) and overlays the assigned members at the
    ``effective`` selection positions, or every assigned member when
    ``effective`` is absent.
    """
    attributes, value_objects = predecessor.identity_maps(facts.view.member_selection)
    if assigned_attributes is None:
        origin: CarriedFrom | ChangedFrom = CarriedFrom(predecessor=predecessor)
    else:
        assert assigned_value_objects is not None  # a changed successor assigns both maps
        if effective is None:
            attributes.update(assigned_attributes)
            value_objects.update(assigned_value_objects)
        else:
            bindings = facts.view.member_selection.bindings
            for position in effective:
                binding = bindings[position]
                if isinstance(binding, AttributeMetadata):
                    attributes[binding.identity] = assigned_attributes[binding.identity]
                else:
                    value_objects[binding.identity] = assigned_value_objects[binding.identity]
        origin = ChangedFrom(predecessor=predecessor)
    _stamp(facts, attributes, valid_start, valid_end)
    entry = InsertEntry(row=adopt_planned_row(attributes, value_objects), origin=origin)
    return PlannedInsert(entity=facts.entity.identity, entries=(entry,))


def opening(
    facts: TemporalFacts,
    attributes: dict[AttributeIdentity, PlannedValue],
    value_objects: dict[ValueObjectIdentity, object],
    valid_time_window: TimeInterval | None,
) -> InsertEntry:
    """A new lineage's row: resolved authored ``attributes`` and
    ``value_objects``, which it adopts, over ``valid_time_window`` — ``None``
    without Valid Time — stamped as every opened row is."""
    if valid_time_window is None:
        _stamp(facts, attributes, None, None)
    else:
        _stamp(facts, attributes, valid_time_window.start, valid_time_window.end)
    return InsertEntry(row=adopt_planned_row(attributes, value_objects), origin=NEW_LINEAGE)


def _stamp(
    facts: TemporalFacts,
    attributes: dict[AttributeIdentity, object],
    valid_start: object,
    valid_end: object,
) -> None:
    """Write an opened row's temporal bounds. Every opened row carries the fresh
    Transaction-Time interval ``[instant, infinity)``: it is current when it is
    written, whatever Valid Time it covers."""
    shape = facts.shape
    if isinstance(shape, Bitemporal):
        valid_time = shape.valid_time
        attributes[valid_time.start_attribute] = valid_start
        attributes[valid_time.end_attribute] = valid_end
    transaction_time = shape.transaction_time
    attributes[transaction_time.start_attribute] = facts.instant
    attributes[transaction_time.end_attribute] = INFINITY


def _dispose(
    facts: TemporalFacts,
    closing: PlannedClose,
    successors: Sequence[PlannedInsert],
    predecessor: PredecessorRow,
    ownership: Ownership,
    state: ObservedStateKey | None,
    derived: tuple[Derivation, ...] = (),
) -> Expansion:
    """The effects one temporal mutation has on its observed predecessor, whose
    observed state is ``state``, and the successors it opens.

    Every successor is nonempty. A predecessor that existed before
    this attempt is closed, which preserves it as history. A predecessor this
    attempt opened has no history to preserve: when exactly one successor keeps
    its complete physical address — the logical key and every axis end — the
    row is revised in place at that address and the other successors are
    opened; otherwise the row is removed and every successor opened. Address
    equality is the whole correspondence: no end coordinate is moved to force
    reuse, and no payload comparison or Transaction-Time start decides it.

    Closing, revising, or removing the predecessor changes ``state``; a kept
    address the revision would assign nothing leaves it as it was.
    """
    changed = () if state is None else (state,)
    pieces = tuple(successors)
    own = _target_endpoint(facts, closing.target)
    if not ownership.owns(own):
        return Expansion(
            steps=(closing, *pieces),
            changed=changed,
            opened=Openings(fresh=openings(facts, pieces)),
            derived=derived,
        )
    continues = ownership.continues_insertion(own)
    kept_at = _kept(facts, own, pieces)
    if kept_at is not None:
        piece = pieces[kept_at]
        others = tuple(other for other in pieces if other is not piece)
        assignments = _revision_assignments(facts, piece.entries[0], predecessor)
        if assignments is None:
            return _owned(others, openings(facts, others), continues, (), derived)
        revision = PlannedTemporalRevision(
            entity=closing.entity,
            target=closing.target,
            assignments=assignments,
            concurrency=closing.concurrency,
            affected_rows=closing.affected_rows,
        )
        return _owned((revision, *others), openings(facts, others), continues, changed, derived)
    removal = PlannedTemporalRemoval(
        entity=closing.entity,
        target=closing.target,
        concurrency=closing.concurrency,
        affected_rows=closing.affected_rows,
    )
    return _owned(
        (removal, *pieces), openings(facts, pieces), continues, changed, derived, removed=own
    )


def _owned(
    steps: tuple[PlannedWrite, ...],
    opened: tuple[OwnedEndpoint, ...],
    continues: bool,
    changed: tuple[ObservedStateKey, ...],
    derived: tuple[Derivation, ...],
    removed: OwnedEndpoint | None = None,
) -> Expansion:
    """An owned predecessor's effects, its successors continuing the insertion
    that opened it when ``continues``."""
    return Expansion(
        steps=steps,
        changed=changed,
        opened=Openings(continued=opened) if continues else Openings(fresh=opened),
        removed=() if removed is None else (removed,),
        derived=derived,
    )


def _kept(facts: TemporalFacts, own: OwnedEndpoint, pieces: Sequence[PlannedInsert]) -> int | None:
    """The position of the one successor among ``pieces`` that keeps the owned
    address ``own``, or ``None`` unless exactly one does."""
    keeping = [
        position
        for position, piece in enumerate(pieces)
        if entry_endpoint(facts, piece.entries[0]) == own
    ]
    return keeping[0] if len(keeping) == 1 else None


def _revision_assignments(
    facts: TemporalFacts, entry: InsertEntry, predecessor: PredecessorRow
) -> PlannedAssignments | None:
    """What revising ``predecessor`` in place into ``entry``'s state assigns.

    Every member ``entry`` does not carry as the predecessor's own cell, plus a
    moved Valid-Time start. The key, every axis end, and the Transaction-Time
    start belong to the address the revision preserves. ``None`` when nothing
    differs.
    """
    shape = facts.shape
    addressed = _addressed(facts)
    valid_start = shape.valid_time.start_attribute if isinstance(shape, Bitemporal) else None
    attributes: dict[AttributeIdentity, PlannedValue] = {}
    for identity, value in entry.row.attributes.items():
        if identity in addressed:
            continue
        if identity == valid_start:
            if value != predecessor.cell(identity):
                attributes[identity] = value
        elif not predecessor.carries(identity, value):
            attributes[identity] = value
    value_objects = {
        identity: value
        for identity, value in entry.row.value_objects.items()
        if not predecessor.carries(identity, value)
    }
    if not attributes and not value_objects:
        return None
    return adopt_planned_assignments(attributes, value_objects)


def _addressed(facts: TemporalFacts) -> frozenset[AttributeIdentity]:
    """The members of a row's physical address a same-address revision keeps:
    the key, every axis end, and the Transaction-Time start."""
    shape = facts.shape
    transaction_time = shape.transaction_time
    address = (
        facts.view.primary_key.identity,
        transaction_time.start_attribute,
        transaction_time.end_attribute,
    )
    if isinstance(shape, Bitemporal):
        return frozenset((*address, shape.valid_time.end_attribute))
    return frozenset(address)


def openings(facts: TemporalFacts, inserts: Sequence[PlannedInsert]) -> tuple[OwnedEndpoint, ...]:
    """The owned address of every row ``inserts`` opens whose key is known."""
    endpoints: list[OwnedEndpoint] = []
    for insert in inserts:
        for entry in insert.entries:
            endpoint = entry_endpoint(facts, entry)
            if endpoint is not None:
                endpoints.append(endpoint)
    return tuple(endpoints)


def entry_endpoint(facts: TemporalFacts, entry: InsertEntry) -> OwnedEndpoint | None:
    attributes = entry.row.attributes
    value = attributes.get(facts.view.primary_key.identity)
    # A key the database allocates is named only once its insert answers it.
    if value is None or isinstance(value, MaxPlusOne):
        return None
    return OwnedEndpoint(facts.entity.identity, (value,), entry_ends(facts, attributes))


def entry_ends(
    facts: TemporalFacts, attributes: Mapping[AttributeIdentity, PlannedValue]
) -> tuple[TemporalUpperBound, ...]:
    shape = facts.shape
    if isinstance(shape, Bitemporal):
        return bitemporal_ends(attributes[shape.valid_time.end_attribute])
    return TRANSACTION_TIME_ENDS


def _target_endpoint(facts: TemporalFacts, target: MilestoneTarget) -> OwnedEndpoint:
    return OwnedEndpoint(facts.entity.identity, target.key_values, target.end_values)


def bitemporal_ends(valid_end: object) -> tuple[TemporalUpperBound, ...]:
    if valid_end is TemporalBound.INFINITY:
        return OPEN_BITEMPORAL_ENDS
    return (Finite(instant=valid_end), OPEN_UPPER_BOUND)


def _planned_close(
    facts: TemporalFacts,
    *,
    key_attributes: tuple[AttributeIdentity, ...],
    key_values: tuple[object, ...],
    observed_valid_end: object | None,
    cause: CloseCause,
    gate: TemporalConcurrency,
    on_shortfall: Shortfall | None = None,
) -> PlannedClose:
    """One settled close of the current milestone ``key_values`` addresses.

    Its assignments carry the Transaction-Time end alone — a close ends a
    milestone's currency and revises no represented value — and it expects
    exactly one row in every mode: a close reaching none would otherwise chain
    a duplicate or an orphaned current row, so the shortfall is an outcome
    rather than a silent success, classified by ``gate`` unless
    ``on_shortfall`` states it.
    """
    entity = facts.entity
    shape = facts.shape
    return PlannedClose(
        entity=entity.identity,
        target=MilestoneTarget(
            key_attributes=key_attributes,
            key_values=key_values,
            end_attributes=_end_attributes(shape),
            end_values=_end_values(shape, observed_valid_end),
        ),
        assignments=PlannedAssignments(
            attributes={shape.transaction_time.end_attribute: facts.instant}
        ),
        cause=cause,
        concurrency=gate,
        affected_rows=ExactCount(
            expected=1,
            on_shortfall=shortfall_for(gate) if on_shortfall is None else on_shortfall,
        ),
    )


def _end_attributes(shape: TransactionTimeOnly | Bitemporal) -> tuple[AttributeIdentity, ...]:
    """One exclusive-end Attribute per As-Of Axis, in canonical order."""
    match shape:
        case TransactionTimeOnly(transaction_time=transaction_time):
            return (transaction_time.end_attribute,)
        case Bitemporal(valid_time=valid_time, transaction_time=transaction_time):
            return (valid_time.end_attribute, transaction_time.end_attribute)


def _end_values(
    shape: TransactionTimeOnly | Bitemporal,
    observed_valid_end: object | None,
) -> tuple[TemporalUpperBound, ...]:
    """One exclusive upper bound per As-Of Axis, in canonical order.

    Transaction Time is invariantly `Infinity`, which is what keeps an
    operational close on a row still current. Valid Time is whatever the
    observed predecessor carries — `Infinity` for a rectangle running to the
    open bound, and a finite instant for a bounded one a prior split left
    behind, so binding a constant on both axes would silently miss every
    bounded sibling.
    """
    if isinstance(shape, TransactionTimeOnly):
        return TRANSACTION_TIME_ENDS
    assert observed_valid_end is not None  # every Bitemporal predecessor covers Valid Time
    return bitemporal_ends(observed_valid_end)
