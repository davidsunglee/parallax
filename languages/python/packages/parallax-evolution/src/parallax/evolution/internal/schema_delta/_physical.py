from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from parallax.core.internal.base import NeutralType
from parallax.core.internal.database_binding import ResolvedSequence, ResolvedTable
from parallax.core.internal.dialect import PhysicalIndexName
from parallax.core.internal.metamodel import (
    AttributeIdentity,
    Column,
    EntityIdentity,
    IndexIdentity,
)
from parallax.evolution.internal.model_evolution import EvolutionOperation
from parallax.evolution.internal.schema_delta._values import SchemaTarget

__all__ = [
    "AddColumn",
    "AlterSequence",
    "CreateExtension",
    "CreateIndex",
    "CreateSequence",
    "CreateTable",
    "DocumentRootCheck",
    "DropIndex",
    "DropSequence",
    "Exclusion",
    "IndexDefinition",
    "IntervalCheck",
    "PhysicalColumn",
    "PhysicalOperation",
    "PositionSequence",
    "RestateColumnDomain",
    "SequenceOperation",
    "TableOperation",
    "TemporalBackingIndex",
    "key_columns",
    "location_of",
    "member_key",
    "table_of",
]


@dataclass(frozen=True, slots=True)
class PhysicalColumn:
    """One physical Column's complete DDL-relevant facts.

    ``nullable`` is the layout's EFFECTIVE nullability, which a shared
    table-per-hierarchy Table relaxes for a subtype-only member and the key,
    discriminator, and Structured Column tiers force closed.
    """

    column: Column
    neutral_type: NeutralType
    max_length: int | None
    nullable: bool


@dataclass(frozen=True, slots=True)
class IndexDefinition:
    """One authored Index as one physical Table holds it.

    ``table`` is the holding mapping owner's table as the endpoint's binding
    resolves it. ``components`` retains the authored Attribute Identities, which
    a collision report names. ``column_attributes`` is the Attribute behind each
    of ``columns`` — the authored components, then a temporal Table's axis ends
    — from which the Physical Index Name is derived.
    """

    table: ResolvedTable
    index: IndexIdentity
    components: tuple[AttributeIdentity, ...]
    column_attributes: tuple[AttributeIdentity, ...]
    columns: tuple[PhysicalColumn, ...]
    unique: bool

    @property
    def mapping_owner(self) -> EntityIdentity:
        return self.table.mapping_owner


@dataclass(frozen=True, slots=True)
class IntervalCheck:
    """One temporal axis's named requirement that ``start`` precede ``end``."""

    name: str
    start: Column
    end: Column


@dataclass(frozen=True, slots=True)
class DocumentRootCheck:
    """A Document Table's named requirement that ``column`` hold a JSON object."""

    name: str
    column: Column


@dataclass(frozen=True, slots=True)
class Exclusion:
    """A temporal Table's named non-overlap constraint.

    No two rows equal on every ``equal`` Column may overlap on every
    ``overlapping`` half-open interval at once; each interval is its start
    Column then its end Column.
    """

    name: str
    equal: tuple[Column, ...]
    overlapping: tuple[tuple[Column, Column], ...]


@dataclass(frozen=True, slots=True)
class TemporalBackingIndex:
    """The Index backing a temporal Table's primary key or exclusion.

    It shares the schema's Index namespace with authored Indices, so the
    Physical Index Name census counts it, under the name its resolved table
    derived for its constraint.
    """

    table: ResolvedTable
    kind: Literal["primaryKey", "exclusion"]
    columns: tuple[Column, ...]
    name: PhysicalIndexName

    @property
    def mapping_owner(self) -> EntityIdentity:
        return self.table.mapping_owner


@dataclass(frozen=True, slots=True)
class CreateExtension:
    """Install the provider extension the created temporal Tables require.

    Tableless: it is one database-wide prerequisite, caused by the canonical
    union of the causes of every Table creation that needs it.
    """

    name: str
    caused_by: tuple[EvolutionOperation, ...]


@dataclass(frozen=True, slots=True)
class CreateSequence:
    """Create the native sequence a newly declared allocator draws from.

    Tableless: the sequence is one object however many Tables consume it,
    caused by every operation that added a consumer of it.
    """

    sequence: ResolvedSequence
    caused_by: tuple[EvolutionOperation, ...]


@dataclass(frozen=True, slots=True)
class AlterSequence:
    """Restate a surviving allocator's sequence under its later allocation settings.

    ``earlier`` and ``later`` are the allocator under each endpoint's binding;
    the sequence is altered where the later one places it.
    """

    earlier: ResolvedSequence
    later: ResolvedSequence
    caused_by: tuple[EvolutionOperation, ...]


@dataclass(frozen=True, slots=True)
class PositionSequence:
    """Move a sequence forward past every key its consuming Tables store and
    every block already reserved from it.

    ``reserved_increment`` is the physical step the sequence's latest
    reservation was taken under: the earlier settings' step for a sequence whose
    step this evolution alters, and its own otherwise.
    """

    sequence: ResolvedSequence
    reserved_increment: int
    caused_by: tuple[EvolutionOperation, ...]


@dataclass(frozen=True, slots=True)
class DropSequence:
    """Drop the sequence of an allocator the later model no longer references,
    where the earlier binding placed it."""

    sequence: ResolvedSequence
    caused_by: tuple[EvolutionOperation, ...]


