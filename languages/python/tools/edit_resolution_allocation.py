"""Repeatable cold and warm allocation readings for the two public edit verbs."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import statistics
import subprocess
import sys
import tracemalloc
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Literal, TypedDict, cast

type Branch = Literal["changed", "change-free"]
type Frontend = Literal["entity", "value-object"]
type Mode = Literal["cold", "warm"]
type Work = Callable[[], object]
type Sample = dict[str, int]
type ArmReport = dict[str, list[Sample] | list[int]]


class SourceIdentity(TypedDict):
    path: str
    matches_revision: bool
    sha256: str
    revision: str


class Provenance(TypedDict):
    executable: str
    python: str
    instrument: SourceIdentity
    implementation: dict[str, SourceIdentity]


class ChildReport(TypedDict):
    provenance: Provenance
    arms: ArmReport


@dataclass(frozen=True, slots=True)
class Reading:
    retained_bytes: int
    retained_blocks: int
    current_bytes: int
    peak_bytes: int


def _collect() -> None:
    gc.collect()
    gc.collect()


def _source_identity(module: ModuleType) -> SourceIdentity:
    source = module.__file__
    if source is None:
        raise RuntimeError(f"{module.__name__} has no source file")
    identity = _path_identity(Path(source))
    if not identity["matches_revision"]:
        raise RuntimeError(
            f"loaded source for {module.__name__} differs from revision {identity['revision']}"
        )
    return identity


def _path_identity(source: Path) -> SourceIdentity:
    resolved = source.resolve()
    repository = subprocess.run(
        ["git", "-C", str(resolved.parent), "rev-parse", "--show-toplevel"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    revision = subprocess.run(
        ["git", "-C", repository, "rev-parse", "HEAD"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    relative = resolved.relative_to(repository).as_posix()
    tracked = subprocess.run(
        ["git", "-C", repository, "show", f"{revision}:{relative}"],
        capture_output=True,
        check=False,
    )
    return {
        "path": str(resolved),
        "sha256": digest,
        "revision": revision,
        "matches_revision": tracked.returncode == 0
        and hashlib.sha256(tracked.stdout).hexdigest() == digest,
    }


def _loaded_provenance() -> Provenance:
    import parallax.core.entity._edit as edit_core
    import parallax.core.entity._entity as entity_frontend
    import parallax.core.entity._value_object as value_object_frontend

    return {
        "executable": str(Path(sys.executable).resolve()),
        "python": sys.version.split()[0],
        "instrument": _path_identity(Path(__file__)),
        "implementation": {
            "edit": _source_identity(edit_core),
            "entity": _source_identity(entity_frontend),
            "value_object": _source_identity(value_object_frontend),
        },
    }


def _validate_provenance(provenance: Provenance, expected_revision: str | None) -> str:
    revisions = {identity["revision"] for identity in provenance["implementation"].values()}
    if len(revisions) != 1:
        raise RuntimeError(
            "the measured edit implementation spans multiple repository revisions: "
            f"{sorted(revisions)}"
        )
    revision = revisions.pop()
    if expected_revision is not None and not revision.startswith(expected_revision):
        raise RuntimeError(
            f"loaded edit implementation revision {revision} does not match "
            f"--expect-revision {expected_revision}"
        )
    return revision


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


def _child(samples: int, warmups: int, expected_revision: str | None) -> ChildReport:
    provenance = _loaded_provenance()
    _validate_provenance(provenance, expected_revision)
    arms: ArmReport = {}
    for frontend in ("entity", "value-object"):
        for branch in ("changed", "change-free"):
            for mode in ("cold", "warm"):
                key = f"{frontend}/{branch}/{mode}"
                arms[key] = _sample_arm(frontend, branch, mode, samples, warmups)
            arms[f"{frontend}/{branch}/growth"] = _growth_arm(frontend, branch, warmups)
    return {"provenance": provenance, "arms": arms}


def _spread(values: Sequence[float]) -> dict[str, float]:
    quartiles = statistics.quantiles(values, n=4, method="inclusive")
    return {
        "median": statistics.median(values),
        "q1": quartiles[0],
        "q3": quartiles[2],
        "min": min(values),
        "max": max(values),
    }


def _summarize(reports: Sequence[ArmReport]) -> dict[str, object]:
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


def _run(
    processes: int, samples: int, warmups: int, expected_revision: str | None
) -> dict[str, object]:
    reports: list[ArmReport] = []
    provenances: list[Provenance] = []
    environment = os.environ | {"PYTHONHASHSEED": "0"}
    for _ in range(processes):
        command = [
            sys.executable,
            __file__,
            "--child",
            "--samples",
            str(samples),
            "--warmups",
            str(warmups),
        ]
        if expected_revision is not None:
            command.extend(["--expect-revision", expected_revision])
        completed = subprocess.run(
            command,
            capture_output=True,
            check=True,
            text=True,
            env=environment,
        )
        report = cast("ChildReport", json.loads(completed.stdout))
        _validate_provenance(report["provenance"], expected_revision)
        provenances.append(report["provenance"])
        reports.append(report["arms"])
    if any(provenance != provenances[0] for provenance in provenances[1:]):
        raise RuntimeError("child processes loaded different edit implementation sources")
    return {
        "python": sys.version.split()[0],
        "processes": processes,
        "samples_per_process": samples,
        "warmups": warmups,
        "provenance": {
            "expected_revision": expected_revision,
            "runs": provenances,
        },
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
    parser.add_argument("--expect-revision")
    args = parser.parse_args(argv)
    if args.child:
        report = _child(args.samples, args.warmups, args.expect_revision)
    else:
        report = _run(args.processes, args.samples, args.warmups, args.expect_revision)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
