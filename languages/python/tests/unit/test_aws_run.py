"""A cloud run's lifetime over scripted ports: nothing here reaches AWS, opens a
socket, or resolves a credential."""

from __future__ import annotations

import signal
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from types import FrameType
from typing import Any

import pytest

from parallax.conformance._replication import Pacing
from parallax.core.db_port import Password
from parallax.postgres import OnDemandOptions, PoolOptions, PostgresEndpoint
from tests._support.aws_environment import AwsInstance, AwsTestEnvironment
from tests._support.aws_run import (
    CONTROL_DATABASE,
    READER_APPLICATION,
    SUITE_LOCK,
    WRITER_APPLICATION,
    AwsRun,
    CloudPacing,
    CloudRunError,
    RunIdentity,
    interrupted_on_termination,
)
from tests._support.routed_reads import SEEDED_MODEL, seeded_fixtures

_WRITER = "parallax-ci.cluster-abc.us-east-2.rds.amazonaws.com"
_READER = "parallax-ci.cluster-ro-abc.us-east-2.rds.amazonaws.com"
_WRITER_INSTANCE = "parallax-ci-writer.abc.us-east-2.rds.amazonaws.com"
_READER_INSTANCE = "parallax-ci-reader.abc.us-east-2.rds.amazonaws.com"

_ENVIRONMENT = AwsTestEnvironment(
    writer_host=_WRITER,
    reader_host=_READER,
    port=5432,
    region="us-east-2",
    login="parallax_conformance_login",
    cluster_id="parallax-ci",
    instances=(
        AwsInstance("parallax-ci-writer", _WRITER_INSTANCE, "writer"),
        AwsInstance("parallax-ci-reader", _READER_INSTANCE, "reader"),
    ),
    ca_bundle_url="https://truststore.pki.rds.amazonaws.com/us-east-2/us-east-2-bundle.pem",
)
_IDENTITY = RunIdentity(7, 2)


@dataclass
class _Clock:
    now: float = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _pacing(clock: _Clock) -> CloudPacing:
    def paced(within: float) -> Pacing:
        return Pacing(within=within, interval=1.0, clock=clock, sleep=clock.advance)

    return CloudPacing(lock=paced(10.0), warm=paced(5.0), visible=paced(3.0))


@dataclass
class _Cluster:
    """What the scripted server answers, and everything said to it."""

    log: list[str] = field(default_factory=list[str])
    timeout: str = "0"
    owners: dict[str, bool | None] = field(default_factory=dict[str, bool | None])
    blockers: list[tuple[Any, ...]] = field(default_factory=list[tuple[Any, ...]])
    owned: list[str] = field(default_factory=lambda: [CONTROL_DATABASE, "ci_1_1", "ci_x"])
    lock_after: int = 0
    unlocked: bool = True
    lingering: set[str] = field(default_factory=set[str])
    refusing: dict[str, int] = field(default_factory=dict[str, int])
    reset_states: dict[str, list[list[tuple[Any, ...]]]] = field(
        default_factory=dict[str, list[list[tuple[Any, ...]]]]
    )
    failing: dict[str, BaseException] = field(default_factory=dict[str, BaseException])

    def answer(self, session: _Session, sql: str, binds: Sequence[object]) -> list[tuple[Any, ...]]:
        if sql.startswith("select pg_try_advisory_lock"):
            assert binds == [SUITE_LOCK]
            granted = self.lock_after <= 0
            self.lock_after -= 1
            return [(granted,)]
        if sql.startswith("select pg_advisory_unlock"):
            return [(self.unlocked,)]
        if sql.startswith("select d.datname"):
            return [(name,) for name in self.owned]
        if sql.startswith("select count(*) from pg_database"):
            return [(1 if binds[0] in self.lingering else 0,)]
        if sql == "select 1":
            return [(1,)]
        if "pg_namespace" in sql:
            states = self.reset_states[session.host]
            return states.pop(0) if len(states) > 1 else states[0]
        return self.cleanup_answer(sql, binds)

    def cleanup_answer(self, sql: str, binds: Sequence[object]) -> list[tuple[Any, ...]]:
        if sql.startswith("select datdba ="):
            owner = self.owners.get(str(binds[0]), True)
            return [] if owner is None else [(owner,)]
        if sql == "select current_setting('statement_timeout')":
            return [(self.timeout,)]
        if sql == "select set_config('statement_timeout', %s, false)":
            self.timeout = str(binds[0])
            return [(self.timeout,)]
        if sql.startswith("select pg_terminate_backend"):
            assert binds and "usename = current_user" in sql
            assert "backend_type = 'client backend'" in sql
            return []
        if sql.startswith("select pid, usename"):
            return self.blockers
        raise AssertionError(sql)


