"""The first-party seam beside the developer surface — the values lane
(``db.read_rows`` / ``tx.read_rows``) — and the Wire read the conformance engine
settles its writes against.

Docker-free, against the shared recording port. What these pin is that a caller
holding no Entity Class reaches the SAME unit of work a typed caller does — the
same read gate, the same force-flush, the same lock suffix, the same observation
record, the same flush triggers — and that the claim a participating Wire read
files onto each node it published is the exact slot a keyed write off that node
then settles against.
"""

from __future__ import annotations

import datetime as dt
import gc
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import cast

import pytest
from _transact_support import (
    ACCOUNT,
    BALANCE,
    FIND_SQL_UNLOCKED,
    account_db,
    db_for,
    published_claims,
)

from _support import mirrored_models as mm
from _support.db_port import (
    BeginCall,
    CommitCall,
    Read,
    ReadCall,
    RollbackCall,
    ScriptedPort,
    Transact,
    Write,
    WriteCall,
)
from parallax.conformance.class_models import MODELS
from parallax.conformance.graph_models import POLICY_MODEL, Policy
from parallax.conformance.story_models import Order
from parallax.core import LATEST, TX_TIME
from parallax.core.db_port import DbPort, Row
from parallax.core.entity._model import model_of
from parallax.core.metamodel import EntityIdentity, entity_by_name
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query import deserialize as deserialize_query
from parallax.core.object_query._fluent import object_query_node
from parallax.core.unit_work import (
    ObjectKey,
    ObservedStateKey,
    RetainedObservation,
    TemporalStateKey,
    VersionedStateKey,
    WriteRejectedError,
)
from parallax.snapshot import InvalidData
from parallax.snapshot.handle import (
    Database,
    DeferredFeatureError,
    QueryTargetError,
    Transaction,
    WireEntity,
)

ACCOUNT_META = model_of(ACCOUNT)
# `Account` is versioned, so the default `optimistic` preference resolves it to
# the Optimistic strategy and every keyed update binds the observed version last.
UPDATE_SQL = "update account set balance = %s, version = %s where id = %s and version = %s"
ACCOUNT_ROW: Row = {"id": 3, "owner": "Grace", "balance": Decimal("10"), "version": 1}
_TX_START = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_INFINITY = dt.datetime(9999, 12, 31, tzinfo=dt.UTC)
_TEMPORAL_BOUNDS: Row = {
    "from_z": _TX_START,
    "thru_z": _INFINITY,
    "in_z": _TX_START,
    "out_z": _INFINITY,
}


def _policy_row() -> Row:
    return {"id": 1, "name": "P-1", **_TEMPORAL_BOUNDS}


def _coverage_row(amount: object = Decimal("250.00")) -> Row:
    return {"id": 10, "policy_id": 1, "amount": amount, **_TEMPORAL_BOUNDS}


def _account() -> EntityIdentity:
    entity = entity_by_name(ACCOUNT_META, "parallax.compatibility.Account")
    assert entity is not None
    return entity.identity


def _account_query(target: str = "parallax.compatibility.Account") -> ObjectQueryNode:
    return deserialize_query(
        {
            "target": target,
            "predicate": {"eq": {"attr": "parallax.compatibility.Account.id", "value": 3}},
        }
    )


def _latest(*dimensions: str) -> dict[str, object]:
    return {dimension: {"asOf": "latest"} for dimension in dimensions}


def _account_state() -> ObservedStateKey:
    return VersionedStateKey(ObjectKey(_account(), (("id", 3),)), 1)


def _node(tx: Transaction, query: ObjectQueryNode | None = None) -> WireEntity:
    return tx.wire.find(query if query is not None else _account_query()).result()


def _run[T](port: DbPort, fn: Callable[[Transaction], T]) -> T:
    return account_db(port).transact(fn)


# --------------------------------------------------------------------------- #
# The values lane and the Wire read participate exactly as find does.          #
# --------------------------------------------------------------------------- #


def test_a_participating_row_read_publishes_the_rows_it_materialized() -> None:
    port = ScriptedPort(Transact(Read(rows=[ACCOUNT_ROW])))
    rows = _run(port, lambda tx: tx.read_rows(_account_query()).rows)
    assert list(rows) == [ACCOUNT_ROW]
    assert port.calls == [BeginCall(), ReadCall(FIND_SQL_UNLOCKED, (3,)), CommitCall()]


def test_a_published_row_is_detached_from_the_mapping_it_was_built_from() -> None:
    port = ScriptedPort(Read(rows=[dict(ACCOUNT_ROW)]))
    row = account_db(port).read_rows(_account_query()).rows[0]
    assert isinstance(row, Mapping)
    with pytest.raises(TypeError):
        cast("dict[str, object]", row)["owner"] = "mutated"


