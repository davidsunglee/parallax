"""Production find-executor tests for ``find`` and ``find_history``.

Exercises the ONE per-level loop against a fake, canned-response `m-db-port`
(no Docker): round-trip accounting (one statement per non-empty level), the
empty-level short-circuit (no child statement issued, gathered from `then`'s
own contract in `m-deep-fetch`), a back-reference level's zero-statement
resolution, `familyVariant` materialization flowing through the executor
(`m-sql` applied to child-level rows), and the milestone-set `find_history`
edge-grouping/ordering.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Any, cast

import pytest
from _transact_support import ACCOUNT, PERSON, NoIoPort

from _support import mirrored_models as mm
from parallax.conformance import models, read_models
from parallax.conformance import vo_models as vo
from parallax.conformance.graph_models import POLICY_MODEL, Policy
from parallax.core import LATEST, TX_TIME
from parallax.core.base import INFINITY
from parallax.core.db_port import DbPort, Row
from parallax.core.dialect import POSTGRES
from parallax.core.entity import FindQuery, GraphConstructionError
from parallax.core.entity._query import LoweredFindQuery, lower_find_query
from parallax.core.execution_log import DatabaseCall, ReadCompleted, ReadTrace
from parallax.core.metamodel import AttributeIdentity, EntityIdentity
from parallax.core.op_algebra import deserialize
from parallax.core.sql_gen import LoweredStatement
from parallax.core.temporal_read import Pin, TemporalReadError
from parallax.snapshot import (
    DeferredFeatureError,
    QueryTargetError,
    SnapshotMaterializationError,
    handle,
)
from parallax.snapshot.handle import _preflight
from parallax.snapshot.materialize import (
    SnapshotDecodingError,
    SnapshotGraphInput,
    SnapshotNodeInput,
    SnapshotNodeRef,
    attribute_value,
)

_MODELS = models.load_models()
ORDERS = _MODELS["orders"]
ANIMAL = _MODELS["animal"]
INVOICE = _MODELS["invoice"]
RATE = _MODELS["rate"]
DOCUMENT = _MODELS["document"]

_UTC = dt.UTC


def _root(result: handle.FindResult) -> SnapshotNodeInput:
    graph = result.graph
    return graph.nodes[graph.roots[0].node_index]


def _value(graph: SnapshotGraphInput, ref: SnapshotNodeRef, entity: str, member: str) -> object:
    """One converted projection's value for a member, named structurally."""
    node = graph.nodes[ref.node_index]
    return attribute_value(
        node, AttributeIdentity(EntityIdentity("parallax.compatibility", entity), member)
    )


def _view(graph: SnapshotGraphInput, node: SnapshotNodeInput, attach_key: str) -> object:
    """The value a node's view carries, found by the attach key a plan derived."""
    del graph
    return next(
        entry.value
        for entry in node.relationship_views
        if (entry.view.narrowed_view or entry.view.relationship.name) == attach_key
    )


def _refs(value: object) -> tuple[SnapshotNodeRef, ...]:
    return cast("tuple[SnapshotNodeRef, ...]", value)


class QueuePort:
    """A fake `m-db-port` returning one canned response per `execute()` call,
    in call order — enough to drive the executor's own per-level loop without
    a real database."""

    def __init__(self, responses: Sequence[list[Row]]) -> None:
        self._responses = list(responses)
        self.executed: list[tuple[str, list[object]]] = []

    def execute(self, sql: str, binds: Sequence[object]) -> list[Row]:
        self.executed.append((sql, list(binds)))
        return self._responses.pop(0)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise NotImplementedError

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:  # pragma: no cover
        raise NotImplementedError


