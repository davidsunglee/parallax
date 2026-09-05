"""Lowering a Unilateral Evolution to physical operations against the layouts.

This is where the model becomes physical: `m-storage-layout` already composed
every Table, its canonical Column order, each Column's effective nullability, and
the physical primary key, so the lowering selects those facts and resolves each
Column's value domain through the declaration its contributor names. It composes
no key, no column order, and no nullability of its own.

An entity-level addition brings a whole Table with it. It suppresses operations
for the members it contains, so the members' Columns and the Entity's authored
Indices are read off the later model here rather than arriving as operations of
their own.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence

from parallax.core import storage_layout
from parallax.core.base import JSON, STRING, NeutralType
from parallax.core.dialect import Dialect
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    IndexMetadata,
    Metamodel,
    Table,
    ValueObjectIdentity,
    derive_primary_key_index,
)
from parallax.core.storage_layout import (
    ColumnSlot,
    InheritanceDiscriminator,
    RelationalDocument,
    StorageLayoutFacet,
    TableLayout,
)
from parallax.evolution.model_evolution import (
    ConcreteSubtypeAdded,
    EntityAdded,
    EvolutionOperation,
    UnilateralEvolution,
)
from parallax.evolution.schema_delta._naming import physical_index_name
from parallax.evolution.schema_delta._physical import (
    CreateIndex,
    CreateTable,
    IndexDefinition,
    PhysicalColumn,
    PhysicalOperation,
)

__all__ = ["plan"]

# The framework-owned table-per-hierarchy tag is not a declared Attribute
# (m-inheritance), so it has no declared type to resolve: the generator fixes one
# wide enough for any authored tagValue.
_TAG_TYPE: NeutralType = STRING
_TAG_MAX_LENGTH = 32


def plan(evolution: UnilateralEvolution, dialect: Dialect) -> tuple[PhysicalOperation, ...]:
    """Every physical operation ``evolution`` asks the database to perform.

    ``dialect`` is needed here because a physical index operation is not
    well-formed without its name, and a name is only derivable against the
    identifier limit the Dialect fixes.
    """
    later = evolution.later
    facet = storage_layout.view(later)
    existing = _existing_tables(evolution.earlier)
    causes = _table_causes(later, facet, evolution.operations)
    return tuple(
        operation
        for layout in facet.tables
        if layout.table in causes and layout.table not in existing
        for operation in _create(later, layout, causes[layout.table], dialect)
    )


def _create(
    model: Metamodel,
    layout: TableLayout,
    causes: tuple[EvolutionOperation, ...],
    dialect: Dialect,
) -> Iterator[PhysicalOperation]:
    """One new Table, then each authored Index it holds as its own statement.

    An Index created as part of creating its Table is caused by everything that
    caused the Table: it arrives because the declarations the Table materializes
    arrived, and no Index operation of its own describes it.
    """
    yield CreateTable(
        table=layout.table,
        columns=tuple(_physical_column(model, slot) for slot in layout.columns),
        primary_key=tuple(slot.column for slot in layout.physical_primary_key),
        caused_by=causes,
    )
    for definition in _index_definitions(model, layout):
        yield CreateIndex(
            definition=definition,
            name=physical_index_name(definition, dialect),
            caused_by=causes,
        )


def _existing_tables(earlier: Metamodel | None) -> frozenset[Table]:
    """The Tables the earlier edition already had; none when provisioning."""
    if earlier is None:
        return frozenset()
    return frozenset(layout.table for layout in storage_layout.view(earlier).tables)


def _table_causes(
    model: Metamodel, facet: StorageLayoutFacet, operations: Sequence[EvolutionOperation]
) -> Mapping[Table, tuple[EvolutionOperation, ...]]:
    """Each Table an entity-level addition brings, and the additions that bring it.

    An Entity brings a Table when it owns rows there or declares one of its
    Columns, so an abstract table-per-hierarchy root is a cause of its family's
    shared Table and an abstract table-per-concrete-subtype root is a cause of
    every concrete Table repeating its members. Operations stay in the canonical
    order they arrived in.
    """
    rows = _row_owners(model, facet)
    causes: dict[Table, list[EvolutionOperation]] = {}
    for operation in operations:
        if not isinstance(operation, (EntityAdded, ConcreteSubtypeAdded)):
            continue
        for layout in facet.tables:
            if rows.get(operation.entity) == layout.table or any(
                slot.declaring_owner == operation.entity for slot in layout.columns
            ):
                causes.setdefault(layout.table, []).append(operation)
    return {table: tuple(operations) for table, operations in causes.items()}


def _row_owners(model: Metamodel, facet: StorageLayoutFacet) -> Mapping[EntityIdentity, Table]:
    """The Table each row-owning Entity's own rows sit in.

    A rowless abstract position has no entry: it owns no row and so brings no
    Table by itself, though the Columns it declares still name it as a cause.
    """
    return {
        entity.identity: view.layout.table
        for entity in model.entities
        if (view := facet.entity(entity.identity)) is not None
    }


def _physical_column(model: Metamodel, slot: ColumnSlot) -> PhysicalColumn:
    """One layout slot with the value domain its contributor declares.

    A top-level Value Object occupies one Structured Column and a Relational
    Document Layout's shared Structured Column carries the document-resident
    members of every governed row; both are the neutral `json` type, and the
    dialect maps that to its own structured-document type.
    """
    contributor = slot.contributor
    if isinstance(contributor, InheritanceDiscriminator):
        return PhysicalColumn(slot.column, _TAG_TYPE, _TAG_MAX_LENGTH, slot.effective_nullable)
    if isinstance(contributor, (ValueObjectIdentity, RelationalDocument)):
        return PhysicalColumn(slot.column, JSON, None, slot.effective_nullable)
    attribute = _declared_attribute(model, contributor)
    return PhysicalColumn(
        slot.column, attribute.type, attribute.max_length, slot.effective_nullable
    )


def _declared_attribute(model: Metamodel, contributor: AttributeIdentity) -> AttributeMetadata:
    entity = model.entity(contributor.entity)
    attribute = None if entity is None else entity.attribute(contributor.name)
    if attribute is None:  # pragma: no cover - a slot names an accepted declaration
        raise ValueError(f"{contributor.entity.canonical}: no attribute {contributor.name!r}")
    return attribute


def _index_definitions(model: Metamodel, layout: TableLayout) -> Iterator[IndexDefinition]:
    """Every authored Index this Table holds, in canonical declaration order.

    A unique or non-unique Index may be declared on any Entity whose members
    reach the Table — a standalone Entity, an ancestor of a
    table-per-concrete-subtype concrete, or any table-per-hierarchy family
    participant — so the layout's contributor lookup, not an ancestry walk,
    decides membership.
    """
    for entity in model.entities:
        for index in _authored_indices(entity):
            slots = [layout.contribution(component) for component in index.attributes]
            if all(slot is None for slot in slots):
                continue
            if any(slot is None for slot in slots):  # pragma: no cover - defensive
                raise ValueError(
                    f"index {index.identity.name!r} spans Table "
                    f"{layout.table.name!r} only partially"
                )
            resolved = [slot for slot in slots if slot is not None]
            yield IndexDefinition(
                table=layout.table,
                index=index.identity,
                components=tuple(index.attributes),
                columns=tuple(_physical_column(model, slot) for slot in resolved),
                unique=index.unique,
            )


def _authored_indices(entity: EntityMetadata) -> tuple[IndexMetadata, ...]:
    """``entity``'s Indices without the derived primary-key one.

    The derived Index is emitted inline by ``create table`` as the key itself, so
    a separate statement for it would be a second object over the same columns.
    """
    derived = derive_primary_key_index(
        entity=entity.identity,
        container=entity.declared_container,
        attributes=entity.declared_attributes,
        as_of_axes=entity.declared_as_of_axes,
    )
    return tuple(
        index for index in entity.indices if derived is None or index.identity != derived.identity
    )
