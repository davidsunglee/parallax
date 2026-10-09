from __future__ import annotations

from parallax.core import continuation, temporal_read
from parallax.core.db_port import DatabaseConnection
from parallax.core.entity._layout import CatalogedModel
from parallax.core.execution_lifecycle._activity import INERT, DatabaseCallScope
from parallax.core.metamodel import EntityMetadata, Metamodel
from parallax.core.object_query._resolved import ResolvedObjectQuery
from parallax.core.read_delivery._fetch import execute_read
from parallax.core.read_delivery._page import INERT_OBSERVER, MaterializationObserver
from parallax.core.read_delivery._page_reader import (
    EagerPageRequest,
    EagerPageResult,
    FlatPageRequest,
    HistoryPageResult,
    PageOrigins,
    PageReader,
)
from parallax.core.read_delivery._publication import Publication
from parallax.core.read_delivery._read_plan import UNCACHED_READ_PLANNER, ReadPlanner
from parallax.core.temporal_read import Pin, TemporalShape
from parallax.core.unit_work import Concurrency

__all__ = [
    "deliver_find",
    "deliver_history",
    "find",
    "find_history",
    "temporal_shape",
]


def find[Origin](
    query: ResolvedObjectQuery,
    model: CatalogedModel,
    port: DatabaseConnection,
    *,
    origins: PageOrigins[Origin],
    preference: Concurrency | None = None,
    calls: DatabaseCallScope = INERT,
    observer: MaterializationObserver = INERT_OBSERVER,
    edition: str = "",
    planner: ReadPlanner = UNCACHED_READ_PLANNER,
) -> EagerPageResult[Origin]:
    """The whole-result read: every root ``query`` matches, with its included values.

    ``query`` is the read's canonical Object Query: one carrying Include Paths,
    or any other query planned with zero levels (root-only instance-form
    materialization).

    ``model`` is the connected model as one value: the accepted Metamodel every
    level's own Entity resolves against, and the exact-model layout catalog
    every level's conversion reads its applicable member set from. The two
    travel together rather than as two arguments, so no read can be handed
    layouts derived from a model other than the one it resolves against.

    ``preference`` is the owning unit of work's Concurrency Preference, and
    EVERY level derives its own read lock from it against that level's own
    target Entity: a versioned root reads lock-free while an unversioned
    included Entity in the same transaction takes the shared lock. Omitting it
    is how a non-transactional read locks nothing at all.

    ``origins`` observes every converted projection and answers the sealed
    Page's origins, which the result carries by reference.

    ``calls`` is the scope this read brackets its Database Calls against: the
    Read the owning operation opened. Passing the shared inert activity runs
    the same code and emits nothing.
    """
    return PageReader(observer).read_page(
        EagerPageRequest(query, model, port, preference, origins, calls, planner, edition)
    )


def find_history(
    query: ResolvedObjectQuery,
    model: CatalogedModel,
    port: DatabaseConnection,
    *,
    read: DatabaseCallScope = INERT,
    observer: MaterializationObserver = INERT_OBSERVER,
    edition: str = "",
    preference: Concurrency | None = None,
    planner: ReadPlanner = UNCACHED_READ_PLANNER,
) -> HistoryPageResult:
    """The flat milestone-set read.

    ``history`` and ``asOfRange`` return the full matching milestone sequence in
    one statement and one Page. Continuation order is authored before SQL
    compilation, so the flat roots already rank by logical key and canonical axis
    starts. A milestone-set query carries no includes, so the Page schema is
    root-only, and it observes no origin.
    """
    meta = model.meta
    ordered = continuation.ordered(query, meta)
    plan = planner.plan(
        edition=edition,
        model=model,
        dialect=port.dialect,
        query=ordered,
        result_form="instance",
        preference=preference,
    )
    if plan.fetch_count:  # pragma: no cover - validated milestone queries cannot include
        # m-case-format: a v1 milestone-set read carries no includes.
        raise ValueError("a milestone-set (history / asOfRange) read carries no fetch steps")
    compiled, converter = plan.root_read()

    stage = PageReader(observer).read_page(
        FlatPageRequest(
            model, compiled, lambda: execute_read(port, compiled, read), Pin(), converter
        )
    )
    return HistoryPageResult(
        page=stage.page, milestones=temporal_shape(meta, query.root), includes=plan.include_tree()
    )


def temporal_shape(meta: Metamodel, entity: EntityMetadata) -> TemporalShape:
    """``entity``'s family Temporal Shape, which every milestone edge of a read
    targeting it is read against.

    Temporality is family-wide (`m-inheritance`), so a milestone edge reads the
    family's shared Temporal Shape rather than the queried target's own,
    possibly locally empty, axes.
    """
    shape = temporal_read.view(meta).shape(entity.identity)
    if shape is None:  # pragma: no cover - the facet covers every accepted Entity
        raise RuntimeError(f"{entity.identity.canonical}: no Temporal Facet shape")
    return shape


def deliver_find[Origin, Eager](
    request: EagerPageRequest[Origin],
    publication: Publication[Origin, Eager],
    *,
    observer: MaterializationObserver = INERT_OBSERVER,
) -> Eager:
    """One whole-result read published as ``publication``'s eager envelope."""
    return publication.from_find(PageReader(observer).read_page(request))


def deliver_history[Origin, Eager](
    query: ResolvedObjectQuery,
    model: CatalogedModel,
    port: DatabaseConnection,
    *,
    publication: Publication[Origin, Eager],
    read: DatabaseCallScope,
    edition: str,
    preference: Concurrency | None,
    planner: ReadPlanner,
) -> Eager:
    """One milestone-set read published as ``publication``'s eager envelope."""
    return publication.from_history(
        find_history(
            query,
            model,
            port,
            read=read,
            edition=edition,
            preference=preference,
            planner=planner,
        )
    )
