from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable, Iterator, Sequence, Set
from dataclasses import dataclass
from operator import attrgetter
from typing import Final, cast

from parallax.core._execution._unit_work.acquisition import (
    CompletionRequest,
    CoverageReadRequest,
    CoverageTerm,
)
from parallax.core._execution._unit_work.effects import (
    CardinalityCorruptionError,
    MissingTargetError,
    WritePreconditionError,
)
from parallax.core._execution._unit_work.instructions import ExpectedTxStart
from parallax.core._execution._unit_work.retain import (
    ReadEvidence,
    RetainedObservation,
    RetainedTargetState,
)
from parallax.core._execution._unit_work.strategy import AuditDecoration
from parallax.core._execution._unit_work.write_items import (
    CoalescedTemporalWrite,
    InsertionKeyedWrite,
    ObservedKeyedWrite,
    PendingOpening,
    TargetKeyedWrite,
    TemporalKeyedWrite,
    singleton_transform,
)
from parallax.core.base import ManagedValue
from parallax.core.inheritance import InheritanceEntityView
from parallax.core.metamodel import AttributeIdentity, EntityMetadata, ValueObjectIdentity
from parallax.core.temporal_read import (
    Bitemporal,
    TimeInterval,
    TransactionTimeOnly,
    milestone_edge,
    valid_time_coverage,
)
from parallax.core.temporal_write.coverage import CoverageTransform
from parallax.core.temporal_write.expansion import (
    ExpansionRole,
    PredecessorExpander,
    TemporalFacts,
)
from parallax.core.write_plan.keys import ObjectKey, ObjectStateKey, TemporalObjectStateKey
from parallax.core.write_plan.observe import PredecessorRow, TemporalObservation
from parallax.core.write_plan.payload import WritePayloadPreparer
from parallax.core.write_plan.plan import (
    BoundRange,
    DeferredRange,
    TemporalWriteOwnership,
)
from parallax.core.write_plan.planned_rows import resolve_row
from parallax.core.write_plan.predecessor_rows import PredecessorRows
from parallax.core.write_plan.steps import KeyTarget, PlannedValue

__all__ = [
    "DeferredTemporalRange",
    "bind_range",
    "coverage_reads",
    "range_source_evidence",
    "retained_completion",
    "settle_opening",
    "settle_range",
]

_COVERAGE_TERMS: Final = 64
"""The most Valid-Time windows one coverage read names; more uncovered windows
are read by several reads, all before the range binds. Past this many, one
statement's cost grows faster than the round trip a larger statement saves."""


@dataclass(frozen=True, slots=True)
class _RangePredecessor:
    """One current row a range transforms: its complete state, the exact state
    it is, and the Valid Time it covers — ``None`` on a Transaction-Time-Only
    target."""

    predecessor: PredecessorRow
    state: ObjectStateKey
    valid_time_coverage: TimeInterval | None


@dataclass(frozen=True, slots=True)
class _ObservedSource:
    """The observation one contribution of a range was admitted through, and
    the Valid-Time pins its sources were read at — ``None`` for a read that
    named no finite one — which judge whether the attempt's completed writes
    left anything of the observed state for them."""

    observation: RetainedObservation
    pins: tuple[dt.datetime | None, ...]


def range_source_evidence(
    item: CoalescedTemporalWrite | TemporalKeyedWrite,
) -> tuple[ReadEvidence, ...]:
    """The distinct Read Evidence of every source whose write a range composes,
    by identity, in authored order."""
    if isinstance(item, ObservedKeyedWrite):
        return item.source_evidence
    if not isinstance(item, CoalescedTemporalWrite):
        return ()
    distinct: list[ReadEvidence] = []
    for contribution in item.contributions:
        for evidence in contribution.source_evidence:
            if all(evidence is not held for held in distinct):
                distinct.append(evidence)
    return tuple(distinct)


def _continues(ownership: TemporalWriteOwnership, source: _ObservedSource) -> bool:
    """Whether every source of ``source`` continues through what the
    attempt's completed writes left of its observed state: not where no
    completed write changed that state, nor where some source's pin lost it."""
    return all(ownership.continues(source.observation, pin) for pin in source.pins)


def _observed_source(
    observation: RetainedObservation, evidence: tuple[ReadEvidence, ...]
) -> _ObservedSource:
    return _ObservedSource(
        observation, tuple(_finite_valid_time(source) for source in evidence) or (None,)
    )


def _finite_valid_time(evidence: ReadEvidence) -> dt.datetime | None:
    pin = evidence.pin
    valid_time = None if pin is None else pin.valid_time
    return valid_time if isinstance(valid_time, dt.datetime) else None


