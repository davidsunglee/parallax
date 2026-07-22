"""Temporal keyed-write DML lowering unit tests.

Pins ``parallax.snapshot.handle.lower_write``'s TEMPORAL dispatch — audit-only
close-and-chain (`m-txtime-write`) and the full-bitemporal rectangle split
(`m-bitemp-write`) — byte-exact against the corpus goldens (``m-txtime-write-001
..006``, ``m-bitemp-write-001..003/006..009``, ``m-inheritance-090/091/094..097
/105``, ``m-value-object-032/033``), the observed-``in_z`` / Valid-Time-
discriminator gate composed with the ``m-opt-lock`` policy (gated only under
optimistic concurrency, `~parallax.core.opt_lock.gates`), and the two zero-row-
close outcomes (:class:`~parallax.core.opt_lock.OptimisticLockConflictError` for a
gated mismatch, :class:`~parallax.core.opt_lock.StaleWriteError` for an ungated
one).
"""

from __future__ import annotations

import dataclasses

import pytest

from parallax.conformance import models
from parallax.core.db_port import JsonDocument
from parallax.core.descriptor import Metamodel
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.unit_work import Concurrency, KeyedWrite, Observation, PlannedWrite
from parallax.snapshot.handle import (
    LoweredStatement,
    WriteLoweringError,
    lower_temporal_close,
    lower_write,
)

pytestmark = pytest.mark.unit

_MODELS = models.load_models()
BALANCE = _MODELS["balance"]
POSITION = _MODELS["position"]
READING = _MODELS["reading"]
INSTRUMENT = _MODELS["instrument"]
RATE = _MODELS["rate"]
QUOTE = _MODELS["quote"]
SUPPLIER = _MODELS["supplier"]
BRANCH = _MODELS["branch"]


def _lower_full(
    instruction: KeyedWrite,
    meta: Metamodel,
    tx_instant: str,
    *,
    observation: Observation | None = None,
    dialect: Dialect = POSTGRES,
    concurrency: Concurrency = "locking",
) -> list[LoweredStatement]:
    return lower_write(
        PlannedWrite(instruction=instruction, observation=observation),
        meta,
        dialect,
        concurrency,
        tx_instant,
    )


def _lower(
    instruction: KeyedWrite,
    meta: Metamodel,
    tx_instant: str,
    *,
    observation: Observation | None = None,
    dialect: Dialect = POSTGRES,
    concurrency: Concurrency = "locking",
) -> list[tuple[str, tuple[object, ...]]]:
    return [
        (lowered.statement.sql, lowered.statement.binds)
        for lowered in _lower_full(
            instruction,
            meta,
            tx_instant,
            observation=observation,
            dialect=dialect,
            concurrency=concurrency,
        )
    ]


# --------------------------------------------------------------------------- #
# Audit-only (m-txtime-write): insert / close-and-chain update / terminate.     #
# --------------------------------------------------------------------------- #
def test_audit_only_insert_opens_a_current_milestone() -> None:
    # m-txtime-write-001.
    insert = KeyedWrite("insert", "Balance", ({"id": 1, "acctNum": "A", "value": 100.00},))
    statements = _lower(insert, BALANCE, "2024-01-01T00:00:00+00:00")
    assert statements == [
        (
            "insert into balance(bal_id, acct_num, val, in_z, out_z) values (?, ?, ?, ?, ?)",
            (1, "A", 100.00, "2024-01-01T00:00:00+00:00", "infinity"),
        )
    ]


