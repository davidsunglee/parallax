"""Compact private storage of materialized write planning (m-unit-work, Docker-free).

Covers a Materialized Write Group's versioned evidence and the state keys its
temporal evidence answers, then Planned Steps' segmented backing — stable view
equality with no object-identity promise, and no mutable flyweight reused across
iterations — and structural sharing carried all the way through temporal
expansion and lowering. Bounded wrapper allocation is a separate invariant from
storage shape and correctness.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Mapping, Sequence, Sized
from decimal import Decimal
from types import FunctionType, MappingProxyType, MethodType
from typing import Any, cast

import pytest

# The module itself, not a name from it: the call-count regression below
# monkeypatches `resolved_assignments` where group settlement looks it up.
import parallax.core.temporal_write.expansion as expansion
from parallax.conformance import models
from parallax.conformance.scripted_clock import FixedClock
from parallax.core import Entity, inheritance, opt_lock, temporal_read
from parallax.core import predicate as predicate_algebra
from parallax.core._formation_profile import BUILTIN_MANIFEST
from parallax.core.base import INFINITY
from parallax.core.db_port import JsonDocument
from parallax.core.dialect import POSTGRES
from parallax.core.entity._construction_input import ABSENT
from parallax.core.execution._planning import build_write_planner
from parallax.core.metamodel import AttributeMetadata, FacetKey, Metamodel
from parallax.core.model_formation import ModelCompilerRequirement
from parallax.core.sql_gen._write import compile_write_step
from parallax.core.temporal_read import TimeInterval
from parallax.core.temporal_write.expansion import PredecessorExpander
from parallax.core.unit_work import (
    MaterializedWriteGroup,
    PredicateSelection,
    PredicateWrite,
    SystemClock,
    TransactionInstant,
    VersionArithmetic,
    VersionedEvidence,
    VersionedEvidenceBuilder,
    WriteAssignment,
    WritePlanner,
    WritePlanningRequest,
)
from parallax.core.unit_work.instructions import (
    PreparedPredicateWrite,
    PreparedTargetWrite,
    TargetWrite,
    prepare_typed_write,
    prepare_wire_write,
)
from parallax.core.unit_work.materialized import GroupStates, target_write
from parallax.core.unit_work.ranges import AuditDecoration, DeferredTemporalRange
from parallax.core.unit_work.strategy import (
    AuditStrategy,
    BatchingStrategy,
    ConcurrencyStrategy,
)
from parallax.core.unit_work.write_planner import compose_writes
from parallax.core.unit_work.write_settlement import (
    WritePlanCompiler,  # producer-reach regression only
)
from parallax.core.write_plan import (
    ChunkedColumnBuilder,
    EntityStateRow,
    PlannedClose,
    PlannedInsert,
    PredecessorRows,
    WritePlan,
    whole,
)
from parallax.core.write_plan.columns import (
    ColumnSlice,
)
from parallax.core.write_plan.keys import TemporalStateKey
from parallax.core.write_plan.steps import ChangedFrom, PlannedUpdate
from tests._support.clock_probes import CountingClock, inert_instant
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit._gc_reachability import reachable_objects
from tests.unit._temporal_group_support import temporal_group
from tests.unit.core import _milestone_rows_support as milestone_rows
from tests.unit.core.unit_work._ownership_support import OpenedRows

_MODELS = models.load_models()
_ACCOUNT = _MODELS["account"]
_BALANCE = _MODELS["balance"]
_BRANCH = _MODELS["branch"]
_POSITION = _MODELS["position"]
_OPENED = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_JAN, _MAR = (dt.datetime(2026, month, 1, tzinfo=dt.UTC) for month in (1, 3))


# --------------------------------------------------------------------------- #
# Group evidence: the states a group selected, and its versioned columns.      #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("entity", milestone_rows.LAYOUT_ENTITIES, ids=milestone_rows.LAYOUT_IDS)
def test_a_groups_state_keys_read_no_axis_end(
    monkeypatch: pytest.MonkeyPatch, entity: type[Entity]
) -> None:
    def refuse(*_arguments: object) -> object:
        raise AssertionError("a state key read an axis end")

    evidence, shape = milestone_rows.milestones(entity, (_JAN, _MAR), (_MAR, INFINITY))
    monkeypatch.setattr(PredecessorRows, "axis_end", refuse)

    keys = list(GroupStates(entity.identity, "id", evidence, shape))

    assert [cast("TemporalStateKey", key).milestone.valid_time for key in keys] == [_JAN, _MAR]


def test_versioned_evidence_aligns_one_version_with_each_key() -> None:
    builder = VersionedEvidenceBuilder(key_position=0, version_position=2)
    builder.append((1, "A", 3))
    builder.append((2, "B", 5))
    evidence = builder.seal()
    assert evidence is not None
    assert (list(evidence.keys), list(evidence.versions), len(evidence)) == ([1, 2], [3, 5], 2)

    versions: ChunkedColumnBuilder[int] = ChunkedColumnBuilder()
    versions.append(3)
    with pytest.raises(ValueError, match="one version with each key"):
        VersionedEvidence(keys=evidence.keys, versions=whole(versions.build()))
    with pytest.raises(ValueError, match="at least one row"):
        VersionedEvidence(
            keys=whole(ChunkedColumnBuilder[object]().build()),
            versions=whole(ChunkedColumnBuilder[int]().build()),
        )


def test_a_versioned_evidence_builder_that_appended_nothing_seals_to_nothing() -> None:
    assert VersionedEvidenceBuilder(key_position=0, version_position=1).seal() is None


def _prepared(instruction: PredicateWrite, model: object) -> PreparedPredicateWrite:
    prepared = prepare_typed_write(instruction, cast("Any", model))
    assert isinstance(prepared, PreparedPredicateWrite)
    return prepared


# --------------------------------------------------------------------------- #
# Planned Steps: a Materialized Write Group settles into a lazily            #
# materialized segment — stable, structurally-equal, non-flyweight views.     #
# --------------------------------------------------------------------------- #
def _version_group(
    entity: str, key_name: str, rows: Sequence[tuple[object, int]], assigned: float
) -> MaterializedWriteGroup:
    del key_name
    builder = VersionedEvidenceBuilder(key_position=0, version_position=1)
    for key_value, version in rows:
        builder.append((key_value, version))
    evidence = builder.seal()
    assert evidence is not None
    predicate = _prepared(
        PredicateWrite(
            "update",
            PredicateSelection(
                entity,
                predicate_algebra.Comparison("lessThan", f"{entity}.balance", "1000000.00"),
            ),
            assignments=(WriteAssignment(f"{entity}.balance", Decimal(str(assigned))),),
        ),
        _ACCOUNT,
    )
    return MaterializedWriteGroup(mutation=predicate, evidence=evidence)


def test_a_materialized_groups_steps_are_equal_but_not_identity_stable_on_repeat_access() -> None:
    group = _version_group("Account", "id", [(1, 1), (2, 1), (3, 1)], assigned=0.00)
    plan = build_write_planner(_ACCOUNT).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="optimistic",
            buffered_writes=[group],
        )
    )
    assert len(plan.steps) == 3
    first_access = plan.steps[0]
    second_access = plan.steps[0]
    assert isinstance(first_access, PlannedUpdate)
    assert isinstance(second_access, PlannedUpdate)
    assert first_access == second_access
    assert first_access is not second_access  # materialize-on-demand, never a retained flyweight
    # Iteration never reuses one mutable object across positions either.
    seen = list(plan.steps)
    assert len(seen) == len(set(id(step) for step in seen))
    updates: list[PlannedUpdate] = []
    for step in seen:
        assert isinstance(step, PlannedUpdate)
        updates.append(step)
    assert [update.target for update in updates] == [
        first_access.target,
        updates[1].target,
        updates[2].target,
    ]


def _temporal_group(
    entity: str, key_name: str, rows: Sequence[tuple[object, Mapping[str, object]]]
) -> MaterializedWriteGroup:
    return temporal_group(
        PredicateWrite(
            "terminate",
            PredicateSelection(
                entity,
                predicate_algebra.Comparison("lessThan", f"{entity}.value", "1000000.00"),
            ),
        ),
        _BALANCE,
        [members for _key, members in rows],
        key_name=key_name,
    )


def test_a_temporal_materialized_groups_close_and_chain_are_equal_but_not_identity_stable() -> None:
    rows = [
        (
            row_id,
            {
                "id": row_id,
                "acctNum": "A",
                "value": 1.00 * row_id,
                "txStart": _OPENED,
                "txEnd": INFINITY,
            },
        )
        for row_id in (1, 2)
    ]
    group = _temporal_group("Balance", "id", rows)
    plan = build_write_planner(_BALANCE).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="optimistic",
            buffered_writes=[group],
        )
    )
    # A plain terminate over Balance (Transaction-Time-Only) closes with no
    # chained successor, so each row settles to exactly one Planned Close.
    assert len(plan.steps) == 2
    first_access = plan.steps[0]
    second_access = plan.steps[0]
    assert isinstance(first_access, PlannedClose)
    assert first_access == second_access
    assert first_access is not second_access
    assert isinstance(plan.steps[1], PlannedClose)
    # Both rows' shapes structurally match — no accidental cross-row state
    # bleeds from one lazily-materialized position into the next.
    assert type(first_access) is type(plan.steps[1])
    assert PlannedInsert not in (type(first_access), type(plan.steps[1]))


# --------------------------------------------------------------------------- #
# Finalizing: a Write Plan may retain what a producer produced for one        #
# settled write, never the producer; a temporal group's topology and instant  #
# are both resolved during `finalize()`, never on step access.                #
# --------------------------------------------------------------------------- #
_PRODUCER_CLASSES = (
    MaterializedWriteGroup,
    TransactionInstant,
    FixedClock,
    SystemClock,
    WritePlanner,
    WritePlanCompiler,
    PredecessorExpander,
    BatchingStrategy,
    ConcurrencyStrategy,
    AuditStrategy,
    type(_BALANCE),
)

_COMPILED_FACET_KEYS: tuple[FacetKey[object], ...] = tuple(
    entry.compiler.facet_key
    for entry in BUILTIN_MANIFEST.entries
    if isinstance(entry.compiler, ModelCompilerRequirement)
)
"""Every key an accepted built-in model installs a compiled facet under.

