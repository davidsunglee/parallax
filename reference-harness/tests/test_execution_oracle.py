"""DB-free tests for the `then.execution` oracle and its adapter mirror.

The oracle (`m-execution-log`) is graded by each language implementation, not by
this harness, so what the harness owes it is that an authored oracle — and the
observation an adapter mirrors back — cannot be internally impossible. Two
layers carry that:

* the schemas close the algebra a call, an attempt, and a case shape admit, on
  BOTH sides of the mirror;
* :mod:`reference_harness.execution_validate` closes the relations no JSON
  Schema states — statement and call indexes that name something, round-trip
  counts that agree at every level and with ``then.roundTrips``, and the
  read-dependency batch's position in front of the read it enabled.

The whole corpus is asserted consistent under both.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from reference_harness.corpus_yaml import read_corpus_yaml
from reference_harness.execution_validate import validate_execution
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


def test_an_active_attempt_carrying_a_failure_is_refused() -> None:
    case = _case(_log(status="active", failure={"phase": "body", "retryEligible": True}))
    assert not _valid_against("compatibility-case.schema.json", case)


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
        "when": {"targetEntity": "Account", "operation": {"all": {}}},
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


# --- the read-dependency batch stands in front of the read it enabled --------


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
