"""How settlement forms a flush's Write Groups (`m-unit-work` *Write Group
formation*): consecutive settled writes of one mutation phase over distinct
objects, at most 64 of them, laid out every effect before any insert."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal

import pytest

from parallax.core import MAX, Attr, DomainModel, Entity, TxTemporal, attr
from parallax.core import predicate as predicate_algebra
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._unit_work.instructions import prepare_typed_write
from parallax.core._execution._unit_work.write_items import CoalescedWrite
from parallax.core.base import INFINITY
from parallax.core.entity._model import model_of
from parallax.core.metamodel import EntityIdentity, Metamodel
from parallax.core.unit_work import (
    Concurrency,
    KeyedWriteInstruction,
    PredicateSelection,
    PredicateWriteInstruction,
    TransactionInstant,
    WriteAssignment,
    WritePlanningRequest,
    object_key,
)
from parallax.core.write_plan import (
    ObjectKey,
    PredecessorRow,
    TemporalObservation,
    VersionObservation,
    WriteObservation,
    WritePlan,
)
from parallax.core.write_plan.steps import (
    KeyTarget,
    MilestoneTarget,
    PlannedInsert,
    PlannedStep,
    PlannedUpdate,
)
from parallax.descriptor._records import Metamodel as DescriptorMetamodel
from tests._support.clock_probes import inert_instant, instant_at
from tests._support.planner_probes import TEST_ACTOR_IDENTITY, observed_buffer, plan_steps
from tests.unit._corpus_model_support import corpus_records, formed
from tests.unit._corpus_model_support import model as corpus_model

_MODELS = corpus_records()
_WALLET = corpus_model("wallet")
_BALANCE = corpus_model("balance")
_POSITION = corpus_model("position")
_ANIMAL = corpus_model("animal")
_LEDGERS = formed(
    DescriptorMetamodel(entities=(*_MODELS["wallet"].entities, *_MODELS["account"].entities))
)
_INSTANT = inert_instant()
_JAN = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


class Log(TxTemporal, table="wg_log", namespace="write.groups"):
    id: Attr[int] = attr(primary_key=MAX)
    amount: Attr[int]


class Tally(Entity, table="wg_tally", namespace="write.groups"):
    id: Attr[int] = attr(primary_key=MAX)
    amount: Attr[int]


_ALLOCATED = model_of(DomainModel(Log, Tally))


def _finalize(
    buffered: Sequence[CoalescedWrite],
    model: Metamodel,
    *,
    concurrency: Concurrency = "optimistic",
    instant: TransactionInstant = _INSTANT,
) -> WritePlan:
    return build_write_planner(model).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=instant,
            concurrency=concurrency,
            buffered_writes=buffered,
        )
    )


def _plan(
    buffer: Sequence[KeyedWriteInstruction | PredicateWriteInstruction],
    model: Metamodel,
    observations: Mapping[ObjectKey, WriteObservation] | None = None,
    *,
    concurrency: Concurrency = "optimistic",
    instant: TransactionInstant = _INSTANT,
) -> WritePlan:
    """``buffer`` admitted as a unit of work admits it, with ``observations``
    retained for the objects they name, and finalized."""
    return _finalize(
        observed_buffer(buffer, model, observations),
        model,
        concurrency=concurrency,
        instant=instant,
    )


def _sizes(plan: WritePlan) -> list[int]:
    return [len(group.writes) for group in plan.groups]


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
    return ["insert" if isinstance(step, PlannedInsert) else "effect" for step in steps]


def _balance_observation(key: int, value: str = "1.00") -> WriteObservation:
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


def _position_observation(key: int) -> WriteObservation:
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
    observe: Callable[[int], WriteObservation],
) -> dict[ObjectKey, WriteObservation]:
    """Each object ``buffer`` writes, observed as ``observe`` answers for its key."""
    observations: dict[ObjectKey, WriteObservation] = {}
    for instruction in buffer:
        key = object_key(instruction, model)
        assert key is not None
        ((_name, value),) = key.primary_key
        assert isinstance(value, int)
        observations[key] = observe(value)
    return observations


@pytest.mark.parametrize(
    ("objects", "sizes"),
    [(0, []), (1, [1]), (64, [64]), (65, [64, 1]), (130, [64, 64, 2])],
)
def test_writes_of_distinct_objects_share_groups_of_at_most_64(
    objects: int, sizes: list[int]
) -> None:
    # Distinct balances, so batching merges none of them into one step.
    plan = _plan([_amend_wallet(key, f"{key}.00") for key in range(1, objects + 1)], _WALLET)
    assert _sizes(plan) == sizes
    assert [key for step in plan_steps(plan) for key in _keys(step)] == list(range(1, objects + 1))
    for group in plan.groups:
        assert len(group.steps) == len(group.writes)


def test_a_group_runs_every_writes_effects_before_any_of_their_inserts() -> None:
    buffer = [
        KeyedWriteInstruction("amend", "Balance", ({"id": key, "value": Decimal("2.00")},))
        for key in (3, 1, 2)
    ]
    plan = _plan(buffer, _BALANCE, _observed(_BALANCE, buffer, _balance_observation))
    (group,) = plan.groups
    assert _kinds(group.steps) == ["effect"] * 3 + ["insert"] * 3
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
    (group,) = plan.groups
    assert _kinds(group.steps) == ["effect", "effect", "insert", "insert", "insert", "insert"]
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
    # write assigns another member, so it is a step of its own.
    buffer = [
        prepare_typed_write(instruction, _WALLET)
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
    (group,) = plan.groups
    assert len(group.writes) == 2
    assert [_keys(step) for step in group.steps] == [(2,), (2,)]


def test_a_deferred_write_stands_alone_between_the_groups_around_it() -> None:
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
    assert _sizes(plan) == [2, 1, 1]
    (deferred,) = plan.groups[1].writes
    assert deferred.deferred is not None
    assert plan.groups[1].steps == ()


@pytest.mark.parametrize(
    ("entity", "allocates"), [(Log, True), (Tally, False)], ids=["allocated", "computed"]
)
def test_an_insert_whose_key_the_database_decides_stands_alone(
    entity: type[Entity], allocates: bool
) -> None:
    computed = prepare_typed_write(
        KeyedWriteInstruction(
            "insert", entity.identity.canonical, ({"id": {"computed": "maxPlusOne"}, "amount": 1},)
        ),
        _ALLOCATED,
    )
    plan = _finalize([computed, computed], _ALLOCATED, instant=instant_at("2024-01-10T00:00:00Z"))
    assert _sizes(plan) == [1, 1]
    assert all(bool(group.writes[0].opened.allocated) is allocates for group in plan.groups)


def test_a_readless_predicate_write_is_a_group_of_its_own_no_group_crosses() -> None:
    predicate = PredicateWriteInstruction(
        "amend",
        PredicateSelection(
            "Wallet",
            predicate_algebra.Comparison("eq", predicate_algebra.FieldSubject("Wallet.id"), 9),
        ),
        assignments=(WriteAssignment("Wallet.owner", "Z"),),
    )
    plan = _plan(
        [_amend_wallet(1, "1.00"), _amend_wallet(2, "2.00"), predicate, _amend_wallet(3, "3.00")],
        _WALLET,
    )
    assert _sizes(plan) == [2, 1, 1]


def _entity(model: Metamodel, name: str) -> EntityIdentity:
    return next(entity.identity for entity in model.entities if entity.identity.name == name)
