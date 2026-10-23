"""Production find-executor tests for ``find`` and ``find_history``.

Exercises the ONE per-level loop against a fake, canned-response `m-db-port`
(no Docker): Database Call accounting (one statement per non-empty level), the
empty-level short-circuit (no child statement issued, gathered from `then`'s
own contract in `m-deep-fetch`), a back-reference level's zero-statement
resolution, `familyVariant` materialization flowing through the executor
(`m-sql` applied to child-level rows), and the milestone-set `find_history`
edge-grouping/ordering.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from decimal import Decimal
from typing import Any, Final, cast

import pytest

from parallax.conformance import dormant_position_document_models as dormant_document
from parallax.conformance import dormant_position_models as dormant
from parallax.conformance import models, read_models
from parallax.conformance import vo_models as vo
from parallax.conformance.composed_beast_models import COMPOSED_BEAST_READER
from parallax.conformance.composed_beast_models import Keeper as BeastKeeper
from parallax.conformance.graph_models import POLICY_MODEL, Policy
from parallax.conformance.story_models import ORDERS_MODEL
from parallax.conformance.story_models import Order as StoryOrder
from parallax.core import (
    LATEST,
    ONE_TO_MANY,
    TX_TIME,
    AbstractRoot,
    AbstractSubtype,
    Attr,
    ConcreteSubtype,
    DomainModel,
    Entity,
    Rel,
    TablePerHierarchy,
    ValueObject,
    attr,
    deep_fetch,
    rel,
)
from parallax.core._execution._concurrency import CONCURRENCY
from parallax.core._execution._preflight import preflight
from parallax.core.base import INFINITY
from parallax.core.db_port import (
    DatabaseConnection,
    DocumentReadOrdinals,
    MappingRow,
    PipelineStatement,
    Row,
    TransactionOutcome,
)
from parallax.core.deep_fetch import RelationshipViewKey
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.entity._authored_resolver import object_query_node
from parallax.core.entity._expressions import AuthoredQuery
from parallax.core.entity._layout import CatalogedModel, LayoutCatalog
from parallax.core.entity._model import model_of
from parallax.core.execution import (
    DeferredFeatureError,
    QueryTargetError,
    ServingModel,
    prepare_model,
)
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Metamodel,
    RelationshipIdentity,
    entity_by_name,
)
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query import deserialize as deserialize_query
from parallax.core.object_query._fluent import ObjectQuery, typed_read_query
from parallax.core.predicate import ModelRejectedError
from parallax.core.predicate._resolved import ResolvedMembership
from parallax.core.read_delivery import (
    InvalidData,
    InvalidDataError,
    PublishedRow,
    StoredDataIssue,
    _read_plan,
    _row_converter,
)
from parallax.core.read_delivery._delivery import find, find_history
from parallax.core.read_delivery._fetch import slot_table
from parallax.core.read_delivery._page import (
    ABSENT,
    ChildSlot,
    InvalidRootInput,
    Page,
    PageRows,
    page_edges,
    page_rows,
)
from parallax.core.read_delivery._page_reader import (
    EMPTY_PAGE_ORIGIN_COLLECTOR,
    EagerPageResult,
    HistoryPageResult,
)
from parallax.core.read_delivery._read_plan import UNCACHED_READ_PLANNER, ReadPlanCache, ReadPlanner
from parallax.core.read_delivery._row_decoding import publication_keys
from parallax.core.read_delivery._row_lane import find_rows
from parallax.core.sql_gen._inheritance import ReadResultContract
from parallax.core.temporal_read import Pin, valid_time_coverage
from parallax.core.unit_work import ReadEvidence
from parallax.core.write_plan import ObjectKey
from parallax.descriptor._records import Attribute as DescriptorAttribute
from parallax.descriptor._records import Entity as DescriptorEntity
from parallax.descriptor._records import Inheritance
from parallax.descriptor._records import Metamodel as DescriptorMetamodel
from parallax.snapshot import (
    Database,
    NoResultFound,
    Snapshot,
    SnapshotMaterializationError,
    TooManyResultsFound,
    WireEntity,
)
from parallax.snapshot._handle import _database, _read
from parallax.snapshot._publication._classify import NonConformingRoot, classify_roots
from parallax.snapshot._publication._root import RootView
from tests._support import mirrored_models as mm
from tests._support.adoption import raises_contextualized
from tests._support.db_port import (
    ConnectsAsItself,
    Read,
    ReadCall,
    RefusingAdapter,
    ScriptedAdapter,
    Transact,
)
from tests._support.document_reads import fold_mapping_rows
from tests._support.root_ownership import own_root
from tests.unit._corpus_model_support import formed, records
from tests.unit._transact_support import ACCOUNT, NEW_ROW, PERSON
from tests.unit.snapshot._snapshot_page_support import (
    ConversionCalls,
    RecordingObserver,
    recorded_conversion_dependencies,
)

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


class EncodedParent(Entity, table="encoded_parent", namespace="parallax.compatibility"):
    id: Attr[int] = attr(primary_key=True)
    payload: Attr[bytes]
    children: Rel[tuple[EncodedChild, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "parent_id"))


class EncodedChild(Entity, table="encoded_child", namespace="parallax.compatibility"):
    id: Attr[int] = attr(primary_key=True)
    parent_id: Attr[int]
    payload: Attr[bytes]
    parent: Rel[EncodedParent | None] = rel(reverse_of="children")


_ENCODED_RELATIONSHIP_MODEL = DomainModel(EncodedParent, EncodedChild)


def _rows(page: Page) -> PageRows:
    """The sealed Page arrays behind an executor result.

    This suite grades fan-back, guards, and the flat history order directly from
    Page storage; a Root View would intentionally fold the duplicate occurrences
    those executor assertions need to distinguish.
    """
    return page_rows(page)


def _root(result: EagerPageResult[ReadEvidence]) -> int:
    return _valid_root(_rows(result.page))


def _valid_root(rows: PageRows, index: int = 0) -> int:
    root = rows.roots[index]
    assert not isinstance(root, InvalidRootInput)
    return root


def _value(rows: PageRows, projection: int, entity: str, member: str) -> object:
    """One converted projection's value for a member, named structurally."""
    identity = AttributeIdentity(EntityIdentity("parallax.compatibility", entity), member)
    return rows.member_rows[projection][rows.layouts[projection].index_of[identity]]


def _view(rows: PageRows, projection: int, attach_key: str) -> object:
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


def _find(
    query: ObjectQueryNode, model: Metamodel, port: DatabaseConnection
) -> EagerPageResult[ReadEvidence]:
    return find(
        preflight(query, model=model, form="graph"),
        _cataloged(model),
        port,
        origin_collector=EMPTY_PAGE_ORIGIN_COLLECTOR,
    )


def _find_history(
    query: ObjectQueryNode, model: Metamodel, port: DatabaseConnection
) -> HistoryPageResult:
    return find_history(preflight(query, model=model, form="graph"), _cataloged(model), port)


class QueuePort(ConnectsAsItself):
    """A fake `m-db-port` returning one canned response per `execute()` call,
    in call order — enough to drive the executor's own per-level loop without
    a real database."""

    dialect: Dialect = POSTGRES

    def __init__(self, responses: Sequence[list[MappingRow]]) -> None:
        self._responses = list(responses)
        self.executed: list[tuple[str, list[object]]] = []

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        self.executed.append((sql, list(binds)))
        return fold_mapping_rows(self._responses.pop(0), document_reads, sql)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise NotImplementedError

    def transaction[T](
        self,
        body: Callable[[DatabaseConnection], T],
        *,
        isolation: str | None = None,
        access_mode: str | None = None,
    ) -> TransactionOutcome[T]:  # pragma: no cover
        raise NotImplementedError


