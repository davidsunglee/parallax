"""DB-free tests for the `then.executionLifecycle` oracle and its adapter mirror.

The oracle (`m-execution-lifecycle`) is graded by each language implementation,
not by this harness, so what the harness owes it is that an authored stream —
and the observation an adapter mirrors back — cannot describe a run that could
not have happened. Two layers carry that:

* the schemas close the algebra an event, an outcome, and a failure admit, on
  BOTH sides of the mirror;
* :mod:`reference_harness.execution_validate` closes the relations no JSON
  Schema states, on BOTH sides too — correlation that describes a tree,
  balanced Starteds and Finisheds, attribution one link deep, statement indexes
  that name something, a call count agreeing with the record's own count
  oracle, each batch's positional trigger claim, and the attempt history a
  terminal transaction stream admits.

The whole corpus is asserted consistent under both.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from reference_harness.corpus_yaml import read_corpus_yaml
from reference_harness.execution_validate import (
    validate_execution,
    validate_execution_observation,
)
from reference_harness.schemas import build_registry, load_schemas

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMAS = _REPO_ROOT / "core" / "schemas"
_CASES = _REPO_ROOT / "core" / "compatibility" / "cases"
_REGISTRY = build_registry(load_schemas(_SCHEMAS.parent))


def _valid_against(schema_name: str, doc: dict[str, Any]) -> bool:
    schema = json.loads((_SCHEMAS / schema_name).read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, registry=_REGISTRY)
    return next(validator.iter_errors(doc), None) is None


def _event(sequence: int, activity: int, parent: int | None, **transition: Any) -> dict[str, Any]:
    return {"sequence": sequence, "activity": activity, "parent": parent, **transition}


def _root(kind: str, events: list[dict[str, Any]], execution: int = 1) -> dict[str, Any]:
    return {"execution": execution, "kind": kind, "events": events}


def _lifecycle(*roots: dict[str, Any]) -> dict[str, Any]:
    return {"roots": list(roots)}


def _write_root(**attempt_finish: Any) -> dict[str, Any]:
    """One transaction root: an invocation, an attempt, a pre-commit batch, one write."""
    finish = attempt_finish or {"outcome": "committed"}
    return _root(
        "transaction-invocation",
        [
            _event(
                1,
                1,
                None,
                transactionInvocationStarted={
                    "invocation": "outer",
                    "concurrency": "locking",
                    "retries": 10,
                    "retryOptimisticConflicts": False,
                },
            ),
            _event(2, 2, 1, transactionAttemptStarted={}),
            _event(3, 3, 2, writeBatchStarted={"trigger": "pre-commit"}),
            _event(
                4,
                4,
                3,
                databaseCallStarted={"target": "Account", "kind": "write", "statement": 0},
            ),
            _event(5, 4, 3, databaseCallFinished={"outcome": "writeCompleted", "affectedRows": 1}),
            _event(6, 3, 2, writeBatchFinished={"outcome": "completed"}),
            _event(7, 2, 1, transactionAttemptFinished=finish),
            _event(8, 1, None, transactionInvocationFinished={"outcome": "committed"}),
        ],
    )


def _case(lifecycle: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    case: dict[str, Any] = {
        "model": "models/account.yaml",
        "tags": ["m-execution-lifecycle"],
        "shape": "writeSequence",
        "when": {
            "writeSequence": [
                {
                    "mutation": "insert",
                    "entity": "Account",
                    "statements": 1,
                    "rows": [{"id": 9}],
                }
            ]
        },
        "then": {
            "statements": [
                {"sql": {"postgres": "insert into account(id) values (?)"}, "binds": [9]}
            ],
            "tableState": {"account": [{"id": 9}]},
            "roundTrips": 1,
            "executionLifecycle": lifecycle,
        },
    }
    for key, value in overrides.items():
        case[key] = value
    return case


def _run_envelope(lifecycle: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": "1",
        "command": "run",
        "status": "ok",
        "adapter": {"language": "example", "name": "example-adapter", "version": "1.0.0"},
        "case": "cases/m-execution-lifecycle-001-standalone-read.yaml",
        "dialect": "postgres",
        "caseShape": "writeSequence",
        "emissions": [{"casePointer": "/then/statements/0", "sql": "select 1", "binds": []}],
        "observations": {"roundTrips": 1, "executionLifecycle": lifecycle},
    }


# --- positive controls, so every refusal below is refused for its own reason --


def test_the_fixture_case_and_envelope_are_accepted_as_authored() -> None:
    assert _valid_against("compatibility-case.schema.json", _case(_lifecycle(_write_root())))
    assert _valid_against(
        "conformance-adapter.schema.json", _run_envelope(_lifecycle(_write_root()))
    )
    assert validate_execution(_case(_lifecycle(_write_root()))) == []
    assert validate_execution_observation(_run_envelope(_lifecycle(_write_root()))) == []


# --- the closed event algebra, on both sides of the mirror -------------------


def test_an_event_carrying_two_transitions_is_refused_by_both_schemas() -> None:
    root = _write_root()
    root["events"][0]["readStarted"] = {"target": "Account", "interface": "typed"}
    assert not _valid_against("compatibility-case.schema.json", _case(_lifecycle(root)))
    assert not _valid_against("conformance-adapter.schema.json", _run_envelope(_lifecycle(root)))


def test_an_event_carrying_no_transition_is_refused_by_both_schemas() -> None:
    root = _write_root()
    del root["events"][0]["transactionInvocationStarted"]
    assert not _valid_against("compatibility-case.schema.json", _case(_lifecycle(root)))
    assert not _valid_against("conformance-adapter.schema.json", _run_envelope(_lifecycle(root)))


def test_an_event_omitting_its_parent_is_refused_by_both_schemas() -> None:
    """`null` is the root activity's ASSERTION, so absence is not the same claim."""
    root = _write_root()
    del root["events"][0]["parent"]
    assert not _valid_against("compatibility-case.schema.json", _case(_lifecycle(root)))
    assert not _valid_against("conformance-adapter.schema.json", _run_envelope(_lifecycle(root)))


