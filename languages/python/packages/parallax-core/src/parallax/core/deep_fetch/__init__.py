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
keyed by ``(the segment's relationship reference, whether a narrow was AUTHORED,
the resolved effective concrete-subtype set)`` — the dedup identity
``m-deep-fetch.md`` fixes, with the authored flag carried alongside the resolved
set because a segment's own view key is derived from it. Two paths sharing a
prefix therefore walk into the SAME trie node and never duplicate a level; two
hops narrowed to different concrete sets resolve to DIFFERENT keys, and a broad
hop is never the same hop as an authored narrow over the same relationship —
including a REDUNDANT narrow resolving to the target's entire effective set,
which returns the same rows under a distinct bracketed view key. Each distinct
key counts toward `L`.

A path may additionally carry a **root guard** (``NavigationPath.narrow``), which
restricts the queried objects the path starts from. It joins the key at the ROOT
position only, and it keys on the **resolved source set** rather than on whether a
guard was authored — the deliberate opposite of the segment rule above, because a
guard creates no view of its own. Two guards resolving to the same concretes are
therefore one hop, a guard admitting every root object IS the broad path, and every
proper guard resolves to a strict subset and separates automatically.

## Back-reference cycles (m-case-format "Back-reference cycles")

m-case-format stops recursion at a **true cycle** — a relationship reaching an
**ancestor node on the current path** — so the shortcut this module applies is
sound only where the reached node is that ancestor by construction, never merely
where the reached *family* was seen before. The condition is the **inverse edge**:
a segment is a back-reference when it is **to-one** and its direction is the peer
of the very direction its parent level was reached by (each names the other as its
reverse, across the same association). The parent row then carries the ancestor's
key on the SAME correlation attribute the arrival hop joined on, so walking it
backwards can only land on the parent level's own parent — already materialized.
Such a level is marked :attr:`FetchLevel.is_back_reference` and carries no child
query at all — the assembler resolves it from the graph-local identity map, never
issuing SQL for it (m-deep-fetch's "at most 1 + L" ceiling is an upper bound; a
back-reference level costs zero).

Every other family revisit is an ordinary queried level, because nothing pins the
reached row to the path's ancestor:

- a **to-many** segment gathers its rows by the CHILD's own foreign key to the
  parent, so they are whatever that key selects rather than the ancestor the path
  arrived from — the owner of the Dog a path reached may own Dogs the read never
  materialized;
- a to-one segment over a **different association** than the one the path arrived
  on revisits the family through an unrelated key, so it may select a row of that
  family the read never materialized at all;
- a to-one segment hanging directly off the **root** revisits the root's own family
  with no arrival edge behind it, so there is no ancestor row to resolve against.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal, NamedTuple

from parallax.core import inheritance, navigate
from parallax.core.inheritance import InheritanceEntityView, InheritanceFacet
from parallax.core.metamodel import (
    AttributeIdentity,
    Cardinality,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    NullPlacement,
    RelationshipIdentity,
    SortDirection,
    TemporalDimension,
    entity_by_name,
)
from parallax.core.op_algebra import (
    And,
    DeepFetch,
    Membership,
    Narrow,
    NavigationPath,
    Operation,
    OrderBy,
    OrderKey,
    PathSegment,
    Scalar,
)
from parallax.core.relationship import RelationshipMetadata
from parallax.core.temporal_read import inject_as_of, resolve_pinned_instants

