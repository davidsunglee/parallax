"""DB-free fidelity tests for the grouped compatibility-case schema (COR-23).

Pinned fixture documents against the new ``compatibility-case.schema.json``: a
minimal well-formed document for each of the eight shapes is ACCEPTED, and a
curated set of malformed documents — the legacy flat layout, a mislabeled
``shape``, a plain-string ``sql`` at a golden location, an empty ``sql`` map, an
extra key inside a closed group, and ``binds`` authored outside a statement
entry — is REJECTED.

This fixture set is the regression gate for the grouped layout; Phase 4 reuses it
verbatim as the TypeScript validator's fidelity suite, so the accept/reject
corpus stays in lockstep across the two harnesses.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "core" / "schemas" / "compatibility-case.schema.json"
)


def _validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(_SCHEMA_PATH.read_text(encoding="utf-8")))


def _is_valid(doc: dict[str, Any]) -> bool:
    return next(_validator().iter_errors(doc), None) is None


# --- minimal well-formed documents, one per shape --------------------------


def _read_case() -> dict[str, Any]:
    return {
        "model": "models/orders.yaml",
        "tags": ["m-agg"],
        "shape": "read",
        "when": {"operation": {"all": {}}},
        "then": {
            "statements": [{"sql": {"postgres": "select t0.id from orders t0"}, "binds": []}],
            "rows": [{"id": 1}],
            "roundTrips": 1,
        },
    }


def _write_sequence_case() -> dict[str, Any]:
    return {
        "model": "models/balance.yaml",
        "tags": ["m-audit-write"],
        "shape": "writeSequence",
        "when": {
            "writeSequence": [
                {"mutation": "insert", "entity": "Balance", "rows": [{"id": 1, "acctNum": "A"}]}
            ]
        },
        "then": {
            "statements": [
                {"sql": {"postgres": "insert into balance(bal_id) values (?)"}, "binds": [1]}
            ],
            "tableState": {"balance": [{"bal_id": 1}]},
        },
    }


def _scenario_case() -> dict[str, Any]:
    return {
        "model": "models/account.yaml",
        "tags": ["m-unit-work"],
        "shape": "scenario",
        "when": {
            "scenario": [
                {
                    "find": {"eq": {"attr": "Account.id", "value": 7}},
                    "roundTrips": 1,
                    "statements": [
                        {
                            "sql": {"postgres": "select t0.id from account t0 where t0.id = ?"},
                            "binds": [7],
                        }
                    ],
                    "expectRows": [{"id": 7}],
                }
            ]
        },
        "then": {"roundTrips": 1},
    }


def _conflict_case() -> dict[str, Any]:
    return {
        "model": "models/account.yaml",
        "tags": ["m-opt-lock"],
        "shape": "conflict",
        "given": {"apply": [{"sql": "update account set version = 2 where id = 2"}]},
        "when": {"uow": {"concurrency": "optimistic"}, "write": {"id": 2, "observedVersion": 1}},
        "then": {
            "statements": [
                {
                    "sql": {
                        "postgres": "update account set balance = ? where id = ? and version = ?"
                    },
                    "binds": [250.0, 2, 1],
                }
            ],
            "affectedRows": 0,
            "tableState": {"account": [{"id": 2, "version": 2}]},
        },
    }


def _coherence_case() -> dict[str, Any]:
    step_sql = [{"sql": {"postgres": "select t0.id from account t0 where t0.id = ?"}, "binds": [2]}]
    return {
        "model": "models/account.yaml",
        "tags": ["m-coherence"],
        "shape": "coherence",
        "when": {
            "coherence": [
                {"node": "B", "kind": "read", "statements": step_sql, "observeRows": [{"id": 2}]},
                {
                    "node": "A",
                    "kind": "write",
                    "statements": [
                        {
                            "sql": {"postgres": "update account set balance = ? where id = ?"},
                            "binds": [9, 2],
                        }
                    ],
                },
            ]
        },
    }


def _error_case() -> dict[str, Any]:
    stmt = {"sql": {"postgres": "insert into widget(id) values (?)"}, "binds": [1]}
    return {
        "model": "models/error-cases.yaml",
        "tags": ["m-db-error"],
        "shape": "error",
        "then": {
            "statements": [stmt, stmt],
            "errorClass": "uniqueViolation",
            "nativeCode": {"postgres": "23505", "mariadb": 1062},
        },
    }


def _concurrency_success_case() -> dict[str, Any]:
    return {
        "model": "models/account.yaml",
        "tags": ["m-read-lock"],
        "shape": "concurrencySuccess",
        "given": {"fixtures": True},
        "when": {
            "concurrency": {
                "rounds": [
                    {
                        "A": {
                            "kind": "read",
                            "statements": [
                                {
                                    "sql": {
                                        "postgres": "select t0.id from account t0 where t0.id = ?"
                                    },
                                    "binds": [2],
                                }
                            ],
                            "expectRows": [{"id": 2}],
                        }
                    }
                ]
            }
        },
    }


def _conflict_retry_case() -> dict[str, Any]:
    """The conflict RETRY form (`when.attempts`): each attempt asserts `affectedRows`.

    Distinct from `_conflict_case` (the single-attempt `when.write` + `then.affectedRows`
    form); this pins the retry attempts def, whose per-attempt affected-row count carries
    the assertion-group name `affectedRows`, NOT the legacy `expectedAffectedRows`.
    """
    return {
        "model": "models/account.yaml",
        "tags": ["m-opt-lock"],
        "shape": "conflict",
        "given": {"apply": [{"sql": "update account set version = 2 where id = 2"}]},
        "when": {
            "uow": {"concurrency": "optimistic"},
            "attempts": [
                {
                    "statements": [
                        {
                            "sql": {
                                "postgres": "update account set balance = ? "
                                "where id = ? and version = ?"
                            },
                            "binds": [250.0, 2, 1],
                        }
                    ],
                    "write": {"id": 2, "balance": 250.0, "observedVersion": 1},
                    "affectedRows": 0,
                },
                {
                    "statements": [
                        {
                            "sql": {
                                "postgres": "update account set balance = ? "
                                "where id = ? and version = ?"
                            },
                            "binds": [250.0, 2, 2],
                        }
                    ],
                    "write": {"id": 2, "balance": 250.0, "observedVersion": 2},
                    "affectedRows": 1,
                },
            ],
        },
        "then": {"tableState": {"account": [{"id": 2, "version": 3}]}},
    }


def _boundary_case() -> dict[str, Any]:
    return {
        "model": "models/account.yaml",
        "tags": ["m-auto-retry"],
        "shape": "boundary",
        "lane": "api-conformance",
        "given": {"fault": "serialization-failure"},
        "when": {
            "uow": {"concurrency": "optimistic"},
            "boundary": [{"action": "read"}, {"action": "update"}],
        },
        "then": {"outcome": "committed"},
    }


VALID_CASES = {
    "read": _read_case,
    "writeSequence": _write_sequence_case,
    "scenario": _scenario_case,
    "conflict": _conflict_case,
    "conflict-retry": _conflict_retry_case,
    "coherence": _coherence_case,
    "error": _error_case,
    "concurrencySuccess": _concurrency_success_case,
    "boundary": _boundary_case,
}


@pytest.mark.parametrize("shape", sorted(VALID_CASES))
def test_schema_accepts_minimal_case_for_every_shape(shape: str) -> None:
    doc = VALID_CASES[shape]()
    errors = list(_validator().iter_errors(doc))
    assert errors == [], f"{shape} case should validate, got: {[e.message for e in errors]}"


# --- rejected malformed documents ------------------------------------------


def _legacy_layout() -> dict[str, Any]:
    """The pre-migration flat layout: no shape, positional goldenSql/binds."""
    return {
        "model": "models/orders.yaml",
        "tags": ["m-agg"],
        "operation": {"all": {}},
        "goldenSql": {"postgres": "select t0.id from orders t0"},
        "binds": [],
        "expectedRows": [{"id": 1}],
    }


def _mislabeled_shape() -> dict[str, Any]:
    """A well-formed writeSequence document mislabeled as a read."""
    doc = _write_sequence_case()
    doc["shape"] = "read"
    return doc


def _string_sql_at_golden_location() -> dict[str, Any]:
    """A golden statement whose sql is a plain string instead of a dialect map."""
    doc = _read_case()
    doc["then"]["statements"][0]["sql"] = "select t0.id from orders t0"
    return doc


def _empty_sql_map() -> dict[str, Any]:
    """A golden statement whose sql map declares no dialect."""
    doc = _read_case()
    doc["then"]["statements"][0]["sql"] = {}
    return doc


def _extra_key_in_closed_group() -> dict[str, Any]:
    """A stray legacy key inside the closed `then` group."""
    doc = _read_case()
    doc["then"]["expectedRows"] = [{"id": 1}]
    return doc


def _binds_outside_statement_entry() -> dict[str, Any]:
    """`binds` authored at the root instead of inside a statement entry."""
    doc = _read_case()
    doc["binds"] = [1]
    return doc


def _attempt_legacy_affected_rows() -> dict[str, Any]:
    """A retry attempt carrying the legacy `expectedAffectedRows` name (finding 1).

    The attempts def requires `affectedRows` and is closed, so the legacy
    `expected*` spelling is rejected two ways: `affectedRows` is now missing and
    `expectedAffectedRows` is an extra key. No legacy executable vocabulary may
    validate inside a migrated case body.
    """
    doc = _conflict_retry_case()
    attempt = doc["when"]["attempts"][0]
    attempt["expectedAffectedRows"] = attempt.pop("affectedRows")
    return doc


def _cross_shape_when_member() -> dict[str, Any]:
    """A read case carrying a stray cross-shape `when.boundary` block (finding 2).

    The read branch now constrains `when` to only that shape's members
    (`operation` / `uow` / `equivalentEncodings`), so a mislabeled/mixed document
    that also carries an unrelated action member fails its shape branch and no
    other branch matches — the `oneOf` rejects it.
    """
    doc = _read_case()
    doc["when"]["boundary"] = [{"action": "read"}]
    return doc


REJECTED_CASES = {
    "legacy-layout": _legacy_layout,
    "mislabeled-shape": _mislabeled_shape,
    "string-sql-at-golden-location": _string_sql_at_golden_location,
    "empty-sql-map": _empty_sql_map,
    "extra-key-in-closed-group": _extra_key_in_closed_group,
    "binds-outside-statement-entry": _binds_outside_statement_entry,
    "attempt-legacy-affected-rows": _attempt_legacy_affected_rows,
    "cross-shape-when-member": _cross_shape_when_member,
}


@pytest.mark.parametrize("label", sorted(REJECTED_CASES))
def test_schema_rejects_malformed_case(label: str) -> None:
    doc = REJECTED_CASES[label]()
    assert not _is_valid(doc), f"{label} document should be rejected by the schema"
