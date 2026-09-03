"""The streamed read's memory bound, measured (`cost` class).

A streamed read exists to make the Parallax-owned working set independent of the
total number of roots. `m-snapshot-read` *What a delivery costs* states the bound
in three layers — one page's sealed graph at `O(P_B)`, the current root's merge
and classification at `O(G_max)`, and its construction or Wire unwind at
`O(G_max)` — and names three exclusions. This suite is the instrument for those
layers — the first apart, the second and third together as a pair, for the reason
below — and for two of the three exclusions, in both namespaces.

**The three layers, and how each is priced.** The page graph and the published
root are both alive at a point a census can be taken from outside the delivery,
and each carries its own coefficient, so the census prices those two apart. The
merge between them is alive at no such point — it is built and dropped inside one
publication — so it is priced as a PEAK instead, over a region opened at one root
and closed at the next: how far the process rose inside that region over the
level it opened at. That reading cannot separate the merge from the construction
it feeds, since neither is alive when the other can be sampled and both are
`O(G_max)`; what it separates is the pair from the page they were cut from. Both
halves of the middle layer's contract are therefore read — that it does not
survive the root it published, by the census between two roots, and that its peak
is one root's own graph rather than the page's, by the region.

**Nine readings, each its own statement.** Page graphs do not accumulate with
the result. A delivery holds one page graph and one published root at a time, and
the survivor census says so in arithmetic rather than in prose: it is exactly
affine in the page's own node population and the published root's, with **no term
in the total result size and none in how far the delivery has got**. No Python
object, reference, or reported object size anywhere in the process moves with
either, which is the same claim taken over the whole heap instead of over the
delivery's own survivors. Publishing one root peaks at that root's own graph,
exactly independent of the result, of the position, and of the page, and costing
less per node at each of eight fan-outs than at the one before. And
two of the three exclusions are demonstrated rather than asserted — a caller
retaining every root reproduces the `O(N)` growth the bound declines to prevent,
and a writing loop's buffer grows with the page size and stops there. A wide
Continuation Order is priced on a grid of its own: the width costs the plan once
and the page one coordinate per root position whatever it is.

**The third exclusion has no executable witness here, by construction.** What the
database and its driver hold for a delivery — server-side cursors, connection
buffers, a driver's own result-set materialization — is outside the bound and
outside every window below: the port these readings run against answers each page
from a counter, so there is nothing of a driver's for any of them to see. A real
port that read the whole result before answering the first page would leave every
figure here unchanged, which is the exclusion restated as a property of the
instrument rather than demonstrated by it.

**The exclusions are what make the retention readings mean anything.** A bound
that excluded nothing would be a claim about the caller's program rather than
about Parallax, so the price of one root comes from the retaining arm — what one
root of THIS graph costs on THIS interpreter — and the streamed arm has to come
in under one of them across nine times as many roots.

**The census is pinned as exact counts rather than fitted, and that is what sees
a constant.** Every byte reading in the first measurement is a DIFFERENCE — one
result size against another, one position against another — so a page graph held
one page too long cancels out of all of them and is invisible to the instrument
that measures bytes. The census is the reading that is not a difference: its
coefficients are literals, every one of them names what it counts, and a second
live page graph fails it at every point of the grid.

**The census is read five ways, and all five begin at the window's own
survivors.** A page graph or a root is a kind Parallax defines and is counted; a
built-in `list` the delivery banks one item into per PAGE is not, and past the
first page it adds no survivor of any kind. So the census is taken over every
survivor whatever defined its type, over the REFERENCES those survivors hold,
from the heap's side over what a holder older than the window took FROM the
survivors, and in BYTES over what the survivors and everything untracked they
hold weigh. What every one of them shares is where the walk starts, and it is the
delivery's own live structure: a container gaining one reference per page moves
the reference count and a buffer gaining bytes per page moves the byte reading,
but only because both hang off something the delivery published.

**Which is why the independence claim is made over the whole process instead.**
A holder created BEFORE the measurement window, appending one already-existing
value per page, is outside every arm above and outside every byte DIFFERENCE
here, since the window it would have to be born in is the one it predates. The
whole-heap reading has no window: it counts every tracked object in the process,
every reference each of them holds, and what they and everything untracked they
reach report through `sys.getsizeof`, as three totals compared across arms that
differ in exactly one thing. That is what widens "nothing grows with `N`" from
what a sample can reach to every Python object in the process — and it is why
every value the fixtures produce is fixed-width, because a total will move for a
longer string as readily as for a leak. What it does not widen to is memory a
Python object merely points at, which is the last paragraph below.

**What the nine readings still do not prove.** Nothing here sees a transient
smaller than the region it is allocated in — a high-water mark is a maximum, so an
allocation that never takes the process above an earlier moment of the same
publication is invisible however it scales, which is why the page grid the peak
is read across is thirty-two-fold rather than convenient. Nothing here sees what
a real driver holds, for the reason given above. The second and third layers are
priced together rather than apart, for the reason given above that too. The
fan-out grid REJECTS growth super-linear in one root's node count rather than
proving the bound: eight points admit any quadratic coefficient small enough to
stay under the linear term across them, and `_PEAK_FANOUTS` records how small
that is.

**And nothing here sees storage a Python object merely points at.** Every count
above is `gc.get_objects` and `sys.getsizeof`, and every byte figure beside them
is CPython's own allocator through `tracemalloc`. A delivery that banked its
pages into an `mmap` or into a buffer a C extension owned would present a
constant-size shell at every arm of every reading here, and the anonymous mapping
behind it would never reach the allocator `tracemalloc` traces. What would catch
it is a resident-set reading taken from outside the interpreter, and no
measurement in this repository takes one. The readings below are therefore a
statement about the delivery's PYTHON-LEVEL working set, which is what all of
Parallax's own storage is, and not a proof that no memory anywhere grows.

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
from itertools import pairwise
from typing import Any, Final, NamedTuple, cast

from memory_instruments import (
    Seam,
    Span,
    high_water,
    in_a_child_interpreter,
    live_graph,
    retained,
    serve_one_measurement,
    warmed,
    whole_heap,
)

from _support.db_port import body_outcome, projected_row
from parallax.conformance.story_models import ACCOUNT_MODEL, ORDERS_MODEL, Account, Order
from parallax.core.db_port import DbPort, DocumentReadOrdinals, Row, TransactionOutcome
from parallax.core.dialect import POSTGRES, Dialect
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


def _order_row(order_id: int) -> Row:
    """One row of the read, with every value the SAME SIZE at every ordinal.

    The whole-heap census is a total rather than a difference, so a name that got
    a digit longer at a later position would move it for a reason that is not
    retention. Zero-padding is what keeps the only difference between two arms
    the one the reading is about; the integer members need none, since every
    ordinal these fixtures reach is one CPython digit wide.
    """
    return {
        "id": order_id,
        "name": f"order-{order_id:06d}",
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
        "owner": f"owner-{account_id:06d}",
        "balance": Decimal("100.00"),
        "version": 1,
    }


class _GeneratingPort:
    """A port that answers each page from a counter and retains nothing.

    A recording port would grow with the result on its own and swamp the reading
    it is there to take, so this one holds how far through the result it is and
    nothing else. The child level is answered from the parent keys its own
    statement binds rather than from the page that gathered them, which is what
    keeps the lookahead root — read by a page and never kept — from being handed
    children no statement asked for.
    """

    dialect: Dialect = POSTGRES

    __slots__ = ("_delivered", "_fanout", "_total")

    def __init__(self, total: int, fanout: int = _FANOUT) -> None:
        self._total = total
        self._fanout = fanout
        self._delivered = 0

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        del document_reads
        if "order_item t0" in sql:
            return [
                _item_row(cast("int", parent) * 100 + offset, cast("int", parent))
                for parent in binds
                for offset in range(self._fanout)
            ]
        return [
            projected_row(sql, _order_row(order_id))
            for order_id in self._next_page(cast("int", binds[-1]))
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
        del document_reads
        return [
            projected_row(sql, _account_row(account_id))
            for account_id in self._next_page(cast("int", binds[-1]))
        ]

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


type _Opener = Callable[[Database, int], SnapshotStream[Any]]


def _typed_stream(database: Database, batch_size: int) -> SnapshotStream[Any]:
    return database.stream(_query(), batch_size=batch_size)


def _wire_stream(database: Database, batch_size: int) -> SnapshotStream[Any]:
    return database.wire.stream(_query(), batch_size=batch_size)


class _Namespace(NamedTuple):
    """One representation's stream, and the exact census a delivery of it leaves
    alive at any point of itself.

    The four counts are the bound restated as objects. ``fixed`` is everything
    sized by the plan and the handle rather than by the data — the schema, the
    layouts, the authored and validated query products, the continuation, the
    delivery, and the connected model.
    ``per_page_node`` is what the sealed page graph holds for each node it
    carries, so the page term is that count times the page's own root positions
    times one root plus its fanout. Both are counted over the roots the page
    KEEPS: a page reads one root past its batch to prove whether another page
    follows, and neither that root nor anything under it is converted, so it
    leaves the census untouched at every point of the grid. ``per_page_root`` is
    what the page holds per root POSITION rather than per node — the coordinate
    the database evaluated for it — so its term is that count times the page size
    alone, with no fanout in it. ``per_published_node`` is what one published root
    graph holds for each of ITS nodes, which is the page-node product with the
    page size taken out.

    Nothing in any of the three products is the total result size, and nothing is
    how far the delivery has got. That absence is the claim.
    """

    name: str
    opener: _Opener
    fixed: int
    per_page_node: int
    per_page_root: int
    per_published_node: int

    def survivors_for(self, *, batch_size: int, fanout: int) -> int:
        nodes_per_root = 1 + fanout
        return (
            self.fixed
            + self.per_page_node * batch_size * nodes_per_root
            + self.per_page_root * batch_size
            + self.per_published_node * nodes_per_root
        )


_TYPED: Final = _Namespace(
    "typed", _typed_stream, fixed=41, per_page_node=2, per_page_root=1, per_published_node=2
)
"""The Typed lane. Two objects per page node — the Source Hint a page retains for
it and the Object Key that hint is filed under — one per page ROOT rather than
per node, the coordinate the database evaluated for it, and two per published
node, the frozen Entity instance and the node state naming what it was read
from.

