"""Source-owned write evidence: identity, lifetime, and claim transfer.

The Python-interface half of the observed-state contract, driven through the real
handles over a fake port. Evidence belongs to the VALUE a read produced, so what
these tests measure is what a value carries, how long it lives, what survives an
edit or a copy, and what a conversion strips.

The seam's own mechanics — which rows retain what, and under which state key —
live in `test_write_inputs.py`; what lives here is the choreography a caller
actually performs.
"""

from __future__ import annotations

import datetime as dt
import gc
import pickle
from decimal import Decimal
from typing import Any, cast

import pytest
from _transact_support import (
    BALANCE,
    RecordingPort,
    account_db,
    balance_row,
    db_for,
    new_account,
)

from _support import mirrored_models as mm
from parallax.conformance import vo_models as vo
from parallax.core.unit_work import (
    OptimisticLockConflictError,
    VersionedStateKey,
    VersionObservation,
)
from parallax.snapshot import InvalidData, WireEntity, connect
from parallax.snapshot._inspection import snapshot_state_of
from parallax.snapshot.handle import KeyedWriteValueError, Transaction, WriteEvidenceError
from parallax.snapshot.materialize import source_hint_of

_ACCOUNT_ROW: dict[str, object] = {
    "id": 1,
    "owner": "Ada",
    "balance": Decimal("100.00"),
    "version": 4,
}
_TX_START = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


def _typed_hint(node: object) -> object:
    state = snapshot_state_of(node)
    assert state is not None
    return state.source


def _account_port(rows: list[dict[str, object]] | None = None) -> RecordingPort:
    return RecordingPort(rows=[dict(row) for row in (rows or [_ACCOUNT_ROW])])


# --------------------------------------------------------------------------- #
# What a source value carries.                                                #
# --------------------------------------------------------------------------- #
def test_a_typed_node_carries_the_state_its_row_observed() -> None:
    node = account_db(_account_port()).find(mm.Account.where(mm.Account.id == 1)).result()
    hint = _typed_hint(node)
    assert hint is not None
    assert cast("Any", hint).observation.key == VersionedStateKey(cast("Any", hint).object_key, 4)


def test_a_wire_node_and_a_typed_node_of_one_row_carry_the_identical_evidence() -> None:
    # The two representations of one observed state share ONE retained
    # observation object, not equal copies of one: consumption is the mutable
    # fact living on that object, so a second copy would keep licensing writes
    # after the flush that spent the first. Both reads participate and the typed
    # source stays live across the second, which is what makes them one state.
    port = RecordingPort(row_queue=([dict(_ACCOUNT_ROW)], [dict(_ACCOUNT_ROW)]))

    def fn(tx: Transaction) -> tuple[object, object]:
        typed = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        wire = tx.wire.find(mm.Account.where(mm.Account.id == 1)).result()
        assert isinstance(wire, WireEntity)
        return _typed_hint(typed), source_hint_of(wire)

    typed_hint, wire_hint = (cast("Any", hint) for hint in account_db(port).transact(fn).value)
    assert wire_hint is not None
    assert wire_hint.object_key == typed_hint.object_key
    assert wire_hint.observation is typed_hint.observation


# --------------------------------------------------------------------------- #
# Claim transfer and stripping.                                               #
# --------------------------------------------------------------------------- #
def test_entity_edit_transfers_the_sources_claim_to_the_derived_value() -> None:
    node = account_db(_account_port()).find(mm.Account.where(mm.Account.id == 1)).result()
    edited = node.edit(balance=Decimal("125.00"))
    assert _typed_hint(edited) is _typed_hint(node)


def test_wire_copy_answers_the_same_value_and_therefore_the_same_claim() -> None:
    import copy as copy_module

    node = account_db(_account_port()).wire.find(mm.Account.where(mm.Account.id == 1)).result()
    assert isinstance(node, WireEntity)
    for copied in (cast("Any", node).copy(), copy_module.copy(node), copy_module.deepcopy(node)):
        assert copied is node
        assert source_hint_of(cast("WireEntity", copied)) is source_hint_of(node)


