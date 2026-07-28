"""Independent canonical physical Table Layout compiler (m-storage-layout).

The reference harness derives these immutable values directly from frozen core
descriptor declarations and inheritance family facts. It does not import a
language implementation. The graph supplies deterministic physical claim
validation and structural layout baselines.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, TypeAlias

from .inheritance import (
    ROLE_ROOT,
    STRATEGY_TPCS,
    STRATEGY_TPH,
    Family,
    effective_column,
    inheritance_of,
    role_of,
)
from .naming import default_column_name
from .value_object_resolve import RejectionError

STORAGE_LAYOUT_TABLE_MAPPING_COLLISION = "storage-layout-table-mapping-collision"
STORAGE_LAYOUT_COLUMN_COLLISION = "storage-layout-column-collision"

MODEL_REJECTED_RULES: frozenset[str] = frozenset(
    {
        STORAGE_LAYOUT_TABLE_MAPPING_COLLISION,
        STORAGE_LAYOUT_COLUMN_COLLISION,
    }
)


class ColumnTier(enum.Enum):
    """The closed canonical Table-wide semantic tier order."""

    IDENTITY = "identity"
    DISCRIMINATOR = "discriminator"
    DOMAIN = "domain"
    TEMPORAL = "temporal"
    AUDIT = "audit"
    DOCUMENT = "document"


@dataclass(frozen=True, slots=True)
class AttributeContributor:
    """The canonical identity of one declared scalar Attribute."""

    owner: str
    name: str


@dataclass(frozen=True, slots=True)
class ValueObjectContributor:
    """The canonical identity of one top-level Value Object occurrence."""

    owner: str
    name: str


@dataclass(frozen=True, slots=True)
class InheritanceDiscriminator:
    """The framework-owned discriminator contributed by one TPH root."""

    root: str


ColumnContributor: TypeAlias = (
    AttributeContributor | ValueObjectContributor | InheritanceDiscriminator
)
"""The closed identity-bearing Attribute, Value Object, or discriminator algebra."""


@dataclass(frozen=True, slots=True)
class ColumnSlot:
    """One immutable physical Column occurrence in one Table Layout."""

    column: str
    tier: ColumnTier
    contributor: ColumnContributor
    declaring_owner: str
    effective_nullable: bool
    applicable_entities: frozenset[str]


@dataclass(frozen=True, slots=True)
class TableLayout:
    """The complete physical shape and immutable indexes of one Table."""

    table: str
    columns: tuple[ColumnSlot, ...]
    physical_primary_key: tuple[ColumnSlot, ...]
    _column_index: Mapping[str, ColumnSlot] = field(init=False, repr=False, compare=False)
    _contributor_index: Mapping[ColumnContributor, ColumnSlot] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_column_index",
            MappingProxyType({slot.column: slot for slot in self.columns}),
        )
        object.__setattr__(
            self,
            "_contributor_index",
            MappingProxyType({slot.contributor: slot for slot in self.columns}),
        )

    def __deepcopy__(self, memo: dict[int, Any]) -> TableLayout:
        return self

    def column(self, column: str) -> ColumnSlot | None:
        """Return the slot claiming ``column``, or absent."""
        return self._column_index.get(column)

    def contribution(self, contributor: ColumnContributor) -> ColumnSlot | None:
        """Return this Table's occurrence of ``contributor``, or absent."""
        return self._contributor_index.get(contributor)


@dataclass(frozen=True, slots=True)
class DiscriminatorAssignment:
    """One concrete Entity's derived discriminator slot and value."""

    slot: ColumnSlot
    value: str


@dataclass(frozen=True, slots=True)
class _OrdinalSelection:
    """A compact bit selection over one Table Layout's slot ordinals."""

    bits: int

    def materialize(self, columns: Sequence[ColumnSlot]) -> tuple[ColumnSlot, ...]:
        return tuple(slot for ordinal, slot in enumerate(columns) if self.bits & (1 << ordinal))