def _known_predecessors(
    composed: CoalescedTemporalWrite,
    facts: TemporalFacts,
    key_attribute: AttributeIdentity,
    key_value: object,
    ownership: TemporalWriteOwnership,
) -> tuple[tuple[_RangePredecessor, ...], tuple[_RangePredecessor, ...]]:
    """The predecessors a composed range already knows, as the ones the
    transform binds — disjoint, ordered by start — beside the ones it only
    validates.

    Each distinct observed state the attempt's completed writes did not change
    is one predecessor, in authored order. A source whose observed state they
    changed brings no predecessor of its own: it continues through the current
    rows they produced and the attempt holds, which follow every observation.
    Two predecessors whose coverage overlaps cannot both describe current
    state, so the later one is bound and the earlier is validated alone: its
    guarded effect fails unless the database itself holds overlapping current
    coverage. The held rows come last and are bound without comparing them to
    each other, since one object's current rows never overlap.
    """
    distinct: list[_RangePredecessor] = []
    continuing = False
    for contribution in composed.contributions:
        retained = contribution.retained_observation
        if retained is None:  # an insertion or a caller authorized it, and it observed nothing
            continue
        if _continues(ownership, _observed_source(retained, contribution.source_evidence)):
            continuing = True
            continue
        observation = retained.evidence
        assert isinstance(observation, TemporalObservation)  # a temporal write observes a milestone
        predecessor = _predecessor(
            facts, key_attribute, key_value, observation.predecessor, retained.key
        )
        if all(predecessor.state != held.state for held in distinct):
            distinct.append(predecessor)
    bound = (
        _held(
            facts,
            key_attribute,
            key_value,
            ownership,
            composed.transform.valid_time_window,
            excluding={observed.state for observed in distinct},
        )
        if continuing
        else []
    )
    validated: list[_RangePredecessor] = []
    for predecessor in reversed(distinct):
        if any(_overlapping(predecessor, held) for held in bound):
            validated.append(predecessor)
        else:
            bound.append(predecessor)
    _order_by_start(bound)
    validated.reverse()
    return tuple(bound), tuple(validated)


def _held(
    facts: TemporalFacts,
    key_attribute: AttributeIdentity,
    key_value: object,
    ownership: TemporalWriteOwnership,
    window: TimeInterval | None,
    *,
    excluding: Set[ObjectStateKey] = frozenset(),
) -> list[_RangePredecessor]:
    """Every current row of the object over ``window`` the attempt's
    completed writes produced and hold, whichever source's continuation holds
    it, in Valid-Time order, except a state ``excluding`` names."""
    target = _object_key(facts, key_attribute, key_value)
    held = (
        _predecessor(facts, key_attribute, key_value, row, None)
        for row in ownership.current_rows(target, window)
    )
    return [predecessor for predecessor in held if predecessor.state not in excluding]


_START: Final = attrgetter("start")

_UNANCHORED: Final = object()
"""The anchor of a range no insertion authorized any write of."""

_EXISTENCE: Final = object()
"""The anchor of a Transaction-Time-Only range an insertion authorized a write
of: the current row itself, wherever it lies on an axis that has no Valid Time."""


def _anchor(composed: CoalescedTemporalWrite) -> object:
    """Where a composed range requires current coverage because an insertion
    authorized one of its writes: that insertion's own start, which every such
    write states as its window's start."""
    for contribution in composed.contributions:
        if contribution.observation is None and contribution.condition is None:
            return _anchored_at(contribution.valid_time_window)
    return _UNANCHORED


def _anchored_at(window: TimeInterval | None) -> object:
    return _EXISTENCE if window is None else window.start


@dataclass(frozen=True, slots=True)
class _TargetCondition:
    """A caller's literal condition on a composed range: the coverage at the
    start of the caller's prepared ``valid_time_window`` — the current row,
    where it is ``None`` on a Transaction-Time-Only object — stands at
    Transaction-Time start ``expected``. The window is also what the caller
    asked to revise whatever it reaches over."""

    valid_time_window: TimeInterval | None
    expected: dt.datetime


def _conditions(composed: CoalescedTemporalWrite) -> tuple[_TargetCondition, ...]:
    """The distinct target conditions the callers of a composed range's
    addressed writes state, in authored order: one per exact-window operation,
    where admission let in only writes that agree on it, and another for each
    operation over a disjoint window. Admission lets no two addressed windows
    share a start unless they are equal, so the distinct conditions keep every
    distinct addressed window."""
    conditions: list[_TargetCondition] = []
    for contribution in composed.contributions:
        condition = contribution.condition
        if condition is None:
            continue
        stated = _TargetCondition(contribution.valid_time_window, condition.instant)
        if stated not in conditions:
            conditions.append(stated)
    return tuple(conditions)