def test_find_issues_one_statement_per_non_empty_level() -> None:
    port = QueuePort(
        [
            [
                {
                    "id": 1,
                    "name": "Ada",
                    "sku": "A",
                    "qty": 1,
                    "price": Decimal("1"),
                    "active": True,
                    "ordered_on": dt.date(2024, 1, 1),
                }
            ],
            [{"id": 11, "order_id": 1, "sku": "x", "quantity": 1, "shipped_on": None}],
        ]
    )
    op = deserialize(
        {
            "deepFetch": {
                "operand": {"eq": {"attr": "Order.id", "value": 1}},
                "paths": [{"segments": [{"rel": "Order.items"}]}],
            }
        }
    )
    result = handle.find(op, ORDERS, POSTGRES, "Order", port)
    assert result.execution.round_trips == 2
    items = _refs(_view(result.graph, _root(result), "items"))
    assert [_value(result.graph, ref, "OrderItem", "id") for ref in items] == [11]


def test_find_empty_root_short_circuits_with_no_child_statement() -> None:
    port = QueuePort([[]])
    op = deserialize(
        {
            "deepFetch": {
                "operand": {"eq": {"attr": "Order.id", "value": 999}},
                "paths": [{"segments": [{"rel": "Order.items"}, {"rel": "OrderItem.statuses"}]}],
            }
        }
    )
    result = handle.find(op, ORDERS, POSTGRES, "Order", port)
    assert result.execution.round_trips == 1
    assert result.graph.roots == ()
    assert len(port.executed) == 1


def test_find_empty_intermediate_level_suppresses_only_the_grandchild_statement() -> None:
    port = QueuePort(
        [
            [
                {
                    "id": 4,
                    "name": "Margaret",
                    "sku": None,
                    "qty": 20,
                    "price": Decimal("1"),
                    "active": True,
                    "ordered_on": dt.date(2024, 4, 20),
                }
            ],
            [],  # the items level executes and returns zero rows
        ]
    )
    op = deserialize(
        {
            "deepFetch": {
                "operand": {"eq": {"attr": "Order.id", "value": 4}},
                "paths": [{"segments": [{"rel": "Order.items"}, {"rel": "OrderItem.statuses"}]}],
            }
        }
    )
    result = handle.find(op, ORDERS, POSTGRES, "Order", port)
    assert result.execution.round_trips == 2
    assert _view(result.graph, _root(result), "items") == ()


def test_find_back_reference_level_issues_no_additional_statement() -> None:
    port = QueuePort(
        [
            [
                {
                    "id": 1,
                    "name": "Ada",
                    "sku": "A",
                    "qty": 1,
                    "price": Decimal("1"),
                    "active": True,
                    "ordered_on": dt.date(2024, 1, 1),
                }
            ],
            [{"id": 11, "order_id": 1, "sku": "x", "quantity": 1, "shipped_on": None}],
        ]
    )
    op = deserialize(
        {
            "deepFetch": {
                "operand": {"eq": {"attr": "Order.id", "value": 1}},
                "paths": [{"segments": [{"rel": "Order.items"}, {"rel": "OrderItem.order"}]}],
            }
        }
    )
    result = handle.find(op, ORDERS, POSTGRES, "Order", port)
    assert result.execution.round_trips == 2  # the back-reference costs nothing
    (item,) = _refs(_view(result.graph, _root(result), "items"))
    back = _view(result.graph, result.graph.nodes[item.node_index], "order")
    assert back == result.graph.roots[0]


@pytest.mark.parametrize(
    ("relationship", "term"),
    [
        ("itemsByShipDate", "t0.shipped_on asc"),
        ("notesDescNullsLast", "t0.resolved_on desc nulls last"),
        ("notesAscNullsFirst", "t0.resolved_on asc nulls first"),
        ("notesDescNullsFirst", "t0.resolved_on desc"),
    ],
)
def test_find_carries_a_declared_null_placement_into_child_level_sql(
    relationship: str, term: str
) -> None:
    # A placement authored on a relationship declaration has to survive the whole
    # executor path — descriptor ingestion, the accepted model, the deep-fetch
    # order-key rewrite, and the m-dialect seam — before it reaches the child
    # level's own ORDER BY. Each pairing renders differently on Postgres because
    # the dialect compensates only where its native placement is wrong: an
    # unauthored placement and `desc`/`first` already hold, so both render plain.
    root: list[Row] = [
        {
            "id": 1,
            "name": "Ada",
            "sku": "A",
            "qty": 1,
            "price": Decimal("1"),
            "active": True,
            "ordered_on": dt.date(2024, 1, 1),
        }
    ]
    port = QueuePort([root, []])
    op = deserialize(
        {
            "deepFetch": {
                "operand": {"eq": {"attr": "Order.id", "value": 1}},
                "paths": [{"segments": [{"rel": f"Order.{relationship}"}]}],
            }
        }
    )
    handle.find(op, ORDERS, POSTGRES, "Order", port)
    child_sql, _binds = port.executed[1]
    assert child_sql.endswith(f" order by {term}")