@dataclass
class _Session:
    cluster: _Cluster
    host: str
    database: str

    @property
    def dialect(self) -> Any:
        from parallax.core.dialect import POSTGRES

        return POSTGRES

    def _said(self, sql: str) -> None:
        self.cluster.log.append(f"{self.host}/{self.database}: {sql}")
        failure = self.cluster.failing.get(sql)
        if failure is not None:
            raise failure

    def execute(self, sql: str, binds: Sequence[object]) -> list[tuple[Any, ...]]:
        self._said(sql)
        return self.cluster.answer(self, sql, binds)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        self._said(sql)
        return 0

    def close(self) -> None:
        self._said("close")


@dataclass
class _Ports:
    cluster: _Cluster
    endpoints: list[tuple[str, str, str, object]] = field(
        default_factory=list[tuple[str, str, str, object]]
    )

    def session(self, host: str, database: str) -> Any:
        remaining = self.cluster.refusing.get(host, 0)
        if remaining:
            self.cluster.refusing[host] = remaining - 1
            raise ConnectionError(f"{host} is resuming")
        self.cluster.log.append(f"{host}/{database}: open")
        return _Session(self.cluster, host, database)

    def endpoint(
        self,
        host: str,
        database: str,
        *,
        application_name: str,
        pool: PoolOptions | OnDemandOptions,
    ) -> PostgresEndpoint:
        self.endpoints.append((host, database, application_name, pool))
        return PostgresEndpoint(
            f"host={host} dbname={database} application_name={application_name}",
            credentials=Password("scripted"),
            pool=pool,
        )

    def close(self) -> None:
        self.cluster.log.append("ports: close")


def _started(cluster: _Cluster, clock: _Clock | None = None) -> tuple[AwsRun, _Ports]:
    ports = _Ports(cluster)
    run = AwsRun.start(_ENVIRONMENT, _IDENTITY, ports, _pacing(clock or _Clock()))
    return run, ports


_CONTROL = f"{_WRITER}/{CONTROL_DATABASE}"
_ADMIN = f"{_WRITER}/ci_7_2"


def _drop_steps(database: str) -> list[str]:
    return [
        f"{_CONTROL}: select current_setting('statement_timeout')",
        f"{_CONTROL}: select set_config('statement_timeout', %s, false)",
        f"{_CONTROL}: select datdba = (select oid from pg_roles where rolname = current_user) "
        "from pg_database where datname = %s",
        f'{_CONTROL}: alter database "{database}" allow_connections false',
        f"{_CONTROL}: select pg_terminate_backend(pid) from pg_stat_activity "
        "where datname = %s and usename = current_user and backend_type = 'client backend'",
        f'{_CONTROL}: drop database if exists "{database}"',
        f"{_CONTROL}: select count(*) from pg_database where datname = %s",
        f"{_CONTROL}: select set_config('statement_timeout', %s, false)",
    ]


