"""Shared fixtures for the `parallax.snapshot.handle` transaction suites.

The recording fake `m-db-port`, the two `Database` builders over it, the mirrored
model handles, and the SQL/row goldens that more than one successor suite drives.
Split out of `test_transact.py` in COR-42 Phase 5, when that file became four.

Exported names carry no leading underscore: importing an underscored name across
modules is a `reportPrivateUsage` error under pyright strict, so privacy is
carried by this MODULE's underscore — the same convention the private
`parallax.snapshot.handle` modules follow. Never imported by production code.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Final, cast

import mirrored_models as mm
from parallax.conformance import models
from parallax.core import AsOfAttribute, Attr, Entity, EntityConfig, Field
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import Bind, DbPort, Row
from parallax.core.descriptor import Metamodel
from parallax.core.dialect import POSTGRES
from parallax.core.entity import metamodel
from parallax.core.unit_work import FixedClock
from parallax.snapshot import connect
from parallax.snapshot.handle import Database

__all__ = [
    "ACCOUNT",
    "BALANCE",
    "CONTACT",
    "FIND_SQL",
    "FIND_SQL_NO_LOCK",
    "FIXED",
    "INFINITY_INSTANT",
    "INSERT_SQL",
    "NEW_ROW",
    "ORDERS",
    "PAYMENT",
    "PERSON",
    "PERSON_MIRROR_META",
    "SHIPMENT",
    "WHERE_POSITION_META",
    "NoIoPort",
    "RecordingPort",
    "WherePosition",
    "account_db",
    "balance_row",
    "db_for",
    "deadlock",
    "grace",
    "new_account",
]


_MODELS = models.load_models()
ACCOUNT = _MODELS["account"]
BALANCE = _MODELS["balance"]
CONTACT = _MODELS["contact"]
SHIPMENT = _MODELS["shipment"]
PAYMENT = _MODELS["payment"]
PERSON = _MODELS["person"]
ORDERS = _MODELS["orders"]


FIXED = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


# A LOCAL bitemporal entity — the `_where`-verb materialization tests' own
# bounded/plain rectangle-split fixture. `models/position.yaml` DOES have a
# shared mirror now (`parallax.conformance.story_models.Position`, installed by
# D-31), but it is not a drop-in: it maps to table `position` with columns
# `pos_id`/`val`, while the assertions below pin emitted SQL against
# `where_position`/`id`/`value`. Swapping would rewrite every one of them for no
# gain, so the local fixture stays.
class WherePosition(Entity, frozen=True):
    __parallax__ = EntityConfig(
        table="where_position",
        namespace="parallax.compatibility",
        mutability="transactional",
        as_of=(
            AsOfAttribute(
                name="businessDate", from_column="from_z", to_column="thru_z", axis="business"
            ),
            AsOfAttribute(
                name="processingDate", from_column="in_z", to_column="out_z", axis="processing"
            ),
        ),
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    acct_num: Attr[str] = Field(max_length=32)
    value: Attr[Decimal] = Field(type="decimal(18,2)")
    business_from: Attr[dt.datetime] = Field(column="from_z")
    business_to: Attr[dt.datetime] = Field(column="thru_z")
    processing_from: Attr[dt.datetime] = Field(column="in_z")
    processing_to: Attr[dt.datetime] = Field(column="out_z")


WHERE_POSITION_META = metamodel([WherePosition])


NEW_ROW: Row = {"id": 7, "owner": "Newton", "balance": 5.00, "version": 1}


def new_account() -> mm.Account:
    return mm.Account(id=7, owner="Newton", balance=Decimal("5.00"), version=1)


def grace() -> mm.Account:
    return mm.Account(id=3, owner="Grace", balance=Decimal("10.00"), version=1)


# The m-unit-work-001 goldens, rendered to driver SQL as the port receives them.
INSERT_SQL = POSTGRES.to_driver_sql(
    "insert into account(id, owner, balance, version) values (?, ?, ?, ?)"
)


FIND_SQL = POSTGRES.to_driver_sql(
    "select t0.id, t0.owner, t0.balance, t0.version from account t0 where t0.id = ? for share of t0"
)


FIND_SQL_NO_LOCK = POSTGRES.to_driver_sql(
    "select t0.id, t0.owner, t0.balance, t0.version from account t0 where t0.id = ?"
)


def deadlock() -> DatabaseError:
    return DatabaseError(category="deadlock", native_code="40P01", message="deadlock detected")


class RecordingPort:
    """An in-memory ``m-db-port`` recording every call in order (no Docker).

    ``txn_faults`` raises at the next ``transaction`` entries (a driver failure
    the adapter translated and rolled back); ``read_faults`` raises from the
    next ``execute`` calls (a failure inside the transaction body).
    ``write_affected_queue`` (COR-3 Phase 8 increment 6) scripts a SEQUENCE of
    affected-row counts across successive ``execute_write`` calls — an
    optimistic-lock retry-loop probe's own oracle: attempt 0's gated UPDATE
    affects ``0`` (the conflict), a retried attempt's affects ``1`` (success) —
    falling back to the constant ``write_affected`` once exhausted (or when
    never set, unaffected — every existing single-affected-count caller is
    unchanged).
    """

    def __init__(self, *, rows: Sequence[Row] = (), write_affected: int = 1) -> None:
        self.ops: list[tuple[object, ...]] = []
        self.rows = list(rows)
        self.write_affected = write_affected
        self.write_affected_queue: list[int] = []
        self.txn_faults: list[DatabaseError] = []
        self.read_faults: list[DatabaseError] = []

    def execute(self, sql: str, binds: Sequence[Bind]) -> list[Row]:
        if self.read_faults:
            raise self.read_faults.pop(0)
        self.ops.append(("read", sql, tuple(binds)))
        return [dict(row) for row in self.rows]

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        self.ops.append(("write", sql, tuple(binds)))
        if self.write_affected_queue:
            return self.write_affected_queue.pop(0)
        return self.write_affected

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:
        self.ops.append(("begin",))
        if self.txn_faults:
            self.ops.append(("rollback",))
            raise self.txn_faults.pop(0)
        try:
            result = body(self)
        except BaseException:
            self.ops.append(("rollback",))
            raise
        self.ops.append(("commit",))
        return result

    @property
    def begins(self) -> int:
        return sum(1 for op in self.ops if op == ("begin",))


def account_db(port: RecordingPort) -> Database:
    # The spec §8 module-level `connect` is the classmethod's alias, so this
    # covers both spellings.
    return connect(port, ACCOUNT, clock=FixedClock(FIXED))


def db_for(meta: Metamodel, port: RecordingPort) -> Database:
    return Database.connect(port, meta, clock=FixedClock(FIXED))


# --------------------------------------------------------------------------- #
# Phase-8 mid-phase review remediation, finding B: `Transaction.find` records #
# a TEMPORAL observation (not just a versioned one) so a locking-mode write's #
# historical-observation license (`m-opt-lock`) is REAL, not a permanent      #
# no-op — exercised through the typed `tx.terminate` verb (COR-3 Phase 8      #
# increment 7), the SAME `_buffer` neutral seam the conformance engine uses.  #
# --------------------------------------------------------------------------- #
INFINITY_INSTANT: Final[dt.datetime] = dt.datetime(9999, 12, 31, tzinfo=dt.UTC)


def balance_row(*, in_z: dt.datetime, out_z: dt.datetime = INFINITY_INSTANT) -> Row:
    return {
        "bal_id": 1,
        "acct_num": "A-1",
        "val": Decimal("5.00"),
        "in_z": in_z,
        "out_z": out_z,
    }


# A minimal `DbPort` that raises if the connection is ever touched — the harness
# behind every "the guard runs BEFORE any I/O" pin. Shared by the keyed and
# predicate suites, so it lives here rather than in either one.
class NoIoPort:
    """A minimal ``DbPort`` that raises if the connection is ever touched."""

    def execute(self, sql: str, binds: Sequence[Bind]) -> list[Row]:
        raise AssertionError("no read expected — the guard runs first")

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        raise AssertionError("no write expected — the guard runs first")

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:
        return body(cast("DbPort", self))


# The mirrored-model metamodel those guard pins target — distinct from `PERSON`
# above, which is the corpus `models/person.yaml` handle.
PERSON_MIRROR_META = metamodel([mm.Person, mm.Passport])
