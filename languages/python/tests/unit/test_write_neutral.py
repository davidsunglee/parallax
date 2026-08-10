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
from parallax.core.entity._query import lower_find_query
from parallax.core.metamodel import EntityIdentity, entity_by_name
from parallax.core.op_algebra import Operation, deserialize
from parallax.core.unit_work import (
    EscapedTransactionError,
    ObjectKey,
    ObservationKey,
    VersionObservation,
    WriteInstruction,
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
    return NeutralReadRequest.rows(target=_account(), operation=_by_id())


def _graph_request() -> NeutralReadRequest:
    return NeutralReadRequest.graph(target=_account(), operation=_by_id())


def _by_id() -> Operation:
    return deserialize({"eq": {"attr": "parallax.compatibility.Account.id", "value": 3}})


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
    request = NeutralReadRequest.rows(
        target=EntityIdentity("parallax.compatibility", "NoSuchEntity"), operation=_by_id()
    )
    with pytest.raises(QueryTargetError):
        account_db(RecordingPort()).read_neutral(request)


def test_a_refused_participating_read_flushes_nothing() -> None:
    # The gate runs BEFORE `uow.read`, whose force-flush would otherwise execute
    # the pending buffer on the way to a read that was going to be refused —
    # turning a refusal into a write. `tx.find` is held to the same ordering.
    port = RecordingPort()
    request = NeutralReadRequest.rows(
        target=EntityIdentity("parallax.compatibility", "NoSuchEntity"), operation=_by_id()
    )

    def fn(tx: Transaction) -> None:
        tx.write_neutral(_update(11), observation=VersionObservation(observed_version=1))
        tx.read_neutral(request)

    with pytest.raises(QueryTargetError):
        _run(port, fn)
    assert [op[0] for op in port.ops] == ["begin", "rollback"]


def test_the_neutral_read_reports_a_deferred_feature_by_name() -> None:
    request = NeutralReadRequest.graph(
        target=_policy(),
        operation=deserialize(
            {
                "deepFetch": {
                    "operand": {
                        "history": {"operand": {"all": {}}, "dimension": "transaction-time"}
                    },
                    "paths": [{"segments": [{"rel": "parallax.compatibility.Policy.coverages"}]}],
                }
            }
        ),
    )
    with pytest.raises(DeferredFeatureError) as raised:
        _policy_db(RecordingPort()).read_neutral(request)
    assert raised.value.features == ("snapshot-history-includes",)


def test_a_row_form_request_refuses_the_relationship_levels_it_cannot_materialize() -> None:
    request = NeutralReadRequest.rows(
        target=_policy(),
        operation=deserialize(
            {
                "deepFetch": {
                    "operand": {"all": {}},
                    "paths": [{"segments": [{"rel": "parallax.compatibility.Policy.coverages"}]}],
                }
            }
        ),
    )
    with pytest.raises(ValueError, match="row-form read materializes no relationships"):
        _policy_db(RecordingPort(rows=[])).read_neutral(request)


def _policy() -> EntityIdentity:
    entity = entity_by_name(model_of(MODELS["policy"]), "parallax.compatibility.Policy")
    assert entity is not None
    return entity.identity


def _policy_db(port: RecordingPort) -> Database:
    return db_for(MODELS["policy"], port)


def test_a_milestone_set_read_answers_one_pinned_graph_per_milestone() -> None:
    port = RecordingPort(rows=_balance_history_rows())
    lowered = lower_find_query(mm.Balance.where(mm.Balance.id == 1).history(TX_TIME))
    request = NeutralReadRequest.graph(target=lowered.target, operation=lowered.operation)

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
    lowered = lower_find_query(mm.Balance.where(mm.Balance.id == 1))
    request = NeutralReadRequest.graph(target=lowered.target, operation=lowered.operation)

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
    lowered = lower_find_query(Order.where(Order.id == 1))
    request = NeutralReadRequest.graph(target=lowered.target, operation=lowered.operation)

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
