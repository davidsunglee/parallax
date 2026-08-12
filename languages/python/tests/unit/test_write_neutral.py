"""The model-neutral runtime seam: ``tx.read_neutral`` and ``tx.write_neutral``.

Docker-free, against the shared recording port. What these pin is that a caller
with no Entity Class reaches the SAME unit of work a typed caller does — the same
force-flush, the same lock suffix, the same observation record, the same carrier
decision, the same flush triggers — and that the Observation Key a neutral read
publishes is the exact slot a neutral write then settles against.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal
from typing import cast

import pytest
from _transact_support import (
    ACCOUNT,
    BALANCE,
    FIND_SQL,
    FIND_SQL_NO_LOCK,
    RecordingPort,
    account_db,
    db_for,
)

from _support import mirrored_models as mm
from parallax.conformance.class_models import MODELS
from parallax.conformance.story_models import Order
from parallax.core import TX_TIME
from parallax.core.db_port import Row
from parallax.core.entity._model import model_of
from parallax.core.metamodel import EntityIdentity, entity_by_name
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query import deserialize as deserialize_query
from parallax.core.object_query._fluent import object_query_node
from parallax.core.unit_work import (
    EscapedTransactionError,
    ObjectKey,
    ObservationKey,
    VersionObservation,
    WriteInstruction,
    WriteRejectedError,
    instructions,
)
from parallax.snapshot.handle import (
    Database,
    DeferredFeatureError,
    NeutralGraph,
    NeutralGraphs,
    NeutralReadRequest,
    NeutralRows,
    QueryTargetError,
    Transaction,
    UnobservedWriteError,
)

ACCOUNT_META = model_of(ACCOUNT)
UPDATE_SQL = "update account set balance = %s, version = %s where id = %s"
ACCOUNT_ROW: Row = {"id": 3, "owner": "Grace", "balance": 10, "version": 1}


def _account() -> EntityIdentity:
    entity = entity_by_name(ACCOUNT_META, "parallax.compatibility.Account")
    assert entity is not None
    return entity.identity


def _rows_request() -> NeutralReadRequest:
    return NeutralReadRequest.rows(_account_query())


def _graph_request() -> NeutralReadRequest:
    return NeutralReadRequest.graph(_account_query())


def _account_query(target: str = "parallax.compatibility.Account") -> ObjectQueryNode:
    return deserialize_query(
        {
            "target": target,
            "predicate": {"eq": {"attr": "parallax.compatibility.Account.id", "value": 3}},
        }
    )


def _latest(*dimensions: str) -> dict[str, object]:
    return {dimension: {"asOf": "latest"} for dimension in dimensions}


def _account_slot() -> ObservationKey:
    return ObservationKey(ObjectKey(_account(), (("id", 3),)), None)


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
# read_neutral participates exactly as find does.                              #
# --------------------------------------------------------------------------- #


def test_a_participating_row_read_takes_the_transactions_own_lock() -> None:
    port = RecordingPort(rows=[ACCOUNT_ROW])
    rows = _run(port, lambda tx: tx.read_neutral(_rows_request()).output)
    assert isinstance(rows, NeutralRows)
    assert list(rows) == [ACCOUNT_ROW]
    assert port.ops == [("begin",), ("read", FIND_SQL, (3,)), ("commit",)]


def test_a_standalone_neutral_read_takes_no_lock_and_publishes_no_key() -> None:
    port = RecordingPort(rows=[ACCOUNT_ROW])
    result = account_db(port).read_neutral(_graph_request())
    graph = result.output
    assert isinstance(graph, NeutralGraph)
    assert graph.roots[0].node.observation_key is None
    assert port.ops == [("read", FIND_SQL_NO_LOCK, (3,))]
    assert result.execution.round_trips == 1


def test_a_participating_graph_read_publishes_the_slot_the_unit_of_work_filed() -> None:
    port = RecordingPort(rows=[ACCOUNT_ROW])

    def fn(tx: Transaction) -> object:
        graph = tx.read_neutral(_graph_request()).output
        assert isinstance(graph, NeutralGraph)
        key = graph.roots[0].node.observation_key
        assert key is not None
        # The slot the read filed under is the one the unit of work answers for,
        # which is what makes the key a REFERENCE rather than a reconstruction.
        return key

    assert cast("ObservationKey", _run(port, fn)) == _account_slot()


def test_a_participating_read_force_flushes_pending_neutral_writes_first() -> None:
    port = RecordingPort(rows=[ACCOUNT_ROW])

    def fn(tx: Transaction) -> None:
        tx.write_neutral(_update(11), observation=VersionObservation(observed_version=1))
        tx.read_neutral(_rows_request())

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


def test_an_explicit_observation_licenses_the_version_advance() -> None:
    port = RecordingPort()
    _run(
        port,
        lambda tx: tx.write_neutral(
            _update(11), observation=VersionObservation(observed_version=1)
        ),
    )
    assert port.ops[1][1:] == (UPDATE_SQL, (11, 2, 3))


def test_an_observation_key_resolves_against_this_units_own_record() -> None:
    port = RecordingPort(rows=[ACCOUNT_ROW])

    def fn(tx: Transaction) -> None:
        graph = tx.read_neutral(_graph_request()).output
        assert isinstance(graph, NeutralGraph)
        key = graph.roots[0].node.observation_key
        assert key is not None
        tx.write_neutral(_update(11), observation=key)

    _run(port, fn)
    assert [op[0] for op in port.ops] == ["begin", "read", "write", "commit"]
    assert port.ops[2][1:] == (UPDATE_SQL, (11, 2, 3))


# --------------------------------------------------------------------------- #
# Refusals.                                                                    #
# --------------------------------------------------------------------------- #


def test_a_key_naming_no_recorded_observation_fails_at_the_call() -> None:
    port = RecordingPort()
    with pytest.raises(UnobservedWriteError) as raised:

        def fn(tx: Transaction) -> None:
            tx.write_neutral(_update(11), observation=_account_slot())

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
        escaped[0].write_neutral(_update(11), observation=_account_slot())


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


def test_the_neutral_read_is_refused_for_an_undeclared_target() -> None:
    request = NeutralReadRequest.rows(_account_query("parallax.compatibility.NoSuchEntity"))
    with pytest.raises(QueryTargetError):
        account_db(RecordingPort()).read_neutral(request)


def test_a_refused_participating_read_flushes_nothing() -> None:
    # The gate runs BEFORE `uow.read`, whose force-flush would otherwise execute
    # the pending buffer on the way to a read that was going to be refused —
    # turning a refusal into a write. `tx.find` is held to the same ordering.
    port = RecordingPort()
    request = NeutralReadRequest.rows(_account_query("parallax.compatibility.NoSuchEntity"))

    def fn(tx: Transaction) -> None:
        tx.write_neutral(_update(11), observation=VersionObservation(observed_version=1))
        tx.read_neutral(request)

    with pytest.raises(QueryTargetError):
        _run(port, fn)
    assert [op[0] for op in port.ops] == ["begin", "rollback"]


def test_the_neutral_read_reports_a_deferred_feature_by_name() -> None:
    request = NeutralReadRequest.graph(
        deserialize_query(
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
    )
    with pytest.raises(DeferredFeatureError) as raised:
        _policy_db(RecordingPort()).read_neutral(request)
    assert raised.value.features == ("snapshot-history-includes",)


def test_a_deferred_participating_read_flushes_nothing() -> None:
    # The classification runs BEFORE `uow.read`, whose force-flush would
    # otherwise execute the pending buffer on the way to a read that was going
    # to be refused — turning a deferral into a write.
    port = RecordingPort()
    request = NeutralReadRequest.graph(
        deserialize_query(
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
    )

    def fn(tx: Transaction) -> None:
        tx.write_neutral(_policy_insert())
        tx.read_neutral(request)

    with pytest.raises(DeferredFeatureError) as raised:
        _policy_db(port).transact(fn)
    assert raised.value.features == ("snapshot-history-includes",)
    assert [op[0] for op in port.ops] == ["begin", "rollback"]


def test_a_row_form_request_refuses_the_relationship_levels_it_cannot_materialize() -> None:
    request = NeutralReadRequest.rows(
        deserialize_query(
            {
                "target": "parallax.compatibility.Policy",
                "predicate": {"all": {}},
                "temporal": _latest("transaction-time", "valid-time"),
                "includes": [{"segments": [{"rel": "parallax.compatibility.Policy.coverages"}]}],
            }
        )
    )
    with pytest.raises(ValueError, match="row-form read materializes no relationships"):
        _policy_db(RecordingPort(rows=[])).read_neutral(request)


def test_a_refused_row_form_participating_read_flushes_nothing() -> None:
    # The form refusal is the read gate's, not the values lane's, so it lands on
    # the same side of `uow.read`'s force-flush as the other three: a pending
    # buffered write is still pending when the refusal escapes, and the
    # transaction rolls back having executed no DML.
    port = RecordingPort(rows=[_ORDER_ROW])
    request = NeutralReadRequest.rows(
        deserialize_query(
            {
                "target": "parallax.compatibility.Order",
                "predicate": {"all": {}},
                "includes": [{"segments": [{"rel": "parallax.compatibility.Order.items"}]}],
            }
        )
    )

    def fn(tx: Transaction) -> None:
        tx.write_neutral(_order_update())
        tx.read_neutral(request)

    with pytest.raises(ValueError, match="row-form read materializes no relationships"):
        _run_on(db_for(MODELS["orders"], port), fn)
    assert [op[0] for op in port.ops] == ["begin", "rollback"]


def test_an_ordered_capped_query_carrying_no_includes_still_answers() -> None:
    # The refusal is about a relationship level, not about how many clauses a
    # query fills: ordering and a cap add none.
    port = RecordingPort(rows=[_ORDER_ROW])
    request = NeutralReadRequest.rows(
        deserialize_query(
            {
                "target": "parallax.compatibility.Order",
                "predicate": {"all": {}},
                "orderBy": [{"attr": "parallax.compatibility.Order.id"}],
                "limit": 1,
            }
        )
    )
    result = db_for(MODELS["orders"], port).read_neutral(request)
    assert isinstance(result.output, NeutralRows)


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


def test_a_milestone_set_read_answers_one_pinned_graph_per_milestone() -> None:
    port = RecordingPort(rows=_balance_history_rows())
    request = NeutralReadRequest.graph(
        object_query_node(mm.Balance.where(mm.Balance.id == 1).history(TX_TIME))
    )

    def fn(tx: Transaction) -> object:
        return tx.read_neutral(request).output

    graphs = _run_on(db_for(BALANCE, port), fn)
    assert isinstance(graphs, NeutralGraphs)
    assert len(graphs) == 2
    pins = [graph.pin for graph in graphs]
    assert pins[0] != pins[1], "each milestone carries its own edge pin"
    # A milestone-set read records no observation on the unit of work, exactly as
    # `tx.find`'s own history branch does, so it publishes no slot to settle
    # against: a key here would name nothing and fail the write it was handed to.
    assert all(graph.roots[0].node.observation_key is None for graph in graphs)


def test_a_temporal_node_publishes_the_slot_its_own_milestone_qualifies() -> None:
    port = RecordingPort(rows=[_balance_history_rows()[1]])
    request = NeutralReadRequest.graph(object_query_node(mm.Balance.where(mm.Balance.id == 1)))

    def fn(tx: Transaction) -> object:
        graph = tx.read_neutral(request).output
        assert isinstance(graph, NeutralGraph)
        key = graph.roots[0].node.observation_key
        assert key is not None
        # A milestone chain holds several rows per primary key, so the slot the
        # recording side files under is qualified by the milestone the row names,
        # and this key — derived off member identities rather than columns —
        # names that same qualified slot.
        assert key.milestone is not None
        return key

    key = cast("ObservationKey", _run_on(db_for(BALANCE, port), fn))
    assert key.object_key.primary_key == (("id", 1),)


def test_an_unversioned_non_temporal_node_carries_no_observation_slot() -> None:
    port = RecordingPort(rows=[_ORDER_ROW])
    request = NeutralReadRequest.graph(object_query_node(Order.where(Order.id == 1)))

    def fn(tx: Transaction) -> object:
        return tx.read_neutral(request).output

    graph = _run_on(db_for(MODELS["orders"], port), fn)
    assert isinstance(graph, NeutralGraph)
    assert graph.roots[0].node.observation_key is None


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
