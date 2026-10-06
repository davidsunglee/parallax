from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Final, cast

from parallax.core.base import ManagedValue
from parallax.core.inheritance import InheritanceEntityView
from parallax.core.metamodel import AttributeIdentity
from parallax.core.temporal_read import (
    Bitemporal,
    TimeInterval,
    TransactionTimeOnly,
    milestone_edge,
    valid_time_coverage,
)
from parallax.core.temporal_write.coverage import CoverageTransform
from parallax.core.temporal_write.expansion import (
    Expansion,
    ExpansionRole,
    PredecessorExpansion,
    TemporalFacts,
    bitemporal_ends,
    entry_endpoint,
    opening,
)
from parallax.core.unit_work.clock import TransactionInstant
from parallax.core.unit_work.effects import (
    CardinalityCorruptionError,
    MissingTargetError,
    WritePreconditionError,
    enforce_affected_rows,
)
from parallax.core.unit_work.materialized import ChainedTemporalWrite, ComposedTemporalWrite
from parallax.core.unit_work.retain import RetainedObservation
from parallax.core.unit_work.strategy import ActorIdentity, AuditStrategy
from parallax.core.write_plan.keys import ObjectKey, ObservedStateKey, TemporalStateKey
from parallax.core.write_plan.materialized import PredecessorRows
from parallax.core.write_plan.observe import PredecessorRow, TemporalObservation
from parallax.core.write_plan.plan import (
    TRANSACTION_TIME_ENDS,
    BoundRange,
    Completion,
    Completions,
    Derivation,
    Descent,
    Openings,
    OwnedEndpoint,
    Ownership,
    RangeAcquisition,
)
from parallax.core.write_plan.steps import TERMINATED, KeyTarget, PlannedInsert
from parallax.core.write_plan.steps import PlannedWrite as PlannedStep

__all__ = [
    "Decoration",
    "DeferredTemporalRange",
    "bind_deferred",
    "range_claims",
    "settle_range",
]


@dataclass(frozen=True, slots=True)
class Decoration:
    """The configured provenance decoration binding gives every step one range
    collects, whether the range binds at planning or at execution. Built for
    one binding and never retained by what it binds."""

    audit: AuditStrategy
    actor_identity: ActorIdentity
    transaction_instant: TransactionInstant

    def __call__(self, step: PlannedStep) -> PlannedStep:
        return self.audit.decorate(
            step,
            actor_identity=self.actor_identity,
            transaction_instant=self.transaction_instant,
        )


@dataclass(frozen=True, slots=True)
class _Original:
    """One current row a range transforms: its complete predecessor state, the
    exact state it is, and the Valid Time it covers — ``None`` on a
    Transaction-Time-Only target."""

    predecessor: PredecessorRow
    state: ObservedStateKey
    valid_time_coverage: TimeInterval | None


def range_claims(composed: ComposedTemporalWrite) -> Completion | None:
    """The distinct retained observations a composed range's unit spends, each
    once."""
    distinct: list[RetainedObservation] = []
    for contribution in composed.contributions:
        claim = contribution.claim
        if claim is not None and all(claim is not held for held in distinct):
            distinct.append(claim)
    if not distinct:
        return None
    if len(distinct) == 1:
        return distinct[0]
    return Completions(tuple(distinct))


