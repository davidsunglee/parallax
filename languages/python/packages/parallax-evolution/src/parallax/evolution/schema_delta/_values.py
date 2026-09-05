"""The values and errors a Schema Delta crosses the wheel's boundary as.

Statements leave as plain strings with no wrapper and no per-statement causal
metadata: the physical-operation algebra stays private, and an application
applying a delta already holds the Evolution and observes the statement that
failed. Created-Index provenance is the sole exception, because only a physical
name lets a host correlate a later violation with the rollout that created it.

Both errors are aggregated values raised once with the complete finding set, and
neither returns a partial delta.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from parallax.core.dialect import PhysicalIndexName
from parallax.core.metamodel import AttributeIdentity, Column, IndexIdentity, Table
from parallax.evolution.model_evolution import EvolutionOperation

__all__ = [
    "CollidingIndex",
    "CollisionGroup",
    "CreatedIndex",
    "IndexPresence",
    "PhysicalIndexNameCollisionError",
    "PhysicalLocation",
    "SchemaDelta",
    "UnsupportedSchemaEvolutionError",
    "UnsupportedSchemaOperation",
]


@dataclass(frozen=True, slots=True)
class CreatedIndex:
    """One newly created Index, as a host correlates a later violation with it."""

    physical_index_name: PhysicalIndexName
    physical_table: Table
    logical_index_identity: IndexIdentity
    unique: bool


@dataclass(frozen=True, slots=True)
class SchemaDelta:
    """The ordered dialect statements carrying a database to the later model.

    The statements are prefix-safe in this order and deliberately NOT idempotent:
    none of them says ``if exists`` or ``if not exists``, because a delta states
    what must happen to a database at the earlier edition rather than reconciling
    an unknown one.
    """

    statements: tuple[str, ...]
    created_indices: tuple[CreatedIndex, ...]


@dataclass(frozen=True, slots=True)
class PhysicalLocation:
    """Where one physical operation acts: its Table, and the member within it."""

    table: Table
    column: Column | None = None
    index: PhysicalIndexName | None = None


@dataclass(frozen=True, slots=True)
class UnsupportedSchemaOperation:
    """One physical operation the selected Dialect's renderer cannot spell.

    ``kind`` is the private algebra's own operation name, which is the one part
    of that algebra a caller sees: it is what makes the refusal legible without
    exposing the operation values themselves.
    """

    kind: str
    location: PhysicalLocation
    reason: str
    caused_by: tuple[EvolutionOperation, ...]


class UnsupportedSchemaEvolutionError(Exception):
    """No statement for this Dialect: every operation it cannot render, at once.

    Renderer support is a deployment capability rather than a model-semantic
    fact, so this never reclassifies the dialect-independent Unilateral Evolution
    as coordinated.
    """

    def __init__(
        self, dialect_identity: str, operations: tuple[UnsupportedSchemaOperation, ...]
    ) -> None:
        self.dialect_identity = dialect_identity
        self.operations = operations
        spelled = ", ".join(operation.kind for operation in operations)
        super().__init__(
            f"{dialect_identity} cannot render {len(operations)} operation(s): {spelled}"
        )


class IndexPresence(enum.Enum):
    """Which endpoints of the Evolution hold one colliding Index definition."""

    EARLIER = "earlier"
    LATER = "later"
    BOTH = "both"


@dataclass(frozen=True, slots=True)
class CollidingIndex:
    """One definition of a collision group, in the terms the model authored it."""

    table: Table
    index: IndexIdentity
    components: tuple[AttributeIdentity, ...]
    unique: bool
    presence: IndexPresence


@dataclass(frozen=True, slots=True)
class CollisionGroup:
    """Two or more distinct definitions that derived one Physical Index Name."""

    name: PhysicalIndexName
    definitions: tuple[CollidingIndex, ...]


class PhysicalIndexNameCollisionError(Exception):
    """Distinct Index definitions derived one name; neither was silently renamed.

    A defensive backstop for an unexpected 128-bit fingerprint collision, not an
    ordinary control path: a definition's name is derived from its own facts
    alone, so it is stable independently of every other Index in the model.
    """

    def __init__(self, dialect_identity: str, groups: tuple[CollisionGroup, ...]) -> None:
        self.dialect_identity = dialect_identity
        self.groups = groups
        spelled = ", ".join(group.name.value for group in groups)
        super().__init__(f"{dialect_identity} derived colliding Physical Index Names: {spelled}")