Each key carries its owner's own decision procedure for "is this value my
facet?", which recognizes a facet no shape distinguishes.
"""


def _is_producer(value: object) -> bool:
    return isinstance(value, _PRODUCER_CLASSES) or any(
        key.accepts(value) for key in _COMPILED_FACET_KEYS
    )


def _reachable_from_plan(plan: WritePlan) -> list[object]:
    """Everything a plan's segments and execution units reach, every deferred
    range's description included."""
    return [
        value for held in (*plan.steps.segments, *plan.units) for value in reachable_objects(held)
    ]


def test_every_facet_an_accepted_model_carries_counts_as_a_producer() -> None:
    # A plan may reach nothing `_is_producer` recognizes, so every facet an
    # accepted model carries, and the clock, must count as a producer, while
    # what either produced for one settled write must not.
    facets = [_BALANCE.facet(key) for key in _COMPILED_FACET_KEYS]
    assert len(facets) == len(_COMPILED_FACET_KEYS) > 1

    for facet in facets:
        assert _is_producer(facet)
    assert _is_producer(_BALANCE)
    entity = _BALANCE.entities[0]
    assert not _is_producer(inheritance.view(_BALANCE).entity(entity.identity))
    assert not _is_producer(VersionArithmetic(initial=1, increment=1))
    instant = inert_instant()
    assert _is_producer(instant.clock)
    assert not _is_producer(instant.value())


