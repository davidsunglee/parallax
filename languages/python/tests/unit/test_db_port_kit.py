"""The shared port kit's own contract: what a script guarantees its consumers.

Docker-free. The suites that moved onto the kit are its coverage of ordinary
answering — every one of them asserts on rows, counts, and recorded calls. What
they never exercise is what the kit exists to add over the mutable queues it
replaced: that a call the script does not reach fails at the call, that the
shape states which side of a transaction boundary a call landed on, that an
entry left unreached is reported, and that one failure instance cannot be
reported twice.
"""

from __future__ import annotations

import pytest

from _support.db_port import (
    BeginCall,
    CommitCall,
    Read,
    ReadCall,
    RefusingPort,
    RollbackCall,
    ScriptedPort,
    Transact,
    Write,
    WriteCall,
)
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import (
    BeginFailed,
    Bind,
    Committed,
    DbPort,
    RollbackFailed,
    RolledBack,
    Row,
)
from parallax.core.dialect import POSTGRES


def _deadlock() -> DatabaseError:
    return DatabaseError(category="deadlock", native_code="40P01", message="deadlock detected")


def _read(port: DbPort, sql: str = "select 1", binds: tuple[Bind, ...] = ()) -> list[Row]:
    return port.execute(sql, binds)


# --------------------------------------------------------------------------- #
# Answering by position, and refusing everything else.                        #
# --------------------------------------------------------------------------- #
def test_each_call_takes_the_next_entry_of_its_kind() -> None:
    port = ScriptedPort(Read(rows=[{"id": 1}]), Read(rows=[{"id": 2}]))

    assert [_read(port), _read(port)] == [[{"id": 1}], [{"id": 2}]]


def test_a_call_the_script_does_not_reach_fails_at_the_call() -> None:
    port = ScriptedPort(Read(rows=[{"id": 1}]))
    _read(port)

    with pytest.raises(AssertionError, match="unscripted read"):
        _read(port)


def test_a_call_of_another_kind_than_the_next_entry_fails_at_the_call() -> None:
    # Positional means positional: a pending read is not skipped because a write
    # arrived, which is what a per-kind queue did and what hid the ordering.
    port = ScriptedPort(Read(rows=[]), Write(affected=1))

    with pytest.raises(AssertionError, match="unscripted write"):
        port.execute_write("update account set owner = ?", ("Ada",))


def test_times_answers_that_many_successive_calls_the_same_way() -> None:
    port = ScriptedPort(Read(rows=[{"page": 1}], times=3))

    assert [_read(port) for _ in range(3)] == [[{"page": 1}]] * 3
    with pytest.raises(AssertionError, match="unscripted read"):
        _read(port)


def test_a_scripted_failure_is_raised_by_the_call_it_belongs_to() -> None:
    failure = _deadlock()
    port = ScriptedPort(Read(rows=[{"id": 1}]), Read(raises=failure))
    _read(port)

    with pytest.raises(DatabaseError) as raised:
        _read(port)

    assert raised.value is failure


def test_rows_reach_the_caller_as_copies_the_script_does_not_share() -> None:
    rows = [{"id": 1}]
    port = ScriptedPort(Read(rows=rows), Read(rows=rows))
    answered = _read(port)
    answered[0]["id"] = 2

    assert _read(port) == [{"id": 1}]


# --------------------------------------------------------------------------- #
# Nesting states the scope, which a flat sequence of answers cannot.          #
# --------------------------------------------------------------------------- #
def test_a_nested_entry_answers_only_inside_the_boundary_that_holds_it() -> None:
    port = ScriptedPort(Transact(Read(rows=[{"id": 1}])))

    with pytest.raises(AssertionError, match="unscripted read"):
        _read(port)


def test_an_entry_outside_the_boundary_does_not_answer_inside_it() -> None:
    port = ScriptedPort(Transact(), Read(rows=[{"id": 1}]))

    outcome = port.transaction(_read)

    assert isinstance(outcome, RolledBack)
    assert isinstance(outcome.trigger.error, AssertionError)


def test_a_body_reaching_a_further_boundary_takes_the_entry_nested_in_this_one() -> None:
    port = ScriptedPort(Transact(Transact(Write(affected=2))))

    outcome = port.transaction(
        lambda tx: tx.transaction(lambda inner: inner.execute_write("u", ()))
    )

    assert outcome == Committed(Committed(2))


