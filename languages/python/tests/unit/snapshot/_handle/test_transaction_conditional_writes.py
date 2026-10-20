"""Authority selection on the public verbs (scripted port).

The method names a write's authority: ``amend`` and ``replace`` take a source,
while ``amend_if``, ``replace_if``, ``delete_if``, and ``terminate_if`` take
exactly one revision their caller states. These tests grade the revision rules
in their fixed order, the refusal of a target with no revision, the Typed
conditional verbs' class-and-key addressing and assignment judgment, the Typed
source amendment's two exclusive authoring forms, the stated-``None`` refusals
of every start, and the retired spellings — each against what the call puts on
the wire, which for a refusal is nothing. Where each conditional verb's
refusals fall relative to one another is ``test_target_write_order.py``'s.
"""

from __future__ import annotations

import datetime as dt
import inspect
from collections.abc import Callable
from decimal import Decimal
from typing import Any, cast

import pytest

from parallax.conformance.class_models import MODELS
from parallax.conformance.story_models import Wallet
from parallax.core import Attr, Entity, Int32, attr
from parallax.core._execution._unit_work.instructions import (
    deserialize,
    prepare_typed_write,
    serialize,
)
from parallax.core.dialect import POSTGRES
from parallax.core.entity import AttributeAssignment, DomainModel
from parallax.core.entity._expressions import AttributeRef
from parallax.core.entity._model import model_of
from parallax.core.unit_work import (
    TargetWriteInstruction,
    WriteInstructionError,
    WriteRejectedError,
)
from parallax.snapshot import TxnContext, WireEntity
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
    account_db,
    db_for,
)
from tests.unit.snapshot._handle._vessel_model import VESSEL, Ferry, Tug, Vessel

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
    call: Callable[[TxnContext], object],
    match: str,
    error: type[Exception] | tuple[type[Exception], ...] = WriteInstructionError,
) -> None:
    port = ScriptedAdapter(Transact())

    def fn(tx: TxnContext) -> None:
        with pytest.raises(error, match=match):
            call(tx)

    account_db(port).transact(fn)
    assert _calls(port) == []


# --------------------------------------------------------------------------- #
# Exactly one applicable revision, judged after the window and before the      #
# payload; nothing falls back on a source's authority.                         #
# --------------------------------------------------------------------------- #
_CONDITIONS: list[tuple[dict[str, object], str]] = [
    ({}, "requires version"),
    ({"version": 3, "tx_start": FIXED}, "one condition to state"),
    ({"version": None}, r"version=None"),
    ({"version": True}, "integer version"),
    ({"tx_start": FIXED}, "takes version, not tx_start"),
    ({"tx_start": None}, "takes version, not tx_start"),
]

_VERBS = [
    "typed-amend",
    "wire-amend",
    "typed-replace",
    "wire-replace",
    "typed-delete",
    "wire-delete",
]


def _conditional(verb: str, entity: type[Entity], **stated: Any) -> Callable[[TxnContext], None]:
    """``verb`` over the object id 1 of ``entity``, an Account or a Wallet, which
    share the members each verb writes."""
    name = entity.__name__

    def call(tx: TxnContext) -> None:
        typed = cast("type[mm.Account]", entity)
        if verb == "typed-amend":
            tx.amend_if(typed, typed.owner.set("Bo"), key=1, **stated)
        elif verb == "wire-amend":
            tx.wire.amend_if(name, {"id": 1, "owner": "Bo"}, **stated)
        elif verb == "typed-replace":
            tx.replace_if(typed(id=1, owner="Bo", balance=Decimal(1)), **stated)
        elif verb == "wire-replace":
            tx.wire.replace_if(name, {"id": 1, "owner": "Bo", "balance": "1"}, **stated)
        elif verb == "typed-delete":
            tx.delete_if(typed, key=1, **stated)
        else:
            tx.wire.delete_if(name, {"id": 1}, **stated)

    return call


@pytest.mark.parametrize(("condition", "match"), _CONDITIONS)
@pytest.mark.parametrize("verb", _VERBS)
def test_a_conditional_write_states_exactly_the_one_revision_its_entity_takes(
    verb: str, condition: dict[str, object], match: str
) -> None:
    _refused(_conditional(verb, mm.Account, **condition), match)


