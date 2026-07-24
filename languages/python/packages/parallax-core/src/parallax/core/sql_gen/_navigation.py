"""Relationship resolution and hop PLANNING (m-sql "Joins by navigation").

A `navigate` / `exists` / `notExists` node lowers to a correlated `EXISTS`
(`notExists`: negated) semi-join. The correlation columns are derived
MECHANICALLY from the relationship's declared `join` predicate — the user never
writes a join, and nothing here guesses one. A POLYMORPHIC target resolves its
effective concrete-subtype set exactly as a top-level inheritance read does
(through the Inheritance Facet): table-per-hierarchy stays one `EXISTS` carrying
an interior tag guard, table-per-concrete-subtype fans out to a grouped `OR` of
one `EXISTS` per effective concrete, in the family's canonical order. The per-hop
as-of predicate (if any) already rides inside the hop's `op` as a plain predicate
node — `parallax.core.navigate.canonicalize` injected it upstream — so nothing
here is temporal-aware.

The join comes from the identity-resolved Relationship Declaration the target
Entity's own Metadata carries, never from a paired relationship facet: a defining
declaration owns the join outright, and a reverse declaration names its defining
peer, whose join swaps sides. That is the whole of what a semi-join needs — a
direction's cardinality decides nothing about an `EXISTS`.

**This module returns PLANS and never lowers anything.** A plan carries the
hop's un-lowered interior operation and, for a table-per-hierarchy hop, the tag
guard's INPUTS as an `_inheritance.TagPredicate` — never a rendered fragment,
since the fragment needs a child alias no plan has yet. :func:`open_branch`
renders it to a fragment plus bind VALUES once the branch takes its alias;
`_predicate` — the package's one recursive owner — lowers the interior and only
then pushes those values. It also contains no `match` over the predicate node
union: the two operation nodes it inspects are the hop node itself (to read
`rel` / `op` / negation) and a TOP-LEVEL `narrow` inside the hop's `op` (to
resolve the hop's position, `m-navigate` "Polymorphic navigation"), never a
descent into either.

That "never binds" rule is STRUCTURAL, not remembered. Every entry point here
takes a :class:`~parallax.core.sql_gen._context.PlanScope`, which exposes model
resolution, column rendering, and alias allocation — and no `bind` / `binds`.
Pushing a guard bind from a planner is therefore a type error. It matters
because the failure is invisible to the SQL: a guard bound at planning time
lands ahead of the interior's own binds while the emitted text still puts the
guard last, so text and binds disagree only when a user bind and a framework
bind share one `EXISTS` (`m-inheritance-110`, the corpus witness).

Planning a hop is two steps, and the split is load-bearing:

* :func:`plan_hop` RESOLVES — which branches this hop has, what each selects
  from, how they combine. It allocates nothing.
* :func:`open_branch` OPENS one branch — takes its alias, renders its
  correlation and its deferred tag guard.

The caller opens each branch immediately before lowering that branch's own
interior. That is what preserves the alias sequence for a grouped
table-per-concrete-subtype hop whose interior ITSELF navigates: today the second
branch's alias comes after everything the first branch's interior allocated, so
opening every branch up front would silently renumber that shape.

Named without a leading underscore because the MODULE carries the privacy, the
package convention `_context` established: importers alias each name down.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from parallax.core.inheritance import InheritanceFacet
from parallax.core.metamodel import (
    AbstractRoot,
    DefiningRelationshipDeclaration,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    RelationshipJoin,
    RelativeEntityReference,
    ReverseRelationshipDeclaration,
    TablePerHierarchy,
    resolve_entity_reference,
)
from parallax.core.op_algebra import Exists, Narrow, Navigate, NotExists, Operation
from parallax.core.sql_gen._context import PlanScope as _PlanScope
from parallax.core.sql_gen._context import SqlGenError
from parallax.core.sql_gen._context import declared_table as _table
from parallax.core.sql_gen._inheritance import TagPredicate as _TagPredicate
from parallax.core.sql_gen._inheritance import entity_view as _entity_view
from parallax.core.sql_gen._inheritance import narrow_position as _narrow_position
from parallax.core.sql_gen._inheritance import position_table as _position_table
from parallax.core.sql_gen._inheritance import tag_column as _tag_column
from parallax.core.sql_gen._inheritance import tag_guard as _tag_guard


# --------------------------------------------------------------------------- #
# The plans.                                                                   #
#                                                                              #
# A table-per-hierarchy hop's tag guard travels as `_inheritance.TagPredicate`  #
# — the same value a top-level family read's plan carries, deliberately not a   #
# second local spelling of the same three facts. It is the guard's INPUTS and   #
# not a rendered fragment because the fragment needs the child alias, which     #
# does not exist until the branch opens: `open_branch` turns it into the        #
# fragment plus its bind VALUES, and nothing binds either way.                  #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class HopBranch:
    """One correlated `EXISTS` this hop will open, RESOLVED but not yet opened.

    ``entity`` is the active entity of the branch's interior scope — the hop's
    own target for a monomorphic hop and for a table-per-concrete-subtype branch
    (the concrete), the FAMILY ROOT for a table-per-hierarchy hop, whose target
    may be abstract and whose attribute resolution must widen across the family
    exactly as a top-level inheritance read's does.
    """

    entity: EntityMetadata
    table: str
    related_attr: str
    parent_column: str
    inner: Operation | None
    tag: _TagPredicate | None
    keyword: str


@dataclass(frozen=True, slots=True)
class HopPlan:
    """One hop: its branches and how their rendered fragments compose.

    ``grouped`` is the table-per-concrete-subtype fan-out (2+ effective
    concretes) — an `or` of per-branch `EXISTS`, parenthesized, with a negation
    applied to the GROUP rather than to each branch. Every other shape is a
    single branch that carries its own `exists` / `not exists` keyword.
    """

    branches: tuple[HopBranch, ...]
    grouped: bool
    negate: bool

    def combine(self, fragments: Sequence[str]) -> str:
        """Compose the rendered branch fragments into this hop's SQL."""
        if not self.grouped:
            return fragments[0]
        grouped = f"({' or '.join(fragments)})"
        return f"not {grouped}" if self.negate else grouped


