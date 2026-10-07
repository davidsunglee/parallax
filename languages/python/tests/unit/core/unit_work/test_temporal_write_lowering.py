"""Temporal write finalization and lowering unit tests.

Pins the two halves a temporal mutation crosses — the finalized Planned Close and
Planned Insert successors it expands into, and the DML each of those steps lowers
to — for audit-only close-and-chain (`m-temporal-write`) and the full-bitemporal
rectangle split (`m-temporal-write`).

The statements stay byte-exact against the corpus goldens (``m-temporal-write-001
..006``, ``m-temporal-write-017..019/022..025``, ``m-inheritance-090/091/094..097
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

from parallax.conformance.scripted_clock import FixedClock
from parallax.core import (
    MAX,
    Attr,
    DomainModel,
    TxTemporal,
    attr,
    opt_lock,
    storage_layout,
    temporal_read,
)
from parallax.core.base import INFINITY as OPEN_BOUND
from parallax.core.db_port import JsonDocument, MappingRow
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.entity._model import model_of
from parallax.core.execution._planning import build_write_planner
from parallax.core.metamodel import EntityIdentity, EntityMetadata
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.sql_gen import LoweredStatement, SqlGenError
from parallax.core.sql_gen._write import compile_write_step
from parallax.core.temporal_read import Edge, TransactionTimeOnly
from parallax.core.unit_work import (
    Concurrency,
    KeyedMutation,
    KeyedWrite,
    TransactionSettings,
    UnitOfWork,
    WriteBatchTrigger,
    run_unit_of_work,
)
from parallax.core.write_plan import (
    SUPERSEDED,
    TERMINATED,
    ObjectKey,
    PlannedClose,
    PlannedInsert,
    PredecessorRow,
    TemporalObservation,
    WriteObservation,
    WritePlan,
    WritePlanningError,
)
from parallax.core.write_plan.keys import TemporalStateKey
from parallax.core.write_plan.plan import OwnedEndpoint
from parallax.core.write_plan.steps import (
    INFINITY,
    NEW_LINEAGE,
    OPTIMISTIC_CONFLICT,
    RETURNED_MAX_PLUS_ONE,
    STALE_WRITE,
    UNGATED,
    CarriedFrom,
    ChangedFrom,
    ExactCount,
    Finite,
    InsertEntry,
    NewLineage,
    PlannedRow,
    PlannedTemporalGuard,
    PlannedTemporalRemoval,
    PlannedTemporalRevision,
    TemporalGate,
)
from parallax.core.write_plan.steps import PlannedWrite as PlannedStep
from parallax.descriptor._records import Metamodel
from parallax.snapshot.handle import Transaction
from tests._support.clock_probes import instant_at
from tests._support.db_port import (
    Read,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
)
from tests._support.lowering_probes import lower_instruction, lower_instruction_steps
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit._corpus_model_support import corpus_records, formed
from tests.unit._judged_evidence_support import judged_evidence
from tests.unit._transact_support import (
    INFINITY_INSTANT,
    WHERE_POSITION_META,
    WherePosition,
    db_for,
)
from tests.unit.core.unit_work._ownership_support import OpenedRows


def _no_flush(
    _plan: WritePlan, *, trigger: WriteBatchTrigger, bind_deferred: object, completed: object
) -> None:
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
    all: the bounds join ``payload`` inside the one Predecessor MappingRow, which is
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
        instruction,
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
        instruction,
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
        instruction,
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
# Audit-only (m-temporal-write): insert / close-and-chain update / terminate.     #
# --------------------------------------------------------------------------- #
def test_audit_only_insert_opens_a_current_milestone() -> None:
    # m-temporal-write-001.
    insert = KeyedWrite(
        "insert", "Balance", ({"id": 1, "acctNum": "A", "value": Decimal("100.00")},)
    )
    statements = _lower(insert, BALANCE, "2024-01-01T00:00:00+00:00")
    assert statements == [
        (
            "insert into balance(bal_id, acct_num, val, in_z, out_z) values (?, ?, ?, ?, ?)",
            (1, "A", 100.00, _instant("2024-01-01T00:00:00+00:00"), OPEN_BOUND),
        )
    ]


def test_audit_only_update_closes_then_chains_the_authored_full_row() -> None:
    # m-temporal-write-002: an ungated (locking-mode) close, then a chain carrying
    # the instruction's OWN authored FULL row. The row names every member the
    # predecessor could have carried forward, so merging is an identity and the
    # chain is exactly the authored row.
    update = KeyedWrite(
        "update", "Balance", ({"id": 1, "acctNum": "A", "value": Decimal("150.00")},)
    )
    observation = _observed(
        tx_start="2024-01-01T00:00:00+00:00",
        payload={"id": 1, "acctNum": "A", "value": Decimal("100.00")},
    )
    statements = _lower(update, BALANCE, "2024-06-01T00:00:00+00:00", observation=observation)
    assert statements == [
        (
            "update balance set out_z = ? where bal_id = ? and out_z = ?",
            (_instant("2024-06-01T00:00:00+00:00"), 1, "infinity"),
        ),
        (
            "insert into balance(bal_id, acct_num, val, in_z, out_z) values (?, ?, ?, ?, ?)",
            (1, "A", 150.00, _instant("2024-06-01T00:00:00+00:00"), OPEN_BOUND),
        ),
    ]


def test_audit_only_terminate_closes_only() -> None:
    # m-temporal-write-003: terminate = close, chain nothing.
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
    # m-temporal-write-004: the chained row carries ALL corrected attributes.
    update = KeyedWrite(
        "update", "Balance", ({"id": 1, "acctNum": "B", "value": Decimal("250.00")},)
    )
    observation = _observed(
        tx_start="2024-01-01T00:00:00+00:00",
        payload={"id": 1, "acctNum": "A", "value": Decimal("100.00")},
    )
    statements = _lower(update, BALANCE, "2024-06-01T00:00:00+00:00", observation=observation)
    assert statements[1] == (
        "insert into balance(bal_id, acct_num, val, in_z, out_z) values (?, ?, ?, ?, ?)",
        (1, "B", 250.00, _instant("2024-06-01T00:00:00+00:00"), OPEN_BOUND),
    )


def test_audit_only_update_merges_a_sparse_row_onto_the_observed_payload() -> None:
    # A sparse public `tx.update(copy)` row contains the primary key plus its
    # effective change set. This shape is never authored by the conformance
    # engine, which always supplies
    # a full row) merges onto the observed payload, so the chained row still
    # carries `acctNum` even though the instruction's own row never named it.
    sparse_update = KeyedWrite("update", "Balance", ({"id": 1, "value": Decimal("150.00")},))
    observation = _observed(
        tx_start="2024-01-01T00:00:00+00:00",
        payload={"id": 1, "acctNum": "A", "value": Decimal("100.00")},
    )
    statements = _lower(
        sparse_update, BALANCE, "2024-06-01T00:00:00+00:00", observation=observation
    )
    assert statements[1] == (
        "insert into balance(bal_id, acct_num, val, in_z, out_z) values (?, ?, ?, ?, ?)",
        (1, "A", 150.00, _instant("2024-06-01T00:00:00+00:00"), OPEN_BOUND),
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
    sparse_update = KeyedWrite("update", "Balance", ({"id": 1, "value": Decimal("150.00")},))
    observation = _observed(
        tx_start="2024-01-01T00:00:00+00:00",
        payload={"id": 1, "acctNum": "A", "value": Decimal("100.00")},
    )
    close, opened = _finalize(
        sparse_update, BALANCE, "2024-06-01T00:00:00+00:00", observation=observation
    )
    assert isinstance(close, PlannedClose)
    assert close.cause == SUPERSEDED
    assert _member_values(opened) == {
        "id": 1,
        "acctNum": "A",
        "value": Decimal("150.00"),
        "txStart": dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
        "txEnd": OPEN_BOUND,
    }
    assert isinstance(opened, PlannedInsert)
    assert opened.entries[0].origin == ChangedFrom(predecessor=observation.predecessor)


def test_audit_only_update_carries_a_full_authored_row_over_every_observed_member() -> None:
    # The corpus-driven engine authors FULL rows for an audit-only write, so the
    # merge onto the predecessor is a strict identity even though the
    # predecessor carries every member: the authored row overrides each one it
    # names, and no exercised compile-lane emission can change.
    full_update = KeyedWrite(
        "update", "Balance", ({"id": 1, "acctNum": "A", "value": Decimal("150.00")},)
    )
    observation = _observed(
        tx_start="2024-01-01T00:00:00+00:00",
        payload={"id": 1, "acctNum": "STALE", "value": Decimal("999.00")},
    )
    _close, opened = _finalize(
        full_update, BALANCE, "2024-06-01T00:00:00+00:00", observation=observation
    )
    row = _member_values(opened)
    assert row["acctNum"] == "A"
    assert row["value"] == 150.00


def test_audit_only_insert_begins_a_lineage_and_closes_nothing() -> None:
    insert = KeyedWrite(
        "insert", "Balance", ({"id": 1, "acctNum": "A", "value": Decimal("100.00")},)
    )
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
    with pytest.raises(ValueError, match="do not support 'terminate'"):
        _finalize(terminate, _MODELS["account"], "2024-08-01T00:00:00+00:00")


def test_audit_only_close_is_ungated_under_locking_regardless_of_observation() -> None:
    # m-temporal-write-005: a locking-mode close never binds `in_z`, even when one
    # was observed.
    update = KeyedWrite(
        "update", "Balance", ({"id": 1, "acctNum": "A", "value": Decimal("175.00")},)
    )
    observation = _observed(tx_start="2024-06-01T00:00:00+00:00")
    step, close = _lower_steps(
        update, BALANCE, "2024-09-01T00:00:00+00:00", observation=observation, concurrency="locking"
    )[0]
    assert close.sql == "update balance set out_z = ? where bal_id = ? and out_z = ?"
    assert isinstance(step, PlannedClose)
    # ungated: a shortfall is the non-retriable stale write
    assert step.affected_rows == ExactCount(1, STALE_WRITE)


def test_audit_only_close_gates_on_observed_in_z_under_optimistic() -> None:
    # m-temporal-write-006: the gated close binds the observed in_z LAST.
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
    insert = KeyedWrite(
        "insert", "Balance", ({"id": 9, "acctNum": "D", "value": Decimal("100.00")},)
    )
    steps = _lower_steps(insert, BALANCE, "2024-06-01T00:00:00+00:00", concurrency="optimistic")
    assert len(steps) == 1
    assert isinstance(steps[0][0], PlannedInsert)


# --------------------------------------------------------------------------- #
# Full bitemporal (m-temporal-write): the rectangle split and its degenerates.   #
# --------------------------------------------------------------------------- #
_R1_PAYLOAD = {"id": 1, "acctNum": "A", "value": Decimal("100.00")}


def test_bitemporal_update_until_splits_head_middle_tail() -> None:
    # m-temporal-write-017.
    update_until = KeyedWrite(
        "updateUntil",
        "Position",
        ({"id": 1, "value": Decimal("200.00")},),
        valid_from=_instant("2024-03-01T00:00:00+00:00"),
        until=_instant("2024-09-01T00:00:00+00:00"),
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
                OPEN_BOUND,
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
                OPEN_BOUND,
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
                OPEN_BOUND,
            ),
        ),
    ]


def test_bitemporal_terminate_until_chains_head_and_tail_no_middle() -> None:
    # m-temporal-write-018.
    terminate_until = KeyedWrite(
        "terminateUntil",
        "Position",
        ({"id": 1},),
        valid_from=_instant("2024-03-01T00:00:00+00:00"),
        until=_instant("2024-09-01T00:00:00+00:00"),
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
    # m-temporal-write-019: no close, a single INSERT.
    insert_until = KeyedWrite(
        "insertUntil",
        "Position",
        ({"id": 1, "acctNum": "A", "value": Decimal("100.00")},),
        valid_from=_instant("2024-03-01T00:00:00+00:00"),
        until=_instant("2024-09-01T00:00:00+00:00"),
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
                OPEN_BOUND,
            ),
        )
    ]


def test_bitemporal_plain_update_splits_head_and_new_tail_only() -> None:
    # m-temporal-write-022: the two-way degenerate — no middle, no old tail.
    update = KeyedWrite(
        "update",
        "Position",
        ({"id": 1, "value": Decimal("200.00")},),
        valid_from=_instant("2024-06-01T00:00:00+00:00"),
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
                OPEN_BOUND,
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
                OPEN_BOUND,
            ),
        ),
    ]


def test_bitemporal_plain_terminate_chains_head_only() -> None:
    # m-temporal-write-023.
    terminate = KeyedWrite(
        "terminate", "Position", ({"id": 1},), valid_from=_instant("2024-06-01T00:00:00+00:00")
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
                OPEN_BOUND,
            ),
        ),
    ]


def test_bitemporal_plain_insert_opens_one_fully_current_rectangle() -> None:
    # m-temporal-write-025.
    insert = KeyedWrite(
        "insert",
        "Position",
        ({"id": 1, "acctNum": "A", "value": Decimal("100.00")},),
        valid_from=_instant("2024-01-01T00:00:00+00:00"),
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
                OPEN_BOUND,
                _instant("2024-01-01T00:00:00+00:00"),
                OPEN_BOUND,
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
    # only whether the `in_z` gate follows it. The correction ends where the
    # rectangle does, so it touches no coverage beyond the one it observed.
    observed = _observed(
        tx_start="2023-11-01T00:00:00+00:00",
        valid_start="2024-01-01T00:00:00+00:00",
        valid_end="2024-07-01T00:00:00+00:00",
        payload=_R1_PAYLOAD,
    )
    update = KeyedWrite(
        "updateUntil",
        "Position",
        ({"id": 1, "value": Decimal("200.00")},),
        valid_from=_instant("2024-04-01T00:00:00+00:00"),
        until=_instant("2024-07-01T00:00:00+00:00"),
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
# driver hands each back: real `datetime` values on both axes, the open-bound
# sentinel for an open one. They share nothing a close addresses or gates on — distinct
# Valid-Time windows and distinct `in_z` — so every bind below names exactly one
# of them.
_CURRENT_RECTANGLE: MappingRow = {
    "id": 1,
    "acct_num": "A",
    "value": Decimal("100.00"),
    "from_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
    "thru_z": INFINITY_INSTANT,
    "in_z": dt.datetime(2024, 2, 1, tzinfo=dt.UTC),
    "out_z": INFINITY_INSTANT,
}

_RETROACTIVE_RECTANGLE: MappingRow = {
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
    # at the correction's own instant, then once at a Valid-Time instant inside the
    # earlier rectangle, then updated from the value the FIRST read handed back.
    # The close must address the rectangle THAT value came from: `thru_z` binds its own exclusive
    # Valid-Time end, head and tail reconstruct its own window split at the
    # correction, and the optimistic gate binds its own `in_z`. The distinction is
    # which read a write settles against — an as-of read is evidence about the
    # milestone IT observed, never about whichever milestone the same primary key
    # happened to be read at last, so reading one row at a second coordinate
    # leaves the first read's evidence intact. Driven through the developer verbs
    # rather than a hand-supplied observation because the misresolution is in how
    # the observation is resolved, which a lowering-only probe cannot see.
    port = ScriptedAdapter(
        Transact(
            Read(rows=[_CURRENT_RECTANGLE]), Read(rows=[_RETROACTIVE_RECTANGLE]), Write(times=3)
        )
    )

    def fn(tx: Transaction) -> None:
        current = tx.find(
            WherePosition.where(WherePosition.id == 1).as_of(
                valid_time=dt.datetime(2024, 8, 1, tzinfo=dt.UTC)
            )
        ).result()
        tx.find(
            WherePosition.where(WherePosition.id == 1).as_of(
                valid_time=dt.datetime(2024, 2, 15, tzinfo=dt.UTC)
            )
        ).result()
        tx.update(current.edit(value=Decimal("150.00")))

    db_for(WHERE_POSITION_META, port).transact(fn, concurrency=concurrency)

    close, head, tail = (op for op in port.calls if isinstance(op, WriteCall))
    assert close == WriteCall(
        POSTGRES.to_driver_sql(
            "update where_position set out_z = ? "
            f"where id = ? and thru_z = ? and out_z = ?{gate_sql}"
        ),
        (dt.datetime(2024, 6, 1, tzinfo=dt.UTC), 1, "infinity", "infinity", *gate_binds),
    )
    assert head.binds == (
        1,
        "A",
        Decimal("100.00"),
        dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
        dt.datetime(2024, 8, 1, tzinfo=dt.UTC),
        dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
        INFINITY_INSTANT,
    )
    assert tail.binds == (
        1,
        "A",
        Decimal("150.00"),
        dt.datetime(2024, 8, 1, tzinfo=dt.UTC),
        INFINITY_INSTANT,
        dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
        INFINITY_INSTANT,
    )


def test_temporal_close_requires_an_effective_table() -> None:
    terminate = KeyedWrite("terminate", "Balance", ({"id": 1},))
    (close,) = _finalize(
        terminate,
        BALANCE,
        "2024-10-01T00:00:00+00:00",
        observation=_observed(tx_start="2024-02-01T00:00:00+00:00"),
    )
    balance = dataclasses.replace(BALANCE.entity("Balance"), table=None)
    with pytest.raises(SqlGenError, match="write target has no effective table"):
        compile_write_step(close, formed(Metamodel(entities=(balance,))), POSTGRES)


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
    insert = KeyedWrite(
        "insert", "SpotQuote", ({"id": 1, "price": Decimal("50.00"), "symbol": "ACME"},)
    )
    assert _lower(insert, QUOTE, "2024-01-01T00:00:00+00:00") == [
        (
            "insert into spot_quote(id, price, symbol, in_z, out_z) values (?, ?, ?, ?, ?)",
            (1, 50.00, "ACME", _instant("2024-01-01T00:00:00+00:00"), OPEN_BOUND),
        )
    ]


class AllocatedLedger(TxTemporal, table="ledger", namespace="lowering.allocated"):
    id: Attr[int] = attr(primary_key=MAX)
    amount: Attr[int]


def test_a_generated_key_milestone_insert_binds_managed_infinity_outside_typed_spans() -> None:
    # The `max` form renders one row through scalar binding rather than the
    # repeated row binder, so the open end crosses that path as a framework bind.
    model = model_of(DomainModel(AllocatedLedger))
    entity = model.entity(AllocatedLedger.identity)
    shape = temporal_read.view(model).shape(AllocatedLedger.identity)
    assert entity is not None
    assert isinstance(shape, TransactionTimeOnly)
    opened = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    members = {member.identity.name: member.identity for member in entity.declared_attributes}
    row = PlannedRow(
        attributes={
            members["id"]: RETURNED_MAX_PLUS_ONE,
            members["amount"]: 100,
            shape.transaction_time.start_attribute: opened,
            shape.transaction_time.end_attribute: OPEN_BOUND,
        }
    )
    step = PlannedInsert(
        entity=entity.identity, entries=(InsertEntry(row=row, origin=NEW_LINEAGE),)
    )

    statement = compile_write_step(step, model, POSTGRES)

    assert statement.sql == (
        "insert into ledger(id, amount, in_z, out_z) "
        "select coalesce(max(t0.id), ?) + ?, ?, ?, ? from ledger t0 returning id"
    )
    assert statement.binds == (0, 1, 100, opened, OPEN_BOUND)
    assert statement.binds[-1] is OPEN_BOUND
    assert statement.wire_binds() == (0, 1, 100, "2024-01-01T00:00:00.000000Z", "infinity")
    typed = {index for span in statement.typed_bind_spans for index in span.indexes()}
    assert typed == {2, 3}


# One materialized SpotQuote row, physical-column keyed and complete
# (instance-form projects every applicable Column). Interval values are driver-native —
# an aware `datetime` for a finite bound, the neutral open-bound sentinel for an
# open one — which is what the port returns and what the observation retains
# unchanged.
_SPOT_QUOTE_COLUMNS: Mapping[str, object] = {
    "id": 1,
    "price": Decimal("50.00"),
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
    uow: UnitOfWork,
    entity: EntityIdentity,
    document: object | None = None,
) -> WriteObservation | None:
    """The evidence a read of the SpotQuote row retained for its milestone.

    Read off the read origin the retention answered, and cross-checked against a
    reread of the same milestone: the two are one object, because the unit of
    work answers a state it already holds evidence for with that evidence rather
    than a second copy.
    """
    hint = judged_evidence(model, entity, _SPOT_QUOTE_COLUMNS, document=document, ledger=uow)[0]
    assert hint.observation is not None
    state = TemporalStateKey(ObjectKey(entity, (("id", 1),)), _SPOT_QUOTE_EDGE)
    assert hint.observation.key == state
    reread = judged_evidence(model, entity, _SPOT_QUOTE_COLUMNS, document=document, ledger=uow)[0]
    assert reread.observation is hint.observation
    return hint.observation.evidence


def test_a_temporal_concrete_observes_its_own_declared_members_not_the_roots() -> None:
    # An observation's payload comes from the row-owning Entity's OWN Table Layout
    # selection, so a member declared on a concrete subtype — SpotQuote's `symbol` —
    # is observed like any inherited one. The audit-only update chain merges a
    # sparse `tx.update(copy)` row over exactly that payload, so an observation
    # narrowed to the declaring root's members would silently NULL `symbol` on the
    # next milestone instead of carrying it forward.
    model, entity = _accepted("SpotQuote", QUOTE)

    def observe(uow: UnitOfWork) -> WriteObservation | None:
        return _retained(model, uow, entity.identity)

    observation = run_unit_of_work(
        observe,
        settings=TransactionSettings(),
        clock=FixedClock(dt.datetime(2024, 6, 1, tzinfo=dt.UTC)),
        meta=model,
        flush_executor=_no_flush,
        planner=build_write_planner(model),
        actor_identity=TEST_ACTOR_IDENTITY,
        evidence_policy_for=opt_lock.view(model).required_key,
    )
    assert isinstance(observation, TemporalObservation)
    assert dict(observation.predecessor.members) == {
        "id": 1,
        "price": Decimal("50.00"),
        "symbol": "ACME",
        "txStart": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "txEnd": OPEN_BOUND,
    }

    update = KeyedWrite("update", "SpotQuote", ({"id": 1, "price": Decimal("60.00")},))
    _close, chain = _lower(update, QUOTE, "2024-06-01T00:00:00+00:00", observation=observation)
    assert chain == (
        "insert into spot_quote(id, price, symbol, in_z, out_z) values (?, ?, ?, ?, ?)",
        (1, 60.00, "ACME", _instant("2024-06-01T00:00:00+00:00"), OPEN_BOUND),
    )


def test_a_real_find_retains_the_rows_raw_structured_column_for_its_observation() -> None:
    # The fan-out drops the Structured Column from a row's member columns, so a
    # temporal observation would lose it exactly where a successor needs it. `find`
    # hands it to the collector beside those columns instead, and the Predecessor
    # MappingRow retains it beside — never among — the members it was decoded from, so a
    # key no member declares is still there when the successor is patched
    # (`m-unit-work`).
    model, entity = _accepted("SpotQuote", QUOTE)
    stored = {"price": "50.00", "symbol": "ACME", "charterCode": "NB-118"}

    def observe(uow: UnitOfWork) -> WriteObservation | None:
        return _retained(model, uow, entity.identity, stored)

    observation = run_unit_of_work(
        observe,
        settings=TransactionSettings(),
        clock=FixedClock(dt.datetime(2024, 6, 1, tzinfo=dt.UTC)),
        meta=model,
        flush_executor=_no_flush,
        planner=build_write_planner(model),
        actor_identity=TEST_ACTOR_IDENTITY,
        evidence_policy_for=opt_lock.view(model).required_key,
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
        "terminate", "Bond", ({"id": 1},), valid_from=_instant("2024-06-01T00:00:00+00:00")
    )
    observation = _observed(
        tx_start="2024-01-01T00:00:00+00:00",
        valid_start="2024-01-01T00:00:00+00:00",
        valid_end="infinity",
        payload={"id": 1, "price": Decimal("100.00"), "coupon": Decimal("5.00")},
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
# Inheritance composition (m-inheritance x m-temporal-write).    #
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


# --------------------------------------------------------------------------- #
# Unchanged milestones (m-temporal-write): a guard on the observed address and      #
# start, assigning the start to itself, where the dialect's count proves it.   #
# --------------------------------------------------------------------------- #
_GUARDED_AT = "2024-01-01T00:00:00+00:00"


def test_a_transaction_time_update_its_row_already_holds_lowers_to_one_guard() -> None:
    update = KeyedWrite("update", "Balance", ({"id": 1, "value": Decimal("100.00")},))
    lowered = _lower_steps(
        update,
        BALANCE,
        "2024-08-01T00:00:00+00:00",
        observation=_observed(
            tx_start=_GUARDED_AT, payload={"id": 1, "acctNum": "A", "value": 100}
        ),
        concurrency="optimistic",
    )
    ((step, statement),) = lowered
    assert isinstance(step, PlannedTemporalGuard)
    assert (statement.sql, statement.binds) == (
        "update balance set in_z = in_z where bal_id = ? and out_z = ? and in_z = ?",
        (1, "infinity", _instant(_GUARDED_AT)),
    )


def test_a_bitemporal_guard_addresses_its_rectangle_by_both_ends() -> None:
    update = KeyedWrite(
        "updateUntil",
        "Position",
        ({"id": 1, "value": Decimal("100.00")},),
        _instant("2024-03-01T00:00:00+00:00"),
        _instant("2024-05-01T00:00:00+00:00"),
    )
    lowered = _lower(
        update,
        POSITION,
        "2024-08-01T00:00:00+00:00",
        observation=_observed(
            tx_start=_GUARDED_AT,
            valid_start="2024-01-01T00:00:00+00:00",
            valid_end="2024-06-01T00:00:00+00:00",
            payload=_R1_PAYLOAD,
        ),
        concurrency="optimistic",
    )
    assert lowered == [
        (
            "update position set in_z = in_z where pos_id = ? and thru_z = ? and out_z = ? "
            "and in_z = ?",
            (1, _instant("2024-06-01T00:00:00+00:00"), "infinity", _instant(_GUARDED_AT)),
        )
    ]


def test_a_table_per_hierarchy_guard_carries_the_tag_guard_after_the_key() -> None:
    update = KeyedWrite("update", "MeterReading", ({"id": 1, "celsius": Decimal("21.50")},))
    lowered = _lower(
        update,
        READING,
        "2024-08-01T00:00:00+00:00",
        observation=_observed(tx_start=_GUARDED_AT, payload={"id": 1, "celsius": Decimal("21.50")}),
        concurrency="optimistic",
    )
    assert lowered == [
        (
            "update reading set in_z = in_z where id = ? and kind = ? and out_z = ? and in_z = ?",
            (1, "meter", "infinity", _instant(_GUARDED_AT)),
        )
    ]


def test_a_dialect_whose_count_cannot_prove_a_guard_closes_and_chains_instead() -> None:
    update = KeyedWrite("update", "Balance", ({"id": 1, "value": Decimal("100.00")},))
    lowered = _lower_steps(
        update,
        BALANCE,
        "2024-08-01T00:00:00+00:00",
        observation=_observed(
            tx_start=_GUARDED_AT, payload={"id": 1, "acctNum": "A", "value": 100}
        ),
        dialect=dataclasses.replace(POSTGRES, counts_unchanged_rows=False),
        concurrency="optimistic",
    )
    assert [type(step) for step, _ in lowered] == [PlannedClose, PlannedInsert]


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
        "terminate", "Bond", ({"id": 1},), valid_from=_instant("2024-06-01T00:00:00+00:00")
    )
    observation = _observed(
        tx_start="2024-01-01T00:00:00+00:00",
        valid_start="2024-01-01T00:00:00+00:00",
        valid_end="infinity",
        payload={"id": 1, "price": Decimal("100.00"), "coupon": Decimal("5.00")},
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
        "terminate", "DepositRate", ({"id": 1},), valid_from=_instant("2024-06-01T00:00:00+00:00")
    )
    observation = _observed(
        tx_start="2024-01-01T00:00:00+00:00",
        valid_start="2024-01-01T00:00:00+00:00",
        valid_end="infinity",
        payload={"id": 1, "amount": Decimal("2.50"), "grade": "A"},
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
        valid_from=_instant("2024-03-01T00:00:00+00:00"),
        until=_instant("2024-09-01T00:00:00+00:00"),
    )
    observation = _observed(
        tx_start="2024-01-01T00:00:00+00:00",
        valid_start="2024-01-01T00:00:00+00:00",
        valid_end="infinity",
        payload={"id": 2, "price": Decimal("100.00"), "ticker": "ACME"},
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
        valid_from=_instant("2024-03-01T00:00:00+00:00"),
        until=_instant("2024-09-01T00:00:00+00:00"),
    )
    observation = _observed(
        tx_start="2024-01-01T00:00:00+00:00",
        valid_start="2024-01-01T00:00:00+00:00",
        valid_end="infinity",
        payload={"id": 2, "amount": Decimal("6.75"), "spread": Decimal("1.25")},
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
        valid_from=_instant("2024-03-01T00:00:00+00:00"),
        until=_instant("2024-09-01T00:00:00+00:00"),
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
# Zero-row close: the two distinct outcomes (m-opt-lock / m-temporal-write).      #
# --------------------------------------------------------------------------- #
def test_multi_row_temporal_write_is_refused() -> None:
    # A temporal keyed write lowers ONE row at a time: each row opens its own
    # milestone chain (`m-temporal-write`), so there is no
    # shared statement a collapse could render. `m-batch-write`'s eligibility
    # never collapses a temporal entity, so reaching here with two rows is a
    # caller wiring defect — refused, never lowered as if only the first row
    # existed.
    batched = KeyedWrite(
        "update",
        "Balance",
        ({"id": 1, "value": Decimal("100.00")}, {"id": 2, "value": Decimal("200.00")}),
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
            "value": Decimal("200.00"),
        }
    )
    steps = _finalize(
        KeyedWrite(
            mutation,
            "Position",
            (row,),
            valid_from=_instant("2024-03-01T00:00:00+00:00"),
            until=None if until is None else _instant(until),
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
            ({"id": 1, "acctNum": "A", "value": Decimal("100.00")},),
            valid_from=_instant("2024-03-01T00:00:00+00:00"),
            until=_instant("2024-09-01T00:00:00+00:00"),
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
                "terminate",
                "Position",
                ({"id": 1},),
                valid_from=_instant("2024-06-01T00:00:00+00:00"),
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
# Rows the attempt opened: revised or removed at their address, never closed.   #
# --------------------------------------------------------------------------- #
_T = "2024-07-01T00:00:00+00:00"
_BALANCE_ID = EntityIdentity("parallax.compatibility", "Balance")
_POSITION_ID = EntityIdentity("parallax.compatibility", "Position")


def _owning(entity: EntityIdentity, *ends: object) -> OpenedRows:
    return OpenedRows(
        frozenset(
            {
                OwnedEndpoint(
                    entity,
                    (1,),
                    tuple(INFINITY if end is None else Finite(instant=end) for end in ends),
                )
            }
        )
    )


def _own_balance() -> OpenedRows:
    return _owning(_BALANCE_ID, None)


def _own_position(valid_end: dt.datetime | None = None) -> OpenedRows:
    return _owning(_POSITION_ID, valid_end, None)


def _owned_lowering(
    instruction: KeyedWrite,
    meta: Metamodel,
    observation: WriteObservation,
    ownership: OpenedRows,
    *,
    concurrency: Concurrency = "locking",
) -> list[tuple[PlannedStep, tuple[str, tuple[object, ...]]]]:
    return [
        (step, (statement.sql, statement.binds))
        for step, statement in lower_instruction_steps(
            instruction,
            formed(meta),
            POSTGRES,
            concurrency,
            instant_at(_T),
            observation=observation,
            ownership=ownership,
        )
    ]


def test_an_owned_transaction_time_row_is_revised_in_place_at_its_address() -> None:
    update = KeyedWrite("update", "Balance", ({"id": 1, "value": Decimal("175.00")},))
    observation = _observed(tx_start=_T, payload={"id": 1, "acctNum": "A", "value": 150})
    lowered = _owned_lowering(update, BALANCE, observation, _own_balance())
    assert [type(step) for step, _ in lowered] == [PlannedTemporalRevision]
    assert [statement for _, statement in lowered] == [
        ("update balance set val = ? where bal_id = ? and out_z = ?", (175.00, 1, "infinity"))
    ]


def test_an_owned_revision_gates_on_its_observed_start_under_optimistic() -> None:
    update = KeyedWrite("update", "Balance", ({"id": 1, "value": Decimal("175.00")},))
    observation = _observed(tx_start=_T, payload={"id": 1, "acctNum": "A", "value": 150})
    lowered = _owned_lowering(
        update, BALANCE, observation, _own_balance(), concurrency="optimistic"
    )
    (step, statement) = lowered[0]
    assert isinstance(step, PlannedTemporalRevision)
    assert step.affected_rows == ExactCount(expected=1, on_shortfall=OPTIMISTIC_CONFLICT)
    assert statement == (
        "update balance set val = ? where bal_id = ? and out_z = ? and in_z = ?",
        (175.00, 1, "infinity", _instant(_T)),
    )


def test_terminating_an_owned_transaction_time_row_removes_it() -> None:
    terminate = KeyedWrite("terminate", "Balance", ({"id": 1},))
    lowered = _owned_lowering(terminate, BALANCE, _observed(tx_start=_T), _own_balance())
    assert [type(step) for step, _ in lowered] == [PlannedTemporalRemoval]
    assert [statement for _, statement in lowered] == [
        ("delete from balance where bal_id = ? and out_z = ?", (1, "infinity"))
    ]


def test_a_row_whose_start_equals_the_instant_is_closed_unless_the_attempt_opened_it() -> None:
    # A row an earlier attempt committed at the same instant — a repeating clock —
    # carries `in_z = T` too; only the attempt's own record makes a row owned.
    update = KeyedWrite("update", "Balance", ({"id": 1, "value": Decimal("175.00")},))
    observation = _observed(tx_start=_T, payload={"id": 1, "acctNum": "A", "value": 150})
    assert [type(step) for step in _finalize(update, BALANCE, _T, observation=observation)] == [
        PlannedClose,
        PlannedInsert,
    ]


def _owned_position(valid_start: str, valid_end: str = "infinity") -> TemporalObservation:
    return _observed(tx_start=_T, valid_start=valid_start, valid_end=valid_end, payload=_R1_PAYLOAD)


def _position_row(value: float, start: str, end: str | None) -> tuple[object, ...]:
    return (
        1,
        "A",
        value,
        _instant(start),
        OPEN_BOUND if end is None else _instant(end),
        _instant(_T),
        OPEN_BOUND,
    )


_POSITION_INSERT = (
    "insert into position(pos_id, acct_num, val, from_z, thru_z, in_z, out_z) "
    "values (?, ?, ?, ?, ?, ?, ?)"
)
_JAN = "2024-01-01T00:00:00+00:00"
_MAR = "2024-03-01T00:00:00+00:00"
_JUN = "2024-06-01T00:00:00+00:00"
_DEC = "2024-12-01T00:00:00+00:00"


def test_an_owned_suffix_update_revises_the_retained_end_and_inserts_the_head() -> None:
    update = KeyedWrite(
        "update", "Position", ({"id": 1, "value": Decimal("200.00")},), valid_from=_instant(_MAR)
    )
    lowered = _owned_lowering(update, POSITION, _owned_position(_JAN), _own_position())
    assert [type(step) for step, _ in lowered] == [PlannedTemporalRevision, PlannedInsert]
    assert [statement for _, statement in lowered] == [
        (
            "update position set val = ?, from_z = ? where pos_id = ? and thru_z = ? and out_z = ?",
            (200.00, _instant(_MAR), 1, "infinity", "infinity"),
        ),
        (_POSITION_INSERT, _position_row(100.00, _JAN, _MAR)),
    ]


def test_an_owned_whole_rectangle_value_change_is_one_revision() -> None:
    # The head would cover no Valid Time, so it is not opened at all.
    update = KeyedWrite(
        "update", "Position", ({"id": 1, "value": Decimal("200.00")},), valid_from=_instant(_JAN)
    )
    lowered = _owned_lowering(update, POSITION, _owned_position(_JAN), _own_position())
    assert [statement for _, statement in lowered] == [
        (
            "update position set val = ? where pos_id = ? and thru_z = ? and out_z = ?",
            (200.00, 1, "infinity", "infinity"),
        )
    ]


def test_an_owned_interior_correction_moves_the_tail_start_and_inserts_head_and_middle() -> None:
    update_until = KeyedWrite(
        "updateUntil",
        "Position",
        ({"id": 1, "value": Decimal("200.00")},),
        valid_from=_instant(_MAR),
        until=_instant(_JUN),
    )
    lowered = _owned_lowering(
        update_until, POSITION, _owned_position(_JAN, _DEC), _own_position(_instant(_DEC))
    )
    assert [type(step) for step, _ in lowered] == [
        PlannedTemporalRevision,
        PlannedInsert,
        PlannedInsert,
    ]
    assert [statement for _, statement in lowered] == [
        (
            "update position set from_z = ? where pos_id = ? and thru_z = ? and out_z = ?",
            (_instant(_JUN), 1, _instant(_DEC), "infinity"),
        ),
        (_POSITION_INSERT, _position_row(100.00, _JAN, _MAR)),
        (_POSITION_INSERT, _position_row(200.00, _MAR, _JUN)),
    ]


def test_an_owned_bounded_termination_keeps_the_tail_and_inserts_the_head() -> None:
    terminate_until = KeyedWrite(
        "terminateUntil",
        "Position",
        ({"id": 1},),
        valid_from=_instant(_MAR),
        until=_instant(_JUN),
    )
    lowered = _owned_lowering(terminate_until, POSITION, _owned_position(_JAN), _own_position())
    assert [statement for _, statement in lowered] == [
        (
            "update position set from_z = ? where pos_id = ? and thru_z = ? and out_z = ?",
            (_instant(_JUN), 1, "infinity", "infinity"),
        ),
        (_POSITION_INSERT, _position_row(100.00, _JAN, _MAR)),
    ]


def test_an_owned_unbounded_termination_removes_the_row_and_inserts_its_head() -> None:
    # No successor keeps the row's own Valid-Time end, so nothing is moved to
    # make one: the row is removed and its head opened at its own address.
    terminate = KeyedWrite("terminate", "Position", ({"id": 1},), valid_from=_instant(_MAR))
    lowered = _owned_lowering(terminate, POSITION, _owned_position(_JAN), _own_position())
    assert [type(step) for step, _ in lowered] == [PlannedTemporalRemoval, PlannedInsert]
    assert [statement for _, statement in lowered] == [
        (
            "delete from position where pos_id = ? and thru_z = ? and out_z = ?",
            (1, "infinity", "infinity"),
        ),
        (_POSITION_INSERT, _position_row(100.00, _JAN, _MAR)),
    ]


def test_terminating_a_whole_owned_rectangle_removes_it_and_opens_nothing() -> None:
    terminate = KeyedWrite("terminate", "Position", ({"id": 1},), valid_from=_instant(_JAN))
    lowered = _owned_lowering(terminate, POSITION, _owned_position(_JAN), _own_position())
    assert [statement for _, statement in lowered] == [
        (
            "delete from position where pos_id = ? and thru_z = ? and out_z = ?",
            (1, "infinity", "infinity"),
        )
    ]


def test_terminating_an_owned_rectangle_at_its_own_end_changes_nothing() -> None:
    # The terminated window starts where the rectangle already ends, so its one
    # successor is the whole rectangle at its own address with nothing moved:
    # there is nothing to revise, remove, or open.
    terminate = KeyedWrite("terminate", "Position", ({"id": 1},), valid_from=_instant(_DEC))
    lowered = _owned_lowering(
        terminate, POSITION, _owned_position(_JAN, _DEC), _own_position(_instant(_DEC))
    )
    assert lowered == []


def test_a_pre_attempt_rectangle_is_closed_and_opens_only_nonempty_successors() -> None:
    update = KeyedWrite(
        "update", "Position", ({"id": 1, "value": Decimal("200.00")},), valid_from=_instant(_JAN)
    )
    observation = _observed(
        tx_start=_JAN, valid_start=_JAN, valid_end="infinity", payload=_R1_PAYLOAD
    )
    statements = _lower(update, POSITION, _T, observation=observation)
    assert statements == [
        (
            "update position set out_z = ? where pos_id = ? and thru_z = ? and out_z = ?",
            (_instant(_T), 1, "infinity", "infinity"),
        ),
        (_POSITION_INSERT, _position_row(200.00, _JAN, None)),
    ]
