"""Generated temporal interval checks on a real PostgreSQL (m-storage-layout / m-db-error).

Provisioning goes through the shipped Schema Delta, so the catalog these tests
read is the one every database-backed suite runs against. Writes here are raw
statements from outside Parallax: the checks govern every writer of the table.
The adoption tests run the manual migration the PostgreSQL lifecycle guide
documents against a table provisioned without its checks.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest

from parallax.conformance import models, provision
from parallax.conformance.models import default_models_dir
from parallax.core import storage_layout
from parallax.core.base import INFINITY
from parallax.core.db_error import DatabaseError
from parallax.core.metamodel import Metamodel, Table
from parallax.core.storage_layout import TemporalHistoryConstraints

_JAN = datetime(2024, 1, 1, tzinfo=UTC)
_FEB = datetime(2024, 2, 1, tzinfo=UTC)
_MAR = datetime(2024, 3, 1, tzinfo=UTC)

_INSERT_POSITION = (
    "insert into position (pos_id, acct_num, val, from_z, thru_z, in_z, out_z) "
    "values (%s, %s, %s, %s, %s, %s, %s)"
)
_CHECKS = (
    "select t0.conname, pg_get_constraintdef(t0.oid), t0.convalidated "
    "from pg_constraint t0 join pg_class t1 on t1.oid = t0.conrelid "
    "where t1.relname = %s and t0.contype = 'c' order by t0.conname"
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


def _names(model: Metamodel, table: str) -> tuple[str, str]:
    constraints = _constraints(model, table)
    assert constraints.valid_axis is not None
    return (
        constraints.transaction_axis.interval_check_name,
        constraints.valid_axis.interval_check_name,
    )


def _refused(profile_run: Any, sql: str, binds: list[object]) -> DatabaseError:
    with pytest.raises(DatabaseError) as raised:
        profile_run.port.execute_write(sql, binds)
    return raised.value


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
def test_the_catalog_holds_each_axis_check_under_its_compiled_name(
    profile_run: Any, model_file: str, tables: tuple[str, ...]
) -> None:
    model = _provision(profile_run, model_file)
    for table in tables:
        constraints = _constraints(model, table)
        expected = [
            (constraints.transaction_axis.interval_check_name, "CHECK ((in_z < out_z))", True)
        ]
        if constraints.valid_axis is not None:
            expected.append(
                (constraints.valid_axis.interval_check_name, "CHECK ((from_z < thru_z))", True)
            )
        rows = profile_run.port.execute(_CHECKS, [table])
        assert sorted(tuple(row) for row in rows) == sorted(expected)


def test_a_non_temporal_table_holds_no_check(profile_run: Any) -> None:
    _provision(profile_run, "payment.yaml")
    assert profile_run.port.execute(_CHECKS, ["payment"]) == []


@pytest.mark.parametrize(
    ("from_z", "thru_z", "in_z", "out_z", "axis"),
    [
        (_JAN, INFINITY, _FEB, _FEB, "tx"),
        (_JAN, INFINITY, _MAR, _FEB, "tx"),
        (_FEB, _FEB, _JAN, INFINITY, "valid"),
        (_MAR, _FEB, _JAN, INFINITY, "valid"),
    ],
    ids=["empty-tx", "inverted-tx", "empty-valid", "inverted-valid"],
)
def test_an_external_write_of_an_empty_or_inverted_interval_is_refused_by_name(
    profile_run: Any,
    from_z: object,
    thru_z: object,
    in_z: object,
    out_z: object,
    axis: str,
) -> None:
    model = _provision(profile_run, "position.yaml")
    tx, valid = _names(model, "position")
    error = _refused(profile_run, _INSERT_POSITION, [1, "A", 1, from_z, thru_z, in_z, out_z])

    assert (error.category, error.native_code) == ("constraintViolation", "23514")
    assert error.constraint_name == (tx if axis == "tx" else valid)
    assert error.violated_index is None
    assert not error.is_retriable
    assert isinstance(error.__cause__, psycopg.errors.CheckViolation)
    assert profile_run.port.execute("select t0.pos_id from position t0", []) == []


def test_an_update_that_closes_a_row_at_its_own_start_is_refused(profile_run: Any) -> None:
    model = _provision(profile_run, "balance.yaml")
    profile_run.port.execute_write(
        "insert into balance (bal_id, acct_num, val, in_z, out_z) values (%s, %s, %s, %s, %s)",
        [1, "A", 1, _FEB, INFINITY],
    )
    error = _refused(
        profile_run,
        "update balance set out_z = %s where bal_id = %s and out_z = %s",
        [_FEB, 1, INFINITY],
    )
    assert (
        error.constraint_name == _constraints(model, "balance").transaction_axis.interval_check_name
    )


# --------------------------------------------------------------------------- #
# Adopting the checks on a table that existed before them                     #
# --------------------------------------------------------------------------- #
def _without_checks(profile_run: Any) -> tuple[str, str]:
    """A ``position`` table as an earlier release created it, holding bad rows.

    That release generated neither the checks nor the exclusion, whose ranges
    could not even be formed over an inverted interval.
    """
    model = _provision(profile_run, "position.yaml")
    tx, valid = _names(model, "position")
    exclusion = _constraints(model, "position").exclusion_name
    for name in (exclusion, tx, valid):
        profile_run.port.execute_write(f"alter table position drop constraint {name}", [])
    profile_run.port.execute_write(_INSERT_POSITION, [1, "A", 1, _JAN, INFINITY, _MAR, _FEB])
    profile_run.port.execute_write(_INSERT_POSITION, [2, "B", 1, _FEB, _FEB, _JAN, INFINITY])
    profile_run.port.execute_write(_INSERT_POSITION, [3, "C", 1, _JAN, _FEB, _JAN, INFINITY])
    return tx, valid


def test_the_validation_queries_find_every_row_a_check_would_refuse(profile_run: Any) -> None:
    _without_checks(profile_run)
    transaction = profile_run.port.execute(
        "select pos_id, in_z, out_z from position where not (in_z < out_z)", []
    )
    valid = profile_run.port.execute(
        "select pos_id, from_z, thru_z from position where not (from_z < thru_z)", []
    )
    assert [row[0] for row in transaction] == [1]
    assert [row[0] for row in valid] == [2]


def test_adding_a_check_over_a_refused_row_fails_and_adds_nothing(profile_run: Any) -> None:
    tx, _valid = _without_checks(profile_run)
    error = _refused(
        profile_run, f"alter table position add constraint {tx} check (in_z < out_z)", []
    )
    assert (error.category, error.constraint_name) == ("constraintViolation", tx)
    assert profile_run.port.execute(_CHECKS, ["position"]) == []


def test_a_staged_check_governs_new_writes_and_validates_once_the_rows_are_corrected(
    profile_run: Any,
) -> None:
    tx, valid = _without_checks(profile_run)
    profile_run.port.execute_write(
        f"alter table position add constraint {tx} check (in_z < out_z) not valid", []
    )
    profile_run.port.execute_write(
        f"alter table position add constraint {valid} check (from_z < thru_z) not valid", []
    )
    assert sorted(tuple(row) for row in profile_run.port.execute(_CHECKS, ["position"])) == [
        (tx, "CHECK ((in_z < out_z)) NOT VALID", False),
        (valid, "CHECK ((from_z < thru_z)) NOT VALID", False),
    ]

    fresh = _refused(profile_run, _INSERT_POSITION, [4, "D", 1, _JAN, INFINITY, _FEB, _FEB])
    assert fresh.constraint_name == tx
    stored = _refused(profile_run, f"alter table position validate constraint {tx}", [])
    assert (stored.category, stored.constraint_name) == ("constraintViolation", tx)

    profile_run.port.execute_write("update position set in_z = %s where pos_id = %s", [_JAN, 1])
    profile_run.port.execute_write("delete from position where pos_id = %s", [2])
    profile_run.port.execute_write(f"alter table position validate constraint {tx}", [])
    profile_run.port.execute_write(f"alter table position validate constraint {valid}", [])
    assert sorted(tuple(row) for row in profile_run.port.execute(_CHECKS, ["position"])) == [
        (tx, "CHECK ((in_z < out_z))", True),
        (valid, "CHECK ((from_z < thru_z))", True),
    ]
