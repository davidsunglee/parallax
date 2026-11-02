"""One cloud run's lifetime against the deployed AWS test environment.

The run works entirely as the conformance login the environment's role bootstrap
created, authenticated by an IAM token signed for each host it reaches and over
TLS verified against the certificate bundle the environment names: no
administrative credential reaches it. Its control and administration sessions
reset their role, because the login's CREATEDB attribute is the login's own, not
its default role's; every session it hands a test keeps the default role, as an
application's does, and inspection sessions reset theirs only to see the same
login's other sessions in full.

Cloud runs share one cluster, so a run holds a session advisory lock on the
control database for its whole lifetime. Under that lock any run database the
login still owns is stale — a runner killed before its cleanup ran never reached
it — so the run drops every one before creating its own; that recovery is why a
run that dies uncleanly costs nothing but its next run's first seconds.

Cleanup runs newest first and attempts every step whatever the ones before it
did: runtimes and sessions, the run database, the lock, the control session, the
fetched certificate bundle. A database whose removal is not confirmed fails the
run rather than leaving a leak behind passing assertions, and a failure that
cleanup itself meets is raised beside the one that started it rather than in
its place. Closing every connection is also what lets the cluster pause.
"""

from __future__ import annotations

import re
import shutil
import signal
import tempfile
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType, TracebackType
from typing import TYPE_CHECKING, Final, Protocol, Self

from parallax.conformance._replication import Pacing
from parallax.conformance.provision import (
    RuntimeLedger,
    TrackedAdapter,
    database_authorization,
    reset_database,
)
from tests._support.aws_environment import AwsTestEnvironment, PublishedEnvironment

if TYPE_CHECKING:
    from parallax.conformance._database_control import DriverControl
    from parallax.core.metamodel import Metamodel
    from parallax.postgres import OnDemandOptions, PoolOptions, PostgresEndpoint, PostgresRole

__all__ = [
    "CONTROL_DATABASE",
    "READER_APPLICATION",
    "SUITE_LOCK",
    "WRITER_APPLICATION",
    "AwsRun",
    "CloudPacing",
    "CloudPorts",
    "CloudRunError",
    "RunIdentity",
    "interrupted_on_termination",
]

CONTROL_DATABASE: Final = "parallax_ci_control"
"""The database the cluster was created with, which holds the suite lock."""

SUITE_LOCK: Final = 0x70_61_72_61_78
"""The advisory lock key every cloud run holds on the control database."""

WRITER_APPLICATION: Final = "parallax-ci-writer"
READER_APPLICATION: Final = "parallax-ci-reader"
"""The application names each route's sessions carry, by which an inspection
session finds where a route's backends physically are."""

_RUN_DATABASE = re.compile(r"ci_[0-9]+_[0-9]+")
_RESET_ROLE = "reset role"
_TRY_LOCK = "select pg_try_advisory_lock(%s)"
_UNLOCK = "select pg_advisory_unlock(%s)"
_OWNED = (
    "select d.datname from pg_database d join pg_roles r on r.oid = d.datdba "
    "where r.rolname = current_user order by d.datname"
)
_PRESENT = "select count(*) from pg_database where datname = %s"
_ANSWER = "select 1"
_TABLES = (
    "select coalesce(string_agg(tablename, ',' order by tablename), '') "
    "from pg_tables where schemaname = 'public'"
)


class CloudRunError(RuntimeError):
    """The cloud run could not establish, or could not confirm releasing, what it owns."""


@dataclass(frozen=True, slots=True)
class RunIdentity:
    """Which CI run attempt this is, which names its database."""

    run_id: int
    attempt: int

    @property
    def database(self) -> str:
        return f"ci_{self.run_id}_{self.attempt}"

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> RunIdentity:
        try:
            return cls(int(environment["GITHUB_RUN_ID"]), int(environment["GITHUB_RUN_ATTEMPT"]))
        except (KeyError, ValueError) as missing:
            raise CloudRunError(
                "a cloud run names its database by GITHUB_RUN_ID and GITHUB_RUN_ATTEMPT"
            ) from missing


