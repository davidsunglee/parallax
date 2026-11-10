"""A primary and its synchronous streaming standby, for proofs a real replica owes.

What a reader route observes about the writer's changes is a property of
physical replication, so it is proved against a standby the primary actually
streams to rather than inferred from routing diagnostics. The standby replays
synchronously, and the shipped adapter's writer sessions default to
``remote_apply``: a committed write is already applied on the standby, so an
ordinary proof reads its own writes back through the reader without waiting.
A lag proof instead commits ``local`` while replay is paused, and resumes and
waits on log positions afterwards.

Pausing replay blocks every ``remote_apply`` commit until it resumes, which is
why the pause is a context that always resumes, a pair that cannot resume closes
itself rather than serve a later proof, and every wait here is a bounded poll of
a server condition rather than a sleep.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Generator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal, Protocol

from parallax.conformance.provision import (
    CONFORMANCE_LOGIN,
    RuntimeLedger,
    TrackedAdapter,
    conformance_credentials,
    database_authorization,
    install_authority_fixtures,
    reset_database,
)

if TYPE_CHECKING:
    from testcontainers.core.container import DockerContainer

    from parallax.conformance._database_control import DriverControl
    from parallax.core.internal.db_port import Password
    from parallax.core.internal.metamodel import Metamodel
    from parallax.postgres import PostgresEndpoint, PostgresRole

__all__ = ["LazyReplication", "Pacing", "ReplicationLaunch", "ReplicationPair", "Server"]

type SynchronousCommit = Literal["remote_apply", "local"]

_PRIMARY_ALIAS: Final[str] = "primary"
"""The primary's name on the pair's own network, where the standby reaches it."""

_STANDBY_NAME: Final[str] = "standby"
"""The name the standby streams under, and the one the primary waits for."""

_REPLICATION_LOGIN: Final[str] = "parallax_replication"
_REPLICATION_PASSWORD: Final[str] = "parallax-replication-password"

_STREAMING = (
    "select count(*) from pg_stat_replication where application_name = %s and state = 'streaming'"
)
_SYNCHRONOUS = (
    "select count(*) from pg_stat_replication where application_name = %s and sync_state = 'sync'"
)
_PAUSE_STATE = "select pg_get_wal_replay_pause_state()"
_WRITER_LSN = "select pg_current_wal_lsn()::text"
_REPLAYED = "select coalesce(pg_last_wal_replay_lsn() >= %s::pg_lsn, false)"


@dataclass(frozen=True, slots=True)
class Server:
    """One started server of the pair, as connection strings reachable from here.

    ``administration`` authenticates the server's superuser and carries its
    secret; ``login`` names the conformance login and carries none, because the
    adapter takes that secret beside it.
    """

    administration: str
    login: str


class ReplicationLaunch(Protocol):
    """Where the pair's network and servers come from.

    Each step registers its own release on ``resources`` before it can fail, so
    whatever a step managed to start is released however the opening ends.
    """

    def network(self, resources: ExitStack) -> object: ...

    def primary(self, resources: ExitStack, network: object, replication_login: str) -> Server:
        """Start the primary on ``network``, admitting ``replication_login`` to
        stream from it once its configuration is reloaded."""
        ...

    def standby(self, resources: ExitStack, network: object, source: str) -> Server:
        """Start a hot standby on ``network`` from a base backup of ``source``."""
        ...

    def session(self, conninfo: str) -> DriverControl: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class Pacing:
    """How long the pair waits for a server condition, and how it polls for it."""

    within: float = 60.0
    interval: float = 0.02
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep

    def wait_until(self, condition: Callable[[], bool], what: str) -> None:
        deadline = self.clock() + self.within
        while not condition():
            if self.clock() >= deadline:
                raise TimeoutError(f"waited {self.within:g} s for {what}")
            self.sleep(self.interval)


class ReplicationPair:
    """A primary and its synchronous standby, owned until :meth:`close`.

    Its adapters route writes to the primary and reads to the standby through
    the shipped configuration, and every runtime they open is released before
    the servers stop.
    """

    def __init__(
        self,
        *,
        primary: DriverControl,
        standby: DriverControl,
        servers: tuple[Server, Server],
        resources: ExitStack,
        pacing: Pacing,
    ) -> None:
        self._primary = primary
        self._standby = standby
        self._servers = servers
        self._resources = resources
        self._pacing = pacing
        self._ledger = RuntimeLedger()
        self._closed = False

    @classmethod
    def open(
        cls, launch: ReplicationLaunch | None = None, *, pacing: Pacing | None = None
    ) -> ReplicationPair:
        """Start the pair and wait until the standby replays synchronously.

        The standby is brought up and seen streaming before the primary is made
        to wait for it: a primary waiting on a standby that does not exist yet
        would block its own setup. Anything already started is released, in
        reverse, if any step fails.
        """
        launched = launch if launch is not None else _Testcontainers()
        paced = pacing if pacing is not None else Pacing()
        with ExitStack() as resources:
            network = launched.network(resources)
            primary = launched.primary(resources, network, _REPLICATION_LOGIN)
            primary_session = launched.session(primary.administration)
            resources.callback(primary_session.close)
            install_authority_fixtures(primary_session)
            primary_session.execute_write(
                f'create role "{_REPLICATION_LOGIN}" replication login '
                f"password '{_REPLICATION_PASSWORD}'",
                [],
            )
            primary_session.execute("select pg_reload_conf()", [])
            standby = launched.standby(resources, network, _replication_source())
            standby_session = launched.session(standby.administration)
            resources.callback(standby_session.close)
            pair = cls(
                primary=primary_session,
                standby=standby_session,
                servers=(primary, standby),
                resources=resources.pop_all(),
                pacing=paced,
            )
        try:
            pair._synchronize()
        except BaseException:
            pair.close()
            raise
        return pair

    def _synchronize(self) -> None:
        self._pacing.wait_until(
            lambda: self._count(self._primary, _STREAMING) == 1, "the standby to stream"
        )
        self._primary.execute_write(
            f"alter system set synchronous_standby_names = '{_STANDBY_NAME}'", []
        )
        self._primary.execute("select pg_reload_conf()", [])
        self._pacing.wait_until(
            lambda: self._count(self._primary, _SYNCHRONOUS) == 1,
            "the standby to replay synchronously",
        )

    @staticmethod
    def _count(session: DriverControl, sql: str) -> object:
        ((count,),) = session.execute(sql, [_STANDBY_NAME])
        return count

    @property
    def login_identity(self) -> str:
        return CONFORMANCE_LOGIN

    @property
    def credentials(self) -> Password:
        return conformance_credentials()

    def authorization(self, selector: str) -> PostgresRole:
        return database_authorization(selector)

    def adapter(self, *, synchronous_commit: SynchronousCommit = "remote_apply") -> TrackedAdapter:
        """The shipped adapter with the primary as its writer and the standby as
        its reader, its writer sessions committing under ``synchronous_commit``.
        """
        from parallax.postgres import PostgresAdapter

        primary, standby = self._servers
        return TrackedAdapter(
            PostgresAdapter(
                writer=self._endpoint(
                    primary, options=f"-c synchronous_commit={synchronous_commit}"
                ),
                reader=self._endpoint(standby),
                prepare_threshold=None,
            ),
            self._ledger,
        )

    def _endpoint(self, server: Server, **connection: str) -> PostgresEndpoint:
        """One route over ``server``, retaining as leanly as the ordinary lane does."""
        from psycopg.conninfo import make_conninfo

        from parallax.postgres import PoolOptions, PostgresEndpoint

        return PostgresEndpoint(
            make_conninfo(server.login, **connection),
            credentials=self.credentials,
            pool=PoolOptions(min_size=0, num_workers=1),
        )

    def reset(self, model: Metamodel, fixtures: Mapping[str, object]) -> None:
        """Reset the primary's schema and fixtures, and wait for the standby to apply them."""
        reset_database(self._primary, model, fixtures)
        self.wait_replayed(self.writer_lsn())

    def writer_lsn(self) -> str:
        """The primary's current log position."""
        ((position,),) = self._primary.execute(_WRITER_LSN, [])
        return str(position)

    def wait_replayed(self, lsn: str) -> None:
        """Wait until the standby has replayed through ``lsn``."""
        self._pacing.wait_until(
            lambda: self._standby.execute(_REPLAYED, [lsn]) == [(True,)],
            f"the standby to replay through {lsn}",
        )

    @contextmanager
    def paused_replay(self) -> Generator[None]:
        """Pause the standby's replay for the body, and resume it however the body ends.

        The standby keeps receiving the log while paused; what it stops doing is
        applying it, so its sessions keep seeing what was replayed before. A
        resume that fails closes the pair, since it may still be paused.
        """
        try:
            self._standby.execute("select pg_wal_replay_pause()", [])
            self._pacing.wait_until(
                lambda: self._standby.execute(_PAUSE_STATE, []) == [("paused",)],
                "the standby's replay to pause",
            )
            yield
        finally:
            try:
                self._standby.execute("select pg_wal_replay_resume()", [])
            except BaseException:
                self.close()
                raise

    def release_runtimes(self) -> int:
        """Close every runtime this pair's adapters opened and a caller left open,
        and answer how many there were."""
        return self._ledger.release()

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        """Release every runtime, then the sessions, servers and network, newest first."""
        self._closed = True
        try:
            self._ledger.release()
        finally:
            self._resources.close()