@pytest.mark.parametrize(
    "condition",
    [{}, {"version": 1}, {"tx_start": FIXED}, {"version": 1, "tx_start": FIXED}],
    ids=["none", "version", "tx-start", "both"],
)
@pytest.mark.parametrize("verb", _VERBS)
def test_an_unversioned_target_takes_no_conditional_write(
    verb: str, condition: dict[str, object]
) -> None:
    port = ScriptedAdapter(Transact())

    def fn(tx: TxnContext) -> None:
        with pytest.raises(WriteInstructionError, match="has none to state"):
            _conditional(verb, Wallet, **condition)(tx)

    db_for(MODELS["wallet"], port).transact(fn)
    assert _calls(port) == []


@pytest.mark.parametrize(
    "method",
    [
        TxnContext.amend_if,
        TxnContext.replace_if,
        TxnContext.delete_if,
        TxnContext.terminate_if,
        WireTransactionView.amend_if,
        WireTransactionView.replace_if,
        WireTransactionView.delete_if,
        WireTransactionView.terminate_if,
    ],
)
def test_no_conditional_verb_takes_an_unversioned_assertion(method: Callable[..., None]) -> None:
    assert "unversioned" not in inspect.signature(method).parameters


# --------------------------------------------------------------------------- #
# A conditional deletion names its object by its primary key alone.           #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("document", "match"),
    [
        ({"id": 1, "owner": "Bo"}, "primary key alone"),
        ({"owner": "Bo"}, "states no 'id'"),
        ({"id": 1, "nickname": "Bo"}, "undeclared"),
        ({"id": "one"}, "id"),
    ],
    ids=["member", "no-key", "undeclared", "ill-typed-key"],
)
def test_a_conditional_deletion_states_its_key_alone(
    document: dict[str, object], match: str
) -> None:
    _refused(
        lambda tx: tx.wire.delete_if("Account", document, version=3),
        match,
        (WriteInstructionError, WriteRejectedError),
    )


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


_TYPED_KEYED: dict[str, Callable[[TxnContext, object], None]] = {
    "amend": lambda tx, key: tx.amend_if(
        mm.Account, mm.Account.owner.set("Bo"), key=key, version=3
    ),
    "delete": lambda tx, key: tx.delete_if(mm.Account, key=key, version=3),
}


@pytest.mark.parametrize("verb", list(_TYPED_KEYED))
@pytest.mark.parametrize(
    "key", [(1,), {"id": 1}, [1], {1}], ids=["tuple", "mapping", "list", "set"]
)
def test_a_conditional_key_is_one_scalar_value(verb: str, key: object) -> None:
    _refused(lambda tx: _TYPED_KEYED[verb](tx, key), "one scalar primary-key value")


@pytest.mark.parametrize("verb", list(_TYPED_KEYED))
@pytest.mark.parametrize("key", ["one", True, 1.5], ids=["string", "boolean", "fraction"])
def test_a_conditional_key_is_judged_against_the_key_type(verb: str, key: object) -> None:
    _refused(lambda tx: _TYPED_KEYED[verb](tx, key), "declared type", WriteRejectedError)


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
    port = ScriptedAdapter(Transact(Write()))

    def fn(tx: TxnContext) -> None:
        tx.amend_if(Ferry, Vessel.name.set("Skua"), Ferry.berths.set(8), key=4, version=3)

    db_for(VESSEL, port).transact(fn)
    (write,) = _calls(port)
    assert isinstance(write, WriteCall)
    assert write.sql.endswith("where id = %s and kind = %s and version = %s")
    assert write.binds == ("Skua", 8, 4, 4, "ferry", 3)


def test_a_conditional_deletion_of_a_concrete_target_is_guarded_by_its_tag() -> None:
    port = ScriptedAdapter(Transact(Write()))
    db_for(VESSEL, port).transact(lambda tx: tx.delete_if(Ferry, key=4, version=3))
    assert _calls(port) == [
        WriteCall(
            POSTGRES.to_driver_sql("delete from vessel where id = ? and kind = ? and version = ?"),
            (4, "ferry", 3),
        )
    ]


