"""How settlement forms a flush's Write Groups (`m-unit-work` *Write Group
formation*)."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from typing import Any

import pytest

from parallax.core import Bitemporal
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work import write_settlement as settlement
from parallax.core._execution._unit_work.instructions import prepare_typed_write, prepare_wire_write
from parallax.core._execution._unit_work.write_items import (
    AdmittedWrite,
    ComposedTemporalWrite,
    ComposedWrite,
    target_write,
)
from parallax.core.internal import inheritance
from parallax.core.internal.base import INFINITY
from parallax.core.internal.concurrency import ConcurrencyPreference
from parallax.core.internal.metamodel import AttributeIdentity, EntityIdentity, Metamodel
from parallax.core.internal.unit_work import (
    KeyedWriteInstruction,
    TargetMutation,
    TargetWriteInstruction,
    TransactionInstant,
    WritePlanningRequest,
    admitted_write,
    object_key,
)
from parallax.core.internal.write_plan import (
    ObjectKey,
    PredecessorRow,
    StateObservation,
    TemporalObservation,
    VersionObservation,
    WritePlan,
)
from parallax.core.internal.write_plan.plan import AcquisitionSpan, SettledWrite, WriteGroup
from parallax.core.internal.write_plan.steps import (
    FAILED_PRECONDITION,
    TERMINATED,
    KeyTarget,
    MilestoneTarget,
    PlannedClose,
    PlannedInsert,
    PlannedStep,
    PlannedUpdate,
    TemporalGate,
)
from parallax.descriptor._records import Metamodel as DescriptorMetamodel
from tests._support.bindings import bound_model
from tests._support.clock_probes import instant_at
from tests._support.planner_probes import (
    TEST_ACTOR_IDENTITY,
    admitted_writes,
    observed_buffer,
    plan_steps,
    unobserved_write,
)
from tests._support.write_preparation import write_preparation_of
from tests.unit._corpus_model_support import corpus_records, formed
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit.core._shared_coverage_support import MODEL as SHARED_MODEL
from tests.unit.core._shared_coverage_support import (
    ShareCols,
    ShareDoc,
    day,
    frag,
    frag_rows,
    observation,
    rectangle,
)
from tests.unit.core._shared_coverage_support import plan as shared_plan

_MODELS = corpus_records()
_WALLET = corpus_model("wallet")
_BALANCE = corpus_model("balance")
_POSITION = corpus_model("position")
_ANIMAL = corpus_model("animal")
_LEDGERS = formed(
    DescriptorMetamodel(entities=(*_MODELS["wallet"].entities, *_MODELS["account"].entities))
)
# Later than every stored Transaction-Time start a test below closes.
_INSTANT = instant_at("2024-06-01T00:00:00+00:00")
_JAN = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


def _finalize(
    buffered: Sequence[ComposedWrite],
    model: Metamodel,
    *,
    concurrency: ConcurrencyPreference = "optimistic",
    instant: TransactionInstant = _INSTANT,
) -> WritePlan:
    return build_write_planner(bound_model(model)).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant,
            preference=concurrency,
            composed_writes=buffered,
        )
    )


def _plan(
    buffer: Sequence[KeyedWriteInstruction],
    model: Metamodel,
    observations: Mapping[ObjectKey, StateObservation] | None = None,
    *,
    concurrency: ConcurrencyPreference = "optimistic",
    instant: TransactionInstant = _INSTANT,
) -> WritePlan:
    return _finalize(
        observed_buffer(buffer, model, observations),
        model,
        concurrency=concurrency,
        instant=instant,
    )


def _sizes(plan: WritePlan) -> list[int | str]:
    """Each plan entry's write count, or ``"deferred"`` for a deferred write,
    which is an entry of its own."""
    return [
        len(entry.writes) if isinstance(entry, WriteGroup) else "deferred" for entry in plan.entries
    ]


def _groups(plan: WritePlan) -> list[WriteGroup]:
    groups = [entry for entry in plan.entries if isinstance(entry, WriteGroup)]
    assert len(groups) == len(plan.entries)
    return groups


def _amend_wallet(key: int, balance: str) -> KeyedWriteInstruction:
    return KeyedWriteInstruction("amend", "Wallet", ({"id": key, "balance": Decimal(balance)},))


def _keys(step: PlannedStep) -> tuple[object, ...]:
    match step:
        case PlannedInsert(entries=entries):
            return tuple(
                value
                for entry in entries
                for name, value in entry.row.attributes.items()
                if name.name == "id"
            )
        case PlannedUpdate(target=KeyTarget(key_values=values)):
            return tuple(value for (value,) in values)
        case _:
            assert isinstance(step.target, MilestoneTarget)
            return step.target.key_values


def _kinds(steps: Sequence[PlannedStep]) -> list[str]:
    return ["insert" if isinstance(step, PlannedInsert) else "non-insert" for step in steps]


def _balance_observation(key: int, value: str = "1.00") -> StateObservation:
    return TemporalObservation(
        predecessor=PredecessorRow(
            members={
                "id": key,
                "acctNum": "A",
                "value": Decimal(value),
                "txStart": _JAN,
                "txEnd": INFINITY,
            }
        )
    )


def _position_observation(key: int) -> StateObservation:
    return TemporalObservation(
        predecessor=PredecessorRow(
            members={
                "id": key,
                "acctNum": f"P{key}",
                "value": Decimal("1.0"),
                "validStart": _JAN,
                "validEnd": INFINITY,
                "txStart": _JAN,
                "txEnd": INFINITY,
            }
        )
    )


def _observed(
    model: Metamodel,
    buffer: Sequence[KeyedWriteInstruction],
    observe: Callable[[int], StateObservation],
) -> dict[ObjectKey, StateObservation]:
    observations: dict[ObjectKey, StateObservation] = {}
    for instruction in buffer:
        key = object_key(instruction, model)
        assert key is not None
        ((_name, value),) = key.primary_key
        assert isinstance(value, int)
        observations[key] = observe(value)
    return observations


_LIMIT = settlement._WRITES_PER_GROUP  # pyright: ignore[reportPrivateUsage] - the group bound


@pytest.mark.parametrize(
    ("objects", "sizes"),
    [
        (0, []),
        (1, [1]),
        (_LIMIT - 1, [_LIMIT - 1]),
        (_LIMIT, [_LIMIT]),
        (_LIMIT + 1, [_LIMIT, 1]),
        (2 * _LIMIT + 2, [_LIMIT, _LIMIT, 2]),
    ],
    ids=["none", "one", "just-below", "at", "just-above", "two-full-and-two"],
)
def test_writes_of_distinct_objects_share_groups_of_at_most_the_group_bound(
    objects: int, sizes: list[int]
) -> None:
    # Distinct balances, so batching merges none of them into one step, and
    # every full group's updates are one shape: a span over all of them, with
    # no row cap of its own.
    plan = _plan([_amend_wallet(key, f"{key}.00") for key in range(1, objects + 1)], _WALLET)
    assert _sizes(plan) == sizes
    assert [key for step in plan_steps(plan) for key in _keys(step)] == list(range(1, objects + 1))
    for group in _groups(plan):
        assert len(group.steps) == len(group.writes)
        spans = [(span.start, span.stop) for span in group.effect_spans]
        assert spans == ([] if len(group.writes) == 1 else [(0, len(group.writes))])


def test_a_repeated_object_starts_the_next_group_however_far_below_the_bound() -> None:
    # Object 1 again after `_LIMIT - 1` writes: its group closes one short of
    # the bound, and the next fills to the bound before the rest. The writes
    # reach the planner as admitted, without admission coalescing the later
    # write of object 1 into the earlier one.
    keys = [*range(1, _LIMIT), 1, *range(_LIMIT, 2 * _LIMIT)]
    preparation = write_preparation_of(_WALLET)
    buffer = [
        unobserved_write(
            prepare_typed_write(_amend_wallet(key, f"{index}.00"), preparation), _WALLET
        )
        for index, key in enumerate(keys)
    ]
    plan = _finalize(buffer, _WALLET)
    assert _sizes(plan) == [_LIMIT - 1, _LIMIT, 1]
    assert [key for step in plan_steps(plan) for key in _keys(step)] == keys


def test_a_group_runs_every_writes_non_insert_steps_before_any_of_their_inserts() -> None:
    buffer = [
        KeyedWriteInstruction("amend", "Balance", ({"id": key, "value": Decimal("2.00")},))
        for key in (3, 1, 2)
    ]
    plan = _plan(buffer, _BALANCE, _observed(_BALANCE, buffer, _balance_observation))
    (group,) = _groups(plan)
    assert _kinds(group.steps) == ["non-insert"] * 3 + ["insert"] * 3
    assert [_keys(step) for step in group.steps] == [(3,), (1,), (2,)] * 2


def test_a_bitemporal_amendment_keeps_its_own_successors_in_order_behind_every_close() -> None:
    buffer = [
        KeyedWriteInstruction(
            "amend",
            "Position",
            ({"id": key, "value": Decimal("2.0")},),
            valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
        )
        for key in (7, 5)
    ]
    plan = _plan(
        buffer,
        _POSITION,
        _observed(_POSITION, buffer, _position_observation),
        instant=instant_at("2024-06-01T00:00:00+00:00"),
    )
    (group,) = _groups(plan)
    assert _kinds(group.steps) == ["non-insert"] * 2 + ["insert"] * 4
    assert [_keys(step) for step in group.steps] == [(7,), (5,), (7,), (7,), (5,), (5,)]
    heads = [step for step in group.steps[2:] if isinstance(step, PlannedInsert)]
    starts = [
        next(value for name, value in entry.row.attributes.items() if name.name == "validStart")
        for step in heads
        for entry in step.entries
    ]
    assert starts == [_JAN, dt.datetime(2024, 3, 1, tzinfo=dt.UTC)] * 2


@pytest.mark.parametrize(
    ("later", "sizes"), [(2, [1, 1]), (3, [2])], ids=["a-key-the-batch-holds", "another-key"]
)
def test_a_batch_brings_every_key_it_writes_to_the_distinct_object_check(
    later: int, sizes: list[int]
) -> None:
    # The first two rows collapse into one step over keys 1 and 2; the later
    # write assigns another member, so it is a step of its own. The writes
    # reach the planner as admitted, without admission coalescing the later
    # write of key 2 into the earlier one.
    buffer = [
        unobserved_write(prepare_typed_write(instruction, write_preparation_of(_WALLET)), _WALLET)
        for instruction in (
            _amend_wallet(1, "5.00"),
            _amend_wallet(2, "5.00"),
            KeyedWriteInstruction("amend", "Wallet", ({"id": later, "owner": "Z"},)),
        )
    ]
    plan = _finalize(buffer, _WALLET)
    assert _sizes(plan) == sizes
    batch, *_ = plan_steps(plan)
    assert _keys(batch) == (1, 2)


@pytest.mark.parametrize(
    ("later", "sizes"), [(2, [1, 1]), (3, [2])], ids=["a-key-the-batch-holds", "another-key"]
)
def test_an_insert_batch_brings_every_key_it_opens_to_the_distinct_object_check(
    later: int, sizes: list[int]
) -> None:
    # The two Dog inserts collapse into one step opening keys 1 and 2; a Cat of
    # the same family opening one of those keys writes that family's object
    # again, so the two cannot share a group, whichever ranks first.
    plan = _plan(
        [
            KeyedWriteInstruction("insert", "Dog", ({"id": 1, "name": "Rex"},)),
            KeyedWriteInstruction("insert", "Dog", ({"id": 2, "name": "Fido"},)),
            KeyedWriteInstruction("insert", "Cat", ({"id": later, "name": "Tom"},)),
        ],
        _ANIMAL,
    )
    assert _sizes(plan) == sizes
    (batch,) = (step for step in plan_steps(plan) if step.entity.name == "Dog")
    assert _keys(batch) == (1, 2)


def test_one_key_value_names_one_object_per_family_not_per_key_name() -> None:
    unrelated = _plan(
        [
            _amend_wallet(1, "5.00"),
            KeyedWriteInstruction("amend", "Account", ({"id": 1, "balance": Decimal("5.00")},)),
        ],
        _LEDGERS,
        {ObjectKey(_entity(_LEDGERS, "Account"), (("id", 1),)): VersionObservation(1)},
    )
    assert _sizes(unrelated) == [2]
    one_family = _plan(
        [
            KeyedWriteInstruction("amend", "Dog", ({"id": 1, "name": "Rex"},)),
            KeyedWriteInstruction("amend", "Cat", ({"id": 1, "name": "Tom"},)),
            KeyedWriteInstruction("amend", "Cat", ({"id": 2, "name": "Kit"},)),
        ],
        _ANIMAL,
    )
    assert _sizes(one_family) == [1, 2]


def test_a_write_with_no_step_joins_its_group_and_completes_with_it() -> None:
    buffer = [
        KeyedWriteInstruction("amend", "Balance", ({"id": 1, "value": Decimal("1.00")},)),
        KeyedWriteInstruction("amend", "Balance", ({"id": 2, "value": Decimal("2.00")},)),
    ]
    plan = _plan(
        buffer,
        _BALANCE,
        _observed(_BALANCE, buffer, _balance_observation),
        concurrency="locking",
    )
    (group,) = _groups(plan)
    assert len(group.writes) == 2
    assert [_keys(step) for step in group.steps] == [(2,), (2,)]


def test_a_deferred_write_is_an_entry_of_its_own_between_the_groups_around_it() -> None:
    def amend(key: int, month: int, year: int = 2024) -> KeyedWriteInstruction:
        return KeyedWriteInstruction(
            "amend",
            "Position",
            ({"id": key, "value": Decimal("2.0")},),
            valid_from=dt.datetime(year, month, 1, tzinfo=dt.UTC),
        )

    # The middle write's window starts before the milestone its source
    # observed, so it reads the rest of its coverage at execution.
    buffer = [amend(5, 3), amend(6, 3), amend(7, 6, 2023), amend(8, 3)]
    plan = _plan(
        buffer,
        _POSITION,
        _observed(_POSITION, buffer, _position_observation),
        instant=instant_at("2024-06-01T00:00:00+00:00"),
    )
    assert _sizes(plan) == [2, "deferred", 1]
    deferred = plan.entries[1]
    assert isinstance(deferred, SettledWrite)
    assert deferred.deferred is not None


def _entity(model: Metamodel, name: str) -> EntityIdentity:
    return next(entity.identity for entity in model.entities if entity.identity.name == name)


# --------------------------------------------------------------------------- #
# Acquisition spans over consecutive groups of deferred writes                #
# (`m-unit-work` *Shared coverage acquisition*).                              #
# --------------------------------------------------------------------------- #
def _spans(plan: WritePlan) -> list[tuple[int, int]]:
    return [(span.start, span.stop) for span in plan.acquisition_spans]


def _fragmented(*keys: int, entity: type[Bitemporal] = ShareCols) -> list[AdmittedWrite]:
    return [write for key in keys for write in frag(entity, key, 1)]


def _inside(key: int) -> AdmittedWrite:
    """A write of object ``key`` its observation covers, so it binds at planning."""
    observed = rectangle(ShareCols, key, 0, None, 0)
    prepared = prepare_wire_write(
        KeyedWriteInstruction(
            "amendUntil", ShareCols.identity.canonical, ({"id": key, "amount": 9},), day(0), day(1)
        ),
        write_preparation_of(SHARED_MODEL),
    )
    held = observation(ShareCols, observed)
    return admitted_write(prepared, held, held.key.object)


def _terminated(key: int) -> AdmittedWrite:
    """A termination of object ``key`` reaching past what it observed."""
    observed = frag_rows(ShareCols, key, 1)[0]
    prepared = prepare_wire_write(
        KeyedWriteInstruction(
            "terminateUntil", ShareCols.identity.canonical, ({"id": key},), day(0), day(2)
        ),
        write_preparation_of(SHARED_MODEL),
    )
    held = observation(ShareCols, observed)
    return admitted_write(prepared, held, held.key.object)


def test_a_plan_with_no_deferred_write_records_no_span() -> None:
    assert _spans(_plan([], _WALLET)) == []
    assert _spans(_plan([_amend_wallet(key, f"{key}.00") for key in (1, 2)], _WALLET)) == []
    assert _spans(shared_plan([_inside(1), _inside(2)])) == []


def _target(
    model: Metamodel,
    entity: str,
    key: int,
    verb: TargetMutation = "amend",
    valid_from: dt.datetime | None = None,
) -> AdmittedWrite:
    """An Optimistic target write of object ``key`` stating ``_JAN``, which
    reads its coverage at execution."""
    values: dict[str, object] = {"id": key} if verb == "terminate" else {"id": key, "amount": 5}
    if entity == "Balance":
        values = {"id": key} if verb == "terminate" else {"id": key, "value": "9.00"}
    return target_write(
        prepare_wire_write(
            TargetWriteInstruction(verb, entity, values, if_tx_start=_JAN, valid_from=valid_from),
            write_preparation_of(model),
        ),
        inheritance.inheritance_facet_of(model),
    )


def _transaction_time_targets(*keys: int, verb: TargetMutation = "amend") -> list[AdmittedWrite]:
    return [_target(_BALANCE, "Balance", key, verb) for key in keys]


def _bitemporal_plan(objects: int) -> WritePlan:
    return shared_plan(_fragmented(*range(1, objects + 1)))


def _transaction_time_plan(objects: int) -> WritePlan:
    targets = _transaction_time_targets(*range(1, objects + 1))
    return _finalize(admitted_writes(_BALANCE, targets), _BALANCE)


@pytest.mark.parametrize(
    "planned",
    [_bitemporal_plan, _transaction_time_plan],
    ids=["bitemporal", "transaction-time-only"],
)
@pytest.mark.parametrize(
    ("objects", "spans"),
    [
        (1, []),
        (2, [(0, 2)]),
        (31, [(0, 31)]),
        (32, [(0, 32)]),
        (33, [(0, 32)]),
        (65, [(0, 32), (32, 64)]),
        (66, [(0, 32), (32, 64), (64, 66)]),
        (67, [(0, 32), (32, 64), (64, 67)]),
    ],
)
def test_consecutive_deferred_writes_share_spans_of_at_most_32(
    planned: Callable[[int], WritePlan], objects: int, spans: list[tuple[int, int]]
) -> None:
    plan = planned(objects)
    # Every deferred write keeps its own entry, whatever span it belongs to.
    assert _sizes(plan) == ["deferred"] * objects
    assert _spans(plan) == spans


def test_a_span_never_skips_a_group_of_another_entity_or_a_write_bound_at_planning() -> None:
    another = shared_plan([*_fragmented(1), *_fragmented(1, entity=ShareDoc), *_fragmented(2, 3)])
    assert _sizes(another) == ["deferred"] * 4
    assert _spans(another) == [(2, 4)]
    planned = shared_plan([*_fragmented(1), _inside(4), *_fragmented(2, 3)])
    assert _sizes(planned) == ["deferred", 1, "deferred", "deferred"]
    assert _spans(planned) == [(2, 4)]


def test_a_transaction_time_only_span_never_skips_a_write_bound_at_planning() -> None:
    observed = KeyedWriteInstruction("amend", "Balance", ({"id": 4, "value": Decimal("2.00")},))
    buffer = [*_transaction_time_targets(1), observed, *_transaction_time_targets(2, 3)]
    plan = _finalize(
        observed_buffer(buffer, _BALANCE, _observed(_BALANCE, [observed], _balance_observation)),
        _BALANCE,
    )
    assert _sizes(plan) == ["deferred", 1, "deferred", "deferred"]
    assert _spans(plan) == [(2, 4)]


def test_deferred_writes_of_each_temporal_shape_form_spans_of_their_own() -> None:
    model = corpus_model("unchanged-milestone-layout-twin-columns")
    feb = dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
    buffer = [
        _target(model, "KeptLog", 1),
        _target(model, "KeptLog", 2),
        _target(model, "KeptSpan", 1, valid_from=feb),
        _target(model, "KeptSpan", 2, valid_from=feb),
    ]
    plan = _finalize(admitted_writes(model, buffer), model)
    assert _sizes(plan) == ["deferred"] * 4
    assert _spans(plan) == [(0, 2), (2, 4)]


@pytest.mark.parametrize(
    ("model", "deferred", "concurrency"),
    [
        (SHARED_MODEL, lambda: [*_fragmented(1, 2), _terminated(3), _terminated(4)], "optimistic"),
        (
            _BALANCE,
            lambda: [
                *_transaction_time_targets(1, 2),
                *_transaction_time_targets(3, 4, verb="terminate"),
            ],
            "locking",
        ),
    ],
    ids=["bitemporal", "transaction-time-only"],
)
def test_a_span_never_crosses_a_mutation_phase(
    model: Metamodel,
    deferred: Callable[[], list[AdmittedWrite]],
    concurrency: ConcurrencyPreference,
) -> None:
    plan = _finalize(admitted_writes(model, deferred()), model, concurrency=concurrency)
    assert _sizes(plan) == ["deferred"] * 4
    assert _spans(plan) == [(0, 2), (2, 4)]


def _terminations(*keys: int) -> list[AdmittedWrite]:
    return _transaction_time_targets(*keys, verb="terminate")


def test_an_optimistic_transaction_time_only_termination_settles_at_planning() -> None:
    plan = _finalize(_terminations(1, 2, 3), _BALANCE)
    (group,) = _groups(plan)
    assert _spans(plan) == []
    assert [type(step) for step in group.steps] == [PlannedClose] * 3
    assert [_keys(step) for step in group.steps] == [(1,), (2,), (3,)]
    for step in group.steps:
        assert isinstance(step, PlannedClose)
        assert step.cause == TERMINATED
        assert isinstance(step.concurrency, TemporalGate)
        assert step.concurrency.observed_start == _JAN
        assert step.affected_rows.on_shortfall == FAILED_PRECONDITION
    assert [(span.start, span.stop) for span in group.effect_spans] == [(0, 3)]


def test_optimistic_transaction_time_only_terminations_fill_groups_to_the_group_bound() -> None:
    plan = _finalize(_terminations(*range(1, _LIMIT + 2)), _BALANCE)
    assert _sizes(plan) == [_LIMIT, 1]
    assert [(span.start, span.stop) for span in _groups(plan)[0].effect_spans] == [(0, _LIMIT)]


def test_a_repeated_termination_target_starts_the_next_group() -> None:
    # Reaching the planner as admitted, the later termination of object 1 is
    # not composed into the earlier one.
    plan = _finalize(_terminations(1, 2, 1, 3), _BALANCE)
    assert _sizes(plan) == [2, 2]


@pytest.mark.parametrize(
    "deferred",
    [
        lambda: _finalize(_transaction_time_targets(1, 2), _BALANCE),
        lambda: _finalize(_terminations(1, 2), _BALANCE, concurrency="locking"),
        lambda: _finalize(
            [_target(_POSITION, "Position", key, "terminate", valid_from=_JAN) for key in (1, 2)],
            _POSITION,
        ),
    ],
    ids=["optimistic-amendments", "locking-terminations", "bitemporal-terminations"],
)
def test_a_target_needing_its_predecessors_cells_or_lock_still_defers(
    deferred: Callable[[], WritePlan],
) -> None:
    plan = deferred()
    assert _sizes(plan) == ["deferred"] * 2
    assert _spans(plan) == [(0, 2)]


def _candidate(key: int, *, shared_lock: bool = False, entity: str = "ShareCols") -> Any:
    identity = EntityIdentity("parallax.execution.shared", entity)
    key_attribute = AttributeIdentity(identity, "id")
    return settlement._AcquisitionCandidate(  # pyright: ignore[reportPrivateUsage] - the facts a span compares
        identity, key_attribute, shared_lock, (key_attribute, key)
    )


@pytest.mark.parametrize(
    ("later", "spans"),
    [
        (_candidate(2), [(0, 3)]),
        (_candidate(1), [(1, 3)]),
        (_candidate(2, shared_lock=True), []),
        (_candidate(2, entity="ShareDoc"), []),
        (None, []),
    ],
    ids=["compatible", "same-object", "another-lock", "another-entity", "reads-alone"],
)
def test_a_deferred_write_joins_the_open_span_only_where_it_reads_alike_another_object(
    later: Any, spans: list[tuple[int, int]]
) -> None:
    # Objects 1 and 3 read alike; ``later`` comes between them.
    extend = settlement._extend_run  # pyright: ignore[reportPrivateUsage] - the span's boundary rule
    recorded: list[AcquisitionSpan] = []
    run = extend(recorded, None, 0, _candidate(1))
    run = extend(recorded, run, 1, later)
    run = extend(recorded, run, 2, _candidate(3))
    settlement._close_run(recorded, run)  # pyright: ignore[reportPrivateUsage] - the span's boundary rule
    assert [(span.start, span.stop) for span in recorded] == spans


def test_only_a_deferred_write_reads_with_a_span() -> None:
    # Two parts' writes compose into one write naming the object's key.
    (item,) = admitted_writes(SHARED_MODEL, frag(ShareCols, 1, 2))
    assert isinstance(item, ComposedTemporalWrite)
    (write,) = shared_plan(frag(ShareCols, 1, 2)).entries
    assert isinstance(write, SettledWrite)
    candidate = settlement._acquisition_candidate  # pyright: ignore[reportPrivateUsage] - what a span compares
    families = inheritance.inheritance_facet_of(SHARED_MODEL)
    assert candidate(write, item, families) is not None
    # A settled write with no deferred range shares nothing.
    assert candidate(SettledWrite(), item, families) is None


def test_the_ready_writes_of_a_full_span_fit_one_write_group() -> None:
    # A span's ready writes execute as one group, which no span can overfill.
    ranges = settlement._WRITES_PER_SPAN  # pyright: ignore[reportPrivateUsage] - the span bound
    writes = settlement._WRITES_PER_GROUP  # pyright: ignore[reportPrivateUsage] - the group bound
    assert ranges <= writes


def test_a_group_lays_its_updates_out_shape_by_shape_and_records_their_spans() -> None:
    buffer = [
        _amend_wallet(1, "1.00"),
        KeyedWriteInstruction("amend", "Wallet", ({"id": 2, "owner": "Bo"},)),
        _amend_wallet(3, "3.00"),
        KeyedWriteInstruction("amend", "Wallet", ({"id": 4, "owner": "Di"},)),
        KeyedWriteInstruction(
            "amend", "Wallet", ({"id": 5, "owner": "Ed", "balance": Decimal("5")},)
        ),
    ]
    (group,) = _groups(_plan(buffer, _WALLET))
    assert [_keys(step) for step in group.steps] == [(1,), (3,), (2,), (4,), (5,)]
    assert [(span.start, span.stop) for span in group.effect_spans] == [(0, 2), (2, 4)]


def test_a_group_of_temporal_amendments_spans_their_closes_ahead_of_their_inserts() -> None:
    buffer = [
        KeyedWriteInstruction("amend", "Balance", ({"id": key, "value": Decimal("2.00")},))
        for key in (1, 2)
    ]
    (group,) = _groups(_plan(buffer, _BALANCE, _observed(_BALANCE, buffer, _balance_observation)))
    assert [type(step) for step in group.steps] == [PlannedClose] * 2 + [PlannedInsert] * 2
    (span,) = group.effect_spans
    assert (span.start, span.stop) == (0, 2)
