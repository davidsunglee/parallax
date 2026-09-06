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
from parallax.core.inheritance import InheritanceFacet
from parallax.core.inheritance import view as inheritance_view
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
    inheritance_parent,
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
    AttributeDelta,
    ConcreteSubtypeAdded,
    EntityAdded,
    EntityAltered,
    EvolutionOperation,
    IndexAdded,
    IndexAltered,
    IndexRemoved,
    InheritanceChanged,
    MaximumLengthChanged,
    NullabilityChanged,
    UnilateralEvolution,
    ValueObjectOccurrenceAdded,
    ValueObjectOccurrenceAltered,
    ValueObjectOccurrenceDelta,
)
from parallax.evolution.schema_delta._naming import census, collision_groups, physical_index_name
from parallax.evolution.schema_delta._physical import (
    AddColumn,
    CreateIndex,
    CreateTable,
    DropIndex,
    IndexDefinition,
    PhysicalColumn,
    PhysicalOperation,
    RestateColumnDomain,
)
from parallax.evolution.schema_delta._values import CollisionGroup

__all__ = ["Plan", "plan"]

# The framework-owned table-per-hierarchy tag is not a declared Attribute
# (m-inheritance), so it has no declared type to resolve: the generator fixes one
# wide enough for any authored tagValue.
_TAG_TYPE: NeutralType = STRING
_TAG_MAX_LENGTH = 32


