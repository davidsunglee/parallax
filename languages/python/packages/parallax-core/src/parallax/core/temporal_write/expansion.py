from __future__ import annotations

import bisect
import datetime as dt
import functools
from array import array
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from types import MappingProxyType
from typing import Final, Literal, Protocol, cast

from parallax.core.base import INFINITY, TemporalBound
from parallax.core.inheritance import InheritanceEntityView
from parallax.core.metamodel import (
    AttributeIdentity,
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
    CoverageGap,
    CoverageTransform,
    Successor,
)
from parallax.core.write_plan.keys import ObjectKey, ObservedStateKey, TemporalStateKey
from parallax.core.write_plan.materialized import PredecessorRows
from parallax.core.write_plan.observe import AssignedComparison, PredecessorRow
from parallax.core.write_plan.plan import (
    OPEN_BITEMPORAL_ENDS,
    TRANSACTION_TIME_ENDS,
    BoundRange,
    Derivation,
    Openings,
    OwnedEndpoint,
    TemporalWriteOwnership,
    UnitEffects,
)
from parallax.core.write_plan.planned_rows import (
    PreparedAssignment,
    WritePlanningError,
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
    ExecutedMembers,
    Finite,
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
    RowOrigin,
    Shortfall,
    TemporalConcurrency,
    TemporalGate,
    TemporalUpperBound,
    WriteRow,
    adopt_planned_assignments,
    adopt_planned_row,
    assignments_added,
    shortfall_for,
)
from parallax.core.write_plan.steps import INFINITY as OPEN_UPPER_BOUND

