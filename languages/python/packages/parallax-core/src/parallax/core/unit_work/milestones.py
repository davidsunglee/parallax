from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from parallax.core.base import TemporalBound
from parallax.core.inheritance import InheritanceEntityView
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityMetadata,
    ValueObjectIdentity,
)
from parallax.core.temporal_read import Bitemporal, TransactionTimeOnly
from parallax.core.unit_work.strategy import AuthoredState, CarriedState, ChangedState
from parallax.core.unit_work.temporal import ResolvedSuccessor, bind_successor
from parallax.core.write_plan.keys import ObservedStateKey
from parallax.core.write_plan.observe import PredecessorRow
from parallax.core.write_plan.plan import (
    OPEN_BITEMPORAL_ENDS,
    TRANSACTION_TIME_ENDS,
    Openings,
    OwnedEndpoint,
    Ownership,
    UnitEffects,
)
from parallax.core.write_plan.planned_rows import WritePlanningError
from parallax.core.write_plan.steps import (
    INFINITY,
    UNGATED,
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
    TemporalConcurrency,
    TemporalGate,
    TemporalUpperBound,
    Ungated,
    adopt_planned_assignments,
    shortfall_for,
)
from parallax.core.write_plan.steps import PlannedWrite as PlannedStep

__all__ = [
    "Settled",
    "SettledClose",
    "TemporalFacts",
    "bitemporal_ends",
    "close_step",
    "dispose",
    "entry_endpoint",
    "entry_ends",
    "kept",
    "openings",
    "predecessor_maps",
    "preserved",
    "revision_assignments",
    "successor_step",
    "target_endpoint",
]


@dataclass(frozen=True, slots=True)
class SettledClose:
    """What closing the current milestone takes, settled once per temporal
    mutation whose topology closes one.

    One value rather than four independently optional fields on the facts: a
    topology either closes or does not, and each of these is settled exactly
    when it does — so a cause reaching emission without its gate basis is
    unconstructable rather than asserted against, and a mutation that opens a
    milestone without closing one settles no address and asks for no gate
    decision at all.
    """

    cause: CloseCause
    key_attributes: tuple[AttributeIdentity, ...]
    gate_start_attribute: AttributeIdentity
    gated: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class Settled(UnitEffects):
    """One settled mutation's steps beside the effects their success
    publishes."""

    steps: tuple[PlannedStep, ...]


@dataclass(frozen=True, slots=True)
class TemporalFacts:
    """Every semantic fact one temporal mutation settles before any row of it
    is bound — decided once per keyed instruction and once per Materialized
    Write Group by Write Settlement, and once per range.

    Everything here is a value some producer emitted for THIS mutation: the
    facet's compiled view of the target, the family's Temporal Shape whose axes
    bound its intervals, the instant the clock resolved, what closing takes if
    the topology closes anything, and the successors the Temporal Strategy's
    topology described. No producer is among them, which is what lets a segment
    or a deferred range hold this by reference and still settle no decision
    later.
    """

    entity: EntityMetadata
    view: InheritanceEntityView
    shape: TransactionTimeOnly | Bitemporal
    instant: dt.datetime
    close: SettledClose | None
    resolved_successors: tuple[ResolvedSuccessor, ...]


def close_step(
    facts: TemporalFacts,
    close: SettledClose,
    *,
    key_values: tuple[object, ...],
    observed_valid_end: object | None,
    observed_gate_start: object | None,
) -> PlannedClose:
    """One temporal row's close, from the few observed cells it reads.

    ``observed_gate_start`` is read only for a gated close, and
    ``observed_valid_end`` only for a Bitemporal one.
    """
    return _close(
        facts.entity,
        facts.shape,
        key_attributes=close.key_attributes,
        key_values=key_values,
        observed_valid_end=observed_valid_end,
        cause=close.cause,
        gate=(
            TemporalGate(
                start_attribute=close.gate_start_attribute,
                observed_start=observed_gate_start,
            )
            if close.gated
            else UNGATED
        ),
        instant=facts.instant,
    )


def preserved(
    facts: TemporalFacts, closing: PlannedClose, ownership: Ownership, *, guards: bool
) -> Settled | None:
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
        return Settled(steps=())
    if not guards:
        return None
    guard = PlannedTemporalGuard(
        entity=closing.entity,
        target=closing.target,
        concurrency=concurrency,
        affected_rows=closing.affected_rows,
    )
    return Settled(steps=(guard,))