def test_a_row_count_beside_a_failed_call_is_refused_by_both_schemas() -> None:
    root = _write_root()
    root["events"][4]["databaseCallFinished"] = {
        "outcome": "failed",
        "category": "deadlock",
        "affectedRows": 0,
    }
    assert not _valid_against("compatibility-case.schema.json", _case(_lifecycle(root)))
    assert not _valid_against("conformance-adapter.schema.json", _run_envelope(_lifecycle(root)))


def test_a_completed_call_omitting_its_count_is_refused_by_both_schemas() -> None:
    root = _write_root()
    root["events"][4]["databaseCallFinished"] = {"outcome": "writeCompleted"}
    assert not _valid_against("compatibility-case.schema.json", _case(_lifecycle(root)))
    assert not _valid_against("conformance-adapter.schema.json", _run_envelope(_lifecycle(root)))


# --- attribution belongs to a failing outcome alone --------------------------


def test_an_attribution_on_a_completed_activity_is_refused_by_both_schemas() -> None:
    root = _write_root()
    root["events"][5]["writeBatchFinished"] = {"outcome": "completed", "attribution": "direct"}
    assert not _valid_against("compatibility-case.schema.json", _case(_lifecycle(root)))
    assert not _valid_against("conformance-adapter.schema.json", _run_envelope(_lifecycle(root)))


def test_a_failing_activity_omitting_its_attribution_is_refused_by_both_schemas() -> None:
    root = _write_root()
    root["events"][5]["writeBatchFinished"] = {"outcome": "failed"}
    assert not _valid_against("compatibility-case.schema.json", _case(_lifecycle(root)))
    assert not _valid_against("conformance-adapter.schema.json", _run_envelope(_lifecycle(root)))


def test_a_caused_failure_naming_no_cause_is_refused_by_both_schemas() -> None:
    root = _write_root()
    root["events"][5]["writeBatchFinished"] = {"outcome": "failed", "attribution": "caused"}
    assert not _valid_against("compatibility-case.schema.json", _case(_lifecycle(root)))
    assert not _valid_against("conformance-adapter.schema.json", _run_envelope(_lifecycle(root)))


