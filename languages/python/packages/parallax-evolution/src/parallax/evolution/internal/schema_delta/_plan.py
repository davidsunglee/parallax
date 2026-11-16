from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from parallax.core.internal import storage_layout
from parallax.core.internal.base import JSON, STRING, NeutralType
from parallax.core.internal.database_binding import (
    ResolvedBinding,
    ResolvedSequence,
    ResolvedTable,
    ResolvedTemporalConstraints,
)
from parallax.core.internal.dialect import Dialect, PhysicalIndexName
from parallax.core.internal.inheritance import (
    InheritanceEntityView,
    InheritanceFacet,
    inheritance_facet_of,
)
from parallax.core.internal.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    IndexIdentity,
    KeySequence,
    Metamodel,
    PrimaryKey,
    TablePerHierarchy,
    inheritance_parent,
)
from parallax.core.internal.storage_layout import (
    ColumnSlot,
    ColumnTier,
    InheritanceDiscriminator,
    StorageLayoutFacet,
    TableLayout,
)
from parallax.evolution.internal.model_evolution import (
    AttributeAdded,
    AttributeAltered,
    AttributeDelta,
    AttributeRemoved,
    ConcreteSubtypeAdded,
    ConcreteSubtypeRemoved,
    CoordinatedEvolution,
    CoordinationReason,
    EntityAdded,
    EntityAltered,
    EntityRemoved,
    EvolutionOperation,
    IndexAdded,
    IndexAltered,
    IndexRemoved,
    InheritanceChanged,
    MaximumLengthChanged,
    NullabilityChanged,
    PrimaryKeyChanged,
    TypeChanged,
    UnilateralEvolution,
    ValueObjectOccurrenceAdded,
    ValueObjectOccurrenceAltered,
    ValueObjectOccurrenceDelta,
)
from parallax.evolution.internal.schema_delta._naming import (
    census,
    collision_groups,
    physical_index_name,
    relation_census,
)
from parallax.evolution.internal.schema_delta._physical import (
    AddColumn,
    CreateExtension,
    CreateIndex,
    CreateSequence,
    CreateTable,
    DocumentRootCheck,
    DropIndex,
    Exclusion,
    IndexDefinition,
    IntervalCheck,
    PhysicalColumn,
    PhysicalOperation,
    RestateColumnDomain,
    TemporalBackingIndex,
)
from parallax.evolution.internal.schema_delta._values import CollisionGroup

__all__ = [
    "Plan",
    "abandoned_by",
    "joined_allocators",
    "plan",
    "temporal_backing_indices",
]

# The framework-owned table-per-hierarchy tag is not a declared Attribute
# (m-inheritance), so it has no declared type to resolve: the generator fixes one
# wide enough for any authored tagValue.
_TAG_TYPE: NeutralType = STRING
_TAG_MAX_LENGTH = 32

_EXCLUSION_PREREQUISITE: Final = "btree_gist"
"""The extension supplying the GiST equality operators an exclusion's scalar
key Columns need beside its interval ranges."""


@dataclass(frozen=True, slots=True)
class Plan:
    """What the database is asked to do, and every name clash that would outlive it.

    The census the clashes are read from spans both endpoints' complete Index
    sets, and the tables and sequences sharing their names' scope, rather than
    the operations below it. An Index the delta never mentions
    is still an object in the database while a new one is created beside it — and
    the operations could not answer the question anyway, because they are built
    by telling definitions apart BY their derived names, so under a collision the
    two are already one and the statements bounding their lifetimes are the ones
    never emitted. Comparing the definitions establishes those lifetimes instead.
    """

    operations: tuple[PhysicalOperation, ...]
    collisions: tuple[CollisionGroup, ...]


