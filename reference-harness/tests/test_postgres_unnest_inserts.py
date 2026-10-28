"""Authored PostgreSQL column-array inserts execute once and store the rows their
arrays align.

Each statement is hand-authored in the column-array form a multi-row insert
takes on PostgreSQL (`insert … select * from unnest(cast(? as T[]), …)`), run
through :class:`CaseExecution` as a golden would be, and graded by reading the
whole table back. MariaDB has no array parameter, so it never executes this form.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from reference_harness._case_execution import CaseExecution
from reference_harness.case import Case, Model, load_model
from reference_harness.case_assertions import rows_equal
from reference_harness.provisioning import provision_empty
from reference_harness.table_state import read_tables

_COMPATIBILITY_ROOT = Path(__file__).resolve().parents[2] / "core" / "compatibility"


def _nullable(name: str, neutral_type: str, **facts: Any) -> dict[str, Any]:
    return {"name": name, "type": neutral_type, "nullable": True, **facts}


_WIDE = Model(
    Path("wide.yaml"),
    {
        "entity": {
            "name": "Wide",
            "namespace": "example",
            "table": "wide",
            "attributes": [
                {"name": "id", "type": "int64", "primaryKey": True},
                _nullable("flag", "boolean"),
                _nullable("small", "int32"),
                _nullable("big", "int64"),
                _nullable("ratio", "float32"),
                _nullable("measure", "float64"),
                _nullable("amount", "decimal(18,2)"),
                _nullable("label", "string", maxLength=16),
                _nullable("payload", "bytes"),
                _nullable("day", "date"),
                _nullable("clock", "time"),
                _nullable("stamp", "timestamp"),
                _nullable("ref", "uuid"),
                {"name": "tags", "type": "string", "multiplicity": "many"},
            ],
            "valueObjects": [
                {
                    "name": "address",
                    "nullable": True,
                    "attributes": [_nullable("city", "string")],
                }
            ],
        }
    },
)

_WIDE_INSERT = (
    "insert into wide(id, flag, small, big, ratio, measure, amount, label, payload, day, "
    "clock, stamp, ref, tags, address) select * from unnest(cast(? as bigint[]), "
    "cast(? as boolean[]), cast(? as int[]), cast(? as bigint[]), cast(? as real[]), "
    "cast(? as double precision[]), cast(? as decimal[]), cast(? as text[]), "
    "cast(? as bytea[]), cast(? as date[]), cast(? as time[]), cast(? as timestamptz[]), "
    "cast(? as uuid[]), cast(? as jsonb[]), cast(? as jsonb[]))"
)

# One row per element position; every nullable member is SQL NULL in the second.
_WIDE_ROWS: list[dict[str, Any]] = [
    {
        "id": 1,
        "flag": True,
        "small": -2147483648,
        "big": 9223372036854775807,
        "ratio": 0.1,
        "measure": -2.25,
        "amount": "10.50",
        "label": "Mira",
        "payload": "01020304",
        "day": "2026-01-15",
        "clock": "12:34:56.789012",
        "stamp": "2024-01-01T12:00:00.123456Z",
        "ref": "123e4567-e89b-12d3-a456-426614174000",
        "tags": ["red", "blue"],
        "address": {"city": None},
    },
    {
        "id": 2,
        "flag": None,
        "small": None,
        "big": None,
        "ratio": None,
        "measure": None,
        "amount": None,
        "label": None,
        "payload": None,
        "day": None,
        "clock": None,
        "stamp": None,
        "ref": None,
        "tags": [],
        "address": None,
    },
    {
        "id": 3,
        "flag": False,
        "small": 2147483647,
        "big": -9223372036854775808,
        "ratio": -3.5,
        "measure": 1e300,
        "amount": "-9999999999999999.99",
        "label": "with, comma {}",
        "payload": "",
        "day": "1970-01-01",
        "clock": "00:00:00",
        "stamp": "1999-12-31T23:59:59.999999Z",
        "ref": "00000000-0000-0000-0000-000000000000",
        "tags": ["nested"],
        "address": {"city": "Oslo"},
    },
]


def _column_arrays(columns: list[str], rows: list[dict[str, Any]]) -> list[list[Any]]:
    return [[row[column] for row in rows] for column in columns]


def _case(model: Model) -> Case:
    return Case(Path("synthetic-column-arrays.yaml"), {"shape": "scenario", "then": {}}, model)


def _postgres_only(provider: Any) -> None:
    if provider.dialect != "postgres":
        pytest.skip("only PostgreSQL binds column arrays; MariaDB inserts multi-row VALUES")


def _insert(provider: Any, case: Case, statement: str, binds: list[list[Any]]) -> int:
    provision_empty(case, provider)
    return CaseExecution(case, provider).execute(statement, binds)


def test_every_scalar_document_and_null_element_is_stored_in_its_row(provider) -> None:
    _postgres_only(provider)
    case = _case(_WIDE)
    columns = list(_WIDE_ROWS[0])

    assert _insert(provider, case, _WIDE_INSERT, _column_arrays(columns, _WIDE_ROWS)) == 3

    stored = read_tables(case, provider, ("wide",))["wide"]
    assert rows_equal(stored, _WIDE_ROWS), stored


def test_a_document_element_keeps_json_null_apart_from_sql_null(provider) -> None:
    # A JSON null inside a document stays inside that one `jsonb` element, a nested
    # JSON array stays one element rather than an array dimension, and only a
    # `None` element is SQL NULL.
    _postgres_only(provider)
    case = _case(_WIDE)
    _insert(provider, case, _WIDE_INSERT, _column_arrays(list(_WIDE_ROWS[0]), _WIDE_ROWS))

    observed = provider.query(
        "select id, address is null as sql_null, jsonb_typeof(address -> 'city') as city, "
        "jsonb_typeof(tags) as tags, jsonb_array_length(tags) as tag_count "
        "from wide order by id"
    )
    assert observed == [
        {"id": 1, "sql_null": False, "city": "null", "tags": "array", "tag_count": 2},
        {"id": 2, "sql_null": True, "city": None, "tags": "array", "tag_count": 0},
        {"id": 3, "sql_null": False, "city": "string", "tags": "array", "tag_count": 1},
    ]


def test_each_shared_document_is_stored_beside_its_own_rows_tag(provider) -> None:
    # Table-per-hierarchy siblings share `payment_document` and declare `detail`
    # differently, so the tag array and the document array align row by row.
    _postgres_only(provider)
    case = _case(load_model(_COMPATIBILITY_ROOT, "models/document-layout.yaml"))
    rows = [
        {"id": 2, "kind": "cash", "payload": {"detail": "12.50"}},
        {"id": 3, "kind": "card", "payload": {"detail": "visa-4242", "authorizationCode": "A1"}},
        {"id": 4, "kind": "cash", "payload": {"detail": "0.00"}},
    ]
    statement = (
        "insert into payment_document(id, kind, payload) select * from "
        "unnest(cast(? as bigint[]), cast(? as text[]), cast(? as jsonb[]))"
    )

    assert _insert(provider, case, statement, _column_arrays(["id", "kind", "payload"], rows)) == 3

    stored = read_tables(case, provider, ("payment_document",))["payment_document"]
    assert rows_equal(stored, rows), stored


def test_temporal_successors_store_finite_bounds_beside_the_open_bound(provider) -> None:
    _postgres_only(provider)
    case = _case(load_model(_COMPATIBILITY_ROOT, "models/position.yaml"))
    rows = [
        {
            "pos_id": 1,
            "acct_num": "A",
            "val": "100.00",
            "from_z": "2024-01-01T00:00:00.000000Z",
            "thru_z": "2024-03-01T00:00:00.000000Z",
            "in_z": "2024-02-15T00:00:00.000000Z",
            "out_z": "infinity",
        },
        {
            "pos_id": 1,
            "acct_num": "A",
            "val": "200.00",
            "from_z": "2024-03-01T00:00:00.000000Z",
            "thru_z": "infinity",
            "in_z": "2024-02-15T00:00:00.000000Z",
            "out_z": "infinity",
        },
    ]
    columns = list(rows[0])
    statement = (
        f"insert into position({', '.join(columns)}) select * from unnest("
        "cast(? as bigint[]), cast(? as text[]), cast(? as decimal[]), "
        "cast(? as timestamptz[]), cast(? as timestamptz[]), cast(? as timestamptz[]), "
        "cast(? as timestamptz[]))"
    )

    assert _insert(provider, case, statement, _column_arrays(columns, rows)) == 2

    stored = read_tables(case, provider, ("position",))["position"]
    assert rows_equal(stored, rows), stored
    assert provider.query("select count(*) as open from position where out_z = 'infinity'") == [
        {"open": 2}
    ]