__all__ = [
    "CorrelationMember",
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
class CorrelationMember:
    """One endpoint of a level's correlation, in every spelling the level needs.

    A level correlates on an Attribute (`m-deep-fetch` "A level names its
    correlation members, not only their columns"), and the three spellings are one
    fact: ``identity`` is the modeled member addressed at the position the join
    names it at, ``column`` is the physical column it maps to, and ``reference``
    is the `m-op-algebra` ``Class.attribute`` reference string the child query's
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
    above — :meth:`child_operation` is never called for it; ``back_reference_family``
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
    child_target: str | None = None
    related: CorrelationMember | None = None
    as_of_terms: tuple[Operation, ...] = ()
    order_keys: tuple[OrderKey, ...] = ()
    narrow_to: tuple[str, ...] | None = None
    source_position: tuple[EntityIdentity, ...] | None = None

    def child_operation(self, parent_keys: Sequence[Scalar]) -> tuple[str, Operation]:
        """Build ``(child entity name, child operation)`` from the gathered ``parent_keys``.

        Plain algebra only: an ``in`` membership over the child-side
        correlation's own reference, the
        propagated as-of predicate ANDed after it, optionally ``Narrow``-wrapped
        (a 2+-concrete resolved position), optionally ``OrderBy``-wrapped (the
        declared relationship ordering) — never compiled, never executed. Raises
        if called on a back-reference level (it issues no child query at all).
        """
        reference = None if self.related is None else self.related.reference
        if self.is_back_reference or self.child_target is None or reference is None:
            raise DeepFetchError(
                f"{self.attach_key!r} is a back-reference level and issues no child query"
            )
        predicate: Operation = Membership(op="in", attr=reference, values=tuple(parent_keys))
        if self.as_of_terms:
            predicate = And(operands=(predicate, *self.as_of_terms))
        if self.narrow_to is not None:
            predicate = Narrow(to=self.narrow_to, operand=predicate)
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
        paths: tuple[NavigationPath, ...] = op.paths
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
    root_pins: Mapping[TemporalDimension, str]
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
        self._root_position = _resolve_root_source(self.model, self.families, root_entity, None)

    def add_path(self, path: NavigationPath) -> None:
        source = _resolve_root_source(
            self.model, self.families, self._owners[_ROOT_ID], path.narrow
        )
        parent_id = _ROOT_ID
        for segment in path.segments:
            parent_id = self._add_segment(parent_id, segment, source)

    def _add_segment(
        self, parent_id: int, segment: PathSegment, root_source: tuple[EntityIdentity, ...]
    ) -> int:
        if parent_id != _ROOT_ID and self.levels[parent_id].is_back_reference:
            raise DeepFetchError(
                f"{segment.rel!r}: a deep-fetch path cannot continue past a back-reference "
                "level (m-case-format 'Back-reference cycles' — the ancestor-revisit hop's "
                "rows are already fully known; no corpus case needs a level beneath one)"
            )
        owner = self._owners[parent_id]
        direction = navigate.resolve_relationship(segment.rel, owner.identity, self.model)
        related_entity = _entity(self.model, direction.join.target.entity)
        position = _resolve_position(self.model, self.families, related_entity, segment)
        narrowed = bool(segment.narrow)
        source = root_source if parent_id == _ROOT_ID else None
        key = _TrieKey(
            parent=parent_id,
            root_source=source,
            rel=segment.rel,
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

        _, _, rel_local = segment.rel.rpartition(".")
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
            child_target, narrow_to = _child_target(direction, position, segment)
            level = FetchLevel(
                attach_key=attach_key,
                relationship=direction.identity,
                to_many=to_many,
                parent=parent_ref,
                owner=owner,
                child_target=child_target,
                related=CorrelationMember(
                    identity=direction.join.target,
                    column=_attribute_column(self.families, direction.join.target),
                    reference=f"{child_target}.{direction.join.target.name}",
                ),
                as_of_terms=navigate.hop_as_of_terms(related_entity, self.model, self.root_pins),
                order_keys=_order_keys(direction, child_target),
                narrow_to=narrow_to,
                source_position=source_position,
            )

        index = len(self.levels)
        self.levels.append(level)
        self._children[key] = index
        self._arrivals[index] = direction
        self._owners[index] = related_entity
        return index


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


def _narrowed_position(
    model: Metamodel, facet: InheritanceFacet, to: Sequence[str]
) -> tuple[EntityIdentity, ...] | None:
    """The canonical effective concrete set an authored ``to`` list denotes, or
    ``None`` when a name denotes no single Entity or the members span two families.

    Each name is an operation reference and resolves model-wide by
    :func:`~parallax.core.metamodel.entity_by_name`'s rule, never into the
    referring Entity's own namespace — the caller classifies the miss in its own
    vocabulary, as `m-op-algebra`'s validator does for the same spellings.
    """
    members: list[EntityIdentity] = []
    for name in to:
        entity = entity_by_name(model, name)
        if entity is None:
            return None
        members.append(entity.identity)
    position = facet.position(tuple(members))
    return None if position is None else tuple(position.concrete_subtypes)


def _resolve_position(
    model: Metamodel, facet: InheritanceFacet, related: EntityMetadata, segment: PathSegment
) -> tuple[EntityIdentity, ...]:
    """The hop's resolved effective concrete-subtype set (m-deep-fetch dedup
    identity's second component): the segment's own narrow when authored, else
    the relationship target's own effective set — a non-polymorphic target's
    trivial one-name set either way.

    A family position names its members by their DECLARED names, because those
    are the names a narrowed view key spells and the names a graph assembler
    keys a row's own concrete and family identity by; a non-participant names
    itself canonically, as the relationship's own declared target does.
    """
    if related.inheritance is None:
        return (related.identity,)
    if segment.narrow:
        position = _narrowed_position(model, facet, segment.narrow)
        if position is None:
            raise DeepFetchError(
                f"narrow to {list(segment.narrow)} names an entity the model does not "
                "declare, or spans more than one inheritance family"
            )
        return position
    return tuple(_entity_view(facet, related.identity).concrete_subtypes)


def _resolve_root_source(
    model: Metamodel,
    facet: InheritanceFacet,
    root: EntityMetadata,
    narrow: tuple[str, ...] | None,
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
    if narrow is None:
        return tuple(_entity_view(facet, root.identity).concrete_subtypes)
    position = _narrowed_position(model, facet, narrow)
    if position is None:
        raise DeepFetchError(
            f"path-root narrow to {list(narrow)} names an entity the model does not "
            "declare, or spans more than one inheritance family"
        )
    return position


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


def _child_target(
    direction: RelationshipMetadata,
    position: tuple[EntityIdentity, ...],
    segment: PathSegment,
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
        return position[0].canonical, None
    if segment.narrow:
        return direction.join.target.entity.canonical, tuple(segment.narrow)
    return direction.join.target.entity.canonical, None


_SORT_DIRECTIONS: Final[Mapping[SortDirection, Literal["asc", "desc"]]] = {
    SortDirection.ASCENDING: "asc",
    SortDirection.DESCENDING: "desc",
}

_NULL_PLACEMENTS: Final[Mapping[NullPlacement, Literal["first", "last"]]] = {
    NullPlacement.NULLS_FIRST: "first",
    NullPlacement.NULLS_LAST: "last",
}


def _order_keys(direction: RelationshipMetadata, qualifier: str) -> tuple[OrderKey, ...]:
    """The declared relationship ``orderBy``, canonicalized to qualified `OrderKey`s
    (m-deep-fetch "Ordered to-many children"). The class-name qualifier is
    resolution-inert (`m-sql`'s `entity_attribute` matches on the bare attribute
    name alone) but keeps the reference grammar's shape.

    This is the translation boundary between the metamodel's Sort Direction and
    Null Placement and the operation algebra's own wire vocabulary: an accepted
    ordering term always carries both (an omitted direction normalizes to
    ascending and an omitted placement to nulls-last at formation), while an
    authored sort key may still leave either of its own unset."""
    return tuple(
        OrderKey(
            attr=f"{qualifier}.{term.attribute.name}",
            direction=_SORT_DIRECTIONS[term.direction],
            nulls=_NULL_PLACEMENTS[term.nulls],
        )
        for term in direction.order_by
    )
