"""Temporal writes through the public API against a real server, realized by
the shipped transport (`m-execution` *Flush execution*).

Each cell is a public temporal write — a keyed amendment, a Wire target
replacement, a keyed amendment carrying collection documents, or keyed
amendments alternating between two Entities — over each of its freshly seeded
objects. The one transaction a cell runs must cross the port exactly as
:func:`expected_realization` calculates from the workload — ordered invocations
of its closes where the acquired connection holds ordered write transport, and
multi-row inserts of its openings within the bind limit the connection reports
— its one flush must make exactly the calls :func:`expected_flush_calls`
calculates, and it must leave exactly the history :func:`expected_history`
calculates, each collection cell row still holding its seeded collections.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable, Sequence
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
    expected_flush_calls,
    expected_history,
    expected_realization,
    object_key,
    ordered_history,
    seeded_history,
    window,
)
from tests.api._flush_calls import FlushCalls, call_runs

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
_ENTITIES: dict[Workload, tuple[type[Any], ...]] = {
    "keyed-amend": (KeyedSpan,),
    "target-replace": (TargetSpan,),
    "collection-amend": (CollectionSpan,),
    "interleaved-amend": (KeyedSpan, TargetSpan),
}
"""Each workload's Entities; a sample's object belongs to the one its index
selects in turn."""
_TABLES: dict[type[Any], str] = {
    KeyedSpan: "trn_keyed_span",
    TargetSpan: "trn_target_span",
    CollectionSpan: "trn_collection_span",
}
_DOCUMENTED: frozenset[type[Any]] = frozenset({TargetSpan, CollectionSpan})
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


def _entity(cell: Cell, sample: int) -> type[Any]:
    entities = _ENTITIES[cell.workload]
    return entities[sample % len(entities)]


def _fixtures(cell: Cell) -> dict[str, object]:
    fixtures: dict[str, list[dict[str, object]]] = {}
    for sample in range(cell.objects):
        rows = fixtures.setdefault(_entity(cell, sample).__name__, [])
        for seeded in seeded_history(cell.workload, cell.size, sample):
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
    return dict(fixtures)


def _keys(cell: Cell, entity: type[Any]) -> list[int]:
    return [object_key(sample) for sample in range(cell.objects) if _entity(cell, sample) is entity]


def _write(cell: Cell) -> Callable[[TxnContext], None]:
    """Every object's write, in key order, buffered for the one pre-commit
    flush. An amendment edits what one read of each Entity's objects, as of
    the window's start, answered."""
    start, end = window(cell.size)
    entities = _ENTITIES[cell.workload]
    samples = range(cell.objects)
    if cell.workload == "target-replace":
        (entity,) = entities

        def replace(tx: TxnContext) -> None:
            for sample in samples:
                tx.wire.replace_if(
                    entity.__name__,
                    {"id": object_key(sample), "label": REPLACED_LABEL, "amount": AMOUNT},
                    tx_start=SEEDED_AT,
                    valid_from=start,
                    until=end,
                )

        return replace

    def amend(tx: TxnContext) -> None:
        sources: dict[int, Any] = {}
        for entity in entities:
            keys = _keys(cell, entity)
            query = entity.where(entity.id.between(keys[0], keys[-1])).as_of(valid_time=start)
            sources.update((source.id, source) for source in tx.find(query).results())
        for sample in samples:
            tx.amend(sources[object_key(sample)].edit(amount=AMOUNT), until=end)

    return amend


def _concurrency(workload: Workload) -> _Concurrency:
    return "locking" if workload == "target-replace" else "optimistic"


def _stored_rows(profile_run: Any, cell: Cell, entity: type[Any]) -> list[HistoryRow]:
    table = _TABLES[entity]
    keys = _keys(cell, entity)
    if entity in _DOCUMENTED:
        document = _document_column(profile_run, table)
        values = f"{document}->>'label', ({document}->>'amount')::int"
    else:
        values = "label, amount"
    return [
        HistoryRow(*cast("tuple[Any, ...]", row))
        for row in profile_run.port.execute(
            f"select id, from_z, thru_z, in_z, out_z, {values} from {table} "
            "where id between %s and %s",
            [keys[0], keys[-1]],
        )
    ]


def _document_column(profile_run: Any, table: str) -> str:
    ((document,),) = profile_run.port.execute(
        "select column_name from information_schema.columns "
        "where table_name = %s and data_type = 'jsonb' and column_name not in ('tags', 'legs')",
        [table],
    )
    return cast("str", document)


def _stored(profile_run: Any, cell: Cell) -> tuple[list[HistoryRow], int | None]:
    """The cell's stored history, and for the collection cell how many of its
    rows hold collections other than the seeded ones."""
    rows = ordered_history(
        row
        for entity in _ENTITIES[cell.workload]
        for row in _stored_rows(profile_run, cell, entity)
    )
    if cell.workload != "collection-amend":
        return rows, None
    document = _document_column(profile_run, _TABLES[CollectionSpan])
    ((differing,),) = profile_run.port.execute(
        f"select count(*) from {_TABLES[CollectionSpan]} where id between %s and %s "
        f"and (({document}->'tags') is distinct from %s::jsonb "
        f"or ({document}->'legs') is distinct from %s::jsonb)",
        [object_key(0), object_key(cell.objects - 1), json.dumps(_TAGS), json.dumps(_LEGS)],
    )
    return rows, int(differing)


def _expected_history(cell: Cell) -> list[HistoryRow]:
    return ordered_history(
        row
        for sample in range(cell.objects)
        for row in expected_history(cell.workload, cell.size, sample)
    )


def _database(profile_run: Any, tally: PortTally, cell: Cell, calls: FlushCalls) -> ScopedDatabase:
    decorated = DecoratingAdapter(
        profile_run.port,
        lambda connection: cast("Any", CountingConnection(connection, tally, cell.connection)),
    )
    return own_root(
        connect(decorated, _MODEL, clock=FixedClock(AMENDED_AT), lifecycle_provider=calls)
    ).using_database_login()


def _flush_runs(calls: FlushCalls) -> Sequence[tuple[str, list[tuple[str, int | None]]]]:
    return [(flush.trigger, call_runs(flush.calls)) for flush in calls.flushes]


@pytest.mark.parametrize("cell", CELLS, ids=lambda cell: cell.id)
def test_a_temporal_write_crosses_the_port_as_calculated_and_leaves_its_history(
    profile_run: Any, cell: Cell
) -> None:
    profile_run.reset(model_of(_MODEL), _fixtures(cell))
    tally = PortTally()
    calls = FlushCalls()
    _database(profile_run, tally, cell, calls).transact(
        _write(cell), concurrency=_concurrency(cell.workload)
    )
    stored, differing = _stored(profile_run, cell)
    expected = _expected_history(cell)
    assert stored == expected
    # Each closed milestone and each opened row is one Planned Step, however
    # the statements carried them.
    assert tally.logical_writes == len(expected)
    assert tally.realization() == expected_realization(
        cell, ordered=psycopg.capabilities.has_pipeline()
    )
    assert _flush_runs(calls) == [("pre_commit", expected_flush_calls(cell))]
    if differing is not None:
        assert differing == 0