def _known_originals(
    composed: ComposedTemporalWrite, facts: TemporalFacts, object_key: ObjectKey
) -> tuple[tuple[_Original, ...], tuple[_Original, ...]]:
    """The originals a composed range's own observations already know, as the
    ones the transform binds — disjoint, ordered by start — beside the ones it
    only validates.

    Each distinct observed state is one original, in authored order. Two
    observations whose coverage overlaps cannot both describe current state, so
    the later-authored one is bound and the earlier is validated alone: its
    guarded effect fails unless the database itself holds overlapping current
    coverage.
    """
    distinct: list[_Original] = []
    for contribution in composed.contributions:
        observation = contribution.observation
        if observation is None:  # an insertion authorized it, and it observed nothing
            continue
        assert isinstance(observation, TemporalObservation)  # a temporal write observes a milestone
        claim = contribution.claim
        original = _original(
            facts,
            object_key,
            observation.predecessor,
            None if claim is None else claim.key,
        )
        if all(original.state != held.state for held in distinct):
            distinct.append(original)
    bound: list[_Original] = []
    validated: list[_Original] = []
    for original in reversed(distinct):
        if any(_overlapping(original, held) for held in bound):
            validated.append(original)
        else:
            bound.append(original)
    _order_by_start(bound)
    validated.reverse()
    return tuple(bound), tuple(validated)


_UNANCHORED: Final = object()
"""The anchor of a range no insertion authorized any write of."""

_EXISTENCE: Final = object()
"""The anchor of a Transaction-Time-Only range an insertion authorized a write
of: the current row itself, wherever it lies on an axis that has no Valid Time."""


def _anchor(composed: ComposedTemporalWrite) -> object:
    """Where a composed range requires current coverage because an insertion
    authorized one of its writes: that insertion's own start, which every such
    write states as its window's start."""
    for contribution in composed.contributions:
        if contribution.observation is None and contribution.condition is None:
            window = contribution.valid_time_window
            return _EXISTENCE if window is None else window.start
    return _UNANCHORED


@dataclass(frozen=True, slots=True)
class _StartingCondition:
    """A caller's condition on a composed range: the coverage at the start of
    the caller's prepared ``valid_time_window`` — the current row, where it is
    ``None`` on a Transaction-Time-Only object — stands at Transaction-Time
    start ``expected``. The window is also what the caller asked to revise
    whatever it reaches over."""

    valid_time_window: TimeInterval | None
    expected: dt.datetime


def _conditions(composed: ComposedTemporalWrite) -> tuple[_StartingCondition, ...]:
    """The distinct starting conditions the callers of a composed range's
    addressed writes state, in authored order: one per exact-window operation,
    where admission let in only writes that agree on it, and another for each
    operation over a disjoint window. Admission lets no two addressed windows
    share a start unless they are equal, so the distinct conditions keep every
    distinct addressed window."""
    conditions: list[_StartingCondition] = []
    for contribution in composed.contributions:
        condition = contribution.condition
        if condition is None:
            continue
        stated = _StartingCondition(contribution.valid_time_window, condition.instant)
        if stated not in conditions:
            conditions.append(stated)
    return tuple(conditions)


def _original(
    facts: TemporalFacts,
    object_key: ObjectKey,
    predecessor: PredecessorRow,
    state: ObservedStateKey | None,
) -> _Original:
    shape = facts.shape
    if state is None:
        state = TemporalStateKey(object_key, milestone_edge(shape, predecessor, None))
    return _Original(
        predecessor=predecessor,
        state=state,
        valid_time_coverage=valid_time_coverage(shape, predecessor, None),
    )


def _holds_start(window: TimeInterval | None, original: _Original) -> bool:
    """Whether ``original`` holds ``window``'s start — the current row itself
    where ``window`` is ``None`` on a Transaction-Time-Only object."""
    if window is None:
        return True
    coverage = original.valid_time_coverage
    assert coverage is not None  # one object's windows and coverage share its shape
    return coverage.contains(window.start)


def _overlapping(first: _Original, second: _Original) -> bool:
    first_coverage = first.valid_time_coverage
    second_coverage = second.valid_time_coverage
    return (
        first_coverage is None
        or second_coverage is None
        or first_coverage.overlaps(second_coverage)
    )


def _valid_time_coverages(originals: Iterable[_Original]) -> Iterator[TimeInterval]:
    """The Valid Time each of a Bitemporal range's bound ``originals`` covers,
    in the start order their owner already established."""
    for original in originals:
        coverage = original.valid_time_coverage
        assert coverage is not None  # only a Bitemporal range traverses coverage
        yield coverage


