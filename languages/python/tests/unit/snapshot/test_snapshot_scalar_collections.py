"""Scalar collections materialize with their owner, in one statement.

A collection is part of its owner's row: under Columns its own structured Column,
under Document an array member of the shared document, and inside a Value Object
an array within that occurrence's document. Typed publication answers immutable
tuples and Wire publication the canonical arrays, and reaching any collection or
element costs no further database call. The scripted port answers one row per
layout and records every call.
"""

from __future__ import annotations

import decimal
from collections.abc import Mapping
from typing import Any

import pytest

from parallax.core import (
    Attr,
    Document,
    DomainModel,
    Entity,
    Int32,
    ValueObject,
    attr,
    object_query,
)
from parallax.core.base import DocumentValue, PresentDocument
from parallax.snapshot import connect
from tests._support.db_port import Read, ReadCall, ScriptedAdapter
from tests._support.root_ownership import own_root

_NS = "scalar.collection.publication"


class Mark(ValueObject):
    scores: Attr[tuple[int, ...]] = attr(type=Int32)


class Item(Entity, table="item", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    amounts: Attr[tuple[decimal.Decimal, ...]] = attr(precision=6, scale=2)
    marks: Attr[tuple[Mark, ...]]


class Sheet(Entity, table="sheet", namespace=_NS, layout=Document):
    id: Attr[int] = attr(primary_key=True)
    amounts: Attr[tuple[decimal.Decimal, ...]] = attr(precision=6, scale=2)
    marks: Attr[tuple[Mark, ...]]


_MODEL = DomainModel(Item, Sheet)
_AMOUNTS: list[DocumentValue] = ["1.50", "1.50", "7.00"]
_MARKS: list[DocumentValue] = [{"scores": [3, 3]}, {"scores": []}]
_ROWS: dict[str, dict[str, object]] = {
    "columns": {
        "id": 1,
        "amounts": PresentDocument(_AMOUNTS),
        "marks": PresentDocument(_MARKS),
    },
    "document": {"id": 1, "payload": PresentDocument({"amounts": _AMOUNTS, "marks": _MARKS})},
}


@pytest.mark.parametrize(("layout", "entity"), [("columns", Item), ("document", Sheet)])
def test_one_statement_materializes_every_collection_typed_and_wire(
    layout: str, entity: Any
) -> None:
    port = ScriptedAdapter(Read(rows=[_ROWS[layout]]), Read(rows=[_ROWS[layout]]))
    database = own_root(connect(port, _MODEL)).using_database_login()

    typed = database.find(entity.where(entity.id == 1)).result()
    (wire,) = database.wire.find(
        {"target": f"{_NS}.{entity.__name__}", "predicate": {"true": {}}}
    ).results()

    assert typed.amounts == (
        decimal.Decimal("1.50"),
        decimal.Decimal("1.50"),
        decimal.Decimal("7.00"),
    )
    assert [mark.scores for mark in typed.marks] == [(3, 3), ()]
    assert wire["amounts"] == _AMOUNTS
    assert wire["marks"] == _MARKS
    assert len([call for call in port.calls if isinstance(call, ReadCall)]) == 2


@pytest.mark.parametrize(("layout", "entity"), [("columns", Item), ("document", Sheet)])
def test_a_row_form_read_publishes_the_managed_tuple(layout: str, entity: Any) -> None:
    row = {key: value for key, value in _ROWS[layout].items() if key != "marks"}
    port = ScriptedAdapter(Read(rows=[row]))
    database = own_root(connect(port, _MODEL)).using_database_login()

    (published,) = database.read_rows(
        object_query.deserialize({"target": f"{_NS}.{entity.__name__}", "predicate": {"true": {}}})
    ).rows

    assert isinstance(published, Mapping)
    assert published["amounts"] == (
        decimal.Decimal("1.50"),
        decimal.Decimal("1.50"),
        decimal.Decimal("7.00"),
    )
