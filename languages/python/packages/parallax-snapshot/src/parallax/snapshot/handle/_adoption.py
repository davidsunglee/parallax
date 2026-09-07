"""``parallax.snapshot.handle._adoption`` — how an execution adopts a Model
Edition, and the failure that carries it.

Every execution that owns its adoption does the same three things: takes the
Serving Model's current selection, opens its lifecycle activity carrying that
edition, and turns an ordinary exception escaping the whole execution into an
:class:`ExecutionFailure` naming the edition it ran under. The first and last
are written here once, and the opening in between belongs to the execution's
own lifecycle seam. One :class:`AdoptedExecution` exists per root execution and
owns "which edition is current for this execution", which is what lets a
transaction adopt afresh for each attempt and still report the final attempt's
edition once.

The rules this module carries: a join or a participating read inherits and
never adopts or wraps, so a failure inside one propagates internally and is
contextualized once at the outer execution; retry classification sees the
underlying error, because the wrap is applied after the retry loop resolves;
a failure already contextualized passes through unchanged; and a control-flow
or fatal exception is never contextualized at all, because it is not an
ordinary failure of the execution.

Names crossing a module boundary are spelled bare; privacy is carried by this
MODULE's leading underscore and by the package's frozen ``__all__``.
"""

from __future__ import annotations

from collections.abc import Callable

from parallax.snapshot.handle._publication import ModelSelection, ServingModel

__all__ = ["AdoptedExecution", "ExecutionFailure"]


class ExecutionFailure(Exception):
    """An ordinary failure escaping an execution, under the edition it adopted.

    :attr:`edition` is always an actual Adopted Edition — there is no
    edition-less variant, because a failure before adoption keeps its own type
    — and :attr:`cause` is the exception that escaped, which is also the
    ``__cause__`` so native chaining reads the same object. A transaction
    invocation reports its final attempt's edition; a rollback that did not
    complete arrives with both of its live errors inside the cause.
    """

    def __init__(self, edition: str, cause: Exception) -> None:
        super().__init__(f"execution under model edition {edition!r} failed: {cause!r}")
        self.edition = edition
        self.cause = cause


class AdoptedExecution:
    """One root execution's adoption of the Serving Model's current selection.

    :meth:`adopt` records the selection the execution runs under from now on,
    and :meth:`contextualized` runs the execution's body and names that
    edition on whatever ordinary failure escapes it. A transaction calls
    :meth:`adopt` once per attempt and :meth:`contextualized` once around the
    whole retry loop, so the edition a failure reports is the last one adopted.
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

    def contextualized[T](self, body: Callable[[], T]) -> T:
        """Run ``body``, naming the adopted edition on an ordinary failure.

        An :class:`ExecutionFailure` that already carries an edition passes
        through, so a nested execution's failure is contextualized exactly
        once, and every other ``BaseException`` propagates untouched.
        """
        try:
            return body()
        except ExecutionFailure:
            raise
        except Exception as exc:
            raise ExecutionFailure(self.edition, exc) from exc
