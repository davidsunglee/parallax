"""The bounded retry loop's own waiting (`m-auto-retry`), driven through the
timing it is handed: a replay waits a full-jitter delay under the longer of a
fixed window and one scaled by the failed attempt's own duration, each doubling
per attempt up to its limit, under an absolute ceiling; and nothing that is not
a replay waits at all.

When a failure becomes a retry candidate is the transaction runner's, graded in
``tests/unit/core/_execution/_transaction/test_runner.py``; the Temporal
Conflict's own verdict and exhaustion are graded here beside the loop.
"""

from __future__ import annotations

import datetime as dt
import random
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import pytest

from parallax.core.auto_retry import RetryCandidate, RetryTiming, retry_eligible, run_with_retry
from parallax.core.db_error import DatabaseError
from parallax.core.metamodel import EntityIdentity
from parallax.core.unit_work import RollbackOnlyError, TemporalConflictError


@dataclass
class _Time:
    """A clock that moves only when an attempt works or the loop sleeps."""

    now: float = 0.0
    slept: list[float] = field(default_factory=list[float])

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def work(self, seconds: float) -> None:
        self.now += seconds


@dataclass
class _Jitter:
    """Answers every draw at ``fraction`` of its window, recording each window."""

    fraction: float = 1.0
    windows: list[float] = field(default_factory=list[float])

    def __call__(self, window: float) -> float:
        self.windows.append(window)
        return self.fraction * window


@pytest.fixture
def timeline() -> _Time:
    return _Time()


@pytest.fixture
def jitter() -> _Jitter:
    return _Jitter()


@pytest.fixture
def timing(timeline: _Time, jitter: _Jitter) -> RetryTiming:
    return RetryTiming(monotonic=timeline.monotonic, sleep=timeline.sleep, jitter=jitter)


def _deadlock() -> DatabaseError:
    return DatabaseError(category="deadlock", native_code="40P01", message="deadlock")


_DEADLOCK = _deadlock()
_FAST = 2**-20


def _failing_for(
    timeline: _Time, durations: Sequence[float], failure: Exception = _DEADLOCK
) -> Callable[[], str]:
    """An attempt that works each of ``durations`` in turn and fails, then
    commits. Binary fractions keep the loop's clock arithmetic exact until a
    wait that is not one moves the clock."""
    remaining = iter(durations)

    def attempt() -> str:
        duration = next(remaining, None)
        if duration is None:
            return "ok"
        timeline.work(duration)
        raise RetryCandidate(failure)

    return attempt


def test_a_first_attempt_that_succeeds_neither_draws_nor_waits(
    timeline: _Time, jitter: _Jitter, timing: RetryTiming
) -> None:
    assert run_with_retry(_failing_for(timeline, []), retries=10, timing=timing) == "ok"

    assert jitter.windows == []
    assert timeline.slept == []


def test_an_eligible_failure_is_replayed_after_one_draw_and_one_wait(timeline: _Time) -> None:
    trace: list[str] = []
    failing = _failing_for(timeline, [_FAST, _FAST])

    def attempt() -> str:
        trace.append("attempt")
        return failing()

    def draw(window: float) -> float:
        trace.append("draw")
        return window

    def sleep(seconds: float) -> None:
        del seconds
        trace.append("sleep")

    timing = RetryTiming(monotonic=timeline.monotonic, sleep=sleep, jitter=draw)

    assert run_with_retry(attempt, retries=10, timing=timing) == "ok"

    assert trace == ["attempt", "draw", "sleep", "attempt", "draw", "sleep", "attempt"]


def test_a_fast_failed_attempt_waits_under_the_fixed_window_doubling_to_its_limit(
    timeline: _Time, jitter: _Jitter, timing: RetryTiming
) -> None:
    assert run_with_retry(_failing_for(timeline, [_FAST] * 6), retries=10, timing=timing) == "ok"

    windows = [0.008, 0.016, 0.025, 0.025, 0.025, 0.025]
    assert jitter.windows == windows
    assert timeline.slept == windows


def test_a_slow_failed_attempt_waits_under_its_scaled_window_doubling_to_its_limit(
    timeline: _Time, jitter: _Jitter, timing: RetryTiming
) -> None:
    duration = 7 * 2**-6

    assert run_with_retry(_failing_for(timeline, [duration] * 7), retries=10, timing=timing) == "ok"

    windows = [7 * 2**-8, 7 * 2**-7, 7 * 2**-6, 7 * 2**-5, 7 * 2**-4, 7 * 2**-3, 7 * 2**-3]
    assert jitter.windows == windows
    assert timeline.slept == windows


