"""The Write Plan's own contract (m-write-plan values, `m-unit-work` *Write Plan
and Planned Steps*).

A Write Group holds at least one write. A group laid out from its members runs
every non-insert step before any insert. An attempt that opened nothing owns
nothing, and holds nothing for any source to continue from.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterator, Mapping

import pytest

from parallax.core.internal.metamodel import AttributeIdentity
from parallax.core.internal.write_plan import PlannedInsert
from parallax.core.internal.write_plan.keys import ObjectKey, VersionedObjectStateKey
from parallax.core.internal.write_plan.plan import (
    NO_TEMPORAL_WRITE_OWNERSHIP,
    OPEN_BITEMPORAL_ENDS,
    BoundRange,
    EffectSpan,
    SettledWrite,
    TemporalRowCoordinates,
    WriteEffects,
    WriteGroup,
)
from parallax.core.internal.write_plan.steps import (
    MISSING_TARGET,
    NEW_LINEAGE,
    UNVERSIONED,
    ExactCount,
    KeyTarget,
    PlannedDelete,
    PlannedStep,
    WriteRow,
)
from tests._support.managed_rows import managed_row_of
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._corpus_model_support import target as entity_of

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
        WriteGroup.from_members((), effect_shape=_unshaped)


def test_an_attempt_that_opened_nothing_owns_nothing_an_insertion_opened() -> None:
    coordinates = TemporalRowCoordinates(_ACCOUNT, (1,), OPEN_BITEMPORAL_ENDS)
    assert not NO_TEMPORAL_WRITE_OWNERSHIP.owns(coordinates)
    assert not NO_TEMPORAL_WRITE_OWNERSHIP.continues_insertion(coordinates)
    assert NO_TEMPORAL_WRITE_OWNERSHIP.insertion_coverage(coordinates, None) == ()


def test_an_attempt_that_opened_nothing_holds_nothing_for_a_source_to_continue() -> None:
    coordinates = TemporalRowCoordinates(_ACCOUNT, (1,), OPEN_BITEMPORAL_ENDS)
    target = ObjectKey(_ACCOUNT, (("id", 1),))
    state = VersionedObjectStateKey(target, 1)
    assert not NO_TEMPORAL_WRITE_OWNERSHIP.demanded(state, coordinates)
    assert NO_TEMPORAL_WRITE_OWNERSHIP.continues(object(), None) is None
    assert tuple(NO_TEMPORAL_WRITE_OWNERSHIP.current_rows(target, None)) == ()


def _delete(key: int) -> PlannedDelete:
    return PlannedDelete(
        entity=_ACCOUNT,
        target=KeyTarget(key_attributes=(_ID,), key_values=((key,),)),
        concurrency=UNVERSIONED,
        affected_rows=ExactCount(expected=1, on_shortfall=MISSING_TARGET),
    )


def test_one_member_keeps_its_own_steps_tuple() -> None:
    write = BoundRange(steps=(_delete(1), _insert(1)))
    group = WriteGroup.from_members(iter([(write, write.steps)]), effect_shape=_unshaped)
    assert group.writes == (write,)
    assert group.steps is write.steps


def test_members_run_every_non_insert_step_before_any_insert_each_in_member_order() -> None:
    first = (_delete(1), _insert(1), _insert(2))
    second = (_delete(2), _delete(3), _insert(3))
    third = (_insert(4),)
    writes = (SettledWrite(), BoundRange(steps=second), SettledWrite())
    group = WriteGroup.from_members(
        zip(writes, (first, second, third), strict=True), effect_shape=_unshaped
    )
    assert group.writes == writes
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


def test_a_member_without_steps_completes_with_its_group() -> None:
    writes = (SettledWrite(), SettledWrite())
    group = WriteGroup.from_members(
        zip(writes, ((), (_insert(1),)), strict=True), effect_shape=_unshaped
    )
    assert group.writes == writes
    assert len(group.steps) == 1


class _Refused(Exception):
    pass


def test_a_second_member_is_asked_for_only_once_the_first_is_taken() -> None:
    asked: list[int] = []

    def members() -> Iterator[tuple[WriteEffects, tuple[PlannedStep, ...]]]:
        for key in (1, 2):
            asked.append(key)
            yield SettledWrite(), (_insert(key),)
            assert asked == [1, 2][: len(asked)]

    group = WriteGroup.from_members(members(), effect_shape=_unshaped)
    assert asked == [1, 2]
    assert len(group.writes) == 2


def test_a_failing_producer_leaves_no_group_and_its_failure_intact() -> None:
    failure = _Refused()

    def members() -> Iterator[tuple[WriteEffects, tuple[PlannedStep, ...]]]:
        yield SettledWrite(), (_insert(1),)
        yield SettledWrite(), (_insert(2),)
        raise failure

    with pytest.raises(_Refused) as raised:
        WriteGroup.from_members(members(), effect_shape=_unshaped)
    assert raised.value is failure


def test_a_failure_taking_a_member_closes_the_suspended_producer() -> None:
    closed: list[bool] = []

    def members() -> Iterator[tuple[WriteEffects, tuple[PlannedStep, ...]]]:
        try:
            yield SettledWrite(), (_insert(1),)
            yield SettledWrite(), 0  # type: ignore[misc] - a member whose steps cannot be laid out
            yield SettledWrite(), (_insert(3),)
        finally:
            closed.append(True)

    with pytest.raises(TypeError):
        WriteGroup.from_members(members(), effect_shape=_unshaped)
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
    writes = tuple(SettledWrite() for _ in effects)
    group = WriteGroup.from_members(
        zip(writes, ((effect,) for effect in effects), strict=True),
        effect_shape=_shaped({1: "X", 2: "X", 3: "Y", 4: "X", 5: "Y"}),
    )
    assert _keys(group.steps) == [1, 2, 4, 3, 5]
    assert group.effect_spans == (EffectSpan(0, 3, "X"), EffectSpan(3, 5, "Y"))


def test_an_unshaped_effect_is_a_barrier_no_later_effect_joins_across() -> None:
    effects = [_delete(key) for key in (1, 2, 3)]
    group = WriteGroup.from_members(
        zip((SettledWrite(), SettledWrite(), SettledWrite()), ((e,) for e in effects), strict=True),
        effect_shape=_shaped({1: "X", 3: "X"}),
    )
    assert _keys(group.steps) == [1, 2, 3]
    assert group.effect_spans == ()


def test_an_effect_never_runs_ahead_of_its_own_writes_earlier_effect() -> None:
    first = (_delete(1),)
    second = (_delete(2), _delete(3))
    third = (_delete(4),)
    group = WriteGroup.from_members(
        zip((SettledWrite(), SettledWrite(), SettledWrite()), (first, second, third), strict=True),
        effect_shape=_shaped({1: "X", 2: "Y", 3: "X", 4: "X"}),
    )
    assert _keys(group.steps) == [1, 2, 3, 4]
    assert group.effect_spans == (EffectSpan(2, 4, "X"),)


def test_one_write_may_join_one_block_with_several_effects_of_its_shape() -> None:
    first = (_delete(1),)
    second = (_delete(2), _delete(3))
    group = WriteGroup.from_members(
        zip((SettledWrite(), SettledWrite()), (first, second), strict=True),
        effect_shape=_shaped({1: "X", 2: "X", 3: "X"}),
    )
    assert _keys(group.steps) == [1, 2, 3]
    assert group.effect_spans == (EffectSpan(0, 3, "X"),)


def test_a_single_member_keeps_its_steps_and_forms_no_effect_span() -> None:
    write = BoundRange(steps=(_delete(1), _delete(2)))
    group = WriteGroup.from_members(
        iter([(write, write.steps)]), effect_shape=_shaped({1: "X", 2: "X"})
    )
    assert group.steps is write.steps
    assert group.effect_spans == ()


def test_inserts_follow_every_grouped_effect_in_member_order() -> None:
    first = (_delete(1), _insert(1))
    second = (_delete(2), _insert(2))
    group = WriteGroup.from_members(
        zip((SettledWrite(), SettledWrite()), (first, second), strict=True),
        effect_shape=_shaped({1: "X", 2: "X"}),
    )
    assert group.steps == (first[0], second[0], first[1], second[1])
    assert group.effect_spans == (EffectSpan(0, 2, "X"),)


def test_a_failing_effect_shape_closes_the_suspended_producer() -> None:
    closed: list[bool] = []
    failure = _Refused()

    def shape(step: PlannedStep) -> Hashable | None:
        raise failure

    def members() -> Iterator[tuple[WriteEffects, tuple[PlannedStep, ...]]]:
        try:
            yield SettledWrite(), (_delete(1),)
            yield SettledWrite(), (_delete(2),)
            yield SettledWrite(), (_delete(3),)
        finally:
            closed.append(True)

    with pytest.raises(_Refused) as raised:
        WriteGroup.from_members(members(), effect_shape=shape)
    assert raised.value is failure
    assert closed == [True]


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
        WriteGroup((SettledWrite(),), steps, spans)
