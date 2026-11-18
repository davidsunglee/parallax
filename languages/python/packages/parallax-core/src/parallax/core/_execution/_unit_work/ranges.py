from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable, Iterator, Sequence, Set
from dataclasses import dataclass
from operator import attrgetter
from typing import Final, cast

from parallax.core._execution._unit_work.effects import (
    MISSING_TARGET,
    WritePreconditionError,
    cardinality_corruption,
    shortfall,
)
from parallax.core._execution._unit_work.evidence import ReadEvidence, RetainedObservation
from parallax.core._execution._unit_work.row_acquisition import (
    CompletionRequest,
    CoverageReadKey,
    CoverageTerm,
    RetainedStartingRow,
)
from parallax.core._execution._unit_work.strategy import AuditDecoration
from parallax.core._execution._unit_work.write_items import (
    ComposedBitemporalOpening,
    InsertionAuthorized,
    StateObserved,
    TemporalCoverageAuthority,
    TemporalCoverageWrite,
    TemporalIntent,
    TxStartConditioned,
    is_licensed_by,
)
from parallax.core.internal.base import ManagedValue
from parallax.core.internal.metamodel import AttributeIdentity
from parallax.core.internal.planned_step.keys import (
    ObjectKey,
    ObjectStateKey,
    TemporalObjectStateKey,
)
from parallax.core.internal.planned_step.managed_row import ManagedRow
from parallax.core.internal.planned_step.observe import PredecessorRow, TemporalObservation
from parallax.core.internal.planned_step.payload import WritePayloadPreparer
from parallax.core.internal.planned_step.predecessor_rows import PredecessorRows
from parallax.core.internal.planned_step.steps import KeyTarget
from parallax.core.internal.planned_step.write_effects import BoundRange, TemporalWriteOwnership
from parallax.core.internal.temporal_read import (
    Bitemporal,
    Edge,
    TimeInterval,
    TransactionTimeOnly,
    milestone_edge,
    valid_time_coverage,
)
from parallax.core.internal.temporal_write.coverage import CoverageTransform
from parallax.core.internal.temporal_write.expansion import (
    ExpansionRole,
    PredecessorExpander,
    TemporalFacts,
)

__all__ = [
    "DeferredRange",
    "settle_opening",
    "settle_range",
]


@dataclass(frozen=True, slots=True)
class _RangePredecessor:
    """One current milestone a range transforms: the exact state it is, its
    complete stored ``row`` — ``None`` where only the milestone a caller stated
    is known (:func:`_stated_predecessor`) — and the Valid Time it covers,
    ``None`` on a Transaction-Time-Only target."""

    row: PredecessorRow | None
    state: TemporalObjectStateKey
    valid_time_coverage: TimeInterval | None


@dataclass(frozen=True, slots=True)
class _ObservedSource:
    """The observation one observed intent of a range was admitted through, and
    the Valid-Time pins its sources were read at — ``None`` for a read that
    named no finite one — which judge whether the attempt's completed writes
    left anything of the observed state for them."""

    observation: RetainedObservation
    pins: tuple[dt.datetime | None, ...]


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
    intents: tuple[TemporalIntent[TemporalCoverageAuthority], ...],
    window: TimeInterval | None,
    facts: TemporalFacts,
    target: ObjectKey,
    ownership: TemporalWriteOwnership,
) -> tuple[tuple[_RangePredecessor, ...], tuple[_RangePredecessor, ...]]:
    """The predecessors a range of ``intents`` over ``window`` already knows,
    as the ones its transform binds — disjoint, ordered by start — beside the
    ones it only validates.

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
    for intent in intents:
        authority = intent.authority
        if not isinstance(authority, StateObserved):
            continue
        retained = authority.retained_observation
        if _continues(ownership, _observed_source(retained, authority.source_evidence)):
            continuing = True
            continue
        observation = retained.evidence
        assert isinstance(observation, TemporalObservation)  # a temporal write observes a milestone
        predecessor = _predecessor(facts, target, observation.predecessor, retained.key)
        if all(predecessor.state != held.state for held in distinct):
            distinct.append(predecessor)
    bound = (
        _held(
            facts,
            target,
            ownership,
            window,
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
    target: ObjectKey,
    ownership: TemporalWriteOwnership,
    window: TimeInterval | None,
    *,
    excluding: Set[ObjectStateKey] = frozenset(),
) -> list[_RangePredecessor]:
    """Every current row of the object ``target`` over ``window`` the
    attempt's completed writes produced and hold, whichever source's
    continuation holds it, in Valid-Time order, except a state ``excluding``
    names."""
    held = (
        _predecessor(facts, target, row, None) for row in ownership.current_rows(target, window)
    )
    return [predecessor for predecessor in held if predecessor.state not in excluding]


_START: Final = attrgetter("start")


def _anchor(
    intents: tuple[TemporalIntent[TemporalCoverageAuthority], ...],
) -> TemporalIntent[InsertionAuthorized] | None:
    """The first write of a range an insertion authorized, whose window's start
    is where the range requires current coverage — every such write states
    that insertion's start — or ``None`` where no insertion authorized one."""
    for intent in intents:
        if is_licensed_by(intent, InsertionAuthorized):
            return intent
    return None


