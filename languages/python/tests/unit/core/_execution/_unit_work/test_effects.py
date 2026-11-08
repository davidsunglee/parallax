"""Affected-row enforcement and its refusal codes (m-unit-work).

`enforce_affected_rows` is the single authoritative reading of an execution
result, so what it answers must be decided by the step alone: the policy names
an outcome class, the enforcer raises the code that class names, and no caller
re-derives either. These are pure value-type tests: no dialect, no SQL, no
database.

Two invariants are asserted independently of the shortfall matrix, because
neither is expressible in the policy: an excess over any exact count is always
Cardinality Corruption whatever the step's shortfall tag says, and the raised
conflict names its row and nothing else — in particular no SQL,
statement index, driver exception, whole Planned Step, assignments, or
observation, which is what keeps the diagnostic stable across dialects and lets
a retry loop recognize the canonical conflict without an optional module.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest

from parallax.core import ConflictError, InternalError, ParallaxError
from parallax.core.metamodel import AttributeIdentity
from parallax.core.predicate import TrueNode, validate_predicate
from parallax.core.unit_work import (
    CARDINALITY_CORRUPTION,
    OPTIMISTIC_LOCK_CONFLICT,
    WRITE_PRECONDITION_FAILED,
    WritePreconditionError,
    WriteResultError,
    allocated_keys,
    enforce_affected_rows,
    returns_allocated_keys,
)
from parallax.core.unit_work import MISSING_TARGET as MISSING_TARGET_CODE
from parallax.core.unit_work import STALE_WRITE as STALE_WRITE_CODE
from parallax.core.write_plan import SUPERSEDED, PlannedClose, PlannedInsert
from parallax.core.write_plan.steps import (
    ANY_COUNT,
    FAILED_PRECONDITION,
    INFINITY,
    MAX_PLUS_ONE,
    MISSING_TARGET,
    NEW_LINEAGE,
    OPTIMISTIC_CONFLICT,
    RETURNED_MAX_PLUS_ONE,
    STALE_WRITE,
    UNGATED,
    UNVERSIONED,
    AffectedRows,
    ExactCount,
    KeyTarget,
    MilestoneTarget,
    NonTemporalConcurrency,
    PlannedAssignments,
    PlannedDelete,
    PlannedStep,
    PlannedTemporalGuard,
    PlannedTemporalRemoval,
    PlannedTemporalRevision,
    PlannedUpdate,
    ResolvedMutationSelection,
    Shortfall,
    TemporalConcurrency,
    TemporalGate,
    Versioned,
    VersionGate,
    WriteRow,
)
from tests._support.errors import raises_code
from tests._support.managed_rows import managed_row_of
from tests.unit._corpus_model_support import model as corpus_model
from tests.unit._corpus_model_support import target as entity_of

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

_SHORTFALL_CODES: dict[Shortfall, str] = {
    MISSING_TARGET: MISSING_TARGET_CODE,
    STALE_WRITE: STALE_WRITE_CODE,
    OPTIMISTIC_CONFLICT: OPTIMISTIC_LOCK_CONFLICT,
}

# A step's shortfall tag is settled BY its concurrency decision, so a case
# exercising one tag must build the decision that implies it.
_KEYED_CONCURRENCY: dict[Shortfall, NonTemporalConcurrency] = {
    MISSING_TARGET: UNVERSIONED,
    STALE_WRITE: Versioned(attribute=_VERSION, gate=UNGATED),
    OPTIMISTIC_CONFLICT: Versioned(attribute=_VERSION, gate=VersionGate(observed_version=1)),
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


def _revision(shortfall: Shortfall = STALE_WRITE) -> PlannedTemporalRevision:
    return PlannedTemporalRevision(
        entity=_ACCOUNT,
        target=_CURRENT_SLOT,
        assignments=_RENAME,
        concurrency=_CLOSE_CONCURRENCY[shortfall],
        affected_rows=ExactCount(expected=1, on_shortfall=shortfall),
        predecessor_document_is_object=False,
    )


def _removal(shortfall: Shortfall = STALE_WRITE) -> PlannedTemporalRemoval:
    return PlannedTemporalRemoval(
        entity=_ACCOUNT,
        target=_CURRENT_SLOT,
        concurrency=_CLOSE_CONCURRENCY[shortfall],
        affected_rows=ExactCount(expected=1, on_shortfall=shortfall),
    )


_MILESTONE_STEPS = pytest.mark.parametrize(
    "build", [_close, _revision, _removal], ids=["close", "revision", "removal"]
)


def _guard() -> PlannedTemporalGuard:
    concurrency = _CLOSE_CONCURRENCY[OPTIMISTIC_CONFLICT]
    assert isinstance(concurrency, TemporalGate)
    return PlannedTemporalGuard(
        entity=_ACCOUNT,
        target=_CURRENT_SLOT,
        concurrency=concurrency,
        affected_rows=ExactCount(expected=1, on_shortfall=OPTIMISTIC_CONFLICT),
    )


@pytest.mark.parametrize(
    ("actual", "refusal"),
    [
        (1, None),
        (0, (ConflictError, OPTIMISTIC_LOCK_CONFLICT)),
        (2, (InternalError, CARDINALITY_CORRUPTION)),
    ],
    ids=["matched", "unmatched", "excess"],
)
def test_a_guard_matches_its_one_milestone_or_conflicts(
    actual: int, refusal: tuple[type[ParallaxError], str] | None
) -> None:
    if refusal is None:
        enforce_affected_rows(_guard(), actual)
        return
    with raises_code(*refusal):
        enforce_affected_rows(_guard(), actual)


def _insert() -> PlannedInsert:
    return PlannedInsert(
        entity=_ACCOUNT,
        entries=(WriteRow(row=managed_row_of(_ACCOUNT_MODEL, {_ID: 1}), origin=NEW_LINEAGE),),
    )


@pytest.mark.parametrize("shortfall", list(_SHORTFALL_CODES), ids=lambda tag: type(tag).__name__)
@pytest.mark.parametrize("build", [_update, _delete], ids=["update", "delete"])
def test_a_keyed_shortfall_raises_the_code_its_own_tag_names(
    build: Callable[..., PlannedStep], shortfall: Shortfall
) -> None:
    with raises_code(ConflictError, _SHORTFALL_CODES[shortfall]) as caught:
        enforce_affected_rows(build(shortfall), 0)
    assert caught.value.is_transient is (shortfall is OPTIMISTIC_CONFLICT)


@_MILESTONE_STEPS
@pytest.mark.parametrize("shortfall", list(_CLOSE_CONCURRENCY), ids=lambda tag: type(tag).__name__)
def test_a_milestone_shortfall_raises_the_code_its_own_tag_names(
    build: Callable[[Shortfall], PlannedStep], shortfall: Shortfall
) -> None:
    with raises_code(ConflictError, _SHORTFALL_CODES[shortfall]) as caught:
        enforce_affected_rows(build(shortfall), 0)
    assert caught.value.is_transient is (shortfall is OPTIMISTIC_CONFLICT)


def test_a_multi_key_target_is_enforced_against_its_aggregate_count() -> None:
    step = _delete(target=_THREE_KEYS)
    enforce_affected_rows(step, 3)
    with raises_code(ConflictError, MISSING_TARGET_CODE, match=r"affected 2 row\(s\), expected 3"):
        enforce_affected_rows(step, 2)


@pytest.mark.parametrize("shortfall", list(_SHORTFALL_CODES), ids=lambda tag: type(tag).__name__)
def test_an_excess_over_any_exact_count_is_cardinality_corruption(shortfall: Shortfall) -> None:
    with raises_code(InternalError, CARDINALITY_CORRUPTION):
        enforce_affected_rows(_update(shortfall), 2)


def test_an_excess_over_a_multi_key_count_is_cardinality_corruption() -> None:
    with raises_code(InternalError, CARDINALITY_CORRUPTION):
        enforce_affected_rows(_delete(target=_THREE_KEYS), 4)


@_MILESTONE_STEPS
@pytest.mark.parametrize("shortfall", list(_CLOSE_CONCURRENCY), ids=lambda tag: type(tag).__name__)
def test_an_excess_over_a_milestone_count_is_cardinality_corruption(
    build: Callable[[Shortfall], PlannedStep], shortfall: Shortfall
) -> None:
    with raises_code(InternalError, CARDINALITY_CORRUPTION):
        enforce_affected_rows(build(shortfall), 2)


@pytest.mark.parametrize("actual", [0, 1, 3])
def test_an_insert_carries_no_policy_and_is_accepted(actual: int) -> None:
    enforce_affected_rows(_insert(), actual)


def _allocating(key: object = RETURNED_MAX_PLUS_ONE) -> PlannedInsert:
    return PlannedInsert(
        entity=_ACCOUNT,
        entries=(
            WriteRow(
                row=managed_row_of(_ACCOUNT_MODEL, {_ID: key, _OWNER: "Ada"}), origin=NEW_LINEAGE
            ),
        ),
    )


def test_only_an_insert_returning_its_allocated_key_answers_rows() -> None:
    assert returns_allocated_keys(_allocating())
    assert not returns_allocated_keys(_allocating(MAX_PLUS_ONE))
    assert not returns_allocated_keys(_insert())
    assert not returns_allocated_keys(_update())


def test_the_allocated_key_is_read_from_the_one_row_its_insert_answered() -> None:
    assert allocated_keys(_allocating(), [(8,)]) == (8,)


@pytest.mark.parametrize(
    ("rows", "reason"),
    [
        ([], "a missing row"),
        ([(8,), (9,)], "an excess row"),
        ([(8, "Ada")], "a row of 2 cell"),
        ([("8",)], "a key of type str"),
        ([(True,)], "a key of type bool"),
    ],
    ids=["missing", "excess", "wide", "text", "boolean"],
)
def test_an_answer_the_insert_cannot_produce_is_a_result_invariant_failure(
    rows: list[tuple[object, ...]], reason: str
) -> None:
    with pytest.raises(WriteResultError, match=reason) as raised:
        allocated_keys(_allocating(), rows)
    assert (raised.value.entity, raised.value.expected, raised.value.actual) == (
        _ACCOUNT,
        1,
        len(rows),
    )


def test_a_key_answered_twice_is_a_result_invariant_failure() -> None:
    two = PlannedInsert(
        entity=_ACCOUNT,
        entries=tuple(
            WriteRow(
                row=managed_row_of(_ACCOUNT_MODEL, {_ID: RETURNED_MAX_PLUS_ONE}), origin=NEW_LINEAGE
            )
            for _ in range(2)
        ),
    )
    with pytest.raises(WriteResultError, match="the key 8 twice"):
        allocated_keys(two, [(8,), (8,)])


@pytest.mark.parametrize("actual", [0, 1, 4096])
def test_any_count_accepts_every_nonnegative_result(actual: int) -> None:
    step = PlannedUpdate(
        entity=_ACCOUNT,
        target=ResolvedMutationSelection(
            _ACCOUNT_META, validate_predicate(_ACCOUNT_META, TrueNode(), _ACCOUNT_MODEL)
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


def test_a_shortfall_names_its_row_and_states_the_counts_in_its_message() -> None:
    with raises_code(ConflictError, MISSING_TARGET_CODE) as caught:
        enforce_affected_rows(_update(), 0)
    error = caught.value
    assert (error.entity, error.key) == (_ACCOUNT.canonical, {"id": 1})
    assert "affected 0 row(s), expected 1 (keys=[{'id': 1}])" in str(error)


def test_a_multi_key_shortfall_names_the_first_row_its_target_addresses() -> None:
    with raises_code(ConflictError, MISSING_TARGET_CODE) as caught:
        enforce_affected_rows(_delete(target=_THREE_KEYS), 1)
    assert caught.value.key == {"id": 1}


def test_a_milestone_shortfall_names_the_row_by_its_milestone_key() -> None:
    with raises_code(ConflictError, STALE_WRITE_CODE) as caught:
        enforce_affected_rows(_close(), 0)
    assert (caught.value.entity, caught.value.key) == (_ACCOUNT.canonical, {"id": 1})


def test_an_excess_states_the_counts_and_names_no_row() -> None:
    with raises_code(InternalError, CARDINALITY_CORRUPTION) as caught:
        enforce_affected_rows(_close(), 2)
    assert "affected 2 row(s), expected 1" in str(caught.value)
    assert not hasattr(caught.value, "key")


@pytest.mark.parametrize(
    "step",
    [_update(), _delete(OPTIMISTIC_CONFLICT), _close()],
    ids=["update", "delete", "close"],
)
def test_no_payload_carries_sql_a_statement_a_plan_or_an_observation(step: PlannedStep) -> None:
    with pytest.raises(ConflictError) as caught:
        enforce_affected_rows(step, 0)
    error = caught.value
    assert set(vars(error)) == {"_entity", "_key", "_transient"}
    assert not any(
        hasattr(error, absent)
        for absent in ("sql", "binds", "statement", "index", "step", "assignments", "observation")
    )
    rendered = str(error).lower()
    assert not any(fragment in rendered for fragment in ("update ", "delete ", "select ", "?"))


_GATED_UPDATE = Versioned(attribute=_VERSION, gate=VersionGate(observed_version=4))
_GATED_CLOSE = TemporalGate(start_attribute=_TX_START, observed_start="2024-01-01T00:00:00+00:00")


@pytest.mark.parametrize("build", [_update, _delete], ids=["update", "delete"])
def test_a_gate_binding_a_callers_revision_fails_as_that_precondition(
    build: Callable[..., PlannedStep],
) -> None:
    step = replace(
        build(OPTIMISTIC_CONFLICT),
        concurrency=_GATED_UPDATE,
        affected_rows=ExactCount(expected=1, on_shortfall=FAILED_PRECONDITION),
    )
    with pytest.raises(WritePreconditionError) as failed:
        enforce_affected_rows(step, 0)
    assert (failed.value.entity, dict(failed.value.key), failed.value.expected) == (
        _ACCOUNT.canonical,
        {"id": 1},
        4,
    )
    assert failed.value.code == WRITE_PRECONDITION_FAILED
    assert not failed.value.is_transient
    with raises_code(InternalError, CARDINALITY_CORRUPTION):
        enforce_affected_rows(step, 2)


@_MILESTONE_STEPS
def test_a_milestone_gate_binding_a_callers_start_fails_as_that_precondition(
    build: Callable[[Shortfall], PlannedStep],
) -> None:
    step = replace(
        build(OPTIMISTIC_CONFLICT),
        concurrency=_GATED_CLOSE,
        affected_rows=ExactCount(expected=1, on_shortfall=FAILED_PRECONDITION),
    )
    with pytest.raises(WritePreconditionError) as failed:
        enforce_affected_rows(step, 0)
    assert (dict(failed.value.key), failed.value.expected) == (
        {"id": 1},
        "2024-01-01T00:00:00+00:00",
    )


@pytest.mark.parametrize(
    "concurrency",
    [UNVERSIONED, Versioned(attribute=_VERSION, gate=UNGATED)],
    ids=["unversioned", "ungated"],
)
def test_only_a_gate_can_fail_as_a_callers_precondition(
    concurrency: NonTemporalConcurrency,
) -> None:
    with pytest.raises(ValueError, match="classifies a shortfall"):
        PlannedUpdate(
            entity=_ACCOUNT,
            target=_ONE_KEY,
            assignments=_RENAME,
            concurrency=concurrency,
            affected_rows=ExactCount(expected=1, on_shortfall=FAILED_PRECONDITION),
        )
    with pytest.raises(ValueError, match="classifies a shortfall"):
        PlannedClose(
            entity=_ACCOUNT,
            target=_CURRENT_SLOT,
            assignments=PlannedAssignments(attributes={_TX_END: "2024-09-01T00:00:00+00:00"}),
            cause=SUPERSEDED,
            concurrency=UNGATED,
            affected_rows=ExactCount(expected=1, on_shortfall=FAILED_PRECONDITION),
        )
