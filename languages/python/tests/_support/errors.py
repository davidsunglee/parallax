"""The assertion every suite makes about a Parallax error: its class and its code."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import pytest

from parallax.core import ParallaxError

__all__ = ["raises_code", "retry_notes"]


@contextmanager
def raises_code[E: ParallaxError](
    kind: type[E], code: str, *, match: str | None = None
) -> Generator[pytest.ExceptionInfo[E]]:
    """Assert the block raises a ``kind`` whose ``code`` is ``code``.

    ``match`` is searched in the rendered text, exactly as ``pytest.raises``
    searches it.
    """
    with pytest.raises(kind, match=match) as failed:
        yield failed
    assert failed.value.code == code, f"expected {code!r}, got {failed.value.code!r}"


def retry_notes(error: BaseException) -> list[str]:
    """The notes on ``error`` other than the edition notes of the executions it
    left, which the boundary tests grade on their own."""
    return [note for note in getattr(error, "__notes__", []) if not note.startswith("raised in a ")]
