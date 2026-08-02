"""Immutable Storage Layout values, views, indexes, and typed retrieval."""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Protocol, TypeGuard

from parallax.core.metamodel import (
    AttributeIdentity,
    Column,
    EntityIdentity,
    FacetKey,
    MemberIdentity,
    Metamodel,
    Table,
    ValueObjectIdentity,
)
from parallax.core.storage_layout._rules import STORAGE_LAYOUT_MODULE

__all__ = [
    "FACET_KEY",
    "ColumnContributor",
    "ColumnSlot",
    "ColumnTier",
    "DirectColumn",
    "DiscriminatorAssignment",
    "DocumentPath",
    "EntityLayoutView",
    "InheritanceDiscriminator",
    "MemberPlacement",
    "PositionBranch",
    "PositionColumn",
    "PositionColumnFacts",
    "PositionLayoutView",
    "PositionMemberFacts",
    "RelationalDocument",
    "StorageLayoutEntityFacts",
    "StorageLayoutFacet",
    "StorageLayoutFamilyFacts",
    "TableLayout",
    "is_storage_layout_facet",
    "storage_layout_facet",
    "table_layout",
    "view",
]


class ColumnTier(enum.Enum):
    """The closed canonical Table-wide semantic tier order."""

    IDENTITY = "identity"
    DISCRIMINATOR = "discriminator"
    DOMAIN = "domain"
    TEMPORAL = "temporal"
    AUDIT = "audit"
    DOCUMENT = "document"


@dataclass(frozen=True, slots=True)
class InheritanceDiscriminator:
    """The framework-owned TPH discriminator contributed by ``root``."""

    root: EntityIdentity


@dataclass(frozen=True, slots=True)
class RelationalDocument:
    """The shared Structured Column of ``layout_owner``'s ``Document`` layout.

    The layout owner is the standalone Entity or family root whose declaration
    selected the layout, so one table-per-hierarchy family has one contributor
    for its shared Table and a table-per-concrete-subtype family one per concrete
    Table, all naming the same owner and the same Column. It is the only
    contributor that claims a Structured Column under ``Document``:
    document-resident members contribute no slot and make no Column claim at all.
    """

    layout_owner: EntityIdentity


type ColumnContributor = (
    AttributeIdentity | ValueObjectIdentity | InheritanceDiscriminator | RelationalDocument
)
"""The closed identity-bearing provenance algebra for physical Columns.

An Attribute contributes its ``AttributeIdentity``, a top-level document
contributes its ``ValueObjectIdentity``, a TPH tag contributes an
``InheritanceDiscriminator`` carrying the family root identity, and a Relational
Document Layout's shared Structured Column contributes a ``RelationalDocument``
carrying its layout owner.
"""


@dataclass(frozen=True, slots=True)
class ColumnSlot:
    """One immutable physical Column occurrence in one Table Layout.

    Slot equality is structural over the accepted values retained here. A slot
    in another TPCS Table necessarily has a different applicability set even
    when it references the same inherited declaration.
    """

    column: Column
    tier: ColumnTier
    contributor: ColumnContributor
    declaring_owner: EntityIdentity
    effective_nullable: bool
    applicable_entities: frozenset[EntityIdentity]


@dataclass(frozen=True, slots=True)
class DirectColumn:
    """A member stored in a Column of its own, over the slot its contributor owns."""

    slot: ColumnSlot


@dataclass(frozen=True, slots=True)
class DocumentPath:
    """A member stored inside ``slot``'s document at ``path``.

    ``path`` is a nonempty sequence of canonical local declared member names
    relative to the root of the document that slot carries — the Table's one
    shared Structured Column under ``Document``, and the containing top-level
    Value Object occurrence's own Structured Column under ``Columns``. It names
    no physical spelling, no dotted string, and no provider-native path
    expression; rendering one into a dialect path expression happens below this
    contract. An empty path raises :class:`ValueError`.
    """

    slot: ColumnSlot
    path: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("a Document Path names at least one member")


type MemberPlacement = DirectColumn | DocumentPath
"""Where one logical member of one Table lives.

``DirectColumn`` names a Column the member's own contributor owns;
``DocumentPath`` names a document slot plus the path locating the member inside
it. The union is closed and carries no provisional or deferred arm.
"""


class TableLayout(Protocol):
    """The complete canonical physical shape of one structural Table."""

    @property
    def table(self) -> Table: ...
    @property
    def columns(self) -> Sequence[ColumnSlot]: ...
    @property
    def physical_primary_key(self) -> Sequence[ColumnSlot]: ...
    def column(self, column: Column) -> ColumnSlot | None: ...
    def contribution(self, contributor: ColumnContributor) -> ColumnSlot | None: ...
    def placement(self, member: MemberIdentity) -> MemberPlacement | None: ...


@dataclass(frozen=True, slots=True)
class DiscriminatorAssignment:
    """The shared-table discriminator slot and one concrete Entity's tag value."""

    slot: ColumnSlot
    value: str