def test_find_collects_claims_without_decoding_trusted_scalar_payloads() -> None:
    with recorded_conversion_dependencies() as calls:
        result = _find(
            deserialize_query({"target": "Order", "predicate": {"true": {}}}),
            ORDERS,
            QueuePort([[{**_ORDER_ROW, "id": 1}, {**_ORDER_ROW, "id": 2}]]),
        )
        assert len(page_rows(result.page).keys) == 2
        RootView(result.page, 0)
        RootView(result.page, 1)

    assert calls == ConversionCalls()


def _states_decoded(observer: RecordingObserver) -> int:
    return sum(value for name, value in observer.events if name == "states_decoded")


def test_a_later_root_document_is_not_classified_before_its_root_view() -> None:
    meta = model_of(_PROFILE_OWNER_MODEL)
    observer = RecordingObserver()
    result = find(
        preflight(
            deserialize_query({"target": "ProfileOwner", "predicate": {"true": {}}}),
            model=meta,
            form="graph",
        ),
        _cataloged(meta),
        QueuePort(
            [
                [
                    {"id": 1, "profile": {"label": "ready"}},
                    {"id": 2, "profile": {"label": 7}},
                ]
            ]
        ),
        origin_collector=EMPTY_PAGE_ORIGIN_COLLECTOR,
        observer=observer,
    )

    assert _states_decoded(observer) == 0
    assert RootView(result.page, 0).issues(0) == ()
    assert _states_decoded(observer) == 1
    later = RootView(result.page, 1)
    assert _states_decoded(observer) == 2
    assert [issue.code for issue in later.issues(0)] == ["stored-data-leaf-undecodable"]


class PipelineQueuePort(QueuePort):
    def __init__(self, responses: Sequence[list[MappingRow]]) -> None:
        super().__init__(responses)
        self.pipelines: list[tuple[PipelineStatement, ...]] = []

    def execute_pipeline(self, statements: Sequence[PipelineStatement]) -> list[list[Row]]:
        batch = tuple(statements)
        self.pipelines.append(batch)
        return super().execute_pipeline(batch)


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
            "predicate": {"eq": {"path": "Order.id", "value": 1}},
            "includes": [{"segments": [{"rel": "Order.items"}]}],
        }
    )
    result = _find(query, ORDERS, port)
    assert len(port.executed) == 2
    rows = _rows(result.page)
    items = _refs(_view(rows, _root(result), "items"))
    assert [_value(rows, ref, "OrderItem", "id") for ref in items] == [11]


def test_encoded_payloads_preserve_integer_identity_gather_and_fanback() -> None:
    port = QueuePort(
        [
            [{"id": 1, "payload_hex": "0a1b"}],
            [{"id": 7, "parent_id": 1, "payload_hex": "0c1d"}],
        ]
    )
    query = deserialize_query(
        {
            "target": "EncodedParent",
            "predicate": {"true": {}},
            "includes": [
                {
                    "segments": [
                        {"rel": "EncodedParent.children"},
                        {"rel": "EncodedChild.parent"},
                    ]
                }
            ],
        }
    )

    result = _find(query, model_of(_ENCODED_RELATIONSHIP_MODEL), port)
    rows = _rows(result.page)
    root = _root(result)
    assert len(_refs(_view(rows, root, "children"))) == 1

    assert port.executed[1][1][-1] == [1]
    assert _value(rows, root, "EncodedParent", "id") == 1
    consumed = RootView(result.page)
    assert (
        consumed.view(1, consumed.view_layout(1).index_of[_view_key("EncodedChild", "parent")]) == 0
    )
    parent_values = consumed.member_values(0)
    child_values = consumed.member_values(1)
    assert (
        parent_values[
            consumed.layout(0).index_of[
                AttributeIdentity(
                    EntityIdentity("parallax.compatibility", "EncodedParent"), "payload"
                )
            ]
        ]
        == b"\x0a\x1b"
    )
    assert (
        child_values[
            consumed.layout(1).index_of[
                AttributeIdentity(
                    EntityIdentity("parallax.compatibility", "EncodedChild"), "payload"
                )
            ]
        ]
        == b"\x0c\x1d"
    )


def test_dependency_ready_sibling_levels_share_one_pipeline_batch() -> None:
    port = PipelineQueuePort(
        [
            [{**_ORDER_ROW, "id": 1}],
            [{"id": 11, "order_id": 1, "sku": "x", "quantity": 1, "shipped_on": None}],
            [{"id": 21, "order_id": 1, "label": "urgent", "priority": 2}],
        ]
    )
    query = deserialize_query(
        {
            "target": "Order",
            "predicate": {"eq": {"path": "Order.id", "value": 1}},
            "includes": [
                {"segments": [{"rel": "Order.items"}]},
                {"segments": [{"rel": "Order.tags"}]},
            ],
        }
    )

    result = _find(query, ORDERS, port)

    (pipeline,) = port.pipelines
    assert len(pipeline) == 2
    assert [statement.binds for statement in pipeline] == [([1],), ([1],)]
    assert all(" = any(%s)" in statement.sql for statement in pipeline)
    rows = _rows(result.page)
    root = _root(result)
    assert len(_refs(_view(rows, root, "items"))) == 1
    assert len(_refs(_view(rows, root, "tags"))) == 1


def test_find_empty_root_short_circuits_with_no_child_statement() -> None:
    port = QueuePort([[]])
    query = deserialize_query(
        {
            "target": "Order",
            "predicate": {"eq": {"path": "Order.id", "value": 999}},
            "includes": [{"segments": [{"rel": "Order.items"}, {"rel": "OrderItem.statuses"}]}],
        }
    )
    result = _find(query, ORDERS, port)
    assert len(port.executed) == 1
    assert _rows(result.page).roots == ()
    assert len(port.executed) == 1


def test_row_form_does_not_judge_an_unrequested_required_occurrence() -> None:
    port = QueuePort([[{"id": 1}]])
    result = (
        own_root(Database.connect(port, _PROFILE_OWNER_MODEL))
        .using_database_login()
        .read_rows(
            object_query_node(ProfileOwner.where(ProfileOwner.id == 1), _PROFILE_OWNER_MODEL)
        )
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
            "predicate": {"eq": {"path": "Order.id", "value": 4}},
            "includes": [{"segments": [{"rel": "Order.items"}, {"rel": "OrderItem.statuses"}]}],
        }
    )
    result = _find(query, ORDERS, port)
    assert len(port.executed) == 2
    assert _view(_rows(result.page), _root(result), "items") == ()


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
            "predicate": {"eq": {"path": "Order.id", "value": 1}},
            "includes": [{"segments": [{"rel": "Order.items"}, {"rel": "OrderItem.order"}]}],
        }
    )
    result = _find(query, ORDERS, port)
    assert len(port.executed) == 2  # the back-reference costs nothing
    rows = _rows(result.page)
    assert len(_refs(_view(rows, _root(result), "items"))) == 1
    consumed = RootView(result.page)
    assert consumed.view(1, consumed.view_layout(1).index_of[_view_key("OrderItem", "order")]) == 0


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
    root: list[MappingRow] = [
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
            "predicate": {"eq": {"path": "Order.id", "value": 1}},
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
            "predicate": {"eq": {"path": "Person.id", "value": 10}},
            "includes": [{"segments": [{"rel": "Person.animals"}]}],
        }
    )
    result = _find(query, ANIMAL, port)
    rows = _rows(result.page)
    (animal,) = _refs(_view(rows, _root(result), "animals"))
    assert rows.layouts[animal].concrete == EntityIdentity("parallax.compatibility", "Dog")
    # The synthetic tag is nobody's member, so no row position stands for it.
    assert all(attribute.identity.name != "kind" for attribute in rows.layouts[animal].attributes)


def _partially_composed_keepers() -> QueuePort:
    return QueuePort(
        [
            [{"id": 10, "name": "Mowgli"}, {"id": 11, "name": "Bagheera"}],
            [
                {"id": 1, "kind": "wolf", "name": "Akela", "keeper_id": 10, "howl": "aroo"},
                {"id": 2, "kind": "bear", "name": "Baloo", "keeper_id": 11, "howl": None},
            ],
        ]
    )