def _order_by_start(originals: list[_Original]) -> None:
    """Order a range's originals by their Valid-Time starts. Those of a
    Transaction-Time-Only object have none to order by and stay as they are."""
    if originals and originals[0].valid_time_coverage is not None:
        originals.sort(key=_coverage_start)


def _coverage_start(original: _Original) -> dt.datetime:
    coverage = original.valid_time_coverage
    assert coverage is not None  # only a Bitemporal range orders its originals
    return coverage.start


def _holds(original: _Original, anchor: object) -> bool:
    """Whether ``original`` holds the insertion ``anchor`` of a Bitemporal
    range."""
    coverage = original.valid_time_coverage
    assert coverage is not None and isinstance(anchor, dt.datetime)  # a Bitemporal anchor
    return coverage.contains(anchor)


def _valid_end(original: _Original) -> object | None:
    """The Valid-Time end cell ``original`` covers to, which its physical address
    holds; ``None`` on a Transaction-Time-Only object."""
    coverage = original.valid_time_coverage
    return None if coverage is None else coverage.end


@dataclass(slots=True)
class _Binding:
    """What binding one range accumulates: every original's own effect before
    any opening, and the facts its unit publishes."""

    effects: list[PlannedStep] = field(default_factory=list[PlannedStep])
    openings: list[PlannedStep] = field(default_factory=list[PlannedStep])
    changed: list[ObservedStateKey] = field(default_factory=list[ObservedStateKey])
    removed: list[OwnedEndpoint] = field(default_factory=list[OwnedEndpoint])
    fresh: list[OwnedEndpoint] = field(default_factory=list[OwnedEndpoint])
    continued: list[OwnedEndpoint] = field(default_factory=list[OwnedEndpoint])
    derived: list[Derivation] = field(default_factory=list[Derivation])

    def take(self, expansion: Expansion, decorate: Decoration) -> None:
        for step in expansion.steps:
            (self.openings if isinstance(step, PlannedInsert) else self.effects).append(
                decorate(step)
            )
        self.changed.extend(expansion.changed)
        self.removed.extend(expansion.removed)
        self.fresh.extend(expansion.opened.fresh)
        self.continued.extend(expansion.opened.continued)
        self.derived.extend(expansion.derived)

    def range(self, concludes: ObjectKey | None) -> BoundRange:
        return BoundRange(
            steps=(*self.effects, *self.openings),
            changed=tuple(self.changed),
            removed=tuple(self.removed),
            opened=Openings(tuple(self.fresh), tuple(self.continued)),
            derived=tuple(self.derived),
            concludes=concludes,
        )


@dataclass(frozen=True, slots=True)
class _RangeMeaning:
    """What one range settled to before any coverage is bound: finalized data
    alone, holding no ownership, decoration, clock, or other producer.

    ``facts.instant`` is the attempt's resolved instant. ``valid_time_window``
    is the final transform's enclosing window, derived once when settlement
    begins and shared by the coverage check, acquisition, and continuation;
    ``None`` on a Transaction-Time-Only object. ``derives`` says a later unit
    of the same flush depends on what this one does to its originals, so its
    bound range records it (:class:`Derivation`).
    """

    facts: TemporalFacts
    transform: CoverageTransform
    valid_time_window: TimeInterval | None
    gated: bool
    key_attribute: AttributeIdentity
    key_value: object
    object_key: ObjectKey
    anchor: object = _UNANCHORED
    conditions: tuple[_StartingCondition, ...] = ()
    derives: bool = False
    guards: bool = False


