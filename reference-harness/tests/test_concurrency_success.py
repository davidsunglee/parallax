"""Unit tests for the `m-read-lock` behavioral concurrency-SUCCESS shape (DB-free).

The shape recognition, the `then.errorClass`-absent discriminator that keeps it
distinct from an error/concurrency case, the explicit per-step `kind`
discriminator (`read` / `write`) with its structural `expectRows` if/then, and the
runner's minimal `kind`-based structural guard are pinned here. The DB-coupled part
-- running two held sessions and asserting NO error + each read's `expectRows` on
its held session -- is exercised end-to-end against real Postgres + MariaDB by the
compatibility suite's `m-read-lock-007` / `m-read-lock-008` cases via `test_compatibility.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from reference_harness.case import Case, Model
from reference_harness.case_runner import CaseFailure, _assert_schema
from reference_harness.schemas import build_registry, load_schemas

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_PATH = _REPO_ROOT / "core" / "schemas" / "compatibility-case.schema.json"
_REGISTRY = build_registry(load_schemas(_REPO_ROOT / "core"))

_SHARED_READ = {
    "postgres": (
        "select t0.id, t0.owner, t0.balance, t0.version "
        "from account t0 where t0.id = ? for share of t0"
    ),
    "mariadb": (
        "select t0.id, t0.owner, t0.balance, t0.version "
        "from account t0 where t0.id = ? lock in share mode"
    ),
}

_UPDATE = {
    "postgres": "update account set balance = ? where id = ?",
    "mariadb": "update account set balance = ? where id = ?",
}


def _entry(sql: dict[str, str], binds: list[Any]) -> dict[str, Any]:
    """A single golden statement entry ({sql, binds}) for a concurrency step."""
    return {"sql": sql, "binds": binds}


def _case_validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(_SCHEMA_PATH.read_text()), registry=_REGISTRY)


def _concurrency_case(raw: dict) -> Case:
    descriptor = {"entity": {"name": "Account", "table": "account", "attributes": []}}
    model = Model(path=Path("account.yaml"), descriptor=descriptor)
    return Case(path=Path("m-read-lock-007-x.yaml"), raw=raw, model=model)


# --- shape recognition (the errorClass-absent discriminator) -----------------


def test_case_recognizes_concurrency_success_shape() -> None:
    # A concurrency choreography with NO errorClass is the concurrency-success
    # shape; it is NOT an error case (the two shapes are mutually exclusive).
    case = _concurrency_case(
        {
            "shape": "concurrencySuccess",
            "when": {
                "concurrency": {
                    "rounds": [
                        {
                            "A": {
                                "kind": "read",
                                "statements": [_entry(_SHARED_READ, [2])],
                                "expectRows": [{"id": 2}],
                            }
                        },
                        {
                            "B": {
                                "kind": "read",
                                "statements": [_entry(_SHARED_READ, [2])],
                                "expectRows": [{"id": 2}],
                            }
                        },
                    ]
                }
            },
        }
    )
    assert case.is_concurrency_success
    assert not case.is_error
    assert case.concurrency is not None


def test_error_concurrency_is_not_concurrency_success() -> None:
    # An error/concurrency case (m-read-lock-006) carries then.errorClass, so it stays an `error`
    # case and is NOT a concurrency-success case -- the discriminator that keeps the
    # root oneOf single-match. It carries NO `kind` (only the classified error is
    # asserted).
    case = _concurrency_case(
        {
            "shape": "error",
            "when": {
                "concurrency": {"rounds": [{"A": {"statements": [_entry(_SHARED_READ, [2])]}}]}
            },
            "then": {
                "errorClass": "lockWaitTimeout",
                "nativeCode": {"postgres": "55P03", "mariadb": 1205},
            },
        }
    )
    assert case.is_error
    assert not case.is_concurrency_success


# --- schema accept -----------------------------------------------------------


def test_schema_accepts_shared_reader_concurrency_success_case() -> None:
    # m-read-lock-007: both A and B take the shared read lock and BOTH succeed, each a kind: read
    # asserting its held-session rows. Validates against the concurrency-success oneOf
    # member (concurrency present, errorClass absent, every present step declaring kind).
    case = {
        "model": "models/account.yaml",
        "shape": "concurrencySuccess",
        "given": {"fixtures": True},
        "when": {
            "concurrency": {
                "rounds": [
                    {
                        "A": {
                            "kind": "read",
                            "statements": [_entry(_SHARED_READ, [2])],
                            "expectRows": [
                                {"id": 2, "owner": "Linus", "balance": 250.00, "version": 1}
                            ],
                        }
                    },
                    {
                        "B": {
                            "kind": "read",
                            "statements": [_entry(_SHARED_READ, [2])],
                            "expectRows": [
                                {"id": 2, "owner": "Linus", "balance": 250.00, "version": 1}
                            ],
                        }
                    },
                ]
            }
        },
        "tags": [
            "m-read-lock",
            "m-dialect",
            "read-lock",
            "concurrency",
            "shared-lock-compatible",
            "slice-example-1",
        ],
    }
    assert list(_case_validator().iter_errors(case)) == []


def test_schema_accepts_projection_admits_writer_concurrency_success_case() -> None:
    # m-read-lock-008: A holds an unlocked projection (kind: read + expectRows), B's UPDATE is
    # admitted (kind: write, NO expectRows -- a write asserts only that it did not block).
    projection = {
        "postgres": "select distinct t0.id from account t0",
        "mariadb": "select distinct t0.id from account t0",
    }
    case = {
        "model": "models/account.yaml",
        "shape": "concurrencySuccess",
        "given": {"fixtures": True},
        "when": {
            "concurrency": {
                "rounds": [
                    {
                        "A": {
                            "kind": "read",
                            "statements": [_entry(projection, [])],
                            "expectRows": [{"id": 1}, {"id": 2}, {"id": 3}],
                        }
                    },
                    {"B": {"kind": "write", "statements": [_entry(_UPDATE, [999.00, 2])]}},
                ]
            }
        },
        "tags": [
            "m-read-lock",
            "m-dialect",
            "read-lock",
            "concurrency",
            "projection-omits-lock",
            "slice-example-1",
        ],
    }
    assert list(_case_validator().iter_errors(case)) == []


# --- schema reject -----------------------------------------------------------


def test_schema_rejects_concurrency_with_error_class_but_no_native_code() -> None:
    # A concurrency case carrying errorClass MUST fully satisfy the error branch
    # (then.nativeCode required): it cannot fall back to the success branch,
    # whose `not: errorClass` guard it fails. Missing nativeCode ⇒ it
    # matches NEITHER branch ⇒ rejected.
    case = {
        "model": "models/account.yaml",
        "shape": "error",
        "when": {"concurrency": {"rounds": [{"A": {"statements": [_entry(_SHARED_READ, [2])]}}]}},
        "then": {"errorClass": "lockWaitTimeout"},
        "tags": ["m-read-lock", "m-dialect", "read-lock", "concurrency"],
    }
    assert list(_case_validator().iter_errors(case)), (
        "Schema should reject a concurrency case that carries errorClass but omits "
        "nativeCode (matches neither the error nor the success branch)"
    )


def test_schema_rejects_success_step_missing_kind() -> None:
    # The concurrency-success oneOf member requires `kind` on every present step
    # (rounds.items.properties.{A,B}.required: [kind]); a step that omits it matches
    # neither the success nor the error branch and is rejected.
    case = {
        "model": "models/account.yaml",
        "shape": "concurrencySuccess",
        "when": {
            "concurrency": {
                "rounds": [
                    {"A": {"statements": [_entry(_SHARED_READ, [2])], "expectRows": [{"id": 2}]}}
                ]
            }
        },
        "tags": ["m-read-lock", "read-lock", "concurrency"],
    }
    assert list(_case_validator().iter_errors(case)), (
        "Schema should reject a concurrency-success step that omits kind"
    )


def test_schema_rejects_read_step_missing_expect_rows() -> None:
    # The concurrencyStep if/then requires expectRows when kind is `read`; a read
    # step that omits it is rejected structurally (no verb sniffing needed).
    case = {
        "model": "models/account.yaml",
        "shape": "concurrencySuccess",
        "when": {
            "concurrency": {
                "rounds": [{"A": {"kind": "read", "statements": [_entry(_SHARED_READ, [2])]}}]
            }
        },
        "tags": ["m-read-lock", "read-lock", "concurrency"],
    }
    assert list(_case_validator().iter_errors(case)), (
        "Schema should reject a kind: read step that omits expectRows"
    )


def test_schema_rejects_write_step_with_expect_rows() -> None:
    # The concurrencyStep if/then FORBIDS expectRows when kind is `write` (a write
    # grades no rows); a write step that carries it is rejected structurally.
    case = {
        "model": "models/account.yaml",
        "shape": "concurrencySuccess",
        "when": {
            "concurrency": {
                "rounds": [
                    {
                        "A": {
                            "kind": "write",
                            "statements": [_entry(_UPDATE, [999.00, 2])],
                            "expectRows": [{"id": 2}],
                        }
                    }
                ]
            }
        },
        "tags": ["m-read-lock", "read-lock", "concurrency"],
    }
    assert list(_case_validator().iter_errors(case)), (
        "Schema should reject a kind: write step that carries expectRows"
    )


def test_schema_rejects_non_array_expect_rows() -> None:
    # concurrencyStep.expectRows is `{"type": "array"}`; a scalar is rejected (kind:
    # read makes it present, so the failure is specifically the type).
    case = {
        "model": "models/account.yaml",
        "shape": "concurrencySuccess",
        "when": {
            "concurrency": {
                "rounds": [
                    {
                        "A": {
                            "kind": "read",
                            "statements": [_entry(_SHARED_READ, [2])],
                            "expectRows": "nope",
                        }
                    }
                ]
            }
        },
        "tags": ["m-read-lock", "read-lock", "concurrency"],
    }
    assert list(_case_validator().iter_errors(case)), (
        "Schema should reject a non-array expectRows on a concurrency step"
    )


# --- runner structural guard -------------------------------------------------


def test_runner_assert_schema_raises_for_empty_concurrency_success_case() -> None:
    # _assert_schema must raise for a concurrency-success case whose rounds declare
    # no golden statement (an empty choreography has nothing to run).
    case = _concurrency_case(
        {
            "shape": "concurrencySuccess",
            "when": {"concurrency": {"rounds": [{"A": {"statements": []}}]}},
        }
    )
    with pytest.raises(CaseFailure, match="empty concurrency"):
        _assert_schema(case)


def test_runner_assert_schema_rejects_step_missing_kind() -> None:
    # A step that omits kind would mis-dispatch (the runner branches read-vs-write on
    # the explicit kind, no verb sniffing), so _assert_schema fails fast, naming the
    # offending /concurrency/rounds/{i}/{node} pointer.
    case = _concurrency_case(
        {
            "shape": "concurrencySuccess",
            "when": {
                "concurrency": {
                    "rounds": [
                        {
                            "A": {
                                "kind": "read",
                                "statements": [_entry(_SHARED_READ, [2])],
                                "expectRows": [{"id": 2}],
                            }
                        },
                        # round 1: a step that FORGOT kind -- must be rejected.
                        {
                            "B": {
                                "statements": [_entry(_SHARED_READ, [2])],
                                "expectRows": [{"id": 2}],
                            }
                        },
                    ]
                }
            },
        }
    )
    with pytest.raises(CaseFailure, match=r"/concurrency/rounds/1/B: a concurrency-success step"):
        _assert_schema(case)


def test_runner_assert_schema_rejects_read_step_missing_expect_rows() -> None:
    # Defense-in-depth over the schema if/then: a kind: read step that omits expectRows
    # would be graded against nothing, so _assert_schema fails fast on its pointer.
    case = _concurrency_case(
        {
            "shape": "concurrencySuccess",
            "when": {
                "concurrency": {
                    "rounds": [
                        {
                            "A": {
                                "kind": "read",
                                "statements": [_entry(_SHARED_READ, [2])],
                                "expectRows": [{"id": 2}],
                            }
                        },
                        # round 1: a read that FORGOT expectRows -- must be rejected.
                        {"B": {"kind": "read", "statements": [_entry(_SHARED_READ, [2])]}},
                    ]
                }
            },
        }
    )
    with pytest.raises(CaseFailure, match=r"/concurrency/rounds/1/B: a kind: read step"):
        _assert_schema(case)


def test_runner_assert_schema_allows_write_step_without_expect_rows() -> None:
    # m-read-lock-008's shape: a kind: read step declares expectRows and the round-2 kind: write
    # UPDATE omits it. The guard must NOT disturb the passing write step.
    projection = {
        "postgres": "select distinct t0.id from account t0",
        "mariadb": "select distinct t0.id from account t0",
    }
    case = _concurrency_case(
        {
            "shape": "concurrencySuccess",
            "when": {
                "concurrency": {
                    "rounds": [
                        {
                            "A": {
                                "kind": "read",
                                "statements": [_entry(projection, [])],
                                "expectRows": [{"id": 1}, {"id": 2}, {"id": 3}],
                            }
                        },
                        {"B": {"kind": "write", "statements": [_entry(_UPDATE, [999.00, 2])]}},
                    ]
                }
            },
        }
    )
    _assert_schema(case)  # must not raise
