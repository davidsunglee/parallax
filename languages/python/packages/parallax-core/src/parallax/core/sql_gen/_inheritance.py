from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

from parallax.core.base import (
    NeutralType,
    UnknownFamilyTag,
)
from parallax.core.deep_fetch import PlannedEntityQuery, ResolvedReadProjection
from parallax.core.dialect import LockMode, ScalarResult
from parallax.core.document_codec import MemberShape
from parallax.core.inheritance import (
    EntityMemberSelection,
    InheritanceEntityView,
    InheritanceFacet,
    InheritancePositionView,
    family_variant_name,
)
from parallax.core.metamodel import (
    AbstractRoot,
    AbstractSubtype,
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    MemberIdentity,
    Multiplicity,
    TablePerConcreteSubtype,
    TablePerHierarchy,
    ValueObjectIdentity,
    ValueObjectMetadata,
)
from parallax.core.sql_gen._context import ColumnScope as _ColumnScope
from parallax.core.sql_gen._context import SqlGenError
from parallax.core.sql_gen._context import table_layout as _table_layout
from parallax.core.storage_layout import (
    ColumnContributor,
    ColumnSlot,
    ColumnTier,
    DirectColumn,
    DocumentResidentSelection,
    EntityLayoutView,
    InheritanceDiscriminator,
    PositionBranch,
    PositionLayoutView,
    RelationalDocument,
    StorageLayoutFacet,
    TableLayout,
)


def entity_view(facet: InheritanceFacet, entity: EntityIdentity) -> InheritanceEntityView:
    """``entity``'s family-effective view; the facet covers every accepted Entity."""
    view = facet.entity(entity)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        raise SqlGenError(f"{entity.canonical}: the model declares no such entity")
    return view


def storage_entity_view(facet: StorageLayoutFacet, entity: EntityIdentity) -> EntityLayoutView:
    """``entity``'s prepared physical selection; accepted row owners are total."""
    view = facet.entity(entity)
    if view is None:  # pragma: no cover - the facet covers every accepted row owner
        raise SqlGenError(f"{entity.canonical}: the model declares no storage layout")
    return view


def tag_column(layout: TableLayout, root: EntityIdentity) -> str:
    """The physical discriminator Column ``root``'s family discriminates by."""
    slot = layout.contribution(InheritanceDiscriminator(root))
    if slot is None:  # pragma: no cover - every table-per-hierarchy layout carries one
        raise SqlGenError(f"{root.canonical}: this family's Table Layout has no discriminator")
    return slot.column.name


def tag_value(facet: InheritanceFacet, concrete: EntityIdentity) -> str:
    """The value ``concrete``'s rows carry in its family's shared tag column."""
    value = entity_view(facet, concrete).tag_value
    if value is None:  # pragma: no cover - a validated TPH concrete always declares one
        raise SqlGenError(
            f"{concrete.canonical}: table-per-hierarchy concrete subtype declares no tagValue"
        )
    return value


type ResolvedVariant = tuple[EntityIdentity, str | None, UnknownFamilyTag | None]
"""What resolving one row answers: the concrete Entity it names, the
`familyVariant` spelling it publishes, and the stored discriminator no composed
concrete subtype claimed."""


@dataclass(frozen=True, slots=True)
class FixedRowIdentity:
    """Every row of this read names one Entity; no carrier is read.

    A standalone read, a table-per-hierarchy read whose queried target is itself
    concrete, and a table-per-concrete-subtype read resolving to one concrete
    all project nothing that could name a different Entity, so the answer is
    fixed when the read is compiled and no row is consulted for it.
    """

    entity: EntityIdentity


@dataclass(frozen=True, slots=True)
class TaggedRowIdentity:
    """Table-per-hierarchy: the framework-owned raw tag ``column`` names the row's
    concrete, and never reaches the caller.

    ``tag_pairs`` is a `(tagValue, Identity, variant spelling)` mapping in the
    facet's canonical concrete-subtype order. For a homogeneous read it is the
    WHOLE family's — never the read's own resolved position, since a narrowed
    abstract read still projects the shared table's tag column and may observe
    any of them — and for a heterogeneous shared document it is the position's,
    which is the pairing the document shapes are keyed by. A tuple of pairs
    rather than a `Mapping` is what keeps `CompiledRead` hashable and its `repr`
    stable; ``by_tag`` holds the whole answer a hit gives, so a resolved row
    allocates nothing for it.

    "The whole family" is the family as this model COMPOSES it, which need not be
    the family the shared Table holds: a model may compose a family's concrete
    leaves partially (`m-inheritance`), and an abstract-root read injects no tag
    predicate, so a row tagged for an uncomposed sibling can reach its reader.
    ``root`` is carried so that row is refused by name — the family it belongs to
    and the composed tags it could have matched — rather than by a bare mapping
    miss.
    """

    column: str
    root: EntityIdentity
    tag_pairs: tuple[tuple[str, EntityIdentity, str], ...]
    by_tag: Mapping[object, ResolvedVariant] = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "by_tag",
            {tag: (identity, spelling, None) for tag, identity, spelling in self.tag_pairs},
        )


@dataclass(frozen=True, slots=True)
class LiteralRowIdentity:
    """Table-per-concrete-subtype `union all`: the per-branch projected
    subtype-name literal ``column`` names the row's concrete — there is no tag
    column to derive it from.

    The branch that produced a row owns some of the union's result aliases and
    reads the rest as its siblings' typed `NULL` padding. ``narrow_to_owned``
    is the object lane's: such a read publishes only what the resolved branch
    owns, while a row-form read keeps a sibling's null padding under an alias
    that is its own publication key, as the corpus expects.
    """

    column: str
    variants: tuple[tuple[str, EntityIdentity], ...]
    narrow_to_owned: bool
    by_spelling: Mapping[object, ResolvedVariant] = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "by_spelling",
            {spelling: (identity, spelling, None) for spelling, identity in self.variants},
        )


