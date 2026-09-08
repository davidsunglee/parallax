"""Repeatable cold and warm allocation readings for the two public edit verbs."""

from __future__ import annotations

import argparse
import gc
import json
import os
import statistics
import subprocess
import sys
import tracemalloc
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Literal, cast

type Branch = Literal["changed", "change-free"]
type Frontend = Literal["entity", "value-object"]
type Mode = Literal["cold", "warm"]
type Work = Callable[[], object]
type Sample = dict[str, int]
type ChildReport = dict[str, list[Sample] | list[int]]


@dataclass(frozen=True, slots=True)
class Reading:
    retained_bytes: int
    retained_blocks: int
    current_bytes: int
    peak_bytes: int


def _collect() -> None:
    gc.collect()
    gc.collect()


def _measure(work: Work) -> Reading:
    _collect()
    before_snapshot = tracemalloc.take_snapshot()
    before_current, _ = tracemalloc.get_traced_memory()
    tracemalloc.reset_peak()
    held = work()
    current, peak = tracemalloc.get_traced_memory()
    after_snapshot = tracemalloc.take_snapshot()
    retained = after_snapshot.compare_to(before_snapshot, "lineno")
    reading = Reading(
        retained_bytes=sum(stat.size_diff for stat in retained),
        retained_blocks=sum(stat.count_diff for stat in retained),
        current_bytes=current - before_current,
        peak_bytes=peak - before_current,
    )
    del held, retained, after_snapshot, before_snapshot
    _collect()
    return reading


def _new_entity() -> type:
    from parallax.core import Attr, Entity, attr

    class MeasuredEntity(
        Entity, table="measured_entity", namespace="parallax.edit_resolution_allocation"
    ):
        id: Attr[int] = attr(primary_key=True)
        label: Attr[str]

    return MeasuredEntity


def _new_value_object() -> type:
    from parallax.core import Attr, ValueObject

    class MeasuredValueObject(ValueObject):
        label: Attr[str]

    return MeasuredValueObject


def _new_class(frontend: Frontend) -> type:
    return _new_entity() if frontend == "entity" else _new_value_object()


def _edit(value: Any, branch: Branch) -> object:
    return value.edit(label="b") if branch == "changed" else value.edit()


def _cold_work(frontend: Frontend, branch: Branch) -> Work:
    def work() -> object:
        cls = _new_class(frontend)
        source = cls(id=1, label="a") if frontend == "entity" else cls(label="a")
        return cls, source, _edit(source, branch)

    return work


def _warm_work(frontend: Frontend, branch: Branch, warmups: int) -> Work:
    cls = _new_class(frontend)
    source = cls(id=1, label="a") if frontend == "entity" else cls(label="a")

    def work() -> object:
        return _edit(source, branch)

    for _ in range(warmups):
        work()
    _collect()
    return work


def _sample_arm(
    frontend: Frontend, branch: Branch, mode: Mode, samples: int, warmups: int
) -> list[dict[str, int]]:
    if mode == "cold":
        _warm_work(frontend, branch, 1)
    work = _cold_work(frontend, branch) if mode == "cold" else _warm_work(frontend, branch, warmups)
    tracemalloc.start()
    try:
        return [asdict(_measure(work)) for _ in range(samples)]
    finally:
        tracemalloc.stop()


def _growth_arm(frontend: Frontend, branch: Branch, warmups: int) -> list[int]:
    work = _warm_work(frontend, branch, warmups)
    tracemalloc.start()
    try:
        for _ in range(warmups):
            work()
        _collect()
        floor, _ = tracemalloc.get_traced_memory()
        readings = [0]
        completed = 0
        for checkpoint in (100, 500, 1000):
            for _ in range(checkpoint - completed):
                work()
            completed = checkpoint
            _collect()
            current, _ = tracemalloc.get_traced_memory()
            readings.append(current - floor)
        return readings
    finally:
        tracemalloc.stop()


def _child(samples: int, warmups: int) -> ChildReport:
    arms: ChildReport = {}
    for frontend in ("entity", "value-object"):
        for branch in ("changed", "change-free"):
            for mode in ("cold", "warm"):
                key = f"{frontend}/{branch}/{mode}"
                arms[key] = _sample_arm(frontend, branch, mode, samples, warmups)
            arms[f"{frontend}/{branch}/growth"] = _growth_arm(frontend, branch, warmups)
    return arms


def _spread(values: Sequence[float]) -> dict[str, float]:
    quartiles = statistics.quantiles(values, n=4, method="inclusive")
    return {
        "median": statistics.median(values),
        "q1": quartiles[0],
        "q3": quartiles[2],
        "min": min(values),
        "max": max(values),
    }


def _summarize(reports: Sequence[ChildReport]) -> dict[str, object]:
    summary: dict[str, object] = {}
    for key in reports[0]:
        if key.endswith("/growth"):
            process_readings = [cast("list[int]", report[key]) for report in reports]
            summary[key] = {
                f"after_{checkpoint}": _spread(
                    [float(readings[index]) for readings in process_readings]
                )
                for index, checkpoint in enumerate((0, 100, 500, 1000))
            }
            continue
        process_samples = [cast("list[Sample]", report[key]) for report in reports]
        summary[key] = {
            metric: _spread(
                [
                    float(statistics.median(sample[metric] for sample in samples))
                    for samples in process_samples
                ]
            )
            for metric in Reading.__annotations__
        }
    return summary


def _run(processes: int, samples: int, warmups: int) -> dict[str, object]:
    reports: list[ChildReport] = []
    environment = os.environ | {"PYTHONHASHSEED": "0"}
    for _ in range(processes):
        completed = subprocess.run(
            [
                sys.executable,
                __file__,
                "--child",
                "--samples",
                str(samples),
                "--warmups",
                str(warmups),
            ],
            capture_output=True,
            check=True,
            text=True,
            env=environment,
        )
        reports.append(cast("ChildReport", json.loads(completed.stdout)))
    return {
        "python": sys.version.split()[0],
        "processes": processes,
        "samples_per_process": samples,
        "warmups": warmups,
        "metrics": {
            "retained": "tracemalloc snapshot difference while the edit result is live",
            "current": "traced current bytes above the pre-call floor",
            "peak": "traced high-water bytes above the pre-call floor",
            "growth": "traced current bytes after dropped-result edit counts",
        },
        "arms": _summarize(reports),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--processes", type=int, default=5)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--warmups", type=int, default=200)
    args = parser.parse_args(argv)
    if args.child:
        report = _child(args.samples, args.warmups)
    else:
        report = _run(args.processes, args.samples, args.warmups)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
