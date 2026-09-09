"""The two typed retention policies a Postgres runtime is opened under.

:class:`PoolOptions` keeps connections between operations; :class:`OnDemandOptions`
keeps none. Which record is supplied selects which behavior the runtime has, so
there is no mode flag to disagree with a setting and no combination that names
idle inventory for a runtime that holds none.

Both are frozen, slotted, keyword-only, and validated at construction, so a
malformed configuration is refused before anything is allocated. Their field
names follow the driver's where the meaning is the same, which makes an
operator's existing knowledge transfer; they are still Parallax records, and the
translation to native parameters happens where the pool is built.

Most of what they carry is the same, so it is declared and validated once and
documented here rather than twice. ``max_size`` is the ceiling on connections in
use at once. ``acquire_timeout`` bounds ONE caller's wait for a connection,
``startup_timeout`` bounds becoming ready before the handle is published, and
``reconnect_timeout`` is how long the runtime's own background retrying keeps
trying to restore capacity; they are three different controls and none of them is
a retry budget for an operation. ``max_waiting`` caps how many callers may queue
at once, with ``0`` meaning the queue is not counted. ``max_lifetime`` retires a
connection by age with native jitter, so a whole generation does not expire at
once. ``validate_on_checkout`` spends a round trip proving a connection still
works before an operation gets it, which is what turns a connection the server
closed while idle into a replacement rather than a failed statement.
``num_workers`` sizes the runtime's own maintenance threads, not application
concurrency.

The defaults are a starting point chosen to be safe rather than fast, and no
benchmark claims them optimal. Tune them from measured occupancy and queue
latency for the deployment they run in.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ["OnDemandOptions", "PoolOptions", "RetentionOptions"]


def _integer(name: str, value: object) -> int:
    """``value`` as a plain ``int``, refusing a Boolean.

    ``bool`` is an ``int`` subclass, so ``max_size=True`` would otherwise
    configure a capacity of one. Nothing else is coerced either: an integral
    float is a different type expressing a different intent, and accepting it
    would make ``max_size=10.0`` and ``max_size=10`` two spellings a reader has
    to know are the same.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} takes an int (got {value!r})")
    return value


def _duration(name: str, value: object) -> float:
    """``value`` as a finite positive number of seconds.

    Integers are accepted and normalized to ``float``, so ``15`` and ``15.0``
    are one value. A Boolean, a nonfinite, a zero, and a negative are each
    refused: zero and infinity would be sentinels for "disabled" and
    "unlimited", and neither is a control this configuration offers.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{name} takes a number of seconds (got {value!r})")
    seconds = float(value)
    if not math.isfinite(seconds):
        raise ValueError(f"{name} takes a finite number of seconds (got {value!r})")
    if seconds <= 0.0:
        raise ValueError(f"{name} takes a positive number of seconds (got {value!r})")
    return seconds


def _set_normalized_fields(options: object, **normalized: object) -> None:
    """Write ``normalized`` back over a frozen record's own fields.

    Validation normalizes as well as refuses — an ``int`` number of seconds
    becomes a ``float``, so ``15`` and ``15.0`` are one value afterwards — and a
    frozen dataclass has no other way to keep what its own ``__post_init__``
    decided.
    """
    for name, value in normalized.items():
        object.__setattr__(options, name, value)


def _flag(name: str, value: object) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name} takes a bool (got {value!r})")
    return value


def _capacity(value: object) -> int:
    capacity = _integer("max_size", value)
    if capacity < 1:
        raise ValueError(f"max_size takes at least 1 connection (got {value!r})")
    return capacity


def _waiting(value: object) -> int:
    waiting = _integer("max_waiting", value)
    if waiting < 0:
        raise ValueError(f"max_waiting takes a nonnegative queue length (got {value!r})")
    return waiting


def _workers(value: object) -> int:
    workers = _integer("num_workers", value)
    if workers < 1:
        raise ValueError(f"num_workers takes at least 1 worker (got {value!r})")
    return workers


@dataclass(frozen=True, slots=True, kw_only=True)
class _SharedRetention:
    """Every setting both retention policies carry, declared and checked once.

    The module docstring says what each one controls. What matters here is that
    there is one declaration of each: a default or a range check kept in both
    records is one that can drift between them.
    """

    max_size: int = 10
    acquire_timeout: float = 15.0
    startup_timeout: float = 30.0
    max_waiting: int = 0
    validate_on_checkout: bool = True
    max_lifetime: float = 3600.0
    reconnect_timeout: float = 300.0
    num_workers: int = 3

    def __post_init__(self) -> None:
        _set_normalized_fields(
            self,
            max_size=_capacity(self.max_size),
            max_waiting=_waiting(self.max_waiting),
            num_workers=_workers(self.num_workers),
            validate_on_checkout=_flag("validate_on_checkout", self.validate_on_checkout),
            acquire_timeout=_duration("acquire_timeout", self.acquire_timeout),
            startup_timeout=_duration("startup_timeout", self.startup_timeout),
            max_lifetime=_duration("max_lifetime", self.max_lifetime),
            reconnect_timeout=_duration("reconnect_timeout", self.reconnect_timeout),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class PoolOptions(_SharedRetention):
    """Keep connections between operations, within a bounded capacity.

    ``min_size`` is the capacity the runtime tries to keep ready and ``max_size``
    the ceiling it may grow to; ``max_idle`` retires capacity above the minimum
    incrementally rather than giving each connection an exact idle deadline.
    Neither that retirement nor retirement by age interrupts a connection an
    operation is using.
    """

    min_size: int = 1
    max_idle: float = 600.0

    def __post_init__(self) -> None:
        super().__post_init__()
        minimum = _integer("min_size", self.min_size)
        if not 0 <= minimum <= self.max_size:
            raise ValueError(
                f"min_size takes 0 through max_size={self.max_size} (got {self.min_size!r})"
            )
        _set_normalized_fields(
            self, min_size=minimum, max_idle=_duration("max_idle", self.max_idle)
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class OnDemandOptions(_SharedRetention):
    """Keep no connection between operations.

    Every acquisition establishes a connection, and releasing one closes it
    unless a caller is already waiting, in which case it may be handed straight
    on. So this bounds concurrency without holding inventory — it does NOT
    promise a brand-new physical connection per operation, and there is no
    ``min_size`` or ``max_idle`` here because there is no inventory for either to
    describe. ``max_lifetime``, ``reconnect_timeout``, and ``num_workers`` still
    apply: they govern the replacement and hand-on paths rather than idle
    retention.

    One establishment behavior is worth knowing before tuning: the driver
    derives its own connection-establishment timeout from whatever remains of
    the acquisition budget, overriding a ``connect_timeout`` from the connection
    string or the environment for that creation. ``acquire_timeout`` is
    therefore the control that matters here, and the two do not compose as
    independent limits.
    """


type RetentionOptions = PoolOptions | OnDemandOptions
"""Either retention policy, as the one thing an adapter is configured with."""
