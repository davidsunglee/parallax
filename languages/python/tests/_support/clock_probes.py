"""Clock Strategy probes for the write-path suites.

A real flush gets its :class:`~parallax.core.unit_work.TransactionInstant` from
the unit of work that owns the attempt. A suite that calls ``plan_flush`` or
the lowering seam directly builds one here instead, over the same ``FixedClock`` a
deterministic ``Database`` is built with — so an assertion over rendered SQL sees
exactly the literal a production flush at that instant would bind.

:class:`CountingClock` is the direct counterpart: it makes *whether* the Clock
Strategy was consulted observable, for the ADR 0010 rule that only surviving
timestamp-requiring work may capture an instant.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from parallax.core.unit_work import FixedClock, TransactionInstant

__all__ = ["INERT_INSTANT_LITERAL", "CountingClock", "inert_instant", "instant_at"]

# The deterministic stand-in for a lowering whose statements bind no
# Transaction-Time instant — the spelling the conformance engine pins a
# non-temporal entry's inert clock value to.
INERT_INSTANT_LITERAL = "1970-01-01T00:00:00+00:00"


def instant_at(literal: str) -> TransactionInstant:
    """An uncaptured Transaction Instant pinned to ``literal``."""
    return TransactionInstant(FixedClock(dt.datetime.fromisoformat(literal)))


def inert_instant() -> TransactionInstant:
    """An uncaptured Transaction Instant no non-temporal lowering ever reads."""
    return instant_at(INERT_INSTANT_LITERAL)


class CountingClock:
    """A clock that yields a scripted instant per read and counts its reads.

    Reading past the script raises ``IndexError`` rather than repeating, so an
    unexpected extra capture fails loudly instead of silently succeeding.
    """

    def __init__(self, instants: Sequence[dt.datetime]) -> None:
        self._instants = tuple(instants)
        self.calls = 0

    def now(self) -> dt.datetime:
        self.calls += 1
        return self._instants[self.calls - 1]