def _object_key(
    facts: TemporalFacts, key_attribute: AttributeIdentity, key_value: object
) -> ObjectKey:
    return ObjectKey(facts.entity.identity, ((key_attribute.name, key_value),))


def _predecessor(
    facts: TemporalFacts,
    key_attribute: AttributeIdentity,
    key_value: object,
    row: PredecessorRow,
    state: ObjectStateKey | None,
) -> _RangePredecessor:
    shape = facts.shape
    if state is None:
        state = TemporalObjectStateKey(
            _object_key(facts, key_attribute, key_value), milestone_edge(shape, row, None)
        )
    return _RangePredecessor(
        predecessor=row,
        state=state,
        valid_time_coverage=valid_time_coverage(shape, row, None),
    )


def _holds_start(window: TimeInterval | None, predecessor: _RangePredecessor) -> bool:
    """Whether ``predecessor`` holds ``window``'s start — the current row
    itself where ``window`` is ``None`` on a Transaction-Time-Only object."""
    if window is None:
        return True
    coverage = predecessor.valid_time_coverage
    assert coverage is not None  # one object's windows and coverage share its shape
    return coverage.contains(window.start)


def _overlapping(first: _RangePredecessor, second: _RangePredecessor) -> bool:
    first_coverage = first.valid_time_coverage
    second_coverage = second.valid_time_coverage
    return (
        first_coverage is None
        or second_coverage is None
        or first_coverage.overlaps(second_coverage)
    )


def _valid_time_coverages(predecessors: Iterable[_RangePredecessor]) -> Iterator[TimeInterval]:
    """The Valid Time each of a Bitemporal range's bound ``predecessors``
    covers, in the start order their owner already established."""
    for predecessor in predecessors:
        coverage = predecessor.valid_time_coverage
        assert coverage is not None  # only a Bitemporal range traverses coverage
        yield coverage


def _order_by_start(predecessors: list[_RangePredecessor]) -> None:
    """Order a range's predecessors by their Valid-Time starts. Those of a
    Transaction-Time-Only object have none to order by and stay as they are."""
    if predecessors and predecessors[0].valid_time_coverage is not None:
        predecessors.sort(key=_coverage_start)


def _coverage_start(predecessor: _RangePredecessor) -> dt.datetime:
    coverage = predecessor.valid_time_coverage
    assert coverage is not None  # only a Bitemporal range orders its predecessors
    return coverage.start


def _holds(predecessor: _RangePredecessor, anchor: object) -> bool:
    """Whether ``predecessor`` holds the insertion ``anchor`` of a Bitemporal
    range."""
    coverage = predecessor.valid_time_coverage
    assert coverage is not None and isinstance(anchor, dt.datetime)  # a Bitemporal anchor
    return coverage.contains(anchor)


def _physical(predecessor: _RangePredecessor) -> tuple[ObjectStateKey, object | None]:
    """The physical row ``predecessor`` is: its state, which names its start on
    each axis, and the Valid-Time end its coordinates hold."""
    return predecessor.state, _valid_end(predecessor)


def _expansions(
    starts: Sequence[_RangePredecessor],
    validations: Sequence[_RangePredecessor],
    predecessors: Sequence[_RangePredecessor],
) -> Iterator[tuple[PredecessorRow, ExpansionRole, ObjectStateKey, TimeInterval | None]]:
    """Each predecessor in the role it settles in, in the order its own effect
    runs: the starts, the validations, then every other predecessor."""
    for predecessor in starts:
        yield _expanded(predecessor, "starting")
    for predecessor in validations:
        yield _expanded(predecessor, "validation")
    for predecessor in predecessors:
        if not starts or all(predecessor is not start for start in starts):
            yield _expanded(predecessor, "coverage")


def _expanded(
    predecessor: _RangePredecessor, role: ExpansionRole
) -> tuple[PredecessorRow, ExpansionRole, ObjectStateKey, TimeInterval | None]:
    return predecessor.predecessor, role, predecessor.state, predecessor.valid_time_coverage


def _valid_end(predecessor: _RangePredecessor) -> object | None:
    """The Valid-Time end cell ``predecessor`` covers to, which its coordinates
    hold; ``None`` on a Transaction-Time-Only object."""
    coverage = predecessor.valid_time_coverage
    return None if coverage is None else coverage.end