def test_a_broad_include_over_a_partial_family_diagnoses_its_unknown_child_at_the_root() -> None:
    # Keeper.beasts targets the abstract root and the reader composes Wolf alone:
    # the child level keeps Beast as its target, so it reads the shared table
    # unguarded and Bagheera's bear reaches classification rather than vanishing.
    port = _partially_composed_keepers()
    db = own_root(Database.connect(port, COMPOSED_BEAST_READER)).using_database_login()
    query = (
        BeastKeeper.where(BeastKeeper.all)
        .order_by(BeastKeeper.id.asc())
        .include(BeastKeeper.beasts)
    )

    snapshot = db.find(query)

    child_sql, child_binds = port.executed[1]
    assert child_sql == (
        "select t0.id, t0.kind, t0.name, t0.keeper_id, t0.howl from beast t0 "
        "where t0.keeper_id = any(%s) order by t0.id asc"
    )
    assert child_binds == [[10, 11]]
    with pytest.raises(InvalidDataError) as refused:
        snapshot.results()
    mowgli, bagheera = snapshot.checked().results()
    assert [beast.name for beast in cast("Any", mowgli).beasts] == ["Akela"]
    assert refused.value.invalid_data == (bagheera,)
    record = cast("InvalidData[object]", bagheera)
    assert record.data is None
    assert record.object_key is not None
    (issue,) = record.issues
    assert (issue.code, issue.entity, issue.member, issue.object_key, issue.path) == (
        "stored-data-family-tag-unknown",
        EntityIdentity("parallax.compatibility", "Beast"),
        None,
        None,
        (),
    )
    assert issue.stored_value == "bear"
    projected = snapshot.wire().checked().results()
    assert projected[1] == bagheera
    direct = (
        own_root(Database.connect(_partially_composed_keepers(), COMPOSED_BEAST_READER))
        .using_database_login()
        .wire.find(query)
    )
    assert direct.checked().results() == projected


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
        {"target": "Document", "predicate": {"true": {}}, "narrowTo": ["Invoice"]}
    )
    result = _find(query, DOCUMENT, port)
    rows = _rows(result.page)
    assert rows.layouts[_root(result)].concrete == EntityIdentity(
        "parallax.compatibility", "Invoice"
    )


def test_find_history_returns_chronologically_ordered_edge_pinned_roots() -> None:
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
                    "id": 1000,
                    "invoice_id": 100,
                    "amount": Decimal("75.00"),
                    "in_z": dt.datetime(2024, 4, 1, tzinfo=_UTC),
                    "out_z": INFINITY,
                },
            ]
        ]
    )
    query = deserialize_query(
        {
            "target": "InvoiceLine",
            "predicate": {"eq": {"path": "InvoiceLine.id", "value": 1000}},
            "temporal": {"transaction-time": {"history": {}}},
        }
    )
    result = _find_history(query, INVOICE, port)
    assert len(port.executed) == 1
    assert [
        edge.tx_time if edge is not None else None
        for edge in page_edges(result.page, result.milestones)
    ] == [
        dt.datetime(2024, 1, 1, tzinfo=_UTC),
        dt.datetime(2024, 4, 1, tzinfo=_UTC),
    ]
    rows = _rows(result.page)
    assert [
        _value(rows, _valid_root(rows, index), "InvoiceLine", "amount") for index in range(2)
    ] == [
        Decimal("50.00"),
        Decimal("75.00"),
    ]


def test_find_history_keeps_distinct_roots_that_share_one_edge() -> None:
    # Two different physical rows may carry the same Transaction-Time edge;
    # the flat result preserves both database-arrival positions without creating
    # an edge-keyed materialization partition.
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
            "predicate": {"eq": {"path": "InvoiceLine.invoiceId", "value": 100}},
            "temporal": {"transaction-time": {"history": {}}},
        }
    )
    result = _find_history(query, INVOICE, port)
    rows = _rows(result.page)
    assert [_value(rows, _valid_root(rows, index), "InvoiceLine", "id") for index in range(2)] == [
        1000,
        2000,
    ]


def test_find_history_trusts_a_native_temporal_start_but_cannot_derive_an_edge() -> None:
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
            "predicate": {"eq": {"path": "InvoiceLine.invoiceId", "value": 100}},
            "temporal": {"transaction-time": {"history": {}}},
        }
    )
    result = _find_history(query, INVOICE, port)
    assert tuple(page_edges(result.page, result.milestones)) == (None,)
    (verdict,) = classify_roots(RootView(result.page), INVOICE, CONCURRENCY).roots
    assert not isinstance(verdict, NonConformingRoot)


def test_find_history_does_not_reclassify_a_native_primary_key() -> None:
    # The provider-facing fake can bypass a real primary-key constraint, but the
    # materializer still treats the native Column as provider-normalized identity
    # rather than creating a second host-side validity boundary.
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
            "predicate": {"eq": {"path": "InvoiceLine.invoiceId", "value": 100}},
            "temporal": {"transaction-time": {"history": {}}},
        }
    )
    result = _find_history(query, INVOICE, port)
    assert _rows(result.page).roots == (0,)
    assert RootView(result.page, 0).invalid_roots == ()
    assert _value(_rows(result.page), 0, "InvoiceLine", "id") is None


def test_find_history_over_a_concrete_inheritance_target_resolves_the_roots_axes() -> None:
    # `DepositRate` declares NO `as_of_axes` of its own (`Rate`, the
    # family root, does). Every milestone edge the read derives must resolve
    # through the root rather than consulting the concrete entity's empty local
    # axis collection.
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
            "predicate": {"eq": {"path": "DepositRate.id", "value": 1}},
            "temporal": {"transaction-time": {"history": {}}, "valid-time": {"asOf": "latest"}},
        }
    )
    result = _find_history(query, RATE, port)
    assert [
        edge.tx_time if edge is not None else None
        for edge in page_edges(result.page, result.milestones)
    ] == [
        dt.datetime(2024, 1, 1, tzinfo=_UTC),
        dt.datetime(2024, 2, 1, tzinfo=_UTC),
    ]
    rows = _rows(result.page)
    assert [_value(rows, _valid_root(rows, index), "Rate", "amount") for index in range(2)] == [
        Decimal("2.25"),
        Decimal("2.50"),
    ]
    # The Valid-Time dimension rides along too (bitemporal): both milestones share it.
    assert all(
        edge is not None and edge.valid_time == dt.datetime(2024, 1, 1, tzinfo=_UTC)
        for edge in page_edges(result.page, result.milestones)
    )


_RATE_FROM = dt.datetime(2024, 1, 1, tzinfo=_UTC)
_RATE_UNTIL = dt.datetime(2024, 6, 1, tzinfo=_UTC)