def test_a_sibling_member_and_an_abstract_target_are_refused() -> None:
    port = ScriptedAdapter(Transact())
    ancestor = Vessel.name.set("Skua").attr.entity

    def fn(tx: TxnContext) -> None:
        with pytest.raises(WriteInstructionError, match="declares or inherits"):
            tx.amend_if(Ferry, cast("Any", Tug.pull.set(1)), key=4, version=3)
        with pytest.raises(WriteInstructionError, match="declares or inherits"):
            tx.amend_if(
                Ferry, AttributeAssignment(AttributeRef(ancestor, "berths"), 8), key=4, version=3
            )
        with pytest.raises(WriteRejectedError, match="concrete"):
            tx.amend_if(Vessel, Vessel.name.set("Skua"), key=4, version=3)
        with pytest.raises(WriteRejectedError, match="concrete"):
            tx.delete_if(Vessel, key=4, version=3)

    db_for(VESSEL, port).transact(fn)
    assert _calls(port) == []


class Locker(Entity, table="locker", namespace="parallax.conditional"):
    code: Attr[str] = attr(primary_key=True, max_length=8)
    holder: Attr[str | None] = attr(max_length=16)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)


def test_a_conditional_key_addresses_the_key_attribute_whatever_its_name() -> None:
    port = ScriptedAdapter(Transact(Write(), Write()))

    def fn(tx: TxnContext) -> None:
        tx.amend_if(Locker, Locker.holder.set("Bo"), key="A1", version=2)
        tx.delete_if(Locker, key="B2", version=5)

    db_for(DomainModel(Locker), port).transact(fn)
    assert _calls(port) == [
        WriteCall(
            POSTGRES.to_driver_sql(
                "update locker set holder = ?, version = ? where code = ? and version = ?"
            ),
            ("Bo", 3, "A1", 2),
        ),
        WriteCall(
            POSTGRES.to_driver_sql("delete from locker where code = ? and version = ?"), ("B2", 5)
        ),
    ]


# --------------------------------------------------------------------------- #
# Typed source amendment: an edited value or explicit assignments, never both. #
# --------------------------------------------------------------------------- #
def _read_then(write: Callable[[TxnContext, mm.Account], None]) -> list[PortCall]:
    port = ScriptedAdapter(Transact(Read(rows=[_row()]), Write()))

    def fn(tx: TxnContext) -> None:
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


def test_a_source_assignment_addressing_another_entity_is_refused() -> None:
    # The type checker refuses an assignment of another Entity beside a source;
    # preparation still refuses one a caller passes past it.
    port = ScriptedAdapter(Transact(Read(rows=[_row()])))

    def fn(tx: TxnContext) -> None:
        found = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        with pytest.raises(WriteInstructionError, match="declares or inherits"):
            tx.amend(found, Wallet.balance.set(Decimal(1)))  # pyright: ignore[reportArgumentType]

    account_db(port).transact(fn)
    assert [type(call) for call in _calls(port)] == [ReadCall]


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
    def write(tx: TxnContext, found: mm.Account) -> None:
        with pytest.raises(WriteInstructionError, match="one write has one author"):
            tx.amend(edit(found), mm.Account.balance.set(Decimal("5.00")))

    assert _read_then(write) == [ReadCall(FIND_SQL_UNLOCKED, (1,))]


def test_a_source_replacement_writes_the_whole_state_of_an_unedited_value() -> None:
    calls = _read_then(lambda tx, found: tx.replace(found))
    assert calls[-1] == WriteCall(_GATED_FULL, ("Ada", Decimal("100.00"), 4, 1, 3))


def test_a_wire_source_replacement_without_data_writes_what_the_node_published() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row()]), Write()))

    def fn(tx: TxnContext) -> None:
        tx.wire.replace(tx.wire.find({"target": "Account", "predicate": _ONE}).result())

    account_db(port).transact(fn)
    assert _calls(port)[-1] == WriteCall(_GATED_FULL, ("Ada", Decimal("100.00"), 4, 1, 3))


_ONE = {"eq": {"path": "Account.id", "value": 1}}


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

    def fn(tx: TxnContext) -> None:
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

    def fn(tx: TxnContext) -> None:
        tx.wire.amend(tx.wire.find({"target": "Account", "predicate": _ONE}).result(), changes)

    account_db(port).transact(fn)
    expected: list[PortCall] = [ReadCall(FIND_SQL_UNLOCKED, (1,))]
    if written is not None:
        expected.append(WriteCall(_GATED_BALANCE, (written, 4, 1, 3)))
    assert _calls(port) == expected


