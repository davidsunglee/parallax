from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Final, Literal, cast

from parallax.conformance import models
from parallax.conformance._lifecycle_observation import LifecycleObservation
from parallax.conformance.story_models import ORDERS_MODEL, Order
from parallax.conformance.workloads import Provisioning, catalog
from parallax.core import Attr, Bitemporal, Document, DomainModel, ObjectQuery, TxTemporal, attr
from parallax.snapshot import ScopedDatabase
from tests._support.bindings import TEST_BINDING

ROOTS: Final = 200
PAGE_SIZE: Final = 32
GROUP: Final = "live-reads"
PREFIX: Final = "live-read-"
WORKLOAD_IDS: Final = ("conventional-fanout", "historical-txtime", "historical-bitemporal")
LANES: Final = ("typed", "wire")
FORMS: Final = ("eager", "page32")
TX_BOUNDARIES: Final = tuple(dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 4, 7))
TX_INSTANT: Final = dt.datetime(2024, 5, 1, tzinfo=dt.UTC)
VALID_BOUNDARIES: Final = tuple(dt.datetime(2023, month, 1, tzinfo=dt.UTC) for month in (1, 5, 9))
VALID_INSTANT: Final = dt.datetime(2023, 6, 1, tzinfo=dt.UTC)

type Lane = Literal["typed", "wire"]
type Form = Literal["eager", "page32"]


class HistoricalLedger(TxTemporal, table="live_read_ledger", namespace="benchmark.live"):
    id: Attr[int] = attr(primary_key=True)
    payload: Attr[str]


class HistoricalPosition(
    Bitemporal, table="live_read_position", namespace="benchmark.live", layout=Document()
):
    id: Attr[int] = attr(primary_key=True)
    payload: Attr[str]


_MODELS: Final = {
    "conventional-fanout": ORDERS_MODEL,
    "historical-txtime": DomainModel(HistoricalLedger),
    "historical-bitemporal": DomainModel(HistoricalPosition),
}


def domain_model(workload: str) -> DomainModel:
    return _MODELS[workload]


def cells() -> tuple[tuple[str, str], ...]:
    """Only additional readings; conventional Wire keeps its existing contract addresses."""
    return tuple(
        (f"{PREFIX}{workload}", f"live.{lane}.{form}.maxMs")
        for workload in WORKLOAD_IDS
        for lane in LANES
        for form in FORMS
        if (workload, lane) != ("conventional-fanout", "wire")
    )


def address(workload: str, cell: str) -> tuple[str, Lane, Form] | None:
    if not workload.startswith(PREFIX):
        return None
    if (workload, cell) not in cells():
        raise ValueError(f"unknown live read address {workload}.{cell}")
    _, lane, form, _ = cell.split(".")
    return workload.removeprefix(PREFIX), cast("Lane", lane), cast("Form", form)


def typed_query(workload: str) -> ObjectQuery[Any, Any]:
    if workload == "conventional-fanout":
        return Order.where(Order.all).include(Order.items)
    if workload == "historical-txtime":
        return HistoricalLedger.where(HistoricalLedger.all).as_of(tx_time=TX_INSTANT)
    if workload == "historical-bitemporal":
        return HistoricalPosition.where(HistoricalPosition.all).as_of(
            tx_time=TX_INSTANT, valid_time=VALID_INSTANT
        )
    raise ValueError(workload)