def test_find_materializes_family_variant_on_child_level_rows() -> None:
    port = QueuePort(
        [
            [{"id": 10, "name": "Alice"}],
            [
                {
                    "id": 1,
                    "name": "Rex",
                    "owner_id": 10,
                    "license_id": "L-100",
                    "indoor": None,
                    "bark_volume": 7,
                    "tusk_length": None,
                    "kind": "dog",
                }
            ],
        ]
    )
    op = deserialize(
        {
            "deepFetch": {
                "operand": {"eq": {"attr": "Person.id", "value": 10}},
                "paths": [{"segments": [{"rel": "Person.animals"}]}],
            }
        }
    )
    result = handle.find(op, ANIMAL, POSTGRES, "Person", port)
    (animal,) = _refs(_view(result.graph, _root(result), "animals"))
    node = result.graph.nodes[animal.node_index]
    assert node.concrete_entity == EntityIdentity("parallax.compatibility", "Dog")
    # The synthetic tag is nobody's member, so no converted entry carries it.
    assert all(entry.identity.name != "kind" for entry in node.attributes)


def test_find_threads_a_root_narrow_to_a_single_tpcs_concrete() -> None:
    # A table-per-concrete-subtype abstract root narrowed to exactly one
    # concrete compiles to an ordinary
    # single-table read (`m-sql`'s `_compile_tpcs_single`) — the row carries no
    # `familyVariant` at all. `CompiledRead.narrow_to` is what lets the converted
    # row still name the row's own concrete identity, rather than the abstract
    # queried `targetEntity`.
    port = QueuePort(
        [
            [
                {
                    "id": 1,
                    "title": "Invoice-A",
                    "folder_id": None,
                    "currency": "USD",
                    "amount_due": Decimal("120.00"),
                }
            ]
        ]
    )
    op = deserialize({"narrow": {"to": ["Invoice"], "operand": {"all": {}}}})
    result = handle.find(op, DOCUMENT, POSTGRES, "Document", port)
    assert _root(result).concrete_entity == EntityIdentity("parallax.compatibility", "Invoice")


def test_find_history_groups_rows_into_chronologically_ordered_edge_pinned_graphs() -> None:
    port = QueuePort(
        [
            [
                {
                    "id": 1000,
                    "invoice_id": 100,
                    "amount": Decimal("75.00"),
                    "in_z": dt.datetime(2024, 4, 1, tzinfo=_UTC),
                    "out_z": INFINITY,
                },
                {
                    "id": 1000,
                    "invoice_id": 100,
                    "amount": Decimal("50.00"),
                    "in_z": dt.datetime(2024, 1, 1, tzinfo=_UTC),
                    "out_z": dt.datetime(2024, 4, 1, tzinfo=_UTC),
                },
            ]
        ]
    )
    op = deserialize(
        {
            "history": {
                "operand": {"eq": {"attr": "InvoiceLine.id", "value": 1000}},
                "dimension": "transaction-time",
            }
        }
    )
    result = handle.find_history(op, INVOICE, POSTGRES, "InvoiceLine", port)
    assert result.execution.round_trips == 1
    assert [g.pin.tx_time for g in result.graphs] == [
        dt.datetime(2024, 1, 1, tzinfo=_UTC),
        dt.datetime(2024, 4, 1, tzinfo=_UTC),
    ]
    assert [_value(g, g.roots[0], "InvoiceLine", "amount") for g in result.graphs] == [
        Decimal("50.00"),
        Decimal("75.00"),
    ]


