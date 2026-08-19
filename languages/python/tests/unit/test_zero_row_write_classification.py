"""A zero-row keyed write in Locking mode, and what must NOT happen to it.

The state has no end-to-end witness because no client can reach it: a
Locking-mode keyed write settles zero rows only if its target disappeared while
the read that licenses the write held that row's shared lock, which correct
locking prevents. The claim is therefore pinned here, with no database, no
interference, and no write ingress:

* a versioned keyed write settled UNGATED (the Locking arm) carries the
  never-retriable stale write as its shortfall class, and an unversioned one
  carries the never-retriable missing target;
* the bounded re-execution loop does NOT retry either, and reports that verdict
  to its observer, so a caller with retry budget left still surfaces the failure
  after exactly one attempt.

The second half is the failure mode worth preventing: a loop that re-ran a
stale write would re-execute the whole unit of work against a cause no re-read
can change. The per-step derivation on its own is ``test_write_planner``'s; what
is composed here is the chain from that derivation, through the affected-row
enforcer, to the retry decision.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from _corpus_model_support import model as corpus_model

from _support.clock_probes import inert_instant
from _support.planner_probes import TEST_SUBJECT_IDENTITY, observed_buffer
from parallax.core.auto_retry import run_with_retry
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, Metamodel
from parallax.core.unit_work import (
    MISSING_TARGET,
    STALE_WRITE,
    AffectedRows,
    ExactCount,
    KeyedWrite,
    KeyTarget,
    MissingTargetError,
    OptimisticLockConflictError,
    PlannedDelete,
    PlannedUpdate,
    PlanningRequest,
    StaleWriteError,
    VersionObservation,
    WriteEffectError,
    enforce_affected_rows,
    object_key,
)
from parallax.core.unit_work.planned import PlannedWrite
from parallax.snapshot.handle import build_write_planner

_ACCOUNT = corpus_model("account")
_WALLET = corpus_model("wallet")

_ROW_2 = EntityIdentity("parallax.compatibility", "Account")
_KEY_2 = KeyTarget(key_attributes=(AttributeIdentity(_ROW_2, "id"),), key_values=((2,),))


def _locking_policy(
    write: KeyedWrite, model: Metamodel, *, observed: int | None
) -> tuple[PlannedWrite, AffectedRows]:
    """The single step a Locking-mode unit of work plans for ``write``, and the
    Affected Rows Policy it carries."""
    key = object_key(write, model)
    assert key is not None  # every write here names one row of a keyed Entity
    observations = (
        None if observed is None else {key: VersionObservation(observed_version=observed)}
    )
    plan = build_write_planner(model).plan(
        PlanningRequest(
            subject_identity=TEST_SUBJECT_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="locking",
            buffered_writes=observed_buffer([write], model, observations),
        )
    )
    (step,) = plan.steps
    assert isinstance(step, PlannedUpdate | PlannedDelete)  # neither write opens a row
    return step, step.affected_rows


@pytest.mark.parametrize(
    "write",
    [
        KeyedWrite("update", "Account", ({"id": 2, "balance": 250.00},)),
        KeyedWrite("delete", "Account", ({"id": 2},)),
    ],
    ids=["update", "delete"],
)
def test_a_versioned_locking_write_reaching_no_row_is_the_non_retriable_stale_write(
    write: KeyedWrite,
) -> None:
    # The Locking arm renders no gate — the shared read lock is what makes the
    # write correct — so a shortfall cannot be a gate that came up short.
    step, policy = _locking_policy(write, _ACCOUNT, observed=1)
    assert policy == ExactCount(1, STALE_WRITE)
    with pytest.raises(StaleWriteError):
        enforce_affected_rows(step, 0)


@pytest.mark.parametrize(
    "write",
    [
        KeyedWrite("update", "Wallet", ({"id": 2, "balance": 250.00},)),
        KeyedWrite("delete", "Wallet", ({"id": 2},)),
    ],
    ids=["update", "delete"],
)
def test_an_unversioned_write_reaching_no_row_is_the_non_retriable_missing_target(
    write: KeyedWrite,
) -> None:
    # An unversioned Non-Temporal row observes no state, so no gate could have
    # come up short and no version could have moved: what the shortfall says is
    # only that the addressed row is not there.
    step, policy = _locking_policy(write, _WALLET, observed=None)
    assert policy == ExactCount(1, MISSING_TARGET)
    with pytest.raises(MissingTargetError):
        enforce_affected_rows(step, 0)


def _raising(error: WriteEffectError) -> tuple[Callable[[], int], list[int]]:
    attempts: list[int] = []

    def attempt() -> int:
        attempts.append(len(attempts))
        raise error

    return attempt, attempts


@pytest.mark.parametrize(
    "error",
    [
        StaleWriteError(_ROW_2, _KEY_2, 1, 0),
        MissingTargetError(_ROW_2, _KEY_2, 1, 0),
    ],
    ids=["stale-write", "missing-target"],
)
def test_a_non_retriable_shortfall_surfaces_after_one_attempt_with_budget_left(
    error: WriteEffectError,
) -> None:
    # Outside the loop's caught set entirely, which is stronger than being
    # classified non-retriable: there is no opt-in, and no `extra_retriable`
    # extension, that could turn one of these into a re-execution.
    attempt, attempts = _raising(error)
    with pytest.raises(type(error)):
        run_with_retry(attempt, retries=10, extra_retriable=lambda _exc: True)
    assert len(attempts) == 1


def test_the_retriable_conflict_is_the_one_shortfall_the_loop_can_re_execute() -> None:
    # The contrast that gives the verdict above its meaning: the same loop, the
    # same budget, and a gate that came up short IS re-run — but only where the
    # unit of work opted in, which is what `extra_retriable` carries.
    attempt, attempts = _raising(OptimisticLockConflictError(_ROW_2, _KEY_2, 1, 0))
    with pytest.raises(OptimisticLockConflictError):
        run_with_retry(attempt, retries=2, extra_retriable=lambda _exc: True)
    assert len(attempts) == 3  # the first attempt plus its two re-executions


def test_an_un_opted_in_conflict_still_surfaces_after_one_attempt() -> None:
    # The same recognized conflict, the same budget, and no opt-in: the loop
    # catches it and declines to re-execute, so the caller sees it after the
    # first attempt exactly as an unrecognized failure would surface.
    attempt, attempts = _raising(OptimisticLockConflictError(_ROW_2, _KEY_2, 1, 0))
    with pytest.raises(OptimisticLockConflictError):
        run_with_retry(attempt, retries=10)
    assert len(attempts) == 1
