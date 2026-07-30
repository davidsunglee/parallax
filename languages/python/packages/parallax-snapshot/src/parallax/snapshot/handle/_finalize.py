"""``parallax.snapshot.handle._finalize`` — buffered intent to finalized steps.

:func:`finalize_item` turns one execution-ordered item of a flush plan into the
Planned Writes it executes as: the semantic half of write finalization, where a
neutral write instruction's member spellings resolve to Attribute and Value
Object identities, framework-owned values are derived, and a database-computed
marker is classified once into the closed generated-value vocabulary. Nothing
here reads a dialect, renders SQL, or names a physical column — those are
:mod:`parallax.snapshot.handle._step_lowering`'s answer to the already-settled
step.

Families this seam does not yet finalize answer ``None`` and keep their existing
lowering. Resolving the target and its family membership belongs here because an
instruction names its entity the way its canonical document spells it, and an
inheritance participant declares its members on the family root alone (ADR 0026).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, cast

from parallax.core import inheritance, opt_lock
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityMetadata,
    Metamodel,
    ValueObjectIdentity,
)
from parallax.core.unit_work import KeyedWrite, PlannedWrite
from parallax.core.unit_work.planned import (
    MAX_PLUS_ONE,
    NEW_LINEAGE,
    InsertEntry,
    PlannedInsert,
    PlannedRow,
    PlannedValue,
)
from parallax.snapshot.handle._family import declaring, entity_of, version_attribute
from parallax.snapshot.handle._write_types import WriteLoweringError

__all__ = ["finalize_item"]

# The one keyed mutation verb this seam finalizes. `insertUntil` and the
# milestone verbs open, split, or close a milestone rather than add a row, and a
# temporal entity's plain `insert` opens one too, so neither is this shape.
_FINALIZED_VERBS: Final[frozenset[str]] = frozenset({"insert"})

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


def finalize_item(planned: PlannedWrite, meta: Metamodel) -> tuple[PlannedInsert, ...] | None:
    """The Planned Writes ``planned`` executes as, or ``None`` when its family
    still lowers from the instruction itself.

    A non-temporal ``insert`` — single-row, or the multi-row shape the planner's
    collapse stage produced — becomes exactly one :class:`PlannedInsert` whose
    entries follow the instruction's own row order. Every other family answers
    ``None``.
    """
    instruction = planned.instruction
    if not isinstance(instruction, KeyedWrite) or instruction.mutation not in _FINALIZED_VERBS:
        return None
    entity = entity_of(meta, instruction.entity)
    declaring_entity = declaring(meta, entity)
    if declaring_entity.declared_as_of_axes:
        return None
    version_attr = version_attribute(meta, declaring_entity)
    members = _members(meta, entity)
    entries = tuple(
        InsertEntry(row=_planned_row(entity, members, row, version_attr), origin=NEW_LINEAGE)
        for row in instruction.rows
    )
    return (PlannedInsert(entity=entity.identity, entries=entries),)


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
            attributes[member] = _cell(entity, name, value)
    if version_attr is not None:
        attributes[version_attr.identity] = opt_lock.INITIAL_VERSION
    return PlannedRow(attributes=attributes, value_objects=value_objects)


def _cell(entity: EntityMetadata, name: str, value: object) -> PlannedValue:
    """``value`` as a planned scalar cell: an ordinary literal, or the closed
    generated-value expression its DB-computed marker names.

    An ``increment`` marker is a self-referential advance an inserted row has
    nothing to advance from, and an unrecognized ``computed`` strategy names no
    allocation this target supports; both are refused here rather than rendered
    wrongly (`m-pk-gen`).
    """
    marker = _marker(value)
    if marker is None:
        return value
    kind, strategy = marker
    if kind != "computed":
        raise WriteLoweringError(
            f"unsupported DB-computed marker on {entity.identity.name!r}.{name}: a {kind!r} "
            "marker is not recognized for insert lowering"
        )
    if strategy != "maxPlusOne":
        raise WriteLoweringError(
            f"unsupported DB-computed marker on {entity.identity.name!r}.{name}: "
            f"{strategy!r} is not a recognized `computed` strategy (m-pk-gen)"
        )
    return MAX_PLUS_ONE


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