def test_audit_only_update_closes_then_chains_the_authored_full_row() -> None:
    # m-txtime-write-002: an ungated (locking-mode) close, then a chain carrying
    # the instruction's OWN authored FULL row. The observation carries no
    # `payload`, so merging is an identity and the chain is exactly the
    # authored row.
    update = KeyedWrite("update", "Balance", ({"id": 1, "acctNum": "A", "value": 150.00},))
    observation = Observation(tx_start="2024-01-01T00:00:00+00:00")
    statements = _lower(update, BALANCE, "2024-06-01T00:00:00+00:00", observation=observation)
    assert statements == [
        (
            "update balance set out_z = ? where bal_id = ? and out_z = ?",
            ("2024-06-01T00:00:00+00:00", 1, "infinity"),
        ),
        (
            "insert into balance(bal_id, acct_num, val, in_z, out_z) values (?, ?, ?, ?, ?)",
            (1, "A", 150.00, "2024-06-01T00:00:00+00:00", "infinity"),
        ),
    ]


def test_audit_only_terminate_closes_only() -> None:
    # m-txtime-write-003: terminate = close, chain nothing.
    terminate = KeyedWrite("terminate", "Balance", ({"id": 1},))
    statements = _lower(terminate, BALANCE, "2024-08-01T00:00:00+00:00")
    assert statements == [
        (
            "update balance set out_z = ? where bal_id = ? and out_z = ?",
            ("2024-08-01T00:00:00+00:00", 1, "infinity"),
        )
    ]


def test_audit_only_update_carries_every_new_attribute() -> None:
    # m-txtime-write-004: the chained row carries ALL corrected attributes.
    update = KeyedWrite("update", "Balance", ({"id": 1, "acctNum": "B", "value": 250.00},))
    observation = Observation(tx_start="2024-01-01T00:00:00+00:00")
    statements = _lower(update, BALANCE, "2024-06-01T00:00:00+00:00", observation=observation)
    assert statements[1] == (
        "insert into balance(bal_id, acct_num, val, in_z, out_z) values (?, ?, ?, ?, ?)",
        (1, "B", 250.00, "2024-06-01T00:00:00+00:00", "infinity"),
    )


def test_audit_only_update_merges_a_sparse_row_onto_the_observed_payload() -> None:
    # A sparse public `tx.update(copy)` row contains the primary key plus its
    # effective change set. This shape is never authored by the conformance
    # engine, which always supplies
    # a full row) merges onto the observed payload, so the chained row still
    # carries `acctNum` even though the instruction's own row never named it.
    sparse_update = KeyedWrite("update", "Balance", ({"id": 1, "value": 150.00},))
    observation = Observation(
        tx_start="2024-01-01T00:00:00+00:00", payload={"id": 1, "acctNum": "A", "value": 100.00}
    )
    statements = _lower(
        sparse_update, BALANCE, "2024-06-01T00:00:00+00:00", observation=observation
    )
    assert statements[1] == (
        "insert into balance(bal_id, acct_num, val, in_z, out_z) values (?, ?, ?, ?, ?)",
        (1, "A", 150.00, "2024-06-01T00:00:00+00:00", "infinity"),
    )


def test_audit_only_plan_merges_the_sparse_row_at_the_planner_seam() -> None:
    # The same merge is pinned directly at the pure planning seam
    # (`parallax.core.txtime_write.plan`) rather than through the full
    # `lower_write` composition — `MilestoneOpen.row` carries the merged
    # payload, never the caller's sparse row alone.
    from parallax.core import txtime_write

    sparse_update = KeyedWrite("update", "Balance", ({"id": 1, "value": 150.00},))
    observation = Observation(
        tx_start="2024-01-01T00:00:00+00:00", payload={"id": 1, "acctNum": "A", "value": 100.00}
    )
    plan = txtime_write.plan(
        sparse_update, BALANCE.entity("Balance"), "2024-06-01T00:00:00+00:00", observation
    )
    close, opened = plan.steps
    assert isinstance(close, txtime_write.MilestoneClose)
    assert isinstance(opened, txtime_write.MilestoneOpen)
    assert opened.row == {
        "id": 1,
        "acctNum": "A",
        "value": 150.00,
        "tx_start": "2024-06-01T00:00:00+00:00",
        "tx_end": "infinity",
    }


