"""Editable Wire data and published-node replacement (scripted port).

``tx.wire.editable_data`` copies a published node's key and writable members
into fresh mutable containers by the model's selection, and a published node is
itself a conditional replacement's whole state. These tests grade what the copy
holds and leaves out, that it is independent of the node, that it serves any
verb, and that neither it nor a node-stated replacement reads anything or
borrows the node's authority.
"""

from __future__ import annotations

import copy
from decimal import Decimal
from typing import Any, cast

import pytest

from parallax.core.base import PresentDocument
from parallax.core.db_port import MappingRow
from parallax.core.dialect import POSTGRES
from parallax.core.unit_work import WriteInstructionError
from parallax.snapshot import Transaction, WireEntity
from tests._support.db_port import (
    BeginCall,
    CommitCall,
    PortCall,
    Read,
    ReadCall,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
)
from tests.unit._transact_support import CONTACT, FIND_SQL_UNLOCKED, PAYMENT, account_db, db_for

_ACCOUNT_ROW: MappingRow = {"id": 1, "owner": "Ada", "balance": Decimal("100.00"), "version": 3}
_ACCOUNT_QUERY: dict[str, object] = {
    "target": "Account",
    "predicate": {"eq": {"attr": "Account.id", "value": 1}},
}
_CONTACT_ROW: MappingRow = {
    "id": 1,
    "name": "Ada",
    "address": PresentDocument(
        {"street": "S", "city": "C", "geo": {"country": "NO", "point": {"lat": 1.0, "lon": 2.0}}}
    ),
}
_CONTACT_QUERY: dict[str, object] = {
    "target": "parallax.compatibility.Contact",
    "predicate": {"eq": {"attr": "parallax.compatibility.Contact.id", "value": 1}},
}
_GATED_FULL = POSTGRES.to_driver_sql(
    "update account set owner = ?, balance = ?, version = ? where id = ? and version = ?"
)
_INSERT = POSTGRES.to_driver_sql(
    "insert into account(id, owner, balance, version) values (?, ?, ?, ?)"
)


def _calls(port: ScriptedAdapter) -> list[PortCall]:
    return [call for call in port.calls if not isinstance(call, BeginCall | CommitCall)]


def test_editable_data_holds_the_key_and_writable_members_but_no_revision() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_ACCOUNT_ROW])))
    copies: list[dict[str, object]] = []

    def fn(tx: Transaction) -> None:
        node = tx.wire.find(_ACCOUNT_QUERY).result()
        assert node["version"] == 3
        copies.append(tx.wire.editable_data(node))

    account_db(port).transact(fn)
    (data,) = copies
    assert data == {"id": 1, "owner": "Ada", "balance": "100.00"}
    assert type(data) is dict
    assert _calls(port) == [ReadCall(FIND_SQL_UNLOCKED, (1,))]


def test_editable_data_is_independent_of_the_node_at_every_depth() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[copy.deepcopy(_CONTACT_ROW)])))

    def fn(tx: Transaction) -> None:
        node = tx.wire.find(_CONTACT_QUERY).result()
        data = tx.wire.editable_data(node)
        address = cast("dict[str, Any]", data["address"])
        assert type(address) is dict and type(address["geo"]) is dict
        assert type(address["phones"]) is list
        address["geo"]["country"] = "SE"
        cast("list[object]", address["phones"]).append({"type": "home", "number": "1"})
        published = cast("dict[str, Any]", node["address"])
        assert published["geo"]["country"] == "NO"
        assert published["phones"] == []
        assert tx.wire.editable_data(node)["address"] == published

    db_for(CONTACT, port).transact(fn)


def test_editable_data_leaves_derived_variant_metadata_out() -> None:
    row: MappingRow = {"id": 4, "kind": "card", "amount": Decimal(1), "card_network": "visa"}
    port = ScriptedAdapter(Transact(Read(rows=[row])))

    def fn(tx: Transaction) -> None:
        node = tx.wire.find(
            {"target": "Payment", "predicate": {"eq": {"attr": "Payment.id", "value": 4}}}
        ).result()
        assert node["familyVariant"] == "CardPayment"
        assert tx.wire.editable_data(node) == {"id": 4, "amount": "1.00", "cardNetwork": "visa"}

    db_for(PAYMENT, port).transact(fn)


