"""``parallax.snapshot.handle._finalize`` — buffered intent to finalized steps.

:func:`finalize_item` turns one execution-ordered item of a flush plan into the
Planned Writes it executes as: the semantic half of write finalization, where a
neutral write instruction's member spellings resolve to Attribute and Value
Object identities, framework-owned values are derived, a database-computed
marker is classified once into the closed generated-value vocabulary, temporal
topology is expanded in place, and the concurrency mode is spent — deciding the
gate, the version advance, and the shortfall classification — so nothing
downstream reads it again. Nothing here reads a dialect, renders SQL, or names a
physical column; those are
:mod:`parallax.snapshot.handle._step_lowering`'s answer to the already-settled
step.

Temporal expansion belongs here rather than in lowering precisely because it
needs no dialect: the temporal facets answer one neutral topology per authored
mutation, and this seam resolves that topology against the observed predecessor,
the authored row, and the attempt's Transaction Instant. It is the only place
that instant is consulted, so a flush declaring no Transaction-Time boundary
never reads the Clock Strategy at all.

Resolving the target and its family membership belongs here because an
instruction names its entity the way its canonical document spells it, and an
inheritance participant declares its members on the family root alone (ADR 0026).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final, cast

from parallax.core import bitemp_write, inheritance, opt_lock, txtime_write
from parallax.core.base import INFINITY_LITERAL
from parallax.core.metamodel import (
    AsOfAxisMetadata,
    AttributeIdentity,
    AttributeMetadata,
    EntityMetadata,
    Metamodel,
    TemporalDimension,
    ValueObjectIdentity,
)
from parallax.core.unit_work import (
    ANY_COUNT,
    INFINITY,
    LATEST_PINNED,
    MAX_PLUS_ONE,
    NEW_LINEAGE,
    SUPERSEDED,
    UNGATED,
    UNVERSIONED,
    CloseCause,
    Concurrency,
    ExactCount,
    Finite,
    InsertEntry,
    KeyedWrite,
    KeyTarget,
    MilestoneTarget,
    NonTemporalConcurrency,
    PlannedAssignments,
    PlannedClose,
    PlannedDelete,
    PlannedInsert,
    PlannedRow,
    PlannedUpdate,
    PlannedValue,
    PlannedWrite,
    PredicateTarget,
    PredicateWrite,
    SelfIncrement,
    TemporalAxes,
    TemporalConcurrency,
    TemporalGate,
    TemporalObservation,
    TemporalStrategy,
    TemporalUpperBound,
    TransactionInstant,
    Versioned,
    VersionGate,
    WriteObservation,
    expand_milestone,
    shortfall_for,
)
from parallax.core.unit_work.planned import PlannedWrite as PlannedStep
from parallax.snapshot.handle._family import (
    assignment_member,
    declaring,
    entity_of,
    family_primary_key,
    tx_time_axis,
    version_attribute,
)
from parallax.snapshot.handle._write_types import WriteLoweringError

__all__ = ["finalize_item", "plan_temporal_close"]

# The keyed mutation verbs this seam finalizes — the non-temporal write triad.
# The milestone verbs open, split, or close a milestone rather than write a row
# outright, and a temporal entity's own `insert` opens one too, so neither is
# this shape.
_FINALIZED_VERBS: Final[frozenset[str]] = frozenset({"insert", "update", "delete"})

# The predicate-selected verbs a readless template exists for. A `terminate` or
# `*Until` predicate write names a milestone, so its only legal targets
# materialize to keyed writes long before finalization.
_READLESS_VERBS: Final[frozenset[str]] = frozenset({"update", "delete"})

# A scalar cell's recognized DB-computed marker kinds
# (`write-instruction.schema.json#/$defs/writeComputedMarker`), classified by
# SHAPE — a one-key mapping naming one of them. A Value Object occurrence never
# reaches this classification: its member resolves to a
# :class:`ValueObjectIdentity`, so a marker-shaped document stays a document
# (m-value-object "Writing" marker disambiguation).
_MARKER_KEYS: Final[frozenset[str]] = frozenset({"computed", "increment"})

# One writable member's resolved semantic identity, keyed by the spelling a
# write row names it with.
type _Members = Mapping[str, AttributeIdentity | ValueObjectIdentity]


def finalize_item(
    planned: PlannedWrite,
    meta: Metamodel,
    concurrency: Concurrency,
    tx_instant: TransactionInstant,
) -> tuple[PlannedStep, ...]:
    """The Planned Writes ``planned`` executes as.

    A non-temporal ``insert``, ``update``, or ``delete`` — single-row, or the
    multi-row shape the planner's collapse stage produced — and a readless
    predicate ``update`` or ``delete`` each become exactly one step. A temporal
    mutation expands in place into one Planned Close followed immediately by its
    Planned Insert successors, in the facet's canonical order.

    ``concurrency`` is spent here: it decides whether an observation-requiring
    write gates, and therefore how a shortfall against the step's expected effect
    classifies. It is the last point at which the mode is a question.
    ``tx_instant`` is the attempt's lazy Transaction Instant, consulted only by a
    temporal mutation — the only family that declares a Transaction-Time
    boundary.
    """
    instruction = planned.instruction
    if isinstance(instruction, PredicateWrite):
        return _finalize_predicate(instruction, meta)
    entity = entity_of(meta, instruction.entity)
    declaring_entity = declaring(meta, entity)
    if declaring_entity.declared_as_of_axes:
        return _finalize_temporal(
            entity,
            declaring_entity,
            instruction,
            meta,
            concurrency,
            planned.observation,
            tx_instant,
        )
    if instruction.mutation not in _FINALIZED_VERBS:
        raise WriteLoweringError(
            f"{instruction.mutation!r} is a temporal milestone verb, and "
            f"{entity.identity.name!r} declares no temporal dimension — a milestone verb never "
            "applies to a non-temporal entity (m-txtime-write / m-bitemp-write)"
        )
    version_attr = version_attribute(meta, declaring_entity)
    members = _members(meta, entity)
    if instruction.mutation == "insert":
        return (_finalize_insert(entity, members, instruction, version_attr),)
    observed_version = _observed_version(entity, instruction, version_attr, planned.observation)
    settled = _concurrency(version_attr, observed_version, concurrency)
    key_attributes = tuple(attribute.identity for attribute in family_primary_key(meta, entity))
    target = _key_target(entity, key_attributes, instruction.rows)
    affected_rows = ExactCount(expected=len(target.key_values), on_shortfall=shortfall_for(settled))
    if instruction.mutation == "delete":
        return (
            PlannedDelete(
                entity=entity.identity,
                target=target,
                concurrency=settled,
                affected_rows=affected_rows,
            ),
        )
    return (
        PlannedUpdate(
            entity=entity.identity,
            target=target,
            assignments=_update_assignments(
                entity, members, instruction, key_attributes, version_attr, observed_version
            ),
            concurrency=settled,
            affected_rows=affected_rows,
        ),
    )


def _finalize_predicate(instruction: PredicateWrite, meta: Metamodel) -> tuple[PlannedStep, ...]:
    """One readless predicate-selected write as its single step.

    The refusals live here, on the semantic side, because they answer what a
    write MEANS rather than how it reads: an inheritance-family target has no
    per-object write to select (`m-inheritance`), and a versioned or temporal
    target has no readless template at all — it materializes to keyed writes at
    buffer time (ADR 0014), so reaching finalization is a caller wiring defect.
    Both guards are total rather than upstream-only: this seam is reached
    straight from a deserialized instruction as well as from the developer verbs.
    """
    entity = entity_of(meta, instruction.target.entity)
    inheritance.reject_predicate_write(entity)
    declaring_entity = declaring(meta, entity)
    if (
        declaring_entity.declared_as_of_axes
        or version_attribute(meta, declaring_entity) is not None
    ):
        raise WriteLoweringError(
            f"{instruction.target.entity!r}: a predicate write on a versioned or temporal "
            "target has no readless template — it must materialize to keyed writes before "
            "reaching finalization (m-opt-lock; ADR 0014); this is a caller wiring defect"
        )
    if instruction.mutation not in _READLESS_VERBS:
        raise WriteLoweringError(
            f"{instruction.target.entity!r}: a readless predicate {instruction.mutation!r} names "
            "a milestone, and every legal milestone target materializes to keyed writes before "
            "finalization (m-batch-write 'Predicate-selected readless forms')"
        )
    target = PredicateTarget(predicate=instruction.target.predicate)
    if instruction.mutation == "delete":
        return (
            PlannedDelete(
                entity=entity.identity,
                target=target,
                concurrency=UNVERSIONED,
                affected_rows=ANY_COUNT,
            ),
        )
    members = _members(meta, entity)
    assignment_row = {
        assignment_member(assignment.attr): assignment.value
        for assignment in instruction.assignments
    }
    return (
        PlannedUpdate(
            entity=entity.identity,
            target=target,
            assignments=_assignments(entity, members, assignment_row),
            concurrency=UNVERSIONED,
            affected_rows=ANY_COUNT,
        ),
    )


def _finalize_insert(
    entity: EntityMetadata,
    members: _Members,
    instruction: KeyedWrite,
    version_attr: AttributeMetadata | None,
) -> PlannedInsert:
    entries = tuple(
        InsertEntry(row=_planned_row(entity, members, row, version_attr), origin=NEW_LINEAGE)
        for row in instruction.rows
    )
    return PlannedInsert(entity=entity.identity, entries=entries)


def _key_target(
    entity: EntityMetadata,
    key_attributes: tuple[AttributeIdentity, ...],
    rows: Sequence[Mapping[str, object]],
) -> KeyTarget:
    """The rows an addressed keyed write selects, one aligned value tuple each."""
    return KeyTarget(
        key_attributes=key_attributes,
        key_values=tuple(_key_tuple(entity, key_attributes, row) for row in rows),
    )


def _key_tuple(
    entity: EntityMetadata,
    key_attributes: tuple[AttributeIdentity, ...],
    row: Mapping[str, object],
) -> tuple[object, ...]:
    """One addressed row's aligned primary-key values.

    A row that omits a key member addresses nothing, so it is refused here rather
    than lowered into a predicate with a missing bind.
    """
    values: list[object] = []
    for attribute in key_attributes:
        if attribute.name not in row:
            raise WriteLoweringError(
                f"{entity.identity.name!r}: an addressed write row omits the primary-key "
                f"member {attribute.name!r}, so it selects no row"
            )
        values.append(row[attribute.name])
    return tuple(values)


# --------------------------------------------------------------------------- #
# Temporal mutations (m-txtime-write / m-bitemp-write).                        #
# The facet answers the neutral topology; this seam resolves it against the    #
# observed predecessor, the authored row, and the attempt's Transaction        #
# Instant, and settles the close's own address, gate, and expected effect.     #
# --------------------------------------------------------------------------- #
def _finalize_temporal(
    entity: EntityMetadata,
    declaring_entity: EntityMetadata,
    instruction: KeyedWrite,
    meta: Metamodel,
    concurrency: Concurrency,
    observation: WriteObservation | None,
    tx_instant: TransactionInstant,
) -> tuple[PlannedStep, ...]:
    """One temporal mutation as its close and its successors, in that order.

    Each row of a milestone chain opens its own successors, so a temporal write
    settles one row at a time: `m-batch-write` never collapses a temporal
    entity, and reaching here with several rows is a caller wiring defect.
    """
    if len(instruction.rows) != 1:
        raise WriteLoweringError(
            f"multi-row temporal {instruction.mutation!r} on {entity.identity.name!r} "
            f"({len(instruction.rows)} rows): a temporal keyed write settles one row at a "
            "time (m-txtime-write / m-bitemp-write) — the set-based batch collapse never "
            "applies to a temporal entity's own milestone chain (m-batch-write)"
        )
    valid_axis = declaring_entity.as_of_axis(TemporalDimension.VALID_TIME)
    strategy: TemporalStrategy = (
        bitemp_write.RECTANGLE_SPLIT if valid_axis is not None else txtime_write.MILESTONE_CHAIN
    )
    topology = strategy.topology(instruction.mutation)
    observed = observation if isinstance(observation, TemporalObservation) else None
    if topology.closure is not None and observed is None:
        raise WriteLoweringError(
            f"{entity.identity.name!r}: a temporal {instruction.mutation!r} closes the current "
            "milestone, and every close requires the Temporal Observation it addresses, gates "
            "on, and carries state forward from (m-unit-work; m-opt-lock)"
        )
    if observed is not None:
        # The REAL licensing check: an engine-supplied observation is
        # latest-pinned by construction, but a developer's own historical or
        # edge-pinned `Transaction.find` took its read lock on a row a
        # locking-mode close would never reach.
        opt_lock.check_locking_license(concurrency, observed.transaction_time_basis)
    tx_axis = tx_time_axis(declaring_entity)
    axes = TemporalAxes(
        transaction_start=tx_axis.start_attribute.name,
        transaction_end=tx_axis.end_attribute.name,
        valid_start=None if valid_axis is None else valid_axis.start_attribute.name,
        valid_end=None if valid_axis is None else valid_axis.end_attribute.name,
    )
    # Reaching a temporal mutation is what makes the attempt capture its
    # instant; the close's new Transaction-Time end and every successor's fresh
    # start derive from that one value.
    instant = tx_instant.value()
    members = _members(meta, entity)
    steps: list[PlannedStep] = []
    if topology.closure is not None:
        assert observed is not None  # refused above
        gate = _gate(declaring_entity, topology.closure.gate_basis, observed, concurrency)
        steps.append(
            _close(
                entity,
                declaring_entity,
                meta,
                identity=instruction.rows[0],
                observed_valid_end=(
                    None
                    if valid_axis is None
                    else observed.predecessor.member(valid_axis.end_attribute.name)
                ),
                cause=topology.closure.cause,
                gate=gate,
                instant=instant,
            )
        )
    steps.extend(
        PlannedInsert(
            entity=entity.identity,
            entries=(
                InsertEntry(
                    row=_planned_row(entity, members, milestone.members, None),
                    origin=milestone.origin,
                ),
            ),
        )
        for milestone in expand_milestone(
            topology,
            axes,
            transaction_instant=instant,
            authored=instruction.rows[0],
            valid_from=instruction.valid_from,
            until=instruction.until,
            predecessor=None if observed is None else observed.predecessor,
        )
    )
    return tuple(steps)


def plan_temporal_close(
    identity: Mapping[str, object],
    entity_name: str,
    meta: Metamodel,
    concurrency: Concurrency,
    tx_instant: TransactionInstant,
    observed_tx_start: object | None,
    observed_valid_end: object | None = None,
) -> PlannedClose:
    """A STANDALONE temporal milestone close — the `m-opt-lock` conflict lane's
    own probe.

    Every real close-bearing mutation chains at least one successor, and a
    conflict probe deliberately runs only the close, so it settles one here
    directly rather than through an authored mutation. ``identity`` is the row
    the address keys on, ``observed_valid_end`` completes that address on a
    Bitemporal target, and ``observed_tx_start`` is the gate candidate; a probe
    names all three explicitly rather than reading them from a tracked
    milestone. The cause it records is supersession — what a real mutation's own
    close performs, and whose successors the probe deliberately does not run.
    """
    entity = entity_of(meta, entity_name)
    declaring_entity = declaring(meta, entity)
    gate: TemporalConcurrency = UNGATED
    if observed_tx_start is not None:
        opt_lock.check_locking_license(concurrency, LATEST_PINNED)
        if opt_lock.gates(concurrency):
            gate = TemporalGate(
                start_attribute=tx_time_axis(declaring_entity).start_attribute,
                observed_start=observed_tx_start,
            )
    return _close(
        entity,
        declaring_entity,
        meta,
        identity=identity,
        observed_valid_end=observed_valid_end,
        cause=SUPERSEDED,
        gate=gate,
        instant=tx_instant.value(),
    )


def _close(
    entity: EntityMetadata,
    declaring_entity: EntityMetadata,
    meta: Metamodel,
    *,
    identity: Mapping[str, object],
    observed_valid_end: object | None,
    cause: CloseCause,
    gate: TemporalConcurrency,
    instant: str,
) -> PlannedClose:
    """One settled close of the current milestone ``identity`` addresses.

    Its assignments carry the Transaction-Time end alone — a close ends a
    milestone's currency and revises no represented value — and it expects
    exactly one row in every mode: a close reaching none would otherwise chain a
    duplicate or an orphaned current row, so the shortfall is an outcome rather
    than a silent success.
    """
    key_attributes = _family_key(meta, entity)
    return PlannedClose(
        entity=entity.identity,
        target=MilestoneTarget(
            key_attributes=key_attributes,
            key_values=_key_tuple(entity, key_attributes, identity),
            end_attributes=tuple(axis.end_attribute for axis in _as_of_axes(declaring_entity)),
            end_values=_end_values(entity, declaring_entity, observed_valid_end),
        ),
        assignments=PlannedAssignments(
            attributes={tx_time_axis(declaring_entity).end_attribute: instant}
        ),
        cause=cause,
        concurrency=gate,
        affected_rows=ExactCount(expected=1, on_shortfall=shortfall_for(gate)),
    )


def _end_values(
    entity: EntityMetadata, declaring_entity: EntityMetadata, observed_valid_end: object | None
) -> tuple[TemporalUpperBound, ...]:
    """One exclusive upper bound per As-Of Axis, in canonical order.

    Transaction Time is invariantly `Infinity`, which is what keeps an
    operational close on a row still current. Valid Time is whatever the
    observed predecessor carries — `Infinity` for a rectangle running to the
    open bound, and a finite instant for a bounded one a prior split left
    behind, so binding a constant on both axes would silently miss every bounded
    sibling.
    """
    values: list[TemporalUpperBound] = []
    for axis in _as_of_axes(declaring_entity):
        if axis.dimension is TemporalDimension.TRANSACTION_TIME:
            values.append(INFINITY)
        elif observed_valid_end is None:
            raise WriteLoweringError(
                f"bitemporal close on {entity.identity.name!r}: no observed Valid-Time end "
                "supplied — a Bitemporal milestone address needs one exclusive upper bound "
                "per As-Of Axis (m-bitemp-write 'Address and gate are separate')"
            )
        elif observed_valid_end == INFINITY_LITERAL:
            values.append(INFINITY)
        else:
            values.append(Finite(instant=observed_valid_end))
    return tuple(values)


def _as_of_axes(declaring_entity: EntityMetadata) -> tuple[AsOfAxisMetadata, ...]:
    """``declaring_entity``'s declared As-Of Axes in canonical order."""
    valid_axis = declaring_entity.as_of_axis(TemporalDimension.VALID_TIME)
    tx_axis = tx_time_axis(declaring_entity)
    return (tx_axis,) if valid_axis is None else (valid_axis, tx_axis)