def _instant(value: dt.datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def history_rows(workload: str) -> list[dict[str, object]]:
    if workload not in WORKLOAD_IDS[1:]:
        raise ValueError(workload)
    rows: list[dict[str, object]] = []
    intervals = 2 if workload == "historical-bitemporal" else 1
    for key in range(1, ROOTS + 1):
        for version, start in enumerate(TX_BOUNDARIES):
            for interval in range(intervals):
                row: dict[str, object] = {
                    "id": key,
                    "payload": f"key-{key}:version-{version}:interval-{interval}",
                    "txStart": _instant(start),
                    "txEnd": _instant(TX_BOUNDARIES[version + 1]) if version < 2 else "infinity",
                }
                if intervals == 2:
                    row.update(
                        validStart=_instant(VALID_BOUNDARIES[interval]),
                        validEnd=_instant(VALID_BOUNDARIES[interval + 1]),
                    )
                rows.append(row)
    return rows


def provision(workload: str, provisioner: Provisioning) -> None:
    if workload == "conventional-fanout":
        catalog()[workload].validate_class_backed(ORDERS_MODEL, typed_query(workload))
        catalog()[workload].provision(provisioner, ROOTS)
        return
    model = models.accepted_model_of(domain_model(workload))
    entity = model.entities[0].identity.canonical
    provisioner.reset(model, {entity: history_rows(workload)}, TEST_BINDING)


def wire_query(workload: str) -> Mapping[str, object]:
    model = models.accepted_model_of(domain_model(workload))
    temporal = {"transaction-time": {"asOf": _instant(TX_INSTANT)}}
    if workload == "historical-bitemporal":
        temporal["valid-time"] = {"asOf": _instant(VALID_INSTANT)}
    return {
        "target": model.entities[0].identity.canonical,
        "predicate": {"true": {}},
        "temporal": temporal,
    }


def _query(database: ScopedDatabase, workload: str, lane: Lane) -> tuple[Any, Any]:
    if lane == "typed":
        return database, typed_query(workload)
    wire = catalog()[workload].query if workload == "conventional-fanout" else wire_query(workload)
    return database.wire, wire


def read(database: ScopedDatabase, workload: str, lane: Lane, form: Form) -> int:
    """Consume complete public delivery without projecting the Typed result."""
    api, query = _query(database, workload, lane)
    if form == "eager":
        return len(api.find(query).results())
    count = 0
    with api.stream(query, batch_size=PAGE_SIZE) as stream:
        for _row in stream:
            count += 1
    return count


def _value(row: Any, lane: Lane, typed: str, wire: str | None = None) -> Any:
    return getattr(row, typed) if lane == "typed" else row[wire or typed]


def _text(value: object) -> str:
    if isinstance(value, dt.datetime):
        return _instant(value)
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, str) and "T" in value:
        return _instant(dt.datetime.fromisoformat(value))
    return str(value)


def _normalized(row: Any, workload: str, lane: Lane) -> tuple[object, ...]:
    def value(typed: str, wire: str | None = None) -> Any:
        return _value(row, lane, typed, wire)

    if workload == "conventional-fanout":
        items = tuple(
            (
                _value(item, lane, "id"),
                _value(item, lane, "order_id", "orderId"),
                _value(item, lane, "sku"),
                _value(item, lane, "quantity"),
                _text(_value(item, lane, "shipped_on", "shippedOn")),
            )
            for item in value("items")
        )
        return (
            value("id"),
            value("name"),
            value("sku"),
            value("qty"),
            Decimal(str(value("price"))),
            value("active"),
            _text(value("ordered_on", "orderedOn")),
            items,
        )
    result = (
        value("id"),
        value("payload"),
        _text(value("tx_start", "txStart")),
        _text(value("tx_end", "txEnd")),
    )
    if workload == "historical-bitemporal":
        result += (
            _text(value("valid_start", "validStart")),
            _text(value("valid_end", "validEnd")),
        )
    return result


def expected(workload: str) -> tuple[tuple[object, ...], ...]:
    if workload == "conventional-fanout":
        source = catalog()[workload].rows(ROOTS)
        orders = source.entity("parallax.compatibility.Order")
        children = source.entity("parallax.compatibility.OrderItem")
        rows = (
            {
                **row,
                "items": sorted(
                    (item for item in children if item["orderId"] == row["id"]),
                    key=lambda item: cast("int", item["id"]),
                    reverse=True,
                ),
            }
            for row in orders
        )
        return tuple(_normalized(row, workload, "wire") for row in rows)
    interval = 1 if workload == "historical-bitemporal" else 0
    return tuple(
        (
            key,
            f"key-{key}:version-1:interval-{interval}",
            _instant(TX_BOUNDARIES[1]),
            _instant(TX_BOUNDARIES[2]),
            *((_instant(VALID_BOUNDARIES[1]), _instant(VALID_BOUNDARIES[2])) if interval else ()),
        )
        for key in range(1, ROOTS + 1)
    )


def verify(
    database: ScopedDatabase, workload: str, observation: LifecycleObservation
) -> Mapping[str, int]:
    """Untimed exact payload, identity, membership, temporal and statement proof for all forms."""
    wanted = expected(workload)
    counts: dict[str, int] = {}
    for lane in LANES:
        for form in FORMS:
            mark = len(observation.calls)
            api, query = _query(database, workload, lane)
            if form == "eager":
                rows = api.find(query).results()
            else:
                with api.stream(query, batch_size=PAGE_SIZE) as stream:
                    rows = tuple(stream)
            actual = tuple(
                sorted(
                    (_normalized(row, workload, lane) for row in rows),
                    key=lambda row: cast("int", row[0]),
                )
            )
            if actual != wanted:
                raise ValueError(f"{workload}.{lane}.{form}: delivered rows differ from fixture")
            count = sum(call.kind == "read" for call in observation.calls[mark:])
            wanted_count = (1 if form == "eager" else 7) * (
                2 if workload == "conventional-fanout" else 1
            )
            if count != wanted_count:
                raise ValueError(
                    f"{workload}.{lane}.{form}: {count} read statements, expected {wanted_count}"
                )
            counts[f"{lane}.{form}"] = count
    return counts
