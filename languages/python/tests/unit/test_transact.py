"""Developer transaction surface unit tests (spec §5, Docker-free fake ports).

`Database.transact` composes M3's unit-of-work shell, increment 1's write
lowering, and the ``m-auto-retry`` bounded loop over an injected ``m-db-port``.
These tests drive that composition through recording fake ports: the
buffer→flush→lower→execute wiring proof, read-your-own-writes ordering, the
participation-mode lock suffix, join semantics (same Transaction, option
conflicts, rollback-only foreclosure), withheld values on abort, and the retry
classification matrix — including the spec §5 requirement that a rollback-only
commit refusal keeps its original cause's retriability.
"""

from __future__ import annotations

import contextlib
import datetime as dt
from collections.abc import Callable, Sequence
from decimal import Decimal

import pytest

import inheritance_models as im
import mirrored_models as mm
from parallax.conformance import models
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import Bind, DbPort, Row
from parallax.core.dialect import POSTGRES
from parallax.core.unit_work import (
    EscapedTransactionError,
    FixedClock,
    FlushPlan,
    RollbackOnlyError,
    TransactionSettings,
    UnitOfWork,
    UnitOfWorkError,
    WriteInstructionError,
    run_unit_of_work,
)
from parallax.snapshot import connect
from parallax.snapshot.handle import Database, Transaction, TransactionOptionConflictError

pytestmark = pytest.mark.unit

_ACCOUNT = models.load_models()["account"]
_BALANCE = models.load_models()["balance"]
_FIXED = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)

_NEW_ROW: Row = {"id": 7, "owner": "Newton", "balance": 5.00, "version": 1}


def _new_account() -> mm.Account:
    return mm.Account(id=7, owner="Newton", balance=Decimal("5.00"), version=1)


def _edited_balance(balance: str) -> mm.Account:
    # A "fetched" Ada (id=1, balance=100.00, version=1), then an edited copy
    # touching only `balance` — the Change Record `tx.update` reads.
    fetched = mm.Account(id=1, owner="Ada", balance=Decimal("100.00"), version=1)
    return fetched.model_copy(update={"balance": Decimal(balance)})


def _grace() -> mm.Account:
    return mm.Account(id=3, owner="Grace", balance=Decimal("10.00"), version=1)


# The m-unit-work-001 goldens, rendered to driver SQL as the port receives them.
_INSERT_SQL = POSTGRES.to_driver_sql(
    "insert into account(id, owner, balance, version) values (?, ?, ?, ?)"
)
_FIND_SQL = POSTGRES.to_driver_sql(
    "select t0.id, t0.owner, t0.balance, t0.version from account t0 where t0.id = ? for share of t0"
)
_FIND_SQL_NO_LOCK = POSTGRES.to_driver_sql(
    "select t0.id, t0.owner, t0.balance, t0.version from account t0 where t0.id = ?"
)


def _deadlock() -> DatabaseError:
    return DatabaseError(category="deadlock", native_code="40P01", message="deadlock detected")


class _RecordingPort:
    """An in-memory ``m-db-port`` recording every call in order (no Docker).

    ``txn_faults`` raises at the next ``transaction`` entries (a driver failure
    the adapter translated and rolled back); ``read_faults`` raises from the
    next ``execute`` calls (a failure inside the transaction body).
    """

    def __init__(self, *, rows: Sequence[Row] = ()) -> None:
        self.ops: list[tuple[object, ...]] = []
        self.rows = list(rows)
        self.txn_faults: list[DatabaseError] = []
        self.read_faults: list[DatabaseError] = []

    def execute(self, sql: str, binds: Sequence[Bind]) -> list[Row]:
        if self.read_faults:
            raise self.read_faults.pop(0)
        self.ops.append(("read", sql, tuple(binds)))
        return [dict(row) for row in self.rows]

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        self.ops.append(("write", sql, tuple(binds)))
        return 1

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:
        self.ops.append(("begin",))
        if self.txn_faults:
            self.ops.append(("rollback",))
            raise self.txn_faults.pop(0)
        try:
            result = body(self)
        except BaseException:
            self.ops.append(("rollback",))
            raise
        self.ops.append(("commit",))
        return result

    @property
    def begins(self) -> int:
        return sum(1 for op in self.ops if op == ("begin",))


