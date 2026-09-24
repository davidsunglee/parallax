from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol

from parallax.core.inheritance import EntityMemberSelection, family_variant_name
from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    MemberIdentity,
    Metamodel,
    Multiplicity,
    PrimaryKey,
    RelationshipIdentity,
    TablePerConcreteSubtype,
    ValueObjectMetadata,
)
from parallax.core.relationship import RelationshipMetadata
from parallax.core.relationship import view as relationship_view

__all__ = [
    "CatalogedModel",
    "EntityLayout",
    "LayoutCatalog",
    "NarrowableView",
]


class NarrowableView(Protocol):
    """One relationship view to place in canonical order.

    Structural rather than nominal because the view key itself belongs to the
    materializing runtime above this scope: a layout orders views without
    naming the type that spells one.
    """

    @property
    def relationship(self) -> RelationshipIdentity: ...
    @property
    def narrowed_view(self) -> str | None: ...


@dataclass(frozen=True, slots=True)
class EntityLayout:
    """Member rows contain ancestry-ordered Attributes, then Value Objects.

    ``primary_key`` indexes that row in declared key order. ``family`` is the
    family root except for table-per-concrete-subtype, whose concrete classes
    have independent key namespaces. Relationship positions use whole identities
    and ancestry-first declaration order. ``family_variant`` is qualified only
    when concrete local names collide; standalone Entities have none.
    """

    concrete: EntityIdentity
    family: EntityIdentity
    member_selection: EntityMemberSelection
    temporal_ends: frozenset[AttributeIdentity]
    relationships: tuple[RelationshipIdentity, ...]
    relationship_index: Mapping[RelationshipIdentity, int]
    to_many: frozenset[RelationshipIdentity]
    primary_key: tuple[int, ...]
    temporal_starts: tuple[int, ...] = ()
    family_variant: str | None = None

    @property
    def members(self) -> Sequence[MemberIdentity]:
        return self.member_selection.identities

    @property
    def attribute_count(self) -> int:
        return self.member_selection.attribute_count

    @property
    def index_of(self) -> Mapping[MemberIdentity, int]:
        return self.member_selection.index

    @property
    def attributes(self) -> Sequence[AttributeMetadata]:
        return self.member_selection.attributes

    @property
    def occurrences(self) -> Sequence[ValueObjectMetadata]:
        return self.member_selection.value_objects

    @property
    def value_objects(self) -> Sequence[ValueObjectMetadata]:
        return self.member_selection.value_objects

    def key_of(self, row: tuple[object, ...]) -> object:
        """``row``'s logical key: the raw scalar for a single-column primary key,
        a tuple of them in declared order for a composite one.

        The whole-graph pin the identity triple also names is deliberately
        omitted, because every row of one materialization stands at the same pin
        and so it can distinguish nothing.
        """
        if len(self.primary_key) == 1:
            return row[self.primary_key[0]]
        return tuple(row[position] for position in self.primary_key)

    def ordered[V: NarrowableView](self, views: Iterable[V]) -> tuple[V, ...]:
        """``views`` in canonical slot order: each relationship's own declaration
        position with a direction this concrete does not navigate last, the
        broad view before that relationship's narrowed ones, and narrowed views
        by their derived key."""
        return tuple(sorted(views, key=self._rank))

    def _rank(self, view: NarrowableView) -> tuple[int, int, str]:
        position = self.relationship_index.get(view.relationship, len(self.relationship_index))
        return position, int(view.narrowed_view is not None), view.narrowed_view or ""


