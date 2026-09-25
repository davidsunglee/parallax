from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from parallax.core.inheritance._facet import (
    FACET_KEY,
    INHERITANCE_MODULE,
    InheritanceEntityFacts,
    InheritanceFacet,
    inheritance_facet,
    member_selection,
)
from parallax.core.metamodel import (
    AbstractRoot,
    AttributeMetadata,
    CompiledMetadata,
    ConcreteSubtype,
    EntityIdentity,
    EntityMetadata,
    FacetKey,
    InheritanceStrategy,
    PersistenceMode,
    PrimaryKey,
    RelationshipDeclaration,
    StorageContainer,
    TablePerConcreteSubtype,
    TablePerHierarchy,
    ValueObjectMetadata,
    inheritance_parent,
)
from parallax.core.model_formation import ModuleIdentity

__all__ = ["MODEL_COMPILER", "root_metadata"]


def root_metadata(
    inheritance: InheritanceFacet, metadata: CompiledMetadata, entity: EntityIdentity
) -> EntityMetadata:
    """The accepted Metadata of ``entity``'s family root, resolved through the facet.

    The one read of a root's own declarations, for downstream compilers over
    ``CompiledMetadata`` and runtime consumers over an accepted Metamodel alike;
    a consumer needing only the family's identity reads the view's ``root``.
    The Inheritance Facet covers every accepted Entity and its root is one of
    them, so an absent view, or a root the metadata does not contain, is a state
    formation output cannot be in and raises a contract failure rather than a
    model defect.
    """
    position = inheritance.entity(entity)
    root = None if position is None else metadata.entity(position.root)
    if root is None:
        raise RuntimeError(
            f"Entity {entity.canonical!r} has no Inheritance Facet view, or names a "
            "family root the accepted Metamodel does not contain"
        )
    return root


def compile_facet(metadata: CompiledMetadata) -> InheritanceFacet:
    """Compile every accepted Entity's family-effective position.

    Roots compile first, whatever order ``metadata`` lists them in, so each
    family's primary key is found once on its root and every descendant carries
    that same accepted Attribute.
    """
    by_identity = {entity.identity: entity for entity in metadata.entities}
    ancestries = {entity.identity: _ancestry(entity, by_identity) for entity in metadata.entities}
    children: dict[EntityIdentity, list[EntityIdentity]] = {}
    for entity in metadata.entities:
        parent = inheritance_parent(entity.inheritance)
        if parent is not None:
            children.setdefault(parent, []).append(entity.identity)
    facts: dict[EntityIdentity, InheritanceEntityFacts] = {}
    for entity in metadata.entities:
        ancestry = ancestries[entity.identity]
        if ancestry[0] == entity.identity:
            facts[entity.identity] = _facts(
                entity, by_identity, ancestry, children, _primary_key(entity)
            )
    for entity in metadata.entities:
        ancestry = ancestries[entity.identity]
        if ancestry[0] != entity.identity:
            facts[entity.identity] = _facts(
                entity, by_identity, ancestry, children, facts[ancestry[0]].primary_key
            )
    return inheritance_facet([facts[entity.identity] for entity in metadata.entities])


def _primary_key(root: EntityMetadata) -> AttributeMetadata:
    """The one primary-key Attribute ``root`` declares for its whole family.

    Validation asks the one-key rule of every position, the root included, so an
    accepted family declares exactly one key and declares it on the root; any
    other count is a state no accepted model can be in.
    """
    keys = [
        attribute
        for attribute in root.declared_attributes
        if isinstance(attribute.primary_key, PrimaryKey)
    ]
    if len(keys) != 1:
        raise RuntimeError(
            f"Entity {root.identity.canonical!r} declares {len(keys)} primary-key "
            "Attributes for its family, which validation should have rejected"
        )
    return keys[0]


def _ancestry(
    entity: EntityMetadata, by_identity: Mapping[EntityIdentity, EntityMetadata]
) -> tuple[EntityIdentity, ...]:
    """``entity``'s chain from its family root down to itself.

    A standalone Entity is its own chain. A participant's chain ends at the
    abstract root that validation established, so a walk that revisits a
    position or tops out anywhere else has reached a state no accepted model
    can be in.
    """
    chain = [entity.identity]
    visited = {entity.identity}
    position = entity
    while True:
        parent = inheritance_parent(position.inheritance)
        if parent is None:
            break
        ancestor = by_identity.get(parent)
        if ancestor is None or ancestor.identity in visited:
            raise RuntimeError(
                f"Entity {entity.identity.canonical!r} has an inheritance ancestry that "
                "validation should have rejected as unresolvable or cyclic"
            )
        visited.add(ancestor.identity)
        chain.append(ancestor.identity)
        position = ancestor
    if entity.inheritance is not None and not isinstance(position.inheritance, AbstractRoot):
        raise RuntimeError(
            f"Entity {entity.identity.canonical!r} reaches no abstract root, which "
            "validation should have rejected"
        )
    return tuple(reversed(chain))


