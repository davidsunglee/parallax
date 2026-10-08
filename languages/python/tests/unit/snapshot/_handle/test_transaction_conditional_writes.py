"""Authority selection on the public verbs (scripted port).

The method names a write's authority: ``amend`` and ``replace`` take a source,
while ``amend_if`` and ``replace_if`` take exactly one condition their caller
states. These tests grade the condition rules in their fixed order, the Typed
conditional amendment's class-and-key addressing and assignment judgment, the
Typed source amendment's two exclusive authoring forms, the stated-``None``
refusals of every start, and the retired spellings — each against what the
call puts on the wire, which for a refusal is nothing.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal
from typing import Any, cast

import pytest

from parallax.conformance.class_models import MODELS
from parallax.conformance.read_models import CardPayment, CashPayment, Payment
from parallax.conformance.story_models import Wallet
from parallax.core import Attr, Entity, attr
from parallax.core.dialect import POSTGRES
from parallax.core.entity import AttributeAssignment, DomainModel
from parallax.core.entity._expressions import AttributeRef
from parallax.core.entity._model import model_of
from parallax.core.unit_work import TargetWrite, WriteInstructionError, WriteRejectedError
from parallax.core.unit_work.instructions import deserialize, prepare_typed_write
from parallax.core.write_plan.steps import UNVERSIONED
from parallax.snapshot import Transaction
from parallax.snapshot._handle._wire import WireTransactionView
from tests._support import mirrored_models as mm
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
from tests.unit._transact_support import (
    FIND_SQL_UNLOCKED,
    FIXED,
    PAYMENT,
    account_db,
    db_for,
)
from tests.unit._where_position_model import WHERE_POSITION_META

_GATED_BALANCE = POSTGRES.to_driver_sql(
    "update account set balance = ?, version = ? where id = ? and version = ?"
)
_GATED_FULL = POSTGRES.to_driver_sql(
    "update account set owner = ?, balance = ?, version = ? where id = ? and version = ?"
)


def _calls(port: ScriptedAdapter) -> list[PortCall]:
    return [call for call in port.calls if not isinstance(call, BeginCall | CommitCall)]


def _row(version: int = 3) -> dict[str, object]:
    return {"id": 1, "owner": "Ada", "balance": Decimal("100.00"), "version": version}


def _refused(
    call: Callable[[Transaction], object],
    match: str,
    error: type[Exception] = WriteInstructionError,
) -> None:
    port = ScriptedAdapter(Transact())

    def fn(tx: Transaction) -> None:
        with pytest.raises(error, match=match):
            call(tx)

    account_db(port).transact(fn)
    assert _calls(port) == []


# --------------------------------------------------------------------------- #
# Exactly one applicable condition, judged after the window and before the     #
# payload; nothing falls back on a source's authority.                         #
# --------------------------------------------------------------------------- #
_CONDITIONS: list[tuple[dict[str, object], str]] = [
    ({}, "requires version"),
    ({"version": 3, "tx_start": FIXED}, "one condition to state"),
    ({"version": 3, "unversioned": True}, "one condition to state"),
    ({"version": None}, r"version=None"),
    ({"version": True}, "integer version"),
    ({"tx_start": FIXED}, "takes version, not tx_start"),
    ({"unversioned": True}, "takes version, not unversioned"),
    ({"tx_start": None}, "takes version, not tx_start"),
]


@pytest.mark.parametrize(("condition", "match"), _CONDITIONS)
@pytest.mark.parametrize("verb", ["typed-amend", "wire-amend", "typed-replace", "wire-replace"])
def test_a_conditional_write_states_exactly_the_one_condition_its_entity_takes(
    verb: str, condition: dict[str, object], match: str
) -> None:
    stated = cast("dict[str, Any]", condition)

    def call(tx: Transaction) -> None:
        if verb == "typed-amend":
            tx.amend_if(mm.Account, mm.Account.owner.set("Bo"), key=1, **stated)
        elif verb == "wire-amend":
            tx.wire.amend_if("Account", {"id": 1, "owner": "Bo"}, **stated)
        elif verb == "typed-replace":
            tx.replace_if(mm.Account(id=1, owner="Bo", balance=Decimal(1)), **stated)
        else:
            tx.wire.replace_if("Account", {"id": 1, "owner": "Bo", "balance": "1"}, **stated)

    _refused(call, match)


@pytest.mark.parametrize(
    ("condition", "match"),
    [
        ({}, "requires unversioned"),
        ({"unversioned": False}, "accepts only True"),
        ({"unversioned": 1}, "accepts only True"),
        ({"unversioned": None}, "accepts only True"),
        ({"version": 1}, "takes unversioned, not version"),
    ],
)
def test_an_unversioned_target_requires_the_assertion_itself(
    condition: dict[str, object], match: str
) -> None:
    port = ScriptedAdapter(Transact())
    stated = cast("dict[str, Any]", condition)

    def fn(tx: Transaction) -> None:
        with pytest.raises(WriteInstructionError, match=match):
            tx.wire.amend_if("Wallet", {"id": 5, "balance": "2.00"}, **stated)
        with pytest.raises(WriteInstructionError, match=match):
            tx.amend_if(Wallet, Wallet.balance.set(Decimal(2)), key=5, **stated)

    db_for(MODELS["wallet"], port).transact(fn)
    assert _calls(port) == []


def test_a_window_is_refused_before_a_missing_condition() -> None:
    _refused(lambda tx: tx.wire.amend_if("Account", {"id": 1, "owner": "Bo"}, until=FIXED), "until")


def test_a_temporal_target_requires_its_start_condition() -> None:
    port = ScriptedAdapter(Transact())

    def fn(tx: Transaction) -> None:
        with pytest.raises(WriteInstructionError, match="takes tx_start, not unversioned"):
            tx.wire.amend_if("WherePosition", {"id": 1}, unversioned=True, valid_from=FIXED)
        with pytest.raises(WriteInstructionError, match=r"tx_start=None"):
            tx.wire.amend_if(
                "WherePosition", {"id": 1}, tx_start=cast("Any", None), valid_from=FIXED
            )

    db_for(WHERE_POSITION_META, port).transact(fn)
    assert _calls(port) == []


# --------------------------------------------------------------------------- #
# Typed conditional amendment: a concrete class, its scalar key, and           #
# assignments judged against that class's ancestry before they are flattened. #
# --------------------------------------------------------------------------- #
def test_a_typed_conditional_amendment_writes_its_assignments_under_its_version() -> None:
    port = ScriptedAdapter(Transact(Write()))
    account_db(port).transact(
        lambda tx: tx.amend_if(
            mm.Account, mm.Account.balance.set(Decimal("175.00")), key=1, version=3
        )
    )
    assert _calls(port) == [WriteCall(_GATED_BALANCE, (Decimal("175.00"), 4, 1, 3))]


def test_an_equal_conditional_assignment_is_still_written() -> None:
    port = ScriptedAdapter(Transact(Write()))
    account_db(port).transact(
        lambda tx: tx.amend_if(
            mm.Account, mm.Account.balance.set(Decimal("100.00")), key=1, version=3
        )
    )
    assert _calls(port) == [WriteCall(_GATED_BALANCE, (Decimal("100.00"), 4, 1, 3))]


@pytest.mark.parametrize(
    "key", [(1,), {"id": 1}, [1], {1}], ids=["tuple", "mapping", "list", "set"]
)
def test_a_conditional_key_is_one_scalar_value(key: object) -> None:
    _refused(
        lambda tx: tx.amend_if(mm.Account, mm.Account.owner.set("Bo"), key=key, version=3),
        "one scalar primary-key value",
    )


@pytest.mark.parametrize("key", ["one", True, 1.5], ids=["string", "boolean", "fraction"])
def test_a_conditional_key_is_judged_against_the_key_type(key: object) -> None:
    _refused(
        lambda tx: tx.amend_if(mm.Account, mm.Account.owner.set("Bo"), key=key, version=3),
        "declared type",
        WriteRejectedError,
    )


@pytest.mark.parametrize(
    "entity", [int, "Account", Wallet], ids=["foreign-class", "spelling", "another-models"]
)
def test_a_typed_conditional_amendment_takes_an_entity_class_of_its_model(entity: object) -> None:
    _refused(
        lambda tx: tx.amend_if(cast("Any", entity), mm.Account.owner.set("Bo"), key=1, version=3),
        "Entity Class",
        TypeError,
    )


def _raw(member: str, value: object) -> AttributeAssignment[Any]:
    """An assignment no ``Attr.set`` judged, as a caller could construct one."""
    return AttributeAssignment(AttributeRef("parallax.compatibility.Account", member), value)


@pytest.mark.parametrize(
    ("assignments", "match"),
    [
        ((mm.Account.owner.set("Bo"), mm.Account.owner.set("Cy")), "duplicated"),
        ((_raw("id", 2),), "primary-key"),
        ((_raw("version", 9),), "framework-owned"),
        ((Wallet.balance.set(Decimal(1)),), "declares or inherits"),
        ((_raw("balance", "much"),), "balance"),
        ((_raw("nickname", "x"),), "declares or inherits"),
    ],
    ids=["duplicate", "primary-key", "version", "foreign", "ill-typed", "undeclared"],
)
def test_an_assignment_is_judged_before_anything_is_buffered(
    assignments: tuple[Any, ...], match: str
) -> None:
    _refused(lambda tx: tx.amend_if(mm.Account, *assignments, key=1, version=3), match)


def test_an_inherited_assignment_applies_to_a_concrete_target() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[{"id": 4, "amount": Decimal(1)}]), Write()))

    def fn(tx: Transaction) -> None:
        tx.amend_if(
            CardPayment,
            Payment.amount.set(Decimal("2.00")),
            CardPayment.card_network.set("amex"),
            key=4,
            unversioned=True,
        )

    db_for(PAYMENT, port).transact(fn)
    read, write = _calls(port)
    assert isinstance(read, ReadCall) and "for share" in read.sql
    assert isinstance(write, WriteCall) and write.sql.endswith("where id = %s and kind = %s")
    assert write.binds == (Decimal("2.00"), "amex", 4, "card")


def test_a_sibling_member_and_an_abstract_target_are_refused() -> None:
    port = ScriptedAdapter(Transact())

    def fn(tx: Transaction) -> None:
        with pytest.raises(WriteInstructionError, match="declares or inherits"):
            tx.amend_if(
                CardPayment,
                cast("Any", CashPayment.tendered.set(Decimal(1))),
                key=4,
                unversioned=True,
            )
        with pytest.raises(WriteRejectedError, match="concrete"):
            tx.amend_if(Payment, Payment.amount.set(Decimal(1)), key=4, unversioned=True)

    db_for(PAYMENT, port).transact(fn)
    assert _calls(port) == []


class Locker(Entity, table="locker", namespace="parallax.conditional"):
    code: Attr[str] = attr(primary_key=True, max_length=8)
    holder: Attr[str | None] = attr(max_length=16)


def test_a_conditional_key_addresses_the_key_attribute_whatever_its_name() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[{"code": "A1", "holder": "Ada"}]), Write()))
    db_for(DomainModel(Locker), port).transact(
        lambda tx: tx.amend_if(Locker, Locker.holder.set("Bo"), key="A1", unversioned=True)
    )
    write = _calls(port)[-1]
    assert write == WriteCall(
        POSTGRES.to_driver_sql("update locker set holder = ? where code = ?"), ("Bo", "A1")
    )


# --------------------------------------------------------------------------- #
# Typed source amendment: an edited value or explicit assignments, never both. #
# --------------------------------------------------------------------------- #
def _read_then(write: Callable[[Transaction, mm.Account], None]) -> list[PortCall]:
    port = ScriptedAdapter(Transact(Read(rows=[_row()]), Write()))

    def fn(tx: Transaction) -> None:
        write(tx, tx.find(mm.Account.where(mm.Account.id == 1)).result())

    account_db(port).transact(fn)
    return _calls(port)


def test_explicit_source_assignments_write_exactly_what_they_name() -> None:
    edited = _read_then(lambda tx, found: tx.amend(found.edit(balance=Decimal("100.00"))))
    explicit = _read_then(
        lambda tx, found: tx.amend(found, mm.Account.balance.set(Decimal("100.00")))
    )
    assert (
        edited
        == explicit
        == [
            ReadCall(FIND_SQL_UNLOCKED, (1,)),
            WriteCall(_GATED_BALANCE, (Decimal("100.00"), 4, 1, 3)),
        ]
    )


def test_an_empty_edit_adds_no_history_to_refuse_beside_assignments() -> None:
    calls = _read_then(
        lambda tx, found: tx.amend(found.edit(), mm.Account.balance.set(Decimal("5.00")))
    )
    assert calls[-1] == WriteCall(_GATED_BALANCE, (Decimal("5.00"), 4, 1, 3))


def _disjoint(found: mm.Account) -> mm.Account:
    return found.edit(owner="Bo")


def _equal(found: mm.Account) -> mm.Account:
    return found.edit(balance=Decimal("100.00"))


def _restored(found: mm.Account) -> mm.Account:
    return found.edit(owner="Bo").edit(owner="Ada")


@pytest.mark.parametrize(
    "edit", [_disjoint, _equal, _restored], ids=["disjoint", "equal", "restored"]
)
def test_assignments_beside_any_edit_history_are_refused(
    edit: Callable[[mm.Account], mm.Account],
) -> None:
    def write(tx: Transaction, found: mm.Account) -> None:
        with pytest.raises(WriteInstructionError, match="one write has one author"):
            tx.amend(edit(found), mm.Account.balance.set(Decimal("5.00")))

    assert _read_then(write) == [ReadCall(FIND_SQL_UNLOCKED, (1,))]


def test_a_source_replacement_writes_the_whole_state_of_an_unedited_value() -> None:
    calls = _read_then(lambda tx, found: tx.replace(found))
    assert calls[-1] == WriteCall(_GATED_FULL, ("Ada", Decimal("100.00"), 4, 1, 3))


def test_a_wire_source_replacement_without_data_writes_what_the_node_published() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row()]), Write()))

    def fn(tx: Transaction) -> None:
        tx.wire.replace(tx.wire.find({"target": "Account", "predicate": _ONE}).result())

    account_db(port).transact(fn)
    assert _calls(port)[-1] == WriteCall(_GATED_FULL, ("Ada", Decimal("100.00"), 4, 1, 3))


_ONE = {"eq": {"attr": "Account.id", "value": 1}}


@pytest.mark.parametrize(
    ("data", "outcome"),
    [
        ({"owner": "Bo", "balance": "1.00"}, ("Bo", Decimal("1.00"))),
        ({"id": 1, "owner": "Bo", "balance": "1.00"}, ("Bo", Decimal("1.00"))),
        ({}, "required"),
        ({"owner": "Bo"}, "required"),
        ({"id": 2, "owner": "Bo", "balance": "1"}, "never changes it"),
    ],
    ids=["stated", "matching-key", "empty", "incomplete", "another-key"],
)
def test_wire_replacement_data_stands_alone(
    data: dict[str, object], outcome: tuple[object, ...] | str
) -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row()]), Write()))

    def fn(tx: Transaction) -> None:
        node = tx.wire.find({"target": "Account", "predicate": _ONE}).result()
        if isinstance(outcome, str):
            with pytest.raises((WriteInstructionError, WriteRejectedError), match=outcome):
                tx.wire.replace(node, data)
        else:
            tx.wire.replace(node, data)

    account_db(port).transact(fn)
    if isinstance(outcome, tuple):
        assert _calls(port)[-1] == WriteCall(_GATED_FULL, (*outcome, 4, 1, 3))
    else:
        assert _calls(port) == [ReadCall(FIND_SQL_UNLOCKED, (1,))]


@pytest.mark.parametrize(
    ("changes", "written"),
    [
        ({"id": 1}, None),
        ({"id": 1, "balance": "5.00"}, Decimal("5.00")),
    ],
    ids=["key-only", "key-and-member"],
)
def test_a_wire_source_amendment_sets_a_matching_key_aside(
    changes: dict[str, object], written: Decimal | None
) -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row()]), Write()))

    def fn(tx: Transaction) -> None:
        tx.wire.amend(tx.wire.find({"target": "Account", "predicate": _ONE}).result(), changes)

    account_db(port).transact(fn)
    expected: list[PortCall] = [ReadCall(FIND_SQL_UNLOCKED, (1,))]
    if written is not None:
        expected.append(WriteCall(_GATED_BALANCE, (written, 4, 1, 3)))
    assert _calls(port) == expected


def test_a_wire_source_key_that_is_no_key_value_is_refused() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row()])))

    def fn(tx: Transaction) -> None:
        node = tx.wire.find({"target": "Account", "predicate": _ONE}).result()
        with pytest.raises(WriteInstructionError):
            tx.wire.amend(node, {"id": "one", "balance": "5.00"})

    account_db(port).transact(fn)
    assert _calls(port) == [ReadCall(FIND_SQL_UNLOCKED, (1,))]


# --------------------------------------------------------------------------- #
# A stated start of None is refused wherever a start is taken.                 #
# --------------------------------------------------------------------------- #
_NONE = cast("dt.datetime", None)
_STARTS: dict[str, Callable[[Transaction], object]] = {
    "insert": lambda tx: tx.insert(
        mm.Account(id=7, owner="N", balance=Decimal(1)), valid_from=_NONE
    ),
    "wire.insert": lambda tx: tx.wire.insert(
        "Account", {"id": 7, "owner": "N", "balance": "1"}, valid_from=_NONE
    ),
    "amend_if": lambda tx: tx.amend_if(
        mm.Account, mm.Account.owner.set("Bo"), key=1, version=3, valid_from=_NONE
    ),
    "wire.amend_if": lambda tx: tx.wire.amend_if("Account", {"id": 1}, version=3, valid_from=_NONE),
    "replace_if": lambda tx: tx.replace_if(
        mm.Account(id=1, owner="Bo", balance=Decimal(1)), version=3, valid_from=_NONE
    ),
    "wire.replace_if": lambda tx: tx.wire.replace_if(
        "Account", {"id": 1, "owner": "Bo", "balance": "1"}, version=3, valid_from=_NONE
    ),
    "amend_where": lambda tx: tx.amend_where(
        mm.Account.where(mm.Account.id == 1), mm.Account.owner.set("Bo"), valid_from=_NONE
    ),
    "wire.amend_where": lambda tx: tx.wire.amend_where(
        {"entity": "Account", "predicate": _ONE}, {"owner": "Bo"}, valid_from=_NONE
    ),
    "terminate_where": lambda tx: tx.terminate_where(
        mm.Account.where(mm.Account.id == 1), valid_from=_NONE
    ),
    "wire.terminate_where": lambda tx: tx.wire.terminate_where(
        {"entity": "Account", "predicate": _ONE}, valid_from=_NONE
    ),
}


@pytest.mark.parametrize("verb", list(_STARTS))
def test_a_stated_none_start_is_refused_rather_than_read_as_omission(verb: str) -> None:
    _refused(_STARTS[verb], "valid_from=None")


# --------------------------------------------------------------------------- #
# The retired logical spellings are gone, not aliased.                         #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("owner", [Transaction, WireTransactionView], ids=["typed", "wire"])
@pytest.mark.parametrize("name", ["update", "update_where", "amend_target", "replace_target"])
def test_no_retired_method_remains(owner: type[object], name: str) -> None:
    assert not hasattr(owner, name)


@pytest.mark.parametrize(
    "document",
    [
        {"mutation": "update", "entity": "Account", "rows": [{"id": 1}]},
        {"mutation": "updateUntil", "entity": "Account", "rows": [{"id": 1}]},
        {"mutation": "update", "entity": "Account", "row": {"id": 1}, "ifVersion": 1},
        {
            "mutation": "update",
            "target": {"entity": "Account", "predicate": _ONE},
            "assignments": [{"attr": "Account.owner", "value": "Bo"}],
        },
    ],
    ids=["keyed", "bounded", "target", "predicate"],
)
def test_no_retired_instruction_token_is_accepted(document: dict[str, object]) -> None:
    with pytest.raises(WriteInstructionError, match="mutation"):
        deserialize(document)


@pytest.mark.parametrize(
    ("entity", "row", "outcome"),
    [
        ("Wallet", {"id": 5, "balance": 2}, None),
        ("Account", {"id": 1, "owner": "Bo"}, "takes version, not unversioned"),
    ],
    ids=["unversioned", "versioned"],
)
def test_an_instruction_carrying_the_assertion_alone_is_judged_like_a_stated_one(
    entity: str, row: dict[str, object], outcome: str | None
) -> None:

    model = model_of(MODELS["wallet"] if entity == "Wallet" else MODELS["account"])
    instruction = TargetWrite("amend", entity, row, unversioned=True)
    if outcome is None:
        assert prepare_typed_write(instruction, model).expectation is UNVERSIONED
    else:
        with pytest.raises(WriteInstructionError, match=outcome):
            prepare_typed_write(instruction, model)


def test_a_source_write_and_a_keyed_replacement_are_canonical_tokens() -> None:
    keyed = deserialize({"mutation": "replace", "entity": "Account", "rows": [{"id": 1}]})
    bounded = deserialize(
        {
            "mutation": "replaceUntil",
            "entity": "Account",
            "rows": [{"id": 1}],
            "validFrom": "2024-01-01T00:00:00Z",
            "until": "2024-02-01T00:00:00Z",
        }
    )
    assert (keyed.mutation, bounded.mutation) == ("replace", "replaceUntil")