def test_find_history_groups_two_distinct_rows_sharing_one_edge_into_one_graph() -> None:
    # Two DIFFERENT physical InvoiceLine rows (ids 1000 and 2000) sharing the
    # exact same Transaction-Time edge (in_z) belong to the SAME milestone graph —
    # the "edge already seen" branch of the grouping loop (as opposed to the
    # "first row at this edge" branch the single-row-per-edge test above pins).
    port = QueuePort(
        [
            [
                {
                    "id": 1000,
                    "invoice_id": 100,
                    "amount": Decimal("50.00"),
                    "in_z": dt.datetime(2024, 1, 1, tzinfo=_UTC),
                    "out_z": dt.datetime(2024, 4, 1, tzinfo=_UTC),
                },
                {
                    "id": 2000,
                    "invoice_id": 100,
                    "amount": Decimal("25.00"),
                    "in_z": dt.datetime(2024, 1, 1, tzinfo=_UTC),
                    "out_z": dt.datetime(2024, 4, 1, tzinfo=_UTC),
                },
            ]
        ]
    )
    op = deserialize(
        {
            "history": {
                "operand": {"eq": {"attr": "InvoiceLine.invoiceId", "value": 100}},
                "dimension": "transaction-time",
            }
        }
    )
    result = handle.find_history(op, INVOICE, POSTGRES, "InvoiceLine", port)
    assert len(result.graphs) == 1
    graph = result.graphs[0]
    assert [_value(graph, ref, "InvoiceLine", "id") for ref in graph.roots] == [1000, 2000]


def test_find_history_over_a_concrete_inheritance_target_resolves_the_roots_axes() -> None:
    # `DepositRate` declares NO `as_of_axes` of its own (`Rate`, the
    # family root, does). `milestone_edge`, `_edge_pin`, and `_edge_sort_key`
    # must resolve through the root rather than consulting the concrete
    # entity's empty local axis collection.
    port = QueuePort(
        [
            [
                {
                    "id": 1,
                    "amount": Decimal("2.25"),
                    "grade": "B",
                    "from_z": dt.datetime(2024, 1, 1, tzinfo=_UTC),
                    "thru_z": INFINITY,
                    "in_z": dt.datetime(2024, 1, 1, tzinfo=_UTC),
                    "out_z": dt.datetime(2024, 2, 1, tzinfo=_UTC),
                },
                {
                    "id": 1,
                    "amount": Decimal("2.50"),
                    "grade": "A",
                    "from_z": dt.datetime(2024, 1, 1, tzinfo=_UTC),
                    "thru_z": INFINITY,
                    "in_z": dt.datetime(2024, 2, 1, tzinfo=_UTC),
                    "out_z": INFINITY,
                },
            ]
        ]
    )
    op = deserialize(
        {
            "history": {
                "operand": {"eq": {"attr": "DepositRate.id", "value": 1}},
                "dimension": "transaction-time",
            }
        }
    )
    result = handle.find_history(op, RATE, POSTGRES, "DepositRate", port)
    assert [g.pin.tx_time for g in result.graphs] == [
        dt.datetime(2024, 1, 1, tzinfo=_UTC),
        dt.datetime(2024, 2, 1, tzinfo=_UTC),
    ]
    assert [_value(g, g.roots[0], "Rate", "amount") for g in result.graphs] == [
        Decimal("2.25"),
        Decimal("2.50"),
    ]
    # The Valid-Time dimension rides along too (bitemporal): both milestones share it.
    assert all(g.pin.valid_time == dt.datetime(2024, 1, 1, tzinfo=_UTC) for g in result.graphs)


def test_find_history_refuses_a_plan_carrying_deep_fetch_levels() -> None:
    policy = _MODELS["policy"]
    port = QueuePort([[]])
    op = deserialize(
        {
            "deepFetch": {
                "operand": {"history": {"operand": {"all": {}}, "dimension": "transaction-time"}},
                "paths": [{"segments": [{"rel": "Policy.coverages"}]}],
            }
        }
    )
    with pytest.raises(ValueError, match="no deep-fetch levels"):
        handle.find_history(op, policy, POSTGRES, "Policy", port)


