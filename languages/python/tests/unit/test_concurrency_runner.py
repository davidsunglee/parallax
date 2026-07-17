"""``parallax.conformance.concurrency_runner`` unit tests (m-read-lock
behavioral matrix, COR-3 Phase 8 increment 6, Docker-free fake peer sessions).

Pins the pure `when.concurrency.rounds` parsing and the rounds runner's own
choreography (thread/barrier round-boundary protocol, per-node
`DatabaseError` capture, unconditional session teardown) as far as fakes
allow; the real two-session Postgres proof lives in
``tests/conformance/test_concurrency_rounds.py``.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from parallax.conformance import case_format, concurrency_runner
from parallax.conformance.concurrency_runner import ConcurrencyStep, RoundsRun
from parallax.core.db_error import DatabaseError
from parallax.core.dialect import POSTGRES

pytestmark = pytest.mark.unit


def _case(document: dict[str, Any], *, case_id: str = "m-read-lock-900") -> case_format.Case:
    return case_format.Case(
        path=Path(f"{case_id}.yaml"),
        case_id=case_id,
        shape="error",
        tags=("m-read-lock", "slice-snapshot-1"),
        model="models/account.yaml",
        document=document,
    )


# --------------------------------------------------------------------------- #
# parse_rounds: when.concurrency.rounds -> the per-node step plan.            #
# --------------------------------------------------------------------------- #
def test_parse_rounds_reads_node_presence_and_dialect_keyed_sql() -> None:
    case = _case(
        {
            "when": {
                "concurrency": {
                    "rounds": [
                        {
                            "A": {
                                "statements": [
                                    {
                                        "sql": {"postgres": "select 1 for share of t0"},
                                        "binds": [2],
                                    }
                                ]
                            }
                        },
                        {
                            "B": {
                                "statements": [{"sql": {"postgres": "update t set x = 1"}}],
                            }
                        },
                    ]
                }
            }
        }
    )
    rounds = concurrency_runner.parse_rounds(case, "postgres")
    assert len(rounds) == 2
    assert set(rounds[0]) == {"A"}
    assert set(rounds[1]) == {"B"}
    assert rounds[0]["A"].statements == (("select 1 for share of t0", (2,)),)
    assert rounds[0]["A"].kind is None
    assert rounds[0]["A"].expect_rows is None
    # A statement with no authored `binds` defaults to the empty tuple.
    assert rounds[1]["B"].statements == (("update t set x = 1", ()),)


def test_parse_rounds_reads_kind_and_expect_rows_for_concurrency_success() -> None:
    case = _case(
        {
            "when": {
                "concurrency": {
                    "rounds": [
                        {
                            "A": {
                                "statements": [{"sql": {"postgres": "select 1"}}],
                                "kind": "read",
                                "expectRows": [{"id": 2}],
                            },
                            "B": {
                                "statements": [{"sql": {"postgres": "update t set x = 1"}}],
                                "kind": "write",
                            },
                        }
                    ]
                }
            }
        }
    )
    (round0,) = concurrency_runner.parse_rounds(case, "postgres")
    assert round0["A"].kind == "read"
    assert round0["A"].expect_rows == ({"id": 2},)
    assert round0["B"].kind == "write"
    assert round0["B"].expect_rows is None


def test_parse_rounds_a_node_absent_from_a_round_is_omitted() -> None:
    case = _case(
        {
            "when": {
                "concurrency": {
                    "rounds": [{"A": {"statements": [{"sql": {"postgres": "select 1"}}]}}]
                }
            }
        }
    )
    (round0,) = concurrency_runner.parse_rounds(case, "postgres")
    assert "B" not in round0


# --------------------------------------------------------------------------- #
# run_rounds: the thread/barrier choreography over fake peer sessions.        #
# --------------------------------------------------------------------------- #
class _FakeSession:
    """A fake `PeerSession`: records every call, optionally raises a scripted
    `DatabaseError` on a matching statement, never blocks."""

    def __init__(self, *, raises_on: str | None = None, error: DatabaseError | None = None) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.closed = False
        self._raises_on = raises_on
        self._error = error

    def execute(self, sql: str, binds: Sequence[Any]) -> list[dict[str, Any]]:
        self.calls.append(("execute", sql, tuple(binds)))
        if self._raises_on is not None and self._raises_on in sql:
            assert self._error is not None
            raise self._error
        return [{"id": 2}] if "select" in sql else []

    def execute_write(self, sql: str, binds: Sequence[Any]) -> int:
        self.calls.append(("execute_write", sql, tuple(binds)))
        if self._raises_on is not None and self._raises_on in sql:
            assert self._error is not None
            raise self._error
        return 1

    def close(self) -> None:
        self.closed = True


def _rounds(*specs: dict[str, ConcurrencyStep]) -> tuple[dict[str, ConcurrencyStep], ...]:
    return tuple(specs)


def test_run_rounds_applies_the_lock_timeout_tuning_to_both_sessions() -> None:
    a, b = _FakeSession(), _FakeSession()
    peers = iter([a, b])
    concurrency_runner.run_rounds(_rounds({}), POSTGRES, lambda: next(peers))
    for session in (a, b):
        assert session.calls[0][0] == "execute"
        assert "lock_timeout" in session.calls[0][1]


def test_run_rounds_dispatches_read_and_write_kinds_to_the_right_verb() -> None:
    a, b = _FakeSession(), _FakeSession()
    peers = iter([a, b])
    rounds = _rounds(
        {
            "A": ConcurrencyStep(
                statements=(("select 1", ()),), kind="read", expect_rows=({"id": 2},)
            ),
            "B": ConcurrencyStep(
                statements=(("update t set x = 1", ()),), kind="write", expect_rows=None
            ),
        }
    )
    run = concurrency_runner.run_rounds(rounds, POSTGRES, lambda: next(peers))
    assert len(run.rounds) == 1
    assert run.rounds[0]["A"].rows == ({"id": 2},)
    assert run.rounds[0]["A"].error is None
    assert run.rounds[0]["B"].rows == ()
    assert run.rounds[0]["B"].error is None
    # `A`'s statement dispatched via `execute` (a read); `B`'s via `execute_write`.
    assert [call[0] for call in a.calls] == [
        "execute",
        "execute",
    ]  # lock_timeout SET, then the read
    assert [call[0] for call in b.calls] == ["execute", "execute_write"]


def test_run_rounds_an_undeclared_kind_step_executes_verbatim() -> None:
    # The `error` shape's own steps carry no `kind` (m-case-format); both a
    # SELECT and an UPDATE reach `execute` uniformly (no SQL-verb sniffing).
    a, b = _FakeSession(), _FakeSession()
    peers = iter([a, b])
    rounds = _rounds(
        {
            "A": ConcurrencyStep(
                statements=(("select 1 for share of t0", (2,)),), kind=None, expect_rows=None
            )
        },
        {
            "B": ConcurrencyStep(
                statements=(("update account set balance = ?", (999,)),),
                kind=None,
                expect_rows=None,
            )
        },
    )
    run = concurrency_runner.run_rounds(rounds, POSTGRES, lambda: next(peers))
    assert run.rounds[0]["A"].rows == ({"id": 2},)
    assert [call[0] for call in b.calls] == ["execute", "execute"]


def test_run_rounds_captures_a_database_error_on_its_own_node_and_round() -> None:
    err = DatabaseError(
        category="lockWaitTimeout", native_code="55P03", message="lock wait timeout"
    )
    a = _FakeSession()
    b = _FakeSession(raises_on="update", error=err)
    peers = iter([a, b])
    rounds = _rounds(
        {"A": ConcurrencyStep(statements=(("select 1", ()),), kind=None, expect_rows=None)},
        {
            "B": ConcurrencyStep(
                statements=(("update t set x = 1", ()),), kind=None, expect_rows=None
            )
        },
    )
    run = concurrency_runner.run_rounds(rounds, POSTGRES, lambda: next(peers))
    assert run.rounds[0]["A"].error is None
    assert "B" not in run.rounds[0]
    assert run.rounds[1]["B"].error is err
    assert "A" not in run.rounds[1]


def test_run_rounds_closes_both_sessions_even_when_one_raises() -> None:
    err = DatabaseError(category="deadlock", native_code="40P01", message="deadlock")
    a = _FakeSession(raises_on="select", error=err)
    b = _FakeSession()
    peers = iter([a, b])
    rounds = _rounds(
        {"A": ConcurrencyStep(statements=(("select 1", ()),), kind=None, expect_rows=None)}
    )
    concurrency_runner.run_rounds(rounds, POSTGRES, lambda: next(peers))
    assert a.closed
    assert b.closed


def test_run_rounds_setup_failure_closes_the_already_open_first_session() -> None:
    # Review remediation finding 4: a second-peer CONSTRUCTION failure must
    # not leak the already-open first session — incremental `ExitStack`
    # protection registers each session for close the moment it opens.
    a = _FakeSession()
    calls = {"n": 0}

    def peer_factory() -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            return a
        raise RuntimeError("the second peer never opens")

    with pytest.raises(RuntimeError, match="the second peer never opens"):
        concurrency_runner.run_rounds(_rounds({}), POSTGRES, peer_factory)
    assert a.closed


def test_run_rounds_setup_failure_closes_both_sessions_when_tuning_the_second_fails() -> None:
    # A session that opened successfully but fails its OWN lock-contention
    # TUNING is still "successfully opened" — it and its already-tuned
    # partner both close (the same incremental protection, one step later).
    err = DatabaseError(category="connectionDead", native_code="XX000", message="tuning failed")
    a = _FakeSession()
    b = _FakeSession(raises_on="lock_timeout", error=err)
    peers = iter([a, b])
    with pytest.raises(DatabaseError):
        concurrency_runner.run_rounds(_rounds({}), POSTGRES, lambda: next(peers))
    assert a.closed
    assert b.closed


def test_run_rounds_raises_the_originating_failure_not_a_partners_barrier_break() -> None:
    # Review remediation finding 4: when the SECOND-checked node (`B`) is the
    # one with the genuine, unexpected defect and the FIRST-checked node
    # (`A`) merely trips over the resulting `barrier.abort()` (a SECONDARY
    # `BrokenBarrierError`, never a defect of its own — `A` has no round-0
    # step, so it is already blocked at the round's own boundary when `B`
    # aborts), the raised exception must be `B`'s genuine one — never `A`'s
    # masking barrier break (the join/inspect-order bug this remediation
    # fixes) — with the secondary chained as its own `__cause__`.
    class _Broken:
        def execute(self, sql: str, binds: Sequence[Any]) -> list[dict[str, Any]]:
            if "lock_timeout" in sql:
                return []
            raise RuntimeError("B's own genuine defect")

        def execute_write(self, sql: str, binds: Sequence[Any]) -> int:
            return 0

        def close(self) -> None:
            pass

    a = _FakeSession()
    b = _Broken()
    peers = iter([a, b])
    rounds = _rounds(
        {"B": ConcurrencyStep(statements=(("select 1", ()),), kind=None, expect_rows=None)}
    )
    with pytest.raises(RuntimeError, match="B's own genuine defect") as excinfo:
        concurrency_runner.run_rounds(rounds, POSTGRES, lambda: next(peers))
    assert isinstance(excinfo.value.__cause__, threading.BrokenBarrierError)
    assert a.closed


def test_run_rounds_reraises_an_unexpected_non_database_error() -> None:
    # An UNEXPECTED (never a witnessed path) non-`DatabaseError` failure —
    # never caught/recorded as a per-node outcome — aborts the barrier (so
    # the OTHER thread's own `barrier.wait()` never hangs) and re-raises on
    # the caller's thread once both workers join.
    class _Broken:
        def execute(self, sql: str, binds: Sequence[Any]) -> list[dict[str, Any]]:
            if "lock_timeout" in sql:
                return []
            raise RuntimeError("a worker thread's own unexpected defect")

        def execute_write(self, sql: str, binds: Sequence[Any]) -> int:
            return 0

        def close(self) -> None:
            pass

    a = _Broken()
    b = _FakeSession()
    peers = iter([a, b])
    rounds = _rounds(
        {"A": ConcurrencyStep(statements=(("select 1", ()),), kind=None, expect_rows=None)}
    )
    with pytest.raises(RuntimeError, match="unexpected defect"):
        concurrency_runner.run_rounds(rounds, POSTGRES, lambda: next(peers))
    assert b.closed


def test_run_rounds_reports_no_outcome_for_an_absent_node() -> None:
    a, b = _FakeSession(), _FakeSession()
    peers = iter([a, b])
    rounds = _rounds(
        {"A": ConcurrencyStep(statements=(("select 1", ()),), kind=None, expect_rows=None)}
    )
    run = concurrency_runner.run_rounds(rounds, POSTGRES, lambda: next(peers))
    assert set(run.rounds[0]) == {"A"}


# --------------------------------------------------------------------------- #
# The barrier protocol: a round with only one active node still waits for    #
# its idle partner to reach the SAME round boundary before the next round    #
# starts (m-case-format "the harness ... synchronizes rounds with a          #
# barrier").                                                                  #
# --------------------------------------------------------------------------- #
def test_run_rounds_barrier_blocks_the_next_round_until_both_sides_finish() -> None:
    order: list[str] = []
    order_lock = threading.Lock()
    release = threading.Event()
    started = threading.Event()

    class _NoOpA:
        def execute(self, sql: str, binds: Sequence[Any]) -> list[dict[str, Any]]:
            if "lock_timeout" not in sql:
                with order_lock:
                    order.append("A")
            return []

        def execute_write(self, sql: str, binds: Sequence[Any]) -> int:
            return 0

        def close(self) -> None:
            pass

    class _SlowB:
        def execute(self, sql: str, binds: Sequence[Any]) -> list[dict[str, Any]]:
            if "lock_timeout" in sql:
                return []
            with order_lock:
                order.append("B-start")
            started.set()
            assert release.wait(timeout=5), "the test never released B"
            with order_lock:
                order.append("B-end")
            return []

        def execute_write(self, sql: str, binds: Sequence[Any]) -> int:
            return 0

        def close(self) -> None:
            pass

    sessions = iter([_NoOpA(), _SlowB()])
    rounds = _rounds(
        {"B": ConcurrencyStep(statements=(("select 1", ()),), kind=None, expect_rows=None)},
        {"A": ConcurrencyStep(statements=(("select 2", ()),), kind=None, expect_rows=None)},
    )
    outcome: list[RoundsRun] = []

    def go() -> None:
        outcome.append(concurrency_runner.run_rounds(rounds, POSTGRES, lambda: next(sessions)))

    runner = threading.Thread(target=go)
    runner.start()
    assert started.wait(timeout=5), "B never reached its round-0 step"
    with order_lock:
        # A has nothing to do in round 0, but the round-0 END barrier still
        # withholds round 1 (A's own step) until B finishes its held step.
        assert order == ["B-start"]
    release.set()
    runner.join(timeout=5)
    assert order == ["B-start", "B-end", "A"]
    assert outcome[0].rounds[1]["A"].rows == ()
