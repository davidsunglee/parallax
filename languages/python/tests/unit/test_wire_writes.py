"""The Wire write interface (`python.md` §5, `m-unit-work`).

``tx.wire``'s keyed and predicate verb families, driven through the real handles
over a recording port. Three questions are asked here and nowhere else: that a
Wire verb lowers through the SAME pipeline its Typed peer does, that its static
judgements all precede any evidence question, and that a Wire write and a Typed
write of one object meet in one claim algebra rather than in two.

What a Wire READ publishes is `test_wire_reads.py`'s subject; the claim algebra
itself is `test_write_claims.py`'s. What lives here is the ingress.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import pickle
from decimal import Decimal
from typing import Any, cast

import pytest
from _transact_support import (
    ACCOUNT,
    BALANCE,
    CONTACT,
    FIXED,
    INFINITY_INSTANT,
    PERSON,
    WHERE_POSITION_META,
    NoIoPort,
    RecordingPort,
    balance_row,
    db_for,
)

from _support import mirrored_models as mm
from parallax.core.db_port import DbPort, JsonDocument, Row
from parallax.core.unit_work import FixedClock, WriteRejectedError, instructions
from parallax.snapshot import connect
from parallax.snapshot.handle import (
    Database,
    KeyedWriteValueError,
    Transaction,
    TransactionTimePinReadOnlyError,
    WireEntity,
    WriteEvidenceError,
)

_ACCOUNT_ROW: Row = {"id": 1, "owner": "Ada", "balance": Decimal("100.00"), "version": 4}
_PERSON_ROW: Row = {"id": 1, "name": "Ada"}
_TX_START = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_VALID_FROM = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
_OTHER_FROM = dt.datetime(2024, 9, 1, tzinfo=dt.UTC)
_UNTIL = dt.datetime(2024, 11, 1, tzinfo=dt.UTC)

_ACCOUNT_QUERY: dict[str, object] = {
    "target": "parallax.compatibility.Account",
    "predicate": {"eq": {"attr": "parallax.compatibility.Account.id", "value": 1}},
}
_PERSON_QUERY: dict[str, object] = {
    "target": "parallax.compatibility.Person",
    "predicate": {"eq": {"attr": "parallax.compatibility.Person.id", "value": 1}},
}
_BALANCE_QUERY: dict[str, object] = {
    "target": "parallax.compatibility.Balance",
    "predicate": {"eq": {"attr": "parallax.compatibility.Balance.id", "value": 1}},
    "temporal": {"transaction-time": {"asOf": "latest"}},
}
_POSITION_QUERY: dict[str, object] = {
    "target": "parallax.compatibility.WherePosition",
    "predicate": {"eq": {"attr": "parallax.compatibility.WherePosition.id", "value": 1}},
    "temporal": {
        "transaction-time": {"asOf": "latest"},
        "valid-time": {"asOf": "latest"},
    },
}
_PERSON_TARGET: dict[str, object] = {
    "entity": "parallax.compatibility.Person",
    "predicate": {"eq": {"attr": "parallax.compatibility.Person.id", "value": 1}},
}


def _position_row() -> Row:
    return {
        "id": 1,
        "acct_num": "A",
        "value": Decimal("200.00"),
        "from_z": _TX_START,
        "thru_z": INFINITY_INSTANT,
        "in_z": _TX_START,
        "out_z": INFINITY_INSTANT,
    }


def _writes(port: RecordingPort) -> list[tuple[object, ...]]:
    return [op for op in port.ops if op[0] == "write"]


def _reads(port: RecordingPort) -> list[tuple[object, ...]]:
    return [op for op in port.ops if op[0] == "read"]


def _account_port(rows: list[Row] | None = None) -> RecordingPort:
    return RecordingPort(rows=[dict(row) for row in (rows or [_ACCOUNT_ROW])])


def _node(tx: Transaction, query: dict[str, object]) -> WireEntity:
    return tx.wire.find(query).result()


def _standalone(db: Database, query: dict[str, object]) -> WireEntity:
    return db.wire.find(query).result()


# --------------------------------------------------------------------------- #
# Canonical lowering: every verb reaches the shared pipeline, and a Wire write #
# emits exactly what its Typed peer emits for the same intent.                #
# --------------------------------------------------------------------------- #
def test_a_wire_update_emits_what_the_typed_update_emits() -> None:
    wire_port = _account_port()

    def wire(tx: Transaction) -> None:
        tx.wire.update(_node(tx, _ACCOUNT_QUERY), {"balance": "125.00"})

    db_for(ACCOUNT, wire_port).transact(wire)

    typed_port = _account_port()

    def typed(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(node.edit(balance=Decimal("125.00")))

    db_for(ACCOUNT, typed_port).transact(typed)

    assert _writes(wire_port) == _writes(typed_port)


def test_a_wire_delete_emits_what_the_typed_delete_emits() -> None:
    wire_port = _account_port()
    db_for(ACCOUNT, wire_port).transact(lambda tx: tx.wire.delete(_node(tx, _ACCOUNT_QUERY)))

    typed_port = _account_port()
    db_for(ACCOUNT, typed_port).transact(
        lambda tx: tx.delete(tx.find(mm.Account.where(mm.Account.id == 1)).result())
    )

    assert _writes(wire_port) == _writes(typed_port)


def test_a_wire_insert_emits_what_the_typed_insert_emits() -> None:
    wire_port = _account_port()
    db_for(ACCOUNT, wire_port).transact(
        lambda tx: tx.wire.insert(
            "parallax.compatibility.Account",
            {"id": 7, "owner": "Newton", "balance": "5.00"},
        )
    )

    typed_port = _account_port()
    db_for(ACCOUNT, typed_port).transact(
        lambda tx: tx.insert(mm.Account(id=7, owner="Newton", balance=Decimal("5.00")))
    )

    assert _writes(wire_port) == _writes(typed_port)


def test_a_wire_terminate_closes_the_observed_milestone() -> None:
    port = RecordingPort(rows=[balance_row(in_z=_TX_START)])
    db_for(BALANCE, port).transact(lambda tx: tx.wire.terminate(_node(tx, _BALANCE_QUERY)))

    assert len(_writes(port)) == 1
    sql = cast("str", _writes(port)[0][1])
    assert sql.startswith("update balance set out_z")


def test_a_wire_update_until_splits_the_observed_rectangle() -> None:
    port = RecordingPort(rows=[_position_row()])

    def fn(tx: Transaction) -> None:
        tx.wire.update_until(
            _node(tx, _POSITION_QUERY),
            {"value": "300.00"},
            valid_from=_VALID_FROM,
            until=_UNTIL,
        )

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(fn)

    kinds = [cast("str", op[1]).split()[0] for op in _writes(port)]
    assert kinds == ["update", "insert", "insert", "insert"]


def test_a_wire_terminate_until_closes_and_reopens_the_flanks() -> None:
    port = RecordingPort(rows=[_position_row()])

    def fn(tx: Transaction) -> None:
        tx.wire.terminate_until(_node(tx, _POSITION_QUERY), valid_from=_VALID_FROM, until=_UNTIL)

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(fn)

    kinds = [cast("str", op[1]).split()[0] for op in _writes(port)]
    assert kinds == ["update", "insert", "insert"]


def test_a_wire_insert_until_opens_one_bounded_rectangle() -> None:
    port = RecordingPort(rows=[])

    def fn(tx: Transaction) -> None:
        tx.wire.insert_until(
            "parallax.compatibility.WherePosition",
            {"id": 2, "acctNum": "B", "value": "10.00"},
            valid_from=_VALID_FROM,
            until=_UNTIL,
        )

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(fn)

    assert [cast("str", op[1]).split()[0] for op in _writes(port)] == ["insert"]


def test_a_wire_predicate_delete_over_an_unversioned_target_is_readless() -> None:
    port = RecordingPort(rows=[])
    db_for(PERSON, port).transact(lambda tx: tx.wire.delete_where(_PERSON_TARGET))

    assert _reads(port) == []
    assert _writes(port) == [("write", "delete from person where id = %s", (1,))]


def test_a_wire_predicate_update_lowers_its_assignments_canonically() -> None:
    port = RecordingPort(rows=[])
    db_for(PERSON, port).transact(
        lambda tx: tx.wire.update_where(_PERSON_TARGET, {"name": "Grace"})
    )

    assert _writes(port) == [("write", "update person set name = %s where id = %s", ("Grace", 1))]


def test_a_wire_predicate_terminate_over_a_temporal_target_materializes() -> None:
    port = RecordingPort(rows=[balance_row(in_z=_TX_START)])
    db_for(BALANCE, port).transact(
        lambda tx: tx.wire.terminate_where(
            {
                "entity": "parallax.compatibility.Balance",
                "predicate": {"eq": {"attr": "parallax.compatibility.Balance.id", "value": 1}},
            }
        )
    )

    assert len(_reads(port)) == 1
    assert len(_writes(port)) == 1


def test_the_bounded_predicate_verbs_reach_the_rectangle_split() -> None:
    for verb, expected in (("update_until_where", 4), ("terminate_until_where", 3)):
        port = RecordingPort(rows=[_position_row()])
        target: dict[str, object] = {
            "entity": "parallax.compatibility.WherePosition",
            "predicate": {"eq": {"attr": "parallax.compatibility.WherePosition.id", "value": 1}},
        }

        def fn(tx: Transaction, verb: str = verb, target: dict[str, object] = target) -> None:
            if verb == "update_until_where":
                tx.wire.update_until_where(
                    target, {"value": "300.00"}, valid_from=_VALID_FROM, until=_UNTIL
                )
            else:
                tx.wire.terminate_until_where(target, valid_from=_VALID_FROM, until=_UNTIL)

        Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(fn)
        assert len(_writes(port)) == expected


# --------------------------------------------------------------------------- #
# A keyed source is a Parallax Wire read result, and nothing else.            #
# --------------------------------------------------------------------------- #
def _lost_provenance(node: WireEntity) -> list[object]:
    """Every way a caller can hold the same data and no longer hold the source."""
    return [
        dict(node),
        {"id": 1, "owner": "Ada", "balance": "100.00", "version": 4},
        json.loads(json.dumps(node)),
        pickle.loads(pickle.dumps(node)),
    ]


def test_a_mapping_that_lost_its_provenance_is_no_keyed_source() -> None:
    port = _account_port()

    def fn(tx: Transaction) -> None:
        node = _node(tx, _ACCOUNT_QUERY)
        for candidate in _lost_provenance(node):
            with pytest.raises(instructions.WriteInstructionError, match="Parallax Wire read"):
                tx.wire.update(cast("WireEntity", candidate), {"balance": "125.00"})

    db_for(ACCOUNT, port).transact(fn)
    assert _writes(port) == []


def test_a_copy_of_a_published_node_keeps_its_provenance() -> None:
    # An immutable value's copy IS the value, so the claim travels with it —
    # the Wire counterpart of `Entity.edit` transferring a Typed node's claim.
    port = _account_port()

    def fn(tx: Transaction) -> None:
        node = _node(tx, _ACCOUNT_QUERY)
        tx.wire.update(copy.deepcopy(node), {"balance": "125.00"})

    db_for(ACCOUNT, port).transact(fn)
    assert len(_writes(port)) == 1


def test_none_and_a_non_mapping_are_refused_as_keyed_sources() -> None:
    port = _account_port()

    def fn(tx: Transaction) -> None:
        for candidate in (None, 7, "Account"):
            with pytest.raises(instructions.WriteInstructionError):
                tx.wire.delete(cast("WireEntity", candidate))

    db_for(ACCOUNT, port).transact(fn)


# --------------------------------------------------------------------------- #
# Static validation precedes the strategy and its evidence, always.           #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"id": 2}, "primary-key"),
        ({"version": 9}, "framework-owned"),
        ({"nope": 1}, "does not name a declared member"),
        ({"passport": {}}, "does not name a declared member"),
        ({"owner": 5}, "does not match the declared type"),
    ],
)
def test_an_illegal_wire_assignment_is_refused_statically(
    changes: dict[str, object], match: str
) -> None:
    port = _account_port()

    def fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError, match=match):
            tx.wire.update(_node(tx, _ACCOUNT_QUERY), changes)

    db_for(ACCOUNT, port).transact(fn)
    assert _writes(port) == []


def test_a_temporal_axis_member_is_not_assignable() -> None:
    port = RecordingPort(rows=[balance_row(in_z=_TX_START)])

    def fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError, match="framework-owned"):
            tx.wire.update(_node(tx, _BALANCE_QUERY), {"txStart": "2024-01-01T00:00:00Z"})

    db_for(BALANCE, port).transact(fn)


def test_an_illegal_assignment_beats_unusable_evidence() -> None:
    # A standalone source of an effective-Locking target has no usable evidence
    # AND the change names a member no write may assign: the static verdict is
    # the one a caller sees, because nothing about concurrency has been asked yet.
    port = RecordingPort(rows=[dict(_PERSON_ROW)])
    db = db_for(PERSON, port)
    standalone = _standalone(db, _PERSON_QUERY)

    def fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError, match="primary-key"):
            tx.wire.update(standalone, {"id": 2})

    db.transact(fn)
    assert _writes(port) == []


def test_a_reversed_window_is_refused_before_any_member_is_measured() -> None:
    port = RecordingPort(rows=[_position_row()])

    def fn(tx: Transaction) -> None:
        with pytest.raises(ValueError, match="valid_from < until"):
            tx.wire.update_until(
                _node(tx, _POSITION_QUERY),
                {"value": "300.00"},
                valid_from=_UNTIL,
                until=_VALID_FROM,
            )

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(fn)
    assert _writes(port) == []


def test_a_non_temporal_target_takes_no_valid_from() -> None:
    port = _account_port()

    def fn(tx: Transaction) -> None:
        with pytest.raises(ValueError, match="takes no valid_from"):
            tx.wire.update(_node(tx, _ACCOUNT_QUERY), {"balance": "125.00"}, valid_from=_VALID_FROM)

    db_for(ACCOUNT, port).transact(fn)


def test_a_predicate_target_carries_exactly_entity_and_predicate() -> None:
    port = RecordingPort(rows=[])

    def fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError, match="exactly `entity`"):
            tx.wire.delete_where({**_PERSON_TARGET, "limit": 1})
        with pytest.raises(instructions.WriteInstructionError, match="exactly `entity`"):
            tx.wire.delete_where({"entity": "parallax.compatibility.Person"})
        with pytest.raises(instructions.WriteInstructionError, match="non-empty entity name"):
            tx.wire.delete_where({"entity": "", "predicate": {"all": {}}})

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == []


def test_an_insert_refuses_a_value_a_read_published() -> None:
    port = _account_port()

    def fn(tx: Transaction) -> None:
        node = _node(tx, _ACCOUNT_QUERY)
        with pytest.raises(KeyedWriteValueError) as exc_info:
            tx.wire.insert("parallax.compatibility.Account", node)
        assert exc_info.value.code == "write-value-already-stored"

    db_for(ACCOUNT, port).transact(fn)


def test_an_insert_refuses_a_framework_owned_member() -> None:
    port = _account_port()

    def fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError, match="framework-owned"):
            tx.wire.insert(
                "parallax.compatibility.Account",
                {"id": 7, "owner": "Newton", "balance": "5.00", "version": 3},
            )

    db_for(ACCOUNT, port).transact(fn)
    assert _writes(port) == []


def test_an_unresolvable_entity_spelling_is_refused_at_the_verb() -> None:
    port = _account_port()

    def fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError, match="unknown entity"):
            tx.wire.insert("parallax.compatibility.Nope", {"id": 7})

    db_for(ACCOUNT, port).transact(fn)


def test_a_finite_transaction_time_pinned_source_is_read_only() -> None:
    port = RecordingPort(rows=[balance_row(in_z=_TX_START)])
    pinned: dict[str, object] = {
        **_BALANCE_QUERY,
        "temporal": {"transaction-time": {"asOf": "2024-03-01T00:00:00+00:00"}},
    }

    def fn(tx: Transaction) -> None:
        with pytest.raises(TransactionTimePinReadOnlyError):
            tx.wire.terminate(_node(tx, pinned))

    db_for(BALANCE, port).transact(fn)
    assert _writes(port) == []


# --------------------------------------------------------------------------- #
# Evidence: the Phase 5 concurrency matrix, through Wire writes.              #
# --------------------------------------------------------------------------- #
def test_an_unversioned_participating_wire_source_licenses_an_ungated_write() -> None:
    port = RecordingPort(rows=[dict(_PERSON_ROW)])

    def fn(tx: Transaction) -> None:
        tx.wire.update(_node(tx, _PERSON_QUERY), {"name": "Grace"})

    db_for(PERSON, port).transact(fn)

    assert cast("str", _reads(port)[0][1]).endswith("for share of t0")
    assert _writes(port) == [("write", "update person set name = %s where id = %s", ("Grace", 1))]


def test_a_standalone_unversioned_wire_source_has_no_usable_evidence() -> None:
    port = RecordingPort(rows=[dict(_PERSON_ROW)])
    db = db_for(PERSON, port)
    standalone = _standalone(db, _PERSON_QUERY)

    def fn(tx: Transaction) -> None:
        with pytest.raises(WriteEvidenceError) as exc_info:
            tx.wire.update(standalone, {"name": "Grace"})
        assert exc_info.value.code == "write-evidence-unavailable"

    db.transact(fn)
    assert _writes(port) == []


def test_a_standalone_versioned_wire_source_supplies_its_own_gate() -> None:
    port = _account_port()
    db = db_for(ACCOUNT, port)
    standalone = _standalone(db, _ACCOUNT_QUERY)

    db.transact(lambda tx: tx.wire.update(standalone, {"balance": "125.00"}))

    assert len(_reads(port)) == 1
    assert _writes(port) == [
        (
            "write",
            "update account set balance = %s, version = %s where id = %s and version = %s",
            (Decimal("125.00"), 5, 1, 4),
        )
    ]


def test_explicit_locking_refuses_a_standalone_versioned_wire_source() -> None:
    port = _account_port()
    db = db_for(ACCOUNT, port)
    standalone = _standalone(db, _ACCOUNT_QUERY)

    def fn(tx: Transaction) -> None:
        with pytest.raises(WriteEvidenceError) as exc_info:
            tx.wire.update(standalone, {"balance": "125.00"})
        assert exc_info.value.code == "write-evidence-unavailable"

    db.transact(fn, concurrency="locking")
    assert _writes(port) == []


def test_a_wire_source_whose_evidence_a_flush_spent_is_refused() -> None:
    port = _account_port()

    def fn(tx: Transaction) -> None:
        node = _node(tx, _ACCOUNT_QUERY)
        tx.wire.update(node, {"balance": "125.00"})
        # The dependent read force-flushes, which spends the claim the write carried.
        tx.wire.find(_ACCOUNT_QUERY)
        with pytest.raises(WriteEvidenceError) as exc_info:
            tx.wire.update(node, {"balance": "150.00"})
        assert exc_info.value.code == "write-evidence-consumed"

    db_for(ACCOUNT, port).transact(fn)


def test_two_wire_intents_over_different_regions_are_refused_synchronously() -> None:
    port = RecordingPort(rows=[_position_row()])

    def fn(tx: Transaction) -> None:
        node = _node(tx, _POSITION_QUERY)
        tx.wire.update_until(node, {"value": "300.00"}, valid_from=_VALID_FROM, until=_UNTIL)
        with pytest.raises(WriteEvidenceError) as exc_info:
            tx.wire.update_until(node, {"value": "400.00"}, valid_from=_OTHER_FROM, until=_UNTIL)
        assert exc_info.value.code == "write-evidence-already-claimed"

    Database.connect(port, WHERE_POSITION_META, clock=FixedClock(FIXED)).transact(fn)


def test_a_wire_verb_refuses_before_any_io() -> None:
    port = NoIoPort()
    db = Database.connect(cast("DbPort", port), ACCOUNT, clock=FixedClock(FIXED))

    def fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError):
            tx.wire.update(cast("WireEntity", {"id": 1}), {"balance": "1.00"})

    db.transact(fn)


# --------------------------------------------------------------------------- #
# Coalescing, restoration, and the no-op — including across representations.  #
# --------------------------------------------------------------------------- #
def test_two_wire_assignments_of_one_state_merge_with_the_later_value_winning() -> None:
    port = _account_port()

    def fn(tx: Transaction) -> None:
        node = _node(tx, _ACCOUNT_QUERY)
        tx.wire.update(node, {"balance": "125.00"})
        tx.wire.update(node, {"balance": "150.00", "owner": "Grace"})

    db_for(ACCOUNT, port).transact(fn)

    assert len(_writes(port)) == 1
    assert cast("tuple[object, ...]", _writes(port)[0][2])[:2] == ("Grace", Decimal("150.00"))


def test_a_wire_assignment_equal_to_what_the_read_published_is_a_no_op() -> None:
    port = _account_port()

    def fn(tx: Transaction) -> None:
        node = _node(tx, _ACCOUNT_QUERY)
        tx.wire.update(node, {"balance": node["balance"], "owner": node["owner"]})

    db_for(ACCOUNT, port).transact(fn)
    assert _writes(port) == []


def test_a_wire_restore_chain_across_two_verbs_emits_nothing() -> None:
    port = _account_port()

    def fn(tx: Transaction) -> None:
        node = _node(tx, _ACCOUNT_QUERY)
        tx.wire.update(node, {"balance": "125.00"})
        tx.wire.update(node, {"balance": "100.00"})

    db_for(ACCOUNT, port).transact(fn)
    assert _writes(port) == []


def test_a_typed_assignment_a_wire_verb_restores_emits_nothing() -> None:
    # Both sources are taken BEFORE either write, because a participating read
    # force-flushes: read-your-own-writes is what a mixed chain has to work
    # inside, not around.
    port = _account_port()

    def fn(tx: Transaction) -> None:
        typed = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        node = _node(tx, _ACCOUNT_QUERY)
        tx.update(typed.edit(balance=Decimal("125.00")))
        tx.wire.update(node, {"balance": "100.00"})

    db_for(ACCOUNT, port).transact(fn)
    assert _writes(port) == []


def test_a_wire_assignment_a_typed_verb_restores_emits_nothing() -> None:
    port = _account_port()

    def fn(tx: Transaction) -> None:
        typed = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        node = _node(tx, _ACCOUNT_QUERY)
        tx.wire.update(node, {"balance": "125.00"})
        tx.update(typed.edit(balance=Decimal("125.00")).edit(balance=Decimal("100.00")))

    db_for(ACCOUNT, port).transact(fn)
    assert _writes(port) == []


def test_a_typed_and_a_wire_assignment_of_one_object_merge_in_authored_order() -> None:
    port = _account_port()

    def fn(tx: Transaction) -> None:
        typed = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        node = _node(tx, _ACCOUNT_QUERY)
        tx.update(typed.edit(balance=Decimal("125.00")))
        tx.wire.update(node, {"owner": "Grace"})

    db_for(ACCOUNT, port).transact(fn)

    assert len(_writes(port)) == 1
    assert cast("tuple[object, ...]", _writes(port)[0][2])[:2] == ("Grace", Decimal("125.00"))


def test_a_wire_update_then_delete_of_one_object_emits_one_delete() -> None:
    port = RecordingPort(rows=[dict(_PERSON_ROW)])

    def fn(tx: Transaction) -> None:
        node = _node(tx, _PERSON_QUERY)
        tx.wire.update(node, {"name": "Grace"})
        tx.wire.delete(node)

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == [("write", "delete from person where id = %s", (1,))]


def test_a_typed_update_of_a_row_a_wire_insert_opened_coalesces_in_place() -> None:
    # The buffered-insert ledger is ONE ledger: the Typed provenance refusal
    # exempts a value naming an object the WIRE verb inserted, so the pair
    # coalesces into a single INSERT carrying the final value rather than being
    # refused as a write of a row no read produced.
    port = RecordingPort(rows=[])

    def fn(tx: Transaction) -> None:
        tx.wire.insert("parallax.compatibility.Person", {"id": 9, "name": "Newton"})
        tx.update(mm.Person(id=9, name="Newton").edit(name="Grace"))

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == [
        ("write", "insert into person(id, name) values (%s, %s)", (9, "Grace"))
    ]


# --------------------------------------------------------------------------- #
# Input capture: what a verb buffered is its own from the moment it returns.  #
# --------------------------------------------------------------------------- #
def test_mutating_the_changes_mapping_after_the_verb_returns_changes_nothing() -> None:
    port = _account_port()
    changes: dict[str, object] = {"balance": "125.00"}

    def fn(tx: Transaction) -> None:
        tx.wire.update(_node(tx, _ACCOUNT_QUERY), changes)
        changes["balance"] = "999.00"
        changes["owner"] = "Mallory"

    db_for(ACCOUNT, port).transact(fn)
    assert _writes(port) == [
        (
            "write",
            "update account set balance = %s, version = %s where id = %s and version = %s",
            (Decimal("125.00"), 5, 1, 4),
        )
    ]


def test_mutating_insert_data_after_the_verb_returns_changes_nothing() -> None:
    port = RecordingPort(rows=[])
    data: dict[str, Any] = {"id": 9, "name": "Newton"}

    def fn(tx: Transaction) -> None:
        tx.wire.insert("parallax.compatibility.Person", data)
        data["name"] = "Mallory"

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == [
        ("write", "insert into person(id, name) values (%s, %s)", (9, "Newton"))
    ]


def test_mutating_a_predicate_target_after_the_verb_returns_changes_nothing() -> None:
    port = RecordingPort(rows=[])
    predicate: dict[str, Any] = {"eq": {"attr": "parallax.compatibility.Person.id", "value": 1}}
    target: dict[str, Any] = {"entity": "parallax.compatibility.Person", "predicate": predicate}

    def fn(tx: Transaction) -> None:
        tx.wire.delete_where(target)
        cast("dict[str, Any]", predicate["eq"])["value"] = 99

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == [("write", "delete from person where id = %s", (1,))]


def test_a_returned_wire_mapping_still_refuses_mutation_after_a_write() -> None:
    port = _account_port()

    def fn(tx: Transaction) -> None:
        node = _node(tx, _ACCOUNT_QUERY)
        tx.wire.update(node, {"balance": "125.00"})
        with pytest.raises(TypeError):
            cast("dict[str, object]", node)["balance"] = "999.00"
        assert node["balance"] == "100.00"

    db_for(ACCOUNT, port).transact(fn)


def test_the_wire_view_is_reachable_from_the_module_level_connect() -> None:
    port = _account_port()
    connect(port, ACCOUNT, clock=FixedClock(FIXED)).transact(
        lambda tx: tx.wire.delete(_node(tx, _ACCOUNT_QUERY))
    )
    assert len(_writes(port)) == 1


# --------------------------------------------------------------------------- #
# Value Object documents: an authored occurrence crosses the serde seam whole. #
# --------------------------------------------------------------------------- #
def _bound_address(port: RecordingPort) -> dict[str, Any]:
    """The address document the insert actually bound, as ordinary data.

    A Document-layout occurrence binds through a canonical JSON carrier, so the
    bind is unwrapped once here rather than at each assertion.
    """
    bound = cast("tuple[object, ...]", _writes(port)[0][2])[2]
    assert isinstance(bound, JsonDocument)
    return cast("dict[str, Any]", bound.value)


_ADDRESS: dict[str, Any] = {
    "street": "1 Main",
    "city": "Springfield",
    "geo": {"country": "US", "point": {"lat": 1.5, "lon": 2.5}},
    "phones": [{"type": "home", "number": "555", "expires": "2030-01-01"}],
}


def test_an_authored_occurrence_decodes_at_every_depth() -> None:
    # The `many` element's `expires` is an ISO date STRING, which only the serde
    # crossing admits: an undecoded string is no member of `date`'s value space,
    # so a verb that skipped the crossing would refuse this document rather than
    # bind it. What reaches storage is the canonical spelling of the whole
    # subtree, nested `one` and `many` alike.
    port = RecordingPort(rows=[])
    data: dict[str, Any] = {"id": 1, "name": "Ada", "address": copy.deepcopy(_ADDRESS)}

    db_for(CONTACT, port).transact(
        lambda tx: tx.wire.insert("parallax.compatibility.Contact", data)
    )

    assert _bound_address(port) == {
        "street": "1 Main",
        "city": "Springfield",
        "geo": {"country": "US", "point": {"lat": 1.5, "lon": 2.5}},
        "phones": [{"type": "home", "number": "555", "expires": "2030-01-01"}],
    }


def test_an_authored_occurrence_is_captured_at_the_call() -> None:
    port = RecordingPort(rows=[])
    address: dict[str, Any] = copy.deepcopy(_ADDRESS)
    data: dict[str, Any] = {"id": 1, "name": "Ada", "address": address}

    def fn(tx: Transaction) -> None:
        tx.wire.insert("parallax.compatibility.Contact", data)
        cast("list[dict[str, Any]]", address["phones"]).append({"type": "work"})
        cast("dict[str, Any]", address["geo"])["country"] = "FR"

    db_for(CONTACT, port).transact(fn)

    document = _bound_address(port)
    assert cast("dict[str, Any]", document["geo"])["country"] == "US"
    assert len(cast("list[object]", document["phones"])) == 1


def test_a_nullable_occurrence_may_be_authored_absent() -> None:
    port = RecordingPort(rows=[])
    db_for(CONTACT, port).transact(
        lambda tx: tx.wire.insert(
            "parallax.compatibility.Contact", {"id": 1, "name": "Ada", "address": None}
        )
    )
    assert len(_writes(port)) == 1


@pytest.mark.parametrize(
    "address",
    [
        5,
        {**_ADDRESS, "phones": "oops"},
        {**_ADDRESS, "geo": 7},
    ],
)
def test_a_malformed_occurrence_document_is_refused_by_the_judgement(address: object) -> None:
    # Decoding is total and nonthrowing, so a value no declared decoding
    # recognizes reaches the type verdict rather than a decoding failure.
    port = RecordingPort(rows=[])

    def fn(tx: Transaction) -> None:
        with pytest.raises(WriteRejectedError, match=r"Contact\.address"):
            tx.wire.insert(
                "parallax.compatibility.Contact",
                {"id": 1, "name": "Ada", "address": copy.deepcopy(address)},
            )

    db_for(CONTACT, port).transact(fn)
    assert _writes(port) == []


def test_a_predicate_target_that_is_not_a_document_is_refused() -> None:
    port = RecordingPort(rows=[])

    def fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError, match="canonical"):
            tx.wire.delete_where(cast("dict[str, object]", ["Person"]))

    db_for(PERSON, port).transact(fn)


def test_an_insert_naming_an_undeclared_member_reaches_the_honesty_gate() -> None:
    # Decoding leaves a key the model declares no member for exactly as authored,
    # so what names it is the member-name honesty gate rather than a decoding
    # failure standing in for one.
    port = RecordingPort(rows=[])

    def fn(tx: Transaction) -> None:
        with pytest.raises(instructions.WriteInstructionError, match="undeclared member"):
            tx.wire.insert("parallax.compatibility.Person", {"id": 9, "name": "Newton", "nope": 1})

    db_for(PERSON, port).transact(fn)
    assert _writes(port) == []
