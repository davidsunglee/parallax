from __future__ import annotations

from typing import Final

from parallax.core.dialect import POSTGRES, Dialect

__all__ = ["DIALECT_CATALOG", "dialect_for"]

DIALECT_CATALOG: Final[tuple[str, ...]] = ("postgres", "mariadb")
"""Every Dialect Identity the specification supports, in canonical order.

The catalog is the SPEC's, not this implementation's: a name is listed here
whether or not :func:`dialect_for` can answer with a strategy for it, so a
consumer enumerating the supported Dialects reports a missing one as an explicit
gap rather than silently narrowing the matrix to what it happens to ship.
"""


def dialect_for(name: str) -> Dialect:
    """The pure dialect strategy for ``name`` (postgres is the only concrete one)."""
    if name == "postgres":
        return POSTGRES
    raise ValueError(f"unsupported dialect {name!r}")
