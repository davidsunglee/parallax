"""The streamed read's memory bound, measured (`cost` class).

A streamed read exists to make the Parallax-owned working set independent of the
total number of roots. `m-snapshot-read` *What a delivery costs* states the bound
in three layers — one page's sealed graph at `O(P_B)`, the current root's merge
and classification at `O(G_max)`, and its construction or Wire unwind at
`O(G_max)` — and names three exclusions. This suite is the instrument for the
whole bound and for both exclusions, in both namespaces.

**Two of the three layers are priced separately; the middle one is graded by its
RELEASE.** A page graph and a published root are both alive at the sample point
and each carries its own coefficient, so the census prices them apart. The merge
between them is not alive at any point a sample can be taken from outside the
delivery — it is built and dropped inside one publication — and it borrows the
page graph's own arrays rather than copying them, so even held deliberately its
closure is dominated by structure the first layer has already been charged for.
What is stated about it here is therefore what the spec's release column states
and what a sample between two roots can settle: no merge survives the root it
published. A merge kept for the page, or kept past its root, fails that at every
point of the grid; a merge whose peak exceeds one root while it lives is what no
instrument outside the delivery separates from the page it was scoped from.

**Six readings, each its own statement.** Page graphs do not accumulate with the
result. A delivery holds one page graph and one published root at a time, and the
survivor census says so in arithmetic rather than in prose: it is exactly affine
in the page's own node population and the published root's, with **no term in the
total result size and none in how far the delivery has got**. The two exclusions
are demonstrated rather than asserted — a caller retaining every root reproduces
the `O(N)` growth the bound declines to prevent, and a writing loop's buffer
grows with the page size and stops there.

**The exclusions are what make the first four readings mean anything.** A bound
that excluded nothing would be a claim about the caller's program rather than
about Parallax, so the price of one root comes from the retaining arm — what one
root of THIS graph costs on THIS interpreter — and the streamed arm has to come
in under one of them across nine times as many roots.

**The census is pinned as exact counts rather than fitted, and that is what sees
a constant.** Every byte reading here is a DIFFERENCE — one result size against
another, one position against another — so a page graph held one page too long
cancels out of all of them and is invisible to the instrument that measures
bytes. The census is the reading that is not a difference: its coefficients are
literals, every one of them names what it counts, and a second live page graph
fails it at every point of the grid.

**The census is read four ways, because counting Parallax's own objects is blind
where the bound is weakest.** A page graph or a root is a kind Parallax defines
and is counted; a built-in `list` the delivery banks one item into per PAGE is
not, and past the first page it adds no survivor of any kind — while every byte
reading here compares two arms standing at the same position, which is to say
having read the same number of pages. So the counts are taken over every survivor
whatever defined its type, over the REFERENCES those survivors hold, and from the
heap's side over what a holder older than the window took. The reference count is
the one that prices a page: two sample positions differ by the pages between them,
and pages grow with `N`.

Every reading reads a whole interpreter, so each runs in one of its own behind
``in_a_child_interpreter`` and the class is CI's rather than the merge gate's.
The machine-relative figures — what a page and a root cost in bytes on one
machine — are `tools/stream_overhead.py`'s and are recorded in
`docs/stream-baseline.md`; nothing here reads a byte total as a verdict.
"""

from __future__ import annotations

import datetime as dt
import gc
import sys
import tracemalloc
from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Any, Final, NamedTuple, cast

from memory_instruments import (
    Seam,
    in_a_child_interpreter,
    live_graph,
    retained,
    serve_one_measurement,
    warmed,
)

from _support.db_port import body_outcome
from parallax.conformance.story_models import ACCOUNT_MODEL, ORDERS_MODEL, Account, Order
from parallax.core.db_port import DbPort, DocumentReadOrdinals, Row, TransactionOutcome
from parallax.core.object_query._fluent import ObjectQuery
from parallax.snapshot import SnapshotStream
from parallax.snapshot.handle import Database, Transaction
from parallax.snapshot.materialize import SnapshotGraph
from parallax.snapshot.materialize._graph import GraphRows
from parallax.snapshot.materialize._merge import GraphMerge

_SMALL: Final = 20
"""Roots in the small reading — enough for several pages at the page size below."""

_MID: Final = 40
"""Twice the small reading. What the retaining arm's linearity is read from: two
differences over the same baseline, whose ratio is the ratio of their own root
counts if and only if the growth is proportional to the result."""

