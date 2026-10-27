from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from types import MappingProxyType

from parallax.core.metamodel import EntityIdentity

__all__ = ["TemporalConflictError"]


class TemporalConflictError(RuntimeError):
    """Stored temporal history moved where the attempt's Transaction Instant
    cannot follow it.

    ``instant`` is the attempt's Transaction Instant. ``key`` names the object
    by its primary key where the refusing path knows it, and ``stored_bound`` is
    the stored Transaction-Time start the instant failed to follow where the
    refusal compared one. A retry is a new attempt with a fresh instant and a
    fresh read of stored history, so this is a recoverable conflict.
    """

    def __init__(
        self,
        entity: EntityIdentity,
        instant: dt.datetime,
        *,
        key: Mapping[str, object] | None = None,
        stored_bound: dt.datetime | None = None,
    ) -> None:
        self.entity = entity
        self.instant = instant
        self.key = None if key is None else MappingProxyType(dict(key))
        self.stored_bound = stored_bound
        named = "" if key is None else f" — key={dict(key)!r}"
        bound = "" if stored_bound is None else f", stored start {stored_bound.isoformat()}"
        super().__init__(
            f"{entity.name}: the Transaction Instant {instant.isoformat()} does not follow "
            f"stored temporal history{named}{bound}"
        )
