from __future__ import annotations

import datetime as _dt
from collections.abc import Sequence

from parallax.core.base import normalize_instant

__all__ = ["ClockExhaustedError", "FixedClock", "ScriptedClock"]


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


class ClockExhaustedError(RuntimeError):
    """A :class:`ScriptedClock` was asked for another instant past its script.

    A story's own authoring convention is one corpus writeSequence entry = one
    flushing ``db.transact`` call = one scripted instant, in entry order (the
    engine's own demarcation) — reaching this error means a story
    consumed more flushing transactions than it scripted instants for, never a
    transient condition to retry past.
    """


class ScriptedClock:
    """A :class:`~parallax.core.unit_work.Clock` yielding a FIXED, ORDERED
    sequence of instants — one per call to :meth:`now`, never the same instant
    twice.

    Construct one FRESH instance per story run (:data:`~parallax.conformance.
    stories.WriteStory.clock` is a zero-argument FACTORY for exactly this
    reason): the fake-port no-drift guard and the real-Postgres story runner
    each drive their own story execution independently, and sharing one
    mutable scripted-clock instance across them would let one consumer's own
    reads silently exhaust the other's script.
    """

    __slots__ = ("_instants", "_next")

    def __init__(self, instants: Sequence[_dt.datetime]) -> None:
        if not instants:
            raise ValueError("a ScriptedClock needs at least one instant")
        self._instants = tuple(normalize_instant(instant) for instant in instants)
        self._next = 0

    def now(self) -> _dt.datetime:
        if self._next >= len(self._instants):
            raise ClockExhaustedError(
                f"ScriptedClock exhausted after {len(self._instants)} scripted instant(s) — "
                "a writeSequence story scripts exactly one instant per flushing db.transact "
                "call, in entry order; it never reuses the last instant"
            )
        instant = self._instants[self._next]
        self._next += 1
        return instant