def test_a_direct_failure_naming_a_cause_is_refused_by_both_schemas() -> None:
    root = _write_root()
    root["events"][5]["writeBatchFinished"] = {
        "outcome": "failed",
        "attribution": "direct",
        "cause": 4,
    }
    assert not _valid_against("compatibility-case.schema.json", _case(_lifecycle(root)))
    assert not _valid_against("conformance-adapter.schema.json", _run_envelope(_lifecycle(root)))


# --- the invocation states the policy it resolved ----------------------------


def test_a_committed_attempt_carrying_a_failure_is_refused_by_both_schemas() -> None:
    root = _write_root(outcome="committed", phase="commit", retryEligible=True)
    assert not _valid_against("compatibility-case.schema.json", _case(_lifecycle(root)))
    assert not _valid_against("conformance-adapter.schema.json", _run_envelope(_lifecycle(root)))


def test_a_rolled_back_attempt_omitting_its_phase_is_refused_by_both_schemas() -> None:
    root = _write_root(outcome="rolledBack", attribution="direct")
    assert not _valid_against("compatibility-case.schema.json", _case(_lifecycle(root)))
    assert not _valid_against("conformance-adapter.schema.json", _run_envelope(_lifecycle(root)))


def test_a_successful_rollback_naming_a_second_failure_is_refused_by_both_schemas() -> None:
    root = _write_root(
        outcome="rolledBack",
        phase="commit",
        retryEligible=False,
        attribution="direct",
        rollbackCode="whatever",
    )
    assert not _valid_against("compatibility-case.schema.json", _case(_lifecycle(root)))
    assert not _valid_against("conformance-adapter.schema.json", _run_envelope(_lifecycle(root)))


def test_a_commit_phase_failure_naming_a_cause_is_refused_by_both_schemas() -> None:
    root = _write_root(
        outcome="rolledBack",
        phase="commit",
        retryEligible=True,
        attribution="caused",
        cause=3,
    )
    assert not _valid_against("compatibility-case.schema.json", _case(_lifecycle(root)))
    assert not _valid_against("conformance-adapter.schema.json", _run_envelope(_lifecycle(root)))


def test_a_joined_invocation_restating_the_resolved_policy_is_refused_by_both_schemas() -> None:
    root = _write_root()
    root["events"][0]["transactionInvocationStarted"] = {"invocation": "joined", "retries": 10}
    assert not _valid_against("compatibility-case.schema.json", _case(_lifecycle(root)))
    assert not _valid_against("conformance-adapter.schema.json", _run_envelope(_lifecycle(root)))


def test_an_outer_invocation_omitting_the_resolved_policy_is_refused_by_both_schemas() -> None:
    root = _write_root()
    root["events"][0]["transactionInvocationStarted"] = {"invocation": "outer"}
    assert not _valid_against("compatibility-case.schema.json", _case(_lifecycle(root)))
    assert not _valid_against("conformance-adapter.schema.json", _run_envelope(_lifecycle(root)))


# --- correlation that describes a tree ---------------------------------------


def test_a_sequence_disagreeing_with_its_delivery_position_is_flagged() -> None:
    root = _write_root()
    root["events"][3]["sequence"] = 9
    assert validate_execution(_case(_lifecycle(root)))


def test_a_started_taking_an_id_out_of_order_is_flagged() -> None:
    root = _write_root()
    root["events"][3]["activity"] = 9
    root["events"][4]["activity"] = 9
    assert validate_execution(_case(_lifecycle(root)))


def test_a_parent_no_started_ever_assigned_is_flagged() -> None:
    root = _write_root()
    root["events"][3]["parent"] = 99
    root["events"][4]["parent"] = 99
    assert validate_execution(_case(_lifecycle(root)))


def test_a_parent_that_had_already_finished_is_flagged() -> None:
    events = _write_root()["events"]
    events[3]["parent"] = 4
    reordered = _root(
        "transaction-invocation",
        [
            events[0],
            events[1],
            events[2],
            _event(3, 3, 2, writeBatchFinished={"outcome": "completed"}),
            _event(
                4,
                4,
                3,
                databaseCallStarted={"target": "Account", "kind": "write", "statement": 0},
            ),
            _event(5, 4, 3, databaseCallFinished={"outcome": "writeCompleted", "affectedRows": 1}),
            events[6],
            events[7],
        ],
    )
    problems = validate_execution(_case(_lifecycle(reordered)))
    assert any("had already finished" in problem for problem in problems)