type RowIdentity = FixedRowIdentity | TaggedRowIdentity | LiteralRowIdentity
"""How one read's rows name their Entity: fixed when the read is compiled, by a
table-per-hierarchy tag, or by a `union all` branch's variant literal."""


@dataclass(frozen=True, slots=True)
class DocumentFanOut:
    """One resolved concrete's share of a read's shared Structured Column.

    ``shape`` is absent for a `union all` branch that stores no document of its
    own: such a row carries no document to decode and still pads the members its
    siblings' documents carry, which is the state that padding stands for.
    ``members`` may be empty for a present shape too — an observation-bearing
    read of an owner with no document-resident member projects the column for the
    stored document itself, and naming it keeps that document off the row's
    values.
    """

    shape: MemberShape | None
    members: tuple[tuple[str, tuple[str, ...]], ...]
    padding: tuple[str, ...] = ()
    member_paths: Mapping[str, tuple[str, ...]] = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "member_paths", dict(self.members))


@dataclass(frozen=True, slots=True)
class SharedDocumentMapping:
    """Relational Document Layout: the one projected Structured Column the
    members the read asked for are fanned out of.

    The Structured Column is never a result field (`m-sql`): each member lands
    under the very result key it would have carried as a direct Column, which is
    what makes one read's logical output the same under either layout.

    ``column`` is ONE row key for the whole read, including a `union all` whose
    branches each hold their own Structured Column: Storage Layout is root-owned,
    so every branch of a family spells that column the way the root declared it,
    and the union projects the document tier under one result alias
    (`_contributor_column`) whatever the branch that rendered the row.
    """

    column: str
    per_entity: tuple[tuple[EntityIdentity, DocumentFanOut], ...]
    by_entity: Mapping[EntityIdentity, DocumentFanOut] = field(
        init=False, compare=False, repr=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "by_entity", dict(self.per_entity))


@dataclass(frozen=True, slots=True)
class DirectDocumentMappings:
    """Each concrete's projected documents stored in a Column of their own.

    A provider folds every selected document pair before materialization,
    regardless of whether the carrier is the Table's shared Structured Column, a
    Value Object's own Column, or a scalar collection's own Column. These are the
    latter two carriers, each with its member's declared definition, resolved
    once at compile time rather than per row. They are keyed by the concrete a
    row RESOLVES to, so a read whose position holds several concretes classifies
    the documents of the one its row names.
    """

    per_entity: tuple[
        tuple[EntityIdentity, tuple[AttributeMetadata | ValueObjectMetadata, ...]], ...
    ]
    by_entity: Mapping[EntityIdentity, tuple[AttributeMetadata | ValueObjectMetadata, ...]] = field(
        init=False, compare=False, repr=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "by_entity", dict(self.per_entity))


@dataclass(frozen=True, slots=True)
class CellSource:
    """A member read from its own folded driver-row cell."""

    ordinal: int


@dataclass(frozen=True, slots=True)
class DocumentMemberSource:
    """A member located at ``member_name`` in the shared Structured Column the
    folded driver-row cell at ``ordinal`` carries."""

    ordinal: int
    member_name: str


type MemberSource = CellSource | DocumentMemberSource


@dataclass(frozen=True, slots=True)
class EntitySources:
    """Where a row resolving to ``entity`` carries each of its members, aligned
    with ``selection``'s canonical member order.

    ``None`` is a member the read intentionally does not carry, which a row
    delivers as absent; a carried SQL `NULL` is a present cell.
    """

    entity: EntityIdentity
    selection: EntityMemberSelection
    sources: tuple[MemberSource | None, ...]

    def cell_ordinals(self) -> tuple[int | None, ...]:
        """Each member's own cell, absent for a shared-document resident."""
        return tuple(
            source.ordinal if isinstance(source, CellSource) else None for source in self.sources
        )

    def document_member_names(self) -> tuple[str | None, ...]:
        """Each shared-document resident's member name in the unwrapped document."""
        return tuple(
            source.member_name if isinstance(source, DocumentMemberSource) else None
            for source in self.sources
        )


@dataclass(frozen=True, slots=True)
class DriverRowSlot:
    """What publication needs to know about one folded value cell.

    ``scalar`` is the cell's scalar publication spelling and encoding; a
    document cell has none. ``padding_key`` is the key under which the cell
    stays in every resolved row's flat publication, as null where that row's
    Entity carries nothing there; a cell only its owners publish has none.
    """

    scalar: ScalarResult | None
    padding_key: str | None