def test_audit_only_plan_carries_a_full_row_unchanged_when_no_payload_is_observed() -> None:
    # The compile-sweep/case-driven engine never populates `Observation.payload`
    # for an audit-only write (it authors FULL rows directly, `_strip_
    # observation`) — the merge is then a strict identity, so no exercised
    # compile-lane emission can ever change (the Part 2 byte-identical guard).
    full_update = KeyedWrite("update", "Balance", ({"id": 1, "acctNum": "A", "value": 150.00},))
    observation = Observation(tx_start="2024-01-01T00:00:00+00:00")  # no payload at all
    from parallax.core import txtime_write

    plan = txtime_write.plan(
        full_update, BALANCE.entity("Balance"), "2024-06-01T00:00:00+00:00", observation
    )
    _close, opened = plan.steps
    assert isinstance(opened, txtime_write.MilestoneOpen)
    assert opened.row["acctNum"] == "A"
    assert opened.row["value"] == 150.00


def test_audit_only_close_is_ungated_under_locking_regardless_of_observation() -> None:
    # m-txtime-write-005: a locking-mode close never binds `in_z`, even when one
    # was observed.
    update = KeyedWrite("update", "Balance", ({"id": 1, "acctNum": "A", "value": 175.00},))
    observation = Observation(tx_start="2024-06-01T00:00:00+00:00")
    statements = _lower_full(
        update, BALANCE, "2024-09-01T00:00:00+00:00", observation=observation, concurrency="locking"
    )
    close = statements[0]
    assert close.statement.sql == "update balance set out_z = ? where bal_id = ? and out_z = ?"
    assert close.expected_affected == 1
    assert close.stale_error is True  # ungated: a mismatch is the non-retriable StaleWriteError


def test_audit_only_close_gates_on_observed_in_z_under_optimistic() -> None:
    # m-txtime-write-006: the gated close binds the observed in_z LAST.
    close_only = KeyedWrite("terminate", "Balance", ({"id": 1},))
    observation = Observation(tx_start="2024-06-01T00:00:00+00:00")
    statements = _lower_full(
        close_only,
        BALANCE,
        "2024-09-01T00:00:00+00:00",
        observation=observation,
        concurrency="optimistic",
    )
    assert len(statements) == 1
    lowered = statements[0]
    assert lowered.statement.sql == (
        "update balance set out_z = ? where bal_id = ? and out_z = ? and in_z = ?"
    )
    assert lowered.statement.binds == (
        "2024-09-01T00:00:00+00:00",
        1,
        "infinity",
        "2024-06-01T00:00:00+00:00",
    )
    assert lowered.expected_affected == 1
    assert (
        lowered.stale_error is False
    )  # gated: a mismatch is the retriable OptimisticLockConflictError


def test_audit_only_insert_is_never_gated() -> None:
    # An INSERT never consults an observation — no close, nothing to gate.
    insert = KeyedWrite("insert", "Balance", ({"id": 9, "acctNum": "D", "value": 100.00},))
    statements = _lower_full(insert, BALANCE, "2024-06-01T00:00:00+00:00", concurrency="optimistic")
    assert len(statements) == 1
    assert statements[0].expected_affected is None


# --------------------------------------------------------------------------- #
# Full bitemporal (m-bitemp-write): the rectangle split and its degenerates.   #
# --------------------------------------------------------------------------- #
_R1_PAYLOAD = {"id": 1, "acctNum": "A", "value": 100.00}


