"""``parallax.conformance.scripted_clock`` — a harness-owned, ordered-instant Clock.

D-29 (COR-3 Phase 8 increment 7 completion round): every temporal writeSequence
story needs SUCCESSIVE DISTINCT Transaction-Time instants across its own choreography
(one corpus writeSequence entry, one flushing ``db.transact`` call, one Clock
read each — the case-driven engine's own precedent,
:func:`~parallax.conformance.engine.run_write_sequence_case`) — a single
``FixedClock`` (`parallax.core.unit_work.clock`) pins only ONE instant, so it
cannot drive a multi-entry story on its own.

:class:`ScriptedClock` satisfies core's structural, ``runtime_checkable``
``Clock`` protocol (`parallax.core.unit_work.Clock`) without any core change —
this is harness-owned machinery, never a core seam: an ORDERED sequence of
instants, consumed one per :meth:`~ScriptedClock.now` call, in entry order.
Exhaustion raises loudly (:class:`ClockExhaustedError`) rather than silently
repeating the last instant — a silent reuse would corrupt a later entry's own
goldens without any signal at all. Every instant is normalized on construction
(mirroring :class:`~parallax.core.unit_work.clock.FixedClock`'s own rule): a
naive datetime is rejected here, at story-authoring time, never at flush.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Sequence

from parallax.core.base import normalize_instant

__all__ = ["ClockExhaustedError", "ScriptedClock"]


class ClockExhaustedError(RuntimeError):
    """A :class:`ScriptedClock` was asked for another instant past its script.

    A story's own authoring convention is one corpus writeSequence entry = one
    flushing ``db.transact`` call = one scripted instant, in entry order (the
    engine's own demarcation, DQ4) — reaching this error means a story
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
