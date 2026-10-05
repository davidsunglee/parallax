"""A state-graded Scenario, and every group's fate."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from reference_harness.case import Case
from reference_harness.case_assertions import CaseFailure
from reference_harness.unit_work_scenario import assert_unit_work_scenario

from .conftest import (
    Affected,
    Executed,
    Opened,
    Queried,
    Rows,
    ScriptedProvider,
    assert_judged,
)

type CaseLoader = Callable[[str], Case]

_NON_TEMPORAL = (
    "m-unit-work-049-a-barrier-keeps-non-temporal-writes-on-their-own-sides"
    "-layout-twin-columns.yaml"
)
_REFUSALS = (
    "m-unit-work-047-a-refused-submission-leaves-earlier-work-pending-layout-twin-columns.yaml"
)
_BARRIER = (
    "m-bitemp-write-030-a-barrier-keeps-each-operation-on-its-own-side-layout-twin-columns.yaml"
)
_ROLLBACK = (
    "m-bitemp-write-032-a-read-between-writes-completes-the-earlier-layout-twin-columns.yaml"
)

_T0 = "2023-12-01T00:00:00.000000Z"
_T1 = "2023-12-15T00:00:00.000000Z"
_INF = "infinity"


def _span(id_: int, start: str, end: str, inz: str, outz: str, amount: int, label: str) -> dict:
    return {
        "id": id_,
        "amount": amount,
        "label": label,
        "memo": {"note": f"n{id_}"},
        "from_z": start,
        "thru_z": end,
        "in_z": inz,
        "out_z": outz,
    }


_STARTING_SPANS = (
    _span(1, "2024-01-01T00:00:00.000000Z", _INF, _T0, _INF, 100, "a"),
    _span(2, "2024-01-01T00:00:00.000000Z", _INF, _T0, _INF, 100, "b"),
    _span(3, "2024-01-01T00:00:00.000000Z", "2024-06-01T00:00:00.000000Z", _T0, _INF, 100, "c"),
    _span(3, "2024-06-01T00:00:00.000000Z", _INF, _T1, _INF, 200, "c"),
    _span(4, "2024-01-01T00:00:00.000000Z", _INF, _T0, _T1, 90, "d"),
    _span(4, "2024-01-01T00:00:00.000000Z", _INF, _T1, _INF, 100, "d"),
)
_STARTING_TAGS = ({"id": 1, "quantity": 5, "label": "t"}, {"id": 2, "quantity": 9, "label": "u"})
_STARTING_ACCOUNTS = ({"id": 1, "balance": 10, "version": 1, "memo": {"note": "m1"}},)
_STARTING = {
    "sequence_span": _STARTING_SPANS,
    "sequence_tag": _STARTING_TAGS,
    "sequence_account": _STARTING_ACCOUNTS,
}


def _starting(case: Case) -> list[Rows]:
    """One scripted read-back per table the case states, in its order."""
    return [Rows(_STARTING[table]) for table in case.expected_table_state]


def _grade(case: Case) -> ScriptedProvider:
    with ScriptedProvider(script=_starting(case)) as db:
        assert_unit_work_scenario(case, db)
    return db


def _rows(case: Case, table: str) -> list[dict[str, Any]]:
    return case.then["tableState"][table]


def _find(rows: list[dict[str, Any]], **cells: Any) -> dict[str, Any]:
    (row,) = (row for row in rows if all(row.get(k) == v for k, v in cells.items()))
    return row


# --- what a state-graded run asks the database for ---------------------------


@pytest.mark.parametrize("name", [_NON_TEMPORAL, _REFUSALS, _BARRIER, _ROLLBACK])
def test_a_state_graded_case_reads_back_its_starting_rows_and_executes_nothing(
    corpus_case: CaseLoader, name: str
) -> None:
    case = corpus_case(name)
    db = _grade(case)
    assert not [call for call in db.chronology if isinstance(call, (Opened, Executed))]
    assert [call.sql.rsplit(" ", 2)[-2] for call in db.chronology if isinstance(call, Queried)] == [
        table for table in case.expected_table_state
    ]


# --- the frame rule ----------------------------------------------------------


def test_a_key_no_submission_names_keeps_its_starting_rows(damaged_case: CaseLoader) -> None:
    case = damaged_case(_BARRIER)
    _find(_rows(case, "sequence_span"), id=4, out_z=_INF)["amount"] = 101
    with pytest.raises(CaseFailure, match="changes key 4, but no committed submission names it"):
        _grade(case)


def test_a_key_only_a_rolled_back_group_names_keeps_its_starting_rows(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_ROLLBACK)
    _find(_rows(case, "sequence_span"), id=4, out_z=_INF)["label"] = "z"
    with pytest.raises(CaseFailure, match="only rolled-back or refused submissions name it"):
        _grade(case)


def test_a_table_a_predicate_submission_writes_states_any_row_of_it(
    damaged_case: CaseLoader,
) -> None:
    # The barrier selects rows only its predicate decides, so every row of its table
    # is the case's to state.
    case = damaged_case(_NON_TEMPORAL)
    _find(_rows(case, "sequence_tag"), id=2)["label"] = "seen-by-the-barrier"
    _grade(case)


# --- milestones and overlap --------------------------------------------------


def test_a_row_no_committed_group_opened_is_refused(damaged_case: CaseLoader) -> None:
    case = damaged_case(_BARRIER)
    row = _find(_rows(case, "sequence_span"), id=1, from_z="2024-02-01T00:00:00.000000Z")
    row["in_z"] = "2024-10-15T00:00:00.000000Z"
    with pytest.raises(CaseFailure, match="neither a starting row"):
        _grade(case)


def test_a_starting_milestone_is_closed_and_never_removed(damaged_case: CaseLoader) -> None:
    case = damaged_case(_BARRIER)
    rows = _rows(case, "sequence_span")
    rows.remove(_find(rows, id=1, in_z=_T0))
    with pytest.raises(CaseFailure, match="drops the starting row"):
        _grade(case)


def test_current_rows_of_one_key_never_overlap(damaged_case: CaseLoader) -> None:
    case = damaged_case(_BARRIER)
    row = _find(
        _rows(case, "sequence_span"), id=1, from_z="2024-01-01T00:00:00.000000Z", out_z=_INF
    )
    row["thru_z"] = "2024-03-01T00:00:00.000000Z"
    with pytest.raises(CaseFailure, match="Valid-Time intervals overlap"):
        _grade(case)


# --- refusals ----------------------------------------------------------------


def test_an_already_claimed_refusal_needs_an_earlier_pending_write(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_REFUSALS)
    entries = case.when["scenario"][2]["write"]
    entries[0]["expectError"] = entries[2].pop("expectError")
    with pytest.raises(CaseFailure, match="no earlier write of its object is pending"):
        _grade(case)


def test_a_find_between_two_writes_leaves_nothing_pending(damaged_case: CaseLoader) -> None:
    case = damaged_case(_REFUSALS)
    steps = case.when["scenario"]
    refused = steps[2]["write"].pop(2)
    steps.insert(3, {"uow": "unequal", "objectQuery": steps[1]["objectQuery"]})
    steps.insert(4, {"uow": "unequal", "write": [refused]})
    for step in steps[5:]:
        for entry in step.get("write", []):
            if isinstance(entry.get("on"), int):
                entry["on"] += 2
    with pytest.raises(CaseFailure, match="no earlier write of its object is pending"):
        _grade(case)


def test_an_inserted_object_refusal_is_a_caller_addressed_write_of_an_insert(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_REFUSALS)
    case.when["scenario"][2]["write"][2]["expectError"] = "write-evidence-inserted"
    with pytest.raises(CaseFailure, match="refused as a write of an inserted object"):
        _grade(case)


# --- flush failures ----------------------------------------------------------


def test_a_flush_failure_names_an_object_its_group_writes(damaged_case: CaseLoader) -> None:
    case = damaged_case(_ROLLBACK)
    case.then["units"]["stale"]["flushFailure"]["key"] = {"id": 3}
    with pytest.raises(CaseFailure, match="no submission pending at that flush writes it"):
        _grade(case)


def test_a_flush_failure_names_an_object_its_flush_writes(damaged_case: CaseLoader) -> None:
    # Span 3 is written before the group's read flushes it, so the commit that
    # fails never writes it.
    case = damaged_case(_ROLLBACK)
    case.when["scenario"][7]["write"][0]["row"]["id"] = 3
    case.when["scenario"][7]["write"][0]["ifTxStart"] = _T0
    case.then["units"]["stale"]["flushFailure"]["key"] = {"id": 3}
    with pytest.raises(CaseFailure, match="no submission pending at that flush writes it"):
        _grade(case)


def test_a_flush_failure_names_a_shortfall_its_group_can_reach(damaged_case: CaseLoader) -> None:
    # Only caller-addressed writes of span 4 stand in the group, and their gate's
    # shortfall is a failed precondition, never an observed write's conflict.
    case = damaged_case(_ROLLBACK)
    case.then["units"]["stale"]["flushFailure"]["shortfall"] = "optimisticConflict"
    with pytest.raises(CaseFailure, match="no submission pending at that flush writes it"):
        _grade(case)


# --- the rules the document settles before any database ---------------------


def test_every_group_of_a_state_graded_case_states_its_fate(damaged_case: CaseLoader) -> None:
    case = damaged_case(_BARRIER)
    del case.then["units"]["observed"]
    with pytest.raises(CaseFailure, match="states no fate for group"):
        assert_judged(case)


def test_a_fate_names_a_group(damaged_case: CaseLoader) -> None:
    case = damaged_case(_BARRIER)
    case.then["units"]["elsewhere"] = {"outcome": "committed"}
    with pytest.raises(CaseFailure, match="label no `uow` group"):
        assert_judged(case)


def test_a_flush_failure_is_reported_where_its_group_last_flushes(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_ROLLBACK)
    case.then["units"]["stale"]["flushFailure"]["at"] = 8
    with pytest.raises(CaseFailure, match="last flush runs at 'commit'"):
        assert_judged(case)


def test_a_flush_failure_needs_a_flush(damaged_case: CaseLoader) -> None:
    case = damaged_case(_REFUSALS)
    case.when["scenario"].append({"uow": "unequal", "objectQuery": case.scenario[0]["objectQuery"]})
    case.when["scenario"].append({"uow": "unequal", "objectQuery": case.scenario[0]["objectQuery"]})
    case.then["units"]["unequal"] = {
        "outcome": "rolledBack",
        "flushFailure": {
            "at": 8,
            "entity": "SequenceSpan",
            "key": {"id": 1},
            "shortfall": "failedPrecondition",
        },
    }
    with pytest.raises(CaseFailure, match="last flush runs nothing"):
        assert_judged(case)


def test_a_group_holds_one_transaction_instant(damaged_case: CaseLoader) -> None:
    case = damaged_case(_BARRIER)
    case.when["scenario"][0]["write"][2]["at"] = "2024-11-09T00:00:00.000000Z"
    with pytest.raises(CaseFailure, match="one unit of work holds one"):
        assert_judged(case)


@pytest.mark.parametrize(
    ("damage", "refusal"),
    [
        pytest.param(
            lambda steps: steps[4]["write"][2].update(on="/scenario/4/write/1"),
            "is not an earlier insert submission",
            id="a-pointer-to-a-barrier",
        ),
        pytest.param(
            lambda steps: steps[4]["write"][2].update(on="/scenario/5/write/0"),
            "is not an earlier insert submission",
            id="a-pointer-to-another-group",
        ),
        pytest.param(
            lambda steps: steps[4]["write"][0].update(expectError="write-evidence-already-claimed"),
            "a submission its verb refuses",
            id="a-pointer-to-a-refused-insert",
        ),
        pytest.param(
            lambda steps: steps[4]["write"][0].update(on=0),
            "only an observed keyed write takes",
            id="an-insert-naming-a-source",
        ),
    ],
)
def test_a_pointer_names_the_value_an_earlier_insert_of_its_group_answered(
    damaged_case: CaseLoader, damage: Callable[[list[dict[str, Any]]], None], refusal: str
) -> None:
    case = damaged_case(_NON_TEMPORAL)
    damage(case.when["scenario"])
    with pytest.raises(CaseFailure, match=refusal):
        assert_judged(case)


def test_a_state_graded_case_groups_every_write(damaged_case: CaseLoader) -> None:
    case = damaged_case(_NON_TEMPORAL)
    del case.when["scenario"][5]["uow"]
    for entry in case.when["scenario"][5]["write"]:
        entry.pop("on", None)
    del case.then["units"]["reinserted"]
    with pytest.raises(CaseFailure, match="an ungrouped write in a state-graded case"):
        assert_judged(case)


def test_a_state_graded_case_states_every_table_it_writes(damaged_case: CaseLoader) -> None:
    case = damaged_case(_BARRIER)
    del case.then["tableState"]["sequence_tag"]
    with pytest.raises(CaseFailure, match="states no rows for \\['sequence_tag'\\]"):
        assert_judged(case)


def test_a_golden_graded_buffer_carries_no_refusal(damaged_case: CaseLoader) -> None:
    case = damaged_case(
        "m-unit-work-015-close-settles-against-the-milestone-its-own-find-observed.yaml"
    )
    case.when["scenario"][2]["write"][0]["expectError"] = "write-evidence-already-claimed"
    with pytest.raises(CaseFailure, match="only a `grading: state` scenario carries"):
        assert_judged(case)


# --- a golden-graded Scenario's own table state ------------------------------


def test_a_golden_graded_scenarios_table_state_is_graded(
    corpus_case: CaseLoader, damaged_case: CaseLoader
) -> None:
    def script(case: Case) -> list[Any]:
        (find,) = (step for step in case.scenario if "expectRows" in step)
        return [
            Rows(tuple(find["expectRows"])),
            Affected(1),
            Affected(1),
            Affected(1),
            Affected(1),
            *(
                Rows(tuple(dict(row) for row in rows))
                for rows in case.expected_table_state.values()
            ),
        ]

    case = corpus_case("m-batch-write-011-readless-predicate-ordering-barrier.yaml")
    with ScriptedProvider(script=script(case)) as db:
        assert_unit_work_scenario(case, db)

    damaged = damaged_case("m-batch-write-011-readless-predicate-ordering-barrier.yaml")
    stated = script(damaged)
    damaged.then["tableState"]["order_item"][0]["sku"] = "B-200"
    with pytest.raises(CaseFailure, match="state after the scenario"):
        assert_unit_work_scenario(damaged, ScriptedProvider(script=stated))
