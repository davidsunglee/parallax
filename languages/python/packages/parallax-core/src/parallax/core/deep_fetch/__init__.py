"""``parallax.core.deep_fetch`` enforcement scope (m-deep-fetch).

The **pure** deep-fetch planner: it turns a (possibly ``DeepFetch``-wrapped)
``m-op-algebra`` operation into an ordered :class:`FetchPlan` — the canonicalized
root query plus a flat, dependency-ordered list of :class:`FetchLevel` entries,
each knowing how to build its own child query from its parent level's distinct
gathered keys. It never compiles a statement (``m-sql``), never executes
anything (``m-db-port``), and reifies no list — the two lifecycle result
surfaces (operation-backed lists, snapshot graphs) are built **on top of** this
plan by their own modules (``m-op-list --> m-deep-fetch``,
``m-snapshot-read --> m-deep-fetch``).

Per the dependency graph, ``m-deep-fetch`` depends on ``m-navigate``
alone — transitively reaching ``m-op-algebra``, ``m-temporal-read``,
``m-inheritance``, and ``m-relationship``, all of which this module imports
directly (the DAG permits any edge ``m-navigate`` itself reaches). A level's
to-many decision and its correlation columns are read off the compiled
direction ``m-navigate`` resolves, because a reverse declaration carries neither
an inverted cardinality nor a swapped join of its own. Root canonicalization reuses the exact
composition-at-the-engine order every read compile site shares (``inject_as_of``
then ``navigate.canonicalize``); each level's own propagated
as-of term and relationship resolution reuse ``parallax.core.navigate``'s
:func:`~parallax.core.navigate.hop_as_of_terms` /
:func:`~parallax.core.navigate.resolve_relationship` — the SAME primitives a
navigation hop's own interior rewrite uses — so a deep-fetch child level's
temporal propagation can never drift from a navigation filter's.

## Dedup identity and shared-prefix folding

Levels form a **trie** over the declared paths: each ``PathSegment`` is looked
up (or inserted) as a child of its parent level (the root, or an earlier level)
keyed by ``(the segment's relationship reference, the resolved effective
concrete-subtype set)`` — the pair ``m-deep-fetch.md`` fixes as dedup identity.
Two paths sharing a prefix therefore walk into the SAME trie node and never
duplicate a level; a broad and a narrowed hop over the same relationship, or two
hops narrowed to different concrete sets, resolve to DIFFERENT keys and become
distinct levels, each counting toward `L`.

## Back-reference cycles (m-case-format "Back-reference cycles")

While inserting a path's segments, this module tracks the chain of relationship
**target families** already reached on that same declared path (the root's own
family first). A segment whose resolved target family matches one already on
that chain is a **back-reference**: m-snapshot-read's graph-local identity
guarantees its rows are — by construction — exactly the already-materialized
ancestor's own rows (reached by walking the SAME correlation FK backwards), so
the level is marked :attr:`FetchLevel.is_back_reference` and carries no child
query at all — the assembler resolves it from the graph-local identity map,
never issuing SQL for it (m-deep-fetch's "at most 1 + L" ceiling is an upper
bound; a back-reference level costs zero).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal

from parallax.core import inheritance, navigate
from parallax.core.inheritance import InheritanceEntityView, InheritanceFacet
from parallax.core.metamodel import (
    AttributeIdentity,
    Cardinality,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    RelativeEntityReference,
    SortDirection,
    TemporalDimension,
    resolve_entity_reference,
)
from parallax.core.op_algebra import (
    And,
    DeepFetch,
    Membership,
    Narrow,
    Operation,
    OrderBy,
    OrderKey,
    PathSegment,
    Scalar,
)
from parallax.core.relationship import RelationshipMetadata
from parallax.core.temporal_read import inject_as_of, resolve_pinned_instants

__all__ = [
    "DeepFetchError",
    "FetchLevel",
    "FetchPlan",
    "LevelRef",
    "ParentRef",
    "RootRef",
    "plan",
]


class DeepFetchError(ValueError):
    """A deep-fetch path cannot be planned against the metamodel."""


@dataclass(frozen=True, slots=True)
class RootRef:
    """A level's parent rows are the root query's own rows."""


@dataclass(frozen=True, slots=True)
class LevelRef:
    """A level's parent rows are an earlier level's, named by its ``FetchPlan.levels`` index."""

    index: int


ParentRef = RootRef | LevelRef


@dataclass(frozen=True, slots=True)
class FetchLevel:
    """One deep-fetch level: an attach point, plus how to build its child query.

    ``attach_key`` is the relationship name, or — for a narrowed polymorphic hop
    (``m-deep-fetch`` "Polymorphic and narrowed deep fetch") — the derived
    narrowed-view key ``<rel>[<Concrete>,<Concrete>]``. ``parent`` names which
    already-fetched rows this level gathers its distinct keys from (the root, or
    an earlier level); ``parent_column`` is the PHYSICAL column on those parent
    rows to gather (the relationship join's owner-side attribute, mechanically
    derived, never authored).

    A **queryable** level (``is_back_reference`` false) additionally carries
    ``child_target`` (the entity this level's own read compiles against — a
    single concrete when the resolved position is exactly one, else the
    relationship's own polymorphic target), ``related_attr`` (the
    child-side ``Class.attribute`` the ``IN`` membership binds against) and
    ``related_column`` (the SAME attribute's physical column — what the
    assembler groups the returned child rows by, fanning each back to its
    parent), ``as_of_terms`` (the propagated per-axis as-of predicate, already
    resolved), ``order_keys`` (the declared relationship ``orderBy``,
    canonicalized to qualified `OrderKey`s), and ``narrow_to`` (the segment's own
    authored narrow, carried only when the resolved position spans 2+ concretes —
    a single-concrete resolution bypasses narrowing entirely by targeting that
    concrete directly, m-sql's existing inheritance-read dispatch).

    A **back-reference** level (``is_back_reference`` true) carries none of the
    above — :meth:`child_operation` is never called for it; ``back_reference_family``
    names the family the assembler resolves through its identity map instead, as
    that map keys a row on its family ROOT's declared name.
    """

    attach_key: str
    to_many: bool
    parent: ParentRef
    parent_column: str
    is_back_reference: bool = False
    back_reference_family: str | None = None
    child_target: str | None = None
    related_attr: str | None = None
    related_column: str | None = None
    as_of_terms: tuple[Operation, ...] = ()
    order_keys: tuple[OrderKey, ...] = ()
    narrow_to: tuple[str, ...] | None = None

    def child_operation(self, parent_keys: Sequence[Scalar]) -> tuple[str, Operation]:
        """Build ``(child entity name, child operation)`` from the gathered ``parent_keys``.

        Plain algebra only: an ``in`` membership over :attr:`related_attr`, the
        propagated as-of predicate ANDed after it, optionally ``Narrow``-wrapped
        (a 2+-concrete resolved position), optionally ``OrderBy``-wrapped (the
        declared relationship ordering) — never compiled, never executed. Raises
        if called on a back-reference level (it issues no child query at all).
        """
        if self.is_back_reference or self.child_target is None or self.related_attr is None:
            raise DeepFetchError(
                f"{self.attach_key!r} is a back-reference level and issues no child query"
            )
        predicate: Operation = Membership(
            op="in", attr=self.related_attr, values=tuple(parent_keys)
        )
        if self.as_of_terms:
            predicate = And(operands=(predicate, *self.as_of_terms))
        if self.narrow_to is not None:
            predicate = Narrow(entity=self.child_target, to=self.narrow_to, operand=predicate)
        if self.order_keys:
            predicate = OrderBy(operand=predicate, keys=self.order_keys)
        return self.child_target, predicate


@dataclass(frozen=True, slots=True)
class FetchPlan:
    """A deep fetch's canonicalized root query plus its ordered levels.

    ``root_operation`` is ready for ``compile_read`` unchanged (as-of injected,
    navigation canonicalized). ``levels`` is dependency-ordered: a level's own
    ``parent`` (root, or an earlier level) always precedes it, so a single
    left-to-right pass satisfies every level's data dependency.
    """

    root_operation: Operation
    levels: tuple[FetchLevel, ...]


def plan(entity: EntityMetadata, op: Operation, model: Metamodel) -> FetchPlan:
    """Plan a deep fetch against ``model`` — a pure function of ``op`` alone.

    ``op`` is the read's raw (undeserialized-no-further, but not yet temporally
    injected or navigation-canonicalized) operation: a ``DeepFetch`` node, or any
    other read operation planned with zero levels (the degenerate "materialize
    with no relationships" case a plain snapshot read, or a milestone-set
    ``history`` / ``asOfRange`` read, needs — both funnel through the SAME root
    canonicalization this function performs). ``entity`` is the read's queried
    root Entity (``targetEntity``) — an inheritance participant (abstract root,
    abstract subtype, or concrete subtype) declares no as-of axes of its own
    when its family's axes live on the root (`m-inheritance`), so the root
    query's as-of injection resolves through the Inheritance Facet's family root
    rather than ``entity``'s own (possibly empty) declaration.
    """
    families = inheritance.view(model)
    temporal_entity = _entity(model, _entity_view(families, entity.identity).root)
    if isinstance(op, DeepFetch):
        root_raw: Operation = op.operand
        paths: tuple[tuple[PathSegment, ...], ...] = op.paths
    else:
        root_raw = op
        paths = ()

    root_pins = resolve_pinned_instants(root_raw, temporal_entity)
    root_injected = inject_as_of(root_raw, temporal_entity)
    root_operation = navigate.canonicalize(root_injected, model, entity, root_pins)

    builder = _PlanBuilder(model=model, families=families, root_pins=root_pins)
    builder.seed_root(entity)
    for path in paths:
        builder.add_path(path)
    return FetchPlan(root_operation=root_operation, levels=tuple(builder.levels))


# --------------------------------------------------------------------------- #
# The trie builder (shared-prefix dedup, back-reference detection).           #
# --------------------------------------------------------------------------- #
_ROOT_ID = -1


def _new_levels() -> list[FetchLevel]:
    return []


def _new_children() -> dict[tuple[int, str, tuple[str, ...]], int]:
    return {}


def _new_ancestor_families() -> dict[int, frozenset[EntityIdentity]]:
    return {}


def _new_owners() -> dict[int, EntityMetadata]:
    return {}


@dataclass(slots=True)
class _PlanBuilder:
    model: Metamodel
    families: InheritanceFacet
    root_pins: Mapping[TemporalDimension, str]
    levels: list[FetchLevel] = field(default_factory=_new_levels)
    _children: dict[tuple[int, str, tuple[str, ...]], int] = field(default_factory=_new_children)
    _ancestor_families: dict[int, frozenset[EntityIdentity]] = field(
        default_factory=_new_ancestor_families
    )
    # Each trie node's own Entity: the scope a segment beneath it names its
    # ``Class.relationship`` reference relative to.
    _owners: dict[int, EntityMetadata] = field(default_factory=_new_owners)

    def seed_root(self, root_entity: EntityMetadata) -> None:
        self._ancestor_families[_ROOT_ID] = frozenset(
            {_entity_view(self.families, root_entity.identity).root}
        )
        self._owners[_ROOT_ID] = root_entity

    def add_path(self, path: tuple[PathSegment, ...]) -> None:
        parent_id = _ROOT_ID
        for segment in path:
            parent_id = self._add_segment(parent_id, segment)

    def _add_segment(self, parent_id: int, segment: PathSegment) -> int:
        if parent_id != _ROOT_ID and self.levels[parent_id].is_back_reference:
            raise DeepFetchError(
                f"{segment.rel!r}: a deep-fetch path cannot continue past a back-reference "
                "level (m-case-format 'Back-reference cycles' — the ancestor-revisit hop's "
                "rows are already fully known; no corpus case needs a level beneath one)"
            )
        owner = self._owners[parent_id]
        direction = navigate.resolve_relationship(segment.rel, owner.identity, self.model)
        related_entity = _entity(self.model, direction.join.target.entity)
        position = _resolve_position(self.families, related_entity, segment)
        key = (parent_id, segment.rel, position)
        existing = self._children.get(key)
        if existing is not None:
            return existing

        family = _entity_view(self.families, related_entity.identity).root
        parent_ancestors = self._ancestor_families[parent_id]
        is_back_reference = family in parent_ancestors

        _, _, rel_local = segment.rel.rpartition(".")
        attach_key = _view_key(rel_local, bool(segment.narrow), position)
        to_many = direction.cardinality is Cardinality.ONE_TO_MANY
        parent_column = _attribute_column(self.families, direction.join.source)
        parent_ref: ParentRef = RootRef() if parent_id == _ROOT_ID else LevelRef(parent_id)

        if is_back_reference:
            level = FetchLevel(
                attach_key=attach_key,
                to_many=to_many,
                parent=parent_ref,
                parent_column=parent_column,
                is_back_reference=True,
                back_reference_family=family.name,
            )
        else:
            child_target, narrow_to = _child_target(direction, position, segment)
            level = FetchLevel(
                attach_key=attach_key,
                to_many=to_many,
                parent=parent_ref,
                parent_column=parent_column,
                child_target=child_target,
                related_attr=f"{child_target}.{direction.join.target.name}",
                related_column=_attribute_column(self.families, direction.join.target),
                as_of_terms=navigate.hop_as_of_terms(related_entity, self.model, self.root_pins),
                order_keys=_order_keys(direction, child_target),
                narrow_to=narrow_to,
            )

        index = len(self.levels)
        self.levels.append(level)
        self._children[key] = index
        self._ancestor_families[index] = parent_ancestors | {family}
        self._owners[index] = related_entity
        return index


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
    participant that inherits it, so the search widens to the family root's own
    projection superset. A standalone Entity is its own root and its own
    superset, so the widening is the identity there rather than a second path.
    """
    root = _entity_view(facet, attribute.entity).root
    for candidate in _entity_view(facet, root).superset_attributes:
        if candidate.identity.name == attribute.name:
            return candidate.storage.name
    raise DeepFetchError(  # pragma: no cover - guards an unvalidated relationship
        f"{attribute.entity.canonical}: {attribute.name!r} names no declared attribute"
    )


