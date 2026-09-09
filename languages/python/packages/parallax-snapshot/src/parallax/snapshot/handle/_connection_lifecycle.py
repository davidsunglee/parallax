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

Both ends are also where the operation's resource observation happens, because
the observed activity and the resource call are the same two moments. Each end
opens its own scope under the owning activity, so an Acquisition and a Release
are siblings of the execution work between them rather than a lease enclosing
it. Each also tells its scope where the resource call came back, so what these
functions then read off the resource — the cleanup fact the call left behind —
falls outside the interval the scope reports and outside the hold that interval
bounds. Observation never changes what the resource does: cleanup that has to
happen happens whether or not the scope around it could be delivered, and a
cleanup fact no Handler received falls back to the restricted resource log.
"""

from __future__ import annotations

from parallax.core.db_port import ConnectionContext, DatabaseConnection, report_resource_issues
from parallax.core.execution_lifecycle._activity import (
    ConnectionAcquisitionActivity,
    ConnectionOwnerActivity,
    ConnectionReleaseActivity,
)

__all__ = ["enter_connection", "exit_connection"]


def enter_connection(
    resource: ConnectionContext, owner: ConnectionOwnerActivity
) -> tuple[DatabaseConnection, int | None]:
    """Acquire ``resource``'s connection under ``owner``, or raise having
    consumed its cleanup facts.

    Answers the scoped execution and the moment the hold began — ``None`` where
    nothing measured it, which is every operation nobody is observing. The
    caller carries that moment to :func:`exit_connection` rather than any object
    holding it, because it is one integer belonging to one operation and a
    timing record would be a second lifetime to keep right.

    A failed entry has already run cleanup over whatever partial ownership it
    took — Python never calls ``__exit__`` for an ``__enter__`` that raised, so
    the context does it itself — and what that cleanup ESTABLISHED is read back
    here rather than being left on a value nobody looks at again. Reading it is
    the point: the cleanup ran, which is not the same as everything having been
    reclaimed. The acquisition failure itself propagates untouched, so the
    owning activity fails with the reason acquisition gave rather than with
    anything about the cleanup.

    The one case that is not simply "acquire or fail" is an acquisition that
    SUCCEEDED and whose observation then did not survive. The connection is
    real, nothing will ever be handed it, and it goes straight back — cleanup
    the caller can no longer be told about, which is what the fallback log is
    for.
    """
    acquisition = owner.acquisition()
    acquired: DatabaseConnection | None = None
    try:
        with acquisition:
            try:
                acquired = resource.__enter__()
            except BaseException:
                acquisition.call_returned()
                acquisition.unacquired(resource.cleanup_result)
                raise
            acquisition.call_returned()
    except BaseException:
        if acquired is not None:
            _leave(resource, None)
        _report_unheard(acquisition, resource)
        raise
    return acquired, acquisition.held_since_ns


def exit_connection(
    resource: ConnectionContext,
    owner: ConnectionOwnerActivity,
    held_since_ns: int | None,
    failure: BaseException | None,
) -> None:
    """Release ``resource``'s connection under ``owner``, reporting problems
    rather than raising them.

    ``failure`` is what ended the operation, or ``None`` where it completed, and
    it is passed through so the context sees the same exception the caller does.
    ``held_since_ns`` is what :func:`enter_connection` answered for this same
    acquisition, so the release reports a hold measured from where the
    acquisition ended rather than from where this call began.

    Nothing here re-raises a resource problem: a successful read, an exhausted
    stream, and a committed transaction all keep their outcomes whatever the
    release ran into, and an operation that failed keeps ITS failure rather than
    having it replaced by a problem discovered while cleaning up after it.

    Observation cannot prevent the release either. The Release scope's own
    opening is the only part of this that can refuse to happen, and when it does
    the connection still goes back — unobserved, and reported to the restricted
    log like every cleanup fact nobody heard.
    """
    release = owner.release(held_since_ns)
    attempted = False
    try:
        with release:
            try:
                attempted = True
                _leave(resource, failure)
            finally:
                release.call_returned()
                release.relinquished(resource.cleanup_result)
    except BaseException:
        if not attempted:
            _leave(resource, failure)
        _report_unheard(release, resource)
        raise
    _report_unheard(release, resource)


def _leave(resource: ConnectionContext, failure: BaseException | None) -> None:
    """Exit ``resource``, telling it what ended the operation it served."""
    resource.__exit__(
        type(failure) if failure is not None else None,
        failure,
        failure.__traceback__ if failure is not None else None,
    )


def _report_unheard(
    scope: ConnectionAcquisitionActivity | ConnectionReleaseActivity, resource: ConnectionContext
) -> None:
    """Log ``resource``'s cleanup facts unless a Handler already received them.

    Initial acceptance is not delivery and neither is invocation: the scope
    answers whether a Handler RETURNED from receiving these facts, and only that
    answer keeps the restricted log from stating what an application has already
    been told. Anything else — no Provider, a quarantined one, a fan-out whose
    every child failed — leaves this the only place the fact can be heard.
    """
    if scope.cleanup_reported:
        return
    report_resource_issues("operation", resource.cleanup_result)
