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
from _transact_support import ACCOUNT, PERSON

from _support import mirrored_models as mm
from _support.db_port import (
    RefusingPort,
)
from _support.document_reads import fold_mapping_rows
from parallax.conformance import models, read_models
from parallax.conformance import vo_models as vo
from parallax.conformance.graph_models import POLICY_MODEL, Policy
from parallax.core import LATEST, TX_TIME, Attr, DomainModel, Entity, ValueObject, attr, deep_fetch
from parallax.core.base import INFINITY
from parallax.core.db_port import DbPort, DocumentReadOrdinals, Row, TransactionOutcome
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.entity._layout import CatalogedModel
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Metamodel,
    RelationshipIdentity,
    entity_by_name,
)
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query import deserialize as deserialize_query
from parallax.core.object_query._fluent import ObjectQuery, object_query_node
from parallax.core.temporal_read import Pin, TemporalReadError
from parallax.snapshot import (
    DeferredFeatureError,
    InvalidData,
    InvalidDataError,
    ObjectKey,
    QueryTargetError,
    SnapshotMaterializationError,
    StoredDataIssue,
    handle,
)
from parallax.snapshot.handle import _read, _read_scope
from parallax.snapshot.handle._preflight import preflight
from parallax.snapshot.materialize import (
    InvalidRootInput,
    RelationshipViewKey,
    SnapshotDecodingError,
    SnapshotGraph,
)
from parallax.snapshot.materialize._graph import ABSENT, GraphRows, graph_rows
from parallax.snapshot.materialize._views import ChildSlot

_MODELS = models.load_models()
ORDERS = _MODELS["orders"]
ANIMAL = _MODELS["animal"]
INVOICE = _MODELS["invoice"]
RATE = _MODELS["rate"]
DOCUMENT = _MODELS["document"]

_UTC = dt.UTC

_ORDER_ROW: dict[str, object] = {
    "id": 0,
    "name": "Ada",
    "sku": "A",
    "qty": 1,
    "price": Decimal("1"),
    "active": True,
    "ordered_on": dt.date(2024, 1, 1),
}
"""One `Order` row, its key named by whichever case reads it."""

_ANIMAL_ROW: dict[str, object] = {
    "id": 0,
    "name": "",
    "owner_id": 10,
    "license_id": None,
    "indoor": None,
    "bark_volume": None,
    "tusk_length": None,
    "kind": "dog",
}
"""One shared-table animal row, per-concrete columns null until a case names one."""


class RequiredProfile(ValueObject):
    label: Attr[str]


class ProfileOwner(Entity, table="profile_owner", namespace="parallax.compatibility"):
    id: Attr[int] = attr(primary_key=True)
    profile: Attr[RequiredProfile]


_PROFILE_OWNER_MODEL = DomainModel(ProfileOwner)


def _rows(graph: SnapshotGraph) -> GraphRows:
    """The sealed arrays behind ``graph``.

    This suite grades what the EXECUTOR built — fan-back, guards, and milestone
    partitioning — so it reads the graph's own rows rather than a merge's view
    of them, which would fold exactly the duplicates a fan-back has to keep
    apart.
    """
    return graph_rows(graph)


def _root(result: handle.FindResult) -> int:
    return _valid_root(_rows(result.graph))


def _valid_root(rows: GraphRows, index: int = 0) -> int:
    root = rows.roots[index]
    assert not isinstance(root, InvalidRootInput)
    return root


def _value(rows: GraphRows, projection: int, entity: str, member: str) -> object:
    """One converted projection's value for a member, named structurally."""
    identity = AttributeIdentity(EntityIdentity("parallax.compatibility", entity), member)
    return rows.member_rows[projection][rows.layouts[projection].index_of[identity]]


def _view(rows: GraphRows, projection: int, attach_key: str) -> object:
    """The value a projection's view carries, found by the attach key a plan
    derived — and ``ABSENT`` where the projection holds no such slot at all.

    A view row is positional against the source layout the execution's schema
    laid the projection out with, so finding a slot by name means asking the
    schema which slots that ``(source level, concrete)`` pair carries.
    """
    layout = rows.schema.source(rows.sources[projection], rows.layouts[projection])
    return next(
        (
            rows.view_rows[projection][slot]
            for slot, key in enumerate(layout.slots)
            if (key.narrowed_view or key.relationship.name) == attach_key
        ),
        ABSENT,
    )


