"""Temporal write finalization and lowering unit tests.

Pins the two halves a temporal mutation crosses — the finalized Planned Close and
Planned Insert successors it expands into, and the DML each of those steps lowers
to — for audit-only close-and-chain (`m-txtime-write`) and the full-bitemporal
rectangle split (`m-bitemp-write`).

The statements stay byte-exact against the corpus goldens (``m-txtime-write-001
..006``, ``m-bitemp-write-001..003/006..009``, ``m-inheritance-090/091/094..097
/105``, ``m-value-object-032/033``). Alongside them the settled steps pin what
lowering can no longer see: the mode-independent Milestone Target (the key plus
one exclusive upper bound per As-Of Axis) against the observed-``in_z`` gate the
concurrency mode decides, each successor's Insert Origin, each close's Close
Cause, and the two zero-row-close shortfall tags
(:class:`~parallax.core.unit_work.OptimisticConflict` for a gated mismatch,
:class:`~parallax.core.unit_work.StaleWrite` for an ungated one).

Most cases here hand the planner one instruction and one observation directly.
Where the question is *which* milestone a write settles against, that shape
cannot ask it — the answer is decided before planning — so those cases drive the
developer verbs over a recording port instead and pin the same emitted DML.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Mapping
from decimal import Decimal
from typing import Final, cast

import pytest
from _corpus_model_support import corpus_records, formed
from _transact_support import (
    INFINITY_INSTANT,
    WHERE_POSITION_META,
    WherePosition,
    db_for,
)

from _support.clock_probes import instant_at
from _support.db_port import (
    Read,
    ScriptedPort,
    Transact,
    Write,
    WriteCall,
)
from _support.lowering_probes import lower_instruction, lower_instruction_steps
from _support.planner_probes import TEST_SUBJECT_IDENTITY
from parallax.core import bitemp_write, storage_layout, txtime_write
from parallax.core.base import INFINITY as OPEN_BOUND
from parallax.core.db_port import JsonDocument, Row
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.metamodel import EntityIdentity, EntityMetadata, TemporalDimension
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.object_query import LATEST
from parallax.core.sql_gen import LoweredStatement, SqlGenError
from parallax.core.sql_gen._write import compile_write
from parallax.core.temporal_read import Edge
from parallax.core.unit_work import (
    INFINITY,
    OPTIMISTIC_CONFLICT,
    STALE_WRITE,
    SUPERSEDED,
    TERMINATED,
    UNGATED,
    CarriedFrom,
    ChangedFrom,
    Concurrency,
    ExactCount,
    Finite,
    FixedClock,
    KeyedMutation,
    KeyedWrite,
    NewLineage,
    ObjectKey,
    PlannedClose,
    PlannedInsert,
    PredecessorRow,
    TemporalGate,
    TemporalObservation,
    TemporalStateKey,
    TransactionSettings,
    UnitOfWork,
    WriteBatchTrigger,
    WriteObservation,
    WritePlan,
    WritePlanningError,
    instant_literal,
    run_unit_of_work,
)
from parallax.core.unit_work.planned import PlannedWrite as PlannedStep
from parallax.descriptor._records import Metamodel
from parallax.snapshot.handle import (
    Transaction,
    build_write_planner,
    plan_temporal_close,
)
from parallax.snapshot.handle._write_inputs import ReadObservations, retain_evidence


def _no_flush(_plan: WritePlan, *, trigger: WriteBatchTrigger) -> None:
    """A flush sink for a test that never flushes."""
    return None


def _accepted(name: str, meta: Metamodel) -> tuple[AcceptedMetamodel, EntityMetadata]:
    """One corpus model and one of its Entities, both accepted."""
    model = formed(meta)
    entity = model.entity(EntityIdentity("parallax.compatibility", name))
    assert entity is not None
    return model, entity


_MODELS = corpus_records()
BALANCE = _MODELS["balance"]
POSITION = _MODELS["position"]
READING = _MODELS["reading"]
INSTRUMENT = _MODELS["instrument"]
RATE = _MODELS["rate"]
QUOTE = _MODELS["quote"]
SUPPLIER = _MODELS["supplier"]
BRANCH = _MODELS["branch"]


def _observed(
    *,
    tx_start: str,
    tx_end: str = "infinity",
    valid_start: str | None = None,
    valid_end: str | None = None,
    payload: Mapping[str, object] | None = None,
) -> TemporalObservation:
    """The predecessor milestone a find would have recorded whole.

    Every corpus model spells its axis bounds `txStart`/`txEnd` and, when it
    declares Valid Time, `validStart`/`validEnd`, so one builder serves them
    all: the bounds join ``payload`` inside the one Predecessor Row, which is
    where a close reads its address and its gate from.
    """
    members: dict[str, object] = dict(payload or {})
    members["txStart"] = _managed_instant(tx_start)
    members["txEnd"] = _managed_instant(tx_end)
    if valid_start is not None:
        members["validStart"] = _managed_instant(valid_start)
    if valid_end is not None:
        members["validEnd"] = _managed_instant(valid_end)
    return TemporalObservation(predecessor=PredecessorRow(members=members))


def _managed_instant(value: str) -> object:
    return OPEN_BOUND if value == "infinity" else _instant(value)


def _instant(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value)


def _canonical_instruction(instruction: KeyedWrite) -> KeyedWrite:
    def canonical(value: str | None) -> str | None:
        return None if value is None else instant_literal(dt.datetime.fromisoformat(value))

    return dataclasses.replace(
        instruction,
        valid_from=canonical(instruction.valid_from),
        until=canonical(instruction.until),
    )


def _lower_full(
    instruction: KeyedWrite,
    meta: Metamodel,
    tx_instant: str,
    *,
    observation: WriteObservation | None = None,
    dialect: Dialect = POSTGRES,
    concurrency: Concurrency = "locking",
) -> list[LoweredStatement]:
    return lower_instruction(
        _canonical_instruction(instruction),
        formed(meta),
        dialect,
        concurrency,
        instant_at(tx_instant),
        observation=observation,
    )


def _lower_steps(
    instruction: KeyedWrite,
    meta: Metamodel,
    tx_instant: str,
    *,
    observation: WriteObservation | None = None,
    dialect: Dialect = POSTGRES,
    concurrency: Concurrency = "locking",
) -> list[tuple[PlannedStep, LoweredStatement]]:
    """The same statements, paired with the settled step each came from."""
    return lower_instruction_steps(
        _canonical_instruction(instruction),
        formed(meta),
        dialect,
        concurrency,
        instant_at(tx_instant),
        observation=observation,
    )


def _finalize(
    instruction: KeyedWrite,
    meta: Metamodel,
    tx_instant: str,
    *,
    observation: WriteObservation | None = None,
    concurrency: Concurrency = "locking",
) -> tuple[PlannedStep, ...]:
    steps = lower_instruction_steps(
        _canonical_instruction(instruction),
        formed(meta),
        POSTGRES,
        concurrency,
        instant_at(tx_instant),
        observation=observation,
    )
    return tuple(step for step, _statement in steps)


def _lower(
    instruction: KeyedWrite,
    meta: Metamodel,
    tx_instant: str,
    *,
    observation: WriteObservation | None = None,
    dialect: Dialect = POSTGRES,
    concurrency: Concurrency = "locking",
) -> list[tuple[str, tuple[object, ...]]]:
    return [
        (statement.sql, statement.binds)
        for statement in _lower_full(
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
            (1, "A", 100.00, _instant("2024-01-01T00:00:00+00:00"), "infinity"),
        )
    ]


def test_audit_only_update_closes_then_chains_the_authored_full_row() -> None:
    # m-txtime-write-002: an ungated (locking-mode) close, then a chain carrying
    # the instruction's OWN authored FULL row. The row names every member the
    # predecessor could have carried forward, so merging is an identity and the
    # chain is exactly the authored row.
    update = KeyedWrite("update", "Balance", ({"id": 1, "acctNum": "A", "value": 150.00},))
    observation = _observed(tx_start="2024-01-01T00:00:00+00:00")
    statements = _lower(update, BALANCE, "2024-06-01T00:00:00+00:00", observation=observation)
    assert statements == [
        (
            "update balance set out_z = ? where bal_id = ? and out_z = ?",
            (_instant("2024-06-01T00:00:00+00:00"), 1, "infinity"),
        ),
        (
            "insert into balance(bal_id, acct_num, val, in_z, out_z) values (?, ?, ?, ?, ?)",
            (1, "A", 150.00, _instant("2024-06-01T00:00:00+00:00"), "infinity"),
        ),
    ]


def test_audit_only_terminate_closes_only() -> None:
    # m-txtime-write-003: terminate = close, chain nothing.
    terminate = KeyedWrite("terminate", "Balance", ({"id": 1},))
    statements = _lower(
        terminate,
        BALANCE,
        "2024-08-01T00:00:00+00:00",
        observation=_observed(tx_start="2024-01-01T00:00:00+00:00"),
    )
    assert statements == [
        (
            "update balance set out_z = ? where bal_id = ? and out_z = ?",
            (_instant("2024-08-01T00:00:00+00:00"), 1, "infinity"),
        )
    ]


def test_audit_only_update_carries_every_new_attribute() -> None:
    # m-txtime-write-004: the chained row carries ALL corrected attributes.
    update = KeyedWrite("update", "Balance", ({"id": 1, "acctNum": "B", "value": 250.00},))
    observation = _observed(tx_start="2024-01-01T00:00:00+00:00")
    statements = _lower(update, BALANCE, "2024-06-01T00:00:00+00:00", observation=observation)
    assert statements[1] == (
        "insert into balance(bal_id, acct_num, val, in_z, out_z) values (?, ?, ?, ?, ?)",
        (1, "B", 250.00, _instant("2024-06-01T00:00:00+00:00"), "infinity"),
    )


def test_audit_only_update_merges_a_sparse_row_onto_the_observed_payload() -> None:
    # A sparse public `tx.update(copy)` row contains the primary key plus its
    # effective change set. This shape is never authored by the conformance
    # engine, which always supplies
    # a full row) merges onto the observed payload, so the chained row still
    # carries `acctNum` even though the instruction's own row never named it.
    sparse_update = KeyedWrite("update", "Balance", ({"id": 1, "value": 150.00},))
    observation = _observed(
        tx_start="2024-01-01T00:00:00+00:00", payload={"id": 1, "acctNum": "A", "value": 100.00}
    )
    statements = _lower(
        sparse_update, BALANCE, "2024-06-01T00:00:00+00:00", observation=observation
    )
    assert statements[1] == (
        "insert into balance(bal_id, acct_num, val, in_z, out_z) values (?, ?, ?, ?, ?)",
        (1, "A", 150.00, _instant("2024-06-01T00:00:00+00:00"), "infinity"),
    )


def _member_values(step: PlannedStep) -> dict[str, object]:
    """One single-entry Planned Insert's row, keyed by declared member name."""
    assert isinstance(step, PlannedInsert)
    (entry,) = step.entries
    return {identity.name: value for identity, value in entry.row.attributes.items()} | {
        identity.path[-1]: value for identity, value in entry.row.value_objects.items()
    }


