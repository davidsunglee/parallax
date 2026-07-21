"""Relationship resolution and hop PLANNING (m-sql "Joins by navigation").

A `navigate` / `exists` / `notExists` node lowers to a correlated `EXISTS`
(`notExists`: negated) semi-join. The correlation columns are derived
MECHANICALLY from the relationship's declared `join` predicate — the user never
writes a join, and nothing here guesses one. A POLYMORPHIC target resolves its
effective concrete-subtype set exactly as a top-level inheritance read does
(`_inheritance.narrow_effective_set` / `inheritance.effective_concrete_subtypes`):
table-per-hierarchy stays one `EXISTS` carrying an interior tag guard,
table-per-concrete-subtype fans out to a grouped `OR` of one `EXISTS` per
effective concrete, alphabetical. The per-hop as-of predicate (if any) already
rides inside the hop's `op` as a plain predicate node — `parallax.core.navigate.
canonicalize` injected it upstream — so nothing here is temporal-aware.

**This module returns PLANS and never lowers anything.** A plan carries the
hop's un-lowered interior operation and, for a table-per-hierarchy hop, its tag
guard as a fragment plus bind VALUES; `_predicate` — the package's one recursive
owner — lowers the interior and only then pushes those values. It also contains
no `match` over the predicate node union: the two operation nodes it inspects are
the hop node itself (to read `rel` / `op` / negation) and a TOP-LEVEL `narrow`
inside the hop's `op` (to resolve the hop's position, `m-navigate` "Polymorphic
navigation"), never a descent into either.

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

from parallax.core import inheritance
from parallax.core.descriptor import Entity, Metamodel, Relationship
from parallax.core.op_algebra import Exists, Narrow, Navigate, NotExists, Operation
from parallax.core.sql_gen._context import PlanScope as _PlanScope
from parallax.core.sql_gen._context import SqlGenError
from parallax.core.sql_gen._inheritance import TagPredicate as _TagPredicate
from parallax.core.sql_gen._inheritance import narrow_effective_set as _narrow_effective_set
from parallax.core.sql_gen._inheritance import tag_guard as _tag_guard
from parallax.core.sql_gen._inheritance import tph_tag_column as _tph_tag_column


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

    entity: Entity
    table: str | None
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

    entity: Entity
    alias: str
    table: str | None
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
def _resolve_relationship_ref(rel_ref: str, meta: Metamodel) -> Relationship:
    class_name, _, member_name = rel_ref.partition(".")
    entity = meta.entity(class_name)
    for relationship in entity.relationships:
        if relationship.name == member_name:
            return relationship
    raise SqlGenError(  # pragma: no cover - guards an unvalidated operation
        f"{rel_ref!r} names no declared relationship on {entity.name}"
    )


def _parse_join(join: str) -> tuple[str, str]:
    """Split a relationship's `this.<attr> = <Entity>.<attr>` join predicate into
    ``(owner attribute name, related attribute name)`` — the mechanical
    correlation-column derivation `m-navigate` requires."""
    lhs, _, rhs = join.partition(" = ")
    _, _, owner_attr = lhs.partition(".")
    _, _, related_attr = rhs.partition(".")
    return owner_attr, related_attr


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
    relationship = _resolve_relationship_ref(op.rel, scope.meta)
    target_entity = scope.meta.entity(relationship.related_entity)
    owner_attr, related_attr = _parse_join(relationship.join)
    parent_column = scope.column_of(f"{scope.entity.name}.{owner_attr}")
    if target_entity.inheritance is not None:
        return _plan_polymorphic_hop(
            relationship.related_entity,
            target_entity,
            op.op,
            parent_column,
            related_attr,
            scope,
            negate=negate,
        )
    return _plan_simple_hop(target_entity, op.op, parent_column, related_attr, negate=negate)


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
    correlation = (
        f"{child.column_of(f'{branch.entity.name}.{branch.related_attr}')} = {branch.parent_column}"
    )
    tag_fragment: tuple[str, ...] = ()
    tag_binds: tuple[object, ...] = ()
    if branch.tag is not None:
        tag_sql, tag_binds = _tag_guard(child, scope.meta, branch.tag)
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
    target_entity: Entity,
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
                entity=target_entity,
                table=target_entity.table,
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
    meta: Metamodel, relatable_entity: str, inner: Operation | None
) -> tuple[tuple[str, ...], Operation | None, bool]:
    """The polymorphic hop's resolved effective position + remaining interior
    predicate, mirroring a top-level family read's own narrow interception: a
    top-level `narrow` in the hop's `op` (`m-navigate` "Polymorphic navigation")
    replaces the target's own effective set with its resolved `to` set; otherwise
    the target's own effective concrete-subtype set stands. The third element is
    whether the UNTOUCHED target itself is the family's abstract root (the TPH
    "no tag predicate at all" case, `m-inheritance`).
    """
    if isinstance(inner, Narrow):
        return _narrow_effective_set(meta, inner.to), inner.operand, False
    target = meta.entity(relatable_entity)
    is_bare_root = target.inheritance is not None and target.inheritance.role == "root"
    return (
        tuple(inheritance.effective_concrete_subtypes(meta, relatable_entity)),
        inner,
        is_bare_root,
    )


def _plan_polymorphic_hop(
    related_entity: str,
    target_entity: Entity,
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
    concrete, alphabetical, grouped by `or` (m-sql "Polymorphic navigation
    lowering")."""
    root = inheritance.family_root(scope.meta, target_entity)
    assert root.inheritance is not None
    position, remaining_inner, is_bare_root = _hop_position(scope.meta, related_entity, inner)
    if root.inheritance.strategy == "table-per-hierarchy":
        return _plan_tph_hop(
            root,
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
    root: Entity,
    position: Sequence[str],
    remaining_inner: Operation | None,
    parent_column: str,
    related_attr: str,
    scope: _PlanScope,
    *,
    is_bare_root: bool,
    negate: bool,
) -> HopPlan:
    # An UNTOUCHED abstract root hops to the whole family, so it carries no tag
    # predicate at all — the same rule a top-level family read applies, spelled
    # here as the absence of a `TagPredicate` rather than as a sentinel kind.
    tag = None if is_bare_root else _TagPredicate(_tph_tag_column(root), tuple(position))
    table = scope.meta.entity(position[0]).table
    if table is None:  # pragma: no cover - a validated TPH concrete always declares one
        raise SqlGenError(f"{position[0]}: table-per-hierarchy concrete subtype declares no table")
    return HopPlan(
        branches=(
            HopBranch(
                # The interior's active entity is the hop's TARGET FAMILY ROOT
                # (possibly abstract): family-wide attribute resolution needs only
                # that `inheritance is not None`, exactly like a top-level
                # inheritance read's context.
                entity=scope.meta.entity(root.name),
                table=table,
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
    position: Sequence[str],
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
                    scope.meta.entity(position[0]),
                    remaining_inner,
                    parent_column,
                    related_attr,
                    negate=negate,
                ),
            ),
            grouped=False,
            negate=negate,
        )
    return HopPlan(
        branches=tuple(
            _tpcs_branch(
                scope.meta.entity(name), remaining_inner, parent_column, related_attr, negate=False
            )
            for name in position
        ),
        grouped=True,
        negate=negate,
    )


def _tpcs_branch(
    concrete: Entity,
    remaining_inner: Operation | None,
    parent_column: str,
    related_attr: str,
    *,
    negate: bool,
) -> HopBranch:
    if concrete.table is None:  # pragma: no cover - a validated TPCS concrete always has one
        raise SqlGenError(f"{concrete.name}: table-per-concrete-subtype subtype declares no table")
    return HopBranch(
        entity=concrete,
        table=concrete.table,
        related_attr=related_attr,
        parent_column=parent_column,
        inner=remaining_inner,
        tag=None,
        keyword=_keyword(negate),
    )


def _keyword(negate: bool) -> str:
    return "not exists" if negate else "exists"
