"""Target submissions in a golden-graded Scenario (`m-case-format` *Buffered
keyed write instructions*): admitted where the document alone says what they
cost, aligned with the golden by the revision their caller states, and owing
the acquisitions and coverage reads their flush makes, whatever their
temporal shape. Every refusal below is a defect of the document, refused
before provisioning."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from reference_harness.case import Case
from reference_harness.case_assertions import CaseFailure

from .conftest import assert_judged

type CaseLoader = Callable[[str], Case]

_OPTIMISTIC = (
    "m-unit-work-074-transaction-time-only-target-amendments-share-a-read-layout-twin-columns.yaml"
)
_LOCKING = (
    "m-unit-work-076-locking-transaction-time-only-target-amendments-group-at-the-flush"
    "-layout-twin-columns.yaml"
)
_UNCHANGED = (
    "m-unit-work-078-unchanged-transaction-time-only-replacements-group-their-guards"
    "-layout-twin-columns.yaml"
)
_MIXED = (
    "m-unit-work-080-each-temporal-shapes-target-writes-share-a-span-of-their-own"
    "-layout-twin-columns.yaml"
)
_INSERTED = (
    "m-unit-work-082-insertion-authorized-transaction-time-only-edits-share-a-read"
    "-layout-twin-columns.yaml"
)


def _miscounted(case: Case, step: int, by: int) -> Case:
    scenario: list[dict[str, Any]] = case.when["scenario"]
    scenario[step]["databaseCalls"] += by
    case.then["databaseCalls"] += by
    return case


@pytest.mark.parametrize("name", [_OPTIMISTIC, _LOCKING, _UNCHANGED, _MIXED, _INSERTED])
def test_a_golden_graded_buffer_carries_target_submissions(
    corpus_case: CaseLoader, name: str
) -> None:
    assert_judged(corpus_case(name))


# --- the reads a target submission's flush owes --------------------------------


@pytest.mark.parametrize(
    ("name", "step", "owed"),
    [
        (_OPTIMISTIC, 0, 1),
        (_LOCKING, 0, 2),
        (_UNCHANGED, 1, 1),
        (_MIXED, 0, 2),
        (_INSERTED, 2, 1),
    ],
    ids=[
        "transaction-time-only-targets-share-one-read",
        "locking-acquires-each-row-at-its-call",
        "guarded-and-closed-targets-share-one-read",
        "each-shape-reads-in-a-span-of-its-own",
        "writes-through-flushed-inserts-share-one-read",
    ],
)
@pytest.mark.parametrize("by", [-1, 1], ids=["one-fewer", "one-more"])
def test_a_step_declares_the_reads_its_targets_owe(
    damaged_case: CaseLoader, name: str, step: int, owed: int, by: int
) -> None:
    case = _miscounted(damaged_case(name), step, by)
    with pytest.raises(CaseFailure, match=f"owes {owed} resolving read"):
        assert_judged(case)


# --- the revision a target's golden states -------------------------------------


@pytest.mark.parametrize(("name", "step"), [(_OPTIMISTIC, 0), (_UNCHANGED, 1)])
def test_an_optimistic_target_gates_its_starting_row_on_its_callers_start(
    damaged_case: CaseLoader, name: str, step: int
) -> None:
    case = damaged_case(name)
    first = case.when["scenario"][step]["statements"][0]
    first["binds"][1] = ["2023-12-02T00:00:00.000000Z", *first["binds"][1][1:]]
    with pytest.raises(CaseFailure, match="gated on its caller's stated start"):
        assert_judged(case)


# --- the target forms only a state-graded case carries -------------------------


def test_a_refused_target_submission_stays_state_graded(damaged_case: CaseLoader) -> None:
    case = damaged_case(_OPTIMISTIC)
    case.when["scenario"][0]["write"][1]["expectError"] = "write-evidence-already-claimed"
    with pytest.raises(CaseFailure, match="refused submission, which only a `grading: state`"):
        assert_judged(case)


def test_a_locking_bitemporal_target_stays_state_graded(damaged_case: CaseLoader) -> None:
    case = damaged_case(_MIXED)
    case.when["uow"]["concurrency"] = "locking"
    with pytest.raises(CaseFailure, match="Locking target submission of a Bitemporal Entity"):
        assert_judged(case)


def test_a_target_of_an_object_its_group_writes_again_stays_state_graded(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_OPTIMISTIC)
    write: list[dict[str, Any]] = case.when["scenario"][0]["write"]
    write.append({**write[0], "row": {"id": 1, "amount": 115}})
    with pytest.raises(CaseFailure, match="also writes in its group"):
        assert_judged(case)


def test_a_target_of_an_object_its_group_observed_stays_state_graded(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_OPTIMISTIC)
    find = {
        "uow": "amend",
        "objectQuery": {
            "target": "parallax.compatibility.KeptLog",
            "predicate": {"eq": {"path": "parallax.compatibility.KeptLog.id", "value": 1}},
            "temporal": {"transaction-time": {"asOf": "latest"}},
        },
        "databaseCalls": 1,
        "statements": [],
        "expectRows": [
            {
                "id": 1,
                "amount": 100,
                "in_z": "2023-12-01T00:00:00.000000Z",
                "out_z": "infinity",
                "memo": {"note": "n5"},
            }
        ],
    }
    case.when["scenario"].insert(0, find)
    with pytest.raises(CaseFailure, match="scenario\\[0\\] of its group observed"):
        assert_judged(case)
