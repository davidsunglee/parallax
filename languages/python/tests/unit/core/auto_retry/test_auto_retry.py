"""The bounded retry loop's own waiting (`m-auto-retry`), with its random
source and its sleep substituted: a replay waits a full-jitter delay under a
ceiling that doubles per attempt up to a cap, and nothing that is not a
replay waits at all.

Which failures become retry candidates, and when, is the transaction runner's,
graded in ``tests/unit/core/_execution/_transaction/test_runner.py``.
"""

from __future__ import annotations

import random

import pytest

from parallax.core import auto_retry
from parallax.core.auto_retry import RetryCandidate, run_with_retry
from parallax.core.db_error import DatabaseError

_BASE_S = auto_retry._BASE_S  # pyright: ignore[reportPrivateUsage] - the formula, not the tuned values, is graded
_CAP_S = auto_retry._CAP_S  # pyright: ignore[reportPrivateUsage] - the formula, not the tuned values, is graded


class _CeilingRng(random.Random):
    """Answers every draw at the top of its range, recording each range."""

    def __init__(self) -> None:
        super().__init__(0)
        self.ranges: list[tuple[float, float]] = []

    def uniform(self, a: float, b: float) -> float:
        self.ranges.append((a, b))
        return b


@pytest.fixture
def waits(monkeypatch: pytest.MonkeyPatch) -> tuple[_CeilingRng, list[float]]:
    rng = _CeilingRng()
    slept: list[float] = []
    monkeypatch.setattr(auto_retry, "_rng", rng)
    monkeypatch.setattr(auto_retry, "_sleep", slept.append)
    return rng, slept


def test_each_replay_waits_under_a_ceiling_that_doubles_up_to_the_cap(
    waits: tuple[_CeilingRng, list[float]],
) -> None:
    rng, slept = waits
    failure = DatabaseError(category="deadlock", native_code="40P01", message="deadlock")
    attempts: list[int] = []

    def attempt() -> str:
        attempts.append(len(attempts))
        if len(attempts) <= 7:
            raise RetryCandidate(failure)
        return "ok"

    assert run_with_retry(attempt, retries=10) == "ok"
    ceilings = [min(_CAP_S, _BASE_S * 2**n) for n in range(7)]
    assert rng.ranges == [(0.0, ceiling) for ceiling in ceilings]
    assert slept == ceilings
    assert ceilings == sorted(ceilings)


def test_an_exhausted_bound_waits_only_between_its_attempts(
    waits: tuple[_CeilingRng, list[float]],
) -> None:
    _rng, slept = waits
    failure = DatabaseError(category="deadlock", native_code="40P01", message="deadlock")

    def attempt() -> str:
        raise RetryCandidate(failure)

    with pytest.raises(DatabaseError) as surfaced:
        run_with_retry(attempt, retries=2)
    assert surfaced.value is failure
    assert len(slept) == 2


@pytest.mark.parametrize("retries", [0, 10])
def test_a_failure_handed_over_as_itself_never_waits(
    waits: tuple[_CeilingRng, list[float]], retries: int
) -> None:
    _rng, slept = waits
    failure = DatabaseError(category="deadlock", native_code="40P01", message="deadlock")

    def attempt() -> str:
        raise failure

    with pytest.raises(DatabaseError):
        run_with_retry(attempt, retries=retries)
    assert slept == []


def test_a_zero_bound_never_waits(waits: tuple[_CeilingRng, list[float]]) -> None:
    _rng, slept = waits
    failure = DatabaseError(category="deadlock", native_code="40P01", message="deadlock")

    def attempt() -> str:
        raise RetryCandidate(failure)

    with pytest.raises(DatabaseError):
        run_with_retry(attempt, retries=0)
    assert slept == []


def test_a_draw_stays_inside_its_ceiling_however_many_attempts_preceded_it() -> None:
    rng = random.Random(7)
    for attempt in (1, 2, 6, 7, 10_000):
        ceiling = min(_CAP_S, _BASE_S * 2 ** min(attempt - 1, 32))
        assert 0.0 <= auto_retry._delay(attempt, rng) <= ceiling  # pyright: ignore[reportPrivateUsage] - the internal delay is what this bounds


def test_a_negative_bound_is_refused_before_any_attempt() -> None:
    attempts: list[int] = []
    with pytest.raises(ValueError, match="retries must be >= 0"):
        run_with_retry(lambda: attempts.append(1), retries=-1)
    assert attempts == []