__all__ = [
    "ExpansionRole",
    "PredecessorExpander",
    "PredecessorUse",
    "RowAudit",
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

type _Overlay = tuple[
    Mapping[AttributeIdentity, PlannedValue], Mapping[ValueObjectIdentity, object]
]
"""Resolved assigned members a produced row overlays on its starting state."""


class RowAudit(Protocol):
    """How a temporal unit's audit finalizes each row it produces and stamps
    each close it emits, already bound to the attempt's actor and instant.

    ``neutral`` says every row and close passes through unchanged, so compact
    backing need build none merely to ask.
    """

    @property
    def neutral(self) -> bool: ...

    def finalize_row(self, write_row: WriteRow, /) -> WriteRow: ...

    def decorate_close(self, close: PlannedClose, /) -> PlannedClose: ...


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


_NOTHING: Final[BoundRange] = BoundRange(steps=())

type _Extent = tuple[object, object, bool]
"""One successor's Valid-Time start and end — ``None`` both without Valid
Time — and whether it executes the unit's assignments rather than carrying its
predecessor's state."""


class PredecessorExpander:
    """The per-object rules of one temporal unit: whether its transform reaches
    a predecessor, whether the predecessor is unchanged and how that is proven,
    how it is closed and gated, how the attempt's ownership disposes of it, and
    which successors it opens — and the new lineages the unit opens from no
    predecessor at all, a pending insertion's surviving parts and a
    replacement's gaps.

    Built once per unit — a range binding, a Materialized Write Group, or a
    pending insertion — from the unit's settled facts and the attempt's
    ownership as it stands then. ``key_value`` is a range's one object key; a
    group reads each row's own. ``gated`` and ``guards`` say whether its closes
    gate and whether the database can prove an unchanged milestone by a guard,
    and ``derives`` whether a later unit of the flush relies on what it derives.
    ``audit`` finalizes each row the unit produces, carried, changed, or new,
    once, and stamps each close it emits.

    Every predecessor, whichever representation holds it, is settled by one
    decision (:func:`_disposition`) and realized by one construction of its own
    step (:func:`_own_step`) and its successors (:func:`_represented`), so a
    range's predecessors and a group's rows differ only in where their cells and
    successors are read from. Each canonical assignment mapping is resolved,
    and its comparison with stored values prepared, once per expansion however
    many predecessors and gaps share it. Nothing returned retains the expansion
    or the ownership it read.
    """

    __slots__ = (
        "_audit",
        "_comparisons",
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
        derives: bool = False,
        ownership: TemporalWriteOwnership,
        audit: RowAudit,
    ) -> None:
        self._facts = facts
        self._transform = transform
        self._key_attributes = (key_attribute,)
        self._key_values = (key_value,)
        self._gated = gated
        self._guards = guards
        self._derives = derives
        self._ownership = ownership
        self._audit = audit
        self._resolved: tuple[
            tuple[Mapping[str, object], _ResolvedState, ExecutedMembers], ...
        ] = ()
        self._comparisons: tuple[tuple[Mapping[str, object], AssignedComparison], ...] = ()

    def expand(
        self,
        predecessor: PredecessorRow,
        *,
        role: ExpansionRole,
        state: ObservedStateKey,
        coverage: TimeInterval | None,
    ) -> BoundRange:
        """``predecessor`` — the current row whose observed state is ``state``
        and whose Valid Time is ``coverage`` (``None`` without Valid Time) —
        expanded in its ``role``.

        A transform that does not reach the predecessor leaves it alone. One
        it leaves exactly as it was is kept where that is proven, whether the
        unit's source observed it, an insertion authorized the write, or a
        caller's condition named it (:meth:`_unchanged`). Otherwise the
        predecessor is closed — Superseded where a successor assigns,
        Terminated otherwise — and its nonempty successors opened, or the
        attempt's own row is revised or removed instead. A ``starting``
        predecessor's gate, a guard keeping it included, fails as its caller's
        precondition. A ``validation`` predecessor is retired as Terminated
        through the same disposal, opening nothing. Only an emitted close is
        stamped by the unit's audit; a guard proving a kept milestone and the
        close a removal or revision addresses like are not.
        """
        facts = self._facts
        if role == "validation":
            closing = self.closing(predecessor, coverage, TERMINATED)
            successors: tuple[Successor, ...] = ()
            own = _target_endpoint(facts, closing.target)
            code = _disposition(
                unchanged=False,
                owned=self._ownership.owns(own),
                gated=self._gated,
                guards=self._guards,
                extents=(),
                start=None,
                end=_valid_end(coverage),
            )
            return self._realized(code, predecessor, state, coverage, closing, successors, own)
        transform = self._transform
        if not transform.reaches(coverage):
            return _NOTHING
        successors = transform.successors_of(coverage)
        cause = (
            SUPERSEDED
            if any(successor.assigned is not None for successor in successors)
            else TERMINATED
        )
        closing = self.closing(predecessor, coverage, cause, starting=role == "starting")
        own = _target_endpoint(facts, closing.target)
        owned = self._ownership.owns(own)
        gated, guards = self._gated, self._guards
        code = _disposition(
            unchanged=_provable(owned=owned, gated=gated, guards=guards)
            and self._unchanged(predecessor, coverage, successors),
            owned=owned,
            gated=gated,
            guards=guards,
            extents=tuple(_extent(successor) for successor in successors) if owned else (),
            start=None if coverage is None else coverage.start,
            end=_valid_end(coverage),
        )
        return self._realized(code, predecessor, state, coverage, closing, successors, own)

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

    def lineage(self, seed: _ResolvedState, window: TimeInterval) -> tuple[PlannedInsert, ...]:
        """A pending insertion's resolved ``seed`` state over its own ``window``
        as the rows the unit's transform leaves of it: each nonempty successor
        of that coverage, carrying the seed with its assignments overlaid, a new
        lineage like the insertion itself. Nothing outside ``window`` is opened."""
        entity = self._facts.entity.identity
        return tuple(
            PlannedInsert(
                entity=entity,
                entries=(
                    self._new_lineage(seed, successor.valid_time_coverage, successor.assigned),
                ),
            )
            for successor in self._transform.successors_of(window)
        )

    def gap(self, gap: CoverageGap) -> WriteRow:
        """The new lineage a replacement opens over ``gap``, at the range's
        own key."""
        return self._new_lineage(
            ({self._key_attributes[0]: self._key_values[0]}, {}),
            gap.valid_time_window,
            gap.assigned,
        )

    def settle_group(
        self, evidence: PredecessorRows, assignments: Sequence[PreparedAssignment]
    ) -> SettledGroup:
        """A Materialized Write Group's selected rows, every one a coverage
        predecessor of this expansion's one-segment transform, settled into
        the immutable backing its steps and effects are read from.

        ``assignments`` are the group's own, resolved here once for every row
        into the one executed assignment set every changed successor shares; a
        marker no opened row can express is refused before anything is
        settled. Selection already judged every selected row changed, so no row
        is judged unchanged again, and a surviving row executes every
        assignment, those restoring a stored value included, exactly as a keyed
        write does. Each row's disposition is the one decision :meth:`expand`
        takes — reach, close, revision or removal of a row the attempt opened,
        and the nonempty successors — read from the row's own cells without
        building any of its steps. An unowned Transaction-Time-Only group reads
        no row at all: every row takes the one disposition its mutation decides.

        A non-neutral audit finalizes every produced row and stamps every
        emitted close here, once, and the backing keeps only what it added
        (:attr:`SettledGroup.audited`), so enumerating the group's steps never
        audits again.
        """
        facts = self._facts
        attributes, value_objects = resolved_assignments(facts.entity, assignments, "insert")
        executed = _in_member_order(facts, (*attributes, *value_objects))
        selection = evidence.selection
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
            gated=self._gated,
            guards=self._guards,
            key_position=evidence.key_position,
            valid_positions=valid_positions,
        ).settle(evidence)
        group = SettledGroup(
            facts=facts,
            transform=transform,
            key_attributes=self._key_attributes,
            key_position=evidence.key_position,
            cause=SUPERSEDED if transform.assigns else TERMINATED,
            gate_position=(
                selection.position(shape.transaction_time.start_attribute) if self._gated else None
            ),
            valid_positions=valid_positions,
            assigned_attributes=MappingProxyType(attributes),
            assigned_value_objects=MappingProxyType(value_objects),
            executed=executed,
            uniform=uniform,
            dispositions=dispositions,
            offsets=offsets,
            length=length,
        )
        audit = self._audit
        if audit.neutral:
            return group
        return group.audited_by(audit, evidence)

    def _unchanged(
        self,
        predecessor: PredecessorRow,
        coverage: TimeInterval | None,
        successors: Sequence[Successor],
    ) -> bool:
        """Whether ``successors`` leave ``predecessor`` as it was: together they
        cover all of it, and each assigned member already holds its value there
        — an amendment's assignments and a replacement's complete writable state
        alike, compared by declared value."""
        if coverage is None:
            if len(successors) != 1:
                return False
        elif not _complete(successors, coverage):
            return False
        return all(
            successor.assigned is None or predecessor.holds(self._comparison(successor.assigned))
            for successor in successors
        )

    def _comparison(self, assigned: Mapping[str, object]) -> AssignedComparison:
        for mapping, comparison in self._comparisons:
            if mapping is assigned:
                return comparison
        comparison = AssignedComparison(self._facts.view.member_selection, assigned)
        self._comparisons += ((assigned, comparison),)
        return comparison

    def _resolution(self, assigned: Mapping[str, object]) -> tuple[_ResolvedState, ExecutedMembers]:
        for mapping, maps, executed in self._resolved:
            if mapping is assigned:
                return maps, executed
        facts = self._facts
        maps = resolve_row(facts.entity, facts.view, assigned, context="insert")
        executed = _in_member_order(facts, (*maps[0], *maps[1]))
        self._resolved += ((assigned, maps, executed),)
        return maps, executed

    def _realized(
        self,
        code: int,
        predecessor: PredecessorRow,
        state: ObservedStateKey,
        coverage: TimeInterval | None,
        closing: PlannedClose,
        successors: tuple[Successor, ...],
        own: OwnedEndpoint,
    ) -> BoundRange:
        """The predecessor's settled ``code`` as its steps — its own effect
        before the successors it opens — and their effects (`m-temporal-write`
        *Ownership disposal*). Only emitted rows are built, and the bindable
        document is prepared only where some successor is opened."""
        disposal = code & _DISPOSAL
        if disposal == _PRESERVE:
            return _NOTHING
        facts = self._facts
        if disposal == _GUARD:
            return BoundRange(steps=(_own_step(facts, code, closing, None, None),))
        kept = _kept_index(code)
        others = successors if kept is None else (*successors[:kept], *successors[kept + 1 :])
        inserts = self._opened(predecessor, others)
        effect: tuple[PlannedWrite, ...] = ()
        if disposal == _CLOSE:
            effect = (self._audit.decorate_close(closing),)
        elif disposal != _KEEP:
            kept_row = None if kept is None else self._candidate(predecessor, successors[kept])
            effect = (_own_step(facts, code, closing, kept_row, predecessor),)
        owned = disposal != _CLOSE
        opened = openings(facts, inserts)
        return BoundRange(
            steps=(*effect, *inserts),
            changed=(state,) if _changes(code) else (),
            removed=(own,) if disposal == _REMOVE else (),
            opened=(
                Openings(continued=opened)
                if owned and self._ownership.continues_insertion(own)
                else Openings(fresh=opened)
            ),
            derived=(
                (self._derivation(predecessor, state, coverage, own, owned, successors),)
                if self._derives
                else ()
            ),
        )

    def _successor(self, predecessor: PredecessorRow, successor: Successor) -> PlannedInsert:
        return PlannedInsert(
            entity=self._facts.entity.identity, entries=(self._candidate(predecessor, successor),)
        )

    def _candidate(self, predecessor: PredecessorRow, successor: Successor) -> WriteRow:
        """``successor`` of ``predecessor`` as the finalized row it produces."""
        coverage = successor.valid_time_coverage
        if coverage is None:
            start = end = None
        else:
            start, end = coverage.start, coverage.end
        assigned = successor.assigned
        if assigned is None:
            row = _successor_row(self._facts, predecessor, start, end)
        else:
            maps, executed = self._resolution(assigned)
            row = _successor_row(
                self._facts, predecessor, start, end, assigned=maps, executed=executed
            )
        return self._audit.finalize_row(row)

    def _new_lineage(
        self,
        seed: _ResolvedState,
        coverage: TimeInterval | None,
        assigned: Mapping[str, object] | None,
    ) -> WriteRow:
        """A new lineage over ``coverage`` carrying a fresh copy of ``seed``
        with ``assigned`` overlaid, finalized once."""
        start, end = (None, None) if coverage is None else (coverage.start, coverage.end)
        return self._audit.finalize_row(
            _represented(
                self._facts,
                dict(seed[0]),
                dict(seed[1]),
                start,
                end,
                NEW_LINEAGE,
                assigned=None if assigned is None else self._resolution(assigned)[0],
            )
        )

    def _opened(
        self, predecessor: PredecessorRow, successors: Sequence[Successor]
    ) -> tuple[PlannedInsert, ...]:
        """The successors opened as rows, sharing one bindable predecessor."""
        if not successors:
            return ()
        bindable = predecessor.with_bindable_document()
        return tuple(self._successor(bindable, successor) for successor in successors)

    def _derivation(
        self,
        predecessor: PredecessorRow,
        state: ObservedStateKey,
        coverage: TimeInterval | None,
        own: OwnedEndpoint,
        owned: bool,
        successors: Sequence[Successor],
    ) -> Derivation:
        """What a later unit needs of one predecessor's expansion: its state and
        coverage, its own address where the attempt owned it, and each
        nonempty row derived from it — at the predecessor's own key, since no
        successor assigns a key — with the coverage it opens."""
        facts = self._facts
        key = (predecessor.cell(facts.view.primary_key.identity),)
        return Derivation(
            original=state,
            valid_time_coverage=coverage,
            owned=own if owned else None,
            rows=tuple(
                (
                    OwnedEndpoint(
                        facts.entity.identity,
                        key,
                        TRANSACTION_TIME_ENDS if extent is None else bitemporal_ends(extent.end),
                    ),
                    extent,
                )
                for extent in (successor.valid_time_coverage for successor in successors)
            ),
        )


