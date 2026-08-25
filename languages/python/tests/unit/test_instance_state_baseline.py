"""The frozen instance-state baseline's one gate: that its fixture still stands
for the path it was taken to stand for.

``docs/instance-state-baseline.md`` records what one published Entity retains
today, and `just python-report-instance-state` re-derives it. Neither grades a
number — a total in bytes is machine- and interpreter-relative — so the only
thing that can go wrong silently is the arm: the report measures
``_instance_state_support.legacy_publication``, a fixture that builds one node the
way Entity Graph Construction builds one today, and a fixture that has drifted
still produces numbers.

So the report compares every scenario's fixture against the real publication path
before it measures anything, and this module grades that comparison from both
sides: it names nothing over the shipping mix, and it names the site over each of
three fixtures that have stopped reproducing publication in a different way. The
third arm is the one the fixture exists for — ordinary keyword construction gets
every value right and the field set wrong, which no comparison of values could
see.

Nothing here measures. Every reading this report takes reads the whole
interpreter and belongs in a child of its own, which is what the report's own
`in_a_child` is for; a test taking one beside the rest of the suite would be
classified `dbfree` while needing an interpreter no other test shares.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import pytest
from _instance_state_support import (
    SCENARIOS,
    LegacyArm,
    Scenario,
    disagreements,
    legacy_publication,
    published,
)

import instance_state_overhead as report
from parallax.core.entity import UNLOADED
from parallax.core.entity._declaration import LIFECYCLE_STATE_SLOT
from parallax.core.entity._instance_state import instance_state
from parallax.core.entity._row import ABSENT

# --------------------------------------------------------------------------- #
# The shipping mix.                                                            #
# --------------------------------------------------------------------------- #


def test_the_canonical_mix_is_the_six_scenarios_the_measurement_contract_names() -> None:
    assert tuple(scenario.name for scenario in SCENARIOS) == (
        "shallow",
        "wide",
        "nested",
        "nullable",
        "partial",
        "polymorphic",
    )


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.name)
def test_every_canonical_fixture_still_reproduces_publication(scenario: Scenario) -> None:
    assert disagreements(scenario) == ()


def test_the_report_finds_nothing_over_the_shipping_mix() -> None:
    assert report.findings(SCENARIOS) == []


def test_a_materialized_node_carries_an_empty_field_set_and_the_fixture_reproduces_it() -> None:
    # The distinction the fixture exists for, stated directly rather than only
    # through the comparison: publication's zero-argument `model_construct`
    # leaves the field set permanently empty, and every later member arrives by
    # `object.__setattr__`, which never adds to it.
    scenario = SCENARIOS[0]
    assert cast("Any", published(scenario, None)).__pydantic_fields_set__ == set()
    assert cast("Any", legacy_publication(scenario, None)).__pydantic_fields_set__ == set()


# --------------------------------------------------------------------------- #
# Three ways a fixture stops standing for the path, and the refusal each earns. #
# --------------------------------------------------------------------------- #


def _ordinary_construction(scenario: Scenario, state: object | None) -> object:
    """Every value right, the field set wrong.

    Keyword ``model_construct`` records each member it was handed, so the node
    reports a full ``model_fields_set`` where a materialized one reports none —
    the difference the frozen reading is largely made of, and one no comparison
    of member VALUES could see.
    """
    plan = scenario.plan
    values = {
        py_name: scenario.values[position]
        for position, py_name in plan.attributes
        if scenario.values[position] is not ABSENT
    }
    instance = cast("Any", plan.cls).model_construct(**values)
    for py_name in plan.relationships:
        object.__setattr__(instance, py_name, UNLOADED)
    if state is not None:
        object.__setattr__(instance, LIFECYCLE_STATE_SLOT, state)
    return instance


def _without_relationship_slots(scenario: Scenario, state: object | None) -> object:
    """Every member right, no relationship slot written.

    Publication installs the unloaded sentinel in every declared relationship
    slot on every node, so a fixture skipping them prices a node the read never
    published.
    """
    instance = cast("Any", legacy_publication(scenario, state))
    for py_name in scenario.plan.relationships:
        instance_state(instance).pop(py_name, None)
    return instance


def _without_lifecycle_state(scenario: Scenario, _state: object | None) -> object:
    """The node right, its lifecycle state never attached — the half of the
    comparison a fixture could reproduce alone, which is why both halves are
    compared."""
    return legacy_publication(scenario, None)


@pytest.mark.parametrize(
    "arm",
    [_ordinary_construction, _without_relationship_slots, _without_lifecycle_state],
    ids=["ordinary-construction", "no-relationship-slots", "no-lifecycle-state"],
)
def test_a_fixture_that_stopped_reproducing_publication_is_named(arm: LegacyArm) -> None:
    doctored = replace(SCENARIOS[0], legacy=arm)
    findings = disagreements(doctored)
    assert findings, "this arm reproduces publication, which it must not"
    assert all(finding.startswith(doctored.name) for finding in findings)


def test_the_report_refuses_to_measure_a_fixture_that_stopped_reproducing_publication(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The whole command, not only the comparison: a non-zero exit BEFORE any
    # child starts is what keeps a drifted fixture from producing a reading that
    # looks like every other one.
    doctored = replace(SCENARIOS[0], legacy=cast("Any", _ordinary_construction))
    monkeypatch.setattr(report, "SCENARIOS", (doctored,))
    assert report.main([]) == 1
    assert "no longer reproduces publication" in capsys.readouterr().err


def test_the_report_refuses_more_than_one_scenario_argument(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert report.main(["shallow", "wide"]) == 2
    assert "usage:" in capsys.readouterr().err
