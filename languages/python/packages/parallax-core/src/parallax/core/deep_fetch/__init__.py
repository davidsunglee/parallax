"""``parallax.core.deep_fetch`` enforcement scope (m-deep-fetch).

The **pure** deep-fetch planner: it turns a (possibly ``DeepFetch``-wrapped)
``m-op-algebra`` operation into an ordered :class:`FetchPlan` — the canonicalized
root query plus a flat, dependency-ordered list of :class:`FetchLevel` entries,
each knowing how to build its own child query from its parent level's distinct
gathered keys. It never compiles a statement (``m-sql``), never executes
anything (``m-db-port``), and reifies no list — the two lifecycle result
surfaces (operation-backed lists, snapshot graphs) are built **on top of** this
plan by their own modules (the DQ5 core amendment; ``m-op-list --> m-deep-fetch``,
``m-snapshot-read --> m-deep-fetch``).

Per the amended dependency graph, ``m-deep-fetch`` depends on ``m-navigate``
alone — transitively reaching ``m-op-algebra``, ``m-temporal-read``, and
``m-inheritance``, all of which this module imports directly (the DAG permits
any edge ``m-navigate`` itself reaches). Root canonicalization reuses the exact
composition-at-the-engine order every read compile site shares (``inject_as_of``
then ``navigate.canonicalize``, the M2 precedent); each level's own propagated
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

from parallax.core import inheritance, navigate
from parallax.core.descriptor import Entity, Metamodel, Relationship, TemporalDimension
from parallax.core.inheritance._position import resolve_narrow_position
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
    ``child_target`` (the entity name :func:`~parallax.core.sql_gen.compile_read`
    compiles against — a single concrete when the resolved position is exactly
    one, else the relationship's own polymorphic target), ``related_attr`` (the
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
    names the family the assembler resolves through its identity map instead.
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


def plan(target: str, op: Operation, meta: Metamodel) -> FetchPlan:
    """Plan a deep fetch against ``meta`` — a pure function of ``op`` alone.

    ``op`` is the read's raw (undeserialized-no-further, but not yet temporally
    injected or navigation-canonicalized) operation: a ``DeepFetch`` node, or any
    other read operation planned with zero levels (the degenerate "materialize
    with no relationships" case a plain snapshot read, or a milestone-set
    ``history`` / ``asOfRange`` read, needs — both funnel through the SAME root
    canonicalization this function performs). ``target`` is the read's queried
    root entity (``targetEntity``) — an inheritance participant (abstract root,
    abstract subtype, or concrete subtype) declares no as-of axes of its own
    when its family's axes live on the root (`m-inheritance`), so the root
    query's as-of injection resolves through `inheritance.declaring_entity`
    (the family root) rather than ``target``'s own (possibly empty) record.
    """
    root_entity = meta.entity(target)
    temporal_entity = inheritance.declaring_entity(meta, root_entity)
    if isinstance(op, DeepFetch):
        root_raw: Operation = op.operand
        paths: tuple[tuple[PathSegment, ...], ...] = op.paths
    else:
        root_raw = op
        paths = ()

    root_pins = resolve_pinned_instants(root_raw, temporal_entity)
    root_injected = inject_as_of(root_raw, temporal_entity)
    root_operation = navigate.canonicalize(root_injected, meta, root_pins)

    builder = _PlanBuilder(meta=meta, root_pins=root_pins)
    builder.seed_root(root_entity)
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


def _new_ancestor_families() -> dict[int, frozenset[str]]:
    return {}


@dataclass(slots=True)
class _PlanBuilder:
    meta: Metamodel
    root_pins: Mapping[TemporalDimension, str]
    levels: list[FetchLevel] = field(default_factory=_new_levels)
    _children: dict[tuple[int, str, tuple[str, ...]], int] = field(default_factory=_new_children)
    _ancestor_families: dict[int, frozenset[str]] = field(default_factory=_new_ancestor_families)

    def seed_root(self, root_entity: Entity) -> None:
        self._ancestor_families[_ROOT_ID] = frozenset({_family_name(self.meta, root_entity)})

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
        relationship = navigate.resolve_relationship(segment.rel, self.meta)
        related_entity = self.meta.entity(relationship.join.target.entity)
        position = _resolve_position(self.meta, relationship, segment)
        key = (parent_id, segment.rel, position)
        existing = self._children.get(key)
        if existing is not None:
            return existing

        family = _family_name(self.meta, related_entity)
        parent_ancestors = self._ancestor_families[parent_id]
        is_back_reference = family in parent_ancestors

        _, _, rel_local = segment.rel.rpartition(".")
        attach_key = _view_key(rel_local, bool(segment.narrow), position)
        to_many = relationship.cardinality == "one-to-many"
        parent_column = _owner_column(self.meta, segment.rel, relationship)
        parent_ref: ParentRef = RootRef() if parent_id == _ROOT_ID else LevelRef(parent_id)

        if is_back_reference:
            level = FetchLevel(
                attach_key=attach_key,
                to_many=to_many,
                parent=parent_ref,
                parent_column=parent_column,
                is_back_reference=True,
                back_reference_family=family,
            )
        else:
            child_target, narrow_to = _child_target(relationship, position, segment)
            related_attr_name = relationship.join.target.attribute
            level = FetchLevel(
                attach_key=attach_key,
                to_many=to_many,
                parent=parent_ref,
                parent_column=parent_column,
                child_target=child_target,
                related_attr=f"{child_target}.{related_attr_name}",
                related_column=_resolve_attr_column(self.meta, related_entity, related_attr_name),
                as_of_terms=navigate.hop_as_of_terms(related_entity, self.meta, self.root_pins),
                order_keys=_order_keys(relationship, child_target),
                narrow_to=narrow_to,
            )

        index = len(self.levels)
        self.levels.append(level)
        self._children[key] = index
        self._ancestor_families[index] = parent_ancestors | {family}
        return index


# --------------------------------------------------------------------------- #
# Pure resolution helpers (mirror m-navigate / m-sql's own mechanical rules).  #
# --------------------------------------------------------------------------- #
def _family_name(meta: Metamodel, entity: Entity) -> str:
    """The family-normalized identity name (m-snapshot-read): the inheritance
    family's root name for a participant, else the entity's own name."""
    if entity.inheritance is None:
        return entity.name
    return inheritance.family_root(meta, entity).name


def _resolve_attr_column(meta: Metamodel, entity: Entity, attr_name: str) -> str:
    candidates = (
        inheritance.family_attributes(meta, entity)
        if entity.inheritance is not None
        else entity.attributes
    )
    for attribute in candidates:
        if attribute.name == attr_name:
            return attribute.column
    raise DeepFetchError(  # pragma: no cover - guards an unvalidated relationship
        f"{entity.name}: {attr_name!r} names no declared attribute"
    )


def _owner_column(meta: Metamodel, rel_ref: str, relationship: Relationship) -> str:
    """The PHYSICAL column, on the hop's OWNER entity, whose distinct values this
    level gathers from its parent rows (the join's LHS attribute, resolved to its
    column — family-wide when the owner is an inheritance participant)."""
    class_name, _, _ = rel_ref.rpartition(".")
    owner_entity = meta.entity(class_name)
    return _resolve_attr_column(meta, owner_entity, relationship.join.source)


def _resolve_position(
    meta: Metamodel, relationship: Relationship, segment: PathSegment
) -> tuple[str, ...]:
    """The hop's resolved effective concrete-subtype set (m-deep-fetch dedup
    identity's second component): the segment's own narrow when authored, else
    the relationship target's own effective set — a non-polymorphic target's
    trivial one-name set either way. The narrowed branch calls the SHARED
    ``resolve_narrow_position`` seam (COR-3 Phase 7 increment 7 round-3, P2) --
    the entity frontend's narrowed-view key derivation
    (``parallax.core.entity.graph_state``) calls the identical function, so
    the two can never drift."""
    related = meta.entity(relationship.join.target.entity)
    if related.inheritance is None:
        return (relationship.join.target.entity,)
    if segment.narrow:
        return resolve_narrow_position(meta, segment.narrow)
    return tuple(inheritance.effective_concrete_subtypes(meta, related.name))


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
    relationship: Relationship, position: tuple[str, ...], segment: PathSegment
) -> tuple[str, tuple[str, ...] | None]:
    """The level's ``compile_read`` target entity, and its ``Narrow.to`` (or
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
    related = relationship.join.target.entity
    if len(position) == 1:
        return position[0], None
    if segment.narrow:
        return related, tuple(segment.narrow)
    return related, None


def _order_keys(relationship: Relationship, qualifier: str) -> tuple[OrderKey, ...]:
    """The declared relationship ``orderBy``, canonicalized to qualified `OrderKey`s
    (m-deep-fetch "Ordered to-many children"). The class-name qualifier is
    resolution-inert (`m-sql`'s `entity_attribute` matches on the bare attribute
    name alone) but keeps the reference grammar's shape."""
    return tuple(
        OrderKey(attr=f"{qualifier}.{term.attr}", direction=term.direction)
        for term in relationship.order_by
    )