def test_bitemporal_update_until_splits_head_middle_tail() -> None:
    # m-bitemp-write-001.
    update_until = KeyedWrite(
        "updateUntil",
        "Position",
        ({"id": 1, "value": 200.00},),
        valid_from="2024-03-01T00:00:00+00:00",
        until="2024-09-01T00:00:00+00:00",
    )
    observation = Observation(
        tx_start="2024-01-01T00:00:00+00:00",
        valid_start="2024-01-01T00:00:00+00:00",
        valid_end="infinity",
        payload=_R1_PAYLOAD,
    )
    statements = _lower(
        update_until, POSITION, "2024-02-15T00:00:00+00:00", observation=observation
    )
    assert statements == [
        (
            "update position set out_z = ? where pos_id = ? and out_z = ?",
            ("2024-02-15T00:00:00+00:00", 1, "infinity"),
        ),
        (
            "insert into position(pos_id, acct_num, val, from_z, thru_z, in_z, out_z) "
            "values (?, ?, ?, ?, ?, ?, ?)",
            (
                1,
                "A",
                100.00,
                "2024-01-01T00:00:00+00:00",
                "2024-03-01T00:00:00+00:00",
                "2024-02-15T00:00:00+00:00",
                "infinity",
            ),
        ),
        (
            "insert into position(pos_id, acct_num, val, from_z, thru_z, in_z, out_z) "
            "values (?, ?, ?, ?, ?, ?, ?)",
            (
                1,
                "A",
                200.00,
                "2024-03-01T00:00:00+00:00",
                "2024-09-01T00:00:00+00:00",
                "2024-02-15T00:00:00+00:00",
                "infinity",
            ),
        ),
        (
            "insert into position(pos_id, acct_num, val, from_z, thru_z, in_z, out_z) "
            "values (?, ?, ?, ?, ?, ?, ?)",
            (
                1,
                "A",
                100.00,
                "2024-09-01T00:00:00+00:00",
                "infinity",
                "2024-02-15T00:00:00+00:00",
                "infinity",
            ),
        ),
    ]


def test_bitemporal_terminate_until_chains_head_and_tail_no_middle() -> None:
    # m-bitemp-write-002.
    terminate_until = KeyedWrite(
        "terminateUntil",
        "Position",
        ({"id": 1},),
        valid_from="2024-03-01T00:00:00+00:00",
        until="2024-09-01T00:00:00+00:00",
    )
    observation = Observation(
        tx_start="2024-01-01T00:00:00+00:00",
        valid_start="2024-01-01T00:00:00+00:00",
        valid_end="infinity",
        payload=_R1_PAYLOAD,
    )
    statements = _lower(
        terminate_until, POSITION, "2024-02-15T00:00:00+00:00", observation=observation
    )
    assert len(statements) == 3
    assert statements[1][1][2] == 100.00  # head carries the OLD value
    assert statements[2][1][2] == 100.00  # tail carries the OLD value too (no middle)
    assert statements[2][1][3:5] == ("2024-09-01T00:00:00+00:00", "infinity")


def test_bitemporal_insert_until_opens_one_bounded_rectangle() -> None:
    # m-bitemp-write-003: no close, a single INSERT.
    insert_until = KeyedWrite(
        "insertUntil",
        "Position",
        ({"id": 1, "acctNum": "A", "value": 100.00},),
        valid_from="2024-03-01T00:00:00+00:00",
        until="2024-09-01T00:00:00+00:00",
    )
    statements = _lower(insert_until, POSITION, "2024-01-01T00:00:00+00:00")
    assert statements == [
        (
            "insert into position(pos_id, acct_num, val, from_z, thru_z, in_z, out_z) "
            "values (?, ?, ?, ?, ?, ?, ?)",
            (
                1,
                "A",
                100.00,
                "2024-03-01T00:00:00+00:00",
                "2024-09-01T00:00:00+00:00",
                "2024-01-01T00:00:00+00:00",
                "infinity",
            ),
        )
    ]


