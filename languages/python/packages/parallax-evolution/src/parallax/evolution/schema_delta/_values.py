from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Final, Literal

from parallax.core.base import UnsupportedError
from parallax.core.dialect import PhysicalIndexName
from parallax.core.metamodel import AttributeIdentity, Column, IndexIdentity, Table
from parallax.evolution.model_evolution import EvolutionOperation

__all__ = [
    "CollidingIndex",
    "CollidingTemporalConstraint",
    "CollisionGroup",
    "CreatedIndex",
    "IndexPresence",
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
    an unknown one. The one exception is a provider extension a created Table
    requires, which the provider rather than the model owns.
    """

    statements: tuple[str, ...]
    created_indices: tuple[CreatedIndex, ...]


@dataclass(frozen=True, slots=True)
class PhysicalLocation:
    """Where one physical operation acts: its Table and the member within it,
    or the database-wide ``extension`` a tableless prerequisite installs."""

    table: Table | None = None
    column: Column | None = None
    index: PhysicalIndexName | None = None
    extension: str | None = None


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


SCHEMA_EVOLUTION_UNSUPPORTED: Final = "schema-evolution-unsupported"


class UnsupportedSchemaEvolutionError(UnsupportedError):
    """No statement for this Dialect: every operation it cannot render, at once.

    Renderer support is a deployment capability rather than a model-semantic
    fact, so this never reclassifies the dialect-independent Unilateral Evolution
    as coordinated.
    """

    def __init__(
        self, dialect_identity: str, operations: tuple[UnsupportedSchemaOperation, ...]
    ) -> None:
        spelled = ", ".join(operation.kind for operation in operations)
        super().__init__(
            SCHEMA_EVOLUTION_UNSUPPORTED,
            f"{dialect_identity} cannot render {len(operations)} operation(s): {spelled}",
        )
        self.dialect_identity = dialect_identity
        self.operations = operations


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
class CollidingTemporalConstraint:
    """One temporal Table's primary key or exclusion in a collision group.

    Its backing Index shares the schema's Index namespace, but no authored Index
    declares it, so it is reported by its kind and the physical Columns it
    covers in constraint order.
    """

    table: Table
    kind: Literal["primaryKey", "exclusion"]
    columns: tuple[Column, ...]
    presence: IndexPresence


@dataclass(frozen=True, slots=True)
class CollisionGroup:
    """Two or more distinct definitions that derived one Physical Index Name.

    ``definitions`` holds the authored Indices and ``temporal_constraints`` the
    temporal primary keys and exclusions; together they hold at least two.
    """

    name: PhysicalIndexName
    definitions: tuple[CollidingIndex, ...]
    temporal_constraints: tuple[CollidingTemporalConstraint, ...] = ()