def _resolve_position(
    facet: InheritanceFacet, related: EntityMetadata, segment: PathSegment
) -> tuple[str, ...]:
    """The hop's resolved effective concrete-subtype set (m-deep-fetch dedup
    identity's second component): the segment's own narrow when authored, else
    the relationship target's own effective set — a non-polymorphic target's
    trivial one-name set either way.

    Each authored narrow name is resolved relative to the target's own
    namespace, exactly as any other bare model reference is, and the facet
    resolves their union to the position's canonical effective set.

    A family position names its members by their DECLARED names, because those
    are the names a narrowed view key spells and the names a graph assembler
    keys a row's own concrete and family identity by; a non-participant names
    itself canonically, as the relationship's own declared target does.
    """
    if related.inheritance is None:
        return (related.identity.canonical,)
    if segment.narrow:
        members = tuple(
            resolve_entity_reference(related.identity, RelativeEntityReference(name))
            for name in segment.narrow
        )
        position = facet.position(members)
        if position is None:
            raise DeepFetchError(
                f"narrow to {sorted(identity.canonical for identity in members)} names an "
                "entity the model does not declare, or spans more than one inheritance family"
            )
        return tuple(identity.name for identity in position.concrete_subtypes)
    return tuple(
        identity.name for identity in _entity_view(facet, related.identity).concrete_subtypes
    )


