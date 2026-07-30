"""``parallax.snapshot.handle._finalize`` — buffered intent to finalized steps.

:func:`finalize_item` turns one execution-ordered item of a flush plan into the
Planned Writes it executes as: the semantic half of write finalization, where a
neutral write instruction's member spellings resolve to Attribute and Value
Object identities, framework-owned values are derived, a database-computed
marker is classified once into the closed generated-value vocabulary, and the
concurrency mode is spent — deciding the gate, the version advance, and the
shortfall classification — so nothing downstream reads it again. Nothing here
reads a dialect, renders SQL, or names a physical column; those are
:mod:`parallax.snapshot.handle._step_lowering`'s answer to the already-settled
step.

Families this seam does not yet finalize answer ``None`` and keep their existing
lowering. Resolving the target and its family membership belongs here because an
instruction names its entity the way its canonical document spells it, and an
inheritance participant declares its members on the family root alone (ADR 0026).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final, cast

from parallax.core import inheritance, opt_lock
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityMetadata,
    Metamodel,
    ValueObjectIdentity,
)
from parallax.core.unit_work import (
    ANY_COUNT,
    MAX_PLUS_ONE,
    MISSING_TARGET,
    NEW_LINEAGE,
    OPTIMISTIC_CONFLICT,
    STALE_WRITE,
    UNGATED,
    UNVERSIONED,
    Concurrency,
    ExactCount,
    InsertEntry,
    KeyedWrite,
    KeyTarget,
    NonTemporalConcurrency,
    PlannedAssignments,
    PlannedDelete,
    PlannedInsert,
    PlannedRow,
    PlannedUpdate,
    PlannedValue,
    PlannedWrite,
    PredicateTarget,
    PredicateWrite,
    SelfIncrement,
    Shortfall,
    Versioned,
    VersionGate,
    WriteObservation,
)
from parallax.core.unit_work.planned import PlannedWrite as PlannedStep
from parallax.snapshot.handle._family import (
    assignment_member,
    declaring,
    entity_of,
    family_primary_key,
    version_attribute,
)
from parallax.snapshot.handle._write_types import WriteLoweringError

__all__ = ["finalize_item"]

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
    planned: PlannedWrite, meta: Metamodel, concurrency: Concurrency
) -> tuple[PlannedStep, ...] | None:
    """The Planned Writes ``planned`` executes as, or ``None`` when its family
    still lowers from the instruction itself.

    A non-temporal ``insert``, ``update``, or ``delete`` — single-row, or the
    multi-row shape the planner's collapse stage produced — and a readless
    predicate ``update`` or ``delete`` each become exactly one step. Every other
    family answers ``None``.

    ``concurrency`` is spent here: it decides whether an observation-requiring
    write gates, and therefore how a shortfall against the step's expected effect
    classifies. It is the last point at which the mode is a question.
    """
    instruction = planned.instruction
    if isinstance(instruction, PredicateWrite):
        return _finalize_predicate(instruction, meta)
    if instruction.mutation not in _FINALIZED_VERBS:
        return None
    entity = entity_of(meta, instruction.entity)
    declaring_entity = declaring(meta, entity)
    if declaring_entity.declared_as_of_axes:
        return None
    version_attr = version_attribute(meta, declaring_entity)
    members = _members(meta, entity)
    if instruction.mutation == "insert":
        return (_finalize_insert(entity, members, instruction, version_attr),)
    observed_version = _observed_version(entity, instruction, version_attr, planned.observation)
    settled = _concurrency(version_attr, observed_version, concurrency)
    key_attributes = tuple(attribute.identity for attribute in family_primary_key(meta, entity))
    target = _key_target(entity, key_attributes, instruction.rows)
    affected_rows = ExactCount(expected=len(target.key_values), on_shortfall=_shortfall(settled))
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


def _finalize_predicate(
    instruction: PredicateWrite, meta: Metamodel
) -> tuple[PlannedStep, ...] | None:
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
            "reaching lower_write (m-opt-lock; ADR 0014); this is a caller wiring defect"
        )
    if instruction.mutation not in _READLESS_VERBS:
        return None
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
    """The rows an addressed keyed write selects, one aligned value tuple each.

    A row that omits a key member addresses nothing, so it is refused here rather
    than lowered into a predicate with a missing bind.
    """
    values: list[tuple[object, ...]] = []
    for row in rows:
        tuple_values: list[object] = []
        for attribute in key_attributes:
            if attribute.name not in row:
                raise WriteLoweringError(
                    f"{entity.identity.name!r}: an addressed write row omits the primary-key "
                    f"member {attribute.name!r}, so it selects no row"
                )
            tuple_values.append(row[attribute.name])
        values.append(tuple(tuple_values))
    return KeyTarget(key_attributes=key_attributes, key_values=tuple(values))


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


def _shortfall(settled: NonTemporalConcurrency) -> Shortfall:
    """How a shortfall against an addressed write's expected effect classifies.

    Classification follows the settled GATE, never the verb (ADR 0044/0047): a
    gated shortfall is the detected lost update a re-read could resolve, while an
    ungated one on an observation-requiring write is the non-retriable stale
    outcome — no gate could have caused it, so it is a consistency violation. An
    observation-free keyed write observed nothing, so its shortfall says only
    that the addressed rows are not there.
    """
    if not isinstance(settled, Versioned):
        return MISSING_TARGET
    return OPTIMISTIC_CONFLICT if isinstance(settled.gate, VersionGate) else STALE_WRITE


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
