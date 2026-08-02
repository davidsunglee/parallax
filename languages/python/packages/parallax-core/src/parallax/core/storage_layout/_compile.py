"""Eager compilation of canonical immutable physical Table Layouts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

from parallax.core.inheritance import FACET_KEY as INHERITANCE_FACET_KEY
from parallax.core.inheritance import InheritanceEntityView, InheritanceFacet
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    Column,
    CompiledMetadata,
    ConcreteSubtype,
    Document,
    EntityIdentity,
    EntityMetadata,
    FacetKey,
    MemberIdentity,
    NestedValueObjectMetadata,
    PrimaryKey,
    Table,
    TablePerHierarchy,
    ValueObjectIdentity,
    ValueObjectMetadata,
)
from parallax.core.model_formation import ModuleIdentity
from parallax.core.relationship import FACET_KEY as RELATIONSHIP_FACET_KEY
from parallax.core.relationship import RelationshipFacet
from parallax.core.storage_layout._facet import (
    FACET_KEY,
    ColumnContributor,
    ColumnSlot,
    ColumnTier,
    DirectColumn,
    DiscriminatorAssignment,
    DocumentPath,
    InheritanceDiscriminator,
    MemberPlacement,
    PositionColumn,
    PositionColumnFacts,
    PositionMemberFacts,
    RelationalDocument,
    SlotOrdinalSelection,
    StorageLayoutEntityFacts,
    StorageLayoutFacet,
    StorageLayoutFamilyFacts,
    TableLayout,
    storage_layout_facet,
    table_layout,
)
from parallax.core.storage_layout._roles import DirectRoles
from parallax.core.storage_layout._rules import STORAGE_LAYOUT_MODULE

__all__ = [
    "MODEL_COMPILER",
    "StorageLayoutModelCompiler",
    "classify_attribute_tier",
    "compile_facet",
]


@dataclass(frozen=True, slots=True)
class _LayoutGroup:
    table: Table
    mapping_owner: EntityIdentity
    root: EntityIdentity
    row_owners: tuple[EntityIdentity, ...]
    attributes: tuple[AttributeMetadata, ...]
    value_objects: tuple[ValueObjectMetadata, ...]
    tag_column: Column | None
    document: Document | None


@dataclass(frozen=True, slots=True)
class _SlotDraft:
    column: Column
    tier: ColumnTier
    contributor: ColumnContributor
    declaring_owner: EntityIdentity
    declared_nullable: bool
    applicable_entities: frozenset[EntityIdentity]


@dataclass(frozen=True, slots=True)
class _CompilationIndex:
    entities: tuple[EntityMetadata, ...]
    entities_by_identity: Mapping[EntityIdentity, EntityMetadata]
    views_by_identity: Mapping[EntityIdentity, InheritanceEntityView]
    ancestries_by_identity: Mapping[EntityIdentity, tuple[EntityIdentity, ...]]
    family_members_by_root: Mapping[EntityIdentity, tuple[EntityMetadata, ...]]
    roots: tuple[EntityIdentity, ...]
    joined: frozenset[AttributeIdentity]


def classify_attribute_tier(
    attribute: AttributeMetadata,
    temporal_designations: frozenset[AttributeIdentity],
    audit_designations: frozenset[AttributeIdentity] = frozenset(),
) -> ColumnTier:
    """Classify one Attribute with the normative overlap precedence.

    The optional audit-designation input creates no declaration, and temporal
    designation wins over a revision-instant alias.
    """
    if isinstance(attribute.primary_key, PrimaryKey):
        return ColumnTier.IDENTITY
    if attribute.identity in temporal_designations:
        return ColumnTier.TEMPORAL
    if attribute.identity in audit_designations:
        return ColumnTier.AUDIT
    return ColumnTier.DOMAIN


def _entity_view(inheritance: InheritanceFacet, identity: EntityIdentity) -> InheritanceEntityView:
    view = inheritance.entity(identity)
    if view is None:
        raise RuntimeError(
            f"Entity {identity.canonical!r} has no Inheritance Facet view in accepted metadata"
        )
    return view


def _declared_endpoint(
    endpoint: AttributeIdentity,
    views_by_identity: Mapping[EntityIdentity, InheritanceEntityView],
) -> AttributeIdentity:
    """The Identity the Attribute ``endpoint`` addresses actually bears.

    An endpoint is addressed at the position that names it, so an inherited one
    carries the descendant's Identity while its accepted declaration carries the
    ancestor's. Residency compares declarations, so the addressed Identity is
    resolved back to the declared one here.
    """
    view = views_by_identity.get(endpoint.entity)
    declared = None if view is None else view.applicable_attribute(endpoint.name)
    return endpoint if declared is None else declared.identity


def _compilation_index(
    metadata: CompiledMetadata,
    inheritance: InheritanceFacet,
    relationship: RelationshipFacet,
) -> _CompilationIndex:
    """Index accepted Entities, family facts, and join endpoints in one metadata visit.

    Both endpoints of every direction are collected, because both stay direct
    Columns under Relational Document Layout. A reverse direction names the same
    pair its defining peer does, with the sides exchanged.
    """
    entities = tuple(metadata.entities)
    entities_by_identity = {entity.identity: entity for entity in entities}
    views_by_identity: dict[EntityIdentity, InheritanceEntityView] = {}
    ancestries_by_identity: dict[EntityIdentity, tuple[EntityIdentity, ...]] = {}
    family_members: dict[EntityIdentity, list[EntityMetadata]] = {}
    roots: list[EntityIdentity] = []
    addressed: list[AttributeIdentity] = []
    for entity in entities:
        view = _entity_view(inheritance, entity.identity)
        views_by_identity[entity.identity] = view
        ancestries_by_identity[entity.identity] = tuple(view.ancestry)
        family_members.setdefault(view.root, []).append(entity)
        if view.root == entity.identity:
            roots.append(entity.identity)
        for direction in relationship.relationships(entity.identity) or ():
            addressed.extend((direction.join.source, direction.join.target))
    joined = {_declared_endpoint(endpoint, views_by_identity) for endpoint in addressed}
    return _CompilationIndex(
        entities=entities,
        entities_by_identity=entities_by_identity,
        views_by_identity=views_by_identity,
        ancestries_by_identity=ancestries_by_identity,
        family_members_by_root={root: tuple(members) for root, members in family_members.items()},
        roots=tuple(roots),
        joined=frozenset(joined),
    )


def _family_members(
    index: _CompilationIndex, root: EntityIdentity
) -> tuple[tuple[AttributeMetadata, ...], tuple[ValueObjectMetadata, ...]]:
    """The complete family declaration stream behind layout composition.

    Concrete positions establish canonical branch order. Their ancestors are
    encountered root first, concrete declarations follow in canonical order,
    and any rowless branch with no concrete descendant follows deterministically
    so every accepted family participant still contributes to the shared shape.
    """
    family = index.family_members_by_root[root]
    root_view = index.views_by_identity[root]
    concrete_entities = tuple(root_view.concrete_subtypes)
    encountered = set(concrete_entities)
    contributors: list[EntityIdentity] = []
    for concrete in concrete_entities:
        for ancestor in index.ancestries_by_identity[concrete][:-1]:
            if ancestor in encountered:
                continue
            encountered.add(ancestor)
            contributors.append(ancestor)
    contributors.extend(concrete_entities)
    for entity in sorted(
        family,
        key=lambda entity: (entity.identity != root, entity.identity.sort_key),
    ):
        if entity.identity in encountered:
            continue
        encountered.add(entity.identity)
        contributors.append(entity.identity)
    by_identity = {entity.identity: entity for entity in family}
    return (
        tuple(
            attribute
            for identity in contributors
            for attribute in by_identity[identity].declared_attributes
        ),
        tuple(
            value_object
            for identity in contributors
            for value_object in by_identity[identity].declared_value_objects
        ),
    )


def _document_layout(index: _CompilationIndex, root: EntityIdentity) -> Document | None:
    """``root``'s own declared ``Document`` layout, or absence for ``Columns``.

    Storage Layout is root-owned, so a participant's effective layout is derived
    from the family root's own declared metadata on every lookup rather than
    copied onto descendants.
    """
    layout = index.entities_by_identity[root].declared_layout
    return layout if isinstance(layout, Document) else None


def _groups(index: _CompilationIndex) -> tuple[_LayoutGroup, ...]:
    groups: list[_LayoutGroup] = []
    for entity in index.entities:
        view = index.views_by_identity[entity.identity]
        strategy = view.strategy
        if strategy is None:
            if entity.declared_container is None:
                continue
            groups.append(
                _LayoutGroup(
                    table=entity.declared_container,
                    mapping_owner=entity.identity,
                    root=entity.identity,
                    row_owners=(entity.identity,),
                    attributes=tuple(entity.declared_attributes),
                    value_objects=tuple(entity.declared_value_objects),
                    tag_column=None,
                    document=_document_layout(index, entity.identity),
                )
            )
            continue
        if isinstance(strategy, TablePerHierarchy):
            if entity.identity != view.root:
                continue
            if entity.declared_container is None:
                raise RuntimeError(
                    f"TPH root {entity.identity.canonical!r} has no Table after validation"
                )
            attributes, value_objects = _family_members(index, view.root)
            groups.append(
                _LayoutGroup(
                    table=entity.declared_container,
                    mapping_owner=entity.identity,
                    root=view.root,
                    row_owners=tuple(view.concrete_subtypes),
                    attributes=attributes,
                    value_objects=value_objects,
                    tag_column=Column(strategy.tag_column),
                    document=_document_layout(index, view.root),
                )
            )
            continue
        if not isinstance(entity.inheritance, ConcreteSubtype):
            continue
        if entity.declared_container is None:
            raise RuntimeError(
                f"TPCS concrete {entity.identity.canonical!r} has no Table after validation"
            )
        groups.append(
            _LayoutGroup(
                table=entity.declared_container,
                mapping_owner=entity.identity,
                root=view.root,
                row_owners=(entity.identity,),
                attributes=tuple(view.applicable_attributes),
                value_objects=tuple(view.applicable_value_objects),
                tag_column=None,
                document=_document_layout(index, view.root),
            )
        )
    groups.sort(key=lambda group: group.mapping_owner.sort_key)
    seen: set[Table] = set()
    for group in groups:
        if group.table in seen:
            raise RuntimeError(
                f"Table {group.table.name!r} has multiple mapping owners after validation"
            )
        seen.add(group.table)
    return tuple(groups)


def _temporal_designations(root: EntityMetadata) -> frozenset[AttributeIdentity]:
    return frozenset(
        attribute
        for axis in root.declared_as_of_axes
        for attribute in (axis.start_attribute, axis.end_attribute)
    )


def _temporal_start_designations(root: EntityMetadata) -> tuple[AttributeIdentity, ...]:
    """Temporal starts in canonical dimension rank with duplicates removed."""
    starts: list[AttributeIdentity] = []
    seen: set[AttributeIdentity] = set()
    for axis in sorted(root.declared_as_of_axes, key=lambda axis: axis.dimension.value):
        if axis.start_attribute in seen:
            continue
        seen.add(axis.start_attribute)
        starts.append(axis.start_attribute)
    return tuple(starts)


def _applicability(
    index: _CompilationIndex,
    row_owners: Sequence[EntityIdentity],
) -> tuple[
    dict[AttributeIdentity, set[EntityIdentity]],
    dict[ValueObjectIdentity, set[EntityIdentity]],
]:
    attributes: dict[AttributeIdentity, set[EntityIdentity]] = {}
    value_objects: dict[ValueObjectIdentity, set[EntityIdentity]] = {}
    for concrete in row_owners:
        view = index.views_by_identity[concrete]
        for attribute in view.applicable_attributes:
            attributes.setdefault(attribute.identity, set()).add(concrete)
        for value_object in view.applicable_value_objects:
            value_objects.setdefault(value_object.identity, set()).add(concrete)
    return attributes, value_objects


def _interned(
    values: set[EntityIdentity],
    intern: dict[frozenset[EntityIdentity], frozenset[EntityIdentity]],
) -> frozenset[EntityIdentity]:
    frozen = frozenset(values)
    return intern.setdefault(frozen, frozen)


def _interned_ordinal_selection(
    layout: TableLayout,
    entity: EntityIdentity,
    intern: dict[int, SlotOrdinalSelection],
) -> SlotOrdinalSelection:
    bits = sum(
        1 << ordinal
        for ordinal, slot in enumerate(layout.columns)
        if entity in slot.applicable_entities
    )
    return intern.setdefault(bits, SlotOrdinalSelection(bits))


def _effective_nullable(
    draft: _SlotDraft,
    key_set: frozenset[ColumnContributor],
    row_owners: frozenset[EntityIdentity],
) -> bool:
    """Whether ``draft``'s Column admits ``NULL``, by the normative cascade.

    The shared Structured Column is never nullable: every governed row carries a
    document, and a row with no applicable document-resident member carries the
    empty object rather than ``NULL``.
    """
    if draft.contributor in key_set or draft.tier is ColumnTier.DISCRIMINATOR:
        return False
    if isinstance(draft.contributor, RelationalDocument):
        return False
    if draft.applicable_entities != row_owners:
        return True
    return draft.declared_nullable


def _contained_members(
    occurrence: ValueObjectMetadata | NestedValueObjectMetadata,
    prefix: tuple[str, ...],
) -> list[tuple[MemberIdentity, tuple[str, ...]]]:
    """Every member inside ``occurrence``, paired with its path below ``prefix``.

    Each contained member extends its container's path by one canonical segment
    at every depth. A ``Many`` occurrence contributes exactly one segment like
    any other: that the path crosses a collection is recorded by the
    occurrence's own declared multiplicity rather than by a synthetic segment.
    """
    members: list[tuple[MemberIdentity, tuple[str, ...]]] = []
    for leaf in occurrence.attributes:
        members.append((leaf.identity, (*prefix, leaf.identity.name)))
    for nested in occurrence.value_objects:
        path = (*prefix, nested.identity.path[-1])
        members.append((nested.identity, path))
        members.extend(_contained_members(nested, path))
    return members


def _placements(
    group: _LayoutGroup,
    roles: DirectRoles,
    by_contributor: Mapping[ColumnContributor, ColumnSlot],
) -> dict[MemberIdentity, MemberPlacement]:
    """Where every member applicable to ``group``'s Table lives.

    Under ``Columns`` a top-level Attribute and a top-level Value Object
    occurrence are placed over the slot their own contributor owns, and every
    member inside an occurrence is placed over that occurrence's own Structured
    Column. Under ``Document`` a direct-role Attribute keeps its Column and every
    other applicable member is placed over the Table's one shared Structured
    Column, whose document root the paths are relative to.
    """
    document_slot = (
        None if group.document is None else by_contributor[RelationalDocument(group.root)]
    )
    placements: dict[MemberIdentity, MemberPlacement] = {}
    for attribute in group.attributes:
        if document_slot is None or roles.covers(attribute):
            placements[attribute.identity] = DirectColumn(by_contributor[attribute.identity])
            continue
        placements[attribute.identity] = DocumentPath(document_slot, (attribute.identity.name,))
    for value_object in group.value_objects:
        name = value_object.identity.path[0]
        if document_slot is None:
            occurrence_slot = by_contributor[value_object.identity]
            placements[value_object.identity] = DirectColumn(occurrence_slot)
            prefix: tuple[str, ...] = ()
        else:
            occurrence_slot = document_slot
            prefix = (name,)
            placements[value_object.identity] = DocumentPath(occurrence_slot, (name,))
        for member, path in _contained_members(value_object, prefix):
            placements[member] = DocumentPath(occurrence_slot, path)
    return placements


def _layout(
    index: _CompilationIndex,
    group: _LayoutGroup,
    roles: DirectRoles,
    audit_designations: frozenset[AttributeIdentity],
    applicability_intern: dict[frozenset[EntityIdentity], frozenset[EntityIdentity]],
) -> TableLayout:
    root = index.entities_by_identity[group.root]
    attribute_applicability, value_object_applicability = _applicability(index, group.row_owners)
    row_owners = _interned(set(group.row_owners), applicability_intern)
    key_contributors: list[AttributeIdentity] = [
        attribute.identity
        for attribute in group.attributes
        if isinstance(attribute.primary_key, PrimaryKey)
    ]
    for contributor in _temporal_start_designations(root):
        if contributor not in key_contributors:
            key_contributors.append(contributor)
    key_set: frozenset[ColumnContributor] = frozenset(key_contributors)

    drafts: list[_SlotDraft] = []
    for attribute in group.attributes:
        if group.document is not None and not roles.covers(attribute):
            continue
        applicable = _interned(
            attribute_applicability.get(attribute.identity, set()), applicability_intern
        )
        tier = classify_attribute_tier(attribute, roles.temporal, audit_designations)
        drafts.append(
            _SlotDraft(
                column=attribute.storage,
                tier=tier,
                contributor=attribute.identity,
                declaring_owner=attribute.identity.entity,
                declared_nullable=attribute.nullable,
                applicable_entities=applicable,
            )
        )
    if group.tag_column is not None:
        drafts.append(
            _SlotDraft(
                column=group.tag_column,
                tier=ColumnTier.DISCRIMINATOR,
                contributor=InheritanceDiscriminator(group.root),
                declaring_owner=group.root,
                declared_nullable=False,
                applicable_entities=row_owners,
            )
        )
    if group.document is None:
        for value_object in group.value_objects:
            applicable = _interned(
                value_object_applicability.get(value_object.identity, set()), applicability_intern
            )
            drafts.append(
                _SlotDraft(
                    column=value_object.storage,
                    tier=ColumnTier.DOCUMENT,
                    contributor=value_object.identity,
                    declaring_owner=value_object.identity.entity,
                    declared_nullable=value_object.nullable,
                    applicable_entities=applicable,
                )
            )
    else:
        drafts.append(
            _SlotDraft(
                column=group.document.column,
                tier=ColumnTier.DOCUMENT,
                contributor=RelationalDocument(group.root),
                declaring_owner=group.root,
                declared_nullable=False,
                applicable_entities=row_owners,
            )
        )

    ordered = tuple(draft for tier in ColumnTier for draft in drafts if draft.tier is tier)
    columns = tuple(
        ColumnSlot(
            column=draft.column,
            tier=draft.tier,
            contributor=draft.contributor,
            declaring_owner=draft.declaring_owner,
            effective_nullable=_effective_nullable(draft, key_set, row_owners),
            applicable_entities=draft.applicable_entities,
        )
        for draft in ordered
    )
    column_names = [slot.column for slot in columns]
    contributors = [slot.contributor for slot in columns]
    if len(set(column_names)) != len(column_names) or len(set(contributors)) != len(contributors):
        raise RuntimeError(
            f"Table {group.table.name!r} retains a duplicate Column or contributor after validation"
        )
    by_contributor = {slot.contributor: slot for slot in columns}
    physical_key: list[ColumnSlot] = []
    for contributor in key_contributors:
        slot = by_contributor.get(contributor)
        if slot is None:  # pragma: no cover - resolution rejects an axis naming no Attribute
            raise RuntimeError(
                f"Table {group.table.name!r} has no slot for physical-key contributor {contributor}"
            )
        if slot not in physical_key:
            physical_key.append(slot)
    return table_layout(
        group.table, columns, physical_key, _placements(group, roles, by_contributor)
    )


def _family_facts(
    index: _CompilationIndex,
    roles_of_root: Mapping[EntityIdentity, DirectRoles],
    audit_designations: frozenset[AttributeIdentity],
    applicability_intern: dict[frozenset[EntityIdentity], frozenset[EntityIdentity]],
) -> tuple[StorageLayoutFamilyFacts, ...]:
    families: list[StorageLayoutFamilyFacts] = []
    for root in index.roots:
        entity = index.entities_by_identity[root]
        root_view = index.views_by_identity[root]
        attributes, value_objects = _family_members(index, root)
        roles = roles_of_root[root]
        document = _document_layout(index, root)
        attribute_applicability, value_object_applicability = _applicability(
            index, root_view.concrete_subtypes
        )
        drafts: list[PositionColumnFacts] = []
        members: list[PositionMemberFacts] = []
        for attribute in attributes:
            applicable = _interned(
                attribute_applicability.get(attribute.identity, set()),
                applicability_intern,
            )
            members.append(PositionMemberFacts(attribute.identity, applicable))
            if document is not None and not roles.covers(attribute):
                continue
            drafts.append(
                PositionColumnFacts(
                    PositionColumn(
                        contributor=attribute.identity,
                        tier=classify_attribute_tier(attribute, roles.temporal, audit_designations),
                        declaring_owner=attribute.identity.entity,
                    ),
                    applicable,
                )
            )
        for value_object in value_objects:
            applicable = _interned(
                value_object_applicability.get(value_object.identity, set()),
                applicability_intern,
            )
            members.append(PositionMemberFacts(value_object.identity, applicable))
            if document is not None:
                continue
            drafts.append(
                PositionColumnFacts(
                    PositionColumn(
                        contributor=value_object.identity,
                        tier=ColumnTier.DOCUMENT,
                        declaring_owner=value_object.identity.entity,
                    ),
                    applicable,
                )
            )
        ordered = tuple(
            facts for tier in ColumnTier for facts in drafts if facts.column.tier is tier
        )
        families.append(
            StorageLayoutFamilyFacts(
                root=entity.identity,
                concrete_entities=tuple(root_view.concrete_subtypes),
                columns=ordered,
                members=tuple(members),
            )
        )
    return tuple(families)


def compile_facet(
    metadata: CompiledMetadata,
    inheritance: InheritanceFacet,
    relationship: RelationshipFacet,
    *,
    audit_designations: frozenset[AttributeIdentity] = frozenset(),
) -> StorageLayoutFacet:
    """Compile one compact canonical layout graph for ``metadata``.

    ``audit_designations`` is an internal tier-classification input only: it
    creates no declaration and decides no residency, so it cannot compile a
    member into a place the Rule Set validated it out of. The built-in formation
    profile supplies the empty set.
    """
    applicability_intern: dict[frozenset[EntityIdentity], frozenset[EntityIdentity]] = {}
    index = _compilation_index(metadata, inheritance, relationship)
    roles_of_root = {
        root: DirectRoles(
            joined=index.joined,
            temporal=_temporal_designations(index.entities_by_identity[root]),
        )
        for root in index.roots
    }
    groups = _groups(index)
    layouts = tuple(
        _layout(
            index,
            group,
            roles_of_root[group.root],
            audit_designations,
            applicability_intern,
        )
        for group in groups
    )
    by_table = {layout.table: layout for layout in layouts}
    entity_facts: list[StorageLayoutEntityFacts] = []
    ordinal_selection_intern: dict[int, SlotOrdinalSelection] = {}
    for group in groups:
        layout = by_table[group.table]
        discriminator_slot = layout.contribution(InheritanceDiscriminator(group.root))
        for concrete in group.row_owners:
            inherited = index.views_by_identity[concrete]
            discriminator = None
            if discriminator_slot is not None:
                if inherited.tag_value is None:
                    raise RuntimeError(
                        f"TPH concrete {concrete.canonical!r} has no tag value after validation"
                    )
                discriminator = DiscriminatorAssignment(discriminator_slot, inherited.tag_value)
            entity_facts.append(
                StorageLayoutEntityFacts(
                    entity=concrete,
                    root=group.root,
                    layout=layout,
                    discriminator=discriminator,
                    column_ordinals=_interned_ordinal_selection(
                        layout,
                        concrete,
                        ordinal_selection_intern,
                    ),
                )
            )
    return storage_layout_facet(
        layouts,
        entity_facts,
        _family_facts(
            index,
            roles_of_root,
            audit_designations,
            applicability_intern,
        ),
    )


class StorageLayoutModelCompiler:
    """The Storage Layout Model Compiler requiring Inheritance and Relationship."""

    __slots__ = ()

    @property
    def owner(self) -> ModuleIdentity:
        """The catalog identity owning this compiler."""
        return STORAGE_LAYOUT_MODULE

    @property
    def facet_key(self) -> FacetKey[StorageLayoutFacet]:
        """The key under which the compiled facet is installed."""
        return FACET_KEY

    @property
    def requires(self) -> frozenset[FacetKey[Any]]:
        """The exact prerequisite facet set."""
        return frozenset({INHERITANCE_FACET_KEY, RELATIONSHIP_FACET_KEY})

    def compile(
        self,
        metadata: CompiledMetadata,
        required_facets: Mapping[FacetKey[Any], object],
    ) -> StorageLayoutFacet:
        """Compile accepted Metadata and the required Inheritance and Relationship Facets."""
        inheritance = cast(InheritanceFacet, required_facets[INHERITANCE_FACET_KEY])
        relationship = cast(RelationshipFacet, required_facets[RELATIONSHIP_FACET_KEY])
        return compile_facet(metadata, inheritance, relationship)


MODEL_COMPILER: Final[StorageLayoutModelCompiler] = StorageLayoutModelCompiler()
"""The stateless compiler instance supplied by the built-in profile."""