def test_plain_dict_conversion_strips_a_wire_nodes_keyed_source_status() -> None:
    # The hint rides a slot rather than a mapping entry, so a plain conversion
    # carries none of it: what comes out is ordinary domain data, which is
    # exactly what it is.
    node = account_db(_account_port()).wire.find(mm.Account.where(mm.Account.id == 1)).result()
    assert isinstance(node, WireEntity)
    converted = dict(node)
    assert converted == dict(node.items())
    assert type(converted) is dict
    assert not isinstance(converted, WireEntity)
    assert not hasattr(converted, "_source")


def test_pickling_a_typed_node_strips_its_keyed_source_status() -> None:
    # A pickled value crosses a boundary the lifecycle state cannot: the hint and
    # the claim behind it describe a live read, and a round trip would otherwise
    # rebuild the claim as a fresh object whose consumed state is whatever the
    # bytes happened to capture. What comes back is ordinary domain data, so the
    # verbs refuse it as a value no read of this store produced.
    port = _account_port()
    db = account_db(port)
    node = db.find(mm.Account.where(mm.Account.id == 1)).result()

    restored = cast("mm.Account", pickle.loads(pickle.dumps(node)))
    assert restored == node
    assert snapshot_state_of(restored) is None

    with pytest.raises(KeyedWriteValueError) as refusal:
        db.transact(lambda tx: tx.update(restored.edit(balance=Decimal("125.00"))))
    assert refusal.value.code == "write-value-not-stored"
    assert not any(op[0] == "write" for op in port.ops)


def test_pickling_a_plainly_constructed_value_has_nothing_to_strip() -> None:
    # The other half of the same boundary: a value no read produced carries no
    # lifecycle state, so its round trip is the ordinary one and the result is
    # the value it always was.
    fresh = new_account()
    restored = cast("mm.Account", pickle.loads(pickle.dumps(fresh)))
    assert restored == fresh
    assert snapshot_state_of(restored) is None


# --------------------------------------------------------------------------- #
# Lifetime: liveness is strong reachability.                                  #
# --------------------------------------------------------------------------- #
def test_a_retained_included_child_outlives_its_released_root_and_snapshot() -> None:
    # Retaining a root naturally retains its children; extracting and retaining a
    # CHILD keeps that child's own evidence after the root and the Snapshot are
    # released, because the claim belongs to the entity node rather than to the
    # result it arrived in.
    from parallax.conformance.graph_models import POLICY_MODEL, Policy
    from parallax.core import LATEST

    policy_row: dict[str, object] = {
        "id": 1,
        "name": "P-1",
        "from_z": _TX_START,
        "thru_z": dt.datetime(9999, 12, 31, tzinfo=dt.UTC),
        "in_z": _TX_START,
        "out_z": dt.datetime(9999, 12, 31, tzinfo=dt.UTC),
    }
    coverage_row: dict[str, object] = {
        "id": 10,
        "policy_id": 1,
        "amount": Decimal("250.00"),
        "from_z": _TX_START,
        "thru_z": dt.datetime(9999, 12, 31, tzinfo=dt.UTC),
        "in_z": _TX_START,
        "out_z": dt.datetime(9999, 12, 31, tzinfo=dt.UTC),
    }
    port = RecordingPort(row_queue=([policy_row], [coverage_row]))
    snapshot = db_for(POLICY_MODEL, port).find(
        Policy.where(Policy.id == 1).as_of(valid_time=LATEST).include(Policy.coverages)
    )
    child = snapshot.result().coverages[0]
    del snapshot
    gc.collect()
    hint = cast("Any", _typed_hint(child))
    assert hint.observation is not None
    assert hint.object_key.primary_key == (("id", 10),)


def test_releasing_every_source_makes_the_transactions_index_forget_the_state() -> None:
    # Liveness IS the reference graph: the unit of work holds a WEAK index, so an
    # observed state no source value and no buffered write reaches disappears
    # from it on the runtime's own collection schedule, with no claim counting
    # and no scope-bound bookkeeping.
    port = _account_port()

    def fn(tx: Transaction) -> tuple[object, object]:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        hint = cast("Any", _typed_hint(node))
        state = hint.observation.key
        held = tx._uow.retained_for(state)  # pyright: ignore[reportPrivateUsage] - the index is first-party state
        assert held is hint.observation
        del node, hint, held
        gc.collect()
        return state, tx._uow.retained_for(state)  # pyright: ignore[reportPrivateUsage] - the index is first-party state

    state, after_release = account_db(port).transact(fn).value
    assert state is not None
    assert after_release is None