def test_a_second_activity_without_a_parent_is_flagged() -> None:
    root = _write_root()
    root["events"][1]["parent"] = None
    root["events"][6]["parent"] = None
    assert validate_execution(_case(_lifecycle(root)))


def test_a_root_kind_disagreeing_with_its_own_root_activity_is_flagged() -> None:
    root = _write_root()
    root["kind"] = "read"
    problems = validate_execution(_case(_lifecycle(root)))
    assert any("root activity is readStarted" in problem for problem in problems)


def test_a_finished_naming_a_different_parent_than_its_started_is_flagged() -> None:
    root = _write_root()
    root["events"][5]["parent"] = 1
    assert validate_execution(_case(_lifecycle(root)))


def test_a_finished_of_a_different_kind_than_its_started_is_flagged() -> None:
    root = _write_root()
    root["events"][5] = _event(6, 3, 2, readFinished={"outcome": "completed"})
    problems = validate_execution(_case(_lifecycle(root)))
    assert any("same activity KIND" in problem for problem in problems)


def test_an_activity_finished_twice_is_flagged() -> None:
    root = _write_root()
    root["events"][5] = _event(
        6, 4, 3, databaseCallFinished={"outcome": "writeCompleted", "affectedRows": 1}
    )
    problems = validate_execution(_case(_lifecycle(root)))
    assert any("already finished" in problem for problem in problems)


def test_a_finished_naming_an_activity_no_started_assigned_is_flagged() -> None:
    root = _write_root()
    root["events"][5] = _event(6, 9, 2, writeBatchFinished={"outcome": "completed"})
    problems = validate_execution(_case(_lifecycle(root)))
    assert any("no Started assigned" in problem for problem in problems)


def test_a_root_left_with_an_open_activity_is_flagged() -> None:
    root = _write_root()
    del root["events"][5]
    root["events"][5]["sequence"] = 6
    root["events"][6]["sequence"] = 7
    problems = validate_execution(_case(_lifecycle(root)))
    assert any("still open" in problem for problem in problems)


def test_a_root_ending_on_something_other_than_its_root_activity_is_flagged() -> None:
    root = _write_root()
    root["events"].append(_event(9, 5, 1, transactionAttemptStarted={}))
    root["events"].append(_event(10, 5, 1, transactionAttemptFinished={"outcome": "committed"}))
    problems = validate_execution(_case(_lifecycle(root)))
    assert any("last event delivered" in problem for problem in problems)


def test_a_root_that_opens_no_root_activity_is_flagged() -> None:
    root = _root(
        "transaction-invocation",
        [
            _event(1, 1, 2, transactionAttemptStarted={}),
            _event(2, 1, 2, transactionAttemptFinished={"outcome": "committed"}),
        ],
    )
    problems = validate_execution(_case(_lifecycle(root)))
    assert any("opens no root activity" in problem for problem in problems)


def test_a_first_observation_index_out_of_order_is_flagged() -> None:
    lifecycle = _lifecycle(_write_root(), _write_root())
    lifecycle["roots"][1]["execution"] = 1
    assert validate_execution(_case(lifecycle))


# --- attribution walks one link at a time ------------------------------------


def test_a_cause_naming_something_other_than_a_direct_child_is_flagged() -> None:
    root = _write_root(
        outcome="rolledBack", phase="pre-commit", retryEligible=False, attribution="caused", cause=4
    )
    root["events"][7]["transactionInvocationFinished"] = {
        "outcome": "failed",
        "attribution": "caused",
        "cause": 2,
    }
    problems = validate_execution(_case(_lifecycle(root)))
    assert any("no direct child of activity 2" in problem for problem in problems)


def test_a_cause_naming_a_child_that_had_not_finished_is_flagged() -> None:
    root = _root(
        "transaction-invocation",
        [
            _event(
                1,
                1,
                None,
                transactionInvocationStarted={
                    "invocation": "outer",
                    "concurrency": "locking",
                    "retries": 10,
                    "retryOptimisticConflicts": False,
                },
            ),
            _event(2, 2, 1, transactionAttemptStarted={}),
            _event(
                3,
                1,
                None,
                transactionInvocationFinished={
                    "outcome": "failed",
                    "attribution": "caused",
                    "cause": 2,
                },
            ),
            _event(4, 2, 1, transactionAttemptFinished={"outcome": "committed"}),
        ],
    )
    case = _case(_lifecycle(root))
    case["then"]["roundTrips"] = 0
    problems = validate_execution(case)
    assert any("had not finished" in problem for problem in problems)


