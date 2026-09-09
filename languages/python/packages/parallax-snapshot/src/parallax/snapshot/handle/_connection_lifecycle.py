"""``parallax.snapshot.handle._connection_lifecycle`` — the two ends of one
operation's connection, written once.

Three owners bracket a connection: an eager read around its whole execution, a
transaction attempt around its boundary, and a standalone stream from its first
page to its settlement. What each of them does at the two ends is identical, and
getting either end subtly wrong in one of the three is exactly the bug that
leaks a connection under one operation shape and not the others. So the ends
live here as two plain functions, and each owner keeps its own bracket — the
shape of a read, an attempt, and a delivery are genuinely different and no
shared context manager could hold all three.

Neither function raises for a resource problem of its own. Acquisition failure
is the caller's to propagate, because it is the operation failing; release
problems are diagnostic and must never replace what the operation already
established, so they are reported and dropped. That asymmetry is the whole
contract: an operation that could not START is a failure, and an operation that
could not fully let go afterwards is a successful operation with something worth
saying about the resource.
"""

from __future__ import annotations

from parallax.core.db_port import ConnectionContext, DatabaseConnection, report_resource_issues

__all__ = ["enter_connection", "exit_connection"]


def enter_connection(resource: ConnectionContext) -> DatabaseConnection:
    """Acquire ``resource``'s connection, or raise having consumed its cleanup facts.

    A failed entry has already run cleanup over whatever partial ownership it
    took — Python never calls ``__exit__`` for an ``__enter__`` that raised, so
    the context does it itself — and what that cleanup ESTABLISHED is read back
    here rather than being left on a value nobody looks at again. Reading it is
    the point: the cleanup ran, which is not the same as everything having been
    reclaimed. The acquisition failure itself propagates untouched, so the owning
    activity fails with the reason acquisition gave rather than with anything
    about the cleanup.
    """
    try:
        return resource.__enter__()
    except BaseException:
        report_resource_issues("operation", resource.cleanup_result)
        raise


def exit_connection(resource: ConnectionContext, failure: BaseException | None) -> None:
    """Release ``resource``'s connection, reporting problems rather than raising them.

    ``failure`` is what ended the operation, or ``None`` where it completed, and
    it is passed through so the context sees the same exception the caller does.
    Nothing here re-raises: a successful read, an exhausted stream, and a
    committed transaction all keep their outcomes whatever the release ran into,
    and an operation that failed keeps ITS failure rather than having it replaced
    by a problem discovered while cleaning up after it.
    """
    resource.__exit__(
        type(failure) if failure is not None else None,
        failure,
        failure.__traceback__ if failure is not None else None,
    )
    report_resource_issues("operation", resource.cleanup_result)
