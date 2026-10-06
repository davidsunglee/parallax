"""The time-interval runtime workloads, their capture, and the comparison rule.

The workload suites drive every cell once in this process and read the port's
counts at each window boundary, so what a window contains is established by
what had and had not happened when it opened and closed. The comparison suites
judge synthetic captures and scripted repetitions, so every result the rule can
reach is reached by a case of known geometry.
"""

from __future__ import annotations

import importlib
import json
import math
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest

import time_interval_runtime as tool
from tests.unit import _time_interval_runtime_support as support

_SOURCE_KEYED = "flow/source-keyed/typed/columns/preparation-inclusive"
_READ_PLAN = importlib.import_module("parallax.snapshot.handle._read_plan")


# --------------------------------------------------------------------------- #
# The cell catalog                                                              #
# --------------------------------------------------------------------------- #
def test_every_flow_combination_is_a_cell_or_a_stated_not_applicable_one() -> None:
    cells = {cell.id for cell in support.CELLS}
    stated = {(entry.flow, entry.interface, entry.mode) for entry in support.NOT_APPLICABLE}
    for flow in support.FLOWS:
        for interface in support.INTERFACES:
            for layout in support.LAYOUTS:
                for mode in support.MODES:
                    cell = support.FlowCell(flow, interface, layout, mode).id
                    assert (cell in cells) != ((flow, interface, mode) in stated), cell


def test_writes_are_preparation_inclusive_only_and_reads_measure_both_modes() -> None:
    modes: dict[str, set[str]] = {}
    for cell in support.CELLS:
        if isinstance(cell, support.FlowCell):
            modes.setdefault(cell.flow, set()).add(cell.mode)
    assert modes == {
        "source-keyed": {"preparation-inclusive"},
        "predicate": {"preparation-inclusive"},
        "target-patch": {"preparation-inclusive"},
        "target-replace": {"preparation-inclusive"},
        "read-eager": {"preparation-inclusive", "reused-execution"},
        "read-stream": {"preparation-inclusive", "reused-execution"},
    }


