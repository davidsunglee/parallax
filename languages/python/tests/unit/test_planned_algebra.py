"""Construction invariants of the finalized Planned Write algebra (m-unit-work).

A Planned Write is what SQL lowering receives with every semantic question
already settled, so the shapes that would leave one unsettled must be
unconstructible rather than merely unusual: an insert with no entries, an entry
row naming no member, and entries of one step disagreeing about which members or
which generated-value cells they carry. These are pure value-type tests — no
metamodel, no dialect, no SQL — pinned against synthetic identities so the
invariant, not a corpus model, is what fails them.

An addressed step's target, concurrency decision, and expected effect describe
one row selection together, so the combinations that would describe two — a
readless predicate carrying a gate, an exact count disagreeing with the number of
keys addressed, a per-row gate on a multi-key target, a shortfall classified
against what the settled gate implies — are unconstructible too. A generated
value is likewise unconstructible at the statement position that could not
express it. A Temporal Observation's predecessor is complete or absent, never
partial.

The Write Plan's own contract is here too: an empty Planned Steps is the one
canonical result for a flush that survives nothing, and Planned Steps is a
logical sequence whose views compare by value rather than by object identity.
"""

from __future__ import annotations

import pytest

from parallax.core.metamodel import AttributeIdentity, EntityIdentity, ValueObjectIdentity
from parallax.core.op_algebra import All
from parallax.core.unit_work import (
    ANY_COUNT,
    MAX_PLUS_ONE,
    MISSING_TARGET,
    NEW_LINEAGE,
    OPTIMISTIC_CONFLICT,
    STALE_WRITE,
    UNGATED,
    UNVERSIONED,
    AffectedRows,
    ExactCount,
    InsertEntry,
    KeyTarget,
    NonTemporalConcurrency,
    PlannedAssignments,
    PlannedDelete,
    PlannedInsert,
    PlannedRow,
    PlannedSteps,
    PlannedUpdate,
    PredecessorRow,
    PredicateTarget,
    SelfIncrement,
    Shortfall,
    Versioned,
    VersionGate,
    WritePlan,
    shortfall_for,
)
from parallax.core.unit_work.planned import WriteTarget

_ACCOUNT = EntityIdentity(None, "Account")
_ID = AttributeIdentity(_ACCOUNT, "id")
_OWNER = AttributeIdentity(_ACCOUNT, "owner")
_VERSION = AttributeIdentity(_ACCOUNT, "version")
_ADDRESS = ValueObjectIdentity(_ACCOUNT, ("address",))
_ONE_KEY = KeyTarget(key_attributes=(_ID,), key_values=((1,),))
_TWO_KEYS = KeyTarget(key_attributes=(_ID,), key_values=((1,), (2,)))
_BALANCE_SET = PlannedAssignments(attributes={_OWNER: "Ada"})


def _entry(row: PlannedRow) -> InsertEntry:
    return InsertEntry(row=row, origin=NEW_LINEAGE)


def _delete(
    target: WriteTarget,
    concurrency: NonTemporalConcurrency,
    affected_rows: AffectedRows,
) -> PlannedDelete:
    return PlannedDelete(
        entity=_ACCOUNT,
        target=target,
        concurrency=concurrency,
        affected_rows=affected_rows,
    )


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


def test_planned_assignments_naming_no_member_are_refused() -> None:
    with pytest.raises(ValueError, match="at least one member"):
        PlannedAssignments(attributes={})


def test_a_planned_row_refuses_the_generated_value_no_insert_can_express() -> None:
    # The registry advance reads the stored row it is rewriting; an insert has no
    # stored row, so the combination names an allocation nothing could render.
    with pytest.raises(ValueError, match="never a Planned Row cell"):
        PlannedRow(attributes={_ID: SelfIncrement(amount=1)})


def test_planned_assignments_refuse_the_generated_value_no_update_can_express() -> None:
    # `max` folds into the row an insert opens; a `SET` clause has no position to
    # fold it into, so it is refused here rather than bound as a literal object.
    with pytest.raises(ValueError, match="never a Planned Assignment"):
        PlannedAssignments(attributes={_ID: MAX_PLUS_ONE})


def test_each_generated_value_is_constructible_at_its_own_statement_position() -> None:
    assert PlannedRow(attributes={_ID: MAX_PLUS_ONE}).attributes[_ID] == MAX_PLUS_ONE
    advance = SelfIncrement(amount=1)
    assert PlannedAssignments(attributes={_ID: advance}).attributes[_ID] == advance


def test_planned_assignments_span_both_scalar_and_value_object_identities() -> None:
    assignments = PlannedAssignments(
        attributes={_OWNER: "Ada"}, value_objects={_ADDRESS: {"city": "Oslo"}}
    )
    assert assignments.members == frozenset({_OWNER, _ADDRESS})


def test_a_key_target_names_at_least_one_key_attribute() -> None:
    with pytest.raises(ValueError, match="at least one primary-key Attribute"):
        KeyTarget(key_attributes=(), key_values=((1,),))


def test_a_key_target_addresses_at_least_one_row() -> None:
    with pytest.raises(ValueError, match="at least one row"):
        KeyTarget(key_attributes=(_ID,), key_values=())


def test_every_addressed_key_tuple_is_complete() -> None:
    # A tuple shorter than the key shape names no row, so it is refused where the
    # target is settled rather than lowered into a predicate with a missing bind.
    with pytest.raises(ValueError, match="every value tuple is complete"):
        KeyTarget(key_attributes=(_ID, _OWNER), key_values=((1, "Ada"), (2,)))


