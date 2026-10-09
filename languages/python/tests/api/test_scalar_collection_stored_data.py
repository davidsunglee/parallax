"""Stored scalar collections are classified, never repaired, under both layouts.

A missing key and a JSON null are the empty collection. Any other non-array
carrier, and any element that is not its scalar's canonical encoding, makes the
whole collection unavailable: the owning root is invalid stored data, located
at the collection or at every failing element's position, and no shortened
collection is published. Default eager and streamed access refuse the root and
``checked()`` returns it in band. Corrupt states are seeded with raw SQL, so the
expected findings come from the stored text rather than from production.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Literal

import pytest

from parallax.core import Attr, Document, DomainModel, Entity, Int32, ValueObject, attr
from parallax.core.entity._model import model_of
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)
from parallax.core.read_delivery import InvalidData, InvalidDataError, StoredDataIssue
from parallax.snapshot import ScopedDatabase, connect
from tests._support.adoption import raises_contextualized
from tests._support.root_ownership import own_root

_NAMESPACE = "scalar.collection.stored"


class Detail(ValueObject):
    labels: Attr[tuple[str, ...]] = attr()


class Line(ValueObject):
    marks: Attr[tuple[int, ...]] = attr(type=Int32)


class Order(Entity, table="scs_order", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    counts: Attr[tuple[int, ...]] = attr()
    detail: Attr[Detail | None] = attr()
    lines: Attr[tuple[Line, ...]] = attr()


class Sheet(Entity, table="scs_sheet", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    counts: Attr[tuple[int, ...]] = attr()
    detail: Attr[Detail | None] = attr()
    lines: Attr[tuple[Line, ...]] = attr()


_MODEL = DomainModel(Order, Sheet)

type Layout = Literal["columns", "document"]
_LAYOUTS: tuple[Layout, ...] = ("columns", "document")
_ENTITIES: dict[Layout, Any] = {"columns": Order, "document": Sheet}


def _served(profile_run: Any, layout: Layout, member: str, stored: str) -> ScopedDatabase:
    """A database holding one row whose ``member`` is stored as the JSON ``stored``."""
    profile_run.reset(model_of(_MODEL), {})
    db = own_root(connect(profile_run.port, _MODEL)).using_database_login()
    entity = _ENTITIES[layout]
    db.transact(lambda tx: tx.insert(entity(id=1, counts=(1,), detail=Detail(labels=("a",)))))
    if layout == "columns":
        sql = f"update scs_order set {member} = '{stored}'::jsonb"
    else:
        sql = (
            f"update scs_sheet set payload = jsonb_set(payload, '{{{member}}}', '{stored}'::jsonb)"
        )
    profile_run.port.execute_write(sql, [])
    return db


def _entity(layout: Layout) -> EntityIdentity:
    return EntityIdentity(_NAMESPACE, _ENTITIES[layout].__name__)


def _issues(record: object) -> set[tuple[str, object, tuple[str | int, ...], object]]:
    assert isinstance(record, InvalidData)
    issues: Iterable[StoredDataIssue] = record.issues
    return {(issue.code, issue.member, issue.path, issue.stored_value) for issue in issues}


def _checked_eager(db: ScopedDatabase, layout: Layout) -> object:
    entity = _ENTITIES[layout]
    (record,) = db.find(entity.where(entity.id == 1)).checked().results()
    return record


def _checked_streamed(db: ScopedDatabase, layout: Layout) -> object:
    entity = _ENTITIES[layout]
    with db.stream(entity.where(entity.id == 1), batch_size=1) as stream:
        (record,) = list(stream.checked())
    return record


_ACCESS: dict[str, Callable[[ScopedDatabase, Layout], object]] = {
    "eager": _checked_eager,
    "streamed": _checked_streamed,
}


@pytest.mark.parametrize("layout", _LAYOUTS)
@pytest.mark.parametrize("stored", ["null", "[]"])
def test_json_null_and_the_empty_array_read_as_the_empty_collection(
    profile_run: Any, layout: Layout, stored: str
) -> None:
    db = _served(profile_run, layout, "counts", stored)
    entity = _ENTITIES[layout]

    assert db.find(entity.where(entity.id == 1)).result().counts == ()


def test_a_missing_document_key_reads_as_the_empty_collection(profile_run: Any) -> None:
    profile_run.reset(model_of(_MODEL), {})
    db = own_root(connect(profile_run.port, _MODEL)).using_database_login()
    db.transact(lambda tx: tx.insert(Sheet(id=1, counts=(1,))))
    profile_run.port.execute_write("update scs_sheet set payload = payload - 'counts'", [])

    assert db.find(Sheet.where(Sheet.id == 1)).result().counts == ()


@pytest.mark.parametrize("access", _ACCESS)
@pytest.mark.parametrize("layout", _LAYOUTS)
def test_a_non_array_carrier_makes_the_whole_collection_unavailable(
    profile_run: Any, layout: Layout, access: str
) -> None:
    db = _served(profile_run, layout, "counts", '"1,2"')

    record = _ACCESS[access](db, layout)

    assert _issues(record) == {
        (
            "stored-data-leaf-undecodable",
            AttributeIdentity(_entity(layout), "counts"),
            ("counts",),
            "1,2",
        )
    }


@pytest.mark.parametrize("access", _ACCESS)
@pytest.mark.parametrize("layout", _LAYOUTS)
def test_every_invalid_element_is_reported_at_its_position(
    profile_run: Any, layout: Layout, access: str
) -> None:
    db = _served(profile_run, layout, "counts", '[1, "2", 3, 1.5, null]')

    record = _ACCESS[access](db, layout)

    member = AttributeIdentity(_entity(layout), "counts")
    assert _issues(record) == {
        ("stored-data-leaf-undecodable", member, ("counts", 1), "2"),
        ("stored-data-leaf-undecodable", member, ("counts", 3), 1.5),
        ("stored-data-leaf-undecodable", member, ("counts", 4), None),
    }


@pytest.mark.parametrize("layout", _LAYOUTS)
def test_default_access_refuses_an_invalid_collection_rather_than_shortening_it(
    profile_run: Any, layout: Layout
) -> None:
    db = _served(profile_run, layout, "counts", '[1, "2"]')
    entity = _ENTITIES[layout]
    query = entity.where(entity.id == 1)

    with pytest.raises(InvalidDataError):
        db.find(query).result()
    with raises_contextualized(InvalidDataError), db.stream(query, batch_size=1) as stream:
        list(stream)


@pytest.mark.parametrize("layout", _LAYOUTS)
def test_nested_collections_keep_every_enclosing_name_and_index(
    profile_run: Any, layout: Layout
) -> None:
    db = _served(profile_run, layout, "lines", '[{"marks": [1]}, {"marks": [2, "x", 3.5]}]')

    record = _checked_eager(db, layout)

    lines = ValueObjectIdentity(_entity(layout), ("lines",))
    marks = ValueObjectAttributeIdentity(lines, "marks")
    assert _issues(record) == {
        ("stored-data-leaf-undecodable", marks, ("lines", 1, "marks", 1), "x"),
        ("stored-data-leaf-undecodable", marks, ("lines", 1, "marks", 2), 3.5),
    }


@pytest.mark.parametrize("layout", _LAYOUTS)
def test_an_absent_enclosing_value_object_invents_no_collection(
    profile_run: Any, layout: Layout
) -> None:
    db = _served(profile_run, layout, "detail", "null")
    entity = _ENTITIES[layout]

    read = db.find(entity.where(entity.id == 1)).result()

    assert read.detail is None