@dataclass(frozen=True, slots=True)
class EntityLayoutView:
    """One row-owning Entity's table-ordered slot selection."""

    entity: str
    layout: TableLayout
    discriminator: DiscriminatorAssignment | None
    _column_ordinals: _OrdinalSelection = field(repr=False)

    @property
    def columns(self) -> tuple[ColumnSlot, ...]:
        """Materialize the applicable slots in canonical Table order."""
        return self._column_ordinals.materialize(self.layout.columns)


@dataclass(frozen=True, slots=True)
class PositionColumn:
    """One logical declaration contributor of a polymorphic position."""

    contributor: AttributeContributor | ValueObjectContributor
    tier: ColumnTier
    declaring_owner: str


@dataclass(frozen=True, slots=True)
class PositionBranch:
    """One physical branch aligned with a position's logical columns."""

    layout: TableLayout
    concrete_entities: tuple[str, ...]
    slots: tuple[ColumnSlot | None, ...]
    discriminator_slot: ColumnSlot | None


@dataclass(frozen=True, slots=True)
class PositionLayoutView:
    """A canonical concrete set's logical columns and physical branches."""

    concrete_entities: tuple[str, ...]
    columns: tuple[PositionColumn, ...]
    branches: tuple[PositionBranch, ...]


@dataclass(frozen=True, slots=True)
class _Group:
    table: str
    mapping_owner: str
    root: str
    row_owners: tuple[str, ...]
    declarations: tuple[dict[str, Any], ...]
    tag_column: str | None


@dataclass(frozen=True, slots=True)
class _ModelIndex:
    definitions: tuple[dict[str, Any], ...]
    family: Family
    standalone: tuple[dict[str, Any], ...]
    roots: tuple[str, ...]
    family_members: Mapping[str, tuple[dict[str, Any], ...]]


@dataclass(frozen=True, slots=True)
class _Draft:
    column: str
    tier: ColumnTier
    contributor: ColumnContributor
    declaring_owner: str
    declared_nullable: bool
    applicable_entities: frozenset[str]


@dataclass(frozen=True, slots=True)
class _PositionFacts:
    column: PositionColumn
    applicable_entities: frozenset[str]


@dataclass(frozen=True, slots=True)
class _FamilyFacts:
    root: str
    concrete_entities: tuple[str, ...]
    columns: tuple[_PositionFacts, ...]


def _identity(definition: Mapping[str, Any]) -> str:
    namespace = definition.get("namespace")
    name = definition["name"]
    return name if namespace is None else f"{namespace}.{name}"


def _identity_sort_key(identity: str) -> tuple[str, str]:
    namespace, separator, name = identity.rpartition(".")
    return (namespace if separator else "", name if separator else identity)


def _canonical(family: Family, identity: str) -> str:
    return family.defs.canonical_key(identity)


def _family_members(index: _ModelIndex, root: str) -> tuple[dict[str, Any], ...]:
    return index.family_members.get(root, ())


def _model_index(entity_defs: Sequence[dict[str, Any]]) -> _ModelIndex:
    """Index definitions, parents, and family membership once."""
    definitions = tuple(entity_defs)
    family = Family(list(definitions))
    standalone: list[dict[str, Any]] = []
    roots: list[str] = []
    family_members: dict[str, list[dict[str, Any]]] = {}
    for definition in definitions:
        block = inheritance_of(definition)
        if block is None:
            standalone.append(definition)
            continue
        identity = family.key_of(definition)
        root = family.root_of(identity)
        if root is None:
            continue
        family_members.setdefault(root, []).append(definition)
        if role_of(definition) == ROLE_ROOT:
            roots.append(identity)
    return _ModelIndex(
        definitions=definitions,
        family=family,
        standalone=tuple(standalone),
        roots=tuple(sorted(roots, key=_identity_sort_key)),
        family_members={root: tuple(members) for root, members in family_members.items()},
    )