def _replication_source() -> str:
    """How the standby reaches the primary to take its backup and then stream from it.

    The connection string carries the name the standby streams under: the base
    backup records it as the standby's own, which is what the primary's
    synchronous standby list names.
    """
    from psycopg.conninfo import make_conninfo

    return make_conninfo(
        host=_PRIMARY_ALIAS,
        port=5432,
        user=_REPLICATION_LOGIN,
        password=_REPLICATION_PASSWORD,
        application_name=_STANDBY_NAME,
    )


class LazyReplication[Pair: _Owned]:
    """The one pair a run opens on first use, released with the run.

    A pair that closed itself is replaced on the next use.
    """

    __slots__ = ("_closed", "_open", "_pair")

    def __init__(self, open_pair: Callable[[], Pair]) -> None:
        self._open = open_pair
        self._pair: Pair | None = None
        self._closed = False

    def pair(self) -> Pair:
        if self._closed:
            raise RuntimeError("the run owning this replication pair has closed")
        if self._pair is None or self._pair.closed:
            self._pair = self._open()
        return self._pair

    def release_runtimes(self) -> int:
        return 0 if self._pair is None else self._pair.release_runtimes()

    def close(self) -> None:
        self._closed = True
        pair, self._pair = self._pair, None
        if pair is not None:
            pair.close()