def test_a_materialized_plans_segments_retain_no_group_instant_or_planner() -> None:
    # A Write Plan retains no producer: no private group, Transaction Instant,
    # clock, planner, strategy, Metamodel, or facet is reachable from any segment.
    rows = [
        (
            row_id,
            {
                "id": row_id,
                "acctNum": "A",
                "value": 1.00 * row_id,
                "txStart": _OPENED,
                "txEnd": INFINITY,
            },
        )
        for row_id in (1, 2)
    ]
    plan = build_write_planner(_BALANCE).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="optimistic",
            buffered_writes=[_temporal_group("Balance", "id", rows)],
        )
    )
    walked = _reachable_from_plan(plan)
    assert not [value for value in walked if _is_producer(value)]
    # The resolved instant and the key columns' slices sit nested inside the
    # segment, so reaching them shows the walk descended.
    assert any(isinstance(value, dt.datetime) for value in walked)
    assert any(isinstance(value, ColumnSlice) for value in walked)


def test_a_deferred_range_retains_finalized_data_and_neither_producer_nor_ownership() -> None:
    # A deferred range is bound at execution, under the ownership the attempt
    # holds then and the audit the unit of work supplies; its plan entry keeps
    # the finalized meaning and the resolved instant, and nothing that could
    # decide again — no clock, strategy, planner, live ownership, actor, or a
    # bound method or closure reaching one.
    clock = CountingClock([dt.datetime(2024, 6, 1, tzinfo=dt.UTC)])
    ownership = OpenedRows(frozenset())
    prepared = prepare_wire_write(
        TargetWrite(
            "updateUntil",
            "Position",
            {"id": 1, "value": "9.00"},
            if_tx_start=_OPENED,
            valid_from=_JAN,
            until=_MAR,
        ),
        _POSITION,
    )
    assert isinstance(prepared, PreparedTargetWrite)
    plan = build_write_planner(_POSITION).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=TransactionInstant(clock),
            concurrency="optimistic",
            buffered_writes=compose_writes(
                _POSITION, [target_write(prepared, inheritance.view(_POSITION))]
            ),
            ownership=ownership,
        )
    )
    (unit,) = plan.units
    assert isinstance(unit.deferred, DeferredTemporalRange)
    walked = _reachable_from_plan(plan)
    assert not [value for value in walked if _is_producer(value)]
    assert not [value for value in walked if isinstance(value, OpenedRows | AuditDecoration)]
    assert all(value is not TEST_ACTOR_IDENTITY for value in walked)
    assert not [value for value in walked if isinstance(value, MethodType | FunctionType)]
    # The walk descended into the description: its resolved instant and the
    # requested window are both reached.
    assert dt.datetime(2024, 6, 1, tzinfo=dt.UTC) in walked
    assert any(isinstance(value, TimeInterval) for value in walked)
    assert clock.calls == 1


