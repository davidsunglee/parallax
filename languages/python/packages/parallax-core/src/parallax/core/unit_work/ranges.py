from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Final, cast

from parallax.core.base import ManagedValue, normalize_instant
from parallax.core.inheritance import InheritanceEntityView
from parallax.core.metamodel import AttributeIdentity, ValueObjectIdentity
from parallax.core.temporal_read import (
    Bitemporal,
    TimeInterval,
    TransactionTimeOnly,
    milestone_edge,
    valid_time_coverage,
)
from parallax.core.unit_work.clock import TransactionInstant
from parallax.core.unit_work.effects import (
    CardinalityCorruptionError,
    MissingTargetError,
    WritePreconditionError,
    enforce_affected_rows,
)
from parallax.core.unit_work.materialized import ChainedTemporalWrite, ComposedTemporalWrite
from parallax.core.unit_work.milestones import (
    Settled,
    SettledClose,
    TemporalFacts,
    bitemporal_ends,
    close_step,
    dispose,
    entry_endpoint,
    openings,
    preserved,
    successor_step,
    target_endpoint,
)
from parallax.core.unit_work.retain import RetainedObservation
from parallax.core.unit_work.strategy import (
    AUTHORED_STATE,
    CARRIED_STATE,
    CHANGED_STATE,
    ActorIdentity,
    AuditStrategy,
)
from parallax.core.unit_work.temporal import BoundPiece, TemporalTransform, literal_successor
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
from parallax.core.write_plan.planned_rows import resolve_row
from parallax.core.write_plan.steps import (
    FAILED_PRECONDITION,
    SUPERSEDED,
    TERMINATED,
    CloseCause,
    ExactCount,
    KeyTarget,
    PlannedClose,
    PlannedInsert,
    PlannedValue,
)
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


def _reaches(window: TimeInterval | None, original: _Original) -> bool:
    """Whether ``window`` overlaps ``original`` — the whole axis where it is
    ``None`` on a Transaction-Time-Only object."""
    if window is None:
        return True
    coverage = original.valid_time_coverage
    assert coverage is not None  # one object's windows and coverage share its shape
    return coverage.overlaps(window)


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


