"""The scenario lane's state-graded groups over a recording port."""

from __future__ import annotations

import decimal
from pathlib import Path
from typing import Any

import pytest

from parallax.conformance import case_format, models
from parallax.conformance._lanes import scenario
from parallax.conformance._mechanism.envelope import UnclassifiedEngineError
from parallax.core import ConflictError, UsageError
from parallax.core.internal.unit_work import (
    MISSING_TARGET,
    OPTIMISTIC_LOCK_CONFLICT,
    STALE_WRITE,
    TEMPORAL_CONFLICT,
    WRITE_PRECONDITION_FAILED,
)
from tests._support.repo import REPO_ROOT
from tests.unit.conformance._recording_ports import FakeWritePort

_CORPUS = REPO_ROOT / "core" / "compatibility"
_ACCOUNT_ROW = {"id": 1, "owner": "Ada", "balance": decimal.Decimal("5.00"), "version": 1}
_FIND = {
    "uow": "g",
    "objectQuery": {"target": "Account", "predicate": {"eq": {"path": "Account.id", "value": 1}}},
}


def _state_graded(steps: list[dict[str, Any]], units: dict[str, Any]) -> case_format.Case:
    document: dict[str, Any] = {
        "model": "models/account.yaml",
        "shape": "scenario",
        "grading": "state",
        "when": {"scenario": steps},
        "then": {"units": units, "tableState": {"account": []}},
    }
    return case_format.Case(
        path=Path("m-unit-work-997-synthetic.yaml"),
        case_id="m-unit-work-997",
        shape="scenario",
        tags=("m-unit-work", "slice-snapshot-1"),
        model="models/account.yaml",
        document=document,
    )


def _update(row: dict[str, Any], **entry: Any) -> dict[str, Any]:
    return {"mutation": "amend", "entity": "Account", "rows": [row], **entry}


@pytest.mark.parametrize(
    ("steps", "at"),
    [
        pytest.param(
            [
                {
                    "uow": "g",
                    "write": [
                        {
                            "mutation": "amend",
                            "entity": "Account",
                            "row": {"id": 1, "balance": "9.00"},
                            "ifVersion": 1,
                        }
                    ],
                }
            ],
            "commit",
            id="at-commit",
        ),
        pytest.param(
            [
                {
                    "uow": "g",
                    "write": [
                        {
                            "mutation": "amend",
                            "entity": "Account",
                            "row": {"id": 1, "balance": "9.00"},
                            "ifVersion": 1,
                        }
                    ],
                },
                _FIND,
            ],
            1,
            id="at-a-flushing-find",
        ),
    ],
)
def test_a_flush_failure_is_reported_where_the_flush_ran(steps: list[Any], at: object) -> None:
    case = _state_graded(steps, {"g": {"outcome": "rolledBack"}})
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW], zero_affected_for=("update px.account",))

    run = scenario.run_scenario_case(case, port)

    assert run.units == {
        "g": {
            "outcome": "rolledBack",
            "flushFailure": {
                "at": at,
                "entity": "parallax.compatibility.Account",
                "key": {"id": 1},
                "shortfall": "failedPrecondition",
            },
        }
    }
    assert port.rollbacks == 1


def test_an_abandoned_group_rolls_back_what_it_flushed_and_states_no_failure() -> None:
    case = _state_graded(
        [_FIND, {"uow": "g", "write": [_update({"id": 1, "owner": "Bo"}, on=0)]}],
        {"g": {"outcome": "rolledBack"}},
    )
    case = case_format.Case(
        path=case.path,
        case_id=case.case_id,
        shape=case.shape,
        tags=case.tags,
        model=case.model,
        document={**case.document, "then": {"units": {"g": {"outcome": "rolledBack"}}}},
    )
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW])

    run = scenario.run_scenario_case(case, port)

    assert run.units == {"g": {"outcome": "rolledBack"}}
    assert len(port.writes) == 1
    assert port.rollbacks == 1


