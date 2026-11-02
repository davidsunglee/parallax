"""What the Aurora proofs share: the seeded run database, and where a backend
physically is, read off each instance rather than off Parallax's diagnostics."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from tests._support.aws_run import READER_APPLICATION, WRITER_APPLICATION, AwsRun
from tests._support.routed_reads import SEEDED, SEEDED_MODEL, TABLES, seeded_fixtures

if TYPE_CHECKING:
    from parallax.conformance._database_control import DriverControl

APPLICATIONS: Final = {"writer": WRITER_APPLICATION, "reader": READER_APPLICATION}
"""The application name each route's sessions carry."""

_HOLDS = "select count(*) from pg_stat_activity where pid = %s and application_name = %s"
_BACKENDS = "select pid from pg_stat_activity where application_name = %s"
_WRITING = (
    "select count(*) from pg_stat_activity "
    "where application_name = %s and backend_xid is not null and pid <> pg_backend_pid()"
)


def count(session: DriverControl, sql: str, binds: list[object]) -> int:
    """The single count *sql* answers on *session*."""
    ((value,),) = session.execute(sql, binds)
    assert isinstance(value, int)
    return value


def _seeded_on(session: DriverControl) -> bool:
    return all(
        count(session, f"select count(*) from {table}", []) == len(SEEDED) for table in TABLES
    )


def seeded(run: AwsRun) -> None:
    """The run database reset to the seeded rows, visible on every instance."""
    run.reset(SEEDED_MODEL, seeded_fixtures())
    for instance in run.environment.instances:
        session = run.session(instance.host)
        run.wait_until(
            lambda session=session: _seeded_on(session),
            f"{instance.identifier} to see the seeded rows",
        )


def holding(run: AwsRun, pid: object, route: str) -> set[str]:
    """Every instance on which a backend *pid* carrying *route*'s application name
    is running."""
    return {
        instance.identifier
        for instance in run.environment.instances
        if count(run.session(instance.host), _HOLDS, [pid, APPLICATIONS[route]])
    }


def backends(run: AwsRun, route: str) -> set[tuple[str, object]]:
    """Every backend carrying *route*'s application name, with the instance it
    runs on."""
    return {
        (instance.identifier, pid)
        for instance in run.environment.instances
        for (pid,) in run.session(instance.host).execute(_BACKENDS, [APPLICATIONS[route]])
    }


def writing(run: AwsRun, route: str) -> set[str]:
    """Every instance on which a backend of *route*'s application holds a
    transaction that has written."""
    return {
        instance.identifier
        for instance in run.environment.instances
        if count(run.session(instance.host), _WRITING, [APPLICATIONS[route]])
    }


def instances(run: AwsRun, role: str) -> set[str]:
    """The instances the published record says play *role*."""
    return {instance.identifier for instance in run.environment.instances if instance.role == role}
