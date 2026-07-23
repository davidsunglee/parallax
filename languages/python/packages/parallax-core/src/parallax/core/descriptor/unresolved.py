"""The descriptor-backed Unresolved Metamodel adapter (m-descriptor).

Parsed descriptor records are interchange carriers; this is where they become
the representation-independent formation input Model Formation begins from. The
adaptation is local and reference-free: every fact that needs no cross-entity
knowledge becomes its final Metadata value here, while a relationship target, a
reverse peer, and an inheritance parent stay Entity References for the
foundational resolver to advance. Nothing in the produced view resolves a
reference, pairs a relationship direction, flattens a family, or offers a
lookup, and no descriptor record reaches a consumer through it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from parallax.core.base import NeutralType
from parallax.core.descriptor import records
from parallax.core.descriptor.errors import DescriptorError
from parallax.core.descriptor.type_spelling import parse_type_spelling
from parallax.core.metamodel import (
    APPLICATION_ASSIGNED,
    MAX,
    NOT_PRIMARY_KEY,
    TABLE_PER_CONCRETE_SUBTYPE,
    AbstractRoot,
    AbstractSubtype,
    AsOfAxisMetadata,
    AttributeIdentity,
    AttributeMetadata,
    AttributePrimaryKey,
    AttributeReference,
    Cardinality,
    Column,
    ConcreteSubtype,
    EntityIdentity,
    EntityReference,
    ExactEntityReference,
    IndexIdentity,
    IndexMetadata,
    InheritanceStrategy,
    Multiplicity,
    NestedValueObjectOccurrenceDeclaration,
    PersistenceMode,
    PkGeneration,
    PrimaryKey,
    RelationshipIdentity,
    RelationshipReference,
    RelativeEntityReference,
    SortDirection,
    StorageContainer,
    Table,
    TablePerHierarchy,
    TemporalDimension,
    UnresolvedDefiningRelationshipDeclaration,
    UnresolvedEntityDeclaration,
    UnresolvedInheritance,
    UnresolvedMetamodel,
    UnresolvedRelationshipDeclaration,
    UnresolvedRelationshipJoin,
    UnresolvedRelationshipOrder,
    UnresolvedReverseRelationshipDeclaration,
    ValueObjectAttributeDeclaration,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
)
from parallax.core.metamodel import Sequence as SequenceGeneration

__all__ = ["unresolved_metamodel"]

_CARDINALITIES: Final[Mapping[records.RelationshipCardinality, Cardinality]] = {
    "one-to-one": Cardinality.ONE_TO_ONE,
    "many-to-one": Cardinality.MANY_TO_ONE,
    "one-to-many": Cardinality.ONE_TO_MANY,
}

_DIRECTIONS: Final[Mapping[str, SortDirection]] = {
    "asc": SortDirection.ASCENDING,
    "desc": SortDirection.DESCENDING,
}

_MULTIPLICITIES: Final[Mapping[records.Multiplicity, Multiplicity]] = {
    "one": Multiplicity.ONE,
    "many": Multiplicity.MANY,
}

_DIMENSIONS: Final[Mapping[records.TemporalDimension, TemporalDimension]] = {
    "validTime": TemporalDimension.VALID_TIME,
    "transactionTime": TemporalDimension.TRANSACTION_TIME,
}


@dataclass(frozen=True, slots=True)
class _EntityDeclaration:
    """One parsed Entity record seen through the Unresolved seam.

    Every member is the descriptor's own local declaration in authoring order.
    The record it was adapted from is not retained: the view is the declaration,
    not a handle back to interchange.
    """

    identity: EntityIdentity
    container: StorageContainer | None
    persistence: PersistenceMode | None
    attributes: tuple[AttributeMetadata, ...]
    relationships: tuple[UnresolvedRelationshipDeclaration, ...]
    value_objects: tuple[ValueObjectOccurrenceDeclaration, ...]
    as_of_axes: tuple[AsOfAxisMetadata, ...]
    inheritance: UnresolvedInheritance | None
    indices: tuple[IndexMetadata, ...]


@dataclass(frozen=True, slots=True)
class _UnresolvedMetamodel:
    """A nonempty enumeration of adapted declarations in document order."""

    entities: tuple[UnresolvedEntityDeclaration, ...]


def unresolved_metamodel(metamodel: records.Metamodel) -> UnresolvedMetamodel:
    """Adapt parsed descriptor records into formation's Unresolved Metamodel.

    Raises :class:`DescriptorError` when a record carries a value the model
    contract cannot represent — an unknown type spelling, an inheritance position
    missing the strategy or parent its role requires, or a value a model type
    refuses such as an empty namespace or a bounded length on a non-text
    Attribute. An empty document is rejected here as well, so formation never
    receives an empty source.
    """
    if not metamodel.entities:
        raise DescriptorError("descriptor declares no entity")
    return _UnresolvedMetamodel(tuple(_adapted(entity) for entity in metamodel.entities))


def _adapted(entity: records.Entity) -> UnresolvedEntityDeclaration:
    """One Entity record as a declaration, with model-value rejections classified.

    Model values enforce their own invariants by refusing construction, and this
    seam is where a record meets them. Their rejection is a fact about the
    descriptor, so it leaves here as a :class:`DescriptorError` naming the Entity
    rather than as the raw refusal.
    """
    try:
        return _declaration(entity)
    except DescriptorError:
        raise
    except ValueError as error:
        raise DescriptorError(f"entity {entity.canonical_name!r}: {error}") from error


def _declaration(entity: records.Entity) -> UnresolvedEntityDeclaration:
    identity = EntityIdentity(entity.namespace, entity.name)
    where = f"entity {identity.canonical!r}"
    return _EntityDeclaration(
        identity=identity,
        container=None if entity.table is None else Table(entity.table),
        persistence=_persistence(entity),
        attributes=tuple(_attribute(identity, member, where) for member in entity.attributes),
        relationships=tuple(_relationship(identity, member) for member in entity.relationships),
        value_objects=tuple(_value_object(member, where) for member in entity.value_objects),
        as_of_axes=tuple(_axis(identity, axis) for axis in entity.as_of_axes),
        inheritance=None if entity.inheritance is None else _inheritance(entity.inheritance, where),
        indices=tuple(_index(identity, member) for member in entity.indices),
    )


def _persistence(entity: records.Entity) -> PersistenceMode | None:
    """The Persistence Mode this Entity itself declares, if any.

    Absence is a declaration fact, not the Read Write default: on a standalone
    Entity or a family root it means the default, and on a descendant it means
    inherit. An explicitly declared Read Write is therefore reported as declared,
    so a family rule can still see a descendant that spelled a mode at all.
    """
    match entity.persistence:
        case None:
            return None
        case "read-write":
            return PersistenceMode.READ_WRITE
        case "read-only":
            return PersistenceMode.READ_ONLY


def _attribute(
    entity: EntityIdentity, attribute: records.Attribute, where: str
) -> AttributeMetadata:
    return AttributeMetadata(
        identity=AttributeIdentity(entity, attribute.name),
        type=_neutral_type(attribute.type, f"{where} attribute {attribute.name!r}"),
        storage=Column(attribute.column),
        primary_key=_primary_key(attribute, where),
        nullable=attribute.nullable,
        max_length=attribute.max_length,
        read_only=attribute.read_only,
        optimistic_locking=attribute.optimistic_locking,
    )


def _primary_key(attribute: records.Attribute, where: str) -> AttributePrimaryKey:
    """The Attribute's primary-key state, generation included on the key branch.

    An omitted generator on a declared key normalizes to Application Assigned,
    which is also how the descriptor's own canonical form spells it.
    """
    if not attribute.primary_key:
        return NOT_PRIMARY_KEY
    generator = attribute.pk_generator
    if generator is None:
        return PrimaryKey(APPLICATION_ASSIGNED)
    return PrimaryKey(_generation(generator, f"{where} attribute {attribute.name!r}"))


def _generation(generator: records.PkGenerator, where: str) -> PkGeneration:
    """The generation a record's strategy denotes, fully parameterized.

    An omitted Sequence sizing parameter takes its semantic default, so an
    accepted Sequence is never partially configured.
    """
    match generator.strategy:
        case "none":
            return APPLICATION_ASSIGNED
        case "max":
            return MAX
        case "sequence":
            name = generator.sequence_name
            if name is None:
                raise DescriptorError(f"{where}: a sequence generation names its sequence")
            return SequenceGeneration(
                name=name,
                batch_size=1 if generator.batch_size is None else generator.batch_size,
                initial_value=1 if generator.initial_value is None else generator.initial_value,
                increment_size=1 if generator.increment_size is None else generator.increment_size,
            )


def _neutral_type(spelling: str, where: str) -> NeutralType:
    resolved = parse_type_spelling(spelling)
    if resolved is None:
        raise DescriptorError(f"{where}: {spelling!r} is not a neutral type spelling")
    return resolved


def _axis(entity: EntityIdentity, axis: records.AsOfAxisMetadata) -> AsOfAxisMetadata:
    return AsOfAxisMetadata(
        dimension=_DIMENSIONS[axis.dimension],
        start_attribute=AttributeIdentity(entity, axis.start_attribute),
        end_attribute=AttributeIdentity(entity, axis.end_attribute),
    )


def _index(entity: EntityIdentity, index: records.Index) -> IndexMetadata:
    return IndexMetadata(
        identity=IndexIdentity(entity, index.name),
        attributes=tuple(AttributeIdentity(entity, name) for name in index.attributes),
        unique=index.unique,
    )


def _relationship(
    entity: EntityIdentity, declaration: records.RelationshipDeclaration
) -> UnresolvedRelationshipDeclaration:
    identity = RelationshipIdentity(entity, declaration.name)
    match declaration:
        case records.DefiningRelationship():
            return UnresolvedDefiningRelationshipDeclaration(
                identity=identity,
                cardinality=_CARDINALITIES[declaration.cardinality],
                join=UnresolvedRelationshipJoin(
                    source=AttributeIdentity(entity, declaration.join.source),
                    target=AttributeReference(
                        entity=_entity_reference(declaration.join.target.entity),
                        name=declaration.join.target.attribute,
                    ),
                ),
                dependent=declaration.dependent,
                order_by=_order_by(declaration.order_by),
            )
        case records.ReverseRelationship():
            owner, _, peer = declaration.reverse_of.rpartition(".")
            return UnresolvedReverseRelationshipDeclaration(
                identity=identity,
                reverse_of=RelationshipReference(entity=_entity_reference(owner), name=peer),
                order_by=_order_by(declaration.order_by),
            )


def _order_by(
    terms: tuple[records.OrderByTerm, ...],
) -> tuple[UnresolvedRelationshipOrder, ...]:
    return tuple(
        UnresolvedRelationshipOrder(term.attr, _DIRECTIONS[term.direction]) for term in terms
    )


def _entity_reference(spelling: str) -> EntityReference:
    """The reference an authored Entity spelling denotes.

    A bare name is relative to whichever Entity declares it, and a qualified
    name is already exact — its namespace is everything before the final dot,
    so a dotted namespace qualifies exactly as a simple one does. The reference
    keeps no owner, no raw spelling, and no fallback state.
    """
    namespace, dot, name = spelling.rpartition(".")
    if not dot:
        return RelativeEntityReference(spelling)
    return ExactEntityReference(EntityIdentity(namespace, name))


def _inheritance(inheritance: records.Inheritance, where: str) -> UnresolvedInheritance:
    match inheritance.role:
        case "root":
            return AbstractRoot(_strategy(inheritance, where))
        case "abstract-subtype":
            return AbstractSubtype(_parent(inheritance, where))
        case "concrete-subtype":
            return ConcreteSubtype(_parent(inheritance, where), inheritance.tag_value)


def _strategy(inheritance: records.Inheritance, where: str) -> InheritanceStrategy:
    match inheritance.strategy:
        case "table-per-hierarchy":
            tag_column = inheritance.tag_column
            if tag_column is None:
                raise DescriptorError(f"{where}: a table-per-hierarchy root declares a tag column")
            return TablePerHierarchy(tag_column)
        case "table-per-concrete-subtype":
            return TABLE_PER_CONCRETE_SUBTYPE
        case None:
            raise DescriptorError(f"{where}: an inheritance root declares a strategy")


def _parent(inheritance: records.Inheritance, where: str) -> EntityReference:
    parent = inheritance.parent
    if parent is None:
        raise DescriptorError(f"{where}: an inheritance descendant names its parent")
    return _entity_reference(parent)


def _value_object(occurrence: records.ValueObject, where: str) -> ValueObjectOccurrenceDeclaration:
    return ValueObjectOccurrenceDeclaration(
        name=occurrence.name,
        storage=Column(occurrence.storage_column),
        shape=_shape(occurrence.attributes, occurrence.value_objects, f"{where}.{occurrence.name}"),
        multiplicity=_MULTIPLICITIES[occurrence.multiplicity],
        nullable=occurrence.nullable,
    )


def _nested_value_object(
    occurrence: records.NestedValueObject, where: str
) -> NestedValueObjectOccurrenceDeclaration:
    return NestedValueObjectOccurrenceDeclaration(
        name=occurrence.name,
        shape=_shape(occurrence.attributes, occurrence.value_objects, f"{where}.{occurrence.name}"),
        multiplicity=_MULTIPLICITIES[occurrence.multiplicity],
        nullable=occurrence.nullable,
    )


def _shape(
    attributes: tuple[records.ValueObjectAttribute, ...],
    value_objects: tuple[records.NestedValueObject, ...],
    where: str,
) -> ValueObjectShapeDeclaration:
    """One occurrence's shape, with a Shape Key minted for this declaration.

    A descriptor spells every occurrence out in full and never names a reusable
    type, so no two occurrences share a declaration node and each therefore
    carries its own key — structurally equal shapes stay distinct declarations.
    """
    return ValueObjectShapeDeclaration(
        key=ValueObjectShapeKey(),
        attributes=tuple(
            ValueObjectAttributeDeclaration(
                name=member.name,
                type=_neutral_type(member.type, f"{where}.{member.name}"),
                nullable=member.nullable,
            )
            for member in attributes
        ),
        value_objects=tuple(_nested_value_object(member, where) for member in value_objects),
    )
