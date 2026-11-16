from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from time import monotonic
from typing import Final, TypeIs

from parallax.core.internal.base import InternalError, UsageError
from parallax.core.internal.database_binding import (
    PhysicalSequence,
    ResolvedSequence,
    sequence_ddl,
)
from parallax.core.internal.db_error import DatabaseError
from parallax.core.internal.db_port import (
    ConnectionAcquisitionError,
    ConnectionContext,
    ReservationContextSource,
    Row,
)
from parallax.core.internal.dialect import Dialect, Unsupported
from parallax.core.internal.sql_gen import LoweredStatement

__all__ = [
    "KEY_RESERVATION_INVALID",
    "KEY_SEQUENCE_EXHAUSTED",
    "KEY_SEQUENCE_MISMATCH",
    "KEY_SEQUENCE_MISSING",
    "KeyAllocator",
    "Reserve",
]

KEY_SEQUENCE_MISSING: Final = "key-sequence-missing"
"""A reservation found no sequence where the binding places the allocator."""

KEY_SEQUENCE_MISMATCH: Final = "key-sequence-mismatch"
"""A reservation found a live sequence whose definition the model's declaration
cannot allocate from: another step, bounds outside the key range, or cycling."""

KEY_SEQUENCE_EXHAUSTED: Final = "key-sequence-exhausted"
"""Every key the allocator's key range holds has been reserved."""

KEY_RESERVATION_INVALID: Final = "key-reservation-invalid"
"""The reservation statement answered a row of a shape it never produces."""

_INTEGER_SEQUENCE_TYPES: Final = frozenset({"smallint", "integer", "bigint"})

type Reserve = Callable[[ConnectionContext, LoweredStatement, Callable[[list[Row]], int]], int]
"""How the execution that needs keys runs a reservation: the statement on the
context's own connection, observed as that execution's Read, answering what the
callback makes of the rows it returned."""


@dataclass(slots=True, eq=False)
class _Reservation:
    """The keys one root still holds from one sequence's latest block.

    ``next_key`` is ``None`` until the first reservation and greater than
    ``last_key`` once the block is spent. Every read and write of it happens
    under ``lock``, which a refill holds for its whole duration so a waiter
    wakes to the winner's block.
    """

    lock: threading.Lock = field(default_factory=threading.Lock)
    next_key: int | None = None
    last_key: int = 0

    def take(self, increment_size: int) -> int | None:
        key = self.next_key
        if key is None or key > self.last_key:
            return None
        self.next_key = key + increment_size
        return key