def _refs(value: object) -> tuple[int, ...]:
    return cast("tuple[int, ...]", value)


def _cataloged(model: Metamodel) -> CatalogedModel:
    """``model`` paired with its member layouts, as a connected ``Database``
    resolves the pair once and hands the executor for every read it serves."""
    return CatalogedModel(model)


def _find(query: ObjectQueryNode, model: Metamodel, port: DbPort) -> handle.FindResult:
    return handle.find(preflight(query, model=model, form="graph"), _cataloged(model), port)


def _find_history(
    query: ObjectQueryNode, model: Metamodel, port: DbPort
) -> handle.HistoryFindResult:
    return handle.find_history(preflight(query, model=model, form="graph"), _cataloged(model), port)


class QueuePort:
    """A fake `m-db-port` returning one canned response per `execute()` call,
    in call order — enough to drive the executor's own per-level loop without
    a real database."""

    dialect: Dialect = POSTGRES

    def __init__(self, responses: Sequence[list[Row]]) -> None:
        self._responses = list(responses)
        self.executed: list[tuple[str, list[object]]] = []

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        self.executed.append((sql, list(binds)))
        return fold_mapping_rows(self._responses.pop(0), document_reads)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise NotImplementedError

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:  # pragma: no cover
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
    query = deserialize_query(
        {
            "target": "Order",
            "predicate": {"eq": {"attr": "Order.id", "value": 1}},
            "includes": [{"segments": [{"rel": "Order.items"}]}],
        }
    )
    result = _find(query, ORDERS, port)
    assert len(port.executed) == 2
    rows = _rows(result.graph)
    items = _refs(_view(rows, _root(result), "items"))
    assert [_value(rows, ref, "OrderItem", "id") for ref in items] == [11]


def test_find_empty_root_short_circuits_with_no_child_statement() -> None:
    port = QueuePort([[]])
    query = deserialize_query(
        {
            "target": "Order",
            "predicate": {"eq": {"attr": "Order.id", "value": 999}},
            "includes": [{"segments": [{"rel": "Order.items"}, {"rel": "OrderItem.statuses"}]}],
        }
    )
    result = _find(query, ORDERS, port)
    assert len(port.executed) == 1
    assert _rows(result.graph).roots == ()
    assert len(port.executed) == 1


def test_row_form_does_not_judge_an_unrequested_required_occurrence() -> None:
    port = QueuePort([[{"id": 1}]])
    result = handle.Database.connect(port, _PROFILE_OWNER_MODEL).read_rows(
        object_query_node(ProfileOwner.where(ProfileOwner.id == 1))
    )
    assert result.rows == ({"id": 1},)
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
    query = deserialize_query(
        {
            "target": "Order",
            "predicate": {"eq": {"attr": "Order.id", "value": 4}},
            "includes": [{"segments": [{"rel": "Order.items"}, {"rel": "OrderItem.statuses"}]}],
        }
    )
    result = _find(query, ORDERS, port)
    assert len(port.executed) == 2
    assert _view(_rows(result.graph), _root(result), "items") == ()


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
    query = deserialize_query(
        {
            "target": "Order",
            "predicate": {"eq": {"attr": "Order.id", "value": 1}},
            "includes": [{"segments": [{"rel": "Order.items"}, {"rel": "OrderItem.order"}]}],
        }
    )
    result = _find(query, ORDERS, port)
    assert len(port.executed) == 2  # the back-reference costs nothing
    rows = _rows(result.graph)
    (item,) = _refs(_view(rows, _root(result), "items"))
    assert _view(rows, item, "order") == rows.roots[0]


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
    query = deserialize_query(
        {
            "target": "Order",
            "predicate": {"eq": {"attr": "Order.id", "value": 1}},
            "includes": [{"segments": [{"rel": f"Order.{relationship}"}]}],
        }
    )
    _find(query, ORDERS, port)
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
    query = deserialize_query(
        {
            "target": "Person",
            "predicate": {"eq": {"attr": "Person.id", "value": 10}},
            "includes": [{"segments": [{"rel": "Person.animals"}]}],
        }
    )
    result = _find(query, ANIMAL, port)
    rows = _rows(result.graph)
    (animal,) = _refs(_view(rows, _root(result), "animals"))
    assert rows.layouts[animal].concrete == EntityIdentity("parallax.compatibility", "Dog")
    # The synthetic tag is nobody's member, so no row position stands for it.
    assert all(attribute.identity.name != "kind" for attribute in rows.layouts[animal].attributes)


