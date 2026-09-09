"""What a runtime publishes for pool-wide observation, stated neutrally.

A runtime that manages a pool keeps bookkeeping an operator wants — how much
capacity exists, how much of it is idle, how many callers are queued — and one
that manages no pool keeps none. :class:`PoolMetricsSource` is the handle to the
former; ``None`` is the honest answer for the latter.

The handle is named here, in the lifetime contract, rather than beside the
observation machinery that consumes it, because it is a property of the RESOURCE:
what may be measured is decided by what the runtime owns, and who is interested
is decided somewhere else entirely.
"""

from __future__ import annotations

from typing import Protocol

__all__ = ["PoolMetricsSource"]


class PoolMetricsSource(Protocol):
    """A stable, read-only handle on one runtime's pool bookkeeping.

    Stable means its identity does not change for the runtime's life, shutdown
    included: a holder keeps the same object throughout, and what changes when
    the runtime closes is what the handle can answer rather than which object
    answers.

    Reading through it never runs SQL, never takes a connection, and never
    exposes a credential or a native connection: it reads bookkeeping the
    runtime already maintains.

    It declares no member yet, because the measurements a sample carries and the
    availability it reports are one contract stated together with the sample
    itself. A runtime publishes the handle; nothing here can be sampled until
    that contract exists.
    """
