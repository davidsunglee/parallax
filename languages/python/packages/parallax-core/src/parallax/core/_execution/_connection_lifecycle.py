from __future__ import annotations

from typing import Literal

from parallax.core._execution._routing import OperationRouting
from parallax.core.execution_lifecycle._activity import (
    ConnectionAcquisitionActivity,
    ConnectionOwnerActivity,
    ConnectionReleaseActivity,
)
from parallax.core.internal.db_port import (
    ConnectionContext,
    DatabaseConnection,
    report_resource_issues,
)

__all__ = ["TransactionPreparation", "enter_connection", "exit_connection"]


def enter_connection(
    resource: ConnectionContext, owner: ConnectionOwnerActivity, routing: OperationRouting
) -> tuple[DatabaseConnection, int | None]:
    """Acquire ``resource``'s connection under ``owner``, or raise having
    consumed its cleanup facts.

    ``resource`` is the context ``routing`` created for this acquisition. The
    route it selected is recorded on the acquisition activity and on
    ``routing`` whichever way entry ends, so the operation's later
    acquisitions request what that selection requires.

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
    acquisition = owner.acquisition(routing.policy)
    acquired: DatabaseConnection | None = None
    try:
        with acquisition:
            try:
                acquired = resource.__enter__()
            except BaseException:
                acquisition.call_returned()
                selection = resource.selection
                routing.record(selection)
                acquisition.unacquired(resource.cleanup_result, selection)
                raise
            acquisition.call_returned()
            selection = resource.selection
            routing.record(selection)
            acquisition.acquired(selection)
    except BaseException:
        if acquired is not None:
            _leave(resource, None)
        _report_unheard(acquisition, resource)
        raise
    return acquired, acquisition.held_since_ns


class TransactionPreparation:
    """One outer attempt's acquisition, settled only once its boundary has opened.

    An attempt's connection is not finished being prepared when the context's
    entry returns: the native ``BEGIN`` is still to come, and a lease the
    adapter is still setting up may change route there or fail. So the
    acquisition stays open across the boundary's opening and settles exactly
    once — :meth:`granted` on entry to the transaction body, before anything
    of the attempt exists, or :meth:`unprepared` where the boundary never
    opened. A failure while entering settles at once, as any acquisition's
    does. Nothing modeled ever runs inside the open acquisition: the body's
    first act is to settle it.

    An unprepared lease is cleaned up here, as the failed acquisition's own
    cleanup, so its owner opens no Release for it; a granted one is released
    by the owner as every lease is.
    """

    __slots__ = ("_acquisition", "_resource", "_routing", "_state")

    def __init__(
        self, resource: ConnectionContext, owner: ConnectionOwnerActivity, routing: OperationRouting
    ) -> None:
        self._resource = resource
        self._routing = routing
        self._acquisition = owner.acquisition(routing.policy)
        self._state: Literal["unentered", "pending", "granted", "unprepared"] = "unentered"

    @property
    def pending(self) -> bool:
        """Whether the lease was entered and is not yet settled either way."""
        return self._state == "pending"

    @property
    def releasable(self) -> bool:
        """Whether the lease was granted, and so is its owner's to release."""
        return self._state == "granted"

    @property
    def held_since_ns(self) -> int | None:
        """When the lease's entry returned, for an acquisition that measured it."""
        return self._acquisition.held_since_ns

    def enter(self) -> DatabaseConnection:
        """Open the acquisition and enter the lease, or raise having settled both."""
        acquisition = self._acquisition
        resource = self._resource
        acquisition.__enter__()
        self._state = "pending"
        try:
            connection = resource.__enter__()
        except BaseException as failure:
            acquisition.call_returned()
            self._settle_failed(failure, entered=False)
            raise
        acquisition.call_returned()
        return connection

    def granted(self) -> None:
        """Settle the acquisition as granted, on the route the lease ended on."""
        self._state = "granted"
        acquisition = self._acquisition
        acquisition.prepared()
        selection = self._resource.selection
        self._routing.record(selection)
        acquisition.acquired(selection)
        acquisition.__exit__(None, None, None)

    def unprepared(self, failure: BaseException) -> None:
        """Settle the acquisition as failed by ``failure``, the boundary that
        never opened, cleaning its lease up once as that acquisition's own.

        The acquisition's duration ends once that cleanup has answered, however
        it ends, because the cleanup is the failed acquisition's own work."""
        self._settle_failed(failure, entered=True)

    def _settle_failed(self, failure: BaseException, *, entered: bool) -> None:
        self._state = "unprepared"
        acquisition = self._acquisition
        resource = self._resource
        try:
            if entered:
                try:
                    _leave(resource, failure)
                finally:
                    acquisition.prepared()
        finally:
            try:
                selection = resource.selection
                self._routing.record(selection)
                acquisition.unacquired(resource.cleanup_result, selection)
            finally:
                try:
                    acquisition.__exit__(type(failure), failure, failure.__traceback__)
                finally:
                    _report_unheard(acquisition, resource)


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
