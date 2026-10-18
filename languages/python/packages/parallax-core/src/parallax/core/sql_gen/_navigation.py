from __future__ import annotations

from dataclasses import dataclass

from parallax.core.metamodel import EntityMetadata
from parallax.core.sql_gen._context import CandidateRenderScope as _CandidateRenderScope
from parallax.core.sql_gen._inheritance import tag_guard as _tag_guard
from parallax.core.sql_gen._planning import (
    RelationshipCandidateBranch as _RelationshipCandidateBranch,
)


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


def render_relationship_candidate(
    branch: _RelationshipCandidateBranch, parent: _CandidateRenderScope, alias: str | None = None
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