def _family_declarations(
    family: Family,
    members: Sequence[dict[str, Any]],
    root: str,
    row_owners: Sequence[str],
) -> tuple[dict[str, Any], ...]:
    """The root-first, canonical-concrete declaration stream of one family."""
    encountered = set(row_owners)
    contributor_identities: list[str] = []
    for concrete in row_owners:
        for ancestor in family.ancestry(concrete)[:-1]:
            if ancestor in encountered:
                continue
            encountered.add(ancestor)
            contributor_identities.append(ancestor)
    contributor_identities.extend(row_owners)
    remaining = sorted(
        (_identity(member) for member in members),
        key=lambda identity: (identity != root, _identity_sort_key(identity)),
    )
    for identity in remaining:
        if identity in encountered:
            continue
        encountered.add(identity)
        contributor_identities.append(identity)
    return tuple(family.defs[identity] for identity in contributor_identities)


def _project_groups(index: _ModelIndex) -> tuple[_Group, ...]:
    """Project independent standalone, TPH-family, and TPCS-concrete owners."""
    family = index.family
    groups: list[_Group] = []
    for definition in index.standalone:
        if "table" not in definition:
            continue
        identity = _identity(definition)
        groups.append(
            _Group(
                table=definition["table"],
                mapping_owner=identity,
                root=identity,
                row_owners=(identity,),
                declarations=(definition,),
                tag_column=None,
            )
        )

    for root in index.roots:
        root_definition = family.defs[root]
        block = inheritance_of(root_definition)
        strategy = block.get("strategy") if block is not None else None
        members = _family_members(index, root)
        concretes = tuple(
            _canonical(family, identity) for identity in family.concrete_descendants(root)
        )
        if strategy == STRATEGY_TPH:
            tag = block.get("tag") if block is not None else None
            tag_column = tag.get("column") if isinstance(tag, dict) else None
            if "table" not in root_definition or tag_column is None:
                continue
            groups.append(
                _Group(
                    table=root_definition["table"],
                    mapping_owner=root,
                    root=root,
                    row_owners=concretes,
                    declarations=_family_declarations(family, members, root, concretes),
                    tag_column=tag_column,
                )
            )
        elif strategy == STRATEGY_TPCS:
            for concrete in concretes:
                definition = family.defs[concrete]
                if "table" not in definition:
                    continue
                groups.append(
                    _Group(
                        table=definition["table"],
                        mapping_owner=concrete,
                        root=root,
                        row_owners=(concrete,),
                        declarations=tuple(
                            family.defs[identity] for identity in family.ancestry(concrete)
                        ),
                        tag_column=None,
                    )
                )
    return tuple(sorted(groups, key=lambda group: _identity_sort_key(group.mapping_owner)))


def _attribute_contributor(
    definition: Mapping[str, Any], attribute: Mapping[str, Any]
) -> AttributeContributor:
    return AttributeContributor(_identity(definition), attribute["name"])


def _value_object_contributor(
    definition: Mapping[str, Any], value_object: Mapping[str, Any]
) -> ValueObjectContributor:
    return ValueObjectContributor(_identity(definition), value_object["name"])


def _diagnostic_claims(group: _Group) -> tuple[tuple[str, ColumnContributor], ...]:
    keys = tuple(
        (effective_column(attribute), _attribute_contributor(definition, attribute))
        for definition in group.declarations
        for attribute in definition.get("attributes", []) or []
        if isinstance(attribute, dict) and bool(attribute.get("primaryKey"))
    )
    discriminator: tuple[tuple[str, ColumnContributor], ...] = (
        ()
        if group.tag_column is None
        else ((group.tag_column, InheritanceDiscriminator(group.root)),)
    )
    attributes = tuple(
        (effective_column(attribute), _attribute_contributor(definition, attribute))
        for definition in group.declarations
        for attribute in definition.get("attributes", []) or []
        if isinstance(attribute, dict) and not bool(attribute.get("primaryKey"))
    )
    documents = tuple(
        (
            value_object.get("column", default_column_name(value_object["name"])),
            _value_object_contributor(definition, value_object),
        )
        for definition in group.declarations
        for value_object in definition.get("valueObjects", []) or []
        if isinstance(value_object, dict)
    )
    return (*keys, *discriminator, *attributes, *documents)


