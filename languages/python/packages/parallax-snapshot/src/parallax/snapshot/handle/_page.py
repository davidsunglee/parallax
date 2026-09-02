"""``parallax.snapshot.handle._page`` — one page of a streamed read (m-snapshot-read).

The one deep operation a stream's loop is written against: it is told where the
delivery stands and answers the page that continues it. Everything paging is
made of — how many roots to ask for, which node asks for them, which of the
returned roots survive, and where the next page resumes — is settled inside,
because those facts only agree when one operation owns all of them. A caller
that computed the request itself and then built a query from it could read one
page with another page's request, and the failure that admits is exactly the
one this design exists to prevent: a silently skipped root.

The cut lands between the root statement and conversion, where
:func:`~parallax.snapshot.handle._read.find` has its one joint: a page's
decision reads coordinates alone, and coordinates are lifted off the rows before
anything is converted, deep-fetched, or classified.

:class:`StreamPage` never surfaces publicly. Cursor state is not a thing a
caller of a Snapshot Stream holds, so neither the eager
:class:`~parallax.snapshot.materialize.SnapshotGraph` nor
:class:`~parallax.snapshot._read_result.FindResult` grows a field for it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from parallax.core.continuation import ContinuationPlan
from parallax.core.db_port import DbPort
from parallax.core.entity._layout import CatalogedModel
from parallax.core.execution_lifecycle._activity import INERT, DatabaseCallScope
from parallax.core.object_query._validated import ContinuationCoordinate
from parallax.core.sql_gen import SqlGenError
from parallax.core.unit_work import Concurrency
from parallax.snapshot.handle._read import RootRead, build_graph, read_roots
from parallax.snapshot.handle._write_inputs import ObservationLedger, ReadSources
from parallax.snapshot.materialize import SnapshotGraph, UnwindTree

__all__ = ["At", "PagePlan", "StreamPage", "read_stream_page"]


@dataclass(frozen=True, slots=True)
class PagePlan:
    """How one delivery pages: its page nodes and the two counts bounding them.

    All three are fixed for a delivery's whole life and mean nothing apart —
    ``batch_size`` is how many roots a page asks for, ``limit`` is the authored
    cap the delivery may never read past, and ``plan`` is what turns either into
    a node. Carrying them as one value is what leaves the stream holding a
    position and nothing else.
    """

    plan: ContinuationPlan
    batch_size: int
    limit: int | None

    def size(self, emitted: int) -> int:
        """How many roots the page after ``emitted`` asks for.

        An authored limit is a hard database-read boundary rather than a filter
        applied afterwards, so a final page asks only for what is left of it.
        """
        if self.limit is None:
            return self.batch_size
        return min(self.batch_size, self.limit - emitted)


@dataclass(frozen=True, slots=True)
class At:
    """Where a delivery stands: what it last delivered, and how much.

    ``coordinate`` is absent on the first page alone. It is the coordinate the
    DATABASE evaluated for the last root the previous page kept, which is what
    lets a delivery resume past a root whose stored data contradicted the model.
    """

    coordinate: ContinuationCoordinate | None
    emitted: int


@dataclass(frozen=True, slots=True)
class StreamPage:
    """One page's sealed graph, what it stands at, and whether more follow.

    ``graph``, ``includes``, and ``sources`` are exactly what an eager
    :class:`~parallax.snapshot._read_result.FindResult` carries, because a page
    IS an eager read of a bounded root query — the publication seam above is the
    same one, and only which graphs it is handed differs.
    """

    graph: SnapshotGraph
    includes: UnwindTree
    sources: ReadSources
    coordinates: tuple[ContinuationCoordinate, ...]
    exhausted: bool

    @property
    def resume_from(self) -> ContinuationCoordinate | None:
        """The coordinate the next page seeks past, or absence for an empty page.

        A property rather than a call-site subscript: "seek from the last root
        this page KEPT" is the rule the whole design rests on, and a subscript
        is something a caller can get one off.
        """
        return self.coordinates[-1] if self.coordinates else None

    @property
    def delivered(self) -> int:
        """How many roots this page publishes.

        Derived rather than stored, so it cannot disagree with the coordinates
        it counts.
        """
        return len(self.coordinates)


def read_stream_page(
    page_plan: PagePlan,
    at: At,
    model: CatalogedModel,
    port: DbPort,
    *,
    preference: Concurrency | None = None,
    ledger: ObservationLedger | None = None,
    calls: DatabaseCallScope = INERT,
) -> StreamPage:
    """Read and seal the page of ``page_plan`` that follows ``at``.

    The node is this plan's own — the caller's query under the Continuation
    Order, capped at the size this position asks for, and seeking past the
    coordinate the last delivered root stood at. The roots come back, their
    coordinates are lifted off them, and only then is the graph below them
    built: the ``1 + L`` shape of a page is an eager read's, so ``model``,
    ``port``, ``preference``, ``ledger``, and ``calls`` are the executor's own
    and every level below the root derives its lock, its retained evidence, and
    its Database Call bracket from them exactly as an eager find does.

    A short page proves exhaustion — fewer roots than asked for means no more
    exist — and a full one does not, so it costs one more root statement,
    unless an authored ``limit`` has by then been delivered in full.
    """
    size = page_plan.size(at.emitted)
    query = (
        page_plan.plan.first(limit=size)
        if at.coordinate is None
        else page_plan.plan.after(at.coordinate, limit=size)
    )
    root_read = read_roots(query, model, port, preference=preference, calls=calls)
    coordinates = _coordinates(root_read)
    result = build_graph(root_read, model, port, preference=preference, ledger=ledger, calls=calls)
    delivered = at.emitted + len(coordinates)
    return StreamPage(
        graph=result.graph,
        includes=result.includes,
        sources=result.sources,
        coordinates=coordinates,
        exhausted=len(coordinates) < size
        or (page_plan.limit is not None and delivered >= page_plan.limit),
    )


def _coordinates(root_read: RootRead) -> tuple[ContinuationCoordinate, ...]:
    """Every root's evaluated coordinate, in the order the database placed them.

    A paging read captures one cell per Continuation Order term for every row it
    returns, so a root without a coordinate is a violation of the m-sql / port
    contract rather than an ordinary stored-data state — invalid stored data
    reaches here with its coordinate intact, which is the whole point.
    """
    coordinates = tuple(row.coordinate for row in root_read.rows)
    if any(coordinate is None for coordinate in coordinates):  # pragma: no cover - see above
        raise SqlGenError("a paging read returned a root carrying no evaluated coordinate")
    return cast("tuple[ContinuationCoordinate, ...]", coordinates)
