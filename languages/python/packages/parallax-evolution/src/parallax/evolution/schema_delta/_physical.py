"""The private physical-operation algebra a Unilateral Evolution lowers to.

Nothing here crosses the wheel's boundary: statements leave as plain strings and
``createdIndices`` is the sole provenance mapping out. The algebra is the closed
choice below and carries no drop-table, drop-column, rename, primary-key
alteration, or arbitrary-SQL arm, because no Unilateral Evolution can produce
one.

Each operation carries RESOLVED physical facts rather than Storage Layout
objects. A ``ColumnSlot`` names its contributor, not the value domain a column
type is spelled from, so a renderer holding one would have to resolve the
declaration through the Metamodel anyway; resolving once in the planner is what
keeps rendering a pure function of the operation and the Dialect.
"""

from __future__ import annotations

from dataclasses import dataclass

from parallax.core.base import NeutralType
from parallax.core.dialect import PhysicalIndexName
from parallax.core.metamodel import AttributeIdentity, Column, IndexIdentity, Table
from parallax.evolution.model_evolution import EvolutionOperation
from parallax.evolution.schema_delta._values import PhysicalLocation

__all__ = [
    "AddColumn",
    "CreateIndex",
    "CreateTable",
    "DropIndex",
    "ExpandColumnDomain",
    "IndexDefinition",
    "PhysicalColumn",
    "PhysicalOperation",
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

    ``components`` retains the logical Attribute Identities in authored order
    beside the physical ``columns`` they resolved to, because the Physical Index
    Name is derived from the logical facts and a collision report names them.
    """

    table: Table
    index: IndexIdentity
    components: tuple[AttributeIdentity, ...]
    columns: tuple[PhysicalColumn, ...]
    unique: bool


@dataclass(frozen=True, slots=True)
class CreateTable:
    """Create one whole Table: every target Column and the derived primary key.

    Authored secondary Indices are deliberately excluded — each is its own
    separately named statement, so a violation reports a name a rollout can
    correlate.
    """

    table: Table
    columns: tuple[PhysicalColumn, ...]
    primary_key: tuple[Column, ...]
    caused_by: tuple[EvolutionOperation, ...]


@dataclass(frozen=True, slots=True)
class AddColumn:
    """Add one new physical Column to an existing Table."""

    table: Table
    column: PhysicalColumn
    caused_by: tuple[EvolutionOperation, ...]


@dataclass(frozen=True, slots=True)
class ExpandColumnDomain:
    """Widen one surviving Column's stored domain.

    Only an expansion: relaxed nullability, a longer or removed String bound, or
    both together. It is not a generic column alteration, because nothing that
    narrows a domain is unilateral.
    """

    table: Table
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


type PhysicalOperation = CreateTable | AddColumn | ExpandColumnDomain | CreateIndex | DropIndex
"""Everything a Unilateral Evolution can ask a relational schema to do."""


def table_of(operation: PhysicalOperation) -> Table:
    """The one Table ``operation`` acts on.

    Every operation of this algebra is local to a single Table — the algebra
    emits no foreign key and an Index is always local — which is what makes
    statement order one sort rather than a graph traversal.
    """
    match operation:
        case CreateTable() | AddColumn() | ExpandColumnDomain():
            return operation.table
        case CreateIndex() | DropIndex():
            return operation.definition.table


def member_key(operation: PhysicalOperation) -> str:
    """The member within the Table that ``operation`` addresses, for ordering.

    A whole-Table operation addresses no member and sorts first among its kind.
    """
    match operation:
        case CreateTable():
            return ""
        case AddColumn():
            return operation.column.column.name
        case ExpandColumnDomain():
            return operation.later.column.name
        case CreateIndex() | DropIndex():
            return operation.name.value


def location_of(operation: PhysicalOperation) -> PhysicalLocation:
    """Where ``operation`` acts, as a refusal reports it."""
    match operation:
        case CreateTable():
            return PhysicalLocation(table=operation.table)
        case AddColumn():
            return PhysicalLocation(table=operation.table, column=operation.column.column)
        case ExpandColumnDomain():
            return PhysicalLocation(table=operation.table, column=operation.later.column)
        case CreateIndex() | DropIndex():
            return PhysicalLocation(table=operation.definition.table, index=operation.name)