# --------------------------------------------------------------------------- #
# The shared read-preflight seam (`_preflight.preflight_find`)                 #
# --------------------------------------------------------------------------- #
def test_db_find_refuses_a_target_the_connected_model_does_not_declare() -> None:
    # `Person` is a perfectly declared Entity — of another model. What makes the
    # query unanswerable is the CONNECTED model, which is why the refusal is a
    # RuntimeError and why it names neither the query nor the model. Preflight
    # resolves the target before anything else, so the port is never touched:
    # `NoIoPort` raises on any read or write.
    db = handle.Database.connect(NoIoPort(), ACCOUNT)
    with pytest.raises(QueryTargetError) as caught:
        db.find(mm.Person.where(mm.Person.id == 1))
    assert caught.value.code == "query-target-not-in-model"


def test_db_find_refuses_a_deferred_execution_feature_by_name() -> None:
    # `.history()` with `.include(...)` is a VALID query the implementation has
    # not built yet, so the refusal names the Feature rather than calling the
    # query wrong. `NoIoPort` raises on any read or write: classification runs
    # before SQL generation, connection acquisition, and adapter access alike.
    db = handle.Database.connect(NoIoPort(), POLICY_MODEL)
    query = Policy.where(Policy.all).history(TX_TIME).include(Policy.coverages)
    with pytest.raises(DeferredFeatureError) as caught:
        db.find(query)
    assert caught.value.code == "execution-feature-deferred"
    assert caught.value.features == ("snapshot-history-includes",)


def test_a_pinned_axis_with_includes_is_not_deferred() -> None:
    # The deferral is the milestone SET combined with includes, never a temporal
    # read combined with includes: an `as_of` pin answers one graph, which the
    # deep-fetch executor has always served. The root level comes back empty, so
    # the child level short-circuits and one statement is the whole execution.
    port = QueuePort([[]])
    db = handle.Database.connect(port, POLICY_MODEL)
    query = Policy.where(Policy.all).as_of(tx_time=LATEST).include(Policy.coverages)
    assert db.find(query).results() == []
    assert len(port.executed) == 1


def test_result_shaping_wrappers_do_not_hide_a_deferred_feature() -> None:
    # Ordering and a limit lower BETWEEN the deep fetch and the temporal
    # wrapper, so recognizing the combination means peeling them: a deferral is
    # a property of the read, never of how its rows are shaped afterwards.
    db = handle.Database.connect(NoIoPort(), POLICY_MODEL)
    query = (
        Policy.where(Policy.all)
        .history(TX_TIME)
        .order_by(Policy.id.asc())
        .limit(5)
        .include(Policy.coverages)
    )
    with pytest.raises(DeferredFeatureError) as caught:
        db.find(query)
    assert caught.value.features == ("snapshot-history-includes",)


def test_an_undeclared_target_outranks_a_deferred_feature() -> None:
    # One query, both faults. Target resolution is step 1 and classification is
    # step 3, so the connected model's inability to answer at all is what
    # surfaces — a deferral result is never exposed for a query the model does
    # not even declare a target for.
    db = handle.Database.connect(NoIoPort(), ACCOUNT)
    query = Policy.where(Policy.all).history(TX_TIME).include(Policy.coverages)
    with pytest.raises(QueryTargetError) as caught:
        db.find(query)
    assert caught.value.code == "query-target-not-in-model"


def test_a_refusal_reports_every_matching_feature_in_ascending_order() -> None:
    # The installed inventory holds ONE member, and a second is a coordinated
    # contract change rather than a test fixture, so the multi-match promise is
    # pinned on the value that carries it: `features` is every match, ascending,
    # whatever order the matching set iterated in.
    error = DeferredFeatureError(frozenset({"snapshot-history-includes", "a-staged-feature"}))
    assert error.features == ("a-staged-feature", "snapshot-history-includes")
    assert "a-staged-feature, snapshot-history-includes" in str(error)


def test_a_refusal_naming_no_feature_cannot_be_constructed() -> None:
    # `features` is nonempty by construction, not merely by the seam's own
    # guard: the class is exported, so a caller reaches the constructor
    # directly, and an empty match set is the answer for a query this
    # implementation EXECUTES — a refusal built from one would name no reason.
    with pytest.raises(ValueError, match="at least one Feature"):
        DeferredFeatureError(frozenset())