_LARGE: Final = 200
"""Ten times the small reading, which is the whole shape of the claim: what the
stream keeps may not scale with this number."""

_BATCH: Final = 8
"""Root positions per page. Small enough that both readings page many times, so
what is measured is the steady state rather than one page holding everything."""

_FANOUT: Final = 2
"""Included children per root, so a page graph holds relationship fanout rather
than bare roots and `P_B` is measured over something with depth."""

_PAGE_SIZES: Final = (2, 4, 8)
"""The page sizes the census grid varies, holding everything else fixed."""

_FANOUTS: Final = (1, 2, 3)
"""The fanouts it varies beside them, so the page term and the root term move
independently rather than through one product neither could be read out of."""

_AT: Final = 20
"""Roots consumed before the census sample. Deliberately not a multiple of every
page size in the grid, so the sample lands mid-page at some points and on a page
boundary at others and the reading is the same at both."""

_FURTHER: Final = 37
"""A second, later sample position. The census at ``_AT`` and at this must agree:
what a delivery holds is what it holds at every point of the same delivery."""

_TENFOLD: Final = 10
"""The factor between the two result sizes every independence reading is taken
at."""


def _order_row(order_id: int) -> Row:
    return {
        "id": order_id,
        "name": f"order-{order_id}",
        "sku": "A-100",
        "qty": 5,
        "price": Decimal("10.50"),
        "active": True,
        "ordered_on": dt.date(2024, 1, 5),
    }


def _item_row(item_id: int, order_id: int) -> Row:
    return {
        "id": item_id,
        "order_id": order_id,
        "sku": "SKU",
        "quantity": 1,
        "shipped_on": dt.date(2024, 2, 1),
    }


def _account_row(account_id: int) -> Row:
    return {
        "id": account_id,
        "owner": f"owner-{account_id}",
        "balance": Decimal("100.00"),
        "version": 1,
    }


class _GeneratingPort:
    """A port that answers each page from a counter and retains nothing.

    A recording port would grow with the result on its own and swamp the reading
    it is there to take, so this one holds exactly the page it last answered:
    the parent keys the child level is about to gather, and how far through the
    result it is.
    """

    __slots__ = ("_delivered", "_fanout", "_page", "_total")

    def __init__(self, total: int, fanout: int = _FANOUT) -> None:
        self._total = total
        self._fanout = fanout
        self._delivered = 0
        self._page: tuple[int, ...] = ()

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        del document_reads
        if "order_item t0" in sql:
            return [
                _item_row(parent * 100 + offset, parent)
                for parent in self._page
                for offset in range(self._fanout)
            ]
        self._page = self._next_page(cast("int", binds[-1]))
        return [_order_row(order_id) for order_id in self._page]

    def _next_page(self, size: int) -> tuple[int, ...]:
        taken = min(size, self._total - self._delivered)
        page = tuple(range(self._delivered + 1, self._delivered + taken + 1))
        self._delivered += taken
        return page

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise NotImplementedError

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:  # pragma: no cover
        raise NotImplementedError


class _WritingPort(_GeneratingPort):
    """The same generator over a model a loop can write, answering every write
    and recording none of them.

    The buffer is the subject of the reading it serves, so what the port must not
    do is accumulate beside it: a recorded statement per write would grow with
    the result and report the buffer's bound as broken when nothing about the
    buffer moved.
    """

    __slots__ = ()

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        del document_reads, sql
        return [_account_row(account_id) for account_id in self._next_page(cast("int", binds[-1]))]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        del sql, binds
        return 1

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:
        del isolation
        return body_outcome(cast("DbPort", self), body)


def _query() -> ObjectQuery[Order, Order]:
    return Order.where(Order.active == True).include(Order.items)  # noqa: E712 - the query algebra's own equality


type _Opener = Callable[[Database, int], SnapshotStream[Any]]


def _typed_stream(database: Database, batch_size: int) -> SnapshotStream[Any]:
    return database.stream(_query(), batch_size=batch_size)


def _wire_stream(database: Database, batch_size: int) -> SnapshotStream[Any]:
    return database.wire.stream(_query(), batch_size=batch_size)