def test_every_shared_algorithm_is_measured_at_every_size() -> None:
    measured = {
        (cell.algorithm, cell.size)
        for cell in support.CELLS
        if isinstance(cell, support.AlgorithmCell)
    }
    assert measured == {
        (algorithm, size) for algorithm in support.ALGORITHMS for size in (8, 32, 128)
    }


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        (["--flow", "target-patch", "--interface", "typed"], "Typed target-patch"),
        (["--flow", "predicate", "--mode", "reused-execution"], "prepares its instruction"),
        (["--flow", "source-keyed", "--size", "8"], "takes no --size"),
        (["--algorithm", "removal-window", "--size", "16"], "no cell of size 16"),
        (["--algorithm", "removal-window", "--layout", "columns"], "only --size"),
        (["--all", "--mode", "reused-execution"], "no narrowing axis"),
    ],
)
def test_an_unsupported_selection_is_refused_before_anything_is_measured(
    arguments: list[str], reason: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "capture"
    assert tool.main(["capture", *arguments, "--output", str(output)]) == 2
    assert reason in capsys.readouterr().err
    assert not output.exists()


@pytest.mark.parametrize("cell", support.CELLS, ids=lambda cell: cell.id)
def test_a_cells_selection_arguments_select_exactly_that_cell(cell: support.Cell) -> None:
    args = tool.build_parser().parse_args(
        ["capture", *tool.selection_arguments(cell), "--output", "unused"]
    )
    assert tool.selected_cells(args) == (cell,)


# --------------------------------------------------------------------------- #
# What each window contains                                                     #
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class _Boundaries(support.Stopwatch):
    """A stopwatch noting the port's counts as each window opens and closes."""

    counts: Callable[[], support.Outcome] | None = None
    opened: list[support.Outcome] = field(default_factory=list[support.Outcome])
    closed: list[support.Outcome] = field(default_factory=list[support.Outcome])

    def start(self) -> None:
        assert self.counts is not None
        self.opened.append(self.counts())
        support.Stopwatch.start(self)

    def stop(self) -> None:
        support.Stopwatch.stop(self)
        assert self.counts is not None
        self.closed.append(self.counts())


def _bounded_run(cell: support.Cell) -> tuple[support.Outcome, _Boundaries]:
    with support.driver(cell) as driver:
        boundaries = _Boundaries(counts=driver.counts)
        return driver.run(boundaries), boundaries


def _window_contents(cell: support.Cell) -> tuple[support.Outcome, support.Outcome]:
    """What the port must have counted when the first window opens and when
    the last one closes."""
    expected = support.expected_outcome(cell)
    nothing = support.Outcome()
    if isinstance(cell, support.AlgorithmCell):
        counted = support.Outcome(statements=expected.statements, reads=expected.reads)
        if cell.algorithm == "replacement-gaps":
            return nothing, expected
        if cell.algorithm == "destruction-merge":
            # Every flush and read of the scenario precedes the reinsertion.
            return counted, counted
        # Only the read flushing the first removal falls between the windows.
        return support.Outcome(
            statements=expected.statements - 1, reads=expected.reads - 1
        ), counted
    if cell.flow == "source-keyed":
        return support.Outcome(reads=1), expected
    return nothing, expected


@pytest.mark.parametrize("cell", support.CELLS, ids=lambda cell: cell.id)
def test_each_window_contains_its_whole_operation_and_nothing_composed_before_it(
    cell: support.Cell,
) -> None:
    outcome, boundaries = _bounded_run(cell)
    assert outcome == support.expected_outcome(cell)
    opened, closed = _window_contents(cell)
    assert boundaries.opened[0] == opened
    assert boundaries.closed[-1] == closed
    windows = (
        2 if isinstance(cell, support.AlgorithmCell) and cell.algorithm == "removal-window" else 1
    )
    assert boundaries.windows == windows
    assert boundaries.elapsed_ns > 0


def test_a_removal_window_reads_its_invalidating_flush_between_its_two_windows() -> None:
    outcome, boundaries = _bounded_run(support.AlgorithmCell("removal-window", 8))
    first_closed, second_opened = boundaries.closed[0], boundaries.opened[1]
    assert second_opened.statements == first_closed.statements + 1
    assert second_opened.reads == first_closed.reads + 1
    assert outcome.refused == 8


@pytest.fixture
def compilations(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[int]]:
    """Every read-plan compilation, counted as it happens."""
    compiled = vars(_READ_PLAN)["_plan_uncached"]
    count = [0]

    def counted(*args: object, **kwargs: object) -> object:
        count[0] += 1
        return compiled(*args, **kwargs)

    monkeypatch.setattr(_READ_PLAN, "_plan_uncached", counted)
    yield count


_READ_CELLS = tuple(
    cell
    for cell in support.CELLS
    if isinstance(cell, support.FlowCell) and cell.flow.startswith("read-")
)


@pytest.mark.parametrize("cell", _READ_CELLS, ids=lambda cell: cell.id)
def test_a_preparation_inclusive_read_compiles_inside_its_window_and_a_reused_one_never_does(
    cell: support.FlowCell, compilations: list[int]
) -> None:
    marks: list[int] = []

    @dataclass(slots=True)
    class Marking(support.Stopwatch):
        def start(self) -> None:
            marks.append(compilations[0])
            support.Stopwatch.start(self)

        def stop(self) -> None:
            support.Stopwatch.stop(self)
            marks.append(compilations[0])

    with support.driver(cell) as driver:
        composed = compilations[0]
        for _ in range(2):
            driver.run(Marking())
    inside = [after - before for before, after in zip(marks[::2], marks[1::2], strict=True)]
    if cell.mode == "preparation-inclusive":
        assert composed == 0
        assert all(count >= 1 for count in inside)
    else:
        assert composed >= 1
        assert inside == [0, 0]


def test_measuring_keeps_every_sample_and_checks_every_run() -> None:
    cell = support.cell_named(_SOURCE_KEYED)
    reading = support.measure(cell, warmups=1, measured=3)
    assert len(reading.samples_us) == 3
    assert all(sample > 0 for sample in reading.samples_us)
    assert (reading.windows, reading.outcome) == (1, support.expected_outcome(cell))
    with pytest.raises(ValueError, match="measured must be positive"):
        support.measure(cell, warmups=0, measured=0)


def test_a_run_reporting_another_outcome_is_refused_rather_than_timed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def other(cell: support.Cell) -> support.Outcome:
        del cell
        return support.Outcome(statements=99)

    monkeypatch.setattr(support, "expected_outcome", other)
    with pytest.raises(RuntimeError, match="expected"):
        support.measure(support.cell_named(_SOURCE_KEYED), warmups=0, measured=1)


def test_a_stopwatch_refuses_unbalanced_windows() -> None:
    stopwatch = support.Stopwatch()
    with pytest.raises(RuntimeError, match="no window"):
        stopwatch.stop()
    stopwatch.start()
    with pytest.raises(RuntimeError, match="already open"):
        stopwatch.start()


# --------------------------------------------------------------------------- #
# Capture                                                                       #
# --------------------------------------------------------------------------- #
_SUBJECT: Mapping[str, object] = {"commit": "c0ffee", "productionDigest": "tree"}


def _samples(center: float, spread: float = 0.002) -> list[float]:
    return [center * (1 + spread * offset) for offset in range(-4, 5)]


def _reading(cell: support.Cell, samples: Sequence[float] | None = None) -> dict[str, object]:
    return {
        "cell": cell.id,
        "samplesUs": list(_samples(100.0) if samples is None else samples),
        "windows": 1,
        "outcome": support.expected_outcome(cell).document(),
    }


def test_a_capture_records_every_sample_identity_condition_and_failure(tmp_path: Path) -> None:
    measured, failing = (
        support.cell_named(_SOURCE_KEYED),
        support.AlgorithmCell("removal-window", 8),
    )
    samples = [float(value) for value in (9, 1, 8, 2, 7, 3, 6, 4, 5)]

    def reader(cell: support.Cell) -> Mapping[str, object] | str:
        return _reading(cell, samples) if cell == measured else "the child exited 1"

    output = tmp_path / "capture"
    assert tool.capture((measured, failing), output, reader, subject=_SUBJECT) == 3
    document = json.loads((output / tool.CAPTURE_FILE).read_text())
    record = document["cells"][measured.id]
    assert record["samplesUs"] == samples
    assert record["medianUs"] == 5.0
    assert (record["warmups"], record["measured"], record["windows"]) == (3, 9, 1)
    assert record["stages"] == support.description(measured).stages
    assert document["cells"][failing.id] == {"status": "failed", "reason": "the child exited 1"}
    assert document["subject"] == dict(_SUBJECT)
    assert document["support"] == tool.support_identity()
    assert document["sampling"] == tool.sampling()
    assert document["selections"] == [measured.id, failing.id]
    assert document["executionSeam"] == support.EXECUTION_SEAM
    assert {entry["reason"] for entry in document["notApplicable"]} == {
        entry.reason for entry in support.NOT_APPLICABLE
    }
    assert set(document["environment"]) >= set(tool.ENVIRONMENT_KEYS)


def test_a_recorded_capture_is_never_overwritten(tmp_path: Path) -> None:
    cell = support.cell_named(_SOURCE_KEYED)
    output = tmp_path / "capture"
    assert tool.capture((cell,), output, _reading, subject=_SUBJECT) == 0
    with pytest.raises(tool.CaptureError, match="immutable"):
        tool.capture((cell,), output, _reading, subject=_SUBJECT)


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"cell": "flow/other"}, "answered 'flow/other'"),
        ({"samplesUs": [1.0] * 8}, "9 positive samples"),
        ({"samplesUs": [0.0] * 9}, "9 positive samples"),
        ({"windows": 0}, "timed no window"),
        ({"outcome": support.Outcome(statements=1).document()}, "the outcome is not"),
    ],
)
def test_a_reading_that_is_not_a_complete_run_of_its_cell_is_refused(
    change: Mapping[str, object], reason: str
) -> None:
    cell = support.cell_named(_SOURCE_KEYED)
    record = tool.cell_record(cell, {**_reading(cell), **change})
    assert record["status"] == "failed"
    assert reason in cast("str", record["reason"])


