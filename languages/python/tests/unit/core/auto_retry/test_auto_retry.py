"""The bounded retry loop's own waiting (`m-auto-retry`), with its clock, its
random source, and its sleep substituted: a replay waits a full-jitter delay
under the longer of a fixed window and one scaled by the failed attempt's own
duration, each doubling per attempt up to its limit, under an absolute ceiling;
and nothing that is not a replay waits at all.

Which failures become retry candidates, and when, is the transaction runner's,
graded in ``tests/unit/core/_execution/_transaction/test_runner.py``.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import pytest

from parallax.core import auto_retry
from parallax.core.auto_retry import RetryCandidate, run_with_retry
from parallax.core.db_error import DatabaseError

# The formula, not the tuned values, is graded.
_FLOOR_FIRST_S = auto_retry._FLOOR_FIRST_S  # pyright: ignore[reportPrivateUsage]
_FLOOR_LIMIT_S = auto_retry._FLOOR_LIMIT_S  # pyright: ignore[reportPrivateUsage]
_SCALE_FIRST = auto_retry._SCALE_FIRST  # pyright: ignore[reportPrivateUsage]
_SCALE_LIMIT = auto_retry._SCALE_LIMIT  # pyright: ignore[reportPrivateUsage]
_CEILING_S = auto_retry._CEILING_S  # pyright: ignore[reportPrivateUsage]


def _floor(attempt: int) -> float:
    return min(_FLOOR_LIMIT_S, _FLOOR_FIRST_S * 2 ** (attempt - 1))


def _scaled(attempt: int, elapsed: float) -> float:
    return min(_SCALE_FIRST * 2 ** (attempt - 1), _SCALE_LIMIT) * elapsed


def _window(attempt: int, elapsed: float) -> float:
    return min(_CEILING_S, max(_floor(attempt), _scaled(attempt, elapsed)))


class _CeilingRng(random.Random):
    """Answers every draw at the top of its range, recording each range."""

    def __init__(self) -> None:
        super().__init__(0)
        self.ranges: list[tuple[float, float]] = []

    def uniform(self, a: float, b: float) -> float:
        self.ranges.append((a, b))
        return b


@dataclass
class _Time:
    """A clock that moves only when an attempt works or the loop sleeps."""

    now: float = 0.0
    slept: list[float] = field(default_factory=list[float])

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def work(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def rng(monkeypatch: pytest.MonkeyPatch) -> _CeilingRng:
    ceiling = _CeilingRng()
    monkeypatch.setattr(auto_retry, "_rng", ceiling)
    return ceiling


@pytest.fixture
def timeline(monkeypatch: pytest.MonkeyPatch) -> _Time:
    fake = _Time()
    monkeypatch.setattr(auto_retry, "_clock", fake.clock)
    monkeypatch.setattr(auto_retry, "_sleep", fake.sleep)
    return fake


_DEADLOCK = DatabaseError(category="deadlock", native_code="40P01", message="deadlock")


def _failing_for(timeline: _Time, durations: Sequence[float]) -> Callable[[], str]:
    """An attempt that works each of ``durations`` in turn and fails, then
    commits. Binary fractions keep the loop's clock arithmetic exact until a
    wait that is not one moves the clock."""
    remaining = list(durations)

    def attempt() -> str:
        if not remaining:
            return "ok"
        timeline.work(remaining.pop(0))
        raise RetryCandidate(_DEADLOCK)

    return attempt


def test_a_fast_failed_attempt_waits_under_the_fixed_window_doubling_to_its_limit(
    rng: _CeilingRng, timeline: _Time
) -> None:
    elapsed = 2**-20
    assert _SCALE_LIMIT * elapsed < _FLOOR_FIRST_S

    assert run_with_retry(_failing_for(timeline, [elapsed] * 6), retries=10) == "ok"

    floors = [_floor(attempt) for attempt in range(1, 7)]
    assert rng.ranges == [(0.0, floor) for floor in floors]
    assert timeline.slept == floors
    assert floors[0] == _FLOOR_FIRST_S
    assert floors[-1] == _FLOOR_LIMIT_S
    assert floors == sorted(floors)


def test_a_slow_failed_attempt_waits_under_its_scaled_window_doubling_to_its_limit(
    rng: _CeilingRng, timeline: _Time
) -> None:
    elapsed = 7 * 2**-6
    assert _SCALE_FIRST * elapsed > _FLOOR_LIMIT_S
    assert _SCALE_LIMIT * elapsed < _CEILING_S

    assert run_with_retry(_failing_for(timeline, [elapsed] * 6), retries=10) == "ok"

    windows = [_scaled(attempt, elapsed) for attempt in range(1, 7)]
    assert rng.ranges == [(0.0, window) for window in windows]
    assert timeline.slept == windows
    assert windows[0] == _SCALE_FIRST * elapsed
    assert windows[-1] == _SCALE_LIMIT * elapsed
    assert windows == sorted(windows)


def test_each_window_follows_the_attempt_that_just_failed_and_excludes_earlier_waits(
    rng: _CeilingRng, timeline: _Time
) -> None:
    durations = [2**-4, 2**-20, 2**-5]

    assert run_with_retry(_failing_for(timeline, durations), retries=10) == "ok"

    assert [low for low, _ in rng.ranges] == [0.0] * 3
    assert [high for _, high in rng.ranges] == pytest.approx(
        [_window(attempt, elapsed) for attempt, elapsed in enumerate(durations, start=1)]
    )
    assert rng.ranges[1] == (0.0, _floor(2))


def test_no_window_passes_the_ceiling_however_long_the_attempt_took(
    rng: _CeilingRng, timeline: _Time
) -> None:
    assert run_with_retry(_failing_for(timeline, [3600.0, 3600.0]), retries=10) == "ok"

    assert rng.ranges == [(0.0, _CEILING_S), (0.0, _CEILING_S)]


def test_an_exhausted_bound_waits_only_between_its_attempts(
    rng: _CeilingRng, timeline: _Time
) -> None:
    del rng
    with pytest.raises(DatabaseError) as surfaced:
        run_with_retry(_failing_for(timeline, [0.004] * 5), retries=2)
    assert surfaced.value is _DEADLOCK
    assert len(timeline.slept) == 2


@pytest.mark.parametrize("retries", [0, 10])
def test_a_failure_handed_over_as_itself_never_waits(
    rng: _CeilingRng, timeline: _Time, retries: int
) -> None:
    del rng

    def attempt() -> str:
        raise _DEADLOCK

    with pytest.raises(DatabaseError):
        run_with_retry(attempt, retries=retries)
    assert timeline.slept == []


def test_a_zero_bound_never_waits(rng: _CeilingRng, timeline: _Time) -> None:
    del rng
    with pytest.raises(DatabaseError):
        run_with_retry(_failing_for(timeline, [0.004]), retries=0)
    assert timeline.slept == []


def test_a_draw_stays_inside_its_window_however_many_attempts_preceded_it() -> None:
    rng = random.Random(7)
    for attempt in (1, 2, 6, 7, 10_000):
        for elapsed in (0.0, 0.004, 0.5, 3600.0):
            delay = auto_retry._delay(attempt, elapsed, rng)  # pyright: ignore[reportPrivateUsage] - the internal delay is what this bounds
            assert 0.0 <= delay <= _window(min(attempt, 33), elapsed) <= _CEILING_S


def test_a_negative_bound_is_refused_before_any_attempt() -> None:
    attempts: list[int] = []
    with pytest.raises(ValueError, match="retries must be >= 0"):
        run_with_retry(lambda: attempts.append(1), retries=-1)
    assert attempts == []
