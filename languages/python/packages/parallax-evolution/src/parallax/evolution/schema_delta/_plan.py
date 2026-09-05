"""Lowering a Unilateral Evolution to physical operations against the layouts.

This is where the model becomes physical: `m-storage-layout` already composed
every Table, its canonical Column order, each Column's effective nullability, and
the physical primary key, so the lowering selects those facts and resolves each
Column's value domain through the declaration its contributor names. It composes
no key, no column order, and no nullability of its own.

The lowering therefore reads the two endpoints' compiled layouts and asks what
the later one holds that the earlier one does not, rather than re-deriving a
physical consequence per operation kind. An Evolution Operation decides what a
physical difference MEANS — which operations caused it, and so whether one exists
at all — and the layouts decide what it IS.

An entity-level addition brings a whole Table with it. It suppresses operations
for the members it contains, so the members' Columns and the Entity's authored
Indices are read off the later model here rather than arriving as operations of
their own.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass

from parallax.core import storage_layout
from parallax.core.base import JSON, STRING, NeutralType
from parallax.core.dialect import Dialect, PhysicalIndexName
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    IndexIdentity,
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
    AttributeAdded,
    AttributeAltered,
    ConcreteSubtypeAdded,
    EntityAdded,
    EntityAltered,
    EvolutionOperation,
    IndexAdded,
    IndexAltered,
    IndexRemoved,
    InheritanceChanged,
    UnilateralEvolution,
    ValueObjectOccurrenceAdded,
)
from parallax.evolution.schema_delta._naming import NamedIndex, census, physical_index_name
from parallax.evolution.schema_delta._physical import (
    AddColumn,
    CreateIndex,
    CreateTable,
    DropIndex,
    ExpandColumnDomain,
    IndexDefinition,
    PhysicalColumn,
    PhysicalOperation,
)

__all__ = ["Plan", "plan"]

# The framework-owned table-per-hierarchy tag is not a declared Attribute
# (m-inheritance), so it has no declared type to resolve: the generator fixes one
# wide enough for any authored tagValue.
_TAG_TYPE: NeutralType = STRING
_TAG_MAX_LENGTH = 32


@dataclass(frozen=True, slots=True)
class Plan:
    """What the database is asked to do, and every Index that exists while it does.

    The Index census spans both endpoints because a name has to be unique among
    the Indices that COEXIST, not merely among the ones a statement touches: an
    Index the delta never mentions is still an object in the database while a new
    one is created beside it.
    """

    operations: tuple[PhysicalOperation, ...]
    indices: tuple[NamedIndex, ...]


def plan(evolution: UnilateralEvolution, dialect: Dialect) -> Plan:
    """Every physical operation ``evolution`` asks the database to perform.

    ``dialect`` is needed here because a physical index operation is not
    well-formed without its name, and a name is only derivable against the
    identifier limit the Dialect fixes.
    """
    later = _Endpoint.of(evolution.later)
    earlier = None if evolution.earlier is None else _Endpoint.of(evolution.earlier)
    causes = _Causes.over(evolution.operations, later, earlier)
    return Plan(
        operations=tuple(
            operation
            for layout in later.facet.tables
            for operation in _lower(layout, later, earlier, causes, dialect)
        ),
        indices=census(_authored_indices(earlier), _authored_indices(later), dialect),
    )


def _authored_indices(endpoint: _Endpoint | None) -> tuple[IndexDefinition, ...]:
    """Every authored Index one endpoint holds, resolved into the Table holding it."""
    if endpoint is None:
        return ()
    return tuple(
        definition
        for layout in endpoint.facet.tables
        for definition in _index_definitions(endpoint.model, layout)
    )


def _lower(
    layout: TableLayout,
    later: _Endpoint,
    earlier: _Endpoint | None,
    causes: _Causes,
    dialect: Dialect,
) -> Iterator[PhysicalOperation]:
    """Everything one target Table needs, given what the earlier edition held.

    A Table the earlier edition did not have is created whole; one it had is
    carried forward Column by Column and Index by Index. No Table and no Column
    is ever taken away: nothing that destroys a stored shape is unilateral, so
    the algebra has no arm for it.
    """
    defined = tuple(_index_definitions(later.model, layout))
    before = None if earlier is None else earlier.table(layout.table)
    if before is None or earlier is None:
        yield from _create(layout, later, defined, causes.table(layout.table), dialect)
        return
    yield from _columns(layout, before, later, earlier, causes)
    yield from _indices(tuple(_index_definitions(earlier.model, before)), defined, causes, dialect)


@dataclass(frozen=True, slots=True)
class _Endpoint:
    """One accepted Metamodel beside its compiled layouts."""

    model: Metamodel
    facet: StorageLayoutFacet

    @staticmethod
    def of(model: Metamodel) -> _Endpoint:
        return _Endpoint(model=model, facet=storage_layout.view(model))

    def table(self, table: Table) -> TableLayout | None:
        return self.facet.table(table)

    def rows(self) -> Mapping[EntityIdentity, Table]:
        """The Table each row-owning Entity's own rows sit in.

        A rowless abstract position has no entry: it owns no row, so the Columns
        it declares are answered for by the concrete subtypes that do.
        """
        return {
            entity.identity: view.layout.table
            for entity in self.model.entities
            if (view := self.facet.entity(entity.identity)) is not None
        }


def _create(
    layout: TableLayout,
    later: _Endpoint,
    definitions: Sequence[IndexDefinition],
    causes: tuple[EvolutionOperation, ...],
    dialect: Dialect,
) -> Iterator[PhysicalOperation]:
    """One new Table, then each authored Index it holds as its own statement.

    A Table the earlier edition did not have is created whole. An Index created
    as part of creating its Table is caused by everything that caused the Table:
    it arrives because the declarations the Table materializes arrived, and no
    Index operation of its own describes it.
    """
    yield CreateTable(
        table=layout.table,
        columns=tuple(_physical_column(later.model, slot) for slot in layout.columns),
        primary_key=tuple(slot.column for slot in layout.physical_primary_key),
        caused_by=causes,
    )
    for definition in definitions:
        yield CreateIndex(
            definition=definition,
            name=physical_index_name(definition, dialect),
            caused_by=causes,
        )


def _columns(
    layout: TableLayout,
    before: TableLayout,
    later: _Endpoint,
    earlier: _Endpoint,
    causes: _Causes,
) -> Iterator[PhysicalOperation]:
    """Each Column this Table gains, and each whose stored domain widens.

    A Column both editions hold whose domain is not a widening asks for no
    statement: the algebra has no narrowing arm, because every prefix of a
    Schema Delta must leave the earlier edition operable and destroy no stored
    value.
    """
    for slot in layout.columns:
        held = before.column(slot.column)
        target = _physical_column(later.model, slot)
        if held is None:
            yield AddColumn(
                table=layout.table,
                column=target,
                caused_by=causes.column(layout.table, slot),
            )
            continue
        source = _physical_column(earlier.model, held)
        if _expands(source, target):
            yield ExpandColumnDomain(
                table=layout.table,
                earlier=source,
                later=target,
                caused_by=causes.expansion(
                    layout.table, slot, relaxed=source.nullable != target.nullable
                ),
            )


def _expands(earlier: PhysicalColumn, later: PhysicalColumn) -> bool:
    """Whether ``later`` admits every value ``earlier`` did, and more.

    A widening is relaxed nullability, a longer String bound, a removed String
    bound, or those together. Every other difference is a narrowing or a Neutral
    Type change, neither of which a Unilateral Evolution can ask for, and a
    Column that did not change at all asks for nothing.
    """
    return (
        earlier != later
        and earlier.neutral_type == later.neutral_type
        and (later.nullable or not earlier.nullable)
        and _bound_admits(earlier.max_length, later.max_length)
    )


def _bound_admits(earlier: int | None, later: int | None) -> bool:
    """Whether a String bound was kept, lengthened, or removed."""
    return earlier == later or (earlier is not None and (later is None or later > earlier))


def _indices(
    carried: Sequence[IndexDefinition],
    defined: Sequence[IndexDefinition],
    causes: _Causes,
    dialect: Dialect,
) -> Iterator[PhysicalOperation]:
    """Each authored Index a surviving Table gains, and each it no longer defines.

    Two definitions are the same physical Index exactly when they derive the same
    Physical Index Name, which is what makes an altered Index a create beside a
    drop: every fact the name is derived over is a fact the database holds, so a
    definition that changed one of them is a different object.
    """
    target = _named(defined, dialect)
    held = _named(carried, dialect)
    for name, definition in target.items():
        if name not in held:
            yield CreateIndex(definition=definition, name=name, caused_by=causes.index(definition))
    for name, definition in held.items():
        if name not in target:
            yield DropIndex(definition=definition, name=name, caused_by=causes.index(definition))


def _named(
    definitions: Sequence[IndexDefinition], dialect: Dialect
) -> Mapping[PhysicalIndexName, IndexDefinition]:
    return {physical_index_name(definition, dialect): definition for definition in definitions}


@dataclass(frozen=True, slots=True)
class _Causes:
    """Which Evolution Operations asked for a physical change.

    A Column arrives because the declaration it materializes arrived, or —
    when both editions declare it — because this Table started materializing
    that declaration. A stored domain widens because the member's own
    declaration widened, or because the rows the Table holds changed: a
    Column required of every shape a Table stored is nullable once it stores one
    more.
    """

    operations: tuple[EvolutionOperation, ...]
    later_rows: Mapping[EntityIdentity, Table]
    earlier_rows: Mapping[EntityIdentity, Table]
    declared_in: Mapping[Table, frozenset[EntityIdentity]]

    @staticmethod
    def over(
        operations: Sequence[EvolutionOperation], later: _Endpoint, earlier: _Endpoint | None
    ) -> _Causes:
        return _Causes(
            operations=tuple(operations),
            later_rows=later.rows(),
            earlier_rows={} if earlier is None else earlier.rows(),
            declared_in={
                layout.table: frozenset(slot.declaring_owner for slot in layout.columns)
                for layout in later.facet.tables
            },
        )

    def table(self, table: Table) -> tuple[EvolutionOperation, ...]:
        """Every addition that brings ``table``.

        An Entity brings a Table when it owns rows there or declares one of its
        Columns, so an abstract table-per-hierarchy root is a cause of its
        family's shared Table and an abstract table-per-concrete-subtype root is
        a cause of every concrete Table repeating its members.
        """
        return tuple(
            operation
            for operation in self.operations
            if isinstance(operation, (EntityAdded, ConcreteSubtypeAdded))
            and (
                self.later_rows.get(operation.entity) == table
                or operation.entity in self.declared_in.get(table, frozenset())
            )
        )

    def column(self, table: Table, slot: ColumnSlot) -> tuple[EvolutionOperation, ...]:
        """Why ``slot``'s Column is in ``table`` now and was not before."""
        brought = tuple(
            operation for operation in self.operations if _brings_declaration(operation, slot)
        )
        return brought or tuple(
            operation
            for operation in self.operations
            if isinstance(operation, EntityAltered)
            and _reparents(operation)
            and self.later_rows.get(operation.entity) == table
        )

    def expansion(
        self, table: Table, slot: ColumnSlot, *, relaxed: bool
    ) -> tuple[EvolutionOperation, ...]:
        """Why ``slot``'s stored domain is wider than it was.

        A relaxed nullability additionally answers to whatever changed the shapes
        ``table`` stores, because a Column is required exactly while every one of
        them declares it.
        """
        return tuple(
            operation
            for operation in self.operations
            if _widens_declaration(operation, slot)
            or (relaxed and self._changes_stored_shapes(operation, table))
        )

    def index(self, definition: IndexDefinition) -> tuple[EvolutionOperation, ...]:
        """The operations that asked for this Index definition to exist or go.

        An Index whose own operation describes it names it; one an entity-level
        addition brought silently is caused by that addition, exactly as the
        Columns beside it are.
        """
        named = tuple(
            operation for operation in self.operations if _names_index(operation, definition.index)
        )
        brought = tuple(
            operation
            for operation in self.operations
            if isinstance(operation, (EntityAdded, ConcreteSubtypeAdded))
            and operation.entity == definition.index.entity
        )
        return named or brought or self.table(definition.table)

    def _changes_stored_shapes(self, operation: EvolutionOperation, table: Table) -> bool:
        """Whether ``operation`` moves a row-owning shape into or out of ``table``."""
        return isinstance(operation, (EntityAdded, ConcreteSubtypeAdded, EntityAltered)) and (
            (self.later_rows.get(operation.entity) == table)
            != (self.earlier_rows.get(operation.entity) == table)
        )


