"""The primary/standby pair's ownership, ordering and waits, without Docker.

A scripted launch stands in for the servers and scripted sessions for the
server conditions, so what is proved here is the pair's own discipline:
everything started is released newest first however opening or closing ends,
replay always resumes or the pair closes, and every wait gives up at its
deadline. What the standby
actually shows a reader is proved against real servers under
``tests/provider_contract``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, field
from typing import Any

import pytest
from psycopg.conninfo import conninfo_to_dict

from parallax.conformance._replication import (
    LazyReplication,
    Pacing,
    ReplicationPair,
    Server,
)
from parallax.conformance.provision import CONFORMANCE_LOGIN, conformance_credentials
from parallax.core.internal.db_port import (
    AccessMode,
    DatabaseConnection,
    DocumentReadOrdinals,
    IsolationLevel,
    OrderedWriteTransport,
    PipelineStatement,
    Row,
    TransactionOutcome,
)
from parallax.core.internal.dialect import POSTGRES, Dialect
from parallax.postgres import PostgresAdapter, PostgresRole
from tests.unit._corpus_model_support import corpus

_PRIMARY = Server(
    administration="host=primary.test port=1 dbname=d user=admin password=admin-secret",
    login=f"host=primary.test port=1 dbname=d user={CONFORMANCE_LOGIN}",
)
_STANDBY = Server(
    administration="host=standby.test port=2 dbname=d user=admin password=admin-secret",
    login=f"host=standby.test port=2 dbname=d user={CONFORMANCE_LOGIN}",
)


class _Clock:
    """Monotonic time that moves only when the pair polls."""

    def __init__(self) -> None:
        self.now = 0.0

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _pacing(clock: _Clock, within: float = 1.0) -> Pacing:
    return Pacing(within=within, interval=0.25, clock=lambda: clock.now, sleep=clock.sleep)


type _Answer = Callable[[str, Sequence[object]], list[Row]]


def _always(*rows: Row) -> _Answer:
    """An answer of ``rows`` to every statement."""
    return lambda _sql, _binds: list(rows)


@dataclass
class _Session:
    """A server session answering each statement from ``answer``."""

    name: str
    log: list[str]
    answer: _Answer = field(default=_always())
    executed: list[tuple[str, Sequence[object]]] = field(default_factory=list[tuple[str, Any]])

    @property
    def dialect(self) -> Dialect:
        return POSTGRES

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
        *,
        read_only: bool = False,
    ) -> list[Row]:
        del document_reads, read_only
        self.executed.append((sql, binds))
        return self.answer(sql, binds)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        self.executed.append((sql, binds))
        return 0

    def execute_pipeline(
        self, statements: Sequence[PipelineStatement], *, read_only: bool = False
    ) -> list[list[Row]]:
        raise AssertionError("the pair submits no pipeline")

    @property
    def ordered_write_transport(self) -> OrderedWriteTransport | None:
        return None

    def transaction[T](
        self,
        body: Callable[[DatabaseConnection], T],
        *,
        isolation: IsolationLevel | None = None,
        access_mode: AccessMode | None = None,
    ) -> TransactionOutcome[T]:
        raise AssertionError("the pair opens no transaction of its own")

    def rollback(self) -> None:
        raise AssertionError("the pair holds no transaction to roll back")

    def terminate_session(self, target: DatabaseConnection) -> None:
        raise AssertionError("the pair ends no other session")

    def statements(self) -> list[str]:
        return [sql for sql, _binds in self.executed]

    def close(self) -> None:
        self.log.append(f"close {self.name} session")


def _healthy_primary(sql: str, _binds: Sequence[object]) -> list[Row]:
    if "pg_stat_replication" in sql or "pg_current_wal_lsn" in sql:
        return [(1,)] if "count" in sql else [("0/3000060",)]
    return []


def _healthy_standby(sql: str, _binds: Sequence[object]) -> list[Row]:
    if "pause_state" in sql:
        return [("paused",)]
    if "replay_lsn" in sql:
        return [(True,)]
    return []


@dataclass
class _Launch:
    """A launch recording each step, failing at ``failing`` if named."""

    log: list[str] = field(default_factory=list[str])
    failing: str | None = None
    primary_answer: _Answer = _healthy_primary
    standby_answer: _Answer = _healthy_standby
    sessions: dict[str, _Session] = field(default_factory=dict[str, _Session])

    def _step(self, resources: ExitStack, step: str) -> None:
        resources.callback(self.log.append, f"release {step}")
        self.log.append(f"start {step}")
        if self.failing == step:
            raise RuntimeError(f"{step} failed")

    def network(self, resources: ExitStack) -> object:
        self._step(resources, "network")
        return "network"

    def primary(self, resources: ExitStack, network: object, replication_login: str) -> Server:
        assert network == "network"
        del replication_login
        self._step(resources, "primary")
        return _PRIMARY

    def standby(self, resources: ExitStack, network: object, source: str) -> Server:
        assert network == "network"
        del source
        self._step(resources, "standby")
        return _STANDBY

    def session(self, conninfo: str) -> _Session:
        name = "primary" if conninfo == _PRIMARY.administration else "standby"
        self.log.append(f"open {name} session")
        if self.failing == f"{name} session":
            raise RuntimeError(f"{name} session failed")
        answer = self.primary_answer if name == "primary" else self.standby_answer
        session = _Session(name, self.log, answer)
        self.sessions[name] = session
        return session


def _opened(launch: _Launch, clock: _Clock | None = None) -> ReplicationPair:
    paced = _pacing(clock if clock is not None else _Clock())
    return ReplicationPair.open(launch, pacing=paced)  # database-access: a scripted launch


_RELEASED_NEWEST_FIRST = [
    "close standby session",
    "release standby",
    "close primary session",
    "release primary",
    "release network",
]


@pytest.mark.parametrize(
    ("failing", "started"),
    [
        ("network", ["release network"]),
        ("primary", ["release primary", "release network"]),
        ("primary session", ["release primary", "release network"]),
        (
            "standby",
            ["release standby", "close primary session", "release primary", "release network"],
        ),
        (
            "standby session",
            ["release standby", "close primary session", "release primary", "release network"],
        ),
    ],
)
def test_a_failed_start_releases_everything_started_so_far_newest_first(
    failing: str, started: list[str]
) -> None:
    launch = _Launch(failing=failing)

    with pytest.raises(RuntimeError, match=f"{failing} failed"):
        _opened(launch)

    released = [entry for entry in launch.log if entry.startswith(("release", "close"))]
    assert released == started


@pytest.mark.parametrize("condition", ["state = 'streaming'", "sync_state = 'sync'"])
def test_a_standby_that_never_synchronizes_fails_the_open_at_its_deadline(condition: str) -> None:
    def never(sql: str, binds: Sequence[object]) -> list[Row]:
        return [(0,)] if condition in sql else _healthy_primary(sql, binds)

    launch = _Launch(primary_answer=never)
    clock = _Clock()

    with pytest.raises(TimeoutError, match="waited 1 s for the standby"):
        _opened(launch, clock)

    assert clock.now == pytest.approx(1.0)
    released = [entry for entry in launch.log if entry.startswith(("release", "close"))]
    assert released == _RELEASED_NEWEST_FIRST


class _Runtime:
    """A runtime that records when it is closed."""

    def __init__(self, log: list[str]) -> None:
        self._log = log

    def close(self) -> None:
        self._log.append("close runtime")


def _opening_into(log: list[str]) -> Callable[[PostgresAdapter], _Runtime]:
    """``PostgresAdapter.open`` stubbed to a runtime recording its close in ``log``."""
    return lambda _adapter: _Runtime(log)


def test_closing_releases_runtimes_before_the_sessions_servers_and_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launch = _Launch()
    pair = _opened(launch)
    monkeypatch.setattr(PostgresAdapter, "open", _opening_into(launch.log))
    pair.adapter().open()
    launch.log.clear()

    pair.close()
    pair.close()

    assert launch.log == ["close runtime", *_RELEASED_NEWEST_FIRST]


def test_releasing_runtimes_leaves_the_servers_running(monkeypatch: pytest.MonkeyPatch) -> None:
    launch = _Launch()
    pair = _opened(launch)
    monkeypatch.setattr(PostgresAdapter, "open", _opening_into(launch.log))
    pair.adapter().open()
    launch.log.clear()

    assert pair.release_runtimes() == 1

    assert launch.log == ["close runtime"]
    pair.close()


@pytest.mark.parametrize("synchronous_commit", ["remote_apply", "local"])
def test_the_adapter_writes_to_the_primary_and_reads_from_the_standby(
    synchronous_commit: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    pair = _opened(_Launch())
    opened_from: list[PostgresAdapter] = []

    def opening(configured: PostgresAdapter) -> _Runtime:
        opened_from.append(configured)
        return _Runtime([])

    monkeypatch.setattr(PostgresAdapter, "open", opening)

    pair.adapter(synchronous_commit=synchronous_commit).open()

    (configured,) = opened_from
    assert configured.reader is not None
    writer = conninfo_to_dict(configured.writer.connection_string)
    reader = conninfo_to_dict(configured.reader.connection_string)
    assert (writer["host"], writer["user"]) == ("primary.test", CONFORMANCE_LOGIN)
    assert writer["options"] == f"-c synchronous_commit={synchronous_commit}"
    assert (reader["host"], reader["user"]) == ("standby.test", CONFORMANCE_LOGIN)
    assert "options" not in reader
    assert configured.writer.credentials == conformance_credentials()
    assert configured.reader.credentials == conformance_credentials()
    assert configured.prepare_threshold is None
    assert pair.adapter().dialect is POSTGRES
    assert (pair.login_identity, pair.credentials) == (CONFORMANCE_LOGIN, conformance_credentials())
    assert pair.authorization("role-a") == PostgresRole("parallax_conformance_role_a")
    pair.close()


def test_a_reset_runs_on_the_primary_and_waits_for_the_standby_to_apply_it() -> None:
    launch = _Launch()
    pair = _opened(launch)
    primary, standby = launch.sessions["primary"], launch.sessions["standby"]
    primary.executed.clear()

    pair.reset(corpus()["grade"], {})

    statements = primary.statements()
    assert statements[:2] == ["drop schema if exists public cascade", "create schema public"]
    assert statements[-1] == "select pg_current_wal_lsn()::text"
    assert standby.executed[-1] == (
        "select coalesce(pg_last_wal_replay_lsn() >= ?::pg_lsn, false)",
        ["0/3000060"],
    )
    pair.close()


def test_waiting_for_replay_gives_up_at_its_deadline() -> None:
    launch = _Launch(standby_answer=_always((False,)))
    clock = _Clock()
    pair = _opened(launch, clock)
    started = clock.now

    with pytest.raises(TimeoutError, match="1 s for the standby to replay through 0/4000000"):
        pair.wait_replayed("0/4000000")

    assert clock.now - started == pytest.approx(1.0)
    pair.close()


def _replay_controls(session: _Session) -> list[str]:
    return [sql for sql in session.statements() if sql.startswith("select pg_wal_replay_")]


def test_replay_resumes_when_the_body_fails() -> None:
    launch = _Launch()
    pair = _opened(launch)

    with pytest.raises(LookupError), pair.paused_replay():
        raise LookupError

    assert _replay_controls(launch.sessions["standby"])[-1] == "select pg_wal_replay_resume()"
    pair.close()


def test_replay_resumes_when_the_pause_is_never_confirmed() -> None:
    launch = _Launch(standby_answer=_always(("pause requested",)))
    pair = _opened(launch)
    entered = False

    with pytest.raises(TimeoutError, match="replay to pause"), pair.paused_replay():
        entered = True

    assert not entered
    assert _replay_controls(launch.sessions["standby"]) == [
        "select pg_wal_replay_pause()",
        "select pg_wal_replay_resume()",
    ]
    pair.close()


def test_a_resume_that_fails_closes_the_pair_it_may_have_left_paused() -> None:
    def refusing_resume(sql: str, binds: Sequence[object]) -> list[Row]:
        if "replay_resume" in sql:
            raise ConnectionError("standby session lost")
        return _healthy_standby(sql, binds)

    launch = _Launch(standby_answer=refusing_resume)
    pair = _opened(launch)
    launch.log.clear()

    with pytest.raises(ConnectionError, match="standby session lost"), pair.paused_replay():
        pass

    assert pair.closed
    assert launch.log == _RELEASED_NEWEST_FIRST


class _Owned:
    def __init__(self, log: list[str]) -> None:
        self._log = log
        self.closed = False

    def release_runtimes(self) -> int:
        self._log.append("release runtimes")
        return 2

    def close(self) -> None:
        self._log.append("close")


def test_a_lazy_pair_opens_once_on_first_use() -> None:
    log: list[str] = []
    opened: list[_Owned] = []

    def open_pair() -> _Owned:
        opened.append(_Owned(log))
        return opened[-1]

    lazy = LazyReplication(open_pair)
    assert lazy.release_runtimes() == 0
    assert opened == []

    first = lazy.pair()
    assert lazy.pair() is first
    assert lazy.release_runtimes() == 2
    lazy.close()
    lazy.close()

    assert opened == [first]
    assert log == ["release runtimes", "close"]
    with pytest.raises(RuntimeError, match="has closed"):
        lazy.pair()


def test_a_lazy_pair_never_used_opens_nothing_on_close() -> None:
    def refuse() -> _Owned:
        raise AssertionError("a pair nobody asked for was opened")

    lazy = LazyReplication(refuse)

    lazy.release_runtimes()
    lazy.close()


def test_a_lazy_pair_whose_open_failed_opens_again_on_next_use() -> None:
    attempts: list[str] = []

    def open_pair() -> _Owned:
        attempts.append("open")
        if len(attempts) == 1:
            raise RuntimeError("no docker")
        return _Owned([])

    lazy = LazyReplication(open_pair)
    with pytest.raises(RuntimeError, match="no docker"):
        lazy.pair()

    lazy.pair()

    assert attempts == ["open", "open"]


def test_a_lazy_pair_that_closed_itself_is_replaced_on_next_use() -> None:
    opened: list[_Owned] = []

    def open_pair() -> _Owned:
        opened.append(_Owned([]))
        return opened[-1]

    lazy = LazyReplication(open_pair)
    retired = lazy.pair()
    retired.closed = True

    replacement = lazy.pair()

    assert replacement is not retired
    assert lazy.pair() is replacement
    assert opened == [retired, replacement]