def _render_contributor(contributor: ColumnContributor) -> str:
    if isinstance(contributor, AttributeContributor):
        return f"Attribute {contributor.owner}.{contributor.name}"
    if isinstance(contributor, ValueObjectContributor):
        return f"Value Object {contributor.owner}.{contributor.name}"
    return f"table-per-hierarchy discriminator of {contributor.root}"


def _validate_groups(groups: Sequence[_Group]) -> None:
    first_owners: dict[str, _Group] = {}
    multiply_owned: set[str] = set()
    mapping_collision: tuple[_Group, _Group] | None = None
    for group in groups:
        first = first_owners.get(group.table)
        if first is None:
            first_owners[group.table] = group
            continue
        multiply_owned.add(group.table)
        if mapping_collision is None:
            mapping_collision = (first, group)
    if mapping_collision is not None:
        first, later = mapping_collision
        raise RejectionError(
            STORAGE_LAYOUT_TABLE_MAPPING_COLLISION,
            f"Table {later.table!r} is mapped by independent owners "
            f"{first.mapping_owner!r} and {later.mapping_owner!r}; "
            f"{first.mapping_owner!r} is the canonical first owner",
        )
    for group in groups:
        if group.table in multiply_owned:
            continue
        claimed: dict[str, ColumnContributor] = {}
        for column, contributor in _diagnostic_claims(group):
            existing = claimed.get(column)
            if existing is not None and existing != contributor:
                raise RejectionError(
                    STORAGE_LAYOUT_COLUMN_COLLISION,
                    f"physical Column {column!r} in Table {group.table!r} is claimed by "
                    f"both {_render_contributor(existing)} and "
                    f"{_render_contributor(contributor)}",
                )
            claimed[column] = contributor


def validate_storage_layout(entity_defs: Sequence[dict[str, Any]]) -> None:
    """Reject mapping ownership before any uniquely owned Table's Columns."""
    _validate_groups(_project_groups(_model_index(entity_defs)))


def _temporal_designations(
    root: Mapping[str, Any], root_identity: str
) -> frozenset[AttributeContributor]:
    return frozenset(
        AttributeContributor(root_identity, attribute)
        for axis in root.get("asOfAxes", []) or []
        if isinstance(axis, dict)
        for attribute in (axis["startAttribute"], axis["endAttribute"])
    )


_TEMPORAL_DIMENSION_RANK: Mapping[str, int] = MappingProxyType(
    {"validTime": 0, "transactionTime": 1}
)


def _temporal_start_designations(
    root: Mapping[str, Any], root_identity: str
) -> tuple[AttributeContributor, ...]:
    """Temporal starts in canonical dimension rank with duplicates removed."""
    starts: list[AttributeContributor] = []
    seen: set[AttributeContributor] = set()
    axes = (axis for axis in root.get("asOfAxes", []) or [] if isinstance(axis, dict))
    for axis in sorted(axes, key=lambda axis: _TEMPORAL_DIMENSION_RANK[axis["dimension"]]):
        contributor = AttributeContributor(root_identity, axis["startAttribute"])
        if contributor in seen:
            continue
        seen.add(contributor)
        starts.append(contributor)
    return tuple(starts)


