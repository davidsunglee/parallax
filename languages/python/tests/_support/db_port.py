"""The transaction outcome a fake ``m-db-port`` reports.

A fake port has no boundary of its own: nothing can fail at its begin, its
commit, or its rollback, so every transaction it runs ends exactly as the body
did. Routing every double through one helper keeps that reading in one place
rather than restating it in three dozen fakes — and makes the outcome
construction one edit when those doubles are consolidated.

A double that DOES script a boundary failure builds the outcome itself, beside
the fault it is scripting.
"""

from __future__ import annotations

from collections.abc import Callable

from parallax.core.db_port import (
    CallbackRaised,
    Committed,
    DbPort,
    RolledBack,
    TransactionOutcome,
)

__all__ = ["body_outcome"]


def body_outcome[T](port: DbPort, body: Callable[[DbPort], T]) -> TransactionOutcome[T]:
    """Run ``body`` on ``port`` and report what the body alone decided.

    Committed with its value, or rolled back carrying the exception it raised —
    including a base-level one, which a fake boundary undoes as readily as any
    other and which the composition root re-raises from the outcome.
    """
    try:
        return Committed(body(port))
    except BaseException as raised:
        return RolledBack(CallbackRaised(raised))