def _deposit_rate_history() -> HistoryPageResult:
    """Two Transaction-Time milestones of one `DepositRate`, the first bounded
    on Valid Time and the second open."""
    port = QueuePort(
        [
            [
                {
                    "id": 1,
                    "amount": Decimal("2.25"),
                    "grade": "B",
                    "from_z": _RATE_FROM,
                    "thru_z": _RATE_UNTIL,
                    "in_z": dt.datetime(2024, 1, 1, tzinfo=_UTC),
                    "out_z": dt.datetime(2024, 2, 1, tzinfo=_UTC),
                },
                {
                    "id": 1,
                    "amount": Decimal("2.50"),
                    "grade": "A",
                    "from_z": _RATE_FROM,
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
            "predicate": {"eq": {"path": "DepositRate.id", "value": 1}},
            "temporal": {"transaction-time": {"history": {}}, "valid-time": {"asOf": "latest"}},
        }
    )
    return _find_history(query, RATE, port)


def test_an_inherited_milestones_coverage_reads_the_roots_valid_time_cells_on_the_page() -> None:
    result = _deposit_rate_history()
    rows = _rows(result.page)
    shape = result.milestones
    assert shape is not None

    bounded, opened = (
        valid_time_coverage(shape, rows, _valid_root(rows, index)) for index in range(2)
    )

    assert bounded is not None
    assert opened is not None
    assert bounded.start is _RATE_FROM
    assert bounded.end is _RATE_UNTIL
    assert opened.end is INFINITY


def test_a_pages_milestone_edges_read_no_axis_end(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_arguments: object) -> object:
        raise AssertionError("an edge read an axis end")

    result = _deposit_rate_history()
    monkeypatch.setattr(PageRows, "axis_end", refuse)

    assert [
        (edge.tx_time, edge.valid_time) if edge is not None else None
        for edge in page_edges(result.page, result.milestones)
    ] == [
        (dt.datetime(2024, 1, 1, tzinfo=_UTC), _RATE_FROM),
        (dt.datetime(2024, 2, 1, tzinfo=_UTC), _RATE_FROM),
    ]


def test_find_history_refuses_a_plan_carrying_deep_fetch_levels() -> None:
    policy = _MODELS["policy"]
    port = QueuePort([[]])
    query = deserialize_query(
        {
            "target": "Policy",
            "predicate": {"true": {}},
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
    db = own_root(Database.connect(RefusingAdapter(), ACCOUNT)).using_database_login()
    with pytest.raises(QueryTargetError) as caught:
        db.find(mm.Person.where(mm.Person.id == 1))
    assert caught.value.code == "query-target-not-in-model"


def test_db_find_refuses_a_deferred_execution_feature_by_name() -> None:
    # `.history()` with `.include(...)` is a VALID query the implementation has
    # not built yet, so the refusal names the Feature rather than calling the
    # query wrong. A refusing port raises on any read or write: classification runs
    # before SQL generation, connection acquisition, and adapter access alike.
    db = own_root(Database.connect(RefusingAdapter(), POLICY_MODEL)).using_database_login()
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
    db = own_root(Database.connect(port, POLICY_MODEL)).using_database_login()
    query = (
        Policy.where(Policy.all).as_of(valid_time=LATEST, tx_time=LATEST).include(Policy.coverages)
    )
    assert db.find(query).results() == []
    assert len(port.executed) == 1


def test_result_shaping_clauses_do_not_hide_a_deferred_feature() -> None:
    # Ordering and a cap are siblings of the two clauses the deferral is read
    # off, so neither can stand between them: a deferral is a property of the
    # read, never of how its rows are shaped afterwards.
    db = own_root(Database.connect(RefusingAdapter(), POLICY_MODEL)).using_database_login()
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
    db = own_root(Database.connect(RefusingAdapter(), ACCOUNT)).using_database_login()
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


def test_every_execution_reads_the_querys_own_authored_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The authored state is the query's own immutable value rather than
    # something an execution derives and caches: every execution reads it, two
    # executions of one query see the same frozen value, and neither attaches
    # what it resolved back to it.
    captured: list[AuthoredQuery] = []
    original = typed_read_query

    def recording(query: ObjectQuery[Any, Any]) -> AuthoredQuery:
        authored = original(query)
        captured.append(authored)
        return authored

    monkeypatch.setattr(_database, "typed_read_query", recording)
    query = mm.Person.where(mm.Person.id == 1)
    db = own_root(Database.connect(QueuePort([[], []]), PERSON)).using_database_login()
    db.find(query)
    db.find(query)
    first, second = captured
    assert first is second
    assert first == typed_read_query(query)


# --------------------------------------------------------------------------- #
# The materialization boundary classifies a stored-data finding in band and   #
# translates a graph-construction or lifecycle failure exactly once,          #
# publishing nothing.                                                         #
# --------------------------------------------------------------------------- #
def test_a_native_columns_leaf_is_preserved_without_host_reclassification() -> None:
    # A real provider reaches this point only after its SQL type has normalized
    # the cell. The fake can bypass that boundary, but materialization does not
    # reinterpret the value as fresh Wire or Pydantic input.
    port = QueuePort([[{"id": 1, "owner": "Ada", "balance": "not-a-decimal", "version": 1}]])
    db = own_root(Database.connect(port, ACCOUNT)).using_database_login()
    root = db.find(mm.Account.where(mm.Account.id == 1)).checked().result()
    assert isinstance(root, mm.Account)
    assert root.balance == "not-a-decimal"
    assert len(port.executed) == 1


def test_a_query_failure_keeps_its_own_classification_at_that_boundary() -> None:
    # The counterpart the single translation exists to keep separate: a refusal
    # raised before any graph was being built is never re-classified as a
    # materialization failure.
    db = own_root(Database.connect(RefusingAdapter(), ACCOUNT)).using_database_login()
    with pytest.raises(QueryTargetError):
        db.find(Policy.where(Policy.all).as_of(valid_time=LATEST))


def test_an_issue_bearing_graph_classifies_rather_than_failing_materialization() -> None:
    # Conversion carries the stored-data issue into the graph, and
    # classification answers it in band. A default accessor still refuses — with
    # the invalid-data report, never with a materialization failure.
    port = QueuePort([[{"id": 1, "name": "Ada", "address": {"city": 7}}]])
    db = own_root(Database.connect(port, vo.CUSTOMER_MODEL)).using_database_login()
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


def test_the_values_lane_preserves_a_provider_normalized_native_key() -> None:
    port = QueuePort([[{"id": None, "name": "Ada"}]])
    db = own_root(Database.connect(port, vo.CUSTOMER_MODEL)).using_database_login()
    (row,) = db.read_rows(deserialize_query({"target": "Customer", "predicate": {"true": {}}})).rows
    assert row == {"id": None, "name": "Ada"}


def test_the_values_lane_trusts_each_native_scalar_row() -> None:
    port = QueuePort([[{"id": 1, "name": "Ada"}, {"id": 2, "name": None}]])
    db = own_root(Database.connect(port, vo.CUSTOMER_MODEL)).using_database_login()
    first, second = db.read_rows(
        deserialize_query({"target": "Customer", "predicate": {"true": {}}})
    ).rows
    assert first == {"id": 1, "name": "Ada"}
    assert second == {"id": 2, "name": None}


def _encoded_payload_family() -> Metamodel:
    root = DescriptorEntity(
        name="Root",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(
            DescriptorAttribute(name="id", type="int64", column="id", primary_key=True),
            DescriptorAttribute(name="payload", type="bytes", column="payload", nullable=True),
        ),
    )
    first = DescriptorEntity(
        name="First",
        table="first_tbl",
        inheritance=Inheritance(role="concrete-subtype", parent="Root"),
    )
    second = DescriptorEntity(
        name="Second",
        table="second_tbl",
        inheritance=Inheritance(role="concrete-subtype", parent="Root"),
        attributes=(DescriptorAttribute(name="size", type="int32", column="size", nullable=True),),
    )
    return formed(DescriptorMetamodel(entities=(root, first, second)))


def _row_form(
    model: Metamodel,
    target: str,
    stored: list[MappingRow],
    *,
    cataloged: CatalogedModel | None = None,
    planner: ReadPlanner = UNCACHED_READ_PLANNER,
) -> tuple[PublishedRow, ...]:
    query = preflight(
        deserialize_query({"target": target, "predicate": {"true": {}}}), model=model, form="rows"
    )
    return find_rows(
        query,
        cataloged or _cataloged(model),
        QueuePort([stored]),
        edition="",
        versions=CONCURRENCY,
        planner=planner,
    ).rows


def _counting_publication_keys(patched: pytest.MonkeyPatch) -> list[tuple[str, str | None]]:
    derived: list[tuple[str, str | None]] = []

    def counting(
        contract: ReadResultContract, resolved: EntityIdentity, variant: str | None
    ) -> tuple[str, ...]:
        derived.append((resolved.name, variant))
        return publication_keys(contract, resolved, variant)

    patched.setattr(_row_converter, "publication_keys", counting)
    return derived


def _animal(ordinal: int, kind: str) -> MappingRow:
    return {**_ANIMAL_ROW, "id": ordinal, "kind": kind}


def test_row_form_derives_one_publication_per_concrete_and_variant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    derived = _counting_publication_keys(monkeypatch)

    published = _row_form(
        ANIMAL,
        "Animal",
        [
            _animal(ordinal, kind)
            for ordinal, kind in enumerate(("dog", "cat", "dog", "zebra", "cat", "zebra"), 1)
        ],
    )

    assert len(published) == 6
    assert derived == [("Dog", "Dog"), ("Cat", "Cat"), ("Animal", None)]


def test_a_row_form_page_derives_afresh_without_a_post_bind_layout_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cataloged, planner = _cataloged(ANIMAL), ReadPlanCache()
    stored = [_animal(1, "dog"), _animal(2, "cat")]
    first = _row_form(ANIMAL, "Animal", stored, cataloged=cataloged, planner=planner)

    def forbidden(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("row publication looked a bound fact up again")

    monkeypatch.setattr(_row_converter, "member_sources", forbidden)
    monkeypatch.setattr(LayoutCatalog, "entity", forbidden)
    derived = _counting_publication_keys(monkeypatch)
    second = _row_form(ANIMAL, "Animal", stored, cataloged=cataloged, planner=planner)

    assert second == first
    assert derived == [("Dog", "Dog"), ("Cat", "Cat")]


def test_history_reads_derive_no_row_publication(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("a history read derived a row publication")

    monkeypatch.setattr(_row_converter, "publication_keys", forbidden)
    port = QueuePort(
        [
            [
                {
                    "id": 1000,
                    "invoice_id": 100,
                    "amount": Decimal("75.00"),
                    "in_z": dt.datetime(2024, 1, 1, tzinfo=_UTC),
                    "out_z": INFINITY,
                }
            ]
        ]
    )
    query = deserialize_query(
        {
            "target": "InvoiceLine",
            "predicate": {"eq": {"path": "InvoiceLine.id", "value": 1000}},
            "temporal": {"transaction-time": {"history": {}}},
        }
    )

    assert _find_history(query, INVOICE, port).page.root_count == 1


def _items(row: object) -> list[tuple[str, object]]:
    return list(cast("Mapping[str, object]", row).items())


def test_row_form_publishes_renamed_members_after_the_members_it_keeps() -> None:
    first, second = _row_form(
        _encoded_payload_family(),
        "Root",
        [
            {"id": 1, "payload": "00ff", "size": None, "family_variant": "First"},
            {"id": 2, "payload": None, "size": 3, "family_variant": "Second"},
        ],
    )

    assert _items(first) == [
        ("id", 1),
        ("payload_hex", "00ff"),
        ("size", None),
        ("familyVariant", "First"),
    ]
    assert _items(second) == [
        ("id", 2),
        ("size", 3),
        ("payload_hex", None),
        ("familyVariant", "Second"),
    ]


def test_row_form_pads_sibling_keys_in_publication_key_order() -> None:
    (invoice,) = _row_form(
        DOCUMENT,
        "Document",
        [
            {
                "id": 1,
                "title": "A",
                "folder_id": None,
                "currency": "USD",
                "amount_due": Decimal("2.50"),
                "body": None,
                "paid_amount": None,
                "family_variant": "Invoice",
            }
        ],
    )

    assert _items(invoice) == [
        ("id", 1),
        ("title", "A"),
        ("folder_id", None),
        ("currency", "USD"),
        ("amount_due", Decimal("2.50")),
        ("body", None),
        ("paid_amount", None),
        ("familyVariant", "Invoice"),
    ]


def test_row_form_publishes_an_unknown_tag_under_the_family_root_with_no_variant() -> None:
    (unknown,) = _row_form(ANIMAL, "Animal", [{**_ANIMAL_ROW, "id": 2, "kind": "zebra"}])

    record = cast("InvalidData[Mapping[str, object]]", unknown)
    assert [issue.code for issue in record.issues] == ["stored-data-family-tag-unknown"]
    assert _items(record.data) == [
        ("id", 2),
        ("name", ""),
        ("owner_id", 10),
        ("license_id", None),
        ("indoor", None),
        ("bark_volume", None),
        ("tusk_length", None),
    ]


def test_row_form_publishes_a_member_stored_at_another_members_result_key() -> None:
    blob = DescriptorEntity(
        name="Blob",
        table="blob",
        attributes=(
            DescriptorAttribute(name="id", type="int64", column="id", primary_key=True),
            DescriptorAttribute(name="payload", type="bytes", column="payload", nullable=True),
            DescriptorAttribute(name="shadow", type="bytes", column="payload_hex", nullable=True),
        ),
    )

    (row,) = _row_form(
        formed(DescriptorMetamodel(entities=(blob,))),
        "Blob",
        [{"id": 1, "payload_hex": "00ff", "payload_hex_hex": "0102"}],
    )

    assert _items(row) == [("id", 1), ("payload_hex", "00ff"), ("payload_hex_hex", "0102")]


def test_a_per_node_state_failure_is_translated_once_and_publishes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The read and the conversion both succeed; what fails is building one
    # node's state. State attachment and root publication are atomic, so the
    # whole result is refused rather than partly published.
    def refuse_materialization(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise ValueError("no state for Balance[id=1]")

    monkeypatch.setattr(_read, "typed_root", refuse_materialization)
    port = QueuePort(
        [
            [
                {
                    "bal_id": 1,
                    "acct_num": "A-1",
                    "val": Decimal("5.00"),
                    "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
                    "out_z": INFINITY,
                }
            ]
        ]
    )
    db = own_root(Database.connect(port, read_models.BALANCE_MODEL)).using_database_login()
    with raises_contextualized(SnapshotMaterializationError) as refusal:
        db.find(read_models.Balance.where(read_models.Balance.id == 1))
    assert refusal.value.code == "snapshot-materialization-failed"
    assert isinstance(refusal.value.cause, ValueError)


# --------------------------------------------------------------------------- #
# Snapshot[T]'s own arity accessors, over roots this executor's result surface  #
# publishes.                                                                   #
# --------------------------------------------------------------------------- #
def _snapshot(roots: tuple[object, ...]) -> Snapshot[object]:
    return Snapshot(roots, Pin(), "edition")


def test_result_raises_on_zero_and_on_more_than_one() -> None:
    with pytest.raises(NoResultFound):
        _snapshot(()).result()
    with pytest.raises(TooManyResultsFound):
        _snapshot((1, 2)).result()
    assert _snapshot((1,)).result() == 1


def test_result_or_none_returns_none_on_zero_and_raises_on_more_than_one() -> None:
    assert _snapshot(()).result_or_none() is None
    assert _snapshot((1,)).result_or_none() == 1
    with pytest.raises(TooManyResultsFound):
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
    with pytest.raises(NoResultFound):
        _snapshot(()).result()
    with pytest.raises(TooManyResultsFound):
        _snapshot((_invalid(0), _invalid(1))).result()
    with pytest.raises(TooManyResultsFound):
        _snapshot((_invalid(0), 2)).result_or_none()


def test_a_singular_accessor_reports_exactly_the_root_it_narrowed_to() -> None:
    record = _invalid(0)
    for accessor in ("result", "result_or_none"):
        with pytest.raises(InvalidDataError) as refusal:
            getattr(_snapshot((record,)), accessor)()
        assert refusal.value.invalid_data == (record,)
        # A delayed refusal carries the edition of the result that raised it.
        assert refusal.value.edition == "edition"


def test_eager_results_aggregates_every_invalid_root_in_result_order() -> None:
    first, second = _invalid(0), _invalid(1, "stored-data-family-tag-unknown")
    with pytest.raises(InvalidDataError) as refusal:
        _snapshot((first, "valid", second)).results()
    assert refusal.value.invalid_data == (first, second)
    assert "2 result root(s)" in str(refusal.value)
    assert "stored-data-attribute-null, stored-data-family-tag-unknown" in str(refusal.value)


def test_the_invalid_data_report_is_the_errors_sole_machine_readable_surface() -> None:
    record = _invalid(0)
    error = InvalidDataError((record,), edition="edition")
    assert error.invalid_data == (record,)
    assert error.edition == "edition"
    for absent in ("code", "issues", "records", "cause"):
        assert not hasattr(error, absent)
    with pytest.raises(ValueError, match="at least one record"):
        InvalidDataError((), edition="edition")


def test_the_report_cannot_be_replaced_after_the_message_is_derived() -> None:
    # The count and issue-code summary are derived from the report during
    # construction, so any writable route into the report or into the inherited
    # `args` the message lives in would let a caller leave the refusal's wording
    # describing results the report no longer carries.
    record = _invalid(0)
    error = InvalidDataError((record,), edition="edition")
    message = str(error)
    writable = cast("Any", error)
    for name, replacement in (
        ("invalid_data", ()),
        ("_invalid_data", ()),
        ("edition", "other"),
        ("_edition", "other"),
        ("args", ("nothing is wrong",)),
    ):
        with pytest.raises(AttributeError):
            setattr(writable, name, replacement)
        with pytest.raises(AttributeError):
            delattr(writable, name)
    assert error.invalid_data == (record,)
    assert error.edition == "edition"
    assert str(error) == message


def test_the_frozen_refusal_still_carries_the_state_the_interpreter_owns() -> None:
    # Freezing by hand rather than as a frozen dataclass is what keeps notes and
    # chaining working on a refusal whose report is settled.
    error = InvalidDataError((_invalid(0),), edition="edition")
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
    assert checked.edition == snapshot.edition == "edition"
    assert "CheckedSnapshot(roots=2" in repr(checked)
    # Same storage, so a second view is another window on one result rather than
    # another copy of it.
    assert snapshot.checked().results() == checked.results()


def test_the_checked_view_keeps_the_same_arity_rule_and_refuses_nothing_else() -> None:
    record = _invalid(0)
    assert _snapshot((record,)).checked().result() is record
    assert _snapshot((record,)).checked().result_or_none() is record
    assert _snapshot(()).checked().result_or_none() is None
    with pytest.raises(NoResultFound):
        _snapshot(()).checked().result()
    with pytest.raises(TooManyResultsFound):
        _snapshot((record, "valid")).checked().result()


def test_snapshot_pin_and_repr() -> None:
    pin = Pin(tx_time=dt.datetime(2024, 1, 1, tzinfo=_UTC))
    snapshot = Snapshot((1,), pin, "edition")
    assert snapshot.pin is pin
    assert snapshot.edition == "edition"
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
            "predicate": {"eq": {"path": "Animal.id", "value": 1}},
            "includes": [{"segments": [{"rel": "Animal.owner"}]}],
        }
    )
    result = _find(query, ANIMAL, port)
    assert len(port.executed) == 1
    assert _view(_rows(result.page), _root(result), "owner") is None


def test_a_child_statement_binds_each_gathered_key_once_in_encounter_order() -> None:
    port = QueuePort(
        [
            [
                {**_ANIMAL_ROW, "id": index, "owner_id": owner}
                for index, owner in enumerate((20, 10, 20, 30, 10), start=1)
            ],
            [],
        ]
    )
    query = deserialize_query(
        {
            "target": "Animal",
            "predicate": {"true": {}},
            "includes": [{"segments": [{"rel": "Animal.owner"}]}],
        }
    )
    _find(query, ANIMAL, port)
    assert port.executed[1][1] == [[20, 10, 30]]


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
            "predicate": {"true": {}},
            "includes": [{"segments": [{"rel": "Order.items"}]}],
        }
    )
    result = _find(query, ORDERS, port)
    rows = _rows(result.page)
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
            "predicate": {"eq": {"path": "Order.id", "value": 1}},
            "includes": [{"segments": [{"rel": "Order.items"}, {"rel": "OrderItem.order"}]}],
        }
    )
    result = _find(query, ORDERS, port)
    rows = _rows(result.page)
    item = next(
        projection
        for projection, layout in enumerate(rows.layouts)
        if layout.concrete == EntityIdentity("parallax.compatibility", "OrderItem")
    )
    assert _view(rows, item, "order") is None


# --------------------------------------------------------------------------- #
# Structurally empty positions: no statement, and loaded views where requested. #
# --------------------------------------------------------------------------- #
_DORMANT_ROOTS: Final = pytest.mark.parametrize(
    ("model", "query"),
    [
        pytest.param(
            dormant.DORMANT_POSITION_COLUMNS,
            dormant.Prototype.where(dormant.Prototype.all).include(
                dormant.Prototype.workbenches.prototype
            ),
            id="tph-columns",
        ),
        pytest.param(
            dormant_document.DORMANT_POSITION_DOCUMENT,
            dormant_document.Prototype.where(dormant_document.Prototype.all).include(
                dormant_document.Prototype.workbenches.prototype
            ),
            id="tph-document",
        ),
        pytest.param(
            dormant.DORMANT_POSITION_COLUMNS,
            dormant.Concept.where(dormant.Concept.all).include(dormant.Concept.workbenches),
            id="tpcs-columns",
        ),
        pytest.param(
            dormant_document.DORMANT_POSITION_DOCUMENT,
            dormant_document.Concept.where(dormant_document.Concept.all),
            id="tpcs-document",
        ),
    ],
)


@_DORMANT_ROOTS
def test_a_dormant_root_publishes_no_roots_and_issues_no_statement(
    model: DomainModel, query: ObjectQuery[Any, Any]
) -> None:
    port = ScriptedAdapter()
    db = own_root(Database.connect(port, model)).using_database_login()

    snapshot = db.find(query)
    direct = db.wire.find(query)

    assert snapshot.results() == []
    assert snapshot.wire().results() == []
    assert direct.results() == []
    assert direct.edition == snapshot.edition
    assert port.calls == []


def test_a_dormant_root_prepares_its_levels_but_renders_and_executes_nothing() -> None:
    observer = RecordingObserver()
    meta = model_of(dormant.DORMANT_POSITION_COLUMNS)
    query = deserialize_query(
        {
            "target": "Prototype",
            "predicate": {"true": {}},
            "includes": [
                {"segments": [{"rel": "Prototype.workbenches"}, {"rel": "Workbench.prototype"}]}
            ],
        }
    )

    result = find(
        preflight(query, model=meta, form="graph"),
        _cataloged(meta),
        QueuePort([]),
        origin_collector=EMPTY_PAGE_ORIGIN_COLLECTOR,
        observer=observer,
    )

    assert _rows(result.page).roots == ()
    assert observer.events == [("prepared", 3)]


def _reads(port: ScriptedAdapter) -> list[ReadCall]:
    return [call for call in port.calls if isinstance(call, ReadCall)]


def _wire_entity(published: object) -> WireEntity:
    assert isinstance(published, WireEntity), published
    return published


_COG: Final[MappingRow] = {"id": 1, "kind": "widget", "label": "Cog", "workbench_id": 1, "spin": 3}
_WORKBENCH_ROWS: Final[list[MappingRow]] = [
    {"id": 1, "name": "Bench", "prototype_id": 7, "concept_id": 8},
    {"id": 2, "name": "Shed", "prototype_id": 9, "concept_id": None},
]


def test_an_include_of_a_dormant_target_loads_empty_and_null_without_a_child_statement() -> None:
    port = ScriptedAdapter(Read(rows=list(_WORKBENCH_ROWS)), Read(rows=[_COG]))
    db = own_root(Database.connect(port, dormant.DORMANT_POSITION_COLUMNS)).using_database_login()
    query = (
        dormant.Workbench.where(dormant.Workbench.all)
        .order_by(dormant.Workbench.id.asc())
        .include(dormant.Workbench.prototypes.workbenches)
        .include(dormant.Workbench.prototype)
        .include(dormant.Workbench.gadgets)
    )

    with port:
        snapshot = db.find(query)

    (_root_read, gadgets) = _reads(port)
    assert gadgets.sql == (
        "select t0.id, t0.kind, t0.label, t0.workbench_id, t0.spin from dormant_gadget t0 "
        "where t0.workbench_id = any(%s) order by t0.id asc"
    )
    assert gadgets.binds == ([1, 2],)
    bench, shed = snapshot.results()
    assert (bench.prototypes, bench.prototype) == ((), None)
    assert (shed.prototypes, shed.prototype) == ((), None)
    assert [gadget.label for gadget in bench.gadgets] == ["Cog"]
    assert shed.gadgets == ()
    wired = snapshot.wire().results()
    assert [
        (entity["prototypes"], entity["prototype"], "concepts" in entity)
        for entity in map(_wire_entity, wired)
    ] == [([], None, False), ([], None, False)]


def test_an_include_of_a_dormant_tpcs_target_loads_empty_and_null_without_a_child_statement() -> (
    None
):
    port = ScriptedAdapter(Read(rows=list(_WORKBENCH_ROWS)), Read(rows=[_COG]))
    db = own_root(Database.connect(port, dormant.DORMANT_POSITION_COLUMNS)).using_database_login()
    query = (
        dormant.Workbench.where(dormant.Workbench.all)
        .order_by(dormant.Workbench.id.asc())
        .include(dormant.Workbench.concepts)
        .include(dormant.Workbench.concept)
        .include(dormant.Workbench.gadgets)
    )

    with port:
        direct = db.wire.find(query).results()

    assert len(_reads(port)) == 2
    assert [
        (entity["concepts"], entity["concept"], len(cast("tuple[object, ...]", entity["gadgets"])))
        for entity in map(_wire_entity, direct)
    ] == [([], None, 1), ([], None, 0)]


_GUARDED_NS: Final = "parallax.compatibility"


class Shelf(
    Entity,
    table="guard_shelf",
    namespace=_GUARDED_NS,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    drafts: Rel[tuple[Draft, ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "shelf_id"), order_by=("id",)
    )


class Bookshelf(Shelf, namespace=_GUARDED_NS, inheritance=ConcreteSubtype(tag_value="book")):
    pass


class Spiceshelf(Shelf, namespace=_GUARDED_NS, inheritance=ConcreteSubtype(tag_value="spice")):
    pass


class Sketch(
    Entity,
    table="guard_sketch",
    namespace=_GUARDED_NS,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    shelf_id: Attr[int | None]


class Finished(Sketch, namespace=_GUARDED_NS, inheritance=ConcreteSubtype(tag_value="finished")):
    pass


class Draft(Sketch, namespace=_GUARDED_NS, inheritance=AbstractSubtype()):
    pass


_GUARDED_SHELVES: Final = model_of(
    DomainModel(Shelf, Bookshelf, Spiceshelf, Sketch, Finished, Draft)
)


def test_a_guarded_include_of_a_dormant_target_loads_only_its_admitted_parents() -> None:
    port = QueuePort([[{"id": 1, "kind": "book"}, {"id": 2, "kind": "spice"}]])
    query = deserialize_query(
        {
            "target": "Shelf",
            "predicate": {"true": {}},
            "includes": [{"appliesTo": ["Bookshelf"], "segments": [{"rel": "Shelf.drafts"}]}],
        }
    )

    result = _find(query, _GUARDED_SHELVES, port)

    rows = _rows(result.page)
    book, spice = (_valid_root(rows, index) for index in range(2))
    assert len(port.executed) == 1
    assert _view(rows, book, "drafts") == ()
    assert _view(rows, spice, "drafts") is ABSENT


def _dormant_rate_history(port: DatabaseConnection) -> HistoryPageResult:
    rate = records("rate")
    dormant_rate = DescriptorEntity(
        name="DormantRate",
        namespace="parallax.compatibility",
        inheritance=Inheritance(role="abstract-subtype", parent="parallax.compatibility.Rate"),
    )
    model = formed(replace(rate, entities=(*rate.entities, dormant_rate)))
    query = deserialize_query(
        {
            "target": "DormantRate",
            "predicate": {"true": {}},
            "temporal": {"transaction-time": {"history": {}}, "valid-time": {"asOf": "latest"}},
        }
    )
    return _find_history(query, model, port)


def test_a_dormant_milestone_set_keeps_its_family_temporal_shape_without_a_statement() -> None:
    port = QueuePort([])

    result = _dormant_rate_history(port)

    assert _rows(result.page).roots == ()
    assert (
        result.milestones
        == _find_history(
            deserialize_query(
                {
                    "target": "DepositRate",
                    "predicate": {"true": {}},
                    "temporal": {
                        "transaction-time": {"history": {}},
                        "valid-time": {"asOf": "latest"},
                    },
                }
            ),
            RATE,
            QueuePort([[]]),
        ).milestones
    )
    assert port.executed == []


def test_a_dormant_row_form_read_publishes_no_rows_without_a_statement() -> None:
    port = ScriptedAdapter()
    db = own_root(Database.connect(port, dormant.DORMANT_POSITION_COLUMNS)).using_database_login()

    result = db.read_rows(
        object_query_node(
            dormant.Concept.where(dormant.Concept.all), dormant.DORMANT_POSITION_COLUMNS
        )
    )

    assert result.rows == ()
    assert result.edition == db.find(dormant.Concept.where(dormant.Concept.all)).edition
    assert port.calls == []


@pytest.mark.parametrize(
    ("document", "rule"),
    [
        (
            {"target": "Gadget", "predicate": {"true": {}}, "narrowTo": ["Prototype"]},
            "narrow-empty-effective-set",
        ),
        (
            {"target": "Prototype", "predicate": {"true": {}}, "narrowTo": ["Widget"]},
            "narrow-outside-position",
        ),
    ],
)
def test_an_invalid_query_over_a_dormant_position_is_still_refused(
    document: dict[str, object], rule: str
) -> None:
    port = QueuePort([])

    with pytest.raises(ModelRejectedError) as refused:
        _find(deserialize_query(document), model_of(dormant.DORMANT_POSITION_COLUMNS), port)

    assert refused.value.rule == rule
    assert port.executed == []


def test_an_executable_read_matching_no_rows_still_issues_its_statement() -> None:
    port = ScriptedAdapter(Read(rows=[]))
    db = own_root(Database.connect(port, dormant.DORMANT_POSITION_COLUMNS)).using_database_login()

    with port:
        assert db.find(dormant.Widget.where(dormant.Widget.label == "none")).results() == []

    assert len(_reads(port)) == 1


# --------------------------------------------------------------------------- #
# The view-slot seam: a plan in, a slot table out, and one Page schema.        #
# of one execution is laid out by.                                            #
# --------------------------------------------------------------------------- #
def _slot_table(model: Metamodel, document: dict[str, object]) -> tuple[tuple[ChildSlot, ...], ...]:
    """The slot table ``find`` derives from ``document``'s own plan.

    Reached through the module rather than by name so the executor's own
    derivation is what is graded — this is the one place the plan vocabulary
    stops, and nothing below it ever sees a `FetchStep` again.
    """
    query = deserialize_query(document)
    entity = entity_by_name(model, cast("str", document["target"]))
    assert entity is not None
    validated = preflight(query, model=model, form="graph")
    return slot_table(
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
    # parent by nothing and owns an empty entry. Its own slot carries the
    # concretes its logical claims may resolve to.
    assert _slot_table(
        ORDERS,
        {
            "target": "Order",
            "predicate": {"eq": {"path": "Order.id", "value": 1}},
            "includes": [{"segments": [{"rel": "Order.items"}, {"rel": "OrderItem.order"}]}],
        },
    ) == (
        (ChildSlot(_view_key("Order", "items")),),
        (
            ChildSlot(
                _view_key("OrderItem", "order"),
                targets=frozenset({EntityIdentity("parallax.compatibility", "Order")}),
            ),
        ),
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
            "predicate": {"true": {}},
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
            "predicate": {"true": {}},
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
            "predicate": {"true": {}},
            "includes": [{"segments": [{"rel": "Animal.owner"}], "appliesTo": ["Dog"]}],
        }
    )
    result = _find(query, ANIMAL, port)
    rows = _rows(result.page)
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
    # own order decides which node the result publishes.
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
            "predicate": {"true": {}},
            "includes": [
                {"segments": [{"rel": "Animal.owner"}]},
                {"segments": [{"rel": "Animal.owner"}], "appliesTo": ["Dog"]},
            ],
        }
    )
    result = _find(query, ANIMAL, port)
    assert len(port.executed) == 3
    rows = _rows(result.page)
    people = [
        projection
        for projection, layout in enumerate(rows.layouts)
        if layout.concrete == EntityIdentity("parallax.compatibility", "Person")
    ]
    assert len(people) == 2
    assert _view(rows, _valid_root(rows), "owner") == people[-1]


def test_every_history_root_of_one_read_uses_the_same_page_schema() -> None:
    # A schema is a fact about the plan. Distinct Root Views over the flat
    # history Page therefore expose the same execution-owned layout object.
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
            "predicate": {"eq": {"path": "InvoiceLine.id", "value": 1000}},
            "temporal": {"transaction-time": {"history": {}}},
        }
    )
    result = _find_history(query, INVOICE, port)
    assert len(_rows(result.page).roots) == 2
    first = RootView(result.page, 0)
    second = RootView(result.page, 1)
    assert first.view_layout(0) is second.view_layout(0)