class EntityLayoutView(Protocol):
    """One row-owning Entity's selection over its canonical Table Layout."""

    @property
    def entity(self) -> EntityIdentity: ...
    @property
    def layout(self) -> TableLayout: ...
    @property
    def columns(self) -> Sequence[ColumnSlot]: ...
    @property
    def discriminator(self) -> DiscriminatorAssignment | None: ...


@dataclass(frozen=True, slots=True)
class PositionColumn:
    """One logical declaration-provenance column of a polymorphic position."""

    contributor: AttributeIdentity | ValueObjectIdentity
    tier: ColumnTier
    declaring_owner: EntityIdentity


@dataclass(frozen=True, slots=True)
class PositionBranch:
    """One physical Table branch aligned to a Position Layout's logical columns.

    ``slots`` aligns with the view's ``columns`` and ``placements`` with its
    ``members``; each entry is present when its contributor or member applies to
    at least one selected concrete in this branch and absent otherwise.
    ``placements`` is a derived projection rather than a second fact — each entry
    is ``layout.placement(member)`` — so a polymorphic read gets the per-branch
    answer in the logical order it walks.
    """

    layout: TableLayout
    concrete_entities: tuple[EntityIdentity, ...]
    slots: tuple[ColumnSlot | None, ...]
    placements: tuple[MemberPlacement | None, ...]
    discriminator_slot: ColumnSlot | None


class PositionLayoutView(Protocol):
    """A canonical concrete set's logical projection and physical branches."""

    @property
    def concrete_entities(self) -> Sequence[EntityIdentity]: ...
    @property
    def columns(self) -> Sequence[PositionColumn]: ...
    @property
    def members(self) -> Sequence[MemberIdentity]: ...
    @property
    def branches(self) -> Sequence[PositionBranch]: ...


class StorageLayoutFacet(Protocol):
    """The model's bounded canonical layouts plus Entity and position views."""

    @property
    def tables(self) -> Sequence[TableLayout]: ...
    def table(self, table: Table) -> TableLayout | None: ...
    def entity(self, entity: EntityIdentity) -> EntityLayoutView | None: ...
    def position(
        self, concrete_entities: Sequence[EntityIdentity]
    ) -> PositionLayoutView | None: ...


@dataclass(frozen=True, slots=True)
class _TableLayout:
    table: Table
    columns: tuple[ColumnSlot, ...]
    physical_primary_key: tuple[ColumnSlot, ...]
    _placements: Mapping[MemberIdentity, MemberPlacement] = field(repr=False, compare=False)
    _column_index: Mapping[Column, ColumnSlot] = field(init=False, repr=False, compare=False)
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

    def column(self, column: Column) -> ColumnSlot | None:
        return self._column_index.get(column)

    def contribution(self, contributor: ColumnContributor) -> ColumnSlot | None:
        return self._contributor_index.get(contributor)

    def placement(self, member: MemberIdentity) -> MemberPlacement | None:
        return self._placements.get(member)


def table_layout(
    table: Table,
    columns: Sequence[ColumnSlot],
    physical_primary_key: Sequence[ColumnSlot],
    placements: Mapping[MemberIdentity, MemberPlacement],
) -> TableLayout:
    """Construct one immutable lookup-bearing Table Layout.

    This is the compiler-facing constructor. ``placements`` is the complete
    answer for every member applicable to ``table``, so the published lookup is
    total rather than computed per call. Public consumers receive the protocol
    and cannot mutate either index or ordered sequence.
    """
    return _TableLayout(
        table,
        tuple(columns),
        tuple(physical_primary_key),
        MappingProxyType(dict(placements)),
    )


@dataclass(frozen=True, slots=True)
class _EntityLayoutView:
    entity: EntityIdentity
    layout: TableLayout
    discriminator: DiscriminatorAssignment | None
    _column_ordinals: SlotOrdinalSelection = field(repr=False)

    @property
    def columns(self) -> tuple[ColumnSlot, ...]:
        return self._column_ordinals.materialize(self.layout.columns)


@dataclass(frozen=True, slots=True)
class _PositionLayoutView:
    concrete_entities: tuple[EntityIdentity, ...]
    columns: tuple[PositionColumn, ...]
    members: tuple[MemberIdentity, ...]
    branches: tuple[PositionBranch, ...]


@dataclass(frozen=True, slots=True)
class PositionColumnFacts:
    """Compiler facts for filtering one family-level logical contributor."""

    column: PositionColumn
    applicable_entities: frozenset[EntityIdentity]


@dataclass(frozen=True, slots=True)
class PositionMemberFacts:
    """Compiler facts for filtering one family-level top-level logical member.

    The member sequence is derived before tier partitioning, so these facts are
    retained separately from :class:`PositionColumnFacts` even where the two
    cover the same declarations.
    """

    member: AttributeIdentity | ValueObjectIdentity
    applicable_entities: frozenset[EntityIdentity]


@dataclass(frozen=True, slots=True)
class SlotOrdinalSelection:
    """A compact bit selection over one Table Layout's slot ordinals."""

    bits: int

    def materialize(self, columns: Sequence[ColumnSlot]) -> tuple[ColumnSlot, ...]:
        return tuple(slot for ordinal, slot in enumerate(columns) if self.bits & (1 << ordinal))