def plan(evolution: UnilateralEvolution | CoordinatedEvolution) -> Plan:
    """Every physical operation ``evolution`` asks the database to perform.

    The later binding's dialect fixes the identifier limit every physical index
    name is derived against and the scope index names are unique within.

    A Coordinated Evolution plans only the Table operations its manual steps do
    not carry (:class:`_Withholding`); sequence creations are always planned.
    """
    dialect = evolution.later.dialect
    later = _Endpoint.of(evolution.later)
    earlier = None if evolution.earlier is None else _Endpoint.of(evolution.earlier)
    causes = _Causes.over(evolution.operations, later, earlier)
    withholding = _Withholding.of(evolution, causes)
    operations = tuple(
        operation
        for layout in later.facet.tables
        for operation in _lower(layout, later, earlier, causes, dialect, withholding)
        if not withholding.withholds(layout.mapping_owner, operation.caused_by, column=False)
    )
    return Plan(
        operations=(
            *_prerequisites(operations, evolution.operations),
            *_created_sequences(evolution),
            *operations,
        ),
        collisions=collision_groups(
            census(
                _authored_indices(earlier),
                _authored_indices(later),
                dialect,
                earlier_temporal=(
                    () if earlier is None else temporal_backing_indices(earlier.resolved)
                ),
                later_temporal=temporal_backing_indices(later.resolved),
            ),
            surviving=frozenset(layout.mapping_owner for layout in later.facet.tables),
            relations=relation_census(
                None if earlier is None else earlier.resolved, later.resolved, dialect
            ),
        ),
    )


def _prerequisites(
    operations: Sequence[PhysicalOperation], evolution: Sequence[EvolutionOperation]
) -> tuple[CreateExtension, ...]:
    """The one extension every created exclusion requires, if any Table creates one.

    Its causes are the canonical union of those creations' causes.
    """
    dependents = tuple(
        operation
        for operation in operations
        if isinstance(operation, CreateTable) and operation.exclusion is not None
    )
    if not dependents:
        return ()
    caused_by = tuple(
        operation
        for operation in evolution
        if any(operation in dependent.caused_by for dependent in dependents)
    )
    return (CreateExtension(name=_EXCLUSION_PREREQUISITE, caused_by=caused_by),)


def _created_sequences(
    evolution: UnilateralEvolution | CoordinatedEvolution,
) -> tuple[CreateSequence, ...]:
    """One creation for each native allocator the later binding resolves and
    the earlier one does not, caused by the operations that brought each Entity
    drawing from it there.

    An allocator surviving both endpoints already has its sequence, however its
    consumers changed, so none is created, reset, or repositioned for it.
    """
    held: Mapping[str, object] = {} if evolution.earlier is None else evolution.earlier.sequences
    created = tuple(
        sequence
        for allocator, sequence in evolution.later.sequences.items()
        if isinstance(sequence, ResolvedSequence) and allocator not in held
    )
    if not created:
        return ()
    draws = _draws(evolution.later)
    return tuple(
        CreateSequence(
            sequence=sequence,
            caused_by=_moving(evolution.operations, draws.get(sequence.allocator, ())),
        )
        for sequence in created
    )


def abandoned_by(evolution: CoordinatedEvolution, allocator: str) -> tuple[EvolutionOperation, ...]:
    """The operations that took each Entity drawing from ``allocator`` at the
    earlier endpoint away from it: a removal, a key alteration or removal, or a
    move out of the family drawing from it."""
    return _moving(evolution.operations, _draws(evolution.earlier).get(allocator, ()))


def joined_allocators(
    evolution: CoordinatedEvolution,
) -> Mapping[str, tuple[EvolutionOperation, ...]]:
    """Each native allocator an Entity of the earlier endpoint starts drawing
    from, beside the operations that moved it there.

    Whatever moves it — its key's generation, a key it is promoted to or gains
    in place of another, or a move into a family drawing from the allocator —
    the rows it already stores hold keys the allocator never answered.
    """
    earlier = _draws(evolution.earlier)
    survivors = frozenset(entity.identity for entity in evolution.earlier.meta.entities)
    joined: dict[str, tuple[EvolutionOperation, ...]] = {}
    for allocator, draws in _draws(evolution.later).items():
        held = earlier.get(allocator, frozenset())
        arriving = tuple(draw for draw in draws if draw.entity in survivors and draw not in held)
        if arriving:
            joined[allocator] = _moving(evolution.operations, arriving)
    return joined