def test_an_ungrouped_find_reads_committed_state_after_the_groups() -> None:
    case = _state_graded(
        [
            {"uow": "g", "write": [_update({"id": 1, "owner": "Bo"}, on=1)]},
            {k: v for k, v in _FIND.items() if k != "uow"},
        ],
        {"g": {"outcome": "committed"}},
    )
    with pytest.raises(UnclassifiedEngineError, match="not an EARLIER find"):
        scenario.run_scenario_case(case, FakeWritePort(find_rows=[_ACCOUNT_ROW]))
    case = _state_graded(
        [
            _FIND,
            {"uow": "g", "write": [_update({"id": 1, "owner": "Bo"}, on=0)]},
            {k: v for k, v in _FIND.items() if k != "uow"},
        ],
        {"g": {"outcome": "committed"}},
    )
    run = scenario.run_scenario_case(case, FakeWritePort(find_rows=[_ACCOUNT_ROW]))
    assert [entry["at"] for entry in run.step_rows] == ["/scenario/0", "/scenario/2"]


@pytest.mark.parametrize(
    ("steps", "refusal"),
    [
        pytest.param(
            [{"write": [_update({"id": 1, "owner": "Bo"})]}],
            "an ungrouped write",
            id="ungrouped-write",
        ),
        pytest.param(
            [
                _FIND,
                {
                    "uow": "g",
                    "write": [_update({"id": 1, "owner": "Bo"}, on="/scenario/1/write/0")],
                },
            ],
            "opened no value",
            id="pointer-to-no-insert",
        ),
        pytest.param(
            [_FIND, {"uow": "h", "write": [_update({"id": 1, "owner": "Bo"})]}, _FIND],
            "one at a time",
            id="interleaved-groups",
        ),
    ],
)
def test_what_a_state_graded_run_cannot_state_is_refused(steps: list[Any], refusal: str) -> None:
    case = _state_graded(steps, {"g": {"outcome": "committed"}, "h": {"outcome": "committed"}})
    with pytest.raises(UnclassifiedEngineError, match=refusal):
        scenario.run_scenario_case(case, FakeWritePort(find_rows=[_ACCOUNT_ROW]))


@pytest.mark.parametrize(
    ("code", "outcome"),
    [
        (MISSING_TARGET, ("shortfall", "missingTarget")),
        (STALE_WRITE, ("shortfall", "staleWrite")),
        (OPTIMISTIC_LOCK_CONFLICT, ("shortfall", "optimisticConflict")),
        (WRITE_PRECONDITION_FAILED, ("shortfall", "failedPrecondition")),
        (TEMPORAL_CONFLICT, ("error", "temporalConflict")),
    ],
)
def test_a_flush_conflict_is_reported_by_its_code_naming_its_row(
    code: str, outcome: tuple[str, str]
) -> None:
    model = models.load_model(_CORPUS / "models" / "buffered-sequence-layout-twin-columns.yaml")
    failure = ConflictError(code, "m", entity="parallax.compatibility.SequenceSpan", key={"id": 4})
    assert scenario.is_flush_failure(failure)
    assert scenario.flush_failure(model, failure, 3) == {
        "at": 3,
        "entity": "parallax.compatibility.SequenceSpan",
        "key": {"id": 4},
        outcome[0]: outcome[1],
    }


def test_a_conflict_no_flush_failure_names_is_not_one() -> None:
    assert not scenario.is_flush_failure(ConflictError("publication-conflict", "m"))
    assert not scenario.is_flush_failure(UsageError(MISSING_TARGET, "m"))


def test_a_submission_its_model_cannot_lower_is_refused_naming_the_case() -> None:
    case = _state_graded(
        [
            _FIND,
            {
                "uow": "g",
                "write": [_update({"id": 1, "owner": "Bo"}, on=0, until="2024-06-01T00:00:00Z")],
            },
        ],
        {"g": {"outcome": "committed"}},
    )
    with pytest.raises(
        UnclassifiedEngineError, match=r"^m-unit-work-997-synthetic\.yaml: .*`until`"
    ):
        scenario.run_scenario_case(case, FakeWritePort(find_rows=[_ACCOUNT_ROW]))