def test_two_executions_of_one_query_lower_it_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    # Lowering is memoized nowhere: a Find Query caches no lowering and the seam
    # holds no global memo, so each execution builds its own value and keeps it
    # locally. The two are equal — lowering is deterministic — and distinct, so
    # no execution is ever handed a lowering another one still holds.
    lowerings: list[LoweredFindQuery] = []
    original = lower_find_query

    def recording(query: FindQuery[Any, Any]) -> LoweredFindQuery:
        lowered = original(query)
        lowerings.append(lowered)
        return lowered

    monkeypatch.setattr(_preflight, "lower_find_query", recording)
    query = mm.Person.where(mm.Person.id == 1)
    db = handle.Database.connect(QueuePort([[], []]), PERSON)
    db.find(query)
    db.find(query)
    first, second = lowerings
    assert first is not second
    assert first == second


# --------------------------------------------------------------------------- #
# The materialization boundary translates a graph-construction or lifecycle    #
# failure exactly once, and publishes nothing.                                 #
# --------------------------------------------------------------------------- #
def test_a_graph_construction_failure_is_translated_once_at_the_read_boundary() -> None:
    # The read itself succeeded — one statement, one row — and the failure is in
    # building the graph that row describes: `balance` is a Decimal member and
    # the row carries a string, which nothing between the driver and the frozen
    # instance would otherwise reject.
    port = QueuePort([[{"id": 1, "owner": "Ada", "balance": "not-a-decimal", "version": 1}]])
    db = handle.Database.connect(port, ACCOUNT)
    with pytest.raises(SnapshotMaterializationError) as refusal:
        db.find(mm.Account.where(mm.Account.id == 1))
    assert refusal.value.code == "snapshot-materialization-failed"
    cause = refusal.value.cause
    assert isinstance(cause, GraphConstructionError)
    assert cause.code == "entity-graph-invalid-value"
    # The original defect stays diagnosable rather than being replaced.
    assert refusal.value.__cause__ is cause
    assert len(port.executed) == 1


def test_a_query_failure_keeps_its_own_classification_at_that_boundary() -> None:
    # The counterpart the single translation exists to keep separate: a refusal
    # raised before any graph was being built is never re-classified as a
    # materialization failure.
    db = handle.Database.connect(NoIoPort(), ACCOUNT)
    with pytest.raises(QueryTargetError):
        db.find(Policy.where(Policy.all))


def test_a_conversion_failure_keeps_its_own_classification_and_publishes_nothing() -> None:
    # Stored data that contradicts its declared shape is refused BEFORE any graph
    # is being built, so it surfaces as its own decoding refusal rather than as a
    # materialization failure — and no Snapshot is published either way.
    port = QueuePort([[{"id": 1, "name": "Ada", "address": {"city": 7}}]])
    db = handle.Database.connect(port, vo.CUSTOMER_MODEL)
    with pytest.raises(SnapshotDecodingError) as refusal:
        db.find(vo.Customer.where(vo.Customer.id == 1))
    assert refusal.value.code == "snapshot-decoding-failed"
    assert not isinstance(refusal.value, SnapshotMaterializationError)


def test_a_per_node_state_failure_is_translated_once_and_publishes_nothing() -> None:
    # The read and the conversion both succeed; what fails is deriving the node's
    # own milestone edge, because the row carries no Transaction-Time start at
    # all. State attachment and root publication are atomic, so the whole result
    # is refused rather than partly published.
    port = QueuePort([[{"bal_id": 1, "acct_num": "A-1", "val": Decimal("5.00")}]])
    db = handle.Database.connect(port, read_models.BALANCE_MODEL)
    with pytest.raises(SnapshotMaterializationError) as refusal:
        db.find(read_models.Balance.where(read_models.Balance.id == 1))
    assert refusal.value.code == "snapshot-materialization-failed"
    assert isinstance(refusal.value.cause, TemporalReadError)


