"""Per-test ownership for Database Roots used by execution helpers."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar

from parallax.snapshot.handle import Database

_ROOTS: ContextVar[ExitStack | None] = ContextVar("parallax_test_database_roots", default=None)


@contextmanager
def close_owned_roots() -> Generator[None]:
    """Install the owner that closes every root registered by this test."""
    with ExitStack() as roots:
        token = _ROOTS.set(roots)
        try:
            yield
        finally:
            _ROOTS.reset(token)


def own_root[Authorization](root: Database[Authorization], /) -> Database[Authorization]:
    """Retain ``root`` until the current test exits."""
    roots = _ROOTS.get()
    if roots is None:
        root.close()
        raise RuntimeError("own_root requires the per-test root owner")
    return roots.enter_context(root)