@dataclass(frozen=True, slots=True)
class Plan:
    """What the database is asked to do, and every name clash that would outlive it.

    The census the clashes are read from spans both endpoints' complete Index
    sets rather than the operations below it. An Index the delta never mentions
    is still an object in the database while a new one is created beside it — and
    the operations could not answer the question anyway, because they are built
    by telling definitions apart BY their derived names, so under a collision the
    two are already one and the statements bounding their lifetimes are the ones
    never emitted. Comparing the definitions establishes those lifetimes instead.
    """

    operations: tuple[PhysicalOperation, ...]
    collisions: tuple[CollisionGroup, ...]


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
        collisions=collision_groups(
            census(_authored_indices(earlier), _authored_indices(later), dialect),
            surviving=frozenset(layout.table for layout in later.facet.tables),
        ),
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
    """One accepted Metamodel beside the compiled facets the lowering reads."""

    model: Metamodel
    facet: StorageLayoutFacet
    family: InheritanceFacet

    @staticmethod
    def of(model: Metamodel) -> _Endpoint:
        return _Endpoint(
            model=model, facet=storage_layout.view(model), family=inheritance_view(model)
        )

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

    def ancestry(self) -> Mapping[EntityIdentity, frozenset[EntityIdentity]]:
        """The ancestors-or-self each Entity stands under.

        This is the position an inheritance alteration moves, and it is not the
        set of Entities that declare a Column the Entity selects: an ancestor
        declaring nothing yet still stands over it, and gains a Column here the
        moment it declares one.
        """
        return {
            entity.identity: frozenset(view.ancestry)
            for entity in self.model.entities
            if (view := self.family.entity(entity.identity)) is not None
        }

    def parents(self) -> Mapping[EntityIdentity, EntityIdentity]:
        """The one position each Entity extends; absent for one extending nothing.

        This is the single edge an inheritance alteration replaces, and unlike an
        ancestry it is the Entity's own recorded fact: no other Entity's move
        changes it.
        """
        return {
            entity.identity: parent
            for entity in self.model.entities
            if (parent := inheritance_parent(entity.inheritance)) is not None
        }

    def materialized(self) -> Mapping[EntityIdentity, frozenset[Table]]:
        """The Tables whose Columns hold each Entity's declarations.

        An Entity's declarations materialize where its own position is stored and
        wherever a concrete descendant repeats them, which is one Table for a
        table-per-hierarchy family — the root's, holding every member's
        declarations whether or not a concrete subtype composes them — and one
        per concrete descendant under table-per-concrete-subtype.
        """
        views = {
            entity.identity: view
            for entity in self.model.entities
            if (view := self.family.entity(entity.identity)) is not None
        }
        return {
            identity: frozenset(
                container
                for position in (view, *(views[concrete] for concrete in view.concrete_subtypes))
                if (container := position.container) is not None
            )
            for identity, view in views.items()
        }

    def holds(self) -> Mapping[Table, frozenset[EntityIdentity]]:
        """The ancestry each Table materializes, as Entities whose declarations it holds."""
        held: dict[Table, set[EntityIdentity]] = {}
        for identity, tables in self.materialized().items():
            for table in tables:
                held.setdefault(table, set()).add(identity)
        return {table: frozenset(identities) for table, identities in held.items()}


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
    """Each Column this Table gains, and each whose value domain moved.

    A Column both editions hold identically asks for nothing. One whose domain
    moved is restated as the later edition's, and the restatement is legal in
    exactly the two shapes that destroy no stored value: the later domain admits
    every value the earlier did, or the Column stores no shape at either endpoint
    and so holds no value at all. Narrowing a domain rows are stored against is
    not unilateral, so no accepted input reaches this Column any other way.
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
        if source == target:
            continue
        if not _expands(source, target) and not _stores_nothing(held, slot):
            raise ValueError(  # pragma: no cover - classification refuses this pair
                f"{layout.table.name}.{slot.column.name}: a stored domain narrowed"
            )
        yield RestateColumnDomain(
            table=layout.table,
            earlier=source,
            later=target,
            caused_by=causes.domain(
                layout.table, slot, moved_nullability=source.nullable != target.nullable
            ),
        )


def _expands(earlier: PhysicalColumn, later: PhysicalColumn) -> bool:
    """Whether ``later`` admits every value ``earlier`` did.

    A widening is relaxed nullability, a longer String bound, a removed String
    bound, or those together. Every other difference is a narrowing or a Neutral
    Type change, and neither is safe over a Column that holds a stored value.
    """
    return (
        earlier.neutral_type == later.neutral_type
        and (later.nullable or not earlier.nullable)
        and _bound_admits(earlier.max_length, later.max_length)
    )


def _stores_nothing(earlier: ColumnSlot, later: ColumnSlot) -> bool:
    """Whether no shape stores this Column at either endpoint.

    An abstract inheritance position composing no concrete subtype still
    materializes the Columns it declares in its family's Table, and no row is
    ever written against them. That empty applicable set at BOTH endpoints is
    exactly the condition under which `m-model-evolution` reads a domain
    contraction here as unilateral, so it is the same fact that makes restating
    the Column destroy nothing.
    """
    return not earlier.applicable_entities and not later.applicable_entities


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

    One operation is a cause exactly when a fact IT moved is one of the facts the
    physical difference is made of, so every question below is a filter over the
    whole operation sequence rather than a choice between categories: a
    difference several operations were each needed for names all of them.

    A Column is in a Table because its declaration exists AND because the Table
    materializes the position that declares it. A stored domain is not the one it
    was because the declared domain moved, or because the set of shapes the Table
    stores changed — a Column required of every shape a Table stored is nullable
    once it stores one more.
    """

    operations: tuple[EvolutionOperation, ...]
    later_rows: Mapping[EntityIdentity, Table]
    earlier_rows: Mapping[EntityIdentity, Table]
    later_ancestry: Mapping[EntityIdentity, frozenset[EntityIdentity]]
    later_materialized: Mapping[EntityIdentity, frozenset[Table]]
    earlier_held: Mapping[Table, frozenset[EntityIdentity]]
    earlier_parents: Mapping[EntityIdentity, EntityIdentity]
    declared_in: Mapping[Table, frozenset[EntityIdentity]]

    @staticmethod
    def over(
        operations: Sequence[EvolutionOperation], later: _Endpoint, earlier: _Endpoint | None
    ) -> _Causes:
        return _Causes(
            operations=tuple(operations),
            later_rows=later.rows(),
            earlier_rows={} if earlier is None else earlier.rows(),
            later_ancestry=later.ancestry(),
            later_materialized=later.materialized(),
            earlier_held={} if earlier is None else earlier.holds(),
            earlier_parents={} if earlier is None else earlier.parents(),
            declared_in={
                layout.table: frozenset(slot.declaring_owner for slot in layout.columns)
                for layout in later.facet.tables
            },
        )

    def table(self, table: Table) -> tuple[EvolutionOperation, ...]:
        """Why ``table`` exists now and did not before.

        An Entity brings a Table when it owns rows there or declares one of its
        Columns, so an abstract table-per-hierarchy root is a cause of its
        family's shared Table and an abstract table-per-concrete-subtype root is
        a cause of every concrete Table repeating its members. A created Table is
        all of its Columns at once, so an inheritance alteration that placed this
        Table under a declaring position is a cause of it too.
        """
        return tuple(
            operation
            for operation in self.operations
            if self._adds_to(operation, table) or self._carries_any_position(operation, table)
        )

    def _adds_to(self, operation: EvolutionOperation, table: Table) -> bool:
        """Whether ``operation`` adds an Entity owning rows in ``table`` or declaring a Column."""
        return isinstance(operation, (EntityAdded, ConcreteSubtypeAdded)) and (
            self.later_rows.get(operation.entity) == table
            or operation.entity in self.declared_in.get(table, frozenset())
        )

    def _carries_any_position(self, operation: EvolutionOperation, table: Table) -> bool:
        """Whether ``operation`` is why a Table created here stands under a declaring owner."""
        return any(
            self._carries_position(operation, table, owner)
            for owner in self.declared_in.get(table, frozenset())
        )

    def _carries_position(
        self, operation: EvolutionOperation, table: Table, owner: EntityIdentity
    ) -> bool:
        """Whether ``operation`` is why a Table created here materializes ``owner``.

        A Table that did not exist before materialized nothing before, so the
        surviving Table's question — did this Table already hold that position? —
        has no answer here, and asking it anyway names every reparent beneath
        every owner the new Table happens to hold. What a reparent can have
        changed is where the Entity it moved stands, so that is the whole
        question here: the move carried ``owner`` into this Table when the Table
        materializes the moved Entity's declarations and the Entity would not
        stand under ``owner`` had it stayed where it was. Where the Entity stood
        BEFORE decides nothing — the position it left may itself have moved out
        from under ``owner``, and then staying would have left the created Table
        without ``owner``'s Columns.
        """
        return (
            isinstance(operation, EntityAltered)
            and _reparents(operation)
            and self._moved_under(operation, owner)
            and table in self.later_materialized.get(operation.entity, frozenset())
            and owner in self.later_ancestry.get(operation.entity, frozenset())
        )

    def _moved_under(self, operation: EntityAltered, owner: EntityIdentity) -> bool:
        """Whether the edge THIS alteration changed is why its Entity stands under ``owner``.

        The question is what the Entity would stand under had this alteration not
        happened. Neither endpoint's ancestry answers it, because one evolution
        moves as many positions as it likes: an ancestry is transitive and so
        carries every other move in it, and reading one names an Entity whose own
        ancestor moved for a position it carried nowhere itself — or clears an
        Entity that did carry one, because the position it left has since moved
        away. The edge THIS alteration replaced is the Entity's own earlier
        parent, which no other Entity's move can change.

        So the counterfactual ancestry is the Entity's own position, which no move
        takes from it, together with whatever stands over the position it left,
        read from the LATER model: had it stayed there, it would be carried
        wherever that position went. The alteration carried ``owner`` exactly when
        that ancestry does not already hold it — so a reparent is never why a
        Table materializes the moved Entity's OWN declarations, and one that left
        a position still standing under ``owner`` carried nothing. An Entity that
        stood under nothing, a former family root, took its whole ancestry from
        the move.
        """
        vacated = self.earlier_parents.get(operation.entity)
        return owner != operation.entity and (
            vacated is None or owner not in self.later_ancestry.get(vacated, frozenset())
        )

    def column(self, table: Table, slot: ColumnSlot) -> tuple[EvolutionOperation, ...]:
        """Why ``slot``'s Column is in ``table`` now and was not before.

        Both halves are named together when both were needed: a member added on
        an ancestor lands in a Table that materializes that ancestor for the
        first time only because a reparent carried the ancestor's position here,
        and neither operation alone put the Column there.
        """
        return tuple(
            operation
            for operation in self.operations
            if _brings_declaration(operation, slot)
            or self._carries_declarations(operation, table, slot.declaring_owner)
        )

    def domain(
        self, table: Table, slot: ColumnSlot, *, moved_nullability: bool
    ) -> tuple[EvolutionOperation, ...]:
        """Why ``slot``'s stored domain is not the one it was.

        A nullability that moved additionally answers to whatever changed the
        shapes ``table`` stores, because a Column is required exactly while every
        one of them declares it. Nothing a row-set change does can move a String
        bound, so a domain that only moved the bound never names one.
        """
        return tuple(
            operation
            for operation in self.operations
            if _moves_declared_domain(operation, slot)
            or (moved_nullability and self._changes_stored_shapes(operation, table))
        )

    def index(self, definition: IndexDefinition) -> tuple[EvolutionOperation, ...]:
        """The operations that asked for this Index definition to exist or go.

        An Index whose own operation describes it names it; one an entity-level
        addition brought silently is caused by that addition, exactly as the
        Columns beside it are; and one whose Table materializes its declaring
        Entity only because a reparent carried that position here names that too.
        """
        return tuple(
            operation
            for operation in self.operations
            if _names_index(operation, definition.index)
            or (
                isinstance(operation, (EntityAdded, ConcreteSubtypeAdded))
                and operation.entity == definition.index.entity
            )
            or self._carries_declarations(operation, definition.table, definition.index.entity)
        )

    def _carries_declarations(
        self, operation: EvolutionOperation, table: Table, owner: EntityIdentity
    ) -> bool:
        """Whether ``operation`` is why a surviving ``table`` materializes ``owner``.

        The reparented Entity carries ``owner``'s position into ``table`` when
        its own move put it under ``owner`` and ``table`` materializes its
        declarations — but that carries nothing to a Table already materializing
        that position for anything else, whether a sibling left where it was or
        an ancestry the Entity already stood under. Such a Table was going to
        hold this Column however the reparent went, so the question is asked of
        the Table and never of the Entity that moved.

        The decisive clause reads what ``table`` held earlier, so it answers only
        for a Table both endpoints hold; a Table created here is asked
        `_carries_position` instead.
        """
        return (
            isinstance(operation, EntityAltered)
            and _reparents(operation)
            and self._moved_under(operation, owner)
            and owner in self.later_ancestry.get(operation.entity, frozenset())
            and table in self.later_materialized.get(operation.entity, frozenset())
            and owner not in self.earlier_held.get(table, frozenset())
        )

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


def _moves_declared_domain(operation: EvolutionOperation, slot: ColumnSlot) -> bool:
    """Whether ``operation`` is the member alteration that moved ``slot``'s domain.

    A physical Column holds a Neutral Type, a String bound, and a nullability and
    nothing else, so altering the same declaration's write flag, key membership,
    storage location, or occurrence multiplicity moved no stored domain. The
    question is which FACT moved, never which declaration the operation names.
    """
    match operation:
        case AttributeAltered():
            return operation.attribute == slot.contributor and _moves_domain(operation.deltas)
        case ValueObjectOccurrenceAltered():
            return operation.value_object == slot.contributor and _moves_domain(operation.deltas)
        case _:
            return False


def _moves_domain(deltas: Sequence[AttributeDelta | ValueObjectOccurrenceDelta]) -> bool:
    """Whether any delta moved a fact a stored domain is made of.

    A Neutral Type change is never unilateral, so the two facts left are the
    String bound and nullability — the same pair `m-model-evolution`'s value-domain
    boundary is phrased over, in either direction.
    """
    return any(isinstance(delta, (NullabilityChanged, MaximumLengthChanged)) for delta in deltas)


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