@dataclass(frozen=True, slots=True)
class _OpeningSeed:
    """A pending insertion a range settles together with stored coverage: its
    resolved authored state and the Valid-Time window it opens, which no
    stored row is fabricated for."""

    state: tuple[dict[AttributeIdentity, PlannedValue], dict[ValueObjectIdentity, object]]
    window: TimeInterval


@dataclass(frozen=True, slots=True)
class _RangeMeaning:
    """What one range settled to before any coverage is bound: finalized data
    alone, holding no ownership, audit, clock, or other producer.

    ``facts.instant`` is the attempt's resolved instant. ``valid_time_window``
    is the final transform's enclosing window, derived once when settlement
    begins and shared by the coverage check, acquisition, and continuation;
    ``None`` on a Transaction-Time-Only object. ``opening`` is the pending
    insertion a replacement reaching past it settles with.
    """

    facts: TemporalFacts
    transform: CoverageTransform
    valid_time_window: TimeInterval | None
    gated: bool
    key_attribute: AttributeIdentity
    key_value: object
    anchor: object = _UNANCHORED
    conditions: tuple[_TargetCondition, ...] = ()
    guards: bool = False
    opening: _OpeningSeed | None = None

    @property
    def object_key(self) -> ObjectKey:
        return _object_key(self.facts, self.key_attribute, self.key_value)


@dataclass(frozen=True, slots=True)
class _TemporalRangeBinder:
    """One binding of a range's ``meaning`` to its coverage, reading the
    attempt's live ``ownership`` through the range's one predecessor
    ``expansion``, which finalizes every row it produces once. Exists only while
    it binds."""

    meaning: _RangeMeaning
    ownership: TemporalWriteOwnership
    expansion: PredecessorExpander

    def bind(
        self,
        predecessors: Sequence[_RangePredecessor],
        validations: Sequence[_RangePredecessor],
    ) -> BoundRange:
        """The steps the transform takes over ``predecessors``, after a guarded
        validation of each of ``validations``.

        Every predecessor's own effect — a validation, a close, a same-address
        revision, or a removal — runs before any successor opens, so a lost
        source condition fails before the range writes anything new. The
        object settles whole through the range's one
        :class:`PredecessorExpander`, so equal adjacent rows it produces merge
        while each predecessor keeps its own effect.

        A range one of whose writes an insertion authorized requires current
        coverage at that insertion's anchor and fails as a missing target
        without it: the anchor is where the authority starts, never shifted to
        coverage that survives elsewhere.

        A target write range requires the coverage at each of its
        operations' starts to stand at the Transaction-Time start that caller
        stated, literally, and fails as that caller's precondition otherwise —
        before anything executes where the coverage shows it, and at that
        predecessor's gate where only execution can. A start the attempt's own
        completed writes replaced stands at the attempt's own instant, so a
        condition stating the start they replaced fails. The predecessors the
        conditions start from are affected first, in the order the callers
        stated them, so a lost start fails ahead of every other predecessor's
        effect; one guard serves every start one predecessor holds. Validations
        follow, then the remaining predecessors, and a replacement's extent then
        opens its complete state over every gap the predecessors leave.

        A pending insertion the range settles with opens what the transform
        leaves of its own window as new lineages, ahead of the predecessors'
        successors, and its window is coverage no gap opening refills.
        """
        meaning = self.meaning
        self._require_anchor(predecessors)
        starts = self._starts(predecessors)
        transform = meaning.transform
        seed = meaning.opening
        gaps = (
            transform.gaps(_with_opening(_valid_time_coverages(predecessors), seed))
            if transform.replaces and isinstance(meaning.facts.shape, Bitemporal)
            else ()
        )
        return self.expansion.settle(
            _expansions(starts, validations, predecessors),
            lineage=None if seed is None else (seed.state, seed.window),
            gaps=gaps,
        )

    def _require_anchor(self, predecessors: Sequence[_RangePredecessor]) -> None:
        anchor = self.meaning.anchor
        if anchor is _UNANCHORED:
            return
        if any(anchor is _EXISTENCE or _holds(row, anchor) for row in predecessors):
            return
        raise MissingTargetError(self.meaning.facts.entity.identity, self._key_target(), 1, 0)

    def _key_target(self) -> KeyTarget:
        return KeyTarget(
            key_attributes=(self.meaning.key_attribute,), key_values=((self.meaning.key_value,),)
        )

    def _starts(self, predecessors: Sequence[_RangePredecessor]) -> tuple[_RangePredecessor, ...]:
        """The distinct predecessors the range's target operations
        start from, in the order their conditions were stated, once the
        coverage shows each stands at its caller's Transaction-Time start; the
        first that does not fails as that caller's precondition."""
        conditions = self.meaning.conditions
        if not conditions:
            return ()
        starts: list[_RangePredecessor] = []
        for condition in conditions:
            start = next(
                (row for row in predecessors if _holds_start(condition.valid_time_window, row)),
                None,
            )
            if start is None or self._tx_start(start) != condition.expected:
                raise self._failed(condition)
            if all(start is not held for held in starts):
                starts.append(start)
        return tuple(starts)

    def _tx_start(self, predecessor: _RangePredecessor) -> object:
        tx_start = self.meaning.facts.shape.transaction_time.start_attribute
        return predecessor.predecessor.cell(tx_start)

    def _failed(self, condition: _TargetCondition) -> WritePreconditionError:
        return WritePreconditionError(
            self.meaning.facts.entity.identity,
            {self.meaning.key_attribute.name: self.meaning.key_value},
            condition.expected,
        )

    def acquired(
        self,
        acquired: Sequence[_RangePredecessor],
        known: Sequence[_RangePredecessor],
    ) -> tuple[_RangePredecessor, ...]:
        """``known`` together with each current row of ``acquired`` — those the
        range reused and those it read — at coordinates none of them holds,
        ordered by start.

        A target operation's start names one current row, so more than
        one current row holding that start is Cardinality Corruption — an
        invariant failure that outranks the caller's precondition. Under Locking
        every known predecessor is held under the shared lock or was written by
        the attempt itself, so it is current beside the acquired rows and is
        counted with them; under Optimistic an observed predecessor may be
        stale, so only the acquired rows are current evidence and a stale one
        is left to its own gate.
        """
        ends = {_valid_end(predecessor) for predecessor in known}
        merged = [*known, *(row for row in acquired if _valid_end(row) not in ends)]
        self._require_one_start(acquired if self.meaning.gated else merged)
        _order_by_start(merged)
        return tuple(merged)

    def read(self, rows: Sequence[PredecessorRows]) -> list[_RangePredecessor]:
        """Every row of ``rows`` as a predecessor, each physical row once
        (:func:`_distinct`)."""
        return _distinct(
            [[self.predecessor(row) for row in _acquired_rows(acquired)] for acquired in rows]
        )

    def predecessor(self, row: PredecessorRow) -> _RangePredecessor:
        """One current row of the range's object as a predecessor."""
        meaning = self.meaning
        return _predecessor(meaning.facts, meaning.key_attribute, meaning.key_value, row, None)

    def _require_one_start(self, current: Sequence[_RangePredecessor]) -> None:
        for condition in self.meaning.conditions:
            starting = sum(1 for row in current if _holds_start(condition.valid_time_window, row))
            if starting > 1:
                raise CardinalityCorruptionError(
                    self.meaning.facts.entity.identity, self._key_target(), 1, starting
                )