def _db(port: _RecordingPort) -> Database:
    # The spec §8 module-level `connect` is the classmethod's alias, so this
    # covers both spellings.
    return connect(port, _ACCOUNT, clock=FixedClock(_FIXED))


# --------------------------------------------------------------------------- #
# Wiring: buffer -> flush -> lower_write -> execute_write on the connection.   #
# --------------------------------------------------------------------------- #
def test_commit_flushes_the_buffer_through_the_lowering_seam() -> None:
    port = _RecordingPort()

    def fn(tx: Transaction) -> str:
        tx.insert(_new_account())
        return "done"

    assert _db(port).transact(fn) == "done"
    assert port.ops == [
        ("begin",),
        ("write", _INSERT_SQL, (7, "Newton", 5.00, 1)),
        ("commit",),
    ]


def test_update_and_delete_lower_to_their_keyed_dml() -> None:
    # m-unit-work-005 / -006: a keyed update (SET the non-PK members, WHERE the
    # key) and a keyed delete, flushed in the canonical mixed-op order.
    port = _RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.update(_edited_balance("175.00"))
        tx.delete(_grace())

    _db(port).transact(fn)
    assert port.ops == [
        ("begin",),
        (
            "write",
            POSTGRES.to_driver_sql("update account set balance = ?, version = ? where id = ?"),
            (175.00, 2, 1),
        ),
        ("write", POSTGRES.to_driver_sql("delete from account where id = ?"), (3,)),
        ("commit",),
    ]


def test_find_force_flushes_pending_writes_first() -> None:
    # Read-your-own-writes: the buffered insert executes BEFORE the dependent
    # read, inside the same still-open transaction (m-unit-work-001's shape).
    port = _RecordingPort(rows=[_NEW_ROW])

    def fn(tx: Transaction) -> list[mm.Account]:
        tx.insert(_new_account())
        return tx.find(mm.Account.where(mm.Account.id == 7)).results()

    assert _db(port).transact(fn) == [_new_account()]
    assert port.ops == [
        ("begin",),
        ("write", _INSERT_SQL, (7, "Newton", 5.00, 1)),
        ("read", _FIND_SQL, (7,)),
        ("commit",),
    ]


def test_optimistic_mode_suppresses_the_read_lock_suffix() -> None:
    port = _RecordingPort()
    _db(port).transact(
        lambda tx: tx.find(mm.Account.where(mm.Account.id == 7)), concurrency="optimistic"
    )
    assert port.ops == [("begin",), ("read", _FIND_SQL_NO_LOCK, (7,)), ("commit",)]


def test_db_find_pins_an_explicit_as_of_statement() -> None:
    # `statement_pin` reads the statement's OWN temporal wrapper: an explicit
    # `.as_of(processing=LATEST)` pin comes back on the returned `Snapshot`.
    from parallax.core import LATEST

    port = _RecordingPort(
        rows=[
            {
                "bal_id": 1,
                "acct_num": "A-1",
                "val": Decimal("5.00"),
                "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
                "out_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
            }
        ]
    )
    db = Database.connect(port, _BALANCE, clock=FixedClock(_FIXED))
    statement = mm.Balance.where(mm.Balance.id == 1).as_of(processing=LATEST)
    snapshot = db.find(statement)
    assert snapshot.pin.processing is LATEST


