"""Provisioning statement-generation unit tests (Docker-free).

The DDL and fixture-load statement generation is pure and proven here without a
container: descriptor-derived ``create table`` DDL in column order (reserved
identifiers quoted, value objects as ``jsonb``), fixtures mapped attribute-name →
column with value-object documents wrapped for a ``jsonb`` bind, and the reset
statements. The container lifecycle itself is proven by the Docker provider lane.
"""

from __future__ import annotations

import pytest

from parallax.conformance import models, provision
from parallax.core.db_port import JsonDocument

pytestmark = pytest.mark.unit

_MODELS = models.load_models()


def test_reset_statements() -> None:
    assert provision.reset_statements() == [
        "drop schema if exists public cascade",
        "create schema public",
    ]


def test_schema_statements_quote_reserved_and_order_columns() -> None:
    (ddl,) = provision.schema_statements(_MODELS["grade"])
    assert ddl == (
        'create table grade (id bigint, "order" integer, label varchar(32), primary key (id))'
    )


def test_schema_statements_map_value_objects_to_jsonb() -> None:
    (ddl,) = [
        stmt
        for stmt in provision.schema_statements(_MODELS["customer"])
        if stmt.startswith("create table customer ")
    ]
    assert "address jsonb" in ddl
    assert "primary key (id)" in ddl


def test_schema_statements_temporal_pk_is_business_key_plus_from_columns() -> None:
    # A temporal entity's physical PK is the business key plus each axis's fromColumn
    # (m-descriptor): audit-only Balance keys on (bal_id, in_z) so successive
    # milestones sharing one business key coexist.
    (audit,) = provision.schema_statements(_MODELS["balance"])
    assert "primary key (bal_id, in_z)" in audit
    # Bitemporal Position keys on the business key plus BOTH from-columns, business
    # axis before processing (from_z then in_z), matching its declared composite index.
    (bitemporal,) = provision.schema_statements(_MODELS["position"])
    assert "primary key (pos_id, from_z, in_z)" in bitemporal


def test_schema_statements_create_the_shared_table_once() -> None:
    # Payment (abstract root) is tableless; its concrete subtypes share ONE table,
    # so exactly one `create table payment` is emitted (not one per subtype).
    tables = provision.schema_statements(_MODELS["payment"])
    payment_tables = [ddl for ddl in tables if ddl.startswith("create table payment ")]
    assert len(payment_tables) == 1


def test_fixture_statements_map_names_to_columns() -> None:
    fixtures = provision.load_fixtures("models/grade.yaml")
    statements = provision.fixture_statements(_MODELS["grade"], fixtures)
    assert len(statements) == 3
    sql, binds = statements[0]
    assert sql == 'insert into grade (id, "order", label) values (?, ?, ?)'
    assert binds == [1, 1, "low"]


def test_fixture_statements_follow_descriptor_column_order_not_mapping_order() -> None:
    # Re-spelling a fixture row with permuted keys must emit byte-identical SQL:
    # columns and binds follow the descriptor `column_order`, never `row.items()`.
    canonical = {"Grade": [{"id": 1, "ordinal": 1, "label": "low"}]}
    permuted = {"Grade": [{"label": "low", "id": 1, "ordinal": 1}]}
    assert provision.fixture_statements(
        _MODELS["grade"], canonical
    ) == provision.fixture_statements(_MODELS["grade"], permuted)
    (sql, binds) = provision.fixture_statements(_MODELS["grade"], permuted)[0]
    assert sql == 'insert into grade (id, "order", label) values (?, ?, ?)'
    assert binds == [1, 1, "low"]


def test_fixture_statements_skip_a_column_the_row_omits() -> None:
    # A fixture row omitting a (nullable) member emits only the present columns,
    # still in descriptor column order — the omitted `label` is skipped.
    fixtures = {"Grade": [{"ordinal": 2, "id": 5}]}
    (sql, binds) = provision.fixture_statements(_MODELS["grade"], fixtures)[0]
    assert sql == 'insert into grade (id, "order") values (?, ?)'
    assert binds == [5, 2]


def test_fixture_statements_wrap_value_objects() -> None:
    fixtures = provision.load_fixtures("models/customer.yaml")
    statements = provision.fixture_statements(_MODELS["customer"], fixtures)
    _sql, binds = statements[0]
    assert any(isinstance(bind, JsonDocument) for bind in binds)


def test_load_fixtures_missing_model_is_empty() -> None:
    assert provision.load_fixtures("models/does-not-exist.yaml") == {}


def test_fixture_statements_skip_non_list_and_non_mapping_rows() -> None:
    fixtures = {
        "Grade": [
            {"id": 1, "ordinal": 1, "label": "low", "unknownKey": "ignored"},
            "not-a-mapping",
        ],
        "Missing": {"not": "a list"},
    }
    statements = provision.fixture_statements(_MODELS["grade"], fixtures)
    # Only the one valid mapping row produces a statement; the unknown key is dropped.
    assert len(statements) == 1
    _sql, binds = statements[0]
    assert binds == [1, 1, "low"]


def test_fixture_statements_skip_a_non_list_entity_block() -> None:
    # An entity whose fixture value is not a list contributes no insert statements.
    assert provision.fixture_statements(_MODELS["customer"], {"Customer": "not-a-list"}) == []
