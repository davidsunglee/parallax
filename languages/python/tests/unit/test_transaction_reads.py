"""Participating-read unit tests for `parallax.snapshot.handle` (spec §5, Docker-free fake ports).

`Transaction.find` and `Database.find`: force-flush before a read
(read-your-own-writes), the lock suffix each materialized level's own Effective
Concurrency Strategy calls for, statement and
milestone pin derivation, history statements, which of the two entry points
stamps its participation on the values it publishes, and the evidence a read
leaves on those values — proven through the writes they license or refuse. Also
the spec §3 stale-web-edit recipe's Docker-free halves.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

import _mixed_strategy_model as mx
import observation_models as om
import pytest
from _transact_support import (
    ACCOUNT,
    BALANCE,
    FIND_SQL_LOCKED,
    FIND_SQL_UNLOCKED,
    FIXED,
    INFINITY_INSTANT,
    INSERT_SQL,
    NEW_ROW,
    PAYMENT,
    account_db,
    balance_row,
    db_for,
    new_account,
    read_account,
)

from _support import inheritance_models as im
from _support import mirrored_models as mm
from _support.db_port import (
    BeginCall,
    CommitCall,
    Read,
    ReadCall,
    ScriptedPort,
    Transact,
    Write,
    WriteCall,
)
from parallax.conformance import stale_web_edit
from parallax.conformance.class_models import MODELS
from parallax.conformance.graph_models import POLICY_MODEL, Policy
from parallax.core import LATEST, TX_TIME
from parallax.core.base import SQL_NULL, PresentDocument
from parallax.core.db_port import DbPort, JsonDocument, Row
from parallax.core.dialect import POSTGRES
from parallax.core.entity._layout import CatalogedModel
from parallax.core.execution_lifecycle._activity import INERT, DatabaseCallScope
from parallax.core.object_query import ObjectQueryNode
from parallax.core.unit_work import (
    Concurrency,
    FixedClock,
    OptimisticLockConflictError,
)
from parallax.snapshot import DeferredFeatureError, InvalidData, QueryTargetError
from parallax.snapshot.handle import (
    Database,
    FindResult,
    Transaction,
    TransactionTimePinReadOnlyError,
)
from parallax.snapshot.handle import _database as database_module
from parallax.snapshot.handle import _read as handle_read
from parallax.snapshot.handle import _transaction as transaction_module
from parallax.snapshot.handle._write_inputs import ObservationLedger


@dataclass(frozen=True, slots=True)
class _RecordedFind:
    """One executor call: whether it was handed a ledger, the participation that
    ledger answered while its scope was open, and the result the call produced.

    The participation is read inside the call rather than kept as the unit of
    work itself, because a unit of work fences every access once its scope ends —
    which is the same reason evidence outliving a transaction holds a token
    rather than the transaction.
    """

    participation: object | None
    result: FindResult


def _recording_find(recorded: list[_RecordedFind]) -> Callable[..., FindResult]:
    """A ``find`` stand-in recording the ledger each call was handed.

    Spelled with the executor's full signature rather than ``*args`` so the
    recorded parameter is the real one — a rename or a move to a positional
    parameter fails here rather than silently recording ``None`` forever.
    """
    real = handle_read.find

    def recording(
        query: ObjectQueryNode,
        model: CatalogedModel,
        port: DbPort,
        *,
        preference: Concurrency | None = None,
        ledger: ObservationLedger | None = None,
        calls: DatabaseCallScope = INERT,
    ) -> FindResult:
        result = real(
            query,
            model,
            port,
            preference=preference,
            ledger=ledger,
            calls=calls,
        )
        recorded.append(_RecordedFind(None if ledger is None else ledger.participation, result))
        return result

    return recording


def test_a_standalone_find_stamps_no_participation_on_the_evidence_it_retains() -> None:
    # A standalone read has no unit of work to file into, so it hands the
    # executor no ledger — and still retains what its rows observed, because a
    # value's write evidence belongs to the value. What its sources lack is
    # participation, which is exactly what an effective-Locking write asks for.
    calls: list[_RecordedFind] = []
    port = ScriptedPort(Read(rows=[balance_row(in_z=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))]))
    db = db_for(BALANCE, port)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(database_module, "find", _recording_find(calls))
        db.find(mm.Balance.where(mm.Balance.id == 1)).result()
    (call,) = calls
    assert call.participation is None
    (hint,) = call.result.sources.values()
    assert hint.participation is None
    assert hint.observation is not None


def test_a_participating_find_stamps_its_transactions_own_participation() -> None:
    # The other side of the same decision: `Transaction.find` has a unit of work
    # behind it, so it hands the executor that unit of work as the ledger and
    # every source it produces carries that transaction's participation.
    calls: list[_RecordedFind] = []
    port = ScriptedPort(
        Transact(Read(rows=[balance_row(in_z=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))]))
    )
    db = db_for(BALANCE, port)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(transaction_module, "find", _recording_find(calls))
        db.transact(lambda tx: tx.find(mm.Balance.where(mm.Balance.id == 1)).result())
    (call,) = calls
    (hint,) = call.result.sources.values()
    assert call.participation is not None
    assert hint.participation is call.participation


def test_a_non_hydrating_find_retains_no_evidence() -> None:
    # The read publishes its classified root in band, and the row behind that
    # root licenses no later write: no conforming value exists for it, so it is
    # observed by nothing and no source stands behind it.
    calls: list[_RecordedFind] = []
    port = ScriptedPort(
        Transact(Read(rows=[{"id": 1, "owner": "Ada", "balance": "not-a-decimal", "version": 1}]))
    )

    def fn(tx: Transaction) -> None:
        root = tx.find(mm.Account.where(mm.Account.id == 1)).checked().result()
        assert isinstance(root, InvalidData)
        assert root.data is None

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(transaction_module, "find", _recording_find(calls))
        account_db(port).transact(fn)
    assert [dict(call.result.sources) for call in calls] == [{}]


def test_every_attached_level_row_retains_its_own_evidence() -> None:
    # A deep fetch materializes the root and then each level, and every one of
    # those rows retains its own evidence — not only the root's — so an included
    # child a caller keeps is as writable as the root it came from.
    from_z = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    policy_row: Row = {
        "id": 1,
        "name": "P-1",
        "from_z": from_z,
        "thru_z": INFINITY_INSTANT,
        "in_z": from_z,
        "out_z": INFINITY_INSTANT,
    }
    coverage_row: Row = {
        "id": 10,
        "policy_id": 1,
        "amount": Decimal("250.00"),
        "from_z": from_z,
        "thru_z": INFINITY_INSTANT,
        "in_z": from_z,
        "out_z": INFINITY_INSTANT,
    }
    calls: list[_RecordedFind] = []
    port = ScriptedPort(Transact(Read(rows=[policy_row]), Read(rows=[coverage_row])))
    db = db_for(POLICY_MODEL, port)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(transaction_module, "find", _recording_find(calls))
        db.transact(
            lambda tx: tx.find(
                Policy.where(Policy.id == 1).as_of(valid_time=LATEST).include(Policy.coverages)
            ).result()
        )
    (call,) = calls
    assert [hint.object_key.primary_key for hint in call.result.sources.values()] == [
        (("id", 1),),
        (("id", 10),),
    ]


def test_find_on_a_non_versioned_entity_retains_no_observed_state() -> None:
    # Retention is defensive: a materialized node whose entity declares no
    # `optimisticLocking` version column (every Payment-family member) observes
    # no state at all, never raising and never retaining evidence a later write
    # could gate on.
    port = ScriptedPort(
        Transact(Read(rows=[{"id": 1, "amount": Decimal("100.00"), "card_network": "Visa"}]))
    )

    def fn(tx: Transaction) -> None:
        tx.find(im.CardPayment.where(im.CardPayment.id == 1)).result()

    db_for(PAYMENT, port).transact(fn)
    assert [type(op) for op in port.calls] == [BeginCall, ReadCall, CommitCall]


def test_find_force_flushes_pending_writes_first() -> None:
    # Read-your-own-writes: the buffered insert executes BEFORE the dependent
    # read, inside the same still-open transaction (m-unit-work-001's shape).
    port = ScriptedPort(Transact(Write(), Read(rows=[NEW_ROW])))

    def fn(tx: Transaction) -> list[mm.Account]:
        tx.insert(new_account())
        return tx.find(mm.Account.where(mm.Account.id == 7)).results()

    assert account_db(port).transact(fn) == [read_account()]
    assert port.calls == [
        BeginCall(),
        WriteCall(INSERT_SQL, (7, "Newton", 5.00, 1)),
        ReadCall(FIND_SQL_UNLOCKED, (7,)),
        CommitCall(),
    ]


# --------------------------------------------------------------------------- #
# The Effective Concurrency Strategy is derived per Entity, so the lock follows #
# the level's own target rather than the transaction (m-unit-work "Strategy    #
# selection"; m-opt-lock).                                                     #
# --------------------------------------------------------------------------- #
def test_an_explicit_optimistic_preference_reads_a_versioned_entity_lock_free() -> None:
    # Explicit and omitted resolve identically, so this pins the same statement
    # every default-preference find of a versioned Entity above already renders.
    port = ScriptedPort(Transact(Read()))
    account_db(port).transact(
        lambda tx: tx.find(mm.Account.where(mm.Account.id == 7)), concurrency="optimistic"
    )
    assert port.calls == [BeginCall(), ReadCall(FIND_SQL_UNLOCKED, (7,)), CommitCall()]


def test_the_locking_preference_reads_a_versioned_entity_under_the_shared_lock() -> None:
    # The workflow-level override: `locking` forces the Locking strategy onto an
    # Entity whose own facet would otherwise supply a gate.
    port = ScriptedPort(Transact(Read()))
    account_db(port).transact(
        lambda tx: tx.find(mm.Account.where(mm.Account.id == 7)), concurrency="locking"
    )
    assert port.calls == [BeginCall(), ReadCall(FIND_SQL_LOCKED, (7,)), CommitCall()]


def test_a_default_preference_read_of_an_unversioned_entity_takes_the_shared_lock() -> None:
    # The mandatory Locking fallback: an unversioned Non-Temporal family
    # supplies no gate, so `optimistic` cannot mean lock-free for it.
    port = ScriptedPort(Transact(Read(rows=[])))
    db_for(mx.MIXED_STRATEGY_MODEL, port).transact(
        lambda tx: tx.find(mx.ConsignmentLeg.where(mx.ConsignmentLeg.id == 1))
    )
    assert port.calls == [
        BeginCall(),
        ReadCall(
            POSTGRES.to_driver_sql(
                "select t0.id, t0.consignment_id, t0.carrier from consignment_leg t0 "
                "where t0.id = ? for share of t0"
            ),
            (1,),
        ),
        CommitCall(),
    ]


def test_one_default_transaction_locks_the_unversioned_level_and_not_the_versioned_root() -> None:
    # The signature per-level derivation: ONE preference, one deep fetch, two
    # strategies. The versioned root's statement carries no suffix because its
    # write gate is the authority; the unversioned level's does, because a
    # shared lock is the only correctness mechanism its family has.
    port = ScriptedPort(
        Transact(
            Read(rows=[{"id": 1, "total": Decimal("10.00"), "version": 1}]),
            Read(rows=[{"id": 5, "consignment_id": 1, "carrier": "Hansa"}]),
        )
    )
    db_for(mx.MIXED_STRATEGY_MODEL, port).transact(
        lambda tx: tx.find(
            mx.Consignment.where(mx.Consignment.id == 1).include(mx.Consignment.legs)
        )
    )
    assert [type(op) for op in port.calls] == [BeginCall, ReadCall, ReadCall, CommitCall]
    root, level = (call for call in port.calls if isinstance(call, ReadCall))
    root_sql, level_sql = root.sql, level.sql
    assert root_sql == POSTGRES.to_driver_sql(
        "select t0.id, t0.total, t0.version from consignment t0 where t0.id = ?"
    )
    assert level_sql == POSTGRES.to_driver_sql(
        "select t0.id, t0.consignment_id, t0.carrier from consignment_leg t0 "
        "where t0.consignment_id in (?) for share of t0"
    )


def test_the_locking_preference_locks_every_level_of_the_same_deep_fetch() -> None:
    # The same read under the override: one preference forcing one strategy
    # onto both Entities, which is what makes the mixed result above a
    # derivation rather than a property of the model alone.
    port = ScriptedPort(
        Transact(
            Read(rows=[{"id": 1, "total": Decimal("10.00"), "version": 1}]),
            Read(rows=[{"id": 5, "consignment_id": 1, "carrier": "Hansa"}]),
        )
    )
    db_for(mx.MIXED_STRATEGY_MODEL, port).transact(
        lambda tx: tx.find(
            mx.Consignment.where(mx.Consignment.id == 1).include(mx.Consignment.legs)
        ),
        concurrency="locking",
    )
    assert all(
        call.sql.endswith("for share of t0") for call in port.calls if isinstance(call, ReadCall)
    )


def test_a_standalone_find_never_locks_whatever_the_entity_declares() -> None:
    # `db.find` owns no unit of work, so there is no participation to derive a
    # strategy from and the Locking fallback cannot reach it.
    port = ScriptedPort(Read(rows=[]))
    db_for(mx.MIXED_STRATEGY_MODEL, port).find(mx.ConsignmentLeg.where(mx.ConsignmentLeg.id == 1))
    assert port.calls == [
        ReadCall(
            POSTGRES.to_driver_sql(
                "select t0.id, t0.consignment_id, t0.carrier from consignment_leg t0 "
                "where t0.id = ?"
            ),
            (1,),
        )
    ]


def test_db_find_pins_an_explicit_as_of_statement() -> None:
    # `statement_pin` reads the query's OWN Temporal Selection: an explicit
    # `.as_of(tx_time=LATEST)` pin comes back on the returned `Snapshot`.
    from parallax.core import LATEST

    port = ScriptedPort(
        Read(
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
    )
    db = Database.connect(port, BALANCE, clock=FixedClock(FIXED))
    statement = mm.Balance.where(mm.Balance.id == 1).as_of(tx_time=LATEST)
    snapshot = db.find(statement)
    assert snapshot.pin.tx_time is LATEST


def test_db_find_resolves_a_concrete_inheritance_targets_inherited_pin_and_edge() -> None:
    # `DepositRate` declares NO `as_of` of its own (`Rate`, the family root,
    # does) — `_temporal_entity` (`parallax.snapshot.handle`) must resolve
    # through the root to compute both the statement pin and the row's own
    # milestone edge.
    from parallax.core import LATEST
    from parallax.snapshot import edge_of

    port = ScriptedPort(
        Read(
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
    )
    rate = MODELS["rate"]
    db = Database.connect(port, rate, clock=FixedClock(FIXED))
    statement = im.DepositRate.where(im.DepositRate.all).as_of(valid_time=LATEST, tx_time=LATEST)
    snapshot = db.find(statement)
    assert snapshot.pin.tx_time is LATEST
    assert snapshot.pin.valid_time is LATEST
    edge = edge_of(snapshot.result())
    assert edge.tx_time == dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
    assert edge.valid_time == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


@pytest.mark.parametrize("concurrency", ["locking", "optimistic"])
def test_a_temporal_write_after_an_as_of_find_is_refused_in_either_mode(
    concurrency: Concurrency,
) -> None:
    # The choreography an as-of read makes available at all: read a superseded
    # milestone, derive a copy, update. It is refused in BOTH modes, at the verb,
    # before any DML — the copy carries the pinned view's own read-only state
    # (`transaction-time-pin-read-only`), and no concurrency mode is a way past
    # that, because the Transaction-Time past is never rewritten. The mode
    # therefore selects nothing here, which is the point of parametrizing it.
    port = ScriptedPort(
        Transact(Read(rows=[balance_row(in_z=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))]))
    )
    db = db_for(BALANCE, port)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(
            mm.Balance.where(mm.Balance.id == 1).as_of(
                tx_time=dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
            )
        ).result()
        tx.update(fetched.edit(value=Decimal("9.00")))

    with pytest.raises(TransactionTimePinReadOnlyError, match="transaction-time-pin-read-only"):
        db.transact(fn, concurrency=concurrency)
    assert not any(isinstance(op, WriteCall) for op in port.calls)


def test_locking_mode_temporal_write_after_a_latest_find_is_licensed() -> None:
    # An OMITTED axis (the default-latest pin) licenses a locking-mode write:
    # the read observed the CURRENT milestone, so the shared read lock
    # genuinely protects the row the ungated close targets.
    port = ScriptedPort(
        Transact(Read(rows=[balance_row(in_z=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))]), Write())
    )
    db = db_for(BALANCE, port)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(mm.Balance.where(mm.Balance.id == 1)).result()
        tx.terminate(fetched)

    db.transact(fn, concurrency="locking")  # must not raise
    write_ops = [op for op in port.calls if isinstance(op, WriteCall)]
    assert len(write_ops) == 1
    sql = write_ops[0].sql
    assert sql == POSTGRES.to_driver_sql(
        "update balance set out_z = ? where bal_id = ? and out_z = ?"
    )


def test_transaction_time_only_update_via_a_sparse_copy_carries_untouched_fields() -> None:
    # A sparse edited copy contains only the changed value, so chaining must merge
    # it with the observed payload rather than dropping untouched fields. Balance
    # is Transaction-Time temporal, so the default preference resolves it to the
    # Optimistic strategy and the close binds the observed `in_z` as its gate.
    port = ScriptedPort(
        Transact(
            Read(rows=[balance_row(in_z=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))]), Write(times=2)
        )
    )
    db = db_for(BALANCE, port)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(mm.Balance.where(mm.Balance.id == 1)).result()
        tx.update(fetched.edit(value=Decimal("150.00")))

    db.transact(fn)
    write_ops = [op for op in port.calls if isinstance(op, WriteCall)]
    assert len(write_ops) == 2  # the close, then the merged chain
    close_sql, close_binds = write_ops[0].sql, write_ops[0].binds
    assert close_sql == POSTGRES.to_driver_sql(
        "update balance set out_z = ? where bal_id = ? and out_z = ? and in_z = ?"
    )
    assert close_binds == (
        "2024-06-01T00:00:00+00:00",
        1,
        "infinity",
        dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
    )
    chain_sql, chain_binds = write_ops[1].sql, write_ops[1].binds
    assert chain_sql == POSTGRES.to_driver_sql(
        "insert into balance(bal_id, acct_num, val, in_z, out_z) values (?, ?, ?, ?, ?)"
    )
    assert chain_binds == (1, "A-1", Decimal("150.00"), "2024-06-01T00:00:00+00:00", "infinity")


def _branch_row(*, address: dict[str, object] | None) -> Row:
    return {
        "br_id": 1,
        "name": "Central Branch",
        "from_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "thru_z": INFINITY_INSTANT,
        "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "out_z": INFINITY_INSTANT,
        "address": SQL_NULL if address is None else PresentDocument(cast("Any", address)),
    }


def test_bitemporal_update_after_a_find_carries_observed_valid_time_bounds() -> None:
    # Rectangle splitting consumes the observed Valid-Time bounds and full payload.
    # A real find-then-update makes both facts observable in the emitted DML.
    port = ScriptedPort(Transact(Read(rows=[_branch_row(address=None)]), Write(times=3)))
    db = db_for(MODELS["branch"], port)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(mm.Branch.where(mm.Branch.id == 1).as_of(valid_time=LATEST)).result()
        tx.update(
            fetched.edit(name="Renamed Branch"),
            valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
        )

    db.transact(fn)
    write_ops = [op for op in port.calls if isinstance(op, WriteCall)]
    assert len(write_ops) == 3  # close the rectangle, then chain head + tail
    head_binds = write_ops[1].binds
    tail_binds = write_ops[2].binds
    # The HEAD rectangle runs from the OBSERVED valid_from up to the
    # mutation instant, and carries the OBSERVED name. Neither value appears
    # anywhere in the sparse edited copy, so both can only have come from the
    # recorded observation.
    assert head_binds[1] == "Central Branch"
    assert head_binds[2] == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    assert head_binds[3] == "2024-03-01T00:00:00+00:00"
    # The TAIL rectangle opens at the mutation instant with the new payload and
    # closes at the OBSERVED valid_end. That upper bound is the third value
    # only the observation carries: the edited copy never names it, and without
    # this assertion a corrupted `observation.valid_end` would go undetected.
    assert tail_binds[1] == "Renamed Branch"
    assert tail_binds[2] == "2024-03-01T00:00:00+00:00"
    assert tail_binds[3] == INFINITY_INSTANT


def test_bitemporal_update_after_a_find_keeps_the_observed_value_object_document() -> None:
    # A keyed write derives carry-forward values from the observed payload, so a
    # Value Object document omitted by the sparse copy must survive in both chains.
    address: dict[str, object] = {
        "street": "10 Old Road",
        "city": "Helsinki",
        "geo": {"country": "FI"},
        "phones": [],
    }
    port = ScriptedPort(Transact(Read(rows=[_branch_row(address=address)]), Write(times=3)))
    db = db_for(MODELS["branch"], port)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(mm.Branch.where(mm.Branch.id == 1).as_of(valid_time=LATEST)).result()
        tx.update(
            fetched.edit(name="Renamed Branch"),
            valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
        )

    db.transact(fn)
    write_ops = [op for op in port.calls if isinstance(op, WriteCall)]
    assert len(write_ops) == 3
    # BOTH chained rectangles carry the document, not just the one whose
    # payload the edited copy supplied.
    for op in write_ops[1:]:
        binds = op.binds
        assert binds[-1] == JsonDocument(value=address), binds


def test_a_materialized_temporal_node_still_populates_real_axis_values() -> None:
    # A materialized read passes every fetched column, so its axis fields contain
    # the row's coordinates rather than fresh-instance defaults.
    port = ScriptedPort(
        Transact(Read(rows=[balance_row(in_z=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))]))
    )
    db = db_for(BALANCE, port)
    fetched = db.transact(lambda tx: tx.find(mm.Balance.where(mm.Balance.id == 1)).result())
    assert fetched.tx_start == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    assert fetched.tx_end is not None


def _balance_history_rows() -> list[Row]:
    # Two milestones on the SAME Transaction-Time dimension, closed then current.
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

    port = ScriptedPort(Read(rows=_balance_history_rows()))
    db = Database.connect(port, BALANCE, clock=FixedClock(FIXED))
    # `.limit(...)` after `.history()` also pins that a cap is a SIBLING clause:
    # `scans_an_axis` reads the Temporal Selection map, so no other clause can
    # stand between the scan and its classification.
    query = mm.Balance.where(mm.Balance.id == 1).history(TX_TIME).limit(5)
    snapshot = db.find(query)
    assert len(snapshot.results()) == 2
    assert snapshot.pin == Pin()  # the whole-graph pin is per-milestone, not here


def test_tx_find_returns_one_snapshot_root_per_milestone_for_a_history_statement() -> None:
    port = ScriptedPort(Transact(Read(rows=_balance_history_rows())))
    db = Database.connect(port, BALANCE, clock=FixedClock(FIXED))
    statement = mm.Balance.where(mm.Balance.id == 1).history(TX_TIME)
    snapshot = db.transact(lambda tx: tx.find(statement))
    assert len(snapshot.results()) == 2


# --------------------------------------------------------------------------- #
# The spec §3 stale-web-edit recipe module (`parallax.conformance.            #
# stale_web_edit`) — the Docker-free halves of the api-conformance stories:   #
# render captures the transported edge; submit reads the CURRENT milestone    #
# and compares its edge against the transported one.                         #
# --------------------------------------------------------------------------- #
def test_stale_web_edit_balance_render_then_submit_gates_on_the_observed_edge() -> None:
    in_z = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    port = ScriptedPort(
        Read(rows=[balance_row(in_z=in_z)]),
        Transact(Read(rows=[balance_row(in_z=in_z)]), Write(times=2)),
    )
    db = db_for(BALANCE, port)

    node, edge = stale_web_edit.render_balance_milestone(db, id=1)
    assert node.value == Decimal("5.00")
    assert edge.tx_time == in_z
    assert edge.valid_time_or_none is None  # Transaction-Time-Only declares no Valid Time

    stale_web_edit.submit_balance_edit(db, id=1, edge=edge, fields={"value": Decimal("9.00")})
    write_ops = [op for op in port.calls if isinstance(op, WriteCall)]
    close_sql = write_ops[0].sql
    close_binds = write_ops[0].binds
    assert close_sql == POSTGRES.to_driver_sql(
        "update balance set out_z = ? where bal_id = ? and out_z = ? and in_z = ?"
    )
    # The gate binds the coordinate the submit's OWN read observed. The
    # transported edge never reaches the statement — it is only ever compared,
    # and the comparison passing is what says the two coordinates agree.
    assert close_binds[-1] == in_z
    # The chained replacement row preserves fields omitted from the submitted edit.
    chain_binds = write_ops[1].binds
    assert "A-1" in chain_binds
    assert Decimal("9.00") in chain_binds


def test_stale_web_edit_balance_submit_refuses_a_milestone_superseded_before_the_read() -> None:
    # The render read one milestone; by the submit read a concurrent writer has
    # chained a replacement, so the CURRENT milestone's edge is not the
    # transported one. The recipe's own comparison refuses, and nothing is
    # authored — the earlier of the two points staleness surfaces at.
    rendered_in_z = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    superseding_in_z = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
    port = ScriptedPort(
        Read(rows=[balance_row(in_z=rendered_in_z)]),
        Transact(Read(rows=[balance_row(in_z=superseding_in_z)])),
    )
    db = db_for(BALANCE, port)

    _node, edge = stale_web_edit.render_balance_milestone(db, id=1)
    assert edge.tx_time == rendered_in_z

    with pytest.raises(stale_web_edit.StaleMilestoneError, match="superseded"):
        stale_web_edit.submit_balance_edit(db, id=1, edge=edge, fields={"value": Decimal("9.00")})
    assert not any(isinstance(op, WriteCall) for op in port.calls)


def test_stale_web_edit_balance_submit_conflict_raises_optimistic_lock_conflict() -> None:
    # The later of the two points staleness surfaces at: the submit read saw
    # the milestone the form displayed, so the comparison passes, and a writer
    # chains a replacement between that read and the flush. The observed `in_z`
    # is stale by then, so the gated close matches ZERO rows -- which is the
    # window `optimistic` covers by gating and `locking` covers by holding a
    # shared read lock on the row the comparison passed on.
    in_z = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    port = ScriptedPort(
        Read(rows=[balance_row(in_z=in_z)]),
        Transact(Read(rows=[balance_row(in_z=in_z)]), Write(affected=0)),
    )
    db = db_for(BALANCE, port)
    _node, edge = stale_web_edit.render_balance_milestone(db, id=1)

    with pytest.raises(OptimisticLockConflictError):
        stale_web_edit.submit_balance_edit(db, id=1, edge=edge, fields={"value": Decimal("9.00")})


def _branch_milestone_row(*, from_z: dt.datetime, in_z: dt.datetime) -> Row:
    return {
        "br_id": 1,
        "name": "Old Name",
        "from_z": from_z,
        "thru_z": INFINITY_INSTANT,
        "in_z": in_z,
        "out_z": INFINITY_INSTANT,
        "address": SQL_NULL,
    }


def test_stale_web_edit_branch_render_then_submit_pins_valid_time_only() -> None:
    # The bitemporal variant transports both coordinates but replays them
    # differently: Valid Time is PINNED, because a finite Valid-Time pin selects
    # which rectangle was displayed and stays writable, while Transaction Time
    # is COMPARED against the rectangle's current milestone.
    from_z = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    in_z = dt.datetime(2024, 1, 15, tzinfo=dt.UTC)
    port = ScriptedPort(
        Read(rows=[_branch_milestone_row(from_z=from_z, in_z=in_z)]),
        Transact(Read(rows=[_branch_milestone_row(from_z=from_z, in_z=in_z)]), Write(times=3)),
    )
    db = db_for(MODELS["branch"], port)

    node, edge = stale_web_edit.render_branch_milestone(db, id=1)
    assert node.name == "Old Name"
    assert edge.valid_time == from_z
    assert edge.tx_time == in_z

    stale_web_edit.submit_branch_edit(
        db,
        id=1,
        edge=edge,
        fields={"name": "New Name"},
        valid_from=dt.datetime(2024, 2, 1, tzinfo=dt.UTC),
    )
    submit_read_binds = [op for op in port.calls if isinstance(op, ReadCall)][1].binds
    # The transported Valid-Time coordinate reaches the submit read's own
    # containment terms; the Transaction-Time one never reaches a statement.
    assert from_z.isoformat() in submit_read_binds
    assert in_z.isoformat() not in submit_read_binds
    write_ops = [op for op in port.calls if isinstance(op, WriteCall)]
    close_sql = write_ops[0].sql
    close_binds = write_ops[0].binds
    assert close_sql.startswith("update branch set out_z = ")
    assert in_z in close_binds  # the OBSERVED Transaction-Time coordinate gates the close
    # The correction's replacement rows carry the edited field.
    assert any("New Name" in op.binds for op in write_ops[1:])


def test_stale_web_edit_branch_submit_refuses_a_rectangle_superseded_before_the_read() -> None:
    # The Valid-Time pin still selects the displayed RECTANGLE, so a concurrent
    # correction is not hidden by it: the pinned re-read answers that
    # rectangle's current milestone, whose Transaction-Time coordinate is the
    # concurrent writer's, and the comparison refuses.
    from_z = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    rendered_in_z = dt.datetime(2024, 1, 15, tzinfo=dt.UTC)
    superseding_in_z = dt.datetime(2024, 2, 15, tzinfo=dt.UTC)
    port = ScriptedPort(
        Read(rows=[_branch_milestone_row(from_z=from_z, in_z=rendered_in_z)]),
        Transact(Read(rows=[_branch_milestone_row(from_z=from_z, in_z=superseding_in_z)])),
    )
    db = db_for(MODELS["branch"], port)

    _node, edge = stale_web_edit.render_branch_milestone(db, id=1)
    assert edge.tx_time == rendered_in_z

    with pytest.raises(stale_web_edit.StaleMilestoneError, match="superseded"):
        stale_web_edit.submit_branch_edit(
            db,
            id=1,
            edge=edge,
            fields={"name": "New Name"},
            valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
        )
    assert not any(isinstance(op, WriteCall) for op in port.calls)


# --------------------------------------------------------------------------- #
# The shared read-preflight seam (`_preflight.preflight`), on the         #
# participating path: the ordering is what these pin. `uow.read` force-flushes #
# pending writes, so a read the connected model cannot answer must be refused  #
# BEFORE the unit of work is touched — otherwise an invalid read becomes a     #
# write.                                                                       #
# --------------------------------------------------------------------------- #
def test_tx_find_refuses_a_foreign_target_with_no_adapter_activity() -> None:
    def fn(tx: Transaction) -> None:
        tx.find(mm.Person.where(mm.Person.id == 1))

    with pytest.raises(QueryTargetError) as caught:
        Database.connect(ScriptedPort(Transact()), ACCOUNT, clock=FixedClock(FIXED)).transact(fn)
    assert caught.value.code == "query-target-not-in-model"


def test_tx_find_refuses_a_deferred_execution_feature_with_no_adapter_activity() -> None:
    # The participating path classifies through the SAME seam, so a deferred
    # Feature is refused there too — and before `uow.read`, which is what keeps
    # The boundary's own script stays empty: a refused read never force-flushes.
    def fn(tx: Transaction) -> None:
        tx.find(
            Policy.where(Policy.all)
            .history(TX_TIME)
            .as_of(valid_time=LATEST)
            .include(Policy.coverages)
        )

    with pytest.raises(DeferredFeatureError) as caught:
        Database.connect(ScriptedPort(Transact()), POLICY_MODEL, clock=FixedClock(FIXED)).transact(
            fn
        )
    assert caught.value.code == "execution-feature-deferred"
    assert caught.value.features == ("snapshot-history-includes",)


def test_tx_find_preflight_rejects_before_a_pending_write_can_flush() -> None:
    port = ScriptedPort(Transact(Write()))

    def fn(tx: Transaction) -> None:
        tx.insert(new_account())
        with pytest.raises(QueryTargetError):
            tx.find(mm.Person.where(mm.Person.id == 1))
        # The buffered insert is still pending: preflight refused ahead of
        # `uow.read`, so the force-flush that a valid read performs
        # (`test_find_force_flushes_pending_writes_first`) never ran.
        assert port.calls == [BeginCall()]

    Database.connect(port, ACCOUNT, clock=FixedClock(FIXED)).transact(fn)
    assert port.calls == [BeginCall(), WriteCall(INSERT_SQL, (7, "Newton", 5.00, 1)), CommitCall()]


# --------------------------------------------------------------------------- #
# An observation is keyed by the ROW's own resolved Entity Identity, so every  #
# node a participating read materialized is reachable by the keyed write that  #
# names it. One function decides all of these, so each shape gets one proof:   #
# an included child, an included POLYMORPHIC level's concrete, and an          #
# abstract-target root's concrete. Both licensing consumers — the temporal     #
# milestone license at the verb and the versioned advance/gate at the planner  #
# — are exercised across the first two.                                        #
# --------------------------------------------------------------------------- #
def _policy_row(from_z: dt.datetime) -> Row:
    return {
        "id": 1,
        "name": "P-1",
        "from_z": from_z,
        "thru_z": INFINITY_INSTANT,
        "in_z": from_z,
        "out_z": INFINITY_INSTANT,
    }


def _coverage_row(from_z: dt.datetime) -> Row:
    return {
        "id": 10,
        "policy_id": 1,
        "amount": Decimal("250.00"),
        "from_z": from_z,
        "thru_z": INFINITY_INSTANT,
        "in_z": from_z,
        "out_z": INFINITY_INSTANT,
    }


def test_an_included_temporal_nodes_own_observation_licenses_its_keyed_close() -> None:
    # The included level's observation is exactly what the write-evidence rule
    # demands of a keyed close, so the close it licenses reaches DML: the level
    # is observed under the row's own `Coverage`, which is what
    # `tx.terminate(policy.coverages[0], ...)` looks up.
    from_z = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    port = ScriptedPort(
        Transact(
            Read(rows=[_policy_row(from_z)]), Read(rows=[_coverage_row(from_z)]), Write(times=2)
        )
    )

    def fn(tx: Transaction) -> None:
        policy = tx.find(
            Policy.where(Policy.id == 1).as_of(valid_time=LATEST).include(Policy.coverages)
        ).result()
        tx.terminate(policy.coverages[0], valid_from=dt.datetime(2024, 6, 1, tzinfo=dt.UTC))

    db_for(POLICY_MODEL, port).transact(fn)
    write_ops = [op for op in port.calls if isinstance(op, WriteCall)]
    assert write_ops[0].sql.startswith(POSTGRES.to_driver_sql("update coverage set out_z = "))
    assert any(10 in op.binds for op in write_ops)


def test_an_included_versioned_nodes_own_observation_licenses_its_keyed_update() -> None:
    # The versioned licensing consumer, reached through the planner rather than
    # the verb: the update's advance and its optimistic gate both come from the
    # included level's own observation, so a lookup that missed it would raise
    # `UnobservedVersionError` before any DML.
    port = ScriptedPort(
        Transact(
            Read(rows=[{"id": 1, "name": "V-1"}]),
            Read(rows=[{"id": 10, "vault_id": 1, "memo": "before", "version": 4}]),
            Write(),
        )
    )

    def fn(tx: Transaction) -> None:
        vault = tx.find(om.Vault.where(om.Vault.id == 1).include(om.Vault.slips)).result()
        tx.update(vault.slips[0].edit(memo="after"))

    db_for(om.VAULT_MODEL, port).transact(fn, concurrency="optimistic")
    (write_op,) = [op for op in port.calls if isinstance(op, WriteCall)]
    assert write_op.sql == POSTGRES.to_driver_sql(
        "update obs_slip set memo = ?, version = ? where id = ? and version = ?"
    )
    assert write_op.binds == ("after", 5, 10, 4)


def test_an_included_polymorphic_levels_concrete_is_reachable_by_a_keyed_write() -> None:
    # A level spanning two concretes targets the relationship's own abstract
    # position, and each row resolves to its own concrete through the shared
    # table's tag column. The observation follows the ROW, so the close names
    # `Tug` and still finds it.
    in_z = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    port = ScriptedPort(
        Transact(
            Read(rows=[{"id": 1, "name": "F-1"}]),
            Read(
                rows=[
                    {
                        "id": 10,
                        "fleet_id": 1,
                        "name": "T-1",
                        "kind": "tug",
                        "bollard_pull": 30,
                        "deck_area": None,
                        "in_z": in_z,
                        "out_z": INFINITY_INSTANT,
                    },
                    {
                        "id": 11,
                        "fleet_id": 1,
                        "name": "B-1",
                        "kind": "barge",
                        "bollard_pull": None,
                        "deck_area": Decimal("120.00"),
                        "in_z": in_z,
                        "out_z": INFINITY_INSTANT,
                    },
                ]
            ),
            Write(),
        )
    )

    def fn(tx: Transaction) -> None:
        fleet = tx.find(om.Fleet.where(om.Fleet.id == 1).include(om.Fleet.vessels)).result()
        tug = next(vessel for vessel in fleet.vessels if isinstance(vessel, om.Tug))
        tx.terminate(tug)

    db_for(om.FLEET_MODEL, port).transact(fn)
    (write_op,) = [op for op in port.calls if isinstance(op, WriteCall)]
    assert write_op.sql == POSTGRES.to_driver_sql(
        "update obs_vessel set out_z = ? where id = ? and kind = ? and out_z = ? and in_z = ?"
    )
    assert write_op.binds[1:3] == (10, "tug")


def test_an_abstract_target_roots_concrete_is_reachable_by_a_keyed_write() -> None:
    # The same rule with no deep fetch involved at all: one root read over the
    # abstract `Vessel` whose rows each resolve to their own concrete. Keying by
    # the query's target would observe both under `Vessel`, which no keyed write
    # ever names.
    in_z = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    port = ScriptedPort(
        Transact(
            Read(
                rows=[
                    {
                        "id": 11,
                        "fleet_id": 1,
                        "name": "B-1",
                        "kind": "barge",
                        "bollard_pull": None,
                        "deck_area": Decimal("120.00"),
                        "in_z": in_z,
                        "out_z": INFINITY_INSTANT,
                    }
                ]
            ),
            Write(),
        )
    )

    def fn(tx: Transaction) -> None:
        barge = tx.find(om.Vessel.where(om.Vessel.id == 11)).result()
        tx.terminate(barge)

    db_for(om.FLEET_MODEL, port).transact(fn)
    (write_op,) = [op for op in port.calls if isinstance(op, WriteCall)]
    assert write_op.sql == POSTGRES.to_driver_sql(
        "update obs_vessel set out_z = ? where id = ? and kind = ? and out_z = ? and in_z = ?"
    )
    assert write_op.binds[1:3] == (11, "barge")
