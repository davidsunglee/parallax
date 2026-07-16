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
from typing import Final, cast

import pytest

import inheritance_models as im
import mirrored_models as mm
from parallax.conformance import models
from parallax.core import opt_lock
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import Bind, DbPort, Row
from parallax.core.descriptor import Metamodel
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
    WriteRejectedError,
    run_unit_of_work,
    validate_write,
)
from parallax.snapshot import connect
from parallax.snapshot.handle import Database, Transaction, TransactionOptionConflictError

pytestmark = pytest.mark.unit

_ACCOUNT = models.load_models()["account"]
_BALANCE = models.load_models()["balance"]
_CONTACT = models.load_models()["contact"]
_SHIPMENT = models.load_models()["shipment"]
_PAYMENT = models.load_models()["payment"]
_FIXED = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)

_NEW_ROW: Row = {"id": 7, "owner": "Newton", "balance": 5.00, "version": 1}


def _new_account() -> mm.Account:
    return mm.Account(id=7, owner="Newton", balance=Decimal("5.00"), version=1)


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

    def __init__(self, *, rows: Sequence[Row] = (), write_affected: int = 1) -> None:
        self.ops: list[tuple[object, ...]] = []
        self.rows = list(rows)
        self.write_affected = write_affected
        self.txn_faults: list[DatabaseError] = []
        self.read_faults: list[DatabaseError] = []

    def execute(self, sql: str, binds: Sequence[Bind]) -> list[Row]:
        if self.read_faults:
            raise self.read_faults.pop(0)
        self.ops.append(("read", sql, tuple(binds)))
        return [dict(row) for row in self.rows]

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        self.ops.append(("write", sql, tuple(binds)))
        return self.write_affected

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


def _db_for(meta: Metamodel, port: _RecordingPort) -> Database:
    return Database.connect(port, meta, clock=FixedClock(_FIXED))


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


def test_update_lowers_to_its_keyed_dml() -> None:
    # m-unit-work-005, migrated to the m-opt-lock observation flow (COR-3
    # Phase 8 increment 3): a keyed update (SET the non-PK members, WHERE the
    # key, version advanced from THIS unit of work's own recorded
    # observation). The edited copy is built from a row `tx.find` fetches
    # INSIDE this transaction — a versioned update requires a prior
    # observation; an edited copy fetched outside the writing transaction
    # cannot be updated directly (python.md §5).
    port = _RecordingPort(rows=[{"id": 1, "owner": "Ada", "balance": 100.00, "version": 1}])

    def fn(tx: Transaction) -> None:
        fetched = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(fetched.model_copy(update={"balance": Decimal("175.00")}))

    _db(port).transact(fn)
    assert port.ops == [
        ("begin",),
        ("read", _FIND_SQL, (1,)),
        (
            "write",
            POSTGRES.to_driver_sql("update account set balance = ?, version = ? where id = ?"),
            (175.00, 2, 1),
        ),
        ("commit",),
    ]


def test_delete_of_an_observed_versioned_row_gates_on_the_observed_version() -> None:
    # m-unit-work-006, migrated to the m-opt-lock observation flow (COR-3
    # Phase 8 review remediation): a keyed DELETE of a versioned row requires
    # a PRIOR observation exactly like a keyed update (python.md §5) — the
    # deleted row must be fetched INSIDE this transaction first, and the
    # lowered DELETE binds that observed version.
    port = _RecordingPort(rows=[{"id": 3, "owner": "Grace", "balance": 10.00, "version": 1}])

    def fn(tx: Transaction) -> None:
        fetched = tx.find(mm.Account.where(mm.Account.id == 3)).result()
        tx.delete(fetched)

    _db(port).transact(fn)
    assert port.ops == [
        ("begin",),
        ("read", _FIND_SQL, (3,)),
        (
            "write",
            POSTGRES.to_driver_sql("delete from account where id = ? and version = ?"),
            (3, 1),
        ),
        ("commit",),
    ]


def test_delete_of_a_versioned_row_never_observed_raises() -> None:
    # An edited/deleted instance built OUTSIDE the writing transaction (never
    # fetched via THIS unit of work's own `tx.find`) carries no observation —
    # the framework never issues an implicit resolving read on behalf of a
    # keyed write, so the delete raises before any DML, exactly as an
    # unobserved keyed update does.
    port = _RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.delete(_grace())

    with pytest.raises(opt_lock.UnobservedVersionError, match="Account"):
        _db(port).transact(fn)
    assert not any(op[0] == "write" for op in port.ops)


