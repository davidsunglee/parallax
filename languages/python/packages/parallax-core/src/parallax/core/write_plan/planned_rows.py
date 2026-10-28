from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final, cast

from parallax.core.inheritance import InheritanceEntityView, InheritanceFacet
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityMetadata,
    OccurrenceDefinition,
    ValueObjectIdentity,
)
from parallax.core.write_plan.managed_row import ManagedRow, managed_row
from parallax.core.write_plan.observe import occurrence_value
from parallax.core.write_plan.steps import (
    MAX_PLUS_ONE,
    KeyTarget,
    PlannedAssignments,
    PlannedValue,
    SelfIncrement,
    adopt_planned_assignments,
)

__all__ = [
    "WritePlanningError",
    "entity_view",
    "key_target",
    "key_tuple",
    "planned_assignments",
    "planned_cell",
    "planned_cells",
    "planned_row",
]

# A scalar cell's recognized DB-computed marker kinds
# (`write-instruction.schema.json#/$defs/writeComputedMarker`), classified by
# SHAPE — a one-key mapping naming one of them. A Value Object occurrence never
# reaches this classification: its member resolves to a ValueObjectIdentity, so
# a marker-shaped document stays a document (m-value-object "Writing" marker
# disambiguation).
_MARKER_KEYS: Final[frozenset[str]] = frozenset({"computed", "increment"})


class WritePlanningError(ValueError):
    """A buffered write cannot be settled into a Planned Step — a caller
    wiring defect the planner refuses loudly rather than settling wrongly
    (e.g. an addressed row omitting the key it selects by)."""


def planned_row(
    entity: EntityMetadata,
    row: ManagedRow,
    version: tuple[AttributeIdentity, int] | None,
) -> ManagedRow:
    """One write row as its finalized semantic contents.

    A versioned Entity's row derives the INITIAL version at its own Attribute
    (`m-opt-lock`), ignoring any value the row carries — the version is
    framework-owned end to end, and the initial value the caller
    already resolved is a constant rather than an observation. ``version`` is
    absent for a temporal successor row, which carries no version column.
    """
    row = planned_cells(entity, row, "insert")
    if version is None:
        return row
    attribute, initial_value = version
    return row.with_cell(row.selection.members.index[attribute], initial_value)


def planned_assignments(
    entity: EntityMetadata, row: ManagedRow, *, without: int = 0
) -> PlannedAssignments:
    """The members ``row`` states, but for the positions the ``without`` mask
    names, as the identity-keyed replacement values one revising step writes."""
    members = row.selection.members
    identities = members.identities
    attribute_count = members.attribute_count
    shape = members.shape.members
    absent = row.selection.absent
    attributes: dict[AttributeIdentity, PlannedValue] = {}
    value_objects: dict[ValueObjectIdentity, object] = {}
    for position, value in row.stated_cells():
        if without >> position & 1:
            continue
        identity = identities[position]
        if position < attribute_count:
            attributes[cast("AttributeIdentity", identity)] = planned_cell(
                entity, shape[position].name, value, "update"
            )
        else:
            declared = cast("OccurrenceDefinition", shape[position])
            value_objects[cast("ValueObjectIdentity", identity)] = occurrence_value(
                value, declared, absent
            )
    return adopt_planned_assignments(attributes, value_objects)


def planned_cells(entity: EntityMetadata, row: ManagedRow, context: str) -> ManagedRow:
    """``row`` with each scalar cell its DB-computed marker names replaced by
    the generated-value expression the marker plans in ``context``
    (:func:`planned_cell`); ``row`` itself where it holds no marker."""
    attribute_count = row.selection.members.attribute_count
    planned: list[object] | None = None
    for index, (position, value) in enumerate(row.stated_cells()):
        if position >= attribute_count:
            break
        if not isinstance(value, Mapping):
            continue
        marker = cast("Mapping[str, object]", value)
        name = row.selection.members.shape.members[position].name
        cell = planned_cell(entity, name, marker, context)
        if cell is marker:
            continue
        if planned is None:
            planned = list(row.cells)
        planned[index] = cell
    if planned is None:
        return row
    return managed_row(row.selection, tuple(planned), row.presence)


def entity_view(families: InheritanceFacet, entity: EntityMetadata) -> InheritanceEntityView:
    """``entity``'s compiled family-effective view — its applicable member
    chain, the indexes a write row's names resolve through, and the family key.

    An inheritance participant declares only its own members while its
    writes name every inherited one, so the applicable chain, not the
    Entity's own declarations, is what a write-side member lookup reads.
    """
    position = families.entity(entity.identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        raise ValueError(f"{entity.identity.canonical}: the model declares no such entity")
    return position


def key_target(
    entity: EntityMetadata,
    key_attributes: tuple[AttributeIdentity, ...],
    rows: Sequence[ManagedRow],
) -> KeyTarget:
    """The rows an addressed keyed write selects, one aligned value tuple each."""
    return KeyTarget(
        key_attributes=key_attributes,
        key_values=tuple(key_tuple(entity, key_attributes, row) for row in rows),
    )


def key_tuple(
    entity: EntityMetadata,
    key_attributes: tuple[AttributeIdentity, ...],
    row: ManagedRow,
) -> tuple[object, ...]:
    """One addressed row's aligned primary-key values.

    A row that omits a key member addresses nothing, so it is refused here
    rather than settled into a target with a missing value.
    """
    values: list[object] = []
    absent = row.selection.absent
    for attribute in key_attributes:
        value = row.cell(attribute)
        if value is absent:
            raise WritePlanningError(
                f"{entity.identity.name!r}: an addressed write row omits the primary-key "
                f"member {attribute.name!r}, so it selects no row"
            )
        values.append(value)
    return tuple(values)


def planned_cell(entity: EntityMetadata, name: str, value: object, context: str) -> PlannedValue:
    """``value`` as a planned cell: an ordinary literal, or the closed
    generated-value expression its DB-computed marker names.

    Each `m-pk-gen` allocation is legal only where the statement that renders
    it can express it: `max` folds into the row an insert opens, and the
    registry advance reads the very row an update revises. Reaching the other
    position names no allocation this target supports, and is refused here
    rather than settled wrongly.
    """
    marker = _marker(value)
    if marker is None:
        return value
    kind, payload = marker
    if kind == "computed" and context == "insert":
        if payload != "maxPlusOne":
            raise WritePlanningError(
                f"unsupported DB-computed marker on {entity.identity.name!r}.{name}: "
                f"{payload!r} is not a recognized `computed` strategy (m-pk-gen)"
            )
        return MAX_PLUS_ONE
    if kind == "increment" and context == "update":
        return SelfIncrement(amount=cast("int", payload))
    raise WritePlanningError(
        f"unsupported DB-computed marker on {entity.identity.name!r}.{name}: a {kind!r} "
        f"marker is not recognized for {context} planning"
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
