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
                release.released(resource.cleanup_result)
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