def classify_attribute_tier(
    contributor: AttributeContributor,
    attribute: Mapping[str, Any],
    temporal_designations: frozenset[AttributeContributor],
    audit_designations: frozenset[AttributeContributor] = frozenset(),
) -> ColumnTier:
    """Classify one Attribute with identity, temporal, then audit precedence."""
    if bool(attribute.get("primaryKey")):
        return ColumnTier.IDENTITY
    if contributor in temporal_designations:
        return ColumnTier.TEMPORAL
    if contributor in audit_designations:
        return ColumnTier.AUDIT
    return ColumnTier.DOMAIN


def _applicability(
    family: Family, row_owners: Sequence[str]
) -> tuple[dict[AttributeContributor, set[str]], dict[ValueObjectContributor, set[str]]]:
    attributes: dict[AttributeContributor, set[str]] = {}
    value_objects: dict[ValueObjectContributor, set[str]] = {}
    for concrete in row_owners:
        for identity in family.ancestry(concrete):
            definition = family.defs[identity]
            for attribute in definition.get("attributes", []) or []:
                if isinstance(attribute, dict):
                    attributes.setdefault(_attribute_contributor(definition, attribute), set()).add(
                        concrete
                    )
            for value_object in definition.get("valueObjects", []) or []:
                if isinstance(value_object, dict):
                    value_objects.setdefault(
                        _value_object_contributor(definition, value_object), set()
                    ).add(concrete)
    return attributes, value_objects


def _interned(values: set[str], intern: dict[frozenset[str], frozenset[str]]) -> frozenset[str]:
    frozen = frozenset(values)
    return intern.setdefault(frozen, frozen)


def _interned_ordinal_selection(
    layout: TableLayout,
    entity: str,
    intern: dict[int, _OrdinalSelection],
) -> _OrdinalSelection:
    bits = sum(
        1 << ordinal
        for ordinal, slot in enumerate(layout.columns)
        if entity in slot.applicable_entities
    )
    return intern.setdefault(bits, _OrdinalSelection(bits))


