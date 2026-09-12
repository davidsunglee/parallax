"""Transaction control for the conformance run lanes.

Every write-, read-, or conflict-executing lane drives a boundary through the
shipped ``db.transact`` entry point or straight against a port, and grades what
the callback, the write, the boundary, or the read raised rather than the
contextualized form the handle wraps it in. This module owns that translation,
and the one outcome a caller cannot ask a real database for: a `rollback: true`
step, whose boundary ALWAYS aborts after the unit of work inside it has done
its own work.

A `rollback: true` step's transaction ends by raising a private sentinel, and
:func:`absorbing_rollback` is the only correct way to end that step. The
sentinel and the aborting decorator never leave this module: a lane installs
the decorator through :func:`write_connection` or :func:`write_adapter`,
runs the step, and absorbs the abort around whatever else it entered.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Generator, Sequence

from parallax.conformance._database_control import CaseDatabase
from parallax.conformance._decoration import DecoratingAdapter
from parallax.core.db_port import (
    BeginFailed,
    CallbackRaised,
    CommitFailed,
    Committed,
    DatabaseAdapter,
    DatabaseConnection,
    DocumentReadOrdinals,
    IsolationLevel,
    PipelineStatement,
    RollbackFailed,
    RolledBack,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import Dialect
from parallax.core.unit_work import Concurrency
from parallax.snapshot import handle

__all__ = [
    "absorbing_rollback",
    "committed",
    "transact",
    "underlying",
    "write_adapter",
    "write_connection",
]


class _RollbackStep(Exception):
    """Sentinel raised inside a transaction body to abort a ``rollback: true`` step."""


def underlying[T](execution: Callable[[], T]) -> T:
    """Run one adopted ``execution`` and answer the underlying failure rather
    than its contextualized form.

    What the engine grades is what the callback, the write, the boundary, or
    the read raised — a rollback sentinel, a Write Effect Error, an
    optimistic-lock conflict, a lowering refusal, a Database Error — and an
    :class:`~parallax.snapshot.handle.ExecutionFailure` carries exactly that as
    its cause. Re-raising the cause with its own chain intact is what lets each
    lane keep catching the failure it classifies; the edition the wrapper named
    is the case's own literal, which the lifecycle oracle grades instead.

    The re-raise happens after the handler is left, because raising inside it
    would install the wrapper as the cause's ``__context__`` — overwriting
    whatever the cause was already chained to, and pointing the two at each
    other.
    """
    try:
        return execution()
    except handle.ExecutionFailure as failure:
        cause = failure.cause
    raise cause


def transact[T](
    database: handle.Database,
    body: Callable[[handle.Transaction], T],
    *,
    concurrency: Concurrency | None = None,
    isolation: IsolationLevel | None = None,
) -> T:
    """``db.transact`` as every lane drives it, through :func:`underlying`."""
    return underlying(lambda: database.transact(body, concurrency=concurrency, isolation=isolation))


class _AbortingPort:
    """A pass-through ``m-db-port`` whose transaction ALWAYS aborts, after the
    unit of work inside it has finished its own work.

    Case-only choreography for a `rollback: true` step (`m-case-format`), and
    the sibling of the boundary lane's own fault injector: it arranges an
    outcome a caller cannot ask a real database for. The abort is raised once
    the body returns — after the boundary's pre-commit flush has already put
    the buffered DML on the wire — so the case's own contract is reproduced
    exactly (`m-unit-work` "Abort": "the forced flush is safe precisely because
    it lands inside the still-open atomic scope the abort discards"): the write's
    statements execute, count their round trips on the attempt, and are then
    erased by the provider's rollback.

    Raising HERE rather than inside the transaction callback is what makes the
    flush production's own: a callback that raises leaves the unit of work
    discarding its buffer unflushed, so the DML the case asserts would never
    reach the database at all.

    The cost of raising there is that the boundary has already entered its
    commit phase, so the attempt's own failure record names ``commit`` for a
    durability boundary that never failed, and the sentinel — outside every
    classified family — makes ``retryEligible: false`` a default rather than a
    verdict. No case reads either: what a `rollback: true` case asserts is the
    table state and the round trips, and both come from the calls, not from the
    failure record.
    """

    def __init__(self, inner: DatabaseConnection) -> None:
        self._inner = inner

    @property
    def dialect(self) -> Dialect:
        return self._inner.dialect

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        return self._inner.execute(sql, binds, document_reads)

    def execute_pipeline(self, statements: Sequence[PipelineStatement]) -> list[list[Row]]:
        return self._inner.execute_pipeline(statements)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        return self._inner.execute_write(sql, binds)

    def transaction[T](
        self, body: Callable[[DatabaseConnection], T], *, isolation: IsolationLevel | None = None
    ) -> TransactionOutcome[T]:
        def aborting(conn: DatabaseConnection) -> T:
            body(conn)
            raise _RollbackStep

        return self._inner.transaction(aborting, isolation=isolation)


def write_connection(port: DatabaseConnection, *, rollback: bool) -> DatabaseConnection:
    """``port`` itself, or the aborting decorator around it.

    The framework-only write lane executes its own plan straight on a session
    rather than through a Handle, because no public verb expresses it, so what
    a `rollback: true` step decorates there is that session's execution
    directly. Every statement still reaches ``port`` unchanged; only the
    boundary is decorated, and it ends by raising the sentinel
    :func:`absorbing_rollback` absorbs.
    """
    return _AbortingPort(port) if rollback else port


def write_adapter(port: CaseDatabase, *, rollback: bool) -> DatabaseAdapter:
    """``port``'s own configuration, or the aborting decorator a `rollback: true` step needs.

    The decoration is applied where a connection is acquired rather than to a
    handle, because what aborts is one transaction on one connection: a step
    that rolls back decorates every connection its own Handle acquires and
    nothing else's.
    """
    return DecoratingAdapter(port, _AbortingPort) if rollback else port


def committed[T](outcome: TransactionOutcome[T]) -> T:
    """The value a boundary a lane drove itself committed, or the failure that
    ended it.

    A lane drives a few write choreographies straight against the port instead
    of through ``db.transact``, so it answers the outcome the same way the
    composition root does: a committed value is the result, and any other
    outcome raises what the case is grading — the deliberate rollback sentinel,
    or a genuine failure. A rollback that itself failed chains the two, since no
    case authors that outcome and a run reaching it has an unusable connection.
    """
    match outcome:
        case Committed(value):
            return value
        case BeginFailed(error) | RolledBack(CallbackRaised(error) | CommitFailed(error)):
            raise error
        case RollbackFailed(  # pragma: no cover - no case can break a connection mid-rollback
            CallbackRaised(error) | CommitFailed(error), rollback_error
        ):
            raise error from rollback_error


@contextlib.contextmanager
def absorbing_rollback() -> Generator[None]:
    """The scope a `rollback: true` step ends in.

    The step's boundary aborts by raising the sentinel, through
    :func:`transact` or :func:`committed`, and this is the one place that
    sentinel is absorbed: the step's DML executed and counted its round trips,
    and the abort is the outcome the case asked for rather than a failure.
    Everything else propagates. A context manager rather than a parameter,
    because a lane enters this around whatever else the step entered — a
    staged shadow, a boundary it drove itself — and the absorption has to
    close after all of it.
    """
    with contextlib.suppress(_RollbackStep):
        yield