class _Namespace(NamedTuple):
    """One representation's stream, and the exact census a delivery of it leaves
    alive at any point of itself.

    The three counts are the bound restated as objects. ``fixed`` is everything
    sized by the plan and the handle rather than by the data — the schema, the
    layouts, the query, the continuation, the delivery, and the connected model.
    ``per_page_node`` is what the sealed page graph holds for each node it
    carries, so the page term is that count times the page's own root positions
    times one root plus its fanout. ``per_published_node`` is what one published
    root graph holds for each of ITS nodes, which is the same product with the
    page size taken out of it.

    Nothing in either product is the total result size, and nothing is how far
    the delivery has got. That absence is the claim.
    """

    name: str
    opener: _Opener
    fixed: int
    per_page_node: int
    per_published_node: int

    def survivors_for(self, *, batch_size: int, fanout: int) -> int:
        nodes_per_root = 1 + fanout
        return (
            self.fixed
            + self.per_page_node * batch_size * nodes_per_root
            + self.per_published_node * nodes_per_root
        )


_TYPED: Final = _Namespace("typed", _typed_stream, fixed=35, per_page_node=2, per_published_node=2)
"""The Typed lane. Two objects per page node — the Source Hint a page retains for
it and the Object Key that hint is filed under — and two per published node, the
frozen Entity instance and the node state naming what it was read from."""

_WIRE: Final = _Namespace("wire", _wire_stream, fixed=36, per_page_node=2, per_published_node=1)
"""The Wire lane. The same page term, because retention is a property of the read
rather than of the representation, and one object per published node: an unwound
value tree carries its own state in the tree rather than beside it. One MORE
fixed object than the Typed lane — the frozen sequence the published root's one
included relationship is spelled as, which a Typed root answers from its node
state instead. It is fixed rather than per-node because there is one of them per
relationship the include tree names, whatever the fan-out inside it."""

_NAMESPACES: Final = (_TYPED, _WIRE)


def _draining(namespace: _Namespace, total: int, *, retaining: bool) -> Seam:
    """One whole stream of ``total`` roots, sampled with the last page still open.

    The handle and the port are built inside the seam, so everything the reading
    could attribute to the stream was allocated inside its own window.
    """

    def seam(sample: Callable[[], None]) -> None:
        database = Database(cast("DbPort", _GeneratingPort(total)), ORDERS_MODEL)
        held: list[Any] = []
        with namespace.opener(database, _BATCH) as stream:
            for root in stream:
                if retaining:
                    held.append(root)
            sample()
        held.clear()

    return seam


def _paused(namespace: _Namespace, total: int, *, batch_size: int, fanout: int, at: int) -> Seam:
    """A delivery of ``total`` roots sampled while it is still running, holding
    the root at position ``at`` exactly as a caller's loop body holds it.

    Stopping there rather than draining is what makes the reading a statement
    about the STEADY state: everything the delivery published before this root
    is behind it, and everything after it has not been read. The root stays BOUND
    at the sample point, because a loop body holding what it was handed is what
    the bound's second and third layers are about.
    """

    def seam(sample: Callable[[], None]) -> None:
        database = Database(cast("DbPort", _GeneratingPort(total, fanout)), ORDERS_MODEL)
        with namespace.opener(database, batch_size) as stream:
            for position, _root in enumerate(stream):
                if position == at:
                    sample()
                    return

    return seam


def _writing(total: int, *, batch_size: int, at: int, writes: bool) -> Seam:
    """A participating delivery of ``total`` roots whose loop writes every root,
    sampled at position ``at`` with that page's writes still buffered.

    The read-only arm beside it is the same loop with the write removed, so what
    the pair reports is the buffer's own price rather than the transaction's.
    """

    def seam(sample: Callable[[], None]) -> None:
        database = Database(cast("DbPort", _WritingPort(total)), ACCOUNT_MODEL)

        def body(tx: Transaction) -> None:
            with tx.stream(Account.where(Account.id >= 1), batch_size=batch_size) as stream:
                for position, account in enumerate(stream):
                    if writes:
                        tx.update(account.edit(balance=Decimal("125.00")))
                    if position == at:
                        sample()
                        return

        database.transact(body)

    return seam


def _parallax_survivors(seam: Seam) -> list[object]:
    """Every object of Parallax's own that ``seam`` leaves alive at its sample
    point, whatever kind it is."""
    return [obj for obj in live_graph(warmed(seam)).survivors if _defined_by_parallax(type(obj))]