def _view_key(rel_local: str, narrowed: bool, position: tuple[str, ...]) -> str:
    """The graph attach key (m-deep-fetch "Polymorphic and narrowed deep fetch"):
    the ordinary relationship name for a broad hop, else the derived
    ``<rel>[<Concrete>,<Concrete>]`` view key — keyed on whether a narrow was
    AUTHORED, independent of the resolved position's own cardinality (a
    single-concrete narrow still derives a bracketed view key)."""
    if not narrowed:
        return rel_local
    return f"{rel_local}[{','.join(position)}]"


def _child_target(
    direction: RelationshipMetadata, position: tuple[str, ...], segment: PathSegment
) -> tuple[str, tuple[str, ...] | None]:
    """The level's own read target entity, and its ``Narrow.to`` (or
    ``None``) — the child-level analogue of `m-sql`'s abstract-read dispatch,
    but keyed on the RESOLVED POSITION'S cardinality rather than whether the
    named target is itself abstract (m-deep-fetch: a single-concrete narrowed
    view carries no `familyVariant`, unlike a top-level abstract-target read):
    a position resolving to exactly one concrete targets that concrete directly
    (no `Narrow` node — `m-sql`'s existing concrete-target dispatch already
    yields the correct tag filter with no tag projection); a position spanning
    2+ concretes targets the relationship's own (polymorphic) position, `Narrow`-
    wrapped only when the segment itself authored one (a broad hop reaching 2+
    concretes naturally needs no wrapper — `m-sql`'s own effective-set
    resolution already returns the same set from the bare target)."""
    if len(position) == 1:
        return position[0], None
    if segment.narrow:
        return direction.join.target.entity.canonical, tuple(segment.narrow)
    return direction.join.target.entity.canonical, None


_SORT_DIRECTIONS: Final[Mapping[SortDirection, Literal["asc", "desc"]]] = {
    SortDirection.ASCENDING: "asc",
    SortDirection.DESCENDING: "desc",
}


def _order_keys(direction: RelationshipMetadata, qualifier: str) -> tuple[OrderKey, ...]:
    """The declared relationship ``orderBy``, canonicalized to qualified `OrderKey`s
    (m-deep-fetch "Ordered to-many children"). The class-name qualifier is
    resolution-inert (`m-sql`'s `entity_attribute` matches on the bare attribute
    name alone) but keeps the reference grammar's shape.

    This is the translation boundary between the metamodel's Sort Direction and
    the operation algebra's own wire vocabulary: an accepted ordering term always
    carries a direction (an omitted one normalizes to ascending at formation),
    while an authored sort key may still leave its own unset."""
    return tuple(
        OrderKey(
            attr=f"{qualifier}.{term.attribute.name}", direction=_SORT_DIRECTIONS[term.direction]
        )
        for term in direction.order_by
    )
