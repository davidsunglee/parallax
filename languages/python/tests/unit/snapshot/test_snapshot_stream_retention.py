"""The streamed read's memory bound, measured (`cost` class).

A streamed read exists to make the Parallax-owned working set independent of the
total number of roots. `m-snapshot-read` *What a delivery costs* states the bound
in three layers — one sealed Page at `O(P_B)`, the current Root View's judgment
and classification at `O(G_max)`, and its construction or Wire unwind at
`O(G_max)` — and names three exclusions. This suite is the instrument for those
layers — the first apart, the second and third together as a pair, for the reason
below — and for two of the three exclusions, in both namespaces.

**The three layers, and how each is priced.** The Page and the published
root are both alive at a point a census can be taken from outside the delivery,
and each is a kind of its own, so the census prices those two apart. The
Root View work between them is alive at no such point — it is built and dropped inside one
publication — so it is priced as a PEAK instead, over a region opened at one root
and closed at the next: how far the process rose inside that region over the
level it opened at. That reading cannot separate Root View judgment from construction
it feeds, since neither is alive when the other can be sampled and both are
`O(G_max)`; what it separates is the pair from the Page they were cut from. Both
halves of the middle layer's contract are therefore read — that it does not
survive the root it published, by the census between two roots, and that its peak
is one root's reachable nodes rather than the Page's, by the region.

**Seven readings, each its own statement.** Pages do not accumulate with the
result. A delivery holds one Page and one published root at a time, and the
survivor census says so by kind at every point of a crossed grid of page sizes
and fan-outs: one Page, one carrier of its rows, one Root View, and exactly the
published root's own reachable nodes, with **no term in the total result size and
none in how far the delivery has got**. Publishing one root peaks at that root's
reachable node set, exactly independent of the result, of the position, and of
the page, and costing less per node at each of eight fan-outs than at the one
before. And two of the three exclusions are demonstrated rather than asserted — a
caller retaining every root reproduces the `O(N)` growth the bound declines to
prevent, and a writing loop's buffer grows with the page size and stops there. A
wide Continuation Order is priced on a grid of its own: the width costs the plan
once and the page decision releases its per-root coordinates after retaining the
one boundary needed to continue.

**The third exclusion is the port's, by construction.** What the database and its
driver hold for a delivery — server-side cursors, connection buffers, a driver's
own result-set materialization — is outside the bound, and the port these
readings run against answers each page from a counter, so every reading below
grades Parallax's own working set alone.

**The exclusions are what make the retention readings mean anything.** A bound
that excluded nothing would be a claim about the caller's program rather than
about Parallax, so the price of one root comes from the retaining arm — what one
root of THIS shape costs on THIS interpreter — and the streamed arm has to come
in under one of them across nine times as many roots.

**The census counts kinds, and that is what sees a constant.** Every byte
reading in the first measurement is a DIFFERENCE — one result size against
another, one position against another — so a Page held one page too long cancels
out of all of them and is invisible to the instrument that measures bytes. The
census is the reading that is not a difference: it names each kind it counts and
how many of it may be alive, and a second live Page fails it at every point of
the grid.

**The census is read three ways, which is what sees a small term.** The byte
readings are graded against the price of one root, so a delivery keeping one
small object per page stays under that price across every page these results
span. The census grades the same two independence arms exactly instead. A Page
or a root is a kind Parallax defines and is counted; a built-in `list` the
delivery banks one item into per PAGE is not, and past the first page it adds no
survivor of any kind. So the census is also taken over every survivor whatever
defined its type, and over the REFERENCES those survivors hold, where a container
gaining one reference per page moves the count.

Every reading reads a whole interpreter, so each runs in one of its own behind
``in_a_child_interpreter`` and the class is CI's rather than the merge gate's.
The machine-relative figures — what a page and a root cost in bytes on one
machine — are `tools/snapshot_delivery_overhead.py`'s and are recorded in
`docs/stream-baseline.md`; nothing here reads a byte total as a verdict.
"""

from __future__ import annotations

import datetime as dt
import gc
import sys
import tracemalloc
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from itertools import pairwise
from typing import Any, Final, NamedTuple, cast