@dataclass(frozen=True)
class CloudPacing:
    """How long the run waits for the suite lock, for each host to answer, and
    for a reader to see what the writer committed — and how often it looks."""

    lock: Pacing = field(default_factory=lambda: Pacing(within=600.0, interval=5.0))
    warm: Pacing = field(default_factory=lambda: Pacing(within=300.0, interval=2.0))
    visible: Pacing = field(default_factory=lambda: Pacing(within=60.0, interval=0.25))


class CloudPorts(Protocol):
    """How a run reaches the environment: every connection it opens, and the
    endpoints it configures, go through one of these."""

    def session(self, host: str, database: str) -> DriverControl:
        """An autocommit session on *host* as the login."""
        ...

    def endpoint(
        self,
        host: str,
        database: str,
        *,
        application_name: str,
        pool: PoolOptions | OnDemandOptions,
    ) -> PostgresEndpoint:
        """One route's configuration on *host* as the login."""
        ...

    def close(self) -> None:
        """Release what opening the ports fetched."""
        ...


class _Teardown:
    """Cleanup steps, run newest first, every one attempted."""

    def __init__(self) -> None:
        self._steps: list[tuple[str, Callable[[], None]]] = []

    def push(self, what: str, step: Callable[[], None]) -> None:
        self._steps.append((what, step))

    def run(self) -> list[BaseException]:
        failures: list[BaseException] = []
        while self._steps:
            what, step = self._steps.pop()
            try:
                step()
            except BaseException as failure:
                failure.add_note(f"while {what}")
                failures.append(failure)
        return failures


def _raise(failures: Sequence[BaseException]) -> None:
    """Raise *failures* together: an interrupt first, with the rest noted on it;
    otherwise the one failure, or every one as a group."""
    if not failures:
        return
    interrupts = [failure for failure in failures if not isinstance(failure, Exception)]
    if interrupts:
        first = interrupts[0]
        for other in failures:
            if other is not first:
                first.add_note(f"also failed: {other!r}")
        raise first
    errors = [failure for failure in failures if isinstance(failure, Exception)]
    if len(errors) == 1:
        raise errors[0]
    raise ExceptionGroup("a cloud run failed, and so did its cleanup", errors)


def _single(session: DriverControl, sql: str, binds: Sequence[object]) -> object:
    ((value,),) = session.execute(sql, list(binds))
    return value