class LayoutCatalog:
    """One accepted Metamodel's exact-Entity layouts, every one derived at
    construction.

    Constructing a catalog lays out every Entity the model declares, so the
    constructor is the one fallible point: a model whose accepted metadata
    fixes no row for some Entity refuses the whole catalog rather than
    surfacing at the first read that happens to address that Entity. After
    construction every entry is immutable and shared, so a lookup allocates
    nothing and can fail only by naming an Entity this model does not declare.

    Every entry is a pure function of the accepted immutable metadata, so two
    catalogs over one model are interchangeable and nothing compares a layout
    by identity.
    """

    __slots__ = ("_layouts", "_model")

    def __init__(self, model: Metamodel) -> None:
        """Derive every Entity's layout, or raise.

        Raises :class:`ValueError` when the accepted metadata cannot fix one row
        for some Entity — two members claiming one position, or a family
        primary key the row does not express.
        """
        self._model = model
        self._layouts: Mapping[EntityIdentity, EntityLayout] = MappingProxyType(
            {entity.identity: self._build(entity.identity) for entity in model.entities}
        )

    def entity(self, identity: EntityIdentity) -> EntityLayout:
        """``identity``'s layout.

        Raises :class:`ValueError` when this model declares no such Entity.
        """
        layout = self._layouts.get(identity)
        if layout is None:
            raise ValueError(
                f"this model declares no Entity {identity.canonical!r}, "
                "so it lays out no row for one"
            )
        return layout

    def _build(self, identity: EntityIdentity) -> EntityLayout:
        facet = inheritance_view(self._model)
        position = facet.entity(identity)
        if (
            position is None
        ):  # pragma: no cover - an accepted model positions every Entity it declares
            raise ValueError(
                f"this model declares no Entity {identity.canonical!r}, "
                "so it lays out no row for one"
            )
        selection = position.member_selection
        index_of = selection.index
        navigable = _navigable_relationships(self._model, position.ancestry)
        relationships = tuple(direction.identity for direction in navigable)
        return EntityLayout(
            concrete=identity,
            family=(
                identity
                if isinstance(position.strategy, TablePerConcreteSubtype)
                else position.root
            ),
            member_selection=selection,
            temporal_ends=self._temporal_ends(position.root),
            relationships=relationships,
            relationship_index=MappingProxyType(
                {direction: position for position, direction in enumerate(relationships)}
            ),
            to_many=frozenset(
                direction.identity
                for direction in navigable
                if direction.cardinality.target is Multiplicity.MANY
            ),
            primary_key=self._key_positions(identity, position.root, index_of),
            temporal_starts=self._temporal_start_positions(position.root, index_of),
            family_variant=(
                None if position.strategy is None else family_variant_name(facet, identity)
            ),
        )

    def _temporal_ends(self, root: EntityIdentity) -> frozenset[AttributeIdentity]:
        """The family's interval-closing Attributes, under the identities a
        concrete descendant reaches them by."""
        declaring = self._model.entity(root)
        if declaring is None:  # pragma: no cover - an accepted model declares every family root
            return frozenset()
        return frozenset(axis.end_attribute for axis in declaring.declared_as_of_axes)

    def _temporal_start_positions(
        self, root: EntityIdentity, index_of: Mapping[MemberIdentity, int]
    ) -> tuple[int, ...]:
        """The family's axis starts in canonical rank, as row positions."""
        declaring = self._model.entity(root)
        if declaring is None:  # pragma: no cover - an accepted model declares every family root
            return ()
        return tuple(
            index_of[axis.start_attribute]
            for axis in sorted(declaring.declared_as_of_axes, key=lambda axis: axis.dimension.value)
        )

    def _key_positions(
        self,
        identity: EntityIdentity,
        root: EntityIdentity,
        index_of: Mapping[MemberIdentity, int],
    ) -> tuple[int, ...]:
        """Where the family's primary key sits in this concrete's member row.

        The family root owns the key even when a descendant is what a row
        resolved to, so the positions are the root's declared primary-key
        Attributes located in the concrete's own family-effective row. A family
        declaring no key, and one whose key does not locate there in full, are
        both model defects: no row of such an Entity could carry a graph-local
        identity at all.
        """
        declaring = self._model.entity(root)
        if declaring is None:  # pragma: no cover - an accepted model declares every family root
            raise ValueError(
                f"{identity.canonical} names a family root {root.canonical} this model "
                "does not declare"
            )
        key = tuple(
            attribute.identity
            for attribute in declaring.declared_attributes
            if isinstance(attribute.primary_key, PrimaryKey)
        )
        positions = tuple(index_of[name] for name in key if name in index_of)
        if not key or len(positions) != len(key):
            raise ValueError(
                f"{identity.canonical} carries no position for the primary key its family "
                f"{root.canonical} declares, so no row of it names a logical node"
            )
        return positions


@dataclass(frozen=True, slots=True)
class CatalogedModel:
    """One accepted Metamodel and the layouts derived from it, as one value.

    A layout is a function of the model it came from, so a catalog beside a
    Metamodel that did not produce it names a state nothing downstream could
    detect. The record derives its own catalog from the one Metamodel it is
    constructed over, so that state is unrepresentable rather than merely
    checked: there is no second half for a caller to supply, no seam can thread
    the two apart and rejoin them wrongly, and a consumer reads its member
    layouts from the same value it reads its accepted metadata from.

    Constructing one therefore derives the whole catalog, and is the complete,
    fallible layout derivation for a model: it raises where the metadata fixes
    no row for some Entity, and a record that exists lays out every Entity. A
    runtime that must share one model's layouts holds one record rather than
    forming a second beside it.

    ``layouts`` stays out of comparison: it is a function of ``meta``, so it
    distinguishes no two records that ``meta`` does not, while comparing it
    would compare a catalog by identity — which nothing may do — and so make
    two records over one model unequal for having each derived an
    interchangeable catalog. A record is therefore the model it carries.
    """

    meta: Metamodel
    layouts: LayoutCatalog = field(init=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "layouts", LayoutCatalog(self.meta))


def _navigable_relationships(
    model: Metamodel, ancestry: Sequence[EntityIdentity]
) -> tuple[RelationshipMetadata, ...]:
    """Every navigable direction in accepted declaration order, ancestry first.

    A relationship declared on an inheritance ancestor is reached by every
    concrete descendant under the ancestor's own identity and is never
    redeclared, so the navigable set is the ancestry chain's directions with each
    name taken from the nearest declaration.

    The whole declaration rather than the identity alone, so a caller needing a
    further fact of a direction takes it from the walk that placed the direction
    rather than by looking that direction up again.
    """
    facet = relationship_view(model)
    order: dict[str, RelationshipMetadata] = {}
    for ancestor in ancestry:
        for direction in facet.relationships(ancestor) or ():
            order.setdefault(direction.identity.name, direction)
    return tuple(order.values())