def _extent(successor: Successor) -> _Extent:
    coverage = successor.valid_time_coverage
    changed = successor.assigned is not None
    if coverage is None:
        return None, None, changed
    return coverage.start, coverage.end, changed


class PredecessorUse(Enum):
    """What materializing one group step needs of its row's predecessor:
    nothing, only its member cells, or its bindable document — for the last
    time where ``BINDABLE_LAST``, since no later step of the row needs it."""

    NONE = "none"
    MEMBERS = "members"
    BINDABLE = "bindable"
    BINDABLE_LAST = "bindable-last"


# One predecessor's settled disposition, packed into one small integer: the
# successor positions a group row keeps (coverage's bits; a range lists its
# successors instead), what becomes of the predecessor itself, which successor
# keeps an owned row's address, whether its successors continue an insertion,
# and whether the transform reaches it.
_POSITIONS: Final = (CARRIED_HEAD, WITHIN, CARRIED_TAIL)
_POSITION_BITS: Final = CARRIED_HEAD | WITHIN | CARRIED_TAIL
_CLOSE: Final = 0
_REMOVE: Final = 1 << 3
_REVISE: Final = 2 << 3
_KEEP: Final = 3 << 3
_GUARD: Final = 4 << 3
_PRESERVE: Final = 5 << 3
_DISPOSAL: Final = 7 << 3
_CONTINUES: Final = 1 << 6
_UNREACHED: Final = 1 << 7
_KEPT_SHIFT: Final = 8


