"""What the instance-state report is asked for, and every verdict it computes.

``docs/instance-state-baseline.md`` records what a published Entity retains under
both backings, and `just python-report-instance-state` re-derives it. Neither
grades a byte total — one is machine- and interpreter-relative — so what is
gradeable here is everything ABOUT a reading rather than any reading: the mix the
measurement contract names, the warmed scenario held outside every aggregate, the
matrix being the supported minors, an aggregate dividing sums rather than
averaging percentages, the escalation block naming a missed target and a
regression past the limit, and a matrix cell with no reading ending the run
instead of thinning the table.

Every one of those is fed DOCTORED readings, built here with numbers chosen for
what they prove. That is what lets this suite grade a verdict without taking a
measurement — and nothing here measures, deliberately: every reading the report
takes reads the whole interpreter and belongs in a child of its own, which is what
the report's own `in_a_child` is for. A test taking one beside the rest of the
suite would be classified `dbfree` while needing an interpreter no other test
shares.

The arm the report compares against is a fixture: ``legacy_publication`` builds
one node the way Entity Graph Construction built one before the flip, with a
zero-argument ``model_construct`` filled a member at a time. While that path
existed the report compared every scenario's fixture against it before measuring
anything, and refused to measure a fixture that had drifted; the flip deleted the
path and that check retired with it.
"""

from __future__ import annotations

import tomllib
from typing import cast

import pytest
from _instance_state_support import REPORTED, SCENARIOS, WARMED_AUXILIARY, Scenario

import instance_state_overhead as report


def test_the_canonical_mix_is_the_six_scenarios_the_measurement_contract_names() -> None:
    assert tuple(scenario.name for scenario in SCENARIOS) == (
        "shallow",
        "wide",
        "nested",
        "nullable",
        "partial",
        "polymorphic",
    )


