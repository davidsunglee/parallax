"""``ScriptedClock``: a fixed, ordered script of instants that never reuses one."""

from __future__ import annotations

import datetime as dt

import pytest

from parallax.conformance.scripted_clock import ClockExhaustedError, ScriptedClock
from parallax.core import UsageError
from tests._support.errors import raises_code

_I1 = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_I2 = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


def test_scripted_clock_yields_instants_in_order() -> None:
    clock = ScriptedClock([_I1, _I2])
    assert clock.now() == _I1
    assert clock.now() == _I2


def test_scripted_clock_normalizes_on_construction() -> None:
    naive = dt.datetime(2024, 1, 1)  # no tzinfo — rejected exactly like FixedClock
    with raises_code(UsageError, "instant-invalid"):
        ScriptedClock([naive])


def test_scripted_clock_exhaustion_raises_loudly() -> None:
    clock = ScriptedClock([_I1])
    assert clock.now() == _I1
    with pytest.raises(ClockExhaustedError):
        clock.now()


def test_scripted_clock_requires_at_least_one_instant() -> None:
    with pytest.raises(ValueError):
        ScriptedClock([])
