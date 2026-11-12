from __future__ import annotations

from parallax.core.execution_lifecycle._activity import INERT, DatabaseCallScope
from parallax.core.internal.concurrency import ConcurrencyPreference
from parallax.core.internal.db_port import DatabaseConnection
from parallax.core.internal.entity._layout import CatalogedModel
from parallax.core.internal.object_query._resolved import ResolvedObjectQuery
from parallax.core.internal.read_delivery._page import INERT_OBSERVER, MaterializationObserver
from parallax.core.internal.read_delivery._page_reader import (
    EagerPageResult,
    HistoryPageResult,
    PageOriginCollector,
    PageReadContext,
    PageReader,
)
from parallax.core.internal.read_delivery._publication import Publication
from parallax.core.internal.read_delivery._read_plan import (
    UNCACHED_READ_PLANNER,
    ReadPlan,
    ReadPlanner,
)

__all__ = ["deliver_find", "deliver_history", "find", "find_history"]


def find[Origin](
    query: ResolvedObjectQuery,
    model: CatalogedModel,
    port: DatabaseConnection,
    *,
    origin_collector: PageOriginCollector[Origin],
    preference: ConcurrencyPreference | None = None,
    calls: DatabaseCallScope = INERT,
    observer: MaterializationObserver = INERT_OBSERVER,
    edition: str = "",
    planner: ReadPlanner = UNCACHED_READ_PLANNER,
) -> EagerPageResult[Origin]:
    plan = planner.plan(
        edition=edition, model=model, dialect=port.dialect, query=query, preference=preference
    )
    return PageReader(observer).read_page(plan, PageReadContext(port, calls, origin_collector))


def find_history(
    query: ResolvedObjectQuery,
    model: CatalogedModel,
    port: DatabaseConnection,
    *,
    read: DatabaseCallScope = INERT,
    observer: MaterializationObserver = INERT_OBSERVER,
    edition: str = "",
    preference: ConcurrencyPreference | None = None,
    planner: ReadPlanner = UNCACHED_READ_PLANNER,
) -> HistoryPageResult:
    plan = planner.plan(
        edition=edition, model=model, dialect=port.dialect, query=query, preference=preference
    )
    assert plan.milestones is not None
    stage = PageReader(observer).read_page(plan, PageReadContext(port, read))
    return HistoryPageResult(stage.page, plan.milestones, stage.includes)


def deliver_find[Origin, Eager](
    plan: ReadPlan,
    context: PageReadContext[Origin],
    publication: Publication[Origin, Eager],
    *,
    observer: MaterializationObserver = INERT_OBSERVER,
) -> Eager:
    return publication.from_find(PageReader(observer).read_page(plan, context))


def deliver_history[Origin, Eager](
    plan: ReadPlan, context: PageReadContext[Origin], publication: Publication[Origin, Eager]
) -> Eager:
    assert plan.milestones is not None
    stage = PageReader().read_page(plan, context)
    return publication.from_history(HistoryPageResult(stage.page, plan.milestones, stage.includes))
