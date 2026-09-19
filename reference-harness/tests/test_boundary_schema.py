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

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from reference_harness.case import (
    Case,
    DatabaseLoginSelection,
    SubjectSelection,
    load_case,
)
from reference_harness.corpus_yaml import read_corpus_yaml
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


# --- root configuration and the four-field join (m-case-format *Root configuration*)

_OPTION_FIELDS = ("maxRetries", "concurrency", "retryOptimisticConflicts", "isolation")
_A_VALUE = {
    "maxRetries": 2,
    "concurrency": "locking",
    "retryOptimisticConflicts": True,
    "isolation": "serializable",
}


def test_schema_accepts_a_root_configuring_every_option() -> None:
    case = _valid_boundary_case()
    case["given"] = {"databaseOptions": dict(_A_VALUE)}
    assert list(_case_validator().iter_errors(case)) == []


def test_schema_accepts_a_root_on_a_read_case() -> None:
    # Root configuration belongs to every shape that opens a unit of work
    # through a root, so unlike `fault` and `sessionDefault` it is not confined
    # to the boundary shape: the corpus's own standalone-read witness carries one.
    case = read_corpus_yaml(
        _SCHEMA_PATH.parents[1]
        / "compatibility"
        / "cases"
        / "m-read-lock-019-a-standalone-read-under-a-locking-root-takes-no-lock.yaml"
    )
    assert case["given"] == {"databaseOptions": {"concurrency": "locking"}}
    assert list(_case_validator().iter_errors(case)) == []


def test_schema_rejects_a_null_root_field_and_the_retired_retries_key() -> None:
    for field in _OPTION_FIELDS:
        case = _valid_boundary_case()
        case["given"] = {"databaseOptions": {field: None}}
        assert list(_case_validator().iter_errors(case)), field
    retired = _valid_boundary_case()
    retired["given"] = {"databaseOptions": {"retries": 2}}
    assert list(_case_validator().iter_errors(retired)), (
        "Schema should reject the retired `retries` key on the root; the spelling is `maxRetries`"
    )


def test_schema_rejects_a_root_field_outside_its_type_bound_or_vocabulary() -> None:
    for field, value in (
        ("maxRetries", -1),
        ("maxRetries", "2"),
        ("concurrency", "pessimistic"),
        ("retryOptimisticConflicts", "yes"),
        ("isolation", "read-uncommitted"),
    ):
        case = _valid_boundary_case()
        case["given"] = {"databaseOptions": {field: value}}
        assert list(_case_validator().iter_errors(case)), (field, value)


def test_schema_accepts_a_join_step_naming_all_four_options() -> None:
    case = _valid_boundary_case()
    case["when"]["boundary"] = [{"action": "read"}, {"action": "join", **_A_VALUE}]
    assert list(_case_validator().iter_errors(case)) == []


def test_schema_rejects_a_null_join_option() -> None:
    for field in _OPTION_FIELDS:
        case = _valid_boundary_case()
        case["when"]["boundary"] = [{"action": "join", field: None}]
        assert list(_case_validator().iter_errors(case)), field


def test_schema_rejects_every_option_on_an_action_that_opens_no_boundary() -> None:
    """Only a `join` opens a boundary, so only a `join` may name an option for one."""
    for action in ("read", "create", "update", "terminate", "delete"):
        for field in _OPTION_FIELDS:
            case = _valid_boundary_case()
            case["when"]["boundary"] = [{"action": action, field: _A_VALUE[field]}]
            assert list(_case_validator().iter_errors(case)), (action, field)


def test_schema_rejects_the_retired_retries_key_on_a_join() -> None:
    case = _valid_boundary_case()
    case["when"]["boundary"] = [{"action": "join", "retries": 2}]
    assert list(_case_validator().iter_errors(case))


def test_schema_accepts_complete_authority_selectors_at_both_boundaries() -> None:
    for actor, authorization in (
        ({"kind": "subject", "value": " alice "}, "role-a"),
        ({"kind": "subject", "value": "alice\nadmin"}, "role-a"),
        ({"kind": "subject", "value": "DB-login:alice"}, "role-a"),
        ({"kind": "database-login"}, None),
    ):
        case = _valid_boundary_case()
        case["when"]["actorIdentity"] = actor
        if authorization is not None:
            case["when"]["databaseAuthorization"] = authorization
        step = {"action": "join", "actorIdentity": actor}
        if authorization is not None:
            step["databaseAuthorization"] = authorization
        case["when"]["boundary"] = [step]
        assert list(_case_validator().iter_errors(case)) == []