@dataclass(frozen=True, slots=True)
class ReadResultContract:
    """What one compiled read's folded driver rows carry, and where.

    ``row_identity`` is how this read's rows name their Entity, and every read
    has one: a tag map, a union's variant literal, or an identity fixed when the
    read was compiled. A fixed identity — a standalone read, a concrete-target
    table-per-hierarchy read, or a table-per-concrete-subtype read whose position
    resolved to a single concrete — has no carrier and no `familyVariant` to
    materialize. The document entries are the projection's decision alone: a
    read fills them when it projected a document, however its rows are named.

    ``entity_sources`` covers every Entity this read's rows can name: the
    position, and whatever the row identity reaches past it. A homogeneous tag
    map is the WHOLE family's rather than the read's narrow, so a narrowed
    abstract read still resolves a sibling's row to that sibling, and a tag no
    composed concrete claims resolves the row to the family root — which is
    never a concrete in the position. Such an Entity carries only the cells
    that are its own members under their own spelling.

    ``slots`` has one entry per folded cell, so its length is the row's arity;
    carriers and document cells no row publishes have none. The carrier
    ordinals locate the row identity's cell, the shared Structured Column, and
    one Continuation Order coordinate per ordering term, in term order — none
    for a read that pages through nothing. A caller that needs the stored
    document — a temporal observation retains it (`m-write-plan`'s Predecessor
    Row) — reads it from the shared document's cell.
    """

    row_identity: RowIdentity
    shared_document: SharedDocumentMapping | None
    direct_documents: DirectDocumentMappings | None
    entity_sources: tuple[EntitySources, ...] = field(repr=False)
    slots: tuple[DriverRowSlot | None, ...] = field(repr=False)
    identity_ordinal: int | None
    shared_document_ordinal: int | None
    coordinate_ordinals: tuple[int, ...]
    resolvable: tuple[EntityIdentity, ...] = field(init=False, repr=False, compare=False)
    _by_entity: Mapping[EntityIdentity, EntitySources] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        carriers = self._carriers()
        by_entity = {sources.entity: sources for sources in self.entity_sources}
        if len(by_entity) != len(self.entity_sources):
            raise ValueError("an Entity's sources are given once")
        if set(_named_entities(self.row_identity)) - by_entity.keys():
            raise ValueError("every Entity the row identity names has sources")
        for sources in self.entity_sources:
            self._require_sources(sources, carriers)
        object.__setattr__(self, "_by_entity", MappingProxyType(by_entity))
        object.__setattr__(
            self, "resolvable", tuple(sources.entity for sources in self.entity_sources)
        )

    def _carriers(self) -> frozenset[int]:
        carriers = (
            *(() if self.identity_ordinal is None else (self.identity_ordinal,)),
            *(() if self.shared_document_ordinal is None else (self.shared_document_ordinal,)),
            *self.coordinate_ordinals,
        )
        if any(
            not 0 <= ordinal < len(self.slots) or self.slots[ordinal] is not None
            for ordinal in carriers
        ):
            raise ValueError("a result carrier must name a cell the row carries no value in")
        if len(set(carriers)) != len(carriers):
            raise ValueError("two result carriers name one cell")
        if isinstance(self.row_identity, FixedRowIdentity) != (self.identity_ordinal is None):
            raise ValueError("a row identity carrier is required exactly where rows name it")
        if (self.shared_document is None) != (self.shared_document_ordinal is None):
            raise ValueError("a shared document carrier is required exactly where one is read")
        return frozenset(carriers)

    def _require_sources(self, sources: EntitySources, carriers: frozenset[int]) -> None:
        if len(sources.sources) != len(sources.selection.identities):
            raise ValueError(f"{sources.entity.canonical}: sources must align with its members")
        for source in sources.sources:
            if isinstance(source, DocumentMemberSource):
                if source.ordinal != self.shared_document_ordinal:
                    raise ValueError("a document resident is read from the shared document")
            elif source is not None and (
                not 0 <= source.ordinal < len(self.slots) or source.ordinal in carriers
            ):
                raise ValueError(f"{sources.entity.canonical}: a member names no value cell")

    def sources(self, entity: EntityIdentity) -> EntitySources:
        """Where a row resolving to ``entity`` carries its members.

        Raises ``KeyError`` for an Entity this read's rows never name.
        """
        return self._by_entity[entity]

    def source(self, entity: EntityIdentity, member: MemberIdentity) -> MemberSource | None:
        """Where a row resolving to ``entity`` carries ``member``, or ``None``
        where it intentionally carries none."""
        sources = self._by_entity[entity]
        return sources.sources[sources.selection.position(member)]


def _named_entities(row_identity: RowIdentity) -> tuple[EntityIdentity, ...]:
    match row_identity:
        case FixedRowIdentity(entity=entity):
            return (entity,)
        case TaggedRowIdentity(root=root, tag_pairs=pairs):
            return (root, *(identity for _, identity, _ in pairs))
        case LiteralRowIdentity(variants=variants):
            return tuple(identity for _, identity in variants)


def resolvable_entities(
    position: Sequence[EntityIdentity], row_identity: RowIdentity
) -> tuple[EntityIdentity, ...]:
    """The Entities a read of ``position`` can name a row by, position first."""
    return tuple(dict.fromkeys((*position, *_named_entities(row_identity))))


def tag_pairs(
    facet: InheritanceFacet, concretes: Sequence[EntityIdentity]
) -> tuple[tuple[str, EntityIdentity, str], ...]:
    """``concretes``' `(tagValue, Identity, variant spelling)` triples, in order."""
    return tuple(
        (tag_value(facet, concrete), concrete, family_variant_name(facet, concrete))
        for concrete in concretes
    )


def family_tag_pairs(
    facet: InheritanceFacet, root: EntityIdentity
) -> tuple[tuple[str, EntityIdentity, str], ...]:
    """The WHOLE family's triples, in the facet's canonical concrete-subtype order.

    Deliberately the family's set, not the read's resolved position: a narrowed
    abstract read still projects the shared table's raw tag column, and the
    mapping that interprets it is a property of the family, not of the narrow
    (`m-inheritance-012`). A read whose document shapes are keyed per concrete
    resolves the position's own pairs instead, so one row's tag and one row's
    document shape name the same concrete.
    """
    return tag_pairs(facet, entity_view(facet, root).concrete_subtypes)


TagKind = Literal["eq", "in"]


