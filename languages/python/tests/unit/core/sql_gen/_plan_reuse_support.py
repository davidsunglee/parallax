"""Observations of how one compilation plans its read and renders its roots.

The recorder wraps the compiler's real physical, document, and statement
planners, the storage owner's Position Layout answer, and the root-source
renderer, so a test sees every production planning invocation and every
lexical root a builder renders, without a fake planner or a testing-only hook.
"""

from __future__ import annotations

import gc
import sys
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any

import pytest

from parallax.core.sql_gen import _compile as sql_compile
from parallax.core.sql_gen import _inheritance, _planning
from parallax.core.sql_gen._context import StatementBuilder
from parallax.core.sql_gen._inheritance import (
    DirectDocumentMappings,
    SharedDocumentMapping,
    SingleTableReadPlan,
    TpcsUnionReadPlan,
)
from parallax.core.sql_gen._planning import LexicalScopeId, LexicalScopePlan, StatementPlan
from parallax.core.sql_gen._predicate import EntityRowScope, render_shared_sources
from parallax.core.storage_layout import PositionLayoutView
from parallax.core.storage_layout._facet import _StorageLayoutFacet  # pyright: ignore[reportPrivateUsage]


@dataclass(frozen=True, slots=True)
class RenderedRoot:
    statement_plan: StatementPlan
    scope_id: LexicalScopeId
    row: EntityRowScope


type ReadShape = SingleTableReadPlan | TpcsUnionReadPlan
type DocumentReads = tuple[SharedDocumentMapping | None, DirectDocumentMappings | None]


@dataclass(slots=True)
class PlanReuse:
    plans: list[StatementPlan] = field(default_factory=list[StatementPlan])
    roots: list[RenderedRoot] = field(default_factory=list[RenderedRoot])
    read_shapes: list[ReadShape] = field(default_factory=list[ReadShape])
    document_reads: list[DocumentReads] = field(default_factory=list[DocumentReads])
    position_layouts: list[PositionLayoutView | None] = field(
        default_factory=list[PositionLayoutView | None]
    )


def record_plan_reuse(monkeypatch: pytest.MonkeyPatch) -> PlanReuse:
    reuse = PlanReuse()
    real_plan = _planning.plan_statement
    real_read_shape = _inheritance.plan_read_shape
    real_document_reads = _inheritance.plan_document_reads
    real_position = _StorageLayoutFacet.position

    def plan(*args: Any, **kwargs: Any) -> StatementPlan:
        reuse.plans.append(real_plan(*args, **kwargs))
        return reuse.plans[-1]

    def read_shape(*args: Any, **kwargs: Any) -> ReadShape:
        reuse.read_shapes.append(real_read_shape(*args, **kwargs))
        return reuse.read_shapes[-1]

    def document_reads(*args: Any, **kwargs: Any) -> DocumentReads:
        reuse.document_reads.append(real_document_reads(*args, **kwargs))
        return reuse.document_reads[-1]

    def position(facet: _StorageLayoutFacet, concretes: Any) -> PositionLayoutView | None:
        reuse.position_layouts.append(real_position(facet, concretes))
        return reuse.position_layouts[-1]

    def render(statement_plan: StatementPlan, scope_id: LexicalScopeId, row: EntityRowScope) -> str:
        reuse.roots.append(RenderedRoot(statement_plan, scope_id, row))
        return render_shared_sources(statement_plan, scope_id, row)

    monkeypatch.setattr(sql_compile, "_plan_statement", plan)
    monkeypatch.setattr(sql_compile, "_plan_read_shape", read_shape)
    monkeypatch.setattr(_inheritance, "plan_document_reads", document_reads)
    monkeypatch.setattr(_StorageLayoutFacet, "position", position)
    monkeypatch.setattr(sql_compile, "_render_shared_sources", render)
    return reuse


def assert_planned_once(reuse: PlanReuse) -> ReadShape:
    """The one physical plan a compilation made, after checking that it asked
    the storage owner for one Position Layout and planned its documents once,
    and retains both answers rather than copies of them."""
    (shape,) = reuse.read_shapes
    (layout,) = reuse.position_layouts
    ((shared, direct),) = reuse.document_reads
    assert shape.layout is layout
    assert shape.shared_document is shared
    assert shape.direct_documents is direct
    return shape


def reaches_compilation_state(root: object) -> bool:
    """Whether a statement plan, a lexical plan, or a statement builder is
    reachable from ``root``, ignoring what only a class or module holds."""
    module_namespaces = {id(vars(module)) for module in tuple(sys.modules.values())}
    seen: set[int] = set()
    pending = [root]
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, (StatementPlan, LexicalScopePlan, StatementBuilder)):
            return True
        if isinstance(current, (type, ModuleType)) or id(current) in module_namespaces:
            continue
        pending.extend(gc.get_referents(current))
    return False