@dataclass(frozen=True, slots=True)
class OpenBranch:
    """A branch that has taken its alias: everything the caller needs to lower
    the interior and render the subquery, and nothing that has been bound.

    ``tag_binds`` are VALUES. The caller pushes them AFTER lowering ``inner``
    (m-sql "Grouped branch predicates": branch-predicate-first, then tag).
    """

    entity: EntityMetadata
    alias: str
    table: str
    correlation: str
    inner: Operation | None
    tag_fragment: tuple[str, ...]
    tag_binds: tuple[object, ...]
    keyword: str

    def render(self, where: str) -> str:
        """This branch's correlated sub-select, around an already-built `where`."""
        return f"{self.keyword} (select 1 from {self.table} {self.alias} where {where})"


# --------------------------------------------------------------------------- #
# Relationship resolution.                                                     #
# --------------------------------------------------------------------------- #
def _entity(model: Metamodel, identity: EntityIdentity) -> EntityMetadata:
    entity = model.entity(identity)
    if entity is None:  # pragma: no cover - guards an unvalidated operation
        raise SqlGenError(f"{identity.canonical!r} names no declared entity")
    return entity


def _resolve_join(rel_ref: str, scope: _PlanScope) -> RelationshipJoin:
    """The source-to-target Attribute equality one `Class.relationship` reference
    correlates on.

    A defining declaration IS the join. A reverse declaration repeats none of its
    peer's facts, so its own direction is the peer's join with the two sides
    exchanged — which is exactly what a semi-join needs and all it needs, since
    an `EXISTS` is insensitive to the direction's cardinality.

    The reference's class name is bare, so it resolves in the active target's own
    namespace like any other relative model reference.
    """
    class_name, dot, member_name = rel_ref.rpartition(".")
    if not dot:  # pragma: no cover - guards an unvalidated operation
        raise SqlGenError(f"relationship reference {rel_ref!r} needs Class.relationship")
    owner_identity = resolve_entity_reference(
        scope.entity.identity, RelativeEntityReference(class_name)
    )
    owner = scope.meta.entity(owner_identity)
    declaration = None if owner is None else owner.relationship(member_name)
    match declaration:
        case DefiningRelationshipDeclaration(join=join):
            return join
        case ReverseRelationshipDeclaration(reverse_of=reverse_of):
            peer_owner = _entity(scope.meta, reverse_of.source_entity)
            peer = peer_owner.relationship(reverse_of.name)
            if not isinstance(  # pragma: no cover - resolution pairs every reverse
                peer, DefiningRelationshipDeclaration
            ):
                raise SqlGenError(f"{rel_ref!r} names no defining relationship to correlate on")
            return RelationshipJoin(source=peer.join.target, target=peer.join.source)
        case None:
            raise SqlGenError(f"{rel_ref!r} names no declared relationship on {class_name}")