@dataclass(frozen=True, slots=True)
class TagPredicate:
    """The inputs ONE tag guard needs, as one value (m-sql *Tag-predicate
    selection*).

    These travelled as three separate parameters and as three fields on each of
    two plans, and they are meaningless apart — a tag column with nothing to
    compare it against, or a position with no column to compare it in, is not a
    guard. A read or hop carrying NO tag predicate at all (an untouched abstract
    ROOT target) spells that as ``None`` rather than as a sentinel string, so
    "is there a guard here?" is a question the type answers.

    :attr:`kind` is DERIVED rather than stored: m-sql keys the guard's shape
    purely to the resolved position's size, so this cannot describe a
    one-concrete position guarded by `in`, or several guarded by `=`, even by
    accident. The rule is therefore written once, here.
    """

    column: str
    position: tuple[EntityIdentity, ...]

    @property
    def kind(self) -> TagKind:
        """`=` for a single concrete, `in` for several (m-sql *Tag-predicate
        selection*)."""
        return "eq" if len(self.position) == 1 else "in"


def tag_guard(
    scope: _ColumnScope, facet: InheritanceFacet, tag: TagPredicate
) -> tuple[str, tuple[object, ...]]:
    """PLAN the tag-predicate guard for ``tag`` (m-sql *Tag-predicate
    selection*): `t0.<tag> = ?` for one concrete, `t0.<tag> in (?, …)` for several
    — the `in` list in the position's already-canonical order, so its tag values
    follow suit.

    This returns the fragment AND its bind values and pushes nothing; every caller
    binds them itself, after it has lowered its own interior predicate. That split
    is not stylistic. A bind-as-you-render helper can only be sequenced correctly
    if the caller never evaluates it early — and the natural spelling at the
    correlated-hop call site was to pass it as an ARGUMENT to the function that
    lowers the interior, which Python evaluates BEFORE the call. The guard's bind
    then landed ahead of the interior's own while the emitted text still put the
    guard last, so SQL and binds disagreed (`bark_volume = ? and kind = ?` against
    `('dog', 5)`). m-sql "Grouped branch predicates" fixes the contract exactly:
    the guard is appended after the branch predicate and "binds read
    branch-predicate-first then tag". Returning data makes the ordering the
    caller's explicit, visible statement rather than an evaluation-order accident.

    ``scope`` is a :class:`~parallax.core.sql_gen._context.ColumnScope`, not the
    whole context: the ONE capability rendering a guard needs is "how does this
    statement spell its own column", and taking no more than that is what makes
    the paragraph above a type rule rather than a promise. A caller still just
    passes its own resolution scope, which satisfies the protocol structurally.

    The tag column is THIS scope's own column, so it renders through
    :meth:`ColumnScope.own_column` like every other one: the framework-owned tag
    is no more alias-qualified than a declared attribute is. On every read
    scope ``unaliased`` is ``False`` and this is exactly ``qualified(alias,
    tag.column)``, so no emitted read SQL depends on the distinction — it exists
    so the leak cannot reopen from a caller that arrives with an unaliased
    scope, rather than resting on every such caller being rejected upstream
    first.
    """
    col = scope.own_column(tag.column)
    tag_values = [tag_value(facet, concrete) for concrete in tag.position]
    if tag.kind == "eq":
        return f"{col} = ?", (tag_values[0],)
    holes = ", ".join("?" for _ in tag_values)
    return f"{col} in ({holes})", tuple(tag_values)


@dataclass(frozen=True, slots=True)
class ProjectedColumn:
    """One selected physical Column, the contributor it carries, and the seam
    the dialect renders it through.

    ``type`` is the contributing Attribute's neutral type, or ``None`` for a slot
    with no scalar rendering seam — a document column or the framework-owned
    discriminator — which projects as a plain alias-qualified reference.
    """

    contributor: ColumnContributor
    column: str
    type: NeutralType | None
    document: bool = False


def position_slots(
    layout: TableLayout, position: Sequence[EntityIdentity]
) -> tuple[ColumnSlot, ...]:
    """``layout``'s slots applicable to ``position``, in canonical Table order."""
    selected = frozenset(position)
    return tuple(slot for slot in layout.columns if slot.applicable_entities & selected)


def _structured_column_slot(layout: TableLayout) -> ColumnSlot | None:
    """``layout``'s shared Structured Column slot, or absence under `Columns`.

    A governed Table carries exactly one whatever its members' placements are,
    an owner whose every member holds a direct-column role included: its
    Structured Column is still physically present and still holds a document.
    """
    return next(
        (slot for slot in layout.columns if isinstance(slot.contributor, RelationalDocument)), None
    )


type _Members = tuple[tuple[str, tuple[str, ...]], ...]
"""Fetched resident members, as (result key, Document Path) pairs."""