def test_the_read_child_prints_one_reading_of_its_cell(capsys: pytest.CaptureFixture[str]) -> None:
    assert tool.main(["read", _SOURCE_KEYED, "--warmups", "0", "--measured", "2"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["cell"] == _SOURCE_KEYED
    assert len(document["samplesUs"]) == 2


def test_a_child_interpreter_answers_a_reading_the_capture_accepts() -> None:
    cell = support.cell_named(_SOURCE_KEYED)
    record = tool.cell_record(cell, tool.child_reader(cell))
    assert record["status"] == "measured", record
    assert len(cast("list[float]", record["samplesUs"])) == tool.MEASURED


def test_the_production_subject_is_the_checkout_commit_and_a_digest_of_its_sources() -> None:
    identity = tool.production_identity()
    assert len(cast("str", identity["commit"])) == 40
    assert len(cast("str", identity["productionDigest"])) == 64
    assert cast("int", identity["productionFiles"]) > 0


def test_a_files_digest_follows_contents_and_ignores_naming_order(tmp_path: Path) -> None:
    (tmp_path / "a").write_text("one")
    (tmp_path / "b").write_text("two")
    digest = tool.files_digest(tmp_path, ["a", "b"])
    assert tool.files_digest(tmp_path, ["b", "a"]) == digest
    (tmp_path / "b").write_text("three")
    assert tool.files_digest(tmp_path, ["a", "b"]) != digest


# --------------------------------------------------------------------------- #
# The comparison rule                                                           #
# --------------------------------------------------------------------------- #
_ENVIRONMENT: Mapping[str, object] = {
    "implementation": "CPython",
    "pythonVersion": "3.14.8",
    "system": "Darwin",
    "machine": "arm64",
    "node": "host",
}


def _document(
    cells: Mapping[str, Sequence[float] | None],
    *,
    production: str = "baseline-tree",
    support_digest: str = "support",
    environment: Mapping[str, object] | None = None,
    sampling: Mapping[str, object] | None = None,
    selections: Sequence[str] | None = None,
) -> dict[str, object]:
    return {
        "schemaVersion": tool.SCHEMA_VERSION,
        "kind": tool.CAPTURE_KIND,
        "subject": {"productionDigest": production},
        "support": {"digest": support_digest},
        "environment": {**_ENVIRONMENT, **(environment or {})},
        "sampling": dict(tool.sampling() if sampling is None else sampling),
        "executionSeam": support.EXECUTION_SEAM,
        "selections": list(cells if selections is None else selections),
        "notApplicable": [],
        "cells": {
            cell: (
                {"status": "failed", "reason": "the child exited 1"}
                if samples is None
                else {"status": "measured", "samplesUs": list(samples)}
            )
            for cell, samples in cells.items()
        },
    }


def _written(directory: Path, document: Mapping[str, object]) -> Path:
    directory.mkdir(parents=True)
    (directory / tool.CAPTURE_FILE).write_text(json.dumps(document))
    return directory


@dataclass(slots=True)
class _Scripted:
    """Repetitions answering scripted medians, in the order each subject is
    captured; every call is recorded."""

    baseline: list[float]
    candidate: list[float]
    productions: Mapping[str, str] = field(
        default_factory=lambda: {"baseline": "baseline-tree", "candidate": "candidate-tree"}
    )
    calls: list[str] = field(default_factory=list[str])

    def __call__(self, subject: tool.Subject, cell: support.Cell, destination: Path) -> Path | str:
        self.calls.append(subject)
        median = (self.baseline if subject == "baseline" else self.candidate).pop(0)
        return _written(
            destination,
            _document({cell.id: _samples(median)}, production=self.productions[subject]),
        )


def _compared(
    tmp_path: Path,
    baseline: Sequence[float] | None,
    candidate: Sequence[float] | None,
    *,
    repeater: tool.Repeater | None = None,
    max_rounds: int = tool.DEFAULT_MAX_ROUNDS,
    **candidate_conditions: Any,
) -> dict[str, Any]:
    before = _written(tmp_path / "baseline", _document({_SOURCE_KEYED: baseline}))
    after = _written(
        tmp_path / "candidate",
        _document({_SOURCE_KEYED: candidate}, production="candidate-tree", **candidate_conditions),
    )
    output = tmp_path / "comparison"
    result = tool.compare(before, after, output, repeater=repeater, max_rounds=max_rounds)
    document = json.loads((output / tool.COMPARISON_FILE).read_text())
    assert document["result"] == result
    return document


def _only(document: Mapping[str, Any]) -> dict[str, Any]:
    (cell,) = document["cells"]
    return cell


def test_indistinguishable_captures_pass_the_screen_without_repetition(tmp_path: Path) -> None:
    baseline = [90.0, 110.0, 95.0, 105.0, 100.0, 98.0, 102.0, 97.0, 103.0]
    candidate = [value * 1.01 for value in reversed(baseline)]
    repeater = _Scripted([], [])
    cell = _only(_compared(tmp_path, baseline, candidate, repeater=repeater))
    assert (cell["result"], cell["basis"]) == ("no-detected-regression", "screen")
    assert cell["initial"]["suspect"] == []
    assert repeater.calls == []


def test_an_improvement_is_repeated_and_a_stable_one_is_no_regression(tmp_path: Path) -> None:
    # A faster candidate capture may only have been taken under kinder host
    # conditions, so the screen repeats it; paired rounds then show the change.
    repeater = _Scripted(baseline=[100, 100.5, 100, 99.5, 100, 100.2], candidate=[80, 81, 80.5])
    cell = _only(_compared(tmp_path, _samples(100), _samples(80), repeater=repeater))
    assert cell["initial"]["suspect"] == ["beyond-investigation-trigger", "consistent-shift"]
    assert (cell["result"], cell["basis"]) == ("no-detected-regression", "repetition")
    assert all(taken["change"] < 0 for taken in cell["rounds"])


def test_a_slowdown_an_unrelated_speedup_concealed_is_found_by_repetition(
    tmp_path: Path,
) -> None:
    repeater = _Scripted(
        baseline=[100, 100.3, 100, 99.8, 100, 100.1], candidate=[104, 104.2, 104.1]
    )
    cell = _only(_compared(tmp_path, _samples(100), _samples(85), repeater=repeater))
    assert cell["result"] == "reproducible-regression"


def test_a_regression_beyond_the_trigger_that_repeats_is_reproducible(tmp_path: Path) -> None:
    repeater = _Scripted(baseline=[100, 101, 100, 99, 100, 100.5], candidate=[121, 119, 120])
    cell = _only(_compared(tmp_path, _samples(100), _samples(120), repeater=repeater))
    assert cell["result"] == "reproducible-regression"
    assert cell["initial"]["suspect"] == ["beyond-investigation-trigger", "consistent-shift"]
    odd, even = ["baseline", "candidate", "baseline"], ["candidate", "baseline", "baseline"]
    assert [taken["order"] for taken in cell["rounds"]] == [odd, even, odd]
    assert repeater.calls == [*odd, *even, *odd]
    assert cell["rounds"][1]["change"] == pytest.approx(math.log(1.19), rel=1e-3)
    error = tool.median_error(_samples(100))
    assert cell["rounds"][0]["resolution"] == pytest.approx(2 * math.hypot(error, error))


def test_a_consistent_regression_below_the_trigger_is_repeated_and_reproducible(
    tmp_path: Path,
) -> None:
    repeater = _Scripted(
        baseline=[100, 100.2, 100, 99.9, 100, 100.1], candidate=[103, 102.9, 103.1]
    )
    cell = _only(_compared(tmp_path, _samples(100), _samples(103), repeater=repeater))
    assert cell["initial"]["suspect"] == ["consistent-shift"]
    assert cell["result"] == "reproducible-regression"


def test_a_suspect_change_repetition_shows_within_baseline_variation_is_no_regression(
    tmp_path: Path,
) -> None:
    repeater = _Scripted(baseline=[100, 101, 100, 98.5, 100, 99], candidate=[100.5, 99, 100.2])
    cell = _only(_compared(tmp_path, _samples(100), _samples(107), repeater=repeater))
    assert (cell["result"], cell["basis"]) == ("no-detected-regression", "repetition")
    bands = cell["bands"]
    assert bands["smallestBaselineVariation"] == pytest.approx(math.log(1.01), rel=1e-3)
    assert bands["largestBaselineVariation"] == pytest.approx(-math.log(0.985), rel=1e-3)


def test_a_noisy_baseline_that_never_separates_exhausts_its_rounds_inconclusive(
    tmp_path: Path,
) -> None:
    noisy = [80.0, 85.0, 90.0, 95.0, 100.0, 105.0, 110.0, 115.0, 120.0]
    repeater = _Scripted(baseline=[100, 104, 100, 103, 100, 100.5], candidate=[108, 101, 106])
    cell = _only(_compared(tmp_path, noisy, noisy, repeater=repeater))
    assert cell["initial"]["suspect"] == ["excessive-variability"]
    assert cell["result"] == "inconclusive"
    assert len(cell["rounds"]) == 3
    assert "undecided after 3 of at most 3 rounds" in cell["basis"]


@pytest.mark.parametrize("max_rounds", [1, 2])
def test_fewer_rounds_than_a_conclusion_needs_never_conclude(
    tmp_path: Path, max_rounds: int
) -> None:
    repeater = _Scripted(baseline=[100, 100] * max_rounds, candidate=[130] * max_rounds)
    cell = _only(
        _compared(tmp_path, _samples(100), _samples(130), repeater=repeater, max_rounds=max_rounds)
    )
    assert cell["result"] == "inconclusive"
    assert len(cell["rounds"]) == max_rounds


def test_a_suspect_cell_without_requested_repetition_is_inconclusive(tmp_path: Path) -> None:
    cell = _only(_compared(tmp_path, _samples(100), _samples(130)))
    assert cell["result"] == "inconclusive"


@pytest.mark.parametrize(
    ("baseline", "candidate", "absent"),
    [
        (None, _samples(100), "baseline"),
        (_samples(100), None, "candidate"),
    ],
)
def test_a_failed_cell_is_missing_evidence(
    tmp_path: Path, baseline: list[float] | None, candidate: list[float] | None, absent: str
) -> None:
    document = _compared(tmp_path, baseline, candidate)
    assert (_only(document)["result"], document["result"]) == (
        "missing-or-incompatible-evidence",
        "missing-or-incompatible-evidence",
    )
    assert absent in _only(document)["basis"]


def test_a_cell_one_capture_never_selected_is_missing_evidence(tmp_path: Path) -> None:
    other = "flow/read-eager/wire/document/reused-execution"
    before = _written(
        tmp_path / "baseline",
        _document({_SOURCE_KEYED: _samples(100), other: _samples(100)}),
    )
    after = _written(tmp_path / "candidate", _document({_SOURCE_KEYED: _samples(100)}))
    assert tool.compare(before, after, tmp_path / "out") == "missing-or-incompatible-evidence"
    document = json.loads((tmp_path / "out" / tool.COMPARISON_FILE).read_text())
    assert [cell["cell"] for cell in document["cells"]] == [_SOURCE_KEYED, other]
    assert document["cells"][1]["result"] == "missing-or-incompatible-evidence"
    assert document["complete"] is False


@pytest.mark.parametrize(
    ("conditions", "problem"),
    [
        ({"support_digest": "other"}, "measurement-support digests differ"),
        ({"sampling": {"warmups": 1}}, "sampling differs"),
        ({"environment": {"pythonVersion": "3.13.1"}}, "pythonVersion differs"),
        ({"environment": {"node": "elsewhere"}}, "node differs"),
    ],
)
def test_incompatible_captures_judge_no_timing_at_all(
    tmp_path: Path, conditions: Mapping[str, Any], problem: str
) -> None:
    repeater = _Scripted([], [])
    document = _compared(tmp_path, _samples(100), _samples(130), repeater=repeater, **conditions)
    assert document["result"] == "missing-or-incompatible-evidence"
    assert any(problem in reason for reason in document["compatibility"])
    assert "initial" not in _only(document)
    assert repeater.calls == []


def test_a_failed_repetition_is_missing_evidence(tmp_path: Path) -> None:
    def failing(subject: tool.Subject, cell: support.Cell, destination: Path) -> Path | str:
        del cell, destination
        return f"the {subject} capture exited 1"

    cell = _only(_compared(tmp_path, _samples(100), _samples(130), repeater=failing))
    assert cell["result"] == "missing-or-incompatible-evidence"
    assert cell["basis"] == "the baseline capture exited 1"


def test_a_repetition_from_another_production_subject_is_missing_evidence(tmp_path: Path) -> None:
    repeater = _Scripted(
        baseline=[100, 100],
        candidate=[130],
        productions={"baseline": "baseline-tree", "candidate": "moved-tree"},
    )
    cell = _only(_compared(tmp_path, _samples(100), _samples(130), repeater=repeater))
    assert cell["result"] == "missing-or-incompatible-evidence"
    assert "production subject" in cell["basis"]


def test_the_comparisons_result_is_its_most_severe_cell() -> None:
    assert tool.overall(["no-detected-regression", "inconclusive"]) == "inconclusive"
    assert (
        tool.overall(["inconclusive", "reproducible-regression", "no-detected-regression"])
        == "reproducible-regression"
    )
    assert (
        tool.overall(["reproducible-regression", "missing-or-incompatible-evidence"])
        == "missing-or-incompatible-evidence"
    )
    assert tool.overall(["no-detected-regression"]) == "no-detected-regression"
    assert tool.overall([]) == "missing-or-incompatible-evidence"


def _round(
    index: int, baseline: float, candidate: float, control: float, resolution: float = 0.0
) -> tool.Round:
    return tool.Round(index, baseline, candidate, control, resolution, ())


def _rounds(
    changes: Sequence[float], controls: Sequence[float], resolution: float = 0.0
) -> list[tool.Round]:
    return [
        _round(index, 100, 100 * (1 + change), 100 * (1 + control), resolution)
        for index, (change, control) in enumerate(zip(changes, controls, strict=True), start=1)
    ]


def test_a_regression_needs_every_round_beyond_the_largest_baseline_variation() -> None:
    assert tool.judge(_rounds([0.5, 0.5], [0.0, 0.0])) is None
    regressed = _rounds([0.04, 0.03, 0.05], [0.01, -0.02, 0.005])
    assert tool.judge(regressed) == "reproducible-regression"
    assert tool.judge(_rounds([0.04, 0.01, 0.05], [0.01, -0.02, 0.005])) is None


def test_no_regression_needs_the_typical_change_within_the_smallest_baseline_variation() -> None:
    within = _rounds([0.004, -0.01, 0.02], [0.01, -0.02, 0.005])
    assert tool.judge(within) == "no-detected-regression"
    assert tool.judge(_rounds([-0.2, -0.1, -0.15], [0.01, -0.02, 0.005])) == (
        "no-detected-regression"
    )
    # One spiked control widens the largest variation but not the smallest, so
    # a large change it would otherwise excuse stays undecided.
    assert tool.judge(_rounds([0.3, 0.25, 0.28], [0.01, 0.4, -0.02])) is None


def test_a_regression_must_also_exceed_what_the_medians_can_resolve() -> None:
    # A quiet control leaves a 0.1% band; every change exceeds it but stays
    # within the 1% the medians resolve, so nothing is concluded.
    assert tool.judge(_rounds([0.003, 0.007, 0.005], [0.001, -0.0005, 0.001], 0.01)) is None
    resolved = _rounds([0.02, 0.025, 0.03], [0.001, -0.0005, 0.001], 0.01)
    assert tool.judge(resolved) == "reproducible-regression"


def test_a_medians_error_follows_its_capture_dispersion() -> None:
    assert tool.median_error(_samples(100)) == pytest.approx(
        1.2533 * tool.dispersion(_samples(100)) / 1.349 / 3
    )
    assert tool.median_error(_samples(100, 0.02)) > tool.median_error(_samples(100))


def test_the_screen_names_each_reason_a_cell_is_suspect() -> None:
    both = ("beyond-investigation-trigger", "consistent-shift")
    assert tool.screen(_samples(100), _samples(106)).reasons == both
    assert tool.screen(_samples(100), _samples(94)).reasons == both
    assert tool.screen(_samples(100), _samples(98)).reasons == ("consistent-shift",)
    assert tool.screen(_samples(100), _samples(100)).reasons == ()
    wide = [80.0, 85.0, 90.0, 95.0, 100.0, 105.0, 110.0, 115.0, 120.0]
    assert tool.screen(wide, wide).reasons == ("excessive-variability",)


def test_a_comparison_never_overwrites_a_recorded_one(tmp_path: Path) -> None:
    before = _written(tmp_path / "baseline", _document({_SOURCE_KEYED: _samples(100)}))
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "kept").write_text("")
    with pytest.raises(tool.CaptureError, match="immutable"):
        tool.compare(before, before, tmp_path / "out")


def test_an_unreadable_capture_is_refused(tmp_path: Path) -> None:
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / tool.CAPTURE_FILE).write_text(json.dumps({"kind": "other"}))
    with pytest.raises(tool.CaptureError, match="is not a version"):
        tool.load_capture(tmp_path / "bad")
    with pytest.raises(tool.CaptureError, match="no readable capture"):
        tool.load_capture(tmp_path / "absent")


