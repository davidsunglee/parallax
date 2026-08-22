"""Exact-model member layouts: the positional facts one Entity's rows share.

A layout is the flyweight a materializing runtime reads instead of rebuilding a
wrapper skeleton per row. Which members a resolved concrete Entity carries, in
what order, where its category boundary falls, which positions its family's
primary key occupies, and what canonical order its relationship views take are
all functions of the accepted Metamodel alone — so a catalog derives them per
exact Entity, and every row, every graph, and every execution it serves shares
what it derived rather than rebuilding one.

Stated over the accepted :class:`~parallax.core.metamodel.Metamodel` rather than
over the :class:`~parallax.core.entity.DomainModel` that carries one, because
that is the whole of what a layout depends on: a model composing no Entity Class
lays out its rows exactly as one composing every class does.

Two things are deliberately absent. **Storage and result-key names stay out** —
those come from a compiled read's own projection contracts, so a layout stays
query-independent and shareable across every execution. And **row width is
model-fixed, not query-fixed**: a member a read did not project still occupies
its declared position, which is what keeps one layout per exact Entity rather
than one per query shape.

Two rules live here rather than at the callers that would otherwise restate
them: :meth:`EntityLayout.key_of` owns the single-versus-composite spelling of a
logical key, and :meth:`EntityLayout.ordered` owns the canonical view order.
Positions stay public because the hot paths iterate members in order; it is the
rules that are hidden, not the indexing.

A model defect found while deriving a layout is a raised :class:`ValueError`,
never a stored-data classification: a row cannot contradict a position that the
model itself failed to fix.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol

from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    MemberIdentity,
    Metamodel,
    Multiplicity,
    NestedValueObjectMetadata,
    PrimaryKey,
    RelationshipIdentity,
    TablePerConcreteSubtype,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
    ValueObjectMetadata,
)
from parallax.core.relationship import view as relationship_view

__all__ = [
    "CatalogedModel",
    "EntityLayout",
    "LayoutCatalog",
    "NarrowableView",
    "ValueObjectLayout",
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
class ValueObjectLayout:
    """One exact, path-specific Value Object occurrence's declaration-order tuple.

    ``members`` is that occurrence's own leaves followed by its nested
    occurrences, each under the identity it declares. ``nested`` is aligned to
    it and pre-linked — a nested occurrence's own layout is already resolved, so
    descending one is a pointer walk rather than a lookup — and holds ``None``
    exactly at a leaf position.
    """

    identity: ValueObjectIdentity
    multiplicity: Multiplicity
    members: tuple[ValueObjectAttributeIdentity | ValueObjectIdentity, ...]
    index_of: Mapping[ValueObjectAttributeIdentity | ValueObjectIdentity, int]
    nested: tuple[ValueObjectLayout | None, ...]


@dataclass(frozen=True, slots=True)
class EntityLayout:
    """One exact concrete Entity's positional member facts.

    ``members`` is the family-effective member row: every applicable Attribute
    in ancestry-then-declaration order, then every applicable top-level Value
    Object occurrence in theirs, with ``attribute_count`` the boundary between
    the two categories. ``attributes``, ``occurrences``, and ``value_objects``
    are aligned to those two runs, so a caller iterating a row reads its
    metadata by position rather than by search.

    ``family`` is the identity a logical key normalizes to: the family root,
    except under ``TablePerConcreteSubtype``, where each concrete owns an
    independent primary-key namespace and normalizing would conflate two
    different rows that merely share a key value.
    """

    concrete: EntityIdentity
    family: EntityIdentity
    members: tuple[MemberIdentity, ...]
    attribute_count: int
    index_of: Mapping[MemberIdentity, int]
    attributes: tuple[AttributeMetadata, ...]
    occurrences: tuple[ValueObjectMetadata, ...]
    value_objects: tuple[ValueObjectLayout, ...]
    _primary_key: tuple[int, ...]
    _relationship_order: Mapping[str, int]

    def key_of(self, row: tuple[object, ...]) -> object:
        """``row``'s logical key: the raw scalar for a single-column primary key,
        a tuple of them in declared order for a composite one.

        The whole-graph pin the identity triple also names is deliberately
        omitted, because every row of one materialization stands at the same pin
        and so it can distinguish nothing.
        """
        if len(self._primary_key) == 1:
            return row[self._primary_key[0]]
        return tuple(row[position] for position in self._primary_key)

    def ordered[V: NarrowableView](self, views: Iterable[V]) -> tuple[V, ...]:
        """``views`` in canonical slot order: each relationship's own declaration
        position with an undeclared one last, the broad view before that
        relationship's narrowed ones, and narrowed views by their derived key."""
        return tuple(sorted(views, key=self._rank))

    def _rank(self, view: NarrowableView) -> tuple[int, int, str]:
        position = self._relationship_order.get(
            view.relationship.name, len(self._relationship_order)
        )
        return position, int(view.narrowed_view is not None), view.narrowed_view or ""