@dataclass(frozen=True, slots=True)
class DeferredTemporalRange(DeferredRange):
    """A range whose requested window reaches coverage no planning input knew,
    as the finalized data :func:`bind_range` binds once its unit of work has
    read that coverage.

    It holds what settlement decided and nothing that could decide again: no
    ownership, audit, clock, or model. ``predecessors`` are the current rows
    planning knew — observed ones, and those the attempt's completed writes
    produced and hold for a source continuing through them. ``retained`` are
    the starting rows its callers' Locking admissions read whole, each reused
    only if it is still current when the range binds
    (:func:`retained_completion`); the coverage none of them holds is read then
    (:func:`coverage_reads`), and the rows read join the known predecessors at
    every coordinates those do not already hold. Binding then proceeds exactly
    as for a range bound at planning.
    """

    meaning: _RangeMeaning
    predecessors: tuple[_RangePredecessor, ...]
    validations: tuple[_RangePredecessor, ...]
    retained: tuple[RetainedTargetState, ...] = ()


def settle_range(
    item: CoalescedTemporalWrite | TemporalKeyedWrite,
    *,
    view: InheritanceEntityView,
    shape: TransactionTimeOnly | Bitemporal,
    gated: bool,
    instant: dt.datetime,
    ownership: TemporalWriteOwnership,
    audit: AuditDecoration,
    payloads: WritePayloadPreparer,
    guards: bool = False,
) -> BoundRange | DeferredTemporalRange:
    """One temporal object's pending writes as a range over its current
    coverage: bound now where planning knows that coverage, or else the
    deferred description of what binding needs once it is read.

    A lone write reaches here as the carrier it was buffered in, and its
    transform is built once, here, from that carrier; a composition brings the
    transform its buffering composed.

    Every distinct observed state the attempt's completed writes did not
    change is a predecessor: each is validated by its own guarded effect
    before any successor opens, and the transform is bound to the ones that do
    not overlap a later-authored observation of the same coverage. A source
    whose observed state those writes changed continues through the current
    rows they produced and the attempt holds, which join the predecessors
    without being read. Where the predecessors cover the whole requested
    window the range binds now; otherwise the coverage beyond them is read at
    execution and the range binds then. A write an insertion authorized
    observed nothing, so a range of such writes alone always reads its
    coverage, and requires coverage at the insertion's anchor once read. So
    does a target write, whose caller's condition requires the
    coverage at its start to stand at the Transaction-Time start it states;
    the starting row its Locking admission read whole travels with the range,
    which reuses it as coverage if it is still current at execution. A range
    bound now reuses none, and releases each such row here.

    ``instant`` is the attempt's already-resolved Transaction Instant, which a
    deferred range retains as a value.
    """
    key_attribute = view.primary_key.identity
    entity, key_value, transform = _range_of(item, key_attribute)
    facts = TemporalFacts(entity=entity, view=view, shape=shape, instant=instant)
    predecessors, validations, anchor, conditions, retained = _known(
        item, facts, key_attribute, key_value, ownership
    )
    window = transform.valid_time_window
    meaning = _RangeMeaning(
        facts=facts,
        transform=transform,
        valid_time_window=window,
        gated=gated,
        key_attribute=key_attribute,
        key_value=key_value,
        anchor=anchor,
        conditions=conditions,
        guards=guards,
    )
    if window is not None:
        reached = window.first_uncovered(_valid_time_coverages(predecessors)) is not None
    else:
        reached = not predecessors
    if reached:
        return DeferredTemporalRange(
            meaning=meaning, predecessors=predecessors, validations=validations, retained=retained
        )
    for state in retained:
        state.take()
    return _binding(meaning, ownership, audit, payloads).bind(predecessors, validations)


