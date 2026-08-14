"""The first-party seams beside the developer surface: the values lane
(``db.read_rows`` / ``tx.read_rows``) and the conformance bridge
(``tx.observed_read`` / ``tx.write_neutral``).

Docker-free, against the shared recording port. What these pin is that a caller
holding no Entity Class reaches the SAME unit of work a typed caller does — the
same read gate, the same force-flush, the same lock suffix, the same observation
record, the same carrier decision, the same flush triggers — and that the record
a participating bridge read answers with is the exact slot a bridge write then
settles against.
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
    PERSON,
    RecordingPort,
    account_db,
    db_for,
)

from _support import mirrored_models as mm
from parallax.conformance.class_models import MODELS
from parallax.conformance.graph_models import POLICY_MODEL, Policy
from parallax.conformance.story_models import Order
from parallax.core import LATEST, TX_TIME
from parallax.core.db_port import Row
from parallax.core.entity._model import model_of
from parallax.core.metamodel import EntityIdentity, entity_by_name
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query import deserialize as deserialize_query
from parallax.core.object_query._fluent import object_query_node
from parallax.core.unit_work import (
    EscapedTransactionError,
    ObjectKey,
    ObservedStateKey,
    RetainedObservation,
    TemporalStateKey,
    VersionedStateKey,
    VersionObservation,
    WriteInstruction,
    WritePlanningError,
    WriteRejectedError,
    instructions,
)
from parallax.snapshot import InvalidData
from parallax.snapshot.handle import (
    Database,
    DeferredFeatureError,
    QueryTargetError,
    Transaction,
    UnobservedWriteError,
)

ACCOUNT_META = model_of(ACCOUNT)
# `Account` is versioned, so the default `optimistic` preference resolves it to
# the Optimistic strategy and every keyed update binds the observed version last.
UPDATE_SQL = "update account set balance = %s, version = %s where id = %s and version = %s"
ACCOUNT_ROW: Row = {"id": 3, "owner": "Grace", "balance": Decimal("10"), "version": 1}
_TX_START = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_INFINITY = dt.datetime(9999, 12, 31, tzinfo=dt.UTC)
_OBSERVED_VERSION = VersionObservation(observed_version=1)
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


def _update(balance: int) -> WriteInstruction:
    return instructions.deserialize(
        {
            "mutation": "update",
            "entity": "parallax.compatibility.Account",
            "rows": [{"id": 3, "balance": balance}],
        }
    )


def _run[T](port: RecordingPort, fn: Callable[[Transaction], T]) -> T:
    return account_db(port).transact(fn).value


# --------------------------------------------------------------------------- #
# The values lane and the bridge read participate exactly as find does.        #
# --------------------------------------------------------------------------- #


def test_a_participating_row_read_publishes_the_rows_it_materialized() -> None:
    port = RecordingPort(rows=[ACCOUNT_ROW])
    rows = _run(port, lambda tx: tx.read_rows(_account_query()).rows)
    assert list(rows) == [ACCOUNT_ROW]
    assert port.ops == [("begin",), ("read", FIND_SQL_UNLOCKED, (3,)), ("commit",)]


def test_a_published_row_is_detached_from_the_mapping_it_was_built_from() -> None:
    port = RecordingPort(rows=[dict(ACCOUNT_ROW)])
    row = account_db(port).read_rows(_account_query()).rows[0]
    assert isinstance(row, Mapping)
    with pytest.raises(TypeError):
        cast("dict[str, object]", row)["owner"] = "mutated"


def test_a_standalone_bridge_read_takes_no_lock_and_files_no_record() -> None:
    port = RecordingPort(rows=[ACCOUNT_ROW])
    snapshot = account_db(port).wire.find(_account_query())
    assert port.ops == [("read", FIND_SQL_UNLOCKED, (3,))]
    assert snapshot.execution.round_trips == 1


def test_a_participating_bridge_read_answers_the_state_the_unit_of_work_retained() -> None:
    port = RecordingPort(rows=[ACCOUNT_ROW])

    def fn(tx: Transaction) -> object:
        read = tx.observed_read(_account_query())
        assert len(read.observations) == 1
        # The state the read retained under is the one the unit of work answers
        # for, which is what makes the key a REFERENCE rather than a
        # reconstruction.
        return read.observations[0].key

    assert cast("ObservedStateKey", _run(port, fn)) == _account_state()
    assert port.ops == [("begin",), ("read", FIND_SQL_UNLOCKED, (3,)), ("commit",)]


def test_a_bridge_read_answers_the_claim_of_every_node_it_published() -> None:
    # Every independently writable node carries its own claim, included children
    # among them, so a bridge write against a child settles against the state
    # that child's own row was read at rather than against its root's.
    port = RecordingPort(row_queue=([_policy_row()], [_coverage_row()]))
    query = object_query_node(
        Policy.where(Policy.id == 1).as_of(valid_time=LATEST).include(Policy.coverages)
    )

    def fn(tx: Transaction) -> tuple[ObservedStateKey, ...]:
        return tuple(claim.key for claim in tx.observed_read(query).observations)

    keys = db_for(POLICY_MODEL, port).transact(fn).value
    assert [key.object.entity.name for key in keys] == ["Policy", "Coverage"]
    assert [key.object.primary_key for key in keys] == [(("id", 1),), (("id", 10),)]


def test_a_non_hydrating_root_answers_no_claim_for_the_tree_below_it() -> None:
    # A claim belongs to a published Entity node. A non-hydrating root publishes
    # no value at all, and that covers its whole tree: the root's own hydratable
    # projection is excluded with the child that spoiled it, so the bridge holds
    # nothing and — once the read result is released — no observed state of that
    # row is addressable in the unit of work either. Holding the read's raw
    # sources instead would leave write authority for a row nothing published.
    port = RecordingPort(row_queue=([_policy_row()], [_coverage_row(amount=None)]))
    query = object_query_node(
        Policy.where(Policy.id == 1).as_of(valid_time=LATEST).include(Policy.coverages)
    )

    def fn(tx: Transaction) -> tuple[tuple[RetainedObservation, ...], int]:
        read = tx.observed_read(query)
        record = read.snapshot.checked().result()
        assert isinstance(record, InvalidData)
        assert cast("InvalidData[object]", record).data is None
        gc.collect()
        return read.observations, len(tx._uow._observations)  # pyright: ignore[reportPrivateUsage] - the index is first-party state

    claims, indexed = db_for(POLICY_MODEL, port).transact(fn).value
    assert claims == ()
    assert indexed == 0


def test_a_participating_read_force_flushes_pending_bridge_writes_first() -> None:
    port = RecordingPort(rows=[ACCOUNT_ROW])

    def fn(tx: Transaction) -> None:
        tx.write_neutral(_update(11), observation=VersionObservation(observed_version=1))
        tx.read_rows(_account_query())

    _run(port, fn)
    assert [op[0] for op in port.ops] == ["begin", "write", "read", "commit"]


# --------------------------------------------------------------------------- #
# The three observation forms.                                                 #
# --------------------------------------------------------------------------- #


def test_a_bare_instruction_buffers_with_no_evidence() -> None:
    port = RecordingPort()
    insert = instructions.deserialize(
        {
            "mutation": "insert",
            "entity": "parallax.compatibility.Account",
            "rows": [{"id": 7, "owner": "Newton", "balance": 5, "version": 1}],
        }
    )
    _run(port, lambda tx: tx.write_neutral(insert))
    assert [op[0] for op in port.ops] == ["begin", "write", "commit"]


def test_an_unversioned_instruction_claims_its_object_through_this_ingress_too() -> None:
    # A bridge caller holds an instruction rather than the value a verb derives
    # one from, so what its write settles against is derived here from the same
    # two declared facts a typed verb's own resolution reads. Without that, an
    # unversioned Non-Temporal write would claim nothing through this ingress and
    # a case would witness a coalescing a program never gets: two deletes of one
    # key reach the batch collapse as a repeated authored key.
    port = RecordingPort(rows=[{"id": 1, "name": "Ada"}])
    delete = instructions.deserialize(
        {
            "mutation": "delete",
            "entity": "parallax.compatibility.Person",
            "rows": [{"id": 1}],
        }
    )

    def fn(tx: Transaction) -> None:
        tx.write_neutral(delete)
        tx.write_neutral(delete)

    db_for(PERSON, port).transact(fn)
    assert [op[0] for op in port.ops] == ["begin", "write", "commit"]


def test_an_observation_supplied_for_an_insert_is_refused_not_dropped() -> None:
    # Evidence the caller holds is used as given, so a write that settles against
    # none refuses it: an opening row has no prior state for an observation to be
    # about, and dropping it would let the call claim to have settled against a
    # milestone that does not yet exist.
    port = RecordingPort()
    insert = instructions.deserialize(
        {
            "mutation": "insert",
            "entity": "parallax.compatibility.Account",
            "rows": [{"id": 7, "owner": "Newton", "balance": 5}],
        }
    )
    with pytest.raises(ValueError, match="an insert carries no Write Observation"):
        _run(port, lambda tx: tx.write_neutral(insert, observation=_OBSERVED_VERSION))


def test_an_observation_supplied_for_an_unversioned_target_is_refused_not_dropped() -> None:
    # The object arm is what a write against an unversioned Non-Temporal row
    # settles against when its caller holds nothing — never a place to put
    # evidence such a row cannot carry. The refusal is the model-aware one every
    # settled carrier crosses, rather than a silently unobserved write.
    port = RecordingPort(rows=[{"id": 1, "name": "Ada"}])
    update = instructions.deserialize(
        {
            "mutation": "update",
            "entity": "parallax.compatibility.Person",
            "rows": [{"id": 1, "name": "Grace"}],
        }
    )
    with pytest.raises(WritePlanningError, match="carries no Write Observation"):
        db_for(PERSON, port).transact(
            lambda tx: tx.write_neutral(update, observation=_OBSERVED_VERSION)
        )


def test_an_explicit_observation_licenses_the_version_advance() -> None:
    port = RecordingPort()
    _run(
        port,
        lambda tx: tx.write_neutral(
            _update(11), observation=VersionObservation(observed_version=1)
        ),
    )
    assert port.ops[1][1:] == (UPDATE_SQL, (11, 2, 3, 1))


def test_a_write_eliminated_before_dml_leaves_its_claim_unspent() -> None:
    # Consumption follows the surviving WRITE, never the batch it flushed in. The
    # key-only update is known no-op work and is eliminated before any DML, so the
    # claim it carried is still about stored state — even though the insert beside
    # it in the same flush reached the database and made the plan non-empty.
    port = RecordingPort(rows=[ACCOUNT_ROW])
    key_only = instructions.deserialize(
        {
            "mutation": "update",
            "entity": "parallax.compatibility.Account",
            "rows": [{"id": 3}],
        }
    )
    insert = instructions.deserialize(
        {
            "mutation": "insert",
            "entity": "parallax.compatibility.Account",
            "rows": [{"id": 7, "owner": "Newton", "balance": 5, "version": 1}],
        }
    )

    def fn(tx: Transaction) -> RetainedObservation:
        read = tx.observed_read(_account_query())
        claim = read.observations[0]
        tx.write_neutral(key_only, observation=claim.key)
        tx.write_neutral(insert)
        return claim

    spent = _run(port, fn)
    assert [op[0] for op in port.ops] == ["begin", "read", "write", "commit"]
    assert spent.consumed is False


def test_a_surviving_write_spends_its_own_claim() -> None:
    # The other half of the same rule: the claim a settled write carried is spent
    # once the executor returns, so a later transaction handed the same still-live
    # evidence is refused rather than writing over what this one wrote.
    port = RecordingPort(rows=[ACCOUNT_ROW])

    def fn(tx: Transaction) -> RetainedObservation:
        read = tx.observed_read(_account_query())
        claim = read.observations[0]
        tx.write_neutral(_update(11), observation=claim.key)
        return claim

    assert _run(port, fn).consumed is True


def test_an_observed_state_key_resolves_against_this_units_own_index() -> None:
    port = RecordingPort(rows=[ACCOUNT_ROW])

    def fn(tx: Transaction) -> None:
        read = tx.observed_read(_account_query())
        tx.write_neutral(_update(11), observation=read.observations[0].key)

    _run(port, fn)
    assert [op[0] for op in port.ops] == ["begin", "read", "write", "commit"]
    assert port.ops[2][1:] == (UPDATE_SQL, (11, 2, 3, 1))


# --------------------------------------------------------------------------- #
# Refusals.                                                                    #
# --------------------------------------------------------------------------- #


def test_a_key_naming_no_retained_observation_fails_at_the_call() -> None:
    port = RecordingPort()
    with pytest.raises(UnobservedWriteError) as raised:

        def fn(tx: Transaction) -> None:
            tx.write_neutral(_update(11), observation=_account_state())

        _run(port, fn)
    assert raised.value.code == "write-observation-not-recorded"
    # Nothing was buffered, so the doomed transaction emitted no DML at all.
    assert [op[0] for op in port.ops] == ["begin", "rollback"]


def test_a_key_is_invalid_once_its_unit_of_work_has_ended() -> None:
    port = RecordingPort(rows=[ACCOUNT_ROW])
    escaped: list[Transaction] = []

    def fn(tx: Transaction) -> None:
        escaped.append(tx)

    _run(port, fn)
    with pytest.raises(EscapedTransactionError):
        escaped[0].write_neutral(_update(11), observation=_account_state())


def test_a_keyed_instruction_reaches_the_model_aware_validator_the_typed_verbs_do() -> None:
    # An insert omitting a required attribute is a MODEL judgment, invisible to
    # the member-name honesty gate: the row names nothing undeclared. The neutral
    # ingress runs `validate_write` for it, so it is refused with the same
    # classified rule `Transaction._buffer` and the rejected run lane report.
    port = RecordingPort()
    incomplete = instructions.deserialize(
        {
            "mutation": "insert",
            "entity": "parallax.compatibility.Account",
            "rows": [{"id": 7, "balance": 5}],
        }
    )
    with pytest.raises(WriteRejectedError) as raised:
        _run(port, lambda tx: tx.write_neutral(incomplete))
    assert raised.value.rule == "write-required-attribute-missing"
    assert [op[0] for op in port.ops] == ["begin", "rollback"]


def test_an_unresolvable_entity_spelling_is_refused_as_a_naming_defect() -> None:
    # The row judgment presupposes a target, so a spelling naming no declared
    # Entity is left to `validate_instruction`, which owns that classification —
    # never reported as a member complaint about an Entity the model lacks.
    port = RecordingPort()
    unknown = instructions.deserialize(
        {"mutation": "update", "entity": "NoSuchEntity", "rows": [{"id": 3, "balance": 11}]}
    )
    with pytest.raises(instructions.WriteInstructionError, match="NoSuchEntity"):
        _run(port, lambda tx: tx.write_neutral(unknown))
    assert [op[0] for op in port.ops] == ["begin", "rollback"]


def test_a_predicate_instruction_takes_no_observation() -> None:
    port = RecordingPort()
    predicate = instructions.deserialize(
        {
            "mutation": "update",
            "target": {
                "entity": "parallax.compatibility.Account",
                "predicate": {"eq": {"attr": "parallax.compatibility.Account.id", "value": 3}},
            },
            "assignments": [{"attr": "parallax.compatibility.Account.balance", "value": 11}],
        }
    )
    with pytest.raises(TypeError, match="resolves its own per-row evidence"):

        def fn(tx: Transaction) -> None:
            tx.write_neutral(predicate, observation=VersionObservation(observed_version=1))

        _run(port, fn)


def test_a_predicate_instruction_buffers_through_the_shared_predicate_seam() -> None:
    port = RecordingPort(rows=[ACCOUNT_ROW])
    _run(port, lambda tx: tx.write_neutral(_predicate_update()))
    # A versioned target materializes: the resolving read, then one keyed write
    # per resolved row (`m-opt-lock`, ADR 0014) — the readless template is not
    # available and the neutral ingress does not invent one.
    assert [op[0] for op in port.ops] == ["begin", "read", "write", "commit"]


# --------------------------------------------------------------------------- #
# The shared read gate, and the milestone-set form.                            #
# --------------------------------------------------------------------------- #


def test_the_row_read_is_refused_for_an_undeclared_target() -> None:
    with pytest.raises(QueryTargetError):
        account_db(RecordingPort()).read_rows(_account_query("parallax.compatibility.NoSuchEntity"))


def test_a_refused_participating_read_flushes_nothing() -> None:
    # The gate runs BEFORE `uow.read`, whose force-flush would otherwise execute
    # the pending buffer on the way to a read that was going to be refused —
    # turning a refusal into a write. `tx.find` is held to the same ordering.
    port = RecordingPort()
    query = _account_query("parallax.compatibility.NoSuchEntity")

    def fn(tx: Transaction) -> None:
        tx.write_neutral(_update(11), observation=VersionObservation(observed_version=1))
        tx.read_rows(query)

    with pytest.raises(QueryTargetError):
        _run(port, fn)
    assert [op[0] for op in port.ops] == ["begin", "rollback"]


def test_the_bridge_read_reports_a_deferred_feature_by_name() -> None:
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
        _policy_db(RecordingPort()).wire.find(query)
    assert raised.value.features == ("snapshot-history-includes",)


def test_a_deferred_participating_read_flushes_nothing() -> None:
    # The classification runs BEFORE `uow.read`, whose force-flush would
    # otherwise execute the pending buffer on the way to a read that was going
    # to be refused — turning a deferral into a write.
    port = RecordingPort()
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
        tx.write_neutral(_policy_insert())
        tx.observed_read(query)

    with pytest.raises(DeferredFeatureError) as raised:
        _policy_db(port).transact(fn)
    assert raised.value.features == ("snapshot-history-includes",)
    assert [op[0] for op in port.ops] == ["begin", "rollback"]


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
        _policy_db(RecordingPort(rows=[])).read_rows(query)


def test_a_refused_row_form_participating_read_flushes_nothing() -> None:
    # The form refusal is the read gate's, not the values lane's, so it lands on
    # the same side of `uow.read`'s force-flush as the other three: a pending
    # buffered write is still pending when the refusal escapes, and the
    # transaction rolls back having executed no DML.
    port = RecordingPort(rows=[_ORDER_ROW])
    query = deserialize_query(
        {
            "target": "parallax.compatibility.Order",
            "predicate": {"all": {}},
            "includes": [{"segments": [{"rel": "parallax.compatibility.Order.items"}]}],
        }
    )

    def fn(tx: Transaction) -> None:
        tx.write_neutral(_order_update())
        tx.read_rows(query)

    with pytest.raises(ValueError, match="row-form read materializes no relationships"):
        _run_on(db_for(MODELS["orders"], port), fn)
    assert [op[0] for op in port.ops] == ["begin", "rollback"]


def test_an_ordered_capped_query_carrying_no_includes_still_answers() -> None:
    # The refusal is about a relationship level, not about how many clauses a
    # query fills: ordering and a cap add none.
    port = RecordingPort(rows=[_ORDER_ROW])
    query = deserialize_query(
        {
            "target": "parallax.compatibility.Order",
            "predicate": {"all": {}},
            "orderBy": [{"attr": "parallax.compatibility.Order.id"}],
            "limit": 1,
        }
    )
    assert db_for(MODELS["orders"], port).read_rows(query).rows == (_ORDER_ROW,)


def _order_update() -> WriteInstruction:
    return instructions.deserialize(
        {
            "mutation": "update",
            "entity": "parallax.compatibility.Order",
            "rows": [{"id": 1, "qty": 7}],
        }
    )


def _policy_db(port: RecordingPort) -> Database:
    return db_for(MODELS["policy"], port)


def _policy_insert() -> WriteInstruction:
    return instructions.deserialize(
        {
            "mutation": "insert",
            "entity": "parallax.compatibility.Policy",
            "rows": [{"id": 1, "name": "Fleet"}],
            "validFrom": "2024-07-01T00:00:00+00:00",
        }
    )


def test_a_milestone_set_bridge_read_retains_no_evidence() -> None:
    port = RecordingPort(rows=_balance_history_rows())
    query = object_query_node(mm.Balance.where(mm.Balance.id == 1).history(TX_TIME))

    def fn(tx: Transaction) -> object:
        read = tx.observed_read(query)
        return read.observations

    # A milestone-set read retains no evidence at all, exactly as `tx.find`'s own
    # history branch does, so it answers no state to settle against: a key here
    # would name nothing and fail the write it was handed to.
    assert _run_on(db_for(BALANCE, port), fn) == ()


def test_a_temporal_record_names_the_state_its_own_milestone_qualifies() -> None:
    port = RecordingPort(rows=[_balance_history_rows()[1]])
    query = object_query_node(mm.Balance.where(mm.Balance.id == 1))

    def fn(tx: Transaction) -> object:
        read = tx.observed_read(query)
        key = read.observations[0].key
        # A milestone chain holds several rows per primary key, so the state the
        # retaining side addresses is qualified by the milestone the row names.
        assert isinstance(key, TemporalStateKey)
        return key

    key = cast("TemporalStateKey", _run_on(db_for(BALANCE, port), fn))
    assert key.object.primary_key == (("id", 1),)


def test_an_unversioned_non_temporal_read_retains_no_evidence() -> None:
    port = RecordingPort(rows=[_ORDER_ROW])
    query = object_query_node(Order.where(Order.id == 1))

    def fn(tx: Transaction) -> object:
        return tx.observed_read(query).observations

    assert _run_on(db_for(MODELS["orders"], port), fn) == ()


def _run_on[T](db: Database, fn: Callable[[Transaction], T]) -> T:
    return db.transact(fn).value


def _predicate_update() -> WriteInstruction:
    return instructions.deserialize(
        {
            "mutation": "update",
            "target": {
                "entity": "parallax.compatibility.Account",
                "predicate": {"eq": {"attr": "parallax.compatibility.Account.id", "value": 3}},
            },
            "assignments": [{"attr": "parallax.compatibility.Account.balance", "value": 11}],
        }
    )


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