def test_db_find_resolves_a_concrete_inheritance_targets_inherited_pin_and_edge() -> None:
    # `DepositRate` declares NO `as_of` of its own (`Rate`, the family root,
    # does) — `_temporal_entity` (`parallax.snapshot.handle`) must resolve
    # through the root to compute both the statement pin and the row's own
    # milestone edge (COR-3 Phase 7 review remediation, P3/P4).
    from parallax.core import LATEST, edge_of

    port = _RecordingPort(
        rows=[
            {
                "id": 1,
                "amount": Decimal("2.50"),
                "grade": "A",
                "from_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
                "thru_z": dt.datetime(9999, 12, 31, tzinfo=dt.UTC),
                "in_z": dt.datetime(2024, 2, 1, tzinfo=dt.UTC),
                "out_z": dt.datetime(9999, 12, 31, tzinfo=dt.UTC),
            }
        ]
    )
    rate = models.load_models()["rate"]
    db = Database.connect(port, rate, clock=FixedClock(_FIXED))
    statement = im.DepositRate.where().as_of(processing=LATEST)
    snapshot = db.find(statement)
    assert snapshot.pin.processing is LATEST
    assert snapshot.pin.business is None
    edge = edge_of(snapshot.result())
    assert edge.processing == dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
    assert edge.business == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


def _balance_history_rows() -> list[Row]:
    # Two milestones on the SAME processing axis, closed then current.
    return [
        {
            "bal_id": 1,
            "acct_num": "A-1",
            "val": Decimal("5.00"),
            "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
            "out_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
        },
        {
            "bal_id": 1,
            "acct_num": "A-1",
            "val": Decimal("9.00"),
            "in_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
            "out_z": dt.datetime(9999, 12, 31, tzinfo=dt.UTC),
        },
    ]


def test_db_find_returns_one_snapshot_root_per_milestone_for_a_history_statement() -> None:
    from parallax.core import Pin

    port = _RecordingPort(rows=_balance_history_rows())
    db = Database.connect(port, _BALANCE, clock=FixedClock(_FIXED))
    # `.distinct()` after `.history()` also exercises `_is_milestone_set_op`'s
    # own directive-peeling loop (a result-shaping wrapper around the scan).
    statement = mm.Balance.where(mm.Balance.id == 1).history("processing").distinct()
    snapshot = db.find(statement)
    assert len(snapshot.results()) == 2
    assert snapshot.pin == Pin()  # the whole-graph pin is per-milestone, not here


def test_tx_find_returns_one_snapshot_root_per_milestone_for_a_history_statement() -> None:
    port = _RecordingPort(rows=_balance_history_rows())
    db = Database.connect(port, _BALANCE, clock=FixedClock(_FIXED))
    statement = mm.Balance.where(mm.Balance.id == 1).history("processing")
    snapshot = db.transact(lambda tx: tx.find(statement))
    assert len(snapshot.results()) == 2


def test_pin_from_milestone_skips_an_axis_absent_from_the_milestone_pin() -> None:
    # `_pin_from_milestone` is generic over any `Mapping` (not tied to how
    # `_edge_pin` always populates every declared axis in practice) — a
    # bitemporal entity's OWN as-of-attribute loop must skip an axis absent
    # from a given milestone's pin, not KeyError.
    from parallax.snapshot.handle import _pin_from_milestone  # pyright: ignore[reportPrivateUsage]

    position = models.load_models()["position"].entity("Position")
    pin = _pin_from_milestone(position, {"processingDate": _FIXED})
    assert pin.processing == _FIXED
    assert pin.business is None


def test_update_with_an_empty_effective_change_set_issues_no_dml() -> None:
    # A `model_copy()` with no `update=` carries forward the SAME (empty)
    # Change Record: the sparse-update no-op rule (spec §3/§5).
    port = _RecordingPort()
    fetched = mm.Account(id=1, owner="Ada", balance=Decimal("100.00"), version=1)
    edited = fetched.model_copy(update={"balance": Decimal("100.00")})  # net-zero touch

    def fn(tx: Transaction) -> None:
        tx.update(edited)

    _db(port).transact(fn)
    assert port.ops == [("begin",), ("commit",)]  # no write round trip at all