def test_a_run_locks_drops_stale_databases_then_creates_and_warms_its_own() -> None:
    cluster = _Cluster()
    _started(cluster)

    assert cluster.log == [
        f"{_CONTROL}: open",
        f"{_CONTROL}: set role none",
        f"{_CONTROL}: select pg_try_advisory_lock(%s)",
        f"{_CONTROL}: {cluster.log[3].split(': ', 1)[1]}",
        *_drop_steps("ci_1_1"),
        f'{_CONTROL}: create database "ci_7_2"',
        f"{_ADMIN}: open",
        f"{_ADMIN}: set role none",
        *(
            entry
            for host in (_WRITER, _READER, _WRITER_INSTANCE, _READER_INSTANCE)
            for entry in (
                f"{host}/ci_7_2: open",
                f"{host}/ci_7_2: select 1",
                f"{host}/ci_7_2: close",
            )
        ),
    ]
    assert cluster.log[3].startswith(f"{_CONTROL}: select d.datname")


def test_closing_releases_in_ownership_order_and_only_once() -> None:
    cluster = _Cluster(owned=[])
    run, _ = _started(cluster)
    run.session(_READER_INSTANCE)
    cluster.log.clear()

    run.close()
    run.close()

    assert cluster.log == [
        f"{_READER_INSTANCE}/ci_7_2: close",
        f"{_ADMIN}: close",
        *_drop_steps("ci_7_2"),
        f"{_CONTROL}: select pg_advisory_unlock(%s)",
        f"{_CONTROL}: close",
        "ports: close",
    ]


def test_the_janitor_drops_only_run_databases() -> None:
    cluster = _Cluster(
        owned=[CONTROL_DATABASE, "ci_9_1", "ci_", "ci_9_1_extra", "postgres", "ci_3_4"]
    )
    _started(cluster)

    dropped = [entry for entry in cluster.log if "drop database" in entry]
    assert dropped == [
        f'{_CONTROL}: drop database if exists "ci_9_1"',
        f'{_CONTROL}: drop database if exists "ci_3_4"',
    ]


def test_the_lock_is_waited_for_by_polling_within_its_bound() -> None:
    clock = _Clock()
    cluster = _Cluster(owned=[], lock_after=3)
    _started(cluster, clock)

    polls = [entry for entry in cluster.log if "pg_try_advisory_lock" in entry]
    assert len(polls) == 4
    assert clock.now >= 3.0


def test_a_lock_never_granted_fails_the_run_at_its_deadline_and_releases_the_session() -> None:
    clock = _Clock()
    cluster = _Cluster(owned=[], lock_after=1_000)

    with pytest.raises(TimeoutError, match="the cloud suite lock"):
        _started(cluster, clock)

    assert clock.now == 10.0
    assert cluster.log[-2:] == [f"{_CONTROL}: close", "ports: close"]
    assert not any("unlock" in entry or "drop" in entry for entry in cluster.log)


def test_a_host_that_never_answers_fails_the_run_chained_to_its_last_refusal() -> None:
    cluster = _Cluster(owned=[], refusing={_READER: 1_000})

    with pytest.raises(TimeoutError, match=_READER) as timed_out:
        _started(cluster)

    assert isinstance(timed_out.value.__cause__, ConnectionError)
    assert cluster.log[-12:] == [
        f"{_ADMIN}: close",
        *_drop_steps("ci_7_2"),
        f"{_CONTROL}: select pg_advisory_unlock(%s)",
        f"{_CONTROL}: close",
        "ports: close",
    ]


def test_a_resuming_host_is_waited_for() -> None:
    cluster = _Cluster(owned=[], refusing={_WRITER_INSTANCE: 2})
    _started(cluster)
    assert f"{_WRITER_INSTANCE}/ci_7_2: select 1" in cluster.log


def test_a_paused_writer_is_waited_for_before_the_control_session() -> None:
    clock = _Clock()
    cluster = _Cluster(owned=[], refusing={_WRITER: 2})
    _started(cluster, clock)

    assert cluster.log[:2] == [f"{_CONTROL}: open", f"{_CONTROL}: set role none"]
    assert clock.now == 2.0


