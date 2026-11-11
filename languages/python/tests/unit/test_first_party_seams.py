"""The Wire read the conformance engine settles its writes against, the
first-party seam beside the Typed developer surface.

Docker-free, against the shared recording port. What these pin is that a caller
holding no Entity Class reaches the SAME unit of work a typed caller does — the
same read gate, the same force-flush, the same lock suffix, the same observation
record, the same flush triggers — and that the claim a participating Wire read
files onto each node it published is the exact slot a keyed write off that node
then settles against.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal
from typing import cast

import pytest

from parallax.conformance.class_models import MODELS
from parallax.conformance.graph_models import POLICY_MODEL, Policy
from parallax.conformance.story_models import Order
from parallax.core import LATEST, TX_TIME, UnsupportedError
from parallax.core._execution._unit_work.instructions import (
    SET_BASED_WRITE_TARGET_UNSUPPORTED,
)
from parallax.core.internal.base import UsageError
from parallax.core.internal.db_port import DatabaseAdapter, MappingRow
from parallax.core.internal.entity._authored_resolver import object_query_node
from parallax.core.internal.entity._model import model_of
from parallax.core.internal.metamodel import EntityIdentity, entity_by_name
from parallax.core.internal.object_query import ObjectQueryNode
from parallax.core.internal.object_query import deserialize as deserialize_query
from parallax.core.internal.unit_work import (
    RetainedObservation,
)
from parallax.core.internal.write_plan import ObjectKey, ObjectStateKey, VersionObservation
from parallax.core.internal.write_plan.keys import TemporalObjectStateKey, VersionedObjectStateKey
from parallax.snapshot import ScopedDatabase, TxnContext, WireEntity
from tests._support import mirrored_models as mm
from tests._support.db_port import (
    BeginCall,
    CommitCall,
    Read,
    ReadCall,
    RollbackCall,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
)
from tests._support.errors import raises_code
from tests.unit._transact_support import (
    ACCOUNT,
    BALANCE,
    FIND_SQL_UNLOCKED,
    PERSON,
    account_db,
    db_for,
    published_claims,
)

ACCOUNT_META = model_of(ACCOUNT)
# `Account` is versioned, so the default `optimistic` preference resolves it to
# the Optimistic strategy and every keyed update binds the observed version last.
UPDATE_SQL = "update account set balance = ?, version = ? where id = ? and version = ?"
ACCOUNT_ROW: MappingRow = {"id": 3, "owner": "Grace", "balance": Decimal("10"), "version": 1}
_TX_START = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_INFINITY = dt.datetime(9999, 12, 31, tzinfo=dt.UTC)
_TEMPORAL_BOUNDS: MappingRow = {
    "from_z": _TX_START,
    "thru_z": _INFINITY,
    "in_z": _TX_START,
    "out_z": _INFINITY,
}


def _policy_row() -> MappingRow:
    return {"id": 1, "name": "P-1", **_TEMPORAL_BOUNDS}


def _coverage_row(amount: object = Decimal("250.00")) -> MappingRow:
    return {"id": 10, "policy_id": 1, "amount": amount, **_TEMPORAL_BOUNDS}


def _account() -> EntityIdentity:
    entity = entity_by_name(ACCOUNT_META, "parallax.compatibility.Account")
    assert entity is not None
    return entity.identity


def _account_query(target: str = "parallax.compatibility.Account") -> ObjectQueryNode:
    return deserialize_query(
        {
            "target": target,
            "predicate": {"eq": {"path": "parallax.compatibility.Account.id", "value": 3}},
        }
    )


def _account_state() -> ObjectStateKey:
    return VersionedObjectStateKey(ObjectKey(_account(), (("id", 3),)), 1)


def _node(tx: TxnContext, query: ObjectQueryNode | None = None) -> WireEntity:
    return tx.wire.find(query if query is not None else _account_query()).result()


def _run[T](adapter: DatabaseAdapter, fn: Callable[[TxnContext], T]) -> T:
    return account_db(adapter).transact(fn)


# --------------------------------------------------------------------------- #
# The Wire read participates exactly as find does.                             #
# --------------------------------------------------------------------------- #


def test_a_standalone_wire_read_takes_no_lock_and_files_no_record() -> None:
    port = ScriptedAdapter(Read(rows=[ACCOUNT_ROW]))
    account_db(port).wire.find(_account_query())
    assert port.calls == [ReadCall(FIND_SQL_UNLOCKED, (3,), read_only=True)]


def test_a_participating_wire_read_answers_the_state_the_unit_of_work_retained() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[ACCOUNT_ROW])))

    def fn(tx: TxnContext) -> object:
        claims = published_claims(tx.wire.find(_account_query()))
        assert len(claims) == 1
        # The state the read retained under is the one the unit of work answers
        # for, which is what makes the key a REFERENCE rather than a
        # reconstruction.
        return claims[0].key

    assert cast("ObjectStateKey", _run(port, fn)) == _account_state()
    assert port.calls == [
        BeginCall(),
        ReadCall(FIND_SQL_UNLOCKED, (3,), read_only=True),
        CommitCall(),
    ]


def test_a_wire_read_answers_the_claim_of_every_node_it_published() -> None:
    # Every independently writable node carries its own claim, included children
    # among them, so a write against a child settles against the state that
    # child's own row was read at rather than against its root's.
    port = ScriptedAdapter(Transact(Read(rows=[_policy_row()]), Read(rows=[_coverage_row()])))
    query = object_query_node(
        Policy.where(Policy.id == 1).as_of(valid_time=LATEST).include(Policy.coverages),
        POLICY_MODEL,
    )

    def fn(tx: TxnContext) -> tuple[ObjectStateKey, ...]:
        return tuple(claim.key for claim in published_claims(tx.wire.find(query)))

    keys = db_for(POLICY_MODEL, port).transact(fn)
    assert [key.object.entity.name for key in keys] == ["Policy", "Coverage"]
    assert [key.object.primary_key for key in keys] == [(("id", 1),), (("id", 10),)]


def test_a_participating_wire_read_force_flushes_a_pending_write_first() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[ACCOUNT_ROW]), Write(), Read(rows=[ACCOUNT_ROW])))

    def fn(tx: TxnContext) -> None:
        tx.wire.amend(_node(tx), {"balance": "11.00"})
        tx.wire.find(_account_query())

    _run(port, fn)
    assert [type(op) for op in port.calls] == [BeginCall, ReadCall, WriteCall, ReadCall, CommitCall]


# --------------------------------------------------------------------------- #
# What a published node's own claim observed, once its write completes.        #
# --------------------------------------------------------------------------- #


def test_a_baseline_equal_update_writes_literally_and_changes_its_claims_state() -> None:
    # An update restating the value the source published is still an assignment:
    # it composes after the update buffered before it, its final value reaches
    # the wire under the version guard, and the state the claim observed is no
    # longer the stored one.
    port = ScriptedAdapter(Transact(Read(rows=[ACCOUNT_ROW]), Write(times=2)))

    def fn(tx: TxnContext) -> RetainedObservation:
        snapshot = tx.wire.find(_account_query())
        claim = published_claims(snapshot)[0]
        node = snapshot.result()
        tx.wire.amend(node, {"balance": "125.00"})
        tx.wire.amend(node, {"balance": node["balance"]})
        tx.wire.insert(
            "parallax.compatibility.Account", {"id": 7, "owner": "Newton", "balance": "5.00"}
        )
        return claim

    spent = _run(port, fn)
    writes = [call for call in port.calls if isinstance(call, WriteCall)]
    assert [call.sql.split(" ", 1)[0] for call in writes] == ["insert", "update"]
    update = writes[1]
    assert update.sql == UPDATE_SQL
    assert update.binds == (Decimal("10"), 2, 3, 1)
    assert spent.invalidated


def test_a_surviving_write_changes_its_own_claims_state() -> None:
    # The other half of the same rule: once the executor returns, the claim a
    # settled write carried no longer describes the stored row, which its own
    # values and observation still do not pretend otherwise.
    port = ScriptedAdapter(Transact(Read(rows=[ACCOUNT_ROW]), Write()))

    def fn(tx: TxnContext) -> RetainedObservation:
        snapshot = tx.wire.find(_account_query())
        claim = published_claims(snapshot)[0]
        tx.wire.amend(snapshot.result(), {"balance": "11.00"})
        return claim

    claim = _run(port, fn)
    assert claim.invalidated
    assert claim.evidence == VersionObservation(observed_version=1)
    assert port.calls[2] == WriteCall(UPDATE_SQL, (Decimal("11.00"), 2, 3, 1))


# --------------------------------------------------------------------------- #
# An observation-free source continues under the lock its read took.           #
# --------------------------------------------------------------------------- #

_PERSON_ROW: MappingRow = {"id": 1, "name": "Ada"}
_PERSON_UPDATE: tuple[str, tuple[object, ...]] = (
    "update person set name = ? where id = ?",
    ("Grace", 1),
)
_REPRESENTATIONS = ["typed", "wire"]


def _person_query() -> ObjectQueryNode:
    return deserialize_query(
        {
            "target": "parallax.compatibility.Person",
            "predicate": {"eq": {"path": "parallax.compatibility.Person.id", "value": 1}},
        }
    )


def _read_person(tx: TxnContext, representation: str) -> mm.Person | WireEntity:
    if representation == "typed":
        return tx.find(mm.Person.where(mm.Person.id == 1)).result()
    return tx.wire.find(_person_query()).result()


def _rename(tx: TxnContext, source: mm.Person | WireEntity, name: str) -> None:
    if isinstance(source, WireEntity):
        tx.wire.amend(source, {"name": name})
    else:
        tx.amend(source.edit(name=name))


@pytest.mark.parametrize("name", ["Grace", "Ada"], ids=["changed", "equal"])
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
def test_a_completed_unversioned_write_leaves_its_source_writable(
    representation: str, name: str
) -> None:
    # An unversioned row's read observes no state, and the shared lock it took
    # still stands once a write through it completes — an equal value as much
    # as a changed one — so the source and a fresh read of the same row both
    # write again, as one object's coalesced write.
    port = ScriptedAdapter(
        Transact(
            Read(rows=[_PERSON_ROW]),
            Write(),
            Read(rows=[_PERSON_ROW]),
            Write(),
        )
    )

    def fn(tx: TxnContext) -> None:
        source = _read_person(tx, representation)
        _rename(tx, source, name)
        fresh = _read_person(tx, representation)
        _rename(tx, source, "Hopper")
        _rename(tx, fresh, "Lovelace")

    db_for(PERSON, port).transact(fn)
    writes = [call for call in port.calls if isinstance(call, WriteCall)]
    assert writes == [
        WriteCall(_PERSON_UPDATE[0], (name, 1)),
        WriteCall(_PERSON_UPDATE[0], ("Lovelace", 1)),
    ]


def test_every_copy_derived_from_an_unversioned_source_shares_its_authority() -> None:
    # Two edits of one read compose before the flush that completes them, and
    # the read value and every copy derived from it, before or after, write
    # again afterwards under the same authority.
    port = ScriptedAdapter(
        Transact(Read(rows=[_PERSON_ROW]), Write(), Read(rows=[_PERSON_ROW]), Write())
    )

    def fn(tx: TxnContext) -> None:
        source = tx.find(mm.Person.where(mm.Person.id == 1)).result()
        early = source.edit(name="Grace")
        tx.amend(source.edit(name="Hopper"))
        tx.amend(early)
        tx.find(mm.Person.where(mm.Person.id == 1))
        tx.amend(source.edit(name="Lovelace"))
        tx.amend(early.edit(name="Turing"))

    db_for(PERSON, port).transact(fn)
    writes = [call for call in port.calls if isinstance(call, WriteCall)]
    assert writes == [
        WriteCall(*_PERSON_UPDATE),
        WriteCall(_PERSON_UPDATE[0], ("Turing", 1)),
    ]


def test_an_empty_unversioned_update_neither_writes_nor_spends_its_source() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_PERSON_ROW]), Read(rows=[_PERSON_ROW]), Write()))

    def fn(tx: TxnContext) -> None:
        source = tx.wire.find(_person_query()).result()
        tx.wire.amend(source, {})
        tx.wire.find(_person_query())
        tx.wire.amend(source, {"name": "Grace"})

    db_for(PERSON, port).transact(fn)
    writes = [call for call in port.calls if isinstance(call, WriteCall)]
    assert writes == [WriteCall(*_PERSON_UPDATE)]


# --------------------------------------------------------------------------- #
# Refusals.                                                                    #
# --------------------------------------------------------------------------- #


def test_an_insert_payload_reaches_the_model_aware_validator_the_typed_verbs_do() -> None:
    # An insert omitting a required attribute is a MODEL judgment, invisible to
    # the member-name honesty gate: the payload names nothing undeclared. The
    # Wire verb's preparation judges it, so it is refused with the same
    # classified rule the Typed keyed verbs and the rejected run lane report.
    port = ScriptedAdapter(Transact())
    with pytest.raises(UsageError) as raised:
        _run(
            port,
            lambda tx: tx.wire.insert(
                "parallax.compatibility.Account", {"id": 7, "balance": "5.00"}
            ),
        )
    assert raised.value.code == "write-required-attribute-missing"
    assert [type(op) for op in port.calls] == [BeginCall, RollbackCall]


def test_a_predicate_write_of_a_versioned_target_is_refused_at_the_shared_predicate_seam() -> None:
    # A versioned target needs an observation one readless statement cannot
    # make (`m-batch-write`), and the Wire ingress does not invent a read.
    port = ScriptedAdapter(Transact())
    with pytest.raises(UsageError) as refused:
        _run(port, lambda tx: tx.wire.amend_where(_predicate_target(), {"balance": "11.00"}))
    assert refused.value.code == SET_BASED_WRITE_TARGET_UNSUPPORTED
    assert [type(op) for op in port.calls] == [BeginCall, RollbackCall]


# --------------------------------------------------------------------------- #
# The shared read gate, and the milestone-set form.                            #
# --------------------------------------------------------------------------- #


def test_the_wire_read_is_refused_for_an_undeclared_target() -> None:
    with raises_code(UsageError, "query-target-not-in-model"):
        account_db(ScriptedAdapter()).wire.find(
            _account_query("parallax.compatibility.NoSuchEntity")
        )


def test_a_refused_participating_read_flushes_nothing() -> None:
    # The gate runs BEFORE `uow.read`, whose force-flush would otherwise execute
    # the pending buffer on the way to a read that was going to be refused —
    # turning a refusal into a write. `tx.find` is held to the same ordering.
    port = ScriptedAdapter(Transact())
    query = _account_query("parallax.compatibility.NoSuchEntity")

    def fn(tx: TxnContext) -> None:
        tx.wire.insert("parallax.compatibility.Account", {"id": 7, "owner": "N", "balance": "5.00"})
        tx.wire.find(query)

    with raises_code(UsageError, "query-target-not-in-model"):
        _run(port, fn)
    assert [type(op) for op in port.calls] == [BeginCall, RollbackCall]


def test_the_wire_read_reports_a_deferred_feature_by_name() -> None:
    query = deserialize_query(
        {
            "target": "parallax.compatibility.Policy",
            "predicate": {"true": {}},
            "temporal": {
                "valid-time": {"asOf": "latest"},
                "transaction-time": {"history": {}},
            },
            "includes": [{"segments": [{"rel": "parallax.compatibility.Policy.coverages"}]}],
        }
    )
    with raises_code(UnsupportedError, "execution-feature-deferred") as raised:
        _policy_db(ScriptedAdapter()).wire.find(query)
    assert "has deferred snapshot-history-includes and" in raised.value.args[1]


def test_a_deferred_participating_read_flushes_nothing() -> None:
    # The classification runs BEFORE `uow.read`, whose force-flush would
    # otherwise execute the pending buffer on the way to a read that was going
    # to be refused — turning a deferral into a write.
    port = ScriptedAdapter(Transact())
    query = deserialize_query(
        {
            "target": "parallax.compatibility.Policy",
            "predicate": {"true": {}},
            "temporal": {
                "valid-time": {"asOf": "latest"},
                "transaction-time": {"history": {}},
            },
            "includes": [{"segments": [{"rel": "parallax.compatibility.Policy.coverages"}]}],
        }
    )

    def fn(tx: TxnContext) -> None:
        _insert_policy(tx)
        tx.wire.find(query)

    with raises_code(UnsupportedError, "execution-feature-deferred") as raised:
        _policy_db(port).transact(fn)
    assert "has deferred snapshot-history-includes and" in raised.value.args[1]
    assert [type(op) for op in port.calls] == [BeginCall, RollbackCall]


def _policy_db(adapter: DatabaseAdapter) -> ScopedDatabase:
    return db_for(MODELS["policy"], adapter)


def _insert_policy(tx: TxnContext) -> None:
    tx.wire.insert(
        "parallax.compatibility.Policy",
        {"id": 1, "name": "Fleet"},
        valid_from=dt.datetime(2024, 7, 1, tzinfo=dt.UTC),
    )


def test_a_milestone_set_wire_read_retains_no_evidence() -> None:
    port = ScriptedAdapter(Transact(Read(rows=_balance_history_rows())))
    query = object_query_node(mm.Balance.where(mm.Balance.id == 1).history(TX_TIME), BALANCE)

    def fn(tx: TxnContext) -> object:
        return published_claims(tx.wire.find(query))

    # A milestone-set read retains no evidence at all, exactly as `tx.find`'s own
    # history branch does, so it answers no state to settle against: a key here
    # would name nothing and fail the write it was handed to.
    assert _run_on(db_for(BALANCE, port), fn) == ()


def test_a_temporal_record_names_the_state_its_own_milestone_qualifies() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_balance_history_rows()[1]])))
    query = object_query_node(mm.Balance.where(mm.Balance.id == 1), BALANCE)

    def fn(tx: TxnContext) -> object:
        key = published_claims(tx.wire.find(query))[0].key
        # A milestone chain holds several rows per primary key, so the state the
        # retaining side addresses is qualified by the milestone the row names.
        assert isinstance(key, TemporalObjectStateKey)
        return key

    key = cast("TemporalObjectStateKey", _run_on(db_for(BALANCE, port), fn))
    assert key.object.primary_key == (("id", 1),)


def test_an_unversioned_non_temporal_read_retains_no_evidence() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_ORDER_ROW])))
    query = object_query_node(Order.where(Order.id == 1), MODELS["orders"])

    def fn(tx: TxnContext) -> object:
        return published_claims(tx.wire.find(query))

    assert _run_on(db_for(MODELS["orders"], port), fn) == ()


def _run_on[T](db: ScopedDatabase, fn: Callable[[TxnContext], T]) -> T:
    return db.transact(fn)


def _predicate_target() -> dict[str, object]:
    return {
        "entity": "parallax.compatibility.Account",
        "predicate": {"eq": {"path": "parallax.compatibility.Account.id", "value": 3}},
    }


def _balance_history_rows() -> list[MappingRow]:
    return [
        {
            "bal_id": 1,
            "acct_num": "A-1",
            "val": Decimal("5.00"),
            "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
            "out_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
        },
        {
            "bal_id": 1,
            "acct_num": "A-1",
            "val": Decimal("9.00"),
            "in_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
            "out_z": dt.datetime(9999, 12, 31, tzinfo=dt.UTC),
        },
    ]


_ORDER_ROW: MappingRow = {
    "id": 1,
    "name": "Order1",
    "sku": "X-1",
    "qty": 1,
    "price": Decimal("9.99"),
    "active": True,
    "ordered_on": dt.date(2024, 7, 1),
}


_ORDER_PAYLOAD: dict[str, object] = {
    "id": 2,
    "name": "Order2",
    "sku": "X-2",
    "qty": 1,
    "price": "9.99",
    "active": True,
    "orderedOn": "2024-07-01",
}