def _account_plan(group: MaterializedWriteGroup) -> WritePlan:
    return build_write_planner(_ACCOUNT).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="optimistic",
            buffered_writes=[group],
        )
    )


def _segment_fields(segment: object) -> dict[str, object]:
    return {
        field.name: getattr(segment, field.name)
        for field in dataclasses.fields(cast("Any", segment))
    }


def test_a_versioned_segment_settles_produced_values_and_reaches_no_producer() -> None:
    # A Write Plan may retain the version arithmetic the Concurrency Strategy
    # produced for this mutation, and never the strategy that produced it.
    plan = _account_plan(_version_group("Account", "id", [(1, 1), (2, 1)], assigned=9.00))
    walked = _reachable_from_plan(plan)
    assert not [value for value in walked if _is_producer(value)]
    assert any(isinstance(value, VersionArithmetic) for value in walked)
    assert any(isinstance(value, ColumnSlice) for value in walked)


def test_a_versioned_segment_keeps_the_groups_own_version_column_and_no_second_one() -> None:
    # The row-sized structure settling a versioned group must not build. A
    # segment holds no strategy, so advancing every row's version up front into
    # a second tuple used to be the only way to have the advanced values at step
    # access — one extra integer per resolved row, retained for the whole flush.
    # The arithmetic is now a settled fact, so the advance is an addition
    # performed when a row's step is asked for, and the group's OWN evidence
    # columns are the only fields of the segment the row count sizes.
    rows: list[tuple[object, int]] = [(row_id, row_id) for row_id in range(1, 6)]
    group = _version_group("Account", "id", rows, assigned=9.00)
    plan = _account_plan(group)
    (segment,) = plan.steps.segments
    assert len(segment) == len(rows)
    fields = _segment_fields(segment)
    sized = {
        name
        for name, value in fields.items()
        if isinstance(value, Sized) and len(value) == len(rows)
    }
    assert sized == {"keys", "versions"}
    assert isinstance(group.evidence, VersionedEvidence)
    assert fields["keys"] is group.evidence.keys
    assert fields["versions"] is group.evidence.versions
    # Advancing at step access answers what the second column used to hold.
    first = plan.steps[0]
    assert isinstance(first, PlannedUpdate)
    version = next(ident for ident in first.assignments.attributes if ident.name == "version")
    assert first.assignments.attributes[version] == 2