@dataclass(frozen=True, slots=True)
class _Draw:
    """An Entity whose family key draws from a native allocator, beside the
    ancestry placing it in that family."""

    entity: EntityIdentity
    key: AttributeIdentity
    ancestry: frozenset[EntityIdentity] = field(compare=False)


def _draws(resolved: ResolvedBinding) -> Mapping[str, frozenset[_Draw]]:
    """Each native allocator ``resolved`` declares beside every Entity drawing from it."""
    families = inheritance_facet_of(resolved.meta)
    drawing: dict[str, set[_Draw]] = {}
    views = (families.entity(entity.identity) for entity in resolved.meta.entities)
    for view in filter(None, views):
        key = view.primary_key
        if isinstance(key.primary_key, PrimaryKey) and isinstance(
            generation := key.primary_key.generation, KeySequence
        ):
            drawing.setdefault(generation.name, set()).add(
                _Draw(view.entity, key.identity, frozenset(view.ancestry))
            )
    return {allocator: frozenset(held) for allocator, held in drawing.items()}


def _moving(
    operations: Sequence[EvolutionOperation], draws: Iterable[_Draw]
) -> tuple[EvolutionOperation, ...]:
    """The operations, in canonical order, that add, remove, or move any of ``draws``."""
    chosen = tuple(draws)
    return tuple(
        operation for operation in operations if any(_moves(operation, draw) for draw in chosen)
    )


def _moves(operation: EvolutionOperation, draw: _Draw) -> bool:
    match operation:
        case EntityAdded() | EntityRemoved() | ConcreteSubtypeAdded() | ConcreteSubtypeRemoved():
            return operation.entity == draw.entity
        case AttributeAdded() | AttributeRemoved():
            return operation.attribute == draw.key
        case AttributeAltered():
            return operation.attribute == draw.key and any(
                isinstance(delta, PrimaryKeyChanged) for delta in operation.deltas
            )
        case EntityAltered():
            return operation.entity in draw.ancestry and _reparents(operation)
        case _:
            return False


def temporal_backing_indices(resolved: ResolvedBinding) -> tuple[TemporalBackingIndex, ...]:
    """The Index behind each temporal primary key and exclusion one endpoint holds."""
    held: list[TemporalBackingIndex] = []
    for table in resolved.tables:
        constraints = table.temporal_constraints
        if constraints is None:
            continue
        exclusion = _exclusion(constraints)
        held.append(
            TemporalBackingIndex(
                table=table,
                kind="primaryKey",
                columns=tuple(slot.column for slot in constraints.definition.primary_key.columns),
                name=PhysicalIndexName(constraints.primary_key_name),
            )
        )
        held.append(
            TemporalBackingIndex(
                table=table,
                kind="exclusion",
                columns=(
                    *exclusion.equal,
                    *(column for interval in exclusion.overlapping for column in interval),
                ),
                name=PhysicalIndexName(exclusion.name),
            )
        )
    return tuple(held)


def _authored_indices(endpoint: _Endpoint | None) -> tuple[IndexDefinition, ...]:
    """Every authored Index one endpoint holds, resolved into the Table holding it."""
    if endpoint is None:
        return ()
    return tuple(
        definition
        for layout in endpoint.facet.tables
        for definition in _index_definitions(endpoint, layout)
    )


def _lower(
    layout: TableLayout,
    later: _Endpoint,
    earlier: _Endpoint | None,
    causes: _Causes,
    dialect: Dialect,
    withholding: _Withholding,
) -> Iterator[PhysicalOperation]:
    """Everything one target Table needs, given what the earlier edition held.

    A Table the earlier edition did not have is created whole; one it had is
    carried forward Column by Column and Index by Index. No Table and no Column
    is ever taken away: nothing that destroys a stored shape is unilateral, so
    the algebra has no case for it.
    """
    defined = tuple(_index_definitions(later, layout))
    before = None if earlier is None else earlier.facet.table(layout.mapping_owner)
    if before is None or earlier is None:
        yield from _create(layout, later, defined, causes.table(layout.mapping_owner), dialect)
        return
    yield from _columns(layout, before, later, earlier, causes, withholding)
    yield from _indices(tuple(_index_definitions(earlier, before)), defined, causes, dialect)


