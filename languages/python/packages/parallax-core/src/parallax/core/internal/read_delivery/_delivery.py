from __future__ import annotations

from parallax.core.internal.read_delivery._page_reader import (
    HistoryPageResult,
    PageReadContext,
    read_page,
)
from parallax.core.internal.read_delivery._publication import Publication
from parallax.core.internal.read_delivery._read_plan import ReadPlan

__all__ = ["deliver_find", "deliver_history"]


def deliver_find[Origin, Eager](
    plan: ReadPlan, context: PageReadContext[Origin], publication: Publication[Origin, Eager]
) -> Eager:
    return publication.from_find(read_page(plan, context))


def deliver_history[Origin, Eager](
    plan: ReadPlan, context: PageReadContext[Origin], publication: Publication[Origin, Eager]
) -> Eager:
    assert plan.milestones is not None
    stage = read_page(plan, context)
    return publication.from_history(HistoryPageResult(stage.page, plan.milestones, stage.includes))
