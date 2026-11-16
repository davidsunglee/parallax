"""What a keyless Typed insert's reservation leaves behind when it fails, over a
scripted port.

A real server cannot fail a reservation's acquisition, statement, or release on
demand, nor finish one past its budget, so the port answers each reservation as
the test names. Each failure is judged through the public verbs: the insert that
needed the key raises and buffers nothing, the attempt's earlier work still
commits, the runner's existing retry classification decides what escapes the
callback, and the next keyless insert reserves anew rather than handing out
anything the failed reservation answered.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from types import TracebackType
from typing import Any

import pytest

from parallax.conformance.scripted_clock import FixedClock
from parallax.core import ConnectionAcquisitionError, ParallaxError, UsageError
from parallax.core.internal.db_error import DatabaseError
from parallax.core.internal.db_port import (
    CleanupIssue,
    ConnectionContext,
    DatabaseConnection,
    Invalidated,
)
from parallax.core.internal.diagnostics import diagnostic_for
from parallax.snapshot import ScopedDatabase, TxnContext, connect
from tests._support import mirrored_models as mm
from tests._support.bindings import TEST_BINDING
from tests._support.db_port import (
    BeginCall,
    CommitCall,
    Read,
    ReadCall,
    RollbackCall,
    ScriptedAdapter,
    ScriptedRuntime,
    Transact,
    Write,
    WriteCall,
    inserted_rows,
)
from tests._support.errors import raises_code
from tests._support.retry import fast_retry
from tests._support.root_ownership import own_root
from tests.unit._transact_support import deadlock

_FIXED = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
Pass = mm.KeySequencePass
"""Keys from ``pass_ids``: batch 3, initial value 100, increment size 10."""


def _reserved(first: int, **live: object) -> Read:
    """A reservation answering the block starting at ``first`` from a live
    definition matching ``pass_ids``, ``live`` overriding any column."""
    row: dict[str, object] = {
        "first_key": first,
        "increment": 30,
        "minimum": 1,
        "maximum": 2**63 - 1,
        "cycles": False,
        "data_type": "bigint",
    }
    return Read(rows=[row | live])


def _db(port: ScriptedAdapter) -> ScopedDatabase:
    return own_root(
        connect(port, mm.PK_KEY_SEQUENCE_MODEL, clock=FixedClock(_FIXED), binding=TEST_BINDING)
    ).using_database_login()


def _reservations(port: ScriptedAdapter) -> int:
    return sum(isinstance(call, ReadCall) and "nextval" in call.sql for call in port.calls)


def _written(port: ScriptedAdapter) -> list[tuple[object, ...]]:
    return [
        row for call in port.calls if isinstance(call, WriteCall) for row in inserted_rows(call)
    ]


# --------------------------------------------------------------------------- #
# A handled reservation failure buffers nothing and dooms nothing.            #
# --------------------------------------------------------------------------- #

_HANDLED: dict[str, tuple[Callable[[], Read | None], Callable[[], Any], str]] = {
    # (the failed reservation's script entry, its acquisition failure, the code)
    "acquisition-timeout": (
        lambda: None,
        lambda: ConnectionAcquisitionError("budget spent", reason="timeout"),
        "connection-acquisition-failed",
    ),
    "statement-failure": (
        lambda: Read(raises=DatabaseError(category=None, native_code="57014", message="canceled")),
        lambda: None,
        "database-statement-failed",
    ),
    "missing-sequence": (lambda: Read(rows=[]), lambda: None, "key-sequence-missing"),
    "mismatched-sequence": (
        lambda: _reserved(100, increment=7),
        lambda: None,
        "key-sequence-mismatch",
    ),
    "exhausted-sequence": (
        lambda: Read(
            raises=DatabaseError(category=None, native_code="2200H", message="nextval: reached")
        ),
        lambda: None,
        "key-sequence-exhausted",
    ),
}


@pytest.mark.parametrize("failure", list(_HANDLED))
def test_a_handled_reservation_failure_buffers_nothing_and_leaves_the_attempt_to_commit(
    failure: str,
) -> None:
    entry, refusal, code = _HANDLED[failure]
    failed = entry()
    port = ScriptedAdapter(
        Transact(*([failed] if failed is not None else []), _reserved(130), Write()),
        acquisition_failures=[None, refusal()],
    )
    lost = Pass(holder="lost")

    def body(tx: TxnContext) -> int:
        tx.insert(Pass(id=7, holder="given"))
        with pytest.raises(ParallaxError) as refused:
            tx.insert(lost)
        assert refused.value.code == code
        return tx.insert(Pass(holder="kept")).id

    # The failed reservation answered nothing usable, so the next keyless insert
    # reserves anew; the earlier supplied-key row and the later keyless one
    # commit together, and the refused insert left no row and no key behind.
    assert _db(port).transact(body) == 130
    assert _written(port) == [(7, "given"), (130, "kept")]
    assert port.calls[0] == BeginCall()
    assert port.calls[-1] == CommitCall()
    assert lost.id is None


def test_a_reservation_finishing_past_its_budget_publishes_no_key() -> None:
    port = ScriptedAdapter(Transact(_reserved(100), _reserved(130)), reservation_timeout=0.0)

    def body(tx: TxnContext) -> None:
        for _ in range(2):
            with raises_code(
                ConnectionAcquisitionError, "connection-acquisition-failed", match="after"
            ):
                tx.insert(Pass(holder="late"))

    # Each late reservation is abandoned, so the second insert reserves again
    # rather than handing out the first block's next key.
    _db(port).transact(body)
    assert _written(port) == []
    assert _reservations(port) == 2


class _FaultyRelease:
    """A reservation context whose release fails once the scripted one ran, as an
    interrupt landing while a lease is handed back does."""

    def __init__(self, inner: ConnectionContext) -> None:
        self._inner = inner

    @property
    def cleanup_result(self) -> Any:
        return self._inner.cleanup_result

    @property
    def selection(self) -> Any:
        return self._inner.selection

    def __enter__(self) -> DatabaseConnection:
        return self._inner.__enter__()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
        /,
    ) -> None:
        self._inner.__exit__(exc_type, exc, traceback)
        raise RuntimeError("the release was cut short")


class _FaultyReleaseRuntime(ScriptedRuntime):
    """Hands out reservation contexts whose release fails, the first
    ``faulty`` of them."""

    def __init__(self, adapter: ScriptedAdapter, faulty: int) -> None:
        super().__init__(adapter)
        self._faulty = faulty

    def new_reservation_context(self, deadline: float) -> ConnectionContext:
        context = super().new_reservation_context(deadline)
        if not self._faulty:
            return context
        self._faulty -= 1
        return _FaultyRelease(context)


class _FaultyReleaseAdapter(ScriptedAdapter):
    def open(self) -> ScriptedRuntime:
        return _FaultyReleaseRuntime(self, faulty=1)


def test_a_reservation_whose_release_fails_publishes_nothing_it_answered() -> None:
    # The block came back, but the Read it belongs to failed, so the allocator
    # never saw a finished reservation: the next insert reserves again.
    port = _FaultyReleaseAdapter(Transact(_reserved(100), _reserved(130), Write()))

    def body(tx: TxnContext) -> int:
        with pytest.raises(RuntimeError, match="cut short"):
            tx.insert(Pass(holder="lost"))
        return tx.insert(Pass(holder="kept")).id

    assert _db(port).transact(body) == 130
    assert _written(port) == [(130, "kept")]


def test_a_cleanup_issue_after_a_completed_reservation_keeps_its_block() -> None:
    # The statement committed on its own before the release judged the session,
    # so a lease disposed afterwards still reserved its block: handing it out
    # reuses no key, and reserving again would only leave a gap.
    disposed = Invalidated(
        (CleanupIssue("inspect", "suspect", diagnostic_for(RuntimeError("not idle"))),)
    )
    port = ScriptedAdapter(Transact(_reserved(100), Write()), cleanup_results=[disposed])

    def body(tx: TxnContext) -> list[int]:
        return [tx.insert(Pass(holder=name)).id for name in ("a", "b")]

    assert _db(port).transact(body) == [100, 110]
    assert port.cleanups[0] == disposed
    assert _reservations(port) == 1


# --------------------------------------------------------------------------- #
# What escapes the callback keeps the runner's retry classification.          #
# --------------------------------------------------------------------------- #


def test_an_acquisition_failure_in_a_reservation_is_not_made_retryable() -> None:
    port = ScriptedAdapter(
        Transact(),
        acquisition_failures=[None, ConnectionAcquisitionError("budget spent", reason="timeout")],
    )

    with pytest.raises(ConnectionAcquisitionError) as refused:
        _db(port).transact(lambda tx: tx.insert(Pass(holder="first")), retry=fast_retry(3))

    assert refused.value.reason == "timeout"
    assert port.calls == [BeginCall(), RollbackCall()]


@pytest.mark.parametrize(
    ("failure", "retried"),
    [
        (lambda: DatabaseError(category="deadlock", native_code="40P01", message="deadlock"), True),
        (lambda: DatabaseError(category=None, native_code="08006", message="lost"), False),
        (lambda: DatabaseError(category=None, native_code="2200H", message="reached"), False),
    ],
    ids=["deadlock-replays", "connection-loss-stops", "exhaustion-stops"],
)
def test_a_reservation_statement_failure_keeps_its_database_classification(
    failure: Callable[[], DatabaseError], retried: bool
) -> None:
    port = ScriptedAdapter(
        Transact(Read(raises=failure())),
        *([Transact(_reserved(130), Write())] if retried else []),
    )
    db = _db(port)

    if retried:
        assert db.transact(lambda tx: tx.insert(Pass(holder="one")).id, retry=fast_retry(3)) == 130
        assert _written(port) == [(130, "one")]
    else:
        with pytest.raises((DatabaseError, UsageError)):
            db.transact(lambda tx: tx.insert(Pass(holder="one")), retry=fast_retry(3))
        assert _written(port) == []
    assert _reservations(port) == 1 + retried


# --------------------------------------------------------------------------- #
# A retry answers a fresh value under a fresh authority; a held value keeps    #
# the key it holds.                                                            #
# --------------------------------------------------------------------------- #


def test_a_retry_answers_a_fresh_key_while_the_failed_attempt_s_value_keeps_its_own() -> None:
    port = ScriptedAdapter(
        Transact(_reserved(100), Write(), commit=deadlock()),
        Transact(Write()),
        Transact(Write()),
    )
    db = _db(port)
    draft = Pass(holder="drafted")
    answered: list[Any] = []

    def body(tx: TxnContext) -> int:
        if answered:
            # The failed attempt's value lost its insertion with that attempt.
            with raises_code(UsageError, "write-value-not-stored"):
                tx.amend(answered[0].edit(holder="edited"))
        answered.append(tx.insert(draft))
        return answered[-1].id

    assert db.transact(body, retry=fast_retry(3)) == 110
    first, retried = answered[0], answered[-1]
    assert (first.id, retried.id) == (100, 110)
    assert draft.id is None

    # Inserting the held value again uses the key it holds, never a new one.
    assert db.transact(lambda tx: tx.insert(first).id) == 100
    assert _reservations(port) == 1
    assert _written(port) == [(100, "drafted"), (110, "drafted"), (100, "drafted")]


def test_a_rolled_back_value_reinserts_under_its_key_and_the_block_is_not_returned() -> None:
    port = ScriptedAdapter(Transact(_reserved(100)), Transact(Write()), Transact(Write()))
    db = _db(port)
    held: list[Any] = []

    class _Undo(Exception):
        pass

    def first(tx: TxnContext) -> None:
        held.append(tx.insert(Pass(holder="held")))
        raise _Undo

    with pytest.raises(_Undo):
        db.transact(first)

    assert db.transact(lambda tx: tx.insert(held[0]).id) == 100
    # The rollback returned nothing to the root's block: the next keyless
    # insert takes the key after the one the rolled-back insert spent.
    assert db.transact(lambda tx: tx.insert(Pass(holder="next")).id) == 110
    assert _reservations(port) == 1
