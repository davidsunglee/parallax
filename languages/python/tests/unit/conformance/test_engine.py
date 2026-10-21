"""The conformance engine façade: the one decision it makes itself.

Every entry point the façade exports is a lane's, pinned in that lane's own
test module. What is pinned here is the scenario dispatch: a scenario carrying
an action step reaches the snapshot lane, and every other scenario reaches the
keyed unit-of-work lane, with the same case answering the same observation
through the façade as through the lane it selects.
"""

from __future__ import annotations

import datetime as dt
import decimal

from parallax.conformance import case_format, engine
from parallax.conformance._lanes import scenario, snapshot
from parallax.conformance._lifecycle_observation import lifecycle_run
from parallax.conformance._mechanism import case_document
from parallax.core.db_port import MappingRow
from tests._support.case_corpus import case as corpus_case
from tests.unit.conformance._recording_ports import FakeWritePort


def _case(case_id: str) -> case_format.Case:
    return corpus_case(case_id, reachable=True)


_KEYED_SCENARIO = "m-unit-work-001"
_ACTION_STEP_SCENARIO = "m-snapshot-read-010"

_ORDER_ROW: MappingRow = {
    "id": 1,
    "name": "Ada",
    "sku": "A-100",
    "qty": 5,
    "price": decimal.Decimal("10.50"),
    "active": True,
    "ordered_on": dt.date(2024, 1, 5),
}


def test_compile_scenario_case_selects_the_lane_by_the_cases_action_step() -> None:
    keyed = _case(_KEYED_SCENARIO)
    assert engine.compile_scenario_case(keyed, "postgres") == scenario.compile_scenario_case(
        keyed, "postgres"
    )

    action = _case(_ACTION_STEP_SCENARIO)
    steps = case_document.scenario_steps(action)
    assert case_document.has_action_step(steps)
    assert engine.compile_scenario_case(action, "postgres") == snapshot.compile_scenario(
        action, "postgres", steps
    )


def test_run_scenario_case_selects_the_lane_by_the_cases_action_step() -> None:
    keyed = _case(_KEYED_SCENARIO)
    through_facade = engine.run_scenario_case(keyed, FakeWritePort(find_rows=[{"id": 7}]))
    through_lane = scenario.run_scenario_case(keyed, FakeWritePort(find_rows=[{"id": 7}]))
    assert through_facade == through_lane
    assert [e.case_pointer for e in through_facade.emissions] == [
        "/scenario/0/write",
        "/scenario/1/objectQuery",
    ]

    action = _case(_ACTION_STEP_SCENARIO)
    steps = case_document.scenario_steps(action)
    through_facade = engine.run_scenario_case(action, FakeWritePort(find_rows=[dict(_ORDER_ROW)]))
    through_lane = snapshot.run_scenario(
        action, FakeWritePort(find_rows=[dict(_ORDER_ROW)]), steps, lifecycle_run(None)
    )
    assert through_facade == through_lane
    assert [e.case_pointer for e in through_facade.emissions] == [
        "/scenario/0/objectQuery",
        "/scenario/2/objectQuery",
    ]