def test_a_standalone_wire_read_takes_no_lock_and_files_no_record() -> None:
    port = ScriptedPort(Read(rows=[ACCOUNT_ROW]))
    account_db(port).wire.find(_account_query())
    assert port.calls == [ReadCall(FIND_SQL_UNLOCKED, (3,))]


def test_a_participating_wire_read_answers_the_state_the_unit_of_work_retained() -> None:
    port = ScriptedPort(Transact(Read(rows=[ACCOUNT_ROW])))

    def fn(tx: Transaction) -> object:
        claims = published_claims(tx.wire.find(_account_query()))
        assert len(claims) == 1
        # The state the read retained under is the one the unit of work answers
        # for, which is what makes the key a REFERENCE rather than a
        # reconstruction.
        return claims[0].key

    assert cast("ObservedStateKey", _run(port, fn)) == _account_state()
    assert port.calls == [BeginCall(), ReadCall(FIND_SQL_UNLOCKED, (3,)), CommitCall()]


def test_a_wire_read_answers_the_claim_of_every_node_it_published() -> None:
    # Every independently writable node carries its own claim, included children
    # among them, so a write against a child settles against the state that
    # child's own row was read at rather than against its root's.
    port = ScriptedPort(Transact(Read(rows=[_policy_row()]), Read(rows=[_coverage_row()])))
    query = object_query_node(
        Policy.where(Policy.id == 1).as_of(valid_time=LATEST).include(Policy.coverages)
    )

    def fn(tx: Transaction) -> tuple[ObservedStateKey, ...]:
        return tuple(claim.key for claim in published_claims(tx.wire.find(query)))

    keys = db_for(POLICY_MODEL, port).transact(fn)
    assert [key.object.entity.name for key in keys] == ["Policy", "Coverage"]
    assert [key.object.primary_key for key in keys] == [(("id", 1),), (("id", 10),)]


def test_a_non_hydrating_root_answers_no_claim_for_the_tree_below_it() -> None:
    # A claim belongs to a published Entity node. A non-hydrating root publishes
    # no value at all, and that covers its whole tree: the root's own hydratable
    # projection is excluded with the child that spoiled it, so a caller holds
    # nothing and — once the read result is released — no observed state of that
    # row is addressable in the unit of work either. Holding the read's raw
    # sources instead would leave write authority for a row nothing published.
    port = ScriptedPort(
        Transact(Read(rows=[_policy_row()]), Read(rows=[_coverage_row(amount=None)]))
    )
    query = object_query_node(
        Policy.where(Policy.id == 1).as_of(valid_time=LATEST).include(Policy.coverages)
    )

    def fn(tx: Transaction) -> tuple[tuple[RetainedObservation, ...], int]:
        snapshot = tx.wire.find(query)
        record = snapshot.checked().result()
        assert isinstance(record, InvalidData)
        assert cast("InvalidData[object]", record).data is None
        claims = published_claims(snapshot)
        gc.collect()
        return claims, len(tx._uow._observations)  # pyright: ignore[reportPrivateUsage] - the index is first-party state

    claims, indexed = db_for(POLICY_MODEL, port).transact(fn)
    assert claims == ()
    assert indexed == 0


def test_a_participating_row_read_force_flushes_a_pending_write_first() -> None:
    port = ScriptedPort(Transact(Read(rows=[ACCOUNT_ROW]), Write(), Read(rows=[ACCOUNT_ROW])))

    def fn(tx: Transaction) -> None:
        tx.wire.update(_node(tx), {"balance": 11})
        tx.read_rows(_account_query())

    _run(port, fn)
    assert [type(op) for op in port.calls] == [BeginCall, ReadCall, WriteCall, ReadCall, CommitCall]


# --------------------------------------------------------------------------- #
# What a published node's own claim is spent on.                               #
# --------------------------------------------------------------------------- #


def test_a_write_eliminated_before_dml_leaves_its_claim_unspent() -> None:
    # Consumption follows the surviving WRITE, never the batch it flushed in. The
    # second update restores the value the source published, which cancels the
    # assignment buffered before it, so nothing of account 3 reaches the wire and
    # the claim it carried is still about stored state — even though the insert
    # beside it in the same flush reached the database and made the plan
    # non-empty.
    port = ScriptedPort(Transact(Read(rows=[ACCOUNT_ROW]), Write()))

    def fn(tx: Transaction) -> RetainedObservation:
        snapshot = tx.wire.find(_account_query())
        claim = published_claims(snapshot)[0]
        node = snapshot.result()
        tx.wire.update(node, {"balance": 125})
        tx.wire.update(node, {"balance": node["balance"]})
        tx.wire.insert(
            "parallax.compatibility.Account", {"id": 7, "owner": "Newton", "balance": "5.00"}
        )
        return claim

    spent = _run(port, fn)
    assert [type(op) for op in port.calls] == [BeginCall, ReadCall, WriteCall, CommitCall]
    (written,) = (call for call in port.calls if isinstance(call, WriteCall))
    assert written.sql.startswith("insert into account")
    assert spent.consumed is False