def test_bitemporal_plain_update_splits_head_and_new_tail_only() -> None:
    # m-bitemp-write-006: the two-way degenerate — no middle, no old tail.
    update = KeyedWrite(
        "update",
        "Position",
        ({"id": 1, "value": 200.00},),
        valid_from="2024-06-01T00:00:00+00:00",
    )
    observation = Observation(
        tx_start="2024-01-01T00:00:00+00:00",
        valid_start="2024-01-01T00:00:00+00:00",
        valid_end="infinity",
        payload=_R1_PAYLOAD,
    )
    statements = _lower(update, POSITION, "2024-07-01T00:00:00+00:00", observation=observation)
    assert statements == [
        (
            "update position set out_z = ? where pos_id = ? and out_z = ?",
            ("2024-07-01T00:00:00+00:00", 1, "infinity"),
        ),
        (
            "insert into position(pos_id, acct_num, val, from_z, thru_z, in_z, out_z) "
            "values (?, ?, ?, ?, ?, ?, ?)",
            (
                1,
                "A",
                100.00,
                "2024-01-01T00:00:00+00:00",
                "2024-06-01T00:00:00+00:00",
                "2024-07-01T00:00:00+00:00",
                "infinity",
            ),
        ),
        (
            "insert into position(pos_id, acct_num, val, from_z, thru_z, in_z, out_z) "
            "values (?, ?, ?, ?, ?, ?, ?)",
            (
                1,
                "A",
                200.00,
                "2024-06-01T00:00:00+00:00",
                "infinity",
                "2024-07-01T00:00:00+00:00",
                "infinity",
            ),
        ),
    ]


def test_bitemporal_plain_terminate_chains_head_only() -> None:
    # m-bitemp-write-007.
    terminate = KeyedWrite(
        "terminate", "Position", ({"id": 1},), valid_from="2024-06-01T00:00:00+00:00"
    )
    observation = Observation(
        tx_start="2024-01-01T00:00:00+00:00",
        valid_start="2024-01-01T00:00:00+00:00",
        valid_end="infinity",
        payload=_R1_PAYLOAD,
    )
    statements = _lower(terminate, POSITION, "2024-07-01T00:00:00+00:00", observation=observation)
    assert statements == [
        (
            "update position set out_z = ? where pos_id = ? and out_z = ?",
            ("2024-07-01T00:00:00+00:00", 1, "infinity"),
        ),
        (
            "insert into position(pos_id, acct_num, val, from_z, thru_z, in_z, out_z) "
            "values (?, ?, ?, ?, ?, ?, ?)",
            (
                1,
                "A",
                100.00,
                "2024-01-01T00:00:00+00:00",
                "2024-06-01T00:00:00+00:00",
                "2024-07-01T00:00:00+00:00",
                "infinity",
            ),
        ),
    ]


def test_bitemporal_plain_insert_opens_one_fully_current_rectangle() -> None:
    # m-bitemp-write-009.
    insert = KeyedWrite(
        "insert",
        "Position",
        ({"id": 1, "acctNum": "A", "value": 100.00},),
        valid_from="2024-01-01T00:00:00+00:00",
    )
    statements = _lower(insert, POSITION, "2024-01-01T00:00:00+00:00")
    assert statements == [
        (
            "insert into position(pos_id, acct_num, val, from_z, thru_z, in_z, out_z) "
            "values (?, ?, ?, ?, ?, ?, ?)",
            (
                1,
                "A",
                100.00,
                "2024-01-01T00:00:00+00:00",
                "infinity",
                "2024-01-01T00:00:00+00:00",
                "infinity",
            ),
        )
    ]


def test_bitemporal_close_composes_the_business_discriminator_and_in_z_gate() -> None:
    # m-bitemp-write-004/008: the gated close binds `from_z` BEFORE `in_z`, LAST.
    # A standalone close-only probe (the m-opt-lock conflict lane's own shape) is
    # NOT a real bitemporal mutation (every real close-bearing verb chains at
    # least a head) — `lower_temporal_close` composes it directly.
    lowered = lower_temporal_close(
        {"id": 1},
        "Position",
        POSITION,
        POSTGRES,
        "optimistic",
        "2024-10-01T00:00:00+00:00",
        "2024-04-01T00:00:00+00:00",
        "2024-06-01T00:00:00+00:00",
    )
    assert lowered.statement.sql == (
        "update position set out_z = ? where pos_id = ? and out_z = ? and from_z = ? and in_z = ?"
    )
    assert lowered.statement.binds == (
        "2024-10-01T00:00:00+00:00",
        1,
        "infinity",
        "2024-06-01T00:00:00+00:00",
        "2024-04-01T00:00:00+00:00",
    )
    assert lowered.expected_affected == 1
    assert lowered.stale_error is False