def _family_key(meta: Metamodel, entity: EntityMetadata) -> tuple[AttributeIdentity, ...]:
    return tuple(attribute.identity for attribute in family_primary_key(meta, entity))


def _gate(
    declaring_entity: EntityMetadata,
    gate_basis: TemporalDimension,
    observed: TemporalObservation,
    concurrency: Concurrency,
) -> TemporalConcurrency:
    """The settled gate decision one close carries.

    Optimistic mode binds the observed start of the axis the facet names as its
    gate basis — the version analogue for an entity carrying no version column.
    Locking mode records the explicit ungated decision, whose shared read lock is
    what makes the close correct instead.
    """
    if not opt_lock.gates(concurrency):
        return UNGATED
    axis = next(axis for axis in _as_of_axes(declaring_entity) if axis.dimension is gate_basis)
    return TemporalGate(
        start_attribute=axis.start_attribute,
        observed_start=observed.predecessor.member(axis.start_attribute.name),
    )


def _observed_version(
    entity: EntityMetadata,
    instruction: KeyedWrite,
    version_attr: AttributeMetadata | None,
    observation: WriteObservation | None,
) -> int | None:
    """The version an addressed write against a versioned row advances from, or
    ``None`` for an unversioned target.

    A row-carried version value is refused BEFORE the observation is even
    required: the version is framework-owned end to end, so it is never an
    alternative source, observed or not. The observation itself is required in
    both concurrency modes, because the framework never issues a resolving read
    on behalf of a keyed write.
    """
    if version_attr is None:
        return None
    if instruction.mutation == "update" and version_attr.identity.name in instruction.rows[0]:
        opt_lock.reject_caller_authored_version(entity.identity.name, version_attr.identity.name)
    return opt_lock.require_observed(entity.identity.name, observation)