@dataclass(frozen=True, slots=True)
class _RangeBinding:
    """One binding of a range's ``meaning`` to its coverage, reading the
    attempt's live ``ownership`` through the range's one predecessor
    ``expansion`` and decorating every step it collects once. Exists only while
    it binds."""

    meaning: _RangeMeaning
    ownership: Ownership
    decorate: Decoration
    expansion: PredecessorExpansion

    def bind(
        self,
        originals: Sequence[_Original],
        validations: Sequence[_Original],
        discharged: frozenset[int] = frozenset(),
        *,
        concludes: bool = False,
    ) -> BoundRange:
        """The steps the transform takes over ``originals``, after a guarded
        validation of each of ``validations``, naming the object where the
        range ``concludes`` it (:attr:`BoundRange.concludes`).

        Every original's own effect — a validation, a close, a same-address
        revision, or a removal — runs before any successor opens, so a lost
        source condition fails before the range writes anything new. Each
        original expands through the range's one :class:`PredecessorExpansion`,
        and each successor derives from its own original alone.

        A range one of whose writes an insertion authorized requires current
        coverage at that insertion's anchor and fails as a missing target
        without it: the anchor is where the authority starts, never shifted to
        coverage that survives elsewhere.

        A range a caller addressed requires the coverage at each of its
        operations' starts to stand at the Transaction-Time start that caller
        stated, and fails as that caller's precondition otherwise — before
        anything executes where the coverage shows it, and at that original's
        gate where only execution can. The originals they start from are
        affected first, in the order the callers stated them, so a lost start
        fails ahead of every other original's effect; one guard serves every
        start one original holds. A condition an earlier unit of the flush
        already proved (``discharged``, by its position) is judged no further.
        Validations follow, then the remaining originals, and a replacement's
        extent then opens its complete state over every gap the originals leave.
        """
        meaning = self.meaning
        self._require_anchor(originals)
        starts = self._starts(originals, discharged)
        bound = _Binding()
        decorate = self.decorate
        for original in starts:
            bound.take(self._expanded(original, "starting"), decorate)
        for original in validations:
            bound.take(self._expanded(original, "validation"), decorate)
        for original in originals:
            if all(original is not start for start in starts):
                bound.take(self._expanded(original, "coverage"), decorate)
        facts = meaning.facts
        if isinstance(facts.shape, Bitemporal):
            key = {meaning.key_attribute: meaning.key_value}
            for gap in meaning.transform.gaps(_valid_time_coverages(originals)):
                attributes, value_objects = self.expansion.assignments(gap.assigned)
                entry = opening(
                    facts, {**attributes, **key}, dict(value_objects), gap.valid_time_window
                )
                bound.openings.append(
                    decorate(PlannedInsert(entity=facts.entity.identity, entries=(entry,)))
                )
                endpoint = entry_endpoint(facts, entry)
                if endpoint is not None:
                    bound.fresh.append(endpoint)
        return bound.range(meaning.object_key if concludes else None)

    def _expanded(self, original: _Original, role: ExpansionRole) -> Expansion:
        return self.expansion.expand(
            original.predecessor,
            role=role,
            state=original.state,
            coverage=original.valid_time_coverage,
        )

    def _require_anchor(self, originals: Sequence[_Original]) -> None:
        anchor = self.meaning.anchor
        if anchor is _UNANCHORED:
            return
        if any(anchor is _EXISTENCE or _holds(original, anchor) for original in originals):
            return
        raise MissingTargetError(self.meaning.facts.entity.identity, self._key_target(), 1, 0)

    def _key_target(self) -> KeyTarget:
        return KeyTarget(
            key_attributes=(self.meaning.key_attribute,), key_values=((self.meaning.key_value,),)
        )

    def _starts(
        self, originals: Sequence[_Original], discharged: frozenset[int]
    ) -> tuple[_Original, ...]:
        """The distinct originals the range's caller-addressed operations start
        from, in the order their conditions were stated, once the coverage shows
        each stands at its caller's Transaction-Time start; the first that does
        not fails as that caller's precondition."""
        starts: list[_Original] = []
        for position, condition in enumerate(self.meaning.conditions):
            if position in discharged:
                continue
            start = next(
                (
                    original
                    for original in originals
                    if _holds_start(condition.valid_time_window, original)
                ),
                None,
            )
            if start is None or self._tx_start(start) != condition.expected:
                raise self._failed(condition)
            if all(start is not held for held in starts):
                starts.append(start)
        return tuple(starts)

    def _tx_start(self, original: _Original) -> object:
        tx_start = self.meaning.facts.shape.transaction_time.start_attribute
        return original.predecessor.cell(tx_start)

    def _failed(self, condition: _StartingCondition) -> WritePreconditionError:
        return WritePreconditionError(
            self.meaning.facts.entity.identity,
            {self.meaning.key_attribute.name: self.meaning.key_value},
            condition.expected,
        )

    def acquired(
        self,
        rows: PredecessorRows | None,
        known: Sequence[_Original],
    ) -> tuple[_Original, ...]:
        """``known`` together with each acquired row at an address none of them
        holds, ordered by start.

        A caller-addressed operation's start names one current row, so more than
        one current row holding that start is Cardinality Corruption — an
        invariant failure that outranks the caller's precondition. Under Locking
        every known original is held under the shared lock, so it is current
        beside the acquired rows and is counted with them; under Optimistic a
        known original may be stale, so only the acquired rows are current
        evidence and a stale original is left to its own gate.
        """
        if rows is None:
            return tuple(known)
        ends = {_valid_end(original) for original in known}
        acquired = self._read(rows)
        merged = [*known, *(o for o in acquired if _valid_end(o) not in ends)]
        self._require_one_start(acquired if self.meaning.gated else merged)
        _order_by_start(merged)
        return tuple(merged)

    def continued(
        self,
        rows: PredecessorRows | None,
        known: Sequence[_Original],
    ) -> tuple[tuple[_Original, ...], frozenset[int]]:
        """The rows a range an ordering barrier kept after earlier writes of its
        object binds to, read over its whole window, beside the positions of
        the caller conditions the flush has already proved.

        The units before the barrier may have transformed the originals this
        range's writes were admitted against. An observed original still
        standing is an ordinary original. One the flush transformed under
        protection has proven its condition, provided every row derived from it
        within the window still stands as it was opened; the range then binds to
        those rows and their current values. Any other observed original has
        lost its condition, which fails as that write's own shortfall would.

        A caller's start standing at its stated Transaction-Time start is judged
        as usual. One standing at a row the flush derived from a proven original
        that held the caller's start at that stated start is proven too. Any
        other start is the caller's failed precondition, which outranks an
        observed loss.
        """
        read = self._read(rows) if rows is not None else ()
        self._require_one_start(read)
        standing = {original.state for original in read}
        lost = next(
            (
                original
                for original in known
                if original.state not in standing and not self._intact(original.state, read)
            ),
            None,
        )
        discharged: set[int] = set()
        for position, condition in enumerate(self.meaning.conditions):
            start = next(
                (
                    original
                    for original in read
                    if _holds_start(condition.valid_time_window, original)
                ),
                None,
            )
            if start is None:
                raise self._failed(condition)
            if self._tx_start(start) == condition.expected:
                continue
            if not self._descends(start, condition, read):
                raise self._failed(condition)
            discharged.add(position)
        if lost is not None:
            enforce_affected_rows(
                self.expansion.closing(lost.predecessor, lost.valid_time_coverage, TERMINATED),
                0,
            )
        ordered = list(read)
        _order_by_start(ordered)
        return tuple(ordered), frozenset(discharged)

    def _read(self, rows: PredecessorRows) -> list[_Original]:
        return [
            _original(self.meaning.facts, self.meaning.object_key, predecessor, None)
            for predecessor in _acquired_predecessors(rows)
        ]

    def _require_one_start(self, current: Sequence[_Original]) -> None:
        for condition in self.meaning.conditions:
            starting = sum(
                1 for original in current if _holds_start(condition.valid_time_window, original)
            )
            if starting > 1:
                raise CardinalityCorruptionError(
                    self.meaning.facts.entity.identity, self._key_target(), 1, starting
                )

    def _endpoint(self, original: _Original) -> OwnedEndpoint:
        coverage = original.valid_time_coverage
        ends = TRANSACTION_TIME_ENDS if coverage is None else bitemporal_ends(coverage.end)
        return OwnedEndpoint(self.meaning.facts.entity.identity, (self.meaning.key_value,), ends)

    def _opened_here(self, original: _Original) -> Descent | None:
        """What a current row the flush derived descends from, provided it
        stands exactly as it was opened: at an owned address, at this attempt's
        Transaction-Time start, from the Valid-Time start it was opened with."""
        endpoint = self._endpoint(original)
        if (
            not self.ownership.owns(endpoint)
            or self._tx_start(original) != self.meaning.facts.instant
        ):
            return None
        descent = self.ownership.descent(endpoint)
        if descent is None or descent.valid_time_coverage != original.valid_time_coverage:
            return None
        return descent

    def _descends(
        self, start: _Original, condition: _StartingCondition, read: Sequence[_Original]
    ) -> bool:
        """Whether ``start`` is a row the flush derived from a proven original
        that held ``condition``'s start at its stated Transaction-Time start,
        with everything else derived from that original intact."""
        descent = self._opened_here(start)
        if descent is None:
            return False
        original = descent.original
        proof = self.ownership.proven(original)
        if proof is None or not isinstance(original, TemporalStateKey):
            return False
        milestone = original.milestone
        if milestone.tx_time != condition.expected:
            return False
        window = condition.valid_time_window
        coverage = proof.valid_time_coverage
        if window is not None and (coverage is None or not coverage.contains(window.start)):
            return False
        return self._intact(original, read)

    def _intact(self, original: ObservedStateKey, read: Sequence[_Original]) -> bool:
        """Whether the flush transformed ``original`` under protection and every
        row it derived from it that lies inside this range's window still stands
        as it was opened."""
        if self.ownership.proven(original) is None:
            return False
        present = {self._endpoint(row): row for row in read}
        for endpoint, _descent in self.ownership.descendants(
            original, self.meaning.valid_time_window
        ):
            row = present.get(endpoint)
            if row is None or self._opened_here(row) is None:
                return False
        return True