def settle_opening(
    opening: PendingOpening,
    *,
    view: InheritanceEntityView,
    shape: Bitemporal,
    gated: bool,
    instant: dt.datetime,
    ownership: TemporalWriteOwnership,
    audit: AuditDecoration,
    payloads: WritePayloadPreparer,
    guards: bool = False,
) -> BoundRange | DeferredTemporalRange:
    """A pending Bitemporal insertion and the writes its insertion authorized
    since, settled as one write: the insertion's authored state seeds every
    surviving part of its own window, with the composed assignments overlaid
    there, and no predecessor is fabricated for it.

    A replacement it authorized reaching past the insertion's window
    establishes its complete state there exactly as one reaching past a stored
    row does: the stored coverage beyond the window is read at execution, each
    row it reaches is transformed under its own condition, and the
    replacement's gaps open. An amendment or a destruction reaches past the
    window only as far as such a replacement does, and transforms what it
    reaches there too. ``instant`` is the attempt's already-resolved
    Transaction Instant.
    """
    insert = opening.insert
    entity = insert.target
    window = insert.valid_time_window
    assert window is not None  # a Bitemporal opening states its window
    key_attribute = view.primary_key.identity
    facts = TemporalFacts(entity=entity, view=view, shape=shape, instant=instant)
    attributes, value_objects = resolve_row(entity, view, insert.rows[0], context="insert")
    key_value = attributes.get(key_attribute)
    transform = opening.transform
    if opening.beyond is None:
        return PredecessorExpander(
            facts,
            transform,
            key_attribute=key_attribute,
            gated=gated,
            ownership=ownership,
            audit=audit,
            payloads=payloads,
        ).settle((), lineage=((attributes, value_objects), window))
    meaning = _RangeMeaning(
        facts=facts,
        transform=transform,
        valid_time_window=transform.valid_time_window,
        gated=gated,
        key_attribute=key_attribute,
        key_value=key_value,
        guards=guards,
        opening=_OpeningSeed((attributes, value_objects), window),
    )
    return DeferredTemporalRange(meaning=meaning, predecessors=(), validations=())


def _with_opening(
    coverage: Iterator[TimeInterval], seed: _OpeningSeed | None
) -> Iterable[TimeInterval]:
    """``coverage`` with a pending insertion's window in its start order."""
    if seed is None:
        return coverage
    return sorted((seed.window, *coverage), key=_START)


