"""Temporal writes through the public API against a real server, realized by
the shipped transport (`m-execution` *Flush execution*).

Each cell is a public temporal write — a keyed amendment, a Wire target
replacement, or a keyed amendment carrying collection documents — over its own
freshly seeded object. The one transaction a cell
runs must cross the port exactly as :func:`expected_realization` calculates
from the workload — ordered invocations of its closes where the acquired
connection holds ordered write transport, and multi-row inserts of its
openings — and must leave exactly the history :func:`expected_history`
calculates, each collection cell row still holding its seeded collections.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable
from typing import Any, Literal, cast

import psycopg
import pytest

from parallax.conformance._decoration import DecoratingAdapter
from parallax.conformance.scripted_clock import FixedClock
from parallax.core import Attr, Bitemporal, Document, DomainModel, ValueObject, attr
from parallax.core.base import INFINITY
from parallax.core.entity._model import model_of
from parallax.snapshot import ScopedDatabase, TxnContext, connect
from tests._support.root_ownership import own_root
from tests._support.temporal_write_transport import (
    AMENDED_AT,
    AMOUNT,
    CELLS,
    REPLACED_LABEL,
    SEEDED_AT,
    Cell,
    CountingConnection,
    HistoryRow,
    PortTally,
    Workload,
    expected_history,
    expected_realization,
    object_key,
    ordered_history,
    seeded_history,
    window,
)

_NAMESPACE = "transport.realization"


class TransportLeg(ValueObject):
    stops: Attr[tuple[str, ...]] = attr()


class KeyedSpan(Bitemporal, table="trn_keyed_span", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=24)
    amount: Attr[int]


class TargetSpan(Bitemporal, table="trn_target_span", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=24)
    amount: Attr[int]


class CollectionSpan(
    Bitemporal, table="trn_collection_span", namespace=_NAMESPACE, layout=Document()
):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=24)
    amount: Attr[int]
    tags: Attr[tuple[str, ...]] = attr()
    legs: Attr[tuple[TransportLeg, ...]] = attr()


_MODEL = DomainModel(KeyedSpan, TargetSpan, CollectionSpan)
_ENTITIES: dict[Workload, type[Any]] = {
    "keyed-amend": KeyedSpan,
    "target-replace": TargetSpan,
    "collection-amend": CollectionSpan,
}
_TABLES: dict[Workload, str] = {
    "keyed-amend": "trn_keyed_span",
    "target-replace": "trn_target_span",
    "collection-amend": "trn_collection_span",
}
_DOCUMENTED: frozenset[Workload] = frozenset({"target-replace", "collection-amend"})
_TAGS = ("a", "a", "", *(f"t{index}" for index in range(300)))
_LEGS: tuple[dict[str, list[str]], ...] = (
    {"stops": []},
    {"stops": ["x", "x"]},
    *({"stops": ["s"] * 40} for _ in range(20)),
)

type _Concurrency = Literal["optimistic", "locking"]


def _instant(value: object) -> str:
    if value is INFINITY:
        return "infinity"
    assert isinstance(value, dt.datetime)
    return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _fixtures(cell: Cell) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for seeded in seeded_history(cell.workload, cell.size, 0):
        row: dict[str, object] = {
            "id": seeded.key,
            "label": seeded.label,
            "amount": seeded.amount,
            "validStart": _instant(seeded.valid_from),
            "validEnd": _instant(seeded.valid_to),
            "txStart": _instant(seeded.tx_from),
            "txEnd": _instant(seeded.tx_to),
        }
        if cell.workload == "collection-amend":
            row["tags"] = list(_TAGS)
            row["legs"] = [dict(leg) for leg in _LEGS]
        rows.append(row)
    return {_ENTITIES[cell.workload].__name__: rows}


def _write(cell: Cell) -> Callable[[TxnContext], None]:
    workload = cell.workload
    start, end = window(cell.size)
    entity = _ENTITIES[workload]
    key = object_key(0)
    match workload:
        case "keyed-amend" | "collection-amend":

            def amend(tx: TxnContext) -> None:
                source = tx.find(entity.where(entity.id == key).as_of(valid_time=start)).result()
                tx.amend(source.edit(amount=AMOUNT), until=end)

            return amend
        case "target-replace":

            def replace(tx: TxnContext) -> None:
                tx.wire.replace_if(
                    entity.__name__,
                    {"id": key, "label": REPLACED_LABEL, "amount": AMOUNT},
                    tx_start=SEEDED_AT,
                    valid_from=start,
                    until=end,
                )

            return replace


def _concurrency(workload: Workload) -> _Concurrency:
    return "locking" if workload == "target-replace" else "optimistic"


def _stored(profile_run: Any, cell: Cell) -> tuple[list[HistoryRow], int | None]:
    """The cell's stored history, and for the collection cell how many of its
    rows hold collections other than the seeded ones."""
    table = _TABLES[cell.workload]
    key = object_key(0)
    bounds = [key, key]
    port = profile_run.port
    if cell.workload in _DOCUMENTED:
        ((document,),) = port.execute(
            "select column_name from information_schema.columns "
            "where table_name = %s and data_type = 'jsonb' and column_name not in ('tags', 'legs')",
            [table],
        )
        values = f"{document}->>'label', ({document}->>'amount')::int"
    else:
        document = None
        values = "label, amount"
    rows = ordered_history(
        HistoryRow(*cast("tuple[Any, ...]", row))
        for row in port.execute(
            f"select id, from_z, thru_z, in_z, out_z, {values} from {table} "
            "where id between %s and %s",
            bounds,
        )
    )
    if cell.workload != "collection-amend":
        return rows, None
    ((differing,),) = port.execute(
        f"select count(*) from {table} where id between %s and %s "
        f"and (({document}->'tags') is distinct from %s::jsonb "
        f"or ({document}->'legs') is distinct from %s::jsonb)",
        [*bounds, json.dumps(_TAGS), json.dumps(_LEGS)],
    )
    return rows, int(differing)


def _database(profile_run: Any, tally: PortTally) -> ScopedDatabase:
    decorated = DecoratingAdapter(
        profile_run.port, lambda connection: cast("Any", CountingConnection(connection, tally))
    )
    return own_root(connect(decorated, _MODEL, clock=FixedClock(AMENDED_AT))).using_database_login()


@pytest.mark.parametrize("cell", CELLS, ids=lambda cell: cell.id)
def test_a_temporal_write_crosses_the_port_as_calculated_and_leaves_its_history(
    profile_run: Any, cell: Cell
) -> None:
    profile_run.reset(model_of(_MODEL), _fixtures(cell))
    tally = PortTally()
    _database(profile_run, tally).transact(_write(cell), concurrency=_concurrency(cell.workload))
    stored, differing = _stored(profile_run, cell)
    expected = expected_history(cell.workload, cell.size, 0)
    assert stored == expected
    # Each closed milestone and each opened row is one Planned Step, however
    # the statements carried them.
    assert tally.logical_writes == len(expected)
    assert tally.realization() == expected_realization(
        cell, ordered=psycopg.capabilities.has_pipeline()
    )
    if differing is not None:
        assert differing == 0
