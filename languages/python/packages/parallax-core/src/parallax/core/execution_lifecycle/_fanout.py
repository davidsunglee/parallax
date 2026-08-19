"""Composing several Providers into the one seam ``connect`` accepts.

Fan-out is a PROVIDER concern rather than a publisher one. A publisher owns one
root's correlation and its single Handler; a fan-out answers a composite Handler
that owns child ordering and per-child quarantine, so neither has to know about
the other and the containment rules stay written once each.

One event object reaches every child. Nothing is cloned per child, which is what
keeps the borrowed Lowered Statement a single value and delivery work linear in
the number of active Providers.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from parallax.core.execution_lifecycle._activity import (
    ExecutionLifecycleHandler,
    ExecutionLifecycleProvider,
    report_to,
)
from parallax.core.execution_lifecycle._diagnostics import diagnostic_for, qualified_type
from parallax.core.execution_lifecycle._errors import ExecutionLifecycleHandlerError
from parallax.core.execution_lifecycle._events import ExecutionEvent, RootExecution

__all__ = ["FanoutLifecycleProvider"]


@dataclass(frozen=True, slots=True)
class _FanoutChild:
    """One accepted child of a fan-out, and where in the fan-out tree it sits.

    ``position`` is the zero-based child positions descended through to reach
    this Handler, so it is what a Handler Error reports as its nested fan-out
    path. ``provider`` is the Provider that opened ``handler`` and therefore the
    one told when it fails.
    """

    position: tuple[int, ...]
    provider: ExecutionLifecycleProvider
    handler: ExecutionLifecycleHandler


class _CompositeHandler:
    """The one Handler a fan-out's root is given, over the children it opened.

    Children receive the same event object in declaration order. A child that
    fails ordinarily is dropped for the remainder of the root and its own
    Provider is told out of band, while every later sibling still receives that
    same event and every future one — which is what makes the isolation an
    ordering property rather than a best effort. A control-flow or fatal
    exception is not contained here at all: it propagates to the publisher,
    which deactivates the whole root.
    """

    __slots__ = ("_children", "_execution_id")

    def __init__(self, execution_id: UUID, children: Sequence[_FanoutChild]) -> None:
        self._execution_id = execution_id
        self._children = tuple(children)

    def handle(self, event: ExecutionEvent, /) -> None:
        live = self._children
        survivors: list[_FanoutChild] | None = None
        for index, child in enumerate(live):
            try:
                child.handler.handle(event)
            except Exception as failure:
                # The survivor list is built only once a child has actually
                # failed, so the path every event takes while nothing fails
                # allocates nothing and rebinds nothing.
                if survivors is None:
                    survivors = list(live[:index])
                report_to(child.provider, self._error(event, child, failure))
                continue
            if survivors is not None:
                survivors.append(child)
        if survivors is not None:
            self._children = tuple(survivors)

    def _error(
        self, event: ExecutionEvent, child: _FanoutChild, failure: Exception
    ) -> ExecutionLifecycleHandlerError:
        return ExecutionLifecycleHandlerError(
            execution_id=self._execution_id,
            sequence=event.sequence,
            activity_id=event.activity_id,
            handler_type=qualified_type(child.handler),
            fanout_path=child.position,
            diagnostic=diagnostic_for(failure),
        )


class FanoutLifecycleProvider:
    """Several Providers behind the one ``lifecycle_provider`` seam.

    Children open in declaration order and the fan-out declines a root only when
    every child declined it, so one Provider sampling its roots does not silence
    the others. A child whose opening fails ordinarily aborts the root: the
    Handlers already opened for it are discarded unused, because a root no
    Provider will observe completely is worse than one none observes at all.

    Construction rejects the same Provider OBJECT more than once — it would be
    told about one root twice and its Handler would see every event twice —
    while two distinct Providers deliberately sharing one backend are fine, and
    are how an application fans one exporter out under different configurations.

    Fan-outs nest: a child that is itself a fan-out contributes its own children
    to the tree, and each of them reports under the full path descended to reach
    it rather than under a position relative to the nearest enclosing fan-out.
    """

    __slots__ = ("_providers",)

    def __init__(self, providers: Sequence[ExecutionLifecycleProvider], /) -> None:
        composed = tuple(providers)
        if not composed:
            raise ValueError(
                "a fan-out lifecycle provider composes at least one provider; installing "
                "none is what leaving lifecycle_provider unset already means"
            )
        for index, provider in enumerate(composed):
            if any(earlier is provider for earlier in composed[:index]):
                raise ValueError(
                    "a fan-out lifecycle provider composes each provider at most once, and "
                    f"the provider at position {index} is already composed earlier; two "
                    "distinct providers may share a backend, but one object twice would be "
                    "opened twice for one root"
                )
        self._providers = composed

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        return self._opened_at(execution, ())

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        """Tell every composed Provider about a failure of the composite itself.

        A fan-out opens no Handler of its own beyond the composite that drives
        its children, and that composite belongs to all of them rather than to
        any one: it contains each child's ordinary failure and reports it to
        that child's own Provider directly. So a report arriving HERE describes
        the composite, whose loss costs every composed Provider the rest of the
        root, and telling each of them is what keeps that from being silent.
        """
        for provider in self._providers:
            report_to(provider, error)

    def _opened_at(
        self, execution: RootExecution, prefix: tuple[int, ...]
    ) -> ExecutionLifecycleHandler | None:
        """The composite for ``execution``, with each child's path under ``prefix``.

        A nested fan-out is opened through this same method rather than through
        its public ``open``, which is the only way it can learn where it sits:
        the position of a Handler in the tree is known by the fan-out ABOVE it,
        and composing the path at open time is what lets a leaf report the whole
        descent rather than its last step.
        """
        children: list[_FanoutChild] = []
        for index, provider in enumerate(self._providers):
            position = (*prefix, index)
            handler = (
                provider._opened_at(execution, position)
                if isinstance(provider, FanoutLifecycleProvider)
                else provider.open(execution)
            )
            if handler is not None:
                children.append(_FanoutChild(position, provider, handler))
        if not children:
            return None
        return _CompositeHandler(execution.id, children)