# --------------------------------------------------------------------------- #
# Planning.                                                                    #
# --------------------------------------------------------------------------- #
def plan_hop(op: Navigate | Exists | NotExists, scope: _PlanScope) -> HopPlan:
    """Resolve one hop to its branches (m-sql "Joins by navigation").

    The parent side of the correlation is rendered here, against ``scope``'s own
    active entity and alias — so a write predicate's UNALIASED parent column
    (`t1.folder_id = id`, `m-batch-write` readless forms) falls out of the same
    :meth:`~parallax.core.sql_gen._context.ColumnScope.own_column` decision every
    other reference to the target's own columns takes.

    No alias is allocated and no fragment that needs one is rendered; see
    :func:`open_branch`.
    """
    negate = isinstance(op, NotExists)
    join = _resolve_join(op.rel, scope)
    target = _entity(scope.meta, join.target.entity)
    parent_column = scope.column_of(f"{scope.entity.identity.name}.{join.source.name}")
    if target.inheritance is not None:
        return _plan_polymorphic_hop(
            target, op.op, parent_column, join.target.name, scope, negate=negate
        )
    return _plan_simple_hop(target, op.op, parent_column, join.target.name, negate=negate)


def open_branch(branch: HopBranch, scope: _PlanScope) -> OpenBranch:
    """Take ``branch``'s alias and render what depends on it.

    Called by the caller immediately BEFORE it lowers this branch's interior —
    "allocate, then descend" is what makes the `t0, t1, …` sequence depth-first
    in source order, so an interior hop's number is strictly higher than its
    enclosing hop's and a later sibling's is higher than the whole preceding
    subtree's (m-sql rule 1).

    The tag guard is rendered to a fragment and its bind VALUES here and pushed
    nowhere: ``scope`` cannot bind. The caller pushes them after the interior.
    """
    alias = scope.next_alias()
    # A read-only child view, purely to resolve the correlation and the tag
    # column against the branch's own entity and alias. The caller builds its own
    # child resolution scope for lowering; both point at the enclosing statement's
    # single `Ctx` — its bind list and alias counter — by identity, and neither of
    # these two calls allocates.
    child = scope.child(branch.entity, alias)
    related_ref = f"{branch.entity.identity.name}.{branch.related_attr}"
    correlation = f"{child.column_of(related_ref)} = {branch.parent_column}"
    tag_fragment: tuple[str, ...] = ()
    tag_binds: tuple[object, ...] = ()
    if branch.tag is not None:
        tag_sql, tag_binds = _tag_guard(child, scope.facet, branch.tag)
        tag_fragment = (tag_sql,)
    return OpenBranch(
        entity=branch.entity,
        alias=alias,
        table=branch.table,
        correlation=correlation,
        inner=branch.inner,
        tag_fragment=tag_fragment,
        tag_binds=tag_binds,
        keyword=branch.keyword,
    )


def _plan_simple_hop(
    target: EntityMetadata,
    inner: Operation | None,
    parent_column: str,
    related_attr: str,
    *,
    negate: bool,
) -> HopPlan:
    """A monomorphic relationship target: one correlated `EXISTS` over its own
    table (m-sql "Joins by navigation")."""
    return HopPlan(
        branches=(
            HopBranch(
                entity=target,
                table=_table(target),
                related_attr=related_attr,
                parent_column=parent_column,
                inner=inner,
                tag=None,
                keyword=_keyword(negate),
            ),
        ),
        grouped=False,
        negate=negate,
    )


def _hop_position(
    facet: InheritanceFacet, target: EntityMetadata, inner: Operation | None
) -> tuple[tuple[EntityIdentity, ...], Operation | None, bool]:
    """The polymorphic hop's resolved effective position + remaining interior
    predicate, mirroring a top-level family read's own narrow interception: a
    top-level `narrow` in the hop's `op` (`m-navigate` "Polymorphic navigation")
    replaces the target's own effective set with its resolved `to` set; otherwise
    the target's own effective concrete-subtype set stands. The third element is
    whether the UNTOUCHED target itself is the family's abstract root (the TPH
    "no tag predicate at all" case, `m-inheritance`).
    """
    if isinstance(inner, Narrow):
        position = _narrow_position(facet, target.identity, inner.to)
        return tuple(position.concrete_subtypes), inner.operand, False
    view = _entity_view(facet, target.identity)
    return (
        tuple(view.concrete_subtypes),
        inner,
        isinstance(target.inheritance, AbstractRoot),
    )