def plan_document_reads(
    layout: PositionLayoutView,
    facet: InheritanceFacet,
    storage: StorageLayoutFacet,
    projection: ResolvedReadProjection,
    *,
    pad_siblings: bool,
) -> tuple[SharedDocumentMapping | None, DirectDocumentMappings | None]:
    """The documents a read of ``layout``'s position fetches, and the mappings
    that read them back out (`m-sql` *Read projection*, rules 3 and 5).

    The read produces every Attribute and ``projection``'s Value Objects. Each
    one's Member Placement in its concrete's branch decides where it is read
    from: the ones placed at a Document Path make that branch's Structured
    Column needed, projected **once**, raw, whatever their number, and the
    scalar collections and occurrences holding a Column of their own are the
    direct mappings. A read observing the stored document itself — a
    Predecessor Row retains the raw document (`m-write-plan`) — needs every
    Structured Column there is, whatever resides in it.

    The shared mapping is present exactly when some concrete needs its
    Structured Column, which every branch then spells as the root declared it.
    It keys every concrete of the position by the storage owner's complete
    resident shape, so a heterogeneous document is decoded by the shape of the
    concrete the ROW named, and a concrete fetching none of its residents fans
    nothing out of it. ``pad_siblings`` is a flat-row publication's alone: each
    entry then pads every fetched member key its siblings carry, which changes
    neither what is fetched nor what is observed.
    """
    entries: list[tuple[EntityIdentity, DocumentResidentSelection | None, _Members]] = []
    direct: list[tuple[EntityIdentity, tuple[AttributeMetadata | ValueObjectMetadata, ...]]] = []
    document_column: str | None = None
    for branch in layout.branches:
        for concrete in branch.concrete_entities:
            residents = storage_entity_view(storage, concrete).document_residents
            column, members = _fetched_residents(residents, branch.layout, projection)
            if document_column is None:
                document_column = column
            entries.append((concrete, residents, members))
            inherited = entity_view(facet, concrete)
            direct.append(
                (
                    concrete,
                    _direct_members(
                        branch.layout,
                        inherited.applicable_attributes,
                        _requested(projection, inherited.applicable_value_objects),
                    ),
                )
            )
    direct_documents = (
        DirectDocumentMappings(tuple(direct))
        if any(members for _identity, members in direct)
        else None
    )
    if document_column is None:
        return None, direct_documents
    padding = (
        tuple(dict.fromkeys(key for *_entry, members in entries for key, _path in members))
        if pad_siblings
        else ()
    )
    per_entity = tuple(
        (identity, DocumentFanOut(None if residents is None else residents.shape, members, padding))
        for identity, residents, members in entries
    )
    return SharedDocumentMapping(document_column, per_entity), direct_documents


def _fetched_residents(
    residents: DocumentResidentSelection | None,
    layout: TableLayout,
    projection: ResolvedReadProjection,
) -> tuple[str | None, _Members]:
    """The Structured Column one concrete's read needs, if any, and the fetched
    residents it fans out of it."""
    if residents is None:
        return None, ()
    members: list[tuple[str, tuple[str, ...]]] = []
    column: str | None = None
    for position, placement in zip(residents.positions, residents.placements, strict=True):
        binding = residents.member_selection.bindings[position]
        if isinstance(binding, AttributeMetadata) or projection.includes_value_object(
            binding.identity
        ):
            column = placement.slot.column.name
            members.append((binding.storage.name, placement.path))
    if column is None and projection.observe_structured_document:
        slot = _structured_column_slot(layout)
        column = None if slot is None else slot.column.name
    return column, tuple(members)


def _direct_members(
    layout: TableLayout,
    attributes: Sequence[AttributeMetadata],
    occurrences: Sequence[ValueObjectMetadata],
) -> tuple[AttributeMetadata | ValueObjectMetadata, ...]:
    """The scalar collections and occurrences ``layout`` stores in a Column of
    their own, of the ones one concrete's rows carry."""
    return (
        *(
            attribute
            for attribute in attributes
            if attribute.multiplicity is Multiplicity.MANY
            and isinstance(layout.placement(attribute.identity), DirectColumn)
        ),
        *(
            occurrence
            for occurrence in occurrences
            if isinstance(layout.placement(occurrence.identity), DirectColumn)
        ),
    )


def select_projection(
    slots: Sequence[ColumnSlot],
    attributes: Sequence[AttributeMetadata],
    value_objects: Sequence[ValueObjectMetadata],
    *,
    project_discriminator: bool,
) -> tuple[ProjectedColumn, ...]:
    """The m-sql projection order for a single-Table read, taken from ``slots``.

    ``slots`` is already the canonical `Identity`, `Discriminator`, `Domain`,
    `Temporal`, `Audit`, `Document` tier sequence restricted to the read's
    position, so this selects rather than orders: a contributor absent from
    ``attributes`` / ``value_objects`` is not projected, which is how a read
    requesting no Value Object omits their `Document` slots. The discriminator
    is projected iff the read's own queried `target` is abstract, independently
    of what the position resolved to, and keeps its own tier position rather
    than trailing the scalars.
    """
    types: dict[object, tuple[NeutralType | None, bool]] = {
        attribute.identity: (
            (None, True) if attribute.multiplicity is Multiplicity.MANY else (attribute.type, False)
        )
        for attribute in attributes
    }
    types.update({member.identity: (None, True) for member in value_objects})
    selected: list[ProjectedColumn] = []
    for slot in slots:
        if isinstance(slot.contributor, InheritanceDiscriminator):
            if project_discriminator:
                selected.append(ProjectedColumn(slot.contributor, slot.column.name, None))
            continue
        if slot.contributor not in types:
            continue
        neutral_type, document = types[slot.contributor]
        selected.append(
            ProjectedColumn(slot.contributor, slot.column.name, neutral_type, document=document)
        )
    return tuple(selected)


@dataclass(frozen=True, slots=True)
class SingleTableReadPlan:
    """A read of one Table: a standalone Entity, a table-per-hierarchy position,
    or a table-per-concrete-subtype position resolving to exactly one concrete
    (m-sql "Inheritance — table-per-hierarchy lowering" and "… —
    table-per-concrete-subtype lowering").

    A standalone Entity is the one-concrete position of itself. Only a
    table-per-hierarchy read carries a :attr:`tag_guard`, keyed purely to the
    resolved position's SIZE — one concrete lowers to `=` whether reached by a
    directly concrete `target` or by result narrowing, several lower to `in`,
    and only an untouched abstract-**root** `target` (no `narrowTo` at all)
    carries none. Whether the discriminator slot appears in :attr:`columns` is
    instead keyed to whether the queried table-per-hierarchy `target` itself is
    abstract — independent of the narrow's resolved cardinality
    (`m-inheritance-012`: `Animal` narrowed to the single concrete `Dog` still
    projects `t0.kind` and still carries `familyVariant`, because the caller
    queried the polymorphic `Animal` position). These are deliberately two
    different conditions: a bare abstract root projects the tag it does not
    guard on, and a concrete target guards on the tag it does not project.

    A one-concrete table-per-concrete-subtype read keeps the queried `target` as
    its resolution scope's Entity, so an abstract position narrowed to it still
    resolves Attributes across the family's superset.
    """

    table: str
    position: InheritancePositionView
    layout: PositionLayoutView
    columns: tuple[ProjectedColumn, ...]
    tag_guard: TagPredicate | None
    row_identity: RowIdentity
    shared_document: SharedDocumentMapping | None
    direct_documents: DirectDocumentMappings | None

    @property
    def concrete_types(self) -> Sequence[EntityIdentity]:
        return self.position.concrete_subtypes


