"""The streamed read's memory bound, measured (`cost` class).

A streamed read exists to make the Parallax-owned working set independent of the
total number of roots. This suite is the instrument for that claim on the
simplest slice it holds for: one page's sealed graph plus one root's merge and
publication, with page graphs that do not accumulate as the result grows.

Two readings, taken over the same seam and differing only in what the CALLER
does with each root. Draining and dropping is the bound: what the stream keeps
at ten times the roots differs from what it keeps at one times by less than one
root costs. Draining and retaining is the exclusion beside it, and it is what
makes the first reading mean something — values a caller deliberately holds are
outside the bound on purpose, so the same seam reproduces growth proportional to
the result and supplies the per-root price the first reading is compared against.

Every reading reads a whole interpreter, so each runs in one of its own behind
``in_a_child_interpreter`` and the class is CI's rather than the merge gate's.
"""

from __future__ import annotations

import datetime as dt
import sys
import tracemalloc
from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Any, Final, cast

from memory_instruments import Seam, in_a_child_interpreter, retained, serve_one_measurement

from parallax.conformance.story_models import ORDERS_MODEL, Order
from parallax.core.db_port import DbPort, DocumentReadOrdinals, Row, TransactionOutcome
from parallax.core.object_query._fluent import ObjectQuery
from parallax.snapshot.handle import Database

_SMALL: Final = 20
"""Roots in the small reading — enough for several pages at the page size below."""

_LARGE: Final = 200
"""Ten times the small reading, which is the whole shape of the claim: what the
stream keeps may not scale with this number."""

_BATCH: Final = 8
"""Root positions per page. Small enough that both readings page many times, so
what is measured is the steady state rather than one page holding everything."""

_FANOUT: Final = 2
"""Included children per root, so a page graph holds relationship fanout rather
than bare roots and `P_B` is measured over something with depth."""


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


class _GeneratingPort:
    """A port that answers each page from a counter and retains nothing.

    A recording port would grow with the result on its own and swamp the reading
    it is there to take, so this one holds exactly the page it last answered:
    the parent keys the child level is about to gather, and how far through the
    result it is.
    """

    __slots__ = ("_delivered", "_page", "_total")

    def __init__(self, total: int) -> None:
        self._total = total
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
                for offset in range(_FANOUT)
            ]
        size = cast("int", binds[-1])
        taken = min(size, self._total - self._delivered)
        self._page = tuple(range(self._delivered + 1, self._delivered + taken + 1))
        self._delivered += taken
        return [_order_row(order_id) for order_id in self._page]

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise NotImplementedError

    def transaction[T](
        self, body: Callable[[DbPort], T]
    ) -> TransactionOutcome[T]:  # pragma: no cover
        raise NotImplementedError


def _query() -> ObjectQuery[Order, Order]:
    return Order.where(Order.active == True).include(Order.items)  # noqa: E712 - the query algebra's own equality


def _draining(total: int, *, retaining: bool) -> Seam:
    """One whole stream of ``total`` roots, sampled with the last page still open.

    The handle and the port are built inside the seam, so everything the reading
    could attribute to the stream was allocated inside its own window.
    """

    def seam(sample: Callable[[], None]) -> None:
        database = Database(cast("DbPort", _GeneratingPort(total)), ORDERS_MODEL)
        held: list[Any] = []
        with database.stream(_query(), batch_size=_BATCH) as stream:
            for root in stream:
                if retaining:
                    held.append(root)
            sample()
        held.clear()

    return seam


@in_a_child_interpreter
def test_a_streamed_read_keeps_no_more_at_ten_times_the_roots() -> None:
    # The headline claim, in arithmetic. The per-root price comes from the
    # retaining arm rather than from a constant, so the comparison is against
    # what one root of THIS graph actually costs on THIS interpreter — and the
    # streamed arm has to come in under one of them across nine times as many.
    tracemalloc.start()
    try:
        streamed = retained(_draining(_LARGE, retaining=False)) - retained(
            _draining(_SMALL, retaining=False)
        )
        retaining = retained(_draining(_LARGE, retaining=True)) - retained(
            _draining(_SMALL, retaining=True)
        )
    finally:
        tracemalloc.stop()
    per_root = retaining // (_LARGE - _SMALL)
    assert per_root > 0
    assert abs(streamed) < per_root


if __name__ == "__main__":
    serve_one_measurement(sys.argv[1])