def _defined_by_parallax(kind: type) -> bool:
    return kind.__module__.startswith("parallax.")


class _Live(NamedTuple):
    """What a running delivery holds, read four ways from one sample, because
    each answers what the other three cannot.

    ``parallax`` is what Parallax's own structure costs, and ``tracked`` is every
    survivor whatever defined its type, so anything the delivery banks in a
    built-in list, dict, or set — invisible to the first, because ``list`` is not
    a kind Parallax defines — lands in the second. ``references`` is what neither
    count can see: one container is one object however many things it points at,
    so a delivery keeping one item per PAGE moves no count at all and moves this
    by one for every page it has read. ``inbound`` is the same reading from the
    other end, and the only one that sees a holder OLDER than the window: what a
    pre-existing registry took is counted where it points rather than where it is
    held.

    All four are counts of structure rather than readings of an allocator, so all
    four are exact — and none of them sees what a holder that predates the window
    keeps of values the collector never tracked, which is what the byte readings
    are taken beside them for.
    """

    parallax: int
    tracked: int
    references: int
    inbound: int


def _census(seam: Seam) -> tuple[_Live, dict[str, int]]:
    """What a seam leaves alive at its sample point, and how many objects of
    Parallax's own of each kind, keyed by qualified name so no private class has
    to be imported to ask about it."""
    graph = live_graph(warmed(seam))
    alive = [obj for obj in graph.survivors if _defined_by_parallax(type(obj))]
    counts: dict[str, int] = {}
    for obj in alive:
        name = type(obj).__qualname__
        counts[name] = counts.get(name, 0) + 1
    live = _Live(
        len(alive),
        len(graph.survivors),
        sum(len(gc.get_referents(obj)) for obj in graph.survivors),
        graph.inbound,
    )
    return live, counts


_SOURCES: Final = frozenset(
    {
        "parallax.conformance.story_models",
        "parallax.core.continuation",
        "parallax.core.object_query._nodes",
        "parallax.core.predicate._nodes",
        "parallax.core.temporal_read",
        "parallax.core.unit_work.clock",
        "parallax.core.unit_work.planner",
        "parallax.core.unit_work.retain",
        "parallax.core.unit_work.write_planner",
        "parallax.snapshot._inspection",
        "parallax.snapshot._read_result",
        "parallax.snapshot.handle._database",
        "parallax.snapshot.handle._planning",
        "parallax.snapshot.handle._read",
        "parallax.snapshot.handle._stream",
        "parallax.snapshot.materialize._graph",
        "parallax.snapshot.materialize._views",
        "parallax.snapshot.materialize._wire",
    }
)
"""Where every object a running delivery leaves alive is DEFINED.

Read beside the exact counts because the two see different pathologies: a count
pins how many of a kind already here may survive, and this pins that no kind from
anywhere else does. A merge kept past the root it published, a whole-result
``Snapshot``, or a collection some new module accumulated is a name absent from
this set however few of them there are, and the counts alone would price it as
part of a coefficient.

The frontier is the interesting half. There is no entry for the merge module, the
read result's own snapshot, or anything under ``parallax.core.sql_gen`` — a page
is planned and compiled and the products of both are gone by the time it is
published — and none for the Wire view a Wire delivery was opened through, which
is answered fresh per access and released as soon as the stream exists.
"""


def _published_kinds(namespace: _Namespace) -> frozenset[str]:
    """The qualified names a delivery publishes a root and its children as, taken
    from a delivery of the same query rather than imported.

    A SET rather than a pair, because the two lanes disagree about how many names
    there are and neither disagreement is the subject: the Typed lane publishes
    the model's own Entity classes, so a root and a child are two names, and the
    Wire lane publishes one frozen node kind for every position in the tree. What
    both answer is how many published nodes are alive, which is what the census
    counts over whichever names this returns.
    """
    database = Database(cast("DbPort", _GeneratingPort(_BATCH)), ORDERS_MODEL)
    with namespace.opener(database, _BATCH) as stream:
        for root in stream:
            child = _first_child(root)
            return frozenset({type(root).__qualname__, type(child).__qualname__})
    raise AssertionError("the fixture delivers at least one root")  # pragma: no cover