def test_audit_only_update_merges_the_sparse_row_at_the_finalization_seam() -> None:
    # The merge is pinned directly on the settled successor rather than through
    # the rendered statement: the chained row carries the merged payload, never
    # the caller's sparse row alone, and its origin names the predecessor it
    # changed.
    sparse_update = KeyedWrite("update", "Balance", ({"id": 1, "value": 150.00},))
    observation = _observed(
        tx_start="2024-01-01T00:00:00+00:00", payload={"id": 1, "acctNum": "A", "value": 100.00}
    )
    close, opened = _finalize(
        sparse_update, BALANCE, "2024-06-01T00:00:00+00:00", observation=observation
    )
    assert isinstance(close, PlannedClose)
    assert close.cause == SUPERSEDED
    assert _member_values(opened) == {
        "id": 1,
        "acctNum": "A",
        "value": 150.00,
        "txStart": dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
        "txEnd": "infinity",
    }
    assert isinstance(opened, PlannedInsert)
    assert opened.entries[0].origin == ChangedFrom(predecessor=observation.predecessor)


def test_audit_only_update_carries_a_full_authored_row_over_every_observed_member() -> None:
    # The corpus-driven engine authors FULL rows for an audit-only write, so the
    # merge onto the predecessor is a strict identity even though the
    # predecessor carries every member: the authored row overrides each one it
    # names, and no exercised compile-lane emission can change.
    full_update = KeyedWrite("update", "Balance", ({"id": 1, "acctNum": "A", "value": 150.00},))
    observation = _observed(
        tx_start="2024-01-01T00:00:00+00:00",
        payload={"id": 1, "acctNum": "STALE", "value": 999.00},
    )
    _close, opened = _finalize(
        full_update, BALANCE, "2024-06-01T00:00:00+00:00", observation=observation
    )
    row = _member_values(opened)
    assert row["acctNum"] == "A"
    assert row["value"] == 150.00