def test_bitemporal_close_is_fully_ungated_under_locking() -> None:
    # m-bitemp-write-001/006/007's own locking-mode closes: neither from_z nor
    # in_z, regardless of the observation carried.
    lowered = lower_temporal_close(
        {"id": 1},
        "Position",
        POSITION,
        POSTGRES,
        "locking",
        "2024-10-01T00:00:00+00:00",
        "2024-04-01T00:00:00+00:00",
        "2024-06-01T00:00:00+00:00",
    )
    assert lowered.statement.sql == "update position set out_z = ? where pos_id = ? and out_z = ?"
    assert lowered.stale_error is True


def test_temporal_close_requires_an_effective_table() -> None:
    balance = dataclasses.replace(BALANCE.entity("Balance"), table=None)
    malformed = Metamodel(entities=(balance,))
    with pytest.raises(WriteLoweringError, match="temporal write target has no effective table"):
        lower_temporal_close(
            {"id": 1},
            "Balance",
            malformed,
            POSTGRES,
            "locking",
            "2024-10-01T00:00:00+00:00",
            None,
        )


# --------------------------------------------------------------------------- #
# Inheritance composition (m-inheritance x m-txtime-write / m-bitemp-write).    #
# --------------------------------------------------------------------------- #
def test_tph_txtime_terminate_carries_the_tag_guard() -> None:
    # m-inheritance-090: the tag guard rides the identity predicates, before
    # the current-row predicate.
    terminate = KeyedWrite("terminate", "MeterReading", ({"id": 1},))
    statements = _lower(terminate, READING, "2024-08-01T00:00:00+00:00")
    assert statements == [
        (
            "update reading set out_z = ? where id = ? and kind = ? and out_z = ?",
            ("2024-08-01T00:00:00+00:00", 1, "meter", "infinity"),
        )
    ]


def test_tpcs_txtime_terminate_has_no_tag_guard() -> None:
    # m-inheritance-091: table-per-concrete-subtype routes to the concrete's
    # own table, no tag.
    terminate = KeyedWrite("terminate", "SpotQuote", ({"id": 1},))
    statements = _lower(terminate, QUOTE, "2024-08-01T00:00:00+00:00")
    assert statements == [
        (
            "update spot_quote set out_z = ? where id = ? and out_z = ?",
            ("2024-08-01T00:00:00+00:00", 1, "infinity"),
        )
    ]


def test_tph_bitemporal_terminate_carries_the_tag_guard() -> None:
    # m-inheritance-094.
    terminate = KeyedWrite(
        "terminate", "Bond", ({"id": 1},), valid_from="2024-06-01T00:00:00+00:00"
    )
    observation = Observation(
        tx_start="2024-01-01T00:00:00+00:00",
        valid_start="2024-01-01T00:00:00+00:00",
        valid_end="infinity",
        payload={"id": 1, "price": 100.00, "coupon": 5.00},
    )
    statements = _lower(terminate, INSTRUMENT, "2024-07-01T00:00:00+00:00", observation=observation)
    assert statements[0] == (
        "update instrument set out_z = ? where id = ? and kind = ? and out_z = ?",
        ("2024-07-01T00:00:00+00:00", 1, "bond", "infinity"),
    )
    assert statements[1][1][:3] == (1, "bond", 100.00)