@dataclass(frozen=True, slots=True)
class StorageLayoutEntityFacts:
    """Compact retained facts for one row-owning Entity view."""

    entity: EntityIdentity
    root: EntityIdentity
    layout: TableLayout
    discriminator: DiscriminatorAssignment | None
    column_ordinals: SlotOrdinalSelection


@dataclass(frozen=True, slots=True)
class StorageLayoutFamilyFacts:
    """The bounded logical contributor and member sequences position views select from."""

    root: EntityIdentity
    concrete_entities: tuple[EntityIdentity, ...]
    columns: tuple[PositionColumnFacts, ...]
    members: tuple[PositionMemberFacts, ...]


class _StorageLayoutFacet:
    __slots__ = ("_entities", "_families", "_table_values", "_tables")

    _table_values: tuple[TableLayout, ...]
    _tables: Mapping[Table, TableLayout]
    _entities: Mapping[EntityIdentity, StorageLayoutEntityFacts]
    _families: Mapping[EntityIdentity, StorageLayoutFamilyFacts]

    def __init__(
        self,
        layouts: Sequence[TableLayout],
        entities: Sequence[StorageLayoutEntityFacts],
        families: Sequence[StorageLayoutFamilyFacts],
    ) -> None:
        self._table_values = tuple(layouts)
        self._tables = MappingProxyType({layout.table: layout for layout in self._table_values})
        self._entities = MappingProxyType({facts.entity: facts for facts in entities})
        self._families = MappingProxyType({facts.root: facts for facts in families})

    @property
    def tables(self) -> tuple[TableLayout, ...]:
        return self._table_values

    def table(self, table: Table) -> TableLayout | None:
        return self._tables.get(table)

    def entity(self, entity: EntityIdentity) -> EntityLayoutView | None:
        facts = self._entities.get(entity)
        if facts is None:
            return None
        return _EntityLayoutView(
            facts.entity,
            facts.layout,
            facts.discriminator,
            facts.column_ordinals,
        )

    def position(self, concrete_entities: Sequence[EntityIdentity]) -> PositionLayoutView | None:
        selected = tuple(concrete_entities)
        if not selected:
            return _PositionLayoutView((), (), (), ())
        if selected != tuple(sorted(set(selected), key=lambda identity: identity.sort_key)):
            return None
        entity_facts: list[StorageLayoutEntityFacts] = []
        for entity in selected:
            facts = self._entities.get(entity)
            if facts is None:
                return None
            entity_facts.append(facts)
        roots = {facts.root for facts in entity_facts}
        if len(roots) != 1:
            return None
        family = self._families.get(next(iter(roots)))
        if (  # pragma: no cover - every row owner's own root retains its concrete set
            family is None or not set(selected) <= set(family.concrete_entities)
        ):
            return None
        selected_set = frozenset(selected)
        column_facts = tuple(
            facts for facts in family.columns if facts.applicable_entities & selected_set
        )
        columns = tuple(facts.column for facts in column_facts)
        member_facts = tuple(
            facts for facts in family.members if facts.applicable_entities & selected_set
        )
        members = tuple(facts.member for facts in member_facts)

        branch_entities: dict[Table, list[EntityIdentity]] = {}
        for facts in entity_facts:
            branch_entities.setdefault(facts.layout.table, []).append(facts.entity)
        branches: list[PositionBranch] = []
        for table, entities in branch_entities.items():
            layout = self._tables[table]
            branch_set = frozenset(entities)
            slots = tuple(
                (
                    layout.contribution(facts.column.contributor)
                    if facts.applicable_entities & branch_set
                    else None
                )
                for facts in column_facts
            )
            placements = tuple(
                layout.placement(facts.member) if facts.applicable_entities & branch_set else None
                for facts in member_facts
            )
            discriminator = layout.contribution(InheritanceDiscriminator(family.root))
            branches.append(
                PositionBranch(
                    layout=layout,
                    concrete_entities=tuple(entities),
                    slots=slots,
                    placements=placements,
                    discriminator_slot=discriminator,
                )
            )
        return _PositionLayoutView(selected, columns, members, tuple(branches))


def storage_layout_facet(
    layouts: Sequence[TableLayout],
    entities: Sequence[StorageLayoutEntityFacts],
    families: Sequence[StorageLayoutFamilyFacts],
) -> StorageLayoutFacet:
    """Construct the immutable facet from compiler-owned bounded facts."""
    return _StorageLayoutFacet(layouts, entities, families)


def is_storage_layout_facet(value: object) -> TypeGuard[StorageLayoutFacet]:
    """Whether ``value`` is the facet implementation this module constructs."""
    return isinstance(value, _StorageLayoutFacet)


FACET_KEY: Final[FacetKey[StorageLayoutFacet]] = FacetKey(
    STORAGE_LAYOUT_MODULE, is_storage_layout_facet
)
"""The typed key used to install and retrieve the Storage Layout Facet."""


def view(model: Metamodel) -> StorageLayoutFacet:
    """Return ``model``'s typed Storage Layout Facet."""
    return model.facet(FACET_KEY)
