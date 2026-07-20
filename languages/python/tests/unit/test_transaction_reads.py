"""Participating-read unit tests for `parallax.snapshot.handle` (spec §5, Docker-free fake ports).

`Transaction.find` and `Database.find`: force-flush before a read
(read-your-own-writes), the participation-mode lock suffix, statement and
milestone pin derivation, history statements, and the observations a read leaves
behind — proven through the writes they license or refuse. Also the spec §3
stale-web-edit recipe's Docker-free halves.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import cast

import pytest
from _transact_support import (
    BALANCE,
    FIND_SQL,
    FIND_SQL_NO_LOCK,
    FIXED,
    INFINITY_INSTANT,
    INSERT_SQL,
    NEW_ROW,
    PAYMENT,
    RecordingPort,
    account_db,
    balance_row,
    db_for,
    new_account,
)

import inheritance_models as im
import mirrored_models as mm
from parallax.conformance import models, stale_web_edit
from parallax.core import opt_lock
from parallax.core.db_port import JsonDocument, Row
from parallax.core.dialect import POSTGRES
from parallax.core.unit_work import (
    FixedClock,
)
from parallax.snapshot.handle import Database, Transaction

# One of the three sanctioned private test seams (COR-42): `_pin_from_milestone`
# keeps its underscore because nothing outside `_read` calls it in production, so
# this defensive branch is only reachable from a test.
from parallax.snapshot.handle._read import (
    _pin_from_milestone,  # pyright: ignore[reportPrivateUsage]
)

pytestmark = pytest.mark.unit

# The `_pin_from_milestone` probe's own instant — deliberately NOT the shared
# `FIXED` clock instant: this test builds a milestone pin by hand and asserts the
# same value comes back, so it must not depend on what the fake clock is set to.
_MILESTONE_INSTANT = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


def test_find_on_a_non_versioned_entity_records_no_observation() -> None:
    # `Transaction.find`'s observation recording is defensive: a materialized
    # node whose entity declares no `optimisticLocking` version column (every
    # Payment-family member) is skipped, never raising and never observing
    # anything a later write could consult.
    port = RecordingPort(rows=[{"id": 1, "amount": 100.00, "card_network": "Visa"}])

    def fn(tx: Transaction) -> None:
        tx.find(im.CardPayment.where(im.CardPayment.id == 1)).result()

    db_for(PAYMENT, port).transact(fn)
    kinds = [op[0] for op in port.ops]
    assert kinds == ["begin", "read", "commit"]


def test_find_force_flushes_pending_writes_first() -> None:
    # Read-your-own-writes: the buffered insert executes BEFORE the dependent
    # read, inside the same still-open transaction (m-unit-work-001's shape).
    port = RecordingPort(rows=[NEW_ROW])

    def fn(tx: Transaction) -> list[mm.Account]:
        tx.insert(new_account())
        return tx.find(mm.Account.where(mm.Account.id == 7)).results()

    assert account_db(port).transact(fn) == [new_account()]
    assert port.ops == [
        ("begin",),
        ("write", INSERT_SQL, (7, "Newton", 5.00, 1)),
        ("read", FIND_SQL, (7,)),
        ("commit",),
    ]


def test_optimistic_mode_suppresses_the_read_lock_suffix() -> None:
    port = RecordingPort()
    account_db(port).transact(
        lambda tx: tx.find(mm.Account.where(mm.Account.id == 7)), concurrency="optimistic"
    )
    assert port.ops == [("begin",), ("read", FIND_SQL_NO_LOCK, (7,)), ("commit",)]


def test_db_find_pins_an_explicit_as_of_statement() -> None:
    # `statement_pin` reads the statement's OWN temporal wrapper: an explicit
    # `.as_of(processing=LATEST)` pin comes back on the returned `Snapshot`.
    from parallax.core import LATEST

    port = RecordingPort(
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
    db = Database.connect(port, BALANCE, clock=FixedClock(FIXED))
    statement = mm.Balance.where(mm.Balance.id == 1).as_of(processing=LATEST)
    snapshot = db.find(statement)
    assert snapshot.pin.processing is LATEST


def test_db_find_resolves_a_concrete_inheritance_targets_inherited_pin_and_edge() -> None:
    # `DepositRate` declares NO `as_of` of its own (`Rate`, the family root,
    # does) — `_temporal_entity` (`parallax.snapshot.handle`) must resolve
    # through the root to compute both the statement pin and the row's own
    # milestone edge (COR-3 Phase 7 review remediation, P3/P4).
    from parallax.core import LATEST, edge_of

    port = RecordingPort(
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
    db = Database.connect(port, rate, clock=FixedClock(FIXED))
    statement = im.DepositRate.where().as_of(processing=LATEST)
    snapshot = db.find(statement)
    assert snapshot.pin.processing is LATEST
    assert snapshot.pin.business is None
    edge = edge_of(snapshot.result())
    assert edge.processing == dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
    assert edge.business == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


def test_locking_mode_temporal_write_after_an_as_of_find_raises_historical_observation() -> None:
    # An as-of (historical/edge-pinned) find is the ONLY transaction-scoped
    # observation this unit of work has for Balance 1 — a locking-mode close
    # would have nothing but the shared read lock protecting a milestone that
    # is not the current one, so it raises before any DML (`m-opt-lock`
    # "Locking mode additionally requires that the observation be of the
    # current milestone").
    port = RecordingPort(rows=[balance_row(in_z=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))])
    db = db_for(BALANCE, port)

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
    port = RecordingPort(rows=[balance_row(in_z=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))])
    db = db_for(BALANCE, port)

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
    port = RecordingPort(rows=[balance_row(in_z=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))])
    db = db_for(BALANCE, port)

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
    port = RecordingPort(rows=[balance_row(in_z=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))])
    db = db_for(BALANCE, port)

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


def _branch_row(*, address: dict[str, object] | None) -> Row:
    return {
        "br_id": 1,
        "name": "Central Branch",
        "address": address,
        "from_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "thru_z": INFINITY_INSTANT,
        "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "out_z": INFINITY_INSTANT,
    }


def test_bitemporal_update_after_a_find_carries_the_observed_business_bounds() -> None:
    # COR-42 Phase 4: the observable replacement for the former private
    # observation-recording drive. What that test asserted by reading
    # `uow._observations` directly — that a BITEMPORAL node's observation
    # records business_from/business_to and the full payload — is exactly what
    # `bitemp_write.plan` consumes to split the rectangle, so a real
    # `tx.find` -> `tx.update` makes it observable in the emitted DML: the
    # chained rows can only carry `from_z`/`thru_z` and the untouched `name`
    # if the observation recorded them.
    port = RecordingPort(rows=[_branch_row(address=None)])
    db = db_for(models.load_models()["branch"], port)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(mm.Branch.where(mm.Branch.id == 1)).result()
        tx.update(
            fetched.model_copy(update={"name": "Renamed Branch"}),
            business_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
        )

    db.transact(fn)
    write_ops = [op for op in port.ops if op[0] == "write"]
    assert len(write_ops) == 3  # close the rectangle, then chain head + tail
    head_binds = cast("tuple[object, ...]", write_ops[1][2])
    tail_binds = cast("tuple[object, ...]", write_ops[2][2])
    # The HEAD rectangle runs from the OBSERVED business_from up to the
    # mutation instant, and carries the OBSERVED name. Neither value appears
    # anywhere in the sparse edited copy, so both can only have come from the
    # recorded observation.
    assert head_binds[1] == "Central Branch"
    assert head_binds[2] == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    assert head_binds[3] == "2024-03-01T00:00:00+00:00"
    # The TAIL rectangle opens at the mutation instant with the new payload and
    # closes at the OBSERVED business_to. That upper bound is the third value
    # only the observation carries: the edited copy never names it, and without
    # this assertion a corrupted `observation.business_to` goes undetected —
    # the gap the Phases 3-4 review caught by mutating it to 2099.
    assert tail_binds[1] == "Renamed Branch"
    assert tail_binds[2] == "2024-03-01T00:00:00+00:00"
    assert tail_binds[3] == INFINITY_INSTANT


def test_bitemporal_update_after_a_find_keeps_the_observed_value_object_document() -> None:
    # The second former private drive, made observable. A keyed write derives
    # its carry-forward from the recorded observation's payload, so a value-
    # object document the sparse copy never mentions must survive the round
    # trip. Reverting `_temporal_observation` to drop the document makes the
    # chained bind `None` instead of the address mapping — the same regression
    # the private-seam test pinned, now proven through the public verbs.
    address: dict[str, object] = {
        "street": "10 Old Road",
        "city": "Helsinki",
        "geo": {"country": "FI"},
        "phones": [],
    }
    port = RecordingPort(rows=[_branch_row(address=address)])
    db = db_for(models.load_models()["branch"], port)

    def fn(tx: Transaction) -> None:
        fetched = tx.find(mm.Branch.where(mm.Branch.id == 1)).result()
        tx.update(
            fetched.model_copy(update={"name": "Renamed Branch"}),
            business_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
        )

    db.transact(fn)
    write_ops = [op for op in port.ops if op[0] == "write"]
    assert len(write_ops) == 3
    # BOTH chained rectangles carry the document, not just the one whose
    # payload the edited copy supplied.
    for op in write_ops[1:]:
        binds = cast("tuple[object, ...]", op[2])
        assert binds[-1] == JsonDocument(value=address), binds


def test_a_materialized_temporal_node_still_populates_real_axis_values() -> None:
    # D-31's construction optionality only affects a FRESH instance — a
    # materialized read explicitly passes every fetched column, so the
    # resulting node's axis fields are the row's own REAL values, never `None`.
    port = RecordingPort(rows=[balance_row(in_z=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))])
    db = db_for(BALANCE, port)
    fetched = db.transact(lambda tx: tx.find(mm.Balance.where(mm.Balance.id == 1)).result())
    assert fetched.processing_from == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    assert fetched.processing_to is not None


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

    port = RecordingPort(rows=_balance_history_rows())
    db = Database.connect(port, BALANCE, clock=FixedClock(FIXED))
    # `.distinct()` after `.history()` also exercises `is_milestone_set_op`'s
    # own directive-peeling loop (a result-shaping wrapper around the scan).
    statement = mm.Balance.where(mm.Balance.id == 1).history("processing").distinct()
    snapshot = db.find(statement)
    assert len(snapshot.results()) == 2
    assert snapshot.pin == Pin()  # the whole-graph pin is per-milestone, not here


def test_tx_find_returns_one_snapshot_root_per_milestone_for_a_history_statement() -> None:
    port = RecordingPort(rows=_balance_history_rows())
    db = Database.connect(port, BALANCE, clock=FixedClock(FIXED))
    statement = mm.Balance.where(mm.Balance.id == 1).history("processing")
    snapshot = db.transact(lambda tx: tx.find(statement))
    assert len(snapshot.results()) == 2


# --------------------------------------------------------------------------- #
# The spec §3 stale-web-edit recipe module (`parallax.conformance.            #
# stale_web_edit`) — the Docker-free halves of the api-conformance stories:   #
# render captures the transported edge; submit replays it optimistically.     #
# --------------------------------------------------------------------------- #
def test_stale_web_edit_balance_render_then_submit_gates_on_the_transported_edge() -> None:
    in_z = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    port = RecordingPort(rows=[balance_row(in_z=in_z)])
    db = db_for(BALANCE, port)

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
    port = RecordingPort(rows=[balance_row(in_z=in_z)], write_affected=0)
    db = db_for(BALANCE, port)
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
        "thru_z": INFINITY_INSTANT,
        "in_z": in_z,
        "out_z": INFINITY_INSTANT,
        "address": None,
    }
    port = RecordingPort(rows=[branch_row])
    db = db_for(models.load_models()["branch"], port)

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


def test_pin_from_milestone_skips_an_axis_absent_from_the_milestone_pin() -> None:
    # `_pin_from_milestone` is generic over any `Mapping` (not tied to how
    # `_edge_pin` always populates every declared axis in practice) — a
    # bitemporal entity's OWN as-of-attribute loop must skip an axis absent
    # from a given milestone's pin, not KeyError.
    position = models.load_models()["position"].entity("Position")
    pin = _pin_from_milestone(position, {"processingDate": _MILESTONE_INSTANT})
    assert pin.processing == _MILESTONE_INSTANT
    assert pin.business is None
