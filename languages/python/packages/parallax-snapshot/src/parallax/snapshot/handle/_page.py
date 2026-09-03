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
anything is converted, deep-fetched, or classified. Everything that decision is
made of — :meth:`PagePlan.page_request` and :func:`page_decision` — is
computation over counts and coordinates with no port and no SQL under it, which
is what lets the lookahead discard, the tie, and the maximal strict prefix be
exercised directly. It stays an internal seam of this module either way:
:func:`read_stream_page`'s own interface never exposes it, and the stream's
surface above is what the behavior is graded through.

:class:`StreamPage` never surfaces publicly. Cursor state is not a thing a
caller of a Snapshot Stream holds, so neither the eager
:class:`~parallax.snapshot.materialize.SnapshotGraph` nor
:class:`~parallax.snapshot._read_result.FindResult` grows a field for it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import cast

from parallax.core.continuation import ContinuationPlan
from parallax.core.db_port import DbPort
from parallax.core.entity._layout import CatalogedModel
from parallax.core.execution_lifecycle._activity import INERT, DatabaseCallScope
from parallax.core.metamodel import AttributeIdentity
from parallax.core.object_query._validated import ContinuationCoordinate
from parallax.core.sql_gen import SqlGenError
from parallax.core.unit_work import Concurrency
from parallax.snapshot.handle._read import RootRead, build_graph, read_roots
from parallax.snapshot.handle._write_inputs import ObservationLedger, ReadSources
from parallax.snapshot.materialize import SnapshotGraph, UnwindTree

__all__ = [
    "At",
    "PagePlan",
    "PageRequest",
    "PageVerdict",
    "StreamPage",
    "TieFound",
    "page_decision",
    "read_stream_page",
]


@dataclass(frozen=True, slots=True)
class PageRequest:
    """How many roots one page asks for, and how its answer is to be read.

    ``lookahead`` is the whole difference between the two kinds of page. With
    one, ``size`` is a root MORE than the page may deliver, so a full result
    means "one more root exists" and a short one proves exhaustion outright. On
    a final page there is no such root to ask for, and a full result proves
    nothing about what follows — the authored limit settles it instead.

    ``emitted`` travels with them because a tie's ordinal counts from the start
    of the delivery rather than from the start of this page.
    """

    size: int
    lookahead: bool
    emitted: int


@dataclass(frozen=True, slots=True)
class TieFound:
    """Two adjacent roots one page's statement evaluated to ONE coordinate.

    The Continuation Order is total over storage the model describes, so this is
    storage that has lost a constraint the order rests on. Everything the
    refusal reports is settled here, where it was discovered: ``terms`` is the
    order that turned out not to be total, ``ordinal`` counts the first
    undeliverable root from the start of the delivery, and ``coordinate`` is the
    inert diagnostic copy of where it stood — never a coordinate, which is
    pagination authority.
    """

    terms: tuple[AttributeIdentity, ...]
    ordinal: int
    coordinate: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class PageVerdict:
    """Which of a page's roots survive, and what the delivery does after them.

    ``keep`` is the count taken from the FRONT of what the statement returned:
    the discarded lookahead root and every root from a tie onwards are the same
    kind of thing to everything downstream — read, never converted.
    """

    keep: int
    exhausted: bool
    tie: TieFound | None


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

    def page_request(self, emitted: int) -> PageRequest:
        """What the page after ``emitted`` asks the database for.

        A page reads one root PAST its batch, which is what proves exhaustion
        without a terminal statement that returns nothing and what puts the
        first root of the next page inside this page's own tie scan — a tie
        with it would otherwise be stepped straight over by a strict seek.

        An authored limit is a hard database-read and locking boundary rather
        than a filter applied afterwards, so the final page it caps asks for
        exactly what is left of it and reads no excluded root merely to inspect
        a boundary tie. The tie there goes undetected, and no later seek exists
        that could skip it.
        """
        if self.limit is None or self.limit - emitted > self.batch_size:
            return PageRequest(size=self.batch_size + 1, lookahead=True, emitted=emitted)
        return PageRequest(size=self.limit - emitted, lookahead=False, emitted=emitted)


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

    ``coordinates`` is one per root this page KEEPS, so a root the page read and
    discarded — the lookahead, or one at a tie — is absent from it exactly as it
    is absent from the graph.

    ``tie`` is present where the delivery can go no further because two adjacent
    roots stood at one coordinate. The page reports it rather than raising: this
    page's kept roots are published first, and the refusal follows them.
    """

    graph: SnapshotGraph
    includes: UnwindTree
    sources: ReadSources
    coordinates: tuple[ContinuationCoordinate, ...]
    exhausted: bool
    tie: TieFound | None

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
    coordinate the last root the page before it KEPT stood at. The roots come
    back, their coordinates are lifted off them, and only then is the graph
    below them built: the ``1 + L`` shape of a page is an eager read's, so ``model``,
    ``port``, ``preference``, ``ledger``, and ``calls`` are the executor's own
    and every level below the root derives its lock, its retained evidence, and
    its Database Call bracket from them exactly as an eager find does.

    The roots the verdict discards are read and nothing more: the graph is built
    from the kept prefix alone, so a discarded root is never deep-fetched,
    converted, classified, or published, and its children are never fetched
    beside another page's.
    """
    request = page_plan.page_request(at.emitted)
    query = (
        page_plan.plan.first(limit=request.size)
        if at.coordinate is None
        else page_plan.plan.after(at.coordinate, limit=request.size)
    )
    root_read = read_roots(query, model, port, preference=preference, calls=calls)
    coordinates = _coordinates(root_read)
    terms = tuple(term.member.identity for term in query.order_by)
    verdict = page_decision(request, terms, coordinates)
    kept = replace(root_read, rows=root_read.rows[: verdict.keep])
    result = build_graph(kept, model, port, preference=preference, ledger=ledger, calls=calls)
    return StreamPage(
        graph=result.graph,
        includes=result.includes,
        sources=result.sources,
        coordinates=coordinates[: verdict.keep],
        exhausted=verdict.exhausted,
        tie=verdict.tie,
    )


def page_decision(
    request: PageRequest,
    terms: tuple[AttributeIdentity, ...],
    coordinates: tuple[ContinuationCoordinate, ...],
) -> PageVerdict:
    """Which of the roots a page returned it may deliver, and what follows them.

    A scan over the coordinates and nothing else. Sameness is the coordinate's
    own rule — comparing carriers here would put a provider judgment where no
    provider knowledge is — and the scan covers the lookahead root, which is
    what makes a tie that spans a page boundary reachable at all: resuming from
    a kept root that ties with the root after it emits a strict comparison
    stepping over its twin.

    A tie at ``index`` means the tied group starts at ``index - 1``, so the kept
    prefix is the maximal strictly ordered one and the coordinate after it is
    the first undeliverable root. Keeping nothing is ordinary: the page
    publishes no root and the delivery refuses immediately.

    ``terms`` is the Continuation Order those coordinates were evaluated
    against, positionally, and is reported by a tie alone.
    """
    for index in range(1, len(coordinates)):
        if coordinates[index] == coordinates[index - 1]:
            keep = index - 1
            return PageVerdict(
                keep=keep,
                exhausted=True,
                tie=TieFound(
                    terms=terms,
                    ordinal=request.emitted + keep,
                    coordinate=coordinates[keep].snapshot(),
                ),
            )
    if request.lookahead and len(coordinates) == request.size:
        return PageVerdict(keep=request.size - 1, exhausted=False, tie=None)
    return PageVerdict(keep=len(coordinates), exhausted=True, tie=None)


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