@dataclass(frozen=True, slots=True)
class CreateTable:
    """Create one whole Table: every target Column, the derived primary key,
    its checks, and a temporal Table's exclusion.

    ``checks`` holds a temporal Table's interval checks, Valid Time first, then
    a Document Table's root-object check. A temporal Table's primary key
    carries its resolved ``primary_key_name``;
    any other key is left for the database to name. Authored secondary Indices
    are deliberately excluded — each is its own separately named statement, so
    a violation reports a name a rollout can correlate.
    """

    table: ResolvedTable
    columns: tuple[PhysicalColumn, ...]
    primary_key: tuple[Column, ...]
    checks: tuple[IntervalCheck | DocumentRootCheck, ...]
    caused_by: tuple[EvolutionOperation, ...]
    primary_key_name: str | None = None
    exclusion: Exclusion | None = None


@dataclass(frozen=True, slots=True)
class AddColumn:
    """Add one new physical Column to an existing Table."""

    table: ResolvedTable
    column: PhysicalColumn
    caused_by: tuple[EvolutionOperation, ...]


@dataclass(frozen=True, slots=True)
class RestateColumnDomain:
    """Restate one surviving Column's value domain as the later edition's.

    Not a generic column alteration: it is legal in exactly two shapes, and both
    leave every stored value where it is. Either ``later`` admits every value
    ``earlier`` did — relaxed nullability, a longer or removed String bound, or
    those together — or the Column stores no shape at either endpoint, so it holds
    no value the restatement could reach. Narrowing a domain rows are stored
    against is never unilateral and never arrives here.
    """

    table: ResolvedTable
    earlier: PhysicalColumn
    later: PhysicalColumn
    caused_by: tuple[EvolutionOperation, ...]


@dataclass(frozen=True, slots=True)
class CreateIndex:
    """Create one authored Index under its derived Physical Index Name."""

    definition: IndexDefinition
    name: PhysicalIndexName
    caused_by: tuple[EvolutionOperation, ...]


@dataclass(frozen=True, slots=True)
class DropIndex:
    """Drop one Index the later model no longer defines."""

    definition: IndexDefinition
    name: PhysicalIndexName
    caused_by: tuple[EvolutionOperation, ...]


type TableOperation = CreateTable | AddColumn | RestateColumnDomain | CreateIndex | DropIndex
"""An operation local to a single Table."""

type SequenceOperation = CreateSequence | AlterSequence | PositionSequence | DropSequence
"""An operation on one native sequence."""

type PhysicalOperation = CreateExtension | SequenceOperation | TableOperation
"""Everything an evolution can ask a relational schema to do.

A Unilateral Evolution asks for no sequence operation but a creation; altering,
positioning, and dropping a sequence arise only in a coordinated migration."""


def table_of(operation: TableOperation) -> ResolvedTable:
    """The one Table ``operation`` acts on.

    Every Table operation is local to that Table — the algebra emits no foreign
    key and an Index is always local — so their relative order is one sort; the
    only edge leaving a Table is a Table creation's on a prerequisite.
    """
    match operation:
        case CreateTable() | AddColumn() | RestateColumnDomain():
            return operation.table
        case CreateIndex() | DropIndex():
            return operation.definition.table


def member_key(operation: TableOperation) -> str:
    """The member within the Table that ``operation`` addresses, for ordering.

    A whole-Table operation addresses no member and sorts first among its kind.
    """
    match operation:
        case CreateTable():
            return ""
        case AddColumn():
            return operation.column.column.name
        case RestateColumnDomain():
            return operation.later.column.name
        case CreateIndex() | DropIndex():
            return operation.name.value


def location_of(operation: PhysicalOperation) -> SchemaTarget:
    """Where ``operation`` acts, as a refusal reports it."""
    match operation:
        case CreateExtension():
            return SchemaTarget(extension=operation.name)
        case CreateSequence() | PositionSequence() | DropSequence():
            return SchemaTarget(sequence=operation.sequence.physical)
        case AlterSequence():
            return SchemaTarget(sequence=operation.later.physical)
        case CreateTable():
            return SchemaTarget(table=operation.table.physical)
        case AddColumn():
            return SchemaTarget(table=operation.table.physical, column=operation.column.column)
        case RestateColumnDomain():
            return SchemaTarget(table=operation.table.physical, column=operation.later.column)
        case CreateIndex() | DropIndex():
            return SchemaTarget(table=operation.definition.table.physical, index=operation.name)


def key_columns(sequence: ResolvedSequence) -> tuple[tuple[ResolvedTable, Column], ...]:
    """Each Table drawing keys from ``sequence`` beside the Column storing them.

    A temporal Table's physical key closes with axis Columns and a
    table-per-hierarchy Table's may carry its tag, so the key Column is read off
    the family root's declared key: a temporal Table's logical key, and the
    authored Attribute of any other Table's physical key. Every stored row a
    Table holds, history included, sits in that one Column.
    """
    held: list[tuple[ResolvedTable, Column]] = []
    for table in sequence.consuming_tables:
        layout = table.layout
        constraints = layout.temporal_constraints
        slots = (
            constraints.logical_key
            if constraints is not None
            else tuple(
                slot
                for slot in layout.physical_primary_key
                if isinstance(slot.contributor, AttributeIdentity)
            )
        )
        held.extend((table, slot.column) for slot in slots)
    return tuple(held)