@dataclass(frozen=True, slots=True)
class TpcsUnionBranchColumn:
    """One Position Layout contributor as one `union all` branch renders it.

    ``owned`` is that branch's slot presence taken from the Position Layout's own
    slot-or-absence mapping; an unowned contributor renders the typed `NULL`
    placeholder under the same allocated ``result_alias`` its owning branches use.
    """

    contributor: AttributeIdentity | ValueObjectIdentity | RelationalDocument
    column: str
    type: NeutralType | None
    max_length: int | None
    owned: bool
    result_alias: str
    document: bool = False


@dataclass(frozen=True, slots=True)
class TpcsUnionBranchPlan:
    """One `union all` branch: its own table, and the Position Layout's one
    logical contributor sequence paired with this branch's slot presence."""

    identity: EntityIdentity
    variant: str
    table: str
    columns: tuple[TpcsUnionBranchColumn, ...]


@dataclass(frozen=True, slots=True)
class TpcsUnionColumn:
    """One union RESULT column: the contributor it carries and the result alias
    every branch projects it under.

    A branch column is what one branch selects; this is what the union yields, so
    it is what an outer select over the union alias — and therefore an ordering
    key measured against it — can name.
    """

    contributor: AttributeIdentity | ValueObjectIdentity | RelationalDocument
    result_alias: str
    document: bool


@dataclass(frozen=True, slots=True)
class TpcsUnionReadPlan:
    """A position resolving to two or more concretes: canonical `union all`, one
    branch per concrete in canonical order, every branch restarting its own
    alias at `t0` and projecting the same stable superset with `cast(null as
    <type>)` placeholders for columns it does not own, plus its own
    `familyVariant` subtype-name literal.

    The read's predicate is the SAME for every branch — each branch lowers it
    against its own fresh context, which is what restarts the aliases and keeps
    the per-branch binds separable for concatenation in branch order.

    ``columns`` is the union's own result sequence, aligned with every branch's
    :attr:`TpcsUnionBranchPlan.columns`. A `union all` has no clause tail of its own,
    so an ordered or limited read wraps it as a derived table and applies the
    tail against the union's own result aliases — the only place a Position
    Layout contributor is reachable by the one name all branches agree on.
    """

    branches: tuple[TpcsUnionBranchPlan, ...]
    position: InheritancePositionView
    layout: PositionLayoutView
    columns: tuple[TpcsUnionColumn, ...]
    row_identity: RowIdentity
    shared_document: SharedDocumentMapping | None
    direct_documents: DirectDocumentMappings | None

    @property
    def concrete_types(self) -> Sequence[EntityIdentity]:
        return self.position.concrete_subtypes

    def column_of(self, contributor: ColumnContributor) -> TpcsUnionColumn:
        """``contributor``'s union result column.

        A member the layout placed inside a Structured Column makes no Column
        claim of its own, so it is reached through the contributor of the slot
        that carries it rather than through its own identity — which is what
        makes this total for every member the position can order by, the
        positional rule (`m-object-query`) having already excluded the rest.
        """
        for column in self.columns:
            if column.contributor == contributor:
                return column
        raise SqlGenError(  # pragma: no cover - a validated Sort Key names a projected member
            f"{contributor} has no Column in the table-per-concrete-subtype union"
        )


@dataclass(frozen=True, slots=True)
class BranchNarrowPlan:
    """A `narrow` reached MID-predicate (nested inside and/or/not/group) — a
    **grouped branch predicate** (m-sql "Grouped branch predicates"). Carries the
    resolved effective position and the inputs its tag guard needs; the caller
    lowers the resolved operand FIRST, then guards.
    """

    position: tuple[EntityIdentity, ...]
    tag: TagPredicate | None


def plan_read_shape(
    query: PlannedEntityQuery,
    facet: InheritanceFacet,
    storage: StorageLayoutFacet,
    instance_form: bool,
    lock: LockMode | None,
) -> SingleTableReadPlan | TpcsUnionReadPlan:
    """Plan the physical read of ``query``'s position, whatever its Entity's
    inheritance shape.

    The read covers ``query.position``, fetches exactly ``query.projection``'s
    Value Objects, and observes the Structured Column exactly where it asks. A
    standalone Entity, a table-per-hierarchy position, and a
    table-per-concrete-subtype position resolving to one concrete read one
    Table; only a table-per-concrete-subtype position resolving to several reads
    their `union all`. The storage owner's Position Layout is asked for once, and
    both document planning and column selection read that one answer.

    ``instance_form`` is the object lane (`result_form == "instance"`), which
    decides only sibling padding and which branch-owned fields a row publishes.
    ``lock`` is here rather than at the rendering site because the union lane must
    REFUSE a genuinely requested shared row lock before any branch is rendered;
    ordering and the cap are the renderer's, since a union applies them to its
    own outer select rather than to any branch.
    """
    entity = query.entity
    view = entity_view(facet, entity.identity)
    position = query.position
    layout = position_layout(storage, position.concrete_subtypes)
    if isinstance(view.strategy, TablePerConcreteSubtype) and len(position.concrete_subtypes) != 1:
        return _plan_tpcs_union_read(
            position, layout, facet, storage, query.projection, lock, instance_form=instance_form
        )
    return _plan_single_table_read(
        entity,
        view,
        position,
        layout,
        facet,
        storage,
        query.projection,
        narrowed=query.narrow_to is not None,
        instance_form=instance_form,
    )