def _provable(*, owned: bool, gated: bool, guards: bool) -> bool:
    """Whether a milestone left exactly as it was can be kept without changing
    it (`m-temporal-write` *Unchanged milestones*): the attempt's ownership
    proves a row it opened, the shared lock proves one under Locking, and under
    Optimistic only a guard can, which a database must count to give."""
    return owned or not gated or guards


def _disposition(
    *,
    unchanged: bool,
    owned: bool,
    gated: bool,
    guards: bool,
    extents: Sequence[_Extent],
    start: object,
    end: object,
) -> int:
    """What becomes of one reached predecessor covering ``[start, end)`` —
    ``None`` both without Valid Time — whose nonempty successors lie over
    ``extents``, read only where the attempt ``owned`` it.

    A predecessor judged ``unchanged`` is kept wherever that is provable
    (:func:`_provable`): by a guard on its own address under Optimistic, and
    with no statement at all where the attempt opened it or Locking holds it.
    Otherwise one the attempt did not open is closed and every successor
    opened. One it opened is revised in place into the one successor ending
    where it ends — its complete physical address — wherever that successor
    executes the unit's assignments or starts later, else left in place, and
    removed where no successor keeps its address."""
    if unchanged and _provable(owned=owned, gated=gated, guards=guards):
        return _PRESERVE if owned or not gated else _GUARD
    if not owned:
        return _CLOSE
    kept = _keeping((extent[1] for extent in extents), end)
    if kept is None:
        return _REMOVE
    kept_start, _kept_end, changed = extents[kept]
    disposal = _REVISE if changed or kept_start != start else _KEEP
    return disposal | kept << _KEPT_SHIFT


