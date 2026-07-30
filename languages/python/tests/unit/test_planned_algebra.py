"""Construction invariants of the finalized Planned Write algebra (m-unit-work).

A Planned Write is what SQL lowering receives with every semantic question
already settled, so the shapes that would leave one unsettled must be
unconstructible rather than merely unusual: an insert with no entries, an entry
row naming no member, and entries of one step disagreeing about which members or
which generated-value cells they carry. These are pure value-type tests — no
metamodel, no dialect, no SQL — pinned against synthetic identities so the
invariant, not a corpus model, is what fails them.

The Write Plan's own contract is here too: an empty Planned Steps is the one
canonical result for a flush that survives nothing, and Planned Steps is a
logical sequence whose views compare by value rather than by object identity.
"""

from __future__ import annotations

import pytest

from parallax.core.metamodel import AttributeIdentity, EntityIdentity, ValueObjectIdentity
from parallax.core.unit_work import (
    MAX_PLUS_ONE,
    NEW_LINEAGE,
    InsertEntry,
    PlannedInsert,
    PlannedRow,
    PlannedSteps,
    WritePlan,
)

_ACCOUNT = EntityIdentity(None, "Account")
_ID = AttributeIdentity(_ACCOUNT, "id")
_OWNER = AttributeIdentity(_ACCOUNT, "owner")
_ADDRESS = ValueObjectIdentity(_ACCOUNT, ("address",))


def _entry(row: PlannedRow) -> InsertEntry:
    return InsertEntry(row=row, origin=NEW_LINEAGE)


def test_a_planned_row_freezes_the_mapping_it_was_built_from() -> None:
    source: dict[AttributeIdentity, object] = {_ID: 1}
    row = PlannedRow(attributes=source)
    source[_OWNER] = "Ada"
    assert dict(row.attributes) == {_ID: 1}


def test_a_planned_row_carrying_no_member_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one member"):
        PlannedRow(attributes={})


def test_a_planned_row_carrying_only_a_value_object_is_a_member() -> None:
    row = PlannedRow(attributes={}, value_objects={_ADDRESS: {"city": "Oslo"}})
    assert row.members == frozenset({_ADDRESS})


def test_row_members_span_both_scalar_and_value_object_identities() -> None:
    row = PlannedRow(attributes={_ID: 1}, value_objects={_ADDRESS: {"city": "Oslo"}})
    assert row.members == frozenset({_ID, _ADDRESS})


def test_a_planned_insert_with_no_entries_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one entry"):
        PlannedInsert(entity=_ACCOUNT, entries=())


def test_entries_of_one_planned_insert_name_the_same_members() -> None:
    # Membership IS the batching decision: one column list serves every entry,
    # so an entry naming a different member set belongs to a different step
    # rather than to a later value tuple bound against the first entry's columns.
    with pytest.raises(ValueError, match="names the same members"):
        PlannedInsert(
            entity=_ACCOUNT,
            entries=(
                _entry(PlannedRow(attributes={_ID: 1, _OWNER: "Ada"})),
                _entry(PlannedRow(attributes={_ID: 2})),
            ),
        )


def test_entries_of_one_planned_insert_share_one_generated_value_shape() -> None:
    # Same members, different cells generated: a generated value folds into the
    # statement while a literal binds, so the two entries cannot share one.
    with pytest.raises(ValueError, match="generated-value shape"):
        PlannedInsert(
            entity=_ACCOUNT,
            entries=(
                _entry(PlannedRow(attributes={_ID: MAX_PLUS_ONE, _OWNER: "Ada"})),
                _entry(PlannedRow(attributes={_ID: 2, _OWNER: "Bo"})),
            ),
        )


def test_compatible_entries_form_one_planned_insert() -> None:
    step = PlannedInsert(
        entity=_ACCOUNT,
        entries=(
            _entry(PlannedRow(attributes={_ID: 1, _OWNER: "Ada"})),
            _entry(PlannedRow(attributes={_ID: 2, _OWNER: "Bo"})),
        ),
    )
    assert [entry.origin for entry in step.entries] == [NEW_LINEAGE, NEW_LINEAGE]


def test_planned_writes_compare_by_value() -> None:
    # Views are immutable and stable but carry no object-identity promise, so
    # every consumer compares them structurally.
    row = PlannedRow(attributes={_ID: 1})
    assert PlannedInsert(entity=_ACCOUNT, entries=(_entry(row),)) == PlannedInsert(
        entity=_ACCOUNT, entries=(_entry(PlannedRow(attributes={_ID: 1})),)
    )


def test_an_empty_write_plan_is_the_canonical_cancelled_result() -> None:
    plan = WritePlan()
    assert len(plan.steps) == 0
    assert list(plan.steps) == []
    assert plan == WritePlan(steps=PlannedSteps())


def test_planned_steps_expose_their_writes_in_execution_order() -> None:
    first = PlannedInsert(entity=_ACCOUNT, entries=(_entry(PlannedRow(attributes={_ID: 1})),))
    second = PlannedInsert(entity=_ACCOUNT, entries=(_entry(PlannedRow(attributes={_ID: 2})),))
    plan = WritePlan(steps=PlannedSteps((first, second)))
    assert len(plan.steps) == 2
    assert plan.steps[0] == first
    assert list(plan.steps) == [first, second]
