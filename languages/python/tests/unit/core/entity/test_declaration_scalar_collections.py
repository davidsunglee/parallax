"""Typed scalar collections: ``Attr[tuple[T, ...]]`` declarations and their refusals.

This module omits ``from __future__ import annotations`` so the engine sees live
annotation objects. Element-shaping options shape each element, the empty tuple
is the default, and an exact tuple is the only carrier. Every refusal belongs to
an existing owner: annotation shape at class creation, Attribute invariants as
option-context errors, role rules at model formation, and value rules through
the shared assignment judgement.
"""

import datetime as dt
import uuid
from decimal import Decimal
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
from parallax.core.metamodel import Leaf, Multiplicity
from parallax.core.model_formation import MetamodelValidationError
from parallax.core.predicate import serialize
from tests._support.query_probes import predicate_node

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
    assert _attribute("tags").definition == Leaf("tags", STRING, False, _MANY)
    assert _attribute("tags").storage.name == "tag_list"
    assert _attribute("marks").definition == Leaf("marks", INT32, False, _MANY)
    assert _attribute("amounts").type == NeutralDecimal(12, 2)
    assert _attribute("tokens").read_only
    leaves = shape_of(Detail).shape.attributes
    assert [leaf.definition for leaf in leaves] == [
        Leaf("labels", STRING, False, _MANY),
        Leaf("weights", FLOAT32, False, _MANY),
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
    ("member", "authored", "location"),
    [
        ("marks", (1, True), r"marks\[1\]"),
        ("marks", (2**40,), r"marks\[0\]"),
        ("amounts", (Decimal("1.50"), 1.5), r"amounts\[1\]"),
    ],
    ids=["bool-integer", "out-of-width", "float-decimal"],
)
def test_construction_judges_each_element_as_an_edit_does(
    member: str, authored: tuple[object, ...], location: str
) -> None:
    with pytest.raises(ValidationError, match=location):
        Order(id=1, **{member: authored})
    with pytest.raises(EditError, match=location):
        Order(id=1).edit(**{member: authored})


def test_value_object_construction_judges_each_element() -> None:
    with pytest.raises(ValidationError, match=r"weights\[0\]"):
        Detail(weights=cast("Any", ("heavy",)))
    assert Detail(weights=(1, 2.5)).weights == (1.0, 2.5)


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
    assert serialize(predicate_node(Order.tags.any(Order.tags.element == "urgent"))) == {
        "any": {
            "path": "scalar.collection.typed.Order.tags",
            "where": {"eq": {"value": "urgent"}},
        }
    }
    assert serialize(predicate_node(Order.marks.none())) == {
        "none": {"path": "scalar.collection.typed.Order.marks"}
    }