class AwsRun:
    """One run attempt's database on the deployed cluster, owned until :meth:`close`."""

    def __init__(
        self,
        environment: AwsTestEnvironment,
        identity: RunIdentity,
        ports: CloudPorts,
        pacing: CloudPacing,
    ) -> None:
        self.environment = environment
        self.identity = identity
        self._ports = ports
        self._pacing = pacing
        self._teardown = _Teardown()
        self._ledger = RuntimeLedger()
        self._sessions: dict[str, DriverControl] = {}
        self._administration: DriverControl | None = None

    @classmethod
    def open(cls, published: PublishedEnvironment, identity: RunIdentity) -> AwsRun:
        """The run, over the real environment *published* describes."""
        return cls.start(published.environment, identity, AwsPorts.open(published.environment))

    @classmethod
    def start(
        cls,
        environment: AwsTestEnvironment,
        identity: RunIdentity,
        ports: CloudPorts,
        pacing: CloudPacing | None = None,
    ) -> AwsRun:
        """The run over *ports*, which it owns from here whether or not it starts."""
        run = cls(environment, identity, ports, CloudPacing() if pacing is None else pacing)
        try:
            run._begin()
        except BaseException as failure:
            _raise([failure, *run._teardown.run()])
        return run

    def _begin(self) -> None:
        teardown = self._teardown
        teardown.push("releasing the fetched certificate bundle", self._ports.close)
        control = self._ports.session(self.environment.writer_host, CONTROL_DATABASE)
        teardown.push("closing the control session", control.close)
        control.execute_write(_RESET_ROLE, [])
        self._pacing.lock.wait_until(
            lambda: _single(control, _TRY_LOCK, [SUITE_LOCK]) is True, "the cloud suite lock"
        )
        teardown.push("releasing the cloud suite lock", lambda: self._unlock(control))
        for stale in self._stale(control):
            self._drop(control, stale)
        database = self.identity.database
        teardown.push(f"dropping {database}", lambda: self._drop(control, database))
        control.execute_write(f'create database "{database}"', [])
        administration = self._ports.session(self.environment.writer_host, database)
        teardown.push("closing the administration session", administration.close)
        administration.execute_write(_RESET_ROLE, [])
        self._administration = administration
        hosts = [self.environment.writer_host, self.environment.reader_host]
        for host in hosts + [instance.host for instance in self.environment.instances]:
            self._warm(host)
        teardown.push("closing every runtime the suite opened", self._ledger.release)

    def _stale(self, control: DriverControl) -> list[str]:
        """Every run database the login owns; under the lock, none is in use."""
        owned = [str(row[0]) for row in control.execute(_OWNED, [])]
        return [name for name in owned if _RUN_DATABASE.fullmatch(name)]

    def _drop(self, control: DriverControl, database: str) -> None:
        if not _RUN_DATABASE.fullmatch(database):
            raise CloudRunError(f"{database!r} is not a run database this suite may drop")
        control.execute_write(f'drop database if exists "{database}" with (force)', [])
        if _single(control, _PRESENT, [database]) != 0:
            raise CloudRunError(f"dropping {database} was not confirmed; it may have leaked")

    def _unlock(self, control: DriverControl) -> None:
        if _single(control, _UNLOCK, [SUITE_LOCK]) is not True:
            raise CloudRunError("the cloud suite lock was not held when it was released")

    def _warm(self, host: str) -> None:
        """Wait for *host* to accept and answer a session: a paused cluster resumes
        on the first connection attempt, readers only after the writer."""
        refused: list[Exception] = []

        def answered() -> bool:
            try:
                session = self._ports.session(host, self.identity.database)
            except Exception as failure:
                refused[:] = [failure]
                return False
            try:
                return _single(session, _ANSWER, []) == 1
            finally:
                session.close()

        try:
            self._pacing.warm.wait_until(answered, f"{host} to answer")
        except TimeoutError as timed_out:
            raise timed_out from (refused[0] if refused else None)

    def session(self, host: str) -> DriverControl:
        """An inspection session on *host* in this run's database, whose role is
        reset so it sees the login's other sessions in full. One per host, kept
        until the run closes."""
        held = self._sessions.get(host)
        if held is not None:
            return held
        session = self._ports.session(host, self.identity.database)
        self._teardown.push(f"closing the inspection session on {host}", session.close)
        session.execute_write(_RESET_ROLE, [])
        self._sessions[host] = session
        return session

    def adapter(
        self, *, pool: PoolOptions | OnDemandOptions | None = None, reader: bool = True
    ) -> TrackedAdapter:
        """The shipped adapter over this run's database: the writer endpoint and,
        unless *reader* is false, the reader endpoint, each signing for its own
        host. Every runtime it opens is released before the run's database goes."""
        from parallax.postgres import PoolOptions, PostgresAdapter

        retention = PoolOptions(min_size=0, num_workers=1) if pool is None else pool
        database = self.identity.database
        writer = self._ports.endpoint(
            self.environment.writer_host,
            database,
            application_name=WRITER_APPLICATION,
            pool=retention,
        )
        routed = (
            self._ports.endpoint(
                self.environment.reader_host,
                database,
                application_name=READER_APPLICATION,
                pool=retention,
            )
            if reader
            else None
        )
        return TrackedAdapter(
            PostgresAdapter(writer=writer, reader=routed, prepare_threshold=None), self._ledger
        )

    def authorization(self, selector: str) -> PostgresRole:
        return database_authorization(selector)

    def reset(self, model: Metamodel, fixtures: Mapping[str, object]) -> None:
        """Reset the run database's schema and fixtures on the writer, then wait
        until every instance lists the same tables."""
        if self._administration is None:
            raise CloudRunError("the run has not started")
        administration = self._administration
        reset_database(administration, model, fixtures)
        expected = _single(administration, _TABLES, [])
        for instance in self.environment.instances:
            inspected = self.session(instance.host)
            self.wait_until(
                lambda inspected=inspected: _single(inspected, _TABLES, []) == expected,
                f"{instance.identifier} to list the reset tables",
            )

    def wait_until(self, condition: Callable[[], bool], what: str) -> None:
        """Wait, within the visibility bound, for *condition* to hold."""
        self._pacing.visible.wait_until(condition, what)

    def release_case_runtimes(self) -> None:
        """Close every runtime a test composed and left open."""
        self._ledger.release()

    def close(self) -> None:
        """Release everything the run owns, in ownership order."""
        _raise(self._teardown.run())

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        failure: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        cleanup = self._teardown.run()
        if failure is not None and cleanup:
            _raise([failure, *cleanup])
        _raise(cleanup)


