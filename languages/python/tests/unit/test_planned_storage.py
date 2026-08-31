"""Compact private column storage for write planning (m-unit-work, Docker-free).

Covers the compact private storage constructs beneath the finalized Planned
Write algebra: bounded chunk construction and Column Slice sharing
(:mod:`parallax.core.unit_work.columns`), Predecessor Columns' aligned member
lengths, Materialized Write Group's own aligned key/observation columns,
Planned Steps' segmented backing —
stable view equality with no object-identity promise, and no mutable
flyweight reused across iterations — and structural sharing carried all the
way through temporal expansion and lowering. Bounded wrapper allocation is a
separate invariant from storage shape and correctness.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from collections.abc import Mapping, Sequence
from decimal import Decimal
from types import MappingProxyType
from typing import Any, cast

import pytest
from _transact_support import BALANCE as BALANCE_MODEL
from _transact_support import WHERE_POSITION_META, WherePosition, db_for

# The module itself, not a name from it: the call-count regression below
# monkeypatches `resolve_successors` where `_settle_temporal_group` looks it
# up, which is this module's own namespace rather than `unit_work.temporal`'s.
import parallax.core.unit_work.write_planner as write_planner
from _support import mirrored_models as mm
from _support.clock_probes import CountingClock, inert_instant
from _support.db_port import (
    Read,
    ScriptedPort,
    Transact,
    Write,
    WriteCall,
)
from _support.planner_probes import TEST_SUBJECT_IDENTITY
from parallax.conformance import models
from parallax.core import predicate as predicate_algebra
from parallax.core.base import INFINITY
from parallax.core.db_port import JsonDocument
from parallax.core.dialect import POSTGRES
from parallax.core.sql_gen._write import compile_write
from parallax.core.unit_work import (
    ChangedFrom,
    ChunkedColumn,
    ChunkedColumnBuilder,
    ColumnSlice,
    FixedClock,
    MaterializedWriteGroup,
    MilestoneTopology,
    PlannedClose,
    PlannedInsert,
    PlannedUpdate,
    PlanningRequest,
    PredecessorColumns,
    PredecessorShape,
    PredicateMutation,
    PredicateSelection,
    PreparedPredicateWrite,
    PredicateWrite,
    TemporalColumns,
    TransactionInstant,
    VersionColumns,
    WriteAssignment,
    WritePlanner,
    whole,
    prepare_typed_write,
)
from parallax.core.unit_work.columns import (
    _CHUNK_SIZE,  # pyright: ignore[reportPrivateUsage] - bounded-chunking regression only
)
from parallax.core.unit_work.planner import Targets  # forbidden-plan-context regression only
from parallax.snapshot.handle import Database, Transaction, build_write_planner

_MODELS = models.load_models()
_ACCOUNT = _MODELS["account"]
_BALANCE = _MODELS["balance"]
_BRANCH = _MODELS["branch"]


# --------------------------------------------------------------------------- #
# Chunked Column / Column Slice: bounded construction and structural sharing. #
# --------------------------------------------------------------------------- #
def test_a_chunked_column_seals_bounded_chunks_as_it_builds() -> None:
    builder: ChunkedColumnBuilder[int] = ChunkedColumnBuilder()
    count = _CHUNK_SIZE * 2 + 7
    for value in range(count):
        builder.append(value)
    column = builder.build()
    assert len(column) == count
    assert [len(chunk) for chunk in column.chunks] == [_CHUNK_SIZE, _CHUNK_SIZE, 7]
    assert column[0] == 0
    assert column[_CHUNK_SIZE] == _CHUNK_SIZE
    assert column[-1] == count - 1
    assert list(column) == list(range(count))


def test_a_chunked_column_refuses_a_declared_length_disagreeing_with_its_chunks() -> None:
    builder: ChunkedColumnBuilder[int] = ChunkedColumnBuilder()
    builder.append(1)
    column = builder.build()
    with pytest.raises(ValueError, match="declared length"):
        ChunkedColumn(chunks=column.chunks, length=2)


def test_a_chunked_column_refuses_an_out_of_range_index() -> None:
    builder: ChunkedColumnBuilder[int] = ChunkedColumnBuilder()
    builder.append(1)
    column = builder.build()
    with pytest.raises(IndexError):
        column[1]
    with pytest.raises(IndexError):
        column[-2]


def test_a_column_slice_shares_its_backing_column_without_copying() -> None:
    builder: ChunkedColumnBuilder[int] = ChunkedColumnBuilder()
    for value in range(10):
        builder.append(value)
    column = builder.build()
    left = ColumnSlice(column, 0, 5)
    right = ColumnSlice(column, 5, 10)
    assert list(left) == [0, 1, 2, 3, 4]
    assert list(right) == [5, 6, 7, 8, 9]
    assert left.column is right.column  # ONE backing column, two independent views
    # Two independently constructed slices over equal ranges of an equal
    # (not merely identical) column compare equal by structure.
    other = ColumnSlice(whole(builder.build()).column, 0, 5)
    assert left == other
    assert left is not other


def test_a_column_slice_refuses_an_invalid_range() -> None:
    column = whole(ChunkedColumnBuilder[int]().build())
    with pytest.raises(ValueError, match="Column Slice"):
        ColumnSlice(column.column, 1, 0)


def test_a_column_slice_refuses_an_out_of_range_index() -> None:
    builder: ChunkedColumnBuilder[int] = ChunkedColumnBuilder()
    builder.append(1)
    builder.append(2)
    sliced = ColumnSlice(builder.build(), 0, 1)
    with pytest.raises(IndexError):
        sliced[1]
    with pytest.raises(IndexError):
        sliced[-2]


# --------------------------------------------------------------------------- #
# Predecessor Columns: aligned member lengths, on-demand row materialization. #
# --------------------------------------------------------------------------- #
def _predecessor_columns(
    rows: Sequence[Mapping[str, object]],
    *,
    value_objects: tuple[str, ...] = (),
    documents: Sequence[object] = (),
) -> PredecessorColumns:
    attribute_names = tuple(name for name in rows[0] if name not in value_objects)
    builders = {name: ChunkedColumnBuilder[object]() for name in rows[0]}
    for row in rows:
        for name in builders:
            builders[name].append(row[name])
    document_builder: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
    for document in documents:
        document_builder.append(document)
    return PredecessorColumns(
        shape=PredecessorShape(attributes=attribute_names, value_objects=value_objects),
        attribute_columns=tuple(whole(builders[name].build()) for name in attribute_names),
        value_object_columns=tuple(whole(builders[name].build()) for name in value_objects),
        documents=whole(document_builder.build()) if documents else None,
    )


def test_predecessor_columns_retain_the_raw_document_against_later_mutation() -> None:
    # The raw Structured Column is retained beside the decoded members rather than
    # among them, and it is snapshotted for the same reason they are: a row's
    # Predecessor Row is built on demand, once per access, and must answer with the
    # state the read observed however long the caller holds it. A row view answers
    # with a document of its OWN — a portable JSON value, which is what a
    # structured-document bind can carry — so neither a later edit of the mapping
    # the column was built from nor an edit of one view's answer reaches another.
    stored: dict[str, object] = {"title": "Ada", "manifest": {"cargo": "timber"}}
    predecessors = _predecessor_columns([{"id": 1}], documents=[stored])
    retained = cast("dict[str, object]", predecessors.row(0).document)

    cast("dict[str, object]", stored["manifest"])["cargo"] = "ore"
    retained["title"] = "Bo"
    cast("dict[str, object]", retained["manifest"])["cargo"] = "ore"

    assert predecessors.row(0).document == {"title": "Ada", "manifest": {"cargo": "timber"}}
    assert json.dumps(predecessors.row(0).document)


def test_predecessor_columns_materializes_one_complete_row_view_per_index() -> None:
    predecessors = _predecessor_columns(
        [
            {"id": 1, "acctNum": "A", "value": 100.00, "txStart": "t0", "txEnd": "infinity"},
            {"id": 2, "acctNum": "B", "value": 200.00, "txStart": "t1", "txEnd": "infinity"},
        ]
    )
    assert predecessors.length == 2
    assert predecessors.row(0).members == {
        "id": 1,
        "acctNum": "A",
        "value": 100.00,
        "txStart": "t0",
        "txEnd": "infinity",
    }
    assert predecessors.row(0).document is None
    assert predecessors.row(1).member("id") == 2
    # Materialize-on-demand: two calls for the same index build an equal but
    # independently allocated view, never a shared mutable flyweight.
    assert predecessors.row(0) == predecessors.row(0)
    assert predecessors.row(0) is not predecessors.row(0)


def test_predecessor_columns_freezes_nested_documents_after_an_immutable_prefix() -> None:
    address = {"geo": {"country": "FI"}, "phones": [{"number": "111"}]}
    predecessors = _predecessor_columns(
        [{"id": 1, "address": None}, {"id": 2, "address": address}],
        value_objects=("address",),
    )
    planned = cast("Mapping[str, object]", predecessors.row(1).member("address"))
    geo = cast("Mapping[str, object]", planned["geo"])
    phones = cast("Sequence[Mapping[str, object]]", planned["phones"])

    cast("dict[str, object]", address["geo"])["country"] = "SE"
    cast("list[dict[str, object]]", address["phones"])[0]["number"] = "999"

    assert predecessors.row(0).member("address") is None
    assert geo["country"] == "FI"
    assert phones[0]["number"] == "111"
    with pytest.raises(TypeError):
        cast("dict[str, object]", geo)["country"] = "SE"
    with pytest.raises(TypeError):
        cast("dict[str, object]", phones[0])["number"] = "999"


def test_predecessor_columns_refuses_misaligned_member_column_lengths() -> None:
    short: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
    short.append(1)
    long: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
    long.append(1)
    long.append(2)
    with pytest.raises(ValueError, match="one positive row count"):
        PredecessorColumns(
            shape=PredecessorShape(attributes=("id", "value")),
            attribute_columns=(whole(short.build()), whole(long.build())),
        )


def test_predecessor_columns_refuses_an_attribute_column_count_mismatch() -> None:
    one: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
    one.append(1)
    with pytest.raises(ValueError, match="one column per attribute"):
        PredecessorColumns(
            shape=PredecessorShape(attributes=("id", "value")),
            attribute_columns=(whole(one.build()),),
        )


def test_predecessor_columns_refuses_a_value_object_column_count_mismatch() -> None:
    one: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
    one.append(1)
    with pytest.raises(ValueError, match="one column per value object"):
        PredecessorColumns(
            shape=PredecessorShape(attributes=("id",), value_objects=("address",)),
            attribute_columns=(whole(one.build()),),
            value_object_columns=(),
        )


def test_predecessor_columns_refuses_zero_length_member_columns() -> None:
    empty = whole(ChunkedColumnBuilder[object]().build())
    with pytest.raises(ValueError, match="at least one row"):
        PredecessorColumns(shape=PredecessorShape(attributes=("id",)), attribute_columns=(empty,))


# --------------------------------------------------------------------------- #
# Materialized Write Group: aligned key/observation columns and              #
# indivisibility.                                                             #
# --------------------------------------------------------------------------- #
def _prepared(instruction: PredicateWrite, model: object) -> PreparedPredicateWrite:
    prepared = prepare_typed_write(instruction, cast("Any", model))
    assert isinstance(prepared, PreparedPredicateWrite)
    return prepared


def _predicate(entity: str, mutation: PredicateMutation) -> PreparedPredicateWrite:
    return _prepared(
        PredicateWrite(
            mutation,
            PredicateSelection(
                entity,
                predicate_algebra.Comparison(
                    "lessThan", f"{entity}.balance", "1000000.00"
                ),
            ),
        ),
        _ACCOUNT,
    )


def test_a_materialized_write_group_refuses_no_key_attributes() -> None:
    versions: ChunkedColumnBuilder[int] = ChunkedColumnBuilder()
    versions.append(1)
    with pytest.raises(ValueError, match="at least one key Attribute"):
        MaterializedWriteGroup(
            mutation=_predicate("Account", "delete"),
            key_attributes=(),
            key_columns=(),
            observations=VersionColumns(versions=whole(versions.build())),
        )


def test_a_materialized_write_group_refuses_a_key_column_count_mismatch() -> None:
    keys: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
    keys.append(1)
    versions: ChunkedColumnBuilder[int] = ChunkedColumnBuilder()
    versions.append(1)
    with pytest.raises(ValueError, match="one key column per key Attribute"):
        MaterializedWriteGroup(
            mutation=_predicate("Account", "delete"),
            key_attributes=("id", "region"),
            key_columns=(whole(keys.build()),),
            observations=VersionColumns(versions=whole(versions.build())),
        )


def test_a_materialized_write_group_refuses_key_columns_of_differing_lengths() -> None:
    short: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
    short.append(1)
    long: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
    long.append(1)
    long.append(2)
    versions: ChunkedColumnBuilder[int] = ChunkedColumnBuilder()
    versions.append(1)
    with pytest.raises(ValueError, match="key columns share one positive row count"):
        MaterializedWriteGroup(
            mutation=_predicate("Account", "delete"),
            key_attributes=("id", "region"),
            key_columns=(whole(short.build()), whole(long.build())),
            observations=VersionColumns(versions=whole(versions.build())),
        )


def test_a_materialized_write_group_refuses_a_key_observation_length_mismatch() -> None:
    keys: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
    keys.append(1)
    keys.append(2)
    versions: ChunkedColumnBuilder[int] = ChunkedColumnBuilder()
    versions.append(1)
    with pytest.raises(ValueError, match="same row count"):
        MaterializedWriteGroup(
            mutation=_predicate("Account", "delete"),
            key_attributes=("id",),
            key_columns=(whole(keys.build()),),
            observations=VersionColumns(versions=whole(versions.build())),
        )


def test_a_materialized_write_group_refuses_zero_rows() -> None:
    with pytest.raises(ValueError, match="at least one row"):
        MaterializedWriteGroup(
            mutation=_predicate("Account", "delete"),
            key_attributes=("id",),
            key_columns=(whole(ChunkedColumnBuilder[object]().build()),),
            observations=VersionColumns(versions=whole(ChunkedColumnBuilder[int]().build())),
        )


# --------------------------------------------------------------------------- #
# Planned Steps: a Materialized Write Group settles into a lazily            #
# materialized segment — stable, structurally-equal, non-flyweight views.     #
# --------------------------------------------------------------------------- #
def _version_group(
    entity: str, key_name: str, rows: Sequence[tuple[object, int]], assigned: float
) -> MaterializedWriteGroup:
    keys: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
    versions: ChunkedColumnBuilder[int] = ChunkedColumnBuilder()
    for key_value, version in rows:
        keys.append(key_value)
        versions.append(version)
    predicate = _prepared(
        PredicateWrite(
            "update",
            PredicateSelection(
                entity,
                predicate_algebra.Comparison(
                    "lessThan", f"{entity}.balance", "1000000.00"
                ),
            ),
            assignments=(
                WriteAssignment(f"{entity}.balance", Decimal(str(assigned))),
            ),
        ),
        _ACCOUNT,
    )
    return MaterializedWriteGroup(
        mutation=predicate,
        key_attributes=(key_name,),
        key_columns=(whole(keys.build()),),
        observations=VersionColumns(versions=whole(versions.build())),
    )


def test_a_materialized_groups_steps_are_equal_but_not_identity_stable_on_repeat_access() -> None:
    group = _version_group("Account", "id", [(1, 1), (2, 1), (3, 1)], assigned=0.00)
    plan = build_write_planner(_ACCOUNT).plan(
        PlanningRequest(
            subject_identity=TEST_SUBJECT_IDENTITY,
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
    keys: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
    for key_value, _members in rows:
        keys.append(key_value)
    predecessors = _predecessor_columns([members for _key, members in rows])
    predicate = _prepared(
        PredicateWrite(
            "terminate",
            PredicateSelection(
                entity,
                predicate_algebra.Comparison(
                    "lessThan", f"{entity}.value", "1000000.00"
                ),
            ),
        ),
        _BALANCE,
    )
    return MaterializedWriteGroup(
        mutation=predicate,
        key_attributes=(key_name,),
        key_columns=(whole(keys.build()),),
        observations=TemporalColumns(predecessors=predecessors),
    )


def test_a_temporal_materialized_groups_close_and_chain_are_equal_but_not_identity_stable() -> None:
    rows = [
        (
            row_id,
            {
                "id": row_id,
                "acctNum": "A",
                "value": 1.00 * row_id,
                "txStart": "2024-01-01T00:00:00+00:00",
                "txEnd": "infinity",
            },
        )
        for row_id in (1, 2)
    ]
    group = _temporal_group("Balance", "id", rows)
    plan = build_write_planner(_BALANCE).plan(
        PlanningRequest(
            subject_identity=TEST_SUBJECT_IDENTITY,
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
# Finalization: a Materialized Write Group's segment carries no group,        #
# Transaction Instant, Write Planner, entity-resolution context, or          #
# temporal-strategy answer past `plan()`, and a temporal group's topology     #
# and instant are both resolved during `plan()`, never on step access.        #
# --------------------------------------------------------------------------- #
_FORBIDDEN_PLAN_CONTEXT = (
    MaterializedWriteGroup,
    TransactionInstant,
    WritePlanner,
    Targets,
    MilestoneTopology,
)


def _segment_field_values(segment: object) -> list[object]:
    """Every value one Step Segment's own dataclass fields hold, plus — for a
    callable field — whatever its closure cells and bound ``__self__``
    capture.

    A segment that defers to a closure over live planning machinery (rather
    than holding already-settled data) hides exactly there: a callable
    field's ``__closure__`` cells and its ``__self__`` are where a captured
    group, instant, or planner would still be reachable.
    """
    values: list[object] = []
    for field in dataclasses.fields(cast("Any", segment)):
        value = getattr(segment, field.name)
        values.append(value)
        if callable(value) and not isinstance(value, type):
            self_obj = getattr(value, "__self__", None)
            if self_obj is not None:
                values.append(self_obj)
            closure = getattr(getattr(value, "__func__", value), "__closure__", None)
            if closure:
                values.extend(cell.cell_contents for cell in closure)
    return values


def test_a_materialized_plans_segments_retain_no_group_instant_or_planner() -> None:
    # The Write Plan a Materialized Write Group settles into must not be able
    # to re-derive a step from live planning machinery: no segment field (nor
    # any closure a callable field captures) may be the group itself, the
    # attempt's Transaction Instant, or the Write Planner — every semantic
    # fact a step needs is already decided by the time `plan()` returns
    # (`m-unit-work` "The Write Plan ... MUST NOT retain ... a private
    # group").
    rows = [
        (
            row_id,
            {
                "id": row_id,
                "acctNum": "A",
                "value": 1.00 * row_id,
                "txStart": "2024-01-01T00:00:00+00:00",
                "txEnd": "infinity",
            },
        )
        for row_id in (1, 2)
    ]
    plan = build_write_planner(_BALANCE).plan(
        PlanningRequest(
            subject_identity=TEST_SUBJECT_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="optimistic",
            buffered_writes=[_temporal_group("Balance", "id", rows)],
        )
    )
    for segment in plan.steps.segments:
        for value in _segment_field_values(segment):
            assert not isinstance(value, _FORBIDDEN_PLAN_CONTEXT)


def test_a_materialized_temporal_groups_instant_resolves_during_plan_not_on_step_access() -> None:
    # Reaching a temporal Materialized Write Group is what makes the attempt
    # capture its instant (ADR 0010), and the capture happens while `plan()`
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
                "txStart": "2024-01-01T00:00:00+00:00",
                "txEnd": "infinity",
            },
        )
        for row_id in (1, 2, 3)
    ]
    plan = build_write_planner(_BALANCE).plan(
        PlanningRequest(
            subject_identity=TEST_SUBJECT_IDENTITY,
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
    # `resolve_successors` decides which successors exist, each one's
    # represented-state kind, and which Valid-Time bound expression applies —
    # the semantic content of temporal expansion (`m-unit-work` stage 7) —
    # from the group's own topology alone, before any row is in hand. It must
    # run once, while `plan()` settles the segment, and never again on a
    # later `steps[i]` access, however many times or in what order that
    # access repeats: a Write Plan is frozen, and re-running a planning
    # decision at consumption is the same defect as re-capturing the instant
    # there.
    calls: list[object] = []
    original = write_planner.resolve_successors  # pyright: ignore[reportPrivateImportUsage]

    def counting_resolve(*args: object, **kwargs: object) -> object:
        calls.append(None)
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(write_planner, "resolve_successors", counting_resolve)
    rows = [
        (
            row_id,
            {
                "id": row_id,
                "acctNum": "A",
                "value": 1.00 * row_id,
                "txStart": "2024-01-01T00:00:00+00:00",
                "txEnd": "infinity",
            },
        )
        for row_id in (1, 2, 3)
    ]
    plan = build_write_planner(_BALANCE).plan(
        PlanningRequest(
            subject_identity=TEST_SUBJECT_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="optimistic",
            buffered_writes=[_temporal_group("Balance", "id", rows)],
        )
    )
    assert len(calls) == 1
    _ = plan.steps[0]
    _ = plan.steps[0]
    _ = list(plan.steps)
    # No step access — first, repeated, or iterated — re-resolves the topology.
    assert len(calls) == 1


def test_no_materialized_segments_mapping_field_is_a_plain_mutable_dict() -> None:
    # Any mapping stored on a Step Segment is retained across later `step()`
    # calls rather than copied afresh. It must therefore be read-only so every
    # subsequent access observes the same planned values.
    versioned_plan = build_write_planner(_ACCOUNT).plan(
        PlanningRequest(
            subject_identity=TEST_SUBJECT_IDENTITY,
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
                "txStart": "2024-01-01T00:00:00+00:00",
                "txEnd": "infinity",
            },
        )
    ]
    temporal_plan = build_write_planner(_BALANCE).plan(
        PlanningRequest(
            subject_identity=TEST_SUBJECT_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="optimistic",
            buffered_writes=[_temporal_group("Balance", "id", rows)],
        )
    )
    for plan in (versioned_plan, temporal_plan):
        for segment in plan.steps.segments:
            for field in dataclasses.fields(cast("Any", segment)):
                value = getattr(segment, field.name)
                if isinstance(value, Mapping):
                    assert isinstance(value, MappingProxyType), (
                        f"{type(segment).__name__}.{field.name} is a plain mutable mapping"
                    )


def test_mutating_a_materialized_groups_assignment_row_leaves_steps_unaffected() -> None:
    # `_MaterializedTemporalSegment.assignment_row` retains the group's own
    # authored overlay across every resolved row, so a caller reaching it
    # through `plan.steps.segments` and mutating it in place must never
    # change what a subsequently retrieved step carries — a Write Plan is
    # immutable and its views are stable.
    rows = [
        (
            1,
            {
                "id": 1,
                "acctNum": "A",
                "value": 1.00,
                "txStart": "2024-01-01T00:00:00+00:00",
                "txEnd": "infinity",
            },
        )
    ]
    predicate = _prepared(
        PredicateWrite(
            "update",
            PredicateSelection(
                "Balance",
                predicate_algebra.Comparison("lessThan", "Balance.value", "1000000.00"),
            ),
            assignments=(WriteAssignment("Balance.value", Decimal("9.00")),),
        ),
        _BALANCE,
    )
    keys: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
    keys.append(1)
    group = MaterializedWriteGroup(
        mutation=predicate,
        key_attributes=("id",),
        key_columns=(whole(keys.build()),),
        observations=TemporalColumns(
            predecessors=_predecessor_columns([members for _key, members in rows])
        ),
    )
    plan = build_write_planner(_BALANCE).plan(
        PlanningRequest(
            subject_identity=TEST_SUBJECT_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="optimistic",
            buffered_writes=[group],
        )
    )
    before = plan.steps[1]
    assert isinstance(before, PlannedInsert)
    segment = cast("Any", plan.steps.segments[0])
    with pytest.raises(TypeError):
        cast("dict[str, object]", segment.assignment_row)["value"] = 777.0
    after = plan.steps[1]
    assert after == before
    (entry,) = cast("PlannedInsert", after).entries
    value_attribute = next(a for a in entry.row.attributes if a.name == "value")
    assert entry.row.attributes[value_attribute] == 9.0


def test_a_materialized_plan_deeply_freezes_an_assigned_value_object_document() -> None:
    prior_address: dict[str, object] = {
        "street": "10 Old Road",
        "city": "Helsinki",
        "geo": {"country": "FI"},
        "phones": [{"type": "mobile", "number": "111"}],
    }
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
            "validStart": "2024-01-01T00:00:00+00:00",
            "validEnd": "infinity",
            "txStart": "2024-01-01T00:00:00+00:00",
            "txEnd": "infinity",
            "address": prior_address,
        }
    ]
    keys: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
    keys.append(1)
    group = MaterializedWriteGroup(
        mutation=_prepared(
            PredicateWrite(
                "update",
                PredicateSelection("Branch", predicate_algebra.Comparison("eq", "Branch.id", 1)),
                assignments=(WriteAssignment("Branch.address", assigned_address),),
                valid_from="2024-07-01T00:00:00.000000Z",
            ),
            _BRANCH,
        ),
        key_attributes=("id",),
        key_columns=(whole(keys.build()),),
        observations=TemporalColumns(
            predecessors=_predecessor_columns(rows, value_objects=("address",))
        ),
    )
    plan = build_write_planner(_BRANCH).plan(
        PlanningRequest(
            subject_identity=TEST_SUBJECT_IDENTITY,
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
    geo = cast("Mapping[str, object]", address["geo"])
    phones = cast("Sequence[Mapping[str, object]]", address["phones"])
    predecessor_address = cast("Mapping[str, object]", entry.origin.predecessor.member("address"))
    predecessor_geo = cast("Mapping[str, object]", predecessor_address["geo"])
    predecessor_phones = cast("Sequence[Mapping[str, object]]", predecessor_address["phones"])

    cast("dict[str, object]", assigned_address["geo"])["country"] = "SE"
    cast("list[dict[str, object]]", assigned_address["phones"])[0]["number"] = "999"
    cast("dict[str, object]", prior_address["geo"])["country"] = "SE"
    cast("list[dict[str, object]]", prior_address["phones"])[0]["number"] = "999"

    assert geo["country"] == "FI"
    assert phones[0]["number"] == "222"
    assert predecessor_geo["country"] == "FI"
    assert predecessor_phones[0]["number"] == "111"
    with pytest.raises(TypeError):
        cast("dict[str, object]", geo)["country"] = "SE"
    with pytest.raises(TypeError):
        cast("dict[str, object]", phones[0])["number"] = "999"
    with pytest.raises(TypeError):
        cast("list[Mapping[str, object]]", phones)[0] = {"type": "mobile", "number": "999"}
    with pytest.raises(TypeError):
        cast("dict[str, object]", predecessor_geo)["country"] = "SE"
    with pytest.raises(TypeError):
        cast("dict[str, object]", predecessor_phones[0])["number"] = "999"

    assert plan.steps[2] == changed
    statement = compile_write(plan.steps[2], _BRANCH, POSTGRES)
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
    # `plan()` settles a Materialized Write Group's group-wide facts once and
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
    plan = build_write_planner(_ACCOUNT).plan(
        PlanningRequest(
            subject_identity=TEST_SUBJECT_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="optimistic",
            buffered_writes=[group],
        )
    )
    assert len(constructed) == 0  # `plan()` alone constructs none
    assert len(plan.steps) == 500
    for step in plan.steps:
        assert isinstance(step, PlannedUpdate)
    assert len(constructed) == 500  # exactly one per step actually accessed


def test_repeated_planning_of_an_equal_materialized_group_yields_equal_plans() -> None:
    first_plan = build_write_planner(_ACCOUNT).plan(
        PlanningRequest(
            subject_identity=TEST_SUBJECT_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="optimistic",
            buffered_writes=[_version_group("Account", "id", [(1, 1), (2, 1)], assigned=5.00)],
        )
    )
    second_plan = build_write_planner(_ACCOUNT).plan(
        PlanningRequest(
            subject_identity=TEST_SUBJECT_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="optimistic",
            buffered_writes=[_version_group("Account", "id", [(1, 1), (2, 1)], assigned=5.00)],
        )
    )
    assert first_plan == second_plan
    assert first_plan.steps == second_plan.steps


# --------------------------------------------------------------------------- #
# End to end: structural sharing survives materialization, temporal          #
# expansion, and lowering together, for a multi-row bitemporal resolve.       #
# --------------------------------------------------------------------------- #
def _position_row(row_id: int) -> dict[str, object]:
    return {
        "id": row_id,
        "acct_num": "A",
        "value": Decimal("200.00"),
        "from_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "thru_z": INFINITY,
        "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "out_z": INFINITY,
    }


def test_a_multi_row_materialized_bitemporal_update_lowers_one_close_and_chain_per_row() -> None:
    port = ScriptedPort(
        Transact(Read(rows=[_position_row(1), _position_row(2), _position_row(3)]), Write(times=9))
    )
    valid_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
    clock = FixedClock(dt.datetime(2024, 6, 1, tzinfo=dt.UTC))

    def fn(tx: Transaction) -> None:
        tx.update_where(
            WherePosition.where(WherePosition.value == Decimal("200.00")),
            WherePosition.value.set(Decimal("300.00")),
            valid_from=valid_from,
        )

    Database.connect(port, WHERE_POSITION_META, clock=clock).transact(fn, concurrency="optimistic")
    writes = [(op.sql, op.binds) for op in port.calls if isinstance(op, WriteCall)]
    # Each resolved row settles to its own close + head + tail (three
    # statements), and the three rows' own topologies never interleave or
    # merge — the SAME per-row shape a single-row materialize proves,
    # scaled to three, with no shared mutable state between rows.
    assert len(writes) == 9
    closes = [(sql, binds) for sql, binds in writes if sql.startswith("update ")]
    inserts = [(sql, binds) for sql, binds in writes if sql.startswith("insert ")]
    assert len(closes) == 3
    assert len(inserts) == 6
    closed_keys = {binds[1] for _sql, binds in closes}  # `... where pos_id = ? and ...`
    inserted_keys = {binds[0] for _sql, binds in inserts}  # `insert into position(pos_id, ...`
    assert closed_keys == {1, 2, 3}
    assert inserted_keys == {1, 2, 3}


# --------------------------------------------------------------------------- #
# Streaming no-op elimination applies uniformly to the temporal (Predecessor  #
# Columns) branch, not only the versioned one — the per-row equality filter   #
# never retains a comparison-only column for either shape.                    #
# --------------------------------------------------------------------------- #
def _balance_row(row_id: int, value: Decimal) -> dict[str, object]:
    return {
        "bal_id": row_id,
        "acct_num": "A",
        "val": value,
        "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
        "out_z": INFINITY,
    }


def test_a_temporal_materializing_update_eliminates_a_no_op_row_and_chains_the_rest() -> None:
    port = ScriptedPort(
        Transact(
            Read(rows=[_balance_row(1, Decimal("5.00")), _balance_row(2, Decimal("10.00"))]),
            Write(times=2),
        )
    )

    def fn(tx: Transaction) -> None:
        tx.update_where(
            mm.Balance.where(mm.Balance.value < Decimal("1000000.00")),
            mm.Balance.value.set(Decimal("5.00")),
        )

    db_for(BALANCE_MODEL, port).transact(fn, concurrency="optimistic")
    writes = [op for op in port.calls if isinstance(op, WriteCall)]
    # Row 1 already holds the assigned value and is streamed out before it
    # ever reaches a column builder; only row 2's close + chain reach the
    # driver.
    assert len(writes) == 2


def test_a_temporal_materializing_update_with_every_row_a_no_op_buffers_nothing() -> None:
    port = ScriptedPort(Transact(Read(rows=[_balance_row(1, Decimal("5.00"))])))

    def fn(tx: Transaction) -> None:
        tx.update_where(
            mm.Balance.where(mm.Balance.value < Decimal("1000000.00")),
            mm.Balance.value.set(Decimal("5.00")),
        )

    db_for(BALANCE_MODEL, port).transact(fn, concurrency="optimistic")
    assert not any(isinstance(op, WriteCall) for op in port.calls)
