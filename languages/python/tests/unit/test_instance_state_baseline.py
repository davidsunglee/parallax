"""What the instance-state report is asked for, and every comparison it computes.

``docs/instance-state-baseline.md`` records what a published Entity retains under
each backing, and `just python-report-instance-state` re-derives it. Neither
grades a byte total — one is machine- and interpreter-relative — so what is
gradeable here is everything ABOUT a reading rather than any reading: the mix the
measurement contract names, the warmed scenario held outside every aggregate, the
matrix being the supported minors, an aggregate dividing sums rather than
averaging percentages, the ordinary arm staying out of both, construction being
split into a per-node cost and a per-call one, the construction ratio being
corrected by the per-node work the legacy fixture never reproduced and the
regression rule grading that corrected figure, the escalation block naming a
missed target and a regression past the limit, and a matrix cell with no reading
ending the run instead of thinning the table.

Every one of those is fed DOCTORED readings, built here with numbers chosen for
what they prove. That is what lets this suite grade what the report computes
without taking a measurement — and nothing here CAN measure: a reading reads the whole interpreter
and belongs in a child of its own, so it lives in `tools/instance_state_reading.py`
and the module imported here neither binds an instrument nor reaches one. A test
taking a reading beside the rest of the suite would be classified `dbfree` while
needing an interpreter no other test shares.

The arm the aggregates compare against is a fixture: ``legacy_publication``
builds one node the way Entity Graph Construction built one before the flip, with
a zero-argument ``model_construct`` filled a member at a time. While that path
existed the report compared every scenario's fixture against it before measuring
anything, and refused to measure a fixture that had drifted; the flip deleted the
path and that check retired with it. The third arm, ordinary validating
construction, is a different comparison and enters no aggregate — which is itself
one of the things graded here.
"""

from __future__ import annotations

import pathlib
import tomllib
from time import perf_counter
from typing import cast

import pytest
from _instance_state_support import (
    ARMS,
    COMPACT,
    LEGACY,
    ORDINARY,
    REPORTED,
    SCENARIOS,
    WARMED_AUXILIARY,
    Scenario,
    compact_callback_ns,
)

import instance_state_overhead as report
from parallax.core.entity import lifecycle_state_of


def test_the_canonical_mix_is_the_six_scenarios_the_measurement_contract_names() -> None:
    assert tuple(scenario.name for scenario in SCENARIOS) == (
        "shallow",
        "wide",
        "nested",
        "nullable",
        "partial",
        "polymorphic",
    )