def _range_of(
    item: CoalescedTemporalWrite | TemporalKeyedWrite, key_attribute: AttributeIdentity
) -> tuple[EntityMetadata, object, CoverageTransform]:
    """The object ``item`` writes, its key value, and its transform."""
    if isinstance(item, CoalescedTemporalWrite):
        return item.target, item.key[key_attribute.name], item.transform
    instruction = item.instruction
    return (
        instruction.target,
        instruction.rows[0][key_attribute.name],
        singleton_transform(item, key_attribute.name),
    )


def _retained(composed: CoalescedTemporalWrite) -> tuple[RetainedTargetState, ...]:
    return tuple(
        contribution.retained
        for contribution in composed.contributions
        if contribution.retained is not None
    )


def _known(
    item: CoalescedTemporalWrite | TemporalKeyedWrite,
    facts: TemporalFacts,
    key_attribute: AttributeIdentity,
    key_value: object,
    ownership: TemporalWriteOwnership,
) -> tuple[
    tuple[_RangePredecessor, ...],
    tuple[_RangePredecessor, ...],
    object,
    tuple[_TargetCondition, ...],
    tuple[RetainedTargetState, ...],
]:
    """What planning knows of ``item``'s range: the predecessors it binds and
    validates, its insertion anchor, its callers' target conditions, and the
    starting rows their admissions retained."""
    if isinstance(item, CoalescedTemporalWrite):
        predecessors, validations = _known_predecessors(
            item, facts, key_attribute, key_value, ownership
        )
        return predecessors, validations, _anchor(item), _conditions(item), _retained(item)
    window = item.instruction.valid_time_window
    if isinstance(item, InsertionKeyedWrite):
        return (), (), _anchored_at(window), (), ()
    if isinstance(item, TargetKeyedWrite):
        expectation = item.expectation
        conditions = (
            (_TargetCondition(window, expectation.instant),)
            if isinstance(expectation, ExpectedTxStart)
            else ()
        )
        retained = () if item.retained is None else (item.retained,)
        return (), (), _UNANCHORED, conditions, retained
    observed = item.retained_observation
    if _continues(ownership, _observed_source(observed, item.source_evidence)):
        current = _held(facts, key_attribute, key_value, ownership, window)
        return tuple(current), (), _UNANCHORED, (), ()
    observation = observed.evidence
    assert isinstance(observation, TemporalObservation)  # settlement refuses any other
    predecessor = _predecessor(
        facts, key_attribute, key_value, observation.predecessor, observed.key
    )
    return (predecessor,), (), _UNANCHORED, (), ()


def retained_completion(
    description: DeferredTemporalRange, current: Callable[[ObjectStateKey, int], bool]
) -> CompletionRequest | None:
    """The completion of every starting row ``description`` retained that is
    still ``current`` — no change the attempt completed since its read replaced
    it — and that no other predecessor of the range already is, or ``None``
    where none is reusable.

    Each retained row is taken from its state here, reused or not, so a stale
    one is discarded without being judged. A range gated by Optimistic proofs
    reuses none: a row's freshness within the attempt says nothing of changes
    outside it.
    """
    retained = description.retained
    if not retained:
        return None
    meaning = description.meaning
    held = {
        predecessor.state for predecessor in (*description.predecessors, *description.validations)
    }
    rows: list[tuple[object, ...]] = []
    documents: list[object | None] = []
    for state in retained:
        taken = state.take()
        if (
            taken is None
            or meaning.gated
            or state.state in held
            or not current(state.state, state.read_at)
        ):
            continue
        held.add(state.state)
        row, document = taken
        rows.append(row)
        documents.append(document)
    if not rows:
        return None
    return CompletionRequest(
        entity=meaning.facts.entity,
        key_attribute=meaning.key_attribute,
        rows=tuple(rows),
        documents=None if all(document is None for document in documents) else tuple(documents),
    )


