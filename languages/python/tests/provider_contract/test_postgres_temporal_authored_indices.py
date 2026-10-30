"""Authored indices on temporal tables on a real PostgreSQL (m-storage-layout / m-schema-delta).

Provisioning goes through the shipped Schema Delta, and writes go through the
public verbs. Every authored index of a temporal table ends with the table's
axis ends, so an amend that keeps an authored unique value chains its successor,
while a genuine duplicate is still refused under the name the rollout recorded.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from typing import Any, Final

import pytest

from parallax.conformance.scripted_clock import ScriptedClock
from parallax.core import Attr, Bitemporal, DomainModel, TxTemporal, attr, index
from parallax.core.db_error import DatabaseError
from parallax.core.dialect import POSTGRES
from parallax.core.entity._model import model_of
from parallax.core.execution import ExecutionFailure
from parallax.evolution import SchemaDelta, schema_delta
from parallax.evolution.model_evolution import ABSENT, evolve
from parallax.snapshot import ScopedDatabase, TxnContext, connect
from tests._support.root_ownership import own_root

_NAMESPACE: Final = "temporal.authored.index"


class Ledger(
    TxTemporal,
    table="tai_ledger",
    namespace=_NAMESPACE,
    indices=(index("tai_ledger_code", "code", unique=True), index("tai_ledger_label", "label")),
):
    id: Attr[int] = attr(primary_key=True)
    code: Attr[str] = attr(max_length=16)
    label: Attr[str] = attr(max_length=16)


class Tenancy(
    Bitemporal,
    table="tai_tenancy",
    namespace=_NAMESPACE,
    indices=(index("tai_tenancy_code", "code", unique=True), index("tai_tenancy_label", "label")),
):
    id: Attr[int] = attr(primary_key=True)
    code: Attr[str] = attr(max_length=16)
    label: Attr[str] = attr(max_length=16)
    rent: Attr[int]


_MODEL: Final = DomainModel(Ledger, Tenancy)

_JAN, _MAR, _JUN, _JUL = (dt.datetime(2024, month, 1, tzinfo=dt.UTC) for month in (1, 3, 6, 7))

_INDEX_COLUMNS: Final = (
    "select i.relname, x.indisunique, "
    "array(select a.attname from unnest(x.indkey) with ordinality as k(attnum, n) "
    "join pg_attribute a on a.attrelid = x.indrelid and a.attnum = k.attnum order by k.n) "
    "from pg_index x join pg_class i on i.oid = x.indexrelid "
    "join pg_class t on t.oid = x.indrelid where t.relname = %s and i.relname = %s"
)


def _provision(profile_run: Any) -> SchemaDelta:
    """Provision through the shipped Schema Delta and answer that rollout."""
    model = model_of(_MODEL)
    profile_run.reset(model, {})
    return schema_delta(evolve(ABSENT, model), POSTGRES)


def _db(profile_run: Any, instants: Sequence[dt.datetime]) -> ScopedDatabase:
    return own_root(
        connect(profile_run.port, _MODEL, clock=ScriptedClock(list(instants)))
    ).using_database_login()


def _created(rollout: SchemaDelta, name: str) -> tuple[str, str]:
    (created,) = (
        entry for entry in rollout.created_indices if entry.logical_index_identity.name == name
    )
    return created.physical_table.name, created.physical_index_name.value


def _refused(db: ScopedDatabase, work: Callable[[TxnContext], None]) -> DatabaseError:
    with pytest.raises(ExecutionFailure) as failure:
        db.transact(work)
    cause = failure.value.cause
    assert isinstance(cause, DatabaseError)
    return cause


def _rows(profile_run: Any, sql: str, binds: Sequence[object] = ()) -> list[tuple[object, ...]]:
    return [tuple(row) for row in profile_run.port.execute(sql, list(binds))]


@pytest.mark.parametrize(
    ("name", "unique", "columns"),
    [
        ("tai_ledger_code", True, ["code", "out_z"]),
        ("tai_ledger_label", False, ["label", "out_z"]),
        ("tai_tenancy_code", True, ["code", "thru_z", "out_z"]),
        ("tai_tenancy_label", False, ["label", "thru_z", "out_z"]),
    ],
)
def test_the_catalog_holds_each_authored_index_ending_with_the_axis_ends(
    profile_run: Any, name: str, unique: bool, columns: list[str]
) -> None:
    table, physical = _created(_provision(profile_run), name)
    assert _rows(profile_run, _INDEX_COLUMNS, [table, physical]) == [(physical, unique, columns)]


def test_a_transaction_time_amend_keeping_its_unique_value_chains_its_successor(
    profile_run: Any,
) -> None:
    _provision(profile_run)
    db = _db(profile_run, [_JAN, _JUN])
    db.transact(lambda tx: tx.insert(Ledger(id=1, code="X", label="a")))
    db.transact(lambda tx: tx.amend(tx.find(Ledger.where(Ledger.id == 1)).result().edit(label="b")))
    assert _rows(
        profile_run,
        "select id, code, label, in_z, out_z = 'infinity' from tai_ledger order by in_z",
    ) == [(1, "X", "a", _JAN, False), (1, "X", "b", _JUN, True)]


def test_a_bitemporal_split_keeping_its_unique_value_chains_both_successors(
    profile_run: Any,
) -> None:
    _provision(profile_run)
    db = _db(profile_run, [_JAN, _JUL])
    db.transact(lambda tx: tx.insert(Tenancy(id=1, code="Y", label="a", rent=100), valid_from=_JAN))
    db.transact(
        lambda tx: tx.amend(
            tx.find(Tenancy.where(Tenancy.id == 1).as_of(valid_time=_JUN)).result().edit(rent=200)
        )
    )
    assert _rows(
        profile_run,
        "select code, rent, from_z, thru_z = 'infinity', in_z, out_z = 'infinity' "
        "from tai_tenancy order by in_z, from_z",
    ) == [
        ("Y", 100, _JAN, True, _JAN, False),
        ("Y", 100, _JAN, False, _JUL, True),
        ("Y", 200, _JUN, True, _JUL, True),
    ]


def test_a_duplicate_current_value_names_the_authored_index_the_rollout_created(
    profile_run: Any,
) -> None:
    rollout = _provision(profile_run)
    db = _db(profile_run, [_JAN, _MAR])
    db.transact(lambda tx: tx.insert(Ledger(id=1, code="X", label="a")))
    error = _refused(db, lambda tx: tx.insert(Ledger(id=2, code="X", label="b")))
    assert (error.category, error.native_code) == ("uniqueViolation", "23505")
    assert error.violated_index is not None
    assert error.violated_index.value == _created(rollout, "tai_ledger_code")[1]


def test_a_duplicate_at_one_milestone_end_names_the_authored_index_the_rollout_created(
    profile_run: Any,
) -> None:
    rollout = _provision(profile_run)
    db = _db(profile_run, [_JAN, _MAR])
    db.transact(lambda tx: tx.insert(Tenancy(id=1, code="Y", label="a", rent=1), valid_from=_JAN))
    error = _refused(
        db, lambda tx: tx.insert(Tenancy(id=2, code="Y", label="b", rent=2), valid_from=_MAR)
    )
    assert (error.category, error.native_code) == ("uniqueViolation", "23505")
    assert error.violated_index is not None
    assert error.violated_index.value == _created(rollout, "tai_tenancy_code")[1]
