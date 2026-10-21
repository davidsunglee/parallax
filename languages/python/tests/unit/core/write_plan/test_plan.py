"""The Write Plan's own contract (m-write-plan values, `m-unit-work` *Write Plan
and Planned Steps*).

A plan of no Write Group is the one canonical result for a flush that survives
nothing. Each Write Group owns the tuple of its Planned Steps and the settled
writes it completes, and holds at least one; a deferred settled write's group
plans no step. An attempt that opened nothing owns nothing, and holds nothing
for any source to continue from.
"""

from __future__ import annotations

import dataclasses

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
    WriteCompletion,
    WriteGroup,
)
from parallax.core.write_plan.steps import NEW_LINEAGE, PlannedRow, WriteRow
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
    assert plan.groups == ()
    assert plan == WritePlan(())


def test_a_write_group_owns_its_steps_and_settled_writes_in_execution_order() -> None:
    steps = (_insert(1), _insert(2))
    writes = (SettledWrite(), SettledWrite())
    group = WriteGroup(writes, steps)
    plan = WritePlan((group,))
    assert plan.groups[0] is group
    assert group.steps is steps
    assert group.writes is writes


def test_a_write_group_holds_at_least_one_settled_write() -> None:
    with pytest.raises(ValueError, match="at least one settled write"):
        WriteGroup((), (_insert(1),))


class _Deferred(DeferredRange):
    __slots__ = ()


def test_a_deferred_settled_writes_group_plans_no_step() -> None:
    deferred = SettledWrite(deferred=_Deferred())
    plan = WritePlan(
        (
            WriteGroup((SettledWrite(),), (_insert(1),)),
            WriteGroup((deferred,), ()),
            WriteGroup((SettledWrite(),), (_insert(2),)),
        )
    )
    assert [len(group.steps) for group in plan.groups] == [1, 0, 1]
    assert plan.groups[1].writes == (deferred,)


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
    result: type[WriteCompletion],
) -> None:
    assert issubclass(result, WriteCompletion)
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
        isinstance(getattr(write, field.name), WriteCompletion)
        for field in dataclasses.fields(write)
    )
    assert write.deferred is None