def coverage_reads(
    description: DeferredTemporalRange, reused: PredecessorRows | None
) -> tuple[CoverageReadRequest, ...]:
    """The reads of the coverage ``description``'s window needs that nothing
    already holds: its known predecessors, among them the current rows the
    attempt's completed writes produced and hold for a continuing source, the
    ``reused`` starting rows, and a pending insertion's own window.

    What remains of a Bitemporal window is read as its sorted, disjoint parts,
    in reads naming a bounded number of them each; nothing is read where
    nothing remains. A Transaction-Time-Only object's one current row is read
    unless a reused, known, or held row already is it.
    """
    meaning = description.meaning
    known = description.predecessors
    window = meaning.valid_time_window
    if window is None:
        return () if known or reused is not None else (_coverage(meaning, ()),)
    covered = [predecessor.valid_time_coverage for predecessor in known]
    if reused is not None:
        shape = meaning.facts.shape
        covered.extend(valid_time_coverage(shape, reused, index) for index in range(len(reused)))
    seed = meaning.opening
    if seed is not None:
        covered.append(seed.window)
    missing = window.uncovered(
        sorted((interval for interval in covered if interval is not None), key=_START)
    )
    return tuple(
        coverage_requests(
            meaning.facts.entity,
            meaning.key_attribute,
            (CoverageTerm(cast("ManagedValue", meaning.key_value), missing),) if missing else (),
            locking=not meaning.gated,
        )
    )


def _coverage(meaning: _RangeMeaning, windows: tuple[TimeInterval, ...]) -> CoverageReadRequest:
    return CoverageReadRequest(
        entity=meaning.facts.entity,
        key_attribute=meaning.key_attribute,
        terms=(CoverageTerm(cast("ManagedValue", meaning.key_value), windows),),
        locking=not meaning.gated,
    )


def coverage_requests(
    entity: EntityMetadata,
    key_attribute: AttributeIdentity,
    terms: Iterable[CoverageTerm],
    *,
    locking: bool,
) -> Iterator[CoverageReadRequest]:
    """Reads of every Valid-Time window ``terms`` name, in order, each naming at
    most :data:`_COVERAGE_TERMS` key/window terms; an object whose windows do
    not fit what remains of one read continues in the next."""
    pending: list[CoverageTerm] = []
    room = _COVERAGE_TERMS
    for term in terms:
        windows = term.valid_time_windows
        first = 0
        while first < len(windows):
            if not room:
                yield CoverageReadRequest(entity, key_attribute, tuple(pending), locking)
                pending, room = [], _COVERAGE_TERMS
            part = windows[first : first + room]
            pending.append(
                term if len(part) == len(windows) else CoverageTerm(term.key_value, part)
            )
            first += len(part)
            room -= len(part)
    if pending:
        yield CoverageReadRequest(entity, key_attribute, tuple(pending), locking)


def bind_range(
    description: DeferredTemporalRange,
    reused: PredecessorRows | None,
    acquired: Sequence[PredecessorRows],
    *,
    ownership: TemporalWriteOwnership,
    audit: AuditDecoration,
    payloads: WritePayloadPreparer,
) -> BoundRange:
    """``description`` bound to the current rows its window holds — the
    starting rows it ``reused`` and the coverage ``acquired`` beside them —
    through the same binding a range known at planning takes, under the
    attempt's current ``ownership``, every produced row finalized and every
    emitted close decorated once."""
    binding = _binding(description.meaning, ownership, audit, payloads)
    current = binding.read(acquired if reused is None else (reused, *acquired))
    return binding.bind(
        binding.acquired(current, description.predecessors), description.validations
    )


def _binding(
    meaning: _RangeMeaning,
    ownership: TemporalWriteOwnership,
    audit: AuditDecoration,
    payloads: WritePayloadPreparer,
) -> _TemporalRangeBinder:
    return _TemporalRangeBinder(
        meaning,
        ownership,
        PredecessorExpander(
            meaning.facts,
            meaning.transform,
            key_attribute=meaning.key_attribute,
            key_value=meaning.key_value,
            gated=meaning.gated,
            guards=meaning.guards,
            ownership=ownership,
            audit=audit,
            payloads=payloads,
        ),
    )


def _distinct(reads: Sequence[list[_RangePredecessor]]) -> list[_RangePredecessor]:
    """Every predecessor of ``reads`` once per physical row: a row an earlier
    read already returned, at the same state and Valid-Time end, is not
    repeated, while every row one read returns stays, however it overlaps the
    others."""
    if len(reads) < 2:
        return reads[0] if reads else []
    predecessors: list[_RangePredecessor] = []
    earlier: set[tuple[ObjectStateKey, object | None]] = set()
    for read in reads:
        predecessors.extend(row for row in read if _physical(row) not in earlier)
        earlier.update(_physical(row) for row in read)
    return predecessors


def _acquired_rows(rows: PredecessorRows) -> Iterator[PredecessorRow]:
    for index in range(len(rows)):
        yield PredecessorRow.over_row(
            rows.selection, rows.rows[index], rows.document(index), rows.absent
        )
