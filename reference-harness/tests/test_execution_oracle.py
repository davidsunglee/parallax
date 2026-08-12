"""DB-free tests for the `then.execution` oracle and its adapter mirror.

The oracle (`m-execution-log`) is graded by each language implementation, not by
this harness, so what the harness owes it is that an authored oracle — and the
observation an adapter mirrors back — cannot be internally impossible. Two
layers carry that:

* the schemas close the algebra a call, an attempt, and a case shape admit, on
  BOTH sides of the mirror;
* :mod:`reference_harness.execution_validate` closes the relations no JSON
  Schema states, on BOTH sides too — statement and call indexes that name
  something, round-trip counts that agree at every level and with the record's
  own count oracle, each write batch's positional trigger claim, and the attempt
  history a terminal graph admits.

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


def _case(execution: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    case: dict[str, Any] = {
        "model": "models/account.yaml",
        "tags": ["m-execution-log"],
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
            "execution": execution,
        },
    }
    for key, value in overrides.items():
        case[key] = value
    return case


def _write_call(**overrides: Any) -> dict[str, Any]:
    call: dict[str, Any] = {
        "statement": 0,
        "kind": "write",
        "completion": {"writeCompleted": {"affectedRows": 1}},
    }
    call.update(overrides)
    return call


def _log(**overrides: Any) -> dict[str, Any]:
    attempt: dict[str, Any] = {
        "status": "committed",
        "traces": [
            {"writeBatch": {"trigger": "finalization", "calls": [_write_call()], "roundTrips": 1}}
        ],
        "roundTrips": 1,
    }
    attempt.update(overrides)
    return {
        "transactionLog": {
            "concurrency": "locking",
            "retryPolicy": {"maxRetries": 10, "retryOptimisticConflicts": False},
            "attempts": [attempt],
            "roundTrips": 1,
        }
    }


# --- the closed call algebra, on both sides of the mirror -------------------


def test_a_read_call_reporting_a_write_completion_is_refused_by_both_schemas() -> None:
    mismatched = {
        "statement": 0,
        "kind": "read",
        "completion": {"writeCompleted": {"affectedRows": 1}},
    }
    case = _case(_log())
    case["then"]["execution"]["transactionLog"]["attempts"][0]["traces"][0]["writeBatch"][
        "calls"
    ] = [mismatched]
    assert not _valid_against("compatibility-case.schema.json", case)

    envelope = _run_envelope({"readTrace": {"calls": [mismatched], "roundTrips": 1}})
    assert not _valid_against("conformance-adapter.schema.json", envelope)


def test_a_write_call_reporting_a_read_completion_is_refused_by_both_schemas() -> None:
    mismatched = {
        "kind": "write",
        "completion": {"readCompleted": {"returnedRows": 1}},
    }
    envelope = _run_envelope({"readTrace": {"calls": [mismatched], "roundTrips": 1}})
    assert not _valid_against("conformance-adapter.schema.json", envelope)


def _run_envelope(execution: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": "1",
        "command": "run",
        "status": "ok",
        "adapter": {"language": "example", "name": "example-adapter", "version": "1.0.0"},
        "case": "cases/m-execution-log-001-standalone-read-trace.yaml",
        "dialect": "postgres",
        "caseShape": "writeSequence",
        "emissions": [{"casePointer": "/then/statements/0", "sql": "select 1", "binds": []}],
        "observations": {"roundTrips": 1, "execution": execution},
    }


# --- positive controls, so every refusal above is refused for its own reason --


def test_the_fixture_case_and_envelope_are_accepted_as_authored() -> None:
    assert _valid_against("compatibility-case.schema.json", _case(_log()))
    assert _valid_against("conformance-adapter.schema.json", _run_envelope(_log()))
    assert validate_execution(_case(_log())) == []


# --- failure belongs to a rolled-back attempt alone -------------------------


def test_a_committed_attempt_carrying_a_failure_is_refused() -> None:
    case = _case(_log(failure={"phase": "body", "retryEligible": True}))
    assert not _valid_against("compatibility-case.schema.json", case)


def test_an_observed_committed_attempt_carrying_a_failure_is_refused() -> None:
    log = _log(failure={"phase": "body", "retryEligible": True})
    assert not _valid_against("conformance-adapter.schema.json", _run_envelope(log))


def test_a_commit_phase_failure_naming_a_database_call_is_refused_by_both_schemas() -> None:
    failure = {"phase": "commit", "retryEligible": True, "databaseCall": 0}
    case = _case(_log(status="rolled-back", failure=failure))
    assert not _valid_against("compatibility-case.schema.json", case)
    assert not _valid_against(
        "conformance-adapter.schema.json",
        _run_envelope(_log(status="rolled-back", failure=failure)),
    )


# --- the wrapper a case shape admits ----------------------------------------


def test_a_transactional_case_authoring_a_bare_read_trace_is_refused() -> None:
    case = _case({"readTrace": {"calls": [_write_call(kind="read", statement=0)], "roundTrips": 1}})
    case["then"]["execution"]["readTrace"]["calls"][0]["completion"] = {
        "readCompleted": {"returnedRows": 1}
    }
    assert not _valid_against("compatibility-case.schema.json", case)


def _standalone_read_case(execution: dict[str, Any], round_trips: int = 1) -> dict[str, Any]:
    return {
        "model": "models/account.yaml",
        "tags": ["m-execution-log"],
        "shape": "read",
        "when": {"objectQuery": {"target": "Account", "predicate": {"all": {}}}},
        "then": {
            "statements": [{"sql": {"postgres": "select t0.id from account t0"}, "binds": []}],
            "rows": [{"id": 9}],
            "roundTrips": round_trips,
            "execution": execution,
        },
    }


def _standalone_read_trace(round_trips: int = 1) -> dict[str, Any]:
    return {
        "readTrace": {
            "calls": [
                {
                    "statement": 0,
                    "kind": "read",
                    "completion": {"readCompleted": {"returnedRows": 1}},
                }
            ],
            "roundTrips": round_trips,
        }
    }


def test_a_read_case_authoring_a_transaction_log_is_refused() -> None:
    assert _valid_against(
        "compatibility-case.schema.json", _standalone_read_case(_standalone_read_trace())
    )
    assert not _valid_against("compatibility-case.schema.json", _standalone_read_case(_log()))


# --- indexes that name something --------------------------------------------


def test_a_call_naming_an_unauthored_golden_statement_is_flagged() -> None:
    case = _case(_log())
    case["then"]["execution"]["transactionLog"]["attempts"][0]["traces"][0]["writeBatch"]["calls"][
        0
    ]["statement"] = 999
    assert validate_execution(case)


def test_a_call_index_on_a_lane_authoring_no_golden_is_flagged() -> None:
    case = _case(_log())
    del case["then"]["statements"]
    assert validate_execution(case)


def test_a_golden_bearing_call_omitting_its_statement_is_flagged() -> None:
    case = _case(_log())
    del case["then"]["execution"]["transactionLog"]["attempts"][0]["traces"][0]["writeBatch"][
        "calls"
    ][0]["statement"]
    assert validate_execution(case)


def _stepwise_case(when: dict[str, Any], statements: list[int]) -> dict[str, Any]:
    """A case whose goldens live under *when* alone, with calls naming *statements*."""
    calls = [_write_call(statement=index) for index in statements]
    log = _log()
    attempt = log["transactionLog"]["attempts"][0]
    attempt["traces"][0]["writeBatch"]["calls"] = calls
    attempt["traces"][0]["writeBatch"]["roundTrips"] = len(calls)
    attempt["roundTrips"] = len(calls)
    log["transactionLog"]["roundTrips"] = len(calls)
    case = _case(log, when=when)
    del case["then"]["statements"]
    case["then"]["roundTrips"] = len(calls)
    return case


def _golden(sql: str) -> dict[str, Any]:
    return {"sql": {"postgres": sql}, "binds": []}


def test_a_coherence_step_golden_is_part_of_the_flattened_order() -> None:
    when = {
        "coherence": [
            {"statements": [_golden("select 1")]},
            {"statements": [_golden("select 2")]},
        ]
    }
    assert validate_execution(_stepwise_case(when, [0, 1])) == []
    assert validate_execution(_stepwise_case(when, [0, 2]))


def test_a_concurrency_round_golden_is_part_of_the_flattened_order() -> None:
    when = {
        "concurrency": {
            "rounds": [
                {"A": {"statements": [_golden("select 1")]}, "B": {"statements": [_golden("2")]}},
                {"A": {"statements": [_golden("select 3")]}},
            ]
        }
    }
    assert validate_execution(_stepwise_case(when, [0, 1, 2])) == []
    assert validate_execution(_stepwise_case(when, [0, 1, 3]))


def test_an_attempt_failure_naming_an_absent_call_is_flagged() -> None:
    case = _case(
        _log(
            status="rolled-back",
            failure={"phase": "finalization", "retryEligible": False, "databaseCall": 3},
        )
    )
    assert validate_execution(case)


# --- round-trip arithmetic at every level ------------------------------------


def test_a_trace_count_disagreeing_with_its_calls_is_flagged() -> None:
    case = _case(_log())
    case["then"]["execution"]["transactionLog"]["attempts"][0]["traces"][0]["writeBatch"][
        "roundTrips"
    ] = 2
    assert validate_execution(case)


def test_an_attempt_count_disagreeing_with_its_traces_is_flagged() -> None:
    case = _case(_log(roundTrips=2))
    assert validate_execution(case)


def test_a_log_count_disagreeing_with_its_attempts_is_flagged() -> None:
    case = _case(_log())
    case["then"]["execution"]["transactionLog"]["roundTrips"] = 2
    assert validate_execution(case)


def test_a_mutually_mirrored_count_disagreeing_with_the_case_is_flagged() -> None:
    case = _case(_log())
    case["then"]["roundTrips"] = 7
    assert validate_execution(case)


def test_a_read_trace_disagreeing_with_the_case_count_is_flagged() -> None:
    assert validate_execution(_standalone_read_case(_standalone_read_trace(), round_trips=2))


# --- each trigger is a positional claim ---------------------------------------


def _dependency_case(traces: list[dict[str, Any]], round_trips: int) -> dict[str, Any]:
    case = _case(_log())
    log = case["then"]["execution"]["transactionLog"]
    log["attempts"][0]["traces"] = traces
    log["attempts"][0]["roundTrips"] = round_trips
    log["roundTrips"] = round_trips
    case["then"]["roundTrips"] = round_trips
    case["then"]["statements"] = [
        {"sql": {"postgres": "insert into account(id) values (?)"}, "binds": [9]},
        {"sql": {"postgres": "select t0.id from account t0"}, "binds": []},
    ]
    return case


def _read_trace(statement: int) -> dict[str, Any]:
    return {
        "readTrace": {
            "calls": [
                {
                    "statement": statement,
                    "kind": "read",
                    "completion": {"readCompleted": {"returnedRows": 1}},
                }
            ],
            "roundTrips": 1,
        }
    }


def _dependency_batch() -> dict[str, Any]:
    return {"writeBatch": {"trigger": "read-dependency", "calls": [_write_call()], "roundTrips": 1}}


def test_a_read_dependency_batch_before_its_read_passes() -> None:
    case = _dependency_case([_dependency_batch(), _read_trace(1)], 2)
    assert not validate_execution(case)


def test_a_read_dependency_batch_after_its_read_is_flagged() -> None:
    case = _dependency_case([_read_trace(1), _dependency_batch()], 2)
    assert validate_execution(case)


def test_a_read_dependency_batch_followed_by_another_batch_is_flagged() -> None:
    finalization = {
        "writeBatch": {
            "trigger": "finalization",
            "calls": [_write_call(statement=1)],
            "roundTrips": 1,
        }
    }
    case = _dependency_case([_dependency_batch(), finalization], 2)
    assert validate_execution(case)


def test_a_finalization_batch_followed_by_a_read_is_flagged() -> None:
    finalization = {
        "writeBatch": {"trigger": "finalization", "calls": [_write_call()], "roundTrips": 1}
    }
    case = _dependency_case([finalization, _read_trace(1)], 2)
    assert validate_execution(case)


# --- the attempt history a terminal graph admits ------------------------------


def test_an_attempt_claiming_the_live_active_status_is_refused_by_both_schemas() -> None:
    assert not _valid_against("compatibility-case.schema.json", _case(_log(status="active")))
    assert not _valid_against(
        "conformance-adapter.schema.json", _run_envelope(_log(status="active"))
    )


def _attempts_case(
    statuses: list[str], max_retries: int, licence: bool | None = True
) -> dict[str, Any]:
    """A multi-attempt case whose non-final rollbacks carry *licence* as their verdict.

    ``licence=None`` authors those attempts with no failure at all.
    """
    attempts: list[dict[str, Any]] = []
    for index, status in enumerate(statuses):
        attempt: dict[str, Any] = {
            "status": status,
            "traces": [
                {
                    "writeBatch": {
                        "trigger": "finalization",
                        "calls": [_write_call(statement=index)],
                        "roundTrips": 1,
                    }
                }
            ],
            "roundTrips": 1,
        }
        if status == "rolled-back" and index != len(statuses) - 1 and licence is not None:
            attempt["failure"] = {
                "phase": "finalization",
                "retryEligible": licence,
                "databaseCall": 0,
            }
        attempts.append(attempt)
    case = _case(_log())
    case["then"]["statements"] = [_golden(f"insert {index}") for index in range(len(statuses))]
    case["then"]["roundTrips"] = len(statuses)
    case["then"]["execution"]["transactionLog"].update(
        attempts=attempts,
        roundTrips=len(statuses),
        retryPolicy={"maxRetries": max_retries, "retryOptimisticConflicts": False},
    )
    return case


def test_a_rollback_after_the_commit_is_flagged() -> None:
    assert validate_execution(_attempts_case(["rolled-back", "committed"], 1)) == []
    assert validate_execution(_attempts_case(["committed", "rolled-back"], 1))


def test_more_attempts_than_the_retry_bound_allows_are_flagged() -> None:
    assert validate_execution(_attempts_case(["rolled-back", "rolled-back"], 1)) == []
    assert validate_execution(_attempts_case(["rolled-back", "rolled-back"], 0))


def test_a_retry_after_a_failure_the_classifier_refused_is_flagged() -> None:
    assert validate_execution(_attempts_case(["rolled-back", "committed"], 1, licence=False))
    assert validate_execution(_attempts_case(["rolled-back", "rolled-back"], 1, licence=False))


def test_a_re_executed_attempt_recording_no_failure_at_all_is_flagged() -> None:
    assert validate_execution(_attempts_case(["rolled-back", "committed"], 1, licence=None))


def _with_final_verdict(
    statuses: list[str], max_retries: int, retry_eligible: bool
) -> dict[str, Any]:
    case = _attempts_case(statuses, max_retries)
    case["then"]["execution"]["transactionLog"]["attempts"][-1]["failure"] = {
        "phase": "finalization",
        "retryEligible": retry_eligible,
        "databaseCall": 0,
    }
    return case


def test_a_final_verdict_the_classifier_refused_is_terminal_at_any_count() -> None:
    assert validate_execution(_with_final_verdict(["rolled-back"], 10, False)) == []
    assert validate_execution(_with_final_verdict(["rolled-back", "rolled-back"], 1, False)) == []


def test_a_final_retry_eligible_verdict_with_budget_left_is_flagged() -> None:
    assert validate_execution(_with_final_verdict(["rolled-back", "rolled-back"], 1, True)) == []
    assert validate_execution(_with_final_verdict(["rolled-back"], 0, True)) == []
    assert validate_execution(_with_final_verdict(["rolled-back", "rolled-back"], 10, True))
    assert validate_execution(_with_final_verdict(["rolled-back"], 1, True))


def test_a_final_attempt_recording_no_failure_at_all_is_terminal_at_any_count() -> None:
    assert validate_execution(_attempts_case(["rolled-back"], 10)) == []


# --- the same relations over the adapter's observation ------------------------


def test_the_envelope_observation_is_walked_against_its_own_emissions() -> None:
    envelope = _run_envelope(_log())
    assert validate_execution_observation(envelope) == []

    envelope["emissions"] = []
    assert validate_execution_observation(envelope)


def test_an_observed_call_omitting_its_statement_beside_emissions_is_flagged() -> None:
    log = _log()
    del log["transactionLog"]["attempts"][0]["traces"][0]["writeBatch"]["calls"][0]["statement"]
    assert validate_execution_observation(_run_envelope(log))


def test_an_observed_failure_naming_an_absent_call_is_flagged() -> None:
    log = _log(
        status="rolled-back",
        failure={"phase": "finalization", "retryEligible": False, "databaseCall": 3},
    )
    assert validate_execution_observation(_run_envelope(log))


def test_an_envelope_reporting_no_provenance_has_nothing_to_walk() -> None:
    envelope = _run_envelope(_log())
    del envelope["observations"]["execution"]
    assert validate_execution_observation(envelope) == []


# --- the corpus itself --------------------------------------------------------


def test_every_authored_oracle_in_the_corpus_is_internally_consistent() -> None:
    authored = 0
    for case_path in sorted(_CASES.glob("**/*.y*ml")):
        case = read_corpus_yaml(case_path)
        if not isinstance(case, dict):  # pragma: no cover - corpus is a mapping per file
            continue
        then = case.get("then")
        if isinstance(then, dict) and "execution" in then:
            authored += 1
        assert validate_execution(case) == [], case_path.name
    assert authored == 7
