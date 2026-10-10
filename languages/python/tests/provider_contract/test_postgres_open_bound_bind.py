"""The m-core open upper bound bound as native ``infinity``, against a real server.

The adapter's own dumper is what turns the sentinel into driver bytes. Every
statement here runs through a session initialized exactly as an owned connection
is, so the dumper under test is the one the adapter registered; each bind route
is graded against the same statement binding the bound's spelling, which is what
the server received before the adapter dumped the sentinel itself. A public write
then shows the dumper sits below everything a statement is observed by: the SQL
text and each bind's Wire spelling are built before the driver sees a bind.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from typing import Any, cast

import psycopg
import pytest
from psycopg.adapt import PyFormat

from parallax.conformance._postgres_control import PostgresControl
from parallax.conformance.scripted_clock import ScriptedClock
from parallax.core import LATEST, Attr, Bitemporal, DomainModel, attr
from parallax.core.base import INFINITY, TemporalBound
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import PipelineStatement
from parallax.core.entity._model import model_of
from parallax.postgres._connection import (
    _NativeInfinityDumper,  # pyright: ignore[reportPrivateUsage] - the registered dumper is this module's subject
)
from parallax.snapshot import connect
from tests._support.driver_writes import RecordingCaseDatabase
from tests._support.root_ownership import own_root
from tests._support.sweep_goldens import wire_binds

_NAMESPACE = "open.bound"
_SPELLING = "infinity"
_INSERTED = dt.datetime(2024, 3, 1, 9, 30, tzinfo=dt.UTC)
_VALID_FROM = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


class Holding(Bitemporal, table="ob_holding", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    units: Attr[int]


_MODEL = DomainModel(Holding)


@pytest.fixture(scope="module")
def control(profile_run: Any) -> Iterator[PostgresControl]:
    control = cast("PostgresControl", profile_run.control())
    try:
        yield control
    finally:
        control.close()


def test_an_owned_session_binds_the_open_bound_through_the_adapters_dumper(
    control: PostgresControl,
) -> None:
    assert control.native.adapters.get_dumper(TemporalBound, PyFormat.AUTO) is _NativeInfinityDumper
    assert psycopg.adapters.get_dumper(TemporalBound, PyFormat.AUTO) is not _NativeInfinityDumper


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        pytest.param("select %s::timestamptz", (INFINITY,), id="cast"),
        pytest.param("select %s > now()", (True,), id="compared-with-an-instant"),
        pytest.param("select coalesce(%s, now())", (INFINITY,), id="unified-with-an-instant"),
    ],
)
def test_the_server_infers_the_open_bound_as_it_infers_its_spelling(
    control: PostgresControl, sql: str, expected: tuple[object, ...]
) -> None:
    assert control.execute(sql, [INFINITY]) == [expected]
    assert control.execute(sql, [_SPELLING]) == [expected]


@pytest.mark.parametrize("bind", [INFINITY, _SPELLING], ids=["managed", "spelled"])
def test_the_server_receives_the_open_bound_untyped(control: PostgresControl, bind: object) -> None:
    # `isfinite` is overloaded across the temporal types, so only an untyped
    # parameter leaves the server unable to choose one.
    with pytest.raises(DatabaseError, match=r"isfinite\(unknown\) is not unique"):
        control.execute("select isfinite(%s)", [bind])


def test_every_bind_route_stores_the_open_bound_as_native_infinity(
    control: PostgresControl,
) -> None:
    session = control.native
    session.execute(b"drop table if exists open_bound_probe")
    session.execute(b"create temp table open_bound_probe (route text, bound text, at timestamptz)")
    insert_values = "insert into open_bound_probe values (%s, %s, %s)"
    insert_select = "insert into open_bound_probe (route, bound, at) select %s, %s, %s"
    returning = "insert into open_bound_probe values (%s, %s, %s) returning at"
    for bound, bind in (("managed", INFINITY), ("spelled", _SPELLING)):
        assert control.execute_write(insert_values, ["values", bound, bind]) == 1
        assert control.execute_write(insert_select, ["select", bound, bind]) == 1
        assert control.execute_pipeline(
            (PipelineStatement(returning, ("pipeline", bound, bind)),)
        ) == [[(INFINITY,)]]

    stored = control.execute(
        "select route, bound, at, isfinite(at), at = 'infinity'::timestamptz "
        "from open_bound_probe order by route, bound",
        [],
    )

    assert stored == [
        (route, bound, INFINITY, False, True)
        for route in ("pipeline", "select", "values")
        for bound in ("managed", "spelled")
    ]


def test_a_public_write_hands_the_driver_the_sentinel_under_unchanged_observations(
    profile_run: Any,
) -> None:
    profile_run.reset(model_of(_MODEL), {})
    recording = RecordingCaseDatabase(profile_run.port)
    clock = ScriptedClock([_INSERTED])
    db = own_root(connect(recording, _MODEL, clock=clock)).using_database_login()

    db.transact(lambda tx: tx.insert(Holding(id=1, units=3), valid_from=_VALID_FROM))

    ((sql, binds),) = recording.writes
    open_positions = [position for position, bind in enumerate(binds) if bind is INFINITY]
    observed = wire_binds(binds)
    assert len(open_positions) == 2
    assert _SPELLING not in sql.lower()
    assert [observed[position] for position in open_positions] == [_SPELLING, _SPELLING]
    query = {
        "target": f"{_NAMESPACE}.Holding",
        "predicate": {"eq": {"path": f"{_NAMESPACE}.Holding.id", "value": 1}},
        "temporal": {"transaction-time": {"asOf": "latest"}, "valid-time": {"asOf": "latest"}},
    }
    (node,) = db.wire.find(query).results()
    assert (node["validEnd"], node["txEnd"]) == (_SPELLING, _SPELLING)
    typed = Holding.where(Holding.id == 1).as_of(valid_time=LATEST, tx_time=LATEST)
    (row,) = db.find(typed).results()
    assert row.valid_end is INFINITY
    assert row.tx_end is INFINITY