def test_the_report_refuses_more_than_one_scenario_argument(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert report.main(["shallow", "wide"]) == 2
    assert "usage:" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# The mix, and what is measured beside it.                                     #
# --------------------------------------------------------------------------- #


def test_the_warmed_auxiliary_scenario_is_reported_beside_the_mix_and_outside_it() -> None:
    assert WARMED_AUXILIARY not in SCENARIOS
    assert (*SCENARIOS, WARMED_AUXILIARY) == REPORTED
    assert WARMED_AUXILIARY.warms
    assert not any(scenario.warms for scenario in SCENARIOS)
    assert [reading.scenario for reading in report.canonical(_matrix()["3.14"])] == [
        scenario.name for scenario in SCENARIOS
    ]


def test_the_matrix_is_every_python_minor_the_workspace_declares_support_for() -> None:
    minors = report.supported_minors()
    declared = tomllib.loads((report.WORKSPACE / "pyproject.toml").read_text())["project"][
        "requires-python"
    ]
    assert minors[0] == declared.removeprefix(">=").strip()
    assert minors[-1] == report.CURRENT_MINOR
    assert len(minors) == len(set(minors))


# --------------------------------------------------------------------------- #
# The two aggregates, summed rather than averaged.                             #
# --------------------------------------------------------------------------- #


def test_an_aggregate_divides_sums_rather_than_averaging_percentages() -> None:
    readings = [
        _reading("small", retained=(100, 10), bare=(90, 9)),
        _reading("large", retained=(1_000, 900), bare=(900, 810)),
    ]
    primary, secondary = report.aggregates(readings)
    assert (primary.before, primary.after) == (1_100, 910)
    assert primary.reduction == pytest.approx(1 - 910 / 1_100)
    assert secondary.reduction == pytest.approx(1 - 819 / 990)
    mean = sum(reading.reduction for reading in readings) / len(readings)
    assert primary.reduction != pytest.approx(mean)


def test_each_scenario_carries_its_own_percentage_as_a_diagnostic() -> None:
    reading = _reading("small", retained=(1_000, 250), bare=(800, 400))
    assert reading.reduction == pytest.approx(0.75)
    assert reading.bare_reduction == pytest.approx(0.5)


# --------------------------------------------------------------------------- #
# The escalation block, fed doctored readings.                                 #
# --------------------------------------------------------------------------- #


def test_the_escalation_block_names_a_primary_aggregate_short_of_its_target() -> None:
    readings = [_reading("shallow", retained=(1_000, 700), bare=(900, 600))]
    block = report.escalation_block({"3.14": {"shallow": readings[0]}})
    assert block[0] == "REVIEW REQUIRED"
    assert "primary aggregate 30.0% < 33%" in block[1]
    assert "return the measured result to the user for a decision" in block[1]


def test_the_escalation_block_names_a_representative_operation_past_its_limit() -> None:
    reading = _reading(
        "shallow",
        retained=(1_000, 100),
        bare=(900, 90),
        legacy_ns=(1_000.0, 20.0, 500.0),
        compact_ns=(1_100.0, 80.0, 505.0),
    )
    block = report.escalation_block({"3.14": {"shallow": reading}})
    raised = "\n".join(block)
    assert block[0] == "REVIEW REQUIRED"
    assert "attribute read 4.00x over the mix" in raised
    assert "surfaced for human review" in raised
    assert "construction" not in raised
    assert "serialization" not in raised


def test_a_reading_that_meets_both_rules_raises_no_escalation() -> None:
    reading = _reading(
        "shallow",
        retained=(1_000, 100),
        bare=(900, 90),
        legacy_ns=(1_000.0, 20.0, 500.0),
        compact_ns=(1_100.0, 22.0, 505.0),
    )
    block = report.escalation_block({"3.14": {"shallow": reading}})
    assert block == [
        "no escalation: every runtime's primary aggregate reaches 33% and no "
        "representative operation moved past 1.20x"
    ]


def test_one_runtime_missing_its_target_escalates_for_that_runtime_alone() -> None:
    passing = _reading("shallow", retained=(1_000, 100), bare=(900, 90))
    failing = _reading("shallow", retained=(1_000, 900), bare=(900, 810))
    block = report.escalation_block({"3.13": {"shallow": failing}, "3.14": {"shallow": passing}})
    raised = "\n".join(block)
    assert "CPython 3.13: primary aggregate" in raised
    assert "CPython 3.14: primary aggregate" not in raised


# --------------------------------------------------------------------------- #
# Completeness, which is the one verdict this report exits on.                 #
# --------------------------------------------------------------------------- #


def test_a_matrix_cell_with_no_reading_is_named_with_its_reason() -> None:
    matrix = _matrix()
    matrix["3.14"]["nested"] = "the child exited 1"
    del matrix["3.14"]["wide"]
    absent = report.missing_cells(matrix, REPORTED)
    assert absent == [
        "CPython 3.14, wide: no child was run",
        "CPython 3.14, nested: the child exited 1",
    ]
    assert not report.missing_cells(_matrix(), REPORTED)


def test_a_missing_cell_is_a_non_zero_exit_rather_than_a_silent_omission(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def one_child(runtime: str, scenario: Scenario) -> report.Cell:
        if scenario.name == "nested":
            return "the child exited 1"
        return _reading(scenario.name)

    monkeypatch.setattr(report, "in_a_child", one_child)
    assert report.main([]) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "the matrix is incomplete, so no aggregate is reported:" in captured.err
    assert "nested: the child exited 1" in captured.err


def test_every_scenario_both_aggregates_and_every_timing_appear_for_every_runtime() -> None:
    printed = "\n".join(report.render({"3.13": _matrix()["3.14"], "3.14": _matrix()["3.14"]}))
    for runtime in ("CPython 3.13", "CPython 3.14"):
        assert printed.count(runtime) >= 1
    for scenario in REPORTED:
        assert printed.count(scenario.name) >= 2
    assert printed.count("primary (lifecycle included)") == 2
    assert printed.count("secondary (lifecycle excluded)") == 2
    for column in ("build us", "read ns", "dump us", "transient B", "peak B", "cells"):
        assert printed.count(column) == 2


def test_a_child_answers_one_scenario_as_a_line_the_matrix_decodes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    line = report._payload(_reading("shallow"))  # pyright: ignore[reportPrivateUsage] - the child protocol
    print(line)
    decoded = report._decoded(capsys.readouterr().out)  # pyright: ignore[reportPrivateUsage] - the child protocol
    assert decoded == _reading("shallow")


def test_a_child_that_answers_nothing_usable_is_a_reason_rather_than_a_crash() -> None:
    assert report._decoded("") == "the child printed nothing"  # pyright: ignore[reportPrivateUsage] - the child protocol
    assert "did not decode" in cast(
        "str",
        report._decoded("not json"),  # pyright: ignore[reportPrivateUsage] - the child protocol
    )
    assert "did not decode" in cast(
        "str",
        report._decoded('{"scenario": "shallow"}'),  # pyright: ignore[reportPrivateUsage] - the child protocol
    )


# --------------------------------------------------------------------------- #
# Doctored readings.                                                           #
# --------------------------------------------------------------------------- #


def _arm(retained: int, bare: int, timings: tuple[float, float, float]) -> report.ArmReading:
    construct_ns, read_ns, dump_ns = timings
    return report.ArmReading(
        cells=6,
        retained_bytes=retained,
        bare_bytes=bare,
        transient_bytes=512,
        construct_ns=construct_ns,
        read_ns=read_ns,
        dump_ns=dump_ns,
    )


def _reading(
    scenario: str,
    *,
    retained: tuple[int, int] = (1_000, 100),
    bare: tuple[int, int] = (900, 90),
    legacy_ns: tuple[float, float, float] = (1_000.0, 20.0, 500.0),
    compact_ns: tuple[float, float, float] = (1_000.0, 20.0, 500.0),
) -> report.Reading:
    """One scenario's reading, with every number chosen rather than measured."""
    return report.Reading(
        scenario=scenario,
        summary=f"the {scenario} scenario",
        fields=4,
        legacy=_arm(retained[0], bare[0], legacy_ns),
        compact=_arm(retained[1], bare[1], compact_ns),
    )


def _matrix() -> report.Matrix:
    """One complete runtime's worth of doctored readings."""
    return {"3.14": {scenario.name: _reading(scenario.name) for scenario in REPORTED}}
