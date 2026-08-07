"""The Clock Strategy — the injectable Transaction-Time source.

A temporal write's **Transaction-Time instant** (its ``in_z``) is never authored on a
write instruction: it is supplied at flush from the unit of work's configured
clock, so no caller-facing shape can smuggle one in. The default clock reads the
system UTC time; a :class:`FixedClock` pins a chosen instant for deterministic
conformance runs and unit tests.

The clock yields a normalized ``timestamp`` (aware UTC, microsecond) via
:meth:`Clock.now`; :func:`instant_literal` renders it to the canonical neutral
instant string the Planning Request carries as context (the write-instruction
``instant`` wire form, matching the ISO instants the corpus authors and the read
path binds). :class:`TransactionInstant` is the attempt-owned lazy holder of that
string — the value the Planning Request carries, so that whether the clock is
read at all follows from the work that survives planning. ``m-unit-work`` depends
only on ``m-op-algebra`` / ``m-db-port`` / ``m-temporal-read`` and, transitively,
``m-core`` — from which the normalization rule comes.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from parallax.core.base import normalize_instant

__all__ = ["Clock", "FixedClock", "SystemClock", "TransactionInstant", "instant_literal"]


@runtime_checkable
class Clock(Protocol):
    """The Transaction-Time instant source a unit of work reads at flush."""

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
    datetime is rejected here rather than at the database. Conformance cases inject
    this clock when they author a specific Transaction-Time instant.
    """

    __slots__ = ("_instant",)

    def __init__(self, instant: _dt.datetime) -> None:
        self._instant = normalize_instant(instant)

    def now(self) -> _dt.datetime:
        return self._instant


def instant_literal(value: _dt.datetime) -> str:
    """Render a Transaction-Time instant to the canonical neutral instant string.

    The Planning Request carries the Transaction-Time instant as context (never
    as an instruction field, and never retained in the settled Write Plan); this
    is its wire form — the same ISO-8601 UTC spelling the corpus authors
    (`2024-06-01T00:00:00+00:00`) and the read path binds.
    """
    return normalize_instant(value).isoformat()


@dataclass(slots=True)
class TransactionInstant:
    """One attempt's lazily captured, memoized Transaction Instant.

    Constructing one reads no clock. :meth:`value` captures on first call and
    memoizes, so *whether* the Clock Strategy is consulted follows from the work
    that survives planning rather than from the buffer being nonempty: an empty
    flush, a buffer that coalescing cancels, a net-zero edit, and a flush whose
    surviving writes need no Transaction-Time boundary all leave the clock
    untouched. Every timestamp-requiring write in one attempt — across a forced
    read-your-own-writes flush and the commit flush alike — shares the one
    captured literal, because the attempt's unit of work owns one instance. A
    retry is a new attempt with a new instance and captures afresh, but only if
    it independently reaches timestamp-requiring work.

    Equality ignores whether the value has been captured: memoization is an
    implementation of the contract, never part of the identity of the flush
    context a plan carries.
    """

    clock: Clock
    _captured: str | None = field(default=None, init=False, repr=False, compare=False)

    def value(self) -> str:
        """This attempt's Transaction Instant literal, capturing it on first call."""
        if self._captured is None:
            self._captured = instant_literal(self.clock.now())
        return self._captured