def test_audit_only_insert_begins_a_lineage_and_closes_nothing() -> None:
    insert = KeyedWrite("insert", "Balance", ({"id": 1, "acctNum": "A", "value": 100.00},))
    (opened,) = _finalize(insert, BALANCE, "2024-01-01T00:00:00+00:00")
    assert isinstance(opened, PlannedInsert)
    assert opened.entries[0].origin == NewLineage()


def test_audit_only_terminate_records_termination_and_chains_nothing() -> None:
    terminate = KeyedWrite("terminate", "Balance", ({"id": 1},))
    (close,) = _finalize(
        terminate,
        BALANCE,
        "2024-08-01T00:00:00+00:00",
        observation=_observed(tx_start="2024-01-01T00:00:00+00:00"),
    )
    assert isinstance(close, PlannedClose)
    assert close.cause == TERMINATED


def test_a_close_without_an_observation_is_a_finalization_error() -> None:
    # Every close addresses, gates on, and carries state forward from the
    # milestone it observed, so a missing observation is refused while the step
    # is settled rather than lowered as an unaddressed statement.
    terminate = KeyedWrite("terminate", "Balance", ({"id": 1},))
    with pytest.raises(WritePlanningError, match="every close requires the Temporal Observation"):
        _finalize(terminate, BALANCE, "2024-08-01T00:00:00+00:00")


def test_a_milestone_verb_on_a_non_temporal_entity_is_refused() -> None:
    terminate = KeyedWrite("terminate", "Account", ({"id": 1},))
    with pytest.raises(ValueError, match="declares no temporal dimension"):
        _finalize(terminate, _MODELS["account"], "2024-08-01T00:00:00+00:00")


def test_audit_only_close_is_ungated_under_locking_regardless_of_observation() -> None:
    # m-txtime-write-005: a locking-mode close never binds `in_z`, even when one
    # was observed.
    update = KeyedWrite("update", "Balance", ({"id": 1, "acctNum": "A", "value": 175.00},))
    observation = _observed(tx_start="2024-06-01T00:00:00+00:00")
    step, close = _lower_steps(
        update, BALANCE, "2024-09-01T00:00:00+00:00", observation=observation, concurrency="locking"
    )[0]
    assert close.sql == "update balance set out_z = ? where bal_id = ? and out_z = ?"
    assert isinstance(step, PlannedClose)
    # ungated: a shortfall is the non-retriable stale write
    assert step.affected_rows == ExactCount(1, STALE_WRITE)


def test_audit_only_close_gates_on_observed_in_z_under_optimistic() -> None:
    # m-txtime-write-006: the gated close binds the observed in_z LAST.
    close_only = KeyedWrite("terminate", "Balance", ({"id": 1},))
    observation = _observed(tx_start="2024-06-01T00:00:00+00:00")
    steps = _lower_steps(
        close_only,
        BALANCE,
        "2024-09-01T00:00:00+00:00",
        observation=observation,
        concurrency="optimistic",
    )
    assert len(steps) == 1
    step, lowered = steps[0]
    assert lowered.sql == (
        "update balance set out_z = ? where bal_id = ? and out_z = ? and in_z = ?"
    )
    assert lowered.binds == (
        _instant("2024-09-01T00:00:00+00:00"),
        1,
        "infinity",
        _instant("2024-06-01T00:00:00+00:00"),
    )
    assert isinstance(step, PlannedClose)
    # gated: a shortfall is the retriable optimistic conflict
    assert step.affected_rows == ExactCount(1, OPTIMISTIC_CONFLICT)


