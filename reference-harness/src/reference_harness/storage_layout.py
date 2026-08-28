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
from typing import Any

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
from .temporality import temporal_axes
from .value_object_resolve import RejectionError

STORAGE_LAYOUT_TABLE_MAPPING_COLLISION = "storage-layout-table-mapping-collision"
STORAGE_LAYOUT_COLUMN_COLLISION = "storage-layout-column-collision"
STORAGE_LAYOUT_DOCUMENT_MEMBER_COLUMN_OVERRIDE = "storage-layout-document-member-column-override"
STORAGE_LAYOUT_INDEX_OVER_DOCUMENT_MEMBER = "storage-layout-index-over-document-member"
MODEL_REJECTED_RULES: frozenset[str] = frozenset(
    {
        STORAGE_LAYOUT_TABLE_MAPPING_COLLISION,
        STORAGE_LAYOUT_COLUMN_COLLISION,
        STORAGE_LAYOUT_DOCUMENT_MEMBER_COLUMN_OVERRIDE,
        STORAGE_LAYOUT_INDEX_OVER_DOCUMENT_MEMBER,
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


@dataclass(frozen=True, slots=True)
class RelationalDocument:
    """The shared Structured Column of one layout owner's ``Document`` layout."""

    layout_owner: str


type ColumnContributor = (
    AttributeContributor | ValueObjectContributor | InheritanceDiscriminator | RelationalDocument
)
"""The closed identity-bearing Attribute, Value Object, discriminator, or shared
Structured Column algebra."""


@dataclass(frozen=True, slots=True)
class MemberAddress:
    """One logical member of one Entity, addressed by declared member names.

    A one-segment path names a top-level Attribute or a top-level Value Object
    occurrence; a longer path descends into an occurrence. ``owner`` is the
    Entity that declares the outermost member, so an inherited member keeps one
    address across every Table it reaches.
    """

    owner: str
    path: tuple[str, ...]


def member_address(family: Family, entity: str, name: str) -> MemberAddress:
    """The address the top-level member *name* reaches at *entity* is placed under.

    Nearest declaration first, as a position resolves a member: disjoint
    inheritance siblings may reuse one member name (m-inheritance), and where they
    share a Table each declaration holds its own placement, so only the declaring
    owner tells the two apart. A name no declaration in the ancestry carries — a
    synthesized discriminator — addresses the position itself and so matches no
    placement.
    """
    for identity in reversed(family.ancestry(entity)):
        definition = family.defs[identity]
        declared = (
            *(definition.get("attributes") or []),
            *(definition.get("valueObjects") or []),
        )
        if any(isinstance(member, dict) and member.get("name") == name for member in declared):
            return MemberAddress(identity, (name,))
    return MemberAddress(family.defs.canonical_key(entity), (name,))


@dataclass(frozen=True, slots=True)
class DirectColumn:
    """A member stored in a Column of its own."""

    slot: ColumnSlot


@dataclass(frozen=True, slots=True)
class DocumentPath:
    """A member stored inside ``slot``'s document at ``path``.

    ``path`` is relative to the root of the document that slot carries: the
    Table's one shared Structured Column under ``Document``, and the containing
    top-level occurrence's own Structured Column under ``Columns``.
    """

    slot: ColumnSlot
    path: tuple[str, ...]


type MemberPlacement = DirectColumn | DocumentPath
"""Where one logical member of one Table lives."""


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
    placements: Mapping[MemberAddress, MemberPlacement] = field(repr=False, compare=False)
    _column_index: Mapping[str, ColumnSlot] = field(init=False, repr=False, compare=False)
    _contributor_index: Mapping[ColumnContributor, ColumnSlot] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "placements", MappingProxyType(dict(self.placements)))
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

    def placement(self, member: MemberAddress) -> MemberPlacement | None:
        """Return where ``member`` lives in this Table's rows, or absent."""
        return self.placements.get(member)


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

    contributor: ColumnContributor
    tier: ColumnTier
    declaring_owner: str


@dataclass(frozen=True, slots=True)
class PositionBranch:
    """One physical branch aligned with a position's logical columns.

    ``slots`` aligns with the view's ``columns`` and ``placements`` with its
    ``members``; each entry is present when its contributor or member applies to
    at least one selected concrete in this branch.
    """

    layout: TableLayout
    concrete_entities: tuple[str, ...]
    slots: tuple[ColumnSlot | None, ...]
    placements: tuple[MemberPlacement | None, ...]
    discriminator_slot: ColumnSlot | None


@dataclass(frozen=True, slots=True)
class PositionLayoutView:
    """A canonical concrete set's logical columns, members, and physical branches."""

    concrete_entities: tuple[str, ...]
    columns: tuple[PositionColumn, ...]
    members: tuple[MemberAddress, ...]
    branches: tuple[PositionBranch, ...]

    @property
    def column_spellings(self) -> tuple[str, ...]:
        """Each logical column's physical name, positionally aligned with ``columns``.

        A contributor is spelled by the first branch owning a slot for it. Distinct
        contributors may legally reuse one spelling in structurally different
        Tables, so the result can repeat a name; disambiguating that is result
        planning, not layout.
        """
        spellings: list[str] = []
        for index in range(len(self.columns)):
            for branch in self.branches:
                slot = branch.slots[index]
                if slot is not None:
                    spellings.append(slot.column)
                    break
        return tuple(spellings)


@dataclass(frozen=True, slots=True)
class _Group:
    table: str
    mapping_owner: str
    root: str
    row_owners: tuple[str, ...]
    declarations: tuple[dict[str, Any], ...]
    tag_column: str | None
    document_column: str | None


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
class _MemberFacts:
    member: MemberAddress
    applicable_entities: frozenset[str]


@dataclass(frozen=True, slots=True)
class _FamilyFacts:
    root: str
    concrete_entities: tuple[str, ...]
    columns: tuple[_PositionFacts, ...]
    members: tuple[_MemberFacts, ...]


@dataclass(frozen=True, slots=True)
class _DirectRoles:
    """The designations that keep an Attribute a direct Column under ``Document``.

    Model primary keys and an explicit optimistic-lock Attribute are read from
    the Attribute itself; ``joined`` and ``temporal`` name the endpoints of
    accepted Relationship Joins and the As-Of Axis bounds of the family root.
    Each designation names a declared Attribute by its declaring Entity, never by
    a position that inherits it, so an inherited endpoint answers the same way
    from every Table that reaches it. Audit Metadata designates no Attribute in
    any model this harness reads, so the role selects nothing and needs no set of
    its own.
    """

    joined: frozenset[tuple[str, str]]
    temporal: frozenset[tuple[str, str]]

    def covers(self, owner: str, attribute: Mapping[str, Any]) -> bool:
        """Whether ``attribute`` holds a direct role and stays a Column."""
        if bool(attribute.get("primaryKey")) or bool(attribute.get("optimisticLocking")):
            return True
        designation = (owner, attribute["name"])
        return designation in self.joined or designation in self.temporal


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
                document_column=_layout_column(definition),
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
                    document_column=_layout_column(root_definition),
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
                        document_column=_layout_column(root_definition),
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


def _group_value_objects(group: _Group) -> tuple[tuple[str, dict[str, Any]], ...]:
    """Every ``(owner, top-level occurrence)`` contributing to this group's Table."""
    return tuple(
        (_identity(definition), value_object)
        for definition in group.declarations
        for value_object in definition.get("valueObjects", []) or []
        if isinstance(value_object, dict)
    )


def _diagnostic_claims(
    group: _Group, roles: _DirectRoles | None
) -> tuple[tuple[str, ColumnContributor], ...]:
    """One group's physical Column claims, in diagnostic encounter order.

    Only contributors enter the registry. Under ``Document`` the Attribute and
    Value Object categories therefore contain the owner's direct-role Attributes
    alone, and the shared Structured Column is category five — always the later
    claimant.
    """

    def claims(*, primary_key: bool) -> tuple[tuple[str, ColumnContributor], ...]:
        return tuple(
            (effective_column(attribute), _attribute_contributor(definition, attribute))
            for definition in group.declarations
            for attribute in definition.get("attributes", []) or []
            if isinstance(attribute, dict)
            and bool(attribute.get("primaryKey")) is primary_key
            and (roles is None or roles.covers(_identity(definition), attribute))
        )

    discriminator: tuple[tuple[str, ColumnContributor], ...] = (
        ()
        if group.tag_column is None
        else ((group.tag_column, InheritanceDiscriminator(group.root)),)
    )
    documents: tuple[tuple[str, ColumnContributor], ...] = (
        ()
        if roles is not None
        else tuple(
            (
                value_object.get("column", default_column_name(value_object["name"])),
                _value_object_contributor(definition, value_object),
            )
            for definition in group.declarations
            for value_object in definition.get("valueObjects", []) or []
            if isinstance(value_object, dict)
        )
    )
    structured: tuple[tuple[str, ColumnContributor], ...] = (
        ()
        if group.document_column is None
        else ((group.document_column, RelationalDocument(group.root)),)
    )
    return (
        *claims(primary_key=True),
        *discriminator,
        *claims(primary_key=False),
        *documents,
        *structured,
    )


def _render_contributor(contributor: ColumnContributor) -> str:
    if isinstance(contributor, AttributeContributor):
        return f"Attribute {contributor.owner}.{contributor.name}"
    if isinstance(contributor, ValueObjectContributor):
        return f"Value Object {contributor.owner}.{contributor.name}"
    if isinstance(contributor, RelationalDocument):
        return f"Structured Column of the layout {contributor.layout_owner} declares"
    return f"table-per-hierarchy discriminator of {contributor.root}"


def _layout_column(definition: Mapping[str, Any]) -> str | None:
    """The Structured Column this definition's own ``layout`` names, if any.

    The canonical descriptor always carries the resolved name, so a `layout`
    block without one is not a document mapping this validator can reason about.
    """
    layout = definition.get("layout")
    if not isinstance(layout, dict):
        return None
    document = layout.get("document")
    if not isinstance(document, dict):
        return None
    column = document.get("column")
    return column if isinstance(column, str) and column else None


def _group_attributes(group: _Group) -> tuple[tuple[str, dict[str, Any]], ...]:
    """Every ``(owner, attribute)`` contributing to this group's Table."""
    return tuple(
        (_identity(definition), attribute)
        for definition in group.declarations
        for attribute in definition.get("attributes", []) or []
        if isinstance(attribute, dict)
    )


def _declaring_owner(index: _ModelIndex, entity: str, name: str) -> str | None:
    """The Entity declaring the Attribute ``name`` reaches at ``entity``, or absence.

    A join endpoint is addressed at the position that names it, so an inherited
    Attribute is addressed at a descendant while its declaration lives on an
    ancestor. Residency is decided over declarations, so the walk returns the
    declaring Entity — nearest first, as a position resolves a member.
    """
    if entity not in index.family.defs:
        return None
    for identity in reversed(index.family.ancestry(entity)):
        for attribute in index.family.defs[identity].get("attributes", []) or []:
            if isinstance(attribute, dict) and attribute["name"] == name:
                return identity
    return None


def _joined_attributes(index: _ModelIndex) -> frozenset[tuple[str, str]]:
    """Every ``(declaring owner, attribute name)`` an accepted Relationship Join designates.

    Only a defining declaration is read: a reverse declaration introduces no
    Attribute its defining peer does not already name. Both endpoints of one join
    are returned together or not at all, because an endpoint of a join that does
    not resolve locally is not a designated one — that model is rejected by
    relationship formation, and classifying the excluded Attribute as
    document-resident here does not change that outcome.
    """
    endpoints: set[tuple[str, str]] = set()
    for definition in index.definitions:
        owner = _identity(definition)
        namespace = definition.get("namespace")
        for relationship in definition.get("relationships", []) or []:
            join = relationship.get("join") if isinstance(relationship, dict) else None
            if not isinstance(join, dict):
                continue
            target = join.get("target")
            if not isinstance(target, dict):
                continue
            entity = target["entity"]
            qualified = entity if "." in entity or namespace is None else f"{namespace}.{entity}"
            source_name = join["source"]
            target_name = target["attribute"]
            source_owner = _declaring_owner(index, owner, source_name)
            target_owner = _declaring_owner(index, qualified, target_name)
            if source_owner is None or target_owner is None:
                continue
            endpoints.add((source_owner, source_name))
            endpoints.add((target_owner, target_name))
    return frozenset(endpoints)


def _temporal_bounds(root_definition: Mapping[str, Any], root: str) -> frozenset[tuple[str, str]]:
    return frozenset(
        (root, endpoint.name)
        for axis in temporal_axes(root_definition)
        for endpoint in (axis.start, axis.end)
    )


def _direct_roles(
    index: _ModelIndex, group: _Group, joined: frozenset[tuple[str, str]]
) -> _DirectRoles:
    """The direct-column roles of ``group``, or absence of a Document layout."""
    return _DirectRoles(
        joined=joined,
        temporal=_temporal_bounds(index.family.defs[group.root], group.root),
    )


def _validate_groups(groups: Sequence[_Group], roles_of_group: Mapping[str, _DirectRoles]) -> None:
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
        for column, contributor in _diagnostic_claims(group, roles_of_group.get(group.table)):
            existing = claimed.get(column)
            if existing is not None and existing != contributor:
                raise RejectionError(
                    STORAGE_LAYOUT_COLUMN_COLLISION,
                    f"physical Column {column!r} in Table {group.table!r} is claimed by "
                    f"both {_render_contributor(existing)} and "
                    f"{_render_contributor(contributor)}",
                )
            claimed[column] = contributor


def _validate_document_members(
    groups: Sequence[_Group], roles_of_group: Mapping[str, _DirectRoles]
) -> None:
    """Refuse a Column Override that contradicts the layout it is declared under."""
    for group in groups:
        roles = roles_of_group.get(group.table)
        if roles is None:
            continue
        members: tuple[tuple[str, str, str], ...] = (
            *(
                (owner, attribute["name"], effective_column(attribute))
                for owner, attribute in _group_attributes(group)
                if not roles.covers(owner, attribute)
            ),
            *(
                (
                    owner,
                    value_object["name"],
                    value_object.get("column", default_column_name(value_object["name"])),
                )
                for owner, value_object in _group_value_objects(group)
            ),
        )
        for owner, name, column in members:
            if column == default_column_name(name):
                continue
            raise RejectionError(
                STORAGE_LAYOUT_DOCUMENT_MEMBER_COLUMN_OVERRIDE,
                f"document-resident member {owner}.{name} declares Column {column!r}, "
                f"which it does not occupy under the layout {group.root} declares",
            )


def _validate_document_indices(
    index: _ModelIndex, groups: Sequence[_Group], roles_of_group: Mapping[str, _DirectRoles]
) -> None:
    """Refuse an Index component reaching into a shared Structured Column."""
    resident: dict[tuple[str, str], str] = {}
    for group in groups:
        roles = roles_of_group.get(group.table)
        if roles is None:
            continue
        for owner, attribute in _group_attributes(group):
            if not roles.covers(owner, attribute):
                resident.setdefault((owner, attribute["name"]), group.root)
    for definition in index.definitions:
        owner = _identity(definition)
        for declared in definition.get("indices", []) or []:
            if not isinstance(declared, dict):
                continue
            for component in declared.get("attributes", []) or []:
                if (owner, component) not in resident:
                    continue
                raise RejectionError(
                    STORAGE_LAYOUT_INDEX_OVER_DOCUMENT_MEMBER,
                    f"Index {owner}.{declared['name']} names document-resident Attribute "
                    f"{component!r}, which has no Column to index",
                )


def _roles_by_table(index: _ModelIndex, groups: Sequence[_Group]) -> dict[str, _DirectRoles]:
    """The direct-column roles of every Table a ``Document`` layout governs."""
    joined = _joined_attributes(index)
    return {
        group.table: _direct_roles(index, group, joined)
        for group in groups
        if group.document_column is not None
    }


def validate_storage_layout(entity_defs: Sequence[dict[str, Any]]) -> None:
    """Reject mapping ownership, then Columns, then the layout's own consequences."""
    index = _model_index(entity_defs)
    groups = _project_groups(index)
    roles_of_group = _roles_by_table(index, groups)
    _validate_groups(groups, roles_of_group)
    _validate_document_members(groups, roles_of_group)
    _validate_document_indices(index, groups, roles_of_group)


def _temporal_designations(
    root: Mapping[str, Any], root_identity: str
) -> frozenset[AttributeContributor]:
    return frozenset(
        AttributeContributor(root_identity, endpoint.name)
        for axis in temporal_axes(root)
        for endpoint in (axis.start, axis.end)
    )


def derived_primary_key_index(definition: Mapping[str, Any]) -> dict[str, Any] | None:
    """One Entity's derived unique primary-key Index, or absence when it declares no key.

    The Index is derived on the Entity that DECLARES the primary key rather than
    the one that owns the table, because every Index component is a distinct
    local Attribute of the Index's Entity: under `table-per-concrete-subtype` the
    concrete subtype declares neither the key nor the axes, both being
    root-owned. A storage consumer resolves each component through the applicable
    table layout's contributor lookup, which reaches a root-declared Attribute
    from every concrete table.

    Components are the local primary-key Attributes in declaration order followed
    by each declared axis's END Attribute in canonical dimension rank — the
    columns a Latest predicate and a milestone close both pin. They are distinct
    by construction: each dimension derives its own endpoints, and no other
    attribute may bear one of their names. The name is the table's when the
    Entity owns one, and the Entity's own name folded to the same lowercase shape
    otherwise.
    """
    attributes = [
        attribute["name"]
        for attribute in definition.get("attributes", []) or []
        if isinstance(attribute, dict) and bool(attribute.get("primaryKey"))
    ]
    if not attributes:
        return None
    attributes.extend(axis.end.name for axis in temporal_axes(definition))
    table = definition.get("table")
    name = definition["name"]
    stem = (
        table
        if isinstance(table, str) and table
        else default_column_name(name[:1].lower() + name[1:])
    )
    return {"name": f"{stem}_pk", "attributes": attributes, "unique": True}


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


def _contained_members(occurrence: Mapping[str, Any]) -> list[tuple[str, ...]]:
    """Every member path inside ``occurrence``, relative to the occurrence itself.

    Each contained member extends its container's path by one canonical segment
    at every depth. A ``many`` occurrence contributes exactly one segment like
    any other: that the path crosses a collection is recorded by the occurrence's
    own declared multiplicity rather than by a synthetic segment.
    """
    paths: list[tuple[str, ...]] = []
    for leaf in occurrence.get("attributes", []) or []:
        if isinstance(leaf, dict):
            paths.append((leaf["name"],))
    for nested in occurrence.get("valueObjects", []) or []:
        if not isinstance(nested, dict):
            continue
        paths.append((nested["name"],))
        paths.extend((nested["name"], *deeper) for deeper in _contained_members(nested))
    return paths


def _compile_placements(
    group: _Group,
    roles: _DirectRoles | None,
    by_contributor: Mapping[ColumnContributor, ColumnSlot],
) -> dict[MemberAddress, MemberPlacement]:
    """Where every member applicable to ``group``'s Table lives."""
    document_slot = (
        None if group.document_column is None else by_contributor[RelationalDocument(group.root)]
    )
    placements: dict[MemberAddress, MemberPlacement] = {}
    for owner, attribute in _group_attributes(group):
        address = MemberAddress(owner, (attribute["name"],))
        if document_slot is None or (roles is not None and roles.covers(owner, attribute)):
            placements[address] = DirectColumn(
                by_contributor[AttributeContributor(owner, attribute["name"])]
            )
            continue
        placements[address] = DocumentPath(document_slot, (attribute["name"],))
    for owner, value_object in _group_value_objects(group):
        name = value_object["name"]
        if document_slot is None:
            occurrence_slot = by_contributor[ValueObjectContributor(owner, name)]
            placements[MemberAddress(owner, (name,))] = DirectColumn(occurrence_slot)
            prefix: tuple[str, ...] = ()
        else:
            occurrence_slot = document_slot
            prefix = (name,)
            placements[MemberAddress(owner, (name,))] = DocumentPath(occurrence_slot, (name,))
        for relative in _contained_members(value_object):
            placements[MemberAddress(owner, (name, *relative))] = DocumentPath(
                occurrence_slot, (*prefix, *relative)
            )
    return placements


def _compile_layout(
    family: Family,
    group: _Group,
    roles: _DirectRoles | None,
    audit_designations: frozenset[AttributeContributor],
    applicability_intern: dict[frozenset[str], frozenset[str]],
) -> TableLayout:
    root = family.defs[group.root]
    temporal = _temporal_designations(root, group.root)
    attribute_applicability, value_object_applicability = _applicability(family, group.row_owners)
    row_owners = _interned(set(group.row_owners), applicability_intern)
    derived_key = derived_primary_key_index(root)
    key_contributors = (
        []
        if derived_key is None
        else [AttributeContributor(group.root, name) for name in derived_key["attributes"]]
    )
    key_set = frozenset(key_contributors)

    drafts: list[_Draft] = []
    for definition in group.declarations:
        for attribute in definition.get("attributes", []) or []:
            if not isinstance(attribute, dict):
                continue
            if roles is not None and not roles.covers(_identity(definition), attribute):
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
    if group.document_column is None:
        for definition in group.declarations:
            for value_object in definition.get("valueObjects", []) or []:
                if not isinstance(value_object, dict):
                    continue
                contributor = _value_object_contributor(definition, value_object)
                drafts.append(
                    _Draft(
                        column=value_object.get(
                            "column", default_column_name(value_object["name"])
                        ),
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
    else:
        drafts.append(
            _Draft(
                column=group.document_column,
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
            effective_nullable=(
                False
                if draft.contributor in key_set
                or draft.tier is ColumnTier.DISCRIMINATOR
                or isinstance(draft.contributor, RelationalDocument)
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
    return TableLayout(
        group.table,
        columns,
        tuple(physical_key),
        _compile_placements(group, roles, by_contributor),
    )


@dataclass(frozen=True, slots=True)
class StorageLayout:
    """The model's bounded immutable Table, Entity, and position layout graph.

    Deep-copying a graph yields the graph itself: the values are immutable, and
    the read-only indexes behind the lookups are not copyable. A copy that may
    describe a different model must therefore compile its own graph rather than
    carry this one across.
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
        """Build a query-scoped view for one canonical effective concrete set."""
        selected = tuple(concrete_entities)
        if not selected:
            return PositionLayoutView((), (), (), ())
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
        member_facts = tuple(
            facts for facts in family.members if facts.applicable_entities & selected_set
        )
        members = tuple(facts.member for facts in member_facts)
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
                    placements=tuple(
                        layout.placement(facts.member)
                        if facts.applicable_entities & branch_set
                        else None
                        for facts in member_facts
                    ),
                    discriminator_slot=layout.contribution(InheritanceDiscriminator(family.root)),
                )
            )
        return PositionLayoutView(selected, columns, members, tuple(branches))


def _compile_family_facts(
    index: _ModelIndex,
    roles_of_root: Mapping[str, _DirectRoles],
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
        concretes = tuple(
            _canonical(family, identity) for identity in family.concrete_descendants(root)
        )
        family_inputs.append(
            (
                root,
                concretes,
                _family_declarations(family, _family_members(index, root), root, concretes),
            )
        )
    for root, concretes, declarations in sorted(
        family_inputs, key=lambda item: _identity_sort_key(item[0])
    ):
        temporal = _temporal_designations(family.defs[root], root)
        roles = roles_of_root.get(root)
        attribute_applicability, value_object_applicability = _applicability(family, concretes)
        drafts: list[_PositionFacts] = []
        member_facts: list[_MemberFacts] = []
        for definition in declarations:
            owner = _identity(definition)
            for attribute in definition.get("attributes", []) or []:
                if not isinstance(attribute, dict):
                    continue
                contributor = _attribute_contributor(definition, attribute)
                applicable = _interned(
                    attribute_applicability.get(contributor, set()),
                    applicability_intern,
                )
                member_facts.append(
                    _MemberFacts(MemberAddress(owner, (attribute["name"],)), applicable)
                )
                if roles is not None and not roles.covers(owner, attribute):
                    continue
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
                        applicable,
                    )
                )
        for definition in declarations:
            owner = _identity(definition)
            for value_object in definition.get("valueObjects", []) or []:
                if not isinstance(value_object, dict):
                    continue
                contributor = _value_object_contributor(definition, value_object)
                applicable = _interned(
                    value_object_applicability.get(contributor, set()),
                    applicability_intern,
                )
                member_facts.append(
                    _MemberFacts(MemberAddress(owner, (value_object["name"],)), applicable)
                )
                if roles is not None:
                    continue
                drafts.append(
                    _PositionFacts(
                        PositionColumn(
                            contributor=contributor,
                            tier=ColumnTier.DOCUMENT,
                            declaring_owner=contributor.owner,
                        ),
                        applicable,
                    )
                )
        document_column = _layout_column(family.defs[root])
        if document_column is not None:
            drafts.append(
                _PositionFacts(
                    PositionColumn(
                        contributor=RelationalDocument(root),
                        tier=ColumnTier.DOCUMENT,
                        declaring_owner=root,
                    ),
                    _interned(set(concretes), applicability_intern),
                )
            )
        ordered = tuple(
            column for tier in ColumnTier for column in drafts if column.column.tier is tier
        )
        facts.append(_FamilyFacts(root, concretes, ordered, tuple(member_facts)))
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
    roles_of_group = _roles_by_table(index, groups)
    _validate_groups(groups, roles_of_group)
    applicability_intern: dict[frozenset[str], frozenset[str]] = {}
    layouts = tuple(
        _compile_layout(
            family,
            group,
            roles_of_group.get(group.table),
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
        {
            group.root: roles_of_group[group.table]
            for group in groups
            if group.table in roles_of_group
        },
        audit_designations,
        applicability_intern,
    )
    return StorageLayout(
        tables=layouts,
        _tables=MappingProxyType({layout.table: layout for layout in layouts}),
        _entities=MappingProxyType({view.entity: view for view in entity_views}),
        _families=MappingProxyType({facts.root: facts for facts in family_facts}),
    )


def position_view(
    layout: StorageLayout, family: Family, effective_set: Sequence[str]
) -> PositionLayoutView | None:
    """``layout``'s position over ``effective_set``, canonicalized through ``family``.

    ``effective_set`` names entities as a case authors them; each name resolves to
    its canonical identity and the set is presented in canonical order, so neither
    an authored spelling nor an authored order reaches the layout. Absent when the
    named set is not one family's concrete selection.
    """
    canonical = {_canonical(family, name) for name in effective_set}
    return layout.position(tuple(sorted(canonical, key=_identity_sort_key)))


def position_projection(
    layout: StorageLayout, family: Family, effective_set: Sequence[str]
) -> tuple[str, ...]:
    """The ordered physical Columns a read of ``effective_set`` projects.

    The independent oracle's own answer to `m-sql` *Read projection*: within one
    Table the applicable slots keep canonical `TableLayout.columns` order, so a
    table-per-hierarchy read carries its discriminator slot in the
    `Discriminator` tier rather than after the scalars; a cross-table
    table-per-concrete-subtype position instead follows its one logical
    contributor sequence (`PositionLayoutView.column_spellings`). Result aliases,
    typed `NULL` placeholders, and ``familyVariant`` are SQL renderings and never
    appear here.
    """
    view = position_view(layout, family, effective_set)
    if view is None:
        return ()
    if len(view.branches) == 1:
        branch = view.branches[0]
        selected = frozenset(view.concrete_entities)
        return tuple(
            slot.column for slot in branch.layout.columns if slot.applicable_entities & selected
        )
    return view.column_spellings
