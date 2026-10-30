from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from parallax.core.inheritance import InheritanceEntityView, InheritanceFacet
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityMetadata,
    OccurrenceDefinition,
    ValueObjectIdentity,
)
from parallax.core.write_plan.managed_row import ManagedRow
from parallax.core.write_plan.observe import occurrence_value
from parallax.core.write_plan.steps import (
    KeyTarget,
    PlannedAssignments,
    PlannedValue,
    adopt_planned_assignments,
)

__all__ = [
    "WritePlanningError",
    "entity_view",
    "key_target",
    "key_tuple",
    "planned_assignments",
    "planned_row",
]


class WritePlanningError(ValueError):
    """A buffered write cannot be settled into a Planned Step — a caller
    wiring defect the planner refuses loudly rather than settling wrongly
    (e.g. an addressed row omitting the key it selects by)."""


def planned_row(
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
    if version is None:
        return row
    attribute, initial_value = version
    return row.with_cell(row.selection.members.index[attribute], initial_value)


def planned_assignments(row: ManagedRow, *, without: int = 0) -> PlannedAssignments:
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
            attributes[cast("AttributeIdentity", identity)] = value
        else:
            declared = cast("OccurrenceDefinition", shape[position])
            value_objects[cast("ValueObjectIdentity", identity)] = occurrence_value(
                value, declared, absent
            )
    return adopt_planned_assignments(attributes, value_objects)


def entity_view(families: InheritanceFacet, entity: EntityMetadata) -> InheritanceEntityView:
    """``entity``'s compiled family-effective view — its applicable member
    chain, the indices a write row's names resolve through, and the family key.

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