def test_a_surviving_write_spends_its_own_claim() -> None:
    # The other half of the same rule: the claim a settled write carried is spent
    # once the executor returns, so a later transaction handed the same still-live
    # evidence is refused rather than writing over what this one wrote.
    port = ScriptedPort(Transact(Read(rows=[ACCOUNT_ROW]), Write()))

    def fn(tx: Transaction) -> RetainedObservation:
        snapshot = tx.wire.find(_account_query())
        claim = published_claims(snapshot)[0]
        tx.wire.update(snapshot.result(), {"balance": 11})
        return claim

    assert _run(port, fn).consumed is True
    assert port.calls[2] == WriteCall(UPDATE_SQL, (11, 2, 3, 1))


# --------------------------------------------------------------------------- #
# Refusals.                                                                    #
# --------------------------------------------------------------------------- #


def test_an_insert_payload_reaches_the_model_aware_validator_the_typed_verbs_do() -> None:
    # An insert omitting a required attribute is a MODEL judgment, invisible to
    # the member-name honesty gate: the payload names nothing undeclared. The
    # Wire verb runs `validate_write` for it, so it is refused with the same
    # classified rule the Typed keyed verbs and the rejected run lane report.
    port = ScriptedPort(Transact())
    with pytest.raises(WriteRejectedError) as raised:
        _run(
            port,
            lambda tx: tx.wire.insert(
                "parallax.compatibility.Account", {"id": 7, "balance": "5.00"}
            ),
        )
    assert raised.value.rule == "write-required-attribute-missing"
    assert [type(op) for op in port.calls] == [BeginCall, RollbackCall]


def test_a_predicate_write_buffers_through_the_shared_predicate_seam() -> None:
    port = ScriptedPort(Transact(Read(rows=[ACCOUNT_ROW]), Write()))
    _run(port, lambda tx: tx.wire.update_where(_predicate_target(), {"balance": 11}))
    # A versioned target materializes: the resolving read, then one keyed write
    # per resolved row (`m-opt-lock`, ADR 0014) — the readless template is not
    # available and the Wire ingress does not invent one.
    assert [type(op) for op in port.calls] == [BeginCall, ReadCall, WriteCall, CommitCall]


# --------------------------------------------------------------------------- #
# The shared read gate, and the milestone-set form.                            #
# --------------------------------------------------------------------------- #


def test_the_row_read_is_refused_for_an_undeclared_target() -> None:
    with pytest.raises(QueryTargetError):
        account_db(ScriptedPort()).read_rows(_account_query("parallax.compatibility.NoSuchEntity"))


def test_a_refused_participating_read_flushes_nothing() -> None:
    # The gate runs BEFORE `uow.read`, whose force-flush would otherwise execute
    # the pending buffer on the way to a read that was going to be refused —
    # turning a refusal into a write. `tx.find` is held to the same ordering.
    port = ScriptedPort(Transact())
    query = _account_query("parallax.compatibility.NoSuchEntity")

    def fn(tx: Transaction) -> None:
        tx.wire.insert("parallax.compatibility.Account", {"id": 7, "owner": "N", "balance": "5.00"})
        tx.read_rows(query)

    with pytest.raises(QueryTargetError):
        _run(port, fn)
    assert [type(op) for op in port.calls] == [BeginCall, RollbackCall]


def test_the_wire_read_reports_a_deferred_feature_by_name() -> None:
    query = deserialize_query(
        {
            "target": "parallax.compatibility.Policy",
            "predicate": {"all": {}},
            "temporal": {
                "valid-time": {"asOf": "latest"},
                "transaction-time": {"history": {}},
            },
            "includes": [{"segments": [{"rel": "parallax.compatibility.Policy.coverages"}]}],
        }
    )
    with pytest.raises(DeferredFeatureError) as raised:
        _policy_db(ScriptedPort()).wire.find(query)
    assert raised.value.features == ("snapshot-history-includes",)


def test_a_deferred_participating_read_flushes_nothing() -> None:
    # The classification runs BEFORE `uow.read`, whose force-flush would
    # otherwise execute the pending buffer on the way to a read that was going
    # to be refused — turning a deferral into a write.
    port = ScriptedPort(Transact())
    query = deserialize_query(
        {
            "target": "parallax.compatibility.Policy",
            "predicate": {"all": {}},
            "temporal": {
                "valid-time": {"asOf": "latest"},
                "transaction-time": {"history": {}},
            },
            "includes": [{"segments": [{"rel": "parallax.compatibility.Policy.coverages"}]}],
        }
    )

    def fn(tx: Transaction) -> None:
        _insert_policy(tx)
        tx.wire.find(query)

    with pytest.raises(DeferredFeatureError) as raised:
        _policy_db(port).transact(fn)
    assert raised.value.features == ("snapshot-history-includes",)
    assert [type(op) for op in port.calls] == [BeginCall, RollbackCall]