def test_the_recording_stays_flat_where_the_script_nests() -> None:
    port = ScriptedPort(Read(rows=[]), Transact(Write(affected=1)))
    _read(port, "select 1", (7,))
    port.transaction(lambda tx: tx.execute_write("update", ("Ada",)), isolation="serializable")

    assert port.calls == [
        ReadCall("select 1", (7,)),
        BeginCall("serializable"),
        WriteCall("update", ("Ada",)),
        CommitCall(),
    ]


# --------------------------------------------------------------------------- #
# Boundary failures are clauses on the boundary that owns them.               #
# --------------------------------------------------------------------------- #
def test_a_begin_clause_never_opens_and_runs_no_body() -> None:
    failure = _deadlock()
    port = ScriptedPort(Transact(begin=failure))

    outcome = port.transaction(_read)

    assert outcome == BeginFailed(failure)
    assert port.calls == [BeginCall()]


def test_a_boundary_that_never_opens_cannot_be_given_a_body() -> None:
    with pytest.raises(ValueError, match="runs no body"):
        Transact(Read(rows=[]), begin=_deadlock())


def test_a_commit_clause_fails_after_a_body_that_returned() -> None:
    failure = _deadlock()
    port = ScriptedPort(Transact(Write(affected=1), commit=failure))

    outcome = port.transaction(lambda tx: tx.execute_write("update", ()))

    assert isinstance(outcome, RolledBack)
    assert outcome.trigger.error is failure
    assert port.calls == [BeginCall(), WriteCall("update", ()), RollbackCall()]


def test_a_rollback_clause_fails_the_undo_whatever_triggered_it() -> None:
    failure = _deadlock()
    port = ScriptedPort(Transact(rollback=failure))

    def body(_tx: DbPort) -> None:
        raise RuntimeError("the body gave up")

    outcome = port.transaction(body)

    assert isinstance(outcome, RollbackFailed)
    assert outcome.rollback_error is failure


# --------------------------------------------------------------------------- #
# Exhaustion, and the failure-instance identity rule the doubles owe too.     #
# --------------------------------------------------------------------------- #
def test_leaving_the_block_normally_reports_an_entry_never_reached() -> None:
    with pytest.raises(AssertionError, match="not consumed"), ScriptedPort(Read(rows=[])):
        pass


def test_leaving_the_block_normally_reports_a_nested_entry_never_reached() -> None:
    with (
        pytest.raises(AssertionError, match="not consumed"),
        ScriptedPort(Transact(Write(affected=1))) as port,
    ):
        port.transaction(lambda _tx: None)


def test_leaving_the_block_with_the_script_consumed_reports_nothing() -> None:
    with ScriptedPort(Read(rows=[{"id": 1}]), Transact()) as port:
        _read(port)
        port.transaction(lambda _tx: None)


def test_an_exception_leaving_the_block_is_not_displaced_by_the_exhaustion_check() -> None:
    with pytest.raises(ZeroDivisionError), ScriptedPort(Read(rows=[])):
        _ = 1 / 0


def test_two_entries_cannot_report_one_failure_instance() -> None:
    failure = _deadlock()

    with pytest.raises(ValueError, match="one failure instance"):
        ScriptedPort(Transact(Read(raises=failure)), Transact(commit=failure))


def test_one_entry_cannot_report_its_failure_more_than_once() -> None:
    with pytest.raises(ValueError, match="one failure instance"):
        ScriptedPort(Read(raises=_deadlock(), times=2))


# --------------------------------------------------------------------------- #
# Refusal is a port of its own, and refuses SQL rather than metadata.         #
# --------------------------------------------------------------------------- #
def test_a_refusing_port_fails_every_statement_and_every_boundary() -> None:
    port = RefusingPort()

    with pytest.raises(AssertionError, match="no read expected"):
        _read(port)
    with pytest.raises(AssertionError, match="no write expected"):
        port.execute_write("update", ())
    with pytest.raises(AssertionError, match="no transaction expected"):
        port.transaction(_read)


def test_a_refusing_port_still_reports_its_dialect() -> None:
    assert RefusingPort().dialect is POSTGRES