def _requested(
    projection: ResolvedReadProjection, candidates: Sequence[ValueObjectMetadata]
) -> tuple[ValueObjectMetadata, ...]:
    return tuple(
        member for member in candidates if projection.includes_value_object(member.identity)
    )


def _plan_single_table_read(
    entity: EntityMetadata,
    view: InheritanceEntityView,
    position: InheritancePositionView,
    layout: PositionLayoutView,
    facet: InheritanceFacet,
    storage: StorageLayoutFacet,
    projection: ResolvedReadProjection,
    *,
    narrowed: bool,
    instance_form: bool,
) -> SingleTableReadPlan:
    concretes = tuple(position.concrete_subtypes)
    tph = isinstance(view.strategy, TablePerHierarchy)
    # A table-per-hierarchy position reads the root's shared Table; any other
    # single-table position reads its one concrete's own.
    table = _table_layout(storage, facet, entity.identity if tph else concretes[0])
    abstract_target = tph and isinstance(entity.inheritance, (AbstractRoot, AbstractSubtype))
    # Padding is the abstract-target row-form lane's alone: a read that publishes
    # flat rows renders every branch's document members, so a row carries its
    # siblings' keys as null.
    shared, direct = plan_document_reads(
        layout, facet, storage, projection, pad_siblings=abstract_target and not instance_form
    )
    columns = select_projection(
        position_slots(table, concretes),
        position.superset_attributes,
        projection.value_objects,
        project_discriminator=abstract_target,
    )
    if shared is not None:
        document_slot = _structured_column_slot(table)
        if document_slot is None:  # pragma: no cover - a mapped document is a layout's own
            raise SqlGenError(f"{table.table.name}: a shared document needs a Structured Column")
        columns = (
            *columns,
            ProjectedColumn(document_slot.contributor, shared.column, None, document=True),
        )
    tag_guard: TagPredicate | None = None
    # A single-table read with no tag to read names the one concrete its
    # position resolved to: a standalone Entity, a concrete target, or a
    # table-per-concrete-subtype position however it was narrowed.
    row_identity: RowIdentity = FixedRowIdentity(concretes[0])
    if tph:
        tag_col = tag_column(table, view.root)
        # Only an UNTOUCHED abstract root queries the whole family, so only it
        # carries no tag predicate at all.
        if narrowed or not isinstance(entity.inheritance, AbstractRoot):
            tag_guard = TagPredicate(tag_col, concretes)
        # `familyVariant` rides the SAME condition as the discriminator
        # projection: a tag identity reads the column this read projects. A
        # heterogeneous shared document is keyed by the concretes whose shapes
        # it holds, so the two agree on one pairing.
        if abstract_target:
            row_identity = TaggedRowIdentity(
                tag_col,
                view.root,
                tag_pairs(facet, concretes)
                if shared is not None
                else family_tag_pairs(facet, view.root),
            )
    return SingleTableReadPlan(
        table=table.table.name,
        position=position,
        layout=layout,
        columns=columns,
        tag_guard=tag_guard,
        row_identity=row_identity,
        shared_document=shared,
        direct_documents=direct,
    )


def _projects_document_slot(
    contributor: ColumnContributor,
    projection: ResolvedReadProjection,
    *,
    shared_document: bool,
) -> bool:
    """Whether a `union all` branch projects ``contributor``'s `Document` slot.

    A scalar collection's own Structured Column holds an Attribute, which every
    read projects. A top-level Value Object occurrence owns a Structured Column
    of its own under `Columns` layout, projected exactly where the read fetches
    that occurrence (`m-sql` *Read projection* rule 3). A Relational Document
    Layout's shared Structured Column answers rule 5 exactly where document
    planning mapped one, which ``shared_document`` is.
    """
    if isinstance(contributor, AttributeIdentity):
        return True
    if isinstance(contributor, ValueObjectIdentity):
        return projection.includes_value_object(contributor)
    return isinstance(contributor, RelationalDocument) and shared_document


