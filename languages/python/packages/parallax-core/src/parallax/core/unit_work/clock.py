from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from parallax.core.base import normalize_instant

__all__ = ["Clock", "FixedClock", "SystemClock", "TransactionInstant"]


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
    captured managed instant, because the attempt's unit of work owns one instance. A
    retry is a new attempt with a new instance and captures afresh, but only if
    it independently reaches timestamp-requiring work.

    Equality ignores whether the value has been captured: memoization is an
    implementation of the contract, never part of the identity of the flush
    context a plan carries.
    """

    clock: Clock
    _captured: _dt.datetime | None = field(default=None, init=False, repr=False, compare=False)

    def value(self) -> _dt.datetime:
        """This attempt's managed Transaction Instant, capturing it on first call."""
        if self._captured is None:
            self._captured = normalize_instant(self.clock.now())
        return self._captured
