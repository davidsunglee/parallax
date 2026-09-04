"""DB-free schema tests for the boundary-case api-conformance-lane invariant.

A boundary case (`m-auto-retry` / `m-opt-lock` bounded automatic retry) is a
runtime-loop observable the single-connection harness cannot provoke, so it lives
on the `api-conformance` lane and is satisfied by each language's API Conformance
Suite. The
compatibility-case schema ENFORCES that invariant: a boundary case must pin
`lane: api-conformance` and carry no golden SQL. Without the pin, a boundary case
that forgets `lane` would default to `harness`, then hit compile/run paths not
shaped for it (the reference harness would bypass its early skip).
"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from reference_harness.schemas import build_registry, load_schemas

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "core" / "schemas" / "compatibility-case.schema.json"
)
_REGISTRY = build_registry(load_schemas(_SCHEMA_PATH.parents[1]))


def _case_validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(_SCHEMA_PATH.read_text()), registry=_REGISTRY)


def _valid_boundary_case() -> dict:
    """A minimal well-formed boundary case (models the `m-unit-work-004` abort case)."""
    return {
        "model": "models/account.yaml",
        "tags": ["m-unit-work", "abort", "slice-example-1"],
        "shape": "boundary",
        "lane": "api-conformance",
        "when": {
            "boundary": [
                {"action": "read", "note": "observe the row"},
                {"action": "update", "note": "buffer/flush a write"},
            ],
        },
        "then": {"outcome": "aborted"},
    }


def test_schema_accepts_boundary_case_on_the_api_conformance_lane() -> None:
    assert list(_case_validator().iter_errors(_valid_boundary_case())) == []


def test_schema_rejects_boundary_case_missing_lane() -> None:
    """Omitting `lane` must fail — it would otherwise default to `harness`."""
    case = _valid_boundary_case()
    del case["lane"]
    assert list(_case_validator().iter_errors(case)), (
        "Schema should reject a boundary case that omits lane (it would default to harness)"
    )


def test_schema_rejects_boundary_case_on_the_harness_lane() -> None:
    """Explicitly mis-setting `lane: harness` must fail — the lane is pinned."""
    case = _valid_boundary_case()
    case["lane"] = "harness"
    assert list(_case_validator().iter_errors(case)), (
        "Schema should reject a boundary case whose lane is not api-conformance"
    )


def test_schema_rejects_boundary_case_with_golden_sql() -> None:
    """A boundary case carries no golden SQL — the DML stays per-language."""
    case = _valid_boundary_case()
    case["then"]["statements"] = [
        {"sql": {"postgres": "update account set balance = ? where id = ?"}, "binds": [999.0, 2]}
    ]
    assert list(_case_validator().iter_errors(case)), (
        "Schema should reject a boundary case that carries golden SQL"
    )


def test_schema_accepts_a_join_step_naming_its_own_isolation() -> None:
    case = _valid_boundary_case()
    case["when"]["boundary"] = [
        {"action": "read"},
        {"action": "join", "isolation": "serializable"},
    ]
    assert list(_case_validator().iter_errors(case)) == []


def test_schema_rejects_isolation_on_an_action_that_opens_no_boundary() -> None:
    """Only a `join` opens a boundary, so only a `join` may name a level for one."""
    case = _valid_boundary_case()
    case["when"]["boundary"] = [{"action": "read", "isolation": "serializable"}]
    assert list(_case_validator().iter_errors(case)), (
        "Schema should reject an isolation on an action that opens no boundary"
    )


def test_schema_accepts_a_dialect_keyed_outcome() -> None:
    case = _valid_boundary_case()
    case["then"]["outcome"] = {"postgres": "committed", "mariadb": "connection-refused"}
    assert list(_case_validator().iter_errors(case)) == []


def test_schema_rejects_an_outcome_map_keyed_by_an_unknown_dialect() -> None:
    case = _valid_boundary_case()
    case["then"]["outcome"] = {"sqlite": "committed"}
    assert list(_case_validator().iter_errors(case)), (
        "Schema should reject an outcome keyed by a dialect the corpus does not name"
    )


def test_schema_rejects_an_outcome_map_value_outside_the_vocabulary() -> None:
    """A keyed map's values are the SAME closed outcome vocabulary a bare one is."""
    case = _valid_boundary_case()
    case["then"]["outcome"] = {"postgres": "rolled-back"}
    assert list(_case_validator().iter_errors(case)), (
        "Schema should reject an outcome map value outside the closed vocabulary"
    )


def test_schema_accepts_a_session_default_on_a_boundary_case() -> None:
    case = _valid_boundary_case()
    case["given"] = {"sessionDefault": "read-uncommitted"}
    assert list(_case_validator().iter_errors(case)) == []


def test_schema_rejects_a_session_default_inside_the_portable_vocabulary() -> None:
    """The field names the default an adapter must REFUSE, so a portable level is
    not a value it can carry."""
    case = _valid_boundary_case()
    case["given"] = {"sessionDefault": "repeatable-read"}
    assert list(_case_validator().iter_errors(case)), (
        "Schema should reject a sessionDefault naming a portable Isolation Level"
    )


def test_schema_admits_zero_round_trips_only_for_a_boundary_that_never_opened() -> None:
    unopened = _valid_boundary_case()
    unopened["given"] = {"fault": "isolation-setup-failure"}
    unopened["then"] = {"outcome": "boundary-failed", "roundTrips": 0}
    assert list(_case_validator().iter_errors(unopened)) == []

    opened = _valid_boundary_case()
    opened["then"]["roundTrips"] = 0
    assert list(_case_validator().iter_errors(opened)), (
        "Schema should reject zero round trips for a boundary that did open"
    )


def test_schema_admits_zero_round_trips_for_a_dialect_keyed_unopened_boundary() -> None:
    """The relaxation follows the OUTCOME, not the form it is stated in: a case
    whose every named dialect fails to open costs zero on each of them."""
    for outcome in (
        {"mariadb": "boundary-failed"},
        {"postgres": "boundary-failed", "mariadb": "boundary-failed"},
    ):
        case = _valid_boundary_case()
        case["given"] = {"fault": "isolation-setup-failure"}
        case["then"] = {"outcome": outcome, "roundTrips": 0}
        assert list(_case_validator().iter_errors(case)) == [], outcome


def test_schema_rejects_zero_round_trips_where_one_dialect_opened_its_boundary() -> None:
    """One count answers for every dialect the case claims anything about, so a
    map naming a dialect whose boundary DID open states a case costing more."""
    case = _valid_boundary_case()
    case["then"] = {
        "outcome": {"postgres": "committed", "mariadb": "boundary-failed"},
        "roundTrips": 0,
    }
    assert list(_case_validator().iter_errors(case)), (
        "Schema should reject zero round trips where a named dialect's boundary opened"
    )
