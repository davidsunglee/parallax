"""The Clock Strategy — the injectable processing-instant source (m-unit-work, ADR 0010).

A temporal write's **Transaction-Time instant** (its ``in_z``) is never authored on a
write instruction: it is supplied at flush from the unit of work's configured
clock, so no caller-facing shape can smuggle one in. The default clock reads the
system UTC time; a :class:`FixedClock` pins a chosen instant — the path the M4
conformance runner uses to pin a case's authored Transaction-Time instant, and the path
unit tests use for a deterministic flush.

The clock yields a normalized ``timestamp`` (aware UTC, microsecond) via
:meth:`Clock.now`; :func:`instant_literal` renders it to the canonical neutral
instant string the flush plan carries as context (the write-instruction
``instant`` wire form, matching the ISO instants the corpus authors and the read
path binds). ``m-unit-work`` depends only on ``m-op-algebra`` / ``m-db-port`` and,
transitively, ``m-core`` — from which the normalization rule comes.
"""

from __future__ import annotations

import datetime as _dt
from typing import Protocol, runtime_checkable

from parallax.core.base import normalize_instant

__all__ = ["Clock", "FixedClock", "SystemClock", "instant_literal"]


@runtime_checkable
class Clock(Protocol):
    """The processing-instant source a unit of work reads at flush."""

    def now(self) -> _dt.datetime:
        """The current Transaction-Time instant as an aware UTC ``datetime``."""
        ...


class SystemClock:
    """The default clock: the system's current UTC instant (aware, microsecond)."""

    __slots__ = ()

    def now(self) -> _dt.datetime:
        return _dt.datetime.now(_dt.UTC)


class FixedClock:
    """A clock pinned to one instant — deterministic flush timing.

    The instant is normalized (aware UTC, microsecond) on construction, so a naive
    datetime is rejected here rather than at the database. This is the clock the M4
    conformance path injects, pinned to a case's authored Transaction-Time instant.
    """

    __slots__ = ("_instant",)

    def __init__(self, instant: _dt.datetime) -> None:
        self._instant = normalize_instant(instant)

    def now(self) -> _dt.datetime:
        return self._instant


def instant_literal(value: _dt.datetime) -> str:
    """Render a Transaction-Time instant to the canonical neutral instant string.

    The plan carries the Transaction-Time instant as context (never as an instruction
    field); this is its wire form — the same ISO-8601 UTC spelling the corpus
    authors (`2024-06-01T00:00:00+00:00`) and the read path binds.
    """
    return normalize_instant(value).isoformat()
