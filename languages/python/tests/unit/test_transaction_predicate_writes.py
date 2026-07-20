"""Predicate-selected (`*_where`) write unit tests for `parallax.snapshot.handle`.

The set-based verb family (COR-3 Phase 8 increment 5; `python.md` §5): the
bare-statement guard, inheritance rejection, business-bound validation, readless
dispatch for an unversioned non-temporal target, and materialization — the
resolving read's need-sensitive projection, per-row no-op elimination, and
atomic-unit buffering (ADR 0014) — across audit-only, bitemporal, and versioned
non-temporal targets.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import cast

import pytest
from _transact_support import (
    BALANCE,
    FIXED,
    ORDERS,
    PAYMENT,
    PERSON,
    PERSON_MIRROR_META,
    WHERE_POSITION_META,
    NoIoPort,
    RecordingPort,
    WherePosition,
    account_db,
)

import inheritance_models as im
import mirrored_models as mm
from parallax.conformance.story_models import Order
from parallax.core import AsOfAttribute, Attr, Entity, EntityConfig, Field, inheritance
from parallax.core.db_port import JsonDocument, Row
from parallax.core.dialect import POSTGRES
from parallax.core.entity import metamodel
from parallax.core.entity.value_object import ValueObject, VoField
from parallax.core.unit_work import (
    FixedClock,
)
from parallax.snapshot.handle import Database, Transaction

pytestmark = pytest.mark.unit


# A LOCAL audit-only, value-object-bearing entity — the `supplier.yaml` shape
# (`m-value-object-047`'s own model). This fixture predates the idiomatic
# mirror: ledger D-21 has since installed `mm.Supplier` for real, so the
# VO-bearing `update_where` carry-forward pin (finding 2, D-26) could now be
# rewritten onto it. It stays local because a minimal self-contained shape is
# all this pin needs, not because the mirror is missing.
class WhereLedgerAddress(ValueObject, frozen=True):
    city: Attr[str] = VoField(type="string")


class WhereLedger(Entity, frozen=True):
    __parallax__ = EntityConfig(
        table="where_ledger",
        namespace="parallax.compatibility",
        mutability="transactional",
        as_of=(
            AsOfAttribute(
                name="processingDate", from_column="in_z", to_column="out_z", axis="processing"
            ),
        ),
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    name: Attr[str] = Field(max_length=64)
    address: Attr[WhereLedgerAddress | None] = Field(nullable=True, default=None)
    processing_from: Attr[dt.datetime] = Field(column="in_z")
    processing_to: Attr[dt.datetime] = Field(column="out_z")


_WHERE_LEDGER_META = metamodel([WhereLedger])


# A LOCAL bitemporal, value-object-bearing entity — confirmation-pass residual
# P2's own fixture (`m-case-format.md:727`; no corpus witness exercises a
# VO-bearing bitemporal predicate update, D-26): combines `WherePosition`'s
# two axes with `WhereLedger`'s value-object shape.
class WhereRectangleAddress(ValueObject, frozen=True):
    city: Attr[str] = VoField(type="string")


class WhereRectangle(Entity, frozen=True):
    __parallax__ = EntityConfig(
        table="where_rectangle",
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
    address: Attr[WhereRectangleAddress | None] = Field(nullable=True, default=None)
    business_from: Attr[dt.datetime] = Field(column="from_z")
    business_to: Attr[dt.datetime] = Field(column="thru_z")
    processing_from: Attr[dt.datetime] = Field(column="in_z")
    processing_to: Attr[dt.datetime] = Field(column="out_z")


_WHERE_RECTANGLE_META = metamodel([WhereRectangle])


# A LOCAL versioned NON-TEMPORAL, value-object-bearing entity — mirrors
# `models/subscriber.yaml`'s own shape (a versioned document owner) —
# confirmation-pass residual A's own fixture (round 2, the `needs_documents`
# gate in `parallax.snapshot.handle`'s predicate-write lane): TWO value
# objects, so a pin can prove minimal-read discipline (the resolving read
# projects the ASSIGNED document only, never every declared one).
class WhereSubscriberAddress(ValueObject, frozen=True):
    city: Attr[str] = VoField(type="string")


class WhereSubscriberProfile(ValueObject, frozen=True):
    bio: Attr[str] = VoField(type="string")


class WhereSubscriber(Entity, frozen=True):
    __parallax__ = EntityConfig(
        table="where_subscriber", namespace="parallax.compatibility", mutability="transactional"
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    version: Attr[int] = Field(type="int32", optimistic_locking=True)
    address: Attr[WhereSubscriberAddress | None] = Field(nullable=True, default=None)
    profile: Attr[WhereSubscriberProfile | None] = Field(nullable=True, default=None)


_WHERE_SUBSCRIBER_META = metamodel([WhereSubscriber])


# --------------------------------------------------------------------------- #
# Predicate-selected `_where` verb family (COR-3 Phase 8 increment 5;          #
# python.md §5): the bare-statement guard, inheritance rejection, business-    #
# bound validation, readless dispatch, and materialization (resolve + per-row #
# no-op elimination + the atomic-unit buffering, ADR 0014).                    #
# --------------------------------------------------------------------------- #
def test_readless_update_where_buffers_one_statement_no_read() -> None:
    port = RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.update_where(mm.Person.where(mm.Person.id == 1), mm.Person.name.set("Ada"))

    Database.connect(port, PERSON, clock=FixedClock(FIXED)).transact(fn)
    assert port.ops == [
        ("begin",),
        ("write", POSTGRES.to_driver_sql("update person set name = ? where id = ?"), ("Ada", 1)),
        ("commit",),
    ]


def test_readless_delete_where_buffers_one_statement_no_read() -> None:
    port = RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.delete_where(mm.Person.where(mm.Person.id == 1))

    Database.connect(port, PERSON, clock=FixedClock(FIXED)).transact(fn)
    assert port.ops == [
        ("begin",),
        ("write", POSTGRES.to_driver_sql("delete from person where id = ?"), (1,)),
        ("commit",),
    ]


def test_readless_update_where_reorders_assignments_to_column_order() -> None:
    # Round-6 remaining (c): the SET clause orders by descriptor column order
    # (`_lower_predicate_write`'s own `_ordered_cells` reuse), never the
    # AUTHORED assignment order -- reversing the two `.set(...)` calls below
    # (price before name, the opposite of Order's own declared column order)
    # emits BYTE-IDENTICAL SQL to the natural order (mirrors `test_insert_
    # orders_columns_by_column_order_not_row_order`'s own insert-side proof).
    forward_port = RecordingPort()

    def forward(tx: Transaction) -> None:
        tx.update_where(
            Order.where(Order.id == 100),
            Order.name.set("Hopper"),
            Order.price.set(Decimal("9.99")),
        )

    Database.connect(forward_port, ORDERS, clock=FixedClock(FIXED)).transact(forward)

    reordered_port = RecordingPort()

    def reordered(tx: Transaction) -> None:
        tx.update_where(
            Order.where(Order.id == 100),
            Order.price.set(Decimal("9.99")),
            Order.name.set("Hopper"),
        )

    Database.connect(reordered_port, ORDERS, clock=FixedClock(FIXED)).transact(reordered)

    assert forward_port.ops == reordered_port.ops
    assert forward_port.ops == [
        ("begin",),
        (
            "write",
            POSTGRES.to_driver_sql("update orders set name = ?, price = ? where id = ?"),
            ("Hopper", Decimal("9.99"), 100),
        ),
        ("commit",),
    ]


def test_where_verb_rejects_a_non_bare_statement() -> None:
    port = RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.delete_where(mm.Person.where(mm.Person.id == 1).limit(1))

    with pytest.raises(ValueError, match="bare statement"):
        Database.connect(port, PERSON, clock=FixedClock(FIXED)).transact(fn)
    assert not any(op[0] == "write" for op in port.ops)


def test_where_verb_rejects_an_inheritance_family_target() -> None:
    port = RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.update_where(
            im.CardPayment.where(im.CardPayment.id == 1), im.CardPayment.amount.set(Decimal("1.00"))
        )

    with pytest.raises(inheritance.InheritanceError, match="subtype-write-set-based-unsupported"):
        Database.connect(port, PAYMENT, clock=FixedClock(FIXED)).transact(fn)
    assert not any(op[0] in ("read", "write") for op in port.ops)


def test_bitemporal_where_verb_requires_business_from() -> None:
    port = RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.update_where(
            WherePosition.where(WherePosition.id == 1), WherePosition.value.set(Decimal("1.00"))
        )

    with pytest.raises(ValueError, match="requires business_from"):
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(fn)


def test_audit_only_where_verb_forbids_business_from() -> None:
    port = RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.terminate_where(mm.Balance.where(mm.Balance.id == 1), business_from=FIXED)

    with pytest.raises(ValueError, match="takes no business_from"):
        Database.connect(port, BALANCE, clock=FixedClock(FIXED)).transact(fn)


def test_non_temporal_where_verb_forbids_business_from() -> None:
    port = RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.update_where(
            mm.Person.where(mm.Person.id == 1), mm.Person.name.set("Ada"), business_from=FIXED
        )

    with pytest.raises(ValueError, match="takes no business_from"):
        Database.connect(port, PERSON, clock=FixedClock(FIXED)).transact(fn)


def test_materializing_update_where_skips_no_op_rows_and_gates_the_rest() -> None:
    # m-opt-lock-014's own shape: TWO resolved rows, one already equal to the
    # assigned value (skipped: no DML, no version advance), one genuinely
    # changed (one gated per-row UPDATE).
    port = RecordingPort(
        rows=[
            {"id": 1, "owner": "Ada", "balance": 100.00, "version": 1},
            {"id": 3, "owner": "Grace", "balance": 10.00, "version": 1},
        ]
    )

    def fn(tx: Transaction) -> None:
        tx.update_where(
            mm.Account.where(mm.Account.balance < 200), mm.Account.balance.set(Decimal("100.00"))
        )

    account_db(port).transact(fn, concurrency="optimistic")
    kinds = [op[0] for op in port.ops]
    assert kinds == ["begin", "read", "write", "commit"]
    write_sql, write_binds = port.ops[2][1], port.ops[2][2]
    assert write_sql == POSTGRES.to_driver_sql(
        "update account set balance = ?, version = ? where id = ? and version = ?"
    )
    assert write_binds == (100.00, 2, 3, 1)  # account 1's no-op row never wrote


def test_materializing_delete_where_writes_every_resolved_row() -> None:
    # m-opt-lock-015's own shape: delete has no assignment equality to test,
    # so every resolved row writes — N always equals the resolved-row count.
    port = RecordingPort(
        rows=[
            {"id": 1, "owner": "Ada", "balance": 100.00, "version": 1},
            {"id": 3, "owner": "Grace", "balance": 10.00, "version": 1},
        ]
    )

    def fn(tx: Transaction) -> None:
        tx.delete_where(mm.Account.where(mm.Account.balance < 200))

    account_db(port).transact(fn, concurrency="optimistic")
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 2
    assert writes[0][2] == (1, 1)
    assert writes[1][2] == (3, 1)


def test_materializing_write_with_zero_resolved_rows_writes_nothing() -> None:
    # DQ2 rider 4 / m-batch-write.md "Zero resolved rows -> zero keyed writes,
    # success" — a materializing write that resolves nothing still commits
    # cleanly, with no keyed writes at all.
    port = RecordingPort(rows=[])

    def fn(tx: Transaction) -> None:
        tx.delete_where(mm.Account.where(mm.Account.balance < 0))

    account_db(port).transact(fn)
    assert port.ops == [("begin",), ("read", port.ops[1][1], port.ops[1][2]), ("commit",)]
    assert not any(op[0] == "write" for op in port.ops)


def _two_terminate_rows() -> list[Row]:
    return [
        {
            "bal_id": 1,
            "acct_num": "A",
            "val": 150.00,
            "in_z": "2024-01-01T00:00:00+00:00",
            "out_z": "infinity",
        },
        {
            "bal_id": 2,
            "acct_num": "B",
            "val": 50.00,
            "in_z": "2024-02-01T00:00:00+00:00",
            "out_z": "infinity",
        },
    ]


def test_materializing_terminate_where_over_an_audit_only_target() -> None:
    # LOCKING mode (the default): every resolved row gets its own close, in
    # the resolving read's own resolved-row order, and every close stays
    # UNGATED (`m-audit-write` "a LOCKING-mode close stays ungated" —
    # `~parallax.core.opt_lock.gates` only ever binds the observed-`in_z`
    # candidate under optimistic concurrency).
    port = RecordingPort(rows=_two_terminate_rows())

    def fn(tx: Transaction) -> None:
        tx.terminate_where(mm.Balance.where(mm.Balance.value < 200))

    Database.connect(port, BALANCE, clock=FixedClock(FIXED)).transact(fn)
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 2  # one processing-only close per resolved row, no chain
    close_sql = POSTGRES.to_driver_sql(
        "update balance set out_z = ? where bal_id = ? and out_z = ?"
    )
    assert writes[0][1] == close_sql
    assert writes[0][2] == ("2024-06-01T00:00:00+00:00", 1, "infinity")
    assert writes[1][1] == close_sql
    assert writes[1][2] == ("2024-06-01T00:00:00+00:00", 2, "infinity")


def test_materializing_terminate_where_audit_only_gates_under_optimistic_concurrency() -> None:
    # OPTIMISTIC mode: an audit-only close GATES on the observed `in_z`,
    # binding LAST (`m-audit-write.md:65`, `m-opt-lock.md:87-99`) — every
    # resolved row's own close carries THAT row's own observed `in_z`, in
    # resolved-row order, mirroring the corpus's `m-audit-write-006` gated-
    # close shape (`m-value-object-047`'s own re-gated step 2).
    port = RecordingPort(rows=_two_terminate_rows())

    def fn(tx: Transaction) -> None:
        tx.terminate_where(mm.Balance.where(mm.Balance.value < 200))

    Database.connect(port, BALANCE, clock=FixedClock(FIXED)).transact(fn, concurrency="optimistic")
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 2
    gated_sql = POSTGRES.to_driver_sql(
        "update balance set out_z = ? where bal_id = ? and out_z = ? and in_z = ?"
    )
    assert writes[0][1] == gated_sql
    assert writes[0][2] == ("2024-06-01T00:00:00+00:00", 1, "infinity", "2024-01-01T00:00:00+00:00")
    assert writes[1][1] == gated_sql
    assert writes[1][2] == ("2024-06-01T00:00:00+00:00", 2, "infinity", "2024-02-01T00:00:00+00:00")


def test_materializing_update_where_audit_only_chains_the_new_value() -> None:
    # `audit_write.plan` chains the instruction's OWN authored FULL row —
    # never a separate observed payload — so materialization must merge the
    # resolved row's own unassigned scalar payload (acct_num) forward itself.
    port = RecordingPort(
        rows=[
            {
                "bal_id": 1,
                "acct_num": "A",
                "val": 150.00,
                "in_z": "2024-01-01T00:00:00+00:00",
                "out_z": "infinity",
            }
        ]
    )

    def fn(tx: Transaction) -> None:
        tx.update_where(
            mm.Balance.where(mm.Balance.value < 200), mm.Balance.value.set(Decimal("175.00"))
        )

    Database.connect(port, BALANCE, clock=FixedClock(FIXED)).transact(fn)
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 2  # close then chain
    chain_sql, chain_binds = writes[1][1], writes[1][2]
    assert chain_sql == POSTGRES.to_driver_sql(
        "insert into balance(bal_id, acct_num, val, in_z, out_z) values (?, ?, ?, ?, ?)"
    )
    assert chain_binds == (1, "A", 175.00, "2024-06-01T00:00:00+00:00", "infinity")


def test_materializing_update_where_audit_only_carries_the_unassigned_value_object_forward() -> (
    None
):
    # D-26 / finding 2 (`m-case-format.md:727`): an assignment-bearing
    # `update_where` on an audit-only, VALUE-OBJECT-bearing target must carry
    # the resolved row's OWN `address` document FORWARD into the chained row
    # when the caller does not itself reassign it — so the resolving read
    # must project the document column too (unlike a terminate/delete,
    # `m-value-object-047`'s own row-form-omits-slot-4 witness, which stays
    # byte-identical because it never reaches this assignment-bearing branch).
    port = RecordingPort(
        rows=[
            {
                "id": 1,
                "name": "Nordic Foods",
                "address": {"city": "Bergen"},
                "in_z": "2024-01-01T00:00:00+00:00",
                "out_z": "infinity",
            }
        ]
    )

    def fn(tx: Transaction) -> None:
        tx.update_where(
            WhereLedger.where(WhereLedger.id == 1), WhereLedger.name.set("Baltic Traders")
        )

    Database.connect(port, _WHERE_LEDGER_META, clock=FixedClock(FIXED)).transact(fn)
    reads = [op for op in port.ops if op[0] == "read"]
    writes = [op for op in port.ops if op[0] == "write"]
    assert reads[0][1] == POSTGRES.to_driver_sql(
        "select t0.id, t0.name, t0.in_z, t0.out_z, t0.address from where_ledger t0 "
        "where t0.id = ? and t0.out_z = ? for share of t0"
    )
    assert len(writes) == 2  # close then chain
    chain_sql, chain_binds = writes[1][1], writes[1][2]
    assert chain_sql == POSTGRES.to_driver_sql(
        "insert into where_ledger(id, name, in_z, out_z, address) values (?, ?, ?, ?, ?)"
    )
    assert chain_binds == (
        1,
        "Baltic Traders",
        "2024-06-01T00:00:00+00:00",
        "infinity",
        JsonDocument({"city": "Bergen"}),
    )


def _position_row() -> Row:
    return {
        "id": 1,
        "acct_num": "A",
        "value": 200.00,
        "from_z": "2024-01-01T00:00:00+00:00",
        "thru_z": "infinity",
        "in_z": "2024-01-01T00:00:00+00:00",
        "out_z": "infinity",
    }


def test_materializing_plain_update_where_over_a_bitemporal_target() -> None:
    port = RecordingPort(rows=[_position_row()])
    business_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.update_where(
            WherePosition.where(WherePosition.id == 1),
            WherePosition.value.set(Decimal("300.00")),
            business_from=business_from,
        )

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 3  # close + head (old) + new tail


def test_materializing_plain_terminate_where_over_a_bitemporal_target() -> None:
    port = RecordingPort(rows=[_position_row()])
    business_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.terminate_where(WherePosition.where(WherePosition.id == 1), business_from=business_from)

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 2  # close + head only (no tail)


def test_materializing_update_until_where_over_a_bitemporal_target() -> None:
    port = RecordingPort(rows=[_position_row()])
    business_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.update_until_where(
            WherePosition.where(WherePosition.id == 1),
            WherePosition.value.set(Decimal("300.00")),
            business_from=business_from,
            until=until,
        )

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 4  # close + head + middle + tail


def test_materializing_terminate_until_where_over_a_bitemporal_target() -> None:
    port = RecordingPort(rows=[_position_row()])
    business_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.terminate_until_where(
            WherePosition.where(WherePosition.id == 1), business_from=business_from, until=until
        )

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 3  # close + head + tail (no middle)


def test_materializing_terminate_until_where_writes_per_resolved_row() -> None:
    # Round-6 remaining (a): the single-row pin above proves the PER-ROW shape
    # (close + head + tail); this proves the MATERIALIZE loop itself resolves
    # and writes MULTIPLE rows, exactly like `update_where`'s / `delete_where`'s
    # own multi-row pins -- N resolved rows -> 3*N keyed writes, no cross-row
    # elision (`m-opt-lock.md` "Predicate-selected writes materialize when
    # observations are needed").
    port = RecordingPort(rows=[_position_row(), {**_position_row(), "id": 2}])
    business_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.terminate_until_where(
            WherePosition.where(WherePosition.value < 999),
            business_from=business_from,
            until=until,
        )

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 6  # 2 resolved rows * (close + head + tail)


def _rectangle_row(*, address: dict[str, object] | None) -> Row:
    return {
        "id": 1,
        "acct_num": "A",
        "value": 200.00,
        "address": address,
        "from_z": "2024-01-01T00:00:00+00:00",
        "thru_z": "infinity",
        "in_z": "2024-01-01T00:00:00+00:00",
        "out_z": "infinity",
    }


def test_materializing_bitemporal_update_where_carries_the_unassigned_value_object() -> None:
    # Confirmation-pass residual P2 (`m-case-format.md:727`): a BITEMPORAL,
    # value-object-bearing target's assignment-bearing `update_where` must
    # project the document in its resolving read too (the prior round's gate
    # covered only an AUDIT-ONLY target) — the resolved row's own `address`
    # rides head AND the new tail WHOLE when the caller does not itself
    # reassign it (`m-bitemp-write` "head/tail old values come from the
    # observed prior rectangle"; `m-value-object` "the document rides every
    # chained/split row whole" — never decomposed).
    address: dict[str, object] = {"city": "Helsinki"}
    port = RecordingPort(rows=[_rectangle_row(address=address)])
    business_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.update_where(
            WhereRectangle.where(WhereRectangle.id == 1),
            WhereRectangle.value.set(Decimal("300.00")),
            business_from=business_from,
        )

    Database.connect(port, _WHERE_RECTANGLE_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    reads = [op for op in port.ops if op[0] == "read"]
    writes = [op for op in port.ops if op[0] == "write"]
    assert "t0.address" in cast("str", reads[0][1])  # the need-sensitive projection fired
    assert len(writes) == 3  # close + head (old) + new tail
    head_binds = cast("tuple[object, ...]", writes[1][2])
    tail_binds = cast("tuple[object, ...]", writes[2][2])
    assert head_binds[-1] == JsonDocument(address)  # head: OLD value, unreassigned document
    assert tail_binds[-1] == JsonDocument(address)  # new tail: NEW value, SAME document
    assert tail_binds[2] == Decimal("300.00")  # the assigned scalar column DOES take the new value


def test_materializing_update_until_where_bitemporal_carries_the_value_object_on_every_chain() -> (
    None
):
    # The full rectangle split (`m-bitemp-write-010..013`'s own witnessed
    # shape, VO-free `Position`): every one of head/middle/tail carries the
    # resolved row's own `address` forward, whole, since the caller reassigns
    # only `value` — the document is never decomposed at any chain slot.
    address: dict[str, object] = {"city": "Tampere"}
    port = RecordingPort(rows=[_rectangle_row(address=address)])
    business_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.update_until_where(
            WhereRectangle.where(WhereRectangle.id == 1),
            WhereRectangle.value.set(Decimal("300.00")),
            business_from=business_from,
            until=until,
        )

    Database.connect(port, _WHERE_RECTANGLE_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 4  # close + head + middle + tail
    head_binds = cast("tuple[object, ...]", writes[1][2])
    middle_binds = cast("tuple[object, ...]", writes[2][2])
    tail_binds = cast("tuple[object, ...]", writes[3][2])
    assert head_binds[-1] == JsonDocument(address)
    assert middle_binds[-1] == JsonDocument(address)
    assert tail_binds[-1] == JsonDocument(address)
    assert middle_binds[2] == Decimal("300.00")  # middle carries the NEW assigned value


def test_materializing_plain_terminate_where_bitemporal_carries_the_document() -> None:
    # Confirmation-pass residual P2, COMPLETION (`m-case-format.md:727`): a
    # BITEMPORAL terminate's own head rectangle chains the resolved row's OLD
    # payload forward (`bitemp_write.plan`'s terminate branch reads
    # `observed.payload`), so the resolving read must project the document
    # too, even though `terminate` carries no assignments — a bitemporal
    # target's rectangle split ALWAYS chains, unlike an AUDIT-ONLY terminate
    # (close-only, no chained row,
    # `test_materializing_terminate_where_audit_only_stays_document_free`,
    # below). `m-bitemp-write` "head/tail old values come from the observed
    # prior rectangle"; `m-value-object` "the document rides every
    # chained/split row whole".
    address: dict[str, object] = {"city": "Oslo"}
    port = RecordingPort(rows=[_rectangle_row(address=address)])
    business_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.terminate_where(
            WhereRectangle.where(WhereRectangle.id == 1), business_from=business_from
        )

    Database.connect(port, _WHERE_RECTANGLE_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    reads = [op for op in port.ops if op[0] == "read"]
    writes = [op for op in port.ops if op[0] == "write"]
    assert "t0.address" in cast("str", reads[0][1])  # the need-sensitive projection fired
    assert len(writes) == 2  # close + head only (no tail)
    head_binds = cast("tuple[object, ...]", writes[1][2])
    assert head_binds[-1] == JsonDocument(address)  # head: the OLD value's document, whole


def test_materializing_terminate_until_where_bitemporal_carries_the_document_on_head_and_tail() -> (
    None
):
    # `terminateUntil` opens head AND tail (no middle — the window becomes a
    # hole in business time, `terminate_until_where`'s own docstring), and
    # BOTH chain the resolved row's OLD payload forward
    # (`bitemp_write.plan`), so the document rides both, whole.
    address: dict[str, object] = {"city": "Tampere"}
    port = RecordingPort(rows=[_rectangle_row(address=address)])
    business_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.terminate_until_where(
            WhereRectangle.where(WhereRectangle.id == 1), business_from=business_from, until=until
        )

    Database.connect(port, _WHERE_RECTANGLE_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    reads = [op for op in port.ops if op[0] == "read"]
    writes = [op for op in port.ops if op[0] == "write"]
    assert "t0.address" in cast("str", reads[0][1])  # the need-sensitive projection fired
    assert len(writes) == 3  # close + head + tail (no middle)
    head_binds = cast("tuple[object, ...]", writes[1][2])
    tail_binds = cast("tuple[object, ...]", writes[2][2])
    assert head_binds[-1] == JsonDocument(address)
    assert tail_binds[-1] == JsonDocument(address)


def test_materializing_terminate_where_audit_only_stays_document_free() -> None:
    # An AUDIT-ONLY terminate is close-only (`audit_write.plan` — no chained
    # row, `_materialize_row`'s own `assignment_bearing` set excludes it), so
    # the resolving read stays document-free even on a VALUE-OBJECT-bearing
    # target — unlike its BITEMPORAL counterpart, above
    # (`m-value-object-047`'s own row-form-omits-slot-4 witness, unchanged).
    port = RecordingPort(
        rows=[
            {
                "id": 1,
                "name": "Nordic Foods",
                "address": {"city": "Bergen"},
                "in_z": "2024-01-01T00:00:00+00:00",
                "out_z": "infinity",
            }
        ]
    )

    def fn(tx: Transaction) -> None:
        tx.terminate_where(WhereLedger.where(WhereLedger.id == 1))

    Database.connect(port, _WHERE_LEDGER_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    reads = [op for op in port.ops if op[0] == "read"]
    assert "t0.address" not in cast("str", reads[0][1])


# --------------------------------------------------------------------------- #
# Confirmation-pass residual A (round 2, the `needs_documents` gate in the    #
# predicate-write lane): a VERSIONED NON-TEMPORAL VO-bearing target           #
# (`WhereSubscriber`, mirroring `models/subscriber.yaml`'s own shape) never   #
# chains, so that gate used to exclude it categorically -- an                 #
# assignment-bearing `update_where` assigning an UNCHANGED document could     #
# never be recognized by per-row no-op elimination (the comparison could not  #
# see the stored document), emitting an unnecessary gated UPDATE              #
# (`m-opt-lock.md:92-95`). The fix adds a COMPARISON need, projecting the     #
# ASSIGNED document(s) only (minimal-read discipline) -- `profile` (never     #
# assigned by these tests) proves the projection stays minimal, not "every    #
# declared value object".                                                     #
# --------------------------------------------------------------------------- #
def test_materializing_versioned_update_where_eliminates_a_no_op_value_object_row() -> None:
    port = RecordingPort(rows=[{"id": 1, "version": 1, "address": {"city": "Bergen"}}])

    def fn(tx: Transaction) -> None:
        tx.update_where(
            WhereSubscriber.where(WhereSubscriber.id == 1),
            WhereSubscriber.address.set(WhereSubscriberAddress(city="Bergen")),
        )

    Database.connect(port, _WHERE_SUBSCRIBER_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    # No DML and no version advance: the reassigned document is IDENTICAL to
    # the resolved row's own stored value, so the row is eliminated entirely.
    assert [op[0] for op in port.ops] == ["begin", "read", "commit"]


def test_materializing_versioned_update_where_gates_a_changed_value_object_row() -> None:
    port = RecordingPort(rows=[{"id": 1, "version": 1, "address": {"city": "Bergen"}}])

    def fn(tx: Transaction) -> None:
        tx.update_where(
            WhereSubscriber.where(WhereSubscriber.id == 1),
            WhereSubscriber.address.set(WhereSubscriberAddress(city="Oslo")),
        )

    Database.connect(port, _WHERE_SUBSCRIBER_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 1
    assert writes[0][1] == POSTGRES.to_driver_sql(
        "update where_subscriber set address = ?, version = ? where id = ? and version = ?"
    )
    assert writes[0][2] == (JsonDocument({"city": "Oslo"}), 2, 1, 1)


def test_materializing_versioned_update_where_projects_only_the_assigned_value_object() -> None:
    # Minimal-read discipline: the resolving read projects the ASSIGNED
    # document (`address`) only -- never `profile`, the entity's OTHER
    # declared value object, which this `update_where` never touches.
    port = RecordingPort(rows=[{"id": 1, "version": 1, "address": {"city": "Bergen"}}])

    def fn(tx: Transaction) -> None:
        tx.update_where(
            WhereSubscriber.where(WhereSubscriber.id == 1),
            WhereSubscriber.address.set(WhereSubscriberAddress(city="Oslo")),
        )

    Database.connect(port, _WHERE_SUBSCRIBER_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    reads = [op for op in port.ops if op[0] == "read"]
    assert reads[0][1] == POSTGRES.to_driver_sql(
        "select t0.id, t0.version, t0.address from where_subscriber t0 where t0.id = ?"
    )


def test_materializing_update_until_where_rejects_an_equal_window_bound() -> None:
    # No resolving read ever fires — the window rejects at build, before any
    # buffering (`buffer_predicate`, before `_materialize_predicate_write`).
    port = RecordingPort()
    business_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.update_until_where(
            WherePosition.where(WherePosition.id == 1),
            WherePosition.value.set(Decimal("300.00")),
            business_from=business_from,
            until=business_from,
        )

    with pytest.raises(ValueError, match="requires business_from < until"):
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
            fn, concurrency="optimistic"
        )
    assert not any(op[0] in ("read", "write") for op in port.ops)  # never reached the resolve


def test_materializing_terminate_until_where_rejects_a_reversed_window_bound() -> None:
    port = RecordingPort()
    business_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 4, 1, tzinfo=dt.UTC)  # BEFORE business_from — reversed

    def fn(tx: Transaction) -> None:
        tx.terminate_until_where(
            WherePosition.where(WherePosition.id == 1), business_from=business_from, until=until
        )

    with pytest.raises(ValueError, match="requires business_from < until"):
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
            fn, concurrency="optimistic"
        )
    assert not any(op[0] in ("read", "write") for op in port.ops)  # never reached the resolve


# --------------------------------------------------------------------------- #
# The BEHAVIORAL bare-statement rejection, end to end (round-6 confirmation-   #
# pass strengthening): `is_bare()` returning `False` in `test_where_verbs.py`  #
# is NECESSARY but not SUFFICIENT on its own — an actual `tx.update_where` /   #
# `tx.delete_where` call handed a `.distinct()` statement must itself raise    #
# the rejection (python.md §5), never merely be provable through the predicate #
# alone. A port that raises on any I/O proves the guard runs BEFORE the        #
# connection is ever touched.                                                  #
# --------------------------------------------------------------------------- #
def test_update_where_rejects_a_distinct_statement_end_to_end() -> None:
    statement = mm.Person.where(mm.Person.id == 1).distinct()

    def fn(tx: Transaction) -> None:
        tx.update_where(statement, mm.Person.name.set("Ada"))

    with pytest.raises(ValueError, match="bare statement"):
        Database.connect(NoIoPort(), PERSON_MIRROR_META, clock=FixedClock(FIXED)).transact(fn)


def test_delete_where_rejects_a_distinct_statement_end_to_end() -> None:
    statement = mm.Person.where(mm.Person.id == 1).distinct()

    def fn(tx: Transaction) -> None:
        tx.delete_where(statement)

    with pytest.raises(ValueError, match="bare statement"):
        Database.connect(NoIoPort(), PERSON_MIRROR_META, clock=FixedClock(FIXED)).transact(fn)
