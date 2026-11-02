"""Routed execution against a real streaming standby.

The shipped adapter's writer is the primary and its reader the standby, so the
servers themselves say where each lease landed: the standby is in recovery,
refuses writes and Serializable natively, and — while its replay is paused —
lacks a row the primary has committed. Every claim here is read off the
servers, never off Parallax's own route diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from parallax.core.db_error import DatabaseError
from parallax.core.db_port import BeginFailed, Committed, DatabaseConnection, RoutePolicy
from parallax.postgres import PostgresRole
from parallax.snapshot import ReadOnlyTxnContext, connect
from tests._support.root_ownership import own_root
from tests.provider_contract.replication._replication_support import (
    LAYOUTS,
    MODEL,
    READS,
    SEEDED,
    Folio,
    Ledger,
    everything,
    insert,
    replicated,
)

pytestmark = pytest.mark.xdist_group("replication")

_WHERE = "select pg_is_in_recovery(), session_user, current_user"


def _where(runtime: Any, policy: RoutePolicy, role: Any = None) -> tuple[object, ...]:
    source = runtime.login_source() if role is None else runtime.principal_source(role)
    with source.new_context(policy) as connection:
        (row,) = connection.execute(_WHERE, [])
    return row


def test_each_route_lands_on_its_own_server_under_the_same_login(profile_run: Any) -> None:
    pair = replicated(profile_run)
    runtime = pair.adapter().open()
    role = pair.authorization("role-a")
    try:
        writer = _where(runtime, "writer_only")
        reader = _where(runtime, "reader_only")
        preferred = _where(runtime, "reader_preferred")
        principal = _where(runtime, "reader_only", role)
    finally:
        runtime.close()

    login = pair.login_identity
    assert profile_run.replication() is pair
    assert writer == (False, login, "parallax_conformance_default")
    assert reader == (True, login, "parallax_conformance_default")
    assert preferred == reader
    assert principal == (True, login, role.name)


def _isolation(connection: DatabaseConnection) -> object:
    ((level,),) = connection.execute("select current_setting('transaction_isolation')", [])
    return level


def test_the_standby_refuses_writes_and_serializable_natively(profile_run: Any) -> None:
    pair = replicated(profile_run)
    runtime = pair.adapter().open()
    reader = runtime.login_source()
    try:
        with reader.new_context("reader_only") as connection, pytest.raises(DatabaseError) as write:
            connection.execute_write(
                "insert into rv_ledger (id, memo) values (%s, %s)", [9, "refused"]
            )
        with reader.new_context("reader_only") as connection:
            serializable = connection.transaction(
                _isolation, isolation="serializable", access_mode="read_only"
            )
        with reader.new_context("reader_only") as connection:
            repeatable = connection.transaction(
                _isolation, isolation="repeatable_read", access_mode="read_only"
            )
    finally:
        runtime.close()

    assert write.value.native_code == "25006"
    assert isinstance(serializable, BeginFailed)
    assert isinstance(serializable.error, DatabaseError)
    assert serializable.error.native_code == "0A000"
    assert repeatable == Committed("repeatable read")


def test_a_committed_write_is_already_applied_on_the_standby(profile_run: Any) -> None:
    pair = replicated(profile_run)
    db = own_root(connect(pair.adapter(), MODEL)).using_database_login()

    for entity in LAYOUTS.values():
        insert(db, entity, 3)

    for read in READS.values():
        for entity in LAYOUTS.values():
            assert read(db, entity) == [*SEEDED, 3]


@pytest.mark.parametrize("layout", list(LAYOUTS))
@pytest.mark.parametrize("shape", list(READS))
def test_each_read_shape_follows_its_scopes_policy_to_its_server(
    profile_run: Any, shape: str, layout: str
) -> None:
    pair = replicated(profile_run)
    read, entity = READS[shape], LAYOUTS[layout]
    db = own_root(connect(pair.adapter(synchronous_commit="local"), MODEL)).using_database_login()

    with pair.paused_replay():
        insert(db, entity, 3)
        lsn = pair.writer_lsn()
        on_reader = read(db, entity)
        on_preferred = read(db.with_routing(read_policy="reader_preferred"), entity)
        on_writer = read(db.with_routing(read_policy="writer_only"), entity)
    pair.wait_replayed(lsn)

    assert on_reader == on_preferred == SEEDED
    assert on_writer == [*SEEDED, 3]
    assert read(db, entity) == [*SEEDED, 3]


def _found(tx: ReadOnlyTxnContext) -> list[int]:
    return [ledger.id for ledger in tx.find(everything(Ledger)).results()]


def test_transactions_reach_the_server_their_routing_and_isolation_select(
    profile_run: Any,
) -> None:
    pair = replicated(profile_run)
    db = own_root(connect(pair.adapter(synchronous_commit="local"), MODEL)).using_database_login()
    preferred = db.with_routing(read_policy="reader_preferred")

    with pair.paused_replay():
        # A writable transaction from a reader-defaulted scope writes on the
        # primary and reads its own write there.
        db.transact(lambda tx: tx.insert(Ledger(id=3, memo="added-3")))
        written = db.transact(
            lambda tx: [ledger.id for ledger in tx.find(everything(Ledger)).results()]
        )
        lsn = pair.writer_lsn()
        reader_repeatable = db.read_only(_found, isolation="repeatable_read")
        preferred_repeatable = preferred.read_only(_found, isolation="repeatable_read")
        # The standby cannot begin Serializable, so a preferred read resolves to
        # the primary and a strict one is refused before it acquires anything.
        preferred_serializable = preferred.read_only(_found, isolation="serializable")
        with pytest.raises(ValueError, match="writer_only"):
            db.read_only(_found, isolation="serializable")
    pair.wait_replayed(lsn)

    assert written == [*SEEDED, 3]
    assert reader_repeatable == preferred_repeatable == SEEDED
    assert preferred_serializable == [*SEEDED, 3]


def test_a_principal_reads_through_the_standby_under_its_own_authorization(
    profile_run: Any,
) -> None:
    pair = replicated(profile_run)
    root = own_root(connect(pair.adapter(synchronous_commit="local"), MODEL))
    principal = root.using_principal(_Principal("replication", pair.authorization("role-b")))

    with pair.paused_replay():
        insert(root.using_database_login(), Folio, 3)
        lsn = pair.writer_lsn()
        on_reader = READS["typed-eager"](principal, Folio)
        on_writer = READS["typed-eager"](principal.with_routing(read_policy="writer_only"), Folio)
    pair.wait_replayed(lsn)

    assert on_reader == SEEDED
    assert on_writer == [*SEEDED, 3]


@dataclass(frozen=True, slots=True)
class _Principal:
    subject: str
    database_authorization: PostgresRole