def test_find_on_a_non_versioned_entity_records_no_observation() -> None:
    # `Transaction.find`'s observation recording is defensive: a materialized
    # node whose entity declares no `optimisticLocking` version column (every
    # Payment-family member) is skipped, never raising and never observing
    # anything a later write could consult.
    port = _RecordingPort(rows=[{"id": 1, "amount": 100.00, "card_network": "Visa"}])

    def fn(tx: Transaction) -> None:
        tx.find(im.CardPayment.where(im.CardPayment.id == 1)).result()

    _db_for(_PAYMENT, port).transact(fn)
    kinds = [op[0] for op in port.ops]
    assert kinds == ["begin", "read", "commit"]


def test_versioned_update_conflict_aborts_the_whole_unit_of_work() -> None:
    # m-opt-lock's `updatedRows != 1` conflict signal, at the production
    # developer surface: the gated UPDATE's port-reported affected count (0,
    # simulating a concurrent writer) disagrees with the flush plan's
    # exactly-one expectation, so `OptimisticLockConflictError` raises and the
    # whole unit of work rolls back.
    port = _RecordingPort(
        rows=[{"id": 1, "owner": "Ada", "balance": 100.00, "version": 1}], write_affected=0
    )

    def fn(tx: Transaction) -> None:
        fetched = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(fetched.model_copy(update={"balance": Decimal("175.00")}))

    with pytest.raises(opt_lock.OptimisticLockConflictError, match="Account"):
        _db(port).transact(fn)
    assert ("rollback",) in port.ops
    write_ops = [op for op in port.ops if op[0] == "write"]
    assert len(write_ops) == 1  # the gated update, attempted once, then aborted


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


# --------------------------------------------------------------------------- #
# Phase-8 mid-phase review remediation, finding B: `Transaction.find` records #
# a TEMPORAL observation (not just a versioned one) so a locking-mode write's #
# historical-observation license (`m-opt-lock`) is REAL, not a permanent      #
# no-op — wired through `tx._buffer`'s neutral seam (the same route the       #
# conformance engine uses; the developer-facing typed temporal verbs are      #
# COR-3 Phase 8 increment 7).                                                 #
# --------------------------------------------------------------------------- #
_INFINITY_INSTANT: Final[dt.datetime] = dt.datetime(9999, 12, 31, tzinfo=dt.UTC)


def _balance_row(*, in_z: dt.datetime, out_z: dt.datetime = _INFINITY_INSTANT) -> Row:
    return {
        "bal_id": 1,
        "acct_num": "A-1",
        "val": Decimal("5.00"),
        "in_z": in_z,
        "out_z": out_z,
    }


def test_locking_mode_temporal_write_after_an_as_of_find_raises_historical_observation() -> None:
    # An as-of (historical/edge-pinned) find is the ONLY transaction-scoped
    # observation this unit of work has for Balance 1 — a locking-mode close
    # would have nothing but the shared read lock protecting a milestone that
    # is not the current one, so it raises before any DML (`m-opt-lock`
    # "Locking mode additionally requires that the observation be of the
    # current milestone").
    port = _RecordingPort(rows=[_balance_row(in_z=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))])
    db = _db_for(_BALANCE, port)

    def fn(tx: Transaction) -> None:
        tx.find(
            mm.Balance.where(mm.Balance.id == 1).as_of(
                processing=dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
            )
        )
        tx._buffer("terminate", "Balance", {"id": 1})  # pyright: ignore[reportPrivateUsage]

    with pytest.raises(opt_lock.HistoricalObservationError, match="latest-pinned"):
        db.transact(fn)  # locking is the default concurrency
    assert not any(op[0] == "write" for op in port.ops)


def test_optimistic_mode_temporal_write_after_an_as_of_find_gates_on_observed_in_z() -> None:
    # The IDENTICAL choreography under optimistic mode is licensed — the
    # observed-`in_z` gate detects staleness instead of relying on a lock.
    port = _RecordingPort(rows=[_balance_row(in_z=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))])
    db = _db_for(_BALANCE, port)

    def fn(tx: Transaction) -> None:
        tx.find(
            mm.Balance.where(mm.Balance.id == 1).as_of(
                processing=dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
            )
        )
        tx._buffer("terminate", "Balance", {"id": 1})  # pyright: ignore[reportPrivateUsage]

    db.transact(fn, concurrency="optimistic")
    write_ops = [op for op in port.ops if op[0] == "write"]
    assert len(write_ops) == 1
    sql = write_ops[0][1]
    binds = cast("tuple[object, ...]", write_ops[0][2])
    assert sql == POSTGRES.to_driver_sql(
        "update balance set out_z = ? where bal_id = ? and out_z = ? and in_z = ?"
    )
    assert binds[-1] == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


