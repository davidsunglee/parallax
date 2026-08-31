"""Affected-row enforcement and the Write Effect Error family (m-unit-work).

`enforce_affected_rows` is the single authoritative reading of an execution
result, so what it answers must be decided by the step alone: the policy names
an outcome class, the enforcer raises the error that class names, and no caller
re-derives either. These are pure value-type tests — no metamodel, no dialect,
no SQL, no database — pinned against synthetic identities so the rule, not a
corpus model, is what fails them.

Two invariants are asserted independently of the shortfall matrix, because
neither is expressible in the policy: an excess over any exact count is always
Cardinality Corruption whatever the step's shortfall tag says, and the raised
payload carries the four semantic facts and nothing else — in particular no SQL,
statement index, driver exception, whole Planned Write, assignments, or
observation, which is what keeps the diagnostic stable across dialects and lets
a retry loop recognize the canonical conflict without an optional module.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from _corpus_model_support import model as corpus_model
from _corpus_model_support import target as entity_of

from parallax.core.metamodel import AttributeIdentity
from parallax.core.predicate import All, validate_predicate
from parallax.core.unit_work import (
    ANY_COUNT,
    INFINITY,
    MISSING_TARGET,
    NEW_LINEAGE,
    OPTIMISTIC_CONFLICT,
    STALE_WRITE,
    SUPERSEDED,
    UNGATED,
    UNVERSIONED,
    AffectedRows,
    CardinalityCorruptionError,
    ExactCount,
    InsertEntry,
    KeyTarget,
    MilestoneTarget,
    MissingTargetError,
    NonTemporalConcurrency,
    OptimisticLockConflictError,
    PlannedAssignments,
    PlannedClose,
    PlannedDelete,
    PlannedInsert,
    PlannedRow,
    PlannedUpdate,
    Shortfall,
    StaleWriteError,
    TemporalConcurrency,
    TemporalGate,
    Versioned,
    VersionGate,
    WriteEffectError,
    enforce_affected_rows,
)
from parallax.core.unit_work.planned import (
    PlannedWrite as PlannedStep,
)
from parallax.core.unit_work.planned import (
    ValidatedMutationSelection,
)

_ACCOUNT_MODEL = corpus_model("account")
_ACCOUNT_META = entity_of(_ACCOUNT_MODEL, "Account")
_ACCOUNT = _ACCOUNT_META.identity
_ID = AttributeIdentity(_ACCOUNT, "id")
_OWNER = AttributeIdentity(_ACCOUNT, "owner")
_VERSION = AttributeIdentity(_ACCOUNT, "version")
_TX_START = AttributeIdentity(_ACCOUNT, "txStart")
_TX_END = AttributeIdentity(_ACCOUNT, "txEnd")

_ONE_KEY = KeyTarget(key_attributes=(_ID,), key_values=((1,),))
_THREE_KEYS = KeyTarget(key_attributes=(_ID,), key_values=((1,), (2,), (3,)))
_CURRENT_SLOT = MilestoneTarget(
    key_attributes=(_ID,),
    key_values=(1,),
    end_attributes=(_TX_END,),
    end_values=(INFINITY,),
)
_RENAME = PlannedAssignments(attributes={_OWNER: "Ada"})

_SHORTFALL_ERRORS: dict[Shortfall, type[WriteEffectError]] = {
    MISSING_TARGET: MissingTargetError,
    STALE_WRITE: StaleWriteError,
    OPTIMISTIC_CONFLICT: OptimisticLockConflictError,
}

# A step's shortfall tag is settled BY its concurrency decision, so a case
# exercising one tag must build the decision that implies it.
_KEYED_CONCURRENCY: dict[Shortfall, NonTemporalConcurrency] = {
    MISSING_TARGET: UNVERSIONED,
    STALE_WRITE: Versioned(gate=UNGATED),
    OPTIMISTIC_CONFLICT: Versioned(gate=VersionGate(attribute=_VERSION, observed_version=1)),
}

_CLOSE_CONCURRENCY: dict[Shortfall, TemporalConcurrency] = {
    STALE_WRITE: UNGATED,
    OPTIMISTIC_CONFLICT: TemporalGate(
        start_attribute=_TX_START, observed_start="2024-01-01T00:00:00+00:00"
    ),
}


def _update(
    shortfall: Shortfall = MISSING_TARGET,
    target: KeyTarget = _ONE_KEY,
    affected_rows: AffectedRows | None = None,
) -> PlannedUpdate:
    return PlannedUpdate(
        entity=_ACCOUNT,
        target=target,
        assignments=_RENAME,
        concurrency=_KEYED_CONCURRENCY[shortfall],
        affected_rows=affected_rows
        or ExactCount(expected=len(target.key_values), on_shortfall=shortfall),
    )


def _delete(
    shortfall: Shortfall = MISSING_TARGET,
    target: KeyTarget = _ONE_KEY,
    affected_rows: AffectedRows | None = None,
) -> PlannedDelete:
    return PlannedDelete(
        entity=_ACCOUNT,
        target=target,
        concurrency=_KEYED_CONCURRENCY[shortfall],
        affected_rows=affected_rows
        or ExactCount(expected=len(target.key_values), on_shortfall=shortfall),
    )


def _close(shortfall: Shortfall = STALE_WRITE) -> PlannedClose:
    return PlannedClose(
        entity=_ACCOUNT,
        target=_CURRENT_SLOT,
        assignments=PlannedAssignments(attributes={_TX_END: "2024-09-01T00:00:00+00:00"}),
        cause=SUPERSEDED,
        concurrency=_CLOSE_CONCURRENCY[shortfall],
        affected_rows=ExactCount(expected=1, on_shortfall=shortfall),
    )


def _insert() -> PlannedInsert:
    return PlannedInsert(
        entity=_ACCOUNT,
        entries=(InsertEntry(row=PlannedRow(attributes={_ID: 1}), origin=NEW_LINEAGE),),
    )


@pytest.mark.parametrize("shortfall", list(_SHORTFALL_ERRORS), ids=lambda tag: type(tag).__name__)
@pytest.mark.parametrize("build", [_update, _delete], ids=["update", "delete"])
def test_a_keyed_shortfall_raises_the_error_its_own_tag_names(
    build: Callable[..., PlannedStep], shortfall: Shortfall
) -> None:
    with pytest.raises(_SHORTFALL_ERRORS[shortfall]):
        enforce_affected_rows(build(shortfall), 0)


@pytest.mark.parametrize("shortfall", list(_CLOSE_CONCURRENCY), ids=lambda tag: type(tag).__name__)
def test_a_milestone_shortfall_raises_the_error_its_own_tag_names(shortfall: Shortfall) -> None:
    with pytest.raises(_SHORTFALL_ERRORS[shortfall]):
        enforce_affected_rows(_close(shortfall), 0)


def test_a_multi_key_target_is_enforced_against_its_aggregate_count() -> None:
    step = _delete(target=_THREE_KEYS)
    enforce_affected_rows(step, 3)
    with pytest.raises(MissingTargetError) as caught:
        enforce_affected_rows(step, 2)
    assert (caught.value.expected, caught.value.actual) == (3, 2)


@pytest.mark.parametrize("shortfall", list(_SHORTFALL_ERRORS), ids=lambda tag: type(tag).__name__)
def test_an_excess_over_any_exact_count_is_cardinality_corruption(shortfall: Shortfall) -> None:
    with pytest.raises(CardinalityCorruptionError):
        enforce_affected_rows(_update(shortfall), 2)


def test_an_excess_over_a_multi_key_count_is_cardinality_corruption() -> None:
    with pytest.raises(CardinalityCorruptionError):
        enforce_affected_rows(_delete(target=_THREE_KEYS), 4)


@pytest.mark.parametrize("shortfall", list(_CLOSE_CONCURRENCY), ids=lambda tag: type(tag).__name__)
def test_an_excess_over_a_milestone_count_is_cardinality_corruption(shortfall: Shortfall) -> None:
    with pytest.raises(CardinalityCorruptionError):
        enforce_affected_rows(_close(shortfall), 2)


@pytest.mark.parametrize("actual", [0, 1, 3])
def test_an_insert_carries_no_policy_and_is_accepted(actual: int) -> None:
    enforce_affected_rows(_insert(), actual)


@pytest.mark.parametrize("actual", [0, 1, 4096])
def test_any_count_accepts_every_nonnegative_result(actual: int) -> None:
    step = PlannedUpdate(
        entity=_ACCOUNT,
        target=ValidatedMutationSelection(
            _ACCOUNT_META, validate_predicate(_ACCOUNT_META, All(), _ACCOUNT_MODEL)
        ),
        assignments=_RENAME,
        concurrency=UNVERSIONED,
        affected_rows=ANY_COUNT,
    )
    enforce_affected_rows(step, actual)


@pytest.mark.parametrize(
    "step",
    [_update(), _delete(STALE_WRITE), _close()],
    ids=["update", "delete", "close"],
)
def test_a_satisfied_expectation_returns(step: PlannedStep) -> None:
    enforce_affected_rows(step, 1)


def test_the_payload_carries_the_four_semantic_facts_and_the_target_by_reference() -> None:
    step = _update()
    with pytest.raises(MissingTargetError) as caught:
        enforce_affected_rows(step, 0)
    error = caught.value
    assert error.entity == _ACCOUNT
    assert error.target is step.target
    assert (error.expected, error.actual) == (1, 0)


def test_a_milestone_failure_retains_the_close_s_own_target_by_reference() -> None:
    step = _close()
    with pytest.raises(StaleWriteError) as caught:
        enforce_affected_rows(step, 0)
    assert caught.value.target is step.target


@pytest.mark.parametrize(
    "step",
    [_update(), _delete(OPTIMISTIC_CONFLICT), _close()],
    ids=["update", "delete", "close"],
)
def test_no_payload_carries_sql_a_statement_a_plan_or_an_observation(step: PlannedStep) -> None:
    with pytest.raises(WriteEffectError) as caught:
        enforce_affected_rows(step, 0)
    error = caught.value
    assert set(vars(error)) == {"entity", "target", "expected", "actual"}
    assert not any(
        hasattr(error, absent)
        for absent in ("sql", "binds", "statement", "index", "step", "assignments", "observation")
    )
    rendered = str(error).lower()
    assert not any(fragment in rendered for fragment in ("update ", "delete ", "select ", "?"))


def test_every_member_of_the_family_shares_one_base() -> None:
    for error in (
        MissingTargetError,
        StaleWriteError,
        OptimisticLockConflictError,
        CardinalityCorruptionError,
    ):
        assert issubclass(error, WriteEffectError)
