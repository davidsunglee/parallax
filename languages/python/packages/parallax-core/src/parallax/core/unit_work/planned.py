"""The finalized Planned Write algebra (m-unit-work).

A Planned Write is one finalized semantic execution step: its target, row
topology, concurrency decision, and expected effect are all settled, so SQL
lowering answers a purely physical question about it. The algebra is **closed**
and **semantic** — it carries Attribute and Value Object identities, never a
physical column, dialect object, driver value, or SQL fragment — and it admits
no generic disposition field: an Insert Origin exists only on an insert entry,
so a label a variant could contradict is unrepresentable rather than merely
invalid.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

from parallax.core.metamodel import AttributeIdentity, EntityIdentity, ValueObjectIdentity

__all__ = [
    "MAX_PLUS_ONE",
    "NEW_LINEAGE",
    "GeneratedValueExpression",
    "InsertEntry",
    "InsertOrigin",
    "MaxPlusOne",
    "NewLineage",
    "PlannedInsert",
    "PlannedRow",
    "PlannedValue",
    "PlannedWrite",
]


@dataclass(frozen=True, slots=True)
class MaxPlusOne:
    """The `max` primary-key allocation (m-pk-gen), as a planned cell value.

    The allocation folds into the emitted statement rather than binding a
    literal, so the planner decides *that* a cell is allocated this way and
    lowering decides how that reads in one dialect.
    """


MAX_PLUS_ONE: Final[MaxPlusOne] = MaxPlusOne()

type GeneratedValueExpression = MaxPlusOne
"""The closed set of database-computed cell values a Planned Row may carry.

A generated value is decided during planning, from the target's declared
primary-key generation strategy, so no consumer re-classifies an authored
marker document by its shape.
"""

type PlannedValue = object
"""One planned cell: a neutral value, an explicit null, or a
:data:`GeneratedValueExpression`.

Python carries every neutral value natively, so the alias names the position
rather than narrowing it; the generated-value arm is the only one a consumer
distinguishes structurally.
"""


@dataclass(frozen=True, slots=True)
class NewLineage:
    """An insert that begins a new Provenance Lineage."""


NEW_LINEAGE: Final[NewLineage] = NewLineage()

type InsertOrigin = NewLineage
"""Where one insert entry's represented state came from.

Origin belongs to each entry rather than to the whole step or to a parallel
array, so entries of different origins may share one Planned Insert.
"""


@dataclass(frozen=True, slots=True)
class PlannedRow:
    """The immutable, duplicate-free semantic contents of one insert entry.

    ``attributes`` holds every scalar member the row writes — including the
    framework-owned values the planner derived, which no caller authors — and
    ``value_objects`` holds one complete occurrence per top-level Value Object
    member. Both are frozen at construction; a row carrying no member at all is
    refused, because it names nothing to write.
    """

    attributes: Mapping[AttributeIdentity, PlannedValue]
    value_objects: Mapping[ValueObjectIdentity, object] = field(
        default_factory=dict[ValueObjectIdentity, object]
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "attributes", MappingProxyType(dict(self.attributes)))
        object.__setattr__(self, "value_objects", MappingProxyType(dict(self.value_objects)))
        if not self.attributes and not self.value_objects:
            raise ValueError("a Planned Row carries at least one member")

    @property
    def members(self) -> frozenset[AttributeIdentity | ValueObjectIdentity]:
        """Every member identity this row writes, scalar and Value Object alike."""
        return frozenset(self.attributes) | frozenset(self.value_objects)


@dataclass(frozen=True, slots=True)
class InsertEntry:
    """One row of a Planned Insert, with the origin of the state it carries."""

    row: PlannedRow
    origin: InsertOrigin


@dataclass(frozen=True, slots=True)
class PlannedInsert:
    """One or more new rows of one Entity, planned as a single execution step.

    Membership *is* the batching decision, so there is no batch flag and no
    group identifier: every entry of one step names the same members and the
    same generated-value shape, and incompatible entries form separate steps.
    A Planned Insert carries no Write Target, no gate, and no Affected Rows
    Policy.
    """

    entity: EntityIdentity
    entries: tuple[InsertEntry, ...]

    def __post_init__(self) -> None:
        if not self.entries:
            raise ValueError(
                f"{self.entity.canonical}: a Planned Insert carries at least one entry"
            )
        first = self.entries[0].row
        for entry in self.entries[1:]:
            if entry.row.members != first.members:
                raise ValueError(
                    f"{self.entity.canonical}: every entry of one Planned Insert names the "
                    "same members, and these differ"
                )
            if _generated_values(entry.row) != _generated_values(first):
                raise ValueError(
                    f"{self.entity.canonical}: every entry of one Planned Insert carries the "
                    "same generated-value shape, and these differ"
                )


def _generated_values(row: PlannedRow) -> dict[AttributeIdentity, GeneratedValueExpression]:
    return {
        identity: value
        for identity, value in row.attributes.items()
        if isinstance(value, MaxPlusOne)
    }


type PlannedWrite = PlannedInsert
"""The closed algebra of finalized semantic execution steps."""
