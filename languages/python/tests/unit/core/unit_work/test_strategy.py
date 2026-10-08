"""The Concurrency Preference vocabulary and its owner-provided validator
(`m-unit-work` "Strategy selection"): what the closed two-valued vocabulary
admits, how it refuses everything else, and what an accepted value comes back
as; and the audit hooks: the neutral default, and the contract every answer is
held to before settlement uses it.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import pytest

from parallax.core.metamodel import AttributeIdentity
from parallax.core.unit_work import NO_AUDIT, TransactionInstant, concurrency_preference
from parallax.core.unit_work.strategy import (
    CONCURRENCY_PREFERENCES,
    AuditDecoration,
    AuditStrategy,
)
from parallax.core.write_plan import WritePlanningError
from parallax.core.write_plan.steps import (
    INFINITY,
    MISSING_TARGET,
    NEW_LINEAGE,
    STALE_WRITE,
    SUPERSEDED,
    TERMINATED,
    UNGATED,
    UNVERSIONED,
    ExactCount,
    KeyTarget,
    MilestoneTarget,
    NewLineage,
    PlannedAssignments,
    PlannedClose,
    PlannedRow,
    PlannedUpdate,
    WriteRow,
)
from tests._support.clock_probes import CountingClock, inert_instant
from tests._support.planner_probes import TEST_ACTOR_IDENTITY
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._corpus_model_support import target as entity_of
from tests.unit.core.unit_work._audit_support import RecordingAudit


class _UnhashableName(str):
    """A ``str`` no set can be asked about, so the validator is proved to compare."""

    __hash__ = None  # type: ignore[assignment]


def test_the_vocabulary_is_exactly_two_preferences() -> None:
    assert set(CONCURRENCY_PREFERENCES) == {"locking", "optimistic"}


@pytest.mark.parametrize("preference", sorted(CONCURRENCY_PREFERENCES))
def test_every_preference_of_the_vocabulary_is_returned_unchanged(preference: str) -> None:
    assert concurrency_preference(preference) == preference


@pytest.mark.parametrize(
    "value",
    [
        "pessimistic",
        "LOCKING",
        "",
        None,
        True,
        3,
        [],
        {"concurrency": "locking"},
        _UnhashableName("bogus"),
    ],
)
def test_anything_outside_the_vocabulary_is_refused_by_naming_the_whole_set(value: object) -> None:
    with pytest.raises(ValueError, match=r"concurrency must be one of \['locking', 'optimistic'\]"):
        concurrency_preference(value)


def test_an_accepted_preference_comes_back_as_a_plain_hashable_str() -> None:
    preference = concurrency_preference(_UnhashableName("locking"))

    assert preference == "locking"
    assert {preference: "keyable"}


def _account_row() -> tuple[WriteRow, AttributeIdentity, AttributeIdentity]:
    account = entity_of(corpus_model("account"), "Account").identity
    key, owner = AttributeIdentity(account, "id"), AttributeIdentity(account, "owner")
    row = PlannedRow(attributes={key: 1, owner: "Ada"})
    return WriteRow(row=row, origin=NEW_LINEAGE), key, owner


def _account_update() -> PlannedUpdate:
    account = entity_of(corpus_model("account"), "Account").identity
    key = AttributeIdentity(account, "id")
    return PlannedUpdate(
        entity=account,
        target=KeyTarget(key_attributes=(key,), key_values=((1,),)),
        assignments=PlannedAssignments(attributes={AttributeIdentity(account, "owner"): "Ada"}),
        concurrency=UNVERSIONED,
        affected_rows=ExactCount(expected=1, on_shortfall=MISSING_TARGET),
    )


def test_the_neutral_audit_answers_every_input_itself_and_reads_no_clock() -> None:
    # The audit hooks exist as a seam from the start, so provenance becomes a
    # change of injected adapter rather than of interface. The default hands
    # back the very value it was given, which is what makes the seam cost
    # nothing while nothing is wired behind it, and never resolves the instant.
    write_row, _key, _owner = _account_row()
    update = _account_update()
    clock = CountingClock([])
    neutral = AuditDecoration(NO_AUDIT, TEST_ACTOR_IDENTITY, TransactionInstant(clock))

    assert neutral.neutral
    assert neutral.finalize_row(write_row) is write_row
    assert neutral.decorate_update(update) is update
    assert clock.calls == 0
    assert isinstance(NO_AUDIT, AuditStrategy)


def test_a_finalized_row_states_every_value_it_adds_as_an_executed_assignment() -> None:
    write_row, _key, owner = _account_row()
    audit = RecordingAudit(stamps={owner: "audited"})
    bound = AuditDecoration(audit, TEST_ACTOR_IDENTITY, inert_instant())

    finalized = bound.finalize_row(write_row)

    assert not bound.neutral
    assert finalized.row.attributes[owner] == "audited"
    assert finalized.executed == (owner,)
    assert finalized.origin is write_row.origin


@pytest.mark.parametrize("breach", ["origin", "unstated", "dropped"])
def test_an_audit_answer_that_breaks_its_contract_is_refused(breach: str) -> None:
    write_row, key, owner = _account_row()
    stated = WriteRow(row=write_row.row, origin=write_row.origin, executed=(owner,))
    answers = {
        "origin": WriteRow(row=write_row.row, origin=NewLineage()),
        "unstated": WriteRow(row=PlannedRow(attributes={key: 1, owner: "Eve"}), origin=NEW_LINEAGE),
        "dropped": WriteRow(row=stated.row, origin=NEW_LINEAGE),
    }

    class _Breaking:
        def finalize_row(
            self, row: WriteRow, *, actor_identity: object, transaction_instant: object
        ) -> WriteRow:
            del row, actor_identity, transaction_instant
            return answers[breach]

    audited = stated if breach == "dropped" else write_row
    bound = AuditDecoration(cast("Any", _Breaking()), TEST_ACTOR_IDENTITY, inert_instant())
    with pytest.raises(WritePlanningError, match="must state every value it adds or changes"):
        bound.finalize_row(audited)


def test_an_update_decoration_may_not_move_what_the_update_addresses() -> None:
    update = _account_update()

    class _Retargeting:
        def decorate_update(
            self, given: PlannedUpdate, *, actor_identity: object, transaction_instant: object
        ) -> PlannedUpdate:
            del actor_identity, transaction_instant
            target = cast("KeyTarget", given.target)
            return replace(
                given, target=KeyTarget(key_attributes=target.key_attributes, key_values=((2,),))
            )

    bound = AuditDecoration(cast("Any", _Retargeting()), TEST_ACTOR_IDENTITY, inert_instant())
    with pytest.raises(WritePlanningError, match="an update's decoration"):
        bound.decorate_update(update)


def test_a_close_decoration_may_not_change_why_the_milestone_closed() -> None:
    account = entity_of(corpus_model("account"), "Account").identity
    key = AttributeIdentity(account, "id")
    close = PlannedClose(
        entity=account,
        target=MilestoneTarget(
            key_attributes=(key,),
            key_values=(1,),
            end_attributes=(AttributeIdentity(account, "owner"),),
            end_values=(INFINITY,),
        ),
        assignments=PlannedAssignments(attributes={AttributeIdentity(account, "owner"): "x"}),
        cause=SUPERSEDED,
        concurrency=UNGATED,
        affected_rows=ExactCount(expected=1, on_shortfall=STALE_WRITE),
    )

    class _Recausing:
        def decorate_close(
            self, given: PlannedClose, *, actor_identity: object, transaction_instant: object
        ) -> PlannedClose:
            del actor_identity, transaction_instant
            return replace(given, cause=TERMINATED)

    neutral = AuditDecoration(NO_AUDIT, TEST_ACTOR_IDENTITY, inert_instant())
    assert neutral.decorate_close(close) is close
    bound = AuditDecoration(cast("Any", _Recausing()), TEST_ACTOR_IDENTITY, inert_instant())
    with pytest.raises(WritePlanningError, match="a close's decoration"):
        bound.decorate_close(close)