def test_tpcs_bitemporal_terminate_has_no_tag_guard() -> None:
    # m-inheritance-095: routes to the concrete `deposit_rate` table.
    terminate = KeyedWrite(
        "terminate", "DepositRate", ({"id": 1},), valid_from="2024-06-01T00:00:00+00:00"
    )
    observation = Observation(
        tx_start="2024-01-01T00:00:00+00:00",
        valid_start="2024-01-01T00:00:00+00:00",
        valid_end="infinity",
        payload={"id": 1, "amount": 2.50, "grade": "A"},
    )
    statements = _lower(terminate, RATE, "2024-07-01T00:00:00+00:00", observation=observation)
    assert statements[0] == (
        "update deposit_rate set out_z = ? where id = ? and out_z = ?",
        ("2024-07-01T00:00:00+00:00", 1, "infinity"),
    )


def test_tph_bitemporal_terminate_until_chains_head_and_tail() -> None:
    # m-inheritance-096.
    terminate_until = KeyedWrite(
        "terminateUntil",
        "Stock",
        ({"id": 2},),
        valid_from="2024-03-01T00:00:00+00:00",
        until="2024-09-01T00:00:00+00:00",
    )
    observation = Observation(
        tx_start="2024-01-01T00:00:00+00:00",
        valid_start="2024-01-01T00:00:00+00:00",
        valid_end="infinity",
        payload={"id": 2, "price": 100.00, "ticker": "ACME"},
    )
    statements = _lower(
        terminate_until, INSTRUMENT, "2024-02-15T00:00:00+00:00", observation=observation
    )
    assert len(statements) == 3
    assert statements[0] == (
        "update instrument set out_z = ? where id = ? and kind = ? and out_z = ?",
        ("2024-02-15T00:00:00+00:00", 2, "stock", "infinity"),
    )


def test_tpcs_bitemporal_terminate_until_chains_head_and_tail() -> None:
    # m-inheritance-097.
    terminate_until = KeyedWrite(
        "terminateUntil",
        "LoanRate",
        ({"id": 2},),
        valid_from="2024-03-01T00:00:00+00:00",
        until="2024-09-01T00:00:00+00:00",
    )
    observation = Observation(
        tx_start="2024-01-01T00:00:00+00:00",
        valid_start="2024-01-01T00:00:00+00:00",
        valid_end="infinity",
        payload={"id": 2, "amount": 6.75, "spread": 1.25},
    )
    statements = _lower(terminate_until, RATE, "2024-02-15T00:00:00+00:00", observation=observation)
    assert len(statements) == 3
    assert statements[0] == (
        "update loan_rate set out_z = ? where id = ? and out_z = ?",
        ("2024-02-15T00:00:00+00:00", 2, "infinity"),
    )


def test_tph_txtime_optlock_composed_conflict_orders_tag_then_gate_last() -> None:
    # m-inheritance-105: tag guard rides identity predicates, in_z gate LAST.
    close_only = KeyedWrite("terminate", "MeterReading", ({"id": 1},))
    observation = Observation(tx_start="2024-01-01T00:00:00+00:00")
    statements = _lower_full(
        close_only,
        READING,
        "2024-09-01T00:00:00+00:00",
        observation=observation,
        concurrency="optimistic",
    )
    lowered = statements[0]
    assert lowered.statement.sql == (
        "update reading set out_z = ? where id = ? and kind = ? and out_z = ? and in_z = ?"
    )
    assert lowered.statement.binds == (
        "2024-09-01T00:00:00+00:00",
        1,
        "meter",
        "infinity",
        "2024-01-01T00:00:00+00:00",
    )


# --------------------------------------------------------------------------- #
# Value objects ride milestone chaining whole, absent from the close.         #
# --------------------------------------------------------------------------- #
def test_audit_only_update_carries_the_value_object_document_on_the_chain() -> None:
    # m-value-object-032.
    d2: dict[str, object] = {
        "street": "2 New Avenue",
        "city": "Bergen",
        "geo": {"country": "NO"},
        "phones": [],
    }
    update = KeyedWrite("update", "Supplier", ({"id": 1, "name": "Nordic Foods", "address": d2},))
    observation = Observation(tx_start="2024-01-01T00:00:00+00:00")
    statements = _lower_full(update, SUPPLIER, "2024-06-01T00:00:00+00:00", observation=observation)
    close, chain = statements
    assert close.statement.sql == "update supplier set out_z = ? where sup_id = ? and out_z = ?"
    assert chain.statement.binds[-1] == JsonDocument(d2)


