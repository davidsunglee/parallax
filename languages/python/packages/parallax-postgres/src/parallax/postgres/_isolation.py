"""Postgres' own spelling of each portable Isolation Level (m-db-port)."""

from __future__ import annotations

from typing import Final

from parallax.core.db_port import IsolationLevel

__all__ = ["isolation_spelling"]

_SPELLING: Final[dict[IsolationLevel, str]] = {
    "read_committed": "read committed",
    "repeatable_read": "repeatable read",
    "serializable": "serializable",
}


def isolation_spelling(level: IsolationLevel) -> str:
    """Postgres' name for ``level``, as `transaction_isolation` accepts it.

    Postgres forbids each portable level's anomalies under its own name for it, so
    the mapping is a rename; what makes it worth stating once is that every caller
    opening a transaction at a declared level needs it, and a level spelled at each
    of those sites could be spelled differently at each of them.
    """
    return _SPELLING[level]
