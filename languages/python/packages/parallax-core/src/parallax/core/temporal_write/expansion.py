from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal

from parallax.core.base import INFINITY, TemporalBound
from parallax.core.inheritance import InheritanceEntityView
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityMetadata,
    ValueObjectIdentity,
)
from parallax.core.temporal_read import Bitemporal, TimeInterval, TransactionTimeOnly
from parallax.core.temporal_write.coverage import CoverageTransform, Successor
from parallax.core.write_plan.keys import ObservedStateKey
from parallax.core.write_plan.observe import PredecessorRow
from parallax.core.write_plan.plan import (
    OPEN_BITEMPORAL_ENDS,
    TRANSACTION_TIME_ENDS,
    Derivation,
    Openings,
    OwnedEndpoint,
    Ownership,
    UnitEffects,
)
from parallax.core.write_plan.planned_rows import WritePlanningError, resolve_row
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
    "TemporalFacts",
    "bitemporal_ends",
    "dispose",
    "entry_endpoint",
    "entry_ends",
    "kept",
    "opening",
    "openings",
    "planned_close",
    "preserved",
    "revision_assignments",
    "successor_insert",
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

    Built for one binding, from the unit's settled facts and the attempt's
    ownership as it stands then. ``addressed`` holds the windows the unit's
    callers addressed, ``gated`` and ``guards`` whether its closes gate and
    whether the database can prove an unchanged milestone by a guard, and
    ``derives`` whether a later unit of the flush relies on what it derives.
    Each canonical assignment mapping is resolved once per expansion, however
    many successors and gaps share it. Nothing returned retains the expansion.
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
        key_value: object,
        gated: bool,
        guards: bool,
        addressed: tuple[TimeInterval | None, ...],
        derives: bool,
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
        proven (:func:`preserved`). Otherwise the predecessor is closed —
        Superseded where a successor assigns, Terminated otherwise — and its
        nonempty successors opened, or the attempt's own row is revised or
        removed instead (:func:`dispose`). A ``starting`` predecessor's gated
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
        return planned_close(
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
        return preserved(
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
            return successor_insert(self._facts, predecessor, start, end)
        attributes, value_objects = self.assignments(assigned)
        return successor_insert(self._facts, predecessor, start, end, attributes, value_objects)

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
        return dispose(self._facts, closing, inserts, predecessor, self._ownership, state, derived)

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
        own = target_endpoint(facts, closing.target)
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


def preserved(
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
    if ownership.owns(target_endpoint(facts, closing.target)) or isinstance(concurrency, Ungated):
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


def successor_insert(
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


def dispose(
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

    Only nonempty successors are opened. A predecessor that existed before
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
    pieces = tuple(successor for successor in successors if not _is_empty(facts, successor))
    own = target_endpoint(facts, closing.target)
    if not ownership.owns(own):
        return Expansion(
            steps=(closing, *pieces),
            changed=changed,
            opened=Openings(fresh=openings(facts, pieces)),
            derived=derived,
        )
    continues = ownership.continues_insertion(own)
    kept_at = kept(facts, own, pieces)
    if kept_at is not None:
        piece = pieces[kept_at]
        others = tuple(other for other in pieces if other is not piece)
        assignments = revision_assignments(facts, piece.entries[0], predecessor)
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


def kept(facts: TemporalFacts, own: OwnedEndpoint, pieces: Sequence[PlannedInsert]) -> int | None:
    """The position of the one successor among ``pieces`` that keeps the owned
    address ``own``, or ``None`` unless exactly one does."""
    keeping = [
        position
        for position, piece in enumerate(pieces)
        if entry_endpoint(facts, piece.entries[0]) == own
    ]
    return keeping[0] if len(keeping) == 1 else None


def revision_assignments(
    facts: TemporalFacts, entry: InsertEntry, predecessor: PredecessorRow
) -> PlannedAssignments | None:
    """What revising ``predecessor`` in place into ``entry``'s state assigns.

    Every member ``entry`` does not carry as the predecessor's own cell, plus a
    moved Valid-Time start. The key, every axis end, and the Transaction-Time
    start belong to the address the revision preserves. ``None`` when nothing
    differs.
    """
    shape = facts.shape
    addressed = {
        facts.view.primary_key.identity,
        shape.transaction_time.start_attribute,
        shape.transaction_time.end_attribute,
    }
    valid_start: AttributeIdentity | None = None
    if isinstance(shape, Bitemporal):
        addressed.add(shape.valid_time.end_attribute)
        valid_start = shape.valid_time.start_attribute
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


def target_endpoint(facts: TemporalFacts, target: MilestoneTarget) -> OwnedEndpoint:
    return OwnedEndpoint(facts.entity.identity, target.key_values, target.end_values)


def bitemporal_ends(valid_end: object) -> tuple[TemporalUpperBound, ...]:
    if valid_end is TemporalBound.INFINITY:
        return OPEN_BITEMPORAL_ENDS
    return (Finite(instant=valid_end), OPEN_UPPER_BOUND)


def _is_empty(facts: TemporalFacts, successor: PlannedInsert) -> bool:
    """Whether ``successor`` covers no Valid Time at all.

    A Transaction-Time-Only successor always covers its whole axis. A
    Bitemporal one is empty when its finite end equals its start, as a head
    whose mutation starts exactly where the predecessor does.
    """
    shape = facts.shape
    if not isinstance(shape, Bitemporal):
        return False
    row = successor.entries[0].row.attributes
    end = row[shape.valid_time.end_attribute]
    return end is not TemporalBound.INFINITY and end == row[shape.valid_time.start_attribute]


def planned_close(
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
            end_values=_end_values(entity, shape, observed_valid_end),
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
    entity: EntityMetadata,
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
    if observed_valid_end is None:
        raise WritePlanningError(
            f"bitemporal close on {entity.identity.name!r}: no observed Valid-Time end "
            "supplied — a Bitemporal milestone address needs one exclusive upper bound "
            "per As-Of Axis (m-temporal-write 'Address and gate are separate')"
        )
    return bitemporal_ends(observed_valid_end)