def test_a_materialized_temporal_groups_instant_resolves_during_plan_not_on_step_access() -> None:
    # Reaching a temporal Materialized Write Group is what makes the attempt
    # capture its instant (ADR 0010), and the capture happens while `finalize()`
    # runs rather than lazily on a later `steps[i]` access, so the group, the
    # concurrency mode, and the instant itself are never reachable from the
    # plan. Three rows would settle to three closes if the instant were
    # captured per row rather than once for the whole surviving group.
    clock = CountingClock([dt.datetime(2024, 6, 1, tzinfo=dt.UTC)])
    rows = [
        (
            row_id,
            {
                "id": row_id,
                "acctNum": "A",
                "value": 1.00 * row_id,
                "txStart": _OPENED,
                "txEnd": INFINITY,
            },
        )
        for row_id in (1, 2, 3)
    ]
    plan = build_write_planner(_BALANCE).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=TransactionInstant(clock),
            concurrency="optimistic",
            buffered_writes=[_temporal_group("Balance", "id", rows)],
        )
    )
    assert clock.calls == 1
    _ = plan.steps[0]
    _ = plan.steps[2]
    _ = plan.steps[1]
    _ = list(plan.steps)
    # No step access — repeated, out of order, or iterated — reads the clock.
    assert clock.calls == 1


def test_a_materialized_temporal_groups_expansion_resolves_during_plan_not_on_step_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The group's assignments resolve, and every row's disposition settles,
    # once while `finalize()` settles the segment — the semantic content of
    # temporal expansion (`m-unit-work` stage 7) — and never again on a later
    # `steps[i]` access, however many times or in what order that access
    # repeats: a Write Plan is frozen, and re-running a planning decision at
    # consumption is the same defect as re-capturing the instant there.
    calls: list[str] = []
    resolve = expansion.resolved_assignments  # pyright: ignore[reportPrivateImportUsage]
    settle = PredecessorExpander.settle_group

    def counting_resolve(*args: Any, **kwargs: Any) -> Any:
        calls.append("resolve")
        return resolve(*args, **kwargs)

    def counting_settle(*args: Any, **kwargs: Any) -> Any:
        calls.append("settle")
        return settle(*args, **kwargs)

    monkeypatch.setattr(expansion, "resolved_assignments", counting_resolve)
    monkeypatch.setattr(PredecessorExpander, "settle_group", counting_settle)
    rows = [
        {
            "id": row_id,
            "acctNum": "A",
            "value": Decimal("1.00"),
            "txStart": _OPENED,
            "txEnd": INFINITY,
        }
        for row_id in (1, 2, 3)
    ]
    plan = build_write_planner(_BALANCE).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="optimistic",
            buffered_writes=[temporal_group(_value_update("Balance", None), _BALANCE, rows)],
        )
    )
    assert calls == ["settle", "resolve"]
    _ = plan.steps[0]
    _ = plan.steps[0]
    _ = list(plan.steps)
    # No step access — first, repeated, or iterated — settles the group again.
    assert calls == ["settle", "resolve"]