def test_abort_discards_the_buffer_and_withholds_the_value() -> None:
    port = _RecordingPort()

    def fn(tx: Transaction) -> str:
        tx.insert(_new_account())
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        _db(port).transact(fn)
    # Nothing flushed: the buffered write never reached the port.
    assert port.ops == [("begin",), ("rollback",)]


def test_row_naming_an_undeclared_member_is_rejected_at_buffer_time() -> None:
    # The instance-graduated verbs build their row from the compiled entity's
    # OWN declared members, so an undeclared member can no longer be smuggled
    # in through `tx.insert`; the member-name honesty gate still protects the
    # lower-level neutral document route directly (`Transaction._buffer`).
    port = _RecordingPort()
    with pytest.raises(WriteInstructionError, match="shoe_size"):
        _db(port).transact(
            lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage]
                "insert", "Account", {"id": 1, "shoe_size": 9}
            )
        )
    assert ("write", _INSERT_SQL, (1, 9)) not in port.ops


def test_an_escaped_transaction_reference_raises_after_the_scope_ends() -> None:
    port = _RecordingPort()
    escaped: list[Transaction] = []

    def fn(tx: Transaction) -> None:
        escaped.append(tx)

    _db(port).transact(fn)
    with pytest.raises(EscapedTransactionError):
        escaped[0].insert(_new_account())


# --------------------------------------------------------------------------- #
# Join semantics: same Transaction, option conflicts, foreclosure.             #
# --------------------------------------------------------------------------- #
def test_join_receives_the_same_transaction_and_returns_immediately() -> None:
    port = _RecordingPort()
    db = _db(port)

    def outer(tx: Transaction) -> int:
        inner = db.transact(lambda inner_tx: (inner_tx is tx, 42))
        assert inner == (True, 42)
        return inner[1]

    assert db.transact(outer) == 42
    assert port.begins == 1  # the join opened no second database transaction


def test_join_with_equal_or_omitted_options_inherits() -> None:
    port = _RecordingPort()
    db = _db(port)

    def outer(_tx: Transaction) -> str:
        # Explicit-and-equal to the resolved defaults: accepted, not a conflict.
        return db.transact(
            lambda _inner: "joined",
            retries=10,
            concurrency="locking",
            retry_optimistic_conflicts=False,
        )

    assert db.transact(outer) == "joined"


def _must_not_run(_tx: Transaction) -> None:  # pragma: no cover - conflict forecloses it
    raise AssertionError("the joined closure must not run on an option conflict")


_CONFLICTING_JOINS: list[tuple[str, Callable[[Database], object]]] = [
    ("retries", lambda db: db.transact(_must_not_run, retries=3)),
    ("concurrency", lambda db: db.transact(_must_not_run, concurrency="optimistic")),
    (
        "retry_optimistic_conflicts",
        lambda db: db.transact(_must_not_run, retry_optimistic_conflicts=True),
    ),
]


@pytest.mark.parametrize(("option", "join"), _CONFLICTING_JOINS)
def test_join_with_a_conflicting_explicit_option_raises(
    option: str, join: Callable[[Database], object]
) -> None:
    port = _RecordingPort()
    db = _db(port)

    def outer(_tx: Transaction) -> str:
        with pytest.raises(TransactionOptionConflictError, match=option):
            join(db)
        return "survived"

    # The conflict is refused before the joined closure runs, and refusing it
    # does not doom the outer transaction (nothing entered the joined frame).
    assert db.transact(outer) == "survived"


def test_joining_a_doomed_transaction_is_foreclosed_before_its_closure_runs() -> None:
    port = _RecordingPort()
    db = _db(port)
    ran: list[bool] = []

    def outer(_tx: Transaction) -> str:
        with pytest.raises(RuntimeError, match="inner failure"):
            db.transact(_raise_inner)
        with pytest.raises(RollbackOnlyError):
            db.transact(lambda _inner: ran.append(True))
        return "unreachable value"

    # The outer callback caught everything and returned normally, but the inner
    # failure doomed the transaction: commit is refused and the value withheld.
    with pytest.raises(RollbackOnlyError) as excinfo:
        db.transact(outer)
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert ran == []
    assert port.ops == [("begin",), ("rollback",)]