def test_locking_mode_temporal_write_after_a_latest_find_is_licensed() -> None:
    # An OMITTED axis (the default-latest pin) licenses a locking-mode write:
    # the read observed the CURRENT milestone, so the shared read lock
    # genuinely protects the row the ungated close targets.
    port = _RecordingPort(rows=[_balance_row(in_z=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))])
    db = _db_for(_BALANCE, port)

    def fn(tx: Transaction) -> None:
        tx.find(mm.Balance.where(mm.Balance.id == 1))
        tx._buffer("terminate", "Balance", {"id": 1})  # pyright: ignore[reportPrivateUsage]

    db.transact(fn)  # locking (default) — must not raise
    write_ops = [op for op in port.ops if op[0] == "write"]
    assert len(write_ops) == 1
    sql = write_ops[0][1]
    assert sql == POSTGRES.to_driver_sql(
        "update balance set out_z = ? where bal_id = ? and out_z = ?"
    )


def test_record_observations_captures_bitemporal_business_bounds_and_payload() -> None:
    # Finding B's completeness half ("record the observation fields temporal
    # lowering already consumes ... so a transaction-scoped find -> temporal
    # write sequence works end-to-end"): a BITEMPORAL node's recorded
    # observation carries business_from/business_to/payload too — the SAME
    # fields `bitemp_write.plan` consumes for the head/middle/tail split —
    # not just the licensing `in_z`/`latest_pinned` pair the audit-only tests
    # above pin. No idiomatic `Position` mirror class is production-reachable
    # yet (bitemporal typed verbs are COR-3 Phase 8 increment 7), so this
    # drives the neutral seam directly, exactly as the conformance engine's
    # own translation layer does.
    from parallax.core.temporal_read import Pin
    from parallax.snapshot import handle, materialize

    position = models.load_models()["position"]
    node = materialize.Node(
        fields={
            "pos_id": 1,
            "acct_num": "A",
            "val": Decimal("100.00"),
            "from_z": "2024-01-01T00:00:00+00:00",
            "thru_z": "infinity",
            "in_z": "2024-01-01T00:00:00+00:00",
            "out_z": "infinity",
        },
        pk_columns=("pos_id",),
    )
    find_result = handle.FindResult(
        nodes=(node,), execution=handle.Execution(()), all_nodes=(("Position", node),)
    )
    uow = UnitOfWork(
        settings=TransactionSettings(concurrency="locking"),
        clock=FixedClock(_FIXED),
        meta=position,
        flush_executor=lambda _plan: None,
    )
    handle._record_observations(uow, position, find_result, Pin())  # pyright: ignore[reportPrivateUsage]
    observation = uow._observations[("Position", (("id", 1),))]  # pyright: ignore[reportPrivateUsage]
    assert observation.in_z == "2024-01-01T00:00:00+00:00"
    assert observation.business_from == "2024-01-01T00:00:00+00:00"
    assert observation.business_to == "infinity"
    assert observation.payload == {"id": 1, "acctNum": "A", "value": Decimal("100.00")}
    assert observation.latest_pinned is True  # an empty Pin() ⇒ omitted axis ⇒ latest


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
    # lower-level neutral document route directly (`Transaction._buffer`). An
    # otherwise-COMPLETE row isolates this defect from `validate_write` (which
    # runs first, COR-3 Phase 8 increment 2, and only ever walks Account's OWN
    # declared members — it never itself notices a stray extra key).
    port = _RecordingPort()
    with pytest.raises(WriteInstructionError, match="shoe_size"):
        _db(port).transact(
            lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage]
                "insert",
                "Account",
                {"id": 1, "owner": "Newton", "balance": 5.00, "version": 1, "shoe_size": 9},
            )
        )
    assert ("write", _INSERT_SQL, (1, 9)) not in port.ops


# --------------------------------------------------------------------------- #
# validate_write (COR-3 Phase 8 increment 2, m-value-object write validation  #
# x m-inheritance concrete-subtype write protocol): the SAME model-aware      #
# validator the conformance engine's rejected lane calls for the corpus's     #
# `when.write` cases (m-value-object-039..044 / m-inheritance-086..089) — one #
# validator, two callers (design 37 "Patterns to follow"), pinned per rule at #
# this seam. It runs BEFORE `validate_instruction` (see `_buffer`'s own       #
# comment): its inheritance payload-shape rules classify a framework-owned    #
# metadata key or a cross-branch field more specifically than the generic     #
# member-name-honesty gate ever could.                                       #
# --------------------------------------------------------------------------- #
def test_engine_and_transaction_buffer_share_the_identical_write_validator() -> None:
    # Neither caller forks its own copy of the shared validator, so a rule
    # dropped from the ONE implementation fails both lanes identically.
    from parallax.conformance import engine as engine_module
    from parallax.snapshot import handle as handle_module

    assert engine_module.validate_write is validate_write  # pyright: ignore[reportPrivateImportUsage]
    assert handle_module.validate_write is validate_write  # pyright: ignore[reportPrivateImportUsage]