from parallax.conformance.story_models import ACCOUNT_MODEL, ORDERS_MODEL, Account, Order
from parallax.conformance.workloads import catalog
from parallax.core.db_port import (
    DatabaseConnection,
    DocumentReadOrdinals,
    MappingRow,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.object_query._fluent import ObjectQuery
from parallax.snapshot import SnapshotStream
from parallax.snapshot.handle import Database, ScopedDatabase, Transaction
from parallax.snapshot.materialize import Page, RootView
from parallax.snapshot.materialize._page import PageRows
from tests._support.db_port import ConnectsAsItself, body_outcome, projected_row
from tests.unit.memory_instruments import (
    Seam,
    Span,
    high_water,
    in_a_child_interpreter,
    retained,
    serve_one_measurement,
    survivors,
    warmed,
)

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

_WORKLOAD: Final = catalog()["conventional-fanout"]

_FANOUT: Final = _WORKLOAD.fanout // 2
"""Included children per root, so a Page holds relationship fanout rather
than bare roots and `P_B` is measured over something with depth."""

_PAGE_SIZES: Final = tuple(
    dict.fromkeys((1, *(2**power for power in range(1, _WORKLOAD.fanout - 1)), 32, 128))
)
"""A logarithmic probe grid including the delivery contract's 1/32/128 arms."""

_FANOUTS: Final = tuple(range(1, _FANOUT + 2))
"""A centered grid derived from the fixture-owned fanout, so the page and root
terms move independently."""

_AT: Final = 20
"""Roots consumed before the census sample. Deliberately not a multiple of every
page size in the grid, so the sample lands mid-page at some points and on a page
boundary at others and the reading is the same at both."""

_FURTHER: Final = 36
"""A later sample at the same offset within its Page as :data:`_AT`.

Page-owned Entity States accumulate only within the current Page, so equivalent
positions in two Pages must retain the same shape while still proving that no
earlier Page survives.
"""

_TERM_COUNTS: Final = (0, 1, 3)
"""Authored Sort Keys the term grid varies, holding page size and fan-out fixed.

Zero is the undeclared ordering every other reading here runs under, so the grid
starts where they stand and widens from there rather than beside them."""

_TERM_PAGES: Final = (2, 4)
"""The two page sizes the term grid crosses, narrow first.

Two is enough: what the crossing has to separate is a cost per ROOT from a cost
per DELIVERY, and two points either side of it settle which of them moved."""

_TENFOLD: Final = 10
"""The factor between the two result sizes every independence reading is taken
at."""

_EARLY: Final = 2
"""The position the peak reading advances FROM when the page size or the fan-out
is what varies.

Inside the first page at every page size the grids below use, so the root whose
publication is measured never begins one and no page read ever falls inside the
region — which is what lets those grids reach page sizes far larger than the
position, at the cost of two roots per run rather than a page's worth."""

_PEAK_PAGES: Final = (4, 8, 16, 32, 64, 128)
"""The page sizes the publication peak is read across.

Thirty-two-fold, deliberately, and far wider than the census grid. The reading is
a MAXIMUM, so a page-sized term inside the region is invisible while it stays
under the region's own high-water; widening the page until such a term would have
to exceed that high-water is the only thing that closes the gap, and at this
spread anything above a handful of bytes per page root does."""

_PEAK_FANOUTS: Final = (1, 2, 3, 4, 6, 8, 12, 16)
"""The fan-outs it is read across beside them.

Wide enough to REJECT growth super-linear in ``G_max`` rather than merely to show
that the peak moves with it: what a publication costs per node has to fall across
all of it, and a region carrying a term quadratic in the node count makes it rise
instead. A finite grid rejects rather than proves, and its resolution is set by
the widest pair — at these two a quadratic term is caught from a few pointers per
node PAIR upwards, and anything under that stays beneath the linear term at every
point and passes."""

_PEAK_ROOTS: Final = _LARGE * _TENFOLD
"""Roots in the result the peak grid runs against, so the widest page above is a
full page of that size rather than the whole result."""


def _order_row(row: Mapping[str, object]) -> MappingRow:
    return {
        "id": row["id"],
        "name": row["name"],
        "sku": row["sku"],
        "qty": row["qty"],
        "price": row["price"],
        "active": row["active"],
        "ordered_on": dt.date.fromisoformat(cast("str", row["orderedOn"])),
    }


def _item_row(row: Mapping[str, object]) -> MappingRow:
    return {
        "id": row["id"],
        "order_id": row["orderId"],
        "sku": row["sku"],
        "quantity": row["quantity"],
        "shipped_on": dt.date.fromisoformat(cast("str", row["shippedOn"])),
    }


def _account_row(account_id: int) -> MappingRow:
    return {
        "id": account_id,
        "owner": f"owner-{account_id:06d}",
        "balance": Decimal("100.00"),
        "version": 1,
    }


class _GeneratingPort(ConnectsAsItself):
    """A port that answers each page from a counter and retains nothing.

    A recording port would grow with the result on its own and swamp the reading
    it is there to take, so this one holds how far through the result it is and
    nothing else. The child level is answered from the parent keys its own
    statement binds rather than from the page that gathered them, which is what
    keeps the lookahead root — read by a page and never kept — from being handed
    children no statement asked for.
    """

    dialect: Dialect = POSTGRES

    __slots__ = ("_delivered", "_fanout", "_items", "_orders", "_total")

    def __init__(self, total: int, fanout: int = _FANOUT) -> None:
        rows = _WORKLOAD.rows(total, fanout=fanout)
        self._total = total
        self._fanout = rows.fanout
        self._orders = rows.entity("parallax.compatibility.Order")
        self._items = rows.entity("parallax.compatibility.OrderItem")
        self._delivered = 0

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        del document_reads
        if "order_item t0" in sql:
            parents = tuple(cast("list[int]", binds[0]))
            first_id = cast("int", self._orders[0]["id"])
            return [
                tuple(_item_row(row).values())
                for parent in parents
                for row in self._items[
                    (parent - first_id) * self._fanout : (parent - first_id + 1) * self._fanout
                ]
            ]
        return [
            projected_row(sql, _order_row(self._orders[position - 1]))
            for position in self._next_page(cast("int", binds[-1]))
        ]

    def _next_page(self, size: int) -> tuple[int, ...]:
        """The next ``size`` roots, of which the delivery keeps all but the last.

        A page reads one root past its batch and discards it, so the counter
        advances by what the page DELIVERS: the discarded root is read again by
        the page that delivers it, exactly as a real database returns it twice.
        """
        taken = min(size, self._total - self._delivered)
        page = tuple(range(self._delivered + 1, self._delivered + taken + 1))
        self._delivered += taken - 1 if taken == size else taken
        return page

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise NotImplementedError

    def transaction[T](
        self, body: Callable[[DatabaseConnection], T], *, isolation: str | None = None
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
        del document_reads
        return [
            projected_row(sql, _account_row(account_id))
            for account_id in self._next_page(cast("int", binds[-1]))
        ]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        del sql, binds
        return 1

    def transaction[T](
        self, body: Callable[[DatabaseConnection], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:
        del isolation
        return body_outcome(cast("DatabaseConnection", self), body)


_QUERY: Final = Order.where(Order.all).include(Order.items)
_WORKLOAD.validate_class_backed(ORDERS_MODEL, _QUERY)


def _query() -> ObjectQuery[Order, Order]:
    return _QUERY


_ORDER_KEYS: Final = (Order.name.asc(), Order.sku.asc(), Order.qty.asc(), Order.price.asc())
"""Authored Sort Keys the term grid draws its Continuation Orders from.

Direct Columns, so every one of them lowers to a capture cell the stand-in port
can answer, and each adds one term to the order and one carrier to every
coordinate.
"""


def _ordered(terms: int) -> ObjectQuery[Order, Order]:
    """The same delivery under a Continuation Order of ``terms`` authored keys.

    The primary key is appended to every one of them, so the order the page is
    measured against is one term wider than the count named here.
    """
    keys = _ORDER_KEYS[:terms]
    return _query().order_by(*keys) if keys else _query()


type _Opener = Callable[[ScopedDatabase, int], SnapshotStream[Any]]


def _typed_stream(database: ScopedDatabase, batch_size: int) -> SnapshotStream[Any]:
    return database.stream(_query(), batch_size=batch_size)


def _wire_stream(database: ScopedDatabase, batch_size: int) -> SnapshotStream[Any]:
    return database.wire.stream(_query(), batch_size=batch_size)


class _Namespace(NamedTuple):
    """One representation's stream: the lane's name, and the opener that begins
    a delivery of it over a handle at a given page size."""

    name: str
    opener: _Opener


_TYPED: Final = _Namespace("typed", _typed_stream)
"""The Typed lane, publishing each root as the model's own Entity class with its
included children as instances."""

_WIRE: Final = _Namespace("wire", _wire_stream)
"""The Wire lane, publishing the same delivery as frozen Wire nodes, the root's
included relationship spelled as a sequence of them."""

_NAMESPACES: Final = (_TYPED, _WIRE)


def _draining(namespace: _Namespace, total: int, *, retaining: bool) -> Seam:
    """One whole stream of ``total`` roots, sampled with the last page still open.

    The handle and the port are built inside the seam, so everything the reading
    could attribute to the stream was allocated inside its own window.
    """

    def seam(sample: Callable[[], None]) -> None:
        with Database.connect(_GeneratingPort(total), ORDERS_MODEL) as root:
            database = root.using_database_login()
            held: list[Any] = []
            with namespace.opener(database, _BATCH) as stream:
                for published in stream:
                    if retaining:
                        held.append(published)
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
        with Database.connect(_GeneratingPort(total, fanout), ORDERS_MODEL) as root:
            database = root.using_database_login()
            with namespace.opener(database, batch_size) as stream:
                for position, _root in enumerate(stream):
                    if position == at:
                        sample()
                        return

    return seam


def _projecting_paused(total: int, *, batch_size: int, fanout: int, at: int) -> Seam:
    """A Typed delivery projecting each current root and retaining no output."""

    def seam(sample: Callable[[], None]) -> None:
        with Database.connect(_GeneratingPort(total, fanout), ORDERS_MODEL) as root:
            database = root.using_database_login()
            with database.stream(_query(), batch_size=batch_size) as stream:
                for position, published in enumerate(stream):
                    stream.wire(published)
                    if position == at:
                        sample()
                        return

    return seam


def _paused_over(terms: int, total: int, *, batch_size: int, fanout: int, at: int) -> Seam:
    """:func:`_paused`'s Typed reading under a Continuation Order of ``terms``
    authored keys, so the term count varies while everything else holds."""

    def seam(sample: Callable[[], None]) -> None:
        with Database.connect(_GeneratingPort(total, fanout), ORDERS_MODEL) as root:
            database = root.using_database_login()
            with database.stream(_ordered(terms), batch_size=batch_size) as stream:
                for position, _root in enumerate(stream):
                    if position == at:
                        sample()
                        return

    return seam


def _advancing(namespace: _Namespace, total: int, *, batch_size: int, fanout: int, at: int) -> Span:
    """A delivery run to position ``at``, with the publication of the NEXT root
    alone inside the measured region.

    The middle layer of the bound is never alive at a point a census can be taken
    from outside the delivery — it is built and dropped inside one publication —
    so the region rather than a sample point is what can price it. ``at`` is never
    the position a page starts at, so no page read falls inside the region and
    what it covers is Root View judgment, classification, and construction of one
    root from a Page that was already sealed when it opened.
    """

    def span(opened: Callable[[], None], closed: Callable[[], None]) -> None:
        with Database.connect(_GeneratingPort(total, fanout), ORDERS_MODEL) as root:
            database = root.using_database_login()
            with namespace.opener(database, batch_size) as stream:
                roots = iter(stream)
                for _ in range(at):
                    next(roots)
                opened()
                published = next(roots)
                closed()
                del published

    return span


def _writing(total: int, *, batch_size: int, at: int, writes: bool) -> Seam:
    """A participating delivery of ``total`` roots whose loop writes every root,
    sampled at position ``at`` with that page's writes still buffered.

    The read-only arm beside it is the same loop with the write removed, so what
    the pair reports is the buffer's own price rather than the transaction's.
    """

    def seam(sample: Callable[[], None]) -> None:
        with Database.connect(_WritingPort(total), ACCOUNT_MODEL) as root:
            database = root.using_database_login()

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


def _defined_by_parallax(kind: type) -> bool:
    return kind.__module__.startswith("parallax.")


class _Live(NamedTuple):
    """What a running delivery holds, read three ways from one sample, because
    each answers what the other two cannot.

    ``parallax`` is what Parallax's own structure costs, and ``tracked`` is every
    survivor whatever defined its type, so anything the delivery banks in a
    built-in list, dict, or set — invisible to the first, because ``list`` is not
    a kind Parallax defines — lands in the second. ``references`` is what neither
    count can see: one container is one object however many things it points at,
    so a delivery keeping one item per PAGE moves no count at all and moves this
    by one for every page it has read. All three are exact.
    """

    parallax: int
    tracked: int
    references: int


def _census(seam: Seam) -> tuple[_Live, dict[str, int]]:
    """What a seam leaves alive at its sample point, and how many objects of
    Parallax's own of each kind, keyed by qualified name so no private class has
    to be imported to ask about it."""
    alive = survivors(warmed(seam))
    owned = [obj for obj in alive if _defined_by_parallax(type(obj))]
    counts: dict[str, int] = {}
    for obj in owned:
        name = type(obj).__qualname__
        counts[name] = counts.get(name, 0) + 1
    live = _Live(
        len(owned),
        len(alive),
        sum(len(gc.get_referents(obj)) for obj in alive),
    )
    return live, counts


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
    with Database.connect(_GeneratingPort(_BATCH), ORDERS_MODEL) as root:
        database = root.using_database_login()
        with namespace.opener(database, _BATCH) as stream:
            for published in stream:
                child = _first_child(published)
                return frozenset({type(published).__qualname__, type(child).__qualname__})
    raise AssertionError("the fixture delivers at least one root")  # pragma: no cover


def _first_child(root: object) -> object:
    """One included child of ``root``, reached the way the namespace publishing
    it spells the relationship: a Wire tree is a mapping and a Typed node an
    instance, and both answer the same declared view."""
    node = cast("Any", root)
    items = cast("Sequence[object]", node["items"] if isinstance(node, dict) else node.items)
    return items[0]


@in_a_child_interpreter
def test_pages_do_not_accumulate_with_the_result() -> None:
    # The headline claim, in arithmetic, in both namespaces. The per-root price
    # comes from the retaining arm rather than from a constant, so the comparison
    # is against what one root of THIS shape actually costs on THIS interpreter —
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
def test_a_delivery_holds_one_page_and_one_published_root() -> None:
    # The bound's two live layers, counted by kind at a point where both are
    # open, over a crossed grid of page sizes and fan-outs. One sealed Page and
    # its rows, plus the transient Root View that publishes the current root and
    # does not outlive that publication; and exactly one published root carrying
    # exactly its own fanout of children — never the roots already delivered,
    # and never the page's other roots. Counted by kind rather than as a total so
    # a failure names what was retained, and over the grid so the root term is
    # seen to move with the fanout alone and the page kinds with nothing at all.
    for namespace in _NAMESPACES:
        published = _published_kinds(namespace)
        for batch_size in _PAGE_SIZES:
            for fanout in _FANOUTS:
                _, counts = _census(
                    _paused(namespace, _LARGE, batch_size=batch_size, fanout=fanout, at=_AT)
                )
                where = (namespace.name, batch_size, fanout, counts)
                assert counts.get(Page.__qualname__) == 1, where
                assert counts.get(PageRows.__qualname__) == 1, where
                assert counts.get(RootView.__qualname__) == 1, where
                alive = sum(counts.get(kind, 0) for kind in published)
                assert alive == 1 + fanout, where


@in_a_child_interpreter
def test_neither_the_result_size_nor_the_position_reached_moves_what_is_held() -> None:
    # The two independence readings the kind counts above leave implicit, taken
    # directly so a failure names which of them broke. Ten times the roots is the
    # same census; nearly twice as far into the same delivery is the same census.
    #
    # Read three ways rather than as the Parallax-owned count alone, because
    # `list` is not a kind Parallax defines: a delivery banking one item per PAGE
    # adds no Parallax-owned survivor and adds no survivor of any kind past the
    # first, and the references those survivors hold are what see it. Nor is one
    # small object per page visible to the first measurement, which grades its
    # byte differences against the price of a whole root. Here each arm is exact,
    # and growth in the number of pages is growth in `N`.
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

    projected = _census(_projecting_paused(_LARGE, batch_size=_BATCH, fanout=_FANOUT, at=_AT))
    projected_larger = _census(
        _projecting_paused(_LARGE * _TENFOLD, batch_size=_BATCH, fanout=_FANOUT, at=_AT)
    )
    projected_further = _census(
        _projecting_paused(_LARGE, batch_size=_BATCH, fanout=_FANOUT, at=_FURTHER)
    )
    assert projected == projected_larger, (projected, projected_larger)
    assert projected == projected_further, (projected, projected_further)


@in_a_child_interpreter
def test_a_wide_continuation_order_costs_the_plan_once_and_retains_fixed_boundaries() -> None:
    # The page term's other dimension, which the grid above holds at its
    # narrowest: how many terms the Continuation Order has. A coordinate holds
    # its carriers in ONE tuple rather than wrapping each cell. The page decision
    # uses one per root POSITION, releases them before graph assembly, and retains
    # only fixed delivery boundaries. The width itself is a delivery-lifetime
    # cost, paid once by the plan rather than once per root.
    #
    # Stated as two differences over a crossed grid, because either alone is
    # satisfiable by the other: the term difference is the same at both page
    # sizes, so nothing the width costs is per-root, and the page-size difference
    # is the same at every width, so nothing a page costs per root grows with the
    # width. Ten times the roots moves neither.
    counts = {
        (batch_size, terms): _census(
            _paused_over(terms, _LARGE, batch_size=batch_size, fanout=_FANOUT, at=_AT)
        )
        for batch_size in _TERM_PAGES
        for terms in _TERM_COUNTS
    }
    narrow, wide = _TERM_PAGES
    for batch_size in _TERM_PAGES:
        for terms in _TERM_COUNTS:
            # The position entering the current Page, the boundary leaving it,
            # and the marker retained by the delivery's one compiled seek
            # template. All three are fixed whatever the Page size or order width.
            assert counts[batch_size, terms][1]["ContinuationCoordinate"] == 3, (
                batch_size,
                terms,
                counts,
            )
    widths = [
        counts[batch_size, terms][0].parallax - counts[batch_size, _TERM_COUNTS[0]][0].parallax
        for batch_size in _TERM_PAGES
        for terms in _TERM_COUNTS[1:]
    ]
    assert widths[: len(_TERM_COUNTS) - 1] == widths[len(_TERM_COUNTS) - 1 :], (widths, counts)
    assert all(width > 0 for width in widths), (widths, counts)
    pages = {
        terms: counts[wide, terms][0].parallax - counts[narrow, terms][0].parallax
        for terms in _TERM_COUNTS
    }
    assert len(set(pages.values())) == 1, (pages, counts)
    widest = _TERM_COUNTS[-1]
    larger = _census(
        _paused_over(widest, _LARGE * _TENFOLD, batch_size=wide, fanout=_FANOUT, at=_AT)
    )
    assert larger == counts[wide, widest], (larger, counts[wide, widest])


@in_a_child_interpreter
def test_publishing_one_root_peaks_at_that_roots_reachable_nodes_not_at_the_pages() -> None:
    # The middle layer, priced at its PEAK rather than at its release. Everything
    # the census can say about Root View work is that it is gone by the time a sample
    # can be taken between two roots; how far the process ever rose while it
    # existed is a high-water mark inside one publication, and this is the region
    # that contains it.
    #
    # Four statements, and each is an equality or an ordering rather than a level,
    # because a byte total is machine-relative and nothing here is read as a
    # verdict on one.
    #
    # The peak differs by at most a small fixed allocator quantum at ten times the roots and two
    # positions of the same delivery, so a publication carrying any term in the
    # result or in how far the delivery has got fails it outright.
    #
    # It stays within one fixed bound across a thirty-two-fold spread of page sizes, which is
    # the layer's own bound and not an approximation of it: `m-snapshot-read`
    # gives the page to the first layer alone, so the correct reading here is
    # a fixed tolerance independent of Page size. A tolerance of one child would
    # have accepted the eight bytes
    # per page node a projection-indexed array costs. The spread is wide rather
    # than convenient because this reading is a maximum and a page term smaller
    # than the region's own high-water is invisible; at this spread nothing above
    # a handful of bytes per page root can stay under it.
    #
    # It rises with the fan-out, which is what makes `G_max` a real term rather
    # than an absent one — and what it costs PER NODE falls across the whole
    # fan-out grid, which REJECTS a bound above `O(G_max)` rather than proving
    # one: a region carrying an `O(G_max**2)` term costs more per node the more
    # nodes it has, so a falling slope refuses such a term at the eight fan-outs
    # read. Eight points cannot establish an asymptote, and a quadratic
    # coefficient small enough to stay under the linear term across all of them
    # passes; `_PEAK_FANOUTS` records where that resolution sits.
    tracemalloc.start()
    try:
        for namespace in _NAMESPACES:
            near = high_water(
                _advancing(namespace, _LARGE, batch_size=_BATCH, fanout=_FANOUT, at=_AT)
            )
            larger = high_water(
                _advancing(namespace, _LARGE * _TENFOLD, batch_size=_BATCH, fanout=_FANOUT, at=_AT)
            )
            further = high_water(
                _advancing(namespace, _LARGE, batch_size=_BATCH, fanout=_FANOUT, at=_FURTHER)
            )
            assert abs(near - larger) <= 256, (namespace.name, near, larger)
            assert abs(near - further) <= 256, (namespace.name, near, further)
            by_page = [
                high_water(
                    _advancing(
                        namespace, _PEAK_ROOTS, batch_size=batch_size, fanout=_FANOUT, at=_EARLY
                    )
                )
                for batch_size in _PEAK_PAGES
            ]
            assert max(by_page) - min(by_page) <= 16 * 1024, (
                namespace.name,
                _PEAK_PAGES,
                by_page,
            )
            by_fanout = [
                high_water(
                    _advancing(namespace, _PEAK_ROOTS, batch_size=_BATCH, fanout=fanout, at=_EARLY)
                )
                for fanout in _PEAK_FANOUTS
            ]
            assert all(later + 1024 > earlier for earlier, later in pairwise(by_fanout)), (
                namespace.name,
                by_fanout,
            )
            per_node = [
                peak / (1 + fanout) for peak, fanout in zip(by_fanout, _PEAK_FANOUTS, strict=True)
            ]
            assert all(later <= earlier * 1.10 for earlier, later in pairwise(per_node)), (
                namespace.name,
                by_fanout,
                per_node,
            )
    finally:
        tracemalloc.stop()


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
    # there: ten times the roots at one page size is the same reading within a
    # fixed tracer residue, and a larger page is a larger buffer. Read against
    # the same loop with the write removed, so what the difference prices is the
    # buffer rather than the boundary around it.
    tracemalloc.start()
    try:
        buffered: dict[int, int] = {}
        for batch_size in _PAGE_SIZES:
            at = 2 * batch_size - 1
            bounded_total = max(_LARGE, at + 1)
            small = _writing(bounded_total, batch_size=batch_size, at=at, writes=True)
            large = _writing(bounded_total * _TENFOLD, batch_size=batch_size, at=at, writes=True)
            unwritten = _writing(bounded_total, batch_size=batch_size, at=at, writes=False)
            held = retained(small)
            assert abs(held - retained(large)) <= 1024, batch_size
            buffered[batch_size] = held - retained(unwritten)
        # Affine in the page size, which is the bound stated rather than merely
        # ordered: fixed transaction bookkeeping cancels between adjacent arms,
        # leaving the same marginal cost for each additional buffered write.
        marginal = [
            (later_price - earlier_price) / (later_size - earlier_size)
            for (earlier_size, earlier_price), (later_size, later_price) in pairwise(
                buffered.items()
            )
        ]
        assert min(marginal) > 0, buffered
        assert max(marginal) / min(marginal) < 1.1, (buffered, marginal)
    finally:
        tracemalloc.stop()


if __name__ == "__main__":
    serve_one_measurement(sys.argv[1])
