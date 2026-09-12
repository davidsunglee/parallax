"""What a streamed delivery holds, and what the page size buys, in bytes and time.

`m-snapshot-read` bounds the Parallax-owned working set of a streamed read at
`O(P_B + G_max)` — one page's sealed graph, plus the merge and publication of the
one root the caller is holding — and names three exclusions. This measures both
halves of that on one machine: the working set while a delivery is running, and
the growth the exclusions decline to prevent, read beside it so the bound has a
scale rather than only a shape.

It is a `report`: it passes no verdict and joins no aggregate, because a total in
bytes is machine- and interpreter-relative and `tracemalloc` figures move with
CPython. The SHAPE of the bound is gated instead, in
``tests/unit/snapshot/test_snapshot_stream_retention.py``, which the `cost` class owns and
CI runs on every change: that suite pins the survivor census as an exact
population count with no term in the result size and none in how far the delivery
has got, and demonstrates both exclusions rather than asserting them. What has
been read off this, and under what conditions, is ``docs/stream-baseline.md``.

**Where the reading is taken.** With the delivery still running and the caller
holding one root, which is where the working set is. Sampling a drained delivery
answers a different question — what it banked — and the gated suite reads that
one too; here it would report the floor rather than the bound.

**What the port contributes, stated because a fake one usually contributes the
measurement.** The port answers each page from a counter and keeps only the page
it last answered, so nothing behind the seam grows with the result. A recording
port would grow on its own and would be most of every number below.

**What the exclusions are read for.** A bound that excluded nothing would be a
claim about the caller's program rather than about Parallax. The retaining arm
prices one root — what a caller pays to keep what it was handed — and is what
turns "the delivery holds a constant" into a statement with a unit: the constant
is worth so many roots of this graph.

Run it through `just python-report-stream-overhead`.
"""

from __future__ import annotations

import datetime as dt
import platform
import sys
import tracemalloc
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from time import perf_counter
from types import TracebackType
from typing import Any, Final, NamedTuple, cast

