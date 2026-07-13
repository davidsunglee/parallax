"""Unit tests for the `m-db-error` error-classification core (DB-free).

The pure category map + call-site predicates are pinned here. The DB-coupled
parts (extracting the native code from a real driver exception, and triggering
the actual errors) are exercised end-to-end against real Postgres + MariaDB by
the compatibility suite's `error` cases.
"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from reference_harness import errors
from reference_harness.case import Case, Model, load_model
from reference_harness.case_runner import CaseFailure, _assert_schema
from reference_harness.ddl_builder import ddl_for
from reference_harness.providers.mariadb import MariaDbProvider
from reference_harness.providers.postgres import PostgresProvider
from reference_harness.schemas import build_registry, load_schemas


def test_postgres_codes_map_to_categories() -> None:
    assert errors.classify("postgres", "23505") == errors.UNIQUE_VIOLATION
    assert errors.classify("postgres", "40P01") == errors.DEADLOCK
    # A serialization failure is retriable like a deadlock (folded in).
    assert errors.classify("postgres", "40001") == errors.DEADLOCK
    assert errors.classify("postgres", "55P03") == errors.LOCK_WAIT_TIMEOUT


def test_mariadb_errnos_map_to_categories() -> None:
    assert errors.classify("mariadb", 1062) == errors.UNIQUE_VIOLATION
    assert errors.classify("mariadb", 1213) == errors.DEADLOCK
    assert errors.classify("mariadb", 1205) == errors.LOCK_WAIT_TIMEOUT


def test_same_sqlstate_means_different_things_per_dialect() -> None:
    # SQLSTATE 40001 is serialization-failure on PG but the deadlock state on
    # MariaDB (errno 1213). Classification MUST be per-dialect: PG keys on the
    # SQLSTATE string, MariaDB on the vendor errno. A naive cross-dialect match
    # on "40001" would misclassify -- this is why the code source is a dialect
    # decision. Both land on DEADLOCK here, but via different inputs.
    assert errors.classify("postgres", "40001") == errors.DEADLOCK
    assert errors.classify("mariadb", 1213) == errors.DEADLOCK


def test_unknown_code_is_unknown() -> None:
    assert errors.classify("postgres", "99999") == errors.UNKNOWN
    assert errors.classify("postgres", None) == errors.UNKNOWN
    assert errors.classify("mariadb", 9999) == errors.UNKNOWN
    assert errors.classify("mariadb", None) == errors.UNKNOWN


def test_predicates_partition_by_category() -> None:
    assert errors.violates_unique_index(errors.UNIQUE_VIOLATION)
    assert not errors.is_retriable(errors.UNIQUE_VIOLATION)
    assert not errors.is_timed_out(errors.UNIQUE_VIOLATION)

    assert errors.is_retriable(errors.DEADLOCK)
    assert not errors.violates_unique_index(errors.DEADLOCK)
    assert not errors.is_timed_out(errors.DEADLOCK)

    assert errors.is_timed_out(errors.LOCK_WAIT_TIMEOUT)
    assert not errors.is_retriable(errors.LOCK_WAIT_TIMEOUT)


def test_predicate_for_names_the_true_predicate() -> None:
    assert errors.predicate_for(errors.DEADLOCK) == "is_retriable"
    assert errors.predicate_for(errors.UNIQUE_VIOLATION) == "violates_unique_index"
    assert errors.predicate_for(errors.LOCK_WAIT_TIMEOUT) == "is_timed_out"
    assert errors.predicate_for(errors.UNKNOWN) is None


class _FakePgError(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__("fake")
        self.sqlstate = sqlstate


class _FakeMariaError(Exception):
    def __init__(self, errno: int) -> None:
        super().__init__(errno, "fake")  # pymysql packs (errno, msg) into args


def test_postgres_provider_classifies_via_sqlstate() -> None:
    # classify_error is a pure method over the exception; no connection needed,
    # so call it on an uninitialized instance.
    provider = PostgresProvider.__new__(PostgresProvider)
    assert provider.dialect == "postgres"
    assert provider.native_error_code(_FakePgError("23505")) == "23505"
    assert provider.classify_error(_FakePgError("23505")) == errors.UNIQUE_VIOLATION
    assert provider.classify_error(_FakePgError("40P01")) == errors.DEADLOCK
    assert provider.classify_error(_FakePgError("55P03")) == errors.LOCK_WAIT_TIMEOUT
    assert provider.classify_error(Exception("no sqlstate")) == errors.UNKNOWN


def test_mariadb_provider_classifies_via_errno() -> None:
    provider = MariaDbProvider.__new__(MariaDbProvider)
    assert provider.dialect == "mariadb"
    assert provider.native_error_code(_FakeMariaError(1062)) == 1062
    assert provider.classify_error(_FakeMariaError(1062)) == errors.UNIQUE_VIOLATION
    assert provider.classify_error(_FakeMariaError(1213)) == errors.DEADLOCK
    assert provider.classify_error(_FakeMariaError(1205)) == errors.LOCK_WAIT_TIMEOUT
    assert provider.classify_error(Exception("non-integer")) == errors.UNKNOWN


def _error_case(raw: dict) -> Case:
    descriptor = {"entity": {"name": "W", "table": "w", "attributes": []}}
    model = Model(path=Path("m.yaml"), descriptor=descriptor)
    return Case(path=Path("m-db-error-001-x.yaml"), raw=raw, model=model)


_SHARE_LOCK_READ = {
    "postgres": (
        "select t0.id, t0.owner, t0.balance, t0.version "
        "from account t0 where t0.id = ? for share of t0"
    ),
    "mariadb": (
        "select t0.id, t0.owner, t0.balance, t0.version "
        "from account t0 where t0.id = ? lock in share mode"
    ),
}

_ACCOUNT_UPDATE = {
    "postgres": "update account set balance = ? where id = ?",
    "mariadb": "update account set balance = ? where id = ?",
}


def _node(sql: dict, binds: list) -> dict:
    """One concurrency node step carrying a single {sql, binds} golden entry."""
    return {"statements": [{"sql": sql, "binds": binds}]}


def test_case_recognizes_single_connection_error_shape() -> None:
    case = _error_case(
        {
            "shape": "error",
            "then": {
                "errorClass": "uniqueViolation",
                "nativeCode": {"postgres": "23505", "mariadb": 1062},
                "statements": [
                    {"sql": {"postgres": "insert into w (id) values (?)"}, "binds": [1]},
                    {"sql": {"postgres": "insert into w (id) values (?)"}, "binds": [1]},
                ],
            },
        }
    )
    assert case.is_error
    assert not case.is_conflict and not case.is_coherence and not case.is_scenario
    assert case.error_class == "uniqueViolation"
    assert case.expected_native_code == {"postgres": "23505", "mariadb": 1062}
    assert case.concurrency is None


def test_case_recognizes_two_connection_error_shape() -> None:
    rounds = [{"A": {"statements": [{"sql": {"postgres": "x"}, "binds": [1]}]}}]
    case = _error_case(
        {
            "shape": "error",
            "then": {
                "errorClass": "deadlock",
                "nativeCode": {"postgres": "40P01", "mariadb": 1213},
            },
            "when": {"concurrency": {"rounds": rounds}},
        }
    )
    assert case.is_error
    assert case.error_class == "deadlock"
    assert case.concurrency == {"rounds": rounds}


_REPO_ROOT = Path(__file__).resolve().parents[2]

_SCHEMA_PATH = _REPO_ROOT / "core" / "schemas" / "compatibility-case.schema.json"

COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"

_REGISTRY = build_registry(load_schemas(_REPO_ROOT / "core"))


def _case_validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(_SCHEMA_PATH.read_text()), registry=_REGISTRY)


def test_schema_accepts_single_connection_error_case() -> None:
    case = {
        "model": "models/error-cases.yaml",
        "shape": "error",
        "tags": ["m-db-error", "error-classification", "uniqueViolation"],
        "then": {
            "errorClass": "uniqueViolation",
            "nativeCode": {"postgres": "23505", "mariadb": 1062},
            "statements": [
                {
                    "sql": {"postgres": "insert into widget (id, label) values (?, ?)"},
                    "binds": [1, "a"],
                },
                {
                    "sql": {"postgres": "insert into widget (id, label) values (?, ?)"},
                    "binds": [1, "b"],
                },
            ],
        },
    }
    assert list(_case_validator().iter_errors(case)) == []


def test_schema_accepts_two_connection_error_case() -> None:
    def _gauge(binds: list) -> dict:
        return {
            "statements": [
                {"sql": {"postgres": "update gauge set v = ? where id = ?"}, "binds": binds}
            ]
        }

    case = {
        "model": "models/error-cases.yaml",
        "shape": "error",
        "given": {"fixtures": True},
        "tags": ["m-db-error", "error-classification", "deadlock"],
        "when": {
            "concurrency": {
                "rounds": [
                    {"A": _gauge([10, 1]), "B": _gauge([20, 2])},
                    {"A": _gauge([11, 2]), "B": _gauge([21, 1])},
                ]
            }
        },
        "then": {
            "errorClass": "deadlock",
            "nativeCode": {"postgres": "40P01", "mariadb": 1213},
        },
    }
    assert list(_case_validator().iter_errors(case)) == []


def test_case_recognizes_read_lock_concurrency_error_shape() -> None:
    # m-read-lock-006: a behavioral read-lock case whose round-1 A step is a locking SELECT
    # (not a write) that HOLDS the shared lock while B's round-2 UPDATE blocks and
    # times out. The runner runs A's round-1 statement verbatim and is agnostic
    # about statement kind, so a round-1 read is a first-class concurrency step.
    # This pins that assumption against a future regression that treats round-1
    # statements as writes.
    case = _error_case(
        {
            "shape": "error",
            "then": {
                "errorClass": "lockWaitTimeout",
                "nativeCode": {"postgres": "55P03", "mariadb": 1205},
            },
            "when": {
                "concurrency": {
                    "rounds": [
                        {"A": _node(_SHARE_LOCK_READ, [2])},
                        {"B": _node(_ACCOUNT_UPDATE, [999.00, 2])},
                    ]
                }
            },
        }
    )
    assert case.is_error
    assert case.error_class == "lockWaitTimeout"
    assert case.concurrency is not None
    rounds = case.concurrency["rounds"]
    # Round 1 is a locking read on A; round 2 is a write on B.
    assert "for share of t0" in rounds[0]["A"]["statements"][0]["sql"]["postgres"]
    assert rounds[1]["B"]["statements"][0]["sql"]["postgres"].startswith("update account")


def test_schema_accepts_read_lock_concurrency_error_case() -> None:
    # The m-read-lock-006 shape validates against the existing error + concurrency branch as-is:
    # a round-1 A locking SELECT plus a round-2 B UPDATE needs no schema change.
    case = {
        "model": "models/account.yaml",
        "shape": "error",
        "given": {"fixtures": True},
        "tags": [
            "m-read-lock",
            "m-db-error",
            "read-lock",
            "concurrency",
            "error-classification",
            "lockWaitTimeout",
        ],
        "when": {
            "concurrency": {
                "rounds": [
                    {"A": _node(_SHARE_LOCK_READ, [2])},
                    {"B": _node(_ACCOUNT_UPDATE, [999.00, 2])},
                ]
            }
        },
        "then": {
            "errorClass": "lockWaitTimeout",
            "nativeCode": {"postgres": "55P03", "mariadb": 1205},
        },
    }
    assert list(_case_validator().iter_errors(case)) == []


def test_schema_rejects_error_case_without_native_code() -> None:
    case = {
        "model": "models/error-cases.yaml",
        "shape": "error",
        "tags": ["m-db-error", "uniqueViolation"],
        "then": {
            "errorClass": "uniqueViolation",
            "statements": [{"sql": {"postgres": "insert into tag(id) values (?)"}, "binds": [1]}],
        },
    }
    assert list(_case_validator().iter_errors(case)) != []


def _load_error_model() -> Model:
    return load_model(COMPATIBILITY_ROOT, "models/error-cases.yaml")


def test_error_model_builds_ddl_on_both_dialects() -> None:
    model = _load_error_model()
    names = {e.name for e in model.entities}
    assert {"Widget", "Tag", "Gauge"} <= names
    for dialect in ("postgres", "mariadb"):
        ddl = "\n".join(ddl_for(model, dialect))
        assert "create table widget" in ddl
        assert "create table tag" in ddl
        assert "unique (name)" in ddl  # Tag.name unique index (Task 5)


def test_gauge_seeded_with_two_lockable_rows() -> None:
    model = _load_error_model()
    gauge = model.entity("Gauge")
    assert len(gauge.rows) == 2


# --- trigger-presence tests (Fix A: schema, Fix B: runner) -------------------


def test_schema_rejects_triggerless_error_case() -> None:
    """An error case with no then.statements and no when.concurrency MUST fail validation."""
    case = {
        "model": "models/error-cases.yaml",
        "shape": "error",
        "tags": ["m-db-error", "error-classification", "uniqueViolation"],
        "then": {
            "errorClass": "uniqueViolation",
            "nativeCode": {"postgres": "23505", "mariadb": 1062},
        },
    }
    errors_found = list(_case_validator().iter_errors(case))
    assert errors_found, (
        "Schema should reject an error case with no then.statements or when.concurrency trigger"
    )


def test_schema_rejects_empty_round_concurrency_case() -> None:
    """A concurrency case with an empty round ({}) MUST fail schema validation."""
    case = {
        "model": "models/error-cases.yaml",
        "shape": "error",
        "tags": ["m-db-error", "error-classification", "deadlock"],
        "when": {"concurrency": {"rounds": [{}]}},
        "then": {
            "errorClass": "deadlock",
            "nativeCode": {"postgres": "40P01", "mariadb": 1213},
        },
    }
    errors_found = list(_case_validator().iter_errors(case))
    assert errors_found, (
        "Schema should reject a concurrency case with an empty round (no A or B node)"
    )


def test_runner_assert_schema_raises_for_triggerless_error_case() -> None:
    """_assert_schema must raise CaseFailure for an error case with no trigger."""
    case = _error_case(
        {
            "shape": "error",
            "then": {
                "errorClass": "uniqueViolation",
                "nativeCode": {"postgres": "23505", "mariadb": 1062},
            },
        }
    )
    import pytest

    with pytest.raises(CaseFailure, match="no trigger"):
        _assert_schema(case)