def test_bitemporal_update_until_carries_the_value_object_document_on_every_chain() -> None:
    # m-value-object-033: the document rides head/middle/tail — old, new, old.
    d1: dict[str, object] = {
        "street": "10 Old Road",
        "city": "Helsinki",
        "geo": {"country": "FI"},
        "phones": [],
    }
    d2: dict[str, object] = {
        "street": "30 New Road",
        "city": "Tampere",
        "geo": {"country": "FI"},
        "phones": [],
    }
    update_until = KeyedWrite(
        "updateUntil",
        "Branch",
        ({"id": 1, "name": "Central Branch", "address": d2},),
        valid_from="2024-03-01T00:00:00+00:00",
        until="2024-09-01T00:00:00+00:00",
    )
    observation = Observation(
        tx_start="2024-01-01T00:00:00+00:00",
        valid_start="2024-01-01T00:00:00+00:00",
        valid_end="infinity",
        payload={"name": "Central Branch", "address": d1},
    )
    statements = _lower_full(
        update_until, BRANCH, "2024-02-15T00:00:00+00:00", observation=observation
    )
    close, head, middle, tail = statements
    assert close.statement.sql == "update branch set out_z = ? where br_id = ? and out_z = ?"
    assert head.statement.binds[-1] == JsonDocument(d1)
    assert middle.statement.binds[-1] == JsonDocument(d2)
    assert tail.statement.binds[-1] == JsonDocument(d1)


# --------------------------------------------------------------------------- #
# Zero-row close: the two distinct outcomes (m-opt-lock / m-txtime-write).      #
# --------------------------------------------------------------------------- #
def test_multi_row_temporal_write_is_refused() -> None:
    # A temporal keyed write lowers ONE row at a time: each row opens its own
    # milestone chain (`m-txtime-write` / `m-bitemp-write`), so there is no
    # shared statement a collapse could render. `m-batch-write`'s eligibility
    # never collapses a temporal entity, so reaching here with two rows is a
    # caller wiring defect — refused, never lowered as if only the first row
    # existed.
    batched = KeyedWrite(
        "update",
        "Balance",
        ({"id": 1, "value": 100.00}, {"id": 2, "value": 200.00}),
    )
    with pytest.raises(WriteLoweringError, match="multi-row temporal 'update' on 'Balance'"):
        _lower(batched, BALANCE, "2024-02-15T00:00:00+00:00")


def test_temporal_write_requires_a_transaction_instant() -> None:
    # A defensive backstop (`FlushPlan.tx_instant` is always populated by a real
    # flush; no reachable case skips it) — never a wrong emission.
    insert = KeyedWrite("insert", "Balance", ({"id": 1, "acctNum": "A", "value": 100.00},))
    with pytest.raises(WriteLoweringError, match="no transaction instant supplied"):
        lower_write(PlannedWrite(instruction=insert), BALANCE, POSTGRES, "locking")


# --------------------------------------------------------------------------- #
# txtime_write.axis_attr_names: the declared-axis lookup, direct.              #
# --------------------------------------------------------------------------- #
def test_axis_attr_names_refuses_an_axis_the_entity_does_not_declare() -> None:
    # Balance is audit-only (Transaction-Time dimension only) — a caller asking this pure
    # lookup for its (undeclared) Valid-Time dimension is a defensive backstop the
    # render seam is responsible for never reaching with a well-formed
    # instruction (`txtime_write._axis`), not a normal-path outcome.
    from parallax.core import txtime_write

    with pytest.raises(txtime_write.TemporalPlanningError, match="declares no 'validTime'"):
        txtime_write.axis_attr_names(BALANCE.entity("Balance"), "validTime")
