"""The conformance engine's transaction control: what a `rollback: true` step's
aborting boundary passes through, and the one scope that absorbs its abort.

Docker-free, over the engine's recording fake.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from parallax.conformance._mechanism.transaction_control import (
    absorbing_rollback,
    committed,
    write_connection,
)
from parallax.core.internal.db_port import (
    BeginFailed,
    CommitFailed,
    PipelineStatement,
    RolledBack,
    TransactionOutcome,
)
from tests._support.db_port import ScriptedAdapter
from tests.unit.conformance._recording_ports import FakeWritePort


def test_the_aborting_port_passes_reads_and_writes_through() -> None:
    # It decorates the BOUNDARY alone: every statement still reaches the inner
    # port unchanged, so the DML a doomed unit of work flushes is the DML it would
    # have committed.
    inner = FakeWritePort(find_rows=[{"id": 1}])
    port = write_connection(inner, rollback=True)
    assert port.execute("select 1", []) == [(1,)]
    assert port.execute_pipeline((PipelineStatement("select 1"),)) == [[(1,)]]
    assert port.execute_write("update account set balance = ?", [1]) == 1
    assert inner.reads and inner.writes


def test_the_aborting_port_answers_the_inner_ordered_transport_it_leaves_undecorated() -> None:
    absent = write_connection(FakeWritePort(), rollback=True)
    assert absent.ordered_write_transport is None
    inner = ScriptedAdapter(ordered=True)
    port = write_connection(inner, rollback=True)
    assert port.ordered_write_transport is inner.ordered_write_transport


def test_absorbing_rollback_ends_a_rollback_step_quietly() -> None:
    # `committed` re-raises whatever ended the boundary, and the scope absorbs
    # exactly the abort a `rollback: true` step asked for.
    inner = FakeWritePort()
    port = write_connection(inner, rollback=True)
    with absorbing_rollback():
        committed(port.transaction(lambda conn: conn.execute_write("delete from account", [])))
        raise AssertionError("the abort ends the step before this line")
    assert inner.writes == [("delete from account", [])]


def test_absorbing_rollback_lets_every_other_failure_through() -> None:
    inner = FakeWritePort()
    with pytest.raises(ValueError, match="not the sentinel"), absorbing_rollback():
        committed(inner.transaction(lambda conn: _refuse("not the sentinel")))
    assert inner.rollbacks == 1


def _rolled_back_after_commit_failed(error: Exception) -> RolledBack:
    return RolledBack(CommitFailed(error))


@pytest.mark.parametrize(
    "ended", [BeginFailed, _rolled_back_after_commit_failed], ids=["begin-failed", "commit-failed"]
)
def test_committed_raises_the_failure_of_a_boundary_that_did_not_commit(
    ended: Callable[[Exception], TransactionOutcome[int]],
) -> None:
    failure = ValueError("the boundary failed")
    with pytest.raises(ValueError, match="the boundary failed") as raised:
        committed(ended(failure))
    assert raised.value is failure


def _refuse(message: str) -> int:
    raise ValueError(message)
