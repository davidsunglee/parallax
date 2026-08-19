"""``parallax.conformance.execution_lifecycle_stories`` — the executable
API-suite story for observing a joined transaction (`m-execution-lifecycle`).

`m-execution-lifecycle-006`'s portable oracle states the whole delivered stream,
which is what that case grades. What no oracle can state is the SPELLING an
application reaches it through: a Provider named at composition, one fresh
Handler per Root Execution, and events arriving while the work runs rather than
a record read back after it. That spelling is the story, and it is why the case
maps to one at all rather than being colour on a case already graded.

The story is the Provider, the Handler, and the call together — the snippet
:func:`joined_lifecycle_snippet` renders is all three sources — and it is also
what ``tests/api/test_execution_lifecycle_story.py`` executes against real
Postgres, so the documented spelling cannot drift from the executed one.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from decimal import Decimal

from parallax.conformance.story_models import Account
from parallax.core.db_port import DbPort
from parallax.core.entity import DomainModel
from parallax.core.execution_lifecycle import (
    ExecutionEvent,
    ExecutionLifecycleHandler,
    ExecutionLifecycleHandlerError,
    JoinedInvocation,
    RootExecution,
    TransactionAttemptStarted,
    TransactionInvocationStarted,
)
from parallax.snapshot import connect
from parallax.snapshot.handle import Transaction

__all__ = [
    "JoinedShape",
    "JoinedShapeHandler",
    "JoinedShapeProvider",
    "a_joined_unit_of_work_is_observed_inside_the_outer_attempt",
    "joined_lifecycle_snippet",
]

_TARGET_ID = 2
_BUMP = Decimal("1.00")


class JoinedShapeHandler:
    """One Root Execution's Handler: two counters and no event kept past its call.

    A Handler receives its root's events synchronously and serially, so per-root
    state belongs here — and stays bounded, because what an application wants
    from a stream is almost never the stream.
    """

    def __init__(self) -> None:
        self.attempts = 0
        self.joined_parents: list[int | None] = []

    def handle(self, event: ExecutionEvent, /) -> None:
        if isinstance(event, TransactionAttemptStarted):
            self.attempts += 1
        elif isinstance(event, TransactionInvocationStarted) and isinstance(
            event.invocation, JoinedInvocation
        ):
            self.joined_parents.append(event.parent_activity_id)


class JoinedShapeProvider:
    """The one composition seam: a fresh Handler for each accepted root.

    Returning ``None`` here would decline the root outright. Everything shared
    across roots — configuration, exporters — belongs on the Provider and must
    be concurrency-safe, because ``open`` may run for several roots at once.
    """

    def __init__(self) -> None:
        self.handlers: list[JoinedShapeHandler] = []

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        handler = JoinedShapeHandler()
        self.handlers.append(handler)
        return handler

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        raise AssertionError(f"this story's Handler must not fail: {error.diagnostic.message}")


@dataclass(frozen=True, slots=True)
class JoinedShape:
    """What one Handler saw of a joined invocation, and what the caller got back."""

    roots: int
    attempts: int
    joined_parent_is_the_attempt: bool
    balance: Decimal


def a_joined_unit_of_work_is_observed_inside_the_outer_attempt(
    port: DbPort, model: DomainModel
) -> JoinedShape:
    """A joined call is an activity under the OUTER attempt and runs no attempt
    of its own — observed through an installed Provider, while the work runs.

    ``port`` is the shipped adapter over the story database, which holds the
    seeded account row the joined body bumps. Nothing the transaction returns
    describes what it did: the callback's value comes back directly, so what the
    Handler collected while the boundary ran is the whole account of it.
    """
    provider = JoinedShapeProvider()
    db = connect(port, model, lifecycle_provider=provider)

    def outer(tx: Transaction) -> Account:
        current = tx.find(Account.where(Account.id == _TARGET_ID)).result()

        def joined_body(joined_tx: Transaction) -> Account:
            # A joined call shares the outer transaction rather than opening a
            # nested one, so its write buffers on the SAME unit of work and
            # reaches the database in the outer boundary's pre-commit batch.
            bumped = current.edit(balance=current.balance + _BUMP)
            joined_tx.update(bumped)
            return bumped

        return db.transact(joined_body)

    committed = db.transact(outer)

    handler = provider.handlers[0]
    return JoinedShape(
        roots=len(provider.handlers),
        attempts=handler.attempts,
        # A joined invocation's parent is the ATTEMPT that was running when the
        # call was made — activity 2 here — never the outer invocation itself.
        joined_parent_is_the_attempt=handler.joined_parents == [2],
        balance=committed.balance,
    )


def joined_lifecycle_snippet() -> str:
    """The story's own source — the Usage Guide snippet that cannot drift.

    The Handler, the Provider, and the call are one story: a snippet showing the
    call alone would document the seam without showing what an application puts
    behind it.
    """
    return "\n\n\n".join(
        inspect.getsource(part).rstrip("\n")
        for part in (
            JoinedShapeHandler,
            JoinedShapeProvider,
            a_joined_unit_of_work_is_observed_inside_the_outer_attempt,
        )
    )