def _raise_inner(_tx: Transaction) -> None:
    raise RuntimeError("inner failure")


def test_bare_unit_of_work_on_the_thread_is_refused() -> None:
    port = _RecordingPort()
    db = _db(port)

    def executor(_plan: FlushPlan) -> None:  # pragma: no cover - never flushed
        raise AssertionError("no flush expected")

    def body(_uow: UnitOfWork) -> None:
        with pytest.raises(UnitOfWorkError, match="bare unit of work"):
            db.transact(lambda _tx: None)

    run_unit_of_work(
        body,
        settings=TransactionSettings(),
        clock=FixedClock(_FIXED),
        meta=_ACCOUNT,
        flush_executor=executor,
    )


# --------------------------------------------------------------------------- #
# Bounded retry (m-auto-retry through db.transact).                            #
# --------------------------------------------------------------------------- #
def test_a_deadlock_is_retried_and_the_reexecution_succeeds() -> None:
    port = _RecordingPort()
    port.txn_faults = [_deadlock(), _deadlock()]
    assert _db(port).transact(lambda _tx: "ok") == "ok"
    assert port.begins == 3


def test_exhaustion_reraises_the_failure_with_the_attempt_count() -> None:
    port = _RecordingPort()
    port.txn_faults = [_deadlock(), _deadlock(), _deadlock()]
    with pytest.raises(DatabaseError) as excinfo:
        _db(port).transact(lambda _tx: "ok", retries=2)
    assert port.begins == 3
    assert excinfo.value.is_retriable  # the surfaced error is the failure itself
    assert "3 attempts (retries=2)" in "".join(excinfo.value.__notes__)


def test_the_default_bound_is_ten_reexecutions() -> None:
    port = _RecordingPort()
    port.txn_faults = [_deadlock() for _ in range(11)]
    with pytest.raises(DatabaseError) as excinfo:
        _db(port).transact(lambda _tx: "ok")
    assert port.begins == 11
    assert "11 attempts (retries=10)" in "".join(excinfo.value.__notes__)


@pytest.mark.parametrize(
    ("category", "native"),
    [("uniqueViolation", "23505"), ("lockWaitTimeout", "55P03")],
)
def test_non_retriable_categories_surface_after_one_attempt(category: str, native: str) -> None:
    port = _RecordingPort()
    port.txn_faults = [DatabaseError(category=category, native_code=native, message=category)]  # type: ignore[arg-type]
    with pytest.raises(DatabaseError):
        _db(port).transact(lambda _tx: "ok")
    assert port.begins == 1


def test_retries_zero_disables_the_loop() -> None:
    port = _RecordingPort()
    port.txn_faults = [_deadlock()]
    with pytest.raises(DatabaseError):
        _db(port).transact(lambda _tx: "ok", retries=0)
    assert port.begins == 1


def test_negative_retries_are_rejected_before_any_attempt() -> None:
    port = _RecordingPort()
    with pytest.raises(ValueError, match="retries must be >= 0"):
        _db(port).transact(lambda _tx: "ok", retries=-1)
    assert port.begins == 0


def test_rollback_only_refusal_keeps_the_original_retriability() -> None:
    # Spec §5: an inner deadlock dooms the transaction; even though the outer
    # callback catches it and returns normally, the commit refusal preserves the
    # cause's classification — the retry loop re-executes, and the fresh attempt
    # succeeds.
    port = _RecordingPort(rows=[_NEW_ROW])
    port.read_faults = [_deadlock()]
    db = _db(port)

    def outer(_tx: Transaction) -> str:
        with contextlib.suppress(DatabaseError):
            db.transact(lambda inner_tx: inner_tx.find(mm.Account.where(mm.Account.id == 7)))
        return "caught"

    assert db.transact(outer) == "caught"
    assert port.begins == 2
