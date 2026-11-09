from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from parallax.core._execution._publication import ModelSelection, ServingModel

__all__ = ["AdoptedExecution", "ExecutionBoundary"]

ExecutionBoundary = Literal["transaction", "read", "stream"]


class AdoptedExecution:
    """One root execution's adoption of the Serving Model's current selection.

    :meth:`adopt` records the selection the execution runs under from now on,
    and :meth:`noting_edition` runs one boundary's body and notes that edition
    on whatever ordinary failure escapes it. A transaction calls :meth:`adopt`
    once per attempt and :meth:`noting_edition` once around the whole retry
    loop, so the edition a failure is noted with is the last one adopted.
    """

    __slots__ = ("_selection", "_serving")

    def __init__(self, serving: ServingModel) -> None:
        self._serving = serving
        self._selection: ModelSelection | None = None

    def adopt(self) -> ModelSelection:
        """Take the selection currently serving, and retain it as this
        execution's own until the next adoption."""
        selection = self._serving.current()
        self._selection = selection
        return selection

    @property
    def edition(self) -> str:
        """The edition most recently adopted; reading it before the first
        adoption is a programming error rather than an absent value."""
        selection = self._selection
        if selection is None:
            raise RuntimeError("an execution has no edition before it has adopted a selection")
        return selection.edition

    def noting_edition[T](self, boundary: ExecutionBoundary, body: Callable[[], T]) -> T:
        """Run ``body``, noting the adopted edition on an ordinary failure and
        re-raising that same failure.

        Every boundary a failure leaves notes it, so a failure that escapes a
        nested execution carries one note per execution, innermost first.
        Every other ``BaseException`` propagates untouched.
        """
        try:
            return body()
        except Exception as exc:
            exc.add_note(f"raised in a {boundary} under model edition {self.edition!r}")
            raise
