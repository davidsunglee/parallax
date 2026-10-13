from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from parallax.core.base import INFINITY
from parallax.core.metamodel import (
    AbstractRoot,
    AsOfAxisMetadata,
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    TablePerHierarchy,
)
from parallax.core.predicate._resolved import (
    CurrentObject,
    ResolvedComparison,
    ResolvedPredicate,
    ResolvedRelationship,
)
from parallax.core.sql_gen._context import PlanScope as _PlanScope
from parallax.core.sql_gen._context import SqlGenError
from parallax.core.sql_gen._context import table_layout as _table_layout
from parallax.core.sql_gen._inheritance import TagPredicate as _TagPredicate
from parallax.core.sql_gen._inheritance import entity_view as _entity_view
from parallax.core.sql_gen._inheritance import tag_column as _tag_column
from parallax.core.sql_gen._inheritance import tag_guard as _tag_guard
from parallax.core.temporal_read import ranked_axes as _ranked_axes
from parallax.core.temporal_read import view as _temporal_view


@dataclass(frozen=True, slots=True)
class RelationshipCandidateBranch:
    """One physical Table a relationship's candidates are read from, which can
    yield zero, one, or several rows; it takes no alias until it renders."""

    entity: EntityMetadata
    table: str
    source: AttributeMetadata
    related: AttributeMetadata
    family_guard: _TagPredicate | None


@dataclass(frozen=True, slots=True)
class RelationshipCandidatePlan:
    branches: tuple[RelationshipCandidateBranch, ...]


@dataclass(frozen=True, slots=True)
class RenderedRelationshipCandidate:
    """A branch rendered under one alias against one parent scope; its family
    guard's binds travel as values for the caller to push where its text lands."""

    entity: EntityMetadata
    alias: str
    table: str
    correlation_sql: str
    family_guard_sql: str | None
    family_guard_binds: tuple[object, ...]


def _entity(model: Metamodel, identity: EntityIdentity) -> EntityMetadata:
    entity = model.entity(identity)
    if entity is None:  # pragma: no cover - validated positions name accepted entities
        raise SqlGenError(f"{identity.canonical!r} names no declared entity")
    return entity


def plan_relationship_candidates(
    relationship: ResolvedRelationship,
    *,
    position: tuple[EntityIdentity, ...] | None,
    scope: _PlanScope,
) -> RelationshipCandidatePlan:
    """Every physical branch ``relationship``'s candidates come from, read from
    canonical metadata and layout; ``position`` selects a narrower effective
    family where a quantifier's operand narrows its element."""
    target = relationship.target
    if target.inheritance is None:
        return _plan(_branch(target, relationship, scope, None))
    view = _entity_view(scope.facet, target.identity)
    effective = tuple(view.concrete_subtypes) if position is None else position
    if isinstance(view.strategy, TablePerHierarchy):
        is_bare_root = position is None and isinstance(target.inheritance, AbstractRoot)
        root = view.root
        layout = _table_layout(scope.storage, scope.facet, root)
        guard = None if is_bare_root else _TagPredicate(_tag_column(layout, root), effective)
        return _plan(_branch(_entity(scope.meta, root), relationship, scope, guard))
    return RelationshipCandidatePlan(
        tuple(
            _branch(_entity(scope.meta, concrete), relationship, scope, None)
            for concrete in effective
        )
    )


def _plan(branch: RelationshipCandidateBranch) -> RelationshipCandidatePlan:
    return RelationshipCandidatePlan((branch,))


def _branch(
    entity: EntityMetadata,
    relationship: ResolvedRelationship,
    scope: _PlanScope,
    family_guard: _TagPredicate | None,
) -> RelationshipCandidateBranch:
    return RelationshipCandidateBranch(
        entity=entity,
        table=_table_layout(scope.storage, scope.facet, entity.identity).table.name,
        source=relationship.source,
        related=relationship.related,
        family_guard=family_guard,
    )


