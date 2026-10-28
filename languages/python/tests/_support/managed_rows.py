from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Metamodel,
    OccurrenceDefinition,
    ValueObjectIdentity,
)
from parallax.core.write_plan.managed_row import (
    ManagedRow,
    RowSelection,
    adopted_row,
    positional_occurrence,
)
from tests._support.write_preparation import write_preparation_of

__all__ = ["managed_row_of", "row_selection_of"]


def row_selection_of(model: Metamodel, entity: EntityIdentity) -> RowSelection:
    """The row selection production prepares ``entity``'s rows of."""
    return write_preparation_of(model).entity(entity).selection


def managed_row_of(
    model: Metamodel,
    attributes: Mapping[AttributeIdentity, object],
    value_objects: Mapping[ValueObjectIdentity, object] | None = None,
    *,
    entity: EntityIdentity | None = None,
) -> ManagedRow:
    """The Managed Row stating ``attributes`` and ``value_objects`` by
    identity, each occurrence document in its positional form; ``entity``
    defaults to the Entity the first member is addressed at."""
    occurrences = value_objects or {}
    if entity is None:
        entity = next(iter([*attributes, *occurrences])).entity
    selection = row_selection_of(model, entity)
    index = selection.members.index
    members = selection.members.shape.members
    cells: list[object] = [selection.absent] * selection.width
    for identity, value in attributes.items():
        cells[index[identity]] = value
    for identity, value in occurrences.items():
        position = index[identity]
        cells[position] = positional_occurrence(
            value, cast("OccurrenceDefinition", members[position]), selection.absent
        )
    return adopted_row(selection, tuple(cells))
