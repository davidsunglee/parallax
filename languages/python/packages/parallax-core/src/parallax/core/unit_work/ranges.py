from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field, replace
from operator import attrgetter
from typing import Final, cast

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
from parallax.core.temporal_write.coverage import CoverageGap, CoverageTransform
from parallax.core.temporal_write.expansion import (
    ExpansionRole,
    PredecessorExpander,
    TemporalFacts,
    bitemporal_ends,
    entry_endpoint,
    openings,
)
from parallax.core.unit_work.acquisition import CoverageReadRequest
from parallax.core.unit_work.effects import (
    CardinalityCorruptionError,
    MissingTargetError,
    WritePreconditionError,
    enforce_affected_rows,
)
from parallax.core.unit_work.instructions import ExpectedTxStart
from parallax.core.unit_work.materialized import (
    ChainedTemporalWrite,
    ComposedTemporalWrite,
    InsertionKeyedWrite,
    ObservedKeyedWrite,
    PendingOpening,
    TargetKeyedWrite,
    TemporalKeyedWrite,
    singleton_transform,
)
from parallax.core.unit_work.retain import RetainedObservation
from parallax.core.unit_work.strategy import AuditDecoration
from parallax.core.write_plan.keys import ObjectKey, ObservedStateKey, TemporalStateKey
from parallax.core.write_plan.materialized import PredecessorRows
from parallax.core.write_plan.observe import PredecessorRow, TemporalObservation
from parallax.core.write_plan.plan import (
    TRANSACTION_TIME_ENDS,
    BoundRange,
    CombinedSourceAuthority,
    DeferredRange,
    Derivation,
    Descent,
    Openings,
    OwnedEndpoint,
    SourceAuthority,
    TemporalWriteOwnership,
)
from parallax.core.write_plan.planned_rows import resolve_row
from parallax.core.write_plan.steps import TERMINATED, KeyTarget, PlannedInsert, PlannedValue
from parallax.core.write_plan.steps import PlannedWrite as PlannedStep

__all__ = [
    "DeferredTemporalRange",
    "bind_deferred",
    "range_claims",
    "settle_opening",
    "settle_range",
]


@dataclass(frozen=True, slots=True)
class _Original:
    """One current row a range transforms: its complete predecessor state, the
    exact state it is, and the Valid Time it covers — ``None`` on a
    Transaction-Time-Only target."""

    predecessor: PredecessorRow
    state: ObservedStateKey
    valid_time_coverage: TimeInterval | None


def range_claims(item: ComposedTemporalWrite | TemporalKeyedWrite) -> SourceAuthority | None:
    """The distinct retained observations a range's unit spends, each once."""
    if isinstance(item, ObservedKeyedWrite):
        if not item.twins:
            return item.claim
        claims: Iterable[RetainedObservation | None] = (item.claim, *item.twins)
    elif isinstance(item, ComposedTemporalWrite):
        claims = (contribution.claim for contribution in item.contributions)
    else:
        return None
    distinct: list[RetainedObservation] = []
    for claim in claims:
        if claim is not None and all(claim is not held for held in distinct):
            distinct.append(claim)
    if not distinct:
        return None
    if len(distinct) == 1:
        return distinct[0]
    return CombinedSourceAuthority(tuple(distinct))