@dataclass(frozen=True, slots=True)
class DeferredTemporalRange:
    """A range whose requested window reaches coverage no planning input knew,
    as the finalized data :func:`bind_deferred` binds once the executor has
    read that coverage.

    It holds what settlement decided and nothing that could decide again: no
    claim, ownership, decoration, clock, or model. The rows acquired for
    :attr:`acquisition` join the observed originals at every address those do
    not already hold; binding then proceeds exactly as for a range bound at
    planning. A ``continued`` range follows earlier writes of its object across
    an ordering barrier, so it binds to the rows it read alone, judging its
    observed originals and caller conditions against what the earlier units
    proved.
    """

    meaning: _RangeMeaning
    originals: tuple[_Original, ...]
    validations: tuple[_Original, ...]
    acquisition: RangeAcquisition
    continued: bool = False


def settle_range(
    composed: ComposedTemporalWrite,
    *,
    view: InheritanceEntityView,
    shape: TransactionTimeOnly | Bitemporal,
    gated: bool,
    instant: dt.datetime,
    ownership: Ownership,
    decorate: Decoration,
    guards: bool = False,
) -> BoundRange | DeferredTemporalRange:
    """One temporal object's composed writes as a range over its current
    coverage: bound now where planning knows that coverage, or else the
    deferred description of what binding needs once it is read.

    Every distinct observed predecessor is an original: each is validated by
    its own guarded effect before any successor opens, and the transform is
    bound to the ones that do not overlap a later-authored observation of the
    same coverage. Where those originals cover the whole requested window the
    range binds now; otherwise the coverage beyond them is read at execution
    and the range binds then. A write an insertion authorized observed nothing,
    so a range of such writes alone always reads its coverage, and requires
    coverage at the insertion's anchor once read. So does a write a caller
    addressed, whose caller's condition requires the coverage at its start to
    stand at the Transaction-Time start it states.

    A composition an ordering barrier kept after earlier writes of the same
    object (:class:`~parallax.core.unit_work.materialized.ChainedTemporalWrite`)
    always reads its whole window at execution: the units before the barrier
    changed coverage no planning input knows, and the conditions it was
    admitted with may already have been proven on the originals those units
    transformed. One a later region follows records what it derives.

    ``instant`` is the attempt's already-resolved Transaction Instant, which a
    deferred range retains as a value.
    """
    entity = composed.target
    facts = TemporalFacts(entity=entity, view=view, shape=shape, instant=instant)
    key_attribute = view.primary_key.identity
    key_value = composed.key[key_attribute.name]
    object_key = ObjectKey(entity.identity, ((key_attribute.name, key_value),))
    originals, validations = _known_originals(composed, facts, object_key)
    chained = composed if isinstance(composed, ChainedTemporalWrite) else None
    window = composed.transform.valid_time_window
    meaning = _RangeMeaning(
        facts=facts,
        transform=composed.transform,
        valid_time_window=window,
        gated=gated,
        key_attribute=key_attribute,
        key_value=key_value,
        object_key=object_key,
        anchor=_anchor(composed),
        conditions=_conditions(composed),
        derives=chained is not None and chained.leads,
        guards=guards,
    )
    if chained is not None and chained.follows:
        return DeferredTemporalRange(
            meaning=meaning,
            originals=originals,
            validations=validations,
            acquisition=RangeAcquisition(
                entity=entity,
                key_attribute=key_attribute,
                key_value=cast("ManagedValue", key_value),
                valid_time_window=window,
                locking=not gated,
            ),
            continued=True,
        )
    requested = window
    if window is not None:
        uncovered = window.first_uncovered(_valid_time_coverages(originals))
        reached = uncovered is not None
        if uncovered is not None:
            requested = window.clipped(start=uncovered)
    else:
        reached = not originals
    if reached:
        return DeferredTemporalRange(
            meaning=meaning,
            originals=originals,
            validations=validations,
            acquisition=RangeAcquisition(
                entity=entity,
                key_attribute=key_attribute,
                key_value=cast("ManagedValue", key_value),
                valid_time_window=requested,
                locking=not gated,
            ),
        )
    return _binding(meaning, ownership, decorate).bind(originals, validations)


