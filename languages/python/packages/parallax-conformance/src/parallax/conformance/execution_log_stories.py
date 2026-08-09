"""``parallax.conformance.execution_log_stories`` — the executable API-suite
stories for a joined transaction's LIVE Execution Log (`m-execution-log`).

`m-execution-log-007`'s portable oracle states a **terminal** value graph: one
attempt whose traces span both bodies, the joined write reaching the database
under the outer boundary's own finalization. Everything that makes the joined
lifecycle what it is happens BEFORE that terminal state and is invisible to any
terminal oracle — the log being reachable and `active` while the outer boundary
still runs, the joined result exposing the SAME log object rather than a copy, a
trace appended after the join becoming visible on it, the seal at the outer
boundary, and the two intermediate states surfacing as distinct errors. Those are
what these stories prove, through the public surface, and they are the reason the
case maps to a story at all rather than being colour on a case already graded.

Each story's own source is the Usage Guide snippet and is also what
``tests/api/test_execution_log_story.py`` executes against real Postgres — one
source, both consumers, so the documented spelling cannot drift from the
executed one.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from decimal import Decimal

from parallax.conformance.story_models import Account
from parallax.core.execution_log import (
    ExecutionLog,
    TransactionInProgressError,
    TransactionNotCommittedError,
)
from parallax.snapshot.handle import Database, Transaction, TransactionResult

__all__ = [
    "JoinedLog",
    "LiveJoin",
    "RolledBackJoin",
    "a_joined_result_of_a_rolled_back_transaction_has_no_execution",
    "a_joined_unit_of_work_appends_to_the_outer_live_log",
]

_TARGET_ID = 2
_BUMP = Decimal("1.00")


@dataclass(frozen=True, slots=True)
class LiveJoin:
    """What a joined invocation saw of the outer log while it was still open."""

    status_while_running: str
    traces_before_join: int
    traces_after_join: int
    shares_the_outer_log: bool
    sealed_while_running: bool
    execution_refusal: str


@dataclass(frozen=True, slots=True)
class JoinedLog:
    """The live observations beside the invocation's own terminal result."""

    live: LiveJoin
    result: TransactionResult[ExecutionLog]


@dataclass(frozen=True, slots=True)
class RolledBackJoin:
    """A joined result retained past an outer transaction that rolled back."""

    joined: TransactionResult[None]
    refusal: str


def a_joined_unit_of_work_appends_to_the_outer_live_log(db: Database) -> JoinedLog:
    seen: list[LiveJoin] = []

    def outer(tx: Transaction) -> ExecutionLog:
        live = tx.execution_log
        # The attempt is visible before any work completes, so the log never
        # shows a gap between "the invocation started" and "something happened".
        status = live.final_attempt.status
        current = tx.find(Account.where(Account.id == _TARGET_ID)).result()
        before = len(live.final_attempt.traces)

        def joined_body(joined_tx: Transaction) -> None:
            joined_tx.update(current.edit(balance=current.balance + _BUMP))

        # A joined call shares the outer transaction rather than opening a
        # nested one, so its result carries the SAME live log object — and its
        # common execution view is unavailable until that boundary commits.
        joined = db.transact(joined_body)
        try:
            refusal = type(joined.execution).__name__
        except TransactionInProgressError as exc:
            refusal = type(exc).__name__
        seen.append(
            LiveJoin(
                status_while_running=status,
                traces_before_join=before,
                # The read's trace was appended as it closed; the joined write is
                # still buffered, and reaches the database under the OUTER
                # boundary's own finalization.
                traces_after_join=len(live.final_attempt.traces),
                shares_the_outer_log=joined.execution_log is live,
                sealed_while_running=live.is_sealed,
                execution_refusal=refusal,
            )
        )
        return live

    result = db.transact(outer)
    return JoinedLog(live=seen[0], result=result)


def a_joined_result_of_a_rolled_back_transaction_has_no_execution(
    db: Database,
) -> RolledBackJoin:
    retained: list[TransactionResult[None]] = []

    def outer(tx: Transaction) -> None:
        current = tx.find(Account.where(Account.id == _TARGET_ID)).result()

        def joined_body(joined_tx: Transaction) -> None:
            joined_tx.update(current.edit(balance=current.balance + _BUMP))

        retained.append(db.transact(joined_body))
        raise RuntimeError("the outer boundary aborts after the joined body returned")

    with contextlib.suppress(RuntimeError):
        db.transact(outer)
    joined = retained[0]
    # The joined body returned, but the transaction it joined never committed, so
    # the common execution view stays unavailable — under a DIFFERENT refusal
    # from the still-running one.
    try:
        refusal = type(joined.execution).__name__
    except TransactionNotCommittedError as exc:
        refusal = type(exc).__name__
    return RolledBackJoin(joined=joined, refusal=refusal)
