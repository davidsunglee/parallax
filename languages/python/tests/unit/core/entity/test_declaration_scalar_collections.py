"""Typed scalar collections: ``Attr[tuple[T, ...]]`` declarations and their refusals.

This module omits ``from __future__ import annotations`` so the engine sees live
annotation objects. Element-shaping options shape each element, the empty tuple
is the default, and an exact tuple of the element type's carriers is the only
input. Every refusal belongs to an existing owner: annotation shape and element
carriers at class creation and construction, Attribute invariants as
option-context errors, role rules at model formation, and element value spaces
through the shared assignment judgement and the write.
"""

import datetime as dt
import re
import uuid
from collections.abc import Callable
from decimal import Decimal
from enum import IntEnum, StrEnum
from typing import Any, cast

import pytest
from pydantic import ValidationError

from parallax.core import (
    MANY_TO_ONE,
    Attr,
    DomainModel,
    Entity,
    EntityDefinitionError,
    QueryDefinitionError,
    Rel,
    ValueObject,
    attr,
    index,
    rel,
)
from parallax.core.base import FLOAT32, INT32, STRING, Float32, Int32
from parallax.core.base import Decimal as NeutralDecimal
from parallax.core.entity._declaration import declaration_of, shape_of
from parallax.core.entity._errors import EditError
from parallax.core.execution import ExecutionFailure
from parallax.core.metamodel import Multiplicity, ScalarDefinition
from parallax.core.model_formation import MetamodelValidationError
from parallax.core.predicate import serialize
from parallax.core.unit_work import WriteRejectedError
from parallax.snapshot import TxnContext, connect
from tests._support.db_port import ScriptedAdapter, Transact
from tests._support.query_probes import predicate_node
from tests._support.root_ownership import own_root

_NS = "scalar.collection.typed"
_MANY = Multiplicity.MANY


class Detail(ValueObject):
    labels: Attr[tuple[str, ...]] = attr()
    weights: Attr[tuple[float, ...]] = attr(type=Float32)


