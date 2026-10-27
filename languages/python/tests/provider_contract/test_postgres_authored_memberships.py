"""Authored memberships executed as one cast array bind on PostgreSQL.

Every admitted subject type is read three ways — a column, a document-resident
attribute, and a value-object leaf or scalar-collection element — and both
operators select exactly the rows a value comparison selects, excluding a row
whose subject is null. The delivered statement binds the whole list as one
array, so a list longer than the protocol's 65,535 parameters still executes.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any, Final

import pytest

from parallax.conformance._lifecycle_observation import LifecycleObservation
from parallax.core import Attr, Document, DomainModel, Entity, Float32, Int32, ValueObject, attr
from parallax.core.entity._model import model_of
from parallax.snapshot import ScopedDatabase, connect
from tests._support.root_ownership import own_root

_NAMESPACE = "authored.memberships"


class Place(ValueObject):
    city: Attr[str] = attr()
    rank: Attr[int] = attr(type=Int32)


class Probe(Entity, table="am_probe", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    flag: Attr[bool | None] = attr()
    small: Attr[int | None] = attr(type=Int32)
    count: Attr[int | None] = attr()
    ratio: Attr[float | None] = attr(type=Float32)
    score: Attr[float | None] = attr()
    amount: Attr[Decimal | None] = attr(precision=12, scale=2)
    name: Attr[str | None] = attr(max_length=16)
    blob: Attr[bytes | None] = attr()
    day: Attr[dt.date | None] = attr()
    moment: Attr[dt.time | None] = attr()
    instant: Attr[dt.datetime | None] = attr()
    key: Attr[uuid.UUID | None] = attr()
    place: Attr[Place | None] = attr()
    tags: Attr[tuple[str, ...]] = attr()
    counts: Attr[tuple[int, ...]] = attr()


class Sheet(Entity, table="am_sheet", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    flag: Attr[bool | None] = attr()
    small: Attr[int | None] = attr(type=Int32)
    count: Attr[int | None] = attr()
    ratio: Attr[float | None] = attr(type=Float32)
    score: Attr[float | None] = attr()
    amount: Attr[Decimal | None] = attr(precision=12, scale=2)
    name: Attr[str | None] = attr(max_length=16)
    blob: Attr[bytes | None] = attr()
    day: Attr[dt.date | None] = attr()
    moment: Attr[dt.time | None] = attr()
    instant: Attr[dt.datetime | None] = attr()
    key: Attr[uuid.UUID | None] = attr()


_MODEL = DomainModel(Probe, Sheet)

_SCALARS: Final[Mapping[str, tuple[object, object, object]]] = {
    "flag": (True, False, True),
    "small": (3, 70_000 // 7, 5),
    "count": (7, 2**40, 9),
    "ratio": (1.5, 2.25, -0.5),
    "score": (0.1, 2.5, -3.75),
    "amount": (Decimal("1.50"), Decimal("2.00"), Decimal("3.25")),
    "name": ("Ada", "Bo", "Cy"),
    "blob": (b"\x0a\xff", b"", b"\x00"),
    "day": (dt.date(2024, 2, 29), dt.date(2024, 3, 1), dt.date(1999, 12, 31)),
    "moment": (dt.time(13, 5, 7, 250), dt.time(0, 0), dt.time(23, 59, 59, 999_999)),
    "instant": (
        dt.datetime(2024, 6, 1, 12, 0, tzinfo=dt.UTC),
        dt.datetime(2024, 6, 1, 12, 0, 0, 1, tzinfo=dt.UTC),
        dt.datetime(1970, 1, 1, tzinfo=dt.UTC),
    ),
    "key": (uuid.UUID(int=1), uuid.UUID(int=2), uuid.UUID(int=2**127)),
}
"""Three distinct values per scalar member, for rows 1, 2, and 3; row 4 holds
nulls. Row 2's value is never listed, and a membership lists rows 1 and 3."""


def _seeded(profile_run: Any) -> tuple[ScopedDatabase, LifecycleObservation]:
    profile_run.reset(model_of(_MODEL), {})
    observation = LifecycleObservation()
    db = own_root(
        connect(profile_run.port, _MODEL, lifecycle_provider=observation.provider)
    ).using_database_login()

    def seed(tx: Any) -> None:
        for index in range(3):
            values = {name: triple[index] for name, triple in _SCALARS.items()}
            tx.insert(
                Probe(
                    id=index + 1,
                    place=Place(city=("Oslo", "Lima", "Rome")[index], rank=index + 1),
                    tags=(("a", "b"), ("c",), ("b", "d"))[index],
                    counts=((1, 2), (3,), (2, 4))[index],
                    **values,
                )
            )
            tx.insert(Sheet(id=index + 1, **values))
        tx.insert(Probe(id=4, tags=(), counts=()))
        tx.insert(Sheet(id=4))

    db.transact(seed)
    return db, observation


def _ids(
    db: ScopedDatabase, observation: LifecycleObservation, entity: Any, predicate: object
) -> set[int]:
    mark = len(observation.calls)
    found = {row.id for row in db.find(entity.where(predicate)).results()}
    (call,) = (call for call in observation.calls[mark:] if call.kind == "read")
    statement = call.statement
    assert " = any(cast(? as " in statement.sql
    assert " in (" not in statement.sql
    assert sum(isinstance(bind, list) for bind in statement.binds) == 1
    return found


@pytest.mark.parametrize("entity", [Probe, Sheet], ids=["column", "document-attribute"])
def test_a_membership_of_every_scalar_type_selects_its_rows_and_excludes_nulls(
    profile_run: Any, entity: Any
) -> None:
    db, observation = _seeded(profile_run)
    for name, (first, _second, third) in _SCALARS.items():
        member = getattr(entity, name)
        assert _ids(db, observation, entity, member.in_([first, third])) == {1, 3}, name
        assert _ids(db, observation, entity, member.not_in([first, third])) == {2}, name
        assert _ids(db, observation, entity, member.in_([third, third, first])) == {1, 3}, name


_ELEMENTS: Final[tuple[tuple[str, Callable[[], object], set[int]], ...]] = (
    ("leaf-in", lambda: Probe.place.city.in_(["Oslo", "Rome"]), {1, 3}),
    ("leaf-not-in", lambda: Probe.place.rank.not_in([1, 3]), {2}),
    ("element-in", lambda: Probe.tags.any(Probe.tags.element.in_(["b", "x"])), {1, 3}),
    ("element-not-in", lambda: Probe.counts.any(Probe.counts.element.not_in([1, 2])), {2, 3}),
    ("element-none", lambda: Probe.counts.none(Probe.counts.element.in_([2])), {2, 4}),
)


@pytest.mark.parametrize(
    ("predicate", "expected"),
    [(predicate, expected) for _id, predicate, expected in _ELEMENTS],
    ids=[name for name, _predicate, _expected in _ELEMENTS],
)
def test_a_value_object_leaf_or_collection_element_membership_selects_its_rows(
    profile_run: Any, predicate: Callable[[], object], expected: set[int]
) -> None:
    db, observation = _seeded(profile_run)
    assert _ids(db, observation, Probe, predicate()) == expected


def test_a_list_wider_than_the_parameter_limit_executes_as_one_array(profile_run: Any) -> None:
    db, observation = _seeded(profile_run)
    wide: list[object] = list(range(3, 70_003))

    assert _ids(db, observation, Probe, Probe.id.in_(wide)) == {3, 4}
    assert _ids(db, observation, Probe, Probe.id.not_in(wide)) == {1, 2}