def _concrete_subtypes(
    entity: EntityMetadata,
    by_identity: Mapping[EntityIdentity, EntityMetadata],
    children: Mapping[EntityIdentity, list[EntityIdentity]],
) -> tuple[EntityIdentity, ...]:
    """``entity`` itself when it is concrete, otherwise every concrete leaf below
    it, in canonical order.

    A standalone Entity is its own trivial set: a read of it returns rows of
    exactly one shape, which is what an effective concrete-subtype set names. A
    concrete subtype is likewise its own set without a walk: validation rejects
    a concrete subtype that is the parent of any position, so nothing is below
    it. The set is empty exactly for an abstract position with no concrete
    descendant — an abstract subtype whose own branch composes none, whether or
    not it has abstract children of its own. A family ROOT always reaches one,
    because validation rejects a family that contains no concrete subtype at
    all.
    """
    if entity.inheritance is None or isinstance(entity.inheritance, ConcreteSubtype):
        return (entity.identity,)
    collected: list[EntityIdentity] = []
    pending = [entity.identity]
    while pending:
        current = pending.pop()
        if isinstance(by_identity[current].inheritance, ConcreteSubtype):
            collected.append(current)
        pending.extend(children.get(current, ()))
    return tuple(sorted(collected, key=lambda identity: identity.sort_key))


def _facts(
    entity: EntityMetadata,
    by_identity: Mapping[EntityIdentity, EntityMetadata],
    ancestry: tuple[EntityIdentity, ...],
    children: Mapping[EntityIdentity, list[EntityIdentity]],
    primary_key: AttributeMetadata,
) -> InheritanceEntityFacts:
    root = by_identity[ancestry[0]]
    strategy = root.inheritance.strategy if isinstance(root.inheritance, AbstractRoot) else None
    chain = [by_identity[identity] for identity in ancestry]
    applicable_attributes: list[AttributeMetadata] = []
    applicable_relationships: list[RelationshipDeclaration] = []
    applicable_value_objects: list[ValueObjectMetadata] = []
    for position in chain:
        applicable_attributes.extend(position.declared_attributes)
        applicable_relationships.extend(position.declared_relationships)
        applicable_value_objects.extend(position.declared_value_objects)
    return InheritanceEntityFacts(
        entity=entity.identity,
        root=root.identity,
        primary_key=primary_key,
        strategy=strategy,
        ancestry=ancestry,
        concrete_subtypes=_concrete_subtypes(entity, by_identity, children),
        container=_container(entity, root, strategy),
        tag_column=_tag_column(strategy),
        tag_value=_tag_value(entity, strategy),
        persistence=_persistence(root),
        member_selection=member_selection(applicable_attributes, applicable_value_objects),
        applicable_relationships=tuple(applicable_relationships),
        declared=entity,
    )


def _container(
    entity: EntityMetadata, root: EntityMetadata, strategy: InheritanceStrategy | None
) -> StorageContainer | None:
    """The one container a read or write of this position targets.

    Table-per-hierarchy families share the root's container, so a descendant
    reads it without any descendant declaring it. Every other position uses its
    own declaration, which a table-per-concrete-subtype abstract position does
    not have.
    """
    if isinstance(strategy, TablePerHierarchy):
        return root.declared_container
    return entity.declared_container


def _tag_column(strategy: InheritanceStrategy | None) -> str | None:
    match strategy:
        case TablePerHierarchy(tag_column):
            return tag_column
        case TablePerConcreteSubtype() | None:
            return None


def _tag_value(entity: EntityMetadata, strategy: InheritanceStrategy | None) -> str | None:
    """The value this position's rows carry in the shared table's tag column.

    Only a table-per-hierarchy concrete subtype has one: an abstract position
    owns no rows to discriminate, and the other strategy discriminates by table.
    """
    if not isinstance(strategy, TablePerHierarchy):
        return None
    if isinstance(entity.inheritance, ConcreteSubtype):
        return entity.inheritance.tag_value
    return None


def _persistence(root: EntityMetadata) -> PersistenceMode:
    """The family's effective Persistence Mode, defaulted at its one owner.

    Persistence is root-owned and uniform, so absence on the root is the Read
    Write default rather than an unanswered question.
    """
    if root.declared_persistence is None:
        return PersistenceMode.READ_WRITE
    return root.declared_persistence


class InheritanceModelCompiler:
    """This module's Model Compiler: one facet, no prerequisite facet, no issues."""

    __slots__ = ()

    @property
    def owner(self) -> ModuleIdentity:
        """The catalog identity that owns this compiler."""
        return INHERITANCE_MODULE

    @property
    def facet_key(self) -> FacetKey[InheritanceFacet]:
        """The key the compiled facet is installed under."""
        return FACET_KEY

    @property
    def requires(self) -> frozenset[FacetKey[Any]]:
        """The facets this compiler reads; inheritance formation reads none."""
        return frozenset()

    def compile(
        self, metadata: CompiledMetadata, required_facets: Mapping[FacetKey[Any], object]
    ) -> InheritanceFacet:
        """Compile ``metadata``'s inheritance families into the per-Entity facet."""
        return compile_facet(metadata)


MODEL_COMPILER: Final[InheritanceModelCompiler] = InheritanceModelCompiler()
"""The single Model Compiler instance a composition root supplies.

It is stateless, so one instance serves every formation; the constant exists so
a profile names the compiler rather than constructing a second one."""