class Order(Entity, table="orders", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    tags: Attr[tuple[str, ...]] = attr(column="tag_list")
    marks: Attr[tuple[int, ...]] = attr(type=Int32)
    amounts: Attr[tuple[Decimal, ...]] = attr(precision=12, scale=2)
    instants: Attr[tuple[dt.datetime, ...]] = attr()
    tokens: Attr[tuple[uuid.UUID, ...]] = attr(read_only=True)
    detail: Attr[Detail | None] = attr()


def _attribute(name: str) -> Any:
    declared = declaration_of(Order)
    return next(item for item in declared.attributes if item.identity.name == name)


def test_a_tuple_annotation_declares_a_collection_of_its_shaped_element_type() -> None:
    assert _attribute("tags").definition == ScalarDefinition("tags", STRING, False, _MANY)
    assert _attribute("tags").storage.name == "tag_list"
    assert _attribute("marks").definition == ScalarDefinition("marks", INT32, False, _MANY)
    assert _attribute("amounts").type == NeutralDecimal(12, 2)
    assert _attribute("tokens").read_only
    leaves = shape_of(Detail).shape.attributes
    assert [leaf.definition for leaf in leaves] == [
        ScalarDefinition("labels", STRING, False, _MANY),
        ScalarDefinition("weights", FLOAT32, False, _MANY),
    ]


def test_every_collection_defaults_to_the_empty_tuple() -> None:
    order = Order(id=1)

    assert (order.tags, order.marks, order.amounts, order.instants, order.tokens) == (
        (),
        (),
        (),
        (),
        (),
    )
    assert Detail().labels == ()


def test_construction_requires_an_exact_tuple() -> None:
    with pytest.raises(TypeError, match="requires a tuple"):
        Order(id=1, tags=cast("Any", ["a"]))
    with pytest.raises(TypeError, match="requires a tuple"):
        Detail(labels=cast("Any", ["a"]))


@pytest.mark.parametrize(
    ("member", "authored", "refusal"),
    [
        (
            "marks",
            (1, True),
            "marks[1]: value True does not match the declared element type Int32()",
        ),
        (
            "amounts",
            (Decimal("1.50"), 1.5),
            "amounts[1]: value 1.5 does not match the declared element type "
            "Decimal(precision=12, scale=2)",
        ),
        (
            "tokens",
            ("123E4567-E89B-12D3-A456-426614174000",),
            "tokens[0]: value '123E4567-E89B-12D3-A456-426614174000' does not match the "
            "declared element type Uuid()",
        ),
        (
            "instants",
            ("2026-01-01T00:00:00Z",),
            "instants[0]: value '2026-01-01T00:00:00Z' does not match the declared element "
            "type Timestamp()",
        ),
        (
            "tags",
            (b"raw",),
            "tags[0]: value b'raw' does not match the declared element type String()",
        ),
        (
            "tags",
            ("a", None),
            "tags[1]: value None does not match the declared element type String()",
        ),
    ],
    ids=[
        "bool-integer",
        "float-decimal",
        "noncanonical-uuid",
        "spelled-instant",
        "bytes-text",
        "null-element",
    ],
)
def test_construction_refuses_an_element_carrier_pydantic_would_convert(
    member: str, authored: tuple[object, ...], refusal: str
) -> None:
    with pytest.raises(ValidationError) as constructed:
        Order(id=1, **{member: authored})

    assert refusal in str(constructed.value)


class _Spelling(StrEnum):
    MALFORMED = "not-a-uuid"


class _Count(IntEnum):
    BEYOND_BINARY32 = 2**24 + 1


def test_a_carrier_refusal_reports_a_subclass_element_as_its_base_value() -> None:
    with pytest.raises(ValidationError) as constructed:
        Order(id=1, tokens=cast("Any", (_Spelling.MALFORMED,)))
    assert "tokens[0]: value 'not-a-uuid' does not match" in str(constructed.value)

    with pytest.raises(ValidationError, match=r"weights\[0\]: value 16777217 does not match"):
        Detail(weights=(_Count.BEYOND_BINARY32,))


def test_value_object_construction_refuses_each_element_carrier() -> None:
    with pytest.raises(ValidationError, match=r"weights\[0\]"):
        Detail(weights=cast("Any", ("heavy",)))
    with pytest.raises(ValidationError, match=r"weights\[0\]: value 16777217"):
        Detail(weights=(2**24 + 1,))
    assert Detail(weights=(1, 2.5)).weights == (1.0, 2.5)


# Each value lies outside its element's value space but in a carrier Pydantic keeps as is.
_OUT_OF_SPACE: list[tuple[str, tuple[object, ...], str]] = [
    ("marks", (1, 2**40), "Order.marks[1]: value 1099511627776 does not match the declared type"),
    (
        "amounts",
        (Decimal("1.234"),),
        "Order.amounts[0]: value Decimal('1.234') does not match the declared type",
    ),
    (
        "instants",
        (dt.datetime(2026, 1, 1),),
        "Order.instants[0]: value datetime.datetime(2026, 1, 1, 0, 0) does not match the "
        "declared type",
    ),
]


def _write_refusal(work: Callable[[TxnContext], object]) -> BaseException:
    port = ScriptedAdapter(Transact())
    database = own_root(connect(port, DomainModel(Order))).using_database_login()
    with pytest.raises(ExecutionFailure) as caught:
        database.transact(work)
    return caught.value.__cause__ or caught.value


@pytest.mark.parametrize(
    ("member", "authored", "refusal"), _OUT_OF_SPACE, ids=["width", "scale", "naive-instant"]
)
def test_an_out_of_space_element_constructs_and_the_write_refuses_it(
    member: str, authored: tuple[object, ...], refusal: str
) -> None:
    order = Order(id=1, **{member: authored})

    assert getattr(order, member) == authored
    refused = _write_refusal(lambda tx: tx.insert(order))
    assert isinstance(refused, WriteRejectedError)
    assert refused.rule == "write-value-type-mismatch"
    assert str(refused).startswith(refusal)


@pytest.mark.parametrize(
    ("member", "authored", "refusal"), _OUT_OF_SPACE, ids=["width", "scale", "naive-instant"]
)
def test_an_edit_judges_a_changed_element_and_carries_an_unchanged_one(
    member: str, authored: tuple[object, ...], refusal: str
) -> None:
    order = Order(id=1, **{member: authored})
    location = refusal.removeprefix("Order.").partition(":")[0]

    with pytest.raises(EditError, match=re.escape(location)):
        Order(id=1).edit(**{member: authored})
    with pytest.raises(EditError, match=re.escape(location)):
        order.edit(**{member: authored})
    assert getattr(order.edit(tags=("carried",)), member) == authored


def test_a_value_object_element_outside_its_space_constructs() -> None:
    detail = Detail(weights=(1e39,))

    assert detail.weights == (1e39,)
    assert detail.edit(labels=("x",)).weights == (1e39,)
    with pytest.raises(EditError, match=r"Detail\.weights\[0\]"):
        Detail().edit(weights=(1e39,))


@pytest.mark.parametrize(
    ("annotation", "match"),
    [
        ("tuple[str, ...] | None", "never nullable"),
        ("tuple[tuple[str, ...], ...]", "not a declarable member type"),
        ("list[str]", "not a declarable member type"),
        ("tuple[str, int]", "spelled `tuple"),
    ],
    ids=["nullable", "nested", "list", "fixed-tuple"],
)
def test_an_ill_shaped_collection_annotation_is_refused(annotation: str, match: str) -> None:
    namespace: dict[str, object] = {}
    source = (
        "class Bad(Entity, table='bad', namespace='scalar.collection.bad'):\n"
        "    id: Attr[int] = attr(primary_key=True)\n"
        f"    tags: Attr[{annotation}] = attr()\n"
    )
    with pytest.raises(EntityDefinitionError, match=match) as caught:
        exec(source, {"Entity": Entity, "Attr": Attr, "attr": attr}, namespace)
    assert caught.value.code == "entity-annotation-invalid"


def test_a_nullable_value_object_collection_leaf_is_refused() -> None:
    with pytest.raises(EntityDefinitionError, match="never nullable") as caught:

        class Bad(ValueObject):  # pyright: ignore[reportUnusedClass]
            labels: Attr[tuple[str, ...] | None] = attr()

    assert caught.value.code == "entity-annotation-invalid"


@pytest.mark.parametrize(
    "options",
    [{"max_length": 8}, {"primary_key": True}, {"optimistic_locking": True}],
    ids=["max-length", "primary-key", "optimistic-locking"],
)
def test_a_collection_refuses_an_entity_option_it_cannot_hold(options: dict[str, Any]) -> None:
    with pytest.raises(EntityDefinitionError, match="many Attribute") as caught:

        class Bad(Entity, table="bad", namespace=_NS):  # pyright: ignore[reportUnusedClass]
            id: Attr[int] = attr(primary_key=not options.get("primary_key", False))
            tags: Attr[tuple[str, ...]] = attr(**options)

    assert caught.value.code == "entity-option-context-invalid"


def test_an_index_naming_a_collection_is_refused_at_formation() -> None:
    class Indexed(Entity, table="indexed", namespace=_NS, indices=(index("byTags", "tags"),)):
        id: Attr[int] = attr(primary_key=True)
        tags: Attr[tuple[str, ...]] = attr()

    with pytest.raises(MetamodelValidationError) as caught:
        DomainModel(Indexed)
    assert [issue.code for issue in caught.value.issues] == [
        "storage-layout-index-over-document-member"
    ]


def test_a_join_endpoint_naming_a_collection_is_refused_at_formation() -> None:
    class Owner(Entity, table="owner", namespace=_NS):
        id: Attr[int] = attr(primary_key=True)

    class Owned(Entity, table="owned", namespace=_NS):
        id: Attr[int] = attr(primary_key=True)
        owners: Attr[tuple[int, ...]] = attr()
        owner: Rel[Owner | None] = rel(cardinality=MANY_TO_ONE, join=("owners", "id"))

    with pytest.raises(MetamodelValidationError) as caught:
        DomainModel(Owner, Owned)
    assert [issue.code for issue in caught.value.issues] == ["relationship-join-type-mismatch"]


def test_an_edit_judges_every_element_and_refuses_a_null_collection() -> None:
    order = Order(id=1, tags=("a",))

    assert order.edit(tags=("b", "b"), marks=()).tags == ("b", "b")
    with pytest.raises(EditError, match=r"Order\.tags\[1\]: value 2") as element:
        order.edit(tags=("a", 2))
    with pytest.raises(EditError, match="required attribute is absent") as null:
        order.edit(tags=None)
    with pytest.raises(EditError) as read_only:
        order.edit(tokens=())
    assert [violation.code for violation in element.value.violations] == ["edit-value-mismatch"]
    assert [violation.code for violation in null.value.violations] == ["edit-value-mismatch"]
    assert [violation.code for violation in read_only.value.violations] == ["edit-read-only"]


def test_a_set_assignment_states_the_whole_collection() -> None:
    assert Order.tags.set(()).value == ()
    with pytest.raises(EditError, match=r"Order\.marks\[0\]"):
        Order.marks.set((2**40,))


@pytest.mark.parametrize("carrier", [["a"], range(2)], ids=["list", "range"])
def test_an_assignment_refuses_any_carrier_but_a_tuple(carrier: object) -> None:
    order = Order(id=1)
    refusals: list[EditError] = []
    for assign in (
        lambda: Order.tags.set(cast("Any", carrier)),
        lambda: order.edit(tags=carrier),
        lambda: Detail().edit(labels=carrier),
    ):
        with pytest.raises(EditError, match="must bind") as caught:
            assign()
        refusals.append(caught.value)
    assert [error.violations[0].code for error in refusals] == ["edit-value-mismatch"] * 3


def test_a_value_object_edit_assigns_its_whole_collection() -> None:
    assert Detail(labels=("x",)).edit(labels=("y", "y")).labels == ("y", "y")
    with pytest.raises(EditError, match=r"Detail\.labels\[0\]"):
        Detail().edit(labels=(1,))


def test_a_nested_collection_is_assigned_only_through_its_owning_occurrence() -> None:
    assert not hasattr(Order.detail.labels, "set")
    assert Order.detail.set(Detail(labels=("x",))).value == Detail(labels=("x",))


@pytest.mark.parametrize(
    "operation",
    [
        lambda: Order.tags == "urgent",
        lambda: Order.tags != "urgent",
        lambda: Order.detail.labels == "x",
        lambda: Detail.labels == "x",
    ],
    ids=["comparison", "negated-comparison", "nested-path", "element-scope"],
)
def test_no_comparison_reads_a_collection_as_one_value(operation: Any) -> None:
    with pytest.raises(QueryDefinitionError, match="scalar collection") as caught:
        operation()
    assert caught.value.code == "query-expression-invalid"


@pytest.mark.parametrize(
    "name", ["in_", "not_in", "between", "contains", "like", "is_null", "is_", "asc", "desc"]
)
def test_a_collection_offers_no_single_value_operation(name: str) -> None:
    assert not hasattr(Order.tags, name)
    assert not hasattr(Order.detail.labels, name)


def test_a_collection_quantifies_its_elements() -> None:
    orders = DomainModel(Order)
    assert serialize(
        predicate_node(Order.where(Order.tags.any(Order.tags.element == "urgent")), orders)
    ) == {
        "any": {
            "path": "scalar.collection.typed.Order.tags",
            "where": {"eq": {"value": "urgent"}},
        }
    }
    assert serialize(predicate_node(Order.where(Order.marks.none()), orders)) == {
        "none": {"path": "scalar.collection.typed.Order.marks"}
    }