def successor_step(
    facts: TemporalFacts,
    resolved: ResolvedSuccessor,
    authored_attributes: Mapping[AttributeIdentity, PlannedValue],
    authored_value_objects: Mapping[ValueObjectIdentity, object],
    predecessor: PredecessorRow | None,
    *,
    effective: Iterable[int] | None = None,
) -> PlannedInsert:
    """One resolved successor of one temporal row, as its own Planned Insert.

    Pure in ``facts``: everything it reads was settled into them, so this
    reaches no clock, strategy, model, or facet and can run either eagerly,
    while an instruction settles, or lazily, when a Materialized Write Group's
    segment is asked for one step.

    A carried or changed successor starts from its predecessor's own cells, so
    every member it does not effectively change is the predecessor's cell
    object — the identity lowering patches by (:class:`ChangedFrom`). A changed
    successor overlays only the authored members at the ``effective`` selection
    positions, or every authored member when ``effective`` is absent because
    the row was selected for its one assignment being effective.
    """
    match resolved.state:
        case AuthoredState():
            attributes = dict(authored_attributes)
            value_objects = dict(authored_value_objects)
        case CarriedState():
            assert predecessor is not None  # a carried successor observed one
            attributes, value_objects = predecessor_maps(facts, predecessor)
        case ChangedState():
            assert predecessor is not None  # a changed successor observed one
            selection = facts.view.member_selection
            attributes, value_objects = predecessor_maps(facts, predecessor)
            if effective is None:
                attributes.update(authored_attributes)
                value_objects.update(authored_value_objects)
            else:
                bindings = selection.bindings
                for position in effective:
                    binding = bindings[position]
                    if isinstance(binding, AttributeMetadata):
                        attributes[binding.identity] = authored_attributes[binding.identity]
                    else:
                        value_objects[binding.identity] = authored_value_objects[binding.identity]
    entry = bind_successor(
        resolved,
        facts.shape,
        transaction_instant=facts.instant,
        attributes=attributes,
        value_objects=value_objects,
        predecessor=predecessor,
    )
    return PlannedInsert(entity=facts.entity.identity, entries=(entry,))


def dispose(
    facts: TemporalFacts,
    closing: PlannedClose,
    successors: Sequence[PlannedInsert],
    predecessor: PredecessorRow,
    ownership: Ownership,
    state: ObservedStateKey | None,
) -> Settled:
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
        return Settled(
            steps=(closing, *pieces),
            changed=changed,
            opened=Openings(fresh=openings(facts, pieces)),
        )
    continues = ownership.continues_insertion(own)
    kept_at = kept(facts, own, pieces)
    if kept_at is not None:
        piece = pieces[kept_at]
        others = tuple(other for other in pieces if other is not piece)
        assignments = revision_assignments(facts, piece.entries[0], predecessor)
        if assignments is None:
            return _owned_successors(others, openings(facts, others), continues, ())
        revision = PlannedTemporalRevision(
            entity=closing.entity,
            target=closing.target,
            assignments=assignments,
            concurrency=closing.concurrency,
            affected_rows=closing.affected_rows,
        )
        return _owned_successors((revision, *others), openings(facts, others), continues, changed)
    removal = PlannedTemporalRemoval(
        entity=closing.entity,
        target=closing.target,
        concurrency=closing.concurrency,
        affected_rows=closing.affected_rows,
    )
    return _owned_successors(
        (removal, *pieces), openings(facts, pieces), continues, changed, removed=own
    )


def _owned_successors(
    steps: tuple[PlannedStep, ...],
    opened: tuple[OwnedEndpoint, ...],
    continues: bool,
    changed: tuple[ObservedStateKey, ...],
    removed: OwnedEndpoint | None = None,
) -> Settled:
    """An owned predecessor's effects, its successors continuing the insertion
    that opened it when ``continues``."""
    return Settled(
        steps=steps,
        changed=changed,
        opened=Openings(continued=opened) if continues else Openings(fresh=opened),
        removed=() if removed is None else (removed,),
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
    return (Finite(instant=valid_end), INFINITY)


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


def predecessor_maps(
    facts: TemporalFacts, predecessor: PredecessorRow
) -> tuple[dict[AttributeIdentity, object], dict[ValueObjectIdentity, object]]:
    try:
        return predecessor.identity_maps(facts.view.member_selection)
    except ValueError as refusal:
        raise WritePlanningError(f"{facts.entity.identity.name!r}: {refusal}") from refusal


def _close(
    entity: EntityMetadata,
    shape: TransactionTimeOnly | Bitemporal,
    *,
    key_attributes: tuple[AttributeIdentity, ...],
    key_values: tuple[object, ...],
    observed_valid_end: object | None,
    cause: CloseCause,
    gate: TemporalConcurrency,
    instant: dt.datetime,
) -> PlannedClose:
    """One settled close of the current milestone ``key_values`` addresses.

    Its assignments carry the Transaction-Time end alone — a close ends a
    milestone's currency and revises no represented value — and it expects
    exactly one row in every mode: a close reaching none would otherwise chain
    a duplicate or an orphaned current row, so the shortfall is an outcome
    rather than a silent success.
    """
    return PlannedClose(
        entity=entity.identity,
        target=MilestoneTarget(
            key_attributes=key_attributes,
            key_values=key_values,
            end_attributes=_end_attributes(shape),
            end_values=_end_values(entity, shape, observed_valid_end),
        ),
        assignments=PlannedAssignments(attributes={shape.transaction_time.end_attribute: instant}),
        cause=cause,
        concurrency=gate,
        affected_rows=ExactCount(expected=1, on_shortfall=shortfall_for(gate)),
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
            "per As-Of Axis (m-bitemp-write 'Address and gate are separate')"
        )
    return bitemporal_ends(observed_valid_end)
