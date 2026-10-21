"""The Usage Guide's target write stories, over a fake port.

Each story is documentation that runs: its source IS the guide's snippet, and
`tests/api/test_target_write_stories.py` executes it against real Postgres. This
is the database-free half — the same calls over a scripted port — so a snippet
that stopped compiling, a deletion that stopped stating its reviewed version,
or an unversioned write that stopped reading under the shared lock fails on the
first run of the fast suite.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from parallax.conformance.class_models import MODELS
from parallax.conformance.target_write_stories import (
    ClosingReport,
    an_unversioned_wallet_is_written_through_a_read_of_the_writing_transaction,
    reviewed_accounts_are_deleted_under_the_versions_their_review_saw,
    reviewed_deletion_snippet,
    unversioned_write_snippet,
)
from parallax.core.db_error import DatabaseError
from parallax.core.execution import ExecutionFailure
from tests._support.db_port import (
    BeginCall,
    Read,
    ReadCall,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
)

_LINUS = {"id": 2, "owner": "Linus", "balance": Decimal("250.00"), "version": 1}
_GRACE = {"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}
_ADA = {"id": 1, "owner": "Ada", "balance": Decimal("100.00"), "version": 1}


def test_the_reviewed_deletions_state_the_versions_the_review_saw() -> None:
    port = ScriptedAdapter(
        Transact(Read(rows=[_LINUS, _GRACE])),
        Transact(Read(rows=[_LINUS]), Write()),
        Transact(Write(affected=0)),
        Transact(Write()),
        Read(rows=[_ADA, {**_LINUS, "version": 2}]),
    )
    report = reviewed_accounts_are_deleted_under_the_versions_their_review_saw(
        port, MODELS["account"]
    )
    assert report == ClosingReport(closed=(3,), refused=(2,), remaining=(1, 2))
    assert [call.access_mode for call in port.calls if isinstance(call, BeginCall)] == [
        "read_only",
        "read_write",
        "read_write",
        "read_write",
    ]
    deletions = [
        call for call in port.calls if isinstance(call, WriteCall) and call.sql.startswith("delete")
    ]
    assert [(call.sql, call.binds) for call in deletions] == [
        ("delete from account where id = %s and version = %s", (2, 1)),
        ("delete from account where id = %s and version = %s", (3, 1)),
    ]


def test_a_deletion_failing_for_any_other_reason_is_never_counted_as_refused() -> None:
    lock_wait = DatabaseError(category="lockWaitTimeout", native_code="55P03", message="busy")
    port = ScriptedAdapter(
        Transact(Read(rows=[_LINUS, _GRACE])),
        Transact(Read(rows=[_LINUS]), Write()),
        Transact(Write(raises=lock_wait)),
    )
    with pytest.raises(ExecutionFailure) as failed:
        reviewed_accounts_are_deleted_under_the_versions_their_review_saw(port, MODELS["account"])
    assert failed.value.cause is lock_wait


def test_the_unversioned_wallet_is_read_under_the_shared_lock_before_its_write() -> None:
    wallet = {"id": 1, "owner": "Ada", "balance": Decimal("100.00")}
    port = ScriptedAdapter(
        Transact(Read(rows=[wallet]), Write()),
        Read(rows=[{**wallet, "balance": Decimal("175.00")}]),
    )
    balance = an_unversioned_wallet_is_written_through_a_read_of_the_writing_transaction(
        port, MODELS["wallet"]
    )
    assert balance == Decimal("175.00")
    read, write, _verified = [call for call in port.calls if isinstance(call, ReadCall | WriteCall)]
    assert isinstance(read, ReadCall) and read.sql.endswith("for share of t0")
    assert write == WriteCall(
        "update wallet set balance = %s where id = %s", (Decimal("175.00"), 1)
    )


def test_the_snippets_the_usage_guide_renders_are_the_sources_that_ran() -> None:
    reviewed = reviewed_deletion_snippet()
    assert "db.read_only(" in reviewed
    assert "tx.delete_if(Account, key=account.id, version=account.version)" in reviewed
    unversioned = unversioned_write_snippet()
    assert "tx.find(query).result()" in unversioned
    assert "tx.amend(wallet," in unversioned
