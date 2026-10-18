"""Observations of how one compilation plans its statement and renders its roots.

The recorder wraps the compiler's real planner and root-source renderer, so a
test sees every production ``plan_statement`` invocation and every lexical root
a builder renders, without a fake planner or a testing-only hook.
"""

from __future__ import annotations

import gc
import sys
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any

import pytest

from parallax.core.sql_gen import _compile as sql_compile
from parallax.core.sql_gen import _planning
from parallax.core.sql_gen._context import StatementBuilder
from parallax.core.sql_gen._planning import LexicalScopeId, LexicalScopePlan, StatementPlan
from parallax.core.sql_gen._predicate import EntityRowScope, render_shared_sources


@dataclass(frozen=True, slots=True)
class RenderedRoot:
    statement_plan: StatementPlan
    scope_id: LexicalScopeId
    row: EntityRowScope


@dataclass(slots=True)
class PlanReuse:
    plans: list[StatementPlan] = field(default_factory=list[StatementPlan])
    roots: list[RenderedRoot] = field(default_factory=list[RenderedRoot])


def record_plan_reuse(monkeypatch: pytest.MonkeyPatch) -> PlanReuse:
    reuse = PlanReuse()
    real_plan = _planning.plan_statement

    def plan(*args: Any, **kwargs: Any) -> StatementPlan:
        reuse.plans.append(real_plan(*args, **kwargs))
        return reuse.plans[-1]

    def render(statement_plan: StatementPlan, scope_id: LexicalScopeId, row: EntityRowScope) -> str:
        reuse.roots.append(RenderedRoot(statement_plan, scope_id, row))
        return render_shared_sources(statement_plan, scope_id, row)

    monkeypatch.setattr(sql_compile, "_plan_statement", plan)
    monkeypatch.setattr(sql_compile, "_render_shared_sources", render)
    return reuse


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
