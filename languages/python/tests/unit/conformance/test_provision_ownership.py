"""What provisioning owns beside its container, without one.

The schema reset and the authority fixtures are statements a session runs, so
a recording session proves their order; the runtime ledger is the backstop
that closes what a case left open, so scripted runtimes prove it attempts
every close and lets no interrupt cut the others short.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import pytest

from parallax.conformance import provision
from parallax.conformance.provision import (
    CONFORMANCE_LOGIN,
    RuntimeLedger,
    TrackedAdapter,
    conformance_credentials,
    database_authorization,
    install_authority_fixtures,
    reset_database,
)
from parallax.core.db_port import (
    AccessMode,
    DatabaseConnection,
    DatabaseRuntime,
    DocumentReadOrdinals,
    IsolationLevel,
    OrderedWriteTransport,
    PipelineStatement,
    Route,
    RouteCapabilities,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import POSTGRES, Dialect
from parallax.postgres import PostgresAdapter, PostgresEndpoint, PostgresRole
from tests.unit._corpus_model_support import corpus

_ROLES = (
    "parallax_conformance_default",
    "parallax_conformance_role_a",
    "parallax_conformance_role_b",
)


class _Recording:
    """A session recording every write it is asked to run."""

    def __init__(self) -> None:
        self.writes: list[tuple[str, Sequence[object]]] = []

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
        raise AssertionError(f"provisioning reads nothing back: {sql!r}")

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        self.writes.append((sql, binds))
        return 0

    def execute_pipeline(
        self, statements: Sequence[PipelineStatement], *, read_only: bool = False
    ) -> list[list[Row]]:
        raise AssertionError("provisioning submits no pipeline")

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
        raise AssertionError("provisioning opens no transaction")

    def statements(self) -> list[str]:
        return [sql for sql, _binds in self.writes]


def test_a_reset_rebuilds_the_schema_loads_fixtures_then_grants_every_conformance_role() -> None:
    model = corpus()["grade"]
    fixtures = provision.load_fixtures("models/grade.yaml")
    session = _Recording()

    reset_database(session, model, fixtures)

    ddl = provision.schema_statements(model)
    inserts = provision.fixture_statements(model, fixtures)
    grants = [
        statement
        for role in _ROLES
        for statement in (
            f'grant usage on schema public to "{role}"',
            f'grant select, insert, update, delete on all tables in schema public to "{role}"',
        )
    ]
    assert session.statements() == [
        *provision.reset_statements(),
        *ddl,
        *(POSTGRES.to_driver_sql(sql) for sql, _binds in inserts),
        *grants,
    ]
    assert [binds for sql, binds in session.writes if sql.startswith("insert")] == [
        binds for _sql, binds in inserts
    ]


def test_the_authority_fixtures_give_the_login_every_role_and_its_default() -> None:
    session = _Recording()

    install_authority_fixtures(session)

    assert session.statements() == [
        *(f'create role "{role}"' for role in _ROLES),
        f"create role \"{CONFORMANCE_LOGIN}\" login password 'parallax-conformance-password'",
        *(f'grant "{role}" to "{CONFORMANCE_LOGIN}"' for role in _ROLES),
        f'alter role "{CONFORMANCE_LOGIN}" set role to "parallax_conformance_default"',
    ]


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

    ledger.release()
    ledger.release()

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

    ledger.release()
    ledger.release()

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
    ledger.release()
    assert len(log) == 4


def test_a_tracked_adapter_keeps_every_runtime_it_opens_on_its_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log: list[str] = []
    configuration = PostgresAdapter(
        writer=PostgresEndpoint("host=nowhere.test", credentials=conformance_credentials())
    )
    monkeypatch.setattr(PostgresAdapter, "open", _opening(log))
    ledger = RuntimeLedger()
    adapter = TrackedAdapter(configuration, ledger)

    adapter.open()
    adapter.open()
    ledger.release()

    assert adapter.dialect is POSTGRES
    assert adapter.configuration is configuration
    assert log == ["close opened", "close opened"]


def _opening(log: list[str]) -> Callable[[PostgresAdapter], _Runtime]:
    return lambda _adapter: _Runtime(log, "opened")