def _plan_tpcs_union_read(
    position: InheritancePositionView,
    layout: PositionLayoutView,
    facet: InheritanceFacet,
    storage: StorageLayoutFacet,
    projection: ResolvedReadProjection,
    lock: LockMode | None,
    *,
    instance_form: bool,
) -> TpcsUnionReadPlan:
    """Table-per-concrete-subtype over several concretes (m-sql "Inheritance —
    table-per-concrete-subtype lowering"). Unlike table-per-hierarchy, the
    single-vs-several split is the ONLY thing that decides `familyVariant` here —
    there is no table-per-concrete-subtype analogue of the abstract-`target`
    slot-2 rule, because a resolved single concrete has no shared table to
    discriminate and no sibling branch to distinguish it from (m-sql, explicit).

    Every branch table is that branch's OWN concrete's container. The position's
    own container is a different fact — the single container a read or write of
    the position itself targets (absent for an abstract table-per-concrete-subtype
    position) — and is deliberately never reached for here: only an abstract
    position resolves to several concretes, and it has no container of its own to
    reach for.
    """
    if lock == "locking":
        # A shared row lock is the one clause a derived-table wrap cannot rescue:
        # PostgreSQL forbids a locking clause over a `UNION` result and over every
        # input of one, and dropping it silently would leave a later ungated write
        # unlicensed. Ordering and limiting have an outer select to land on, so
        # only a GENUINELY requested lock refuses — matching the append site's own
        # `== "locking"` test, which is why a participating read carrying the
        # `optimistic` Effective Concurrency Strategy passes here.
        raise SqlGenError(
            "a read-lock suffix over a table-per-concrete-subtype union-all read "
            "(2+ effective concretes) has no goldened lowering yet"
        )
    # A branch storing no document of its own still pads its siblings' document
    # members, and reads the shared column the union aliased for all of them.
    shared, direct = plan_document_reads(
        layout, facet, storage, projection, pad_siblings=not instance_form
    )
    scalars = tuple(
        index
        for index, column in enumerate(layout.columns)
        if column.tier is not ColumnTier.DOCUMENT
        or _projects_document_slot(
            column.contributor, projection, shared_document=shared is not None
        )
    )
    # A scalar collection's Column holds a document, never its element type's
    # native scalar lane, so it projects and keys as a document.
    by_identity: dict[AttributeIdentity | ValueObjectIdentity, AttributeMetadata] = {
        attribute.identity: attribute
        for attribute in position.superset_attributes
        if attribute.multiplicity is Multiplicity.ONE
    }
    attributes = tuple(
        by_identity.get(contributor)
        if isinstance(contributor, (AttributeIdentity, ValueObjectIdentity))
        else None
        for index in scalars
        for contributor in (layout.columns[index].contributor,)
    )
    spellings = tuple(_contributor_column(layout.branches, index) for index in scalars)
    result_aliases = _result_aliases(spellings)
    union_columns = tuple(
        TpcsUnionColumn(
            contributor=layout.columns[index].contributor,
            result_alias=result_alias,
            document=layout.columns[index].tier is ColumnTier.DOCUMENT,
        )
        for index, result_alias in zip(scalars, result_aliases, strict=True)
    )
    branches = tuple(
        TpcsUnionBranchPlan(
            identity=branch.concrete_entities[0],
            variant=family_variant_name(facet, branch.concrete_entities[0]),
            table=branch.layout.table.name,
            columns=tuple(
                TpcsUnionBranchColumn(
                    contributor=union_column.contributor,
                    column=spelling,
                    type=None if attribute is None else attribute.type,
                    max_length=None if attribute is None else attribute.max_length,
                    owned=branch.slots[index] is not None,
                    result_alias=result_alias,
                    document=layout.columns[index].tier is ColumnTier.DOCUMENT,
                )
                for index, attribute, spelling, result_alias, union_column in zip(
                    scalars, attributes, spellings, result_aliases, union_columns, strict=True
                )
            ),
        )
        for branch in layout.branches
    )
    # Every branch projects its own `family_variant` literal, so resolution is
    # a plain rename — no tag map, no metamodel lookup.
    literal = LiteralRowIdentity(
        "family_variant",
        tuple((branch.variant, branch.identity) for branch in branches),
        instance_form,
    )
    return TpcsUnionReadPlan(
        branches=branches,
        position=position,
        layout=layout,
        columns=union_columns,
        row_identity=literal,
        shared_document=shared,
        direct_documents=direct,
    )


def position_layout(
    storage: StorageLayoutFacet, concretes: Sequence[EntityIdentity]
) -> PositionLayoutView:
    """``concretes``' one logical contributor sequence and per-Table branch map."""
    view = storage.position(tuple(concretes))
    if view is None:  # pragma: no cover - a validated position is one canonical family
        raise SqlGenError(
            f"position {sorted(identity.canonical for identity in concretes)} "
            "has no Position Layout"
        )
    return view


def _contributor_column(branches: Sequence[PositionBranch], index: int) -> str:
    """One logical contributor's physical Column spelling across ``branches``.

    An inherited contributor occupies one Column occurrence per concrete Table
    and every occurrence carries the declaration's own spelling, so the first
    branch that owns the slot fixes the result-alias candidate for all of them.
    """
    for branch in branches:
        slot = branch.slots[index]
        if slot is not None:
            return slot.column.name
    raise SqlGenError(  # pragma: no cover - a Position Layout contributor is owned somewhere
        "a table-per-concrete-subtype position contributor occupies no branch Column"
    )


def _result_aliases(spellings: Sequence[str]) -> tuple[str, ...]:
    """Hygienic result aliases for one union's logical contributor sequence.

    A contributor keeps its own physical spelling only when that spelling occurs
    once across the position and is not the synthetic `family_variant` carrier;
    every other contributor takes the first `parallax_attr_N` outside the
    complete reservation set, so an authored `parallax_attr_0` stays reserved.
    """
    counts: dict[str, int] = {}
    for spelling in spellings:
        counts[spelling] = counts.get(spelling, 0) + 1
    allocated = set(spellings) | {"family_variant"}
    next_internal = 0
    aliases: list[str] = []
    for spelling in spellings:
        if counts[spelling] == 1 and spelling != "family_variant":
            aliases.append(spelling)
            continue
        while f"parallax_attr_{next_internal}" in allocated:
            next_internal += 1
        internal = f"parallax_attr_{next_internal}"
        allocated.add(internal)
        aliases.append(internal)
        next_internal += 1
    return tuple(aliases)


def plan_resolved_branch_narrow(
    facet: InheritanceFacet,
    storage: StorageLayoutFacet,
    entity: EntityMetadata,
    position: tuple[EntityIdentity, ...],
) -> BranchNarrowPlan:
    """Plan a mid-predicate narrow from its resolved effective position."""
    view = entity_view(facet, entity.identity)
    if not isinstance(view.strategy, TablePerHierarchy):
        return BranchNarrowPlan(position, None)
    layout = _table_layout(storage, facet, entity.identity)
    return BranchNarrowPlan(position, TagPredicate(tag_column(layout, view.root), position))
