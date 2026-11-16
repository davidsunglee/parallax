"""What inserted values and a root's own bookkeeping keep, over a provider-free port.

Each reading runs inserts through the public verbs over a port that accepts every
statement and serializes its binds, so what is measured is the framework's side
of an insert: preparation, publication, buffering, flush, and commit. Three
attributions are read apart, for a Typed Columns and a Wire Document entity:

* ``results.discarded``: what one transaction of inserts keeps over repeated
  runs, and allocates and frees again in one, while its callback keeps none of
  the values it inserted;
* ``results.retained``: the bytes still reachable while the callback's caller
  holds the values those inserts carry, beside the same reading with nothing
  held, so their difference is what the caller's results cost; and
* ``root.retention``: what a root keeps across further completed transactions,
  read across a few and across many, which must be the same. Both start after
  a first stretch of transactions has already carried every counter the root
  keeps past CPython's cached small integers, so a counter's value growing a
  digit is not read as the root keeping something per transaction.

The provider's own pool and connection resources are not here: no connection
exists over this port.
"""

from __future__ import annotations

import sys
import tracemalloc
from collections.abc import Callable
from typing import Any, Final, Literal

from parallax.core import Attr, Document, DomainModel, Entity, attr
from parallax.snapshot import Database, ScopedDatabase, TxnContext
from tests._support.bindings import TEST_BINDING
from tests._support.pooled_key_diagnostic import Mode, requested, write_readings
from tests.unit._write_lowering_support import AcceptingPort
from tests.unit.memory_instruments import (
    REPEATS,
    WARMUP,
    Seam,
    allocation,
    in_a_child_interpreter,
    retained,
    retained_increment,
    serve_one_measurement,
)

_NAMESPACE: Final = "key.allocation.memory"


class Ledger(Entity, table="kam_ledger", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


class LedgerSheet(Entity, table="kam_ledger_sheet", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


_MODEL: Final = DomainModel(Ledger, LedgerSheet)
_SCHEMA: Final = "parallax.diagnostic.pooled-primary-keys.allocator-memory/1"
_ROWS: Final = 8
"""Values each measured transaction inserts."""
_SETTLED: Final = 40
"""Transactions a root completes before its retention is first sampled."""
_FEW: Final = 40
_MANY: Final = 160
_ROOT_WARMUP: Final = 10
"""Seam runs before a root-retention reading. Each run opens its own root and
completes hundreds of transactions, so a few already warm everything a
run reaches."""

type _Representation = Literal["typed", "wire"]
_REPRESENTATIONS: Final[tuple[_Representation, ...]] = ("typed", "wire")
_CELLS: Final = {"typed": "columns.typed", "wire": "document.wire"}


def _insert(tx: TxnContext, representation: _Representation, key: int) -> object:
    """Insert ``key`` and answer the value that carries the insertion."""
    if representation == "typed":
        value = Ledger(id=key, label="kept")
        tx.insert(value)
        return value
    return tx.wire.insert(f"{_NAMESPACE}.LedgerSheet", {"id": key, "label": "kept"})


def _transaction(
    representation: _Representation, held: list[object] | None
) -> Callable[[TxnContext], None]:
    def body(tx: TxnContext) -> None:
        for key in range(1, _ROWS + 1):
            value = _insert(tx, representation, key)
            if held is not None:
                held.append(value)

    return body


def _root() -> Database[Any]:
    return Database.connect(AcceptingPort(), _MODEL, binding=TEST_BINDING)


def _discarding(db: ScopedDatabase, representation: _Representation) -> Seam:
    def seam(sample: Callable[[], None]) -> None:
        db.transact(_transaction(representation, None))
        sample()

    return seam


def _holding(db: ScopedDatabase, representation: _Representation, *, hold: bool) -> Seam:
    held: list[object] = []

    def seam(sample: Callable[[], None]) -> None:
        db.transact(_transaction(representation, held if hold else None))
        sample()
        held.clear()

    return seam


def _over_transactions(representation: _Representation, settled: int, further: int) -> Seam:
    def seam(sample: Callable[[], None]) -> None:
        with _root() as root:
            db = root.using_database_login()
            for _ in range(settled):
                db.transact(_transaction(representation, None))
            sample()
            for _ in range(further):
                db.transact(_transaction(representation, None))
            sample()

    return seam


def _root_retention(seam: Seam) -> int:
    return retained_increment(seam, warmups=_ROOT_WARMUP)


def _reading[T](reader: Callable[[Seam], T], seam: Seam) -> T:
    tracemalloc.start()
    try:
        return reader(seam)
    finally:
        tracemalloc.stop()


def _record(cell: str, readings: dict[str, object]) -> None:
    mode, out = requested()
    if out is not None:
        write_readings(out, cell, _document(mode, cell, readings))


def _document(mode: Mode, cell: str, readings: dict[str, object]) -> dict[str, object]:
    return {
        "schema": _SCHEMA,
        "mode": mode,
        "cell": cell,
        "rowsPerTransaction": _ROWS,
        "warmup": WARMUP,
        **readings,
    }


@in_a_child_interpreter
def test_inserted_values_cost_only_while_their_caller_holds_them() -> None:
    for representation in _REPRESENTATIONS:
        with _root() as root:
            db = root.using_database_login()
            kept, transient = _reading(allocation, _discarding(db, representation))
            nothing_held = _reading(retained, _holding(db, representation, hold=False))
            values_held = _reading(retained, _holding(db, representation, hold=True))
        assert values_held > nothing_held
        cell = _CELLS[representation]
        _record(
            f"results.discarded.{cell}",
            {"keptOverRepeatsBytes": kept, "repeats": REPEATS, "transientBytes": transient},
        )
        _record(
            f"results.retained.{cell}",
            {
                "retainedNothingHeldBytes": nothing_held,
                "retainedValuesHeldBytes": values_held,
                "heldBytesPerValue": (values_held - nothing_held) / _ROWS,
            },
        )


@in_a_child_interpreter
def test_a_root_keeps_nothing_more_for_further_completed_transactions() -> None:
    for representation in _REPRESENTATIONS:
        few = _reading(_root_retention, _over_transactions(representation, _SETTLED, _FEW))
        many = _reading(_root_retention, _over_transactions(representation, _SETTLED, _MANY))
        assert many == few
        _record(
            f"root.retention.{_CELLS[representation]}",
            {
                "settledTransactions": _SETTLED,
                "warmup": _ROOT_WARMUP,
                "transactionsFew": _FEW,
                "transactionsMany": _MANY,
                "retainedIncrementFewBytes": few,
                "retainedIncrementManyBytes": many,
            },
        )


if __name__ == "__main__":
    serve_one_measurement(sys.argv[1])
