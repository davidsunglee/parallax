"""The scenario lane's state-graded groups over a recording port.

A state-graded scenario drives every submission through the public verb its form
names and reports what the run left: each group's fate, each refusal at its
submission's pointer, each find's published rows, and the tables read back. It
reports no emissions, since nothing grades which statements a flush chose.
"""

from __future__ import annotations

import decimal
from pathlib import Path
from typing import Any

import pytest

from parallax.conformance import case_format, models
from parallax.conformance._lanes import scenario
from parallax.conformance._mechanism.envelope import EngineError
from parallax.core.metamodel import AttributeIdentity, entity_by_name
from parallax.core.unit_work import OptimisticLockConflictError
from parallax.core.unit_work.planned import INFINITY, MilestoneTarget
from parallax.snapshot.handle import WriteEvidenceError
from tests._support.repo import REPO_ROOT
from tests.unit.conformance._recording_ports import FakeWritePort

_CORPUS = REPO_ROOT / "core" / "compatibility"
_BARRIER_CASE = "m-unit-work-049-a-barrier-keeps-non-temporal-writes-on-their-own-sides"
_ACCOUNT_ROW = {"id": 1, "owner": "Ada", "balance": decimal.Decimal("5.00"), "version": 1}
_FIND = {
    "uow": "g",
    "objectQuery": {"target": "Account", "predicate": {"eq": {"attr": "Account.id", "value": 1}}},
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
    return {"mutation": "update", "entity": "Account", "rows": [row], **entry}


def test_every_submission_reaches_its_own_verb_and_the_run_reports_what_it_left() -> None:
    (case,) = (
        case
        for case in case_format.load_cases()
        if case.path.name == f"{_BARRIER_CASE}-layout-twin-columns.yaml"
    )
    tag = {"id": 1, "quantity": 5, "label": "t"}
    account = {"id": 1, "balance": 10, "version": 1, "memo": {"note": "m1"}}
    port = FakeWritePort(read_script=[[tag], [account]])

    run = scenario.run_scenario_case(case, port)

    assert run.emissions == []
    assert run.errors == []
    assert run.units == {
        label: {"outcome": "committed"}
        for label in ("same-state", "versioned", "inserted", "reinserted")
    }
    assert [entry["at"] for entry in run.step_rows] == ["/scenario/0", "/scenario/2"]
    assert run.table_state is not None
    assert set(run.table_state) == {"sequence_account", "sequence_span", "sequence_tag"}
    tag_writes = [sql for sql, _ in port.writes if "sequence_tag" in sql]
    assert tag_writes[:3] == [
        "update sequence_tag set quantity = %s where id = %s",
        "update sequence_tag set label = %s where quantity < %s",
        "update sequence_tag set quantity = %s where id = %s",
    ]
    assert tag_writes[-2:] == [
        "delete from sequence_tag where id = %s",
        "insert into sequence_tag(id, quantity, label) values (%s, %s, %s)",
    ]


def test_a_refused_submission_is_reported_at_its_pointer_and_its_group_commits() -> None:
    case = _state_graded(
        [
            _FIND,
            {
                "uow": "g",
                "write": [
                    _update({"id": 1, "owner": "Bo"}, on=0),
                    {"mutation": "delete", "entity": "Account", "rows": [{"id": 1}], "on": 0},
                    _update(
                        {"id": 1, "owner": "Cy"}, on=0, expectError="write-evidence-already-claimed"
                    ),
                    {
                        "mutation": "update",
                        "entity": "Account",
                        "row": {"id": 1, "balance": "9.00"},
                        "ifVersion": 1,
                        "expectError": "write-evidence-already-claimed",
                    },
                ],
            },
        ],
        {"g": {"outcome": "committed"}},
    )
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW])

    run = scenario.run_scenario_case(case, port)

    assert run.errors == [
        {"at": "/scenario/1/write/2", "errorClass": "write-evidence-already-claimed"},
        {"at": "/scenario/1/write/3", "errorClass": "write-evidence-already-claimed"},
    ]
    assert run.units == {"g": {"outcome": "committed"}}
    assert [sql for sql, _ in port.writes] == ["delete from account where id = %s and version = %s"]


def test_a_refusal_other_than_the_one_a_submission_declares_propagates() -> None:
    case = _state_graded(
        [
            _FIND,
            {
                "uow": "g",
                "write": [
                    {"mutation": "delete", "entity": "Account", "rows": [{"id": 1}], "on": 0},
                    _update({"id": 1, "owner": "Cy"}, on=0, expectError="write-evidence-inserted"),
                ],
            },
        ],
        {"g": {"outcome": "committed"}},
    )
    with pytest.raises(WriteEvidenceError, match="write-evidence-already-claimed"):
        scenario.run_scenario_case(case, FakeWritePort(find_rows=[_ACCOUNT_ROW]))


@pytest.mark.parametrize(
    ("steps", "at"),
    [
        pytest.param(
            [
                {
                    "uow": "g",
                    "write": [
                        {
                            "mutation": "update",
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
                            "mutation": "update",
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
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW], zero_affected_for=("update account",))

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


def test_an_observed_write_falling_short_reports_its_conflict() -> None:
    case = _state_graded(
        [_FIND, {"uow": "g", "write": [_update({"id": 1, "owner": "Bo"}, on=0)]}],
        {"g": {"outcome": "rolledBack"}},
    )
    port = FakeWritePort(find_rows=[_ACCOUNT_ROW], zero_affected_for=("update account",))

    run = scenario.run_scenario_case(case, port)

    assert run.units is not None
    flush_failure = run.units["g"]["flushFailure"]
    assert isinstance(flush_failure, dict)
    assert flush_failure["shortfall"] == "optimisticConflict"


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
    with pytest.raises(EngineError, match="not an EARLIER find"):
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
    with pytest.raises(EngineError, match=refusal):
        scenario.run_scenario_case(case, FakeWritePort(find_rows=[_ACCOUNT_ROW]))


def test_a_milestone_targets_failure_names_its_key() -> None:
    model = models.load_model(_CORPUS / "models" / "buffered-sequence-layout-twin-columns.yaml")
    entity = entity_by_name(model, "parallax.compatibility.SequenceSpan")
    assert entity is not None
    span = entity.identity
    target = MilestoneTarget(
        key_attributes=(AttributeIdentity(span, "id"),),
        key_values=(4,),
        end_attributes=(AttributeIdentity(span, "validEnd"), AttributeIdentity(span, "txEnd")),
        end_values=(INFINITY, INFINITY),
    )
    failure = OptimisticLockConflictError(span, target, 1, 0)
    assert scenario.flush_failure(model, failure, 3) == {
        "at": 3,
        "entity": "parallax.compatibility.SequenceSpan",
        "key": {"id": 4},
        "shortfall": "optimisticConflict",
    }


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
    with pytest.raises(EngineError, match=r"^m-unit-work-997-synthetic\.yaml: .*`until`"):
        scenario.run_scenario_case(case, FakeWritePort(find_rows=[_ACCOUNT_ROW]))
