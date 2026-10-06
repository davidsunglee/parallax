from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

from parallax.core.inheritance import InheritanceEntityView, InheritanceFacet
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityMetadata,
    ValueObjectIdentity,
    ValueObjectMetadata,
)
from parallax.core.write_plan.steps import (
    MAX_PLUS_ONE,
    KeyTarget,
    PlannedAssignments,
    PlannedRow,
    PlannedValue,
    SelfIncrement,
    adopt_planned_assignments,
    adopt_planned_row,
)

__all__ = [
    "PreparedAssignment",
    "WritePlanningError",
    "assigned_name",
    "entity_view",
    "key_target",
    "key_tuple",
    "planned_assignments",
    "planned_cell",
    "planned_row",
    "prepared_assignments",
    "resolve_row",
    "resolved_assignments",
]

# A scalar cell's recognized DB-computed marker kinds
# (`write-instruction.schema.json#/$defs/writeComputedMarker`), classified by
# SHAPE — a one-key mapping naming one of them. A Value Object occurrence never
# reaches this classification: its member resolves to a ValueObjectIdentity, so
# a marker-shaped document stays a document (m-value-object "Writing" marker
# disambiguation).
_MARKER_KEYS: Final[frozenset[str]] = frozenset({"computed", "increment"})


class WritePlanningError(ValueError):
    """A buffered write cannot be settled into a Planned Write — a caller
    wiring defect the planner refuses loudly rather than settling wrongly
    (e.g. a materializing predicate write that reached planning un-decomposed,
    or a row naming a member outside its Entity's family)."""


@dataclass(frozen=True, slots=True)
class PreparedAssignment:
    """One resolved assignment member and its owned managed value."""

    member: AttributeMetadata | ValueObjectMetadata
    value: object

    @property
    def attr(self) -> str:
        if isinstance(self.member, AttributeMetadata):
            return f"{self.member.identity.entity.canonical}.{self.member.identity.name}"
        return f"{self.member.identity.entity.canonical}.{self.member.identity.path[-1]}"


def planned_row(
    entity: EntityMetadata,
    view: InheritanceEntityView,
    row: Mapping[str, object],
    version: tuple[AttributeIdentity, int] | None,
) -> PlannedRow:
    """One write row as its finalized semantic contents.

    A versioned Entity's row derives the INITIAL version at its own Attribute
    (`m-opt-lock`), ignoring any value the row carries — the version is
    framework-owned end to end, and the initial value the caller
    already resolved is a constant rather than an observation. ``version`` is
    absent for a temporal successor row, which carries no version column.
    """
    attributes, value_objects = resolve_row(entity, view, row, context="insert")
    if version is not None:
        attribute, initial_value = version
        attributes[attribute] = initial_value
    return adopt_planned_row(attributes, value_objects)


def planned_assignments(
    entity: EntityMetadata,
    view: InheritanceEntityView,
    row: Mapping[str, object],
) -> PlannedAssignments:
    attributes, value_objects = resolve_row(entity, view, row, context="update")
    return adopt_planned_assignments(attributes, value_objects)


def prepared_assignments(
    entity: EntityMetadata, assignments: Sequence[PreparedAssignment]
) -> PlannedAssignments:
    """Resolved predicate assignments in their final member-identity maps."""
    attributes, value_objects = resolved_assignments(entity, assignments, "update")
    return adopt_planned_assignments(attributes, value_objects)


def resolved_assignments(
    entity: EntityMetadata, assignments: Sequence[PreparedAssignment], context: str
) -> tuple[dict[AttributeIdentity, PlannedValue], dict[ValueObjectIdentity, object]]:
    """Prepared assignments keyed by member identity, each Attribute cell's
    marker classified for ``context``."""
    attributes: dict[AttributeIdentity, PlannedValue] = {}
    value_objects: dict[ValueObjectIdentity, object] = {}
    for assignment in assignments:
        member = assignment.member
        if isinstance(member, AttributeMetadata):
            attributes[member.identity] = planned_cell(
                entity, member.identity.name, assignment.value, context
            )
        else:
            value_objects[member.identity] = assignment.value
    return attributes, value_objects


def assigned_name(assignment: PreparedAssignment) -> str:
    """The declared member name one prepared assignment writes."""
    identity = assignment.member.identity
    return identity.name if isinstance(identity, AttributeIdentity) else identity.path[-1]


def resolve_row(
    entity: EntityMetadata,
    view: InheritanceEntityView,
    row: Mapping[str, object],
    *,
    context: str | None,
) -> tuple[dict[AttributeIdentity, PlannedValue], dict[ValueObjectIdentity, object]]:
    """``row``'s cells under their resolved member identities, read off the
    family-effective indexes the Inheritance Facet compiled once.

    A Value Object occurrence is consulted FIRST, so an occurrence sharing a
    name with an applicable Attribute still claims the cell.
    """
    attributes: dict[AttributeIdentity, PlannedValue] = {}
    value_objects: dict[ValueObjectIdentity, object] = {}
    for name, value in row.items():
        occurrence = view.applicable_value_object(name)
        if occurrence is not None:
            value_objects[occurrence.identity] = value
            continue
        attribute = view.applicable_attribute(name)
        if attribute is None:
            raise WritePlanningError(
                f"{entity.identity.name!r}: write row names {name!r}, which is not a member "
                "of the Entity's family"
            )
        attributes[attribute.identity] = (
            value if context is None else planned_cell(entity, name, value, context)
        )
    return attributes, value_objects


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
    rows: Sequence[Mapping[str, object]],
) -> KeyTarget:
    """The rows an addressed keyed write selects, one aligned value tuple each."""
    return KeyTarget(
        key_attributes=key_attributes,
        key_values=tuple(key_tuple(entity, key_attributes, row) for row in rows),
    )


def key_tuple(
    entity: EntityMetadata,
    key_attributes: tuple[AttributeIdentity, ...],
    row: Mapping[str, object],
) -> tuple[object, ...]:
    """One addressed row's aligned primary-key values.

    A row that omits a key member addresses nothing, so it is refused here
    rather than settled into a target with a missing value.
    """
    values: list[object] = []
    for attribute in key_attributes:
        if attribute.name not in row:
            raise WritePlanningError(
                f"{entity.identity.name!r}: an addressed write row omits the primary-key "
                f"member {attribute.name!r}, so it selects no row"
            )
        values.append(row[attribute.name])
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