The root term is what makes the page's cost `O(B x T)` in the Continuation Order
rather than in the graph below it: children have no coordinate, and a coordinate
holds its carriers in one tuple rather than wrapping each cell. The delivery's
own carried position is one more of them, and is fixed. That the term count `T`
is a delivery-lifetime cost rather than a per-root one is read on its own grid
below."""

_WIRE: Final = _Namespace(
    "wire", _wire_stream, fixed=42, per_page_node=2, per_page_root=1, per_published_node=1
)
"""The Wire lane. The same page terms, because retention is a property of the read
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


def _paused_over(terms: int, total: int, *, batch_size: int, fanout: int, at: int) -> Seam:
    """:func:`_paused`'s Typed reading under a Continuation Order of ``terms``
    authored keys, so the term count varies while everything else holds."""

    def seam(sample: Callable[[], None]) -> None:
        database = Database(cast("DbPort", _GeneratingPort(total, fanout)), ORDERS_MODEL)
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
    what it covers is the merge, the classification, and the construction of one
    root over a page graph that was already sealed when it opened.
    """

    def span(opened: Callable[[], None], closed: Callable[[], None]) -> None:
        database = Database(cast("DbPort", _GeneratingPort(total, fanout)), ORDERS_MODEL)
        with namespace.opener(database, batch_size) as stream:
            roots = iter(stream)
            for _ in range(at):
                next(roots)
            opened()
            root = next(roots)
            closed()
            del root

    return span


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
    """What a running delivery holds, read five ways from one sample, because each
    answers what the other four cannot.

    ``parallax`` is what Parallax's own structure costs, and ``tracked`` is every
    survivor whatever defined its type, so anything the delivery banks in a
    built-in list, dict, or set — invisible to the first, because ``list`` is not
    a kind Parallax defines — lands in the second. ``references`` is what neither
    count can see: one container is one object however many things it points at,
    so a delivery keeping one item per PAGE moves no count at all and moves this
    by one for every page it has read. ``inbound`` is the same reading from the
    other end: what a holder OLDER than the window took OF THE SURVIVORS is
    counted where it points rather than where it is held. ``held`` is the one
    reading in bytes, and it exists because a container
    can grow without gaining either an object or a reference: a ``bytearray`` a
    delivery extends by one byte per page is not a survivor at all — the collector
    does not track it — points at nothing, and is held by the same frame at every
    position, so the four counts read identical while its allocation grows with
    the pages.

    The four counts are exact, and ``held`` is exact for a different reason worth
    stating: it is a sum over the STRUCTURE rather than over the heap, so nothing
    in it depends on whether the interpreter happened to share a value.

    All five begin at the window's own survivors, which is the limit of what any
    of them can be a statement about: what the DELIVERY holds. A holder that
    predates the window, banking values that predate it too, is reachable from no
    survivor and is outside all five, which is why the independence claim is made
    over the whole process instead.
    """

    parallax: int
    tracked: int
    references: int
    inbound: int
    held: int


def _held_bytes(survivors: Sequence[object]) -> int:
    """What ``survivors`` and everything untracked they hold report through
    :func:`sys.getsizeof`, counting a value once per PATH the walk arrives by.

    The blind spot of every count beside it. :func:`gc.get_objects` answers only
    what the collector tracks, so a ``bytearray``, ``bytes``, ``str``, or tuple of
    such things is no survivor however large it grew, and a container's own
    referent count says nothing about the bytes inside it. Walking outwards from
    each survivor through its untracked referents is what reaches them, and
    ``sys.getsizeof`` is what prices them — the survivors being where the walk
    starts, and therefore the limit of what it can price.

    Counted by PATH rather than by identity, deliberately. Whether two equal
    integers or two equal strings are one object is the interpreter's business —
    CPython shares small ints, so the same walk over the same structure reaches a
    different number of distinct objects according to which values it happens to
    hold — while how many ways the structure arrives at a value of that size is
    the structure's own. Deduplicating by identity makes this reading move with
    the ordinals a delivery has reached; carrying no identity set at all makes it
    a function of the shape alone. The cost of that is multiplicity rather than
    imprecision: a shared untracked subgraph is walked once per path INTO it, so
    everything under it is charged that many times whatever its own inbound
    reference count is.

    The walk stops at every tracked object, which is what keeps it bounded and
    acyclic: an untracked object can hold only untracked objects, so nothing it
    reaches can point back at it, and everything tracked is already counted by the
    survivor sample or belongs to the heap that predates the window.

    What it cannot price is storage a survivor merely points at.
    :func:`sys.getsizeof` is what each type reports about ITSELF, so an
    ``mmap.mmap`` or an extension-owned buffer weighs its shell here however large
    its backing grows.
    """
    total = 0
    pending: list[object] = []
    for survivor in survivors:
        total += sys.getsizeof(survivor)
        pending.extend(held for held in gc.get_referents(survivor) if not gc.is_tracked(held))
    while pending:
        obj = pending.pop()
        total += sys.getsizeof(obj)
        pending.extend(held for held in gc.get_referents(obj) if not gc.is_tracked(held))
    return total


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
        _held_bytes(graph.survivors),
    )
    return live, counts


_SOURCES: Final = frozenset(
    {
        "parallax.conformance.story_models",
        "parallax.core.continuation",
        "parallax.core.metamodel._identities",
        "parallax.core.object_query._validated",
        "parallax.core.object_query._nodes",
        "parallax.core.predicate._validated",
        "parallax.core.predicate._nodes",
        "parallax.core.temporal_read",
        "parallax.core.unit_work.clock",
        "parallax.core.unit_work.planner",
        "parallax.core.unit_work.retain",
        "parallax.core.unit_work.write_planner",
        "parallax.snapshot._inspection",
        "parallax.snapshot.handle._database",
        "parallax.snapshot.handle._page",
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

The frontier is the interesting half. The metamodel entry is the canonical
relationship identity shared by the validated include and its view keys. There
is no entry for the merge module, for the eager executor's own result carrier — a
delivery holds the page it read rather than a find's — or anything under
``parallax.core.sql_gen``, a page being planned and compiled and the products of
both gone by the time it is published; and none for the Wire view a Wire delivery
was opened through, which is answered fresh per access and released as soon as
the stream exists.
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
    # Read five ways rather than as the Parallax-owned count alone, because that
    # count is blind in two directions only this reading covers, and each of them
    # needs a different arm. `list` is not a kind Parallax defines, so a delivery
    # banking one item per PAGE adds no Parallax-owned survivor and adds no
    # survivor of any kind past the first; the references those survivors hold are
    # what see it. A buffer the delivery extends by a byte per page adds no
    # survivor and no reference either, and is not even tracked — the bytes the
    # survivors and everything untracked they hold weigh are what see that one.
    # Neither is visible in the byte DIFFERENCES of the first measurement, whose
    # two arms always stand at the same position and so have read the same number
    # of pages. Here the positions differ by the pages between them, and growth in
    # the number of pages is growth in `N`.
    #
    # Every arm of this reading starts from the window's own survivors, so what it
    # states is about the delivery's own live structure and about nothing else. A
    # holder that predates the window is behind the measurement below, which needs
    # no survivor sample to reach one.
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
def test_a_wide_continuation_order_costs_the_plan_once_and_the_page_per_root() -> None:
    # The page term's other dimension, which the grid above holds at its
    # narrowest: how many terms the Continuation Order has. A coordinate holds
    # its carriers in ONE tuple rather than wrapping each cell, so a page retains
    # one of them per root POSITION whatever the order's width — the width itself
    # is a delivery-lifetime cost, paid once by the plan and the page node rather
    # than once per root.
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
            # The page's own, plus the position the delivery carries between two
            # pages — which is the page before this one's last kept root, and is
            # one whatever the order's width.
            assert counts[batch_size, terms][1]["ContinuationCoordinate"] == batch_size + 1, (
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
def test_nothing_in_the_process_grows_with_the_result_or_the_position() -> None:
    # The same two independence readings taken over the WHOLE PROCESS, which is
    # what makes them a claim about the implementation rather than about the
    # delivery's own survivors. Every arm of the census above begins at an object
    # the window created, so a holder that existed BEFORE the window is outside
    # all of them: it is no survivor, a reference it took may point at an object
    # older than the window too, and a buffer it banked bytes into is reachable
    # from nothing that sample can start at. A module-level container an
    # implementation appended one existing value to per page would move nothing up
    # there and everything here.
    #
    # What the three totals reach is Python-level structure: the collector's
    # listing, the references in it, and what each object reports about its own
    # size. Storage an object merely points at — an `mmap`, an extension-owned
    # buffer — is a constant-size shell in all three however large its backing
    # grows, and no reading in this suite or beside it observes one. The claim
    # this makes is about every Python object in the process, which is what all of
    # Parallax's own storage is, and not about the process's resident set.
    #
    # Three totals, no baseline, and exact equality rather than a tolerance. The
    # arms differ in exactly one thing each — ten times the roots at one position,
    # and a later position of one result — and every value the fixture produces is
    # the same width at every ordinal, so nothing but retention can move a total.
    # All three are handed over together because a total prices whoever is holding
    # what, including this measurement: taken one call at a time, each reading
    # would count the ones already bound beside it.
    #
    # Each arm is warmed by two hundred runs before its reading, which is also
    # what gives the reading its reach: a term paid once per PAGE has been paid by
    # every one of those runs by the time the sample is taken, so two arms differ
    # by the pages of two hundred deliveries rather than of one.
    for namespace in _NAMESPACES:
        near, larger, further = whole_heap(
            _paused(namespace, _LARGE, batch_size=_BATCH, fanout=_FANOUT, at=_AT),
            _paused(namespace, _LARGE * _TENFOLD, batch_size=_BATCH, fanout=_FANOUT, at=_AT),
            _paused(namespace, _LARGE, batch_size=_BATCH, fanout=_FANOUT, at=_FURTHER),
        )
        assert near == larger, (namespace.name, near, larger)
        assert near == further, (namespace.name, near, further)


@in_a_child_interpreter
def test_publishing_one_root_peaks_at_that_roots_graph_and_not_at_the_pages() -> None:
    # The middle layer, priced at its PEAK rather than at its release. Everything
    # the census can say about the merge is that it is gone by the time a sample
    # can be taken between two roots; how far the process ever rose while it
    # existed is a high-water mark inside one publication, and this is the region
    # that contains it.
    #
    # Four statements, and each is an equality or an ordering rather than a level,
    # because a byte total is machine-relative and nothing here is read as a
    # verdict on one.
    #
    # The peak is EXACTLY equal at ten times the roots and exactly equal at two
    # positions of the same delivery, so a publication carrying any term in the
    # result or in how far the delivery has got fails it outright.
    #
    # It is EXACTLY equal across a thirty-two-fold spread of page sizes, which is
    # the layer's own bound and not an approximation of it: `m-snapshot-read`
    # gives the page to the first layer alone, so the correct reading here is
    # equality, and a tolerance of one child would have accepted the eight bytes
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
            assert near == larger, (namespace.name, near, larger)
            assert near == further, (namespace.name, near, further)
            by_page = [
                high_water(
                    _advancing(
                        namespace, _PEAK_ROOTS, batch_size=batch_size, fanout=_FANOUT, at=_EARLY
                    )
                )
                for batch_size in _PEAK_PAGES
            ]
            assert len(set(by_page)) == 1, (namespace.name, _PEAK_PAGES, by_page)
            by_fanout = [
                high_water(
                    _advancing(namespace, _PEAK_ROOTS, batch_size=_BATCH, fanout=fanout, at=_EARLY)
                )
                for fanout in _PEAK_FANOUTS
            ]
            assert all(later > earlier for earlier, later in pairwise(by_fanout)), (
                namespace.name,
                by_fanout,
            )
            per_node = [
                peak / (1 + fanout) for peak, fanout in zip(by_fanout, _PEAK_FANOUTS, strict=True)
            ]
            assert all(later < earlier for earlier, later in pairwise(per_node)), (
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
