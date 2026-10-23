"""A zero-row keyed write in Locking mode, and what must NOT happen to it.

The state has no end-to-end witness because no client can reach it: a
Locking-mode keyed write settles zero rows only if its target disappeared while
the read that licenses the write held that row's shared lock, which correct
locking prevents. The claim is therefore pinned here, with no database, no
interference, and no write ingress:

* a versioned keyed write settled UNGATED (the Locking arm) carries the
  never-retriable stale write as its shortfall class, and an unversioned one
  carries the never-retriable missing target;
* the retry policy calls both ineligible, so no retry candidate carries them
  and a caller with retry budget left still surfaces the failure after exactly
  one attempt.

The verdict and the attempt count are asserted separately on purpose: a loop
that never consulted the policy would also surface after one attempt, so the
count alone cannot tell "classified ineligible" from "never asked". What an
observer is told is the classifier's own verdict (`m-execution-lifecycle` — a
Transaction Attempt reports `retryEligible` independently of the remaining
budget), and that is the function asserted here.

The second half is the failure mode worth preventing: a loop that re-ran a
stale write would re-execute the whole unit of work against a cause no re-read
can change. The per-step derivation on its own is ``test_write_planner``'s; what
is composed here is the chain from that derivation, through the affected-row
enforcer, to the retry decision.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest

from parallax.core._execution._planning import build_write_planner
from parallax.core.auto_retry import RetryCandidate, retry_eligible, run_with_retry
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, Metamodel
from parallax.core.unit_work import (
    KeyedWriteInstruction,
    MissingTargetError,
    OptimisticLockConflictError,
    StaleWriteError,
    WriteEffectError,
    WritePlanningRequest,
    enforce_affected_rows,
    object_key,
)
from parallax.core.write_plan import VersionObservation
from parallax.core.write_plan.steps import (
    MISSING_TARGET,
    STALE_WRITE,
    AffectedRows,
    ExactCount,
    KeyTarget,
    PlannedDelete,
    PlannedStep,
    PlannedUpdate,
)
from tests._support.clock_probes import inert_instant
from tests._support.planner_probes import TEST_ACTOR_IDENTITY, observed_buffer, plan_steps
from tests.unit._corpus_model_support import model as corpus_model

_ACCOUNT = corpus_model("account")
_WALLET = corpus_model("wallet")

_ROW_2 = EntityIdentity("parallax.compatibility", "Account")
_KEY_2 = KeyTarget(key_attributes=(AttributeIdentity(_ROW_2, "id"),), key_values=((2,),))


def _locking_policy(
    write: KeyedWriteInstruction, model: Metamodel, *, observed: int | None
) -> tuple[PlannedStep, AffectedRows]:
    """The single step a Locking-mode unit of work plans for ``write``, and the
    Affected Rows Policy it carries."""
    key = object_key(write, model)
    assert key is not None  # every write here names one row of a keyed Entity
    observations = (
        None if observed is None else {key: VersionObservation(observed_version=observed)}
    )
    plan = build_write_planner(model).finalize(
        WritePlanningRequest(
            actor_identity=TEST_ACTOR_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="locking",
            composed_writes=observed_buffer([write], model, observations),
        )
    )
    (step,) = plan_steps(plan)
    assert isinstance(step, PlannedUpdate | PlannedDelete)  # neither write opens a row
    return step, step.affected_rows


@pytest.mark.parametrize(
    "write",
    [
        KeyedWriteInstruction("amend", "Account", ({"id": 2, "balance": Decimal("250.00")},)),
        KeyedWriteInstruction("delete", "Account", ({"id": 2},)),
    ],
    ids=["amend", "delete"],
)
def test_a_versioned_locking_write_reaching_no_row_is_the_non_retriable_stale_write(
    write: KeyedWriteInstruction,
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
        KeyedWriteInstruction("amend", "Wallet", ({"id": 2, "balance": Decimal("250.00")},)),
        KeyedWriteInstruction("delete", "Wallet", ({"id": 2},)),
    ],
    ids=["amend", "delete"],
)
def test_an_unversioned_write_reaching_no_row_is_the_non_retriable_missing_target(
    write: KeyedWriteInstruction,
) -> None:
    # An unversioned Non-Temporal row observes no state, so no gate could have
    # come up short and no version could have moved: what the shortfall says is
    # only that the addressed row is not there.
    step, policy = _locking_policy(write, _WALLET, observed=None)
    assert policy == ExactCount(1, MISSING_TARGET)
    with pytest.raises(MissingTargetError):
        enforce_affected_rows(step, 0)


def _raising(error: WriteEffectError) -> tuple[Callable[[], int], list[int]]:
    """An attempt that rolls back with ``error`` every time, handed to the loop
    the way the transaction runner hands it: as a retry candidate exactly when
    the policy calls it eligible."""
    attempts: list[int] = []

    def attempt() -> int:
        attempts.append(len(attempts))
        if retry_eligible(error):
            raise RetryCandidate(error)
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
    assert not retry_eligible(error)
    attempt, attempts = _raising(error)
    with pytest.raises(type(error)):
        run_with_retry(attempt, retries=10)
    assert len(attempts) == 1


def test_the_retriable_conflict_is_the_one_shortfall_the_loop_can_re_execute() -> None:
    # The contrast that gives the verdict above its meaning: the same loop, the
    # same budget, and a gate that came up short IS re-run until the bound ends.
    conflict = OptimisticLockConflictError(_ROW_2, _KEY_2, 1, 0)
    assert retry_eligible(conflict)
    attempt, attempts = _raising(conflict)
    with pytest.raises(OptimisticLockConflictError) as surfaced:
        run_with_retry(attempt, retries=2)
    assert surfaced.value is conflict
    assert len(attempts) == 3  # the first attempt plus its two re-executions
