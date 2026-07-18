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
from typing import Any, Final, cast

import pytest

import inheritance_models as im
import mirrored_models as mm
from parallax.conformance import models, stale_web_edit
from parallax.conformance.story_models import Order
from parallax.core import AsOfAttribute, Attr, Entity, EntityConfig, Field, inheritance, opt_lock
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import Bind, DbPort, JsonDocument, Row
from parallax.core.descriptor import Metamodel
from parallax.core.dialect import POSTGRES
from parallax.core.entity import metamodel
from parallax.core.entity.value_object import ValueObject, VoField
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
_PERSON = models.load_models()["person"]
_ORDERS = models.load_models()["orders"]
_FIXED = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


# A LOCAL bitemporal entity (no shared mirror exists for `models/position.yaml`
# yet) — the `_where`-verb materialization tests' own bounded/plain rectangle-
# split fixture.
class WherePosition(Entity, frozen=True):
    __parallax__ = EntityConfig(
        table="where_position",
        namespace="parallax.compatibility",
        mutability="transactional",
        as_of=(
            AsOfAttribute(
                name="businessDate", from_column="from_z", to_column="thru_z", axis="business"
            ),
            AsOfAttribute(
                name="processingDate", from_column="in_z", to_column="out_z", axis="processing"
            ),
        ),
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    acct_num: Attr[str] = Field(max_length=32)
    value: Attr[Decimal] = Field(type="decimal(18,2)")
    business_from: Attr[dt.datetime] = Field(column="from_z")
    business_to: Attr[dt.datetime] = Field(column="thru_z")
    processing_from: Attr[dt.datetime] = Field(column="in_z")
    processing_to: Attr[dt.datetime] = Field(column="out_z")


_WHERE_POSITION_META = metamodel([WherePosition])


# A LOCAL audit-only, value-object-bearing entity — the `supplier.yaml` shape
# (`m-value-object-047`'s own model) has no idiomatic mirror class yet (ledger
# D-21), so the VO-bearing `update_where` carry-forward pin (finding 2, D-26)
# builds its own minimal fixture rather than waiting on that mirror.
class WhereLedgerAddress(ValueObject, frozen=True):
    city: Attr[str] = VoField(type="string")


class WhereLedger(Entity, frozen=True):
    __parallax__ = EntityConfig(
        table="where_ledger",
        namespace="parallax.compatibility",
        mutability="transactional",
        as_of=(
            AsOfAttribute(
                name="processingDate", from_column="in_z", to_column="out_z", axis="processing"
            ),
        ),
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    name: Attr[str] = Field(max_length=64)
    address: Attr[WhereLedgerAddress | None] = Field(nullable=True, default=None)
    processing_from: Attr[dt.datetime] = Field(column="in_z")
    processing_to: Attr[dt.datetime] = Field(column="out_z")


_WHERE_LEDGER_META = metamodel([WhereLedger])


# A LOCAL bitemporal, value-object-bearing entity — confirmation-pass residual
# P2's own fixture (`m-case-format.md:727`; no corpus witness exercises a
# VO-bearing bitemporal predicate update, D-26): combines `WherePosition`'s
# two axes with `WhereLedger`'s value-object shape.
class WhereRectangleAddress(ValueObject, frozen=True):
    city: Attr[str] = VoField(type="string")


class WhereRectangle(Entity, frozen=True):
    __parallax__ = EntityConfig(
        table="where_rectangle",
        namespace="parallax.compatibility",
        mutability="transactional",
        as_of=(
            AsOfAttribute(
                name="businessDate", from_column="from_z", to_column="thru_z", axis="business"
            ),
            AsOfAttribute(
                name="processingDate", from_column="in_z", to_column="out_z", axis="processing"
            ),
        ),
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    acct_num: Attr[str] = Field(max_length=32)
    value: Attr[Decimal] = Field(type="decimal(18,2)")
    address: Attr[WhereRectangleAddress | None] = Field(nullable=True, default=None)
    business_from: Attr[dt.datetime] = Field(column="from_z")
    business_to: Attr[dt.datetime] = Field(column="thru_z")
    processing_from: Attr[dt.datetime] = Field(column="in_z")
    processing_to: Attr[dt.datetime] = Field(column="out_z")


_WHERE_RECTANGLE_META = metamodel([WhereRectangle])


# A LOCAL versioned NON-TEMPORAL, value-object-bearing entity — mirrors
# `models/subscriber.yaml`'s own shape (a versioned document owner) —
# confirmation-pass residual A's own fixture (round 2, `handle.py:1733`): TWO
# value objects, so a pin can prove minimal-read discipline (the resolving
# read projects the ASSIGNED document only, never every declared one).
class WhereSubscriberAddress(ValueObject, frozen=True):
    city: Attr[str] = VoField(type="string")


class WhereSubscriberProfile(ValueObject, frozen=True):
    bio: Attr[str] = VoField(type="string")


class WhereSubscriber(Entity, frozen=True):
    __parallax__ = EntityConfig(
        table="where_subscriber", namespace="parallax.compatibility", mutability="transactional"
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    version: Attr[int] = Field(type="int32", optimistic_locking=True)
    address: Attr[WhereSubscriberAddress | None] = Field(nullable=True, default=None)
    profile: Attr[WhereSubscriberProfile | None] = Field(nullable=True, default=None)


_WHERE_SUBSCRIBER_META = metamodel([WhereSubscriber])

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
    ``write_affected_queue`` (COR-3 Phase 8 increment 6) scripts a SEQUENCE of
    affected-row counts across successive ``execute_write`` calls — an
    optimistic-lock retry-loop probe's own oracle: attempt 0's gated UPDATE
    affects ``0`` (the conflict), a retried attempt's affects ``1`` (success) —
    falling back to the constant ``write_affected`` once exhausted (or when
    never set, unaffected — every existing single-affected-count caller is
    unchanged).
    """

    def __init__(self, *, rows: Sequence[Row] = (), write_affected: int = 1) -> None:
        self.ops: list[tuple[object, ...]] = []
        self.rows = list(rows)
        self.write_affected = write_affected
        self.write_affected_queue: list[int] = []
        self.txn_faults: list[DatabaseError] = []
        self.read_faults: list[DatabaseError] = []

    def execute(self, sql: str, binds: Sequence[Bind]) -> list[Row]:
        if self.read_faults:
            raise self.read_faults.pop(0)
        self.ops.append(("read", sql, tuple(binds)))
        return [dict(row) for row in self.rows]

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        self.ops.append(("write", sql, tuple(binds)))
        if self.write_affected_queue:
            return self.write_affected_queue.pop(0)
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
# no-op — exercised through the typed `tx.terminate` verb (COR-3 Phase 8      #
# increment 7), the SAME `_buffer` neutral seam the conformance engine uses.  #
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
        fetched = tx.find(
            mm.Balance.where(mm.Balance.id == 1).as_of(
                processing=dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
            )
        ).result()
        tx.terminate(fetched)

    with pytest.raises(opt_lock.HistoricalObservationError, match="latest-pinned"):
        db.transact(fn)  # locking is the default concurrency
    assert not any(op[0] == "write" for op in port.ops)


def test_optimistic_mode_temporal_write_after_an_as_of_find_gates_on_observed_in_z() -> None:
    # The IDENTICAL choreography under optimistic mode is licensed — the
    # observed-`in_z` gate detects staleness instead of relying on a lock.
    port = _RecordingPort(rows=[_balance_row(in_z=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))])
    db = _db_for(_BALANCE, port)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(
            mm.Balance.where(mm.Balance.id == 1).as_of(
                processing=dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
            )
        ).result()
        tx.terminate(fetched)

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
        fetched = tx.find(mm.Balance.where(mm.Balance.id == 1)).result()
        tx.terminate(fetched)

    db.transact(fn)  # locking (default) — must not raise
    write_ops = [op for op in port.ops if op[0] == "write"]
    assert len(write_ops) == 1
    sql = write_ops[0][1]
    assert sql == POSTGRES.to_driver_sql(
        "update balance set out_z = ? where bal_id = ? and out_z = ?"
    )


def test_audit_only_update_via_a_sparse_edited_copy_carries_the_untouched_field() -> None:
    # D-30 (COR-3 Phase 8 increment 7 completion round) — the revert-to-red
    # regression pin: a real, PUBLIC `tx.update` of a SPARSE edited copy
    # (`model_copy` touching ONLY `value`, never `acct_num`) against a genuine
    # in-transaction observation (`tx.find`, same as every other keyed-write
    # story here) still chains a row carrying `acct_num` — the merge onto the
    # observed payload (`audit_write.plan`'s own `_merged_row`), never a
    # silent drop of the untouched field. Reverting the D-30 fix (chaining
    # `instruction.rows[0]` verbatim instead of the merged row) makes this
    # assertion fail with `chain_binds[1] is None` (the sparse row carries no
    # `acctNum` at all) instead of `"A-1"` — proven by hand against the
    # pre-fix `audit_write.plan` during development of this pin.
    port = _RecordingPort(rows=[_balance_row(in_z=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))])
    db = _db_for(_BALANCE, port)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(mm.Balance.where(mm.Balance.id == 1)).result()
        tx.update(fetched.model_copy(update={"value": Decimal("150.00")}))

    db.transact(fn)
    write_ops = [op for op in port.ops if op[0] == "write"]
    assert len(write_ops) == 2  # the ungated close, then the merged chain
    close_sql, close_binds = write_ops[0][1], write_ops[0][2]
    assert close_sql == POSTGRES.to_driver_sql(
        "update balance set out_z = ? where bal_id = ? and out_z = ?"
    )
    assert close_binds == ("2024-06-01T00:00:00+00:00", 1, "infinity")
    chain_sql, chain_binds = write_ops[1][1], write_ops[1][2]
    assert chain_sql == POSTGRES.to_driver_sql(
        "insert into balance(bal_id, acct_num, val, in_z, out_z) values (?, ?, ?, ?, ?)"
    )
    assert chain_binds == (1, "A-1", Decimal("150.00"), "2024-06-01T00:00:00+00:00", "infinity")


# --------------------------------------------------------------------------- #
# D-31 (COR-3 Phase 8 increment 7 completion round): axis-attribute           #
# construction optionality + `tx.insert_until`, through the PUBLIC verbs.     #
# --------------------------------------------------------------------------- #
def test_bitemporal_insert_constructs_cleanly_and_stamps_the_business_from() -> None:
    branch = mm.Branch(id=1, name="Central", address=None)  # no placeholder axis values
    port = _RecordingPort()
    db = _db_for(models.load_models()["branch"], port)

    db.transact(lambda tx: tx.insert(branch, business_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC)))
    write_ops = [op for op in port.ops if op[0] == "write"]
    assert len(write_ops) == 1
    sql = write_ops[0][1]
    binds = cast("tuple[object, ...]", write_ops[0][2])
    assert sql == POSTGRES.to_driver_sql(
        "insert into branch(br_id, name, from_z, thru_z, in_z, out_z, address) "
        "values (?, ?, ?, ?, ?, ?, ?)"
    )
    assert binds[2:6] == (
        "2024-01-01T00:00:00+00:00",
        "infinity",
        "2024-06-01T00:00:00+00:00",
        "infinity",
    )


def test_bitemporal_insert_until_opens_a_single_bounded_rectangle() -> None:
    branch = mm.Branch(id=1, name="Central", address=None)
    port = _RecordingPort()
    db = _db_for(models.load_models()["branch"], port)

    db.transact(
        lambda tx: tx.insert_until(
            branch,
            business_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
            until=dt.datetime(2024, 9, 1, tzinfo=dt.UTC),
        )
    )
    write_ops = [op for op in port.ops if op[0] == "write"]
    assert len(write_ops) == 1
    binds = cast("tuple[object, ...]", write_ops[0][2])
    assert binds[2:6] == (
        "2024-03-01T00:00:00+00:00",
        "2024-09-01T00:00:00+00:00",
        "2024-06-01T00:00:00+00:00",
        "infinity",
    )


def test_insert_until_rejects_an_equal_or_reversed_window() -> None:
    branch = mm.Branch(id=1, name="Central", address=None)
    port = _RecordingPort()
    db = _db_for(models.load_models()["branch"], port)
    same_instant = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
    with pytest.raises(ValueError, match="business_from < until"):
        db.transact(
            lambda tx: tx.insert_until(branch, business_from=same_instant, until=same_instant)
        )
    assert not any(op[0] == "write" for op in port.ops)


def test_a_materialized_temporal_node_still_populates_real_axis_values() -> None:
    # D-31's construction optionality only affects a FRESH instance — a
    # materialized read explicitly passes every fetched column, so the
    # resulting node's axis fields are the row's own REAL values, never `None`.
    port = _RecordingPort(rows=[_balance_row(in_z=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))])
    db = _db_for(_BALANCE, port)
    fetched = db.transact(lambda tx: tx.find(mm.Balance.where(mm.Balance.id == 1)).result())
    assert fetched.processing_from == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    assert fetched.processing_to is not None


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


def test_record_observations_keep_the_bitemporal_document_for_keyed_carry_forward() -> None:
    # Confirmation-pass residual P2, second-caller question: the SAME
    # `_temporal_observation` `_record_observations` drives for every real
    # `tx.find` is the one `Transaction._materialize_predicate_write`'s own
    # materializing resolve reuses (`test_materializing_...bitemporal...`
    # below) — a production KEYED write (a later `tx.update(copy)`/
    # `tx.terminate` of a row this SAME unit of work already `tx.find`-
    # observed) derives its `bitemp_write.plan` head/tail carry-forward from
    # THIS recorded observation's own payload, so it must not silently drop a
    # value-object document either. `find`'s own read is always INSTANCE-form
    # (`m-sql`), which projects every document unconditionally, so `node.
    # fields` already carries `address` here — proving the gap was
    # `_temporal_observation` never asking to KEEP it, not a missing
    # projection (unlike the materializing-resolve half, `needs_documents`).
    from parallax.core.temporal_read import Pin
    from parallax.snapshot import handle, materialize

    branch = models.load_models()["branch"]
    address: dict[str, object] = {
        "street": "10 Old Road",
        "city": "Helsinki",
        "geo": {"country": "FI"},
        "phones": [],
    }
    node = materialize.Node(
        fields={
            "br_id": 1,
            "name": "Central Branch",
            "address": address,
            "from_z": "2024-01-01T00:00:00+00:00",
            "thru_z": "infinity",
            "in_z": "2024-01-01T00:00:00+00:00",
            "out_z": "infinity",
        },
        pk_columns=("br_id",),
    )
    find_result = handle.FindResult(
        nodes=(node,), execution=handle.Execution(()), all_nodes=(("Branch", node),)
    )
    uow = UnitOfWork(
        settings=TransactionSettings(concurrency="locking"),
        clock=FixedClock(_FIXED),
        meta=branch,
        flush_executor=lambda _plan: None,
    )
    handle._record_observations(uow, branch, find_result, Pin())  # pyright: ignore[reportPrivateUsage]
    observation = uow._observations[("Branch", (("id", 1),))]  # pyright: ignore[reportPrivateUsage]
    assert observation.payload == {"id": 1, "name": "Central Branch", "address": address}


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
    # This corpus case's own idiomatic-surface spelling is unreachable through
    # `tx.insert` (Pydantic's own field coercion raises first, constructing
    # `ContactAddress(street=42, ...)` never even completes) — a SANCTIONED
    # exception, ledger D-32 (S5, COR-3 Phase 8 increment 7 remediation), so
    # this proof exercises the shared validator directly through the private
    # `_buffer` seam instead, exactly like its two siblings above.
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
    # The no-drift guard for CURRENTLY-LEGAL writes: a sparse keyed update (an id +
    # balance row omitting the required `owner`) must NOT be rejected — an absent
    # top-level member is untouched, never a violation, on any mutation but
    # `insert`. The version advances from this unit of work's own recorded
    # observation (`tx.find`), never a row-carried value (`m-opt-lock`).
    port = _RecordingPort(rows=[{"id": 1, "owner": "Ada", "balance": 100.00, "version": 1}])

    def fn(tx: Transaction) -> None:
        tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx._buffer(  # pyright: ignore[reportPrivateUsage]
            "update", "Account", {"id": 1, "balance": 175.00}
        )

    _db(port).transact(fn)
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


# --------------------------------------------------------------------------- #
# Optimistic-lock conflict opt-in (m-opt-lock "Retry contract"; m-auto-retry, #
# COR-3 Phase 8 increment 6): `retry_optimistic_conflicts` joins             #
# `OptimisticLockConflictError` to the retriable set — the SAME `0`-then-`1`  #
# affected-rows transition `m-opt-lock-009` witnesses against real Postgres,  #
# reproduced here with a scripted `write_affected_queue` fake port.           #
# --------------------------------------------------------------------------- #
def _observe_and_update(tx: Transaction) -> None:
    current = tx.find(mm.Account.where(mm.Account.id == 3)).result()
    tx.update(current.model_copy(update={"balance": Decimal("20.00")}))


def test_optimistic_conflict_surfaces_after_one_attempt_without_the_opt_in() -> None:
    port = _RecordingPort(rows=[{"id": 3, "owner": "Grace", "balance": 10.00, "version": 1}])
    port.write_affected_queue = [0]
    with pytest.raises(opt_lock.OptimisticLockConflictError):
        _db(port).transact(_observe_and_update, concurrency="optimistic")
    assert port.begins == 1


def test_optimistic_conflict_is_auto_retried_to_success_with_the_opt_in() -> None:
    port = _RecordingPort(rows=[{"id": 3, "owner": "Grace", "balance": 10.00, "version": 1}])
    port.write_affected_queue = [0, 1]
    _db(port).transact(
        _observe_and_update, concurrency="optimistic", retry_optimistic_conflicts=True
    )
    assert port.begins == 2  # the conflicting attempt, then the retried (successful) attempt


def test_optimistic_conflict_opt_in_exhausts_its_bound() -> None:
    port = _RecordingPort(rows=[{"id": 3, "owner": "Grace", "balance": 10.00, "version": 1}])
    port.write_affected_queue = [0, 0, 0]  # persistent — every attempt conflicts
    with pytest.raises(opt_lock.OptimisticLockConflictError) as excinfo:
        _db(port).transact(
            _observe_and_update,
            concurrency="optimistic",
            retries=2,
            retry_optimistic_conflicts=True,
        )
    assert port.begins == 3
    assert "3 attempts (retries=2)" in "".join(excinfo.value.__notes__)


def test_optimistic_conflict_opt_in_is_inert_for_a_transient_failure() -> None:
    # The opt-in gates ONLY the conflict classification branch; a transient
    # database failure is retriable regardless of the flag's value (m-auto-retry
    # "Which failures are retriable" — transients are always retriable). This
    # RETRIABLE deadlock is classified retriable by `_retriable_failure` alone
    # (the `or`'s left operand), so it never actually reaches the opt-in's own
    # predicate at all — see the NON-retriable sibling below for that.
    port = _RecordingPort()
    port.txn_faults = [_deadlock()]
    assert _db(port).transact(lambda _tx: "ok", retry_optimistic_conflicts=True) == "ok"
    assert port.begins == 2


def test_optimistic_conflict_opt_in_is_inert_for_a_non_retriable_database_error() -> None:
    # A NON-retriable `DatabaseError` (neither a direct
    # `OptimisticLockConflictError` nor a `RollbackOnlyError` wrapping one)
    # reaches the opt-in's own predicate (`_optimistic_conflict_retriable`,
    # since `_retriable_failure` alone already calls it non-retriable) and
    # is classified non-retriable there too — the opt-in's structural
    # extension never widens the retriable set beyond the optimistic-lock
    # conflict shape itself.
    port = _RecordingPort()
    port.txn_faults = [
        DatabaseError(category="uniqueViolation", native_code="23505", message="dup")
    ]
    with pytest.raises(DatabaseError):
        _db(port).transact(lambda _tx: "ok", retry_optimistic_conflicts=True)
    assert port.begins == 1


def test_optimistic_conflict_opt_in_is_inert_in_locking_mode() -> None:
    # Locking mode never gates a versioned UPDATE (`m-opt-lock` "the version
    # column" — the shared read lock, not a version check, is what makes the
    # write correct), so there is nothing for the opt-in to ever retry: a
    # single-attempt commit, `retry_optimistic_conflicts` notwithstanding.
    port = _RecordingPort(rows=[{"id": 3, "owner": "Grace", "balance": 10.00, "version": 1}])
    _db(port).transact(_observe_and_update, concurrency="locking", retry_optimistic_conflicts=True)
    assert port.begins == 1


def _observe_update_then_force_flush(tx: Transaction) -> None:
    current = tx.find(mm.Account.where(mm.Account.id == 3)).result()
    tx.update(current.model_copy(update={"balance": Decimal("20.00")}))
    tx.find(mm.Account.where(mm.Account.id == 3))  # forces the flush inside THIS (joined) scope


def test_optimistic_conflict_rollback_only_cause_is_retried_with_the_opt_in() -> None:
    # Spec §5's join rule extended to an optimistic-lock conflict (pinned
    # semantics #5): a JOINED scope's own conflict, discovered by its OWN
    # forced flush (read-your-own-writes), dooms the ROOT rollback-only; the
    # outer callback catches it and returns normally, but commit is refused —
    # the outermost retry loop still applies per the ORIGINAL failure's
    # category (the conflict, not a `DatabaseError`), retriable here because
    # the opt-in is set.
    port = _RecordingPort(rows=[{"id": 3, "owner": "Grace", "balance": 10.00, "version": 1}])
    port.write_affected_queue = [0, 1]
    db = _db(port)

    def outer(_tx: Transaction) -> str:
        with contextlib.suppress(opt_lock.OptimisticLockConflictError):
            db.transact(_observe_update_then_force_flush)  # joins; conflicts mid-scope
        return "caught"

    assert db.transact(outer, concurrency="optimistic", retry_optimistic_conflicts=True) == "caught"
    assert port.begins == 2  # the conflicting attempt, then the retried (successful) attempt


# --------------------------------------------------------------------------- #
# Predicate-selected `_where` verb family (COR-3 Phase 8 increment 5;          #
# python.md §5): the bare-statement guard, inheritance rejection, business-    #
# bound validation, readless dispatch, and materialization (resolve + per-row #
# no-op elimination + the atomic-unit buffering, ADR 0014).                    #
# --------------------------------------------------------------------------- #
def test_readless_update_where_buffers_one_statement_no_read() -> None:
    port = _RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.update_where(mm.Person.where(mm.Person.id == 1), mm.Person.name.set("Ada"))

    Database.connect(port, _PERSON, clock=FixedClock(_FIXED)).transact(fn)
    assert port.ops == [
        ("begin",),
        ("write", POSTGRES.to_driver_sql("update person set name = ? where id = ?"), ("Ada", 1)),
        ("commit",),
    ]


def test_readless_delete_where_buffers_one_statement_no_read() -> None:
    port = _RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.delete_where(mm.Person.where(mm.Person.id == 1))

    Database.connect(port, _PERSON, clock=FixedClock(_FIXED)).transact(fn)
    assert port.ops == [
        ("begin",),
        ("write", POSTGRES.to_driver_sql("delete from person where id = ?"), (1,)),
        ("commit",),
    ]


def test_readless_update_where_reorders_assignments_to_column_order() -> None:
    # Round-6 remaining (c): the SET clause orders by descriptor column order
    # (`_lower_predicate_write`'s own `_ordered_cells` reuse), never the
    # AUTHORED assignment order -- reversing the two `.set(...)` calls below
    # (price before name, the opposite of Order's own declared column order)
    # emits BYTE-IDENTICAL SQL to the natural order (mirrors `test_insert_
    # orders_columns_by_column_order_not_row_order`'s own insert-side proof).
    forward_port = _RecordingPort()

    def forward(tx: Transaction) -> None:
        tx.update_where(
            Order.where(Order.id == 100),
            Order.name.set("Hopper"),
            Order.price.set(Decimal("9.99")),
        )

    Database.connect(forward_port, _ORDERS, clock=FixedClock(_FIXED)).transact(forward)

    reordered_port = _RecordingPort()

    def reordered(tx: Transaction) -> None:
        tx.update_where(
            Order.where(Order.id == 100),
            Order.price.set(Decimal("9.99")),
            Order.name.set("Hopper"),
        )

    Database.connect(reordered_port, _ORDERS, clock=FixedClock(_FIXED)).transact(reordered)

    assert forward_port.ops == reordered_port.ops
    assert forward_port.ops == [
        ("begin",),
        (
            "write",
            POSTGRES.to_driver_sql("update orders set name = ?, price = ? where id = ?"),
            ("Hopper", Decimal("9.99"), 100),
        ),
        ("commit",),
    ]


def test_where_verb_rejects_a_non_bare_statement() -> None:
    port = _RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.delete_where(mm.Person.where(mm.Person.id == 1).limit(1))

    with pytest.raises(ValueError, match="bare statement"):
        Database.connect(port, _PERSON, clock=FixedClock(_FIXED)).transact(fn)
    assert not any(op[0] == "write" for op in port.ops)


def test_where_verb_rejects_an_inheritance_family_target() -> None:
    port = _RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.update_where(
            im.CardPayment.where(im.CardPayment.id == 1), im.CardPayment.amount.set(Decimal("1.00"))
        )

    with pytest.raises(inheritance.InheritanceError, match="subtype-write-set-based-unsupported"):
        Database.connect(port, _PAYMENT, clock=FixedClock(_FIXED)).transact(fn)
    assert not any(op[0] in ("read", "write") for op in port.ops)


def test_bitemporal_where_verb_requires_business_from() -> None:
    port = _RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.update_where(
            WherePosition.where(WherePosition.id == 1), WherePosition.value.set(Decimal("1.00"))
        )

    with pytest.raises(ValueError, match="requires business_from"):
        Database.connect(port, _WHERE_POSITION_META, clock=FixedClock(_FIXED)).transact(fn)


def test_audit_only_where_verb_forbids_business_from() -> None:
    port = _RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.terminate_where(mm.Balance.where(mm.Balance.id == 1), business_from=_FIXED)

    with pytest.raises(ValueError, match="takes no business_from"):
        Database.connect(port, _BALANCE, clock=FixedClock(_FIXED)).transact(fn)


def test_non_temporal_where_verb_forbids_business_from() -> None:
    port = _RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.update_where(
            mm.Person.where(mm.Person.id == 1), mm.Person.name.set("Ada"), business_from=_FIXED
        )

    with pytest.raises(ValueError, match="takes no business_from"):
        Database.connect(port, _PERSON, clock=FixedClock(_FIXED)).transact(fn)


def test_materializing_update_where_skips_no_op_rows_and_gates_the_rest() -> None:
    # m-opt-lock-014's own shape: TWO resolved rows, one already equal to the
    # assigned value (skipped: no DML, no version advance), one genuinely
    # changed (one gated per-row UPDATE).
    port = _RecordingPort(
        rows=[
            {"id": 1, "owner": "Ada", "balance": 100.00, "version": 1},
            {"id": 3, "owner": "Grace", "balance": 10.00, "version": 1},
        ]
    )

    def fn(tx: Transaction) -> None:
        tx.update_where(
            mm.Account.where(mm.Account.balance < 200), mm.Account.balance.set(Decimal("100.00"))
        )

    _db(port).transact(fn, concurrency="optimistic")
    kinds = [op[0] for op in port.ops]
    assert kinds == ["begin", "read", "write", "commit"]
    write_sql, write_binds = port.ops[2][1], port.ops[2][2]
    assert write_sql == POSTGRES.to_driver_sql(
        "update account set balance = ?, version = ? where id = ? and version = ?"
    )
    assert write_binds == (100.00, 2, 3, 1)  # account 1's no-op row never wrote


def test_materializing_delete_where_writes_every_resolved_row() -> None:
    # m-opt-lock-015's own shape: delete has no assignment equality to test,
    # so every resolved row writes — N always equals the resolved-row count.
    port = _RecordingPort(
        rows=[
            {"id": 1, "owner": "Ada", "balance": 100.00, "version": 1},
            {"id": 3, "owner": "Grace", "balance": 10.00, "version": 1},
        ]
    )

    def fn(tx: Transaction) -> None:
        tx.delete_where(mm.Account.where(mm.Account.balance < 200))

    _db(port).transact(fn, concurrency="optimistic")
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 2
    assert writes[0][2] == (1, 1)
    assert writes[1][2] == (3, 1)


def test_materializing_write_with_zero_resolved_rows_writes_nothing() -> None:
    # DQ2 rider 4 / m-batch-write.md "Zero resolved rows -> zero keyed writes,
    # success" — a materializing write that resolves nothing still commits
    # cleanly, with no keyed writes at all.
    port = _RecordingPort(rows=[])

    def fn(tx: Transaction) -> None:
        tx.delete_where(mm.Account.where(mm.Account.balance < 0))

    _db(port).transact(fn)
    assert port.ops == [("begin",), ("read", port.ops[1][1], port.ops[1][2]), ("commit",)]
    assert not any(op[0] == "write" for op in port.ops)


def _two_terminate_rows() -> list[Row]:
    return [
        {
            "bal_id": 1,
            "acct_num": "A",
            "val": 150.00,
            "in_z": "2024-01-01T00:00:00+00:00",
            "out_z": "infinity",
        },
        {
            "bal_id": 2,
            "acct_num": "B",
            "val": 50.00,
            "in_z": "2024-02-01T00:00:00+00:00",
            "out_z": "infinity",
        },
    ]


def test_materializing_terminate_where_over_an_audit_only_target() -> None:
    # LOCKING mode (the default): every resolved row gets its own close, in
    # the resolving read's own resolved-row order, and every close stays
    # UNGATED (`m-audit-write` "a LOCKING-mode close stays ungated" —
    # `~parallax.core.opt_lock.gates` only ever binds the observed-`in_z`
    # candidate under optimistic concurrency).
    port = _RecordingPort(rows=_two_terminate_rows())

    def fn(tx: Transaction) -> None:
        tx.terminate_where(mm.Balance.where(mm.Balance.value < 200))

    Database.connect(port, _BALANCE, clock=FixedClock(_FIXED)).transact(fn)
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 2  # one processing-only close per resolved row, no chain
    close_sql = POSTGRES.to_driver_sql(
        "update balance set out_z = ? where bal_id = ? and out_z = ?"
    )
    assert writes[0][1] == close_sql
    assert writes[0][2] == ("2024-06-01T00:00:00+00:00", 1, "infinity")
    assert writes[1][1] == close_sql
    assert writes[1][2] == ("2024-06-01T00:00:00+00:00", 2, "infinity")


def test_materializing_terminate_where_audit_only_gates_under_optimistic_concurrency() -> None:
    # OPTIMISTIC mode: an audit-only close GATES on the observed `in_z`,
    # binding LAST (`m-audit-write.md:65`, `m-opt-lock.md:87-99`) — every
    # resolved row's own close carries THAT row's own observed `in_z`, in
    # resolved-row order, mirroring the corpus's `m-audit-write-006` gated-
    # close shape (`m-value-object-047`'s own re-gated step 2).
    port = _RecordingPort(rows=_two_terminate_rows())

    def fn(tx: Transaction) -> None:
        tx.terminate_where(mm.Balance.where(mm.Balance.value < 200))

    Database.connect(port, _BALANCE, clock=FixedClock(_FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 2
    gated_sql = POSTGRES.to_driver_sql(
        "update balance set out_z = ? where bal_id = ? and out_z = ? and in_z = ?"
    )
    assert writes[0][1] == gated_sql
    assert writes[0][2] == ("2024-06-01T00:00:00+00:00", 1, "infinity", "2024-01-01T00:00:00+00:00")
    assert writes[1][1] == gated_sql
    assert writes[1][2] == ("2024-06-01T00:00:00+00:00", 2, "infinity", "2024-02-01T00:00:00+00:00")


def test_materializing_update_where_audit_only_chains_the_new_value() -> None:
    # `audit_write.plan` chains the instruction's OWN authored FULL row —
    # never a separate observed payload — so materialization must merge the
    # resolved row's own unassigned scalar payload (acct_num) forward itself.
    port = _RecordingPort(
        rows=[
            {
                "bal_id": 1,
                "acct_num": "A",
                "val": 150.00,
                "in_z": "2024-01-01T00:00:00+00:00",
                "out_z": "infinity",
            }
        ]
    )

    def fn(tx: Transaction) -> None:
        tx.update_where(
            mm.Balance.where(mm.Balance.value < 200), mm.Balance.value.set(Decimal("175.00"))
        )

    Database.connect(port, _BALANCE, clock=FixedClock(_FIXED)).transact(fn)
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 2  # close then chain
    chain_sql, chain_binds = writes[1][1], writes[1][2]
    assert chain_sql == POSTGRES.to_driver_sql(
        "insert into balance(bal_id, acct_num, val, in_z, out_z) values (?, ?, ?, ?, ?)"
    )
    assert chain_binds == (1, "A", 175.00, "2024-06-01T00:00:00+00:00", "infinity")


def test_materializing_update_where_audit_only_carries_the_unassigned_value_object_forward() -> (
    None
):
    # D-26 / finding 2 (`m-case-format.md:727`): an assignment-bearing
    # `update_where` on an audit-only, VALUE-OBJECT-bearing target must carry
    # the resolved row's OWN `address` document FORWARD into the chained row
    # when the caller does not itself reassign it — so the resolving read
    # must project the document column too (unlike a terminate/delete,
    # `m-value-object-047`'s own row-form-omits-slot-4 witness, which stays
    # byte-identical because it never reaches this assignment-bearing branch).
    port = _RecordingPort(
        rows=[
            {
                "id": 1,
                "name": "Nordic Foods",
                "address": {"city": "Bergen"},
                "in_z": "2024-01-01T00:00:00+00:00",
                "out_z": "infinity",
            }
        ]
    )

    def fn(tx: Transaction) -> None:
        tx.update_where(
            WhereLedger.where(WhereLedger.id == 1), WhereLedger.name.set("Baltic Traders")
        )

    Database.connect(port, _WHERE_LEDGER_META, clock=FixedClock(_FIXED)).transact(fn)
    reads = [op for op in port.ops if op[0] == "read"]
    writes = [op for op in port.ops if op[0] == "write"]
    assert reads[0][1] == POSTGRES.to_driver_sql(
        "select t0.id, t0.name, t0.in_z, t0.out_z, t0.address from where_ledger t0 "
        "where t0.id = ? and t0.out_z = ? for share of t0"
    )
    assert len(writes) == 2  # close then chain
    chain_sql, chain_binds = writes[1][1], writes[1][2]
    assert chain_sql == POSTGRES.to_driver_sql(
        "insert into where_ledger(id, name, in_z, out_z, address) values (?, ?, ?, ?, ?)"
    )
    assert chain_binds == (
        1,
        "Baltic Traders",
        "2024-06-01T00:00:00+00:00",
        "infinity",
        JsonDocument({"city": "Bergen"}),
    )


def _position_row() -> Row:
    return {
        "id": 1,
        "acct_num": "A",
        "value": 200.00,
        "from_z": "2024-01-01T00:00:00+00:00",
        "thru_z": "infinity",
        "in_z": "2024-01-01T00:00:00+00:00",
        "out_z": "infinity",
    }


def _position_row_dt() -> Row:
    """The KEYED-verb tests' own row fixture: real ``datetime`` values (never
    the bare ISO strings :func:`_position_row` uses) — a KEYED verb's own
    first read runs through the ordinary developer-facing ``tx.find`` (wrap
    into a real node, milestone-edge computation, `parallax.snapshot.wrap`),
    unlike a ``_where`` verb's internal resolving read, which never wraps."""
    return {
        "id": 1,
        "acct_num": "A",
        "value": Decimal("100.00"),
        "from_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "thru_z": _INFINITY_INSTANT,
        "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "out_z": _INFINITY_INSTANT,
    }


def test_materializing_plain_update_where_over_a_bitemporal_target() -> None:
    port = _RecordingPort(rows=[_position_row()])
    business_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.update_where(
            WherePosition.where(WherePosition.id == 1),
            WherePosition.value.set(Decimal("300.00")),
            business_from=business_from,
        )

    Database.connect(port, _WHERE_POSITION_META, clock=FixedClock(_FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 3  # close + head (old) + new tail


def test_materializing_plain_terminate_where_over_a_bitemporal_target() -> None:
    port = _RecordingPort(rows=[_position_row()])
    business_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.terminate_where(WherePosition.where(WherePosition.id == 1), business_from=business_from)

    Database.connect(port, _WHERE_POSITION_META, clock=FixedClock(_FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 2  # close + head only (no tail)


def test_materializing_update_until_where_over_a_bitemporal_target() -> None:
    port = _RecordingPort(rows=[_position_row()])
    business_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.update_until_where(
            WherePosition.where(WherePosition.id == 1),
            WherePosition.value.set(Decimal("300.00")),
            business_from=business_from,
            until=until,
        )

    Database.connect(port, _WHERE_POSITION_META, clock=FixedClock(_FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 4  # close + head + middle + tail


def test_materializing_terminate_until_where_over_a_bitemporal_target() -> None:
    port = _RecordingPort(rows=[_position_row()])
    business_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.terminate_until_where(
            WherePosition.where(WherePosition.id == 1), business_from=business_from, until=until
        )

    Database.connect(port, _WHERE_POSITION_META, clock=FixedClock(_FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 3  # close + head + tail (no middle)


def test_materializing_terminate_until_where_writes_per_resolved_row() -> None:
    # Round-6 remaining (a): the single-row pin above proves the PER-ROW shape
    # (close + head + tail); this proves the MATERIALIZE loop itself resolves
    # and writes MULTIPLE rows, exactly like `update_where`'s / `delete_where`'s
    # own multi-row pins -- N resolved rows -> 3*N keyed writes, no cross-row
    # elision (`m-opt-lock.md` "Predicate-selected writes materialize when
    # observations are needed").
    port = _RecordingPort(rows=[_position_row(), {**_position_row(), "id": 2}])
    business_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.terminate_until_where(
            WherePosition.where(WherePosition.value < 999),
            business_from=business_from,
            until=until,
        )

    Database.connect(port, _WHERE_POSITION_META, clock=FixedClock(_FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 6  # 2 resolved rows * (close + head + tail)


def _rectangle_row(*, address: dict[str, object] | None) -> Row:
    return {
        "id": 1,
        "acct_num": "A",
        "value": 200.00,
        "address": address,
        "from_z": "2024-01-01T00:00:00+00:00",
        "thru_z": "infinity",
        "in_z": "2024-01-01T00:00:00+00:00",
        "out_z": "infinity",
    }


def test_materializing_bitemporal_update_where_carries_the_unassigned_value_object() -> None:
    # Confirmation-pass residual P2 (`m-case-format.md:727`): a BITEMPORAL,
    # value-object-bearing target's assignment-bearing `update_where` must
    # project the document in its resolving read too (the prior round's gate
    # covered only an AUDIT-ONLY target) — the resolved row's own `address`
    # rides head AND the new tail WHOLE when the caller does not itself
    # reassign it (`m-bitemp-write` "head/tail old values come from the
    # observed prior rectangle"; `m-value-object` "the document rides every
    # chained/split row whole" — never decomposed).
    address: dict[str, object] = {"city": "Helsinki"}
    port = _RecordingPort(rows=[_rectangle_row(address=address)])
    business_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.update_where(
            WhereRectangle.where(WhereRectangle.id == 1),
            WhereRectangle.value.set(Decimal("300.00")),
            business_from=business_from,
        )

    Database.connect(port, _WHERE_RECTANGLE_META, clock=FixedClock(_FIXED)).transact(
        fn, concurrency="optimistic"
    )
    reads = [op for op in port.ops if op[0] == "read"]
    writes = [op for op in port.ops if op[0] == "write"]
    assert "t0.address" in cast("str", reads[0][1])  # the need-sensitive projection fired
    assert len(writes) == 3  # close + head (old) + new tail
    head_binds = cast("tuple[object, ...]", writes[1][2])
    tail_binds = cast("tuple[object, ...]", writes[2][2])
    assert head_binds[-1] == JsonDocument(address)  # head: OLD value, unreassigned document
    assert tail_binds[-1] == JsonDocument(address)  # new tail: NEW value, SAME document
    assert tail_binds[2] == Decimal("300.00")  # the assigned scalar column DOES take the new value


def test_materializing_update_until_where_bitemporal_carries_the_value_object_on_every_chain() -> (
    None
):
    # The full rectangle split (`m-bitemp-write-010..013`'s own witnessed
    # shape, VO-free `Position`): every one of head/middle/tail carries the
    # resolved row's own `address` forward, whole, since the caller reassigns
    # only `value` — the document is never decomposed at any chain slot.
    address: dict[str, object] = {"city": "Tampere"}
    port = _RecordingPort(rows=[_rectangle_row(address=address)])
    business_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.update_until_where(
            WhereRectangle.where(WhereRectangle.id == 1),
            WhereRectangle.value.set(Decimal("300.00")),
            business_from=business_from,
            until=until,
        )

    Database.connect(port, _WHERE_RECTANGLE_META, clock=FixedClock(_FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 4  # close + head + middle + tail
    head_binds = cast("tuple[object, ...]", writes[1][2])
    middle_binds = cast("tuple[object, ...]", writes[2][2])
    tail_binds = cast("tuple[object, ...]", writes[3][2])
    assert head_binds[-1] == JsonDocument(address)
    assert middle_binds[-1] == JsonDocument(address)
    assert tail_binds[-1] == JsonDocument(address)
    assert middle_binds[2] == Decimal("300.00")  # middle carries the NEW assigned value


def test_materializing_plain_terminate_where_bitemporal_carries_the_document() -> None:
    # Confirmation-pass residual P2, COMPLETION (`m-case-format.md:727`): a
    # BITEMPORAL terminate's own head rectangle chains the resolved row's OLD
    # payload forward (`bitemp_write.plan`'s terminate branch reads
    # `observed.payload`), so the resolving read must project the document
    # too, even though `terminate` carries no assignments — a bitemporal
    # target's rectangle split ALWAYS chains, unlike an AUDIT-ONLY terminate
    # (close-only, no chained row,
    # `test_materializing_terminate_where_audit_only_stays_document_free`,
    # below). `m-bitemp-write` "head/tail old values come from the observed
    # prior rectangle"; `m-value-object` "the document rides every
    # chained/split row whole".
    address: dict[str, object] = {"city": "Oslo"}
    port = _RecordingPort(rows=[_rectangle_row(address=address)])
    business_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.terminate_where(
            WhereRectangle.where(WhereRectangle.id == 1), business_from=business_from
        )

    Database.connect(port, _WHERE_RECTANGLE_META, clock=FixedClock(_FIXED)).transact(
        fn, concurrency="optimistic"
    )
    reads = [op for op in port.ops if op[0] == "read"]
    writes = [op for op in port.ops if op[0] == "write"]
    assert "t0.address" in cast("str", reads[0][1])  # the need-sensitive projection fired
    assert len(writes) == 2  # close + head only (no tail)
    head_binds = cast("tuple[object, ...]", writes[1][2])
    assert head_binds[-1] == JsonDocument(address)  # head: the OLD value's document, whole


def test_materializing_terminate_until_where_bitemporal_carries_the_document_on_head_and_tail() -> (
    None
):
    # `terminateUntil` opens head AND tail (no middle — the window becomes a
    # hole in business time, `terminate_until_where`'s own docstring), and
    # BOTH chain the resolved row's OLD payload forward
    # (`bitemp_write.plan`), so the document rides both, whole.
    address: dict[str, object] = {"city": "Tampere"}
    port = _RecordingPort(rows=[_rectangle_row(address=address)])
    business_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.terminate_until_where(
            WhereRectangle.where(WhereRectangle.id == 1), business_from=business_from, until=until
        )

    Database.connect(port, _WHERE_RECTANGLE_META, clock=FixedClock(_FIXED)).transact(
        fn, concurrency="optimistic"
    )
    reads = [op for op in port.ops if op[0] == "read"]
    writes = [op for op in port.ops if op[0] == "write"]
    assert "t0.address" in cast("str", reads[0][1])  # the need-sensitive projection fired
    assert len(writes) == 3  # close + head + tail (no middle)
    head_binds = cast("tuple[object, ...]", writes[1][2])
    tail_binds = cast("tuple[object, ...]", writes[2][2])
    assert head_binds[-1] == JsonDocument(address)
    assert tail_binds[-1] == JsonDocument(address)


def test_materializing_terminate_where_audit_only_stays_document_free() -> None:
    # An AUDIT-ONLY terminate is close-only (`audit_write.plan` — no chained
    # row, `_materialize_row`'s own `assignment_bearing` set excludes it), so
    # the resolving read stays document-free even on a VALUE-OBJECT-bearing
    # target — unlike its BITEMPORAL counterpart, above
    # (`m-value-object-047`'s own row-form-omits-slot-4 witness, unchanged).
    port = _RecordingPort(
        rows=[
            {
                "id": 1,
                "name": "Nordic Foods",
                "address": {"city": "Bergen"},
                "in_z": "2024-01-01T00:00:00+00:00",
                "out_z": "infinity",
            }
        ]
    )

    def fn(tx: Transaction) -> None:
        tx.terminate_where(WhereLedger.where(WhereLedger.id == 1))

    Database.connect(port, _WHERE_LEDGER_META, clock=FixedClock(_FIXED)).transact(
        fn, concurrency="optimistic"
    )
    reads = [op for op in port.ops if op[0] == "read"]
    assert "t0.address" not in cast("str", reads[0][1])


# --------------------------------------------------------------------------- #
# Confirmation-pass residual A (round 2, `handle.py:1733`): a VERSIONED       #
# NON-TEMPORAL VO-bearing target (`WhereSubscriber`, mirroring `models/       #
# subscriber.yaml`'s own shape) never chains, so the `needs_documents` gate   #
# used to exclude it categorically -- an assignment-bearing `update_where`    #
# assigning an UNCHANGED document could never be recognized by per-row        #
# no-op elimination (the comparison could not see the stored document),       #
# emitting an unnecessary gated UPDATE (`m-opt-lock.md:92-95`). The fix adds  #
# a COMPARISON need, projecting the ASSIGNED document(s) only (minimal-read   #
# discipline) -- `profile` (never assigned by these tests) proves the         #
# projection stays minimal, not "every declared value object".                #
# --------------------------------------------------------------------------- #
def test_materializing_versioned_update_where_eliminates_a_no_op_value_object_row() -> None:
    port = _RecordingPort(rows=[{"id": 1, "version": 1, "address": {"city": "Bergen"}}])

    def fn(tx: Transaction) -> None:
        tx.update_where(
            WhereSubscriber.where(WhereSubscriber.id == 1),
            WhereSubscriber.address.set(WhereSubscriberAddress(city="Bergen")),
        )

    Database.connect(port, _WHERE_SUBSCRIBER_META, clock=FixedClock(_FIXED)).transact(
        fn, concurrency="optimistic"
    )
    # No DML and no version advance: the reassigned document is IDENTICAL to
    # the resolved row's own stored value, so the row is eliminated entirely.
    assert [op[0] for op in port.ops] == ["begin", "read", "commit"]


def test_materializing_versioned_update_where_gates_a_changed_value_object_row() -> None:
    port = _RecordingPort(rows=[{"id": 1, "version": 1, "address": {"city": "Bergen"}}])

    def fn(tx: Transaction) -> None:
        tx.update_where(
            WhereSubscriber.where(WhereSubscriber.id == 1),
            WhereSubscriber.address.set(WhereSubscriberAddress(city="Oslo")),
        )

    Database.connect(port, _WHERE_SUBSCRIBER_META, clock=FixedClock(_FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 1
    assert writes[0][1] == POSTGRES.to_driver_sql(
        "update where_subscriber set address = ?, version = ? where id = ? and version = ?"
    )
    assert writes[0][2] == (JsonDocument({"city": "Oslo"}), 2, 1, 1)


def test_materializing_versioned_update_where_projects_only_the_assigned_value_object() -> None:
    # Minimal-read discipline: the resolving read projects the ASSIGNED
    # document (`address`) only -- never `profile`, the entity's OTHER
    # declared value object, which this `update_where` never touches.
    port = _RecordingPort(rows=[{"id": 1, "version": 1, "address": {"city": "Bergen"}}])

    def fn(tx: Transaction) -> None:
        tx.update_where(
            WhereSubscriber.where(WhereSubscriber.id == 1),
            WhereSubscriber.address.set(WhereSubscriberAddress(city="Oslo")),
        )

    Database.connect(port, _WHERE_SUBSCRIBER_META, clock=FixedClock(_FIXED)).transact(
        fn, concurrency="optimistic"
    )
    reads = [op for op in port.ops if op[0] == "read"]
    assert reads[0][1] == POSTGRES.to_driver_sql(
        "select t0.id, t0.version, t0.address from where_subscriber t0 where t0.id = ?"
    )


# --------------------------------------------------------------------------- #
# Typed KEYED temporal-window verbs (COR-3 Phase 8 increment 7): `update`'s    #
# own optional bitemporal `business_from`, `terminate`, `update_until`, and    #
# `terminate_until` — the KEYED siblings of `update_where` / `terminate_where` #
# / `update_until_where` / `terminate_until_where`, sharing the SAME           #
# `_buffer` seam and the SAME `_validate_business_from` gate, so a keyed and a #
# predicate-selected write over the identical bitemporal correction lower to  #
# the identical rectangle split (`m-bitemp-write-001/002/006/007`'s own       #
# witnessed shape, replayed here through the KEYED verb instead of `_where`). #
# --------------------------------------------------------------------------- #
def test_keyed_update_lowers_a_plain_bitemporal_correction() -> None:
    # m-bitemp-write-006 "plain-update-split", replayed through the KEYED verb:
    # close + head (old) + new tail.
    port = _RecordingPort(rows=[_position_row_dt()])
    business_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(WherePosition.where(WherePosition.id == 1)).result()
        tx.update(
            fetched.model_copy(update={"value": Decimal("200.00")}), business_from=business_from
        )

    Database.connect(port, _WHERE_POSITION_META, clock=FixedClock(_FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 3  # close + head (old) + new tail


def test_keyed_terminate_lowers_a_plain_bitemporal_termination() -> None:
    # m-bitemp-write-007 "plain-terminate", replayed through the KEYED verb:
    # close + head only (no tail).
    port = _RecordingPort(rows=[_position_row_dt()])
    business_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(WherePosition.where(WherePosition.id == 1)).result()
        tx.terminate(fetched, business_from=business_from)

    Database.connect(port, _WHERE_POSITION_META, clock=FixedClock(_FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 2  # close + head only


def test_keyed_update_until_lowers_the_rectangle_split() -> None:
    # m-bitemp-write-001 "update-until-rectangle-split", replayed through the
    # KEYED verb: close + head + middle + tail.
    port = _RecordingPort(rows=[_position_row_dt()])
    business_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(WherePosition.where(WherePosition.id == 1)).result()
        tx.update_until(
            fetched.model_copy(update={"value": Decimal("200.00")}),
            business_from=business_from,
            until=until,
        )

    Database.connect(port, _WHERE_POSITION_META, clock=FixedClock(_FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 4  # close + head + middle + tail


def test_keyed_update_until_with_an_empty_effective_change_set_issues_no_dml() -> None:
    # The SAME sparse-update no-op rule `update` applies (spec §3/§5): a
    # `model_copy()` whose Change Record nets to zero issues no DML at all --
    # but only AFTER its (here, valid) business window is validated (R2,
    # COR-3 Phase 7 increment 7 round-2: window validation runs BEFORE the
    # no-op return, for every window verb, never the reverse -- see the
    # sibling equal-bounds pin immediately below for the corrected
    # precedence made visible).
    port = _RecordingPort()
    fetched = WherePosition(
        id=1,
        acct_num="A",
        value=Decimal("100.00"),
        business_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        business_to=_INFINITY_INSTANT,
        processing_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        processing_to=_INFINITY_INSTANT,
    )
    edited = fetched.model_copy(update={"value": Decimal("100.00")})  # net-zero touch
    business_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.update_until(edited, business_from=business_from, until=until)

    Database.connect(port, _WHERE_POSITION_META, clock=FixedClock(_FIXED)).transact(
        fn, concurrency="optimistic"
    )
    assert not any(op[0] in ("read", "write") for op in port.ops)


def test_keyed_update_until_with_an_empty_change_set_still_rejects_equal_bounds() -> None:
    # R2 (COR-3 Phase 7 increment 7 round-2): window validation runs BEFORE
    # the empty-effective-change-set no-op return -- equal bounds reject even
    # when the edited copy's own Change Record nets to zero. The prior round
    # deliberately kept the no-op-first ordering, matching what it believed
    # was the existing test's documented precedence (the sibling test above,
    # pre-fix); the reviewer ruled that precedence WRONG per spec §5 ("all
    # validated at build") -- this is the corrected behavior.
    port = _RecordingPort()
    fetched = WherePosition(
        id=1,
        acct_num="A",
        value=Decimal("100.00"),
        business_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        business_to=_INFINITY_INSTANT,
        processing_from=dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        processing_to=_INFINITY_INSTANT,
    )
    edited = fetched.model_copy(update={"value": Decimal("100.00")})  # net-zero touch
    business_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.update_until(edited, business_from=business_from, until=business_from)  # EQUAL bounds

    with pytest.raises(ValueError, match="requires business_from < until"):
        Database.connect(port, _WHERE_POSITION_META, clock=FixedClock(_FIXED)).transact(
            fn, concurrency="optimistic"
        )
    assert not any(op[0] in ("read", "write") for op in port.ops)  # never reached the no-op check


def test_keyed_update_until_with_a_naive_until_raises_the_proper_value_error() -> None:
    # R2: a naive `until` (no tzinfo) must raise the SAME `ValueError` shape
    # `_validate_business_from`'s own `instant_literal` normalization raises
    # for a naive `business_from` (never a bare `TypeError` leaked by
    # comparing a naive `until` against an already-aware `business_from`,
    # the pre-fix defect: comparison ran before normalization).
    port = _RecordingPort(rows=[_position_row_dt()])
    business_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    naive_until = dt.datetime(2024, 9, 1)  # NAIVE -- no tzinfo

    def fn(tx: Transaction) -> None:
        fetched = tx.find(WherePosition.where(WherePosition.id == 1)).result()
        tx.update_until(
            fetched.model_copy(update={"value": Decimal("200.00")}),
            business_from=business_from,
            until=naive_until,
        )

    # `pytest.raises(ValueError, ...)` itself is the pin against the pre-fix
    # leak: `TypeError` is not a `ValueError`, so an un-normalized comparison
    # would escape uncaught here rather than silently satisfy this block.
    with pytest.raises(ValueError, match="naive datetime"):
        Database.connect(port, _WHERE_POSITION_META, clock=FixedClock(_FIXED)).transact(
            fn, concurrency="optimistic"
        )


def test_keyed_terminate_until_lowers_head_and_tail_only() -> None:
    # m-bitemp-write-002 "terminate-until", replayed through the KEYED verb:
    # close + head + tail (no middle).
    port = _RecordingPort(rows=[_position_row_dt()])
    business_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(WherePosition.where(WherePosition.id == 1)).result()
        tx.terminate_until(fetched, business_from=business_from, until=until)

    Database.connect(port, _WHERE_POSITION_META, clock=FixedClock(_FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 3  # close + head + tail


def test_keyed_update_on_a_bitemporal_target_without_business_from_raises() -> None:
    port = _RecordingPort(rows=[_position_row_dt()])

    def fn(tx: Transaction) -> None:
        fetched = tx.find(WherePosition.where(WherePosition.id == 1)).result()
        tx.update(fetched.model_copy(update={"value": Decimal("200.00")}))

    with pytest.raises(ValueError, match="requires business_from"):
        Database.connect(port, _WHERE_POSITION_META, clock=FixedClock(_FIXED)).transact(
            fn, concurrency="optimistic"
        )


def test_keyed_terminate_on_a_non_temporal_target_forbids_business_from() -> None:
    port = _RecordingPort(rows=[{"id": 3, "owner": "Grace", "balance": 10.00, "version": 1}])

    def fn(tx: Transaction) -> None:
        fetched = tx.find(mm.Account.where(mm.Account.id == 3)).result()
        tx.terminate(fetched, business_from=_FIXED)

    with pytest.raises(ValueError, match="takes no business_from"):
        _db(port).transact(fn)


# --------------------------------------------------------------------------- #
# Window-order validation (S4, COR-3 Phase 8 increment 7 remediation):        #
# `python.md` §5 "the `*_until` trio additionally requires `until`, with      #
# `business_from < until` ... all validated at build" — an EQUAL and a        #
# REVERSED window both reject, at the verb call, before any buffering, for    #
# BOTH the KEYED (`update_until`/`terminate_until`) and `_where`              #
# (`update_until_where`/`terminate_until_where`) verb families — the ONE      #
# shared `_validate_until` validator (`handle.py`) makes all four converge.   #
# --------------------------------------------------------------------------- #
def test_keyed_update_until_rejects_an_equal_window_bound() -> None:
    port = _RecordingPort(rows=[_position_row_dt()])
    business_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(WherePosition.where(WherePosition.id == 1)).result()
        tx.update_until(
            fetched.model_copy(update={"value": Decimal("200.00")}),
            business_from=business_from,
            until=business_from,
        )

    with pytest.raises(ValueError, match="requires business_from < until"):
        Database.connect(port, _WHERE_POSITION_META, clock=FixedClock(_FIXED)).transact(
            fn, concurrency="optimistic"
        )


def test_keyed_terminate_until_rejects_a_reversed_window_bound() -> None:
    port = _RecordingPort(rows=[_position_row_dt()])
    business_from = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)  # BEFORE business_from — reversed

    def fn(tx: Transaction) -> None:
        fetched = tx.find(WherePosition.where(WherePosition.id == 1)).result()
        tx.terminate_until(fetched, business_from=business_from, until=until)

    with pytest.raises(ValueError, match="requires business_from < until"):
        Database.connect(port, _WHERE_POSITION_META, clock=FixedClock(_FIXED)).transact(
            fn, concurrency="optimistic"
        )


def test_materializing_update_until_where_rejects_an_equal_window_bound() -> None:
    # No resolving read ever fires — the window rejects at build, before any
    # buffering (`_buffer_predicate`, before `_materialize_predicate_write`).
    port = _RecordingPort()
    business_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.update_until_where(
            WherePosition.where(WherePosition.id == 1),
            WherePosition.value.set(Decimal("300.00")),
            business_from=business_from,
            until=business_from,
        )

    with pytest.raises(ValueError, match="requires business_from < until"):
        Database.connect(port, _WHERE_POSITION_META, clock=FixedClock(_FIXED)).transact(
            fn, concurrency="optimistic"
        )
    assert not any(op[0] in ("read", "write") for op in port.ops)  # never reached the resolve


def test_materializing_terminate_until_where_rejects_a_reversed_window_bound() -> None:
    port = _RecordingPort()
    business_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 4, 1, tzinfo=dt.UTC)  # BEFORE business_from — reversed

    def fn(tx: Transaction) -> None:
        tx.terminate_until_where(
            WherePosition.where(WherePosition.id == 1), business_from=business_from, until=until
        )

    with pytest.raises(ValueError, match="requires business_from < until"):
        Database.connect(port, _WHERE_POSITION_META, clock=FixedClock(_FIXED)).transact(
            fn, concurrency="optimistic"
        )
    assert not any(op[0] in ("read", "write") for op in port.ops)  # never reached the resolve


# --------------------------------------------------------------------------- #
# The spec §3 stale-web-edit recipe module (`parallax.conformance.            #
# stale_web_edit`) — the Docker-free halves of the api-conformance stories:   #
# render captures the transported edge; submit replays it optimistically.     #
# --------------------------------------------------------------------------- #
def test_stale_web_edit_balance_render_then_submit_gates_on_the_transported_edge() -> None:
    in_z = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    port = _RecordingPort(rows=[_balance_row(in_z=in_z)])
    db = _db_for(_BALANCE, port)

    node, edge = stale_web_edit.render_balance_milestone(db, id=1)
    assert node.value == Decimal("5.00")
    assert edge.processing == in_z
    assert edge.business_or_none is None  # audit-only: no business axis declared

    stale_web_edit.submit_balance_edit(db, id=1, edge=edge, fields={"value": Decimal("9.00")})
    write_ops = [op for op in port.ops if op[0] == "write"]
    close_sql = cast("str", write_ops[0][1])
    close_binds = cast("tuple[object, ...]", write_ops[0][2])
    assert close_sql == POSTGRES.to_driver_sql(
        "update balance set out_z = ? where bal_id = ? and out_z = ? and in_z = ?"
    )
    assert close_binds[-1] == in_z  # the TRANSPORTED edge, never a re-resolved latest
    # The chained replacement row carries the UNTOUCHED field too (the D-30
    # observed-payload merge, proven at the recipe's own altitude).
    chain_binds = cast("tuple[object, ...]", write_ops[1][2])
    assert "A-1" in chain_binds
    assert Decimal("9.00") in chain_binds


def test_stale_web_edit_balance_submit_conflict_raises_optimistic_lock_conflict() -> None:
    # A concurrent writer chained a replacement between render and submit: the
    # observed `in_z` is stale, the gated close matches ZERO rows.
    in_z = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    port = _RecordingPort(rows=[_balance_row(in_z=in_z)], write_affected=0)
    db = _db_for(_BALANCE, port)
    _node, edge = stale_web_edit.render_balance_milestone(db, id=1)

    with pytest.raises(opt_lock.OptimisticLockConflictError):
        stale_web_edit.submit_balance_edit(db, id=1, edge=edge, fields={"value": Decimal("9.00")})


def test_stale_web_edit_branch_render_then_submit_pins_both_axes() -> None:
    from_z = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    in_z = dt.datetime(2024, 1, 15, tzinfo=dt.UTC)
    branch_row: Row = {
        "br_id": 1,
        "name": "Old Name",
        "from_z": from_z,
        "thru_z": _INFINITY_INSTANT,
        "in_z": in_z,
        "out_z": _INFINITY_INSTANT,
        "address": None,
    }
    port = _RecordingPort(rows=[branch_row])
    db = _db_for(models.load_models()["branch"], port)

    node, edge = stale_web_edit.render_branch_milestone(db, id=1)
    assert node.name == "Old Name"
    assert edge.business == from_z
    assert edge.processing == in_z

    stale_web_edit.submit_branch_edit(
        db,
        id=1,
        edge=edge,
        fields={"name": "New Name"},
        business_from=dt.datetime(2024, 2, 1, tzinfo=dt.UTC),
    )
    write_ops = [op for op in port.ops if op[0] == "write"]
    close_sql = cast("str", write_ops[0][1])
    close_binds = cast("tuple[object, ...]", write_ops[0][2])
    assert close_sql.startswith("update branch set out_z = ")
    assert in_z in close_binds  # the transported PROCESSING edge gates the close
    # The correction's replacement rows carry the edited field.
    assert any("New Name" in cast("tuple[object, ...]", op[2]) for op in write_ops[1:])


# --------------------------------------------------------------------------- #
# The §5 prior-observation license for keyed TEMPORAL update/terminate        #
# (checkpoint-4 Spec finding 1): the temporal sibling of the versioned        #
# `require_observed` rule, enforced at the developer verb.                    #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("concurrency", ["locking", "optimistic"])
def test_unobserved_temporal_terminate_raises_before_any_dml(concurrency: str) -> None:
    # A keyed temporal close of a milestone this unit of work never observed
    # is a read-before-write programming error in EITHER mode: in locking
    # mode the observing find's shared lock is the ungated close's ONLY
    # protection; in optimistic mode there is no observed `in_z` to gate on.
    port = _RecordingPort(rows=[_balance_row(in_z=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))])
    db = _db_for(_BALANCE, port)

    def fn(tx: Transaction) -> None:
        tx.terminate(mm.Balance(id=1, acct_num="A-1", value=Decimal("5.00")))

    with pytest.raises(opt_lock.UnobservedMilestoneError, match="transaction-scoped find"):
        db.transact(fn, concurrency=cast("Any", concurrency))
    assert not any(op[0] == "write" for op in port.ops)


def test_unobserved_temporal_update_from_a_cross_transaction_copy_raises() -> None:
    # Provenance alone is not a license: a copy edited from a node ANOTHER
    # scope's read materialized (a plain `db.find`, no unit of work) reaches
    # `tx.update` with no transaction-scoped observation — the §5 rule names
    # "the milestone THIS unit of work observed", so it raises (the
    # stale-web-edit recipe's in-transaction re-fetch is the sanctioned
    # spelling for transported coordinates).
    port = _RecordingPort(rows=[_balance_row(in_z=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))])
    db = _db_for(_BALANCE, port)
    node = db.find(mm.Balance.where(mm.Balance.id == 1)).result()

    def fn(tx: Transaction) -> None:
        tx.update(node.model_copy(update={"value": Decimal("9.00")}))

    with pytest.raises(opt_lock.UnobservedMilestoneError, match="transaction-scoped find"):
        db.transact(fn)
    assert not any(op[0] == "write" for op in port.ops)


def test_same_transaction_insert_then_temporal_update_is_licensed() -> None:
    # Read-your-own-writes exemption: this transaction's OWN buffered insert
    # IS the provenance (`m-audit-write-008`'s same-transaction coalescing
    # shape) — no observation lookup applies, and the planner folds the pair
    # into the single INSERT carrying the updated value.
    port = _RecordingPort()
    db = _db_for(_BALANCE, port)

    def fn(tx: Transaction) -> None:
        fresh = mm.Balance(id=9, acct_num="Z", value=Decimal("1.00"))
        tx.insert(fresh)
        tx.update(fresh.model_copy(update={"value": Decimal("2.00")}))

    db.transact(fn)
    write_ops = [op for op in port.ops if op[0] == "write"]
    assert len(write_ops) == 1  # coalesced to one INSERT
    assert Decimal("2.00") in cast("tuple[object, ...]", write_ops[0][2])
