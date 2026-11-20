"""Target submissions in a golden-graded Scenario (`m-case-format` *Buffered
keyed write instructions*): admitted where the document alone says what they
cost, aligned with the golden by the revision their caller states, and owing
the acquisitions and coverage reads their flush makes, whatever their
temporal shape. Every refusal below is a defect of the document, refused
before provisioning."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from reference_harness.case import Case, load_model
from reference_harness.case_assertions import CaseFailure

from .conftest import COMPATIBILITY_ROOT, assert_judged

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
_TERMINATED = (
    "m-unit-work-084-transaction-time-only-target-terminations-close-unread-in-one-statement"
    "-layout-twin-columns.yaml"
)
_FAILED_TERMINATIONS = (
    "m-unit-work-086-a-stale-or-missing-start-fails-its-terminations-group-layout-twin-columns.yaml"
)
_LOCKING_TERMINATED = (
    "m-unit-work-088-locking-transaction-time-only-target-terminations-group-at-the-flush"
    "-layout-twin-columns.yaml"
)


def _miscounted(case: Case, step: int, by: int) -> Case:
    scenario: list[dict[str, Any]] = case.when["scenario"]
    scenario[step]["databaseCalls"] += by
    case.then["databaseCalls"] += by
    return case


@pytest.mark.parametrize(
    "name",
    [
        _OPTIMISTIC,
        _LOCKING,
        _UNCHANGED,
        _MIXED,
        _INSERTED,
        _TERMINATED,
        _FAILED_TERMINATIONS,
        _LOCKING_TERMINATED,
    ],
)
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
        (_TERMINATED, 0, 0),
        (_FAILED_TERMINATIONS, 1, 0),
        (_LOCKING_TERMINATED, 0, 2),
    ],
    ids=[
        "transaction-time-only-targets-share-one-read",
        "locking-acquires-each-row-at-its-call",
        "guarded-and-closed-targets-share-one-read",
        "each-shape-reads-in-a-span-of-its-own",
        "writes-through-flushed-inserts-share-one-read",
        "optimistic-terminations-read-nothing",
        "a-failing-termination-reads-nothing-either",
        "locking-terminations-acquire-each-row-at-its-call",
    ],
)
@pytest.mark.parametrize("by", [-1, 1], ids=["one-fewer", "one-more"])
def test_a_step_declares_the_reads_its_targets_owe(
    damaged_case: CaseLoader, name: str, step: int, owed: int, by: int
) -> None:
    case = _miscounted(damaged_case(name), step, by)
    with pytest.raises(CaseFailure, match=f"owes {owed} resolving read"):
        assert_judged(case)


@pytest.mark.parametrize(
    "name",
    [_OPTIMISTIC, _LOCKING, _TERMINATED, _LOCKING_TERMINATED],
    ids=[
        "optimistic-amendments-share-one-read",
        "locking-acquires-each-row",
        "optimistic-terminations-read-nothing",
        "locking-terminations-acquire-each-row",
    ],
)
def test_an_ungrouped_target_write_resolves_no_source(damaged_case: CaseLoader, name: str) -> None:
    case = damaged_case(name)
    (step,) = case.when["scenario"]
    del step["uow"]
    assert_judged(case)


def test_a_write_through_a_pending_insert_composes_with_it_and_reads_nothing(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_INSERTED)
    scenario: list[dict[str, Any]] = case.when["scenario"]
    edits = scenario.pop(2)
    scenario[0]["write"].extend(edits["write"])
    scenario[1]["flush"][0]["binds"][1] = [130, 140]
    for row, amount in zip(scenario[1]["expectRows"], (130, 140), strict=True):
        row["amount"] = amount
    case.then["databaseCalls"] = 2
    assert_judged(case)


def test_a_write_through_its_flushed_insert_by_default_reads_its_coverage(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_INSERTED)
    for entry in case.when["scenario"][2]["write"]:
        del entry["on"]
    assert_judged(case)


@pytest.mark.parametrize("name", [_OPTIMISTIC, _LOCKING], ids=["optimistic", "locking"])
def test_an_empty_target_amendment_costs_and_emits_nothing(
    damaged_case: CaseLoader, name: str
) -> None:
    case = damaged_case(name)
    write: list[dict[str, Any]] = case.when["scenario"][0]["write"]
    write.append({**write[0], "row": {"id": 999}})
    assert_judged(case)


@pytest.mark.parametrize("targets", [1, 2], ids=["alone", "beside-another-it-stops"])
def test_a_target_a_temporal_conflict_refuses_emits_nothing(
    damaged_case: CaseLoader, targets: int
) -> None:
    case = damaged_case(_OPTIMISTIC)
    seed = damaged_case(_UNCHANGED).when["scenario"][0]
    step: dict[str, Any] = case.when["scenario"][0]
    step["write"] = [
        {**entry, "at": "2023-12-01T00:00:00.000000Z"} for entry in step["write"][:targets]
    ]
    step["databaseCalls"], step["statements"] = 1, []
    case.when["scenario"].insert(0, seed)
    case.then["databaseCalls"] = 2
    case.then["units"] = {
        "amend": {
            "outcome": "rolledBack",
            "flushFailure": {
                "at": "commit",
                "entity": "parallax.compatibility.KeptLog",
                "key": {"id": 1},
                "error": "temporalConflict",
            },
        }
    }
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


def _through_may(case: Case, *, stated: str, may_start: str) -> Case:
    """Case 080 with span 1's target extended over its May rectangle, whose
    close starts at *may_start*, the target stating *stated*."""
    step: dict[str, Any] = case.when["scenario"][0]
    step["write"][2] = {
        **step["write"][2],
        "until": "2024-08-01T00:00:00.000000Z",
        "ifTxStart": stated,
    }
    close = step["statements"][2]["binds"]
    close[0] = [1, 1, 2]
    close[1] = ["2024-04-01T00:00:00.000000Z", "2024-08-01T00:00:00.000000Z", "infinity"]
    close[2] = ["2023-12-01T00:00:00.000000Z", may_start, "2023-12-01T00:00:00.000000Z"]
    close[3] = ["2024-11-01T00:00:00.000000Z"] * 3
    return case


def test_a_bitemporal_target_gates_its_starting_rectangle_on_its_callers_start(
    damaged_case: CaseLoader,
) -> None:
    december_15 = "2023-12-15T00:00:00.000000Z"
    stale = _through_may(damaged_case(_MIXED), stated=december_15, may_start=december_15)
    with pytest.raises(CaseFailure, match="gated on its caller's stated start"):
        assert_judged(stale)


def test_rectangles_sharing_a_start_gate_on_it_each(damaged_case: CaseLoader) -> None:
    december_1 = "2023-12-01T00:00:00.000000Z"
    assert_judged(_through_may(damaged_case(_MIXED), stated=december_1, may_start=december_1))


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


def test_a_find_of_another_entity_observes_no_target_of_the_same_key(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_OPTIMISTIC)
    find = {
        "uow": "amend",
        "objectQuery": {
            "target": "parallax.compatibility.KeptSpan",
            "predicate": {"eq": {"path": "parallax.compatibility.KeptSpan.id", "value": 1}},
        },
        "databaseCalls": 0,
        "statements": [],
        "expectRows": [{"id": 1, "amount": 100, "label": "a"}],
    }
    case.when["scenario"].insert(0, find)
    assert_judged(case)


def test_a_find_including_a_targets_entity_may_have_observed_it() -> None:
    raw: dict[str, Any] = {
        "model": "models/orders-versioned.yaml",
        "tags": ["m-unit-work"],
        "shape": "scenario",
        "when": {
            "uow": {"concurrency": "locking"},
            "scenario": [
                {
                    "uow": "g",
                    "objectQuery": {
                        "target": "parallax.compatibility.Order",
                        "predicate": {
                            "eq": {"path": "parallax.compatibility.Order.id", "value": 1}
                        },
                        "includes": [{"segments": [{"rel": "parallax.compatibility.Order.items"}]}],
                    },
                    "databaseCalls": 0,
                    "statements": [],
                    "expectRows": [{"id": 1}],
                },
                {
                    "uow": "g",
                    "write": [
                        {
                            "mutation": "amend",
                            "entity": "parallax.compatibility.OrderItem",
                            "row": {"id": 11, "sku": "Z"},
                            "ifVersion": 1,
                        }
                    ],
                    "databaseCalls": 2,
                    "statements": [],
                },
            ],
        },
        "then": {"databaseCalls": 2},
    }
    model = load_model(COMPATIBILITY_ROOT, "models/orders-versioned.yaml")
    case = Case(path=Path("m-unit-work-996-synthetic.yaml"), raw=raw, model=model)
    with pytest.raises(CaseFailure, match="scenario\\[0\\] of its group observed"):
        assert_judged(case)
