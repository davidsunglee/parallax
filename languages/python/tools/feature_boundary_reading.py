"""Read one bounded feature operation in an isolated interpreter."""

from __future__ import annotations

import argparse
import gc
import json
import sys
import tracemalloc
from collections.abc import Callable, Sequence
from pathlib import Path
from time import perf_counter_ns
from typing import Final

WORKSPACE: Final = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE))

from tests.unit import _feature_boundary_support as support  # noqa: E402
from tests.unit import memory_instruments as instruments  # noqa: E402

for module, filename in (
    (support, "_feature_boundary_support.py"),
    (instruments, "memory_instruments.py"),
):
    expected = WORKSPACE / "tests" / "unit" / filename
    if Path(module.__file__ or "").resolve() != expected:
        raise ImportError(f"this reading requires {expected}, but resolved {module.__file__}")

METRICS: Final = ("elapsedUs", "peakBytes", "retainedBytes")
CASE_NAMES: Final = tuple(case.name for case in support.CASES)
RETAINED_WARMUPS: Final = instruments.WARMUP


def measure(name: str, *, warmups: int, measured: int) -> dict[str, object]:
    if warmups < 0 or measured <= 0:
        raise ValueError("warmups must be non-negative and measured must be positive")
    instruments.require_own_interpreter("feature boundary measurement")
    case = next(case for case in support.CASES if case.name == name)
    with support.driver_for(name) as driver:
        elapsed: list[float] = []
        with instruments.untraced():
            for _ in range(warmups):
                driver.prepare()
                driver.run()
            for _ in range(measured):
                driver.prepare()
                before = perf_counter_ns()
                held = driver.run()
                elapsed.append((perf_counter_ns() - before) / 1_000 / driver.units)
                del held

        peaks: list[float] = []

        def checkpoint(sample: Callable[[], None]) -> None:
            driver.prepare()
            sample()
            held = driver.run()
            sample()
            del held

        tracemalloc.start()
        try:
            with instruments.untraced():
                for _ in range(warmups):
                    driver.prepare()
                    driver.run()
                for _ in range(measured):
                    driver.prepare()
                    gc.collect()
                    gc.collect()
                    floor, _ = tracemalloc.get_traced_memory()
                    tracemalloc.reset_peak()
                    held = driver.run()
                    _, peak = tracemalloc.get_traced_memory()
                    peaks.append(max(0, peak - floor) / driver.units)
                    del held
            kept = max(0, instruments.retained_increment(checkpoint)) / driver.units
        finally:
            tracemalloc.stop()
        return {
            "case": name,
            "window": case.window,
            "units": driver.units,
            "samples": {
                "elapsedUs": elapsed,
                "peakBytes": peaks,
                "retainedBytes": [kept],
            },
            "warmups": warmups,
            "measured": measured,
            "retainedWarmups": RETAINED_WARMUPS,
        }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASE_NAMES)
    parser.add_argument("--warmups", type=int, required=True)
    parser.add_argument("--measured", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        document = measure(args.case, warmups=args.warmups, measured=args.measured)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(document, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
