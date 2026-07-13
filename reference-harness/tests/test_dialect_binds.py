"""DB-free tests for the per-dialect binds / referenceSql polymorphism (COR-10).

Value-object cases carry Postgres AND MariaDB golden SQL whose bind holes diverge
(Postgres per-segment JSON keys vs a MariaDB single ``'$.a.b'`` path bind), so
``binds`` — like ``sql`` — may be a dialect-keyed map. These tests pin, without a
database:

* the compatibility-case schema accepts the map form for both ``binds`` and
  ``referenceSql`` (and rejects a non-array / unknown-dialect binds map);
* ``Case.statement_binds`` resolves the right list per dialect (and errors when a
  map is asked for without a dialect);
* ``Case.reference_sql_for`` picks the right oracle per dialect, and fails LOUDLY
  (never a silent ``None``) for a dialect a map does not carry;
* ``_assert_binds_dialect_keys`` and ``_assert_reference_sql_dialect_keys`` enforce
  the keys-match invariant for ``binds`` and ``referenceSql`` respectively; and
* the frozen ``m-value-object-*`` corpus authors its binds by whether the golden SQL
  DIVERGES per dialect: a per-dialect binds map exactly when the SQL diverges (the
  nested-extraction reads), and the flat shared-hole form when it is dialect-identical
  (every atomic-document write, and the temporal projection reads whose bare-column SQL
  is the same on both dialects).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from reference_harness.case import Case, Model, discover_cases
from reference_harness.case_runner import (
    CaseFailure,
    _assert_binds_dialect_keys,
    _assert_reference_sql_dialect_keys,
)
from reference_harness.schemas import build_registry, load_schemas

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"
_CASE_SCHEMA_PATH = _REPO_ROOT / "core" / "schemas" / "compatibility-case.schema.json"
_REGISTRY = build_registry(load_schemas(_REPO_ROOT / "core"))


_PG_NESTED = "select t0.id from customer t0 where jsonb_extract_path_text(t0.address, ?) = ?"
_MDB_NESTED = "select t0.id from customer t0 where json_value(t0.address, ?) = ?"


def _case_validator() -> Draft202012Validator:
    return Draft202012Validator(
        json.loads(_CASE_SCHEMA_PATH.read_text(encoding="utf-8")), registry=_REGISTRY
    )


def _make_case(statements: list[dict[str, Any]], reference_sql: Any = None) -> Case:
    then: dict[str, Any] = {"statements": statements, "rows": [], "roundTrips": 1}
    if reference_sql is not None:
        then["referenceSql"] = reference_sql
    raw = {
        "model": "models/customer.yaml",
        "tags": ["m-value-object"],
        "shape": "read",
        "when": {"operation": {"all": {}}},
        "then": then,
    }
    model = Model(
        path=Path("models/customer.yaml"),
        descriptor={"entity": {"name": "Customer", "table": "customer", "attributes": []}},
    )
    return Case(path=Path("m-value-object-999-x.yaml"), raw=raw, model=model)


# --- schema fidelity --------------------------------------------------------


def _read_case_doc() -> dict[str, Any]:
    return {
        "model": "models/customer.yaml",
        "tags": ["m-value-object"],
        "shape": "read",
        "when": {"targetEntity": "Customer", "operation": {"all": {}}},
        "then": {
            "statements": [
                {
                    "sql": {"postgres": _PG_NESTED, "mariadb": _MDB_NESTED},
                    "binds": {"postgres": ["city", "Oslo"], "mariadb": ["$.city", "Oslo"]},
                }
            ],
            "referenceSql": {
                "postgres": "select id from customer where address ->> 'city' = 'Oslo'",
                "mariadb": (
                    "select id from customer where "
                    "nullif(json_unquote(json_extract(address, '$.city')), 'null') = 'Oslo'"
                ),
            },
            "rows": [{"id": 1}],
            "roundTrips": 1,
        },
    }


def test_schema_accepts_dialect_keyed_binds_and_reference_sql() -> None:
    errors = list(_case_validator().iter_errors(_read_case_doc()))
    assert errors == [], [e.message for e in errors]


def test_schema_still_accepts_flat_binds() -> None:
    doc = _read_case_doc()
    doc["then"]["statements"][0]["binds"] = ["city", "Oslo"]
    doc["then"]["statements"][0]["sql"] = {"postgres": "select t0.id from customer t0"}
    doc["then"]["referenceSql"] = "select id from customer"
    assert next(_case_validator().iter_errors(doc), None) is None


def test_schema_rejects_binds_map_with_non_array_value() -> None:
    doc = _read_case_doc()
    doc["then"]["statements"][0]["binds"] = {"postgres": "city"}
    assert next(_case_validator().iter_errors(doc), None) is not None


def test_schema_rejects_binds_map_with_unknown_dialect() -> None:
    doc = _read_case_doc()
    doc["then"]["statements"][0]["binds"] = {"snowflake": ["city", "Oslo"]}
    assert next(_case_validator().iter_errors(doc), None) is not None


# --- Case accessors ---------------------------------------------------------


def test_statement_binds_flat_ignores_dialect() -> None:
    case = _make_case([{"sql": {"postgres": "select 1"}, "binds": [1, 2]}])
    assert case.statement_binds(0) == [1, 2]
    assert case.statement_binds(0, "postgres") == [1, 2]
    assert case.statement_binds(0, "mariadb") == [1, 2]


def test_statement_binds_map_resolves_per_dialect() -> None:
    case = _make_case(
        [
            {
                "sql": {"postgres": "select 1", "mariadb": "select 1"},
                "binds": {"postgres": ["city", "Oslo"], "mariadb": ["$.city", "Oslo"]},
            }
        ]
    )
    assert case.statement_binds(0, "postgres") == ["city", "Oslo"]
    assert case.statement_binds(0, "mariadb") == ["$.city", "Oslo"]


def test_statement_binds_map_without_dialect_errors() -> None:
    case = _make_case(
        [
            {
                "sql": {"postgres": "select 1", "mariadb": "select 1"},
                "binds": {"postgres": [1], "mariadb": [2]},
            }
        ]
    )
    with pytest.raises(KeyError):
        case.statement_binds(0)


def test_reference_sql_for_string_is_dialect_neutral() -> None:
    case = _make_case([{"sql": {"postgres": "select 1"}}], reference_sql="select id from customer")
    assert case.reference_sql_for("postgres") == "select id from customer"
    assert case.reference_sql_for("mariadb") == "select id from customer"


def test_reference_sql_for_map_resolves_per_dialect() -> None:
    case = _make_case(
        [{"sql": {"postgres": "select 1"}}],
        reference_sql={"postgres": "pg oracle", "mariadb": "maria oracle"},
    )
    assert case.reference_sql_for("postgres") == "pg oracle"
    assert case.reference_sql_for("mariadb") == "maria oracle"
    # A dialect the map does NOT carry is a LOUD failure, never a silent None: a
    # silently skipped oracle would let that dialect's golden SQL go unchecked.
    with pytest.raises(KeyError):
        case.reference_sql_for("snowflake")


def test_reference_sql_for_absent_is_none() -> None:
    # An entirely unauthored referenceSql (a trivial case, no oracle) still yields
    # None — the callers legitimately run no oracle for it.
    case = _make_case([{"sql": {"postgres": "select 1"}}])
    assert case.reference_sql_for("postgres") is None
    assert case.reference_sql_for("mariadb") is None


# --- keys-match invariant ---------------------------------------------------


def test_assert_binds_dialect_keys_accepts_matching_map() -> None:
    case = _make_case(
        [
            {
                "sql": {"postgres": "select 1", "mariadb": "select 1"},
                "binds": {"postgres": [1], "mariadb": [2]},
            }
        ]
    )
    _assert_binds_dialect_keys(case)  # no raise


def test_assert_binds_dialect_keys_rejects_missing_dialect() -> None:
    case = _make_case(
        [{"sql": {"postgres": "select 1", "mariadb": "select 1"}, "binds": {"postgres": [1]}}]
    )
    with pytest.raises(CaseFailure):
        _assert_binds_dialect_keys(case)


def test_assert_binds_dialect_keys_ignores_flat_binds() -> None:
    case = _make_case([{"sql": {"postgres": "select 1", "mariadb": "select 1"}, "binds": [1]}])
    _assert_binds_dialect_keys(case)  # flat binds impose no key constraint


def test_assert_reference_sql_dialect_keys_accepts_matching_map() -> None:
    case = _make_case(
        [{"sql": {"postgres": "select 1", "mariadb": "select 1"}}],
        reference_sql={"postgres": "pg oracle", "mariadb": "maria oracle"},
    )
    _assert_reference_sql_dialect_keys(case)  # keys == golden sql dialects: no raise


def test_assert_reference_sql_dialect_keys_rejects_divergent_keys() -> None:
    # The golden sql declares postgres AND mariadb, but the oracle only carries
    # postgres — mariadb would execute with NO independent oracle. Must be rejected.
    case = _make_case(
        [{"sql": {"postgres": "select 1", "mariadb": "select 1"}}],
        reference_sql={"postgres": "pg oracle"},
    )
    with pytest.raises(CaseFailure):
        _assert_reference_sql_dialect_keys(case)


def test_assert_reference_sql_dialect_keys_rejects_extra_dialect() -> None:
    # The oracle carries a dialect (mariadb) the golden sql does not declare — an
    # oracle with no golden to grade against is equally inconsistent.
    case = _make_case(
        [{"sql": {"postgres": "select 1"}}],
        reference_sql={"postgres": "pg oracle", "mariadb": "maria oracle"},
    )
    with pytest.raises(CaseFailure):
        _assert_reference_sql_dialect_keys(case)


def test_assert_reference_sql_dialect_keys_ignores_string() -> None:
    case = _make_case(
        [{"sql": {"postgres": "select 1", "mariadb": "select 1"}}],
        reference_sql="select id from customer",
    )
    _assert_reference_sql_dialect_keys(case)  # a plain string imposes no key constraint


# --- the frozen value-object corpus ----------------------------------------


def _value_object_cases() -> list[Case]:
    # The `rejected`-shape value-object cases (m-value-object negative validation)
    # assert a PRE-SQL refusal and carry NO golden SQL, so the per-dialect-binds
    # invariant (which is about golden extraction / write DML) does not apply to them.
    return [
        c
        for c in discover_cases(_COMPATIBILITY_ROOT)
        if c.path.name.startswith("m-value-object-") and c.shape != "rejected"
    ]


def test_value_object_cases_carry_both_dialects_and_per_dialect_binds() -> None:
    cases = _value_object_cases()
    assert cases, "no m-value-object cases discovered"
    for case in cases:
        assert case.golden_dialects == {"postgres", "mariadb"}, (
            f"{case.path.name}: expected postgres+mariadb golden, got {case.golden_dialects}"
        )
        # The keys-match invariant holds for every value-object case, for both the
        # per-dialect binds and the per-dialect referenceSql oracle.
        _assert_binds_dialect_keys(case)
        _assert_reference_sql_dialect_keys(case)
        for index, entry in enumerate(case.golden_entries()):
            binds = entry.get("binds")
            if binds is None:
                continue
            sql = entry.get("sql")
            # The bind HOLES diverge per dialect EXACTLY when the golden SQL text does,
            # so that — not the read/write axis — is what decides flat vs. map binds:
            #
            #  * DIVERGENT golden SQL → a per-dialect binds map. A value-object nested
            #    EXTRACTION read diverges (Postgres per-segment JSON keys
            #    `jsonb_extract_path_text(col, ?, …)` vs. a MariaDB single `'$.a.b'`
            #    path `json_value(col, ?)`), so its holes — and its binds — are keyed.
            #  * DIALECT-IDENTICAL golden SQL → a flat, shared binds array. A value-object
            #    WRITE binds the whole document as ONE shared hole in columnOrder position
            #    (only the provider ADAPTATION differs — Postgres `Jsonb` / MariaDB
            #    `json.dumps`), and a TEMPORAL projection read (`m-value-object-028..031`)
            #    projects the bare document column and filters on the owner's as-of axis
            #    with the SAME SQL on both dialects — so both carry the authored flat
            #    (shared-hole) form (resolved Q12: flat wherever the hole is shared).
            texts = set(sql.values()) if isinstance(sql, dict) else {sql}
            if len(texts) == 1:
                assert isinstance(binds, list), (
                    f"{case.path.name}: statement {index} has dialect-identical golden SQL, "
                    f"so its bind hole is shared and binds MUST be a flat array, not a "
                    f"per-dialect map"
                )
            else:
                assert isinstance(binds, dict), (
                    f"{case.path.name}: statement {index} has per-dialect golden SQL whose "
                    f"bind holes diverge, so binds MUST be a per-dialect map"
                )
