"""The Write Plan's own contract (m-write-plan values, `m-unit-work` *Write Plan
and Planned Steps*).

A plan of no entry is the one canonical result for a flush that survives
nothing. Each Write Group owns the tuple of its Planned Steps and the writes it
completes, and holds at least one; a deferred settled write is an entry of its
own, with no step. A group laid out from its members runs every non-insert step
before any insert. An attempt that opened nothing owns nothing, and holds
nothing for any source to continue from.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator

import pytest

from parallax.core.metamodel import AttributeIdentity
from parallax.core.write_plan import PlannedInsert, WritePlan
from parallax.core.write_plan.keys import ObjectKey, VersionedObjectStateKey
from parallax.core.write_plan.plan import (
    NO_OPENINGS,
    NO_TEMPORAL_WRITE_OWNERSHIP,
    OPEN_BITEMPORAL_ENDS,
    BoundRange,
    DeferredRange,
    SettledWrite,
    TemporalRowCoordinates,
    WriteEffects,
    WriteGroup,
)
from parallax.core.write_plan.steps import (
    MISSING_TARGET,
    NEW_LINEAGE,
    UNVERSIONED,
    ExactCount,
    KeyTarget,
    PlannedDelete,
    PlannedRow,
    PlannedStep,
    WriteRow,
)
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._corpus_model_support import target as entity_of

_ACCOUNT = entity_of(corpus_model("account"), "Account").identity
_ID = AttributeIdentity(_ACCOUNT, "id")


def _insert(key: int) -> PlannedInsert:
    return PlannedInsert(
        entity=_ACCOUNT,
        entries=(WriteRow(row=PlannedRow(attributes={_ID: key}), origin=NEW_LINEAGE),),
    )


def test_an_empty_write_plan_is_the_canonical_cancelled_result() -> None:
    plan = WritePlan()
    assert plan.entries == ()
    assert plan == WritePlan(())


def test_a_write_group_owns_its_steps_and_settled_writes_in_execution_order() -> None:
    steps = (_insert(1), _insert(2))
    writes = (SettledWrite(), SettledWrite())
    group = WriteGroup(writes, steps)
    plan = WritePlan((group,))
    assert plan.entries[0] is group
    assert group.steps is steps
    assert group.writes is writes


def test_a_write_group_holds_at_least_one_settled_write() -> None:
    with pytest.raises(ValueError, match="at least one write"):
        WriteGroup((), (_insert(1),))
    with pytest.raises(ValueError, match="at least one write"):
        WriteGroup.from_members(())


class _Deferred(DeferredRange):
    __slots__ = ()


def test_a_deferred_settled_write_is_an_entry_of_its_own_between_groups() -> None:
    deferred = SettledWrite(deferred=_Deferred())
    plan = WritePlan(
        (
            WriteGroup((SettledWrite(),), (_insert(1),)),
            deferred,
            WriteGroup((SettledWrite(),), (_insert(2),)),
        )
    )
    assert plan.entries[1] is deferred
    assert [type(entry) for entry in plan.entries] == [WriteGroup, SettledWrite, WriteGroup]


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


_EFFECTS = (
    "changed",
    "advanced",
    "destroyed",
    "removed",
    "opened",
    "derived",
    "current_outputs",
)


@pytest.mark.parametrize("result", [SettledWrite, BoundRange])
def test_every_result_extends_the_one_flat_effects_vocabulary(
    result: type[WriteEffects],
) -> None:
    assert issubclass(result, WriteEffects)
    names = [field.name for field in dataclasses.fields(result)]
    assert names[: len(_EFFECTS)] == list(_EFFECTS)
    assert all(field.kw_only for field in dataclasses.fields(result))
    with pytest.raises(TypeError):
        result(0)  # type: ignore[call-arg]


def test_plan_values_are_held_in_slots_on_themselves() -> None:
    write = SettledWrite()
    group = WriteGroup((write,), ())
    for value in (write, BoundRange(steps=()), group, WritePlan((group,))):
        assert not hasattr(value, "__dict__")


def test_a_settled_write_publishes_nothing_it_does_not_name() -> None:
    write = SettledWrite()
    assert [getattr(write, name) for name in _EFFECTS] == [(), (), (), (), NO_OPENINGS, (), ()]
    assert not any(
        isinstance(getattr(write, field.name), WriteEffects) for field in dataclasses.fields(write)
    )
    assert write.deferred is None


def test_a_source_free_settled_write_shares_the_empty_evidence_tuple() -> None:
    shared: tuple[()] = ()
    assert SettledWrite().source_evidence is shared
    assert SettledWrite(deferred=_Deferred()).source_evidence is shared


def test_a_settled_write_holds_the_evidence_tuple_it_is_given() -> None:
    evidence = (object(), object())
    assert SettledWrite(source_evidence=evidence).source_evidence is evidence
    assert SettledWrite(source_evidence=evidence, deferred=_Deferred()).source_evidence is evidence


def _delete(key: int) -> PlannedDelete:
    return PlannedDelete(
        entity=_ACCOUNT,
        target=KeyTarget(key_attributes=(_ID,), key_values=((key,),)),
        concurrency=UNVERSIONED,
        affected_rows=ExactCount(expected=1, on_shortfall=MISSING_TARGET),
    )


def test_one_member_keeps_its_own_steps_tuple() -> None:
    write = BoundRange(steps=(_delete(1), _insert(1)))
    group = WriteGroup.from_members(iter([(write, write.steps)]))
    assert group.writes == (write,)
    assert group.steps is write.steps


def test_members_run_every_non_insert_step_before_any_insert_each_in_member_order() -> None:
    first = (_delete(1), _insert(1), _insert(2))
    second = (_delete(2), _delete(3), _insert(3))
    third = (_insert(4),)
    writes = (SettledWrite(), BoundRange(steps=second), SettledWrite())
    group = WriteGroup.from_members(zip(writes, (first, second, third), strict=True))
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
    group = WriteGroup.from_members(zip(writes, ((), (_insert(1),)), strict=True))
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

    group = WriteGroup.from_members(members())
    assert asked == [1, 2]
    assert len(group.writes) == 2


def test_a_failing_producer_leaves_no_group_and_its_failure_intact() -> None:
    failure = _Refused()

    def members() -> Iterator[tuple[WriteEffects, tuple[PlannedStep, ...]]]:
        yield SettledWrite(), (_insert(1),)
        yield SettledWrite(), (_insert(2),)
        raise failure

    with pytest.raises(_Refused) as raised:
        WriteGroup.from_members(members())
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
        WriteGroup.from_members(members())
    assert closed == [True]