# --------------------------------------------------------------------------- #
# Adoption: what a standalone read and a transaction report over one Serving   #
# Model, and what a publication between them moves.                            #
# --------------------------------------------------------------------------- #
def _account_query() -> Any:
    return mm.Account.where(mm.Account.id == 7)


def _account_node() -> ObjectQueryNode:
    return deserialize_query(
        {"target": "Account", "predicate": {"eq": {"path": "Account.id", "value": 7}}}
    )


def test_a_standalone_find_and_a_transaction_report_one_edition_until_a_publication() -> None:
    # Both shapes adopt from the same Serving Model, so between publications
    # they report one edition; a publication between them changes only what
    # is adopted afterwards, and a result already published keeps its stamp.
    a = prepare_model(ACCOUNT, edition="ledger-a")
    b = prepare_model(ACCOUNT, edition="ledger-b")
    serving = ServingModel(a)
    port = ScriptedAdapter(
        Read(rows=[NEW_ROW]),
        Read(rows=[NEW_ROW]),
        Read(rows=[NEW_ROW]),
        Transact(Read(rows=[NEW_ROW])),
        Read(rows=[NEW_ROW]),
        Transact(Read(rows=[NEW_ROW])),
    )
    db = own_root(Database.connect(port, serving)).using_database_login()

    found = db.find(_account_query())
    wired = db.wire.find(_account_node())
    rows = db.read_rows(_account_node())
    inside = db.transact(lambda tx: (tx.edition, tx.find(_account_query()).edition))
    assert (found.edition, found.checked().edition, wired.edition, rows.edition) == (
        "ledger-a",
    ) * 4
    assert inside == ("ledger-a", "ledger-a")

    serving.publish(b, expected=a)

    assert (found.edition, wired.edition, rows.edition) == ("ledger-a",) * 3
    assert db.find(_account_query()).edition == "ledger-b"
    assert db.transact(lambda tx: (tx.edition, tx.find(_account_query()).edition)) == (
        "ledger-b",
        "ledger-b",
    )