def _known_originals(
    composed: ComposedTemporalWrite,
    facts: TemporalFacts,
    key_attribute: AttributeIdentity,
    key_value: object,
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
            key_attribute,
            key_value,
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


_START: Final = attrgetter("start")

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
            return _anchored_at(contribution.valid_time_window)
    return _UNANCHORED


def _anchored_at(window: TimeInterval | None) -> object:
    return _EXISTENCE if window is None else window.start


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


def _object_key(
    facts: TemporalFacts, key_attribute: AttributeIdentity, key_value: object
) -> ObjectKey:
    return ObjectKey(facts.entity.identity, ((key_attribute.name, key_value),))


def _original(
    facts: TemporalFacts,
    key_attribute: AttributeIdentity,
    key_value: object,
    predecessor: PredecessorRow,
    state: ObservedStateKey | None,
) -> _Original:
    """One current row as an original: its observed state is the claim's where
    one names it, and otherwise the state its milestone edge keys."""
    shape = facts.shape
    if state is None:
        state = TemporalStateKey(
            _object_key(facts, key_attribute, key_value), milestone_edge(shape, predecessor, None)
        )
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
class _BoundRangeBuilder:
    """What binding one range accumulates: every original's own effect before
    any opening, and the facts its unit publishes, appended as each original
    settles rather than copied whole each time."""

    effects: list[PlannedStep] = field(default_factory=list[PlannedStep])
    openings: list[PlannedStep] = field(default_factory=list[PlannedStep])
    changed: list[ObservedStateKey] = field(default_factory=list[ObservedStateKey])
    removed: list[OwnedEndpoint] = field(default_factory=list[OwnedEndpoint])
    fresh: list[OwnedEndpoint] = field(default_factory=list[OwnedEndpoint])
    continued: list[OwnedEndpoint] = field(default_factory=list[OwnedEndpoint])
    derived: list[Derivation] = field(default_factory=list[Derivation])

    def take(self, expansion: BoundRange) -> None:
        for step in expansion.steps:
            (self.openings if isinstance(step, PlannedInsert) else self.effects).append(step)
        self.changed.extend(expansion.changed)
        self.removed.extend(expansion.removed)
        opened = expansion.opened
        self.fresh.extend(opened.fresh)
        self.continued.extend(opened.continued)
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
    ``None`` on a Transaction-Time-Only object. ``derives`` says a later unit
    of the same flush depends on what this one does to its originals, so its
    bound range records it (:class:`Derivation`). ``opening`` is the pending
    insertion a replacement reaching past it settles with.
    """

    facts: TemporalFacts
    transform: CoverageTransform
    valid_time_window: TimeInterval | None
    gated: bool
    key_attribute: AttributeIdentity
    key_value: object
    anchor: object = _UNANCHORED
    conditions: tuple[_StartingCondition, ...] = ()
    derives: bool = False
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
        original expands through the range's one :class:`PredecessorExpander`,
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

        A pending insertion the range settles with opens what the transform
        leaves of its own window as new lineages, and its window is coverage no
        gap opening refills.
        """
        meaning = self.meaning
        self._require_anchor(originals)
        starts = self._starts(originals, discharged)
        transform = meaning.transform
        seed = meaning.opening
        gaps = (
            transform.gaps(_with_opening(_valid_time_coverages(originals), seed))
            if transform.replaces and isinstance(meaning.facts.shape, Bitemporal)
            else ()
        )
        concluded = meaning.object_key if concludes else None
        if seed is not None:
            return self._settled_with(seed, originals, gaps, concluded)
        if not starts and not validations and not gaps and len(originals) == 1:
            # One original's expansion already orders its own effect first.
            (original,) = originals
            expansion = self._expanded(original, "coverage")
            return expansion if concluded is None else replace(expansion, concludes=concluded)
        bound = _BoundRangeBuilder()
        for original in starts:
            bound.take(self._expanded(original, "starting"))
        for original in validations:
            bound.take(self._expanded(original, "validation"))
        for original in originals:
            if all(original is not start for start in starts):
                bound.take(self._expanded(original, "coverage"))
        for gap in gaps:
            self._open(bound, gap)
        return bound.range(concluded)

    def _settled_with(
        self,
        seed: _OpeningSeed,
        originals: Sequence[_Original],
        gaps: Sequence[CoverageGap],
        concluded: ObjectKey | None,
    ) -> BoundRange:
        """The pending insertion ``seed`` settled as one unit with the stored
        ``originals`` its replacement reaches and the ``gaps`` it establishes:
        every original's own effect first, then the insertion's surviving
        parts, the originals' successors, and the gap openings."""
        bound = _BoundRangeBuilder()
        inserts = self.expansion.lineage(seed.state, seed.window)
        bound.openings.extend(inserts)
        bound.continued.extend(openings(self.meaning.facts, inserts))
        for original in originals:
            bound.take(self._expanded(original, "coverage"))
        for gap in gaps:
            self._open(bound, gap)
        return bound.range(concluded)

    def _open(self, bound: _BoundRangeBuilder, gap: CoverageGap) -> None:
        """Open a replacement's new lineage over ``gap``, after every original's
        own effect."""
        facts = self.meaning.facts
        entry = self.expansion.gap(gap)
        bound.openings.append(PlannedInsert(entity=facts.entity.identity, entries=(entry,)))
        endpoint = entry_endpoint(facts, entry)
        if endpoint is not None:
            bound.fresh.append(endpoint)

    def _expanded(self, original: _Original, role: ExpansionRole) -> BoundRange:
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
        conditions = self.meaning.conditions
        if not conditions:
            return ()
        starts: list[_Original] = []
        for position, condition in enumerate(conditions):
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
        meaning = self.meaning
        return [
            _original(meaning.facts, meaning.key_attribute, meaning.key_value, predecessor, None)
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
class DeferredTemporalRange(DeferredRange):
    """A range whose requested window reaches coverage no planning input knew,
    as the finalized data :func:`bind_deferred` binds once its unit of work has
    read that coverage.

    It holds what settlement decided and nothing that could decide again: no
    claim, ownership, audit, clock, or model. The rows read for
    :attr:`coverage` join the observed originals at every address those do
    not already hold; binding then proceeds exactly as for a range bound at
    planning. A ``continued`` range follows earlier writes of its object across
    an ordering barrier, so it binds to the rows it read alone, judging its
    observed originals and caller conditions against what the earlier units
    proved.
    """

    meaning: _RangeMeaning
    originals: tuple[_Original, ...]
    validations: tuple[_Original, ...]
    coverage: CoverageReadRequest
    continued: bool = False


def settle_range(
    item: ComposedTemporalWrite | TemporalKeyedWrite,
    *,
    view: InheritanceEntityView,
    shape: TransactionTimeOnly | Bitemporal,
    gated: bool,
    instant: dt.datetime,
    ownership: TemporalWriteOwnership,
    audit: AuditDecoration,
    guards: bool = False,
) -> BoundRange | DeferredTemporalRange:
    """One temporal object's pending writes as a range over its current
    coverage: bound now where planning knows that coverage, or else the
    deferred description of what binding needs once it is read.

    A lone write reaches here as the carrier it was buffered in, and its
    transform is built once, here, from that carrier; a composition brings the
    transform its buffering composed.

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
    key_attribute = view.primary_key.identity
    entity, key_value, transform = _range_of(item, key_attribute)
    facts = TemporalFacts(entity=entity, view=view, shape=shape, instant=instant)
    originals, validations, anchor, conditions = _known(item, facts, key_attribute, key_value)
    chained = item if isinstance(item, ChainedTemporalWrite) else None
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
        derives=chained is not None and chained.leads,
        guards=guards,
    )
    if chained is not None and chained.follows:
        return DeferredTemporalRange(
            meaning=meaning,
            originals=originals,
            validations=validations,
            coverage=_coverage(meaning, window),
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
            coverage=_coverage(meaning, requested),
        )
    return _binding(meaning, ownership, audit).bind(originals, validations)


def settle_opening(
    opening: PendingOpening,
    *,
    view: InheritanceEntityView,
    shape: Bitemporal,
    gated: bool,
    instant: dt.datetime,
    ownership: TemporalWriteOwnership,
    audit: AuditDecoration,
    guards: bool = False,
) -> BoundRange | DeferredTemporalRange:
    """A pending Bitemporal insertion and the writes its insertion authorized
    since, settled as one unit: the insertion's authored state seeds every
    surviving part of its own window, with the composed assignments overlaid
    there, and no predecessor is fabricated for it.

    A replacement it authorized reaching past the insertion's window
    establishes its complete state there exactly as one reaching past a stored
    row does: the stored coverage beyond the window is read at execution, each
    row it reaches is transformed under its own proof, and the replacement's
    gaps open. An amendment reaches nothing outside the insertion's window.
    ``instant`` is the attempt's already-resolved Transaction Instant.
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
    beyond = opening.beyond
    if beyond is None:
        inserts = PredecessorExpander(
            facts,
            transform,
            key_attribute=key_attribute,
            gated=gated,
            ownership=ownership,
            audit=audit,
        ).lineage((attributes, value_objects), window)
        return BoundRange(steps=inserts, opened=Openings(continued=openings(facts, inserts)))
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
    return DeferredTemporalRange(
        meaning=meaning, originals=(), validations=(), coverage=_coverage(meaning, beyond)
    )


def _with_opening(
    coverage: Iterator[TimeInterval], seed: _OpeningSeed | None
) -> Iterable[TimeInterval]:
    """``coverage`` with a pending insertion's window in its start order."""
    if seed is None:
        return coverage
    return sorted((seed.window, *coverage), key=_START)


def _range_of(
    item: ComposedTemporalWrite | TemporalKeyedWrite, key_attribute: AttributeIdentity
) -> tuple[EntityMetadata, object, CoverageTransform]:
    """The object ``item`` writes, its key value, and its transform."""
    if isinstance(item, ComposedTemporalWrite):
        return item.target, item.key[key_attribute.name], item.transform
    instruction = item.instruction
    return (
        instruction.target,
        instruction.rows[0][key_attribute.name],
        singleton_transform(item, key_attribute.name),
    )


def _known(
    item: ComposedTemporalWrite | TemporalKeyedWrite,
    facts: TemporalFacts,
    key_attribute: AttributeIdentity,
    key_value: object,
) -> tuple[tuple[_Original, ...], tuple[_Original, ...], object, tuple[_StartingCondition, ...]]:
    """What planning knows of ``item``'s range: the originals it binds and
    validates, its insertion anchor, and its callers' starting conditions."""
    if isinstance(item, ComposedTemporalWrite):
        originals, validations = _known_originals(item, facts, key_attribute, key_value)
        return originals, validations, _anchor(item), _conditions(item)
    window = item.instruction.valid_time_window
    if isinstance(item, InsertionKeyedWrite):
        return (), (), _anchored_at(window), ()
    if isinstance(item, TargetKeyedWrite):
        expectation = item.expectation
        conditions = (
            (_StartingCondition(window, expectation.instant),)
            if isinstance(expectation, ExpectedTxStart)
            else ()
        )
        return (), (), _UNANCHORED, conditions
    observation = item.observation
    assert isinstance(observation, TemporalObservation)  # settlement refuses any other
    claim = item.claim
    original = _original(
        facts,
        key_attribute,
        key_value,
        observation.predecessor,
        None if claim is None else claim.key,
    )
    return (original,), (), _UNANCHORED, ()


def _coverage(meaning: _RangeMeaning, window: TimeInterval | None) -> CoverageReadRequest:
    return CoverageReadRequest(
        entity=meaning.facts.entity,
        key_attribute=meaning.key_attribute,
        key_value=cast("ManagedValue", meaning.key_value),
        valid_time_window=window,
        locking=not meaning.gated,
    )


def bind_deferred(
    description: DeferredTemporalRange,
    rows: PredecessorRows | None,
    *,
    ownership: TemporalWriteOwnership,
    audit: AuditDecoration,
) -> BoundRange:
    """``description`` bound to the coverage read for it — ``None`` where the
    read found no row — through the same binding a range known at planning
    takes, under the attempt's current ``ownership``, every produced row
    finalized and every emitted close decorated once."""
    binding = _binding(description.meaning, ownership, audit)
    if description.continued:
        originals, discharged = binding.continued(
            rows, (*description.originals, *description.validations)
        )
        return binding.bind(originals, (), discharged, concludes=not description.meaning.derives)
    return binding.bind(binding.acquired(rows, description.originals), description.validations)


def _binding(
    meaning: _RangeMeaning, ownership: TemporalWriteOwnership, audit: AuditDecoration
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
            derives=meaning.derives,
            ownership=ownership,
            audit=audit,
        ),
    )


def _acquired_predecessors(rows: PredecessorRows) -> Iterator[PredecessorRow]:
    for index in range(len(rows)):
        yield PredecessorRow.over_row(
            rows.selection, rows.rows[index], rows.document(index), rows.absent
        )