def _compile_layout(
    family: Family,
    group: _Group,
    audit_designations: frozenset[AttributeContributor],
    applicability_intern: dict[frozenset[str], frozenset[str]],
) -> TableLayout:
    root = family.defs[group.root]
    temporal = _temporal_designations(root, group.root)
    attribute_applicability, value_object_applicability = _applicability(family, group.row_owners)
    row_owners = _interned(set(group.row_owners), applicability_intern)
    key_contributors = [
        _attribute_contributor(definition, attribute)
        for definition in group.declarations
        for attribute in definition.get("attributes", []) or []
        if isinstance(attribute, dict) and bool(attribute.get("primaryKey"))
    ]
    for contributor in _temporal_start_designations(root, group.root):
        if contributor not in key_contributors:
            key_contributors.append(contributor)
    key_set = frozenset(key_contributors)

    drafts: list[_Draft] = []
    for definition in group.declarations:
        for attribute in definition.get("attributes", []) or []:
            if not isinstance(attribute, dict):
                continue
            contributor = _attribute_contributor(definition, attribute)
            drafts.append(
                _Draft(
                    column=effective_column(attribute),
                    tier=classify_attribute_tier(
                        contributor, attribute, temporal, audit_designations
                    ),
                    contributor=contributor,
                    declaring_owner=contributor.owner,
                    declared_nullable=bool(attribute.get("nullable", False)),
                    applicable_entities=_interned(
                        attribute_applicability.get(contributor, set()),
                        applicability_intern,
                    ),
                )
            )
    if group.tag_column is not None:
        drafts.append(
            _Draft(
                column=group.tag_column,
                tier=ColumnTier.DISCRIMINATOR,
                contributor=InheritanceDiscriminator(group.root),
                declaring_owner=group.root,
                declared_nullable=False,
                applicable_entities=row_owners,
            )
        )
    for definition in group.declarations:
        for value_object in definition.get("valueObjects", []) or []:
            if not isinstance(value_object, dict):
                continue
            contributor = _value_object_contributor(definition, value_object)
            drafts.append(
                _Draft(
                    column=value_object.get("column", default_column_name(value_object["name"])),
                    tier=ColumnTier.DOCUMENT,
                    contributor=contributor,
                    declaring_owner=contributor.owner,
                    declared_nullable=bool(value_object.get("nullable", False)),
                    applicable_entities=_interned(
                        value_object_applicability.get(contributor, set()),
                        applicability_intern,
                    ),
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
    by_contributor = {slot.contributor: slot for slot in columns}
    physical_key: list[ColumnSlot] = []
    for contributor in key_contributors:
        slot = by_contributor[contributor]
        if slot not in physical_key:
            physical_key.append(slot)
    return TableLayout(group.table, columns, tuple(physical_key))


@dataclass(frozen=True, slots=True)
class StorageLayout:
    """The model's bounded immutable Table, Entity, and position layout graph.

    A caller that deep-copies a parsed corpus case to mutate it safely shares
    this graph instead: the values are immutable, and the read-only indexes
    behind the lookups are not copyable.
    """

    tables: tuple[TableLayout, ...]
    _tables: Mapping[str, TableLayout] = field(repr=False, compare=False)
    _entities: Mapping[str, EntityLayoutView] = field(repr=False, compare=False)
    _families: Mapping[str, _FamilyFacts] = field(repr=False, compare=False)

    def __deepcopy__(self, memo: dict[int, Any]) -> StorageLayout:
        return self

    def table(self, table: str) -> TableLayout | None:
        """Return one structural Table's layout, or absent."""
        return self._tables.get(table)

    def entity(self, entity: str) -> EntityLayoutView | None:
        """Return one concrete row owner's layout selection, or absent."""
        return self._entities.get(entity)

    def position(self, concrete_entities: Sequence[str]) -> PositionLayoutView | None:
        """Build an operation-scoped view for one canonical effective concrete set."""
        selected = tuple(concrete_entities)
        if not selected:
            return PositionLayoutView((), (), ())
        if selected != tuple(sorted(set(selected), key=_identity_sort_key)):
            return None
        entity_views: list[EntityLayoutView] = []
        for entity in selected:
            view = self._entities.get(entity)
            if view is None:
                return None
            entity_views.append(view)
        roots = {
            root
            for root, facts in self._families.items()
            if set(selected) <= set(facts.concrete_entities)
        }
        if len(roots) != 1:
            return None
        family = self._families[next(iter(roots))]
        selected_set = frozenset(selected)
        column_facts = tuple(
            facts for facts in family.columns if facts.applicable_entities & selected_set
        )
        columns = tuple(facts.column for facts in column_facts)
        branch_entities: dict[str, list[str]] = {}
        for view in entity_views:
            branch_entities.setdefault(view.layout.table, []).append(view.entity)
        branches: list[PositionBranch] = []
        for table, entities in branch_entities.items():
            layout = self._tables[table]
            branch_set = frozenset(entities)
            branches.append(
                PositionBranch(
                    layout=layout,
                    concrete_entities=tuple(entities),
                    slots=tuple(
                        layout.contribution(facts.column.contributor)
                        if facts.applicable_entities & branch_set
                        else None
                        for facts in column_facts
                    ),
                    discriminator_slot=layout.contribution(InheritanceDiscriminator(family.root)),
                )
            )
        return PositionLayoutView(selected, columns, tuple(branches))


def _compile_family_facts(
    index: _ModelIndex,
    audit_designations: frozenset[AttributeContributor],
    applicability_intern: dict[frozenset[str], frozenset[str]],
) -> tuple[_FamilyFacts, ...]:
    family = index.family
    facts: list[_FamilyFacts] = []
    family_inputs: list[tuple[str, tuple[str, ...], tuple[dict[str, Any], ...]]] = [
        (_identity(definition), (_identity(definition),), (definition,))
        for definition in index.standalone
    ]
    for root in index.roots:
        members = _family_members(index, root)
        concretes = tuple(
            _canonical(family, identity) for identity in family.concrete_descendants(root)
        )
        family_inputs.append(
            (
                root,
                concretes,
                _family_declarations(family, members, root, concretes),
            )
        )
    for root, concretes, declarations in sorted(
        family_inputs, key=lambda item: _identity_sort_key(item[0])
    ):
        temporal = _temporal_designations(family.defs[root], root)
        attribute_applicability, value_object_applicability = _applicability(family, concretes)
        drafts: list[_PositionFacts] = []
        for definition in declarations:
            for attribute in definition.get("attributes", []) or []:
                if not isinstance(attribute, dict):
                    continue
                contributor = _attribute_contributor(definition, attribute)
                drafts.append(
                    _PositionFacts(
                        PositionColumn(
                            contributor=contributor,
                            tier=classify_attribute_tier(
                                contributor,
                                attribute,
                                temporal,
                                audit_designations,
                            ),
                            declaring_owner=contributor.owner,
                        ),
                        _interned(
                            attribute_applicability.get(contributor, set()),
                            applicability_intern,
                        ),
                    )
                )
        for definition in declarations:
            for value_object in definition.get("valueObjects", []) or []:
                if not isinstance(value_object, dict):
                    continue
                contributor = _value_object_contributor(definition, value_object)
                drafts.append(
                    _PositionFacts(
                        PositionColumn(
                            contributor=contributor,
                            tier=ColumnTier.DOCUMENT,
                            declaring_owner=contributor.owner,
                        ),
                        _interned(
                            value_object_applicability.get(contributor, set()),
                            applicability_intern,
                        ),
                    )
                )
        ordered = tuple(
            column for tier in ColumnTier for column in drafts if column.column.tier is tier
        )
        facts.append(_FamilyFacts(root, concretes, ordered))
    return tuple(facts)


def compile_storage_layout(
    entity_defs: Sequence[dict[str, Any]],
    *,
    audit_designations: frozenset[AttributeContributor] = frozenset(),
) -> StorageLayout:
    """Compile one eager independent canonical layout graph."""
    index = _model_index(entity_defs)
    family = index.family
    groups = _project_groups(index)
    _validate_groups(groups)
    applicability_intern: dict[frozenset[str], frozenset[str]] = {}
    layouts = tuple(
        _compile_layout(
            family,
            group,
            audit_designations,
            applicability_intern,
        )
        for group in groups
    )
    by_table = {layout.table: layout for layout in layouts}
    entity_views: list[EntityLayoutView] = []
    ordinal_selection_intern: dict[int, _OrdinalSelection] = {}
    for group in groups:
        layout = by_table[group.table]
        discriminator_slot = layout.contribution(InheritanceDiscriminator(group.root))
        for concrete in group.row_owners:
            discriminator = None
            if discriminator_slot is not None:
                block = inheritance_of(family.defs[concrete])
                value = block.get("tagValue") if block is not None else None
                if not isinstance(value, str):
                    raise RuntimeError(
                        f"TPH concrete {concrete!r} has no tagValue after validation"
                    )
                discriminator = DiscriminatorAssignment(discriminator_slot, value)
            entity_views.append(
                EntityLayoutView(
                    entity=concrete,
                    layout=layout,
                    discriminator=discriminator,
                    _column_ordinals=_interned_ordinal_selection(
                        layout,
                        concrete,
                        ordinal_selection_intern,
                    ),
                )
            )
    family_facts = _compile_family_facts(
        index,
        audit_designations,
        applicability_intern,
    )
    return StorageLayout(
        tables=layouts,
        _tables=MappingProxyType({layout.table: layout for layout in layouts}),
        _entities=MappingProxyType({view.entity: view for view in entity_views}),
        _families=MappingProxyType({facts.root: facts for facts in family_facts}),
    )
