"""The MariaDB held session's per-attempt lifecycle, driven over a substituted driver.

``MariaDbProvider.open_session`` owns the session state its level and access mode
need for one attempt (m-db-port *Mapping obligations*): it saves
``innodb_snapshot_isolation`` — and ``transaction_read_only`` where a mode is
requested — configures the level and the mode, settles an unfinished
transaction, restores the saved values, and closes. The failures a live server
will not produce on demand — a refused setup, a restore or close that raises —
are scripted here at the driver seam; the live read-back of the restored values
is in ``test_compatibility.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from reference_harness.providers import mariadb
from reference_harness.providers.mariadb import (
    _ACCESS_MODE,
    _ISOLATION,
    _RESTORE_ACCESS_MODE,
    _RESTORE_SNAPSHOT_ISOLATION,
    _SAVE_ACCESS_MODE,
    _SAVE_SNAPSHOT_ISOLATION,
    CONNECTION_FLAGS,
    MariaDbProvider,
)

_LOCK_TUNING = "set innodb_lock_wait_timeout = 1"
_SNAPSHOT_ON = "set session innodb_snapshot_isolation = ON"
_SNAPSHOT_OFF = "set session innodb_snapshot_isolation = OFF"
_WORK = "update gauge set level = 1"
_MORE_WORK = "update gauge set level = 2"


class _DriverError(Exception):
    """A failure the scripted driver raises at a named call."""


def _restore(saved: int) -> str:
    return _RESTORE_SNAPSHOT_ISOLATION % saved


class _Cursor:
    def __init__(self, connection: _Connection) -> None:
        self._connection = connection
        self.rowcount = 0
        self.description = (("value", None, None, None),)

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, sql: str, args: tuple[Any, ...] | None = None) -> int:
        self._connection.call(sql if args is None else sql % args)
        return 0

    def fetchall(self) -> tuple[tuple[Any, ...], ...]:
        return ((self._connection.saved,),)


class _Connection:
    """One scripted connection: records each call, raising where it is told to."""

    def __init__(self, saved: int, failures: dict[str, Exception]) -> None:
        self.saved = saved
        self.failures = failures
        self.calls: list[str] = []
        self.open = True

    def call(self, label: str) -> None:
        self.calls.append(label)
        if label in self.failures:
            raise self.failures[label]

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def commit(self) -> None:
        self.call("commit")

    def rollback(self) -> None:
        self.call("rollback")

    def close(self) -> None:
        self.open = False
        self.call("close")


class _Driver:
    """Stands in for ``pymysql.connect``, handing out one scripted connection per call."""

    def __init__(self) -> None:
        self.saved: list[int] = []
        self.failures: dict[str, Exception] = {}
        self.connections: list[_Connection] = []
        self.parameters: list[dict[str, object]] = []

    def connect(self, **parameters: object) -> _Connection:
        saved = self.saved[len(self.connections)] if self.saved else 0
        connection = _Connection(saved, self.failures)
        self.connections.append(connection)
        self.parameters.append(parameters)
        return connection

    @property
    def calls(self) -> list[str]:
        (connection,) = self.connections
        return connection.calls


@pytest.fixture
def driver(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Driver]:
    scripted = _Driver()
    monkeypatch.setattr(mariadb.pymysql, "connect", scripted.connect)
    yield scripted


@pytest.fixture
def owner() -> MariaDbProvider:
    return MariaDbProvider(None, "harness")


def _setup(level: str | None) -> list[str]:
    return [_SAVE_SNAPSHOT_ISOLATION, *(_ISOLATION[level] if level else ()), _LOCK_TUNING, "commit"]


@pytest.mark.parametrize("level", [*_ISOLATION, None])
def test_a_session_saves_configures_restores_and_closes(
    driver: _Driver, owner: MariaDbProvider, level: str | None
) -> None:
    with owner.open_session(level):
        pass
    assert driver.calls == [*_setup(level), _restore(0), "close"]
    assert not driver.connections[0].open


def test_read_committed_disables_and_repeatable_read_enables_snapshot_isolation_after_saving_it(
    driver: _Driver, owner: MariaDbProvider
) -> None:
    for level in _ISOLATION:
        with owner.open_session(level):
            pass
    setting = {
        level: [call for call in connection.calls if call in (_SNAPSHOT_ON, _SNAPSHOT_OFF)]
        for level, connection in zip(_ISOLATION, driver.connections, strict=True)
    }
    assert setting == {
        "read-committed": [_SNAPSHOT_OFF],
        "repeatable-read": [_SNAPSHOT_ON],
        "serializable": [],
    }
    for level, statement in (("read-committed", _SNAPSHOT_OFF), ("repeatable-read", _SNAPSHOT_ON)):
        calls = driver.connections[list(_ISOLATION).index(level)].calls
        assert calls.index(_SAVE_SNAPSHOT_ISOLATION) < calls.index(statement)


@pytest.mark.parametrize("level", ["read-committed", "repeatable-read"])
def test_each_attempt_context_repeats_the_choreography_on_its_own_connection(
    driver: _Driver, owner: MariaDbProvider, level: str
) -> None:
    driver.saved = [0, 1]
    for _ in driver.saved:
        with owner.open_session(level) as session:
            session.execute(_WORK)
            session.commit()
    first, second = (connection.calls for connection in driver.connections)
    assert first == [*_setup(level), _WORK, "commit", _restore(0), "close"]
    assert second == [*_setup(level), _WORK, "commit", _restore(1), "close"]


def test_unfinished_work_is_rolled_back_before_the_restore(
    driver: _Driver, owner: MariaDbProvider
) -> None:
    with owner.open_session("repeatable-read") as session:
        session.execute(_WORK)
    assert driver.calls[len(_setup("repeatable-read")) :] == [
        _WORK,
        "rollback",
        _restore(0),
        "close",
    ]


def test_a_settled_transaction_is_not_settled_again(
    driver: _Driver, owner: MariaDbProvider
) -> None:
    with owner.open_session("read-committed") as session:
        session.query("select 1")
        session.rollback()
    assert driver.calls[len(_setup("read-committed")) :] == [
        "select 1",
        "rollback",
        _restore(0),
        "close",
    ]


def test_work_after_a_commit_is_a_new_transaction_that_exit_settles(
    driver: _Driver, owner: MariaDbProvider
) -> None:
    with owner.open_session("repeatable-read") as session:
        session.execute(_WORK)
        session.commit()
        session.execute(_MORE_WORK)
    assert driver.calls[len(_setup("repeatable-read")) :] == [
        _WORK,
        "commit",
        _MORE_WORK,
        "rollback",
        _restore(0),
        "close",
    ]


def test_a_failed_setup_runs_no_body_and_closes_without_restoring(
    driver: _Driver, owner: MariaDbProvider
) -> None:
    refusal = driver.failures[_SNAPSHOT_ON] = _DriverError("refused")
    entered = False
    with pytest.raises(_DriverError) as raised:
        with owner.open_session("repeatable-read"):
            entered = True
    assert raised.value is refusal
    assert not entered
    assert driver.calls[-2:] == [_SNAPSHOT_ON, "close"]
    assert _restore(0) not in driver.calls


def test_a_failed_setup_stays_primary_over_a_failed_close(
    driver: _Driver, owner: MariaDbProvider
) -> None:
    refusal = driver.failures[_LOCK_TUNING] = _DriverError("refused")
    driver.failures["close"] = _DriverError("close failed")
    with pytest.raises(_DriverError) as raised:
        with owner.open_session("read-committed"):
            pass
    assert raised.value is refusal
    assert raised.value.__notes__ == [
        "MariaDB session cleanup also failed while closing the connection: "
        "_DriverError('close failed')"
    ]


@pytest.mark.parametrize(
    ("settle", "outcome"),
    [
        ("commit", "the session's last transaction committed"),
        ("rollback", "the session's last transaction rolled back"),
    ],
)
def test_a_failed_restore_surfaces_the_reached_outcome_and_closes(
    driver: _Driver, owner: MariaDbProvider, settle: str, outcome: str
) -> None:
    failure = driver.failures[_restore(0)] = _DriverError("restore failed")
    with pytest.raises(_DriverError) as raised:
        with owner.open_session("repeatable-read") as session:
            session.execute(_WORK)
            getattr(session, settle)()
    assert raised.value is failure
    assert raised.value.__notes__ == [
        f"MariaDB session cleanup failed while restoring innodb_snapshot_isolation; {outcome}"
    ]
    assert driver.calls[-4:] == [_WORK, settle, _restore(0), "close"]
    assert not driver.connections[0].open


def test_a_body_failure_stays_primary_over_every_cleanup_failure(
    driver: _Driver, owner: MariaDbProvider
) -> None:
    driver.failures[_restore(0)] = _DriverError("restore failed")
    driver.failures["close"] = _DriverError("close failed")
    body_failure = ValueError("body failed")
    with pytest.raises(ValueError) as raised:
        with owner.open_session("repeatable-read") as session:
            session.execute(_WORK)
            raise body_failure
    assert raised.value is body_failure
    assert raised.value.__notes__ == [
        "MariaDB session cleanup also failed while restoring innodb_snapshot_isolation: "
        "_DriverError('restore failed')",
        "MariaDB session cleanup also failed while closing the connection: "
        "_DriverError('close failed')",
    ]
    assert driver.calls[-4:] == [_WORK, "rollback", _restore(0), "close"]


def test_the_first_cleanup_failure_surfaces_with_later_ones_noted(
    driver: _Driver, owner: MariaDbProvider
) -> None:
    settle_failure = driver.failures["rollback"] = _DriverError("rollback failed")
    driver.failures["close"] = _DriverError("close failed")
    with pytest.raises(_DriverError) as raised:
        with owner.open_session("serializable") as session:
            session.execute(_WORK)
    assert raised.value is settle_failure
    assert raised.value.__notes__ == [
        "MariaDB session cleanup failed while settling its unfinished transaction; "
        "the session's last transaction never reported a commit",
        "MariaDB session cleanup also failed while closing the connection: "
        "_DriverError('close failed')",
    ]
    assert driver.calls[-4:] == [_WORK, "rollback", _restore(0), "close"]


@pytest.mark.parametrize("mode", list(_ACCESS_MODE))
@pytest.mark.parametrize("level", [*_ISOLATION, None])
def test_an_access_mode_is_saved_applied_after_the_level_and_restored(
    driver: _Driver, owner: MariaDbProvider, level: str | None, mode: str
) -> None:
    with owner.open_session(level, mode) as session:
        session.execute(_WORK)
        session.commit()
    assert driver.calls == [
        _SAVE_SNAPSHOT_ISOLATION,
        _SAVE_ACCESS_MODE,
        *(_ISOLATION[level] if level else ()),
        _ACCESS_MODE[mode],
        _LOCK_TUNING,
        "commit",
        _WORK,
        "commit",
        _restore(0),
        _RESTORE_ACCESS_MODE % 0,
        "close",
    ]


def test_a_failed_access_mode_setup_runs_no_body_and_closes_without_restoring(
    driver: _Driver, owner: MariaDbProvider
) -> None:
    refusal = driver.failures[_ACCESS_MODE["read-only"]] = _DriverError("refused")
    entered = False
    with pytest.raises(_DriverError) as raised:
        with owner.open_session("repeatable-read", "read-only"):
            entered = True
    assert raised.value is refusal
    assert not entered
    assert driver.calls[-2:] == [_ACCESS_MODE["read-only"], "close"]


def test_a_failed_access_mode_restore_surfaces_the_reached_outcome_and_closes(
    driver: _Driver, owner: MariaDbProvider
) -> None:
    failure = driver.failures[_RESTORE_ACCESS_MODE % 0] = _DriverError("restore failed")
    with pytest.raises(_DriverError) as raised:
        with owner.open_session("read-committed", "read-only") as session:
            session.query("select 1")
            session.commit()
    assert raised.value is failure
    assert raised.value.__notes__ == [
        "MariaDB session cleanup failed while restoring transaction_read_only; "
        "the session's last transaction committed"
    ]
    assert driver.calls[-3:] == [_restore(0), _RESTORE_ACCESS_MODE % 0, "close"]


def test_every_connection_a_provider_opens_counts_the_rows_it_matches(
    driver: _Driver,
) -> None:
    # Whatever parameters the provider was handed, a held session and a peer
    # both negotiate CLIENT_FOUND_ROWS, so an UPDATE counts its unchanged matches.
    owner = MariaDbProvider(None, "harness", {"user": "u", "client_flag": 0})
    with owner.open_session("read-committed"):
        pass
    with owner.open_peer():
        pass
    assert [
        (parameters["client_flag"], parameters["autocommit"]) for parameters in driver.parameters
    ] == [(CONNECTION_FLAGS, False), (CONNECTION_FLAGS, True)]
    assert all(parameters["user"] == "u" for parameters in driver.parameters)