class LayoutCatalog:
    """One accepted Metamodel's exact-Entity layouts.

    Entries are derived on first reach rather than eagerly over the whole model,
    so a short-lived process pays only for the Entities it addresses; the shape
    matches the per-Entity caches the graph-construction and row-derivation
    collaborations already keep.

    Reaching an entry is an unsynchronized check-then-set, like the door that
    hands out the catalog itself: concurrent first reaches of one Entity each
    derive a layout and each are answered their own, and whichever landed last
    is what every later reach is answered. That is why the entry count is a
    bound on what a catalog retains rather than a count of the derivations it
    ran. It costs nothing, because every entry is a pure function of the
    accepted immutable metadata, so two catalogs over one model — or two layouts
    for one Entity — are interchangeable, and nothing compares a layout by
    identity.
    """

    __slots__ = ("_cache", "_model")

    def __init__(self, model: Metamodel) -> None:
        self._model = model
        self._cache: dict[EntityIdentity, EntityLayout] = {}

    def entity(self, identity: EntityIdentity) -> EntityLayout:
        """``identity``'s layout, derived on its first reach here and answered
        from the entry that reach retained thereafter.

        Raises :class:`ValueError` when this model declares no such Entity, or
        when its accepted metadata cannot fix one row for it — two members
        claiming one position, or a family primary key the row does not express.
        """
        cached = self._cache.get(identity)
        if cached is not None:
            return cached
        built = self._build(identity)
        self._cache[identity] = built
        return built

    def _build(self, identity: EntityIdentity) -> EntityLayout:
        position = inheritance_view(self._model).entity(identity)
        if position is None:
            raise ValueError(
                f"this model declares no Entity {identity.canonical!r}, "
                "so it lays out no row for one"
            )
        attributes = tuple(position.applicable_attributes)
        occurrences = tuple(position.applicable_value_objects)
        members: tuple[MemberIdentity, ...] = (
            *(attribute.identity for attribute in attributes),
            *(occurrence.identity for occurrence in occurrences),
        )
        index_of: Mapping[MemberIdentity, int] = _positions(members, identity.canonical)
        return EntityLayout(
            concrete=identity,
            family=(
                identity
                if isinstance(position.strategy, TablePerConcreteSubtype)
                else position.root
            ),
            members=members,
            attribute_count=len(attributes),
            index_of=index_of,
            attributes=attributes,
            occurrences=occurrences,
            value_objects=tuple(_occurrence_layout(occurrence) for occurrence in occurrences),
            _primary_key=self._key_positions(identity, position.root, index_of),
            _relationship_order=_relationship_order(self._model, position.ancestry),
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

    Constructing one therefore derives a catalog. A runtime that must share one
    model's layouts holds the record that model retains rather than forming a
    second beside it.

    ``layouts`` stays out of comparison: it is a function of ``meta``, so it
    distinguishes no two records that ``meta`` does not, while comparing it
    would compare a catalog by identity — which nothing may do — and so make
    two records over one model unequal for having each derived an
    interchangeable catalog. A record is therefore the model it carries, which
    is what lets a holder of one compare equal to a holder of the other after a
    race published both.
    """

    meta: Metamodel
    layouts: LayoutCatalog = field(init=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "layouts", LayoutCatalog(self.meta))


def _occurrence_layout(
    declared: ValueObjectMetadata | NestedValueObjectMetadata,
) -> ValueObjectLayout:
    """``declared``'s whole pre-linked subtree, leaves before nested occurrences."""
    members: tuple[ValueObjectAttributeIdentity | ValueObjectIdentity, ...] = (
        *(leaf.identity for leaf in declared.attributes),
        *(nested.identity for nested in declared.value_objects),
    )
    return ValueObjectLayout(
        identity=declared.identity,
        multiplicity=declared.multiplicity,
        members=members,
        index_of=_positions(members, _spelling(declared.identity)),
        nested=(
            *(None for _ in declared.attributes),
            *(_occurrence_layout(nested) for nested in declared.value_objects),
        ),
    )


def _positions[M](members: tuple[M, ...], holder: str) -> Mapping[M, int]:
    """``members``' identity-to-position index, refusing one position two members
    claim — the accepted metadata would then fix no row at all."""
    index = {member: position for position, member in enumerate(members)}
    if len(index) != len(members):
        raise ValueError(
            f"{holder} declares two members under one identity, "
            "so its accepted metadata fixes no member row"
        )
    return MappingProxyType(index)


def _spelling(identity: ValueObjectIdentity) -> str:
    """One occurrence's canonical containment spelling, for a refusal to name."""
    return ".".join((identity.entity.canonical, *identity.path))


def _relationship_order(model: Metamodel, ancestry: Sequence[EntityIdentity]) -> Mapping[str, int]:
    """Each navigable relationship name's position in accepted declaration order,
    ancestry first.

    A relationship declared on an inheritance ancestor is reached by every
    concrete descendant under the ancestor's own identity and is never
    redeclared, so the navigable set is the ancestry chain's directions with each
    name taken from the nearest declaration.
    """
    facet = relationship_view(model)
    order: dict[str, int] = {}
    for ancestor in ancestry:
        for direction in facet.relationships(ancestor) or ():
            order.setdefault(direction.identity.name, len(order))
    return MappingProxyType(order)