def test_each_window_follows_the_attempt_that_just_failed_and_excludes_earlier_waits(
    timeline: _Time, jitter: _Jitter, timing: RetryTiming
) -> None:
    durations = [2**-2, 2**-3, _FAST]

    assert run_with_retry(_failing_for(timeline, durations), retries=10, timing=timing) == "ok"

    assert jitter.windows == [2**-4, 2**-4, 0.025]


def test_no_window_passes_the_ceiling_however_long_the_attempt_took(
    timeline: _Time, jitter: _Jitter, timing: RetryTiming
) -> None:
    assert (
        run_with_retry(_failing_for(timeline, [3600.0, 3600.0]), retries=10, timing=timing) == "ok"
    )

    assert jitter.windows == [1.0, 1.0]


@pytest.mark.parametrize(
    ("fraction", "waits"), [(0.0, [0.0, 0.0]), (0.5, [0.004, 0.008])], ids=["zero", "half"]
)
def test_the_loop_waits_what_was_drawn_rather_than_its_window(
    timeline: _Time, jitter: _Jitter, timing: RetryTiming, fraction: float, waits: list[float]
) -> None:
    jitter.fraction = fraction

    assert run_with_retry(_failing_for(timeline, [_FAST] * 2), retries=10, timing=timing) == "ok"

    assert jitter.windows == [0.008, 0.016]
    assert timeline.slept == waits


def test_an_exhausted_bound_draws_and_waits_only_between_its_attempts(
    timeline: _Time, jitter: _Jitter, timing: RetryTiming
) -> None:
    failure = _deadlock()

    with pytest.raises(DatabaseError) as surfaced:
        run_with_retry(_failing_for(timeline, [_FAST] * 5, failure), retries=2, timing=timing)

    assert surfaced.value is failure
    assert surfaced.value.__notes__ == ["bounded retry exhausted after 3 attempts (retries=2)"]
    assert jitter.windows == [0.008, 0.016]
    assert timeline.slept == [0.008, 0.016]


def test_exhaustion_surfaces_the_failure_with_its_own_chain(
    timeline: _Time, timing: RetryTiming
) -> None:
    cause = RuntimeError("what the failure was raised from")
    context = RuntimeError("what the attempt was handling")
    failure = _deadlock()
    failure.__cause__ = cause
    failure.__context__ = context

    with pytest.raises(DatabaseError) as surfaced:
        run_with_retry(_failing_for(timeline, [_FAST] * 2, failure), retries=1, timing=timing)

    assert surfaced.value is failure
    assert surfaced.value.__cause__ is cause
    assert surfaced.value.__context__ is context


@pytest.mark.parametrize("retries", [0, 10])
def test_a_failure_handed_over_as_itself_never_waits(
    timeline: _Time, jitter: _Jitter, timing: RetryTiming, retries: int
) -> None:
    failure = _deadlock()
    attempts: list[None] = []

    def attempt() -> str:
        attempts.append(None)
        raise failure

    with pytest.raises(DatabaseError) as surfaced:
        run_with_retry(attempt, retries=retries, timing=timing)
    assert surfaced.value is failure
    assert not hasattr(failure, "__notes__")
    assert len(attempts) == 1
    assert jitter.windows == []
    assert timeline.slept == []


def test_a_terminal_failure_of_a_replay_ends_the_loop_without_another_wait(
    timeline: _Time, jitter: _Jitter, timing: RetryTiming
) -> None:
    terminal = _deadlock()
    failing = _failing_for(timeline, [_FAST])

    def attempt() -> str:
        failing()
        raise terminal

    with pytest.raises(DatabaseError) as surfaced:
        run_with_retry(attempt, retries=10, timing=timing)
    assert surfaced.value is terminal
    assert jitter.windows == [0.008]
    assert timeline.slept == [0.008]


def test_a_zero_bound_never_waits(timeline: _Time, jitter: _Jitter, timing: RetryTiming) -> None:
    failure = _deadlock()

    with pytest.raises(DatabaseError) as surfaced:
        run_with_retry(_failing_for(timeline, [_FAST], failure), retries=0, timing=timing)

    assert surfaced.value.__notes__ == ["bounded retry exhausted after 1 attempts (retries=0)"]
    assert jitter.windows == []
    assert timeline.slept == []


