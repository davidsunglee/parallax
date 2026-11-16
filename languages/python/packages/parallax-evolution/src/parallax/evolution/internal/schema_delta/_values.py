from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Final, Literal

from parallax.core.internal.base import UnsupportedError
from parallax.core.internal.database_binding import PhysicalSequence, PhysicalTable
from parallax.core.internal.dialect import PhysicalIndexName
from parallax.core.internal.metamodel import AttributeIdentity, Column, IndexIdentity
from parallax.evolution.internal.model_evolution import EvolutionOperation

__all__ = [
    "CollidingIndex",
    "CollidingRelation",
    "CollidingTemporalConstraint",
    "CollisionGroup",
    "CoordinatedMigration",
    "CreatedIndex",
    "IndexPresence",
    "ManualAction",
    "ManualStep",
    "MigrationStatement",
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


class ManualAction(enum.Enum):
    """What a coordinated migration step asks of the deployment rather than of SQL."""

    DRAIN_EARLIER_ROOTS = "DrainEarlierRoots"
    """Close every Database Root serving the earlier edition, abandoning the keys
    it holds reserved and retiring its provider sessions, before any later step."""
    TRANSFORM_STORED_DATA = "TransformStoredData"
    """Carry the stored data and schema across a change no generated statement
    expresses."""
    RELOCATE = "Relocate"
    """Move or rename a physical table or sequence, with what it holds, to the
    later binding's placement."""
    UPDATE_AUTHORING_SURFACE = "UpdateAuthoringSurface"
    """Change the application's queries and writes for an operation that needs
    no database change of its own."""


@dataclass(frozen=True, slots=True)
class MigrationStatement:
    """One generated statement of a coordinated migration.

    ``caused_by`` names the operations that asked for it."""

    sql: str
    caused_by: tuple[EvolutionOperation, ...]


@dataclass(frozen=True, slots=True)
class ManualStep:
    """One step of a coordinated migration that the deployment performs itself.

    ``caused_by`` names the operations that asked for it."""

    action: ManualAction
    caused_by: tuple[EvolutionOperation, ...]


@dataclass(frozen=True, slots=True)
class CoordinatedMigration:
    """The ordered steps carrying a database and its roots from one edition to the next.

    The editions are a Coordinated Evolution's earlier and later ones. Every
    step is applied in order, each only after the one before it completes, and
    the later edition is published after the last.
    """

    steps: tuple[MigrationStatement | ManualStep, ...]


@dataclass(frozen=True, slots=True)
class SchemaTarget:
    """The table and member, sequence, or database extension a schema operation acts on.

    Where one physical operation acts: its physical table and the member within
    it, the physical ``sequence`` a native allocator creates, or the
    database-wide ``extension`` a tableless prerequisite installs.
    """

    table: PhysicalTable | None = None
    column: Column | None = None
    index: PhysicalIndexName | None = None
    extension: str | None = None
    sequence: PhysicalSequence | None = None


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
class CollidingRelation:
    """A table or sequence an endpoint places under a collision group's name.

    Where index names share their qualifier's relation namespace, such a
    relation holds the name an Index derived.
    """

    relation: PhysicalTable | PhysicalSequence
    presence: IndexPresence


@dataclass(frozen=True, slots=True)
class CollisionGroup:
    """Two or more distinct objects claiming one Physical Index Name.

    ``definitions`` holds the authored Indices, ``temporal_constraints`` the
    temporal primary keys and exclusions, and ``relations`` the tables and
    sequences holding the name; together they hold at least two, at least one
    of them an Index.
    """

    name: PhysicalIndexName
    definitions: tuple[CollidingIndex, ...]
    temporal_constraints: tuple[CollidingTemporalConstraint, ...] = ()
    relations: tuple[CollidingRelation, ...] = ()
