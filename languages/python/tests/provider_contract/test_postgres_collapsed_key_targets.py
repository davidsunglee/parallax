"""Collapsed key targets against a real server (`m-batch-write` *Set-based
flush*, `m-sql` *Batched insert / update*, `m-dialect` *Bind parameter limit*).

A uniform run of unversioned updates or deletes stays one Planned Step and one
statement however many keys it holds, and PostgreSQL receives its key
membership as one array per key Column. What a scripted port cannot establish
is here: that a membership wider than the protocol's 65,535 parameters executes
and changes exactly the rows it names, and that a several-Column key's arrays
select only the rows whose whole key they list.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Final

import pytest

from parallax.conformance._lifecycle_recording import RecordingLifecycleProvider
from parallax.core import Attr, DomainModel, Entity, attr
from parallax.core._execution._write_lowering import lowered
from parallax.core.base import INT64, STRING
from parallax.core.db_port import ArrayBind
from parallax.core.entity._model import model_of
from parallax.core.execution_lifecycle import DatabaseCallStarted
from parallax.core.metamodel import AttributeIdentity
from parallax.core.write_payload import LayoutPayloadPreparer
from parallax.core.write_plan.steps import (
    MISSING_TARGET,
    UNVERSIONED,
    ExactCount,
    KeyTarget,
    PlannedAssignments,
    PlannedDelete,
    PlannedStep,
    PlannedUpdate,
)
from parallax.snapshot import ScopedDatabase, TxnContext, connect
from tests._support.root_ownership import own_root


class Purse(Entity, table="ckt_purse", namespace="collapsed.key.targets"):
    id: Attr[int] = attr(primary_key=True)
    owner: Attr[str] = attr(max_length=16)
    balance: Attr[Decimal] = attr(precision=18, scale=2)


_MODEL: Final = DomainModel(Purse)
_META: Final = model_of(_MODEL)
_WIDE: Final = 70_001
"""More keys than the protocol's 65,535 parameters could bind one by one."""


def _seeded(profile_run: Any) -> None:
    profile_run.reset(_META, {})
    profile_run.port.execute_write(
        "insert into ckt_purse(id, owner, balance) "
        "select key, 'o' || key, 1.00 from generate_series(1, %s) key",
        [_WIDE],
    )


def _database(profile_run: Any, provider: RecordingLifecycleProvider) -> ScopedDatabase:
    return own_root(
        connect(profile_run.port, _MODEL, lifecycle_provider=provider)
    ).using_database_login()


def _writes(provider: RecordingLifecycleProvider) -> list[DatabaseCallStarted]:
    return [
        event
        for root in provider.roots
        for event in root.events
        if isinstance(event, DatabaseCallStarted) and event.kind == "write"
    ]


def _scalar(profile_run: Any, sql: str) -> object:
    ((value,),) = profile_run.port.execute(sql, [])
    return value


def test_a_collapsed_update_and_delete_wider_than_the_parameter_limit_each_run_once(
    profile_run: Any,
) -> None:
    _seeded(profile_run)
    provider = RecordingLifecycleProvider()
    db = _database(profile_run, provider)
    keys: list[object] = list(range(1, _WIDE + 1))

    def amend(tx: TxnContext) -> None:
        for purse in tx.find(Purse.where(Purse.id >= 1)).results():
            tx.amend(purse.edit(balance=Decimal("9.50")))

    db.transact(amend)
    (update,) = _writes(provider)
    assert update.statement.sql == (
        "update ckt_purse set balance = ? where id = any(cast(? as bigint[]))"
    )
    assert update.statement.binds == (Decimal("9.50"), ArrayBind(INT64, keys))
    assert _scalar(profile_run, "select count(*) from ckt_purse where balance = 9.50") == _WIDE

    def delete(tx: TxnContext) -> None:
        for purse in tx.find(Purse.where(Purse.id >= 1)).results():
            tx.delete(purse)

    db.transact(delete)
    _update, removal = _writes(provider)
    assert removal.statement.sql == "delete from ckt_purse where id = any(cast(? as bigint[]))"
    assert removal.statement.binds == (ArrayBind(INT64, keys),)
    assert _scalar(profile_run, "select count(*) from ckt_purse") == 0


_ID: Final = AttributeIdentity(Purse.identity, "id")
_OWNER: Final = AttributeIdentity(Purse.identity, "owner")


def _composite(*keys: tuple[int, str]) -> KeyTarget:
    return KeyTarget((_ID, _OWNER), keys)


def _execute(profile_run: Any, step: PlannedStep) -> int:
    port = profile_run.port
    dialect = port.dialect
    statement = lowered(step, LayoutPayloadPreparer(_META), _META, dialect)
    assert len(statement.binds) == (3 if isinstance(step, PlannedUpdate) else 2)
    return port.execute_write(dialect.to_driver_sql(statement.sql), list(statement.binds))


@pytest.mark.parametrize("width", [3, _WIDE])
def test_a_several_column_key_membership_selects_only_rows_whose_whole_key_it_lists(
    profile_run: Any, width: int
) -> None:
    # A composite primary key never forms (`metamodel-primary-key-multiple`), so
    # the several-Column target is built by hand over the key and `owner`: every
    # even key lists an owner its row does not hold, so only odd rows match.
    _seeded(profile_run)
    listed = tuple((key, f"o{key}" if key % 2 else "other") for key in range(1, width + 1))
    matching = (width + 1) // 2
    update = PlannedUpdate(
        entity=Purse.identity,
        target=_composite(*listed),
        assignments=PlannedAssignments(
            attributes={AttributeIdentity(Purse.identity, "balance"): Decimal("7.25")}
        ),
        concurrency=UNVERSIONED,
        affected_rows=ExactCount(width, MISSING_TARGET),
    )
    statement = lowered(update, LayoutPayloadPreparer(_META), _META, profile_run.port.dialect)
    assert statement.sql == (
        "update ckt_purse set balance = ? where (id, owner) in "
        "(select * from unnest(cast(? as bigint[]), cast(? as text[])))"
    )
    assert statement.binds[1:] == (
        ArrayBind(INT64, [key for key, _owner in listed]),
        ArrayBind(STRING, [owner for _key, owner in listed]),
    )

    assert _execute(profile_run, update) == matching
    assert _scalar(profile_run, "select count(*) from ckt_purse where balance = 7.25") == matching
    unlisted = f"(mod(id, 2) = 0 or id > {width})"
    assert (
        _scalar(profile_run, f"select count(*) from ckt_purse where balance = 7.25 and {unlisted}")
        == 0
    )

    delete = PlannedDelete(
        entity=Purse.identity,
        target=_composite(*listed),
        concurrency=UNVERSIONED,
        affected_rows=ExactCount(width, MISSING_TARGET),
    )
    assert _execute(profile_run, delete) == matching
    assert _scalar(profile_run, "select count(*) from ckt_purse") == _WIDE - matching
    assert _scalar(profile_run, "select count(*) from ckt_purse where balance = 7.25") == 0