def test_a_writer_that_never_resumes_fails_the_run_chained_to_its_last_refusal() -> None:
    cluster = _Cluster(owned=[], refusing={_WRITER: 1_000})

    with pytest.raises(TimeoutError, match=_WRITER) as timed_out:
        _started(cluster)

    assert isinstance(timed_out.value.__cause__, ConnectionError)
    assert cluster.log == ["ports: close"]


def test_an_unconfirmed_drop_of_a_stale_database_fails_the_run_and_still_unlocks() -> None:
    cluster = _Cluster(owned=["ci_1_1"], lingering={"ci_1_1"})

    with pytest.raises(CloudRunError, match="ci_1_1 was not confirmed"):
        _started(cluster)

    assert cluster.log[-3:] == [
        f"{_CONTROL}: select pg_advisory_unlock(%s)",
        f"{_CONTROL}: close",
        "ports: close",
    ]


def test_an_unconfirmed_drop_at_close_fails_the_run_after_every_other_step() -> None:
    cluster = _Cluster(owned=[])
    run, _ = _started(cluster)
    cluster.lingering.add("ci_7_2")
    cluster.log.clear()

    with pytest.raises(CloudRunError, match="may have leaked") as unconfirmed:
        run.close()

    assert "while dropping ci_7_2" in (unconfirmed.value.__notes__ or [])
    assert cluster.log[-3:] == [
        f"{_CONTROL}: select pg_advisory_unlock(%s)",
        f"{_CONTROL}: close",
        "ports: close",
    ]


def test_a_failed_start_and_a_failed_cleanup_are_both_raised() -> None:
    cluster = _Cluster(owned=[], refusing={_READER: 1_000}, lingering={"ci_7_2"})

    with pytest.raises(ExceptionGroup) as both:
        _started(cluster)

    kinds = [type(failure) for failure in both.value.exceptions]
    assert kinds == [TimeoutError, CloudRunError]


def test_a_lock_not_held_at_release_fails_the_close() -> None:
    cluster = _Cluster(owned=[], unlocked=False)
    run, _ = _started(cluster)

    with pytest.raises(CloudRunError, match="not held"):
        run.close()

    assert cluster.log[-2:] == [f"{_CONTROL}: close", "ports: close"]


def test_an_interrupt_during_start_still_cleans_up_and_wins_over_cleanup_failures() -> None:
    cluster = _Cluster(
        owned=[],
        failing={'create database "ci_7_2"': KeyboardInterrupt()},
        unlocked=False,
    )

    with pytest.raises(KeyboardInterrupt) as interrupted:
        _started(cluster)

    notes = interrupted.value.__notes__ or []
    assert any("not held" in note for note in notes)
    assert cluster.log[-1] == "ports: close"


def test_leaving_the_run_by_a_failure_raises_it_beside_a_cleanup_failure() -> None:
    cluster = _Cluster(owned=[])
    run, _ = _started(cluster)
    cluster.lingering.add("ci_7_2")

    with pytest.raises(ExceptionGroup) as both, run:
        raise LookupError("the suite failed")

    assert [type(failure) for failure in both.value.exceptions] == [LookupError, CloudRunError]


def test_leaving_the_run_cleanly_raises_only_a_cleanup_failure() -> None:
    cluster = _Cluster(owned=[])
    run, _ = _started(cluster)
    cluster.lingering.add("ci_7_2")

    with pytest.raises(CloudRunError), run:
        pass


def test_leaving_the_run_by_a_failure_with_a_clean_cleanup_raises_the_failure() -> None:
    cluster = _Cluster(owned=[])
    run, _ = _started(cluster)

    with pytest.raises(LookupError), run:
        raise LookupError("the suite failed")

    assert cluster.log[-1] == "ports: close"


