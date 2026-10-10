from __future__ import annotations

import gc
import sys
import tracemalloc
from collections.abc import Generator
from contextlib import contextmanager
from typing import cast

import pytest

import feature_boundary_overhead as report
import feature_boundary_reading as reading
from tests.unit import _feature_boundary_support as support
from tests.unit.memory_instruments import in_a_child_interpreter, serve_one_measurement


def test_child_and_report_share_cases_and_metrics() -> None:
    assert reading.CASE_NAMES == report.CASE_NAMES == tuple(case.name for case in support.CASES)
    assert reading.METRICS == report.METRICS
    assert reading.RETAINED_WARMUPS == report.RETAINED_WARMUPS


@pytest.mark.parametrize("warmups,measured", [(-1, 1), (0, 0)])
def test_invalid_sampling_fails_before_opening_instruments(warmups: int, measured: int) -> None:
    with pytest.raises(ValueError):
        reading.measure(reading.CASE_NAMES[0], warmups=warmups, measured=measured)


def _assert_reading(name: str) -> None:
    result = reading.measure(name, warmups=1, measured=2)
    samples = cast("dict[str, list[float]]", result["samples"])
    assert result["case"] == name
    assert result["window"] == report.WINDOWS[name]
    assert result["units"] == report.UNITS[name] == 1
    assert result["retainedWarmups"] == 200
    assert len(samples["elapsedUs"]) == len(samples["peakBytes"]) == 2
    assert len(samples["retainedBytes"]) == 1
    assert all(sample > 0 for sample in samples["elapsedUs"])
    assert all(sample >= 0 for metric in reading.METRICS for sample in samples[metric])
    assert not tracemalloc.is_tracing()


@in_a_child_interpreter
def test_a_typed_binding_case_measures_its_operation() -> None:
    name = next(case.name for case in support.CASES if case.window == "typed-predicate-binding")
    _assert_reading(name)


@in_a_child_interpreter
def test_scalar_codec_and_cold_plan_readings_hold_the_product() -> None:
    scalar = next(
        case.name
        for case in support.CASES
        if case.window == "scalar-collection-encode" and "128" in case.name
    )
    cold = next(case.name for case in support.CASES if case.window == "typed-cold-plan")
    _assert_reading(scalar)
    _assert_reading(cold)


@in_a_child_interpreter
def test_retained_checkpoint_excludes_preparation_and_holds_returned_object() -> None:
    class Driver:
        units = 1

        def __init__(self) -> None:
            self.prepared: bytearray | None = None

        def prepare(self) -> None:
            self.prepared = bytearray(100_000)

        def run(self) -> object:
            return bytearray(10_000)

    @contextmanager
    def driver_for(_name: str) -> Generator[Driver]:
        yield Driver()

    original = support.driver_for
    support.driver_for = driver_for
    try:
        result = reading.measure(reading.CASE_NAMES[0], warmups=1, measured=2)
    finally:
        support.driver_for = original
    samples = cast("dict[str, list[float]]", result["samples"])
    assert 10_000 <= samples["retainedBytes"][0] < 20_000
    assert all(10_000 <= sample < 20_000 for sample in samples["peakBytes"])
    gc.collect()


if __name__ == "__main__":
    serve_one_measurement(sys.argv[1])