def test_schema_rejects_incomplete_or_malformed_authority_selectors() -> None:
    invalid_pairs = (
        ({"kind": "subject", "value": "alice"}, None),
        (None, "role-a"),
        ({"kind": "database-login", "value": "runner"}, None),
        ({"kind": "database-login"}, "role-a"),
        ({"kind": "subject", "value": ""}, "role-a"),
        ({"kind": "subject", "value": "db-login:runner"}, "role-a"),
        ({"kind": "service", "value": "alice"}, "role-a"),
    )
    for actor, authorization in invalid_pairs:
        case = _valid_boundary_case()
        if actor is not None:
            case["when"]["actorIdentity"] = actor
        if authorization is not None:
            case["when"]["databaseAuthorization"] = authorization
        assert list(_case_validator().iter_errors(case)), (actor, authorization)
    for selection in (
        {"actorIdentity": None},
        {"databaseAuthorization": None},
        {
            "actorIdentity": {"kind": "database-login"},
            "databaseAuthorization": None,
        },
    ):
        case = _valid_boundary_case()
        case["when"].update(selection)
        assert list(_case_validator().iter_errors(case)), selection


def test_schema_rejects_authority_selectors_on_non_join_actions() -> None:
    for action in ("read", "create", "update", "terminate", "delete"):
        case = _valid_boundary_case()
        case["when"]["boundary"] = [
            {
                "action": action,
                "actorIdentity": {"kind": "subject", "value": "alice"},
                "databaseAuthorization": "role-a",
            }
        ]
        assert list(_case_validator().iter_errors(case)), action


def test_schema_rejects_outer_authority_selectors_on_an_unrelated_shape() -> None:
    case = read_corpus_yaml(
        _SCHEMA_PATH.parents[1]
        / "compatibility"
        / "cases"
        / "m-core-001-scalar-types-roundtrip.yaml"
    )
    case["when"]["actorIdentity"] = {"kind": "database-login"}
    assert list(_case_validator().iter_errors(case))


def test_authority_cases_decode_to_closed_reader_values() -> None:
    compatibility = _SCHEMA_PATH.parents[1] / "compatibility"
    cases = compatibility / "cases"
    subject_case = load_case(
        compatibility,
        cases / "m-execution-authority-001-equal-subject-authority-joins.yaml",
    )
    assert subject_case.actor_selection == SubjectSelection("alice", "role-a")
    assert subject_case.boundary_action_actor_selection(1) is None
    assert subject_case.boundary_action_actor_selection(2) == SubjectSelection("alice", "role-a")

    login_case = load_case(
        compatibility,
        cases / "m-execution-authority-005-equal-login-authority-joins.yaml",
    )
    assert login_case.actor_selection == DatabaseLoginSelection()
    assert login_case.boundary_action_actor_selection(1) == DatabaseLoginSelection()


@pytest.mark.parametrize(
    "selection",
    [
        {"actorIdentity": None},
        {"databaseAuthorization": None},
        {"actorIdentity": {"kind": "subject", "value": "alice"}},
        {
            "actorIdentity": {"kind": "database-login"},
            "databaseAuthorization": None,
        },
    ],
)
def test_reference_reader_rejects_malformed_authority_combinations(
    selection: dict[str, object],
) -> None:
    compatibility = _SCHEMA_PATH.parents[1] / "compatibility"
    canonical = load_case(
        compatibility,
        compatibility / "cases" / "m-execution-authority-001-equal-subject-authority-joins.yaml",
    )
    raw = copy.deepcopy(canonical.raw)
    raw["when"] = {"boundary": raw["when"]["boundary"], **selection}
    malformed = Case(path=canonical.path, raw=raw, model=canonical.model)
    with pytest.raises(ValueError, match=r"actorIdentity|databaseAuthorization"):
        _ = malformed.actor_selection
