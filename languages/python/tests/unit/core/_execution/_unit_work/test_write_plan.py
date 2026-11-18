"""The Write Plan's own contract (`m-unit-work` *Write Plan and Planned Steps*).

A settled write carries its steps and every effect it publishes. A Write Group
holds at least one write, and one laid out from several runs every non-insert
step before any insert.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterator, Mapping, Sequence
from typing import cast

import pytest

from parallax.core._execution._unit_work import write_plan as plan_module
from parallax.core._execution._unit_work.write_plan import SettledWrite, WriteGroup
from parallax.core.internal.metamodel import AttributeIdentity
from parallax.core.internal.planned_step import PlannedInsert
from parallax.core.internal.planned_step.keys import ObjectKey, VersionedObjectStateKey
from parallax.core.internal.planned_step.steps import (
    MISSING_TARGET,
    NEW_LINEAGE,
    UNVERSIONED,
    ExactCount,
    KeyTarget,
    PlannedDelete,
    PlannedStep,
    WriteRow,
)
from parallax.core.internal.planned_step.write_effects import (
    BoundRange,
    CurrentRowOutput,
    Derivation,
    EffectSpan,
    Openings,
    TemporalRowCoordinates,
)
from tests._support.managed_rows import managed_row_of
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._corpus_model_support import target as entity_of
from tests.unit.core._execution._reach_support import frames, reaches

_ACCOUNT_MODEL = corpus_model("account")
_ACCOUNT = entity_of(_ACCOUNT_MODEL, "Account").identity
_ID = AttributeIdentity(_ACCOUNT, "id")


def _unshaped(step: PlannedStep) -> Hashable | None:
    del step
    return None


def _insert(key: int) -> PlannedInsert:
    return PlannedInsert(
        entity=_ACCOUNT,
        entries=(WriteRow(row=managed_row_of(_ACCOUNT_MODEL, {_ID: key}), origin=NEW_LINEAGE),),
    )


def test_a_write_group_holds_at_least_one_settled_write() -> None:
    with pytest.raises(ValueError, match="at least one write"):
        WriteGroup((), (_insert(1),))
    with pytest.raises(ValueError, match="at least one write"):
        WriteGroup.from_writes((), effect_shape=_unshaped)


def test_a_settled_write_from_its_bound_range_keeps_every_effect_and_its_steps() -> None:
    key = ObjectKey(_ACCOUNT, (("id", 1),))
    state = VersionedObjectStateKey(key, 3)
    bound = BoundRange(
        steps=(_delete(1),),
        changed=(state,),
        advanced=(state,),
        destroyed=(key,),
        # Settling carries each effect as it is, so opaque ones stand in.
        removed=cast("tuple[TemporalRowCoordinates, ...]", (object(),)),
        opened=Openings(fresh=cast("tuple[TemporalRowCoordinates, ...]", (object(),))),
        derived=cast("tuple[Derivation, ...]", (object(),)),
        current_outputs=cast("tuple[CurrentRowOutput, ...]", (object(),)),
    )
    evidence = (object(),)
    write = SettledWrite.from_bound(bound, source_evidence=evidence)
    assert write.steps is bound.steps
    assert write.source_evidence is evidence
    for name in (
        "changed",
        "advanced",
        "destroyed",
        "removed",
        "opened",
        "derived",
        "current_outputs",
    ):
        assert getattr(write, name) is getattr(bound, name), name
    assert type(write) is SettledWrite


def _delete(key: int) -> PlannedDelete:
    return PlannedDelete(
        entity=_ACCOUNT,
        target=KeyTarget(key_attributes=(_ID,), key_values=((key,),)),
        concurrency=UNVERSIONED,
        affected_rows=ExactCount(expected=1, on_shortfall=MISSING_TARGET),
    )


def test_one_write_keeps_its_own_steps_tuple() -> None:
    write = SettledWrite(steps=(_delete(1), _insert(1)))
    group = WriteGroup.from_writes(iter([write]), effect_shape=_unshaped)
    assert group.writes == (write,)
    assert group.steps is write.steps


def test_writes_run_every_non_insert_step_before_any_insert_each_in_write_order() -> None:
    first = (_delete(1), _insert(1), _insert(2))
    second = (_delete(2), _delete(3), _insert(3))
    third = (_insert(4),)
    writes = tuple(SettledWrite(steps=steps) for steps in (first, second, third))
    group = WriteGroup.from_writes(writes, effect_shape=_unshaped)
    assert all(laid is write for laid, write in zip(group.writes, writes, strict=True))
    assert group.steps == (
        first[0],
        second[0],
        second[1],
        first[1],
        first[2],
        second[2],
        third[0],
    )
    assert all(
        laid is original
        for laid, original in zip(
            group.steps, (*first[:1], *second[:2], *first[1:], second[2], *third), strict=True
        )
    )


def test_a_write_without_steps_completes_with_its_group() -> None:
    writes = (SettledWrite(steps=()), SettledWrite(steps=(_insert(1),)))
    group = WriteGroup.from_writes(writes, effect_shape=_unshaped)
    assert group.writes == writes
    assert len(group.steps) == 1


class _Refused(Exception):
    pass


def _pulled(keys: Sequence[int], events: list[tuple[str, object]]) -> Iterator[SettledWrite]:
    for key in keys:
        events.append(("pull", key))
        yield SettledWrite(steps=(_delete(key),))


def _laid_out(events: list[tuple[str, object]]) -> Callable[[PlannedStep], Hashable | None]:
    def shape(step: PlannedStep) -> Hashable | None:
        events.append(("lay out", _key(step)))
        return None

    return shape


def test_each_write_after_the_second_is_asked_for_only_once_the_one_before_is_laid_out() -> None:
    events: list[tuple[str, object]] = []
    group = WriteGroup.from_writes(_pulled((1, 2, 3), events), effect_shape=_laid_out(events))
    assert events == [
        ("pull", 1),
        ("pull", 2),
        ("lay out", 1),
        ("lay out", 2),
        ("pull", 3),
        ("lay out", 3),
    ]
    assert len(group.writes) == 3


def test_a_failing_producer_leaves_no_group_and_its_failure_intact() -> None:
    failure = _Refused()

    def writes() -> Iterator[SettledWrite]:
        yield SettledWrite(steps=(_insert(1),))
        yield SettledWrite(steps=(_insert(2),))
        raise failure

    with pytest.raises(_Refused) as raised:
        WriteGroup.from_writes(writes(), effect_shape=_unshaped)
    assert raised.value is failure


def test_a_failure_taking_a_write_closes_the_suspended_producer_before_its_next_write() -> None:
    produced: list[int] = []
    closed: list[bool] = []

    def writes() -> Iterator[SettledWrite]:
        try:
            produced.append(1)
            yield SettledWrite(steps=(_insert(1),))
            produced.append(2)
            yield SettledWrite(steps=cast("tuple[PlannedStep, ...]", 0))  # steps no layout reads
            produced.append(3)
            yield SettledWrite(steps=(_insert(3),))
        finally:
            closed.append(True)

    with pytest.raises(TypeError):
        WriteGroup.from_writes(writes(), effect_shape=_unshaped)
    assert produced == [1, 2]
    assert closed == [True]


def _key(step: PlannedStep) -> object:
    if not isinstance(step, PlannedDelete):
        return "insert"
    target = step.target
    assert isinstance(target, KeyTarget)
    return target.key_values[0][0]


def _shaped(shapes: Mapping[object, str]) -> Callable[[PlannedStep], Hashable | None]:
    def shape(step: PlannedStep) -> Hashable | None:
        return shapes.get(_key(step))

    return shape


def _keys(steps: tuple[PlannedStep, ...]) -> list[object]:
    return [_key(step) for step in steps]


def test_interleaved_effects_lay_out_shape_by_shape_in_first_appearance_order() -> None:
    effects = [_delete(key) for key in (1, 2, 3, 4, 5)]
    group = WriteGroup.from_writes(
        (SettledWrite(steps=(effect,)) for effect in effects),
        effect_shape=_shaped({1: "X", 2: "X", 3: "Y", 4: "X", 5: "Y"}),
    )
    assert _keys(group.steps) == [1, 2, 4, 3, 5]
    assert group.effect_spans == (EffectSpan(0, 3, "X"), EffectSpan(3, 5, "Y"))


def test_an_unshaped_effect_is_a_barrier_no_later_effect_joins_across() -> None:
    effects = [_delete(key) for key in (1, 2, 3)]
    group = WriteGroup.from_writes(
        (SettledWrite(steps=(effect,)) for effect in effects),
        effect_shape=_shaped({1: "X", 3: "X"}),
    )
    assert _keys(group.steps) == [1, 2, 3]
    assert group.effect_spans == ()


def test_an_effect_never_runs_ahead_of_its_own_writes_earlier_effect() -> None:
    first = (_delete(1),)
    second = (_delete(2), _delete(3))
    third = (_delete(4),)
    group = WriteGroup.from_writes(
        (SettledWrite(steps=steps) for steps in (first, second, third)),
        effect_shape=_shaped({1: "X", 2: "Y", 3: "X", 4: "X"}),
    )
    assert _keys(group.steps) == [1, 2, 3, 4]
    assert group.effect_spans == (EffectSpan(2, 4, "X"),)


def test_one_write_may_join_one_block_with_several_effects_of_its_shape() -> None:
    first = (_delete(1),)
    second = (_delete(2), _delete(3))
    group = WriteGroup.from_writes(
        (SettledWrite(steps=steps) for steps in (first, second)),
        effect_shape=_shaped({1: "X", 2: "X", 3: "X"}),
    )
    assert _keys(group.steps) == [1, 2, 3]
    assert group.effect_spans == (EffectSpan(0, 3, "X"),)


def test_a_single_write_keeps_its_steps_and_forms_no_effect_span() -> None:
    write = SettledWrite(steps=(_delete(1), _delete(2)))
    group = WriteGroup.from_writes(iter([write]), effect_shape=_shaped({1: "X", 2: "X"}))
    assert group.steps is write.steps
    assert group.effect_spans == ()


def test_inserts_follow_every_grouped_effect_in_write_order() -> None:
    first = (_delete(1), _insert(1))
    second = (_delete(2), _insert(2))
    group = WriteGroup.from_writes(
        (SettledWrite(steps=steps) for steps in (first, second)),
        effect_shape=_shaped({1: "X", 2: "X"}),
    )
    assert group.steps == (first[0], second[0], first[1], second[1])
    assert group.effect_spans == (EffectSpan(0, 2, "X"),)


def _refusing(key: object, failure: BaseException) -> Callable[[PlannedStep], Hashable | None]:
    def shape(step: PlannedStep) -> Hashable | None:
        if _key(step) == key:
            raise failure
        return None

    return shape


def test_a_failing_effect_shape_closes_the_suspended_producer_before_its_next_write() -> None:
    produced: list[int] = []
    closed: list[bool] = []
    failure = _Refused()

    def writes() -> Iterator[SettledWrite]:
        try:
            for key in (1, 2, 3):
                produced.append(key)
                yield SettledWrite(steps=(_delete(key),))
        finally:
            closed.append(True)

    with pytest.raises(_Refused) as raised:
        WriteGroup.from_writes(writes(), effect_shape=_refusing(1, failure))
    assert raised.value is failure
    assert produced == [1, 2]
    assert closed == [True]


def test_a_failing_effect_shape_leaves_no_frame_holding_a_write_it_took() -> None:
    taken = [SettledWrite(steps=(_delete(key),), source_evidence=(object(),)) for key in (1, 2, 3)]
    with pytest.raises(_Refused) as raised:
        WriteGroup.from_writes(iter(taken), effect_shape=_refusing(2, _Refused()))
    assembling = frames(raised.value.__traceback__, module=plan_module.__file__)
    assert {frame.f_code.co_name for frame in assembling} == {"from_writes", "add"}
    for write in taken[:2]:
        assert not reaches(assembling, write)
        assert not reaches(assembling, write.steps)
        assert not reaches(assembling, write.source_evidence)


@pytest.mark.parametrize(
    "spans",
    [
        (EffectSpan(0, 1, "X"),),
        (EffectSpan(1, 4, "X"),),
        (EffectSpan(0, 2, "X"), EffectSpan(1, 3, "Y")),
        (EffectSpan(1, 3, "X"), EffectSpan(0, 1, "Y")),
    ],
)
def test_effect_spans_hold_two_or_more_steps_in_order_without_overlap(
    spans: tuple[EffectSpan, ...],
) -> None:
    steps = (_delete(1), _delete(2), _delete(3))
    with pytest.raises(ValueError, match="effect spans"):
        WriteGroup((SettledWrite(steps=steps),), steps, spans)
