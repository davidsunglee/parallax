"""Generated document root checks on a real PostgreSQL (m-storage-layout / m-db-error).

Provisioning goes through the shipped Schema Delta, so the catalog these tests
read is the one every database-backed suite runs against. Writes here are raw
statements from outside Parallax: the check governs every writer of the table.
The adoption tests run the manual migration the PostgreSQL lifecycle guide
documents against a table provisioned without its check.
"""

from __future__ import annotations

from typing import Any

import psycopg
import pytest

from parallax.conformance import models, provision
from parallax.conformance.models import default_models_dir
from parallax.core.internal.db_error import DatabaseError
from parallax.core.internal.metamodel import Metamodel
from tests._support.bindings import TEST_SCHEMA, bound_model

_INSERT = "insert into px.collection_twin (id, payload) values (?, cast(? as jsonb))"
_UPDATE = "update px.collection_twin set payload = cast(? as jsonb) where id = ?"
_STORED = "select t0.id, t0.payload::text from px.collection_twin t0 order by t0.id"
_CHECKS = (
    "select t0.conname, pg_get_constraintdef(t0.oid), t0.convalidated "
    "from pg_constraint t0 join pg_class t1 on t1.oid = t0.conrelid "
    "where t1.relname = ? and t0.contype = 'c' order by t0.conname"
)
_DEFINITION = "CHECK ((jsonb_typeof(payload) = 'object'::text))"
_NON_OBJECT_ROOTS = ["null", '"legacy"', "7", "true", "[]", '[{"a": 1}]']


def _provision(profile_run: Any, model_file: str) -> Metamodel:
    model = models.load_model(default_models_dir() / model_file)
    for statement in provision.reset_statements(frozenset({TEST_SCHEMA})):
        profile_run.port.execute_write(statement, [])
    for statement in provision.schema_statements(bound_model(model)):
        profile_run.port.execute_write(statement, [])
    return model


def _check_name(model: Metamodel, table: str) -> str:
    (resolved,) = (
        resolved for resolved in bound_model(model).tables if resolved.physical.name == table
    )
    assert resolved.document_root_constraint is not None
    return resolved.document_root_constraint.check_name


def _document_checks(profile_run: Any, table: str) -> list[tuple[object, ...]]:
    return [
        tuple(row)
        for row in profile_run.port.execute(_CHECKS, [table])
        if str(row[0]).startswith("pxc_doc_")
    ]


def _refused(profile_run: Any, sql: str, binds: list[object]) -> DatabaseError:
    with pytest.raises(DatabaseError) as raised:
        profile_run.port.execute_write(sql, binds)
    return raised.value


def _assert_refused_by(error: DatabaseError, name: str) -> None:
    assert (error.category, error.native_code) == ("constraintViolation", "23514")
    assert error.constraint_name == name
    assert error.violated_index is None
    assert not error.is_transient
    assert isinstance(error.__cause__, psycopg.errors.CheckViolation)


@pytest.mark.parametrize(
    ("model_file", "tables"),
    [
        ("scalar-collection-layout-twin-document.yaml", ("collection_twin",)),
        ("versioned-payment-document.yaml", ("versioned_payment_document",)),
        ("rate-sheet-document.yaml", ("sheet_deposit", "sheet_loan")),
    ],
)
def test_the_catalog_holds_each_document_tables_root_check_under_its_compiled_name(
    profile_run: Any, model_file: str, tables: tuple[str, ...]
) -> None:
    model = _provision(profile_run, model_file)
    for table in tables:
        assert _document_checks(profile_run, table) == [
            (_check_name(model, table), _DEFINITION, True)
        ]


@pytest.mark.parametrize(
    ("model_file", "table"),
    [
        ("scalar-collection-layout-twin-columns.yaml", "collection_twin"),
        ("rate-sheet-document.yaml", "rate_sheet"),
    ],
)
def test_a_columns_table_checks_none_of_its_structured_columns(
    profile_run: Any, model_file: str, table: str
) -> None:
    _provision(profile_run, model_file)
    assert _document_checks(profile_run, table) == []