def test_buffer_rejects_a_required_attribute_missing_at_any_depth() -> None:
    # m-value-object-039's own payload: `address.street` (depth 1) absent.
    port = _RecordingPort()
    with pytest.raises(WriteRejectedError) as exc_info:
        _db_for(_CONTACT, port).transact(
            lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage]
                "insert",
                "Contact",
                {
                    "id": 1,
                    "name": "Acme",
                    "address": {
                        "city": "Oslo",
                        "geo": {"country": "NO", "point": {"lat": 59.9, "lon": 10.7}},
                    },
                },
            )
        )
    assert exc_info.value.rule == "write-required-attribute-missing"


def test_buffer_rejects_a_required_value_object_missing() -> None:
    # m-value-object-044's own payload: the required top-level `destination`
    # value object is entirely absent.
    port = _RecordingPort()
    with pytest.raises(WriteRejectedError) as exc_info:
        _db_for(_SHIPMENT, port).transact(
            lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage]
                "insert", "Shipment", {"id": 5, "name": "Express"}
            )
        )
    assert exc_info.value.rule == "write-required-value-object-missing"


def test_buffer_rejects_a_value_type_mismatch() -> None:
    # m-value-object-043's own payload: `address.street` bound the number 42.
    port = _RecordingPort()
    with pytest.raises(WriteRejectedError) as exc_info:
        _db_for(_CONTACT, port).transact(
            lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage]
                "insert",
                "Contact",
                {
                    "id": 5,
                    "name": "Echo",
                    "address": {
                        "street": 42,
                        "city": "Oslo",
                        "geo": {"country": "NO", "point": {"lat": 59.9, "lon": 10.7}},
                    },
                },
            )
        )
    assert exc_info.value.rule == "write-value-type-mismatch"


def test_buffer_rejects_a_keyless_inheritance_write() -> None:
    # m-inheritance-089's own payload: no primary-key attribute at all.
    port = _RecordingPort()
    with pytest.raises(WriteRejectedError) as exc_info:
        _db_for(_PAYMENT, port).transact(
            lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage]
                "insert", "CardPayment", {"amount": 200.00, "cardNetwork": "Visa"}
            )
        )
    assert exc_info.value.rule == "subtype-write-set-based-unsupported"


def test_buffer_rejects_framework_owned_metadata() -> None:
    # m-inheritance-087's own payload: an authored `tagValue`.
    port = _RecordingPort()
    with pytest.raises(WriteRejectedError) as exc_info:
        _db_for(_PAYMENT, port).transact(
            lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage]
                "insert", "CardPayment", {"id": 10, "amount": 200.00, "tagValue": "card"}
            )
        )
    assert exc_info.value.rule == "subtype-write-metadata-field"


def test_buffer_rejects_a_sibling_branch_attribute() -> None:
    # m-inheritance-086's own payload: both CardPayment's and CashPayment's
    # own columns, so no single concrete subtype accepts every field.
    port = _RecordingPort()
    with pytest.raises(WriteRejectedError) as exc_info:
        _db_for(_PAYMENT, port).transact(
            lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage]
                "insert",
                "Payment",
                {"id": 10, "amount": 200.00, "cardNetwork": "Visa", "tendered": 25.00},
            )
        )
    assert exc_info.value.rule == "subtype-write-sibling-attribute"


def test_buffer_rejects_an_abstract_write_target() -> None:
    # m-inheritance-088's own payload: a well-formed CardPayment-shaped write
    # aimed at the abstract root `Payment`.
    port = _RecordingPort()
    with pytest.raises(WriteRejectedError) as exc_info:
        _db_for(_PAYMENT, port).transact(
            lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage]
                "insert", "Payment", {"id": 10, "amount": 200.00, "cardNetwork": "Visa"}
            )
        )
    assert exc_info.value.rule == "abstract-write-target"


def test_sparse_update_does_not_trip_required_attribute_missing_for_an_untouched_field() -> None:
    # The no-drift guard for CURRENTLY-LEGAL writes: a sparse keyed update (the
    # corpus's own m-unit-work-005 shape, `{id, balance, version}` omitting the
    # required `owner`) must NOT be rejected — an absent top-level member is
    # untouched, never a violation, on any mutation but `insert`.
    port = _RecordingPort()
    _db(port).transact(
        lambda tx: tx._buffer(  # pyright: ignore[reportPrivateUsage]
            "update", "Account", {"id": 1, "balance": 175.00, "version": 2}
        )
    )
    expected = (
        "write",
        POSTGRES.to_driver_sql("update account set balance = ?, version = ? where id = ?"),
        (175.00, 2, 1),
    )
    assert expected in port.ops


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