def render_relationship_candidate(
    branch: RelationshipCandidateBranch, parent: _PlanScope, alias: str | None = None
) -> RenderedRelationshipCandidate:
    """Allocate one branch alias, or adopt ``alias``, and render its correlation
    against ``parent``'s own source endpoint and its family guard."""
    alias = parent.next_alias() if alias is None else alias
    child = parent.child(branch.entity, alias)
    correlation = f"{child.column_for(branch.related)} = {parent.column_for(branch.source)}"
    guard_sql: str | None = None
    guard_binds: tuple[object, ...] = ()
    if branch.family_guard is not None:
        guard_sql, guard_binds = _tag_guard(child, parent.facet, branch.family_guard)
    return RenderedRelationshipCandidate(
        entity=branch.entity,
        alias=alias,
        table=branch.table,
        correlation_sql=correlation,
        family_guard_sql=guard_sql,
        family_guard_binds=guard_binds,
    )


def shared_relationship_is_eligible(
    relationship: ResolvedRelationship,
    candidates: RelationshipCandidatePlan,
    scope: _PlanScope,
) -> bool:
    """Whether ``relationship`` reaches at most one candidate row, so a shared
    join cannot multiply the rows it is joined to.

    Only one physical branch qualifies, because a Table's unique key says
    nothing about another concrete Table of the same family. Then either the
    strict equalities of its correlation and generated visibility fix every
    Column of one of that Table's unique keys — strict equality never matches a
    null component, so a nullable unique Column qualifies too, and a Latest end
    equality fixes a temporal end — or the correlation fixes the target family's
    logical key and the visibility selects one perspective on every temporal
    axis, which the full-history non-overlap invariant (`m-temporal-write`)
    makes one milestone. Declared cardinality, authored conditions, and
    operand-local subtype selection prove nothing.
    """
    if len(candidates.branches) != 1:
        return False
    (branch,) = candidates.branches
    if branch.family_guard is not None and not branch.family_guard.position:
        return False
    visibility = relationship.visibility
    layout = _table_layout(scope.storage, scope.facet, branch.entity.identity)
    fixed = {branch.related.identity, *_latest_ends(visibility)}
    if any(
        key.columns and all(slot.contributor in fixed for slot in key.columns)
        for key in layout.unique_keys
    ):
        return True
    shape = _temporal_view(scope.meta).shape(relationship.target.identity)
    axes = () if shape is None else _ranked_axes(shape)
    logical_key = _entity_view(scope.facet, relationship.target.identity).primary_key
    return (
        bool(axes)
        and branch.related.identity == logical_key.identity
        and all(_one_perspective(axis, visibility) for axis in axes)
    )


def _latest_ends(visibility: tuple[ResolvedPredicate, ...]) -> Iterator[AttributeIdentity]:
    for term in visibility:
        if (
            isinstance(term, ResolvedComparison)
            and term.op == "eq"
            and term.framework
            and term.value is INFINITY
            and isinstance(term.position, CurrentObject)
            and isinstance(term.member, AttributeMetadata)
        ):
            yield term.member.identity


def _one_perspective(axis: AsOfAxisMetadata, visibility: tuple[ResolvedPredicate, ...]) -> bool:
    """Whether ``visibility`` selects ``axis`` at one coordinate: its Latest end
    equality, or the containment pair of one finite instant."""
    if axis.end_attribute in set(_latest_ends(visibility)):
        return True
    starts: list[object] = []
    ends: list[object] = []
    for term in visibility:
        if (
            not isinstance(term, ResolvedComparison)
            or term.framework
            or not isinstance(term.position, CurrentObject)
        ):
            continue
        member = term.member.identity
        if term.op == "lessThanEquals" and member == axis.start_attribute:
            starts.append(term.value)
        elif term.op == "greaterThan" and member == axis.end_attribute:
            ends.append(term.value)
    return any(start == end for start in starts for end in ends)
