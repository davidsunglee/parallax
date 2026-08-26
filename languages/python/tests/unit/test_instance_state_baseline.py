"""The frozen instance-state baseline's own fixture, and what it now stands for.

``docs/instance-state-baseline.md`` records what one published Entity retained
before publication became compact, and `just python-report-instance-state`
re-derives it. Neither grades a number — a total in bytes is machine- and
interpreter-relative.

The arm the report measures is a fixture: ``legacy_publication`` builds one node
the way Entity Graph Construction built one then, with a zero-argument
``model_construct`` filled a member at a time. While that path existed the report
compared every scenario's fixture against it before measuring anything, and
refused to measure a fixture that had drifted. Publication attaches one compact
tuple now, so there is no legacy path left to compare against and that check has
retired with it; what remains gradeable here is the mix the measurement contract
names, and the report's own refusal to be asked for more than one scenario.

Nothing here measures. Every reading this report takes reads the whole
interpreter and belongs in a child of its own, which is what the report's own
`in_a_child` is for; a test taking one beside the rest of the suite would be
classified `dbfree` while needing an interpreter no other test shares.
"""

from __future__ import annotations

import pytest
from _instance_state_support import SCENARIOS

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