def test_an_inspection_session_is_opened_once_per_host_with_its_role_reset() -> None:
    cluster = _Cluster(owned=[])
    run, _ = _started(cluster)
    cluster.log.clear()

    first = run.session(_WRITER_INSTANCE)
    again = run.session(_WRITER_INSTANCE)

    assert first is again
    assert cluster.log == [
        f"{_WRITER_INSTANCE}/ci_7_2: open",
        f"{_WRITER_INSTANCE}/ci_7_2: set role none",
    ]


def test_the_adapter_signs_each_route_for_its_own_endpoint_and_application_name() -> None:
    run, ports = _started(_Cluster(owned=[]))
    on_demand = OnDemandOptions()

    run.adapter()
    run.adapter(pool=on_demand, reader=False)

    (writer, reader, alone) = ports.endpoints
    assert writer[:3] == (_WRITER, "ci_7_2", WRITER_APPLICATION)
    assert reader[:3] == (_READER, "ci_7_2", READER_APPLICATION)
    assert writer[3] == reader[3] == PoolOptions(min_size=0, num_workers=1)
    assert alone == (_WRITER, "ci_7_2", WRITER_APPLICATION, on_demand)


def test_resetting_waits_for_recreated_tables_and_grants_on_every_instance() -> None:
    clock = _Clock()
    previous = [(1, "schema grants", "rv_ledger", 2, "table grants")]
    current = [(3, "schema grants", "rv_ledger", 4, "table grants")]
    cluster = _Cluster(
        owned=[],
        reset_states={
            _WRITER: [current],
            _READER_INSTANCE: [
                previous,
                [],
                [(3, "schema grants", "rv_ledger", 4, None)],
                current,
            ],
            _WRITER_INSTANCE: [current],
        },
    )
    run, _ = _started(cluster, clock)
    cluster.log.clear()

    run.reset(SEEDED_MODEL, seeded_fixtures())

    administration = [entry for entry in cluster.log if entry.startswith(_ADMIN)]
    assert administration[0] == f"{_ADMIN}: drop schema if exists public cascade"
    reader_polls = [
        entry
        for entry in cluster.log
        if entry.startswith(f"{_READER_INSTANCE}/") and "pg_namespace" in entry
    ]
    assert len(reader_polls) == 4
    assert clock.now == 3.0


def test_resetting_gives_up_when_an_instance_never_catches_up() -> None:
    cluster = _Cluster(
        owned=[],
        reset_states={
            _WRITER: [[(3, "schema grants", "rv_ledger", 4, "table grants")]],
            _WRITER_INSTANCE: [[(1, "schema grants", "rv_ledger", 2, "table grants")]],
        },
    )
    run, _ = _started(cluster)

    with pytest.raises(TimeoutError, match="parallax-ci-writer to see the reset schema and grants"):
        run.reset(SEEDED_MODEL, seeded_fixtures())


def test_resetting_before_the_run_started_is_refused() -> None:
    run = AwsRun(_ENVIRONMENT, _IDENTITY, _Ports(_Cluster()), _pacing(_Clock()))
    with pytest.raises(CloudRunError, match="not started"):
        run.reset(SEEDED_MODEL, seeded_fixtures())


def test_case_runtimes_are_released_through_the_runs_ledger() -> None:
    run, _ = _started(_Cluster(owned=[]))
    assert run.release_case_runtimes() == 0
    assert run.authorization("role-a").name == "parallax_conformance_role_a"


