"""The conformance engine's transaction control: what a `rollback: true` step's
aborting boundary passes through, and the one scope that absorbs its abort.

Docker-free, over the engine's recording fake.
"""

from __future__ import annotations

import pytest

from parallax.conformance._mechanism.transaction_control import (
    absorbing_rollback,
    committed,
    write_connection,
)
from parallax.core.db_port import DatabaseConnection, RolledBack
from tests.unit.conformance._recording_ports import FakeWritePort


def test_the_aborting_port_passes_reads_and_writes_through() -> None:
    # It decorates the BOUNDARY alone: every statement still reaches the inner
    # port unchanged, so the DML a doomed unit of work flushes is the DML it would
    # have committed.
    inner = FakeWritePort(find_rows=[{"id": 1}])
    port = write_connection(inner, rollback=True)
    assert port.execute("select 1", []) == [{"id": 1}]
    assert port.execute_write("update account set balance = ?", [1]) == 1
    assert inner.reads and inner.writes


def test_a_port_that_does_not_roll_back_is_handed_back_undecorated() -> None:
    inner = FakeWritePort()
    assert write_connection(inner, rollback=False) is inner


def test_a_rollback_step_flushes_its_work_and_then_aborts() -> None:
    # The abort lands once the body has returned, so the statements the body
    # put on the wire executed and the provider's rollback is what erases them.
    inner = FakeWritePort()
    port = write_connection(inner, rollback=True)

    def body(conn: DatabaseConnection) -> int:
        return conn.execute_write("update account set balance = ?", [1])

    outcome = port.transaction(body)
    assert isinstance(outcome, RolledBack)
    assert inner.writes == [("update account set balance = ?", [1])]
    assert (inner.commits, inner.rollbacks) == (0, 1)


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


def _refuse(message: str) -> int:
    raise ValueError(message)
