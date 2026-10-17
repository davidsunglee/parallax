from __future__ import annotations

from dataclasses import dataclass

from parallax.core.metamodel import (
    AbstractRoot,
    AttributeIdentity,
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    TablePerHierarchy,
)
from parallax.core.predicate._perspective import TemporalPerspective
from parallax.core.predicate._resolved import ResolvedRelationship
from parallax.core.sql_gen._context import PlanScope as _PlanScope
from parallax.core.sql_gen._context import SqlGenError
from parallax.core.sql_gen._context import table_layout as _table_layout
from parallax.core.sql_gen._inheritance import TagPredicate as _TagPredicate
from parallax.core.sql_gen._inheritance import entity_view as _entity_view
from parallax.core.sql_gen._inheritance import tag_column as _tag_column
from parallax.core.sql_gen._inheritance import tag_guard as _tag_guard


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


def temporal_visibility(relationship: ResolvedRelationship) -> TemporalPerspective:
    """The perspective ``relationship``'s candidates are visible under."""
    visibility = relationship.temporal_visibility
    if visibility is None:  # pragma: no cover - temporal resolution reaches every relationship
        raise SqlGenError(f"{relationship.identity}: the relationship's visibility is unresolved")
    return visibility


def shared_relationship_is_eligible(
    relationship: ResolvedRelationship,
    candidates: RelationshipCandidatePlan,
    scope: _PlanScope,
) -> bool:
    """Whether ``relationship`` reaches at most one candidate row, so a shared
    join cannot multiply the rows it is joined to.

    Only one physical branch qualifies, because a Table's unique key says
    nothing about another concrete Table of the same family. Then either the
    strict equalities of its correlation and temporal visibility fix every
    Column of one of that Table's unique keys — strict equality never matches a
    null component, so a nullable unique Column qualifies too, and an axis seen
    at Latest fixes its end — or the correlation fixes the target family's
    logical key and the target is temporal: its visibility selects one
    perspective on every axis, which the full-history non-overlap invariant
    (`m-temporal-write`) makes one milestone. Declared cardinality, authored
    conditions, and operand-local subtype selection prove nothing.
    """
    if len(candidates.branches) != 1:
        return False
    (branch,) = candidates.branches
    guard = branch.family_guard
    if guard is not None and not guard.position:  # pragma: no cover - an empty family is unplanned
        return False
    visibility = temporal_visibility(relationship)
    related = branch.related.identity
    layout = _table_layout(scope.storage, scope.facet, branch.entity.identity)
    if any(
        key.columns
        and all(
            slot.contributor == related
            or (
                isinstance(slot.contributor, AttributeIdentity)
                and visibility.is_latest_end(slot.contributor)
            )
            for slot in key.columns
        )
        for key in layout.unique_keys
    ):
        return True
    logical_key = _entity_view(scope.facet, relationship.target.identity).primary_key
    return visibility.is_temporal and related == logical_key.identity