def _conditions(
    intents: tuple[TemporalIntent[TemporalCoverageAuthority], ...],
) -> tuple[TemporalIntent[TxStartConditioned], ...]:
    """The distinct target conditions the callers of a range's addressed
    writes state, in authored order, each as the first target intent
    stating it: the coverage at the start of its prepared window — the current
    row, where it is ``None`` on a Transaction-Time-Only object — stands at its
    expected Transaction-Time start, whether the write assigns or destroys.

    One condition serves each exact-window operation, where admission let in
    only writes that agree on it, and another each operation over a disjoint
    window. Admission lets no two addressed windows share a start unless they
    are equal, so the distinct conditions keep every distinct addressed window.
    """
    conditions: list[TemporalIntent[TxStartConditioned]] = []
    for intent in intents:
        if is_licensed_by(intent, TxStartConditioned) and all(
            not _states_condition(held, intent) for held in conditions
        ):
            conditions.append(intent)
    return tuple(conditions)


def _states_condition(
    held: TemporalIntent[TxStartConditioned], arriving: TemporalIntent[TxStartConditioned]
) -> bool:
    return (
        held.write_intent.valid_time_window == arriving.write_intent.valid_time_window
        and held.authority.expected == arriving.authority.expected
    )


def _object_key(
    facts: TemporalFacts, key_attribute: AttributeIdentity, key_value: ManagedValue
) -> ObjectKey:
    return ObjectKey(facts.entity.identity, ((key_attribute.name, key_value),))


def _predecessor(
    facts: TemporalFacts,
    target: ObjectKey,
    row: PredecessorRow,
    state: ObjectStateKey | None,
) -> _RangePredecessor:
    shape = facts.shape
    if state is None:
        state = TemporalObjectStateKey(target, milestone_edge(shape, row, None))
    assert isinstance(state, TemporalObjectStateKey)  # a temporal row is a milestone
    return _RangePredecessor(
        row=row, state=state, valid_time_coverage=valid_time_coverage(shape, row, None)
    )


def _binds_from_stated_start(meaning: _RangeMeaning) -> bool:
    """Whether ``meaning`` needs no cell of the milestone it starts from but its
    key and Transaction-Time start, so it binds from the start its caller
    stated rather than from a read row (`m-temporal-write` *A target write*):
    under Optimistic, a Transaction-Time-Only target write assigning no
    successor cells, which no insertion authorized."""
    return (
        meaning.gated
        and isinstance(meaning.facts.shape, TransactionTimeOnly)
        and bool(meaning.conditions)
        and meaning.anchor is None
        and not meaning.transform.assigns
    )