def _kept_index(code: int) -> int | None:
    """Which successor keeps an owned predecessor's address, in order."""
    disposal = code & _DISPOSAL
    if disposal in (_REVISE, _KEEP):
        return code >> _KEPT_SHIFT
    return None


def _changes(code: int) -> bool:
    """Whether the predecessor is closed, removed, or revised: the change to
    its observed state its unit publishes."""
    return not code & _UNREACHED and code & _DISPOSAL in (_CLOSE, _REMOVE, _REVISE)


def _own_step(
    facts: TemporalFacts,
    code: int,
    closing: PlannedClose,
    kept: WriteRow | None,
    predecessor: PredecessorRow | None,
) -> PlannedWrite:
    """The one step of its own a predecessor of disposition ``code`` takes,
    addressed as ``closing`` addresses it: that close — decorated already — a
    guard proving it unchanged, its removal, or its revision into ``kept``,
    the successor keeping its address."""
    disposal = code & _DISPOSAL
    if disposal == _CLOSE:
        return closing
    if disposal == _GUARD:
        concurrency = closing.concurrency
        assert isinstance(concurrency, TemporalGate)  # only a gating unit is proven by a guard
        return PlannedTemporalGuard(
            entity=closing.entity,
            target=closing.target,
            concurrency=concurrency,
            affected_rows=closing.affected_rows,
        )
    if disposal == _REMOVE:
        return PlannedTemporalRemoval(
            entity=closing.entity,
            target=closing.target,
            concurrency=closing.concurrency,
            affected_rows=closing.affected_rows,
        )
    assert disposal == _REVISE and kept is not None and predecessor is not None
    return PlannedTemporalRevision(
        entity=closing.entity,
        target=closing.target,
        assignments=_revision_assignments(facts, kept, predecessor),
        concurrency=closing.concurrency,
        affected_rows=closing.affected_rows,
    )


def _kept_position(code: int) -> int:
    """The group successor position keeping an owned row's address, or none."""
    kept = _kept_index(code)
    return 0 if kept is None else _positions(code & _POSITION_BITS)[kept]


def _opened(code: int) -> int:
    """The successor positions a group row opens: every one it keeps but the
    one an owned row keeps its address at."""
    return code & _POSITION_BITS & ~_kept_position(code)


def _owns_step(code: int) -> bool:
    """Whether the row takes a step of its own: a close, removal, revision, or
    guard."""
    return not code & _UNREACHED and code & _DISPOSAL not in (_KEEP, _PRESERVE)


_ROW_EFFECT: Final = 0
"""The slot of a row's own close, removal, revision, or guard among its
steps."""


@functools.cache
def _positions(positions: int) -> tuple[int, ...]:
    """The successor positions in the union ``positions``, in order by start.
    Decoded once per distinct union."""
    return tuple(position for position in _POSITIONS if positions & position)


@functools.cache
def _slots(code: int) -> tuple[int, ...]:
    """The steps a row of disposition ``code`` takes, in order: its own effect
    where it takes one, then each successor position it opens. Decoded once
    per distinct disposition."""
    successors = _positions(_opened(code))
    return (_ROW_EFFECT, *successors) if _owns_step(code) else successors


