"""Which expression family a descriptor answers, statically and at run time.

The static half is pinned by `assert_type` and by suppressions that must stay
necessary: strict Pyright fails an idle ignore, so each refused capability below
is refused by the declared signatures, not merely at run time.
"""

from __future__ import annotations

from typing import Any, assert_type

import pytest

from parallax.core import (
    MANY_TO_ONE,
    ONE_TO_MANY,
    Attr,
    Entity,
    EntityDefinitionError,
    IncludePath,
    Predicate,
    Rel,
    ValueObject,
    attr,
    rel,
)
from parallax.core.entity._expressions import (
    AssignableManyScalarExpr,
    AssignableManyValueObjectExpr,
    AssignableScalarExpr,
    AssignableValueObjectExpr,
    ManyRelationshipExpr,
    ManyScalarExpr,
    ManyValueObjectExpr,
    RelationshipExpr,
    ScalarElementExpr,
    ScalarExpr,
)
from tests._support.query_probes import predicate_node

_NS = "expression.families"


class Stop(ValueObject):
    city: Attr[str]
    codes: Attr[tuple[str, ...]]


class Leg(ValueObject):
    origin: Attr[Stop]
    stops: Attr[tuple[Stop, ...]]


class Carrier(Entity, table="ef_carrier", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=16)
    routes: Rel[tuple[Route, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "carrier_id"))


class Route(Entity, table="ef_route", namespace=_NS):
    id: Attr[int] = attr(primary_key=True)
    carrier_id: Attr[int | None]
    tags: Attr[tuple[str, ...]]
    leg: Attr[Leg | None]
    legs: Attr[tuple[Leg, ...]]
    carrier: Rel[Carrier | None] = rel(cardinality=MANY_TO_ONE, join=("carrier_id", "id"))


def test_entity_descriptors_answer_their_assignable_families() -> None:
    assert_type(Route.id, AssignableScalarExpr[Route, int])
    assert_type(Route.tags, AssignableManyScalarExpr[Route, str])
    assert_type(Route.leg, AssignableValueObjectExpr[Route, Leg | None])
    assert_type(Route.legs, AssignableManyValueObjectExpr[Route, Leg])
    assert_type(Route.carrier, RelationshipExpr[Route, Carrier])
    assert_type(Carrier.routes, ManyRelationshipExpr[Carrier, Route])
    assert isinstance(Route.tags, AssignableManyScalarExpr)
    assert isinstance(Route.leg, AssignableValueObjectExpr)
    assert isinstance(Route.legs, AssignableManyValueObjectExpr)
    assert isinstance(Route.carrier, RelationshipExpr)
    assert isinstance(Carrier.routes, ManyRelationshipExpr)


def test_value_object_descriptors_answer_query_only_families() -> None:
    assert_type(Stop.city, ScalarExpr[Stop, str])
    assert_type(Stop.codes, ManyScalarExpr[Stop, str])
    assert_type(Leg.stops, ManyValueObjectExpr[Leg, Stop])
    assert_type(Stop.codes.element, ScalarElementExpr[Stop, str])
    assert not isinstance(Stop.city, AssignableScalarExpr)
    assert not hasattr(Stop.city, "set")


def test_relationships_are_include_paths_and_quantify_their_target() -> None:
    include: IncludePath[Carrier, Route] = Carrier.routes
    narrowed: IncludePath[Route, Carrier] = Route.carrier.narrow(Carrier)
    assert include is not None and narrowed is not None
    assert_type(Carrier.routes.any(Route.id > 1), Predicate[Any])
    assert_type(Route.carrier.exists(), Predicate[Any])


def test_collections_refuse_single_value_operations_statically() -> None:
    with pytest.raises(AttributeError):
        Route.tags.like("a")  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
    with pytest.raises(AttributeError):
        Route.legs.origin  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]  # noqa: B018
    with pytest.raises(AttributeError):
        Route.tags.asc()  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
    with pytest.raises(AttributeError):
        Stop.codes.element.is_null()  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]


def test_a_quantifier_reads_its_where_from_the_element_class() -> None:
    assert predicate_node(Route.legs.any(Leg.origin.city == "Oslo")) == predicate_node(
        Route.legs.any(Leg.origin.city == "Oslo")
    )
    Route.legs.any(Route.id == 1)  # pyright: ignore[reportArgumentType]


def test_a_relationship_narrow_continues_only_as_an_include_path() -> None:
    narrowed = Route.carrier.narrow(Carrier)
    assert_type(narrowed.name, IncludePath[Route, Any])
    assert type(narrowed.name) is IncludePath
    with pytest.raises(TypeError):
        _ = narrowed.name > 1  # pyright: ignore[reportOperatorIssue, reportUnknownVariableType]


@pytest.mark.parametrize("name", ["any", "all", "none", "element", "is_a", "exists", "like"])
def test_an_expression_operation_name_is_reserved_for_members(name: str) -> None:
    with pytest.raises(EntityDefinitionError) as caught:
        type(
            "Clash",
            (Entity,),
            {
                "__module__": __name__,
                "__annotations__": {"id": Attr[int], name: Attr[str]},
                "id": attr(primary_key=True),
            },
            table="ef_clash",
            namespace=_NS,
        )
    assert caught.value.code == "entity-reserved-member-name"


def test_a_renamed_member_keeps_its_canonical_name_behind_a_free_python_name() -> None:
    class Ticket(Entity, table="ef_ticket", namespace=_NS):
        id: Attr[int] = attr(primary_key=True)
        any_seat: Attr[str] = attr(name="any", max_length=8)

    assert predicate_node(Ticket.any_seat == "A1") == predicate_node(Ticket.any_seat == "A1")
    assert Ticket.any_seat is not None