class KeyAllocator:
    """One Database root's key allocator: one reservation per physical sequence
    and allocation settings, shared by every execution of the root.

    A key left in a reservation is a lookup, a lock, and an increment, with no
    SQL and no acquisition. A spent reservation is refilled by one
    reserve-and-check statement on the runtime's reservation capacity, outside
    any application transaction, as a Read of the attempt whose insert needed
    the key. The whole refill — waiting on the reservation, acquiring, setting
    up, the statement, and releasing — spends one ``reservation_timeout``
    budget, and nothing it reserved is handed out unless all of it finished
    within that budget and the live definition it read back allows the
    declaration.

    State is keyed by physical identity and allocation settings, never by a
    logical name or edition, so two bindings naming one allocator differently
    share nothing and a selection keeping a sequence keeps its reservation.
    It grows with the sequences the root has served, not with the work it
    ran.
    """

    __slots__ = ("_dialect", "_lock", "_reservations", "_source", "_statement")

    def __init__(self, source: ReservationContextSource, dialect: Dialect) -> None:
        statement = dialect.reserve_sequence()
        self._dialect = dialect
        self._source = source
        self._statement = None if isinstance(statement, Unsupported) else statement
        self._lock = threading.Lock()
        self._reservations: dict[
            tuple[PhysicalSequence, tuple[int, int, tuple[int, int]]], _Reservation
        ] = {}

    def next_key(self, sequence: ResolvedSequence, reserve: Reserve) -> int:
        """The next key ``sequence`` hands out, reserving a block for it first
        when the root holds none.

        Raises :class:`~parallax.core.internal.db_port.ConnectionAcquisitionError`
        with ``timeout`` when the budget runs out waiting on another refill or
        after the reservation finished, the acquisition's own failure, a
        classified :class:`~parallax.core.internal.db_error.DatabaseError`, or a
        :class:`~parallax.core.internal.base.UsageError` naming a missing,
        incompatible, or exhausted sequence. None of them hands out a key.
        """
        increment_size = sequence.key_sequence.increment_size
        reservation = self._reservation_for(sequence)
        deadline = monotonic() + self._source.reservation_timeout
        if not reservation.lock.acquire(timeout=max(0.0, deadline - monotonic())):
            raise ConnectionAcquisitionError(
                f"waiting on another reservation of {sequence.sql} spent its whole budget",
                reason="timeout",
            )
        try:
            key = reservation.take(increment_size)
            if key is None:
                self._refill(reservation, sequence, deadline, reserve)
                key = reservation.take(increment_size)
                assert key is not None  # a published block holds its first key
            return key
        finally:
            reservation.lock.release()

    def _reservation_for(self, sequence: ResolvedSequence) -> _Reservation:
        identity = (sequence.physical, sequence.allocation_settings)
        with self._lock:
            reservation = self._reservations.get(identity)
            if reservation is None:
                reservation = self._reservations[identity] = _Reservation()
            return reservation

    def _refill(
        self,
        reservation: _Reservation,
        sequence: ResolvedSequence,
        deadline: float,
        reserve: Reserve,
    ) -> None:
        """Reserve ``sequence``'s next block and publish it into ``reservation``
        only once the statement, its check, and its release all finished inside
        ``deadline``."""
        sql = self._statement
        if sql is None:  # pragma: no cover - resolution refuses a sequence such a backend lacks
            raise InternalError(KEY_RESERVATION_INVALID, "this backend reserves no sequence")

        def accepted(rows: list[Row]) -> int:
            first = _checked_first_key(rows, sequence)
            if monotonic() > deadline:
                raise ConnectionAcquisitionError(
                    f"the reservation of {sequence.sql} finished after its budget, so the "
                    "keys it reserved are abandoned",
                    reason="timeout",
                )
            return first

        try:
            first = reserve(
                self._source.new_context(deadline),
                LoweredStatement(sql, (sequence.sql,)),
                accepted,
            )
        except DatabaseError as error:
            if self._dialect.reports_sequence_exhaustion(error.native_code):
                raise _exhausted(sequence) from error
            raise
        key_sequence = sequence.key_sequence
        reservation.next_key = first
        reservation.last_key = min(
            first + (key_sequence.batch_size - 1) * key_sequence.increment_size,
            sequence.key_range[1],
        )


def _checked_first_key(rows: list[Row], sequence: ResolvedSequence) -> int:
    """The block's first key, once the live definition read back beside it is
    one the declaration can allocate from."""
    if not rows:
        raise UsageError(
            KEY_SEQUENCE_MISSING,
            f"no sequence {sequence.sql} exists for allocator {sequence.allocator!r}; create it "
            "where the binding places it before inserting without a key",
        )
    if len(rows) != 1 or len(rows[0]) != 6:
        raise InternalError(
            KEY_RESERVATION_INVALID,
            f"reserving from {sequence.sql} answered {len(rows)} rows of an unexpected shape",
        )
    first, increment, minimum, maximum, cycles, data_type = rows[0]
    if not (
        _is_int(first)
        and _is_int(increment)
        and _is_int(minimum)
        and _is_int(maximum)
        and isinstance(cycles, bool)
        and isinstance(data_type, str)
    ):
        raise InternalError(
            KEY_RESERVATION_INVALID,
            f"reserving from {sequence.sql} answered a row of unexpected types",
        )
    expected = sequence_ddl(sequence)
    low, high = sequence.key_range
    problems: list[str] = []
    if increment != expected.increment:
        problems.append(f"it steps by {increment}, not {expected.increment}")
    if cycles:
        problems.append("it cycles")
    if data_type not in _INTEGER_SEQUENCE_TYPES:
        problems.append(f"it holds {data_type} values")
    if minimum < low or maximum > high:
        problems.append(f"its bounds [{minimum}, {maximum}] leave the key range [{low}, {high}]")
    if problems:
        raise UsageError(
            KEY_SEQUENCE_MISMATCH,
            f"sequence {sequence.sql} cannot serve allocator {sequence.allocator!r} with batch "
            f"size {sequence.key_sequence.batch_size} and increment size "
            f"{sequence.key_sequence.increment_size}: {'; '.join(problems)}; the block it "
            "just reserved is abandoned",
        )
    return first


def _is_int(value: object) -> TypeIs[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _exhausted(sequence: ResolvedSequence) -> UsageError:
    low, high = sequence.key_range
    return UsageError(
        KEY_SEQUENCE_EXHAUSTED,
        f"sequence {sequence.sql} has reserved every key allocator {sequence.allocator!r} "
        f"may hand out in [{low}, {high}]",
    )
