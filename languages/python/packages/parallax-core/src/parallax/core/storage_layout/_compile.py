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
    EntityIdentity,
    EntityMetadata,
    FacetKey,
    PrimaryKey,
    Table,
    TablePerHierarchy,
    ValueObjectIdentity,
    ValueObjectMetadata,
)
from parallax.core.model_formation import ModuleIdentity
from parallax.core.storage_layout._facet import (
    FACET_KEY,
    ColumnContributor,
    ColumnSlot,
    ColumnTier,
    DiscriminatorAssignment,
    InheritanceDiscriminator,
    PositionColumn,
    PositionColumnFacts,
    SlotOrdinalSelection,
    StorageLayoutEntityFacts,
    StorageLayoutFacet,
    StorageLayoutFamilyFacts,
    TableLayout,
    storage_layout_facet,
    table_layout,
)
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


def _compilation_index(
    metadata: CompiledMetadata, inheritance: InheritanceFacet
) -> _CompilationIndex:
    """Index accepted Entities and family facts in one metadata visit."""
    entities = tuple(metadata.entities)
    entities_by_identity = {entity.identity: entity for entity in entities}
    views_by_identity: dict[EntityIdentity, InheritanceEntityView] = {}
    ancestries_by_identity: dict[EntityIdentity, tuple[EntityIdentity, ...]] = {}
    family_members: dict[EntityIdentity, list[EntityMetadata]] = {}
    roots: list[EntityIdentity] = []
    for entity in entities:
        view = _entity_view(inheritance, entity.identity)
        views_by_identity[entity.identity] = view
        ancestries_by_identity[entity.identity] = tuple(view.ancestry)
        family_members.setdefault(view.root, []).append(entity)
        if view.root == entity.identity:
            roots.append(entity.identity)
    return _CompilationIndex(
        entities=entities,
        entities_by_identity=entities_by_identity,
        views_by_identity=views_by_identity,
        ancestries_by_identity=ancestries_by_identity,
        family_members_by_root={root: tuple(members) for root, members in family_members.items()},
        roots=tuple(roots),
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


def _layout(
    index: _CompilationIndex,
    group: _LayoutGroup,
    audit_designations: frozenset[AttributeIdentity],
    applicability_intern: dict[frozenset[EntityIdentity], frozenset[EntityIdentity]],
) -> TableLayout:
    root = index.entities_by_identity[group.root]
    temporal = _temporal_designations(root)
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
    key_set = frozenset(key_contributors)

    drafts: list[_SlotDraft] = []
    for attribute in group.attributes:
        applicable = _interned(
            attribute_applicability.get(attribute.identity, set()), applicability_intern
        )
        tier = classify_attribute_tier(attribute, temporal, audit_designations)
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

    ordered = tuple(draft for tier in ColumnTier for draft in drafts if draft.tier is tier)
    columns = tuple(
        ColumnSlot(
            column=draft.column,
            tier=draft.tier,
            contributor=draft.contributor,
            declaring_owner=draft.declaring_owner,
            effective_nullable=(
                False
                if draft.contributor in key_set or draft.tier is ColumnTier.DISCRIMINATOR
                else True
                if draft.applicable_entities != row_owners
                else draft.declared_nullable
            ),
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
    return table_layout(group.table, columns, physical_key)


def _family_facts(
    index: _CompilationIndex,
    audit_designations: frozenset[AttributeIdentity],
    applicability_intern: dict[frozenset[EntityIdentity], frozenset[EntityIdentity]],
) -> tuple[StorageLayoutFamilyFacts, ...]:
    families: list[StorageLayoutFamilyFacts] = []
    for root in index.roots:
        entity = index.entities_by_identity[root]
        root_view = index.views_by_identity[root]
        attributes, value_objects = _family_members(index, root)
        temporal = _temporal_designations(entity)
        attribute_applicability, value_object_applicability = _applicability(
            index, root_view.concrete_subtypes
        )
        drafts: list[PositionColumnFacts] = []
        for attribute in attributes:
            drafts.append(
                PositionColumnFacts(
                    PositionColumn(
                        contributor=attribute.identity,
                        tier=classify_attribute_tier(attribute, temporal, audit_designations),
                        declaring_owner=attribute.identity.entity,
                    ),
                    _interned(
                        attribute_applicability.get(attribute.identity, set()),
                        applicability_intern,
                    ),
                )
            )
        for value_object in value_objects:
            drafts.append(
                PositionColumnFacts(
                    PositionColumn(
                        contributor=value_object.identity,
                        tier=ColumnTier.DOCUMENT,
                        declaring_owner=value_object.identity.entity,
                    ),
                    _interned(
                        value_object_applicability.get(value_object.identity, set()),
                        applicability_intern,
                    ),
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
            )
        )
    return tuple(families)


def compile_facet(
    metadata: CompiledMetadata,
    inheritance: InheritanceFacet,
    *,
    audit_designations: frozenset[AttributeIdentity] = frozenset(),
) -> StorageLayoutFacet:
    """Compile one compact canonical layout graph for ``metadata``.

    ``audit_designations`` is an internal classifier input only. The built-in
    formation profile supplies the empty set.
    """
    applicability_intern: dict[frozenset[EntityIdentity], frozenset[EntityIdentity]] = {}
    index = _compilation_index(metadata, inheritance)
    groups = _groups(index)
    layouts = tuple(
        _layout(
            index,
            group,
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
            audit_designations,
            applicability_intern,
        ),
    )


class StorageLayoutModelCompiler:
    """The Storage Layout Model Compiler requiring the Inheritance Facet."""

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
        return frozenset({INHERITANCE_FACET_KEY})

    def compile(
        self,
        metadata: CompiledMetadata,
        required_facets: Mapping[FacetKey[Any], object],
    ) -> StorageLayoutFacet:
        """Compile accepted Metadata and the required Inheritance Facet."""
        inheritance = cast(InheritanceFacet, required_facets[INHERITANCE_FACET_KEY])
        return compile_facet(metadata, inheritance)


MODEL_COMPILER: Final[StorageLayoutModelCompiler] = StorageLayoutModelCompiler()
"""The stateless compiler instance supplied by the built-in profile."""
