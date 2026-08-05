"""Conformance row-assembly unit tests (the corpus `read (graph)` lane).

Exercises `parallax.conformance._assembly` independently of the Docker-gated run
sweep: Value Object document decoding and its refusal of invalid stored data,
graph-local identity (family normalization and the table-per-concrete-subtype
exception), the empty-level attach shape, back-reference resolution, and the
lane executor's own per-level loop.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from typing import Any, cast

import pytest

from parallax.conformance import models
from parallax.conformance._assembly import (
    Assembler,
    AssemblyError,
    Node,
    _guarded_parents,  # pyright: ignore[reportPrivateUsage] - unit test drives the lane executor's own path-root guard
    find,
    find_history,
)
from parallax.core.base import INFINITY
from parallax.core.db_port import DbPort, Row
from parallax.core.deep_fetch import CorrelationMember, FetchLevel, LevelRef, RootRef
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    RelationshipIdentity,
)
from parallax.core.op_algebra import deserialize
from parallax.descriptor._records import (
    Attribute,
    Entity,
    ValueObject,
    ValueObjectAttribute,
)
from parallax.descriptor._records import Metamodel as DescriptorMetamodel

_MODELS = models.load_models()
ORDERS = models.accepted_model(_MODELS["orders"])
CUSTOMER = models.accepted_model(_MODELS["customer"])
DOCUMENT = models.accepted_model(_MODELS["document"])
DOCUMENT_CODEC = models.accepted_model(_MODELS["document-codec"])
INVOICE = models.accepted_model(_MODELS["invoice"])

_UTC = dt.UTC
_COMPATIBILITY = "parallax.compatibility"


class QueuePort:
    """A fake `m-db-port` returning one canned response per `execute()` call, in
    call order — enough to drive the lane executor without a real database."""

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


def _meta(model: Metamodel, name: str) -> EntityMetadata:
    entity = model.entity(EntityIdentity(_COMPATIBILITY, name))
    assert entity is not None
    return entity


def _assemble(
    asm: Assembler, model: Metamodel, name: str, rows: Sequence[Mapping[str, object]]
) -> list[Node]:
    """Assemble ``rows`` as ``name``'s own concrete, the shape a compiled read
    supplies for a non-polymorphic position."""
    entity = _meta(model, name)
    return asm.materialize_root(
        name,
        rows,
        resolved_entities=[entity.identity] * len(rows),
        family_variants=[None] * len(rows),
        documents=entity.declared_value_objects,
    )


def _doc(node: Node, key: str) -> dict[str, Any]:
    return cast("dict[str, Any]", node.value_objects[key])


def _kids(node: Node, key: str) -> list[Node]:
    return cast("list[Node]", node.relationships[key])


def _kid(node: Node, key: str) -> Node | None:
    return cast("Node | None", node.relationships[key])


# --------------------------------------------------------------------------- #
# Value Object document decoding.                                             #
# --------------------------------------------------------------------------- #
def test_a_recursive_value_object_decodes_to_its_declared_shape() -> None:
    row = {
        "id": 1,
        "name": "Ada",
        "address": {
            "street": "1 Park Ave",
            "city": "Oslo",
            "geo": {"country": "NO", "elevation": 10.5, "point": {"lat": 1.0, "lon": 2.0}},
            "phones": [{"type": "home", "number": "555"}],
        },
    }
    (node,) = _assemble(Assembler(meta=CUSTOMER), CUSTOMER, "Customer", [row])
    address = _doc(node, "address")
    assert "address" not in node.fields
    assert cast("dict[str, Any]", address["geo"])["country"] == "NO"
    assert address["phones"] == [{"type": "home", "number": "555"}]


def test_a_present_leaf_outside_its_declared_type_is_invalid_stored_data() -> None:
    row = {"id": 1, "label": "Ada", "profile": {"amount": "bogus"}}
    with pytest.raises(AssemblyError, match=r"profile\.amount.*invalid stored data"):
        _assemble(Assembler(meta=DOCUMENT_CODEC), DOCUMENT_CODEC, "Sample", [row])


def _fleet_model() -> Metamodel:
    """A hand-built model whose ``many`` Value Object is attached DIRECTLY to the
    entity: every corpus `many` sits nested inside a top-level `one`, so this is
    the only route to the entity-attached `many` decoding branch."""
    entity = Entity(
        name="Fleet",
        table="fleet",
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        value_objects=(
            ValueObject(
                name="stops",
                column="stops",
                multiplicity="many",
                attributes=(ValueObjectAttribute(name="label", type="string"),),
            ),
        ),
    )
    return models.accepted_model(DescriptorMetamodel(entities=(entity,)))


def test_an_entity_attached_many_value_object_decodes_every_element() -> None:
    model = _fleet_model()
    entity = model.entity(EntityIdentity(None, "Fleet"))
    assert entity is not None
    nodes = Assembler(meta=model).materialize_root(
        "Fleet",
        [{"id": 1, "stops": [{"label": "a"}, {"label": "b"}]}, {"id": 2, "stops": "not-an-array"}],
        resolved_entities=[entity.identity, entity.identity],
        family_variants=[None, None],
        documents=entity.declared_value_objects,
    )
    assert nodes[0].value_objects["stops"] == [{"label": "a"}, {"label": "b"}]
    assert nodes[1].value_objects["stops"] == []


# --------------------------------------------------------------------------- #
# Graph-local identity.                                                       #
# --------------------------------------------------------------------------- #
def test_a_duplicate_projection_renders_its_own_node_under_one_shared_identity() -> None:
    asm = Assembler(meta=ORDERS)
    root_rows = [{"id": 1}]
    root_nodes = _assemble(asm, ORDERS, "Order", root_rows)
    shared_rows = [{"id": 11, "order_id": 1}]

    nodes_a = _attach(asm, _to_many_level("items"), root_nodes, root_rows, shared_rows)
    nodes_b = _attach(asm, _to_many_level("itemsByShipDate"), root_nodes, root_rows, shared_rows)

    assert nodes_a[0] is not nodes_b[0]
    assert nodes_a[0].fields == nodes_b[0].fields
    key = (EntityIdentity(_COMPATIBILITY, "OrderItem"), (11,))
    assert asm._identity[key] is nodes_a[0]  # pyright: ignore[reportPrivateUsage] - unit test reads the assembler's own registry


def test_table_per_concrete_subtype_rows_keep_their_own_concrete_identity() -> None:
    # Each concrete owns its own table with its own primary-key namespace, so two
    # different physical rows sharing key value 1 must not collapse into one
    # identity the way a table-per-hierarchy family's rows legitimately do.
    asm = Assembler(meta=DOCUMENT)
    invoice = _meta(DOCUMENT, "Invoice").identity
    receipt = _meta(DOCUMENT, "Receipt").identity
    asm.materialize_root(
        "FinancialDocument",
        [
            {"id": 1, "title": "A", "folder_id": None, "currency": "USD", "amount_due": "1.00"},
            {"id": 1, "title": "B", "folder_id": None, "paid_on": None},
        ],
        resolved_entities=[invoice, receipt],
        family_variants=["Invoice", "Receipt"],
        documents=(),
    )
    registry = asm._identity  # pyright: ignore[reportPrivateUsage] - unit test reads the assembler's own registry
    assert set(registry) == {(invoice, (1,)), (receipt, (1,))}


def test_a_row_count_that_disagrees_with_its_resolved_entities_is_refused() -> None:
    with pytest.raises(AssemblyError, match="resolved entity count"):
        Assembler(meta=ORDERS).materialize_root(
            "Order",
            [{"id": 1}, {"id": 2}],
            resolved_entities=[_meta(ORDERS, "Order").identity],
            family_variants=[None, None],
            documents=(),
        )


def test_a_row_count_that_disagrees_with_its_family_variants_is_refused() -> None:
    with pytest.raises(AssemblyError, match="familyVariant count"):
        Assembler(meta=ORDERS).materialize_root(
            "Order",
            [{"id": 1}, {"id": 2}],
            resolved_entities=[_meta(ORDERS, "Order").identity] * 2,
            family_variants=[None],
            documents=(),
        )


# --------------------------------------------------------------------------- #
# Level attachment.                                                           #
# --------------------------------------------------------------------------- #
_ORDER_ID = AttributeIdentity(EntityIdentity(_COMPATIBILITY, "Order"), "id")
_ITEM_ORDER_ID = AttributeIdentity(EntityIdentity(_COMPATIBILITY, "OrderItem"), "orderId")


def _to_many_level(attach_key: str = "items") -> FetchLevel:
    return FetchLevel(
        attach_key=attach_key,
        relationship=RelationshipIdentity(EntityIdentity(_COMPATIBILITY, "Order"), attach_key),
        to_many=True,
        parent=RootRef(),
        owner=CorrelationMember(identity=_ORDER_ID, column="id"),
        child_target="OrderItem",
        related=CorrelationMember(
            identity=_ITEM_ORDER_ID, column="order_id", reference="OrderItem.orderId"
        ),
    )


def _to_one_level(attach_key: str = "passport") -> FetchLevel:
    return FetchLevel(
        attach_key=attach_key,
        relationship=RelationshipIdentity(EntityIdentity(_COMPATIBILITY, "Order"), attach_key),
        to_many=False,
        parent=RootRef(),
        owner=CorrelationMember(identity=_ORDER_ID, column="id"),
        child_target="OrderItem",
        related=CorrelationMember(
            identity=_ITEM_ORDER_ID, column="person_id", reference="OrderItem.orderId"
        ),
    )


def _attach(
    asm: Assembler,
    level: FetchLevel,
    parent_nodes: Sequence[Node],
    parent_rows: Sequence[Mapping[str, object]],
    child_rows: Sequence[Mapping[str, object]] | None,
) -> list[Node]:
    item = _meta(ORDERS, "OrderItem")
    return asm.attach_level(
        level,
        parent_nodes,
        parent_rows,
        child_rows,
        resolved_entities=[item.identity] * (0 if child_rows is None else len(child_rows)),
        family_variants=[None] * (0 if child_rows is None else len(child_rows)),
        documents=item.declared_value_objects,
    )


def test_an_empty_level_attaches_the_empty_or_null_result_uniformly() -> None:
    """An empty gathered parent-key set issues NO child query at all — never an
    empty result set, which would mean a query did run and matched nothing."""
    asm = Assembler(meta=ORDERS)
    parent_rows = [{"id": 1}, {"id": 2}]
    parent_nodes = _assemble(asm, ORDERS, "Order", parent_rows)

    assert _attach(asm, _to_many_level(), parent_nodes, parent_rows, None) == []
    assert all(node.relationships["items"] == [] for node in parent_nodes)

    assert _attach(asm, _to_one_level(), parent_nodes, parent_rows, None) == []
    assert all(node.relationships["passport"] is None for node in parent_nodes)


def test_a_to_one_level_matches_at_most_one_child_per_parent() -> None:
    asm = Assembler(meta=ORDERS)
    parent_rows = [{"id": 1}, {"id": 2}]
    parent_nodes = _assemble(asm, ORDERS, "Order", parent_rows)
    _attach(asm, _to_one_level(), parent_nodes, parent_rows, [{"id": 101, "person_id": 1}])
    matched = _kid(parent_nodes[0], "passport")
    assert matched is not None
    assert matched.fields["id"] == 101
    assert _kid(parent_nodes[1], "passport") is None


def _back_reference_level(family: EntityIdentity) -> FetchLevel:
    return FetchLevel(
        attach_key="order",
        relationship=RelationshipIdentity(EntityIdentity(_COMPATIBILITY, "OrderItem"), "order"),
        to_many=False,
        parent=LevelRef(0),
        owner=CorrelationMember(identity=_ITEM_ORDER_ID, column="order_id"),
        is_back_reference=True,
        back_reference_family=family,
    )


def test_a_null_correlation_key_attaches_no_back_reference() -> None:
    asm = Assembler(meta=ORDERS)
    item_rows = [{"id": 11, "order_id": None}]
    item_nodes = [Node(fields=dict(item_rows[0]), pk_columns=("id",))]

    asm.attach_level(
        _back_reference_level(EntityIdentity(_COMPATIBILITY, "Order")),
        item_nodes,
        item_rows,
        None,
    )

    assert item_nodes[0].relationships["order"] is None


def test_a_back_reference_to_an_unregistered_ancestor_is_refused() -> None:
    asm = Assembler(meta=ORDERS)
    orphan_rows = [{"id": 11, "order_id": 999}]
    orphan_nodes = [Node(fields=dict(orphan_rows[0]), pk_columns=("id",))]

    with pytest.raises(AssemblyError, match="no already-assembled"):
        asm.attach_level(
            _back_reference_level(EntityIdentity(_COMPATIBILITY, "Order")),
            orphan_nodes,
            orphan_rows,
            None,
        )


def test_a_path_root_guard_admits_only_its_resolved_source_position() -> None:
    # A guard is a source filter, not a view: an excluded parent contributes no
    # key and receives no attachment, so its view stays unset entirely.
    dog = EntityIdentity(_COMPATIBILITY, "Dog")
    cat = EntityIdentity(_COMPATIBILITY, "Cat")
    level = FetchLevel(
        attach_key="toys",
        relationship=RelationshipIdentity(EntityIdentity(_COMPATIBILITY, "Animal"), "toys"),
        to_many=True,
        parent=RootRef(),
        owner=CorrelationMember(
            identity=AttributeIdentity(EntityIdentity(_COMPATIBILITY, "Animal"), "id"), column="id"
        ),
        child_target="Toy",
        related=CorrelationMember(
            identity=AttributeIdentity(EntityIdentity(_COMPATIBILITY, "Toy"), "animalId"),
            column="animal_id",
            reference="Toy.animalId",
        ),
        source_position=(dog,),
    )
    rows: list[Row] = [{"id": 1}, {"id": 2}]
    nodes = [
        Node(fields={"id": 1}, pk_columns=("id",), resolved_entity=dog),
        Node(fields={"id": 2}, pk_columns=("id",), resolved_entity=cat),
    ]
    admitted_rows, admitted_nodes = _guarded_parents(level, rows, nodes)
    assert admitted_rows == [{"id": 1}]
    assert admitted_nodes == [nodes[0]]


# --------------------------------------------------------------------------- #
# The lane executor's own per-level loop.                                     #
# --------------------------------------------------------------------------- #
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
                "paths": [{"segments": [{"rel": "Order.items"}, {"rel": "OrderItem.order"}]}],
            }
        }
    )
    result = find(op, ORDERS, POSTGRES, "Order", port)
    assert result.execution.round_trips == 2  # the back-reference level costs nothing
    item = _kids(result.nodes[0], "items")[0]
    assert _kid(item, "order") is result.nodes[0]


def test_find_gathers_no_keys_from_an_empty_parent_level_and_issues_no_child_sql() -> None:
    port = QueuePort([[]])
    op = deserialize(
        {
            "deepFetch": {
                "operand": {"eq": {"attr": "Order.id", "value": 999}},
                "paths": [{"segments": [{"rel": "Order.items"}, {"rel": "OrderItem.statuses"}]}],
            }
        }
    )
    result = find(op, ORDERS, POSTGRES, "Order", port)
    assert result.execution.round_trips == 1
    assert result.nodes == ()
    assert len(port.executed) == 1


def test_find_history_groups_rows_by_edge_in_chronological_order() -> None:
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
    result = find_history(op, INVOICE, POSTGRES, "InvoiceLine", port)
    assert [graph.pin["transaction-time"] for graph in result.graphs] == [
        dt.datetime(2024, 1, 1, tzinfo=_UTC),
        dt.datetime(2024, 4, 1, tzinfo=_UTC),
    ]
    assert [node.fields["id"] for node in result.graphs[0].nodes] == [1000, 2000]


def test_find_history_refuses_a_plan_carrying_deep_fetch_levels() -> None:
    policy = models.accepted_model(_MODELS["policy"])
    op = deserialize(
        {
            "deepFetch": {
                "operand": {"history": {"operand": {"all": {}}, "dimension": "transaction-time"}},
                "paths": [{"segments": [{"rel": "Policy.coverages"}]}],
            }
        }
    )
    with pytest.raises(AssemblyError, match="no deep-fetch levels"):
        find_history(op, policy, POSTGRES, "Policy", QueuePort([[]]))
