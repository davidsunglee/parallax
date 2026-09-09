"""The owned Postgres runtime against a real server (`database-provider-test-contract`).

What a fake pool cannot establish is here: that a connection really is reused,
that capacity really is bounded, that a queue really refuses, that a runtime that
closed really admits nothing more, and that every connection a pool creates —
initial, grown, replacement, or on-demand — really decodes what the read path
depends on. The deterministic failure paths a server will not produce on demand
are ``tests/unit/test_postgres_pool.py``'s.

Every configuration here names the database this run opened, and every runtime
it opens is closed by the scope that opened it.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest

from parallax.core.base import INFINITY
from parallax.core.db_port import ConnectionAcquisitionError
from parallax.postgres import OnDemandOptions, PoolOptions

_BACKEND = "select pg_backend_pid() as pid"


def _pid(connection: Any) -> int:
    (row,) = connection.execute(_BACKEND, [])
    return int(row["pid"])


def _runtime(profile_run: Any, **options: Any) -> Any:
    return profile_run.configured(**options).open()


# --------------------------------------------------------------------------- #
# Reuse, capacity, and the queue.                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.adapter_smoke
def test_a_retaining_runtime_reuses_the_connection_it_kept(profile_run: Any) -> None:
    runtime = _runtime(profile_run, pool=PoolOptions(min_size=1, max_size=1))
    try:
        with runtime.connection() as first:
            first_pid = _pid(first)
        with runtime.connection() as second:
            assert _pid(second) == first_pid
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_capacity_bounds_how_many_scopes_are_open_at_once(profile_run: Any) -> None:
    # Two scopes at a capacity of two are two DIFFERENT sessions; the third
    # waits for one of them rather than opening a connection past the ceiling.
    runtime = _runtime(profile_run, pool=PoolOptions(min_size=0, max_size=2, acquire_timeout=1.0))
    try:
        with runtime.connection() as first, runtime.connection() as second:
            assert _pid(first) != _pid(second)
            with pytest.raises(ConnectionAcquisitionError) as refused:
                runtime.connection().__enter__()
        assert refused.value.reason == "timeout"
        # The ceiling is not a leak: capacity is available again afterwards.
        with runtime.connection() as third:
            assert _pid(third)
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_a_bounded_queue_refuses_a_further_waiter_rather_than_holding_it(
    profile_run: Any,
) -> None:
    runtime = _runtime(
        profile_run,
        pool=PoolOptions(min_size=0, max_size=1, max_waiting=1, acquire_timeout=2.0),
    )
    waiting = threading.Event()
    refusals: list[str] = []

    def wait_for_capacity() -> None:
        waiting.set()
        try:
            with runtime.connection():
                pass
        except ConnectionAcquisitionError as refused:  # pragma: no cover - timing
            refusals.append(refused.reason)

    try:
        with runtime.connection():
            queued = threading.Thread(target=wait_for_capacity)
            queued.start()
            waiting.wait(timeout=5.0)
            # The queue holds one waiter; the next is refused outright rather
            # than waiting for a slot that is already spoken for.
            with pytest.raises(ConnectionAcquisitionError) as rejected:
                runtime.connection().__enter__()
            assert rejected.value.reason == "queue_rejected"
        queued.join(timeout=10.0)
        assert refusals == []
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_a_closed_runtime_admits_nothing_further(profile_run: Any) -> None:
    runtime = _runtime(profile_run, pool=PoolOptions(min_size=0))
    runtime.close()

    with pytest.raises(ConnectionAcquisitionError) as refused:
        runtime.connection().__enter__()

    assert refused.value.reason == "closed"


@pytest.mark.adapter_smoke
def test_two_runtimes_from_one_configuration_are_independent(profile_run: Any) -> None:
    configured = profile_run.configured(pool=PoolOptions(min_size=1, max_size=1))
    first = configured.open()
    second = configured.open()
    try:
        with first.connection() as one, second.connection() as two:
            assert _pid(one) != _pid(two)
        first.close()
        # Closing one leaves the other working.
        with second.connection() as still_working:
            assert _pid(still_working)
    finally:
        first.close()
        second.close()


# --------------------------------------------------------------------------- #
# On-demand retention.                                                         #
# --------------------------------------------------------------------------- #


@pytest.mark.adapter_smoke
def test_an_on_demand_runtime_keeps_no_idle_connection(profile_run: Any) -> None:
    # Releasing closes the connection unless a caller is already waiting, so a
    # later acquisition establishes another — which is bounded concurrency
    # without inventory rather than a promise of a brand-new session each time.
    runtime = _runtime(profile_run, pool=OnDemandOptions(max_size=2))
    try:
        with runtime.connection() as first:
            first_pid = _pid(first)
        with runtime.connection() as second:
            assert _pid(second) != first_pid
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_an_on_demand_runtime_still_bounds_concurrency(profile_run: Any) -> None:
    runtime = _runtime(profile_run, pool=OnDemandOptions(max_size=1, acquire_timeout=1.0))
    try:
        with runtime.connection(), pytest.raises(ConnectionAcquisitionError) as refused:
            runtime.connection().__enter__()
        assert refused.value.reason == "timeout"
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_on_demand_establishment_takes_its_limit_from_the_acquisition_budget(
    profile_run: Any,
) -> None:
    # The driver derives its own `connect_timeout` from what remains of the
    # checkout budget, overriding one the connection string carries for that
    # creation. A connection string asking for a two-second establishment limit
    # therefore does not get one — the acquisition budget is the control that
    # matters here, and the two do not compose as independent limits.
    from psycopg.conninfo import conninfo_to_dict

    configured = profile_run.configured(pool=OnDemandOptions(max_size=1, acquire_timeout=5.0))
    assert "connect_timeout" not in conninfo_to_dict(configured.connection_string)
    runtime = configured.open()
    try:
        with runtime.connection() as scoped:
            assert _pid(scoped)
    finally:
        runtime.close()


# --------------------------------------------------------------------------- #
# Every physical connection decodes what the read path depends on.             #
# --------------------------------------------------------------------------- #


_CODEC_PROBE = """SELECT
    'infinity'::timestamptz AS unbounded,
    '{"present": null}'::jsonb AS document,
    null::jsonb AS absent,
    'null'::jsonb AS stored_null,
    42::int AS number"""


@pytest.mark.adapter_smoke
def test_every_connection_a_runtime_creates_decodes_the_same_way(profile_run: Any) -> None:
    # Initial capacity, growth, and the connections an on-demand runtime creates
    # per acquisition: a codec installed on some connections and not others is a
    # decoding bug that appears under load and nowhere else.
    for options in (
        PoolOptions(min_size=1, max_size=3),
        PoolOptions(min_size=0, max_size=3),
        OnDemandOptions(max_size=3),
    ):
        runtime = _runtime(profile_run, pool=options)
        try:
            for _ in range(3):
                with runtime.connection() as scoped:
                    (row,) = scoped.execute(_CODEC_PROBE, [])
                assert row["unbounded"] is INFINITY
                assert row["document"] == {"present": None}
                assert row["absent"] is None
                assert row["stored_null"] is None
                assert row["number"] == 42
        finally:
            runtime.close()


@pytest.mark.adapter_smoke
def test_a_finite_timestamp_still_decodes_beside_the_unbounded_one(profile_run: Any) -> None:
    runtime = _runtime(profile_run, pool=PoolOptions(min_size=0, max_size=1))
    try:
        with runtime.connection() as scoped:
            (row,) = scoped.execute(
                "select '2026-01-02 03:04:05+00'::timestamptz as at, "
                "'infinity'::timestamptz as forever",
                [],
            )
        assert row["forever"] is INFINITY
        assert row["at"].year == 2026
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_checkout_validation_can_be_opted_out_of_without_changing_what_executes(
    profile_run: Any,
) -> None:
    # The health check spends a round trip proving a connection still works.
    # Turning it off changes what the runtime does before handing a connection
    # over and nothing about what the caller may then run on it.
    runtime = _runtime(
        profile_run, pool=PoolOptions(min_size=1, max_size=1, validate_on_checkout=False)
    )
    try:
        with runtime.connection() as scoped:
            assert scoped.execute("select 1 as n", []) == [{"n": 1}]
    finally:
        runtime.close()


# --------------------------------------------------------------------------- #
# Transactions across scopes.                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.adapter_smoke
def test_two_scopes_hold_isolated_transactions(profile_run: Any) -> None:
    profile_run.reset(*_grade_model())
    runtime = _runtime(profile_run, pool=PoolOptions(min_size=0, max_size=2))
    try:
        with runtime.connection() as writer, runtime.connection() as reader:

            def insert(conn: Any) -> None:
                conn.execute_write(
                    'insert into grade (id, "order", label) values (%s, %s, %s)',
                    [99, 99, "z"],
                )
                # The other scope's transaction cannot see uncommitted work.
                assert reader.execute("select id from grade where id = 99", []) == []

            writer.transaction(insert)
            assert reader.execute("select id from grade where id = 99", []) == [{"id": 99}]
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_a_scope_leaves_no_transaction_open_behind_it(profile_run: Any) -> None:
    # Autocommit and physical-close semantics: a standalone statement opens no
    # implicit whole-operation transaction, so the connection comes back idle
    # and the next scope over it starts clean.
    runtime = _runtime(profile_run, pool=PoolOptions(min_size=1, max_size=1))
    try:
        with runtime.connection() as first:
            first.execute("select 1", [])
        with runtime.connection() as second:
            (row,) = second.execute("select txid_current_if_assigned() as tx", [])
        assert row["tx"] is None
    finally:
        runtime.close()


@pytest.mark.adapter_smoke
def test_a_session_default_arrives_with_the_connection_rather_than_after_it(
    profile_run: Any,
) -> None:
    # `m-db-port` puts the isolation check at INTAKE, so the default has to be
    # there before initialization rather than set on a borrowed session. It
    # travels as a connection-establishment option, which is why every
    # connection this configuration opens carries it.
    runtime = profile_run.adapter_for_session_default("read-uncommitted").open()
    try:
        with runtime.connection() as scoped:
            (row,) = scoped.execute("show default_transaction_isolation", [])
        # Postgres HAS no level below Read Committed and runs a Read Uncommitted
        # request as Read Committed, so the floor is met and the connection is
        # kept — which is exactly what the corpus case grades.
        assert row["default_transaction_isolation"] == "read uncommitted"
    finally:
        runtime.close()


def _grade_model() -> tuple[Any, Any]:
    from parallax.conformance import engine, provision
    from parallax.conformance.case_format import default_cases_dir, load_case

    case = load_case(default_cases_dir() / "m-descriptor-001-quoted-reserved-identifier.yaml")
    return engine.load_case_metamodel(case), provision.load_fixtures(str(case.document["model"]))