def _refuse_producers(monkeypatch: pytest.MonkeyPatch, model: Metamodel) -> None:
    """Fail every model, facet, and declaration read a settled step could use
    to re-derive a family fact, from now on."""

    def consulted(*_args: object) -> object:
        raise AssertionError("packed step access consulted a producer")

    for facet, methods in (
        (inheritance.view(model), ("entity", "position")),
        (temporal_read.view(model), ("shape", "axis")),
        (opt_lock.view(model), ("key",)),
    ):
        for method in methods:
            monkeypatch.setattr(type(facet), method, consulted)
    monkeypatch.setattr(type(model), "facet", consulted)
    monkeypatch.setattr(type(model), "entity", consulted)
    entity_type = type(model.entities[0])
    monkeypatch.setattr(entity_type, "as_of_axis", consulted)
    monkeypatch.setattr(entity_type, "declared_as_of_axes", property(consulted))
    monkeypatch.setattr(AttributeMetadata, "primary_key", property(consulted))
    monkeypatch.setattr(AttributeMetadata, "optimistic_locking", property(consulted))


def _value_update(entity: str, valid_from: dt.datetime | None) -> PredicateWrite:
    return PredicateWrite(
        "update",
        PredicateSelection(
            entity, predicate_algebra.Comparison("lessThan", f"{entity}.value", "1000000.00")
        ),
        assignments=(WriteAssignment(f"{entity}.value", Decimal("9.00")),),
        valid_from=valid_from,
    )


@pytest.mark.parametrize(
    ("model", "entity", "axes", "valid_from"),
    [
        (_BALANCE, "Balance", {}, None),
        (
            _POSITION,
            "Position",
            {"validStart": dt.datetime(2024, 1, 1, tzinfo=dt.UTC), "validEnd": INFINITY},
            dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
        ),
    ],
    ids=["transaction-time", "bitemporal"],
)
def test_packed_temporal_steps_consult_no_producer_on_repeated_access(
    monkeypatch: pytest.MonkeyPatch,
    model: Metamodel,
    entity: str,
    axes: Mapping[str, object],
    valid_from: dt.datetime | None,
) -> None:
    # Every row of a packed group closes by the family's settled axes, binds
    # its successors' intervals from them, and resolves its members through the
    # retained view, so once `finalize()` returns no row's step — first,
    # repeated, out of order, or iterated — reads a facet, the model, or a
    # declaration again.
    rows = [
        {
            "id": row_id,
            "acctNum": "A",
            "value": Decimal("1.00"),
            **axes,
            "txStart": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
            "txEnd": INFINITY,
        }
        for row_id in (1, 2, 3)
    ]
    plan = build_write_planner(model).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="optimistic",
            buffered_writes=[temporal_group(_value_update(entity, valid_from), model, rows)],
        )
    )
    settled = list(plan.steps)
    assert len(settled) == len(rows) * (3 if valid_from is not None else 2)
    _refuse_producers(monkeypatch, model)
    assert [plan.steps[index] for index in reversed(range(len(settled)))] == settled[::-1]
    assert [plan.steps[index] for index in range(len(settled))] == settled
    assert list(plan.steps) == settled