def _row_steps(code: int) -> int:
    return len(_slots(code))


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

    ``assigned_attributes`` and ``assigned_value_objects`` are the group's one
    assignment set, which every changed successor executes whole and states as
    ``executed``. ``audited`` holds, by row and step slot, only
    what a non-neutral audit added to that step's row or close when the group
    settled; a step it added nothing to, and every step under the neutral one,
    holds nothing.
    """

    facts: TemporalFacts
    transform: CoverageTransform
    key_attributes: tuple[AttributeIdentity, ...]
    key_position: int
    cause: CloseCause
    gate_position: int | None
    valid_positions: tuple[int, int] | None
    assigned_attributes: Mapping[AttributeIdentity, PlannedValue]
    assigned_value_objects: Mapping[ValueObjectIdentity, object]
    executed: ExecutedMembers
    uniform: int
    dispositions: array[int] | None
    offsets: array[int] | None
    length: int
    audited: Mapping[tuple[int, int], PlannedAssignments] = MappingProxyType({})

    def __len__(self) -> int:
        return self.length

    def locate(self, index: int) -> tuple[int, int, PredecessorUse]:
        """The row the group's ``index``-th step belongs to, the step's slot
        among the row's own — its own effect or a successor position — and
        what it needs of the row's predecessor."""
        offsets = self.offsets
        if offsets is None:
            code = self.uniform
            slots = _slots(code)
            row, place = divmod(index, len(slots))
        else:
            row = bisect.bisect_right(offsets, index) - 1
            place = index - offsets[row]
            code = self._code(row)
            slots = _slots(code)
        slot = slots[place]
        if slot == _ROW_EFFECT:
            use = PredecessorUse.MEMBERS if code & _DISPOSAL == _REVISE else PredecessorUse.NONE
        elif place == len(slots) - 1:
            use = PredecessorUse.BINDABLE_LAST
        else:
            use = PredecessorUse.BINDABLE
        return row, slot, use

    def step(
        self,
        row: int,
        slot: int,
        values: tuple[object, ...],
        predecessor: PredecessorRow | None,
    ) -> PlannedWrite:
        """The step at ``slot`` of ``row`` (:meth:`locate`), built from the
        row's member ``values`` and the ``predecessor`` its use asks for."""
        if slot == _ROW_EFFECT:
            return self._effect(row, self._code(row), values, predecessor)
        assert predecessor is not None  # every successor reads its predecessor
        return PlannedInsert(
            entity=self.facts.entity.identity,
            entries=(self._candidate(row, slot, values, predecessor),),
        )

    def audited_by(self, audit: RowAudit, evidence: PredecessorRows) -> SettledGroup:
        """This group with what ``audit`` adds to each row it produces and each
        close it emits, finalized once per step now rather than when a step is
        built."""
        added: dict[tuple[int, int], PlannedAssignments] = {}
        for row, values in enumerate(evidence.rows):
            code = self._code(row)
            if code & _UNREACHED:
                continue
            disposal = code & _DISPOSAL
            if disposal == _CLOSE:
                close = cast("PlannedClose", self._effect(row, code, values, None))
                stamped = assignments_added(
                    close.assignments, audit.decorate_close(close).assignments
                )
                if stamped is not None:
                    added[row, _ROW_EFFECT] = stamped
            positions = _positions(_opened(code))
            if disposal == _REVISE:
                positions = (*positions, _kept_position(code))
            if not positions:
                continue
            predecessor = PredecessorRow.over_row(evidence.selection, values, None, evidence.absent)
            for position in positions:
                candidate = self._candidate(row, position, values, predecessor)
                stamped = _finalized_additions(candidate, audit.finalize_row(candidate))
                if stamped is not None:
                    added[row, position] = stamped
        return replace(self, audited=MappingProxyType(added)) if added else self

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
        key_position = evidence.key_position
        dispositions = self.dispositions
        if dispositions is None and not _changes(self.uniform):
            return
        for row, values in enumerate(evidence.rows):
            if dispositions is None or _changes(dispositions[row]):
                yield TemporalStateKey(
                    ObjectKey(entity, ((key_name, values[key_position]),)),
                    milestone_edge(facts.shape, evidence, row),
                )

    def removals(self, evidence: PredecessorRows) -> Iterator[OwnedEndpoint]:
        dispositions = self.dispositions
        if dispositions is None and self.uniform & _DISPOSAL != _REMOVE:
            return
        key_position = evidence.key_position
        for row, values in enumerate(evidence.rows):
            code = self.uniform if dispositions is None else dispositions[row]
            if code & _DISPOSAL == _REMOVE:
                yield self._endpoint(values[key_position], self._valid_end(values))

    def openings(self, evidence: PredecessorRows, *, continued: bool) -> Iterator[OwnedEndpoint]:
        dispositions = self.dispositions
        if dispositions is None and bool(self.uniform & _CONTINUES) is not continued:
            return
        key_position = evidence.key_position
        for row, values in enumerate(evidence.rows):
            code = self.uniform if dispositions is None else dispositions[row]
            if bool(code & _CONTINUES) is not continued:
                continue
            key = values[key_position]
            for slot in _slots(code):
                if slot != _ROW_EFFECT:
                    _start, end = self._extent(slot, values)
                    yield self._endpoint(key, end)

    def _code(self, row: int) -> int:
        dispositions = self.dispositions
        return self.uniform if dispositions is None else dispositions[row]

    def _effect(
        self,
        row: int,
        code: int,
        values: tuple[object, ...],
        predecessor: PredecessorRow | None,
    ) -> PlannedWrite:
        facts = self.facts
        gate_position = self.gate_position
        closing = _planned_close(
            facts,
            key_attributes=self.key_attributes,
            key_values=(values[self.key_position],),
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
            stamped = self.audited.get((row, _ROW_EFFECT))
            if stamped is not None:
                closing = replace(
                    closing,
                    assignments=adopt_planned_assignments(
                        {**closing.assignments.attributes, **stamped.attributes},
                        {**closing.assignments.value_objects, **stamped.value_objects},
                    ),
                )
        kept = None
        if disposal == _REVISE:
            assert predecessor is not None  # a revision reads its predecessor's cells
            kept = self._candidate(row, _kept_position(code), values, predecessor)
        return _own_step(facts, code, closing, kept, predecessor)

    def _candidate(
        self, row: int, position: int, values: tuple[object, ...], predecessor: PredecessorRow
    ) -> WriteRow:
        """The finalized row ``row``'s successor at ``position`` stores."""
        start, end = self._extent(position, values)
        candidate = (
            _successor_row(
                self.facts,
                predecessor,
                start,
                end,
                assigned=(self.assigned_attributes, self.assigned_value_objects),
                executed=self.executed,
            )
            if position == WITHIN
            else _successor_row(self.facts, predecessor, start, end)
        )
        stamped = self.audited.get((row, position))
        return candidate if stamped is None else _stamped(self.facts, candidate, stamped)

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
    ownership: TemporalWriteOwnership
    owning: bool
    gated: bool
    guards: bool
    key_position: int
    valid_positions: tuple[int, int] | None

    def settle(
        self, evidence: PredecessorRows
    ) -> tuple[int, array[int] | None, array[int] | None, int]:
        """Every row's disposition, as one ``uniform`` code where all rows
        share it, else dense dispositions and the offsets their steps start at;
        and the total step count. An unowned Transaction-Time-Only group reads
        no row."""
        if not self.owning and self.valid_positions is None:
            positions = self.transform.successor_positions(None, None)
            assert positions is not None  # one segment spans the whole axis
            code = positions | self._decided(owned=False, start=None, end=None, positions=0)
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
        owned = continues = False
        if self.owning:
            own = OwnedEndpoint(
                self.facts.entity.identity,
                (values[self.key_position],),
                TRANSACTION_TIME_ENDS if valid is None else bitemporal_ends(end),
            )
            ownership = self.ownership
            owned = ownership.owns(own)
            continues = owned and ownership.continues_insertion(own)
        code = positions | self._decided(owned=owned, start=start, end=end, positions=positions)
        return code | _CONTINUES if continues else code

    def _decided(self, *, owned: bool, start: object, end: object, positions: int) -> int:
        """The row's disposition by the one decision every predecessor takes,
        its successor ``positions`` read only where the attempt ``owned`` it."""
        transform = self.transform
        return _disposition(
            # Selection judged every selected row changed (`m-unit-work`
            # *Comparing an assigned member with its persisted value*).
            unchanged=False,
            owned=owned,
            gated=self.gated,
            guards=self.guards,
            extents=(
                tuple(
                    (*transform.successor_extent(position, start, end), position == WITHIN)
                    for position in _positions(positions)
                )
                if owned
                else ()
            ),
            start=start,
            end=end,
        )


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


def _successor_row(
    facts: TemporalFacts,
    predecessor: PredecessorRow,
    valid_start: object,
    valid_end: object,
    *,
    assigned: _Overlay | None = None,
    executed: ExecutedMembers = (),
) -> WriteRow:
    """One successor of ``predecessor`` over ``[valid_start, valid_end)`` —
    ignored without Valid Time — as the row it represents.

    A successor starts from its predecessor's own cells. A carried one keeps
    them all (:class:`CarriedFrom`); a changed one (:class:`ChangedFrom`)
    overlays every ``assigned`` member, whatever value the predecessor already
    holds there, and states them as its ``executed`` members.
    """
    attributes, value_objects = predecessor.identity_maps(facts.view.member_selection)
    return _represented(
        facts,
        attributes,
        value_objects,
        valid_start,
        valid_end,
        CarriedFrom(predecessor=predecessor)
        if assigned is None
        else ChangedFrom(predecessor=predecessor),
        assigned=assigned,
        executed=executed,
    )


def _represented(
    facts: TemporalFacts,
    attributes: dict[AttributeIdentity, PlannedValue],
    value_objects: dict[ValueObjectIdentity, object],
    valid_start: object,
    valid_end: object,
    origin: RowOrigin,
    *,
    assigned: _Overlay | None = None,
    executed: ExecutedMembers = (),
) -> WriteRow:
    """The row a unit produces over ``[valid_start, valid_end)`` from its
    starting ``attributes`` and ``value_objects``, which it adopts: a
    predecessor's cells or a new lineage's authored state, with ``assigned``
    overlaid and the row stamped as every opened row is."""
    if assigned is not None:
        attributes.update(assigned[0])
        value_objects.update(assigned[1])
    _stamp(facts, attributes, valid_start, valid_end)
    return WriteRow(
        row=adopt_planned_row(attributes, value_objects), origin=origin, executed=executed
    )


def _stamped(facts: TemporalFacts, write_row: WriteRow, stamped: PlannedAssignments) -> WriteRow:
    """``write_row`` with the values an audit added when its group settled,
    each an executed member of the row."""
    row = write_row.row
    return WriteRow(
        row=adopt_planned_row(
            {**row.attributes, **stamped.attributes},
            {**row.value_objects, **stamped.value_objects},
        ),
        origin=write_row.origin,
        executed=_in_member_order(
            facts,
            (
                *write_row.executed,
                *(member for member in stamped.members if member not in write_row.executed),
            ),
        ),
    )


def _in_member_order(
    facts: TemporalFacts, members: Iterable[AttributeIdentity | ValueObjectIdentity]
) -> ExecutedMembers:
    """``members`` in the Entity's member order, so one assignment set selects
    one sequence however it was authored."""
    return tuple(sorted(members, key=facts.view.member_selection.index.__getitem__))


def _finalized_additions(candidate: WriteRow, finalized: WriteRow) -> PlannedAssignments | None:
    """The executed values finalization added to ``candidate`` or replaced in
    it, or ``None`` where it did neither."""
    row = finalized.row
    before = candidate.row
    added = [
        member
        for member in finalized.executed
        if member not in candidate.executed
        or (
            row.attributes[member] is not before.attributes[member]
            if isinstance(member, AttributeIdentity)
            else row.value_objects[member] is not before.value_objects[member]
        )
    ]
    if not added:
        return None
    return adopt_planned_assignments(
        {
            member: row.attributes[member]
            for member in added
            if isinstance(member, AttributeIdentity)
        },
        {
            member: row.value_objects[member]
            for member in added
            if isinstance(member, ValueObjectIdentity)
        },
    )


def opening(
    facts: TemporalFacts,
    attributes: dict[AttributeIdentity, PlannedValue],
    value_objects: dict[ValueObjectIdentity, object],
    valid_time_window: TimeInterval | None,
) -> WriteRow:
    """A new lineage's row: resolved authored ``attributes`` and
    ``value_objects``, which it adopts, over ``valid_time_window`` — ``None``
    without Valid Time — stamped as every opened row is."""
    if valid_time_window is None:
        return _represented(facts, attributes, value_objects, None, None, NEW_LINEAGE)
    return _represented(
        facts,
        attributes,
        value_objects,
        valid_time_window.start,
        valid_time_window.end,
        NEW_LINEAGE,
    )


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


def _keeping(ends: Iterable[object], end: object) -> int | None:
    """Which of a row's successors, by the Valid-Time ``ends`` they reach in
    order, keeps the row's complete physical address: the one ending where the
    row ends, ``end`` — ``None`` throughout without Valid Time, where the one
    successor keeps it. Successors are disjoint and nonempty, so at most one
    does; ``None`` where none does. No successor assigns the key, and the
    Transaction-Time end is invariantly open."""
    for index, successor_end in enumerate(ends):
        if successor_end == end:
            return index
    return None


def _valid_end(coverage: TimeInterval | None) -> object:
    return None if coverage is None else coverage.end


def _revision_assignments(
    facts: TemporalFacts, write_row: WriteRow, predecessor: PredecessorRow
) -> PlannedAssignments:
    """What revising ``predecessor`` in place into ``write_row``'s state
    assigns, once :func:`_disposition` decided to revise it: the successor
    keeping its address executes assignments or starts later.

    Every member the row executes, plus a moved Valid-Time start. The key, every
    axis end, and the Transaction-Time start belong to the address the revision
    preserves.
    """
    shape = facts.shape
    addressed = _addressed(facts)
    row = write_row.row
    attributes: dict[AttributeIdentity, PlannedValue] = {}
    value_objects: dict[ValueObjectIdentity, object] = {}
    for member in write_row.executed:
        if isinstance(member, ValueObjectIdentity):
            value_objects[member] = row.value_objects[member]
        elif member not in addressed:
            attributes[member] = row.attributes[member]
    if isinstance(shape, Bitemporal):
        valid_start = shape.valid_time.start_attribute
        moved_to = row.attributes[valid_start]
        if moved_to != predecessor.cell(valid_start):
            attributes[valid_start] = moved_to
    assert attributes or value_objects  # payload construction never reverses the decision
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


def entry_endpoint(facts: TemporalFacts, entry: WriteRow) -> OwnedEndpoint | None:
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
