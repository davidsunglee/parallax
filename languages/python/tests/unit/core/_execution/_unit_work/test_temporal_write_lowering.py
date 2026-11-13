"""Temporal write finalization and lowering unit tests.

Pins what a corpus golden cannot see of a temporal mutation (`m-temporal-write`):
the mode-independent Milestone Target (the key plus one exclusive upper bound
per As-Of Axis) against the observed-``in_z`` gate the concurrency mode decides,
each successor's Row Origin, each close's Close Cause, the two zero-row-close
shortfall tags (:class:`~parallax.core.internal.unit_work.OptimisticConflict` for a gated
mismatch, :class:`~parallax.core.internal.unit_work.StaleWrite` for an ungated one), and
the geometries of rows the attempt opened that no case states. The statements a
corpus case states are that case's golden.

Most cases here hand the planner one instruction and one observation directly.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Mapping
from decimal import Decimal
from typing import Final, cast

import pytest

from parallax.conformance.scripted_clock import FixedClock
from parallax.core import MAX, Attr, ConflictError, DomainModel, TxTemporal, attr
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._transaction._lifetime import TxnAttemptLifetime
from parallax.core._execution._write_lowering import lowered
from parallax.core.internal import storage_layout, temporal_read
from parallax.core.internal.base import INFINITY as OPEN_BOUND
from parallax.core.internal.base import InternalError
from parallax.core.internal.concurrency import ConcurrencyPreference
from parallax.core.internal.dialect import POSTGRES, Dialect
from parallax.core.internal.entity._model import model_of
from parallax.core.internal.metamodel import CompiledEntity, EntityIdentity
from parallax.core.internal.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.internal.sql_gen import LoweredStatement
from parallax.core.internal.temporal_read import Edge, TransactionTimeOnly
from parallax.core.internal.unit_work import (
    TEMPORAL_CONFLICT,
    KeyedMutation,
    KeyedWriteInstruction,
    TransactionSettings,
    UnitOfWork,
)
from parallax.core.internal.write_payload import LayoutPayloadPreparer
from parallax.core.internal.write_plan import (
    SUPERSEDED,
    TERMINATED,
    ObjectKey,
    PlannedClose,
    PlannedInsert,
    PredecessorRow,
    StateObservation,
    TemporalObservation,
)
from parallax.core.internal.write_plan.keys import TemporalObjectStateKey
from parallax.core.internal.write_plan.plan import TemporalRowCoordinates
from parallax.core.internal.write_plan.planned_rows import WRITE_PLANNING_FAILED
from parallax.core.internal.write_plan.steps import (
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
    NewLineage,
    PlannedStep,
    PlannedTemporalRemoval,
    PlannedTemporalRevision,
    TemporalGate,
    WriteRow,
)
from parallax.descriptor._records import Metamodel
from tests._support.bindings import bound_model
from tests._support.clock_probes import instant_at
from tests._support.errors import raises_code
from tests._support.lowering_probes import lower_instruction, lower_instruction_steps
from tests._support.managed_rows import managed_row_of
from tests._support.planner_probes import NO_COUNTED_STEPS, NO_ROW_READS, TEST_ACTOR_IDENTITY
from tests.unit._corpus_model_support import corpus_records, formed
from tests.unit._judged_evidence_support import judged_evidence
from tests.unit.core._execution._unit_work._ownership_support import OpenedRows


def _no_flush(
    steps: tuple[PlannedStep, ...], /, *, allocates: bool, **capture: object
) -> tuple[object, ...]:
    """Step execution for a test that never flushes."""
    del allocates, capture
    raise AssertionError(f"no step executes, yet {len(steps)} step(s) were handed over")


def _accepted(name: str, meta: Metamodel) -> tuple[AcceptedMetamodel, CompiledEntity]:
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
QUOTE = _MODELS["quote"]


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
    instruction: KeyedWriteInstruction,
    meta: Metamodel,
    tx_instant: str,
    *,
    observation: StateObservation | None = None,
    dialect: Dialect = POSTGRES,
    concurrency: ConcurrencyPreference = "locking",
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
    instruction: KeyedWriteInstruction,
    meta: Metamodel,
    tx_instant: str,
    *,
    observation: StateObservation | None = None,
    dialect: Dialect = POSTGRES,
    concurrency: ConcurrencyPreference = "locking",
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
    instruction: KeyedWriteInstruction,
    meta: Metamodel,
    tx_instant: str,
    *,
    observation: StateObservation | None = None,
    concurrency: ConcurrencyPreference = "locking",
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
    instruction: KeyedWriteInstruction,
    meta: Metamodel,
    tx_instant: str,
    *,
    observation: StateObservation | None = None,
    dialect: Dialect = POSTGRES,
    concurrency: ConcurrencyPreference = "locking",
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
    sparse_update = KeyedWriteInstruction(
        "amend", "Balance", ({"id": 1, "value": Decimal("150.00")},)
    )
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
    # The authored row overrides each observed member it names, whatever the
    # predecessor held there.
    full_update = KeyedWriteInstruction(
        "amend", "Balance", ({"id": 1, "acctNum": "A", "value": Decimal("150.00")},)
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
    insert = KeyedWriteInstruction(
        "insert", "Balance", ({"id": 1, "acctNum": "A", "value": Decimal("100.00")},)
    )
    (opened,) = _finalize(insert, BALANCE, "2024-01-01T00:00:00+00:00")
    assert isinstance(opened, PlannedInsert)
    assert opened.entries[0].origin == NewLineage()


def test_audit_only_terminate_records_termination_and_chains_nothing() -> None:
    terminate = KeyedWriteInstruction("terminate", "Balance", ({"id": 1},))
    (close,) = _finalize(
        terminate,
        BALANCE,
        "2024-08-01T00:00:00+00:00",
        observation=_observed(tx_start="2024-01-01T00:00:00+00:00"),
    )
    assert isinstance(close, PlannedClose)
    assert close.cause == TERMINATED


def test_audit_only_close_is_ungated_under_locking_regardless_of_observation() -> None:
    # m-concurrency-022: a locking-mode close never binds `in_z`, even when one
    # was observed.
    update = KeyedWriteInstruction(
        "amend", "Balance", ({"id": 1, "acctNum": "A", "value": Decimal("175.00")},)
    )
    observation = _observed(tx_start="2024-06-01T00:00:00+00:00")
    step, close = _lower_steps(
        update, BALANCE, "2024-09-01T00:00:00+00:00", observation=observation, concurrency="locking"
    )[0]
    assert close.sql == "update px.balance set out_z = ? where bal_id = ? and out_z = ?"
    assert isinstance(step, PlannedClose)
    # ungated: a shortfall is the non-retriable stale write
    assert step.affected_rows == ExactCount(1, STALE_WRITE)


# --------------------------------------------------------------------------- #
# Full bitemporal (m-temporal-write): what a close addresses.                 #
# --------------------------------------------------------------------------- #
_R1_PAYLOAD = {"id": 1, "acctNum": "A", "value": Decimal("100.00")}


@pytest.mark.parametrize(
    ("concurrency", "gate_sql", "gate_binds"),
    [
        ("locking", "", ()),
        ("optimistic", " and in_z = ?", (_instant("2023-11-01T00:00:00+00:00"),)),
    ],
    ids=["locking", "optimistic"],
)
def test_bitemporal_close_addresses_a_finite_observed_valid_end(
    concurrency: ConcurrencyPreference, gate_sql: str, gate_binds: tuple[object, ...]
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
    update = KeyedWriteInstruction(
        "amendUntil",
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
        f"update px.position set out_z = ? where pos_id = ? and thru_z = ? and out_z = ?{gate_sql}",
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


def test_temporal_close_requires_an_effective_table() -> None:
    terminate = KeyedWriteInstruction("terminate", "Balance", ({"id": 1},))
    (close,) = _finalize(
        terminate,
        BALANCE,
        "2024-10-01T00:00:00+00:00",
        observation=_observed(tx_start="2024-02-01T00:00:00+00:00"),
    )
    (declared,) = BALANCE.entities
    balance = dataclasses.replace(declared, table=None)
    with raises_code(
        InternalError, WRITE_PLANNING_FAILED, match="write target has no effective table"
    ):
        lowered(
            close,
            LayoutPayloadPreparer(bound_model(formed(Metamodel(entities=(balance,))))),
            bound_model(formed(Metamodel(entities=(balance,)))),
            POSTGRES,
        )


# --------------------------------------------------------------------------- #
# m-storage-layout: milestone cells follow tiers; gates map identities to slots.#
# --------------------------------------------------------------------------- #
def test_milestone_insert_cells_follow_semantic_tier_order_not_declaration_order() -> None:
    # SpotQuote declares `symbol` AFTER the root's two Transaction-Time bound
    # Attributes, yet canonical tier order writes every domain slot ahead of the
    # temporal bounds, so the chained milestone's cells are id, price, symbol,
    # then in_z / out_z.
    model, entity = _accepted("SpotQuote", QUOTE)
    view = storage_layout.storage_layout_facet_of(model).entity(entity.identity)
    assert view is not None
    assert tuple(slot.column.name for slot in view.columns) == (
        "id",
        "price",
        "symbol",
        "in_z",
        "out_z",
    )
    insert = KeyedWriteInstruction(
        "insert", "SpotQuote", ({"id": 1, "price": Decimal("50.00"), "symbol": "ACME"},)
    )
    assert _lower(insert, QUOTE, "2024-01-01T00:00:00+00:00") == [
        (
            "insert into px.spot_quote(id, price, symbol, in_z, out_z) values (?, ?, ?, ?, ?)",
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
    shape = temporal_read.temporal_facet_of(model).shape(AllocatedLedger.identity)
    assert entity is not None
    assert isinstance(shape, TransactionTimeOnly)
    opened = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    members = {member.identity.name: member.identity for member in entity.declared_attributes}
    row = managed_row_of(
        model,
        {
            members["id"]: RETURNED_MAX_PLUS_ONE,
            members["amount"]: 100,
            shape.transaction_time.start_attribute: opened,
            shape.transaction_time.end_attribute: OPEN_BOUND,
        },
    )
    step = PlannedInsert(entity=entity.identity, entries=(WriteRow(row=row, origin=NEW_LINEAGE),))

    statement = lowered(
        step, LayoutPayloadPreparer(bound_model(model)), bound_model(model), POSTGRES
    )

    assert statement.sql == (
        "insert into px.ledger(id, amount, in_z, out_z) "
        "select coalesce(max(t0.id), ?) + ?, ?, ?, ? from px.ledger t0 returning id"
    )
    assert statement.binds == (0, 1, 100, opened, OPEN_BOUND)
    assert statement.binds[-1] is OPEN_BOUND
    assert statement.wire_binds() == (0, 1, 100, "2024-01-01T00:00:00.000000Z", "infinity")
    typed = {index for span in statement.typed_bind_spans for index in span.indices()}
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
) -> StateObservation | None:
    """The evidence a read of the SpotQuote row retained for its milestone.

    Read off the read evidence the retention answered, and cross-checked against a
    reread of the same milestone: the two are one object, because the unit of
    work answers a state it already holds evidence for with that evidence rather
    than a second copy.
    """
    hint = judged_evidence(
        model, entity, _SPOT_QUOTE_COLUMNS, document=document, evidence_context=uow.source_authority
    )[0]
    assert hint.observation is not None
    state = TemporalObjectStateKey(ObjectKey(entity, (("id", 1),)), _SPOT_QUOTE_EDGE)
    assert hint.observation.key == state
    reread = judged_evidence(
        model, entity, _SPOT_QUOTE_COLUMNS, document=document, evidence_context=uow.source_authority
    )[0]
    assert reread.observation is hint.observation
    return hint.observation.evidence


def test_a_temporal_concrete_observes_its_own_declared_members_not_the_roots() -> None:
    # An observation's payload comes from the row-owning Entity's OWN Table Layout
    # selection, so a member declared on a concrete subtype — SpotQuote's `symbol` —
    # is observed like any inherited one. The audit-only update chain merges a
    # sparse `tx.amend(copy)` row over exactly that payload, so an observation
    # narrowed to the declaring root's members would silently NULL `symbol` on the
    # next milestone instead of carrying it forward.
    model, entity = _accepted("SpotQuote", QUOTE)

    def observe(uow: UnitOfWork) -> StateObservation | None:
        return _retained(model, uow, entity.identity)

    observation = observe(
        UnitOfWork(
            lifetime=TxnAttemptLifetime(),
            settings=TransactionSettings(),
            clock=FixedClock(dt.datetime(2024, 6, 1, tzinfo=dt.UTC)),
            meta=model,
            execute_write_steps=_no_flush,
            execute_counted_step=NO_COUNTED_STEPS,
            acquire_rows=NO_ROW_READS,
            planner=build_write_planner(bound_model(model)),
            actor_identity=TEST_ACTOR_IDENTITY,
        )
    )
    assert isinstance(observation, TemporalObservation)
    assert dict(observation.predecessor.members) == {
        "id": 1,
        "price": Decimal("50.00"),
        "symbol": "ACME",
        "txStart": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "txEnd": OPEN_BOUND,
    }

    update = KeyedWriteInstruction("amend", "SpotQuote", ({"id": 1, "price": Decimal("60.00")},))
    _close, chain = _lower(update, QUOTE, "2024-06-01T00:00:00+00:00", observation=observation)
    assert chain == (
        "insert into px.spot_quote(id, price, symbol, in_z, out_z) values (?, ?, ?, ?, ?)",
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

    def observe(uow: UnitOfWork) -> StateObservation | None:
        return _retained(model, uow, entity.identity, stored)

    observation = observe(
        UnitOfWork(
            lifetime=TxnAttemptLifetime(),
            settings=TransactionSettings(),
            clock=FixedClock(dt.datetime(2024, 6, 1, tzinfo=dt.UTC)),
            meta=model,
            execute_write_steps=_no_flush,
            execute_counted_step=NO_COUNTED_STEPS,
            acquire_rows=NO_ROW_READS,
            planner=build_write_planner(bound_model(model)),
            actor_identity=TEST_ACTOR_IDENTITY,
        )
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
    view = storage_layout.storage_layout_facet_of(model).entity(entity.identity)
    assert view is not None
    assert tuple(slot.column.name for slot in view.layout.physical_primary_key) == (
        "id",
        "thru_z",
        "out_z",
    )
    terminate = KeyedWriteInstruction(
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
        "update px.instrument set out_z = ? "
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
# Unchanged milestones (m-temporal-write): a guard on the observed address and      #
# start, assigning the start to itself, where the dialect's count proves it.   #
# --------------------------------------------------------------------------- #
_GUARDED_AT = "2024-01-01T00:00:00+00:00"


def test_a_bitemporal_guard_addresses_its_rectangle_by_both_ends() -> None:
    update = KeyedWriteInstruction(
        "amendUntil",
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
            "update px.position set in_z = in_z where pos_id = ? and thru_z = ? and out_z = ? "
            "and in_z = ?",
            (1, _instant("2024-06-01T00:00:00+00:00"), "infinity", _instant(_GUARDED_AT)),
        )
    ]


def test_a_table_per_hierarchy_guard_carries_the_tag_guard_after_the_key() -> None:
    update = KeyedWriteInstruction(
        "amend", "MeterReading", ({"id": 1, "celsius": Decimal("21.50")},)
    )
    lowered = _lower(
        update,
        READING,
        "2024-08-01T00:00:00+00:00",
        observation=_observed(tx_start=_GUARDED_AT, payload={"id": 1, "celsius": Decimal("21.50")}),
        concurrency="optimistic",
    )
    assert lowered == [
        (
            "update px.reading set in_z = in_z where id = ? and kind = ? and out_z = ? and in_z "
            "= ?",
            (1, "meter", "infinity", _instant(_GUARDED_AT)),
        )
    ]


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
        ("amendUntil", "2024-09-01T00:00:00+00:00", SUPERSEDED, (1,)),
        ("terminateUntil", "2024-09-01T00:00:00+00:00", TERMINATED, ()),
        ("amend", None, SUPERSEDED, (1,)),
        ("terminate", None, TERMINATED, ()),
    ],
    ids=["amendUntil", "terminateUntil", "amend", "terminate"],
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
        KeyedWriteInstruction(
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
        KeyedWriteInstruction(
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
            KeyedWriteInstruction(
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
                TemporalRowCoordinates(
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
    instruction: KeyedWriteInstruction,
    meta: Metamodel,
    observation: StateObservation,
    ownership: OpenedRows,
    *,
    concurrency: ConcurrencyPreference = "locking",
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


def test_an_owned_revision_gates_on_its_observed_start_under_optimistic() -> None:
    update = KeyedWriteInstruction("amend", "Balance", ({"id": 1, "value": Decimal("175.00")},))
    observation = _observed(tx_start=_T, payload={"id": 1, "acctNum": "A", "value": 150})
    lowered = _owned_lowering(
        update, BALANCE, observation, _own_balance(), concurrency="optimistic"
    )
    (step, statement) = lowered[0]
    assert isinstance(step, PlannedTemporalRevision)
    assert step.affected_rows == ExactCount(expected=1, on_shortfall=OPTIMISTIC_CONFLICT)
    assert statement == (
        "update px.balance set val = ? where bal_id = ? and out_z = ? and in_z = ?",
        (175.00, 1, "infinity", _instant(_T)),
    )


@pytest.mark.parametrize("stored_start", [_T, "2024-08-01T00:00:00+00:00"])
def test_a_row_the_attempt_did_not_open_is_never_closed_at_or_before_its_start(
    stored_start: str,
) -> None:
    # A row an earlier attempt committed at the same instant — a repeating clock —
    # carries `in_z = T` too; only the attempt's own record makes a row owned, so
    # this one would be closed into an empty or inverted interval.
    update = KeyedWriteInstruction("amend", "Balance", ({"id": 1, "value": Decimal("175.00")},))
    observation = _observed(tx_start=stored_start, payload={"id": 1, "acctNum": "A", "value": 150})
    with raises_code(ConflictError, TEMPORAL_CONFLICT) as refused:
        _finalize(update, BALANCE, _T, observation=observation)
    assert (refused.value.entity, refused.value.key) == (_BALANCE_ID.canonical, {"id": 1})
    assert refused.value.is_transient
    assert f"Transaction Instant {_instant(_T).isoformat()} " in str(refused.value)
    assert f"stored start {_instant(stored_start).isoformat()}" in str(refused.value)


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
    "insert into px.position(pos_id, acct_num, val, from_z, thru_z, in_z, out_z) "
    "values (?, ?, ?, ?, ?, ?, ?)"
)
_JAN = "2024-01-01T00:00:00+00:00"
_MAR = "2024-03-01T00:00:00+00:00"
_JUN = "2024-06-01T00:00:00+00:00"
_DEC = "2024-12-01T00:00:00+00:00"


def test_an_owned_suffix_update_revises_the_retained_end_and_inserts_the_head() -> None:
    update = KeyedWriteInstruction(
        "amend", "Position", ({"id": 1, "value": Decimal("200.00")},), valid_from=_instant(_MAR)
    )
    lowered = _owned_lowering(update, POSITION, _owned_position(_JAN), _own_position())
    assert [type(step) for step, _ in lowered] == [PlannedTemporalRevision, PlannedInsert]
    assert [statement for _, statement in lowered] == [
        (
            "update px.position set val = ?, from_z = ? where pos_id = ? and thru_z = ? and "
            "out_z = ?",
            (200.00, _instant(_MAR), 1, "infinity", "infinity"),
        ),
        (_POSITION_INSERT, _position_row(100.00, _JAN, _MAR)),
    ]


def test_an_owned_interior_correction_moves_the_tail_start_and_inserts_head_and_middle() -> None:
    update_until = KeyedWriteInstruction(
        "amendUntil",
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
            "update px.position set from_z = ? where pos_id = ? and thru_z = ? and out_z = ?",
            (_instant(_JUN), 1, _instant(_DEC), "infinity"),
        ),
        (_POSITION_INSERT, _position_row(100.00, _JAN, _MAR)),
        (_POSITION_INSERT, _position_row(200.00, _MAR, _JUN)),
    ]


def test_an_owned_unbounded_termination_removes_the_row_and_inserts_its_head() -> None:
    # No successor keeps the row's own Valid-Time end, so nothing is moved to
    # make one: the row is removed and its head opened at its own address.
    terminate = KeyedWriteInstruction(
        "terminate", "Position", ({"id": 1},), valid_from=_instant(_MAR)
    )
    lowered = _owned_lowering(terminate, POSITION, _owned_position(_JAN), _own_position())
    assert [type(step) for step, _ in lowered] == [PlannedTemporalRemoval, PlannedInsert]
    assert [statement for _, statement in lowered] == [
        (
            "delete from px.position where pos_id = ? and thru_z = ? and out_z = ?",
            (1, "infinity", "infinity"),
        ),
        (_POSITION_INSERT, _position_row(100.00, _JAN, _MAR)),
    ]


def test_terminating_an_owned_rectangle_at_its_own_end_changes_nothing() -> None:
    # The terminated window starts where the rectangle already ends, so its one
    # successor is the whole rectangle at its own address with nothing moved:
    # there is nothing to revise, remove, or open.
    terminate = KeyedWriteInstruction(
        "terminate", "Position", ({"id": 1},), valid_from=_instant(_DEC)
    )
    lowered = _owned_lowering(
        terminate, POSITION, _owned_position(_JAN, _DEC), _own_position(_instant(_DEC))
    )
    assert lowered == []


def test_a_pre_attempt_rectangle_is_closed_and_opens_only_nonempty_successors() -> None:
    update = KeyedWriteInstruction(
        "amend", "Position", ({"id": 1, "value": Decimal("200.00")},), valid_from=_instant(_JAN)
    )
    observation = _observed(
        tx_start=_JAN, valid_start=_JAN, valid_end="infinity", payload=_R1_PAYLOAD
    )
    statements = _lower(update, POSITION, _T, observation=observation)
    assert statements == [
        (
            "update px.position set out_z = ? where pos_id = ? and thru_z = ? and out_z = ?",
            (_instant(_T), 1, "infinity", "infinity"),
        ),
        (_POSITION_INSERT, _position_row(200.00, _JAN, None)),
    ]
