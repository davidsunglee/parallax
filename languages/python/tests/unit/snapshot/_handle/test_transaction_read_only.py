"""`ScopedDatabase.read_only` and `ReadOnlyTxnContext` (Docker-free fake ports).

The runner's own read-only semantics — the access mode it asks for, join
admission, option resolution, and the lifetime — are graded over the neutral
scope in ``tests/unit/core/_execution/_transaction/test_runner.py``. What stays
here is the Snapshot surface a callback is handed: reads only, Typed and Wire,
none of them locking, inspection of the edition and the resolved options, and a
live stream that cannot outlive its attempt.
"""

from __future__ import annotations

import contextlib
import inspect
from typing import cast

import pytest

from parallax.conformance.scripted_clock import FixedClock
from parallax.core._execution._unit_work.uow import EscapedTransactionError
from parallax.core.entity._authored_resolver import object_query_node
from parallax.core.execution import ReadOnlyTxnOptions, TxnOptions
from parallax.core.unit_work import RollbackOnlyError
from parallax.snapshot import (
    ReadOnlyTxnContext,
    ScopedDatabase,
    SnapshotStream,
    TxnContext,
    WireDatabaseView,
    WireTransactionView,
    connect,
)
from tests._support import mirrored_models as mm
from tests._support.adoption import raises_contextualized
from tests._support.db_port import BeginCall, CommitCall, Read, ReadCall, ScriptedAdapter, Transact
from tests._support.root_ownership import own_root
from tests.unit._transact_support import (
    ACCOUNT,
    FIND_SQL_UNLOCKED,
    FIXED,
    NEW_ROW,
    account_db,
)

_QUERY = mm.Account.where(mm.Account.id == 7)


def _locking_db(port: ScriptedAdapter) -> ScopedDatabase:
    return own_root(
        connect(port, ACCOUNT, options=TxnOptions(concurrency="locking"), clock=FixedClock(FIXED))
    ).using_database_login()


def test_read_only_takes_the_retry_bound_and_isolation_and_no_concurrency() -> None:
    signature = inspect.signature(ScopedDatabase.read_only)
    keywords = [name for name in signature.parameters if name not in ("self", "fn")]
    assert keywords == ["max_retries", "isolation"]
    assert all(
        signature.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY for name in keywords
    )


def test_the_read_only_context_reads_and_names_no_write_verb() -> None:
    writes = {
        "insert",
        "amend",
        "amend_if",
        "replace",
        "replace_if",
        "delete",
        "terminate",
        "amend_where",
        "delete_where",
    }
    assert writes <= set(dir(TxnContext))
    assert not writes & set(dir(ReadOnlyTxnContext))
    assert {"find", "stream", "read_rows", "wire", "edition", "options"} <= set(
        dir(ReadOnlyTxnContext)
    )


def test_typed_and_wire_reads_share_one_read_only_boundary_and_take_no_lock() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[NEW_ROW]), Read(rows=[NEW_ROW])))
    db = _locking_db(port)

    def read(rtx: ReadOnlyTxnContext) -> tuple[str, object]:
        return rtx.find(_QUERY).result().owner, rtx.wire.find(_QUERY).result()["owner"]

    assert db.read_only(read) == ("Newton", "Newton")
    assert port.calls == [
        BeginCall("read_committed", "read_only"),
        ReadCall(FIND_SQL_UNLOCKED, (7,)),
        ReadCall(FIND_SQL_UNLOCKED, (7,)),
        CommitCall(),
    ]


def test_the_read_only_wire_view_is_the_read_interface_and_not_the_writable_one() -> None:
    port = ScriptedAdapter(Transact())
    view = account_db(port).read_only(lambda rtx: rtx.wire)
    assert type(view) is WireDatabaseView
    assert not isinstance(view, WireTransactionView)


def test_the_context_states_its_edition_and_its_resolved_options() -> None:
    port = ScriptedAdapter(Transact())
    db = _locking_db(port)
    edition, options = db.read_only(
        lambda rtx: (rtx.edition, rtx.options), isolation="serializable"
    )
    assert edition
    assert options == ReadOnlyTxnOptions(max_retries=10, isolation="serializable")
    assert port.calls[0] == BeginCall("serializable", "read_only")


def test_row_form_reads_run_inside_the_read_only_boundary() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[NEW_ROW])))
    db = account_db(port)
    rows = db.read_only(lambda rtx: rtx.read_rows(object_query_node(_QUERY, ACCOUNT)).rows)
    assert rows == (NEW_ROW,)
    assert port.calls[0] == BeginCall("read_committed", "read_only")


def test_a_stream_that_escapes_its_read_only_attempt_reads_no_page() -> None:
    port = ScriptedAdapter(Transact())
    escaped = account_db(port).read_only(lambda rtx: rtx.stream(_QUERY, batch_size=10))
    assert isinstance(escaped, SnapshotStream)
    with pytest.raises(EscapedTransactionError), escaped as stream:
        next(iter(stream))
    assert [type(call) for call in port.calls] == [BeginCall, CommitCall]


def test_a_failed_read_only_join_refuses_the_commit() -> None:
    port = ScriptedAdapter(Transact())
    db = account_db(port)

    def outer(_rtx: ReadOnlyTxnContext) -> str:
        with contextlib.suppress(RuntimeError):
            db.read_only(lambda _joined: cast("str", _raise()))
        return "withheld"

    with raises_contextualized(RollbackOnlyError):
        db.read_only(outer)


def _raise() -> object:
    raise RuntimeError("joined failure")
