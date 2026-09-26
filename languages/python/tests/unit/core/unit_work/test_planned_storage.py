"""Compact private column storage for write planning (m-unit-work, Docker-free).

Covers the compact private storage constructs beneath the finalized Planned
Write algebra: bounded chunk construction and Column Slice sharing
(:mod:`parallax.core.unit_work.columns`), a Materialized Write Group's aligned
evidence — retained Predecessor Rows or key/version columns — Planned Steps'
segmented backing —
stable view equality with no object-identity promise, and no mutable
flyweight reused across iterations — and structural sharing carried all the
way through temporal expansion and lowering. Bounded wrapper allocation is a
separate invariant from storage shape and correctness.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Mapping, Sequence, Sized
from decimal import Decimal
from types import MappingProxyType
from typing import Any, cast

import pytest

# The module itself, not a name from it: the call-count regression below
# monkeypatches `resolve_successors` where `_settle_temporal_group` looks it
# up, which is this module's own namespace rather than `unit_work.temporal`'s.
import parallax.core.unit_work.write_settlement as write_settlement
from parallax.conformance import models
from parallax.core import inheritance, opt_lock, temporal_read
from parallax.core import predicate as predicate_algebra
from parallax.core._formation_profile import BUILTIN_MANIFEST
from parallax.core.base import INFINITY, FrozenMap
from parallax.core.db_port import JsonDocument
from parallax.core.dialect import POSTGRES
from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._layout import LayoutCatalog
from parallax.core.metamodel import AttributeMetadata, FacetKey, Metamodel
from parallax.core.model_formation import ModelCompilerRequirement
from parallax.core.sql_gen._write import compile_write_step
from parallax.core.unit_work import (
    ChunkedColumnBuilder,
    EntityStateRow,
    FixedClock,
    MaterializedWriteGroup,
    MilestoneTopology,
    PlannedClose,
    PlannedInsert,
    PlanningRequest,
    PredecessorRows,
    PredecessorRowsBuilder,
    PredicateSelection,
    PredicateWrite,
    SystemClock,
    TransactionInstant,
    VersionArithmetic,
    VersionedEvidence,
    VersionedEvidenceBuilder,
    WriteAssignment,
    WritePlan,
    WritePlanner,
    whole,
)
from parallax.core.unit_work.columns import (
    _CHUNK_SIZE,  # pyright: ignore[reportPrivateUsage] - bounded-chunking regression only
    ChunkedColumn,
    ColumnSlice,
    freeze_retained_value,
)
from parallax.core.unit_work.instructions import (
    PreparedPredicateWrite,
    prepare_typed_write,
)
from parallax.core.unit_work.planned import ChangedFrom, PlannedUpdate, adopt_planned_row
from parallax.core.unit_work.strategy import (
    AuditStrategy,
    BatchingStrategy,
    ConcurrencyStrategy,
    TemporalStrategy,
)
from parallax.core.unit_work.write_settlement import (
    WriteSettlement,  # producer-reach regression only
)
from parallax.snapshot.handle import Database, Transaction, build_write_planner
from tests._support import mirrored_models as mm
from tests._support.clock_probes import CountingClock, inert_instant
from tests._support.db_port import (
    Read,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
)
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests._support.root_ownership import own_root
from tests.unit._document_layout_support import PERSON, document_model
from tests.unit._gc_reachability import reachable_objects
from tests.unit._temporal_group_support import temporal_group
from tests.unit._transact_support import BALANCE as BALANCE_MODEL
from tests.unit._transact_support import WHERE_POSITION_META, WherePosition, db_for

_MODELS = models.load_models()
_ACCOUNT = _MODELS["account"]
_BALANCE = _MODELS["balance"]
_BRANCH = _MODELS["branch"]
_POSITION = _MODELS["position"]


# --------------------------------------------------------------------------- #
# Chunked Column / Column Slice: bounded construction and structural sharing. #
# --------------------------------------------------------------------------- #
def test_retained_tuple_freezes_nested_mutable_values_without_copying_immutable_peers() -> None:
    immutable = ("stable",)

    frozen = freeze_retained_value((immutable, [1, {"nested": [2]}]))

    assert frozen == (immutable, (1, FrozenMap({"nested": (2,)})))
    assert cast("tuple[object, ...]", frozen)[0] is immutable


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
# Group evidence: aligned by construction, adopted by reference.              #
# --------------------------------------------------------------------------- #
_PERSON = LayoutCatalog(document_model()).entity(PERSON)


def _person_row(key: int) -> tuple[object, ...]:
    return (key, "Ada", ABSENT, None, ("Bergen", ("NO",)), (("founder",), (None,)))


def _person_rows(
    rows: Sequence[tuple[object, ...]], documents: Sequence[object] | None = None
) -> PredecessorRows:
    builder = PredecessorRowsBuilder(
        _PERSON.member_selection,
        key_position=_PERSON.primary_key[0],
        absent=ABSENT,
        documents=documents is not None,
    )
    for index, row in enumerate(rows):
        builder.append(row, None if documents is None else documents[index])
    sealed = builder.seal()
    assert sealed is not None
    return sealed


def test_predecessor_rows_retain_each_judged_row_and_raw_document_by_reference() -> None:
    first, second = _person_row(1), _person_row(2)
    stored: list[object] = [{"displayName": "Ada", "unknown": {"kept": True}}, {}]

    evidence = _person_rows([first, second], stored)
    predecessor = evidence.predecessor(0)

    assert len(evidence) == 2
    assert evidence.rows[0] is first
    assert evidence.rows[1] is second
    assert [evidence.key(0), evidence.key(1)] == [1, 2]
    assert evidence.document(0) is stored[0]
    assert predecessor.document is stored[0]
    assert predecessor.member("address") == {"city": "Bergen", "geo": {"country": "NO"}}
    assert predecessor.member("score") is ABSENT
    assert evidence.predecessor(0) == predecessor
    assert evidence.predecessor(0) is not predecessor


def test_predecessor_rows_without_a_structured_column_answer_no_document() -> None:
    evidence = _person_rows([_person_row(1)])

    assert evidence.documents is None
    assert evidence.document(0) is None
    assert evidence.predecessor(0).document is None


def test_predecessor_rows_seal_bounded_chunks_and_keep_documents_aligned() -> None:
    count = _CHUNK_SIZE * 2 + 3
    rows = [_person_row(key) for key in range(count)]
    documents: list[object] = [{"row": key} for key in range(count)]

    evidence = _person_rows(rows, documents)

    assert [len(chunk) for chunk in evidence.rows.column.chunks] == [
        _CHUNK_SIZE,
        _CHUNK_SIZE,
        3,
    ]
    for index in (0, _CHUNK_SIZE - 1, _CHUNK_SIZE, count - 1):
        assert evidence.rows[index] is rows[index]
        assert evidence.key(index) == index
        assert evidence.document(index) is documents[index]


def test_predecessor_rows_read_an_axis_start_by_its_selection_position() -> None:
    evidence = _person_rows([_person_row(5)])
    key = cast("AttributeMetadata", _PERSON.member_selection.bindings[0]).identity

    assert evidence.axis_start(0, key) == 5
    assert evidence.axis_start(0, dataclasses.replace(key, name="txStart")) is None


def test_predecessor_rows_refuse_misaligned_or_empty_evidence() -> None:
    evidence = _person_rows([_person_row(1)], [{}])
    two: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
    two.append({})
    two.append({})
    empty = whole(ChunkedColumnBuilder[tuple[object, ...]]().build())

    with pytest.raises(ValueError, match="one raw document with each row"):
        dataclasses.replace(evidence, documents=whole(two.build()))
    with pytest.raises(ValueError, match="at least one row"):
        dataclasses.replace(evidence, rows=empty, documents=None)
    with pytest.raises(ValueError, match="key position"):
        dataclasses.replace(evidence, key_position=len(_PERSON.member_selection.bindings))


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


def test_an_evidence_builder_that_appended_nothing_seals_to_nothing() -> None:
    temporal = PredecessorRowsBuilder(
        _PERSON.member_selection, key_position=0, absent=ABSENT, documents=True
    )
    versioned = VersionedEvidenceBuilder(key_position=0, version_position=1)

    assert temporal.seal() is None
    assert versioned.seal() is None


def test_trusted_carrier_adoption_rejects_invalid_storage() -> None:
    with pytest.raises(TypeError, match="final dict or mapping proxy"):
        adopt_planned_row(cast("Any", FrozenMap({})), {})


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
    plan = (
        build_write_planner(_ACCOUNT)
        .finalize(
            PlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=inert_instant(),
                concurrency="optimistic",
                buffered_writes=[group],
            )
        )
        .plan
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
                "txStart": "2024-01-01T00:00:00+00:00",
                "txEnd": "infinity",
            },
        )
        for row_id in (1, 2)
    ]
    group = _temporal_group("Balance", "id", rows)
    plan = (
        build_write_planner(_BALANCE)
        .finalize(
            PlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=inert_instant(),
                concurrency="optimistic",
                buffered_writes=[group],
            )
        )
        .plan
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
    WriteSettlement,
    MilestoneTopology,
    BatchingStrategy,
    ConcurrencyStrategy,
    TemporalStrategy,
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


def _reachable_from_segments(plan: WritePlan) -> list[object]:
    return [value for segment in plan.steps.segments for value in reachable_objects(segment)]


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
                "txStart": "2024-01-01T00:00:00+00:00",
                "txEnd": "infinity",
            },
        )
        for row_id in (1, 2)
    ]
    plan = (
        build_write_planner(_BALANCE)
        .finalize(
            PlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=inert_instant(),
                concurrency="optimistic",
                buffered_writes=[_temporal_group("Balance", "id", rows)],
            )
        )
        .plan
    )
    walked = _reachable_from_segments(plan)
    assert not [value for value in walked if _is_producer(value)]
    # The resolved instant and the key columns' slices sit nested inside the
    # segment, so reaching them shows the walk descended.
    assert any(isinstance(value, dt.datetime) for value in walked)
    assert any(isinstance(value, ColumnSlice) for value in walked)


def _account_plan(group: MaterializedWriteGroup) -> WritePlan:
    return (
        build_write_planner(_ACCOUNT)
        .finalize(
            PlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=inert_instant(),
                concurrency="optimistic",
                buffered_writes=[group],
            )
        )
        .plan
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
    walked = _reachable_from_segments(plan)
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
                "txStart": "2024-01-01T00:00:00+00:00",
                "txEnd": "infinity",
            },
        )
        for row_id in (1, 2, 3)
    ]
    plan = (
        build_write_planner(_BALANCE)
        .finalize(
            PlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=TransactionInstant(clock),
                concurrency="optimistic",
                buffered_writes=[_temporal_group("Balance", "id", rows)],
            )
        )
        .plan
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
    # run once, while `finalize()` settles the segment, and never again on a
    # later `steps[i]` access, however many times or in what order that
    # access repeats: a Write Plan is frozen, and re-running a planning
    # decision at consumption is the same defect as re-capturing the instant
    # there.
    calls: list[object] = []
    original = write_settlement.resolve_successors  # pyright: ignore[reportPrivateImportUsage]

    def counting_resolve(*args: object, **kwargs: object) -> object:
        calls.append(None)
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(write_settlement, "resolve_successors", counting_resolve)
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
    plan = (
        build_write_planner(_BALANCE)
        .finalize(
            PlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=inert_instant(),
                concurrency="optimistic",
                buffered_writes=[_temporal_group("Balance", "id", rows)],
            )
        )
        .plan
    )
    assert len(calls) == 1
    _ = plan.steps[0]
    _ = plan.steps[0]
    _ = list(plan.steps)
    # No step access — first, repeated, or iterated — re-resolves the topology.
    assert len(calls) == 1


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
    plan = (
        build_write_planner(model)
        .finalize(
            PlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=inert_instant(),
                concurrency="optimistic",
                buffered_writes=[temporal_group(_value_update(entity, valid_from), model, rows)],
            )
        )
        .plan
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
    versioned_plan = (
        build_write_planner(_ACCOUNT)
        .finalize(
            PlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=inert_instant(),
                concurrency="optimistic",
                buffered_writes=[_version_group("Account", "id", [(1, 1)], assigned=9.0)],
            )
        )
        .plan
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
    temporal_plan = (
        build_write_planner(_BALANCE)
        .finalize(
            PlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=inert_instant(),
                concurrency="optimistic",
                buffered_writes=[_temporal_group("Balance", "id", rows)],
            )
        )
        .plan
    )
    for plan in (versioned_plan, temporal_plan):
        for segment in plan.steps.segments:
            for field in dataclasses.fields(cast("Any", segment)):
                value = getattr(segment, field.name)
                if isinstance(value, Mapping):
                    assert isinstance(value, MappingProxyType), (
                        f"{type(segment).__name__}.{field.name} is a plain mutable mapping"
                    )


def test_mutating_a_materialized_groups_assignments_leaves_steps_unaffected() -> None:
    # `_MaterializedTemporalSegment` retains the group's resolved authored maps
    # across every resolved row, so a caller reaching them through
    # `plan.steps.segments` must not be able to change what a subsequently
    # retrieved step carries — a Write Plan is immutable and its views are
    # stable.
    rows = [
        {
            "id": 1,
            "acctNum": "A",
            "value": 1.00,
            "txStart": "2024-01-01T00:00:00+00:00",
            "txEnd": "infinity",
        }
    ]
    group = temporal_group(_value_update("Balance", None), _BALANCE, rows)
    plan = (
        build_write_planner(_BALANCE)
        .finalize(
            PlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=inert_instant(),
                concurrency="optimistic",
                buffered_writes=[group],
            )
        )
        .plan
    )
    before = plan.steps[1]
    assert isinstance(before, PlannedInsert)
    segment = cast("Any", plan.steps.segments[0])
    (value_identity,) = segment.authored_attributes
    with pytest.raises(TypeError):
        cast("dict[object, object]", segment.authored_attributes)[value_identity] = object()
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
            "validStart": "2024-01-01T00:00:00+00:00",
            "validEnd": "infinity",
            "txStart": "2024-01-01T00:00:00+00:00",
            "txEnd": "infinity",
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
    plan = (
        build_write_planner(_BRANCH)
        .finalize(
            PlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=inert_instant(),
                concurrency="optimistic",
                buffered_writes=[group],
            )
        )
        .plan
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
    statement = compile_write_step(plan.steps[2], _BRANCH, POSTGRES)
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
    plan = (
        build_write_planner(_ACCOUNT)
        .finalize(
            PlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=inert_instant(),
                concurrency="optimistic",
                buffered_writes=[group],
            )
        )
        .plan
    )
    assert len(constructed) == 0  # `finalize()` alone constructs none
    assert len(plan.steps) == 500
    for step in plan.steps:
        assert isinstance(step, PlannedUpdate)
    assert len(constructed) == 500  # exactly one per step actually accessed


def test_repeated_planning_of_an_equal_materialized_group_yields_equal_plans() -> None:
    first_plan = (
        build_write_planner(_ACCOUNT)
        .finalize(
            PlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=inert_instant(),
                concurrency="optimistic",
                buffered_writes=[_version_group("Account", "id", [(1, 1), (2, 1)], assigned=5.00)],
            )
        )
        .plan
    )
    second_plan = (
        build_write_planner(_ACCOUNT)
        .finalize(
            PlanningRequest(
                actor_identity=TEST_ACTOR_IDENTITY,
                transaction_instant=inert_instant(),
                concurrency="optimistic",
                buffered_writes=[_version_group("Account", "id", [(1, 1), (2, 1)], assigned=5.00)],
            )
        )
        .plan
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
    port = ScriptedAdapter(
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

    own_root(
        Database.connect(port, WHERE_POSITION_META, clock=clock)
    ).using_database_login().transact(fn, concurrency="optimistic")
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
    port = ScriptedAdapter(
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
    port = ScriptedAdapter(Transact(Read(rows=[_balance_row(1, Decimal("5.00"))])))

    def fn(tx: Transaction) -> None:
        tx.update_where(
            mm.Balance.where(mm.Balance.value < Decimal("1000000.00")),
            mm.Balance.value.set(Decimal("5.00")),
        )

    db_for(BALANCE_MODEL, port).transact(fn, concurrency="optimistic")
    assert not any(isinstance(op, WriteCall) for op in port.calls)