def _first_child(root: object) -> object:
    """One included child of ``root``, reached the way the namespace publishing
    it spells the relationship: a Wire tree is a mapping and a Typed node an
    instance, and both answer the same declared view."""
    node = cast("Any", root)
    items = cast("Sequence[object]", node["items"] if isinstance(node, dict) else node.items)
    return items[0]


@in_a_child_interpreter
def test_page_graphs_do_not_accumulate_with_the_result() -> None:
    # The headline claim, in arithmetic, in both namespaces. The per-root price
    # comes from the retaining arm rather than from a constant, so the comparison
    # is against what one root of THIS graph actually costs on THIS interpreter —
    # and the streamed arm has to come in under one of them across nine times as
    # many roots.
    #
    # Read three ways, because each sees what the others cannot. A bigger RESULT
    # at one position of the delivery is what a per-result cost would move. A
    # LATER position of one delivery is what a per-root one would move, and the
    # result size cannot see it because the position is the same in both arms. And
    # a DRAINED delivery is where anything the delivery banked past its own pages
    # would still be — the one reading whose subject outlives the paging
    # generator, whose frame is dropped the moment it returns.
    tracemalloc.start()
    try:
        for namespace in _NAMESPACES:
            paused = _paused(namespace, _LARGE, batch_size=_BATCH, fanout=_FANOUT, at=_AT)
            bigger = retained(
                _paused(namespace, _LARGE * _TENFOLD, batch_size=_BATCH, fanout=_FANOUT, at=_AT)
            ) - retained(paused)
            later = retained(
                _paused(namespace, _LARGE, batch_size=_BATCH, fanout=_FANOUT, at=_FURTHER)
            ) - retained(paused)
            drained = retained(_draining(namespace, _LARGE, retaining=False)) - retained(
                _draining(namespace, _SMALL, retaining=False)
            )
            retaining = retained(_draining(namespace, _LARGE, retaining=True)) - retained(
                _draining(namespace, _SMALL, retaining=True)
            )
            per_root = retaining // (_LARGE - _SMALL)
            assert per_root > 0, namespace.name
            assert abs(bigger) < per_root, (namespace.name, bigger, per_root)
            assert abs(later) < per_root, (namespace.name, later, per_root)
            assert abs(drained) < per_root, (namespace.name, drained, per_root)
    finally:
        tracemalloc.stop()


@in_a_child_interpreter
def test_a_delivery_holds_one_page_graph_and_one_published_root() -> None:
    # The bound's two live layers, counted as objects at a point where both are
    # open. One sealed page graph and its rows; NO merge, because the merge a
    # root was published from does not outlive the publication; and exactly one
    # published root carrying exactly its own fanout of children — never the
    # roots already delivered, and never the page's other roots.
    for namespace in _NAMESPACES:
        published = _published_kinds(namespace)
        _, counts = _census(_paused(namespace, _LARGE, batch_size=_BATCH, fanout=_FANOUT, at=_AT))
        assert counts.get(SnapshotGraph.__qualname__) == 1, namespace.name
        assert counts.get(GraphRows.__qualname__) == 1, namespace.name
        assert counts.get(GraphMerge.__qualname__) is None, namespace.name
        alive = sum(counts.get(kind, 0) for kind in published)
        assert alive == 1 + _FANOUT, (namespace.name, counts)


@in_a_child_interpreter
def test_what_a_delivery_holds_is_the_page_and_the_root_and_not_the_result() -> None:
    # The same sample point over a crossed grid, priced exactly. Every reading is
    # the page term plus the root term plus what the plan and the handle cost, and
    # the fit is stated as literals rather than solved for, so an object retained
    # once — which no coefficient derived from these points could see — fails here
    # too. Both terms are real: the page term moves with the page size, the root
    # term with the fanout, and neither with anything else.
    for namespace in _NAMESPACES:
        for batch_size in _PAGE_SIZES:
            for fanout in _FANOUTS:
                live, _ = _census(
                    _paused(namespace, _LARGE, batch_size=batch_size, fanout=fanout, at=_AT)
                )
                assert live.parallax == namespace.survivors_for(
                    batch_size=batch_size, fanout=fanout
                ), (namespace.name, batch_size, fanout, live)