@dataclass(frozen=True, slots=True)
class _Endpoint:
    """One model under its binding, beside the compiled facets the lowering reads."""

    resolved: ResolvedBinding
    model: Metamodel
    facet: StorageLayoutFacet
    family: InheritanceFacet

    @staticmethod
    def of(resolved: ResolvedBinding) -> _Endpoint:
        model = resolved.meta
        return _Endpoint(
            resolved=resolved,
            model=model,
            facet=storage_layout.storage_layout_facet_of(model),
            family=inheritance_facet_of(model),
        )

    def rows(self) -> Mapping[EntityIdentity, EntityIdentity]:
        """The mapping owner of the Table each row-owning Entity's own rows sit in.

        A rowless abstract position has no entry: it owns no row, so the Columns
        it declares are answered for by the concrete subtypes that do.
        """
        return {
            entity.identity: view.layout.mapping_owner
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

    def materialized(self) -> Mapping[EntityIdentity, frozenset[EntityIdentity]]:
        """The Tables whose Columns hold each Entity's declarations, by mapping owner.

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
                owner
                for position in (view, *(views[concrete] for concrete in view.concrete_subtypes))
                if (owner := _mapping_owner(position)) is not None
            )
            for identity, view in views.items()
        }

    def holds(self) -> Mapping[EntityIdentity, frozenset[EntityIdentity]]:
        """The ancestry each Table materializes, keyed by its mapping owner, as
        Entities whose declarations it holds."""
        held: dict[EntityIdentity, set[EntityIdentity]] = {}
        for identity, owners in self.materialized().items():
            for owner in owners:
                held.setdefault(owner, set()).add(identity)
        return {owner: frozenset(identities) for owner, identities in held.items()}


def _mapping_owner(position: InheritanceEntityView) -> EntityIdentity | None:
    """The owner of the Table ``position`` is stored in, or absence where it has none.

    A table-per-hierarchy position is stored in its root's shared Table; any
    other position holding a Table owns it.
    """
    if position.container is None:
        return None
    return position.root if isinstance(position.strategy, TablePerHierarchy) else position.entity


def _create(
    layout: TableLayout,
    later: _Endpoint,
    definitions: Sequence[IndexDefinition],
    causes: tuple[EvolutionOperation, ...],
    dialect: Dialect,
) -> Iterator[PhysicalOperation]:
    """One new Table, then each authored Index it holds as its own statement.

    A Table the earlier edition did not have is created whole, with a temporal
    Table's named primary key, interval checks, and exclusion, and a Document
    Table's root-object check, inline. A Table that survives gains none of them:
    its stored rows are the operator's to validate before any constraint governs
    them. An Index created as part of creating its Table is caused by everything
    that caused the Table: it arrives because the declarations the Table
    materializes arrived, and no Index operation of its own describes it.
    """
    table = later.resolved.table(layout.mapping_owner)
    constraints = table.temporal_constraints
    yield CreateTable(
        table=table,
        columns=tuple(_physical_column(later.model, slot) for slot in layout.columns),
        primary_key=tuple(slot.column for slot in layout.physical_primary_key),
        checks=_checks(table),
        caused_by=causes,
        primary_key_name=None if constraints is None else constraints.primary_key_name,
        exclusion=None if constraints is None else _exclusion(constraints),
    )
    for definition in definitions:
        yield CreateIndex(
            definition=definition,
            name=physical_index_name(definition, dialect),
            caused_by=causes,
        )


def _exclusion(constraints: ResolvedTemporalConstraints) -> Exclusion:
    """The Table's non-overlap constraint, its intervals in canonical axis order."""
    definition = constraints.definition
    axes = (definition.valid_axis, definition.transaction_axis)
    return Exclusion(
        name=constraints.exclusion_name,
        equal=tuple(slot.column for slot in definition.logical_key),
        overlapping=tuple(
            (axis.start.column, axis.end.column) for axis in axes if axis is not None
        ),
    )


def _checks(table: ResolvedTable) -> tuple[IntervalCheck | DocumentRootCheck, ...]:
    """Each temporal axis's interval check in canonical axis order, then the
    document root check."""
    checks: list[IntervalCheck | DocumentRootCheck] = []
    constraints = table.temporal_constraints
    if constraints is not None:
        definition = constraints.definition
        axes = (
            (definition.valid_axis, constraints.valid_check_name),
            (definition.transaction_axis, constraints.transaction_check_name),
        )
        checks.extend(
            IntervalCheck(name=name, start=axis.start.column, end=axis.end.column)
            for axis, name in axes
            if axis is not None and name is not None
        )
    root = table.document_root_constraint
    if root is not None:
        checks.append(DocumentRootCheck(name=root.check_name, column=root.definition.slot.column))
    return tuple(checks)


def _columns(
    layout: TableLayout,
    before: TableLayout,
    later: _Endpoint,
    earlier: _Endpoint,
    causes: _Causes,
    withholding: _Withholding,
) -> Iterator[PhysicalOperation]:
    """Each Column this Table gains, and each whose value domain moved.

    A Column both editions hold identically asks for nothing. One whose domain
    moved is restated as the later edition's, and the restatement is legal in
    exactly the two shapes that destroy no stored value: the later domain admits
    every value the earlier did, or the Column stores no shape at either endpoint
    and so holds no value at all. Narrowing a domain rows are stored against is
    not unilateral, so no accepted input reaches this Column any other way.
    """
    table = later.resolved.table(layout.mapping_owner)
    for slot in layout.columns:
        held = before.column(slot.column)
        target = _physical_column(later.model, slot)
        if held is None:
            added = causes.column(layout.mapping_owner, slot)
            if not withholding.withholds(layout.mapping_owner, added, column=True):
                yield AddColumn(table=table, column=target, caused_by=added)
            continue
        source = _physical_column(earlier.model, held)
        if source == target:
            continue
        caused_by = causes.domain(
            layout.mapping_owner, slot, moved_nullability=source.nullable != target.nullable
        )
        if withholding.withholds(layout.mapping_owner, caused_by, column=True):
            continue
        if not _expands(source, target) and not _stores_nothing(held, slot):
            if withholding.coordinated:
                continue
            raise ValueError(  # pragma: no cover - classification refuses this pair
                f"{layout.table.name}.{slot.column.name}: a stored domain narrowed"
            )
        yield RestateColumnDomain(table=table, earlier=source, later=target, caused_by=caused_by)


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
class _Withholding:
    """Which Table operations a coordinated migration leaves to its manual steps.

    A database-coordinated operation's change is the deployment's to make, so
    no statement is generated for a Table operation it is a cause of, nor for a
    Column of a Table where such an operation alters an Entity whose rows it
    stores at either endpoint: which declarations those rows answer to, and so
    whether the Column is required of them, is what moved. A physical difference no operation
    is a cause of is one such an operation made through a fact this lowering
    does not attribute — a storage location or layout moved — and is withheld
    too. A domain narrowed by an authoring-only change keeps its earlier, wider
    form: such a change leaves the rows it no longer describes in place.

    A Unilateral Evolution withholds nothing.
    """

    coordinated: bool
    database: frozenset[EvolutionOperation]
    causes: _Causes

    @staticmethod
    def of(evolution: UnilateralEvolution | CoordinatedEvolution, causes: _Causes) -> _Withholding:
        if isinstance(evolution, UnilateralEvolution):
            return _Withholding(coordinated=False, database=frozenset(), causes=causes)
        return _Withholding(
            coordinated=True,
            database=frozenset(
                requirement.operation
                for requirement in evolution.coordination_requirements
                if CoordinationReason.DATABASE_MIGRATION_REQUIRED in requirement.reasons
            ),
            causes=causes,
        )

    def withholds(
        self, table: EntityIdentity, caused_by: Sequence[EvolutionOperation], *, column: bool
    ) -> bool:
        """Whether a Table operation on ``table`` caused by ``caused_by`` is
        left to a manual step; ``column`` marks a Column's addition or
        restatement."""
        if not self.coordinated:
            return False
        if not caused_by or self.database.intersection(caused_by):
            return True
        return column and any(
            self.causes.alters_rows_in(operation, table) for operation in self.database
        )


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

    Every Table here is named by its mapping owner, never by its declared name,
    so independent mappings are never one Table.
    """

    operations: tuple[EvolutionOperation, ...]
    later_rows: Mapping[EntityIdentity, EntityIdentity]
    earlier_rows: Mapping[EntityIdentity, EntityIdentity]
    later_ancestry: Mapping[EntityIdentity, frozenset[EntityIdentity]]
    later_materialized: Mapping[EntityIdentity, frozenset[EntityIdentity]]
    earlier_held: Mapping[EntityIdentity, frozenset[EntityIdentity]]
    earlier_parents: Mapping[EntityIdentity, EntityIdentity]
    later_parents: Mapping[EntityIdentity, EntityIdentity]
    declared_in: Mapping[EntityIdentity, frozenset[EntityIdentity]]

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
            later_parents=later.parents(),
            declared_in={
                layout.mapping_owner: frozenset(slot.declaring_owner for slot in layout.columns)
                for layout in later.facet.tables
            },
        )

    def table(self, table: EntityIdentity) -> tuple[EvolutionOperation, ...]:
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
            if self._adds_to(operation, table)
            or any(
                self._carries_declarations(operation, table, owner)
                for owner in self.declared_in.get(table, frozenset())
            )
        )

    def _adds_to(self, operation: EvolutionOperation, table: EntityIdentity) -> bool:
        """Whether ``operation`` adds an Entity owning rows in ``table`` or declaring a Column."""
        return isinstance(operation, (EntityAdded, ConcreteSubtypeAdded)) and (
            self.later_rows.get(operation.entity) == table
            or operation.entity in self.declared_in.get(table, frozenset())
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
        """
        return owner not in self._counterfactual_ancestry(operation.entity)

    def _counterfactual_ancestry(self, entity: EntityIdentity) -> frozenset[EntityIdentity]:
        """What ``entity`` would stand under had its own alteration not happened.

        The counterfactual world puts ``entity`` back on the parent edge it left
        and leaves every other Entity where the LATER model has it, since staying
        put means being carried wherever the vacated position went. So the
        ancestry is walked one parent at a time from that position rather than
        read as the vacated position's later ancestry: two alterations can
        exchange a pair of edges, and then the vacated position stands under the
        moved Entity itself in the later model. Restoring the edge closes a loop,
        and the walk halts there with nothing above it — which is the honest
        answer, because a world that cannot be a model is a world where nothing
        stands over the Entity at all, and the alteration answers for every
        position it now stands under.

        ``entity`` is in its own counterfactual ancestry because no move takes an
        Entity from its own position, so a reparent is never why a Table
        materializes the moved Entity's OWN declarations. An Entity that stood
        under nothing, a former family root, takes its whole ancestry from the
        move and this is the ancestry of one.
        """
        standing = {entity}
        position = self.earlier_parents.get(entity)
        while position is not None and position not in standing:
            standing.add(position)
            position = self.later_parents.get(position)
        return frozenset(standing)

    def column(self, table: EntityIdentity, slot: ColumnSlot) -> tuple[EvolutionOperation, ...]:
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
        self, table: EntityIdentity, slot: ColumnSlot, *, moved_nullability: bool
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
            or self._carries_declarations(
                operation, definition.mapping_owner, definition.index.entity
            )
        )

    def _carries_declarations(
        self, operation: EvolutionOperation, table: EntityIdentity, owner: EntityIdentity
    ) -> bool:
        """Whether ``operation`` is why ``table`` materializes ``owner``.

        The reparented Entity carries ``owner``'s position into ``table`` when
        its own move put it under ``owner`` and ``table`` materializes its
        declarations — but that carries nothing to a Table already materializing
        that position for anything else, whether a sibling left where it was or
        an ancestry the Entity already stood under. Such a Table was going to
        hold this Column however the reparent went, so the question is asked of
        the Table and never of the Entity that moved.

        A Table created here answers to this same rule rather than one of its
        own: it materialized nothing before, so the last clause can only find
        that it did not already hold the position, and the counterfactual decides
        alone.
        """
        return (
            isinstance(operation, EntityAltered)
            and _reparents(operation)
            and self._moved_under(operation, owner)
            and owner in self.later_ancestry.get(operation.entity, frozenset())
            and table in self.later_materialized.get(operation.entity, frozenset())
            and owner not in self.earlier_held.get(table, frozenset())
        )

    def alters_rows_in(self, operation: EvolutionOperation, table: EntityIdentity) -> bool:
        """Whether ``operation`` alters an Entity owning rows in ``table`` at either endpoint."""
        return isinstance(operation, EntityAltered) and table in (
            self.later_rows.get(operation.entity),
            self.earlier_rows.get(operation.entity),
        )

    def _changes_stored_shapes(self, operation: EvolutionOperation, table: EntityIdentity) -> bool:
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
    or storage location moved no stored domain. A multiplicity change does move
    a scalar slot's Column between a scalar and a Structured Column, but it is
    never unilateral and so never reaches here. The question is which FACT moved,
    never which declaration the operation names.
    """
    match operation:
        case AttributeAltered():
            return operation.attribute == slot.contributor and _moves_domain(operation.deltas)
        case ValueObjectOccurrenceAltered():
            return operation.value_object == slot.contributor and _moves_domain(operation.deltas)
        case _:
            return False


def _moves_domain(deltas: Sequence[AttributeDelta | ValueObjectOccurrenceDelta]) -> bool:
    """Whether any delta moved a fact a stored domain is made of: its Neutral
    Type, its String bound, or its nullability.

    A Neutral Type change is never unilateral, so in a Unilateral Evolution the
    two facts left are the String bound and nullability — the same pair
    `m-model-evolution`'s value-domain boundary is phrased over, in either
    direction.
    """
    return any(
        isinstance(delta, (TypeChanged, NullabilityChanged, MaximumLengthChanged))
        for delta in deltas
    )


def _reparents(operation: EntityAltered) -> bool:
    """Whether ``operation`` changes which declarations a surviving Entity holds."""
    return any(isinstance(delta, InheritanceChanged) for delta in operation.deltas)


def _names_index(operation: EvolutionOperation, index: IndexIdentity) -> bool:
    return (
        isinstance(operation, (IndexAdded, IndexRemoved, IndexAltered)) and operation.index == index
    )


def _physical_column(model: Metamodel, slot: ColumnSlot) -> PhysicalColumn:
    """One layout slot with the value domain its contributor declares.

    Every document-tier slot is a Structured Column of the neutral `json` type,
    which the dialect maps to its own structured-document type: a top-level
    Value Object's own Column, a scalar collection's own Column, and a
    Relational Document Layout's shared Structured Column alike. The tier
    decides this before an Attribute's declared type is read, because a scalar
    collection's type names its elements rather than its Column.
    """
    contributor = slot.contributor
    if isinstance(contributor, InheritanceDiscriminator):
        return PhysicalColumn(slot.column, _TAG_TYPE, _TAG_MAX_LENGTH, slot.effective_nullable)
    if slot.tier is ColumnTier.DOCUMENT or not isinstance(contributor, AttributeIdentity):
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


def _index_definitions(endpoint: _Endpoint, layout: TableLayout) -> Iterator[IndexDefinition]:
    """Every authored Index this Table holds, in the layout's canonical order,
    on the table ``endpoint``'s binding resolves.

    The derived primary-key Index is emitted inline by ``create table`` as the
    key itself, so a separate statement for it would be a second object over the
    same columns.
    """
    table = endpoint.resolved.table(layout.mapping_owner)
    model = endpoint.model
    for physical in layout.indices:
        if physical == layout.primary_key_index:
            continue
        yield IndexDefinition(
            table=table,
            index=physical.declaration.identity,
            components=physical.declaration.attributes,
            column_attributes=physical.column_attributes,
            columns=tuple(_physical_column(model, slot) for slot in physical.columns),
            unique=physical.declaration.unique,
        )
