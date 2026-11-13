"""The wheel suite's externally provisioned, disposable PostgreSQL server."""

from __future__ import annotations

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from typing import Any

from psycopg.conninfo import conninfo_to_dict, make_conninfo

from parallax.conformance._postgres_control import PostgresControl
from parallax.conformance.provision import (
    CONFORMANCE_LOGIN,
    ContainerDatabase,
    RuntimeLedger,
    TrackedAdapter,
    conformance_credentials,
    install_authority_fixtures,
    reset_database,
)
from parallax.core.internal.database_binding import DatabaseBinding, ResolvedBinding
from parallax.core.internal.metamodel import Metamodel
from parallax.postgres import PoolOptions, PostgresAdapter, PostgresEndpoint


class WheelDatabase:
    def __init__(self, dsn: str, version: str) -> None:
        self._dsn = dsn
        self._session = self.control()
        self._ledger = RuntimeLedger()
        self._owned: frozenset[str] = frozenset()
        try:
            ((observed,),) = self._session.execute("show server_version", [])
            if str(observed).split()[0] != version:
                raise RuntimeError(f"PostgreSQL {observed!r} does not match selected {version}")
            ((exists,),) = self._session.execute(
                "select exists(select from pg_roles where rolname = ?)", [CONFORMANCE_LOGIN]
            )
            if not exists:
                install_authority_fixtures(self._session)
            options = conninfo_to_dict(dsn)
            options.pop("password", None)
            options["user"] = CONFORMANCE_LOGIN
            self._conninfo = make_conninfo("", **options)
            self.port = ContainerDatabase(self.configured(), self._session)
        except BaseException:
            self._session.close()
            raise

    def _adapter(self, *, pool: Any = None, settings: Mapping[str, str] | None = None) -> Any:
        options = " ".join(f"-c {name}={value}" for name, value in (settings or {}).items())
        return PostgresAdapter(
            writer=PostgresEndpoint(
                make_conninfo(self._conninfo, options=options),
                credentials=conformance_credentials(),
                pool=pool or PoolOptions(min_size=0, num_workers=1),
            ),
            prepare_threshold=None,
        )

    def configured(self, **options: Any) -> TrackedAdapter:
        return TrackedAdapter(self._adapter(**options), self._ledger)

    def control(self) -> PostgresControl:
        return PostgresControl.open(  # database-access: profile_run's disposable wheel-suite server
            self._dsn, autocommit=True, prepare_threshold=None
        )

    def reset(
        self, model: Metamodel, fixtures: Mapping[str, object], binding: DatabaseBinding
    ) -> None:
        self._owned = reset_database(
            self._session, ResolvedBinding(model, binding), fixtures, owned=self._owned
        )

    def release_case_runtimes(self) -> int:
        return self._ledger.release()

    def close(self) -> None:
        try:
            self.release_case_runtimes()
        finally:
            self._session.close()


@contextmanager
def wheel_database(dsn: str, version: str) -> Generator[WheelDatabase]:
    run = WheelDatabase(dsn, version)
    try:
        yield run
    finally:
        run.close()