@in_a_child_interpreter
def test_neither_the_result_size_nor_the_position_reached_moves_what_is_held() -> None:
    # The two independence readings the fit above asserts by omission, taken
    # directly so a failure names which of them broke. Ten times the roots is the
    # same census; nearly twice as far into the same delivery is the same census.
    #
    # Read four ways rather than as the Parallax-owned count alone, because the
    # count above is blind in a direction only this reading covers. `list` is not
    # a kind Parallax defines, so a delivery banking one item per PAGE adds no
    # Parallax-owned survivor and adds no survivor of any kind past the first —
    # and at a FIXED position every byte difference here is between two arms that
    # have read the same number of pages, so nothing in bytes sees it either. It
    # is the reference count that does: the two positions differ by the pages
    # between them, and a delivery holding one thing per page holds more at the
    # second. Growth in the number of pages is growth in `N`.
    defined_in: set[str] = set()
    for namespace in _NAMESPACES:
        near = _census(_paused(namespace, _LARGE, batch_size=_BATCH, fanout=_FANOUT, at=_AT))
        larger = _census(
            _paused(namespace, _LARGE * _TENFOLD, batch_size=_BATCH, fanout=_FANOUT, at=_AT)
        )
        further = _census(
            _paused(namespace, _LARGE, batch_size=_BATCH, fanout=_FANOUT, at=_FURTHER)
        )
        assert near == larger, (namespace.name, near, larger)
        assert near == further, (namespace.name, near, further)
        sources = {
            type(obj).__module__
            for obj in _parallax_survivors(
                _paused(namespace, _LARGE, batch_size=_BATCH, fanout=_FANOUT, at=_AT)
            )
        }
        assert sources <= _SOURCES, (namespace.name, sources - _SOURCES)
        defined_in |= sources
    # Stated over the two lanes together rather than over either, because one
    # module belongs to exactly one of them — a Wire delivery is opened through a
    # view of its own — and a set neither lane reaches would be a name nothing
    # here still produces.
    assert defined_in == _SOURCES, _SOURCES - defined_in


@in_a_child_interpreter
def test_retaining_every_root_reproduces_the_growth_the_bound_excludes() -> None:
    # The first exclusion, demonstrated rather than asserted. A caller that keeps
    # what it was handed is outside the bound on purpose, and this is what that
    # costs: growth proportional to the result, read as the ratio of two
    # differences over one baseline. Ten times the extra roots is ten times the
    # extra bytes, which is the shape `O(N)` has and the shape the reading above
    # proves the delivery itself does not.
    tracemalloc.start()
    try:
        for namespace in _NAMESPACES:
            base = retained(_draining(namespace, _SMALL, retaining=True))
            middle = retained(_draining(namespace, _MID, retaining=True)) - base
            largest = retained(_draining(namespace, _LARGE, retaining=True)) - base
            roots = (_LARGE - _SMALL) / (_MID - _SMALL)
            assert middle > 0, namespace.name
            assert abs(largest / middle - roots) < 0.5, (namespace.name, largest, middle)
    finally:
        tracemalloc.stop()


@in_a_child_interpreter
def test_a_writing_loops_buffer_grows_with_the_page_and_not_with_the_result() -> None:
    # The second exclusion, and the bound the per-page flush puts back on it. A
    # participating loop's buffered writes are the caller's, held until the next
    # page forces them out, so what they cost grows with the PAGE SIZE and stops
    # there: ten times the roots at one page size is the same reading, and a
    # larger page is a larger buffer. Read against the same loop with the write
    # removed, so what the difference prices is the buffer rather than the
    # boundary around it.
    tracemalloc.start()
    try:
        buffered: dict[int, int] = {}
        for batch_size in _PAGE_SIZES:
            at = 2 * batch_size - 1
            small = _writing(_LARGE, batch_size=batch_size, at=at, writes=True)
            large = _writing(_LARGE * _TENFOLD, batch_size=batch_size, at=at, writes=True)
            unwritten = _writing(_LARGE, batch_size=batch_size, at=at, writes=False)
            held = retained(small)
            assert held == retained(large), batch_size
            buffered[batch_size] = held - retained(unwritten)
        # Proportional to the page size, which is the bound stated rather than
        # merely ordered: what one buffered write costs is the same at every page
        # size, so the buffer is the dial's own multiple and nothing else.
        each = {size: price / size for size, price in buffered.items()}
        assert min(each.values()) > 0, buffered
        assert max(each.values()) / min(each.values()) < 1.1, buffered
    finally:
        tracemalloc.stop()


if __name__ == "__main__":
    serve_one_measurement(sys.argv[1])
