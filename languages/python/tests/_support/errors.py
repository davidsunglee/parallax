"""The assertion every suite makes about a Parallax error: its class and its code."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import pytest

from parallax.core import ParallaxError

__all__ = ["raises_code"]


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
