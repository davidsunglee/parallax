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

Every reading is taken in each mode a check run grades, or in the one mode a
capture names: ``assigned`` supplies each key, and ``generated`` omits it, so
each insert takes its key from a KeySequence whose blocks the port answers and
the root's allocator keeps, and a generated Typed insert answers a new value.

The provider's own pool and connection resources are not here: no connection
exists over this port.
"""

from __future__ import annotations

import sys
import tracemalloc
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final, Literal

from parallax.core import Attr, Document, DomainModel, Entity, KeySequence, attr
from parallax.core.internal.db_port import DocumentReadOrdinals, Row
from parallax.core.internal.dialect import POSTGRES
from parallax.snapshot import Database, ScopedDatabase, TxnContext
from tests._support.bindings import TEST_BINDING
from tests._support.pooled_key_diagnostic import MODES, Mode, requested, write_readings
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


_BATCH_SIZE: Final = 10_000
"""A block larger than every key one reading hands out, so a root-retention
window reads the handout state alone: a refill replaces its block's bounds in
place, and whether a window happens to span one would otherwise decide how many
freshly allocated integers it counts, not whether the root keeps more."""


class GeneratedLedger(Entity, table="kam_g_ledger", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=KeySequence("kam_g_ledger_ids", batch_size=_BATCH_SIZE))
    label: Attr[str] = attr(max_length=16)


class GeneratedLedgerSheet(
    Entity, table="kam_g_ledger_sheet", namespace=_NAMESPACE, layout=Document()
):
    id: Attr[int] = attr(primary_key=KeySequence("kam_g_ledger_sheet_ids", batch_size=_BATCH_SIZE))
    label: Attr[str] = attr(max_length=16)


_MODELS: Final[Mapping[Mode, DomainModel]] = {
    "assigned": DomainModel(Ledger, LedgerSheet),
    "generated": DomainModel(GeneratedLedger, GeneratedLedgerSheet),
}
_RESERVE: Final = POSTGRES.reserve_sequence()
_CURSOR_BYTES: Final = 32
"""The traced size of one integer: a generated root's reservation holds its next
key as a fresh integer each handout, which CPython either allocates or takes
from its integer free list, so whether a window traces it varies by one
integer and never grows with the transactions the window spans."""
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


class _ReservingPort(AcceptingPort):
    """The accepting port, answering each key reservation with its sequence's
    next block as a live sequence matching its declaration would."""

    __slots__ = ("_next",)

    def __init__(self) -> None:
        super().__init__()
        self._next: dict[object, int] = {}

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
        *,
        read_only: bool = False,
    ) -> list[Row]:
        if sql != _RESERVE:
            return super().execute(sql, binds, document_reads, read_only=read_only)
        (sequence,) = binds
        first = self._next.get(sequence, 1)
        self._next[sequence] = first + _BATCH_SIZE
        return [(first, _BATCH_SIZE, -(2**63), 2**63 - 1, False, "bigint")]


def _insert(tx: TxnContext, mode: Mode, representation: _Representation, key: int) -> object:
    """Insert ``key``, or a keyless value in generated mode, and answer the
    value that carries the insertion."""
    if representation == "typed":
        if mode == "assigned":
            return tx.insert(Ledger(id=key, label="kept"))
        return tx.insert(GeneratedLedger(label="kept"))
    if mode == "assigned":
        return tx.wire.insert(f"{_NAMESPACE}.LedgerSheet", {"id": key, "label": "kept"})
    return tx.wire.insert(f"{_NAMESPACE}.GeneratedLedgerSheet", {"label": "kept"})


def _transaction(
    mode: Mode, representation: _Representation, held: list[object] | None
) -> Callable[[TxnContext], None]:
    def body(tx: TxnContext) -> None:
        for key in range(1, _ROWS + 1):
            value = _insert(tx, mode, representation, key)
            if held is not None:
                held.append(value)

    return body


def _root(mode: Mode) -> Database[Any]:
    port = AcceptingPort() if mode == "assigned" else _ReservingPort()
    return Database.connect(port, _MODELS[mode], binding=TEST_BINDING)


def _modes() -> tuple[Mode, ...]:
    """Every mode a check run grades, or the one a capture names."""
    mode, out = requested()
    return MODES if out is None else (mode,)


def _discarding(db: ScopedDatabase, mode: Mode, representation: _Representation) -> Seam:
    def seam(sample: Callable[[], None]) -> None:
        db.transact(_transaction(mode, representation, None))
        sample()

    return seam


def _holding(
    db: ScopedDatabase, mode: Mode, representation: _Representation, *, hold: bool
) -> Seam:
    held: list[object] = []

    def seam(sample: Callable[[], None]) -> None:
        db.transact(_transaction(mode, representation, held if hold else None))
        sample()
        held.clear()

    return seam


def _over_transactions(
    mode: Mode, representation: _Representation, settled: int, further: int
) -> Seam:
    def seam(sample: Callable[[], None]) -> None:
        with _root(mode) as root:
            db = root.using_database_login()
            for _ in range(settled):
                db.transact(_transaction(mode, representation, None))
            sample()
            for _ in range(further):
                db.transact(_transaction(mode, representation, None))
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


def _record(mode: Mode, cell: str, readings: dict[str, object]) -> None:
    _, out = requested()
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
    for mode in _modes():
        for representation in _REPRESENTATIONS:
            _read_results(mode, representation)


def _read_results(mode: Mode, representation: _Representation) -> None:
    with _root(mode) as root:
        db = root.using_database_login()
        kept, transient = _reading(allocation, _discarding(db, mode, representation))
        nothing_held = _reading(retained, _holding(db, mode, representation, hold=False))
        values_held = _reading(retained, _holding(db, mode, representation, hold=True))
    assert values_held > nothing_held
    cell = _CELLS[representation]
    _record(
        mode,
        f"results.discarded.{cell}",
        {"keptOverRepeatsBytes": kept, "repeats": REPEATS, "transientBytes": transient},
    )
    _record(
        mode,
        f"results.retained.{cell}",
        {
            "retainedNothingHeldBytes": nothing_held,
            "retainedValuesHeldBytes": values_held,
            "heldBytesPerValue": (values_held - nothing_held) / _ROWS,
        },
    )


@in_a_child_interpreter
def test_a_root_keeps_nothing_more_for_further_completed_transactions() -> None:
    for mode in _modes():
        for representation in _REPRESENTATIONS:
            _read_root_retention(mode, representation)


def _read_root_retention(mode: Mode, representation: _Representation) -> None:
    few = _reading(_root_retention, _over_transactions(mode, representation, _SETTLED, _FEW))
    many = _reading(_root_retention, _over_transactions(mode, representation, _SETTLED, _MANY))
    allowance = 0 if mode == "assigned" else _CURSOR_BYTES
    assert abs(many - few) <= allowance, (mode, representation, few, many)
    _record(
        mode,
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
