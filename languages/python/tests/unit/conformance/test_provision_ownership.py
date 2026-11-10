"""What provisioning owns beside its container, without one.

A case selector names its database authorization, and the runtime ledger closes
and counts what a case left open, so scripted runtimes prove it counts only
those, attempts every close, and lets no interrupt cut the others short.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import pytest

from parallax.conformance.provision import (
    CONFORMANCE_LOGIN,
    RuntimeLedger,
    database_authorization,
)
from parallax.core.db_port import (
    DatabaseRuntime,
    Route,
    RouteCapabilities,
)
from parallax.core.dialect import POSTGRES, Dialect
from parallax.postgres import PostgresRole


def test_a_case_selector_names_its_database_authorization() -> None:
    assert database_authorization("role-b") == PostgresRole("parallax_conformance_role_b")
    with pytest.raises(ValueError, match="unknown database authorization fixture 'role-c'"):
        database_authorization("role-c")


class _Source:
    """A context source standing in for one authority's."""


class _Runtime:
    """A runtime whose close runs ``closing``."""

    dialect: Dialect = POSTGRES
    routes: Mapping[Route, RouteCapabilities] = {"writer": RouteCapabilities.every_level()}
    pool_metrics: tuple[Any, ...] = ()
    login_identity = CONFORMANCE_LOGIN

    def __init__(self, log: list[str], name: str, closing: Callable[[], None] = lambda: None):
        self._log = log
        self._name = name
        self._closing = closing
        self.source = _Source()

    def login_source(self) -> Any:
        return self.source

    def principal_source(self, authorization: PostgresRole) -> Any:
        del authorization
        return self.source

    def close(self) -> None:
        self._log.append(f"close {self._name}")
        self._closing()


def _tracked(ledger: RuntimeLedger, runtime: _Runtime) -> DatabaseRuntime[PostgresRole]:
    return ledger.track(runtime)


def test_a_tracked_runtime_forwards_to_the_runtime_it_tracks() -> None:
    runtime = _Runtime([], "one")
    tracked = _tracked(RuntimeLedger(), runtime)

    assert tracked.dialect is POSTGRES
    assert tracked.routes is runtime.routes
    assert tracked.pool_metrics == ()
    assert tracked.login_identity == CONFORMANCE_LOGIN
    assert tracked.login_source() is runtime.source
    assert tracked.principal_source(PostgresRole("r")) is runtime.source


def test_the_ledger_releases_only_what_was_left_open() -> None:
    log: list[str] = []
    ledger = RuntimeLedger()
    closed = _tracked(ledger, _Runtime(log, "closed"))
    _tracked(ledger, _Runtime(log, "left open"))
    closed.close()
    closed.close()

    assert ledger.release() == 1
    assert ledger.release() == 0

    assert log == ["close closed", "close closed", "close left open"]


def _raising(failure: BaseException) -> Callable[[], None]:
    def close() -> None:
        raise failure

    return close


def test_the_ledger_contains_an_ordinary_failure_and_closes_the_rest() -> None:
    log: list[str] = []
    ledger = RuntimeLedger()
    _tracked(ledger, _Runtime(log, "failing", _raising(RuntimeError("refused"))))
    _tracked(ledger, _Runtime(log, "next"))

    assert ledger.release() == 2
    assert ledger.release() == 0

    assert log == ["close failing", "close next"]


def test_the_ledger_raises_the_first_interrupt_only_after_every_close() -> None:
    log: list[str] = []
    first, second = KeyboardInterrupt("first"), SystemExit("second")
    ledger = RuntimeLedger()
    _tracked(ledger, _Runtime(log, "interrupted", _raising(first)))
    _tracked(ledger, _Runtime(log, "failing", _raising(RuntimeError("refused"))))
    _tracked(ledger, _Runtime(log, "exiting", _raising(second)))
    _tracked(ledger, _Runtime(log, "last"))

    with pytest.raises(KeyboardInterrupt) as raised:
        ledger.release()

    assert raised.value is first
    assert log == ["close interrupted", "close failing", "close exiting", "close last"]
    assert ledger.release() == 0
    assert len(log) == 4
