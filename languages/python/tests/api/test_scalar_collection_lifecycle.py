"""Scalar collections follow their owner's write lifecycle under both layouts.

A collection is a whole-member scalar attribute: keyed, conditional, target,
and predicate-selected writes assign it whole, a replacement fills one it omits
with the empty collection, versions advance and temporal milestones chain as
for any other member, and an equal collection is an unchanged value. Expected
stored arrays are spelled independently here.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Literal

import pytest

from parallax.conformance.scripted_clock import FixedClock, ScriptedClock
from parallax.core import (
    Attr,
    Bitemporal,
    Document,
    DomainModel,
    Entity,
    TxTemporal,
    ValueObject,
    attr,
)
from parallax.core.entity._model import model_of
from parallax.snapshot import ScopedDatabase, Transaction, connect
from tests._support.root_ownership import own_root

_NAMESPACE = "scalar.collection.lifecycle"
_AT = dt.datetime(2024, 6, 15, tzinfo=dt.UTC)


class Leg(ValueObject):
    stops: Attr[tuple[str, ...]] = attr()


class Route(ValueObject):
    name: Attr[str]
    leg: Attr[Leg | None] = attr()


class ColumnsTicket(Entity, table="scl_columns_ticket", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str]
    tags: Attr[tuple[str, ...]] = attr()
    amounts: Attr[tuple[Decimal, ...]] = attr(precision=8, scale=2)
    route: Attr[Route | None] = attr()
    legs: Attr[tuple[Leg, ...]] = attr()
    version: Attr[int] = attr(optimistic_locking=True)


class DocumentTicket(Entity, table="scl_document_ticket", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str]
    tags: Attr[tuple[str, ...]] = attr()
    amounts: Attr[tuple[Decimal, ...]] = attr(precision=8, scale=2)
    route: Attr[Route | None] = attr()
    legs: Attr[tuple[Leg, ...]] = attr()
    version: Attr[int] = attr(optimistic_locking=True)


class ColumnsBoard(Entity, table="scl_columns_board", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    tags: Attr[tuple[str, ...]] = attr()
    route: Attr[Route | None] = attr()
    legs: Attr[tuple[Leg, ...]] = attr()


class DocumentBoard(Entity, table="scl_document_board", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    tags: Attr[tuple[str, ...]] = attr()
    route: Attr[Route | None] = attr()
    legs: Attr[tuple[Leg, ...]] = attr()


class ColumnsSpan(Bitemporal, table="scl_columns_span", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    tags: Attr[tuple[str, ...]] = attr()


class DocumentSpan(Bitemporal, table="scl_document_span", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    tags: Attr[tuple[str, ...]] = attr()


class ColumnsLog(TxTemporal, table="scl_columns_log", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    tags: Attr[tuple[str, ...]] = attr()


class DocumentLog(TxTemporal, table="scl_document_log", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    tags: Attr[tuple[str, ...]] = attr()


_MODEL = DomainModel(
    ColumnsTicket,
    DocumentTicket,
    ColumnsBoard,
    DocumentBoard,
    ColumnsSpan,
    DocumentSpan,
    ColumnsLog,
    DocumentLog,
)
_DOCUMENT = (DocumentTicket, DocumentBoard, DocumentSpan, DocumentLog)
_TABLES: dict[type[Any], str] = {
    ColumnsTicket: "scl_columns_ticket",
    DocumentTicket: "scl_document_ticket",
    ColumnsBoard: "scl_columns_board",
    DocumentBoard: "scl_document_board",
    ColumnsSpan: "scl_columns_span",
    DocumentSpan: "scl_document_span",
    ColumnsLog: "scl_columns_log",
    DocumentLog: "scl_document_log",
}

type _Representation = Literal["typed", "wire"]
type _Concurrency = Literal["optimistic", "locking"]

_TICKETS = pytest.mark.parametrize(
    "entity", [ColumnsTicket, DocumentTicket], ids=["columns", "document"]
)
_BOARDS = pytest.mark.parametrize(
    "entity", [ColumnsBoard, DocumentBoard], ids=["columns", "document"]
)
_SPANS = pytest.mark.parametrize("entity", [ColumnsSpan, DocumentSpan], ids=["columns", "document"])
_LOGS = pytest.mark.parametrize("entity", [ColumnsLog, DocumentLog], ids=["columns", "document"])
_REPRESENTATIONS = pytest.mark.parametrize("representation", ["typed", "wire"])
_STRATEGIES = pytest.mark.parametrize("concurrency", ["optimistic", "locking"])


def _db(profile_run: Any, *instants: dt.datetime) -> ScopedDatabase:
    clock = ScriptedClock(list(instants)) if instants else FixedClock(_AT)
    return own_root(connect(profile_run.port, _MODEL, clock=clock)).using_database_login()


def _reset(profile_run: Any) -> None:
    profile_run.reset(model_of(_MODEL), {})


def _name(entity: type[Any]) -> str:
    return f"{_NAMESPACE}.{entity.__name__}"


def _member(entity: type[Any], member: str) -> str:
    return f"payload->'{member}'" if entity in _DOCUMENT and member != "version" else member


def _stored(profile_run: Any, entity: type[Any], *members: str) -> list[tuple[object, ...]]:
    cells = ", ".join(_member(entity, member) for member in members)
    return [
        tuple(row)
        for row in profile_run.port.execute(
            f"select {cells} from {_TABLES[entity]} order by id", []
        )
    ]


def _by_id(entity: type[Any], key: int) -> dict[str, object]:
    name = _name(entity)
    return {"target": name, "predicate": {"eq": {"path": f"{name}.id", "value": key}}}


def _find(tx: Transaction, entity: type[Any], representation: _Representation) -> Any:
    if representation == "typed":
        return tx.find(entity.where(entity.id == 1)).result()
    return tx.wire.find(_by_id(entity, 1)).result()


# --------------------------------------------------------------------------- #
# Versioned Non-Temporal owners.                                               #
# --------------------------------------------------------------------------- #
def _seed_ticket(profile_run: Any, entity: type[Any]) -> ScopedDatabase:
    _reset(profile_run)
    db = _db(profile_run)
    db.transact(
        lambda tx: tx.insert(
            entity(
                id=1,
                label="seed",
                tags=("a", "b", "a"),
                amounts=(Decimal("1.5"),),
                route=Route(name="r", leg=Leg(stops=("x", "y"))),
                legs=(Leg(stops=("p",)), Leg(stops=())),
            )
        )
    )
    return db


@_STRATEGIES
@_REPRESENTATIONS
@_TICKETS
def test_a_keyed_amendment_assigns_a_collection_and_advances_the_version(
    profile_run: Any,
    entity: type[Any],
    representation: _Representation,
    concurrency: _Concurrency,
) -> None:
    db = _seed_ticket(profile_run, entity)

    def fn(tx: Transaction) -> None:
        source = _find(tx, entity, representation)
        if representation == "typed":
            tx.amend(source.edit(tags=("c", "c")))
        else:
            tx.wire.amend(source, {"tags": ["c", "c"]})

    db.transact(fn, concurrency=concurrency)
    assert _stored(profile_run, entity, "tags", "amounts", "version") == [(["c", "c"], ["1.50"], 2)]


@_REPRESENTATIONS
@_TICKETS
def test_an_equal_collection_assignment_is_still_written(
    profile_run: Any, entity: type[Any], representation: _Representation
) -> None:
    db = _seed_ticket(profile_run, entity)

    def fn(tx: Transaction) -> None:
        source = _find(tx, entity, representation)
        if representation == "typed":
            tx.amend(source, entity.tags.set(("a", "b", "a")))
        else:
            tx.wire.amend(source, {"tags": ["a", "b", "a"]})

    db.transact(fn)
    assert _stored(profile_run, entity, "tags", "version") == [(["a", "b", "a"], 2)]


@_REPRESENTATIONS
@_TICKETS
def test_a_replacement_fills_every_omitted_collection_with_the_empty_collection(
    profile_run: Any, entity: type[Any], representation: _Representation
) -> None:
    db = _seed_ticket(profile_run, entity)

    def fn(tx: Transaction) -> None:
        source = _find(tx, entity, representation)
        if representation == "typed":
            tx.replace(source.edit(label="whole", tags=(), amounts=(), route=None, legs=()))
        else:
            tx.wire.replace(source, {"id": 1, "label": "whole"})

    db.transact(fn)
    assert _stored(profile_run, entity, "label", "tags", "amounts", "route", "legs", "version") == [
        ("whole", [], [], None, [], 2)
    ]


@_STRATEGIES
@_REPRESENTATIONS
@_TICKETS
def test_a_conditional_amendment_and_replacement_carry_collections(
    profile_run: Any,
    entity: type[Any],
    representation: _Representation,
    concurrency: _Concurrency,
) -> None:
    db = _seed_ticket(profile_run, entity)

    def amend(tx: Transaction) -> None:
        if representation == "typed":
            tx.amend_if(entity, entity.tags.set(()), key=1, version=1)
        else:
            tx.wire.amend_if(_name(entity), {"id": 1, "tags": []}, version=1)

    db.transact(amend, concurrency=concurrency)
    assert _stored(profile_run, entity, "tags", "amounts", "version") == [([], ["1.50"], 2)]

    def replace(tx: Transaction) -> None:
        if representation == "typed":
            tx.replace_if(entity(id=1, label="r", amounts=(Decimal(2),)), version=2)
        else:
            tx.wire.replace_if(
                _name(entity), {"id": 1, "label": "r", "amounts": ["2.00"]}, version=2
            )

    db.transact(replace, concurrency=concurrency)
    assert _stored(profile_run, entity, "label", "tags", "amounts", "legs", "version") == [
        ("r", [], ["2.00"], [], 3)
    ]


@_REPRESENTATIONS
@_TICKETS
def test_a_predicate_amendment_of_a_versioned_owner_materializes_its_collections(
    profile_run: Any, entity: type[Any], representation: _Representation
) -> None:
    db = _seed_ticket(profile_run, entity)

    def fn(tx: Transaction) -> None:
        if representation == "typed":
            tx.amend_where(entity.where(entity.id == 1), entity.tags.set(("z",)))
        else:
            tx.wire.amend_where(
                {"entity": _name(entity), "predicate": _by_id(entity, 1)["predicate"]},
                {"tags": ["z"]},
            )

    db.transact(fn)
    assert _stored(profile_run, entity, "tags", "version") == [(["z"], 2)]


# --------------------------------------------------------------------------- #
# Readless predicate amendments of unversioned Non-Temporal owners.            #
# --------------------------------------------------------------------------- #
@_REPRESENTATIONS
@_BOARDS
def test_a_readless_predicate_amendment_replaces_collections_and_value_object_arrays(
    profile_run: Any, entity: type[Any], representation: _Representation
) -> None:
    _reset(profile_run)
    db = _db(profile_run)
    db.transact(
        lambda tx: [
            tx.insert(
                entity(
                    id=key,
                    tags=("a",),
                    route=Route(name="r", leg=Leg(stops=("x",))),
                    legs=(Leg(stops=("p",)),),
                )
            )
            for key in (1, 2)
        ]
    )

    def fn(tx: Transaction) -> None:
        if representation == "typed":
            tx.amend_where(
                entity.where(entity.id == 1),
                entity.tags.set(("b", "b")),
                entity.route.set(Route(name="s", leg=Leg(stops=("y", "z")))),
                entity.legs.set((Leg(stops=()), Leg(stops=("q",)))),
            )
        else:
            changes: dict[str, object] = {
                "tags": ["b", "b"],
                "route": {"name": "s", "leg": {"stops": ["y", "z"]}},
                "legs": [{"stops": []}, {"stops": ["q"]}],
            }
            tx.wire.amend_where(
                {"entity": _name(entity), "predicate": _by_id(entity, 1)["predicate"]}, changes
            )

    db.transact(fn)
    assert _stored(profile_run, entity, "tags", "route", "legs") == [
        (
            ["b", "b"],
            {"name": "s", "leg": {"stops": ["y", "z"]}},
            [{"stops": []}, {"stops": ["q"]}],
        ),
        (["a"], {"name": "r", "leg": {"stops": ["x"]}}, [{"stops": ["p"]}]),
    ]


# --------------------------------------------------------------------------- #
# Temporal owners.                                                             #
# --------------------------------------------------------------------------- #
_JAN, _MAR, _MAY, _JUL = (dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 3, 5, 7))
_S1 = dt.datetime(2023, 11, 1, tzinfo=dt.UTC)
_S2 = dt.datetime(2023, 11, 15, tzinfo=dt.UTC)
_TA = dt.datetime(2024, 1, 10, tzinfo=dt.UTC)


def _span_rows(profile_run: Any, entity: type[Any]) -> list[tuple[object, ...]]:
    sql = (
        "select in_z, case when out_z = 'infinity' then null else out_z end, from_z, "
        f"case when thru_z = 'infinity' then null else thru_z end, "
        f"{_member(entity, 'amount')}, {_member(entity, 'tags')} "
        f"from {_TABLES[entity]} order by from_z, in_z"
    )
    return [
        tuple(int(cell) if isinstance(cell, float) else cell for cell in row)
        for row in profile_run.port.execute(sql, [])
    ]


def _seed_spans(profile_run: Any, entity: type[Any]) -> None:
    _reset(profile_run)
    _db(profile_run, _S1).transact(
        lambda tx: tx.insert(entity(id=1, amount=1, tags=("a",)), valid_from=_JAN, until=_MAY)
    )
    _db(profile_run, _S2).transact(
        lambda tx: tx.insert(entity(id=1, amount=2, tags=("b", "a")), valid_from=_MAY)
    )


@_REPRESENTATIONS
@_SPANS
def test_a_bitemporal_amendment_judges_each_predecessor_collection(
    profile_run: Any, entity: type[Any], representation: _Representation
) -> None:
    _seed_spans(profile_run, entity)

    def fn(tx: Transaction) -> None:
        if representation == "typed":
            source = tx.find(entity.where(entity.id == 1).as_of(valid_time=_JAN)).result()
            tx.amend(source.edit(tags=("b", "a")))
        else:
            name = _name(entity)
            source = tx.wire.find(
                {
                    **_by_id(entity, 1),
                    "temporal": {
                        "transaction-time": {"asOf": "latest"},
                        "valid-time": {"asOf": "2024-01-01T00:00:00.000000Z"},
                    },
                }
            ).result()
            del name
            tx.wire.amend(source, {"tags": ["b", "a"]})

    _db(profile_run, _TA).transact(fn)
    assert _span_rows(profile_run, entity) == [
        (_S1, _TA, _JAN, _MAY, 1, ["a"]),
        (_TA, None, _JAN, _MAY, 1, ["b", "a"]),
        (_S2, None, _MAY, None, 2, ["b", "a"]),
    ]


@_SPANS
def test_a_bitemporal_predicate_amendment_keeps_equal_starting_rows_selected(
    profile_run: Any, entity: type[Any]
) -> None:
    _seed_spans(profile_run, entity)

    _db(profile_run, _TA).transact(
        lambda tx: tx.amend_where(
            entity.where(entity.id == 1), entity.tags.set(("a",)), valid_from=_MAR
        )
    )
    assert _span_rows(profile_run, entity) == [
        (_S1, None, _JAN, _MAY, 1, ["a"]),
        (_S2, _TA, _MAY, None, 2, ["b", "a"]),
        (_TA, None, _MAY, None, 2, ["a"]),
    ]


@_SPANS
def test_an_equal_collection_with_a_changed_milestone_still_executes(
    profile_run: Any, entity: type[Any]
) -> None:
    _seed_spans(profile_run, entity)

    _db(profile_run, _TA).transact(
        lambda tx: tx.amend_where(
            entity.where(entity.id == 1),
            entity.tags.set(("a",)),
            entity.amount.set(9),
            valid_from=_MAR,
            until=_JUL,
        )
    )
    assert _span_rows(profile_run, entity) == [
        (_S1, _TA, _JAN, _MAY, 1, ["a"]),
        (_TA, None, _JAN, _MAR, 1, ["a"]),
        (_TA, None, _MAR, _JUL, 9, ["a"]),
        (_S2, _TA, _MAY, None, 2, ["b", "a"]),
        (_TA, None, _JUL, None, 2, ["b", "a"]),
    ]


@_LOGS
def test_a_transaction_time_owner_chains_a_changed_collection_and_keeps_an_equal_one(
    profile_run: Any, entity: type[Any]
) -> None:
    _reset(profile_run)
    _db(profile_run, _S1).transact(lambda tx: tx.insert(entity(id=1, tags=("a", "b"))))

    def equal(tx: Transaction) -> None:
        tx.amend(tx.find(entity.where(entity.id == 1)).result().edit(tags=("a", "b")))

    _db(profile_run, _S2).transact(equal)

    def changed(tx: Transaction) -> None:
        tx.amend(tx.find(entity.where(entity.id == 1)).result().edit(tags=("b", "a")))

    _db(profile_run, _TA).transact(changed)
    sql = (
        "select in_z, case when out_z = 'infinity' then null else out_z end, "
        f"{_member(entity, 'tags')} from {_TABLES[entity]} order by in_z"
    )
    assert [tuple(row) for row in profile_run.port.execute(sql, [])] == [
        (_S1, _TA, ["a", "b"]),
        (_TA, None, ["b", "a"]),
    ]