def _concurrency(
    version_attr: AttributeMetadata | None,
    observed_version: int | None,
    concurrency: Concurrency,
) -> NonTemporalConcurrency:
    """The settled concurrency decision one addressed non-temporal write carries.

    An unversioned target has nothing to gate on. A versioned one binds its
    observation as a gate under optimistic mode and records an explicit `Ungated`
    decision under locking, whose shared read lock is what makes the write
    correct instead (ADR 0047).
    """
    if version_attr is None or observed_version is None:
        return UNVERSIONED
    if not opt_lock.gates(concurrency):
        return Versioned(gate=UNGATED)
    return Versioned(
        gate=VersionGate(attribute=version_attr.identity, observed_version=observed_version)
    )


def _members(meta: Metamodel, entity: EntityMetadata) -> _Members:
    """``entity``'s family-effective writable members, by the spelling a write
    row names each one with.

    An inheritance participant declares its own members while its writes name
    every inherited one, so the applicable member chain — not the Entity's own
    declarations — is what a write-side lookup reads.
    """
    position = inheritance.view(meta).entity(entity.identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        return {}
    resolved: dict[str, AttributeIdentity | ValueObjectIdentity] = {
        attribute.identity.name: attribute.identity for attribute in position.applicable_attributes
    }
    for value_object in position.applicable_value_objects:
        resolved[value_object.identity.path[-1]] = value_object.identity
    return resolved


def _planned_row(
    entity: EntityMetadata,
    members: _Members,
    row: Mapping[str, object],
    version_attr: AttributeMetadata | None,
) -> PlannedRow:
    """One write row as its finalized semantic contents.

    A versioned Entity's row derives the INITIAL version at its own Attribute
    (`m-opt-lock`), ignoring any value the row carries: the version is
    framework-owned end to end (ADR 0013), and the initial value is a constant
    rather than an observation.
    """
    attributes, value_objects = _resolve(entity, members, row, context="insert")
    if version_attr is not None:
        attributes[version_attr.identity] = opt_lock.INITIAL_VERSION
    return PlannedRow(attributes=attributes, value_objects=value_objects)


def _update_assignments(
    entity: EntityMetadata,
    members: _Members,
    instruction: KeyedWrite,
    key_attributes: tuple[AttributeIdentity, ...],
    version_attr: AttributeMetadata | None,
    observed_version: int | None,
) -> PlannedAssignments:
    """The replacement values an addressed update writes.

    Key members address the write rather than change it, so they never appear
    among the assignments. A collapsed multi-row update assigns identical values
    to every key it addresses (`m-batch-write` refuses to collapse anything
    else), so the first row settles the whole step's assignments. A versioned
    target advances the version in BOTH modes, which is why the advance is an
    assignment rather than a gate member.
    """
    key_names = frozenset(attribute.name for attribute in key_attributes)
    row = instruction.rows[0]
    assigned = {name: value for name, value in row.items() if name not in key_names}
    assignments = _assignments(entity, members, assigned)
    if version_attr is None or observed_version is None:
        return assignments
    return PlannedAssignments(
        attributes={
            **assignments.attributes,
            version_attr.identity: opt_lock.advance(observed_version),
        },
        value_objects=assignments.value_objects,
    )


def _assignments(
    entity: EntityMetadata, members: _Members, row: Mapping[str, object]
) -> PlannedAssignments:
    attributes, value_objects = _resolve(entity, members, row, context="update")
    return PlannedAssignments(attributes=attributes, value_objects=value_objects)


def _resolve(
    entity: EntityMetadata, members: _Members, row: Mapping[str, object], *, context: str
) -> tuple[dict[AttributeIdentity, PlannedValue], dict[ValueObjectIdentity, object]]:
    """``row``'s cells under their resolved member identities."""
    attributes: dict[AttributeIdentity, PlannedValue] = {}
    value_objects: dict[ValueObjectIdentity, object] = {}
    for name, value in row.items():
        member = members.get(name)
        if member is None:
            raise WriteLoweringError(
                f"{entity.identity.name!r}: write row names {name!r}, which is not a member "
                "of the Entity's family"
            )
        if isinstance(member, ValueObjectIdentity):
            value_objects[member] = value
        else:
            attributes[member] = _cell(entity, name, value, context)
    return attributes, value_objects


def _cell(entity: EntityMetadata, name: str, value: object, context: str) -> PlannedValue:
    """``value`` as a planned cell: an ordinary literal, or the closed
    generated-value expression its DB-computed marker names.

    Each `m-pk-gen` allocation is legal only where the statement that renders it
    can express it: `max` folds into the row an insert opens, and the registry
    advance reads the very row an update revises. Reaching the other position
    names no allocation this target supports, and is refused here rather than
    rendered wrongly.
    """
    marker = _marker(value)
    if marker is None:
        return value
    kind, payload = marker
    if kind == "computed" and context == "insert":
        if payload != "maxPlusOne":
            raise WriteLoweringError(
                f"unsupported DB-computed marker on {entity.identity.name!r}.{name}: "
                f"{payload!r} is not a recognized `computed` strategy (m-pk-gen)"
            )
        return MAX_PLUS_ONE
    if kind == "increment" and context == "update":
        return SelfIncrement(amount=cast("int", payload))
    raise WriteLoweringError(
        f"unsupported DB-computed marker on {entity.identity.name!r}.{name}: a {kind!r} "
        f"marker is not recognized for {context} lowering"
    )


def _marker(value: object) -> tuple[str, object] | None:
    """``value``'s ``(marker key, payload)`` when it is shaped as a DB-computed
    marker, else ``None``. A differently shaped mapping is an ordinary literal."""
    if not isinstance(value, Mapping):
        return None
    marker = cast("Mapping[str, object]", value)
    if len(marker) != 1:
        return None
    key = next(iter(marker))
    return (key, marker[key]) if key in _MARKER_KEYS else None