def test_a_run_is_named_by_its_ci_run_and_attempt() -> None:
    identity = RunIdentity.from_environment({"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "4"})
    assert identity.database == "ci_123_4"


@pytest.mark.parametrize(
    "environment",
    [{}, {"GITHUB_RUN_ID": "123"}, {"GITHUB_RUN_ID": "x", "GITHUB_RUN_ATTEMPT": "1"}],
)
def test_a_run_without_a_ci_identity_is_refused(environment: dict[str, str]) -> None:
    with pytest.raises(CloudRunError, match="GITHUB_RUN_ID"):
        RunIdentity.from_environment(environment)


def test_a_termination_request_arrives_as_an_interrupt_only_for_the_duration() -> None:
    before = signal.getsignal(signal.SIGTERM)
    with interrupted_on_termination():
        handler = signal.getsignal(signal.SIGTERM)
        assert callable(handler)
        terminate: Callable[[int, FrameType | None], object] = handler
        with pytest.raises(KeyboardInterrupt):
            terminate(signal.SIGTERM, None)
    assert signal.getsignal(signal.SIGTERM) == before


def test_drop_does_not_force_terminate_background_workers() -> None:
    cluster = _Cluster(owned=[])
    run, _ = _started(cluster)
    cluster.failing['drop database if exists "ci_7_2" with (force)'] = PermissionError(
        "permission denied to terminate process"
    )
    run.close()
    assert f'{_CONTROL}: drop database if exists "ci_7_2"' in cluster.log


def test_drop_preserves_an_unrelated_sessions_failure() -> None:
    cluster = _Cluster(owned=[])
    run, _ = _started(cluster)
    failure = PermissionError("unrelated client remains")
    cluster.failing['drop database if exists "ci_7_2"'] = failure
    with pytest.raises(PermissionError) as refused:
        run.close()
    assert refused.value is failure
    assert cluster.log[-3:] == [
        f"{_CONTROL}: select pg_advisory_unlock(%s)",
        f"{_CONTROL}: close",
        "ports: close",
    ]


@pytest.mark.parametrize("fails", [False, True])
def test_drop_restores_the_control_timeout_after_success_and_failure(fails: bool) -> None:
    cluster = _Cluster(owned=[], timeout="7s")
    run, _ = _started(cluster)
    failure = TimeoutError("drop timed out")
    if fails:
        cluster.failing['drop database if exists "ci_7_2"'] = failure
        cluster.blockers = [(42, "other_login", "client backend", "other_application", "idle")]
        with pytest.raises(TimeoutError) as refused:
            run.close()
        assert refused.value is failure
        assert any("other_login" in note for note in refused.value.__notes__)
    else:
        run.close()
    assert cluster.timeout == "7s"


def test_drop_refuses_a_database_not_owned_by_the_login_before_any_mutation() -> None:
    cluster = _Cluster(owned=["ci_1_1"], owners={"ci_1_1": False})
    with pytest.raises(CloudRunError, match="not owned"):
        _started(cluster)
    assert not any("alter database" in entry or "drop database" in entry for entry in cluster.log)


def test_drop_of_an_already_absent_database_does_not_mutate_anything() -> None:
    cluster = _Cluster(owned=["ci_1_1"], owners={"ci_1_1": None})
    _started(cluster)
    assert not any("alter database" in entry or "drop database" in entry for entry in cluster.log)


def test_blocker_diagnostic_failure_does_not_replace_drop_failure() -> None:
    cluster = _Cluster(owned=[])
    run, _ = _started(cluster)
    failure = PermissionError("drop refused")
    cluster.failing['drop database if exists "ci_7_2"'] = failure
    cluster.failing[
        "select pid, usename, backend_type, application_name, state from pg_stat_activity "
        "where datname = %s order by pid"
    ] = ConnectionError("connection lost")
    with pytest.raises(PermissionError) as refused:
        run.close()
    assert refused.value is failure
    assert any("metadata unavailable" in note for note in refused.value.__notes__)


def test_failure_restoring_timeout_is_raised_beside_the_drop_failure() -> None:
    cluster = _Cluster(owned=[])
    run, _ = _started(cluster)
    cluster.failing["select set_config('statement_timeout', %s, false)"] = ConnectionError(
        "cannot set timeout"
    )
    with pytest.raises(ExceptionGroup) as failures:
        run.close()
    assert len(failures.value.exceptions) == 2
    assert all(isinstance(error, ConnectionError) for error in failures.value.exceptions)
