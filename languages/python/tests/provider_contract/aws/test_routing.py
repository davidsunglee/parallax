"""Routed execution on the deployed Aurora cluster.

Where a lease landed is established by each instance's own ``pg_stat_activity``
— the backend the lease runs on, found by its process and its route's
application name through a separate session on every instance — and Parallax's
reported selection only corroborates it. The native refusals are the cluster's
own.
"""

from __future__ import annotations

from typing import Any

import pytest

from parallax.core.db_error import DatabaseError
from parallax.core.db_port import BeginFailed, Committed, DatabaseConnection, RoutePolicy
from parallax.snapshot import TxnContext, connect
from tests._support.root_ownership import own_root
from tests._support.routed_reads import LAYOUTS, MODEL, READS, SEEDED, Ledger
from tests.provider_contract.aws._aws_support import (
    backends,
    holding,
    instances,
    seeded,
    writing,
)

_PID = "select pg_backend_pid()"


@pytest.mark.parametrize(
    ("policy", "route"),
    [("writer_only", "writer"), ("reader_only", "reader"), ("reader_preferred", "reader")],
)
def test_a_lease_runs_on_the_instance_its_route_names(
    aws_run: Any, policy: RoutePolicy, route: str
) -> None:
    seeded(aws_run)
    runtime = aws_run.adapter().open()
    try:
        context = runtime.login_source().new_context(policy)
        with context as connection:
            ((pid,),) = connection.execute(_PID, [])
            placed = holding(aws_run, pid, route)
        selection = context.selection
    finally:
        runtime.close()

    assert placed == instances(aws_run, route)
    assert selection is not None
    assert selection.route == route


def test_a_writable_transaction_from_a_reader_defaulted_scope_runs_on_the_writer(
    aws_run: Any,
) -> None:
    seeded(aws_run)
    db = own_root(connect(aws_run.adapter(), MODEL)).using_database_login()
    placed: list[set[str]] = []

    def body(tx: TxnContext) -> None:
        tx.insert(Ledger(id=3, memo="added-3"))
        placed.append(writing(aws_run, "writer"))
        placed.append(writing(aws_run, "reader"))

    db.transact(body)

    assert placed == [instances(aws_run, "writer"), set()]
    aws_run.wait_until(
        lambda: READS["rows"](db, Ledger) == [*SEEDED, 3], "the reader to see the committed row"
    )


def _isolation(connection: DatabaseConnection) -> object:
    ((level,),) = connection.execute("select current_setting('transaction_isolation')", [])
    return level


def _write(connection: DatabaseConnection) -> object:
    return connection.execute_write("insert into rv_ledger (id, memo) values (9, 'refused')", [])


@pytest.mark.parametrize("policy", ["writer_only", "reader_only"])
def test_a_write_inside_a_read_only_transaction_is_refused_natively_on_either_route(
    aws_run: Any, policy: RoutePolicy
) -> None:
    seeded(aws_run)
    runtime = aws_run.adapter().open()
    try:
        with runtime.login_source().new_context(policy) as connection:
            refused = connection.transaction(_write, access_mode="read_only")
    finally:
        runtime.close()

    assert not isinstance(refused, Committed)
    failure = getattr(refused, "error", None)
    assert isinstance(failure, DatabaseError)
    assert failure.native_code == "25006"


def test_the_reader_refuses_serializable_and_serves_repeatable_read(aws_run: Any) -> None:
    seeded(aws_run)
    runtime = aws_run.adapter().open()
    try:
        with runtime.login_source().new_context("reader_only") as connection:
            serializable = connection.transaction(
                _isolation, isolation="serializable", access_mode="read_only"
            )
        with runtime.login_source().new_context("reader_only") as connection:
            repeatable = connection.transaction(
                _isolation, isolation="repeatable_read", access_mode="read_only"
            )
    finally:
        runtime.close()

    assert isinstance(serializable, BeginFailed)
    assert isinstance(serializable.error, DatabaseError)
    assert serializable.error.native_code == "0A000"
    assert repeatable == Committed("repeatable read")


@pytest.mark.parametrize(
    ("policy", "route"),
    [("writer_only", "writer"), ("reader_only", "reader"), ("reader_preferred", "reader")],
)
@pytest.mark.parametrize("layout", list(LAYOUTS))
@pytest.mark.parametrize("shape", list(READS))
def test_every_read_shape_and_layout_reads_from_the_instances_its_scopes_policy_names(
    aws_run: Any, shape: str, layout: str, policy: RoutePolicy, route: str
) -> None:
    seeded(aws_run)
    before = {name: backends(aws_run, name) for name in ("writer", "reader")}
    db = own_root(connect(aws_run.adapter(), MODEL, read_policy=policy)).using_database_login()

    assert READS[shape](db, LAYOUTS[layout]) == SEEDED
    opened = {name: backends(aws_run, name) - before[name] for name in before}
    assert opened[route]
    assert {identifier for identifier, _pid in opened[route]} <= instances(aws_run, route)
    if route == "writer":
        assert opened["reader"] == set()
