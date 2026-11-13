"""What the Aurora proofs share: the seeded run database, and where a backend
physically is, read off each instance rather than off Parallax's diagnostics."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from tests._support.aws_run import READER_APPLICATION, WRITER_APPLICATION, AwsRun
from tests._support.bindings import TEST_BINDING
from tests._support.routed_reads import SEEDED, SEEDED_MODEL, TABLES, seeded_fixtures

if TYPE_CHECKING:
    from parallax.conformance._database_control import DriverControl

APPLICATIONS: Final = {"writer": WRITER_APPLICATION, "reader": READER_APPLICATION}
"""The application name each route's sessions carry."""

_HOLDS = "select count(*) from pg_stat_activity where pid = ? and application_name = ?"
_ACTIVITY = "select pid, query_start from pg_stat_activity where application_name = ?"
# An open transaction rather than an assigned xid: a transaction's writes are
# buffered until it flushes, so it has written nothing yet while its body runs.
_IN_TRANSACTION = (
    "select count(*) from pg_stat_activity "
    "where application_name = ? and xact_start is not null and pid <> pg_backend_pid()"
)


def count(session: DriverControl, sql: str, binds: list[object]) -> int:
    """The single count *sql* answers on *session*."""
    ((value,),) = session.execute(sql, binds)
    assert isinstance(value, int)
    return value


def _seeded_on(session: DriverControl) -> bool:
    return all(
        count(session, f"select count(*) from px.{table}", []) == len(SEEDED) for table in TABLES
    )


def seeded(run: AwsRun) -> None:
    """The run database reset to the seeded rows, visible on every instance."""
    run.reset(SEEDED_MODEL, seeded_fixtures(), TEST_BINDING)
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


def activity(run: AwsRun, route: str) -> set[tuple[str, object, object]]:
    """Every backend carrying *route*'s application name: the instance it runs
    on, its process, and when it last began a statement. A backend that has run
    anything since an earlier reading differs from its entry there; an idle one
    does not."""
    return {
        (instance.identifier, pid, started)
        for instance in run.environment.instances
        for (pid, started) in run.session(instance.host).execute(_ACTIVITY, [APPLICATIONS[route]])
    }


def in_transaction(run: AwsRun, route: str) -> set[str]:
    """Every instance on which a backend of *route*'s application holds an open
    transaction."""
    return {
        instance.identifier
        for instance in run.environment.instances
        if count(run.session(instance.host), _IN_TRANSACTION, [APPLICATIONS[route]])
    }


def instances(run: AwsRun, role: str) -> set[str]:
    """The instances the published record says play *role*."""
    return {instance.identifier for instance in run.environment.instances if instance.role == role}
