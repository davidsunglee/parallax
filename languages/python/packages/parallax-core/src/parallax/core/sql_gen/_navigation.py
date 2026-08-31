"""Plan validated relationship navigation without revisiting authored semantics.

Predicate validation supplies the resolved target and both exact join members. This
module chooses inheritance branches, allocates aliases, and renders correlation from
those retained products; it never looks up a relationship or parses a member reference.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from parallax.core.metamodel import (
    AbstractRoot,
    AttributeMetadata,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    TablePerHierarchy,
)
from parallax.core.sql_gen._context import PlanScope as _PlanScope
from parallax.core.sql_gen._context import SqlGenError
from parallax.core.sql_gen._context import table_layout as _table_layout
from parallax.core.sql_gen._inheritance import TagPredicate as _TagPredicate
from parallax.core.sql_gen._inheritance import entity_view as _entity_view
from parallax.core.sql_gen._inheritance import tag_column as _tag_column
from parallax.core.sql_gen._inheritance import tag_guard as _tag_guard


@dataclass(frozen=True, slots=True)
class HopBranch:
    """One resolved correlated branch, before it takes an alias."""

    entity: EntityMetadata
    table: str
    related: AttributeMetadata
    parent_column: str
    tag: _TagPredicate | None
    keyword: str


@dataclass(frozen=True, slots=True)
class HopPlan:
    branches: tuple[HopBranch, ...]
    grouped: bool
    negate: bool

    def combine(self, fragments: Sequence[str]) -> str:
        if not self.grouped:
            return fragments[0]
        grouped = f"({' or '.join(fragments)})"
        return f"not {grouped}" if self.negate else grouped


@dataclass(frozen=True, slots=True)
class OpenBranch:
    """An aliased branch with correlation and deferred framework tag binds."""

    entity: EntityMetadata
    alias: str
    table: str
    correlation: str
    tag_fragment: tuple[str, ...]
    tag_binds: tuple[object, ...]
    keyword: str

    def render(self, where: str) -> str:
        return f"{self.keyword} (select 1 from {self.table} {self.alias} where {where})"


def _entity(model: Metamodel, identity: EntityIdentity) -> EntityMetadata:
    entity = model.entity(identity)
    if entity is None:  # pragma: no cover - validated positions name accepted entities
        raise SqlGenError(f"{identity.canonical!r} names no declared entity")
    return entity


def plan_validated_hop(
    target: EntityMetadata,
    source: AttributeMetadata,
    related: AttributeMetadata,
    *,
    position: tuple[EntityIdentity, ...] | None,
    scope: _PlanScope,
    negate: bool,
) -> HopPlan:
    """Plan one hop from validation's exact target and join endpoints."""
    parent_column = scope.column_for(source)
    if target.inheritance is None:
        return _plan_simple_hop(target, parent_column, related, scope, negate=negate)
    view = _entity_view(scope.facet, target.identity)
    effective = tuple(view.concrete_subtypes) if position is None else position
    is_bare_root = position is None and isinstance(target.inheritance, AbstractRoot)
    if isinstance(view.strategy, TablePerHierarchy):
        return _plan_tph_hop(
            view.root,
            effective,
            parent_column,
            related,
            scope,
            is_bare_root=is_bare_root,
            negate=negate,
        )
    return _plan_tpcs_hop(effective, parent_column, related, scope, negate=negate)


def open_branch(branch: HopBranch, scope: _PlanScope) -> OpenBranch:
    """Allocate one branch alias and render facts that depend on it."""
    alias = scope.next_alias()
    child = scope.child(branch.entity, alias)
    correlation = f"{child.column_for(branch.related)} = {branch.parent_column}"
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
        tag_fragment=tag_fragment,
        tag_binds=tag_binds,
        keyword=branch.keyword,
    )


def _plan_simple_hop(
    target: EntityMetadata,
    parent_column: str,
    related: AttributeMetadata,
    scope: _PlanScope,
    *,
    negate: bool,
) -> HopPlan:
    return HopPlan(
        branches=(
            HopBranch(
                entity=target,
                table=_table_layout(scope.storage, scope.facet, target.identity).table.name,
                related=related,
                parent_column=parent_column,
                tag=None,
                keyword=_keyword(negate),
            ),
        ),
        grouped=False,
        negate=negate,
    )


def _plan_tph_hop(
    root: EntityIdentity,
    position: Sequence[EntityIdentity],
    parent_column: str,
    related: AttributeMetadata,
    scope: _PlanScope,
    *,
    is_bare_root: bool,
    negate: bool,
) -> HopPlan:
    layout = _table_layout(scope.storage, scope.facet, root)
    tag = None if is_bare_root else _TagPredicate(_tag_column(layout, root), tuple(position))
    return HopPlan(
        branches=(
            HopBranch(
                entity=_entity(scope.meta, root),
                table=layout.table.name,
                related=related,
                parent_column=parent_column,
                tag=tag,
                keyword=_keyword(negate),
            ),
        ),
        grouped=False,
        negate=negate,
    )


def _plan_tpcs_hop(
    position: Sequence[EntityIdentity],
    parent_column: str,
    related: AttributeMetadata,
    scope: _PlanScope,
    *,
    negate: bool,
) -> HopPlan:
    if len(position) == 1:
        return HopPlan(
            branches=(_tpcs_branch(position[0], parent_column, related, scope, negate=negate),),
            grouped=False,
            negate=negate,
        )
    return HopPlan(
        branches=tuple(
            _tpcs_branch(concrete, parent_column, related, scope, negate=False)
            for concrete in position
        ),
        grouped=True,
        negate=negate,
    )


def _tpcs_branch(
    concrete: EntityIdentity,
    parent_column: str,
    related: AttributeMetadata,
    scope: _PlanScope,
    *,
    negate: bool,
) -> HopBranch:
    return HopBranch(
        entity=_entity(scope.meta, concrete),
        table=_table_layout(scope.storage, scope.facet, concrete).table.name,
        related=related,
        parent_column=parent_column,
        tag=None,
        keyword=_keyword(negate),
    )


def _keyword(negate: bool) -> str:
    return "not exists" if negate else "exists"