def test_find_threads_a_root_narrow_to_a_single_tpcs_concrete() -> None:
    # A table-per-concrete-subtype abstract root narrowed to exactly one
    # concrete compiles to an ordinary
    # single-table read (`m-sql`'s `_compile_tpcs_single`) — the row carries no
    # `familyVariant` at all. `CompiledRead.narrow_to` is what lets the converted
    # row still name the row's own concrete identity, rather than the abstract
    # queried `target`.
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
    query = deserialize_query(
        {"target": "Document", "predicate": {"all": {}}, "narrowTo": ["Invoice"]}
    )
    result = _find(query, DOCUMENT, port)
    rows = _rows(result.graph)
    assert rows.layouts[_root(result)].concrete == EntityIdentity(
        "parallax.compatibility", "Invoice"
    )


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
    query = deserialize_query(
        {
            "target": "InvoiceLine",
            "predicate": {"eq": {"attr": "InvoiceLine.id", "value": 1000}},
            "temporal": {"transaction-time": {"history": {}}},
        }
    )
    result = _find_history(query, INVOICE, port)
    assert len(port.executed) == 1
    assert [g.pin.tx_time for g in result.graphs] == [
        dt.datetime(2024, 1, 1, tzinfo=_UTC),
        dt.datetime(2024, 4, 1, tzinfo=_UTC),
    ]
    assert [
        _value(rows, _valid_root(rows), "InvoiceLine", "amount")
        for rows in map(_rows, result.graphs)
    ] == [
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
    query = deserialize_query(
        {
            "target": "InvoiceLine",
            "predicate": {"eq": {"attr": "InvoiceLine.invoiceId", "value": 100}},
            "temporal": {"transaction-time": {"history": {}}},
        }
    )
    result = _find_history(query, INVOICE, port)
    assert len(result.graphs) == 1
    rows = _rows(result.graphs[0])
    assert [_value(rows, _valid_root(rows, index), "InvoiceLine", "id") for index in range(2)] == [
        1000,
        2000,
    ]


def test_find_history_classifies_an_invalid_milestone_before_partitioning() -> None:
    port = QueuePort(
        [
            [
                {
                    "id": 1000,
                    "invoice_id": 100,
                    "amount": Decimal("50.00"),
                    "in_z": None,
                    "out_z": INFINITY,
                }
            ]
        ]
    )
    query = deserialize_query(
        {
            "target": "InvoiceLine",
            "predicate": {"eq": {"attr": "InvoiceLine.invoiceId", "value": 100}},
            "temporal": {"transaction-time": {"history": {}}},
        }
    )
    with pytest.raises(SnapshotDecodingError) as refusal:
        _find_history(query, INVOICE, port)
    assert refusal.value.member == AttributeIdentity(
        EntityIdentity("parallax.compatibility", "InvoiceLine"), "txStart"
    )


def test_find_history_refuses_a_root_whose_own_key_never_decoded() -> None:
    # The arm of the shared publication gate with no converted node behind the
    # result position at all: a milestone read has no in-band channel to publish a
    # verdict through, so it refuses the whole batch before partitioning it.
    port = QueuePort(
        [
            [
                {
                    "id": None,
                    "invoice_id": 100,
                    "amount": Decimal("50.00"),
                    "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
                    "out_z": INFINITY,
                }
            ]
        ]
    )
    query = deserialize_query(
        {
            "target": "InvoiceLine",
            "predicate": {"eq": {"attr": "InvoiceLine.invoiceId", "value": 100}},
            "temporal": {"transaction-time": {"history": {}}},
        }
    )
    with pytest.raises(SnapshotDecodingError) as refusal:
        _find_history(query, INVOICE, port)
    assert refusal.value.code == "snapshot-decoding-failed"


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
    query = deserialize_query(
        {
            "target": "DepositRate",
            "predicate": {"eq": {"attr": "DepositRate.id", "value": 1}},
            "temporal": {"transaction-time": {"history": {}}, "valid-time": {"asOf": "latest"}},
        }
    )
    result = _find_history(query, RATE, port)
    assert [g.pin.tx_time for g in result.graphs] == [
        dt.datetime(2024, 1, 1, tzinfo=_UTC),
        dt.datetime(2024, 2, 1, tzinfo=_UTC),
    ]
    assert [
        _value(rows, _valid_root(rows), "Rate", "amount") for rows in map(_rows, result.graphs)
    ] == [
        Decimal("2.25"),
        Decimal("2.50"),
    ]
    # The Valid-Time dimension rides along too (bitemporal): both milestones share it.
    assert all(g.pin.valid_time == dt.datetime(2024, 1, 1, tzinfo=_UTC) for g in result.graphs)


def test_find_history_refuses_a_plan_carrying_deep_fetch_levels() -> None:
    policy = _MODELS["policy"]
    port = QueuePort([[]])
    query = deserialize_query(
        {
            "target": "Policy",
            "predicate": {"all": {}},
            "temporal": {"transaction-time": {"history": {}}, "valid-time": {"asOf": "latest"}},
            "includes": [{"segments": [{"rel": "Policy.coverages"}]}],
        }
    )
    with pytest.raises(DeferredFeatureError, match="snapshot-history-includes"):
        _find_history(query, policy, port)


# --------------------------------------------------------------------------- #
# The shared read-preflight seam (`_preflight.preflight`)                      #
# --------------------------------------------------------------------------- #
def test_db_find_refuses_a_target_the_connected_model_does_not_declare() -> None:
    # `Person` is a perfectly declared Entity — of another model. What makes the
    # query unanswerable is the CONNECTED model, which is why the refusal is a
    # RuntimeError and why it names neither the query nor the model. Preflight
    # resolves the target before anything else, so the port is never touched:
    # A refusing port raises on any read or write.
    db = handle.Database.connect(RefusingPort(), ACCOUNT)
    with pytest.raises(QueryTargetError) as caught:
        db.find(mm.Person.where(mm.Person.id == 1))
    assert caught.value.code == "query-target-not-in-model"


def test_db_find_refuses_a_deferred_execution_feature_by_name() -> None:
    # `.history()` with `.include(...)` is a VALID query the implementation has
    # not built yet, so the refusal names the Feature rather than calling the
    # query wrong. A refusing port raises on any read or write: classification runs
    # before SQL generation, connection acquisition, and adapter access alike.
    db = handle.Database.connect(RefusingPort(), POLICY_MODEL)
    query = (
        Policy.where(Policy.all).history(TX_TIME).as_of(valid_time=LATEST).include(Policy.coverages)
    )
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
    query = (
        Policy.where(Policy.all).as_of(valid_time=LATEST, tx_time=LATEST).include(Policy.coverages)
    )
    assert db.find(query).results() == []
    assert len(port.executed) == 1


def test_result_shaping_clauses_do_not_hide_a_deferred_feature() -> None:
    # Ordering and a cap are siblings of the two clauses the deferral is read
    # off, so neither can stand between them: a deferral is a property of the
    # read, never of how its rows are shaped afterwards.
    db = handle.Database.connect(RefusingPort(), POLICY_MODEL)
    query = (
        Policy.where(Policy.all)
        .history(TX_TIME)
        .as_of(valid_time=LATEST)
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
    db = handle.Database.connect(RefusingPort(), ACCOUNT)
    query = (
        Policy.where(Policy.all).history(TX_TIME).as_of(valid_time=LATEST).include(Policy.coverages)
    )
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


def test_every_execution_reads_the_querys_own_canonical_node(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The canonical node is the query's own immutable value rather than
    # something an execution derives and caches: every execution reads it, and
    # two executions of one query see the same frozen value. Nothing memoizes a
    # DERIVED value, because there is none to derive.
    nodes: list[ObjectQueryNode] = []
    original = object_query_node

    def recording(query: ObjectQuery[Any, Any]) -> ObjectQueryNode:
        node = original(query)
        nodes.append(node)
        return node

    monkeypatch.setattr(_read_scope, "object_query_node", recording)
    query = mm.Person.where(mm.Person.id == 1)
    db = handle.Database.connect(QueuePort([[], []]), PERSON)
    db.find(query)
    db.find(query)
    first, second = nodes
    assert first == second


# --------------------------------------------------------------------------- #
# The materialization boundary classifies a stored-data finding in band and   #
# translates a graph-construction or lifecycle failure exactly once,          #
# publishing nothing.                                                         #
# --------------------------------------------------------------------------- #
def test_an_undecodable_columns_leaf_is_a_non_hydrating_root() -> None:
    # The read itself succeeded, but `balance` lies outside its declared Decimal
    # value space. Conversion classifies that state before graph construction,
    # and no conforming scalar exists to hydrate the root from.
    port = QueuePort([[{"id": 1, "owner": "Ada", "balance": "not-a-decimal", "version": 1}]])
    db = handle.Database.connect(port, ACCOUNT)
    root = db.find(mm.Account.where(mm.Account.id == 1)).checked().result()
    assert isinstance(root, InvalidData)
    assert root.data is None
    assert {(issue.code, issue.member) for issue in root.issues} == {
        (
            "stored-data-leaf-undecodable",
            AttributeIdentity(EntityIdentity("parallax.compatibility", "Account"), "balance"),
        )
    }
    assert root.version == 1
    assert root.edge is None
    assert len(port.executed) == 1


def test_a_query_failure_keeps_its_own_classification_at_that_boundary() -> None:
    # The counterpart the single translation exists to keep separate: a refusal
    # raised before any graph was being built is never re-classified as a
    # materialization failure.
    db = handle.Database.connect(RefusingPort(), ACCOUNT)
    with pytest.raises(QueryTargetError):
        db.find(Policy.where(Policy.all).as_of(valid_time=LATEST))


def test_an_issue_bearing_graph_classifies_rather_than_failing_materialization() -> None:
    # Conversion carries the stored-data issue into the graph, and
    # classification answers it in band. A default accessor still refuses — with
    # the invalid-data report, never with a materialization failure.
    port = QueuePort([[{"id": 1, "name": "Ada", "address": {"city": 7}}]])
    db = handle.Database.connect(port, vo.CUSTOMER_MODEL)
    snapshot = db.find(vo.Customer.where(vo.Customer.id == 1))
    with pytest.raises(InvalidDataError) as refusal:
        snapshot.result()
    assert not isinstance(refusal.value, SnapshotMaterializationError)
    (record,) = refusal.value.invalid_data
    assert record.data is None
    # Both diagnoses ride one record: the required `street` key is absent and the
    # stored `city` is no string. The undecodable leaf is what makes it
    # non-hydrating; absence alone would have collapsed.
    assert {issue.code for issue in record.issues} == {
        "stored-data-required-member-absent",
        "stored-data-leaf-undecodable",
    }


def test_the_values_lane_classifies_an_invalid_requested_root_key() -> None:
    # The values lane publishes the same union the graph lanes do, one result
    # position at a time: a root whose own key never decoded has no converted row
    # behind its position at all, so it publishes its record carrying nothing.
    port = QueuePort([[{"id": None, "name": "Ada"}]])
    db = handle.Database.connect(port, vo.CUSTOMER_MODEL)
    (row,) = db.read_rows(deserialize_query({"target": "Customer", "predicate": {"all": {}}})).rows
    assert isinstance(row, InvalidData)
    assert row.data is None
    assert row.object_key is None
    assert {issue.code for issue in row.issues} == {"stored-data-primary-key-null"}


def test_the_values_lane_publishes_a_clean_row_beside_a_classified_one() -> None:
    # Classification is per result position here as it is in a graph: one row
    # contradicting the model no longer withholds the rows beside it, which is
    # exactly what the shared publication refusal used to do to the whole read.
    port = QueuePort([[{"id": 1, "name": "Ada"}, {"id": 2, "name": None}]])
    db = handle.Database.connect(port, vo.CUSTOMER_MODEL)
    clean, classified = db.read_rows(
        deserialize_query({"target": "Customer", "predicate": {"all": {}}})
    ).rows
    assert clean == {"id": 1, "name": "Ada"}
    assert isinstance(classified, InvalidData)
    assert classified.ordinal == 1
    assert {issue.code for issue in classified.issues} == {"stored-data-attribute-null"}


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
def _snapshot(roots: tuple[object, ...]) -> handle.Snapshot[object]:
    return handle.Snapshot(roots, Pin())


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


def _invalid(ordinal: int, code: str = "stored-data-attribute-null") -> InvalidData[object]:
    """One published record, spelled the way classification publishes it."""
    return InvalidData(
        issues=frozenset(
            {
                StoredDataIssue(
                    code,  # pyright: ignore[reportArgumentType]
                    EntityIdentity("parallax.compatibility", "Account"),
                    path=(),
                    stored_value=None,
                )
            }
        ),
        data=None,
        object_key=ObjectKey(
            EntityIdentity("parallax.compatibility", "Account"), (("id", ordinal),)
        ),
        version=None,
        edge=None,
        ordinal=ordinal,
    )


def test_arity_is_settled_before_stored_data_validity_is_consulted() -> None:
    # Arity precedence is unchanged: an empty or plural result answers its own
    # arity error whether or not the roots it holds are valid.
    with pytest.raises(handle.NoResultFound):
        _snapshot(()).result()
    with pytest.raises(handle.TooManyResultsFound):
        _snapshot((_invalid(0), _invalid(1))).result()
    with pytest.raises(handle.TooManyResultsFound):
        _snapshot((_invalid(0), 2)).result_or_none()


def test_a_singular_accessor_reports_exactly_the_root_it_narrowed_to() -> None:
    record = _invalid(0)
    for accessor in ("result", "result_or_none"):
        with pytest.raises(InvalidDataError) as refusal:
            getattr(_snapshot((record,)), accessor)()
        assert refusal.value.invalid_data == (record,)


def test_eager_results_aggregates_every_invalid_root_in_result_order() -> None:
    first, second = _invalid(0), _invalid(1, "stored-data-family-tag-unknown")
    with pytest.raises(InvalidDataError) as refusal:
        _snapshot((first, "valid", second)).results()
    assert refusal.value.invalid_data == (first, second)
    assert "2 result root(s)" in str(refusal.value)
    assert "stored-data-attribute-null, stored-data-family-tag-unknown" in str(refusal.value)


def test_the_invalid_data_report_is_the_errors_sole_machine_readable_surface() -> None:
    record = _invalid(0)
    error = InvalidDataError((record,))
    assert error.invalid_data == (record,)
    for absent in ("code", "issues", "records", "cause"):
        assert not hasattr(error, absent)
    with pytest.raises(ValueError, match="at least one record"):
        InvalidDataError(())


def test_the_report_cannot_be_replaced_after_the_message_is_derived() -> None:
    # The count and issue-code summary are derived from the report during
    # construction, so any writable route into the report or into the inherited
    # `args` the message lives in would let a caller leave the refusal's wording
    # describing results the report no longer carries.
    record = _invalid(0)
    error = InvalidDataError((record,))
    message = str(error)
    writable = cast("Any", error)
    for name, replacement in (
        ("invalid_data", ()),
        ("_invalid_data", ()),
        ("args", ("nothing is wrong",)),
    ):
        with pytest.raises(AttributeError):
            setattr(writable, name, replacement)
        with pytest.raises(AttributeError):
            delattr(writable, name)
    assert error.invalid_data == (record,)
    assert str(error) == message


def test_the_frozen_refusal_still_carries_the_state_the_interpreter_owns() -> None:
    # Freezing by hand rather than as a frozen dataclass is what keeps notes and
    # chaining working on a refusal whose report is settled.
    error = InvalidDataError((_invalid(0),))
    error.add_note("an ordinary exception still takes notes")
    assert error.__notes__ == ["an ordinary exception still takes notes"]
    del error.__notes__
    assert not hasattr(error, "__notes__")
    cause = ValueError("the read that produced it")
    with pytest.raises(InvalidDataError) as refusal:
        raise error from cause
    assert refusal.value.__cause__ is cause
    assert refusal.value.__traceback__ is not None


def test_the_checked_view_returns_the_union_in_band_over_the_same_storage() -> None:
    record = _invalid(0)
    snapshot = _snapshot((record, "valid"))
    checked = snapshot.checked()
    assert checked.results() == [record, "valid"]
    assert checked.results() is not checked.results()
    assert checked.pin is snapshot.pin
    assert "CheckedSnapshot(roots=2" in repr(checked)
    # Same storage, so a second view is another window on one result rather than
    # another copy of it.
    assert snapshot.checked().results() == checked.results()


def test_the_checked_view_keeps_the_same_arity_rule_and_refuses_nothing_else() -> None:
    record = _invalid(0)
    assert _snapshot((record,)).checked().result() is record
    assert _snapshot((record,)).checked().result_or_none() is record
    assert _snapshot(()).checked().result_or_none() is None
    with pytest.raises(handle.NoResultFound):
        _snapshot(()).checked().result()
    with pytest.raises(handle.TooManyResultsFound):
        _snapshot((record, "valid")).checked().result()


def test_snapshot_pin_and_repr() -> None:
    pin = Pin(tx_time=dt.datetime(2024, 1, 1, tzinfo=_UTC))
    snapshot = handle.Snapshot((1,), pin)
    assert snapshot.pin is pin
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
    query = deserialize_query(
        {
            "target": "Animal",
            "predicate": {"eq": {"attr": "Animal.id", "value": 1}},
            "includes": [{"segments": [{"rel": "Animal.owner"}]}],
        }
    )
    result = _find(query, ANIMAL, port)
    assert len(port.executed) == 1
    assert _view(_rows(result.graph), _root(result), "owner") is None


def test_a_parent_the_child_level_returned_no_row_for_is_loaded_empty() -> None:
    # The level ran and gathered both keys, so both parents are attached to; the
    # one no returned row correlates with is loaded-EMPTY rather than unloaded,
    # which is the other half of the empty-key short-circuit's own claim.
    port = QueuePort(
        [
            [
                {**_ORDER_ROW, "id": 1},
                {**_ORDER_ROW, "id": 2},
            ],
            [{"id": 11, "order_id": 1, "sku": "x", "quantity": 1, "shipped_on": None}],
        ]
    )
    query = deserialize_query(
        {
            "target": "Order",
            "predicate": {"all": {}},
            "includes": [{"segments": [{"rel": "Order.items"}]}],
        }
    )
    result = _find(query, ORDERS, port)
    rows = _rows(result.graph)
    assert len(port.executed) == 2
    assert [_view(rows, root, "items") for root in (0, 1)] == [(2,), ()]


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
    query = deserialize_query(
        {
            "target": "Order",
            "predicate": {"eq": {"attr": "Order.id", "value": 1}},
            "includes": [{"segments": [{"rel": "Order.items"}, {"rel": "OrderItem.order"}]}],
        }
    )
    result = _find(query, ORDERS, port)
    rows = _rows(result.graph)
    item = next(
        projection
        for projection, layout in enumerate(rows.layouts)
        if layout.concrete == EntityIdentity("parallax.compatibility", "OrderItem")
    )
    assert _view(rows, item, "order") is None


# --------------------------------------------------------------------------- #
# The view-slot seam: a plan in, a slot table out, and the schema every graph  #
# of one execution is laid out by.                                            #
# --------------------------------------------------------------------------- #
def _slot_table(model: Metamodel, document: dict[str, object]) -> tuple[tuple[ChildSlot, ...], ...]:
    """The slot table ``find`` derives from ``document``'s own plan.

    Reached through the module rather than by name so the executor's own
    derivation is what is graded — this is the one place the plan vocabulary
    stops, and nothing below it ever sees a `FetchLevel` again.
    """
    query = deserialize_query(document)
    entity = entity_by_name(model, cast("str", document["target"]))
    assert entity is not None
    validated = preflight(query, model=model, form="graph")
    return _read._slot_table(  # pyright: ignore[reportPrivateUsage] - the seam under test
        deep_fetch.plan(validated, model, projection=deep_fetch.ReadProjectionRequest("all", True))
    )


def _view_key(entity: str, name: str, narrowed: str | None = None) -> RelationshipViewKey:
    return RelationshipViewKey(
        RelationshipIdentity(EntityIdentity("parallax.compatibility", entity), name), narrowed
    )


def test_the_slot_table_places_each_level_under_the_source_that_gathers_it() -> None:
    # A level's slot belongs to whichever source its PARENT rows came from, and
    # the table is dense over every source a projection can be converted at — so
    # a back-reference level, which converts no row of its own, is named as a
    # parent by nothing and owns an empty entry.
    assert _slot_table(
        ORDERS,
        {
            "target": "Order",
            "predicate": {"eq": {"attr": "Order.id", "value": 1}},
            "includes": [{"segments": [{"rel": "Order.items"}, {"rel": "OrderItem.order"}]}],
        },
    ) == (
        (ChildSlot(_view_key("Order", "items")),),
        (ChildSlot(_view_key("OrderItem", "order")),),
        (),
    )


def test_a_root_parented_levels_guard_reaches_the_slot_table_as_its_admitted_set() -> None:
    # The guard is the only thing that filters a level's parents, so it is the
    # only per-concrete fact a slot carries — and a narrowed hop is a distinct
    # view key rather than a qualification of the broad one.
    assert _slot_table(
        ANIMAL,
        {
            "target": "Animal",
            "predicate": {"all": {}},
            "includes": [
                {
                    "segments": [{"rel": "Animal.owner"}, {"rel": "Person.pets"}],
                    "appliesTo": ["Dog"],
                }
            ],
        },
    ) == (
        (
            ChildSlot(
                _view_key("Animal", "owner"),
                frozenset({EntityIdentity("parallax.compatibility", "Dog")}),
            ),
        ),
        (ChildSlot(_view_key("Person", "pets")),),
        (),
    )


def test_a_narrowed_hop_takes_its_own_slot_beside_the_broad_one() -> None:
    assert _slot_table(
        ANIMAL,
        {
            "target": "Person",
            "predicate": {"all": {}},
            "includes": [
                {"segments": [{"rel": "Person.pets"}]},
                {"segments": [{"rel": "Person.pets", "narrowTo": ["Dog"]}]},
            ],
        },
    ) == (
        (
            ChildSlot(_view_key("Person", "pets")),
            ChildSlot(_view_key("Person", "pets", "pets[Dog]")),
        ),
        (),
        (),
    )


def test_a_guarded_out_parent_holds_no_slot_for_the_level_it_was_excluded_from() -> None:
    # The dog is admitted and receives its owner; the cat was never a parent of
    # that level at all, so its row holds no such position — which is what keeps
    # "no such related row" distinct from "this object never participated".
    port = QueuePort(
        [
            [
                {**_ANIMAL_ROW, "id": 1, "name": "Rex", "bark_volume": 7, "kind": "dog"},
                {**_ANIMAL_ROW, "id": 2, "name": "Tom", "indoor": True, "kind": "cat"},
            ],
            [{"id": 10, "name": "Alice"}],
        ]
    )
    query = deserialize_query(
        {
            "target": "Animal",
            "predicate": {"all": {}},
            "includes": [{"segments": [{"rel": "Animal.owner"}], "appliesTo": ["Dog"]}],
        }
    )
    result = _find(query, ANIMAL, port)
    rows = _rows(result.graph)
    dog, cat = (
        next(
            projection
            for projection, layout in enumerate(rows.layouts)
            if layout.concrete == EntityIdentity("parallax.compatibility", name)
        )
        for name in ("Dog", "Cat")
    )
    assert _view(rows, dog, "owner") is not ABSENT
    assert _view(rows, cat, "owner") is ABSENT
    assert rows.view_rows[cat] == ()


def test_two_levels_filling_one_view_leave_the_last_fetch_plan_result_in_its_slot() -> None:
    # A broad path and a guarded sibling are distinct hops that attach under one
    # name, so each runs its own statement and each writes the same slot. The
    # slot retains the LAST of them — two projections of one row, and the plan's
    # own order decides which the graph holds.
    port = QueuePort(
        [
            [{**_ANIMAL_ROW, "id": 1, "name": "Rex", "bark_volume": 7, "kind": "dog"}],
            [{"id": 10, "name": "Alice"}],
            [{"id": 10, "name": "Alice"}],
        ]
    )
    query = deserialize_query(
        {
            "target": "Animal",
            "predicate": {"all": {}},
            "includes": [
                {"segments": [{"rel": "Animal.owner"}]},
                {"segments": [{"rel": "Animal.owner"}], "appliesTo": ["Dog"]},
            ],
        }
    )
    result = _find(query, ANIMAL, port)
    assert len(port.executed) == 3
    rows = _rows(result.graph)
    people = [
        projection
        for projection, layout in enumerate(rows.layouts)
        if layout.concrete == EntityIdentity("parallax.compatibility", "Person")
    ]
    assert len(people) == 2
    assert _view(rows, _valid_root(rows), "owner") == people[-1]


def test_every_milestone_graph_of_one_read_is_laid_out_by_the_one_schema() -> None:
    # A schema is a fact about the PLAN, so partitioning one batch's rows into
    # milestones derives none: the staging graph's own schema is what every
    # milestone builder lays its imported rows out against.
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
    query = deserialize_query(
        {
            "target": "InvoiceLine",
            "predicate": {"eq": {"attr": "InvoiceLine.id", "value": 1000}},
            "temporal": {"transaction-time": {"history": {}}},
        }
    )
    result = _find_history(query, INVOICE, port)
    schemas = {id(_rows(graph).schema) for graph in result.graphs}
    assert len(result.graphs) == 2
    assert len(schemas) == 1