class _Owned(Protocol):
    @property
    def closed(self) -> bool: ...

    def release_runtimes(self) -> int: ...

    def close(self) -> None: ...


# The standby is a base backup of the primary, so the superuser and database
# the primary initializes are the standby's too.
_SUPERUSER: Final[str] = "parallax_replication_admin"
_SUPERUSER_PASSWORD: Final[str] = "parallax-replication-admin-password"
_DATABASE: Final[str] = "parallax_replication"


class _Testcontainers:  # pragma: no cover - exercised by the Docker-backed lanes
    """The pair as Testcontainers servers of the ordinary lane's pinned image."""

    def network(self, resources: ExitStack) -> object:
        from testcontainers.core.network import Network

        network = Network()
        network.create()
        resources.callback(network.remove)
        return network

    def primary(self, resources: ExitStack, network: object, replication_login: str) -> Server:
        from testcontainers.community.postgres import PostgresContainer
        from testcontainers.core.network import Network

        from parallax.conformance import constants

        assert isinstance(network, Network)
        container = (
            PostgresContainer(
                constants.POSTGRES_IMAGE,
                username=_SUPERUSER,
                password=_SUPERUSER_PASSWORD,
                dbname=_DATABASE,
                driver=None,
            )
            .with_network(network)
            .with_network_aliases(_PRIMARY_ALIAS)
        )
        resources.callback(container.stop)
        container.start()
        admitted = container.exec(
            [
                "sh",
                "-c",
                f'echo "host replication {replication_login} all scram-sha-256"'
                ' >> "$PGDATA/pg_hba.conf"',
            ]
        )
        if admitted.exit_code != 0:
            raise RuntimeError("the primary refused its replication login's admission")
        return _server(container)

    def standby(self, resources: ExitStack, network: object, source: str) -> Server:
        from testcontainers.core.container import DockerContainer
        from testcontainers.core.network import Network
        from testcontainers.core.wait_strategies import ExecWaitStrategy

        from parallax.conformance import constants

        assert isinstance(network, Network)
        container = (
            DockerContainer(
                constants.POSTGRES_IMAGE,
                user="postgres",
                entrypoint=[
                    "sh",
                    "-c",
                    'pg_basebackup -d "$PARALLAX_REPLICATION_SOURCE" -D "$PGDATA" -R -X stream'
                    " && exec postgres -c hot_standby_feedback=on",
                ],
            )
            .with_env("PARALLAX_REPLICATION_SOURCE", source)
            .with_exposed_ports(5432)
            .with_network(network)
            .waiting_for(
                ExecWaitStrategy(
                    ["pg_isready", "-h", "127.0.0.1", "-U", _SUPERUSER, "-d", _DATABASE]
                ).with_startup_timeout(60)
            )
        )
        resources.callback(container.stop)
        container.start()
        return _server(container)

    def session(self, conninfo: str) -> DriverControl:
        from parallax.conformance._postgres_control import PostgresControl

        return PostgresControl.open(conninfo, autocommit=True, prepare_threshold=None)


def _server(container: DockerContainer) -> Server:  # pragma: no cover - Docker
    from psycopg.conninfo import make_conninfo

    host = container.get_container_host_ip()
    port = container.get_exposed_port(5432)
    return Server(
        administration=make_conninfo(
            host=host, port=port, dbname=_DATABASE, user=_SUPERUSER, password=_SUPERUSER_PASSWORD
        ),
        login=make_conninfo(host=host, port=port, dbname=_DATABASE, user=CONFORMANCE_LOGIN),
    )