def test_the_compare_command_exits_zero_only_without_any_detected_regression(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = _written(tmp_path / "baseline", _document({_SOURCE_KEYED: _samples(100)}))
    same = _written(tmp_path / "same", _document({_SOURCE_KEYED: _samples(100)}))
    slower = _written(tmp_path / "slower", _document({_SOURCE_KEYED: _samples(130)}))
    arguments = ["compare", "--baseline", str(before)]
    assert tool.main([*arguments, "--candidate", str(same), "--output", str(tmp_path / "a")]) == 0
    assert tool.main([*arguments, "--candidate", str(slower), "--output", str(tmp_path / "b")]) == 1
    assert "inconclusive" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("arguments", "reason"),
    [
        (["--repeat"], "requires --baseline-worktree"),
        (["--baseline-worktree", "x", "--candidate-worktree", "y"], "only with --repeat"),
        (
            [
                "--repeat",
                "--baseline-worktree",
                "x",
                "--candidate-worktree",
                "y",
                "--max-repeat-rounds",
                "-1",
            ],
            "non-negative",
        ),
    ],
)
def test_the_compare_command_refuses_an_incoherent_repetition_request(
    arguments: list[str], reason: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = _written(tmp_path / "baseline", _document({_SOURCE_KEYED: _samples(100)}))
    command = ["compare", "--baseline", str(before), "--candidate", str(before)]
    assert tool.main([*command, *arguments, "--output", str(tmp_path / "out")]) == 2
    assert reason in capsys.readouterr().err


def test_a_worktree_repetition_captures_one_cell_through_that_worktrees_environment(
    tmp_path: Path,
) -> None:
    cell = support.cell_named(_SOURCE_KEYED)
    command = tool.repetition_command(cell, tmp_path / "round")
    assert command[:6] == [
        "uv",
        "run",
        "--frozen",
        "python",
        "tools/time_interval_runtime.py",
        "capture",
    ]
    assert command[6:] == [*tool.selection_arguments(cell), "--output", str(tmp_path / "round")]
    repeater = tool.WorktreeRepeater(tmp_path / "no-baseline", tmp_path / "no-candidate")
    failure = repeater("baseline", cell, tmp_path / "round")
    assert isinstance(failure, str)
    assert "could not be started" in failure