def bind_deferred(
    description: DeferredTemporalRange,
    rows: PredecessorRows | None,
    *,
    ownership: Ownership,
    decorate: Decoration,
) -> BoundRange:
    """``description`` bound to the coverage its acquisition read — ``None``
    where the read found no row — through the same binding a range known at
    planning takes, under the attempt's current ``ownership``, every step
    decorated once."""
    binding = _binding(description.meaning, ownership, decorate)
    if description.continued:
        originals, discharged = binding.continued(
            rows, (*description.originals, *description.validations)
        )
        return binding.bind(originals, (), discharged, concludes=not description.meaning.derives)
    return binding.bind(binding.acquired(rows, description.originals), description.validations)


def _binding(meaning: _RangeMeaning, ownership: Ownership, decorate: Decoration) -> _RangeBinding:
    conditions = meaning.conditions
    return _RangeBinding(
        meaning,
        ownership,
        decorate,
        PredecessorExpansion(
            meaning.facts,
            meaning.transform,
            key_attribute=meaning.key_attribute,
            key_value=meaning.key_value,
            gated=meaning.gated,
            guards=meaning.guards,
            addressed=(
                tuple(condition.valid_time_window for condition in conditions) if conditions else ()
            ),
            derives=meaning.derives,
            ownership=ownership,
        ),
    )


def _acquired_predecessors(rows: PredecessorRows) -> Iterator[PredecessorRow]:
    for index in range(len(rows)):
        yield PredecessorRow.over_row(
            rows.selection, rows.rows[index], rows.document(index), rows.absent
        )
