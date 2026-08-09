"""Predicate-selected (`*_where`) write unit tests for `parallax.snapshot.handle`.

The set-based verb family (`python.md` §5) covers the
mutation-compatibility guard, Assignment composition, inheritance rejection,
Valid-Time-bound validation, readless
dispatch for an unversioned non-temporal target, and materialization — the
resolving read's need-sensitive projection, per-row no-op elimination, and
atomic-unit buffering (ADR 0014) — across audit-only, bitemporal, and versioned
non-temporal targets.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from decimal import Decimal
from typing import Any, cast

import pytest
from _transact_support import (
    ACCOUNT,
    BALANCE,
    FIXED,
    ORDERS,
    PAYMENT,
    PERSON,
    RATE,
    WHERE_POSITION_META,
    NoIoPort,
    RecordingPort,
    WherePosition,
    account_db,
)

from _support import inheritance_models as im
from _support import mirrored_models as mm
from parallax.conformance import case_format, engine
from parallax.conformance.graph_models import POLICY_MODEL, Policy
from parallax.conformance.story_models import Order
from parallax.core import (
    TX_TIME,
    Attr,
    Bitemporal,
    Document,
    DomainModel,
    Entity,
    FindQuery,
    Int32,
    QueryDefinitionError,
    TxTemporal,
    ValueObject,
    attr,
    inheritance,
)
from parallax.core.base import InstantError
from parallax.core.db_port import JsonDocument, Row
from parallax.core.dialect import POSTGRES
from parallax.core.op_algebra import OperationRejectedError
from parallax.core.unit_work import (
    FixedClock,
    OptimisticLockConflictError,
    PredicateWrite,
    StaleWriteError,
    WriteRejectedError,
    instructions,
)
from parallax.core.unit_work.write_planner import (
    assigned_many_path,
)
from parallax.snapshot import QueryTargetError
from parallax.snapshot.handle import Database, Transaction


# A local Transaction-Time-Only, value-object-bearing entity with the
# `supplier.yaml` shape from `m-value-object-047`. The minimal self-contained
# fixture keeps this predicate-write test independent of the broader model
# mirror.
class WhereLedgerAddress(ValueObject):
    city: Attr[str]


class WhereLedger(TxTemporal, table="where_ledger", namespace="parallax.compatibility"):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=64)
    address: Attr[WhereLedgerAddress | None]


_WHERE_LEDGER_META = DomainModel(WhereLedger)


# A local bitemporal, value-object-bearing entity combines `WherePosition`'s
# two axes with `WhereLedger`'s value-object shape. No corpus case exercises
# this predicate-update combination (`m-case-format.md:727`).
class WhereRectangleAddress(ValueObject):
    city: Attr[str]


class WhereRectangle(Bitemporal, table="where_rectangle", namespace="parallax.compatibility"):
    id: Attr[int] = attr(primary_key=True)
    acct_num: Attr[str] = attr(max_length=32)
    value: Attr[Decimal] = attr(precision=18, scale=2)
    address: Attr[WhereRectangleAddress | None]


_WHERE_RECTANGLE_META = DomainModel(WhereRectangle)


# A local versioned non-temporal, value-object-bearing entity mirrors
# `models/subscriber.yaml`. Its two value objects prove minimal-read discipline:
# the resolving read projects only the assigned document, never every declared
# document.
class WhereSubscriberAddress(ValueObject):
    city: Attr[str]


class WhereSubscriberProfile(ValueObject):
    bio: Attr[str]


class WhereSubscriber(Entity, table="where_subscriber", namespace="parallax.compatibility"):
    id: Attr[int] = attr(primary_key=True)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)
    address: Attr[WhereSubscriberAddress | None]
    profile: Attr[WhereSubscriberProfile | None]


_WHERE_SUBSCRIBER_META = DomainModel(WhereSubscriber)


# A local Transaction-Time-Only entity under Relational Document Layout: the two
# axis bounds keep Columns of their own and every domain member lives in the
# shared Structured Column, so its resolving read is the one lane that both
# retains a real stored document and patches a successor from it.
class WhereVoyageManifest(ValueObject):
    cargo: Attr[str | None]


class WhereVoyage(
    TxTemporal, table="where_voyage", namespace="parallax.compatibility", layout=Document()
):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str | None] = attr(max_length=64)
    manifest: Attr[WhereVoyageManifest | None]


_WHERE_VOYAGE_META = DomainModel(WhereVoyage)


# A local Bitemporal entity under Relational Document Layout. A rectangle split's
# head and tail CARRY the predecessor's document with nothing patched into them,
# so they are where the retained document reaches a bind unaltered; `stops` makes
# that document carry an array as well as a nested object.
class WhereCharterStop(ValueObject):
    port: Attr[str]


class WhereCharterTerms(ValueObject):
    clause: Attr[str | None]


class WhereCharter(
    Bitemporal, table="where_charter", namespace="parallax.compatibility", layout=Document()
):
    id: Attr[int] = attr(primary_key=True)
    route: Attr[str | None] = attr(max_length=64)
    terms: Attr[WhereCharterTerms | None]
    stops: Attr[tuple[WhereCharterStop, ...]]


_WHERE_CHARTER_META = DomainModel(WhereCharter)


class NestedReadlessStop(ValueObject):
    port: Attr[str]


class NestedReadlessSegment(ValueObject):
    stops: Attr[tuple[NestedReadlessStop, ...]]


class NestedReadlessRoute(ValueObject):
    name: Attr[str]
    segment: Attr[NestedReadlessSegment]


class NestedReadlessVoyage(
    Entity, table="nested_readless_voyage", namespace="parallax.compatibility", layout=Document()
):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str | None]
    route: Attr[NestedReadlessRoute]


_NESTED_READLESS_META = DomainModel(NestedReadlessVoyage)


# --------------------------------------------------------------------------- #
# Predicate-selected `_where` verb family (`python.md` §5): the mutation-      #
# compatibility guard, Assignment composition, inheritance rejection, Valid-   #
# Time-                                                                        #
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


def test_readless_document_many_assignment_is_refused_before_write_sql() -> None:
    port = RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.update_where(
            mm.Traveler.where(mm.Traveler.id == 1),
            mm.Traveler.tags.set((mm.TravelerTag(label="founder"),)),
        )

    with pytest.raises(WriteRejectedError) as raised:
        Database.connect(port, mm.DOCUMENT_LAYOUT_MODEL, clock=FixedClock(FIXED)).transact(fn)
    assert raised.value.rule == "predicate-write-readless-document-many-unsupported"
    assert [op[0] for op in port.ops] == ["begin", "rollback"]


def test_readless_nested_document_many_assignment_is_refused_before_write_sql() -> None:
    port = RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.update_where(
            NestedReadlessVoyage.where(NestedReadlessVoyage.id == 1),
            NestedReadlessVoyage.route.set(
                NestedReadlessRoute(
                    name="Coastal",
                    segment=NestedReadlessSegment(stops=(NestedReadlessStop(port="Oslo"),)),
                )
            ),
        )

    with pytest.raises(WriteRejectedError) as raised:
        Database.connect(port, _NESTED_READLESS_META, clock=FixedClock(FIXED)).transact(fn)
    assert raised.value.rule == "predicate-write-readless-document-many-unsupported"
    assert "route.segment.stops" in str(raised.value)
    assert [op[0] for op in port.ops] == ["begin", "rollback"]


def test_nested_document_many_detection_follows_only_authored_occurrences() -> None:
    entity = _NESTED_READLESS_META.entities[0]
    occurrence = entity.declared_value_objects[0]
    authored_without_many: dict[str, object] = {"name": "Coastal", "segment": {}}
    authored_with_many: dict[str, object] = {
        "name": "Coastal",
        "segment": {"stops": [{"port": "Oslo"}]},
    }

    assert assigned_many_path(occurrence, authored_without_many) is None
    assert assigned_many_path(occurrence, authored_with_many) == ("segment", "stops")
    assert assigned_many_path(occurrence, None) is None


def test_readless_document_scalar_assignment_still_reaches_planning() -> None:
    port = RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.update_where(
            NestedReadlessVoyage.where(NestedReadlessVoyage.id == 1),
            NestedReadlessVoyage.title.set("Coastal"),
        )

    Database.connect(port, _NESTED_READLESS_META, clock=FixedClock(FIXED)).transact(fn)
    assert [op[0] for op in port.ops] == ["begin", "write", "commit"]


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


def test_readless_update_where_reorders_assignments_to_layout_slot_order() -> None:
    # The SET clause orders by the target's Table Layout slots
    # (the settled step's own slot-ordered assignment cells), never the
    # AUTHORED assignment order -- reversing the two `.set(...)` calls below
    # (price before name, the opposite of Order's own slot order) emits
    # BYTE-IDENTICAL SQL to the natural order (mirrors `test_full_row_insert_
    # emits_the_entity_layout_slot_selection`'s own insert-side proof).
    # Eligibility is untouched: the target is still unversioned and
    # non-temporal, so the write stays readless.
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


def test_where_verb_rejects_a_query_that_is_not_mutation_compatible() -> None:
    port = RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.delete_where(mm.Person.where(mm.Person.id == 1).limit(1))

    with pytest.raises(QueryDefinitionError) as caught:
        Database.connect(port, PERSON, clock=FixedClock(FIXED)).transact(fn)
    assert caught.value.code == "query-not-mutation-compatible"
    assert not any(op[0] == "write" for op in port.ops)


def test_where_verb_rejects_an_inheritance_family_target() -> None:
    # The assignment names a member `CardPayment` itself declares, so the
    # composition step accepts it and the family rejection is what refuses the
    # write — which is the point: a set-based write over an inheritance family is
    # unsupported whatever it assigns.
    port = RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.update_where(
            im.CardPayment.where(im.CardPayment.id == 1), im.CardPayment.card_network.set("visa")
        )

    with pytest.raises(inheritance.InheritanceError, match="subtype-write-set-based-unsupported"):
        Database.connect(port, PAYMENT, clock=FixedClock(FIXED)).transact(fn)
    assert not any(op[0] in ("read", "write") for op in port.ops)


def test_where_verb_rejects_an_assignment_addressing_another_entity() -> None:
    # A set-based write assigns members of its exact target, and an inherited
    # member's Assignment addresses the DECLARING Entity — here the family root.
    # The typed ingress composes the Assignment list with the query before it
    # resolves anything, so this classifies as a composition failure; the
    # canonical instruction the conformance engine hands `validate_instruction`
    # carries no query to compose with, and still classifies the family first
    # (`test_write_instructions.py`).
    port = RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.update_where(
            im.CardPayment.where(im.CardPayment.id == 1), im.Payment.amount.set(Decimal("1.00"))
        )

    with pytest.raises(QueryDefinitionError, match=r"Payment\.amount") as caught:
        Database.connect(port, PAYMENT, clock=FixedClock(FIXED)).transact(fn)
    assert caught.value.code == "query-assignment-target-mismatch"
    assert not any(op[0] in ("read", "write") for op in port.ops)


def test_an_assignment_bearing_verb_requires_an_assignment() -> None:
    port = RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.update_where(mm.Person.where(mm.Person.id == 1))

    with pytest.raises(QueryDefinitionError, match="at least one assignment") as caught:
        Database.connect(port, PERSON, clock=FixedClock(FIXED)).transact(fn)
    assert caught.value.code == "query-assignment-target-mismatch"
    assert not any(op[0] in ("read", "write") for op in port.ops)


def test_one_member_is_assigned_once_in_a_predicate_selected_write() -> None:
    port = RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.update_where(
            mm.Person.where(mm.Person.id == 1),
            mm.Person.name.set("Ada"),
            mm.Person.name.set("Grace"),
        )

    with pytest.raises(QueryDefinitionError, match="assigned twice") as caught:
        Database.connect(port, PERSON, clock=FixedClock(FIXED)).transact(fn)
    assert caught.value.code == "query-assignment-target-mismatch"
    assert not any(op[0] in ("read", "write") for op in port.ops)


def test_bitemporal_where_verb_requires_valid_from() -> None:
    port = RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.update_where(
            WherePosition.where(WherePosition.id == 1), WherePosition.value.set(Decimal("1.00"))
        )

    with pytest.raises(ValueError, match="requires valid_from"):
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(fn)


def test_audit_only_where_verb_forbids_valid_from() -> None:
    port = RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.terminate_where(mm.Balance.where(mm.Balance.id == 1), valid_from=FIXED)

    with pytest.raises(ValueError, match="takes no valid_from"):
        Database.connect(port, BALANCE, clock=FixedClock(FIXED)).transact(fn)


def test_non_temporal_where_verb_forbids_valid_from() -> None:
    port = RecordingPort()

    def fn(tx: Transaction) -> None:
        tx.update_where(
            mm.Person.where(mm.Person.id == 1), mm.Person.name.set("Ada"), valid_from=FIXED
        )

    with pytest.raises(ValueError, match="takes no valid_from"):
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
    # `m-batch-write` requires zero resolved rows to produce zero keyed writes.
    # A materializing write that resolves nothing still commits
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
    # UNGATED (`m-txtime-write` "a LOCKING-mode close stays ungated" —
    # `~parallax.core.opt_lock.gates` only ever binds the observed-`in_z`
    # candidate under optimistic concurrency).
    port = RecordingPort(rows=_two_terminate_rows())

    def fn(tx: Transaction) -> None:
        tx.terminate_where(mm.Balance.where(mm.Balance.value < 200))

    Database.connect(port, BALANCE, clock=FixedClock(FIXED)).transact(fn)
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 2  # one Transaction-Time-only close per resolved row, no chain
    close_sql = POSTGRES.to_driver_sql(
        "update balance set out_z = ? where bal_id = ? and out_z = ?"
    )
    assert writes[0][1] == close_sql
    assert writes[0][2] == ("2024-06-01T00:00:00+00:00", 1, "infinity")
    assert writes[1][1] == close_sql
    assert writes[1][2] == ("2024-06-01T00:00:00+00:00", 2, "infinity")


def test_materializing_terminate_where_audit_only_gates_under_optimistic_concurrency() -> None:
    # OPTIMISTIC mode: an audit-only close GATES on the observed `in_z`,
    # binding LAST (`m-txtime-write.md:65`, `m-opt-lock.md:87-99`) — every
    # resolved row's own close carries THAT row's own observed `in_z`, in
    # resolved-row order, mirroring the corpus's `m-txtime-write-006` gated-
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
    # `txtime_write.plan` chains the instruction's OWN authored FULL row —
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
    # `m-case-format` "Predicate-selected write instruction": an
    # assignment-bearing `update_where` on an audit-only, value-object-bearing
    # target must carry the resolved row's OWN `address` document FORWARD into
    # the chained row when the caller does not itself reassign it. The
    # projection that makes this possible is the temporal target's own complete
    # Predecessor Row, which its close-only sibling records just the same.
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


def test_materializing_update_where_document_layout_patches_the_retained_document() -> None:
    # The materializing lane is the one that reads a real stored document rather
    # than reconstructing one, so it is where retention is observable: the resolve
    # projects the Structured Column, the observation keeps the row's raw document,
    # and the chained successor is that document patched — which is why
    # `charterCode`, a key this model declares nowhere, is still in the row the
    # chain writes, and why `manifest` rides forward with the key inside IT too.
    stored = {
        "title": "Coastal Run",
        "charterCode": "NB-118",
        "manifest": {"cargo": "grain", "sealNumber": "S-4021"},
    }
    port = RecordingPort(
        rows=[
            {
                "id": 1,
                "in_z": "2024-01-01T00:00:00+00:00",
                "out_z": "infinity",
                "payload": stored,
            }
        ]
    )

    def fn(tx: Transaction) -> None:
        tx.update_where(
            WhereVoyage.where(WhereVoyage.id == 1), WhereVoyage.title.set("Coastal Return")
        )

    Database.connect(port, _WHERE_VOYAGE_META, clock=FixedClock(FIXED)).transact(fn)
    reads = [op for op in port.ops if op[0] == "read"]
    writes = [op for op in port.ops if op[0] == "write"]
    assert reads[0][1] == POSTGRES.to_driver_sql(
        "select t0.id, t0.in_z, t0.out_z, t0.payload from where_voyage t0 "
        "where t0.id = ? and t0.out_z = ? for share of t0"
    )
    assert len(writes) == 2  # close then chain
    chain_sql, chain_binds = writes[1][1], writes[1][2]
    assert chain_sql == POSTGRES.to_driver_sql(
        "insert into where_voyage(id, in_z, out_z, payload) values (?, ?, ?, ?)"
    )
    assert chain_binds == (
        1,
        "2024-06-01T00:00:00+00:00",
        "infinity",
        JsonDocument(
            {
                "title": "Coastal Return",
                "charterCode": "NB-118",
                "manifest": {"cargo": "grain", "sealNumber": "S-4021"},
            }
        ),
    )


def test_materializing_terminate_where_document_layout_binds_a_carried_document_as_json() -> None:
    # A rectangle split's head CARRIES its predecessor's document with nothing
    # patched into it, so the value the insert binds is the retained document
    # itself. It must reach the bind as the portable JSON value a `Document` is
    # (`m-document-codec`): the compact columnar retention behind it seals its
    # containers read-only, and a read-only view is not something a structured-
    # document bind can serialize, so a retained container reaching the statement
    # would fail the whole write rather than insert the row it carried.
    stored = {
        "route": "Oslo-Bergen",
        "charterCode": "NB-118",
        "terms": {"clause": "standard", "sealNumber": "S-4021"},
        "stops": [{"port": "Kristiansand", "berth": "7"}],
    }
    port = RecordingPort(
        rows=[
            {
                "id": 1,
                "from_z": "2024-01-01T00:00:00+00:00",
                "thru_z": "infinity",
                "in_z": "2024-01-01T00:00:00+00:00",
                "out_z": "infinity",
                "payload": stored,
            }
        ]
    )
    valid_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.terminate_where(WhereCharter.where(WhereCharter.id == 1), valid_from=valid_from)

    Database.connect(port, _WHERE_CHARTER_META, clock=FixedClock(FIXED)).transact(fn)
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 2  # close + head only (no tail)
    head_binds = cast("tuple[object, ...]", writes[1][2])
    carried = cast("JsonDocument", head_binds[-1]).value
    assert carried == stored
    # Equality alone does not settle it: a read-only mapping compares equal to its
    # own contents, so a document of nothing but nested objects would pass that
    # check while still failing the bind. Serializing is what a structured-document
    # bind does, so serializing is what the retained document has to survive.
    assert json.dumps(carried) == json.dumps(stored)


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
    valid_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.update_where(
            WherePosition.where(WherePosition.id == 1),
            WherePosition.value.set(Decimal("300.00")),
            valid_from=valid_from,
        )

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 3  # close + head (old) + new tail


def test_materializing_plain_terminate_where_over_a_bitemporal_target() -> None:
    port = RecordingPort(rows=[_position_row()])
    valid_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.terminate_where(WherePosition.where(WherePosition.id == 1), valid_from=valid_from)

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 2  # close + head only (no tail)


def test_materializing_update_until_where_over_a_bitemporal_target() -> None:
    port = RecordingPort(rows=[_position_row()])
    valid_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.update_until_where(
            WherePosition.where(WherePosition.id == 1),
            WherePosition.value.set(Decimal("300.00")),
            valid_from=valid_from,
            until=until,
        )

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 4  # close + head + middle + tail


def test_materializing_terminate_until_where_over_a_bitemporal_target() -> None:
    port = RecordingPort(rows=[_position_row()])
    valid_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.terminate_until_where(
            WherePosition.where(WherePosition.id == 1), valid_from=valid_from, until=until
        )

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 3  # close + head + tail (no middle)


def test_materializing_terminate_until_where_writes_per_resolved_row() -> None:
    # The single-row test above proves the per-row shape
    # (close + head + tail); this proves the MATERIALIZE loop itself resolves
    # and writes MULTIPLE rows, exactly like `update_where`'s / `delete_where`'s
    # own multi-row pins -- N resolved rows -> 3*N keyed writes, no cross-row
    # elision (`m-opt-lock.md` "Predicate-selected writes materialize when
    # observations are needed").
    port = RecordingPort(rows=[_position_row(), {**_position_row(), "id": 2}])
    valid_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.terminate_until_where(
            WherePosition.where(WherePosition.value < 999),
            valid_from=valid_from,
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
    # `m-case-format.md:727`: a bitemporal, value-object-bearing target's
    # assignment-bearing `update_where` must project the document in its
    # resolving read. The resolved row's own `address`
    # rides head AND the new tail WHOLE when the caller does not itself
    # reassign it (`m-bitemp-write` "head/tail old values come from the
    # observed prior rectangle"; `m-value-object` "the document rides every
    # chained/split row whole" — never decomposed).
    address: dict[str, object] = {"city": "Helsinki"}
    port = RecordingPort(rows=[_rectangle_row(address=address)])
    valid_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.update_where(
            WhereRectangle.where(WhereRectangle.id == 1),
            WhereRectangle.value.set(Decimal("300.00")),
            valid_from=valid_from,
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
    valid_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.update_until_where(
            WhereRectangle.where(WhereRectangle.id == 1),
            WhereRectangle.value.set(Decimal("300.00")),
            valid_from=valid_from,
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
    # `m-case-format.md:727`: a bitemporal terminate's head rectangle chains
    # the resolved row's old
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
    valid_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.terminate_where(WhereRectangle.where(WhereRectangle.id == 1), valid_from=valid_from)

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
    # hole in Valid Time, `terminate_until_where`'s own docstring), and
    # BOTH chain the resolved row's OLD payload forward
    # (`bitemp_write.plan`), so the document rides both, whole.
    address: dict[str, object] = {"city": "Tampere"}
    port = RecordingPort(rows=[_rectangle_row(address=address)])
    valid_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.terminate_until_where(
            WhereRectangle.where(WhereRectangle.id == 1), valid_from=valid_from, until=until
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


def test_materializing_terminate_where_audit_only_observes_the_whole_document() -> None:
    # An AUDIT-ONLY terminate is close-only (`txtime_write.plan` — no chained
    # row, `materialize_row`'s own `assignment_bearing` set excludes it), so it
    # carries no payload forward and writes no document. Its resolving read
    # still projects one, because a Temporal Observation retains a COMPLETE
    # Predecessor Row (`m-unit-work`) whatever the topology does with it —
    # completeness is a property of the observation, not of the verb
    # (`m-value-object-047`, the corpus witness).
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
    writes = [op for op in port.ops if op[0] == "write"]
    assert "t0.address" in cast("str", reads[0][1])
    assert len(writes) == 1  # the close alone — nothing carries the document forward
    assert JsonDocument({"city": "Bergen"}) not in cast("tuple[object, ...]", writes[0][2])


# --------------------------------------------------------------------------- #
# A versioned non-temporal value-object target never chains. Its resolving    #
# read must project assigned documents so per-row no-op elimination can compare #
# them with stored values (`m-opt-lock.md:92-95`). `profile`, which these tests #
# never assign, proves the projection stays minimal rather than including every #
# declared value object.                                                       #
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
    valid_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.update_until_where(
            WherePosition.where(WherePosition.id == 1),
            WherePosition.value.set(Decimal("300.00")),
            valid_from=valid_from,
            until=valid_from,
        )

    with pytest.raises(ValueError, match="requires valid_from < until"):
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
            fn, concurrency="optimistic"
        )
    assert not any(op[0] in ("read", "write") for op in port.ops)  # never reached the resolve


def test_materializing_terminate_until_where_rejects_a_reversed_window_bound() -> None:
    port = RecordingPort()
    valid_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
    until = dt.datetime(2024, 4, 1, tzinfo=dt.UTC)  # BEFORE valid_from — reversed

    def fn(tx: Transaction) -> None:
        tx.terminate_until_where(
            WherePosition.where(WherePosition.id == 1), valid_from=valid_from, until=until
        )

    with pytest.raises(ValueError, match="requires valid_from < until"):
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
            fn, concurrency="optimistic"
        )
    assert not any(op[0] in ("read", "write") for op in port.ops)  # never reached the resolve


# --------------------------------------------------------------------------- #
# The behavioral mutation-compatibility rejection is covered end to end.        #
# `mutation_selection` refusing a clause-bearing query in `test_where_verbs.py` #
# is necessary but an actual `tx.update_where` or `tx.delete_where` call handed #
# one must itself raise the rejection (python.md §5), never merely be provable  #
# through the seam alone. A port that raises on any I/O proves the guard runs   #
# BEFORE the connection is ever touched.                                        #
# --------------------------------------------------------------------------- #
def test_update_where_rejects_an_ordered_query_end_to_end() -> None:
    query = mm.Person.where(mm.Person.id == 1).order_by(mm.Person.id.asc())

    def fn(tx: Transaction) -> None:
        tx.update_where(query, mm.Person.name.set("Ada"))

    with pytest.raises(QueryDefinitionError) as caught:
        Database.connect(NoIoPort(), PERSON, clock=FixedClock(FIXED)).transact(fn)
    assert caught.value.code == "query-not-mutation-compatible"


def test_delete_where_rejects_an_ordered_query_end_to_end() -> None:
    query = mm.Person.where(mm.Person.id == 1).order_by(mm.Person.id.asc())

    def fn(tx: Transaction) -> None:
        tx.delete_where(query)

    with pytest.raises(QueryDefinitionError) as caught:
        Database.connect(NoIoPort(), PERSON, clock=FixedClock(FIXED)).transact(fn)
    assert caught.value.code == "query-not-mutation-compatible"


def test_a_where_verb_never_classifies_deferred_execution_features() -> None:
    # Deferred Execution Feature classification belongs to modeled READ
    # execution. A predicate-selected write requires a mutation-compatible query
    # first, so the read-shaped clauses a deferral is recognized from are what
    # refuses this one — `query-not-mutation-compatible`, never
    # `execution-feature-deferred`, whichever the query would also have matched.
    query = Policy.where(Policy.all).history(TX_TIME).include(Policy.coverages)

    def fn(tx: Transaction) -> None:
        tx.delete_where(query)

    with pytest.raises(QueryDefinitionError) as caught:
        Database.connect(NoIoPort(), POLICY_MODEL, clock=FixedClock(FIXED)).transact(fn)
    assert caught.value.code == "query-not-mutation-compatible"


def test_update_where_refuses_a_target_the_connected_model_does_not_declare() -> None:
    # Target resolution answers the write side with the SAME refusal a read's
    # preflight raises, because it is the same failure: the connected model
    # declares no such Entity. It precedes buffering and every adapter touch.
    def fn(tx: Transaction) -> None:
        tx.update_where(mm.Person.where(mm.Person.id == 1), mm.Person.name.set("Ada"))

    with pytest.raises(QueryTargetError) as caught:
        Database.connect(NoIoPort(), ACCOUNT, clock=FixedClock(FIXED)).transact(fn)
    assert caught.value.code == "query-target-not-in-model"


# --------------------------------------------------------------------------- #
# The selecting predicate is a canonical operation and carries the WHOLE       #
# model-aware operation vocabulary, not just the rules the write instruction   #
# itself states. Authoring reaches no model, so a `_where` verb is the only    #
# place these can be enforced on a predicate-selected write; the two rules     #
# below come from different families so the pin covers the vocabulary rather   #
# than one rule.                                                               #
# --------------------------------------------------------------------------- #
def test_update_where_refuses_an_inverted_between_window_before_any_sql() -> None:
    def fn(tx: Transaction) -> None:
        tx.update_where(mm.Person.where(mm.Person.id.between(10, 1)), mm.Person.name.set("Ada"))

    with pytest.raises(OperationRejectedError) as caught:
        Database.connect(NoIoPort(), PERSON, clock=FixedClock(FIXED)).transact(fn)
    assert caught.value.rule == "between-bounds-inverted"


def test_delete_where_refuses_an_attribute_outside_the_written_position() -> None:
    # A second rule family — the positional reference check — over the same
    # connected model, which declares both Entities and relates them.
    def fn(tx: Transaction) -> None:
        tx.delete_where(mm.Person.where(mm.Passport.number == "X"))  # pyright: ignore[reportArgumentType]

    with pytest.raises(OperationRejectedError) as caught:
        Database.connect(NoIoPort(), PERSON, clock=FixedClock(FIXED)).transact(fn)
    assert caught.value.rule == "attribute-outside-active-position"


# --------------------------------------------------------------------------- #
# A typed `_where` verb validates and RENDERS both Valid-Time bounds BEFORE it  #
# builds the canonical instruction, so a `PredicateWrite` holds an ISO-8601 UTC #
# instant in a temporal slot from the moment it exists —                        #
# `write-instruction.schema.json`'s own definition of an instant — never a      #
# caller's spelling and never anything else standing in for one.                #
#                                                                               #
# A call that is invalid in BOTH places therefore classifies by its BOUND.      #
# Both refusals are correct and neither is lost; only their order is fixed, and #
# it is fixed by the point at which the instruction must already be canonical.  #
# The predicate's own refusal is undiminished — the SAME predicate under a      #
# RENDERABLE bound still classifies `between-bounds-inverted`, which is also    #
# what the conformance ingress gives the same instruction (it takes no          #
# `dt.datetime` at all, so it has no other candidate).                          #
#                                                                               #
# The three kinds below stand for the whole argument space — a bound whose      #
# rendering rejects, one whose rendering overflows, one that renders cleanly —  #
# on each of the two bound slots.                                               #
# --------------------------------------------------------------------------- #
_NAIVE = dt.datetime(2024, 7, 1)
_AWARE = dt.datetime(2024, 8, 1, tzinfo=dt.UTC)
_EXTREME_OFFSET = dt.datetime.min.replace(tzinfo=dt.timezone(dt.timedelta(hours=14)))
_NON_UTC_VALID_FROM = dt.datetime(2024, 7, 1, 5, tzinfo=dt.timezone(dt.timedelta(hours=5)))
_NON_UTC_UNTIL = dt.datetime(2024, 9, 1, 2, tzinfo=dt.timezone(dt.timedelta(hours=2)))


@pytest.mark.parametrize(
    ("valid_from", "until", "expected", "rule"),
    [
        (_NAIVE, None, InstantError, None),
        (_AWARE, None, OperationRejectedError, "between-bounds-inverted"),
        (_EXTREME_OFFSET, None, OverflowError, None),
        (_AWARE, _NAIVE, InstantError, None),
        (
            _AWARE,
            dt.datetime(2024, 9, 1, tzinfo=dt.UTC),
            OperationRejectedError,
            "between-bounds-inverted",
        ),
        (_AWARE, _EXTREME_OFFSET, OverflowError, None),
    ],
    ids=[
        "naive-valid-from",
        "aware-valid-from",
        "extreme-offset-valid-from",
        "naive-until",
        "aware-until",
        "extreme-offset-until",
    ],
)
def test_a_temporal_bound_is_judged_before_an_invalid_predicate(
    valid_from: dt.datetime,
    until: dt.datetime | None,
    expected: type[Exception],
    rule: str | None,
) -> None:
    def fn(tx: Transaction) -> None:
        _bounded_write(tx, WherePosition.where(WherePosition.id.between(10, 1)), valid_from, until)

    with pytest.raises(expected) as caught:
        Database.connect(NoIoPort(), WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(fn)
    if rule is not None:
        assert cast("OperationRejectedError", caught.value).rule == rule


@pytest.mark.parametrize(
    ("valid_from", "until", "expected"),
    [
        (_NAIVE, None, InstantError),
        (_EXTREME_OFFSET, None, OverflowError),
        (_AWARE, _NAIVE, InstantError),
        (_AWARE, _EXTREME_OFFSET, OverflowError),
    ],
    ids=[
        "naive-valid-from",
        "extreme-offset-valid-from",
        "naive-until",
        "extreme-offset-until",
    ],
)
def test_an_unrenderable_bound_is_refused_before_any_buffering(
    valid_from: dt.datetime, until: dt.datetime | None, expected: type[Exception]
) -> None:
    # A bound is judged by the same step that renders it and that decides
    # whether the target's profile admits a bound at all, so an unrenderable one
    # is refused before the instruction exists — and therefore before the
    # buffering seam, the resolving read, and every statement.
    port = RecordingPort(rows=[])

    def fn(tx: Transaction) -> None:
        _bounded_write(tx, WherePosition.where(WherePosition.id == 1), valid_from, until)

    with pytest.raises(expected):
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(fn)
    assert port.ops == [("begin",), ("rollback",)]


def test_a_non_utc_bound_reaches_the_buffer_as_its_canonical_utc_literal() -> None:
    # The instruction that reaches the buffering seam carries
    # `validate_valid_from` / `validate_until`'s own canonical literals, so a
    # bound authored at a NON-UTC offset lands in the rectangle split as the
    # same instant in UTC, never as the caller's spelling.
    port = RecordingPort(rows=[_position_row()])

    def fn(tx: Transaction) -> None:
        _bounded_write(
            tx,
            WherePosition.where(WherePosition.id == 1),
            _NON_UTC_VALID_FROM,
            _NON_UTC_UNTIL,
        )

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        fn, concurrency="optimistic"
    )
    writes = [op for op in port.ops if op[0] == "write"]
    assert len(writes) == 4  # close + head + middle + tail
    middle_binds = cast("tuple[object, ...]", writes[2][2])
    assert "2024-07-01T00:00:00+00:00" in middle_binds  # the authored `valid_from`, in UTC
    assert "2024-09-01T00:00:00+00:00" in middle_binds  # the authored `until`, in UTC


def test_no_typed_bound_reaches_the_frozen_ingress_uncanonicalized() -> None:
    # WHAT THIS PINS. A `PredicateWrite` this lane builds never carries a
    # non-canonical value in a canonical field, proved on the shape that binds
    # BOTH Valid-Time slots into SQL — a bitemporal `updateUntil`, whose
    # rectangle split emits four statements:
    #
    #   - a bound that cannot render never becomes an instruction, so the frozen
    #     ingress is never reached and no statement is ever issued;
    #   - a bound that can render arrives already normalized, so the four
    #     statements a typed call produces are INDISTINGUISHABLE from the ones
    #     the frozen ingress produces for the canonical instruction the
    #     conformance engine would hand it. Anything other than the canonical
    #     literal in either slot would show up as a differing bind.
    #
    # WHAT IT DOES NOT PIN: what the seam itself tolerates. Neither
    # `_buffer_predicate_instruction` nor `validate_instruction` reads a bound,
    # and `write-instruction.schema.json` types a Valid-Time instant as a
    # non-empty string with no pattern, so a caller that hand-authors a document
    # containing a malformed instant still deserializes and still reaches SQL
    # through this same seam. Refusing that belongs to the instruction serde;
    # what belongs here is that no Parallax code path ever produces such a
    # value.
    idle = RecordingPort(rows=[_position_row()])

    def unrenderable(tx: Transaction) -> None:
        tx.update_until_where(
            WherePosition.where(WherePosition.id == 1),
            WherePosition.value.set(Decimal("300.00")),
            valid_from=_EXTREME_OFFSET,
            until=_NON_UTC_UNTIL,
        )

    with pytest.raises(OverflowError):
        Database.connect(idle, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(unrenderable)
    assert idle.ops == [("begin",), ("rollback",)]

    typed_port = RecordingPort(rows=[_position_row()])

    def typed(tx: Transaction) -> None:
        tx.update_until_where(
            WherePosition.where(WherePosition.id == 1),
            WherePosition.value.set(Decimal("300.00")),
            valid_from=_NON_UTC_VALID_FROM,
            until=_NON_UTC_UNTIL,
        )

    Database.connect(typed_port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        typed, concurrency="optimistic"
    )

    canonical = instructions.deserialize(
        {
            "mutation": "updateUntil",
            "target": {
                "entity": "WherePosition",
                "predicate": {"eq": {"attr": "WherePosition.id", "value": 1}},
            },
            "assignments": [{"attr": "WherePosition.value", "value": Decimal("300.00")}],
            "validFrom": "2024-07-01T00:00:00+00:00",
            "until": "2024-09-01T00:00:00+00:00",
        }
    )
    assert isinstance(canonical, PredicateWrite)
    seam_port = RecordingPort(rows=[_position_row()])

    def frozen(tx: Transaction) -> None:
        tx._buffer_predicate_instruction(canonical)  # pyright: ignore[reportPrivateUsage] - the conformance engine's own route into the frozen seam

    Database.connect(seam_port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(
        frozen, concurrency="optimistic"
    )
    typed_writes = [op for op in typed_port.ops if op[0] == "write"]
    assert len(typed_writes) == 4  # close + head + middle + tail
    assert typed_writes == [op for op in seam_port.ops if op[0] == "write"]


def _bounded_write(
    tx: Transaction,
    query: FindQuery[Any, Any],
    valid_from: dt.datetime,
    until: dt.datetime | None,
) -> None:
    assignment = WherePosition.value.set(Decimal("300.00"))
    if until is None:
        tx.update_where(query, assignment, valid_from=valid_from)
    else:
        tx.update_until_where(query, assignment, valid_from=valid_from, until=until)


# --------------------------------------------------------------------------- #
# The conformance engine's OWN ingress, driven as the engine drives it. Both    #
# engine entry points are exercised as functions — the readless one             #
# (`_run_readless_predicate_write`, which opens the transaction itself) and     #
# the materializing one (`_is_materializing_write_step`, which classifies the   #
# step AND validates it before `_run_materializing_pair` executes anything) —   #
# so deleting either function's own `validate_instruction` call fails these     #
# cases. Driving `validate_instruction` from the test instead would leave that  #
# regression unpinned: the refusal would then come from the test, not from the  #
# engine.                                                                       #
#                                                                               #
# The models are the corpus's own, the exact pair the two dispatches are        #
# authored over: `models/wallet.yaml` (unversioned, non-temporal -> READLESS,   #
# m-batch-write-005) and `models/account.yaml` (versioned -> MATERIALIZING,     #
# m-opt-lock-015).                                                              #
#                                                                               #
# The predicates cover both refusal families a write target carries: the        #
# model-aware `between-bounds-inverted` rejection, and each result modifier     #
# `m-case-format` `target.predicate` forbids ("a bare write predicate, never a  #
# result modifier").                                                            #
# --------------------------------------------------------------------------- #
_READLESS_ENGINE_META = engine.load_case_metamodel(
    next(case for case in case_format.load_cases() if case.case_id == "m-batch-write-005")
)
_MATERIALIZING_ENGINE_META = engine.load_case_metamodel(
    next(case for case in case_format.load_cases() if case.case_id == "m-opt-lock-015")
)
_ENGINE_TX_INSTANT = "2024-06-01T00:00:00+00:00"


def _refused_predicates(entity: str) -> list[tuple[str, str, dict[str, object]]]:
    inner: dict[str, object] = {"lessThan": {"attr": f"{entity}.balance", "value": 200.00}}
    return [
        ("between", "upper bound", {"between": {"attr": f"{entity}.id", "lower": 10, "upper": 1}}),
        ("limit", "`limit` is a result modifier", {"limit": {"operand": inner, "count": 1}}),
        (
            "orderBy",
            "`orderBy` is a result modifier",
            {"orderBy": {"operand": inner, "keys": [{"attr": f"{entity}.balance"}]}},
        ),
        ("distinct", "`distinct` is a result modifier", {"distinct": {"operand": inner}}),
    ]


_READLESS_REFUSALS = _refused_predicates("Wallet")
_MATERIALIZING_REFUSALS = _refused_predicates("Account")


@pytest.mark.parametrize(
    ("message", "predicate"),
    [(message, predicate) for _id, message, predicate in _READLESS_REFUSALS],
    ids=[case_id for case_id, _message, _predicate in _READLESS_REFUSALS],
)
def test_the_engines_readless_predicate_ingress_refuses_before_it_opens_a_transaction(
    message: str, predicate: dict[str, object]
) -> None:
    port = RecordingPort()
    with pytest.raises(ValueError, match=re.escape(message)):
        engine._run_readless_predicate_write(  # pyright: ignore[reportPrivateUsage] - the conformance engine's own readless predicate-write ingress
            port,
            _READLESS_ENGINE_META,
            POSTGRES,
            "optimistic",
            {"mutation": "delete", "target": {"entity": "Wallet", "predicate": predicate}},
            _ENGINE_TX_INSTANT,
            rollback=False,
        )
    assert port.ops == []


@pytest.mark.parametrize(
    ("message", "predicate"),
    [(message, predicate) for _id, message, predicate in _MATERIALIZING_REFUSALS],
    ids=[case_id for case_id, _message, _predicate in _MATERIALIZING_REFUSALS],
)
def test_the_engines_materializing_predicate_ingress_refuses_before_it_resolves(
    message: str, predicate: dict[str, object]
) -> None:
    step = {
        "write": {
            "mutation": "delete",
            "target": {"entity": "Account", "predicate": predicate},
            "at": _ENGINE_TX_INSTANT,
        }
    }
    with pytest.raises(ValueError, match=re.escape(message)):
        engine._is_materializing_write_step(step, _MATERIALIZING_ENGINE_META)  # pyright: ignore[reportPrivateUsage] - the conformance engine's own materializing predicate-write ingress


# The frozen seam's OWN contract, driven the way the conformance engine drives
# it — an instruction NOTHING pre-validated, straight into
# `Transaction._buffer_predicate_instruction`. `validate_instruction`
# establishes the CALLER ordering; this establishes that the directly reachable
# seam takes no instruction on faith, so deleting its
# `inheritance.reject_predicate_write` call fails BOTH cases.
#
# The refusal is asserted at the seam CALL, inside the transaction body, which
# is what makes each half discriminating. Without the seam's own guard the
# readless family instruction is merely buffered and the call returns — the
# planner's flush-time refusal would come later, and never at all on the
# abandoned transaction here. And the materializing one reaches the resolving
# read, real SQL on the caller's connection, which `port.ops` then shows.
@pytest.mark.parametrize(
    ("model", "entity"),
    [(PAYMENT, "CardPayment"), (RATE, "DepositRate")],
    ids=["readless-unversioned-family", "materializing-bitemporal-family"],
)
def test_the_frozen_buffering_seam_refuses_an_unvalidated_inheritance_family_instruction(
    model: DomainModel, entity: str
) -> None:
    instruction = instructions.deserialize(
        {
            "mutation": "delete",
            "target": {
                "entity": entity,
                "predicate": {"eq": {"attr": f"{entity}.id", "value": 1}},
            },
        }
    )
    assert isinstance(instruction, PredicateWrite)
    port = RecordingPort(rows=[])

    def fn(tx: Transaction) -> None:
        with pytest.raises(
            inheritance.InheritanceError, match="subtype-write-set-based-unsupported"
        ):
            tx._buffer_predicate_instruction(instruction)  # pyright: ignore[reportPrivateUsage] - the conformance engine's own route into the frozen seam
        assert port.ops == [("begin",)]
        raise _Abandon

    with pytest.raises(_Abandon):
        Database.connect(port, model, clock=FixedClock(FIXED)).transact(fn)


# The seam's second own-contract rule, driven the same way: a milestone verb
# the target's temporal profile does not admit. `Account` is versioned and
# non-temporal, so the instruction MATERIALIZES — without this refusal it
# reaches the resolving read (real SQL, which `port.ops` would show) and then
# settles as an ordinary versioned update that consumes each matched row's
# version while dropping the window the caller bounded. A zero-match resolve
# would not even reach that: it buffers no group, so the flush would refuse
# nothing at all.
@pytest.mark.parametrize("mutation", ["updateUntil", "terminate", "terminateUntil"])
def test_the_frozen_buffering_seam_refuses_a_milestone_verb_on_a_non_temporal_target(
    mutation: str,
) -> None:
    document: dict[str, object] = {
        "mutation": mutation,
        "target": {"entity": "Account", "predicate": {"eq": {"attr": "Account.id", "value": 1}}},
    }
    if mutation == "updateUntil":
        document["assignments"] = [{"attr": "Account.balance", "value": 5.00}]
    if mutation != "terminate":
        document["validFrom"] = "2024-01-01T00:00:00+00:00"
        document["until"] = "2024-06-01T00:00:00+00:00"
    instruction = instructions.deserialize(document)
    assert isinstance(instruction, PredicateWrite)
    port = RecordingPort(rows=[])

    def fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError, match="temporal milestone verb"):
            tx._buffer_predicate_instruction(instruction)  # pyright: ignore[reportPrivateUsage] - the conformance engine's own route into the frozen seam
        assert port.ops == [("begin",)]
        raise _Abandon

    with pytest.raises(_Abandon):
        Database.connect(port, ACCOUNT, clock=FixedClock(FIXED)).transact(fn)


def test_where_verb_rejection_precedes_a_pending_writes_force_flush() -> None:
    # The ordering established for reads holds for a predicate write
    # too: the resolving read a materializing verb performs force-flushes
    # pending writes, so a refused predicate write must be refused before
    # `uow.read` and before `uow.buffer` — otherwise an invalid write flushes
    # a valid one.
    port = RecordingPort(rows=[_position_row()])
    valid_from = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)

    def fn(tx: Transaction) -> None:
        tx.insert(WherePosition(id=9, acct_num="A", value=Decimal("1.00")), valid_from=valid_from)
        with pytest.raises(OperationRejectedError):
            tx.update_where(
                WherePosition.where(WherePosition.id.between(10, 1)),
                WherePosition.value.set(Decimal("300.00")),
                valid_from=valid_from,
            )
        assert port.ops == [("begin",)]
        raise _Abandon

    with pytest.raises(_Abandon):
        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(fn)


class _Abandon(Exception):
    """Abandons the transaction once the ordering above is proven, so the
    pending insert never has to be a valid committed write."""


# --------------------------------------------------------------------------- #
# Both closed predicate refusals precede adapter access, proven by a port that #
# raises on any call rather than by a recorded absence. `RecordingPort` above  #
# proves an op was never appended; `NoIoPort` proves the connection was never  #
# touched, which is the stronger reading of "before Unit of Work or adapter    #
# access" and the one the refusals' own contract states.                       #
# --------------------------------------------------------------------------- #
def test_query_not_mutation_compatible_precedes_every_adapter_call() -> None:
    def fn(tx: Transaction) -> None:
        tx.delete_where(mm.Person.where(mm.Person.id == 1).limit(1))

    with pytest.raises(QueryDefinitionError) as caught:
        Database.connect(NoIoPort(), PERSON, clock=FixedClock(FIXED)).transact(fn)
    assert caught.value.code == "query-not-mutation-compatible"


def test_query_assignment_target_mismatch_precedes_every_adapter_call() -> None:
    def fn(tx: Transaction) -> None:
        tx.update_where(
            im.CardPayment.where(im.CardPayment.id == 1), im.Payment.amount.set(Decimal("1.00"))
        )

    with pytest.raises(QueryDefinitionError) as caught:
        Database.connect(NoIoPort(), PAYMENT, clock=FixedClock(FIXED)).transact(fn)
    assert caught.value.code == "query-assignment-target-mismatch"


# --------------------------------------------------------------------------- #
# Stale-write detection and the optimistic-conflict retry loop, reached        #
# through a TYPED `_where` call: a materialized group's per-row shortfall      #
# classifies and retries exactly as the keyed path's does. Each is stated as   #
# the whole per-attempt op SEQUENCE, because the retry contract is that the    #
# closure is RE-EXECUTED — an attempt that reused the first one's              #
# materialization would still open a second transaction and still commit.     #
# --------------------------------------------------------------------------- #
def _update_balance_where(tx: Transaction) -> None:
    tx.update_where(
        mm.Account.where(mm.Account.balance < 200), mm.Account.balance.set(Decimal("175.00"))
    )


def test_materializing_where_shortfall_in_locking_mode_is_a_stale_write() -> None:
    # The `_where` counterpart of the keyed locking-mode shortfall: the UPDATE a
    # materialized group emits under locking concurrency is ungated, so a
    # zero-row shortfall is the non-retriable stale write and the whole unit of
    # work rolls back.
    port = RecordingPort(
        rows=[{"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}],
        write_affected=0,
    )

    with pytest.raises(StaleWriteError, match="Account"):
        account_db(port).transact(_update_balance_where)
    assert [op[0] for op in port.ops] == ["begin", "read", "write", "rollback"]


def test_materializing_where_shortfall_in_optimistic_mode_is_a_lock_conflict() -> None:
    port = RecordingPort(
        rows=[{"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}],
        write_affected=0,
    )

    with pytest.raises(OptimisticLockConflictError):
        account_db(port).transact(_update_balance_where, concurrency="optimistic")
    assert [op[0] for op in port.ops] == ["begin", "read", "write", "rollback"]


def test_materializing_where_conflict_is_auto_retried_to_success_with_the_opt_in() -> None:
    # The `0`-then-`1` affected-rows transition, driven through the typed
    # `update_where` verb: the retried attempt re-runs the resolving read and
    # the gated write inside a second transaction. The second `read` is the
    # assertion that carries the re-execution contract; the second `begin` and
    # the `commit` alone are also true of an attempt that reused the first
    # attempt's materialization.
    port = RecordingPort(
        rows=[{"id": 3, "owner": "Grace", "balance": Decimal("10.00"), "version": 1}]
    )
    port.write_affected_queue = [0, 1]

    account_db(port).transact(
        _update_balance_where, concurrency="optimistic", retry_optimistic_conflicts=True
    )
    assert [op[0] for op in port.ops] == [
        "begin",
        "read",
        "write",
        "rollback",
        "begin",
        "read",
        "write",
        "commit",
    ]
    reads = [op for op in port.ops if op[0] == "read"]
    assert reads[0] == reads[1]