def test_editable_data_serves_a_conditional_replacement_and_an_insertion() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_ACCOUNT_ROW]), Write(), Write()))

    def fn(tx: Transaction) -> None:
        node = tx.wire.find(_ACCOUNT_QUERY).result()
        data = tx.wire.editable_data(node)
        data["owner"] = "Bo"
        tx.wire.replace_if("Account", data, version=3)
        clone = tx.wire.editable_data(node)
        clone["id"] = 9
        tx.wire.insert("Account", clone)

    account_db(port).transact(fn)
    assert _calls(port) == [
        ReadCall(FIND_SQL_UNLOCKED, (1,)),
        WriteCall(_INSERT, (9, "Ada", Decimal("100.00"), 1)),
        WriteCall(_GATED_FULL, ("Bo", Decimal("100.00"), 4, 1, 3)),
    ]


def test_editable_data_of_an_inserted_node_copies_the_row_it_opened() -> None:
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: Transaction) -> None:
        opened = tx.wire.insert("Account", {"id": 9, "owner": "Ada", "balance": "1.00"})
        assert tx.wire.editable_data(opened) == {"id": 9, "owner": "Ada", "balance": "1.00"}

    account_db(port).transact(fn)


@pytest.mark.parametrize(
    "value",
    [{"id": 1, "owner": "Ada"}, "Account", None],
    ids=["plain-mapping", "spelling", "none"],
)
def test_editable_data_takes_a_node_parallax_published(value: object) -> None:
    port = ScriptedAdapter(Transact())

    def fn(tx: Transaction) -> None:
        with pytest.raises(WriteInstructionError, match="published"):
            tx.wire.editable_data(cast("WireEntity", value))

    account_db(port).transact(fn)
    assert _calls(port) == []


def test_a_published_node_states_a_conditional_replacement_whole() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_ACCOUNT_ROW]), Write()))

    def fn(tx: Transaction) -> None:
        node = tx.wire.find(_ACCOUNT_QUERY).result()
        tx.wire.replace_if(node, version=3)

    account_db(port).transact(fn)
    assert _calls(port)[-1] == WriteCall(_GATED_FULL, ("Ada", Decimal("100.00"), 4, 1, 3))


def test_a_node_stated_replacement_takes_neither_data_nor_its_source_authority() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_ACCOUNT_ROW])))

    def fn(tx: Transaction) -> None:
        node = tx.wire.find(_ACCOUNT_QUERY).result()
        with pytest.raises(WriteInstructionError, match="takes no data"):
            tx.wire.replace_if(node, {"owner": "Bo", "balance": "1"}, version=3)
        with pytest.raises(WriteInstructionError, match="requires version"):
            tx.wire.replace_if(node)
        with pytest.raises(WriteInstructionError, match="states the data"):
            tx.wire.replace_if("Account", version=3)
        with pytest.raises(WriteInstructionError, match="neither"):
            tx.wire.replace_if(cast("Any", dict(node)), version=3)
        with pytest.raises(WriteInstructionError, match="neither"):
            tx.wire.amend_if(cast("Any", node), {"owner": "Bo"}, version=3)

    account_db(port).transact(fn)
    assert _calls(port) == [ReadCall(FIND_SQL_UNLOCKED, (1,))]


def test_editable_data_amends_every_member_it_holds_and_is_no_source() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_ACCOUNT_ROW]), Write()))

    def fn(tx: Transaction) -> None:
        node = tx.wire.find(_ACCOUNT_QUERY).result()
        data = tx.wire.editable_data(node)
        with pytest.raises(WriteInstructionError, match="published"):
            tx.wire.amend(cast("WireEntity", data), {"owner": "Bo"})
        tx.wire.amend(node, data)

    account_db(port).transact(fn)
    assert _calls(port)[-1] == WriteCall(_GATED_FULL, ("Ada", Decimal("100.00"), 4, 1, 3))