from parallax.conformance.story_models import ORDERS_MODEL, Order
from parallax.conformance.workloads import catalog
from parallax.core.db_port import (
    CleanupResult,
    DatabaseConnection,
    DocumentReadOrdinals,
    Returned,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.object_query._fluent import ObjectQuery
from parallax.snapshot import SnapshotStream
from parallax.snapshot.handle import Database

WORKSPACE: Final = Path(__file__).resolve().parents[1]
"""The one directory this report puts on the path, so it can read the instruments
the gated suites read as `tests.unit.memory_instruments` — the same one-way reach
its three siblings make, spelled once here."""

INSTRUMENT_MODULE: Final = WORKSPACE / "tests" / "unit" / "memory_instruments.py"
"""The exact file the reading is taken through.

``tests.unit.memory_instruments`` is resolved from a path this process does not
own, so prepending the workspace is only half of what makes the import
deterministic: a module of that name already in :data:`sys.modules` wins before
any path entry is consulted. The report therefore states which file it means and
refuses to measure through any other, because the alternative failure is silent —
a different definition of the sampling recipe would still produce a number, and
the number would not be the one the recorded baseline is stated over.
"""
sys.path.insert(0, str(WORKSPACE))

from tests.unit import memory_instruments  # noqa: E402

if Path(memory_instruments.__file__ or "").resolve() != INSTRUMENT_MODULE:
    raise ImportError(
        f"this report measures through {INSTRUMENT_MODULE}, but 'memory_instruments' "
        f"resolved to {memory_instruments.__file__}"
    )

from tests.unit.memory_instruments import (  # noqa: E402
    WARMUP,
    LiveGraph,
    Seam,
    live_graph,
    retained,
    untraced,
    warmed,
)

PAGE_SIZES: Final = (1, 2, 8, 32)
"""The dial, across a factor of thirty-two, so what it buys and what it costs are
read on the same table."""

FANOUT: Final = 5
"""Included children per root, so every page graph carries relationship fan-out
and the root the caller holds is a graph rather than a row."""

ROOTS: Final = 200
"""The result the readings are taken over."""

TENFOLD: Final = 10
"""The factor the independence reading multiplies the result by, holding the
position sampled fixed."""


def sample_after(batch_size: int) -> int:
    """Roots consumed before the sample, for a delivery at ``batch_size``.

    Inside the THIRD page at every page size, which is what makes each row a
    steady-state reading of its own dial setting rather than a reading of one
    fixed position that is the first page at the large sizes and the fortieth at
    the small ones.
    """
    return 2 * batch_size + 5


_TIMED: Final = 10
"""Whole deliveries behind each wall-clock figure. A mean over ten, printed for
direction only — nothing here is enforced against elapsed time."""

RETAINED_AT: Final = (20, 200)
"""Result sizes the retaining control is priced from: the caller-retention
exclusion, whose slope is what one root of this graph costs."""


_WORKLOAD: Final = catalog()["conventional-fanout"]


def _order_row(row: Mapping[str, object]) -> Row:
    return {
        "id": row["id"],
        "name": row["name"],
        "sku": row["sku"],
        "qty": row["qty"],
        "price": row["price"],
        "active": row["active"],
        "ordered_on": dt.date.fromisoformat(cast("str", row["orderedOn"])),
        "parallax_seek_0": row["id"],
    }


def _item_row(row: Mapping[str, object]) -> Row:
    return {
        "id": row["id"],
        "order_id": row["orderId"],
        "sku": row["sku"],
        "quantity": row["quantity"],
        "shipped_on": dt.date.fromisoformat(cast("str", row["shippedOn"])),
    }


class _SoleRuntime:
    """The whole resource lifetime around one in-memory connection.

    An instrument must not measure itself, so this records nothing: no
    acquisition list, no cleanup history, and no per-scope allocation beyond the
    context object the contract requires. Every acquisition hands over the same
    connection, because there is one and it is not a resource in any sense that
    would make sharing it wrong here.
    """

    dialect: Dialect = POSTGRES

    __slots__ = ("_connection",)

    def __init__(self, connection: DatabaseConnection) -> None:
        self._connection = connection

    @property
    def pool_metrics(self) -> None:
        return None

    def connection(self) -> _SoleScope:
        return _SoleScope(self._connection)

    def close(self) -> None:
        return


_RELINQUISHED: Final[CleanupResult] = Returned()
"""What a completed relinquishment establishes where nothing had to be reclaimed.

One shared immutable value rather than one per release: an instrument that
allocated a result per acquisition would be measuring itself.
"""


class _SoleScope:
    """One acquisition of the sole connection, which reclaims nothing."""

    __slots__ = ("_connection", "_left")

    def __init__(self, connection: DatabaseConnection) -> None:
        self._connection = connection
        self._left = False

    @property
    def cleanup_result(self) -> CleanupResult | None:
        """What letting go established, once it has happened.

        A double that IS its own connection reclaims nothing, but reclaiming
        nothing is a completed relinquishment rather than an absent one — and it
        is a shared immutable value, so an instrument reporting it still records
        nothing per acquisition.
        """
        return _RELINQUISHED if self._left else None

    def __enter__(self) -> DatabaseConnection:
        return self._connection

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None:
        self._left = True


class CatalogPort:
    """A port that answers each page from a counter and retains nothing beyond
    the page it last answered."""

    dialect: Dialect = POSTGRES

    __slots__ = ("_delivered", "_fanout", "_items", "_orders", "_page")

    def __init__(self, total: int, fanout: int = FANOUT) -> None:
        rows = _WORKLOAD.rows(total)
        if fanout != rows.fanout:
            raise ValueError(f"the catalog fixes fanout at {rows.fanout}, got {fanout}")
        self._fanout = fanout
        self._orders = rows.entity("parallax.compatibility.Order")
        self._items = rows.entity("parallax.compatibility.OrderItem")
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
                _item_row(row)
                for parent in self._page
                for row in self._items[(parent - 1) * self._fanout : parent * self._fanout]
            ]
        size = cast("int", binds[-1])
        taken = min(size, len(self._orders) - self._delivered)
        selected = self._orders[self._delivered : self._delivered + taken]
        self._page = tuple(cast("int", row["id"]) for row in selected)
        self._delivered += taken - 1 if taken == size else taken
        return [_order_row(row) for row in selected]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        raise NotImplementedError

    def transaction[T](
        self, body: Callable[[DatabaseConnection], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:
        raise NotImplementedError


def query() -> ObjectQuery[Order, Order]:
    return Order.where(Order.active == True).include(Order.items)  # noqa: E712 - the query algebra's own equality


class Lane(NamedTuple):
    """One representation and how a delivery of it opens."""

    name: str
    opener: Callable[[Database, int], SnapshotStream[Any]]


def _typed(database: Database, batch_size: int) -> SnapshotStream[Any]:
    return database.stream(query(), batch_size=batch_size)


def _wire(database: Database, batch_size: int) -> SnapshotStream[Any]:
    return database.wire.stream(query(), batch_size=batch_size)


LANES: Final = (Lane("typed", _typed), Lane("wire", _wire))


def paused(lane: Lane, total: int, *, batch_size: int) -> Seam:
    """A delivery of ``total`` roots sampled inside its third page, with that
    page's graph sealed, that root published, and the caller still holding it."""
    at = sample_after(batch_size)

    def seam(sample: Callable[[], None]) -> None:
        database = Database(_SoleRuntime(CatalogPort(total)), ORDERS_MODEL)
        with lane.opener(database, batch_size) as stream:
            for position, _root in enumerate(stream):
                if position == at:
                    sample()
                    return

    return seam


def draining(lane: Lane, total: int, *, batch_size: int, retaining: bool) -> Seam:
    """One whole delivery, sampled with its last page still open, keeping every
    root it was handed or none of them."""

    def seam(sample: Callable[[], None]) -> None:
        database = Database(_SoleRuntime(CatalogPort(total)), ORDERS_MODEL)
        held: list[object] = []
        with lane.opener(database, batch_size) as stream:
            for root in stream:
                if retaining:
                    held.append(root)
            sample()
        held.clear()

    return seam


def elapsed(lane: Lane, total: int, *, batch_size: int) -> float:
    """Seconds one whole delivery of ``total`` roots takes, meaned over repeats.

    Timed with the line tracer uninstalled, for the reason every window here is:
    under branch coverage the tracer's own per-line work is most of what a loop
    this tight would report.
    """
    seam = draining(lane, total, batch_size=batch_size, retaining=False)
    with untraced():
        for _ in range(3):
            seam(lambda: None)
        start = perf_counter()
        for _ in range(_TIMED):
            seam(lambda: None)
        return (perf_counter() - start) / _TIMED


class Reading(NamedTuple):
    """One lane at one page size: what a running delivery holds, and what the
    same reading answers over ten times the roots."""

    bytes_held: int
    bytes_at_tenfold: int
    graph: LiveGraph
    seconds: float


def read(lane: Lane, batch_size: int) -> Reading:
    return Reading(
        retained(paused(lane, ROOTS, batch_size=batch_size)),
        retained(paused(lane, ROOTS * TENFOLD, batch_size=batch_size)),
        live_graph(warmed(paused(lane, ROOTS, batch_size=batch_size))),
        elapsed(lane, ROOTS, batch_size=batch_size),
    )


def per_root_price(lane: Lane) -> float:
    """Bytes one retained root of this graph costs, from the caller-retention
    exclusion's own slope."""
    smaller, larger = RETAINED_AT
    low = retained(draining(lane, smaller, batch_size=8, retaining=True))
    high = retained(draining(lane, larger, batch_size=8, retaining=True))
    return (high - low) / (larger - smaller)


def _conditions() -> list[tuple[str, str]]:
    return [
        ("Python", f"CPython {platform.python_version()}"),
        ("Platform", f"{sys.platform}/{platform.machine()}"),
        ("Warm-up", f"{WARMUP} unsampled runs before every window"),
        (
            "Shape",
            f"{ROOTS} roots, fan-out {FANOUT}, one include level, "
            f"sampled inside the third page with the delivery still running",
        ),
    ]


def _lane_lines(lane: Lane, readings: dict[int, Reading], price: float) -> list[str]:
    header = (
        f"{'page':>6} {'at':>5} {'held B':>10} {'at 10x N':>10} {'delta':>8} {'roots':>7} "
        f"{'survivors':>10} {'inbound':>8} {'us/root':>9}"
    )
    lines = [f"{lane.name} delivery", header]
    for size in PAGE_SIZES:
        reading = readings[size]
        delta = reading.bytes_at_tenfold - reading.bytes_held
        lines.append(
            f"{size:>6} {sample_after(size):>5} "
            f"{reading.bytes_held:>10,} {reading.bytes_at_tenfold:>10,} "
            f"{delta:>+8,} {delta / price:>7.2f} "
            f"{len(reading.graph.survivors):>10,} {reading.graph.inbound:>8,} "
            f"{reading.seconds / ROOTS * 1e6:>9.1f}"
        )
    lines.append("")
    lines.append(
        f"  one retained root of this graph = {price:,.0f} B, so the `roots` column is "
        f"what ten times the result moved the working set by, in roots"
    )
    return lines


def _exclusion_lines(prices: dict[str, float]) -> list[str]:
    smaller, larger = RETAINED_AT
    lines = ["caller-retention exclusion (the growth the bound declines to prevent)"]
    for name, price in prices.items():
        lines.append(
            f"  {name:<6} {price:>8,.0f} B/root over {smaller} -> {larger} roots  "
            f"= {price * larger / 1024:,.0f} KiB at {larger} roots, against a working set "
            f"that did not move"
        )
    return lines


def main(argv: list[str]) -> int:
    """Measure and print; never judge.

    Exit codes: 0 — the measurement ran; 2 — usage error. There is no exit code
    for a number that is too large, deliberately.
    """
    if argv:
        print("usage: python tools/stream_overhead.py", file=sys.stderr)
        return 2

    tracemalloc.start()
    try:
        prices = {lane.name: per_root_price(lane) for lane in LANES}
        readings = {lane.name: {size: read(lane, size) for size in PAGE_SIZES} for lane in LANES}
    finally:
        tracemalloc.stop()

    lines = ["parallax streamed-delivery working set", ""]
    lines += [f"  {name:<10}{value}" for name, value in _conditions()]
    for lane in LANES:
        lines += ["", *_lane_lines(lane, readings[lane.name], prices[lane.name])]
    lines += ["", *_exclusion_lines(prices)]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
