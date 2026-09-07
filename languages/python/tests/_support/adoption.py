"""The assertion every suite makes about a failure escaping an adopted execution.

An ordinary failure leaves an adopted execution as ``ExecutionFailure``: the
edition that execution adopted, and the error itself as its cause. Every suite
that grades what a callback, a write, a boundary, the retry loop, a standalone
read, or one advance of a standalone delivery raised therefore asserts the same
two-layer shape, and states it once here rather than once per site. ``value``
answers the cause, so an assertion written against the underlying error reads
exactly as it would against a bare raise.
"""

from __future__ import annotations

import re
from collections.abc import Generator
from contextlib import contextmanager

import pytest

from parallax.snapshot.handle import ExecutionFailure

__all__ = ["Contextualized", "raises_contextualized"]


class Contextualized[E: Exception]:
    """What the block raised, in both layers: the ``ExecutionFailure`` and the
    cause it carries. Filled in when the block leaves."""

    __slots__ = ("_failure",)

    def __init__(self) -> None:
        self._failure: ExecutionFailure | None = None

    @property
    def failure(self) -> ExecutionFailure:
        failure = self._failure
        assert failure is not None, "read after the block has left"
        return failure

    @property
    def value(self) -> E:
        """The underlying error, which is also the failure's ``__cause__``."""
        return self.failure.cause  # pyright: ignore[reportReturnType] - narrowed by the type check the block made

    @property
    def edition(self) -> str:
        return self.failure.edition


@contextmanager
def raises_contextualized[E: Exception](
    cause: type[E], *, match: str | None = None
) -> Generator[Contextualized[E]]:
    """Assert the block raises ``ExecutionFailure`` caused by a ``cause``.

    ``match`` is searched in the cause's own text, exactly as ``pytest.raises``
    searches the raised value's, so a site that graded a bare raise grades the
    same message through the wrapper.
    """
    caught: Contextualized[E] = Contextualized()
    with pytest.raises(ExecutionFailure) as excinfo:
        yield caught
    failure = excinfo.value
    assert isinstance(failure.cause, cause), (
        f"expected an ExecutionFailure caused by {cause.__name__}, got {failure.cause!r}"
    )
    assert failure.__cause__ is failure.cause
    assert failure.edition
    if match is not None:
        assert re.search(match, str(failure.cause)), f"{match!r} does not match {failure.cause!r}"
    caught._failure = failure  # pyright: ignore[reportPrivateUsage] - filled by the one factory that builds it