# --------------------------------------------------------------------------- #
# Consumption: what a successful flush spends.                                #
# --------------------------------------------------------------------------- #
def test_a_successful_flush_consumes_the_evidence_its_write_used() -> None:
    port = _account_port()

    def fn(tx: Transaction) -> object:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(node.edit(balance=Decimal("125.00")))
        return _typed_hint(node)

    hint = cast("Any", account_db(port).transact(fn).value)
    assert hint.observation.consumed is True


def test_reusing_a_consumed_source_after_the_flush_is_refused() -> None:
    # A consumed source stays an ordinary readable value; what it no longer
    # carries is authority, because the state it observed is not the stored state
    # any more. The refusal is at the second verb, before any DML of its own.
    port = _account_port()
    db = account_db(port)

    def fn(tx: Transaction) -> mm.Account:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(node.edit(balance=Decimal("125.00")))
        return node

    stale = db.transact(fn).value

    def second(tx: Transaction) -> None:
        tx.update(stale.edit(balance=Decimal("150.00")))

    with pytest.raises(WriteEvidenceError) as refusal:
        db.transact(second)
    assert refusal.value.code == "write-evidence-consumed"
    assert [op[0] for op in port.ops].count("write") == 1


def test_a_locking_source_consumed_by_a_flush_cannot_drive_a_second_write() -> None:
    # Consumption is strategy-independent. The shared row lock licenses a write
    # against the state the locked read saw; it says nothing about a state this
    # unit of work has itself already written past, so the participating source
    # that drove the surviving write carries no authority for a second one. The
    # dependent read in the middle is what forces that first write out.
    port = RecordingPort(row_queue=([dict(_ACCOUNT_ROW)], [dict(_ACCOUNT_ROW)]))

    def fn(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(node.edit(balance=Decimal("125.00")))
        tx.find(mm.Account.where(mm.Account.id == 1))
        tx.update(node.edit(balance=Decimal("150.00")))

    with pytest.raises(WriteEvidenceError) as refusal:
        account_db(port).transact(fn, concurrency="locking")
    assert refusal.value.code == "write-evidence-consumed"
    assert [op[0] for op in port.ops].count("write") == 1


def test_an_intent_eliminated_before_dml_consumes_nothing() -> None:
    # An edited copy whose effective change set is empty buffers nothing and
    # issues no statement, so the evidence its source carries is still about the
    # stored state and still licenses a later write.
    port = _account_port()
    db = account_db(port)

    def fn(tx: Transaction) -> mm.Account:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        tx.update(node.edit(balance=Decimal("100.00")))
        return node

    unchanged = db.transact(fn).value
    assert cast("Any", _typed_hint(unchanged)).observation.consumed is False
    assert not any(op[0] == "write" for op in port.ops)


def test_an_aborted_flush_spends_no_evidence() -> None:
    # A failed flush aborts the transaction, so nothing it wrote survives and the
    # evidence a live value carries is still about stored state — which is why
    # abort needs no restoration.
    port = _account_port()
    db = account_db(port)
    escaped: list[mm.Account] = []

    def doomed(tx: Transaction) -> None:
        node = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        escaped.append(node)
        tx.update(node.edit(balance=Decimal("125.00")))
        raise RuntimeError("abort")

    with pytest.raises(RuntimeError, match="abort"):
        db.transact(doomed)
    assert cast("Any", _typed_hint(escaped[0])).observation.consumed is False


# --------------------------------------------------------------------------- #
# Several observed states of one object.                                      #
# --------------------------------------------------------------------------- #
def test_two_observed_versions_of_one_object_coexist_and_resolve_independently() -> None:
    # A reread that sees a NEW version is evidence about a different state, so
    # the older live value is not upgraded: it keeps the version it observed, and
    # a write from it gates on that version rather than on the fresher one.
    port = RecordingPort(row_queue=([dict(_ACCOUNT_ROW)], [{**_ACCOUNT_ROW, "version": 7}]))
    db = account_db(port)

    def fn(tx: Transaction) -> tuple[object, object]:
        first = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        second = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        return _typed_hint(first), _typed_hint(second)

    earlier, later = db.transact(fn).value
    assert cast("Any", earlier).observation is not cast("Any", later).observation
    assert cast("Any", earlier).observation.evidence == VersionObservation(observed_version=4)
    assert cast("Any", later).observation.evidence == VersionObservation(observed_version=7)


def test_a_reread_of_one_state_answers_the_evidence_the_first_read_retained() -> None:
    # Two reads that resolve to ONE observed state share one claim, exactly as
    # two graph positions reaching one node do — so a flush that spends the state
    # spends it for both rather than leaving a second live value able to rewrite
    # what was just written.
    port = RecordingPort(row_queue=([dict(_ACCOUNT_ROW)], [dict(_ACCOUNT_ROW)]))

    def fn(tx: Transaction) -> tuple[object, object]:
        first = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        second = tx.find(mm.Account.where(mm.Account.id == 1)).result()
        return _typed_hint(first), _typed_hint(second)

    earlier, later = account_db(port).transact(fn).value
    assert cast("Any", earlier).observation is cast("Any", later).observation


# --------------------------------------------------------------------------- #
# The standalone optimistic source.                                           #
# --------------------------------------------------------------------------- #
def test_a_standalone_versioned_source_gates_a_later_transactions_write() -> None:
    # The default preference resolves `Account` to Optimistic, where the database
    # gate is the authority — so a value a plain `db.find` produced carries the
    # version it observed into a later transaction and no reread is issued.
    port = _account_port()
    db = account_db(port)
    node = db.find(mm.Account.where(mm.Account.id == 1)).result()

    db.transact(lambda tx: tx.update(node.edit(balance=Decimal("125.00"))))
    assert [op[0] for op in port.ops] == ["read", "begin", "write", "commit"]
    update = port.ops[2]
    assert cast("tuple[object, ...]", update[2])[-1] == 4


def test_a_standalone_versioned_source_meeting_an_intervening_writer_conflicts() -> None:
    # The gate is the concurrency authority, so a stale standalone source is not
    # refused at the verb — it is admitted, and its zero-row gated UPDATE raises
    # the ordinary optimistic conflict the database discovered.
    port = _account_port()
    db = account_db(port)
    node = db.find(mm.Account.where(mm.Account.id == 1)).result()
    port.write_affected = 0

    with pytest.raises(OptimisticLockConflictError):
        db.transact(lambda tx: tx.update(node.edit(balance=Decimal("125.00"))))


def test_a_standalone_temporal_source_carries_its_milestone_into_a_transaction() -> None:
    port = RecordingPort(rows=[balance_row(in_z=_TX_START)])
    db = db_for(BALANCE, port)
    node = db.find(mm.Balance.where(mm.Balance.id == 1)).result()

    db.transact(lambda tx: tx.update(node.edit(value=Decimal("9.00"))))
    assert [op[0] for op in port.ops] == ["read", "begin", "write", "write", "commit"]


# --------------------------------------------------------------------------- #
# Classified sources.                                                         #
# --------------------------------------------------------------------------- #
def test_a_hydratable_invalid_root_carries_its_ordinary_claim() -> None:
    # A hydratable violation's collapse produced legal member values, so the row
    # behind it is an ordinary stored row: the node in `data` carries the same
    # evidence any conforming node of that read would, and stays an ordinary
    # write source. Only a non-hydrating position, which has no conforming value
    # at all, carries none.
    port = RecordingPort(rows=[{"id": 1, "name": "Ada", "address": {"city": "Berlin"}}])
    record = (
        connect(port, vo.CUSTOMER_MODEL)
        .find(vo.Customer.where(vo.Customer.id == 1))
        .checked()
        .result()
    )
    assert isinstance(record, InvalidData)
    hint = cast("Any", _typed_hint(record.data))
    assert hint is not None
    assert hint.object_key.primary_key == (("id", 1),)