def test_a_row_form_read_refuses_the_relationship_levels_it_cannot_materialize() -> None:
    query = deserialize_query(
        {
            "target": "parallax.compatibility.Policy",
            "predicate": {"all": {}},
            "temporal": _latest("transaction-time", "valid-time"),
            "includes": [{"segments": [{"rel": "parallax.compatibility.Policy.coverages"}]}],
        }
    )
    with pytest.raises(ValueError, match="row-form read materializes no relationships"):
        _policy_db(ScriptedPort()).read_rows(query)


def test_a_refused_row_form_participating_read_flushes_nothing() -> None:
    # The form refusal is the read gate's, not the values lane's, so it lands on
    # the same side of `uow.read`'s force-flush as the other three: a pending
    # buffered write is still pending when the refusal escapes, and the
    # transaction rolls back having executed no DML.
    port = ScriptedPort(Transact())
    query = deserialize_query(
        {
            "target": "parallax.compatibility.Order",
            "predicate": {"all": {}},
            "includes": [{"segments": [{"rel": "parallax.compatibility.Order.items"}]}],
        }
    )

    def fn(tx: Transaction) -> None:
        tx.wire.insert("parallax.compatibility.Order", _ORDER_PAYLOAD)
        tx.read_rows(query)

    with pytest.raises(ValueError, match="row-form read materializes no relationships"):
        _run_on(db_for(MODELS["orders"], port), fn)
    assert [type(op) for op in port.calls] == [BeginCall, RollbackCall]


def test_an_ordered_capped_query_carrying_no_includes_still_answers() -> None:
    # The refusal is about a relationship level, not about how many clauses a
    # query fills: ordering and a cap add none.
    port = ScriptedPort(Read(rows=[_ORDER_ROW]))
    query = deserialize_query(
        {
            "target": "parallax.compatibility.Order",
            "predicate": {"all": {}},
            "orderBy": [{"attr": "parallax.compatibility.Order.id"}],
            "limit": 1,
        }
    )
    assert db_for(MODELS["orders"], port).read_rows(query).rows == (_ORDER_ROW,)


def _policy_db(port: DbPort) -> Database:
    return db_for(MODELS["policy"], port)


def _insert_policy(tx: Transaction) -> None:
    tx.wire.insert(
        "parallax.compatibility.Policy",
        {"id": 1, "name": "Fleet"},
        valid_from=dt.datetime(2024, 7, 1, tzinfo=dt.UTC),
    )


def test_a_milestone_set_wire_read_retains_no_evidence() -> None:
    port = ScriptedPort(Transact(Read(rows=_balance_history_rows())))
    query = object_query_node(mm.Balance.where(mm.Balance.id == 1).history(TX_TIME))

    def fn(tx: Transaction) -> object:
        return published_claims(tx.wire.find(query))

    # A milestone-set read retains no evidence at all, exactly as `tx.find`'s own
    # history branch does, so it answers no state to settle against: a key here
    # would name nothing and fail the write it was handed to.
    assert _run_on(db_for(BALANCE, port), fn) == ()


def test_a_temporal_record_names_the_state_its_own_milestone_qualifies() -> None:
    port = ScriptedPort(Transact(Read(rows=[_balance_history_rows()[1]])))
    query = object_query_node(mm.Balance.where(mm.Balance.id == 1))

    def fn(tx: Transaction) -> object:
        key = published_claims(tx.wire.find(query))[0].key
        # A milestone chain holds several rows per primary key, so the state the
        # retaining side addresses is qualified by the milestone the row names.
        assert isinstance(key, TemporalStateKey)
        return key

    key = cast("TemporalStateKey", _run_on(db_for(BALANCE, port), fn))
    assert key.object.primary_key == (("id", 1),)


def test_an_unversioned_non_temporal_read_retains_no_evidence() -> None:
    port = ScriptedPort(Transact(Read(rows=[_ORDER_ROW])))
    query = object_query_node(Order.where(Order.id == 1))

    def fn(tx: Transaction) -> object:
        return published_claims(tx.wire.find(query))

    assert _run_on(db_for(MODELS["orders"], port), fn) == ()


def _run_on[T](db: Database, fn: Callable[[Transaction], T]) -> T:
    return db.transact(fn)


def _predicate_target() -> dict[str, object]:
    return {
        "entity": "parallax.compatibility.Account",
        "predicate": {"eq": {"attr": "parallax.compatibility.Account.id", "value": 3}},
    }


def _balance_history_rows() -> list[Row]:
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


_ORDER_ROW: Row = {
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