@pytest.mark.parametrize("value", [None, {"computed": "maxPlusOne"}], ids=["null", "marker"])
def test_a_key_value_is_concrete_and_non_null(value: object) -> None:
    # A null addresses nothing under SQL equality, and a DB-computed marker names
    # a value that does not exist yet — neither can identify a stored row.
    with pytest.raises(ValueError, match="concrete and non-null"):
        KeyTarget(key_attributes=(_ID,), key_values=((value,),))


def test_repeated_authored_keys_are_invalid_rather_than_deduplicated() -> None:
    # Silently collapsing them would make the step's expected effect disagree
    # with what the caller asked for.
    with pytest.raises(ValueError, match="addressed rows are distinct"):
        KeyTarget(key_attributes=(_ID,), key_values=((1,), (1,)))


def test_an_exact_affected_row_count_is_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        ExactCount(expected=0, on_shortfall=MISSING_TARGET)


@pytest.mark.parametrize(
    ("concurrency", "affected_rows"),
    [
        (Versioned(gate=UNGATED), ANY_COUNT),
        (UNVERSIONED, ExactCount(expected=1, on_shortfall=MISSING_TARGET)),
    ],
    ids=["versioned", "exact-count"],
)
def test_a_predicate_target_implies_unversioned_and_an_unbounded_effect(
    concurrency: NonTemporalConcurrency, affected_rows: AffectedRows
) -> None:
    # A readless predicate resolves no rows, so it can carry no per-row observed
    # version and can promise no row count: a zero-row match succeeds.
    with pytest.raises(ValueError, match="Predicate Target is readless"):
        _delete(PredicateTarget(predicate=All()), concurrency, affected_rows)


@pytest.mark.parametrize(
    "affected_rows",
    [ANY_COUNT, ExactCount(expected=2, on_shortfall=MISSING_TARGET)],
    ids=["any-count", "wrong-count"],
)
def test_a_key_target_expects_exactly_as_many_rows_as_it_addresses(
    affected_rows: AffectedRows,
) -> None:
    with pytest.raises(ValueError, match="exactly as many rows as it addresses"):
        _delete(_ONE_KEY, UNVERSIONED, affected_rows)


def test_a_version_gate_requires_a_singleton_key_target() -> None:
    # Each observed version belongs to exactly one row, so one gate predicate
    # cannot guard a multi-key statement.
    with pytest.raises(ValueError, match="singleton Key Target"):
        _delete(
            _TWO_KEYS,
            Versioned(gate=VersionGate(attribute=_VERSION, observed_version=3)),
            ExactCount(expected=2, on_shortfall=OPTIMISTIC_CONFLICT),
        )


def test_an_ungated_versioned_decision_may_address_several_keys() -> None:
    # The singleton requirement follows the GATE, not versioning: nothing per-row
    # is bound when the decision is Ungated.
    step = _delete(
        _TWO_KEYS,
        Versioned(gate=UNGATED),
        ExactCount(expected=2, on_shortfall=STALE_WRITE),
    )
    assert step.target == _TWO_KEYS


@pytest.mark.parametrize(
    ("concurrency", "shortfall"),
    [
        (UNVERSIONED, MISSING_TARGET),
        (Versioned(gate=UNGATED), STALE_WRITE),
        (Versioned(gate=VersionGate(attribute=_VERSION, observed_version=3)), OPTIMISTIC_CONFLICT),
    ],
    ids=["unversioned", "ungated", "gated"],
)
def test_one_concurrency_decision_admits_one_shortfall_classification(
    concurrency: NonTemporalConcurrency, shortfall: Shortfall
) -> None:
    # The classification follows the settled gate, never the verb (ADR 0044/0047),
    # so the step derives it rather than accepting whatever it is handed.
    assert shortfall_for(concurrency) == shortfall
    step = _delete(_ONE_KEY, concurrency, ExactCount(expected=1, on_shortfall=shortfall))
    assert step.affected_rows == ExactCount(expected=1, on_shortfall=shortfall)


@pytest.mark.parametrize(
    ("concurrency", "shortfall"),
    [
        (Versioned(gate=UNGATED), MISSING_TARGET),
        (Versioned(gate=UNGATED), OPTIMISTIC_CONFLICT),
        (UNVERSIONED, STALE_WRITE),
        (Versioned(gate=VersionGate(attribute=_VERSION, observed_version=3)), STALE_WRITE),
    ],
    ids=["ungated-as-missing", "ungated-as-conflict", "unversioned-as-stale", "gated-as-stale"],
)
def test_a_contradictory_shortfall_classification_is_refused(
    concurrency: NonTemporalConcurrency, shortfall: Shortfall
) -> None:
    # An ungated versioned write DID observe, so its shortfall can never be a
    # missing target, and no gate existed to lose a race against; symmetrically an
    # observation-free write has nothing to be stale about.
    with pytest.raises(ValueError, match="classifies a shortfall as"):
        _delete(_ONE_KEY, concurrency, ExactCount(expected=1, on_shortfall=shortfall))


def test_a_planned_update_settles_its_target_the_same_way_a_delete_does() -> None:
    with pytest.raises(ValueError, match="exactly as many rows as it addresses"):
        PlannedUpdate(
            entity=_ACCOUNT,
            target=_ONE_KEY,
            assignments=_BALANCE_SET,
            concurrency=UNVERSIONED,
            affected_rows=ANY_COUNT,
        )


def test_a_predecessor_row_carrying_no_member_is_refused() -> None:
    # A Temporal Observation retains the whole predecessor or none of it: a
    # partial one would silently drop members temporal expansion carries forward.
    with pytest.raises(ValueError, match="complete state"):
        PredecessorRow(members={})


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