def _stated_predecessor(meaning: _RangeMeaning) -> _RangePredecessor:
    """The current milestone ``meaning``'s one target condition names: its key
    at the Transaction-Time start its caller stated, with no stored row."""
    (condition,) = meaning.conditions
    return _RangePredecessor(
        row=None,
        state=TemporalObjectStateKey(
            meaning.object_key, Edge(tx_time=condition.authority.expected.instant)
        ),
        valid_time_coverage=None,
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


def _physical(predecessor: _RangePredecessor) -> tuple[ObjectStateKey, object | None]:
    """The physical row ``predecessor`` is: its state, which names its start on
    each axis, and the Valid-Time end its coordinates hold."""
    return predecessor.state, _valid_end(predecessor)


def _expansions(
    starts: Sequence[_RangePredecessor],
    validations: Sequence[_RangePredecessor],
    predecessors: Sequence[_RangePredecessor],
) -> Iterator[
    tuple[PredecessorRow | None, ExpansionRole, TemporalObjectStateKey, TimeInterval | None]
]:
    """Each predecessor in the role it settles in, in the order its kind of
    effect runs: the starts, the validations, then every other predecessor."""
    for predecessor in starts:
        yield _expanded(predecessor, "starting")
    for predecessor in validations:
        yield _expanded(predecessor, "validation")
    for predecessor in predecessors:
        if not starts or all(predecessor is not start for start in starts):
            yield _expanded(predecessor, "coverage")


def _expanded(
    predecessor: _RangePredecessor, role: ExpansionRole
) -> tuple[PredecessorRow | None, ExpansionRole, TemporalObjectStateKey, TimeInterval | None]:
    return predecessor.row, role, predecessor.state, predecessor.valid_time_coverage


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

    state: ManagedRow
    window: TimeInterval


@dataclass(frozen=True, slots=True)
class _RangeMeaning:
    """What one range settled to before any coverage is bound: finalized data
    alone, holding no ownership, audit, clock, or other producer.

    ``facts.instant`` is the attempt's resolved instant. ``valid_time_window``
    is the final transform's enclosing window, derived once when settlement
    begins and shared by the coverage check, acquisition, and continuation;
    ``None`` on a Transaction-Time-Only object. ``read_key`` is the read its
    coverage is read by, one instance per Entity and lock decision of the
    finalization that settled it. ``opening`` is the pending insertion a
    replacement reaching past it settles with.
    """

    facts: TemporalFacts
    transform: CoverageTransform
    valid_time_window: TimeInterval | None
    read_key: CoverageReadKey
    key_value: ManagedValue
    anchor: TemporalIntent[InsertionAuthorized] | None = None
    conditions: tuple[TemporalIntent[TxStartConditioned], ...] = ()
    guards: bool = False
    opening: _OpeningSeed | None = None

    @property
    def object_key(self) -> ObjectKey:
        return _object_key(self.facts, self.key_attribute, self.key_value)

    @property
    def key_attribute(self) -> AttributeIdentity:
        return self.read_key.key_attribute

    @property
    def gated(self) -> bool:
        """Whether the range's writes gate on Optimistic proofs: the other half
        of the settled decision whether its coverage reads take the shared row
        lock."""
        return not self.read_key.shared_lock


@dataclass(frozen=True, slots=True)
class _TemporalRangeBinder:
    """One binding of a range's ``meaning`` to its coverage, reading the
    attempt's live ``ownership`` through the range's one predecessor
    ``expansion``, which finalizes every row it produces once. Every current
    row it reads is a milestone of its one ``object_key``. Exists only while it
    binds."""

    meaning: _RangeMeaning
    ownership: TemporalWriteOwnership
    expansion: PredecessorExpander
    object_key: ObjectKey

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
        stated them; one guard serves every start one predecessor holds.
        Validations follow, then the remaining predecessors, and a
        replacement's extent then opens its complete state over every gap the
        predecessors leave. Within that order every close, guard, and removal
        runs before any revision of a row the attempt opened, so a lost start
        fails ahead of every other predecessor's effect unless a revision holds
        it, which fails after every close, guard, and removal of the range.

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
        if anchor is None:
            return
        window = anchor.write_intent.valid_time_window
        if any(_holds_start(window, row) for row in predecessors):
            return
        raise shortfall(
            MISSING_TARGET, self.meaning.facts.entity.identity, self._key_target(), 1, 0
        )

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
            window = condition.write_intent.valid_time_window
            start = next((row for row in predecessors if _holds_start(window, row)), None)
            if (
                start is None
                or start.state.milestone.tx_time != condition.authority.expected.instant
            ):
                raise self._failed(condition)
            if all(start is not held for held in starts):
                starts.append(start)
        return tuple(starts)

    def _failed(self, condition: TemporalIntent[TxStartConditioned]) -> WritePreconditionError:
        return WritePreconditionError(
            self.meaning.facts.entity.identity,
            {self.meaning.key_attribute.name: self.meaning.key_value},
            condition.authority.expected.instant,
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
        return _predecessor(self.meaning.facts, self.object_key, row, None)

    def _require_one_start(self, current: Sequence[_RangePredecessor]) -> None:
        for condition in self.meaning.conditions:
            window = condition.write_intent.valid_time_window
            starting = sum(1 for row in current if _holds_start(window, row))
            if starting > 1:
                raise cardinality_corruption(
                    self.meaning.facts.entity.identity, self._key_target(), 1, starting
                )


@dataclass(frozen=True, slots=True)
class DeferredRange:
    """A range whose requested window reaches coverage no planning input knew,
    as the finalized data it binds once its unit of work has read that
    coverage: a Write Plan's deferred write.

    It holds what settlement decided and nothing that could decide again: no
    ownership, audit, clock, or model. ``predecessors`` are the current rows
    planning knew — observed ones, and those the attempt's completed writes
    produced and hold for a source continuing through them. ``starting_rows``
    are the starting rows its callers' Locking admissions read whole, each reused
    only if it is still current when the range binds; the coverage none of
    them holds is read then, and the rows read join the known predecessors at
    every coordinates those do not already hold. Binding then proceeds exactly
    as for a range bound at planning.

    ``source_evidence`` holds, by identity, the Read Evidence of every source
    whose write it settled, so those sources stay published for as long as the
    plan holding it is reachable. Nothing interprets it.
    """

    meaning: _RangeMeaning
    predecessors: tuple[_RangePredecessor, ...]
    validations: tuple[_RangePredecessor, ...]
    starting_rows: tuple[RetainedStartingRow, ...] = ()
    source_evidence: tuple[ReadEvidence, ...] = ()

    @property
    def read_key(self) -> CoverageReadKey:
        """The read its coverage is read by."""
        return self.meaning.read_key

    @property
    def key_value(self) -> ManagedValue:
        """The value its object's key holds."""
        return self.meaning.key_value

    def take_starting_row_completion(
        self, current: Callable[[ObjectStateKey, int], bool]
    ) -> CompletionRequest | None:
        """The completion of every starting row the range retained that is
        still ``current`` — no change the attempt completed since its read
        replaced it — and that no other predecessor of the range already is,
        or ``None`` where none is reusable.

        Each starting row is taken from its retention here, reused or not, so a
        stale one is discarded without being judged. A range gated by
        Optimistic proofs reuses none: a row's freshness within the attempt
        says nothing of changes outside it.
        """
        starting_rows = self.starting_rows
        if not starting_rows:
            return None
        meaning = self.meaning
        held = {predecessor.state for predecessor in (*self.predecessors, *self.validations)}
        rows: list[tuple[object, ...]] = []
        documents: list[object | None] = []
        for state in starting_rows:
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
            documents=(
                None if all(document is None for document in documents) else tuple(documents)
            ),
        )

    def missing_term(self, reused: PredecessorRows | None) -> CoverageTerm | None:
        """The coverage the range's window needs that nothing already holds —
        its known predecessors, among them the current rows the attempt's
        completed writes produced and hold for a continuing source, the
        ``reused`` starting rows, and a pending insertion's own window — or
        ``None`` where nothing remains to read.

        What remains of a Bitemporal window is its sorted, disjoint parts. A
        Transaction-Time-Only object's one part is its current row, read unless
        a reused, known, or held row already is it.
        """
        meaning = self.meaning
        known = self.predecessors
        key_value = meaning.key_value
        window = meaning.valid_time_window
        if window is None:
            return None if known or reused is not None else CoverageTerm(key_value, None)
        covered = [predecessor.valid_time_coverage for predecessor in known]
        if reused is not None:
            shape = meaning.facts.shape
            covered.extend(
                valid_time_coverage(shape, reused, index) for index in range(len(reused))
            )
        seed = meaning.opening
        if seed is not None:
            covered.append(seed.window)
        missing = window.uncovered(
            sorted((interval for interval in covered if interval is not None), key=_START)
        )
        return CoverageTerm(key_value, missing) if missing else None

    def bind(
        self,
        rows: Sequence[PredecessorRows],
        *,
        ownership: TemporalWriteOwnership,
        audit: AuditDecoration,
        payloads: WritePayloadPreparer,
    ) -> BoundRange:
        """The range bound to the current rows its window holds — ``rows``,
        the starting rows it reused before the rows each coverage read
        returned — through the same binding a range known at planning takes,
        under the attempt's current ``ownership``, every produced row
        finalized and every emitted close decorated once."""
        binding = _binding(self.meaning, ownership, audit, payloads)
        current = binding.read(rows)
        return binding.bind(binding.acquired(current, self.predecessors), self.validations)


def settle_range(
    item: TemporalCoverageWrite,
    intents: tuple[TemporalIntent[TemporalCoverageAuthority], ...],
    *,
    facts: TemporalFacts,
    read_key: CoverageReadKey,
    ownership: TemporalWriteOwnership,
    audit: AuditDecoration,
    payloads: WritePayloadPreparer,
    guards: bool = False,
) -> BoundRange | DeferredRange:
    """One temporal object's pending writes as a range over its current
    coverage: bound now where planning knows that coverage, or else the
    deferred description of what binding needs once it is read.

    ``intents`` are the ones ``item`` answers, which its caller has already
    read. A composition brings them and the transform its admission composed;
    a write alone answers both from itself.

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
    which reuses it as coverage if it is still current at execution. A target
    write needing no cell of that row but its key and start binds now from the
    milestone its caller stated (:func:`_binds_from_stated_start`), its gate
    proving that start when it executes. A range bound now reuses none, and
    releases each such row here.

    ``facts`` are what ``item`` settles about its target, among them the
    attempt's already-resolved Transaction Instant, which a deferred range
    retains as a value. ``read_key`` names the read its coverage is read by
    and decides whether its writes gate.
    """
    target = item.object_key
    ((_, key_value),) = target.primary_key
    transform = item.transform
    window = transform.valid_time_window
    predecessors, validations = _known_predecessors(intents, window, facts, target, ownership)
    meaning = _RangeMeaning(
        facts=facts,
        transform=transform,
        valid_time_window=window,
        read_key=read_key,
        # A target write stating a null key is refused at its call; every
        # other write's key comes from a row read or inserted.
        key_value=cast("ManagedValue", key_value),
        anchor=_anchor(intents),
        conditions=_conditions(intents),
        guards=guards,
    )
    starting_rows = _starting_rows(intents)
    if not predecessors and _binds_from_stated_start(meaning):
        predecessors = (_stated_predecessor(meaning),)
    if window is not None:
        reached = window.first_uncovered(_valid_time_coverages(predecessors)) is not None
    else:
        reached = not predecessors
    if reached:
        return DeferredRange(
            meaning=meaning,
            predecessors=predecessors,
            validations=validations,
            starting_rows=starting_rows,
            source_evidence=item.source_evidence,
        )
    for state in starting_rows:
        state.take()
    return _binding(meaning, ownership, audit, payloads).bind(predecessors, validations)


def settle_opening(
    opening: ComposedBitemporalOpening,
    *,
    facts: TemporalFacts,
    read_key: CoverageReadKey,
    ownership: TemporalWriteOwnership,
    audit: AuditDecoration,
    payloads: WritePayloadPreparer,
    guards: bool = False,
) -> BoundRange | DeferredRange:
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
    reaches there too. ``facts`` are what the opening settles about its
    target, among them the attempt's already-resolved Transaction Instant.
    ``read_key`` names the read that coverage is read by and decides whether
    the closes beyond the window gate.
    """
    insert = opening.insert.instruction
    window = insert.valid_time_window
    assert window is not None  # a Bitemporal opening states its window
    key_attribute = read_key.key_attribute
    (seed,) = insert.rows
    transform = opening.transform
    if opening.beyond is None:
        return PredecessorExpander(
            facts,
            transform,
            key_attribute=key_attribute,
            gated=not read_key.shared_lock,
            ownership=ownership,
            audit=audit,
            payloads=payloads,
        ).settle((), lineage=(seed, window))
    meaning = _RangeMeaning(
        facts=facts,
        transform=transform,
        valid_time_window=transform.valid_time_window,
        read_key=read_key,
        # An insertion's key cell is never null.
        key_value=cast("ManagedValue", seed.cell(key_attribute)),
        guards=guards,
        opening=_OpeningSeed(seed, window),
    )
    return DeferredRange(
        meaning=meaning,
        predecessors=(),
        validations=(),
        source_evidence=opening.source_evidence,
    )


def _with_opening(
    coverage: Iterator[TimeInterval], seed: _OpeningSeed | None
) -> Iterable[TimeInterval]:
    """``coverage`` with a pending insertion's window in its start order."""
    if seed is None:
        return coverage
    return sorted((seed.window, *coverage), key=_START)


def _starting_rows(
    intents: tuple[TemporalIntent[TemporalCoverageAuthority], ...],
) -> tuple[RetainedStartingRow, ...]:
    """The starting row every target intent's Locking admission read whole,
    whichever condition it states, in authored order."""
    return tuple(
        intent.authority.starting_row
        for intent in intents
        if is_licensed_by(intent, TxStartConditioned) and intent.authority.starting_row is not None
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
        meaning.object_key,
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