def test_a_delayed_refusal_from_a_keeps_a_inside_a_transaction_under_b() -> None:
    # The accessor is reached inside a transaction adopted under B, so the
    # failure escaping that transaction is contextualized under B — and the
    # refusal it carries is still the one the result under A settled, with A's
    # edition on it. Access itself starts no execution and adopts nothing.
    a = prepare_model(vo.CUSTOMER_MODEL, edition="ledger-a")
    b = prepare_model(vo.CUSTOMER_MODEL, edition="ledger-b")
    serving = ServingModel(a)
    port = ScriptedAdapter(
        Read(rows=[{"id": 1, "name": "Ada", "address": {"city": 7}}]), Transact()
    )
    db = own_root(Database.connect(port, serving)).using_database_login()

    snapshot = db.find(vo.Customer.where(vo.Customer.id == 1))
    serving.publish(b, expected=a)

    with raises_contextualized(InvalidDataError) as failed:
        db.transact(lambda tx: snapshot.result())

    assert failed.edition == "ledger-b"
    assert failed.value.edition == "ledger-a" == snapshot.edition
    (record,) = failed.value.invalid_data
    assert {issue.code for issue in record.issues} == {
        "stored-data-required-member-absent",
        "stored-data-leaf-undecodable",
    }


def _item_row(item_id: int, order_id: int) -> MappingRow:
    return {
        "id": item_id,
        "order_id": order_id,
        "sku": "SKU",
        "quantity": 1,
        "shipped_on": dt.date(2024, 2, 1),
    }


