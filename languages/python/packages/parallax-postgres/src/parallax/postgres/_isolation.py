from __future__ import annotations

from typing import Final

from parallax.core.db_port import AccessMode, IsolationLevel

__all__ = ["isolation_spelling", "read_only_setting"]

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


_READ_ONLY: Final[dict[AccessMode, str]] = {"read_only": "on", "read_write": "off"}


def read_only_setting(mode: AccessMode) -> str:
    """The `transaction_read_only` value that opens a transaction in ``mode``."""
    return _READ_ONLY[mode]
