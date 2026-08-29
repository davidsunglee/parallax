"""Shared fixtures for the `parallax.snapshot.handle` transaction suites.

The two `Database` builders over a port, the mirrored model handles, and the
SQL/row goldens that more than one suite drives. Shared by
`test_database_transact.py` and the three `test_transaction_*.py` suites, split
apart by observable behavior. The ports themselves come from
`_support.db_port`.

Exported names carry no leading underscore: importing an underscored name across
modules is a `reportPrivateUsage` error under pyright strict, so privacy is
carried by this MODULE's underscore — the same convention the private
`parallax.snapshot.handle` modules follow. Never imported by production code.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from decimal import Decimal
from typing import Final, cast

from _support import mirrored_models as mm
from parallax.conformance.class_models import MODELS
from parallax.core import Attr, Bitemporal, DomainModel, attr
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import (
    DbPort,
    Row,
)
from parallax.core.dialect import POSTGRES
from parallax.core.unit_work import FixedClock, RetainedObservation
from parallax.snapshot import InvalidData, connect
from parallax.snapshot.handle import Database, Snapshot
from parallax.snapshot.materialize import WireEntity, source_hint_of

__all__ = [
    "ACCOUNT",
    "BALANCE",
    "CONTACT",
    "FIND_SQL_LOCKED",
    "FIND_SQL_UNLOCKED",
    "FIXED",
    "INFINITY_INSTANT",
    "INSERT_SQL",
    "NEW_ROW",
    "ORDERS",
    "PAYMENT",
    "PERSON",
    "RATE",
    "SHIPMENT",
    "WHERE_POSITION_META",
    "WherePosition",
    "account_db",
    "balance_row",
    "db_for",
    "deadlock",
    "grace",
    "new_account",
    "published_claims",
]


ACCOUNT = MODELS["account"]
BALANCE = MODELS["balance"]
CONTACT = MODELS["contact"]
SHIPMENT = MODELS["shipment"]
PAYMENT = MODELS["payment"]
PERSON = MODELS["person"]
ORDERS = MODELS["orders"]
# The BITEMPORAL inheritance family (`models/rate.yaml`, table-per-concrete-
# subtype): the only corpus model whose target both participates in a family
# AND materializes, so a predicate write on it takes the resolving-read route
# rather than the readless one `payment.yaml` takes.
RATE = MODELS["rate"]


FIXED = dt.datetime(2024, 6, 1, tzinfo=dt.UTC)


# A LOCAL bitemporal entity — the `_where`-verb materialization tests' own
# bounded/plain rectangle-split fixture. `models/position.yaml` DOES have a
# shared mirror now (`parallax.conformance.story_models.Position`), but it is
# not a drop-in: it maps to table `position` with columns
# `pos_id`/`val`, while the assertions below pin emitted SQL against
# `where_position`/`id`/`value`. Swapping would rewrite every one of them for no
# gain, so the local fixture stays.
class WherePosition(Bitemporal, table="where_position", namespace="parallax.compatibility"):
    id: Attr[int] = attr(primary_key=True)
    acct_num: Attr[str] = attr(max_length=32)
    value: Attr[Decimal] = attr(precision=18, scale=2)


WHERE_POSITION_META = DomainModel(WherePosition)


NEW_ROW: Row = {"id": 7, "owner": "Newton", "balance": Decimal("5.00"), "version": 1}


def new_account() -> mm.Account:
    # No `version=`: the version is framework-owned, so an insert derives the
    # initial value and the constructor refuses a caller-supplied one.
    return mm.Account(id=7, owner="Newton", balance=Decimal("5.00"))


def read_account() -> mm.Account:
    """``new_account()`` as a read hands it back — the same row carrying the
    version the write derived, which only hydration can put on an instance."""
    return mm.Account.model_construct(id=7, owner="Newton", balance=Decimal("5.00"), version=1)


def grace() -> mm.Account:
    return mm.Account.model_construct(id=3, owner="Grace", balance=Decimal("10.00"), version=1)


# The m-unit-work-001 goldens, rendered to driver SQL as the port receives them.
INSERT_SQL = POSTGRES.to_driver_sql(
    "insert into account(id, owner, balance, version) values (?, ?, ?, ?)"
)


# `Account` declares an explicit version, so a participating find of one takes
# the shared lock only under the `locking` preference; the default `optimistic`
# preference resolves it to the Optimistic strategy, whose gate is the authority.
FIND_SQL_LOCKED = POSTGRES.to_driver_sql(
    "select t0.id, t0.owner, t0.balance, t0.version from account t0 where t0.id = ? for share of t0"
)


FIND_SQL_UNLOCKED = POSTGRES.to_driver_sql(
    "select t0.id, t0.owner, t0.balance, t0.version from account t0 where t0.id = ?"
)


def deadlock() -> DatabaseError:
    return DatabaseError(category="deadlock", native_code="40P01", message="deadlock detected")


def account_db(port: DbPort) -> Database:
    # The spec §8 module-level `connect` is the classmethod's alias, so this
    # covers both spellings.
    return connect(port, ACCOUNT, clock=FixedClock(FIXED))


def db_for(meta: DomainModel, port: DbPort) -> Database:
    return Database.connect(port, meta, clock=FixedClock(FIXED))


def published_claims(snapshot: Snapshot[WireEntity]) -> tuple[RetainedObservation, ...]:
    """The retained claims the Entity nodes ``snapshot`` PUBLISHED carry, each
    once, in the order the walk reaches them.

    What a first-party holder of a Wire result reads off `source_hint_of`, and
    the same walk the conformance engine runs over a grouped find's own output.
    Publication is what settles ownership: a claim belongs to a value a caller
    was handed, so a projection no published root reaches contributes none. A
    frozen Wire node is a ``dict`` and therefore unhashable, which is why the
    visited set is identity-keyed over objects the Snapshot holds throughout.
    """
    claims: list[RetainedObservation] = []
    visited: set[int] = set()
    frontier: list[object] = list(snapshot.checked().results())
    cursor = 0
    while cursor < len(frontier):
        value = frontier[cursor]
        cursor += 1
        if isinstance(value, InvalidData):
            frontier.append(cast("InvalidData[object]", value).data)
            continue
        if isinstance(value, list):
            frontier.extend(cast("list[object]", value))
            continue
        if not isinstance(value, WireEntity) or id(value) in visited:
            continue
        visited.add(id(value))
        hint = source_hint_of(value)
        if hint is not None and hint.observation is not None:
            claims.append(hint.observation)
        frontier.extend(cast("Mapping[str, object]", value).values())
    return tuple(claims)


# --------------------------------------------------------------------------- #
# A current milestone of the `Balance` fixture, as the port returns it — the  #
# row every temporal keyed-write suite reads before it writes, exercised      #
# through the typed verbs and so through the SAME `_buffer` neutral seam the  #
# conformance engine uses.                                                    #
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