def test_no_materialized_segments_mapping_field_is_a_plain_mutable_dict() -> None:
    # Any mapping stored on a Step Segment is retained across later `step()`
    # calls rather than copied afresh. It must therefore be read-only so every
    # subsequent access observes the same planned values.
    versioned_plan = build_write_planner(_ACCOUNT).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="optimistic",
            buffered_writes=[_version_group("Account", "id", [(1, 1)], assigned=9.0)],
        )
    )
    rows = [
        (
            1,
            {
                "id": 1,
                "acctNum": "A",
                "value": 1.00,
                "txStart": _OPENED,
                "txEnd": INFINITY,
            },
        )
    ]
    temporal_plan = build_write_planner(_BALANCE).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="optimistic",
            buffered_writes=[_temporal_group("Balance", "id", rows)],
        )
    )
    held = [
        held
        for plan in (versioned_plan, temporal_plan)
        for segment in plan.steps.segments
        for held in (segment, getattr(segment, "backing", None))
        if held is not None
    ]
    assert len(held) == 3  # the versioned segment, and the temporal one with its backing
    for holder in held:
        for field in dataclasses.fields(cast("Any", holder)):
            value = getattr(holder, field.name)
            if isinstance(value, Mapping):
                assert isinstance(value, MappingProxyType), (
                    f"{type(holder).__name__}.{field.name} is a plain mutable mapping"
                )


def test_mutating_a_materialized_groups_assignments_leaves_steps_unaffected() -> None:
    # A temporal group's settled backing retains the group's resolved authored
    # maps across every resolved row, so a caller reaching them through
    # `plan.steps.segments` must not be able to change what a subsequently
    # retrieved step carries — a Write Plan is immutable and its views are
    # stable.
    rows = [
        {
            "id": 1,
            "acctNum": "A",
            "value": 1.00,
            "txStart": _OPENED,
            "txEnd": INFINITY,
        }
    ]
    group = temporal_group(_value_update("Balance", None), _BALANCE, rows)
    plan = build_write_planner(_BALANCE).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="optimistic",
            buffered_writes=[group],
        )
    )
    before = plan.steps[1]
    assert isinstance(before, PlannedInsert)
    backing = cast("Any", plan.steps.segments[0]).backing
    (value_identity,) = backing.assigned_attributes
    with pytest.raises(TypeError):
        cast("dict[object, object]", backing.assigned_attributes)[value_identity] = object()
    after = plan.steps[1]
    assert after == before
    (entry,) = cast("PlannedInsert", after).entries
    assert entry.row.attributes[value_identity] == Decimal("9.00")


