"""The root's key allocator over a scripted reservation: block arithmetic, the
live-definition check, and what a failed or late reservation leaves behind.

A real server cannot be made to answer an exact first key, an exact live
definition, or a reservation that finishes past its budget on demand, so the
reservation is a callable answering the rows each test names.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

import pytest

from parallax.core._execution._key_allocation import KeyAllocator
from parallax.core.internal.base import INT32, INT64, InternalError, UsageError
from parallax.core.internal.database_binding import PhysicalSequence, ResolvedSequence
from parallax.core.internal.db_error import DatabaseError
from parallax.core.internal.db_port import ConnectionAcquisitionError, ConnectionContext, Row
from parallax.core.internal.dialect import POSTGRES
from parallax.core.internal.metamodel import KeySequence
from parallax.core.internal.sql_gen import LoweredStatement
from tests._support.errors import raises_code

_INT64_RANGE = (-(2**63), 2**63 - 1)
_INT32_RANGE = (-(2**31), 2**31 - 1)


def _sequence(
    allocator: str = "ids",
    *,
    batch_size: int = 3,
    increment_size: int = 1,
    initial_value: int = 1,
    key_range: tuple[int, int] = _INT64_RANGE,
    physical: PhysicalSequence | None = None,
) -> ResolvedSequence:
    place = physical if physical is not None else PhysicalSequence(("px",), allocator)
    return ResolvedSequence(
        allocator=allocator,
        physical=place,
        sql=POSTGRES.render_table(place),
        key_sequence=KeySequence(
            allocator,
            batch_size=batch_size,
            increment_size=increment_size,
            initial_value=initial_value,
        ),
        data_type=POSTGRES.column_type(INT32 if key_range == _INT32_RANGE else INT64, None),
        key_range=key_range,
        consuming_tables=(),
    )


def _row(sequence: ResolvedSequence, first: int, **live: object) -> Row:
    """The reservation row a live sequence matching ``sequence`` answers,
    ``live`` overriding its increment, bounds, cycling, or type."""
    settings = sequence.key_sequence
    low, high = sequence.key_range
    return (
        first,
        live.get("increment", settings.batch_size * settings.increment_size),
        live.get("minimum", low),
        live.get("maximum", high),
        live.get("cycles", False),
        live.get("data_type", sequence.data_type),
    )


@dataclass
class _Source:
    reservation_timeout: float = 15.0
    deadlines: list[float] = field(default_factory=list[float])

    def new_context(self, deadline: float, /) -> ConnectionContext:
        self.deadlines.append(deadline)
        return cast("ConnectionContext", _Context())


class _Context:
    """Stands in for a context the scripted reservation never enters."""


@dataclass
class _Reservations:
    """Answers each reservation with the next scripted rows or failure,
    recording the statements it was handed."""

    answers: list[list[Row] | BaseException]
    statements: list[LoweredStatement] = field(default_factory=list[LoweredStatement])

    def __call__(
        self,
        resource: ConnectionContext,
        statement: LoweredStatement,
        accept: Callable[[list[Row]], int],
    ) -> int:
        assert isinstance(resource, _Context)
        self.statements.append(statement)
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return accept(answer)


def _allocator(source: _Source | None = None) -> KeyAllocator:
    return KeyAllocator(source if source is not None else _Source(), POSTGRES)


def _keys(
    allocator: KeyAllocator, sequence: ResolvedSequence, reserve: Any, count: int
) -> list[int]:
    return [allocator.next_key(sequence, reserve) for _ in range(count)]


# --------------------------------------------------------------------------- #
# Block arithmetic.                                                           #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("settings", "firsts", "expected"),
    [
        ({"batch_size": 3}, [1, 4], [1, 2, 3, 4, 5]),
        ({"batch_size": 1}, [7, 8, 9], [7, 8, 9]),
        ({"batch_size": 2, "increment_size": 10}, [100, 120, 140], [100, 110, 120, 130, 140]),
        ({"batch_size": 3, "initial_value": -5}, [-5, -2], [-5, -4, -3, -2, -1]),
        ({"batch_size": 3}, [0, 3], [0, 1, 2, 3, 4]),
    ],
    ids=["batch", "batch-of-one", "stride", "negative-start", "zero-start"],
)
def test_each_reservation_hands_out_its_block_one_stride_apart(
    settings: dict[str, Any], firsts: list[int], expected: list[int]
) -> None:
    sequence = _sequence(**settings)
    reserve = _Reservations([[_row(sequence, first)] for first in firsts])

    assert _keys(_allocator(), sequence, reserve, len(expected)) == expected
    assert reserve.answers == []
    assert [statement.binds for statement in reserve.statements] == [("px.ids",)] * len(firsts)


def test_a_final_block_is_clipped_to_the_key_range_then_exhaustion_is_reported() -> None:
    sequence = _sequence(batch_size=5, key_range=(1, 12))
    exhausted = DatabaseError(
        category=None, native_code="2200H", message="nextval: reached maximum value"
    )
    reserve = _Reservations(
        [
            [_row(sequence, 1, maximum=12)],
            [_row(sequence, 6, maximum=12)],
            [_row(sequence, 11, maximum=12)],
            exhausted,
        ]
    )
    allocator = _allocator()

    assert _keys(allocator, sequence, reserve, 12) == list(range(1, 13))
    with raises_code(UsageError, "key-sequence-exhausted") as refused:
        allocator.next_key(sequence, reserve)
    assert refused.value.__cause__ is exhausted


def test_a_handout_within_a_block_runs_no_reservation() -> None:
    sequence = _sequence(batch_size=4)
    reserve = _Reservations([[_row(sequence, 1)]])
    allocator = _allocator()
    allocator.next_key(sequence, reserve)

    assert _keys(allocator, sequence, _Reservations([]), 3) == [2, 3, 4]


# --------------------------------------------------------------------------- #
# What a reservation is keyed by.                                              #
# --------------------------------------------------------------------------- #


def test_one_physical_sequence_and_settings_share_one_reservation_whatever_names_it() -> None:
    place = PhysicalSequence(("px",), "shared")
    first = _sequence("left", physical=place)
    second = _sequence("right", physical=place)
    allocator = _allocator()
    allocator.next_key(first, _Reservations([[_row(first, 1)]]))

    assert _keys(allocator, second, _Reservations([]), 2) == [2, 3]


@pytest.mark.parametrize(
    "other",
    [
        _sequence(physical=PhysicalSequence(("tenant_b",), "ids")),
        _sequence(batch_size=4),
        _sequence(increment_size=2),
    ],
    ids=["another-location", "another-batch", "another-stride"],
)
def test_another_location_or_settings_reserve_their_own_block(other: ResolvedSequence) -> None:
    sequence = _sequence()
    allocator = _allocator()
    allocator.next_key(sequence, _Reservations([[_row(sequence, 1)]]))

    assert allocator.next_key(other, _Reservations([[_row(other, 50)]])) == 50
    assert allocator.next_key(sequence, _Reservations([])) == 2


def test_an_initial_value_change_keeps_the_reservation() -> None:
    sequence = _sequence(initial_value=1)
    allocator = _allocator()
    allocator.next_key(sequence, _Reservations([[_row(sequence, 1)]]))

    assert allocator.next_key(_sequence(initial_value=900), _Reservations([])) == 2


# --------------------------------------------------------------------------- #
# The live definition every reservation reads back.                            #
# --------------------------------------------------------------------------- #


def test_no_row_is_a_missing_sequence() -> None:
    with raises_code(UsageError, "key-sequence-missing", match="px.ids"):
        _allocator().next_key(_sequence(), _Reservations([[]]))


@pytest.mark.parametrize(
    ("live", "detail"),
    [
        ({"increment": 1}, "steps by 1, not 3"),
        ({"cycles": True}, "it cycles"),
        ({"minimum": -(2**63), "maximum": 2**63 - 1}, "leave the key range"),
        ({"data_type": "numeric"}, "holds numeric values"),
    ],
    ids=["increment", "cycling", "bounds", "type"],
)
def test_a_live_definition_the_declaration_cannot_allocate_from_is_refused(
    live: dict[str, object], detail: str
) -> None:
    sequence = _sequence(key_range=_INT32_RANGE)
    allocator = _allocator()
    with raises_code(UsageError, "key-sequence-mismatch", match=detail):
        allocator.next_key(sequence, _Reservations([[_row(sequence, 1, **live)]]))
    # The block it reserved is abandoned, and the next reservation starts anew.
    assert allocator.next_key(sequence, _Reservations([[_row(sequence, 4)]])) == 4


@pytest.mark.parametrize(
    "rows",
    [
        [(1, 3, 1, 9, False, "bigint"), (4, 3, 1, 9, False, "bigint")],
        [(1, 3, 1, 9, False)],
        [("1", 3, 1, 9, False, "bigint")],
        [(True, 3, 1, 9, False, "bigint")],
    ],
    ids=["two-rows", "short-row", "text-key", "boolean-key"],
)
def test_a_row_no_reservation_produces_is_an_internal_refusal(rows: list[Row]) -> None:
    with raises_code(InternalError, "key-reservation-invalid"):
        _allocator().next_key(_sequence(), _Reservations([rows]))


# --------------------------------------------------------------------------- #
# One budget, and nothing published from a failed or late reservation.        #
# --------------------------------------------------------------------------- #


def test_every_failure_leaves_the_reservation_to_start_anew() -> None:
    sequence = _sequence()
    allocator = _allocator()
    lost = ConnectionAcquisitionError("no connection", reason="unavailable")
    with pytest.raises(ConnectionAcquisitionError) as failed:
        allocator.next_key(sequence, _Reservations([lost]))
    assert failed.value is lost
    statement = DatabaseError(category=None, native_code="XX000", message="broken")
    with pytest.raises(DatabaseError) as broke:
        allocator.next_key(sequence, _Reservations([statement]))
    assert broke.value is statement

    assert allocator.next_key(sequence, _Reservations([[_row(sequence, 10)]])) == 10


def test_a_reservation_finishing_past_its_budget_publishes_nothing() -> None:
    sequence = _sequence()
    source = _Source(reservation_timeout=0.0)
    allocator = _allocator(source)
    with raises_code(ConnectionAcquisitionError, "connection-acquisition-failed", match="after"):
        allocator.next_key(sequence, _Reservations([[_row(sequence, 1)]]))

    source.reservation_timeout = 15.0
    assert allocator.next_key(sequence, _Reservations([[_row(sequence, 4)]])) == 4


def test_each_reservation_takes_its_deadline_from_one_budget() -> None:
    sequence = _sequence(batch_size=1)
    source = _Source(reservation_timeout=7.0)
    allocator = _allocator(source)
    allocator.next_key(sequence, _Reservations([[_row(sequence, 1)]]))
    assert len(source.deadlines) == 1


def test_a_waiter_whose_budget_runs_out_behind_another_reservation_times_out() -> None:
    sequence = _sequence(batch_size=1)
    source = _Source(reservation_timeout=0.05)
    allocator = _allocator(source)
    entered = threading.Event()
    release = threading.Event()

    def stalled(
        resource: ConnectionContext,
        statement: LoweredStatement,
        accept: Callable[[list[Row]], int],
    ) -> int:
        entered.set()
        release.wait(5)
        raise ConnectionAcquisitionError("abandoned", reason="unavailable")

    def hold() -> None:
        with pytest.raises(ConnectionAcquisitionError):
            allocator.next_key(sequence, stalled)

    holder = threading.Thread(target=hold)
    holder.start()
    try:
        assert entered.wait(5)
        with pytest.raises(ConnectionAcquisitionError) as waited:
            allocator.next_key(sequence, _Reservations([]))
        assert waited.value.reason == "timeout"
    finally:
        release.set()
        holder.join(5)


def test_waiters_on_one_reservation_take_the_winner_s_block() -> None:
    sequence = _sequence(batch_size=4)
    allocator = _allocator()
    entered = threading.Event()
    release = threading.Event()
    calls: list[int] = []

    def slow(
        resource: ConnectionContext,
        statement: LoweredStatement,
        accept: Callable[[list[Row]], int],
    ) -> int:
        calls.append(1)
        entered.set()
        release.wait(5)
        return accept([_row(sequence, 1)])

    taken: list[int] = []
    workers = [
        threading.Thread(target=lambda: taken.append(allocator.next_key(sequence, slow)))
        for _ in range(3)
    ]
    workers[0].start()
    assert entered.wait(5)
    for worker in workers[1:]:
        worker.start()
    release.set()
    for worker in workers:
        worker.join(5)

    assert sorted(taken) == [1, 2, 3]
    assert calls == [1]