def test_a_wire_source_key_that_is_no_key_value_is_refused() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_row()])))

    def fn(tx: TxnContext) -> None:
        node = tx.wire.find({"target": "Account", "predicate": _ONE}).result()
        with pytest.raises(WriteInstructionError):
            tx.wire.amend(node, {"id": "one", "balance": "5.00"})

    account_db(port).transact(fn)
    assert _calls(port) == [ReadCall(FIND_SQL_UNLOCKED, (1,))]


# --------------------------------------------------------------------------- #
# A source payload is judged only after the window admits the write.          #
# --------------------------------------------------------------------------- #
_SOURCE_PAYLOADS: dict[str, Callable[[TxnContext, WireEntity, mm.Account], object]] = {
    "wire-mismatching-key": lambda tx, node, found: tx.wire.amend(node, {"id": 2}, until=FIXED),
    "typed-undeclared-assignment": lambda tx, node, found: tx.amend(
        found, _raw("nickname", "x"), until=FIXED
    ),
}


@pytest.mark.parametrize("payload", list(_SOURCE_PAYLOADS))
def test_a_source_payload_is_judged_after_its_window(payload: str) -> None:
    write = _SOURCE_PAYLOADS[payload]
    port = ScriptedAdapter(Transact(Read(rows=[_row()]), Read(rows=[_row()])))

    def fn(tx: TxnContext) -> None:
        node = tx.wire.find({"target": "Account", "predicate": _ONE}).result()
        found = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        with pytest.raises(WriteInstructionError, match="takes no until"):
            write(tx, node, found)

    account_db(port).transact(fn)
    assert [type(call) for call in _calls(port)] == [ReadCall, ReadCall]


# --------------------------------------------------------------------------- #
# A stated start of None is refused wherever a start is taken.                 #
# --------------------------------------------------------------------------- #
_NONE = cast("dt.datetime", None)
_STARTS: dict[str, Callable[[TxnContext], object]] = {
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
}


@pytest.mark.parametrize("verb", list(_STARTS))
def test_a_stated_none_start_is_refused_rather_than_read_as_omission(verb: str) -> None:
    _refused(_STARTS[verb], "valid_from=None")


# --------------------------------------------------------------------------- #
# The retired logical spellings are gone, not aliased.                         #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("owner", [TxnContext, WireTransactionView], ids=["typed", "wire"])
@pytest.mark.parametrize(
    "name", ["update", "update_where", "terminate_where", "amend_target", "replace_target"]
)
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
        ("Wallet", {"id": 5, "balance": 2}, "has none to state"),
        ("Account", {"id": 1, "owner": "Bo"}, "requires version"),
    ],
    ids=["unversioned", "versioned"],
)
def test_an_instruction_stating_no_revision_is_refused_for_every_target(
    entity: str, row: dict[str, object], outcome: str
) -> None:
    model = model_of(MODELS["wallet"] if entity == "Wallet" else MODELS["account"])
    with pytest.raises(WriteInstructionError, match=outcome):
        prepare_typed_write(TargetWriteInstruction("amend", entity, row), model)


@pytest.mark.parametrize("mutation", ["amend", "delete"])
def test_a_target_document_states_exactly_one_revision(mutation: str) -> None:
    with pytest.raises(WriteInstructionError, match="states no revision"):
        deserialize({"mutation": mutation, "entity": "Account", "row": {"id": 1}})


@pytest.mark.parametrize(
    "document",
    [
        {"mutation": "delete", "entity": "Account", "row": {"id": 1}, "ifVersion": 3},
        {
            "mutation": "terminateUntil",
            "entity": "WherePosition",
            "row": {"id": 1},
            "ifTxStart": "2023-12-01T00:00:00.000000Z",
            "validFrom": "2024-01-01T00:00:00.000000Z",
            "until": "2024-02-01T00:00:00.000000Z",
        },
    ],
    ids=["delete", "terminate-until"],
)
def test_a_destructive_target_document_round_trips(document: dict[str, object]) -> None:
    assert serialize(deserialize(document)) == document


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