def _page(orders: tuple[int, ...], parents: tuple[int, ...]) -> tuple[Read, Read]:
    """A page's root rows, then one item for each parent it delivers."""
    return (
        Read(rows=[{**_ORDER_ROW, "id": order} for order in orders]),
        Read(rows=[_item_row(parent * 10, parent) for parent in parents]),
    )


def test_typed_and_wire_reads_share_resolved_include_work_within_each_delivery_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolutions: list[object] = []
    child_compiles: list[deep_fetch.PlannedEntityQuery] = []
    resolve = cast("Callable[..., Any]", vars(deep_fetch)["resolve_temporal_visibility"])
    compile_child = cast("Callable[..., Any]", vars(_read_plan)["compile_template"])

    def counting_resolution(*args: Any, **kwargs: Any) -> Any:
        resolutions.append(kwargs["resolution"])
        return resolve(*args, **kwargs)

    def counting_child(query: deep_fetch.PlannedEntityQuery, *args: Any, **kwargs: Any) -> Any:
        child_compiles.append(query)
        return compile_child(query, *args, **kwargs)

    monkeypatch.setattr(deep_fetch, "resolve_temporal_visibility", counting_resolution)
    monkeypatch.setattr(_read_plan, "compile_template", counting_child)
    eager_read, first_page, last_page = (
        _page((1, 2), (1, 2)),
        _page((1, 2, 3), (1, 2)),
        _page((3,), (3,)),
    )
    port = ScriptedAdapter(
        *eager_read, *eager_read, *first_page, *last_page, *first_page, *last_page
    )
    root = own_root(Database.connect(port, ORDERS_MODEL))
    db = root.using_database_login()
    query = StoryOrder.where(StoryOrder.active == True).include(StoryOrder.items)  # noqa: E712

    typed = db.find(query).results()
    eager = (len(resolutions), len(child_compiles))
    wire = db.wire.find(query).results()

    assert [order.id for order in typed] == [node["id"] for node in wire] == [1, 2]
    assert eager == (2, 1)
    assert [type(resolution).__name__ for resolution in resolutions] == [
        "RootSelections",
        "PropagatedRootSelections",
    ]
    (eager_child,) = child_compiles
    assert isinstance(eager_child.predicate.predicate, ResolvedMembership)

    with db.stream(query, batch_size=2) as stream:
        assert [order.id for order in stream] == [1, 2, 3]
    paged = (len(resolutions), len(child_compiles))
    with db.wire.stream(query, batch_size=2) as wire_stream:
        assert [node["id"] for node in wire_stream] == [1, 2, 3]

    # The first page plans apart from the eager read and compiles its own child
    # read; the later page plans only its root and borrows that closed, compiled
    # child work, and Wire reuses each Typed plan without resolving or compiling
    # anything again.
    assert len(child_compiles) == paged[1] == 2
    assert len(resolutions) == paged[0]
    assert [type(resolution).__name__ for resolution in resolutions[eager[0] :]] == [
        "RootSelections",
        "PropagatedRootSelections",
        "RootSelections",
    ]
    assert child_compiles[1] == eager_child
    statistics = root._resources.planner._statistics()  # pyright: ignore[reportPrivateUsage] - the cache's own census
    assert (statistics.misses, statistics.hits) == (3, 3)