# --- a batch's trigger is a positional claim ---------------------------------


def test_a_pre_commit_batch_followed_by_more_attempt_work_is_flagged() -> None:
    root = _write_root()
    root["events"].insert(
        6, _event(7, 5, 2, readStarted={"target": "Account", "interface": "typed"})
    )
    root["events"].insert(7, _event(8, 5, 2, readFinished={"outcome": "completed"}))
    root["events"][8]["sequence"] = 9
    root["events"][9]["sequence"] = 10
    problems = validate_execution(_case(_lifecycle(root)))
    assert any("boundary owns the FINAL batch" in problem for problem in problems)


def test_a_read_dependency_batch_with_no_read_after_it_is_flagged() -> None:
    root = _write_root()
    root["events"][2]["writeBatchStarted"] = {"trigger": "read-dependency"}
    problems = validate_execution(_case(_lifecycle(root)))
    assert any("in front of the read it enabled" in problem for problem in problems)


def test_a_read_dependency_batch_standing_before_its_read_is_accepted() -> None:
    root = _write_root()
    root["events"][2]["writeBatchStarted"] = {"trigger": "read-dependency"}
    root["events"].insert(
        6, _event(7, 5, 2, readStarted={"target": "Account", "interface": "typed"})
    )
    root["events"].insert(7, _event(8, 5, 2, readFinished={"outcome": "completed"}))
    root["events"][8]["sequence"] = 9
    root["events"][9]["sequence"] = 10
    assert validate_execution(_case(_lifecycle(root))) == []


# --- indexes that name something ---------------------------------------------


def test_a_call_naming_an_unauthored_golden_statement_is_flagged() -> None:
    root = _write_root()
    root["events"][3]["databaseCallStarted"]["statement"] = 999
    assert validate_execution(_case(_lifecycle(root)))


def test_a_call_index_on_a_lane_authoring_no_golden_is_flagged() -> None:
    case = _case(_lifecycle(_write_root()))
    del case["then"]["statements"]
    assert validate_execution(case)


def test_a_golden_bearing_call_omitting_its_statement_is_flagged() -> None:
    root = _write_root()
    del root["events"][3]["databaseCallStarted"]["statement"]
    assert validate_execution(_case(_lifecycle(root)))


def test_a_stepwise_case_indexes_the_goldens_its_own_steps_author() -> None:
    """Goldens authored per scenario step are one flattened order, not none."""
    when = {
        "scenario": [
            {
                "write": {"mutation": "insert", "entity": "Account", "rows": [{"id": 9}]},
                "statements": [{"sql": {"postgres": "insert into account(id) values (?)"}}],
            },
            {
                "write": {"mutation": "insert", "entity": "Account", "rows": [{"id": 10}]},
                "statements": [{"sql": {"postgres": "insert into account(id) values (?)"}}],
            },
        ]
    }
    case = _case(_lifecycle(_write_root()), when=when, shape="scenario")
    del case["then"]["statements"]
    del case["then"]["tableState"]
    assert validate_execution(case) == []
    root = _write_root()
    root["events"][3]["databaseCallStarted"]["statement"] = 2
    stale = _case(_lifecycle(root), when=when, shape="scenario")
    del stale["then"]["statements"]
    del stale["then"]["tableState"]
    assert validate_execution(stale)


# --- the sole count oracle ----------------------------------------------------


def test_a_record_disagreeing_with_the_case_round_trips_is_flagged() -> None:
    case = _case(_lifecycle(_write_root()))
    case["then"]["roundTrips"] = 2
    problems = validate_execution(case)
    assert any("sole count oracle" in problem for problem in problems)


# --- the attempt history a terminal stream admits -----------------------------