def test_the_report_takes_no_arguments_because_it_measures_nothing_itself(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert report.main(["shallow"]) == 2
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
    assert declared == f">={minors[0]}"
    assert len(minors) == report.SUPPORTED_MINORS
    major, floor = (int(part) for part in minors[0].split("."))
    assert minors == tuple(f"{major}.{floor + above}" for above in range(len(minors)))


def test_the_matrix_is_the_declared_range_whichever_interpreter_takes_the_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    declared = report.supported_minors()
    monkeypatch.setattr(report, "CURRENT_MINOR", "3.0")
    assert report.supported_minors() == declared


def test_a_requires_python_this_report_cannot_read_a_range_off_is_refused(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = "~=3.13"\n')
    monkeypatch.setattr(report, "WORKSPACE", tmp_path)
    with pytest.raises(SystemExit, match="supported range"):
        report.supported_minors()


# --------------------------------------------------------------------------- #
# The two aggregates, summed rather than averaged, and the third comparison    #
# reported outside them.                                                       #
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


def test_both_aggregates_divide_the_legacy_arm_and_neither_sees_the_ordinary_one() -> None:
    readings = [
        _reading(
            "small",
            retained=(100, 10),
            bare=(90, 9),
            ordinary_retained=400,
            ordinary_bare=380,
        )
    ]
    primary, secondary = report.aggregates(readings)
    assert (primary.before, primary.after) == (100, 10)
    assert (secondary.before, secondary.after) == (90, 9)
    doubled = [readings[0]._replace(ordinary=readings[0].ordinary._replace(retained_bytes=99_999))]
    assert report.aggregates(doubled) == report.aggregates(readings)


def test_the_ordinary_comparison_is_reported_beside_the_aggregates_and_not_in_them() -> None:
    readings = [
        _reading(
            "small",
            retained=(100, 40),
            bare=(90, 36),
            ordinary_retained=400,
            ordinary_bare=360,
        ),
        _reading(
            "large",
            retained=(1_000, 360),
            bare=(900, 324),
            ordinary_retained=600,
            ordinary_bare=540,
        ),
    ]
    ordinary = report.against_ordinary(readings)
    assert (ordinary.before, ordinary.after) == (1_000, 400)
    assert ordinary.reduction == pytest.approx(0.6)
    assert ordinary.retention == pytest.approx(0.4)
    primary, _ = report.aggregates(readings)
    assert primary.before == 1_100


def test_a_scenario_carries_both_comparisons_and_they_can_disagree() -> None:
    reading = _reading(
        "partial",
        retained=(1_000, 500),
        bare=(900, 450),
        ordinary_retained=800,
        ordinary_bare=720,
    )
    assert reading.reduction == pytest.approx(0.5)
    assert reading.bare_reduction == pytest.approx(0.5)
    assert reading.ordinary_reduction == pytest.approx(0.375)
    assert reading.ordinary_bare_reduction == pytest.approx(0.375)


# --------------------------------------------------------------------------- #
# Construction, at the scope the arms have in common.                          #
# --------------------------------------------------------------------------- #


def test_construction_is_the_cost_of_one_more_node_with_the_call_left_beside_it() -> None:
    per_node, per_call = report.marginal(one_node_ns=1_000.0, many_nodes_ns=1_000.0 + 10 * 400.0)
    assert per_node == pytest.approx(400.0)
    assert per_call == pytest.approx(600.0)


def test_an_arm_that_builds_a_node_and_nothing_else_reports_no_per_call_cost() -> None:
    per_node, per_call = report.marginal(one_node_ns=400.0, many_nodes_ns=400.0 * 11)
    assert per_node == pytest.approx(400.0)
    assert per_call == pytest.approx(0.0)


def test_two_arms_whose_calls_cost_differently_still_compare_at_the_node() -> None:
    # The defect this scope exists to remove: pricing a whole call would make the
    # compact arm 3.50x here and escalate it, where one more node of it costs
    # 1.10x one of the legacy arm's and is inside the limit.
    legacy_call, compact_call = 400.0, 1_400.0
    legacy = report.marginal(legacy_call, legacy_call + 10 * 400.0)
    compact = report.marginal(compact_call, compact_call + 10 * 440.0)
    assert compact[0] / legacy[0] == pytest.approx(1.10)
    assert compact_call / legacy_call == pytest.approx(3.50)
    reading = _reading("shallow")._replace(
        legacy=_arm(1_000, 900, (legacy[0], 20.0, 500.0)),
        compact=_arm(100, 90, (compact[0], 20.0, 500.0)),
    )
    assert report.mix_ratio([reading], report.OPERATIONS[0]) == pytest.approx(1.10)
    assert "construction" not in "\n".join(report.escalation_block({"3.14": {"shallow": reading}}))


def test_the_construction_ratio_is_corrected_by_what_the_fixture_never_reproduced() -> None:
    reading = _reading(
        "shallow",
        legacy_ns=(1_000.0, 20.0, 500.0),
        compact_ns=(1_300.0, 20.0, 500.0),
        scaffolding_ns=300.0,
    )
    construction = report.OPERATIONS[0]
    assert report.mix_ratio([reading], construction) == pytest.approx(1.30)
    assert report.like_for_like_ratio([reading], construction) == pytest.approx(1.00)
    assert report.before_ns(reading, construction) == pytest.approx(1_300.0)
    assert report.scenario_ratio(reading, construction) == pytest.approx(1.00)


def test_an_operation_whose_arms_do_the_same_work_is_corrected_by_nothing() -> None:
    reading = _reading(
        "shallow",
        legacy_ns=(1_000.0, 20.0, 500.0),
        compact_ns=(1_300.0, 60.0, 1_000.0),
        scaffolding_ns=300.0,
    )
    for operation in report.OPERATIONS[1:]:
        assert report.like_for_like_ratio([reading], operation) == pytest.approx(
            report.mix_ratio([reading], operation)
        )
        assert operation.unreproduced(reading.compact) == 0.0
    assert report.mix_ratio([reading], report.OPERATIONS[1]) == pytest.approx(3.0)


def test_the_correction_is_summed_over_the_mix_rather_than_averaged() -> None:
    readings = [
        _reading("small", legacy_ns=(100.0, 20.0, 500.0), compact_ns=(400.0, 20.0, 500.0)),
        _reading(
            "large",
            legacy_ns=(4_000.0, 20.0, 500.0),
            compact_ns=(4_400.0, 20.0, 500.0),
            scaffolding_ns=300.0,
        ),
    ]
    construction = report.OPERATIONS[0]
    assert report.like_for_like_ratio(readings, construction) == pytest.approx(4_800 / 4_400)
    mean = sum(report.scenario_ratio(reading, construction) for reading in readings) / 2
    assert report.like_for_like_ratio(readings, construction) != pytest.approx(mean)


def test_only_the_arm_whose_call_does_more_than_build_nodes_reports_scaffolding() -> None:
    assert (ORDINARY.callbacks_ns, LEGACY.callbacks_ns) == (None, None)
    assert COMPACT.callbacks_ns is compact_callback_ns
    assert COMPACT.graph is not compact_callback_ns


def test_the_compact_arm_times_its_own_callbacks_and_leaves_the_call_a_remainder() -> None:
    scenario = SCENARIOS[0]
    compact_callback_ns(scenario, report.MARGINAL_NODES)
    start = perf_counter()
    inside = compact_callback_ns(scenario, report.MARGINAL_NODES)
    whole = (perf_counter() - start) * 1e9
    assert 0.0 < inside < whole


def test_each_operation_is_reported_against_the_ordinary_arm_as_well() -> None:
    reading = _reading(
        "shallow",
        legacy_ns=(1_000.0, 20.0, 500.0),
        compact_ns=(1_500.0, 60.0, 1_000.0),
    )._replace(ordinary=_arm(2_000, 1_800, (500.0, 30.0, 250.0)))
    assert report.ordinary_ratio([reading], report.OPERATIONS[0]) == pytest.approx(3.0)
    assert report.ordinary_ratio([reading], report.OPERATIONS[1]) == pytest.approx(2.0)
    assert report.ordinary_ratio([reading], report.OPERATIONS[2]) == pytest.approx(4.0)
    assert report.mix_ratio([reading], report.OPERATIONS[1]) == pytest.approx(3.0)


def test_no_ordinary_ratio_can_reach_the_escalation_block() -> None:
    reading = _reading(
        "shallow",
        retained=(1_000, 100),
        bare=(900, 90),
        legacy_ns=(1_000.0, 20.0, 500.0),
        compact_ns=(1_100.0, 22.0, 505.0),
    )._replace(ordinary=_arm(2_000, 1_800, (1.0, 1.0, 1.0)))
    block = report.escalation_block({"3.14": {"shallow": reading}})
    assert block[0].startswith("no escalation")


def test_every_arm_pairs_its_node_builder_with_its_own_graph_builder() -> None:
    assert ARMS == (ORDINARY, LEGACY, COMPACT)
    assert [arm.name for arm in ARMS] == ["ordinary", "legacy", "compact"]
    for arm in ARMS:
        scenario = SCENARIOS[0]
        graph = arm.graph(scenario, report.MARGINAL_NODES)
        assert len(graph) == report.MARGINAL_NODES
        assert all(type(node) is type(graph[0]) for node in graph)
        state = scenario.state() if arm.lifecycle else None
        assert type(graph[0]) is type(arm.node(scenario, state))


def test_an_ordinary_instance_has_no_lifecycle_state_and_the_arm_refuses_one() -> None:
    scenario = SCENARIOS[0]
    assert (ORDINARY.lifecycle, LEGACY.lifecycle, COMPACT.lifecycle) == (False, True, True)
    assert lifecycle_state_of(ORDINARY.node(scenario, None)) is None
    for node in ORDINARY.graph(scenario, 3):
        assert lifecycle_state_of(node) is None
    with pytest.raises(ValueError, match="no lifecycle state to carry"):
        ORDINARY.node(scenario, scenario.state())


def test_a_published_node_is_compared_against_what_an_ordinary_one_actually_holds() -> None:
    scenario = SCENARIOS[0]
    published = COMPACT.node(scenario, scenario.state())
    assert lifecycle_state_of(published) is not None
    assert lifecycle_state_of(ORDINARY.node(scenario, None)) is None


def test_each_scenario_carries_its_own_percentage_as_a_diagnostic() -> None:
    reading = _reading("small", retained=(1_000, 250), bare=(800, 400))
    assert reading.reduction == pytest.approx(0.75)
    assert reading.bare_reduction == pytest.approx(0.5)


def test_what_a_construction_freed_again_is_its_high_water_mark_less_what_it_kept() -> None:
    arm = _arm(retained=400, bare=300, timings=(1.0, 1.0, 1.0))._replace(peak_bytes=1_800)
    assert arm.transient_bytes == 1_400
    assert arm.lifecycle_bytes == 100


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
    assert "attribute read 4.00x like for like over the mix" in raised
    assert "surfaced for human review" in raised
    assert "construction" not in raised
    assert "serialization" not in raised


def test_the_regression_rule_grades_the_like_for_like_figure_and_not_the_raw_one() -> None:
    corrected = _reading(
        "shallow",
        retained=(1_000, 100),
        bare=(900, 90),
        legacy_ns=(1_000.0, 20.0, 500.0),
        compact_ns=(1_500.0, 20.0, 500.0),
        scaffolding_ns=400.0,
    )
    construction = report.OPERATIONS[0]
    assert report.mix_ratio([corrected], construction) == pytest.approx(1.50)
    assert report.like_for_like_ratio([corrected], construction) == pytest.approx(1.50 / 1.40)
    assert report.escalation_block({"3.14": {"shallow": corrected}})[0].startswith("no escalation")

    uncorrected = corrected._replace(
        compact=corrected.compact._replace(construct_ns=1_800.0, scaffolding_ns=0.0)
    )
    raised = "\n".join(report.escalation_block({"3.14": {"shallow": uncorrected}}))
    assert "construction 1.80x like for like over the mix" in raised


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
        "representative operation moved past 1.20x like for like"
    ]


def test_one_runtime_missing_its_target_escalates_for_that_runtime_alone() -> None:
    passing = _reading("shallow", retained=(1_000, 100), bare=(900, 90))
    failing = _reading("shallow", retained=(1_000, 900), bare=(900, 810))
    block = report.escalation_block({"3.13": {"shallow": failing}, "3.14": {"shallow": passing}})
    raised = "\n".join(block)
    assert "CPython 3.13: primary aggregate" in raised
    assert "CPython 3.14: primary aggregate" not in raised


# --------------------------------------------------------------------------- #
# Completeness, which is the one thing this report exits on.                   #
# --------------------------------------------------------------------------- #


def test_a_matrix_cell_with_no_reading_is_named_with_its_reason() -> None:
    matrix = _matrix()
    matrix["3.14"]["nested"] = "the child exited 1"
    del matrix["3.14"]["wide"]
    absent = report.missing_cells(matrix, ("3.14",), REPORTED)
    assert absent == [
        "CPython 3.14, wide: no child was run",
        "CPython 3.14, nested: the child exited 1",
    ]
    assert not report.missing_cells(_matrix(), ("3.14",), REPORTED)


def test_a_runtime_the_matrix_never_ran_is_missing_rather_than_absent_from_the_question() -> None:
    absent = report.missing_cells(_matrix(), ("3.13", "3.14"), REPORTED)
    assert absent == [f"CPython 3.13, {scenario.name}: no child was run" for scenario in REPORTED]


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
    assert printed.count("published vs ordinary (lifecycle included)") == 2
    headers = [line for line in printed.splitlines() if line.startswith("scenario ")]
    assert len(headers) == 2
    for column in (
        "node us",
        "call us",
        "outside us",
        "read ns",
        "dump us",
        "transient B",
        "peak B",
        "cells",
    ):
        assert all(column in header for header in headers)
    measured = [
        line.split()
        for line in printed.splitlines()
        if line.split() and line.split()[-1].replace(",", "").isdigit()
    ]
    for arm in ARMS:
        assert sum(arm.name in row for row in measured) == 2 * len(REPORTED)


def test_each_printed_reduction_names_the_arm_it_divides() -> None:
    lines = report.render(_matrix())
    reductions = [line for line in lines if "reduction" in line]
    assert [line.split()[0] for line in reductions].count("vs") == 2 * len(REPORTED)
    assert sum(line.startswith("vs legacy") for line in reductions) == len(REPORTED)
    assert sum(line.startswith("vs ordinary") for line in reductions) == len(REPORTED)
    printed = "\n".join(lines)
    assert "the representation change — legacy arm against compact" in printed
    assert "stated separately, in no aggregate — ordinary arm against compact" in printed


def test_construction_is_printed_both_ways_and_the_scope_block_says_which_is_graded() -> None:
    matrix = _matrix()
    matrix["3.14"]["shallow"] = _reading(
        "shallow", compact_ns=(1_300.0, 20.0, 500.0), scaffolding_ns=300.0
    )
    printed = "\n".join(report.render(matrix))
    header = next(line for line in printed.splitlines() if "arm against arm" in line)
    assert "like for like" in header
    construction = next(line for line in printed.splitlines() if "construction" in line)
    raw, corrected = (float(field.rstrip("x")) for field in construction.split()[1:3])
    readings = report.canonical(matrix["3.14"])
    assert raw == pytest.approx(report.mix_ratio(readings, report.OPERATIONS[0]), abs=5e-3)
    assert corrected == pytest.approx(
        report.like_for_like_ratio(readings, report.OPERATIONS[0]), abs=5e-3
    )
    assert raw > corrected
    assert "THE 20% RULE GRADES THE LIKE-FOR-LIKE FIGURE," in printed


def test_the_escalation_block_reaches_what_the_report_prints() -> None:
    matrix = {"3.14": {scenario.name: _reading(scenario.name) for scenario in REPORTED}}
    matrix["3.14"]["shallow"] = _reading(
        "shallow",
        retained=(1_000, 700),
        bare=(900, 600),
        compact_ns=(1_100.0, 80.0, 505.0),
    )
    printed = "\n".join(report.render(cast("report.Matrix", matrix)))
    for line in report.escalation_block(cast("report.Matrix", matrix)):
        assert line in printed


def test_a_child_answers_one_scenario_as_a_line_the_matrix_decodes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    line = report.payload(_reading("shallow"))
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


def _arm(
    retained: int,
    bare: int,
    timings: tuple[float, float, float],
    scaffolding: float = 0.0,
) -> report.ArmReading:
    construct_ns, read_ns, dump_ns = timings
    return report.ArmReading(
        cells=6,
        retained_bytes=retained,
        bare_bytes=bare,
        peak_bytes=retained + 512,
        construct_ns=construct_ns,
        call_ns=250.0,
        scaffolding_ns=scaffolding,
        read_ns=read_ns,
        dump_ns=dump_ns,
    )


def _reading(
    scenario: str,
    *,
    retained: tuple[int, int] = (1_000, 100),
    bare: tuple[int, int] = (900, 90),
    ordinary_retained: int = 2_000,
    ordinary_bare: int = 1_800,
    legacy_ns: tuple[float, float, float] = (1_000.0, 20.0, 500.0),
    compact_ns: tuple[float, float, float] = (1_000.0, 20.0, 500.0),
    scaffolding_ns: float = 0.0,
) -> report.Reading:
    """One scenario's reading, with every number chosen rather than measured.

    ``retained`` and ``bare`` are the pair the aggregates divide — legacy, then
    compact. The ordinary arm is a third number rather than a member of either,
    which is the shape of the thing being graded. ``scaffolding_ns`` is the
    compact arm's alone, because it is the only arm whose call does per-node work
    outside its own callbacks.
    """
    return report.Reading(
        scenario=scenario,
        summary=f"the {scenario} scenario",
        fields=4,
        warmup=200,
        ordinary=_arm(ordinary_retained, ordinary_bare, legacy_ns),
        legacy=_arm(retained[0], bare[0], legacy_ns),
        compact=_arm(retained[1], bare[1], compact_ns, scaffolding=scaffolding_ns),
    )


def _matrix() -> report.Matrix:
    """One complete runtime's worth of doctored readings."""
    return {"3.14": {scenario.name: _reading(scenario.name) for scenario in REPORTED}}