def _tiles(pieces: Sequence[BoundPiece], coverage: TimeInterval) -> bool:
    """Whether ``pieces``, in order, cover exactly ``coverage``, each meeting
    the next."""
    if not pieces:
        return False
    first = pieces[0].valid_time_coverage
    last = pieces[-1].valid_time_coverage
    assert first is not None and last is not None  # Bitemporal pieces lie on Valid Time
    if first.start != coverage.start or last.end != coverage.end:
        return False
    previous = first
    for piece in pieces[1:]:
        extent = piece.valid_time_coverage
        assert extent is not None  # Bitemporal pieces lie on Valid Time
        if not previous.meets(extent):
            return False
        previous = extent
    return True


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

    def take(
        self,
        transformed: tuple[Settled, Derivation | None] | None,
        decorate: Decoration,
    ) -> None:
        if transformed is None:
            return
        disposed, derivation = transformed
        for step in disposed.steps:
            (self.openings if isinstance(step, PlannedInsert) else self.effects).append(
                decorate(step)
            )
        self.changed.extend(disposed.changed)
        self.removed.extend(disposed.removed)
        self.fresh.extend(disposed.opened.fresh)
        self.continued.extend(disposed.opened.continued)
        if derivation is not None:
            self.derived.append(derivation)

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
    transform: TemporalTransform
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
    attempt's live ``ownership`` and decorating every step it collects once.
    Exists only while it binds."""

    meaning: _RangeMeaning
    ownership: Ownership
    decorate: Decoration

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
        source condition fails before the range writes anything new. A
        predecessor that existed before the attempt is closed and every nonempty
        piece of it opened; one the attempt opened is revised in place or
        removed (:func:`dispose`). An original the transform does not reach is
        left alone.

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
        A replacement's extent then opens its complete state over every gap the
        originals leave.

        An original the transform leaves exactly as it was — every piece of it
        kept, every assigned member already its value, and no caller-addressed
        window over it — is kept rather than transformed where that is proven
        (:func:`preserved`): it is not changed, derives nothing, and opens
        nothing.
        """
        facts = self.meaning.facts
        self._require_anchor(originals)
        starts = self._starts(originals, discharged)
        bound = _Binding()
        resolved: dict[
            int, tuple[dict[AttributeIdentity, PlannedValue], dict[ValueObjectIdentity, object]]
        ] = {}
        decorate = self.decorate
        for original in starts:
            bound.take(self._transformed(original, True, resolved), decorate)
        for original in validations:
            bound.effects.append(decorate(self._close(original, TERMINATED)))
            bound.changed.append(original.state)
            if self.meaning.derives:
                bound.derived.append(
                    Derivation(original.state, original.valid_time_coverage, None, ())
                )
        for original in originals:
            if all(original is not start for start in starts):
                bound.take(self._transformed(original, False, resolved), decorate)
        if isinstance(facts.shape, Bitemporal):
            for piece in self.meaning.transform.gaps(_valid_time_coverages(originals)):
                opened = self._authored(piece, resolved)
                bound.openings.append(decorate(opened))
                bound.fresh.extend(openings(facts, (opened,)))
        return bound.range(self.meaning.object_key if concludes else None)

    def _transformed(
        self,
        original: _Original,
        starting: bool,
        resolved: dict[
            int, tuple[dict[AttributeIdentity, PlannedValue], dict[ValueObjectIdentity, object]]
        ],
    ) -> tuple[Settled, Derivation | None] | None:
        """What the transform does to ``original`` — its own effect and the
        pieces it leaves — and what a later unit needs of that, or ``None``
        where the transform does not reach it. A ``starting`` original's effect
        fails as its caller's precondition."""
        meaning = self.meaning
        coverage = original.valid_time_coverage
        if not meaning.transform.touches(coverage):
            return None
        pieces = meaning.transform.pieces(coverage)
        if (
            not starting
            and (
                meaning.guards or not meaning.gated or self.ownership.owns(self._endpoint(original))
            )
            and self._unchanged(original, pieces)
        ):
            kept_as_is = preserved(
                meaning.facts,
                self._close(original, SUPERSEDED),
                self.ownership,
                guards=meaning.guards,
            )
            if kept_as_is is not None:
                return kept_as_is, None
        predecessor = original.predecessor.with_bindable_document()
        successors = tuple(self._successor(piece, predecessor, resolved) for piece in pieces)
        cause = SUPERSEDED if any(piece.assigned is not None for piece in pieces) else TERMINATED
        closing = self._close(original, cause)
        if meaning.gated and starting:
            closing = replace(
                closing, affected_rows=ExactCount(expected=1, on_shortfall=FAILED_PRECONDITION)
            )
        disposed = dispose(
            meaning.facts, closing, successors, predecessor, self.ownership, original.state
        )
        if not meaning.derives:
            return disposed, None
        return disposed, self._derivation(original, closing, pieces, successors)

    def _unchanged(self, original: _Original, pieces: Sequence[BoundPiece]) -> bool:
        """Whether ``pieces`` leave ``original`` as it was: they cover all of it,
        each assigned member already holds its value there, and no
        caller-addressed window reaches it."""
        if any(
            _reaches(condition.valid_time_window, original) for condition in self.meaning.conditions
        ):
            return False
        coverage = original.valid_time_coverage
        if coverage is None:
            if len(pieces) != 1:
                return False
        elif not _tiles(pieces, coverage):
            return False
        selection = self.meaning.facts.view.member_selection
        predecessor = original.predecessor
        return all(
            piece.assigned is None or predecessor.holds(selection, piece.assigned)
            for piece in pieces
        )

    def _derivation(
        self,
        original: _Original,
        closing: PlannedClose,
        pieces: Sequence[BoundPiece],
        successors: Sequence[PlannedInsert],
    ) -> Derivation:
        """What a later unit needs of ``original``'s transformation: its state
        and coverage, its own address where the attempt owned it, and each
        nonempty row derived from it with the coverage of the piece it opens."""
        facts = self.meaning.facts
        own = target_endpoint(facts, closing.target)
        rows: list[tuple[OwnedEndpoint, TimeInterval | None]] = []
        for piece, successor in zip(pieces, successors, strict=True):
            (entry,) = successor.entries
            endpoint = entry_endpoint(facts, entry)
            if endpoint is not None:
                rows.append((endpoint, piece.valid_time_coverage))
        return Derivation(
            original=original.state,
            valid_time_coverage=original.valid_time_coverage,
            owned=own if self.ownership.owns(own) else None,
            rows=tuple(rows),
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
            if start is None or self._tx_start(start) != normalize_instant(condition.expected):
                raise self._failed(condition)
            if all(start is not held for held in starts):
                starts.append(start)
        return tuple(starts)

    def _tx_start(self, original: _Original) -> dt.datetime:
        tx_start = self.meaning.facts.shape.transaction_time.start_attribute
        return normalize_instant(cast("dt.datetime", original.predecessor.cell(tx_start)))

    def _failed(self, condition: _StartingCondition) -> WritePreconditionError:
        return WritePreconditionError(
            self.meaning.facts.entity.identity,
            {self.meaning.key_attribute.name: self.meaning.key_value},
            condition.expected,
        )

    def _authored(
        self,
        piece: BoundPiece,
        resolved: dict[
            int, tuple[dict[AttributeIdentity, PlannedValue], dict[ValueObjectIdentity, object]]
        ],
    ) -> PlannedInsert:
        """A gap of a replacement's extent opened with its complete state."""
        assigned = piece.assigned
        assert assigned is not None  # a gap fills only with a stated state
        attributes, value_objects = self._resolved(assigned, resolved)
        return successor_step(
            self.meaning.facts,
            literal_successor(AUTHORED_STATE, piece.valid_time_coverage),
            {**attributes, self.meaning.key_attribute: self.meaning.key_value},
            value_objects,
            None,
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
            if self._tx_start(start) == normalize_instant(condition.expected):
                continue
            if not self._descends(start, condition, read):
                raise self._failed(condition)
            discharged.add(position)
        if lost is not None:
            enforce_affected_rows(self._close(lost, TERMINATED), 0)
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
        if normalize_instant(milestone.tx_time) != normalize_instant(condition.expected):
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

    def _close(self, original: _Original, cause: CloseCause) -> PlannedClose:
        facts = self.meaning.facts
        shape = facts.shape
        close = SettledClose(
            cause=cause,
            key_attributes=(self.meaning.key_attribute,),
            gate_start_attribute=shape.transaction_time.start_attribute,
            gated=self.meaning.gated,
        )
        return close_step(
            facts,
            close,
            key_values=(self.meaning.key_value,),
            observed_valid_end=_valid_end(original),
            observed_gate_start=(
                original.predecessor.cell(shape.transaction_time.start_attribute)
                if self.meaning.gated
                else None
            ),
        )

    def _successor(
        self,
        piece: BoundPiece,
        predecessor: PredecessorRow,
        resolved: dict[
            int, tuple[dict[AttributeIdentity, PlannedValue], dict[ValueObjectIdentity, object]]
        ],
    ) -> PlannedInsert:
        facts = self.meaning.facts
        assigned = piece.assigned
        if assigned is None:
            return successor_step(
                facts,
                literal_successor(CARRIED_STATE, piece.valid_time_coverage),
                {},
                {},
                predecessor,
            )
        attributes, value_objects = self._resolved(assigned, resolved)
        return successor_step(
            facts,
            literal_successor(CHANGED_STATE, piece.valid_time_coverage),
            attributes,
            value_objects,
            predecessor,
        )

    def _resolved(
        self,
        assigned: Mapping[str, object],
        resolved: dict[
            int, tuple[dict[AttributeIdentity, PlannedValue], dict[ValueObjectIdentity, object]]
        ],
    ) -> tuple[dict[AttributeIdentity, PlannedValue], dict[ValueObjectIdentity, object]]:
        """``assigned`` under its resolved member identities, resolved once per
        binding however many pieces carry it."""
        maps = resolved.get(id(assigned))
        if maps is None:
            maps = resolve_row(
                self.meaning.facts.entity, self.meaning.facts.view, assigned, context="insert"
            )
            resolved[id(assigned)] = maps
        return maps


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
    facts = TemporalFacts(
        entity=entity,
        view=view,
        shape=shape,
        instant=instant,
        close=None,
        resolved_successors=(),
    )
    key_attribute = view.primary_key.identity
    key_value = composed.key[key_attribute.name]
    object_key = ObjectKey(entity.identity, ((key_attribute.name, key_value),))
    originals, validations = _known_originals(composed, facts, object_key)
    chained = composed if isinstance(composed, ChainedTemporalWrite) else None
    window = composed.transform.enclosing_window()
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
    return _RangeBinding(meaning, ownership, decorate).bind(originals, validations)


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
    binding = _RangeBinding(description.meaning, ownership, decorate)
    if description.continued:
        originals, discharged = binding.continued(
            rows, (*description.originals, *description.validations)
        )
        return binding.bind(originals, (), discharged, concludes=not description.meaning.derives)
    return binding.bind(binding.acquired(rows, description.originals), description.validations)


def _acquired_predecessors(rows: PredecessorRows) -> Iterator[PredecessorRow]:
    for index in range(len(rows)):
        yield PredecessorRow.over_row(
            rows.selection, rows.rows[index], rows.document(index), rows.absent
        )