def _retry_root(outcomes: list[dict[str, Any]], retries: int) -> dict[str, Any]:
    """One invocation with one attempt per entry of *outcomes* and no calls at all."""
    events = [
        _event(
            1,
            1,
            None,
            transactionInvocationStarted={
                "invocation": "outer",
                "concurrency": "locking",
                "retries": retries,
                "retryOptimisticConflicts": False,
            },
        )
    ]
    for index, outcome in enumerate(outcomes):
        activity = index + 2
        events.append(_event(len(events) + 1, activity, 1, transactionAttemptStarted={}))
        events.append(_event(len(events) + 1, activity, 1, transactionAttemptFinished=outcome))
    committed = outcomes[-1].get("outcome") == "committed"
    events.append(
        _event(
            len(events) + 1,
            1,
            None,
            transactionInvocationFinished=(
                {"outcome": "committed"}
                if committed
                else {"outcome": "failed", "attribution": "caused", "cause": len(outcomes) + 1}
            ),
        )
    )
    return _root("transaction-invocation", events)


def _rolled(retry_eligible: bool) -> dict[str, Any]:
    return {
        "outcome": "rolledBack",
        "phase": "commit",
        "retryEligible": retry_eligible,
        "attribution": "direct",
    }


def _retry_case(root: dict[str, Any]) -> dict[str, Any]:
    case = _case(_lifecycle(root))
    case["then"]["roundTrips"] = 0
    return case


def test_a_committed_attempt_followed_by_another_is_flagged() -> None:
    assert (
        validate_execution(_retry_case(_retry_root([_rolled(True), {"outcome": "committed"}], 1)))
        == []
    )
    assert validate_execution(
        _retry_case(_retry_root([{"outcome": "committed"}, _rolled(True)], 1))
    )


def test_a_non_retriable_failure_followed_by_another_attempt_is_flagged() -> None:
    assert validate_execution(
        _retry_case(_retry_root([_rolled(False), {"outcome": "committed"}], 1))
    )


def test_more_attempts_than_the_resolved_bound_allows_is_flagged() -> None:
    assert validate_execution(_retry_case(_retry_root([_rolled(True), _rolled(True)], 1))) == []
    assert validate_execution(_retry_case(_retry_root([_rolled(True), _rolled(True)], 0)))


def test_a_retry_eligible_final_rollback_with_budget_left_is_flagged() -> None:
    assert validate_execution(_retry_case(_retry_root([_rolled(True)], 0))) == []
    assert validate_execution(_retry_case(_retry_root([_rolled(True)], 1)))
    assert validate_execution(_retry_case(_retry_root([_rolled(False)], 10))) == []


# --- the same relations over the adapter's observation ------------------------


def test_the_envelope_observation_is_walked_against_its_own_emissions() -> None:
    envelope = _run_envelope(_lifecycle(_write_root()))
    assert validate_execution_observation(envelope) == []

    envelope["emissions"] = []
    assert validate_execution_observation(envelope)


def test_an_observed_call_omitting_its_statement_beside_emissions_is_flagged() -> None:
    root = _write_root()
    del root["events"][3]["databaseCallStarted"]["statement"]
    assert validate_execution_observation(_run_envelope(_lifecycle(root)))


def test_an_observed_stream_disagreeing_with_the_observed_round_trips_is_flagged() -> None:
    envelope = _run_envelope(_lifecycle(_write_root()))
    envelope["observations"]["roundTrips"] = 3
    assert validate_execution_observation(envelope)


def test_an_envelope_reporting_no_lifecycle_has_nothing_to_walk() -> None:
    envelope = _run_envelope(_lifecycle(_write_root()))
    del envelope["observations"]["executionLifecycle"]
    assert validate_execution_observation(envelope) == []


# --- the corpus itself --------------------------------------------------------


def test_every_authored_oracle_in_the_corpus_is_internally_consistent() -> None:
    authored = 0
    for case_path in sorted(_CASES.glob("**/*.y*ml")):
        case = read_corpus_yaml(case_path)
        if not isinstance(case, dict):  # pragma: no cover - corpus is a mapping per file
            continue
        then = case.get("then")
        if isinstance(then, dict) and "executionLifecycle" in then:
            authored += 1
        assert validate_execution(case) == [], case_path.name
    assert authored == 6
