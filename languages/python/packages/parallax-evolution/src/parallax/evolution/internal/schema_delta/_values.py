from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Final, Literal

from parallax.core.internal.base import UnsupportedError
from parallax.core.internal.database_binding import PhysicalTable
from parallax.core.internal.dialect import PhysicalIndexName
from parallax.core.internal.metamodel import AttributeIdentity, Column, IndexIdentity
from parallax.evolution.internal.model_evolution import EvolutionOperation

__all__ = [
    "CollidingIndex",
    "CollidingTemporalConstraint",
    "CollisionGroup",
    "CreatedIndex",
    "IndexPresence",
    "SchemaDelta",
    "SchemaTarget",
    "UnsupportedSchemaEvolutionError",
    "UnsupportedSchemaOperation",
]


@dataclass(frozen=True, slots=True)
class CreatedIndex:
    """An index a schema change creates, so a later violation can be traced to it."""

    physical_index_name: PhysicalIndexName
    physical_table: PhysicalTable
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
class SchemaTarget:
    """The table and member, or database extension, a schema operation acts on.

    Where one physical operation acts: its physical table and the member within
    it, or the database-wide ``extension`` a tableless prerequisite installs.
    """

    table: PhysicalTable | None = None
    column: Column | None = None
    index: PhysicalIndexName | None = None
    extension: str | None = None


@dataclass(frozen=True, slots=True)
class UnsupportedSchemaOperation:
    """An operation the Dialect cannot express as SQL.

    ``kind`` is the private algebra's own operation name, which is the one part
    of that algebra a caller sees: it is what makes the refusal legible without
    exposing the operation values themselves.
    """

    kind: str
    location: SchemaTarget
    reason: str
    caused_by: tuple[EvolutionOperation, ...]


SCHEMA_EVOLUTION_UNSUPPORTED: Final = "schema-evolution-unsupported"


class UnsupportedSchemaEvolutionError(UnsupportedError):
    """`schema_delta` cannot render some operations for this Dialect; `operations` lists them.

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

    table: PhysicalTable
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

    table: PhysicalTable
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