def test_a_materialized_plan_shares_an_assigned_document_and_the_retained_predecessor() -> None:
    # The changed successor holds the authored document the prepared write
    # already owns, and its origin views the retained positional row rather
    # than a copy of it; neither can be mutated through what the step exposes.
    assigned_address: dict[str, object] = {
        "street": "30 New Road",
        "city": "Tampere",
        "geo": {"country": "FI"},
        "phones": [{"type": "mobile", "number": "222"}],
    }
    rows = [
        {
            "id": 1,
            "name": "Central Branch",
            "validStart": _OPENED,
            "validEnd": INFINITY,
            "txStart": _OPENED,
            "txEnd": INFINITY,
            "address": {
                "street": "10 Old Road",
                "city": "Helsinki",
                "geo": {"country": "FI"},
                "phones": [{"type": "mobile", "number": "111"}],
            },
        }
    ]
    group = temporal_group(
        PredicateWrite(
            "update",
            PredicateSelection("Branch", predicate_algebra.Comparison("eq", "Branch.id", 1)),
            assignments=(WriteAssignment("Branch.address", assigned_address),),
            valid_from=dt.datetime(2024, 7, 1, tzinfo=dt.UTC),
        ),
        _BRANCH,
        rows,
    )
    assert isinstance(group.evidence, PredecessorRows)
    retained = group.evidence.rows[0]
    plan = build_write_planner(_BRANCH).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="optimistic",
            buffered_writes=[group],
        )
    )
    changed = cast("PlannedInsert", plan.steps[2])
    (entry,) = changed.entries
    assert isinstance(entry.origin, ChangedFrom)
    address_identity = next(iter(entry.row.value_objects))
    address = cast("Mapping[str, object]", entry.row.value_objects[address_identity])
    assert address is group.mutation.managed_assignments[0].value
    geo = cast("Mapping[str, object]", address["geo"])
    phones = cast("Sequence[Mapping[str, object]]", address["phones"])
    predecessor = entry.origin.predecessor
    predecessor_address = cast("Mapping[str, object]", predecessor.member("address"))
    assert predecessor.carries(address_identity, entry.row.value_objects[address_identity]) is False
    assert predecessor.members == EntityStateRow.over_declared_members(
        group.evidence.selection, retained, absent=ABSENT
    )

    cast("dict[str, object]", assigned_address["geo"])["country"] = "SE"
    cast("list[dict[str, object]]", assigned_address["phones"])[0]["number"] = "999"

    assert geo["country"] == "FI"
    assert phones[0]["number"] == "222"
    assert predecessor_address["city"] == "Helsinki"
    with pytest.raises(TypeError):
        cast("dict[str, object]", geo)["country"] = "SE"
    with pytest.raises(TypeError):
        cast("dict[str, object]", phones[0])["number"] = "999"
    with pytest.raises(TypeError):
        cast("list[Mapping[str, object]]", phones)[0] = {"type": "mobile", "number": "999"}
    with pytest.raises(TypeError):
        cast("dict[str, object]", predecessor_address)["city"] = "Espoo"

    assert plan.steps[2] == changed
    *_carried, statement = (compile_write_step(step, _BRANCH, POSTGRES) for step in plan.steps)
    assert statement.binds[-1] == JsonDocument(
        {
            "street": "30 New Road",
            "city": "Tampere",
            "geo": {"country": "FI"},
            "phones": [{"type": "mobile", "number": "222"}],
        }
    )


def test_a_materialized_groups_planned_writes_are_constructed_only_on_step_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `finalize()` settles a Materialized Write Group's group-wide facts once and
    # keeps the per-row data as compact columns; it must not construct one
    # `PlannedUpdate` per resolved row while doing so — that would reintroduce
    # exactly the "million output wrappers" the compact representation exists
    # to avoid. Construction happens only when a consumer indexes a step, and
    # exactly once per index actually accessed.
    constructed: list[object] = []
    original_init = PlannedUpdate.__init__

    def counting_init(self: PlannedUpdate, *args: object, **kwargs: object) -> None:
        constructed.append(self)
        original_init(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(PlannedUpdate, "__init__", counting_init)

    group = _version_group("Account", "id", [(row_id, 1) for row_id in range(500)], assigned=0.00)
    plan = build_write_planner(_ACCOUNT).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="optimistic",
            buffered_writes=[group],
        )
    )
    assert len(constructed) == 0  # `finalize()` alone constructs none
    assert len(plan.steps) == 500
    for step in plan.steps:
        assert isinstance(step, PlannedUpdate)
    assert len(constructed) == 500  # exactly one per step actually accessed


def test_repeated_planning_of_an_equal_materialized_group_yields_equal_plans() -> None:
    first_plan = build_write_planner(_ACCOUNT).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="optimistic",
            buffered_writes=[_version_group("Account", "id", [(1, 1), (2, 1)], assigned=5.00)],
        )
    )
    second_plan = build_write_planner(_ACCOUNT).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="optimistic",
            buffered_writes=[_version_group("Account", "id", [(1, 1), (2, 1)], assigned=5.00)],
        )
    )
    assert first_plan == second_plan
    assert first_plan.steps == second_plan.steps