def test_an_object_root_is_accepted_on_insert_and_update(profile_run: Any) -> None:
    _provision(profile_run, "scalar-collection-layout-twin-document.yaml")
    profile_run.port.execute_write(_INSERT, [1, "{}"])
    profile_run.port.execute_write(_INSERT, [2, '{"tags": ["a"], "legacy": null}'])
    profile_run.port.execute_write(_UPDATE, ['{"tags": []}', 1])
    assert profile_run.port.execute(_STORED, []) == [
        (1, '{"tags": []}'),
        (2, '{"tags": ["a"], "legacy": null}'),
    ]


@pytest.mark.parametrize("root", _NON_OBJECT_ROOTS)
def test_an_external_insert_of_a_non_object_root_is_refused_by_name(
    profile_run: Any, root: str
) -> None:
    model = _provision(profile_run, "scalar-collection-layout-twin-document.yaml")
    error = _refused(profile_run, _INSERT, [1, root])
    _assert_refused_by(error, _check_name(model, "collection_twin"))
    assert profile_run.port.execute(_STORED, []) == []


@pytest.mark.parametrize("root", _NON_OBJECT_ROOTS)
def test_an_external_update_to_a_non_object_root_is_refused_by_name(
    profile_run: Any, root: str
) -> None:
    model = _provision(profile_run, "scalar-collection-layout-twin-document.yaml")
    profile_run.port.execute_write(_INSERT, [1, '{"tags": ["a"]}'])
    error = _refused(profile_run, _UPDATE, [root, 1])
    _assert_refused_by(error, _check_name(model, "collection_twin"))
    assert profile_run.port.execute(_STORED, []) == [(1, '{"tags": ["a"]}')]


# --------------------------------------------------------------------------- #
# Adopting the check on a table that existed before it                        #
# --------------------------------------------------------------------------- #
def _without_check(profile_run: Any) -> str:
    """A ``collection_twin`` table as an earlier release created it, holding bad roots."""
    model = _provision(profile_run, "scalar-collection-layout-twin-document.yaml")
    name = _check_name(model, "collection_twin")
    profile_run.port.execute_write(f"alter table px.collection_twin drop constraint {name}", [])
    profile_run.port.execute_write(_INSERT, [1, "null"])
    profile_run.port.execute_write(_INSERT, [2, '["legacy"]'])
    profile_run.port.execute_write(_INSERT, [3, '{"tags": []}'])
    return name


def test_the_validation_query_finds_every_root_the_check_would_refuse(profile_run: Any) -> None:
    _without_check(profile_run)
    refused = profile_run.port.execute(
        "select id from px.collection_twin where jsonb_typeof(payload) <> 'object' order by id",
        [],
    )
    assert [row[0] for row in refused] == [1, 2]


def test_a_staged_root_check_governs_new_writes_and_validates_once_the_rows_are_repaired(
    profile_run: Any,
) -> None:
    name = _without_check(profile_run)
    profile_run.port.execute_write(
        f"alter table px.collection_twin add constraint {name} "
        "check (jsonb_typeof(payload) = 'object') not valid",
        [],
    )
    assert _document_checks(profile_run, "collection_twin") == [
        (name, f"{_DEFINITION} NOT VALID", False)
    ]

    _assert_refused_by(_refused(profile_run, _INSERT, [4, "7"]), name)
    _assert_refused_by(_refused(profile_run, _UPDATE, ["[]", 3]), name)
    stored = _refused(profile_run, f"alter table px.collection_twin validate constraint {name}", [])
    assert (stored.category, stored.constraint_name) == ("constraintViolation", name)
    assert _document_checks(profile_run, "collection_twin") == [
        (name, f"{_DEFINITION} NOT VALID", False)
    ]

    profile_run.port.execute_write(_UPDATE, ["{}", 1])
    profile_run.port.execute_write("delete from px.collection_twin where id = ?", [2])
    profile_run.port.execute_write(f"alter table px.collection_twin validate constraint {name}", [])
    assert _document_checks(profile_run, "collection_twin") == [(name, _DEFINITION, True)]