def test_a_seeded_draw_stays_inside_its_window_however_many_attempts_preceded_it(
    timeline: _Time,
) -> None:
    source = random.Random(7)
    windows: list[float] = []

    def draw(window: float) -> float:
        windows.append(window)
        return source.uniform(0.0, window)

    durations = [0.0, 0.004, 0.5, 3600.0] * 2_500
    timing = RetryTiming(monotonic=timeline.monotonic, sleep=timeline.sleep, jitter=draw)

    outcome = run_with_retry(_failing_for(timeline, durations), retries=10_000, timing=timing)

    assert outcome == "ok"
    assert len(windows) == 10_000
    assert all(
        0.0 <= wait <= window <= 1.0 for wait, window in zip(timeline.slept, windows, strict=True)
    )


def test_the_system_draw_stays_inside_the_window_it_is_given(timeline: _Time) -> None:
    timing = RetryTiming(monotonic=timeline.monotonic, sleep=timeline.sleep)
    windows = [0.008, 0.016, *[0.025] * 198]

    outcome = run_with_retry(_failing_for(timeline, [_FAST] * 200), retries=200, timing=timing)

    assert outcome == "ok"
    assert all(0.0 <= wait <= window for wait, window in zip(timeline.slept, windows, strict=True))


def test_the_system_timing_reads_the_monotonic_clock_and_really_sleeps() -> None:
    timing = RetryTiming()
    assert timing.monotonic is time.monotonic
    assert timing.sleep is time.sleep


def test_a_negative_bound_is_refused_before_any_attempt() -> None:
    attempts: list[int] = []
    with pytest.raises(ValueError, match="retries must be >= 0"):
        run_with_retry(lambda: attempts.append(1), retries=-1)
    assert attempts == []


_CONFLICT = TemporalConflictError(
    EntityIdentity("parallax.compatibility", "Balance"),
    dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
    key={"id": 1},
    stored_bound=dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
)


def _doomed_by(cause: BaseException) -> RollbackOnlyError:
    try:
        raise RollbackOnlyError("the attempt is rollback-only") from cause
    except RollbackOnlyError as refused:
        return refused


@pytest.mark.parametrize(
    "failure",
    [_CONFLICT, _doomed_by(_CONFLICT)],
    ids=["direct", "rollback-only-cause"],
)
def test_a_temporal_conflict_is_a_recoverable_conflict(failure: BaseException) -> None:
    assert retry_eligible(failure)


@pytest.mark.parametrize("retries", [0, 2])
def test_an_exhausted_temporal_conflict_surfaces_itself_with_the_attempt_count(
    timeline: _Time, timing: RetryTiming, retries: int
) -> None:
    failure = TemporalConflictError(
        EntityIdentity("parallax.compatibility", "Balance"), dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
    )
    attempts: list[None] = []

    def attempt() -> str:
        attempts.append(None)
        timeline.work(0.004)
        raise RetryCandidate(failure)

    with pytest.raises(TemporalConflictError) as surfaced:
        run_with_retry(attempt, retries=retries, timing=timing)
    assert surfaced.value is failure
    assert len(attempts) == retries + 1
    assert surfaced.value.__notes__ == [
        f"bounded retry exhausted after {retries + 1} attempts (retries={retries})"
    ]
    assert len(timeline.slept) == retries


def _exclusion_violation() -> DatabaseError:
    return DatabaseError(
        category="constraintViolation",
        native_code="23P01",
        message="conflicting key value violates exclusion constraint",
        constraint_name="pxc_excl_balance_d9ac2f7e38d8f4040d3f5ed33ac09a0d",
    )


@pytest.mark.parametrize("doomed", [False, True], ids=["direct", "rollback-only-cause"])
def test_a_recognized_conflict_is_recoverable_as_the_original_database_error(
    doomed: bool,
) -> None:
    violation = _exclusion_violation()
    failure = _doomed_by(violation) if doomed else violation
    assert retry_eligible(failure, recognized=(violation,))
    assert not retry_eligible(failure)


def test_recognition_is_of_the_one_failure_and_never_of_an_equal_looking_one() -> None:
    assert not retry_eligible(_exclusion_violation(), recognized=(_exclusion_violation(),))