def _brings_declaration(operation: EvolutionOperation, slot: ColumnSlot) -> bool:
    """Whether ``operation`` is why the declaration behind ``slot`` exists at all."""
    match operation:
        case AttributeAdded():
            return operation.attribute == slot.contributor
        case ValueObjectOccurrenceAdded():
            return operation.value_object == slot.contributor
        case EntityAdded() | ConcreteSubtypeAdded():
            return operation.entity == slot.declaring_owner
        case _:
            return False


def _widens_declaration(operation: EvolutionOperation, slot: ColumnSlot) -> bool:
    """Whether ``operation`` is the member alteration that widened ``slot``'s domain."""
    return isinstance(operation, AttributeAltered) and operation.attribute == slot.contributor


def _reparents(operation: EntityAltered) -> bool:
    """Whether ``operation`` changes which declarations a surviving Entity holds."""
    return any(isinstance(delta, InheritanceChanged) for delta in operation.deltas)


def _names_index(operation: EvolutionOperation, index: IndexIdentity) -> bool:
    return (
        isinstance(operation, (IndexAdded, IndexRemoved, IndexAltered)) and operation.index == index
    )


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
        for index in _secondary_indices(entity):
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


def _secondary_indices(entity: EntityMetadata) -> tuple[IndexMetadata, ...]:
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
