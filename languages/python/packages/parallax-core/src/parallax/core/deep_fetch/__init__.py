"""Resolved deep-fetch planning (m-deep-fetch).

The planner consumes a :class:`ValidatedObjectQuery` plus a caller-owned
:class:`ReadProjectionRequest`. It injects terms from resolved temporal selections,
canonicalizes validated navigation, resolves the requested projection, and produces
one flat :class:`ValidatedEntityQuery` for the root plus dependency-ordered child
levels. Predicate-write materialization enters through :func:`plan_mutation_read`,
which owns construction of its flat read from a :class:`PreparedPredicateWrite`.

This module compiles and executes nothing. SQL sees only the resolved flat products.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal, NamedTuple, cast

from parallax.core import inheritance, navigate, relationship
from parallax.core.base import ManagedValue
from parallax.core.inheritance import InheritanceEntityView, InheritanceFacet
from parallax.core.metamodel import (
    AttributeIdentity,
    AttributeMetadata,
    Cardinality,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    NullPlacement,
    RelationshipIdentity,
    SortDirection,
    TemporalDimension,
    ValueObjectMetadata,
)
from parallax.core.object_query._validated import (
    ValidatedIncludePath,
    ValidatedIncludeSegment,
    ValidatedObjectQuery,
    ValidatedOrderTerm,
    ValidatedTemporalSelection,
    resolved_order_term,
)
from parallax.core.predicate._validated import (
    ValidatedPredicate,
)
from parallax.core.predicate._validated import (
    conjunction as _validated_conjunction,
)
from parallax.core.predicate._validated import (
    managed_membership as _managed_membership,
)
from parallax.core.relationship import RelationshipMetadata
from parallax.core.temporal_read import (
    inject_resolved_as_of,
    resolved_pinned_instants,
    validated_hop_as_of_terms,
)
from parallax.core.unit_work.instructions import PreparedPredicateWrite

__all__ = [
    "CorrelationMember",
    "DeepFetchError",
    "FetchLevel",
    "LevelRef",
    "ObjectQueryPlan",
    "ParentRef",
    "RootRef",
    "plan",
]


class DeepFetchError(ValueError):
    """A deep-fetch path cannot be planned against the metamodel."""


@dataclass(frozen=True, slots=True)
class ReadProjectionRequest:
    """Snapshot-owned demand that deep fetch resolves against an exact target."""

    value_objects: Literal["none", "all"] | frozenset[str]
    observe_structured_document: bool


@dataclass(frozen=True, slots=True)
class ResolvedReadProjection:
    """The exact resolved Value Object/document demand lowerable by SQL."""

    value_objects: tuple[ValueObjectMetadata, ...]
    observe_structured_document: bool


@dataclass(frozen=True, slots=True)
class RootRef:
    """A level's parent rows are the root query's own rows."""


@dataclass(frozen=True, slots=True)
class LevelRef:
    """A level's parent rows are an earlier level's, named by its plan index."""

    index: int


ParentRef = RootRef | LevelRef


@dataclass(frozen=True, slots=True)
class CorrelationMember:
    """One endpoint of a level's correlation, in every spelling the level needs.

    A level correlates on an Attribute (`m-deep-fetch` "A level names its
    correlation members, not only their columns"), and the three spellings are one
    fact: ``identity`` is the modeled member addressed at the position the join
    names it at, ``column`` is the physical column it maps to, and ``reference``
    is the `m-predicate` ``Class.attribute`` reference string the child query's
    ``in`` membership binds against. Bundling them is what keeps them aligned:
    they are derived together from one join endpoint and are never authored.

    ``reference`` is carried only on the child side, whose reference names the
    level's own ``child_target`` rather than the Entity the identity is declared
    on; the owner side is read off already-converted parent rows and binds
    nothing.
    """

    identity: AttributeIdentity
    column: str
    reference: str | None = None


@dataclass(frozen=True, slots=True)
class ValidatedEntityQuery:
    """One resolved flat read accepted by the private SQL compiler."""

    target: EntityIdentity
    entity: EntityMetadata
    validated_predicate: ValidatedPredicate
    projection: ResolvedReadProjection
    narrow_to: tuple[EntityIdentity, ...] | None = None
    order_by: tuple[ValidatedOrderTerm, ...] = ()
    limit: int | None = None


@dataclass(frozen=True, slots=True)
class FetchLevel:
    """One deep-fetch level: an attach point, plus how to build its child query.

    ``attach_key`` is the relationship name, or — for a narrowed polymorphic hop
    (``m-deep-fetch`` "Polymorphic and narrowed deep fetch") — the derived
    narrowed-view key ``<rel>[<Concrete>,<Concrete>]``; ``relationship`` is the
    same view's own direction as a structured Relationship Identity, so a caller
    attaching this level names the modeled direction rather than re-resolving one
    from the derived key. ``parent`` names which
    already-fetched rows this level gathers its distinct keys from (the root, or
    an earlier level), and ``owner`` is the :class:`CorrelationMember` on those
    parent rows to gather — the relationship join's owner-side endpoint.

    A **queryable** level (``is_back_reference`` false) additionally carries
    ``child_target`` (the entity this level's own read compiles against — a
    single concrete when the resolved position is exactly one, else the
    relationship's own polymorphic target), ``related`` (the child-side
    :class:`CorrelationMember` — what the ``IN`` membership binds against and what
    the assembler groups the returned child rows by, fanning each back to its
    parent), ``as_of_terms`` (the propagated per-axis as-of
    predicate, already resolved), ``order_keys`` (the declared relationship
    ``orderBy``, canonicalized to qualified `OrderKey`s), and ``narrow_to`` (the
    segment's own authored narrow, carried only when the resolved position spans
    2+ concretes — a single-concrete resolution bypasses narrowing entirely by
    targeting that concrete directly, m-sql's existing inheritance-read
    dispatch).

    A **back-reference** level (``is_back_reference`` true) carries none of the
    above — :meth:`query_for` is never called for it; ``back_reference_family``
    names the family the assembler resolves through its identity map instead, as
    that map keys a row on its family ROOT's declared name. Its own ``owner`` is
    still carried: a back-reference level gathers the ancestor's key off the
    parent row exactly as a queried one does, it just resolves that key in memory
    rather than through SQL.

    ``source_position`` is the path-root guard, and the one member of this class that
    qualifies the level's PARENT rows rather than its children: the concrete subtypes
    a guarded path admits, so the caller gathers keys from — and attaches this level
    to — only those parents, leaving an excluded parent's ``attach_key`` UNSET rather
    than empty. It is carried only on a level whose parent is the root (a deeper
    level descends from already-guarded parents) and only when the guard admits fewer
    than every root object, so a guard resolving to the whole position is
    indistinguishable from an unguarded path here as well as in the trie key.
    """

    attach_key: str
    relationship: RelationshipIdentity
    to_many: bool
    parent: ParentRef
    owner: CorrelationMember
    is_back_reference: bool = False
    back_reference_family: EntityIdentity | None = None
    child_target: EntityIdentity | None = None
    child: EntityMetadata | None = None
    related: CorrelationMember | None = None
    as_of_terms: tuple[ValidatedPredicate, ...] = ()
    order_terms: tuple[ValidatedOrderTerm, ...] = ()
    narrow_to: tuple[EntityIdentity, ...] | None = None
    source_position: tuple[EntityIdentity, ...] | None = None
    related_member: AttributeMetadata | None = None

    def query_for(self, parent_keys: Sequence[object]) -> ValidatedEntityQuery:
        """Build this level's flat child query from gathered parent keys.

        The membership and propagated temporal terms form the predicate. Narrowing
        and ordering stay query fields rather than being manufactured as wrappers
        solely for SQL compilation. Raises for a back-reference level, which
        issues no child query.
        """
        reference = None if self.related is None else self.related.reference
        if self.is_back_reference or self.child_target is None or reference is None:
            raise DeepFetchError(
                f"{self.attach_key!r} is a back-reference level and issues no child query"
            )
        member = self.related_member
        if member is None:
            raise DeepFetchError(f"{self.attach_key!r} carries no resolved child member")
        values = cast("tuple[ManagedValue, ...]", tuple(parent_keys))
        membership = _managed_membership(
            attr=reference,
            member=member,
            values=values,
        )
        predicate = (
            membership
            if not self.as_of_terms
            else _validated_conjunction(membership, *self.as_of_terms)
        )
        target = self.child
        if target is None:  # pragma: no cover - queryable levels carry exact Metadata
            raise DeepFetchError(f"{self.attach_key!r} carries no resolved child metadata")
        return ValidatedEntityQuery(
            target=target.identity,
            entity=target,
            validated_predicate=predicate,
            narrow_to=self.narrow_to,
            order_by=self.order_terms,
            projection=_projection_for(target, None, ReadProjectionRequest("all", True)),
        )


@dataclass(frozen=True, slots=True)
class ObjectQueryPlan:
    """A resolved flat root query plus dependency-ordered fetch levels."""

    root: ValidatedEntityQuery
    levels: tuple[FetchLevel, ...]


def plan(
    query: ValidatedObjectQuery,
    model: Metamodel,
    *,
    projection: ReadProjectionRequest,
) -> ObjectQueryPlan:
    """Plan validated Includes and resolve the caller's projection request."""
    entity = query.root
    families = inheritance.view(model)
    temporal_entity = _entity(model, _entity_view(families, entity.identity).root)
    root_pins = resolved_pinned_instants(query.temporal)
    root_injected = inject_resolved_as_of(query.predicate, query.temporal, temporal_entity)
    predicate = navigate.canonicalize_validated(root_injected, model, entity, root_pins)
    narrow_to = (
        None if query.narrow_to is None else tuple(item.identity for item in query.narrow_to)
    )
    root = ValidatedEntityQuery(
        target=entity.identity,
        entity=entity,
        validated_predicate=predicate,
        narrow_to=narrow_to,
        order_by=query.order_by,
        projection=_projection_for(entity, families, projection),
        limit=query.limit,
    )

    builder = _PlanBuilder(model=model, families=families, root_pins=root_pins)
    builder.seed_root(entity)
    for path in query.includes:
        builder.add_path(path)
    return ObjectQueryPlan(root=root, levels=tuple(builder.levels))


def plan_mutation_read(
    write: PreparedPredicateWrite,
    *,
    model: Metamodel,
    temporal: tuple[ValidatedTemporalSelection, ...],
    projection: ReadProjectionRequest,
) -> ValidatedEntityQuery:
    """Produce the one resolved flat read required to materialize a predicate write."""
    entity = write.selection.target
    families = inheritance.view(model)
    temporal_entity = _entity(model, _entity_view(families, entity.identity).root)
    root_pins = resolved_pinned_instants(temporal)
    injected = inject_resolved_as_of(write.selection.predicate, temporal, temporal_entity)
    predicate = navigate.canonicalize_validated(injected, model, entity, root_pins)
    assigned = frozenset(
        assignment.member.identity.path[-1]
        for assignment in write.managed_assignments
        if not isinstance(assignment.member, AttributeMetadata)
    )
    requested = projection.value_objects
    if requested == "all":
        value_objects: Literal["all"] | frozenset[str] = "all"
    elif requested == "none":
        value_objects = assigned
    else:
        value_objects = requested | assigned
    resolved_projection = _projection_for(
        entity,
        families,
        ReadProjectionRequest(value_objects, projection.observe_structured_document),
    )
    return ValidatedEntityQuery(
        target=entity.identity,
        entity=entity,
        validated_predicate=predicate,
        projection=resolved_projection,
    )


# --------------------------------------------------------------------------- #
# The trie builder (shared-prefix dedup, back-reference detection).           #
# --------------------------------------------------------------------------- #
_ROOT_ID = -1


def _new_levels() -> list[FetchLevel]:
    return []


class _TrieKey(NamedTuple):
    """One level's dedup identity, with each narrow position's own rule named.

    ``parent`` is the trie node this level hangs from (``_ROOT_ID`` at a path's
    first segment). ``root_source`` is the path's resolved root source set, carried
    at that first segment alone and ``None`` deeper, where ``parent`` already
    separates branches. ``narrowed`` and ``position`` are the SEGMENT's own rule and
    are deliberately the opposite of the root's: the authored flag joins the key
    because a narrowed hop owns a distinct view key even when it resolves to the
    target's whole set, while the root carries no flag at all because a guard owns
    no view and a guard admitting every root object simply IS the broad path.
    """

    parent: int
    root_source: tuple[EntityIdentity, ...] | None
    rel: str
    narrowed: bool
    position: tuple[EntityIdentity, ...]


def _new_children() -> dict[_TrieKey, int]:
    return {}


def _new_arrivals() -> dict[int, RelationshipMetadata]:
    return {}


def _new_owners() -> dict[int, EntityMetadata]:
    return {}


@dataclass(slots=True)
class _PlanBuilder:
    model: Metamodel
    families: InheritanceFacet
    root_pins: Mapping[TemporalDimension, ManagedValue]
    levels: list[FetchLevel] = field(default_factory=_new_levels)
    _children: dict[_TrieKey, int] = field(default_factory=_new_children)
    # The relationship direction each trie node was REACHED by, absent for the root:
    # a segment is a back-reference only against its parent's own arrival edge.
    _arrivals: dict[int, RelationshipMetadata] = field(default_factory=_new_arrivals)
    # Each trie node's own Entity: the position a segment beneath it writes its
    # ``Class.relationship`` reference against.
    _owners: dict[int, EntityMetadata] = field(default_factory=_new_owners)
    # The queried position's own effective concrete set, against which a path's
    # resolved root source set is measured for properness.
    _root_position: tuple[EntityIdentity, ...] = ()

    def seed_root(self, root_entity: EntityMetadata) -> None:
        self._owners[_ROOT_ID] = root_entity
        self._root_position = _resolve_root_source(self.model, self.families, root_entity)

    def add_path(self, path: ValidatedIncludePath) -> None:
        source = path.source_position
        parent_id = _ROOT_ID
        for segment in path.segments:
            parent_id = self._add_segment(parent_id, segment, source)

    def _add_segment(
        self,
        parent_id: int,
        segment: ValidatedIncludeSegment,
        root_source: tuple[EntityIdentity, ...],
    ) -> int:
        if parent_id != _ROOT_ID and self.levels[parent_id].is_back_reference:
            raise DeepFetchError(
                f"{segment.relationship!r}: a deep-fetch path cannot continue "
                "past a back-reference "
                "level (m-case-format 'Back-reference cycles' — the ancestor-revisit hop's "
                "rows are already fully known; no corpus case needs a level beneath one)"
            )
        owner = self._owners[parent_id]
        direction = relationship.view(self.model).relationship(segment.relationship)
        if direction is None:
            raise DeepFetchError(f"resolved relationship {segment.relationship!r} is absent")
        related_entity = segment.target
        position = segment.position
        narrowed = segment.authored_narrow
        source = root_source if parent_id == _ROOT_ID else None
        key = _TrieKey(
            parent=parent_id,
            root_source=source,
            rel=f"{direction.identity.source_entity.canonical}.{direction.identity.name}",
            narrowed=narrowed,
            position=position,
        )
        existing = self._children.get(key)
        if existing is not None:
            return existing

        family = _entity_view(self.families, related_entity.identity).root
        to_many = direction.cardinality is Cardinality.ONE_TO_MANY
        is_back_reference = not to_many and _is_inverse_edge(
            self._arrivals.get(parent_id), direction
        )

        rel_local = direction.identity.name
        attach_key = _view_key(rel_local, narrowed, position, self.families)
        owner = CorrelationMember(
            identity=direction.join.source,
            column=_attribute_column(self.families, direction.join.source),
        )
        parent_ref: ParentRef = RootRef() if parent_id == _ROOT_ID else LevelRef(parent_id)
        # Only a PROPER guard restricts anything; one admitting the whole queried
        # position has already collapsed onto the broad path in the key above.
        source_position = source if source is not None and source != self._root_position else None

        if is_back_reference:
            level = FetchLevel(
                attach_key=attach_key,
                relationship=direction.identity,
                to_many=to_many,
                parent=parent_ref,
                owner=owner,
                is_back_reference=True,
                back_reference_family=family,
                source_position=source_position,
            )
        else:
            child_target = position[0] if len(position) == 1 else direction.join.target.entity
            narrow_to = position if len(position) > 1 and narrowed else None
            child = _entity(self.model, child_target)
            related_member = _attribute_metadata(self.families, direction.join.target)
            level = FetchLevel(
                attach_key=attach_key,
                relationship=direction.identity,
                to_many=to_many,
                parent=parent_ref,
                owner=owner,
                child_target=child_target,
                child=child,
                related=CorrelationMember(
                    identity=direction.join.target,
                    column=_attribute_column(self.families, direction.join.target),
                    reference=f"{child_target.canonical}.{direction.join.target.name}",
                ),
                as_of_terms=validated_hop_as_of_terms(related_entity, self.model, self.root_pins),
                order_terms=_resolved_order_terms(direction, child, self.families),
                narrow_to=narrow_to,
                source_position=source_position,
                related_member=related_member,
            )

        index = len(self.levels)
        self.levels.append(level)
        self._children[key] = index
        self._arrivals[index] = direction
        self._owners[index] = related_entity
        return index


def _projection_for(
    entity: EntityMetadata,
    families: InheritanceFacet | None,
    request: ReadProjectionRequest,
) -> ResolvedReadProjection:
    available = (
        tuple(entity.declared_value_objects)
        if families is None
        else tuple(_entity_view(families, entity.identity).applicable_value_objects)
    )
    if request.value_objects == "all":
        selected = available
    elif request.value_objects == "none":
        selected = ()
    else:
        selected = tuple(
            occurrence
            for occurrence in available
            if occurrence.identity.path[-1] in request.value_objects
        )
    return ResolvedReadProjection(selected, request.observe_structured_document)


def _resolved_order_terms(
    direction: RelationshipMetadata,
    child: EntityMetadata,
    families: InheritanceFacet,
) -> tuple[ValidatedOrderTerm, ...]:
    view = _entity_view(families, child.identity)
    terms: list[ValidatedOrderTerm] = []
    for order in direction.order_by:
        member = view.applicable_attribute(order.attribute.name)
        if member is None:
            raise DeepFetchError(f"resolved relationship order member {order.attribute} is absent")
        terms.append(
            resolved_order_term(
                member,
                direction=_SORT_DIRECTIONS[order.direction],
                nulls=_NULL_PLACEMENTS[order.nulls],
            )
        )
    return tuple(terms)


def _is_inverse_edge(arrival: RelationshipMetadata | None, direction: RelationshipMetadata) -> bool:
    """Whether ``direction`` is ``arrival``'s peer — the two navigable directions of
    ONE association (``m-relationship``), each naming the other as its reverse.

    This is what proves a hop lands on the very node the path arrived from rather
    than merely on that node's family: the two directions share one join, so the
    child row's correlation attribute holds the arrival hop's own source key. Both
    reverse names are checked, and the target Entity with them, so two unrelated
    associations sharing a local relationship name cannot pair. An absent arrival is
    a hop leaving the root, which nothing preceded and which therefore revisits no
    ancestor node at all.
    """
    return (
        arrival is not None
        and arrival.reverse == direction.identity.name
        and direction.reverse == arrival.identity.name
        and direction.join.target.entity == arrival.identity.source_entity
    )


# --------------------------------------------------------------------------- #
# Pure resolution helpers (mirror m-navigate / m-sql's own mechanical rules).  #
#                                                                              #
# Each facet read below is total for an accepted model, so its absence branch  #
# names a state formation cannot produce rather than a model defect a plan     #
# could carry.                                                                 #
# --------------------------------------------------------------------------- #
def _entity(model: Metamodel, identity: EntityIdentity) -> EntityMetadata:
    entity = model.entity(identity)
    if entity is None:  # pragma: no cover - a resolved reference names a declared Entity
        raise DeepFetchError(f"{identity.canonical}: the model declares no such entity")
    return entity


def _entity_view(facet: InheritanceFacet, identity: EntityIdentity) -> InheritanceEntityView:
    view = facet.entity(identity)
    if view is None:  # pragma: no cover - the facet covers every accepted Entity
        raise DeepFetchError(f"{identity.canonical}: the model declares no such entity")
    return view


def _attribute_column(facet: InheritanceFacet, attribute: AttributeIdentity) -> str:
    """The PHYSICAL column ``attribute`` names on the position it is addressed at.

    A join reaches an Attribute through a position, which may be an inheritance
    participant that inherits the declaration, so the lookup runs over that
    position's own ancestry chain — the members applicable there — rather than
    over the family-wide projection superset. Disjoint sibling branches may reuse
    a member name (`m-inheritance` "Members do not shadow across ancestry"), so
    the superset can hold two same-named Attributes over different Columns and
    only the chain says which one the join addresses.
    """
    declared = _entity_view(facet, attribute.entity).applicable_attribute(attribute.name)
    if declared is None:  # pragma: no cover - guards an unvalidated relationship
        raise DeepFetchError(
            f"{attribute.entity.canonical}: {attribute.name!r} names no declared attribute"
        )
    return declared.storage.name


def _attribute_metadata(facet: InheritanceFacet, attribute: AttributeIdentity) -> AttributeMetadata:
    declared = _entity_view(facet, attribute.entity).applicable_attribute(attribute.name)
    if declared is None:  # pragma: no cover - accepted joins name applicable attributes
        raise DeepFetchError(
            f"{attribute.entity.canonical}: {attribute.name!r} names no declared attribute"
        )
    return declared


def _resolve_root_source(
    model: Metamodel,
    facet: InheritanceFacet,
    root: EntityMetadata,
) -> tuple[EntityIdentity, ...]:
    """The concrete source set ONE path starts from (m-deep-fetch's root hop identity).

    Absent a root guard the path starts from every queried object, so the source set
    is the queried position's own effective concrete set; a guard resolves its
    shared Subtype Selection inside that position.

    The result is the position's canonical effective set either way, so two guards
    resolving to the same concretes yield the SAME tuple — which is what makes a
    full-set guard indistinguishable from an unguarded path.
    """
    if root.inheritance is None:
        return (root.identity,)
    return tuple(_entity_view(facet, root.identity).concrete_subtypes)


def _view_key(
    rel_local: str,
    narrowed: bool,
    position: tuple[EntityIdentity, ...],
    facet: InheritanceFacet,
) -> str:
    """The graph attach key (m-deep-fetch "Polymorphic and narrowed deep fetch"):
    the ordinary relationship name for a broad hop, else the derived
    ``<rel>[<Concrete>,<Concrete>]`` view key — keyed on whether a narrow was
    AUTHORED, independent of the resolved position's own cardinality (a
    single-concrete narrow still derives a bracketed view key)."""
    if not narrowed:
        return rel_local
    variants = (inheritance.family_variant_name(facet, identity) for identity in position)
    return f"{rel_local}[{','.join(variants)}]"


_SORT_DIRECTIONS: Final[Mapping[SortDirection, Literal["asc", "desc"]]] = {
    SortDirection.ASCENDING: "asc",
    SortDirection.DESCENDING: "desc",
}

_NULL_PLACEMENTS: Final[Mapping[NullPlacement, Literal["first", "last"]]] = {
    NullPlacement.NULLS_FIRST: "first",
    NullPlacement.NULLS_LAST: "last",
}