# --------------------------------------------------------------------------- #
# Snapshot[T]'s own arity accessors, over roots this executor's result surface  #
# publishes.                                                                   #
# --------------------------------------------------------------------------- #
_ONE_CALL = ReadTrace(
    (DatabaseCall(LoweredStatement("select 1", ()), "read", 1, ReadCompleted(1)),)
)


def _snapshot(roots: tuple[object, ...]) -> handle.Snapshot[object]:
    return handle.Snapshot(roots, Pin(), _ONE_CALL)


def test_result_raises_on_zero_and_on_more_than_one() -> None:
    with pytest.raises(handle.NoResultFound):
        _snapshot(()).result()
    with pytest.raises(handle.TooManyResultsFound):
        _snapshot((1, 2)).result()
    assert _snapshot((1,)).result() == 1


def test_result_or_none_returns_none_on_zero_and_raises_on_more_than_one() -> None:
    assert _snapshot(()).result_or_none() is None
    assert _snapshot((1,)).result_or_none() == 1
    with pytest.raises(handle.TooManyResultsFound):
        _snapshot((1, 2)).result_or_none()


def test_results_returns_a_fresh_list_per_call() -> None:
    snapshot = _snapshot((1, 2))
    first = snapshot.results()
    assert first == [1, 2]
    assert first is not snapshot.results()


def test_snapshot_has_no_iteration_len_or_indexing() -> None:
    snapshot = _snapshot((1, 2))
    assert not hasattr(snapshot, "__iter__")
    assert not hasattr(snapshot, "__len__")
    assert not hasattr(snapshot, "__getitem__")


def test_snapshot_pin_and_execution_and_repr() -> None:
    pin = Pin(tx_time=dt.datetime(2024, 1, 1, tzinfo=_UTC))
    snapshot = handle.Snapshot((1,), pin, _ONE_CALL)
    assert snapshot.pin is pin
    assert snapshot.execution.round_trips == 1
    assert "Snapshot(roots=1" in repr(snapshot)


def test_a_level_whose_gathered_key_set_is_empty_attaches_the_null_result() -> None:
    # m-deep-fetch: an empty gathered parent-key set issues NO child query at all,
    # and every admitted parent still gets a LOADED view rather than an unset one.
    # The root's own `ownerId` is null, so there is no key to gather at all.
    port = QueuePort(
        [
            [
                {
                    "id": 1,
                    "name": "Rex",
                    "owner_id": None,
                    "license_id": None,
                    "indoor": None,
                    "bark_volume": 7,
                    "tusk_length": None,
                    "kind": "dog",
                }
            ]
        ]
    )
    op = deserialize(
        {
            "deepFetch": {
                "operand": {"eq": {"attr": "Animal.id", "value": 1}},
                "paths": [{"segments": [{"rel": "Animal.owner"}]}],
            }
        }
    )
    result = handle.find(op, ANIMAL, POSTGRES, "Animal", port)
    assert result.execution.round_trips == 1
    assert _view(result.graph, _root(result), "owner") is None


def test_a_back_reference_over_a_null_correlation_key_attaches_none() -> None:
    # A null correlation key needs no identity lookup at all — no ancestor row
    # exists to resolve — so the view is attached as loaded-null directly.
    port = QueuePort(
        [
            [
                {
                    "id": 1,
                    "name": "Ada",
                    "sku": "A",
                    "qty": 1,
                    "price": Decimal("1"),
                    "active": True,
                    "ordered_on": dt.date(2024, 1, 1),
                }
            ],
            [{"id": 11, "order_id": None, "sku": "x", "quantity": 1, "shipped_on": None}],
        ]
    )
    op = deserialize(
        {
            "deepFetch": {
                "operand": {"eq": {"attr": "Order.id", "value": 1}},
                "paths": [{"segments": [{"rel": "Order.items"}, {"rel": "OrderItem.order"}]}],
            }
        }
    )
    result = handle.find(op, ORDERS, POSTGRES, "Order", port)
    item = next(
        node
        for node in result.graph.nodes
        if node.concrete_entity == EntityIdentity("parallax.compatibility", "OrderItem")
    )
    assert _view(result.graph, item, "order") is None