def _plan_polymorphic_hop(
    target: EntityMetadata,
    inner: Operation | None,
    parent_column: str,
    related_attr: str,
    scope: _PlanScope,
    *,
    negate: bool,
) -> HopPlan:
    """A polymorphic relationship target: table-per-hierarchy plans a single
    correlated `EXISTS` with the interior tag guard (reusing `_inheritance`'s tag
    machinery); table-per-concrete-subtype plans one `EXISTS` per effective
    concrete, in the family's canonical order, grouped by `or` (m-sql
    "Polymorphic navigation lowering")."""
    view = _entity_view(scope.facet, target.identity)
    position, remaining_inner, is_bare_root = _hop_position(scope.facet, target, inner)
    if isinstance(view.strategy, TablePerHierarchy):
        return _plan_tph_hop(
            view.root,
            position,
            remaining_inner,
            parent_column,
            related_attr,
            scope,
            is_bare_root=is_bare_root,
            negate=negate,
        )
    return _plan_tpcs_hop(
        position, remaining_inner, parent_column, related_attr, scope, negate=negate
    )


def _plan_tph_hop(
    root: EntityIdentity,
    position: Sequence[EntityIdentity],
    remaining_inner: Operation | None,
    parent_column: str,
    related_attr: str,
    scope: _PlanScope,
    *,
    is_bare_root: bool,
    negate: bool,
) -> HopPlan:
    view = _entity_view(scope.facet, root)
    # An UNTOUCHED abstract root hops to the whole family, so it carries no tag
    # predicate at all — the same rule a top-level family read applies, spelled
    # here as the absence of a `TagPredicate` rather than as a sentinel kind.
    tag = None if is_bare_root else _TagPredicate(_tag_column(view), tuple(position))
    return HopPlan(
        branches=(
            HopBranch(
                # The interior's active entity is the hop's TARGET FAMILY ROOT
                # (possibly abstract): family-wide attribute resolution needs only
                # that the position participates, exactly like a top-level
                # inheritance read's resolution scope.
                entity=_entity(scope.meta, root),
                table=_position_table(scope.facet, root),
                related_attr=related_attr,
                parent_column=parent_column,
                inner=remaining_inner,
                tag=tag,
                keyword=_keyword(negate),
            ),
        ),
        grouped=False,
        negate=negate,
    )


def _plan_tpcs_hop(
    position: Sequence[EntityIdentity],
    remaining_inner: Operation | None,
    parent_column: str,
    related_attr: str,
    scope: _PlanScope,
    *,
    negate: bool,
) -> HopPlan:
    if len(position) == 1:
        # m-sql: "a single concrete is one EXISTS (no grouping)" — the negation
        # lands on that one branch, exactly as a monomorphic hop's does.
        return HopPlan(
            branches=(
                _tpcs_branch(
                    position[0], remaining_inner, parent_column, related_attr, scope, negate=negate
                ),
            ),
            grouped=False,
            negate=negate,
        )
    return HopPlan(
        branches=tuple(
            _tpcs_branch(
                concrete, remaining_inner, parent_column, related_attr, scope, negate=False
            )
            for concrete in position
        ),
        grouped=True,
        negate=negate,
    )


def _tpcs_branch(
    concrete: EntityIdentity,
    remaining_inner: Operation | None,
    parent_column: str,
    related_attr: str,
    scope: _PlanScope,
    *,
    negate: bool,
) -> HopBranch:
    """One effective concrete's own `EXISTS` over its own table.

    The table is that concrete's own container, never the queried position's:
    the position may itself be row-bearing with row-bearing descendants, in which
    case its own table is one branch among several.
    """
    return HopBranch(
        entity=_entity(scope.meta, concrete),
        table=_position_table(scope.facet, concrete),
        related_attr=related_attr,
        parent_column=parent_column,
        inner=remaining_inner,
        tag=None,
        keyword=_keyword(negate),
    )


def _keyword(negate: bool) -> str:
    return "not exists" if negate else "exists"
