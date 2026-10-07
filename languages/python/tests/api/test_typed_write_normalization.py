"""Typed write values reach the driver bind normalized by the developer input policy.

Negative float zero and negative underflow bind as positive zero, and an aware
timestamp binds as its UTC instant, on the keyed and predicate write verbs.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Callable, Mapping
from typing import cast

import pytest

from parallax.conformance.scripted_clock import FixedClock
from parallax.core import Attr, DomainModel, Entity, Float32, Int32, ValueObject, attr
from parallax.core.base import PresentDocument
from parallax.core.db_port import JsonDocument
from parallax.snapshot import Transaction, connect
from tests._support.db_port import Read, ScriptedAdapter, Transact, Write, WriteCall
from tests._support.root_ownership import own_root


class Point(ValueObject):
    ratio: Attr[float] = attr(type=Float32)
    measure: Attr[float]


class Reading(Entity, table="reading", namespace="typed.normalization"):
    id: Attr[int] = attr(primary_key=True)
    ratio: Attr[float] = attr(type=Float32)
    measure: Attr[float]
    point: Attr[Point]


class VersionedReading(Entity, table="versioned_reading", namespace="typed.normalization"):
    id: Attr[int] = attr(primary_key=True)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)
    ratio: Attr[float] = attr(type=Float32)
    measure: Attr[float]
    point: Attr[Point]


class Stamp(Entity, table="stamp", namespace="typed.normalization"):
    id: Attr[int] = attr(primary_key=True)
    at: Attr[dt.datetime]


_MODEL = DomainModel(Reading, VersionedReading, Stamp)

# (Float32 input, Float64 input); a Float64 underflow has no host spelling but -0.0.
_NEGATIVE_ZEROS = pytest.mark.parametrize(
    ("ratio", "measure"),
    [(-0.0, -0.0), (-1e-50, float("-1e-400"))],
    ids=["negative-zero", "negative-underflow"],
)


def _write_calls(work: Callable[[Transaction], object], *script: Read | Write) -> list[WriteCall]:
    port = ScriptedAdapter(Transact(*script))
    database = own_root(
        connect(port, _MODEL, clock=FixedClock(dt.datetime(2024, 6, 1, tzinfo=dt.UTC)))
    ).using_database_login()
    database.transact(work)
    return [call for call in port.calls if isinstance(call, WriteCall)]


def _zero_signs(calls: list[WriteCall]) -> list[float]:
    found: list[float] = []

    def visit(value: object) -> None:
        if isinstance(value, JsonDocument):
            visit(value.value)
        elif isinstance(value, float) and value == 0.0:
            found.append(math.copysign(1.0, value))
        elif isinstance(value, Mapping):
            for member in cast("Mapping[object, object]", value).values():
                visit(member)
        elif isinstance(value, tuple | list):
            for member in cast("tuple[object, ...] | list[object]", value):
                visit(member)

    for call in calls:
        visit(call.binds)
    return found


@_NEGATIVE_ZEROS
def test_a_typed_insert_binds_negative_float_zero_as_positive_zero(
    ratio: float, measure: float
) -> None:
    calls = _write_calls(
        lambda tx: tx.insert(
            Reading(id=1, ratio=ratio, measure=measure, point=Point(ratio=ratio, measure=measure))
        ),
        Write(),
    )

    assert _zero_signs(calls) == [1.0] * 4


@_NEGATIVE_ZEROS
def test_a_typed_update_where_binds_negative_float_zero_as_positive_zero(
    ratio: float, measure: float
) -> None:
    calls = _write_calls(
        lambda tx: tx.update_where(
            Reading.where(Reading.id == 1),
            Reading.ratio.set(ratio),
            Reading.measure.set(measure),
            Reading.point.set(Point(ratio=ratio, measure=measure)),
        ),
        Write(),
    )

    assert _zero_signs(calls) == [1.0] * 4


@_NEGATIVE_ZEROS
def test_a_materializing_typed_update_where_binds_negative_float_zero_as_positive_zero(
    ratio: float, measure: float
) -> None:
    stored = {
        "id": 1,
        "version": 1,
        "ratio": 1.5,
        "measure": 2.5,
        "point": PresentDocument({"ratio": 1.5, "measure": 2.5}),
    }
    calls = _write_calls(
        lambda tx: tx.update_where(
            VersionedReading.where(VersionedReading.id >= 0),
            VersionedReading.ratio.set(ratio),
            VersionedReading.measure.set(measure),
            VersionedReading.point.set(Point(ratio=ratio, measure=measure)),
        ),
        Read(rows=[stored]),
        Write(),
    )

    assert _zero_signs(calls) == [1.0] * 4


def test_a_typed_insert_binds_an_aware_timestamp_as_its_utc_instant() -> None:
    offset = dt.datetime(2024, 3, 1, 12, 30, tzinfo=dt.timezone(dt.timedelta(hours=5)))

    (call,) = _write_calls(lambda tx: tx.insert(Stamp(id=1, at=offset)), Write())

    _, bound = call.binds
    assert isinstance(bound, dt.datetime)
    assert (bound, bound.tzinfo) == (dt.datetime(2024, 3, 1, 7, 30, tzinfo=dt.UTC), dt.UTC)