def test_audit_only_insert_is_never_gated() -> None:
    # An INSERT never consults an observation — no close, nothing to gate. A
    # Planned Insert carries neither a gate nor an Affected Rows Policy at all,
    # so the absence is structural rather than a null expectation.
    insert = KeyedWrite("insert", "Balance", ({"id": 9, "acctNum": "D", "value": 100.00},))
    steps = _lower_steps(insert, BALANCE, "2024-06-01T00:00:00+00:00", concurrency="optimistic")
    assert len(steps) == 1
    assert isinstance(steps[0][0], PlannedInsert)


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
    observation = _observed(
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
            "update position set out_z = ? where pos_id = ? and thru_z = ? and out_z = ?",
            (_instant("2024-02-15T00:00:00+00:00"), 1, "infinity", "infinity"),
        ),
        (
            "insert into position(pos_id, acct_num, val, from_z, thru_z, in_z, out_z) "
            "values (?, ?, ?, ?, ?, ?, ?)",
            (
                1,
                "A",
                100.00,
                _instant("2024-01-01T00:00:00+00:00"),
                _instant("2024-03-01T00:00:00+00:00"),
                _instant("2024-02-15T00:00:00+00:00"),
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
                _instant("2024-03-01T00:00:00+00:00"),
                _instant("2024-09-01T00:00:00+00:00"),
                _instant("2024-02-15T00:00:00+00:00"),
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
                _instant("2024-09-01T00:00:00+00:00"),
                OPEN_BOUND,
                _instant("2024-02-15T00:00:00+00:00"),
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
    observation = _observed(
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
    assert statements[2][1][3:5] == (_instant("2024-09-01T00:00:00+00:00"), OPEN_BOUND)


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
                _instant("2024-03-01T00:00:00+00:00"),
                _instant("2024-09-01T00:00:00+00:00"),
                _instant("2024-01-01T00:00:00+00:00"),
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
    observation = _observed(
        tx_start="2024-01-01T00:00:00+00:00",
        valid_start="2024-01-01T00:00:00+00:00",
        valid_end="infinity",
        payload=_R1_PAYLOAD,
    )
    statements = _lower(update, POSITION, "2024-07-01T00:00:00+00:00", observation=observation)
    assert statements == [
        (
            "update position set out_z = ? where pos_id = ? and thru_z = ? and out_z = ?",
            (_instant("2024-07-01T00:00:00+00:00"), 1, "infinity", "infinity"),
        ),
        (
            "insert into position(pos_id, acct_num, val, from_z, thru_z, in_z, out_z) "
            "values (?, ?, ?, ?, ?, ?, ?)",
            (
                1,
                "A",
                100.00,
                _instant("2024-01-01T00:00:00+00:00"),
                _instant("2024-06-01T00:00:00+00:00"),
                _instant("2024-07-01T00:00:00+00:00"),
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
                _instant("2024-06-01T00:00:00+00:00"),
                OPEN_BOUND,
                _instant("2024-07-01T00:00:00+00:00"),
                "infinity",
            ),
        ),
    ]


def test_bitemporal_plain_terminate_chains_head_only() -> None:
    # m-bitemp-write-007.
    terminate = KeyedWrite(
        "terminate", "Position", ({"id": 1},), valid_from="2024-06-01T00:00:00+00:00"
    )
    observation = _observed(
        tx_start="2024-01-01T00:00:00+00:00",
        valid_start="2024-01-01T00:00:00+00:00",
        valid_end="infinity",
        payload=_R1_PAYLOAD,
    )
    statements = _lower(terminate, POSITION, "2024-07-01T00:00:00+00:00", observation=observation)
    assert statements == [
        (
            "update position set out_z = ? where pos_id = ? and thru_z = ? and out_z = ?",
            (_instant("2024-07-01T00:00:00+00:00"), 1, "infinity", "infinity"),
        ),
        (
            "insert into position(pos_id, acct_num, val, from_z, thru_z, in_z, out_z) "
            "values (?, ?, ?, ?, ?, ?, ?)",
            (
                1,
                "A",
                100.00,
                _instant("2024-01-01T00:00:00+00:00"),
                _instant("2024-06-01T00:00:00+00:00"),
                _instant("2024-07-01T00:00:00+00:00"),
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
                _instant("2024-01-01T00:00:00+00:00"),
                "infinity",
                _instant("2024-01-01T00:00:00+00:00"),
                "infinity",
            ),
        )
    ]


@pytest.mark.parametrize(
    ("concurrency", "gate_sql", "gate_binds"),
    [
        ("locking", "", ()),
        ("optimistic", " and in_z = ?", (_instant("2023-11-01T00:00:00+00:00"),)),
    ],
    ids=["locking", "optimistic"],
)
def test_bitemporal_close_addresses_a_finite_observed_valid_end(
    concurrency: Concurrency, gate_sql: str, gate_binds: tuple[object, ...]
) -> None:
    # The observed rectangle is bounded on BOTH Valid-Time sides, which is the
    # shape the Valid-Time component of the address exists for: `out_z = infinity`
    # holds for every disjoint rectangle a key has current at one Transaction
    # Time, so only the rectangle's OWN exclusive Valid-Time end picks out the one
    # this close means to close. The bound value is that end — never the
    # rectangle's start, and never `infinity` — in BOTH modes; concurrency decides
    # only whether the `in_z` gate follows it.
    observed = _observed(
        tx_start="2023-11-01T00:00:00+00:00",
        valid_start="2024-01-01T00:00:00+00:00",
        valid_end="2024-07-01T00:00:00+00:00",
        payload=_R1_PAYLOAD,
    )
    update = KeyedWrite(
        "update", "Position", ({"id": 1, "value": 200.00},), valid_from="2024-04-01T00:00:00+00:00"
    )
    close, head, tail = _lower(
        update,
        POSITION,
        "2024-02-15T00:00:00+00:00",
        observation=observed,
        concurrency=concurrency,
    )
    assert close == (
        f"update position set out_z = ? where pos_id = ? and thru_z = ? and out_z = ?{gate_sql}",
        (
            _instant("2024-02-15T00:00:00+00:00"),
            1,
            _instant("2024-07-01T00:00:00+00:00"),
            "infinity",
            *gate_binds,
        ),
    )
    addressed_valid_end = close[1][2]
    assert addressed_valid_end == cast("dt.datetime", observed.predecessor.member("validEnd"))
    assert addressed_valid_end != cast("dt.datetime", observed.predecessor.member("validStart"))
    # The successors reconstruct exactly the addressed rectangle's window,
    # `[validStart, validEnd)`, split at the correction's `validFrom`.
    assert head[1][3:5] == (
        cast("dt.datetime", observed.predecessor.member("validStart")),
        _instant("2024-04-01T00:00:00+00:00"),
    )
    assert tail[1][3:5] == (_instant("2024-04-01T00:00:00+00:00"), addressed_valid_end)


# The two rectangles one key holds current at one Transaction Time, as the
# driver hands each back: real `datetime` values on both axes, `INFINITY_INSTANT`
# for an open bound. They share nothing a close addresses or gates on — distinct
# Valid-Time windows and distinct `in_z` — so every bind below names exactly one
# of them.
_CURRENT_RECTANGLE: Row = {
    "id": 1,
    "acct_num": "A",
    "value": Decimal("100.00"),
    "from_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
    "thru_z": INFINITY_INSTANT,
    "in_z": dt.datetime(2024, 2, 1, tzinfo=dt.UTC),
    "out_z": INFINITY_INSTANT,
}

_RETROACTIVE_RECTANGLE: Row = {
    "id": 1,
    "acct_num": "A",
    "value": Decimal("50.00"),
    "from_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
    "thru_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
    "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
    "out_z": INFINITY_INSTANT,
}


@pytest.mark.parametrize(
    ("concurrency", "gate_sql", "gate_binds"),
    [
        ("locking", "", ()),
        ("optimistic", " and in_z = ?", (dt.datetime(2024, 2, 1, tzinfo=dt.UTC),)),
    ],
    ids=["locking", "optimistic"],
)
def test_a_close_addresses_the_rectangle_the_written_value_came_from(
    concurrency: Concurrency, gate_sql: str, gate_binds: tuple[dt.datetime, ...]
) -> None:
    # One key holding TWO rectangles current at one Transaction Time — what a
    # retroactive correction leaves behind — read twice in one transaction: once
    # latest, then once at a Valid-Time instant inside the earlier rectangle, then
    # updated from the value the FIRST read handed back. The close must address
    # the rectangle THAT value came from: `thru_z` binds its own exclusive
    # Valid-Time end, head and tail reconstruct its own window split at the
    # correction, and the optimistic gate binds its own `in_z`. The distinction is
    # which read a write settles against — an as-of read is evidence about the
    # milestone IT observed, never about whichever milestone the same primary key
    # happened to be read at last, so reading one row at a second coordinate
    # leaves the first read's evidence intact. Driven through the developer verbs
    # rather than a hand-supplied observation because the misresolution is in how
    # the observation is resolved, which a lowering-only probe cannot see.
    port = ScriptedPort(
        Transact(
            Read(rows=[_CURRENT_RECTANGLE]), Read(rows=[_RETROACTIVE_RECTANGLE]), Write(times=3)
        )
    )

    def fn(tx: Transaction) -> None:
        current = tx.find(
            WherePosition.where(WherePosition.id == 1).as_of(valid_time=LATEST)
        ).result()
        tx.find(
            WherePosition.where(WherePosition.id == 1).as_of(
                valid_time=dt.datetime(2024, 2, 15, tzinfo=dt.UTC)
            )
        ).result()
        tx.update(
            current.edit(value=Decimal("150.00")),
            valid_from=dt.datetime(2024, 8, 1, tzinfo=dt.UTC),
        )

    db_for(WHERE_POSITION_META, port).transact(fn, concurrency=concurrency)

    close, head, tail = (op for op in port.calls if isinstance(op, WriteCall))
    assert close == WriteCall(
        POSTGRES.to_driver_sql(
            "update where_position set out_z = ? "
            f"where id = ? and thru_z = ? and out_z = ?{gate_sql}"
        ),
        (dt.datetime(2024, 6, 1, tzinfo=dt.UTC), 1, INFINITY_INSTANT, "infinity", *gate_binds),
    )
    assert head.binds == (
        1,
        "A",
        Decimal("100.00"),
        dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
        dt.datetime(2024, 8, 1, tzinfo=dt.UTC),
        dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
        "infinity",
    )
    assert tail.binds == (
        1,
        "A",
        Decimal("150.00"),
        dt.datetime(2024, 8, 1, tzinfo=dt.UTC),
        INFINITY_INSTANT,
        dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
        "infinity",
    )


def _probe(
    concurrency: Concurrency,
    *,
    entity: str = "Position",
    meta: Metamodel = POSITION,
    observed_tx_start: str | None = "2024-04-01T00:00:00+00:00",
    observed_valid_end: str | None = "infinity",
) -> PlannedClose:
    """The m-opt-lock conflict lane's own standalone close-only probe.

    It is NOT a real bitemporal mutation — every real close-bearing verb chains
    at least a head — so the lane settles the close directly instead of
    authoring one.
    """
    return plan_temporal_close(
        {"id": 1},
        entity,
        formed(meta),
        concurrency,
        instant_at("2024-10-01T00:00:00+00:00"),
        None if observed_tx_start is None else _managed_instant(observed_tx_start),
        None if observed_valid_end is None else _managed_instant(observed_valid_end),
    )


def test_bitemporal_close_addresses_both_axis_ends_then_gates_on_in_z_last() -> None:
    # m-bitemp-write-004/008: the address is the key then one exclusive upper
    # bound per axis in canonical order (`thru_z` then `out_z`); the observed
    # `in_z` gate binds LAST.
    step = _probe("optimistic")
    statement = compile_write(step, formed(POSITION), POSTGRES)
    assert statement.sql == (
        "update position set out_z = ? where pos_id = ? and thru_z = ? and out_z = ? and in_z = ?"
    )
    assert statement.binds == (
        _instant("2024-10-01T00:00:00+00:00"),
        1,
        "infinity",
        "infinity",
        _instant("2024-04-01T00:00:00+00:00"),
    )
    assert step.affected_rows.expected == 1
    assert isinstance(step.concurrency, TemporalGate)


def test_a_probe_identity_naming_more_than_the_address_is_refused() -> None:
    # The probe's `identity` IS the address, unlike the pipeline's own close,
    # whose `identity` is the full durable row the surrounding mutation revises.
    # A close revises no represented value, so it binds the primary key and
    # nothing else: projecting the key and dropping the rest silently would let a
    # caller's mistranslation — a control key it meant as a gate, or a member it
    # meant the close to carry — reach the database as a well-formed statement
    # that answers a different question than the caller asked.
    with pytest.raises(WritePlanningError, match="addressed by its primary key alone"):
        plan_temporal_close(
            {"id": 1, "quantity": 5},
            "Position",
            formed(POSITION),
            "optimistic",
            instant_at("2024-10-01T00:00:00+00:00"),
            "2024-04-01T00:00:00+00:00",
            "infinity",
        )


def test_bitemporal_close_keeps_its_whole_address_under_locking() -> None:
    # m-bitemp-write-001/006/007's own locking-mode closes: the address is
    # unchanged — only the `in_z` gate disappears (ADR 0046).
    step = _probe("locking")
    statement = compile_write(step, formed(POSITION), POSTGRES)
    assert statement.sql == (
        "update position set out_z = ? where pos_id = ? and thru_z = ? and out_z = ?"
    )
    assert statement.binds == (
        _instant("2024-10-01T00:00:00+00:00"),
        1,
        "infinity",
        "infinity",
    )
    assert step.concurrency == UNGATED
    assert step.target.end_values == (INFINITY, INFINITY)


def test_a_probe_addressing_a_bounded_rectangle_binds_its_finite_valid_end() -> None:
    # m-bitemp-write-017/-018: the bounded arm of the same address. A finite
    # Valid-Time end is the only thing separating two current rectangles that
    # share `in_z` and `out_z`.
    step = _probe("locking", observed_valid_end="2024-06-01T00:00:00+00:00")
    assert step.target.end_values == (
        Finite(instant=dt.datetime(2024, 6, 1, tzinfo=dt.UTC)),
        INFINITY,
    )
    statement = compile_write(step, formed(POSITION), POSTGRES)
    assert statement.binds == (
        _instant("2024-10-01T00:00:00+00:00"),
        1,
        _instant("2024-06-01T00:00:00+00:00"),
        "infinity",
    )


def test_bitemporal_close_without_an_observed_valid_end_is_refused() -> None:
    # A Bitemporal address needs one exclusive upper bound per axis, so a caller
    # supplying none is a wiring defect — refused, never settled as a
    # Transaction-Time-only close that could match a sibling rectangle.
    with pytest.raises(WritePlanningError, match="no observed Valid-Time end supplied"):
        _probe("locking", observed_valid_end=None)


def test_temporal_close_requires_an_effective_table() -> None:
    balance = dataclasses.replace(BALANCE.entity("Balance"), table=None)
    malformed = Metamodel(entities=(balance,))
    model = formed(malformed)
    step = _probe("locking", entity="Balance", meta=malformed, observed_valid_end=None)
    with pytest.raises(SqlGenError, match="write target has no effective table"):
        compile_write(step, model, POSTGRES)


# --------------------------------------------------------------------------- #
# m-storage-layout: milestone cells follow tiers; gates map identities to slots.#
# --------------------------------------------------------------------------- #
def test_milestone_insert_cells_follow_semantic_tier_order_not_declaration_order() -> None:
    # SpotQuote declares `symbol` AFTER the root's two Transaction-Time bound
    # Attributes, yet canonical tier order writes every domain slot ahead of the
    # temporal bounds, so the chained milestone's cells are id, price, symbol,
    # then in_z / out_z.
    model, entity = _accepted("SpotQuote", QUOTE)
    view = storage_layout.view(model).entity(entity.identity)
    assert view is not None
    assert tuple(slot.column.name for slot in view.columns) == (
        "id",
        "price",
        "symbol",
        "in_z",
        "out_z",
    )
    insert = KeyedWrite("insert", "SpotQuote", ({"id": 1, "price": 50.00, "symbol": "ACME"},))
    assert _lower(insert, QUOTE, "2024-01-01T00:00:00+00:00") == [
        (
            "insert into spot_quote(id, price, symbol, in_z, out_z) values (?, ?, ?, ?, ?)",
            (1, 50.00, "ACME", _instant("2024-01-01T00:00:00+00:00"), "infinity"),
        )
    ]


# One materialized SpotQuote row as the read executor hands it to a collector:
# physical-column keyed, complete (instance-form projects every applicable
# Column), and carrying no node of its own. Interval values are driver-native —
# an aware `datetime` for a finite bound, the neutral open-bound sentinel for an
# open one — which is what the port returns and what the observation retains
# unchanged.
_SPOT_QUOTE_COLUMNS: Mapping[str, object] = {
    "id": 1,
    "price": 50.00,
    "symbol": "ACME",
    "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
    "out_z": OPEN_BOUND,
}

# The milestone that row stands on — its finite from-instant on every declared
# axis. An observation of it is filed under this, not under the primary key
# alone, so reading one back names the milestone it is evidence about.
_SPOT_QUOTE_EDGE: Final[Edge] = Edge(tx_time=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))


def _retained(
    model: AcceptedMetamodel,
    observations: ReadObservations,
    uow: UnitOfWork,
    entity: EntityIdentity,
) -> WriteObservation | None:
    """The evidence ``observations`` retained for the SpotQuote milestone.

    Read off the source hint the retention answered, and cross-checked against
    the unit of work's own index: the two are one object, because the index is a
    weak view of what the sources hold rather than a second copy.
    """
    hint = retain_evidence(model, observations, ledger=uow)[0]
    assert hint.observation is not None
    state = TemporalStateKey(ObjectKey(entity, (("id", 1),)), _SPOT_QUOTE_EDGE)
    assert hint.observation.key == state
    assert uow.retained_for(state) is hint.observation
    return hint.observation.evidence


def test_a_temporal_concrete_observes_its_own_declared_members_not_the_roots() -> None:
    # An observation's payload comes from the row-owning Entity's OWN Table Layout
    # selection, so a member declared on a concrete subtype — SpotQuote's `symbol` —
    # is observed like any inherited one. The audit-only update chain merges a
    # sparse `tx.update(copy)` row over exactly that payload, so an observation
    # narrowed to the declaring root's members would silently NULL `symbol` on the
    # next milestone instead of carrying it forward.
    model, entity = _accepted("SpotQuote", QUOTE)
    observations = ReadObservations()
    observations.observe_row(0, entity.identity, _SPOT_QUOTE_COLUMNS, None)

    def observe(uow: UnitOfWork) -> WriteObservation | None:
        return _retained(model, observations, uow, entity.identity)

    observation = run_unit_of_work(
        observe,
        settings=TransactionSettings(),
        clock=FixedClock(dt.datetime(2024, 6, 1, tzinfo=dt.UTC)),
        meta=model,
        flush_executor=_no_flush,
        planner=build_write_planner(model),
        subject_identity=TEST_SUBJECT_IDENTITY,
    )
    assert isinstance(observation, TemporalObservation)
    assert dict(observation.predecessor.members) == {
        "id": 1,
        "price": 50.00,
        "symbol": "ACME",
        "txStart": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "txEnd": OPEN_BOUND,
    }

    update = KeyedWrite("update", "SpotQuote", ({"id": 1, "price": 60.00},))
    _close, chain = _lower(update, QUOTE, "2024-06-01T00:00:00+00:00", observation=observation)
    assert chain == (
        "insert into spot_quote(id, price, symbol, in_z, out_z) values (?, ?, ?, ?, ?)",
        (1, 60.00, "ACME", _instant("2024-06-01T00:00:00+00:00"), "infinity"),
    )


def test_a_real_find_retains_the_rows_raw_structured_column_for_its_observation() -> None:
    # The fan-out drops the Structured Column from a row's member columns, so a
    # temporal observation would lose it exactly where a successor needs it. `find`
    # hands it to the collector beside those columns instead, and the Predecessor
    # Row retains it beside — never among — the members it was decoded from, so a
    # key no member declares is still there when the successor is patched
    # (`m-unit-work`).
    model, entity = _accepted("SpotQuote", QUOTE)
    stored = {"price": "50.00", "symbol": "ACME", "charterCode": "NB-118"}
    observations = ReadObservations()
    observations.observe_row(0, entity.identity, _SPOT_QUOTE_COLUMNS, stored)

    def observe(uow: UnitOfWork) -> WriteObservation | None:
        return _retained(model, observations, uow, entity.identity)

    observation = run_unit_of_work(
        observe,
        settings=TransactionSettings(),
        clock=FixedClock(dt.datetime(2024, 6, 1, tzinfo=dt.UTC)),
        meta=model,
        flush_executor=_no_flush,
        planner=build_write_planner(model),
        subject_identity=TEST_SUBJECT_IDENTITY,
    )
    assert isinstance(observation, TemporalObservation)
    assert observation.predecessor.document == stored
    assert "charterCode" not in observation.predecessor.members


def test_milestone_close_selects_operation_identities_not_the_physical_key() -> None:
    # The physical key spans the model key AND both axis ENDS, so a close's own
    # operation identities land on key slots — but they are still its own: the
    # close also gates on the discriminator and the observed start, neither of
    # which the key selects, and it maps each identity onto its slot rather than
    # reading the key.
    model, entity = _accepted("Bond", INSTRUMENT)
    view = storage_layout.view(model).entity(entity.identity)
    assert view is not None
    assert tuple(slot.column.name for slot in view.layout.physical_primary_key) == (
        "id",
        "thru_z",
        "out_z",
    )
    terminate = KeyedWrite(
        "terminate", "Bond", ({"id": 1},), valid_from="2024-06-01T00:00:00+00:00"
    )
    observation = _observed(
        tx_start="2024-01-01T00:00:00+00:00",
        valid_start="2024-01-01T00:00:00+00:00",
        valid_end="infinity",
        payload={"id": 1, "price": 100.00, "coupon": 5.00},
    )
    close = _lower(
        terminate,
        INSTRUMENT,
        "2024-07-01T00:00:00+00:00",
        observation=observation,
        concurrency="optimistic",
    )[0]
    assert close == (
        "update instrument set out_z = ? "
        "where id = ? and kind = ? and thru_z = ? and out_z = ? and in_z = ?",
        (
            _instant("2024-07-01T00:00:00+00:00"),
            1,
            "bond",
            "infinity",
            "infinity",
            _instant("2024-01-01T00:00:00+00:00"),
        ),
    )


# --------------------------------------------------------------------------- #
# Inheritance composition (m-inheritance x m-txtime-write / m-bitemp-write).    #
# --------------------------------------------------------------------------- #
def test_tph_txtime_terminate_carries_the_tag_guard() -> None:
    # m-inheritance-090: the tag guard rides the identity predicates, before
    # the current-row predicate.
    terminate = KeyedWrite("terminate", "MeterReading", ({"id": 1},))
    statements = _lower(
        terminate,
        READING,
        "2024-08-01T00:00:00+00:00",
        observation=_observed(tx_start="2024-01-01T00:00:00+00:00"),
    )
    assert statements == [
        (
            "update reading set out_z = ? where id = ? and kind = ? and out_z = ?",
            (_instant("2024-08-01T00:00:00+00:00"), 1, "meter", "infinity"),
        )
    ]


def test_tpcs_txtime_terminate_has_no_tag_guard() -> None:
    # m-inheritance-091: table-per-concrete-subtype routes to the concrete's
    # own table, no tag.
    terminate = KeyedWrite("terminate", "SpotQuote", ({"id": 1},))
    statements = _lower(
        terminate,
        QUOTE,
        "2024-08-01T00:00:00+00:00",
        observation=_observed(tx_start="2024-01-01T00:00:00+00:00"),
    )
    assert statements == [
        (
            "update spot_quote set out_z = ? where id = ? and out_z = ?",
            (_instant("2024-08-01T00:00:00+00:00"), 1, "infinity"),
        )
    ]


def test_tph_bitemporal_terminate_carries_the_tag_guard() -> None:
    # m-inheritance-094.
    terminate = KeyedWrite(
        "terminate", "Bond", ({"id": 1},), valid_from="2024-06-01T00:00:00+00:00"
    )
    observation = _observed(
        tx_start="2024-01-01T00:00:00+00:00",
        valid_start="2024-01-01T00:00:00+00:00",
        valid_end="infinity",
        payload={"id": 1, "price": 100.00, "coupon": 5.00},
    )
    statements = _lower(terminate, INSTRUMENT, "2024-07-01T00:00:00+00:00", observation=observation)
    assert statements[0] == (
        "update instrument set out_z = ? where id = ? and kind = ? and thru_z = ? and out_z = ?",
        (_instant("2024-07-01T00:00:00+00:00"), 1, "bond", "infinity", "infinity"),
    )
    assert statements[1][1][:3] == (1, "bond", 100.00)


def test_tpcs_bitemporal_terminate_has_no_tag_guard() -> None:
    # m-inheritance-095: routes to the concrete `deposit_rate` table.
    terminate = KeyedWrite(
        "terminate", "DepositRate", ({"id": 1},), valid_from="2024-06-01T00:00:00+00:00"
    )
    observation = _observed(
        tx_start="2024-01-01T00:00:00+00:00",
        valid_start="2024-01-01T00:00:00+00:00",
        valid_end="infinity",
        payload={"id": 1, "amount": 2.50, "grade": "A"},
    )
    statements = _lower(terminate, RATE, "2024-07-01T00:00:00+00:00", observation=observation)
    assert statements[0] == (
        "update deposit_rate set out_z = ? where id = ? and thru_z = ? and out_z = ?",
        (_instant("2024-07-01T00:00:00+00:00"), 1, "infinity", "infinity"),
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
    observation = _observed(
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
        "update instrument set out_z = ? where id = ? and kind = ? and thru_z = ? and out_z = ?",
        (_instant("2024-02-15T00:00:00+00:00"), 2, "stock", "infinity", "infinity"),
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
    observation = _observed(
        tx_start="2024-01-01T00:00:00+00:00",
        valid_start="2024-01-01T00:00:00+00:00",
        valid_end="infinity",
        payload={"id": 2, "amount": 6.75, "spread": 1.25},
    )
    statements = _lower(terminate_until, RATE, "2024-02-15T00:00:00+00:00", observation=observation)
    assert len(statements) == 3
    assert statements[0] == (
        "update loan_rate set out_z = ? where id = ? and thru_z = ? and out_z = ?",
        (_instant("2024-02-15T00:00:00+00:00"), 2, "infinity", "infinity"),
    )


def test_tph_txtime_optlock_composed_conflict_orders_tag_then_gate_last() -> None:
    # m-inheritance-105: tag guard rides identity predicates, in_z gate LAST.
    close_only = KeyedWrite("terminate", "MeterReading", ({"id": 1},))
    observation = _observed(tx_start="2024-01-01T00:00:00+00:00")
    statements = _lower_full(
        close_only,
        READING,
        "2024-09-01T00:00:00+00:00",
        observation=observation,
        concurrency="optimistic",
    )
    lowered = statements[0]
    assert lowered.sql == (
        "update reading set out_z = ? where id = ? and kind = ? and out_z = ? and in_z = ?"
    )
    assert lowered.binds == (
        dt.datetime(2024, 9, 1, tzinfo=dt.UTC),
        1,
        "meter",
        "infinity",
        dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
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
    observation = _observed(tx_start="2024-01-01T00:00:00+00:00")
    statements = _lower_full(update, SUPPLIER, "2024-06-01T00:00:00+00:00", observation=observation)
    close, chain = statements
    assert close.sql == "update supplier set out_z = ? where sup_id = ? and out_z = ?"
    assert chain.binds[-1] == JsonDocument(d2)


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
    observation = _observed(
        tx_start="2024-01-01T00:00:00+00:00",
        valid_start="2024-01-01T00:00:00+00:00",
        valid_end="infinity",
        payload={"name": "Central Branch", "address": d1},
    )
    statements = _lower_full(
        update_until, BRANCH, "2024-02-15T00:00:00+00:00", observation=observation
    )
    close, head, middle, tail = statements
    assert close.sql == ("update branch set out_z = ? where br_id = ? and thru_z = ? and out_z = ?")
    assert head.binds[-1] == JsonDocument(d1)
    assert middle.binds[-1] == JsonDocument(d2)
    assert tail.binds[-1] == JsonDocument(d1)


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
    with pytest.raises(ValueError, match="temporal target carries 2 rows"):
        _lower(batched, BALANCE, "2024-02-15T00:00:00+00:00")


# --------------------------------------------------------------------------- #
# The rectangle split's own successor origins and causes.                     #
# --------------------------------------------------------------------------- #
def _origins(steps: tuple[PlannedStep, ...]) -> list[object]:
    return [
        entry.origin for step in steps if isinstance(step, PlannedInsert) for entry in step.entries
    ]


_R1_OBSERVED = _observed(
    tx_start="2024-01-01T00:00:00+00:00",
    valid_start="2024-01-01T00:00:00+00:00",
    valid_end="infinity",
    payload=_R1_PAYLOAD,
)


@pytest.mark.parametrize(
    ("mutation", "until", "cause", "changed_positions"),
    [
        ("updateUntil", "2024-09-01T00:00:00+00:00", SUPERSEDED, (1,)),
        ("terminateUntil", "2024-09-01T00:00:00+00:00", TERMINATED, ()),
        ("update", None, SUPERSEDED, (1,)),
        ("terminate", None, TERMINATED, ()),
    ],
    ids=["updateUntil", "terminateUntil", "update", "terminate"],
)
def test_bitemporal_successor_origins_follow_the_split(
    mutation: KeyedMutation,
    until: str | None,
    cause: object,
    changed_positions: tuple[int, ...],
) -> None:
    # A head or tail carries the predecessor's represented state and is
    # therefore `CarriedFrom` it; only the range the correction covers is
    # `ChangedFrom`. A terminate records the absence on the CAUSE, so its
    # survivors stay carried and are never themselves marked terminated.
    row: dict[str, object] = (
        {"id": 1}
        if mutation.startswith("terminate")
        else {
            "id": 1,
            "value": 200.00,
        }
    )
    steps = _finalize(
        KeyedWrite(
            mutation,
            "Position",
            (row,),
            valid_from="2024-03-01T00:00:00+00:00",
            until=until,
        ),
        POSITION,
        "2024-02-15T00:00:00+00:00",
        observation=_R1_OBSERVED,
    )
    close = steps[0]
    assert isinstance(close, PlannedClose)
    assert close.cause == cause
    origins = _origins(steps)
    for position, origin in enumerate(origins):
        expected = (
            ChangedFrom(predecessor=_R1_OBSERVED.predecessor)
            if position in changed_positions
            else CarriedFrom(predecessor=_R1_OBSERVED.predecessor)
        )
        assert origin == expected


def test_bitemporal_insert_successor_begins_a_lineage() -> None:
    steps = _finalize(
        KeyedWrite(
            "insertUntil",
            "Position",
            ({"id": 1, "acctNum": "A", "value": 100.00},),
            valid_from="2024-03-01T00:00:00+00:00",
            until="2024-09-01T00:00:00+00:00",
        ),
        POSITION,
        "2024-01-01T00:00:00+00:00",
    )
    assert _origins(steps) == [NewLineage()]


def test_bitemporal_close_target_is_mode_independent() -> None:
    # Only the gate moves between modes; the addressed rectangle never does.
    targets = [
        _finalize(
            KeyedWrite(
                "terminate", "Position", ({"id": 1},), valid_from="2024-06-01T00:00:00+00:00"
            ),
            POSITION,
            "2024-07-01T00:00:00+00:00",
            observation=_R1_OBSERVED,
            concurrency=mode,
        )[0]
        for mode in ("locking", "optimistic")
    ]
    locking, optimistic = targets
    assert isinstance(locking, PlannedClose) and isinstance(optimistic, PlannedClose)
    assert locking.target == optimistic.target
    assert locking.concurrency == UNGATED
    gate = optimistic.concurrency
    assert isinstance(gate, TemporalGate)
    assert gate.start_attribute.name == "txStart"
    assert gate.observed_start == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


# --------------------------------------------------------------------------- #
# txtime_write.axis_attr_names: the declared-axis lookup, direct.              #
# --------------------------------------------------------------------------- #
def test_axis_attr_names_refuses_an_axis_the_entity_does_not_declare() -> None:
    # Balance is audit-only (Transaction-Time dimension only) — a caller asking this pure
    # lookup for its (undeclared) Valid-Time dimension is a defensive backstop the
    # render seam is responsible for never reaching with a well-formed
    # instruction (`txtime_write._axis`), not a normal-path outcome.
    model, entity = _accepted("Balance", BALANCE)
    with pytest.raises(txtime_write.TemporalPlanningError, match="declares no VALID_TIME"):
        txtime_write.axis_attr_names(model, entity, TemporalDimension.VALID_TIME)


@pytest.mark.parametrize(
    ("strategy", "facet"),
    [
        (txtime_write.MILESTONE_CHAIN, "Transaction-Time-Only"),
        (bitemp_write.RECTANGLE_SPLIT, "Bitemporal"),
    ],
    ids=["txtime", "bitemporal"],
)
def test_a_facet_refuses_a_verb_it_owns_no_topology_for(
    strategy: txtime_write.TransactionTimeChaining | bitemp_write.RectangleSplit, facet: str
) -> None:
    # A facet answers the topology of the milestone verbs it owns; anything else
    # is a caller wiring defect this pure seam refuses rather than describing as
    # the nearest verb it does recognize. Each facet's OWN `topology(mutation)`
    # is single-param — the entity-aware dispatch between the two facets is the
    # composition root's `TemporalStrategy` adapter, one layer up, not a fact
    # either facet itself carries.
    with pytest.raises(txtime_write.TemporalPlanningError, match=facet):
        strategy.topology("delete")