@contextmanager
def interrupted_on_termination() -> Generator[None]:
    """Deliver a termination request as an interrupt for the duration, so a
    cancelled run still releases what it owns before the process ends."""

    def interrupt(_signal: int, _frame: FrameType | None) -> None:
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, interrupt)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


class AwsPorts:
    """The real environment: sessions and endpoints signed per host with IAM
    tokens, over TLS verified against the certificate bundle the record names,
    fetched afresh for each run because the provider rotates it."""

    def __init__(self, environment: AwsTestEnvironment, directory: Path) -> None:
        import botocore.session

        self._environment = environment
        self._directory = directory
        self._bundle = directory / "ca-bundle.pem"
        self._session = botocore.session.get_session()

    @classmethod
    def open(cls, environment: AwsTestEnvironment) -> AwsPorts:
        import urllib.request

        if not environment.ca_bundle_url.startswith("https://"):
            raise CloudRunError("the certificate bundle is published over plain HTTP")
        directory = Path(tempfile.mkdtemp(prefix="parallax-ci-"))
        try:
            with urllib.request.urlopen(environment.ca_bundle_url, timeout=30) as response:
                bundle: bytes = response.read()
            if b"-----BEGIN CERTIFICATE-----" not in bundle:
                raise CloudRunError("the published certificate bundle holds no certificate")
            ports = cls(environment, directory)
            ports._bundle.write_bytes(bundle)
        except BaseException:
            shutil.rmtree(directory, ignore_errors=True)
            raise
        return ports

    def _params(self, application_name: str) -> dict[str, str]:
        return {
            "sslmode": "verify-full",
            "sslrootcert": str(self._bundle),
            "application_name": application_name,
            "connect_timeout": "10",
        }

    def session(self, host: str, database: str) -> DriverControl:
        from psycopg.conninfo import make_conninfo

        from parallax.aws import RdsIamCredentials
        from parallax.conformance._postgres_control import PostgresControl

        environment = self._environment
        token = RdsIamCredentials(
            host=host,
            port=environment.port,
            user=environment.login,
            region=environment.region,
            session=self._session,
        ).resolve()
        conninfo = make_conninfo(
            host=host,
            port=environment.port,
            user=environment.login,
            dbname=database,
            password=token.secret,
            **self._params("parallax-ci-inspection"),
        )
        return PostgresControl.open(conninfo, autocommit=True, prepare_threshold=None)

    def endpoint(
        self,
        host: str,
        database: str,
        *,
        application_name: str,
        pool: PoolOptions | OnDemandOptions,
    ) -> PostgresEndpoint:
        from parallax.aws.postgres import rds_endpoint

        environment = self._environment
        return rds_endpoint(
            host=host,
            user=environment.login,
            database=database,
            region=environment.region,
            port=environment.port,
            params=self._params(application_name),
            session=self._session,
            pool=pool,
        )

    def close(self) -> None:
        shutil.rmtree(self._directory)
