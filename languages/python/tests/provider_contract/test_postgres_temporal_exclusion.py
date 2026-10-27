"""Generated temporal exclusions on a real PostgreSQL (m-storage-layout / m-schema-delta).

Provisioning goes through the shipped Schema Delta, so the catalog these tests
read is the one every database-backed suite runs against. Writes are raw
statements from outside Parallax: the exclusion governs every writer of a
generated table. The migration tests run the manual adoption the PostgreSQL
lifecycle guide documents, from a table as a release before named temporal keys
created it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest

from parallax.conformance import models, provision
from parallax.conformance.models import default_models_dir
from parallax.core import Attr, Bitemporal, DomainModel, Int32, TxTemporal, attr, storage_layout
from parallax.core.base import INFINITY
from parallax.core.db_error import DatabaseError
from parallax.core.entity._model import model_of
from parallax.core.metamodel import Metamodel, Table
from parallax.core.storage_layout import TemporalHistoryConstraints

_JAN, _FEB, _MAR, _APR, _JUN, _SEP = (
    datetime(2024, month, 1, tzinfo=UTC) for month in (1, 2, 3, 4, 6, 9)
)

_INSERT_POSITION = (
    "insert into position (pos_id, acct_num, val, from_z, thru_z, in_z, out_z) "
    "values (%s, %s, %s, %s, %s, %s, %s)"
)
_CONSTRAINTS = (
    "select t0.conname, t0.contype, pg_get_constraintdef(t0.oid), t0.condeferrable "
    "from pg_constraint t0 join pg_class t1 on t1.oid = t0.conrelid "
    "where t1.relname = %s and t0.contype in ('p', 'x') order by t0.contype"
)
_OVERLAPS = (
    "select a.pos_id, a.in_z, b.in_z from position a join position b "
    "on a.pos_id = b.pos_id and a.ctid < b.ctid "
    "and tstzrange(a.in_z, a.out_z) && tstzrange(b.in_z, b.out_z) "
    "and tstzrange(a.from_z, a.thru_z) && tstzrange(b.from_z, b.thru_z) "
    "order by a.pos_id"
)


def _provision(profile_run: Any, model_file: str) -> Metamodel:
    model = models.load_model(default_models_dir() / model_file)
    for statement in provision.reset_statements():
        profile_run.port.execute_write(statement, [])
    for statement in provision.schema_statements(model):
        profile_run.port.execute_write(statement, [])
    return model


def _constraints(model: Metamodel, table: str) -> TemporalHistoryConstraints:
    layout = storage_layout.view(model).table(Table(table))
    assert layout is not None and layout.temporal_constraints is not None
    return layout.temporal_constraints


def _refused(profile_run: Any, sql: str, binds: list[object]) -> DatabaseError:
    with pytest.raises(DatabaseError) as raised:
        profile_run.port.execute_write(sql, binds)
    return raised.value


def _exclusion_definition(constraints: TemporalHistoryConstraints) -> str:
    key = ", ".join(f"{slot.column.name} WITH =" for slot in constraints.logical_key)
    axes = (constraints.valid_axis, constraints.transaction_axis)
    ranges = ", ".join(
        f"tstzrange({axis.start.column.name}, {axis.end.column.name}) WITH &&"
        for axis in axes
        if axis is not None
    )
    return f"EXCLUDE USING gist ({key}, {ranges})"


@pytest.mark.parametrize(
    ("model_file", "tables"),
    [
        ("balance.yaml", ("balance",)),
        ("position.yaml", ("position",)),
        ("instrument.yaml", ("instrument",)),
        ("rate.yaml", ("deposit_rate", "loan_rate")),
        ("shared-coverage-layout-twin-document.yaml", ("coverage_ledger", "coverage_span")),
    ],
)
def test_the_catalog_holds_each_named_key_and_immediate_exclusion(
    profile_run: Any, model_file: str, tables: tuple[str, ...]
) -> None:
    model = _provision(profile_run, model_file)
    assert profile_run.port.execute(
        "select extname from pg_extension where extname = %s", ["btree_gist"]
    ) == [("btree_gist",)]
    for table in tables:
        constraints = _constraints(model, table)
        key = ", ".join(slot.column.name for slot in constraints.primary_key.columns)
        rows = profile_run.port.execute(_CONSTRAINTS, [table])
        assert [tuple(row) for row in rows] == [
            (constraints.primary_key_name, "p", f"PRIMARY KEY ({key})", False),
            (constraints.exclusion_name, "x", _exclusion_definition(constraints), False),
        ]


def test_a_non_temporal_table_keeps_its_database_named_key_and_no_exclusion(
    profile_run: Any,
) -> None:
    _provision(profile_run, "payment.yaml")
    rows = profile_run.port.execute(_CONSTRAINTS, ["payment"])
    assert [tuple(row) for row in rows] == [("payment_pkey", "p", "PRIMARY KEY (id)", False)]


def test_an_external_overlapping_insert_is_refused_by_name(profile_run: Any) -> None:
    model = _provision(profile_run, "position.yaml")
    exclusion = _constraints(model, "position").exclusion_name
    profile_run.port.execute_write(_INSERT_POSITION, [1, "A", 1, _MAR, _SEP, _JAN, INFINITY])
    error = _refused(profile_run, _INSERT_POSITION, [1, "A", 2, _JUN, INFINITY, _FEB, INFINITY])

    assert (error.category, error.native_code) == ("constraintViolation", "23P01")
    assert error.constraint_name == exclusion
    assert error.violated_index is None
    assert not error.is_retriable
    assert isinstance(error.__cause__, psycopg.errors.ExclusionViolation)


def test_an_external_update_moving_a_row_into_overlap_is_refused(profile_run: Any) -> None:
    model = _provision(profile_run, "position.yaml")
    profile_run.port.execute_write(_INSERT_POSITION, [1, "A", 1, _JAN, _MAR, _JAN, INFINITY])
    profile_run.port.execute_write(_INSERT_POSITION, [1, "A", 2, _MAR, INFINITY, _JAN, INFINITY])
    error = _refused(
        profile_run,
        "update position set from_z = %s where pos_id = %s and thru_z = %s",
        [_FEB, 1, INFINITY],
    )
    assert error.constraint_name == _constraints(model, "position").exclusion_name


def test_rows_meeting_in_either_period_are_not_an_overlap(profile_run: Any) -> None:
    _provision(profile_run, "position.yaml")
    profile_run.port.execute_write(_INSERT_POSITION, [1, "A", 1, _JAN, _MAR, _JAN, INFINITY])
    profile_run.port.execute_write(_INSERT_POSITION, [1, "A", 2, _MAR, _JUN, _JAN, INFINITY])
    profile_run.port.execute_write(_INSERT_POSITION, [1, "A", 3, _JUN, INFINITY, _JAN, _FEB])
    profile_run.port.execute_write(_INSERT_POSITION, [1, "A", 4, _JUN, INFINITY, _FEB, INFINITY])
    profile_run.port.execute_write(_INSERT_POSITION, [2, "B", 5, _JAN, INFINITY, _JAN, INFINITY])
    assert len(profile_run.port.execute("select t0.pos_id from position t0", [])) == 5


def test_a_shared_table_refuses_overlap_across_subtypes_of_one_key(profile_run: Any) -> None:
    model = _provision(profile_run, "instrument.yaml")
    insert = (
        "insert into instrument (id, kind, price, from_z, thru_z, in_z, out_z) "
        "values (%s, %s, %s, %s, %s, %s, %s)"
    )
    profile_run.port.execute_write(insert, [1, "bond", 1, _JAN, _JUN, _JAN, INFINITY])
    error = _refused(profile_run, insert, [1, "stock", 1, _MAR, INFINITY, _FEB, INFINITY])
    assert error.constraint_name == _constraints(model, "instrument").exclusion_name


def test_each_concrete_table_constrains_only_its_own_rows(profile_run: Any) -> None:
    model = _provision(profile_run, "rate.yaml")
    for table in ("deposit_rate", "loan_rate"):
        profile_run.port.execute_write(
            f"insert into {table} (id, amount, from_z, thru_z, in_z, out_z) "
            "values (%s, %s, %s, %s, %s, %s)",
            [1, 1, _JAN, INFINITY, _JAN, INFINITY],
        )
    error = _refused(
        profile_run,
        "insert into loan_rate (id, amount, from_z, thru_z, in_z, out_z) "
        "values (%s, %s, %s, %s, %s, %s)",
        [1, 2, _MAR, _JUN, _FEB, INFINITY],
    )
    assert error.constraint_name == _constraints(model, "loan_rate").exclusion_name


class Int32Keyed(TxTemporal, table="excl_int32", namespace="temporal.exclusion"):
    id: Attr[int] = attr(primary_key=True, type=Int32)


class Int64Keyed(TxTemporal, table="excl_int64", namespace="temporal.exclusion"):
    id: Attr[int] = attr(primary_key=True)


class StringKeyed(Bitemporal, table="excl_string", namespace="temporal.exclusion"):
    id: Attr[str] = attr(primary_key=True, max_length=16)


class UuidKeyed(Bitemporal, table="excl_uuid", namespace="temporal.exclusion"):
    id: Attr[uuid.UUID] = attr(primary_key=True)


_KEYED = DomainModel(Int32Keyed, Int64Keyed, StringKeyed, UuidKeyed)


@pytest.mark.parametrize(
    ("table", "key", "bitemporal"),
    [
        ("excl_int32", 7, False),
        ("excl_int64", 7, False),
        ("excl_string", "k-7", True),
        ("excl_uuid", uuid.UUID("123e4567-e89b-12d3-a456-426614174000"), True),
    ],
)
def test_every_accepted_key_type_is_excluded_by_equality(
    profile_run: Any, table: str, key: object, bitemporal: bool
) -> None:
    model = model_of(_KEYED)
    profile_run.reset(model, {})
    # The second row ends elsewhere than the first on every axis, so only the
    # exclusion can refuse it.
    columns = "id, from_z, thru_z, in_z, out_z" if bitemporal else "id, in_z, out_z"
    valid: tuple[list[object], list[object]] = (
        ([_JAN, INFINITY], [_MAR, _JUN]) if bitemporal else ([], [])
    )
    marks = ", ".join(["%s"] * (len(valid[0]) + 3))
    insert = f"insert into {table} ({columns}) values ({marks})"
    profile_run.port.execute_write(insert, [key, *valid[0], _JAN, _JUN])
    error = _refused(profile_run, insert, [key, *valid[1], _FEB, INFINITY])
    assert error.constraint_name == _constraints(model, table).exclusion_name


# --------------------------------------------------------------------------- #
# Adopting named keys, checks, and the exclusion on an existing table         #
# --------------------------------------------------------------------------- #
def _legacy(profile_run: Any) -> TemporalHistoryConstraints:
    """A ``position`` table as a release before named temporal keys created it:
    its key named by the database, no checks, no exclusion, and illegal rows."""
    constraints = _constraints(_provision(profile_run, "position.yaml"), "position")
    assert constraints.valid_axis is not None
    for name in (
        constraints.exclusion_name,
        constraints.transaction_axis.interval_check_name,
        constraints.valid_axis.interval_check_name,
    ):
        profile_run.port.execute_write(f"alter table position drop constraint {name}", [])
    profile_run.port.execute_write(
        f"alter table position rename constraint {constraints.primary_key_name} to position_pkey",
        [],
    )
    profile_run.port.execute_write(_INSERT_POSITION, [1, "A", 1, _JAN, INFINITY, _MAR, _FEB])
    profile_run.port.execute_write(_INSERT_POSITION, [2, "B", 1, _JAN, _SEP, _JAN, INFINITY])
    profile_run.port.execute_write(_INSERT_POSITION, [2, "B", 2, _JUN, INFINITY, _FEB, INFINITY])
    return constraints


def _add_exclusion(constraints: TemporalHistoryConstraints, *, not_valid: bool = False) -> str:
    deferral = " not valid" if not_valid else ""
    return (
        f"alter table position add constraint {constraints.exclusion_name} exclude using gist "
        "(pos_id with =, tstzrange(from_z, thru_z) with &&, tstzrange(in_z, out_z) with &&)"
        f"{deferral}"
    )


def test_the_validation_queries_find_every_inverted_and_overlapping_row(
    profile_run: Any,
) -> None:
    _legacy(profile_run)
    inverted = profile_run.port.execute(
        "select pos_id from position where not (in_z < out_z) or not (from_z < thru_z)", []
    )
    assert [row[0] for row in inverted] == [1]
    assert [row[0] for row in profile_run.port.execute(_OVERLAPS, [])] == [2]


def test_an_exclusion_over_an_inverted_interval_cannot_even_form_its_range(
    profile_run: Any,
) -> None:
    constraints = _legacy(profile_run)
    error = _refused(profile_run, _add_exclusion(constraints), [])
    assert (error.category, error.native_code) == (None, "22000")


def test_an_exclusion_over_overlapping_rows_fails_and_adds_nothing(profile_run: Any) -> None:
    constraints = _legacy(profile_run)
    profile_run.port.execute_write("delete from position where pos_id = %s", [1])
    error = _refused(profile_run, _add_exclusion(constraints), [])
    assert (error.category, error.native_code) == ("constraintViolation", "23P01")
    assert error.constraint_name == constraints.exclusion_name
    assert [row[1] for row in profile_run.port.execute(_CONSTRAINTS, ["position"])] == ["p"]


def test_an_exclusion_cannot_be_staged_unvalidated(profile_run: Any) -> None:
    constraints = _legacy(profile_run)
    error = _refused(profile_run, _add_exclusion(constraints, not_valid=True), [])
    assert error.native_code == "0A000"


def test_the_documented_migration_reaches_the_generated_catalog(profile_run: Any) -> None:
    constraints = _legacy(profile_run)
    assert constraints.valid_axis is not None
    profile_run.port.execute_write("update position set out_z = %s where pos_id = %s", [_APR, 1])
    profile_run.port.execute_write(
        "update position set thru_z = %s where pos_id = %s and val = %s", [_JUN, 2, 1]
    )
    assert profile_run.port.execute(_OVERLAPS, []) == []
    for statement in (
        f"alter table position rename constraint position_pkey to {constraints.primary_key_name}",
        f"alter table position add constraint {constraints.transaction_axis.interval_check_name} "
        "check (in_z < out_z)",
        f"alter table position add constraint {constraints.valid_axis.interval_check_name} "
        "check (from_z < thru_z)",
        "create extension if not exists btree_gist",
        _add_exclusion(constraints),
    ):
        profile_run.port.execute_write(statement, [])
    rows = profile_run.port.execute(_CONSTRAINTS, ["position"])
    assert [tuple(row) for row in rows] == [
        (constraints.primary_key_name, "p", "PRIMARY KEY (pos_id, thru_z, out_z)", False),
        (constraints.exclusion_name, "x", _exclusion_definition(constraints), False),
    ]
