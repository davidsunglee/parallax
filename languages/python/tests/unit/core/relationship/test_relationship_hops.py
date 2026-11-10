"""How a Relationship Path continues past its first hop (`queries-and-results.md`).

The first hop is the relationship descriptor's own and carries the declaration's
exact identity. Every hop past it keeps the Python member name it was written
with, because authoring reaches no model: the serving model's classes spell the
segment when an operation binds the path, and the model states the whole rule
there.

These fixtures pin what binding spells from an authored path, including the two
facts only a declaration knows: a member its declaration renames, and one an
ancestor declares rather than the target itself.

This module omits ``from __future__ import annotations`` so a relationship target
spelled as a class object reaches the engine live, which is what lets one module
declare two Entities that share the canonical name ``Customer``.
"""

from typing import Any

from parallax.core import (
    MANY_TO_ONE,
    ONE_TO_MANY,
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    DomainModel,
    Entity,
    Rel,
    TablePerHierarchy,
    attr,
    rel,
)
from parallax.core.base import UsageError
from parallax.core.entity import IncludePath
from parallax.core.entity._expressions import authored_include_path
from parallax.core.entity._model import model_of
from parallax.core.object_query import validate_object_query
from parallax.core.object_query._nodes import IncludePathNode
from tests._support.errors import raises_code
from tests._support.query_probes import canonical_query
from tests.unit import _deep_include_support as deep


class Leaf(Entity, table="leaf", namespace="orchard"):
    id: Attr[int] = attr(primary_key=True)
    branch_id: Attr[int]


class Branch(Entity, table="branch", namespace="orchard"):
    id: Attr[int] = attr(primary_key=True)
    root_id: Attr[int]
    leaves: Rel[tuple[Leaf, ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "branch_id"), name="canopy"
    )


class Root(Entity, table="root", namespace="orchard"):
    id: Attr[int] = attr(primary_key=True)
    branches: Rel[tuple[Branch, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "root_id"))


ORCHARD = DomainModel(Root, Branch, Leaf)


class SalesNote(Entity, table="sales_note", name="Note", namespace="sales"):
    id: Attr[int] = attr(primary_key=True)
    customer_id: Attr[int]


class SalesCustomer(Entity, table="sales_customer", name="Customer", namespace="sales"):
    id: Attr[int] = attr(primary_key=True)
    notes: Rel[tuple[SalesNote, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "customer_id"))


class CrmCustomer(Entity, table="crm_customer", name="Customer", namespace="crm"):
    id: Attr[int] = attr(primary_key=True)


class SalesOrder(Entity, table="sales_order", name="Order", namespace="sales"):
    id: Attr[int] = attr(primary_key=True)
    customer_id: Attr[int]
    customer: Rel[SalesCustomer] = rel(cardinality=MANY_TO_ONE, join=("customer_id", "id"))


LEDGER = DomainModel(SalesOrder, SalesCustomer, SalesNote)
TWO_NAMESPACE_LEDGER = DomainModel(SalesOrder, SalesCustomer, SalesNote, CrmCustomer)


class Toy(Entity, table="toy", namespace="pets"):
    id: Attr[int] = attr(primary_key=True)
    animal_id: Attr[int]


class Animal(
    Entity,
    table="animal",
    namespace="pets",
    inheritance=AbstractRoot(TablePerHierarchy("kind")),
):
    id: Attr[int] = attr(primary_key=True)
    owner_id: Attr[int]
    toys: Rel[tuple[Toy, ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "animal_id"), name="playthings"
    )


class Dog(Animal, inheritance=ConcreteSubtype("dog")):
    pass


class Owner(Entity, table="owner", namespace="pets"):
    id: Attr[int] = attr(primary_key=True)
    dogs: Rel[tuple[Dog, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "owner_id"))


PETS = DomainModel(Owner, Animal, Dog, Toy)


def _preflight(
    models: DomainModel, root: type[Entity], path: IncludePath[Any, Any]
) -> tuple[IncludePathNode, ...]:
    """Build the Includes clause ``path`` authors and validate it as a read does."""
    query = canonical_query(root.where(root.all).include(path), models)
    accepted = model_of(models)
    target = accepted.entity(models.entity(root).identity)
    assert target is not None
    validate_object_query(target, query, accepted)
    return query.includes


def _spelled(node: IncludePathNode) -> list[tuple[str, tuple[str, ...]]]:
    return [(segment.rel, segment.narrow_to) for segment in node.segments]


def test_a_deeper_hop_across_namespaces_names_the_target_its_model_resolved() -> None:
    # The hop is spelled from the identity the reached class declares, so a second
    # namespace declaring the local name `Customer` does not reach it: the same
    # query binds against both models and addresses `sales.Customer` either way.
    for model in (LEDGER, TWO_NAMESPACE_LEDGER):
        (node,) = _preflight(model, SalesOrder, SalesOrder.customer.notes)
        assert _spelled(node)[-1] == ("sales.Customer.notes", ())


def test_a_renamed_deeper_member_spells_its_declared_name() -> None:
    # `Branch.leaves` declares the canonical name `canopy`.
    (node,) = _preflight(ORCHARD, Root, Root.branches.leaves)
    assert _spelled(node) == [("orchard.Root.branches", ()), ("orchard.Branch.canopy", ())]


def test_an_inherited_deeper_member_spells_its_declaring_ancestor() -> None:
    # `Dog` declares no relationship of its own; `toys` is its family's, declared
    # on `Animal` under the canonical name `playthings`.
    (node,) = _preflight(PETS, Owner, Owner.dogs.toys)
    assert _spelled(node) == [("pets.Owner.dogs", ()), ("pets.Animal.playthings", ())]


def test_a_hop_naming_an_attribute_of_the_target_is_refused_at_binding() -> None:
    # `id` is a declared member of the hop's target, but not a relationship.
    with raises_code(UsageError, "query-path-invalid", match="SalesCustomer declares no"):
        _preflight(LEDGER, SalesOrder, SalesOrder.customer.id)


def test_a_first_hop_reference_names_its_owner_exactly_and_its_declared_member() -> None:
    # The reference splits the first segment the way the wire spells it: the
    # owner's canonical Entity spelling, and the relationship's own declared
    # name rather than the Python member it was authored as.
    assert authored_include_path(Root.branches).described() == "orchard.Root.branches"
    assert authored_include_path(Branch.leaves).described() == "orchard.Branch.canopy"
    assert authored_include_path(SalesOrder.customer).described() == "sales.Order.customer"


def test_a_hop_narrowed_to_a_class_declaring_no_identity_names_it_pythonically() -> None:
    # A narrow reads each class's declared identity structurally; a class
    # carrying none is named by its Python name, and the model refuses it where
    # the narrow is validated. The hop's own target bounds what it may narrow
    # to, so a class outside it is refused statically as well — the suppression
    # is what lets this probe reach the runtime spelling behind that rule.
    class Bare:
        pass

    path = authored_include_path(Root.branches.narrow(Bare))  # pyright: ignore[reportArgumentType]
    assert path.segments[-1].narrow_to == ("Bare",)


def test_a_hop_narrow_to_no_subtype_is_refused_rather_than_erased() -> None:
    # A segment spells "no narrow" as an empty alternative list, so a narrow to
    # nothing would answer a path byte-identical to the broad one — the request
    # would disappear and the deep fetch would mark the broad relationship
    # loaded. The sibling narrowing forms lower to a `narrow` node the model
    # refuses as `narrow-empty-effective-set`; this one lowers to no node, so the
    # arity is its own rule: every Python narrowing form requires at least one
    # subtype alternative.
    with raises_code(UsageError, "query-path-invalid", match="at least one subtype"):
        Root.branches.narrow()


def test_a_second_narrow_on_one_hop_is_refused_rather_than_replacing_the_first() -> None:
    # Narrowing is single-shot per segment: a segment carries one alternative
    # list, so a second narrow on the same hop could only intersect or replace
    # the first, and either silently answers something neither call asked for.
    # The receiver's own target is all its parameter states, so nothing about the
    # first narrow is typed and this is the whole rule.
    with raises_code(UsageError, "query-path-invalid", match="single-shot"):
        Root.branches.narrow(Branch).narrow(Branch)


def test_a_deeper_hop_narrows_independently_of_the_hop_it_continued() -> None:
    # Single-shot is per segment rather than per path: continuing to another
    # relationship starts a fresh alternative list, and the hop it continued
    # keeps the one it was given.
    (node,) = _preflight(ORCHARD, Root, Root.branches.narrow(Branch).leaves.narrow(Leaf))
    assert _spelled(node) == [
        ("orchard.Root.branches", ("orchard.Branch",)),
        ("orchard.Branch.canopy", ("orchard.Leaf",)),
    ]


def _bound(path: IncludePath[Any, Any]) -> list[tuple[str, tuple[str, ...]]]:
    (node,) = _preflight(deep.FAMILY, deep.Keeper, path)
    return _spelled(node)


_ANIMALS = (f"{deep.FAMILY_NS}.Keeper.animals", ())
_NARROWED_TO_DOG = (f"{deep.FAMILY_NS}.Keeper.animals", (f"{deep.FAMILY_NS}.Dog",))


def test_a_continuation_reaches_a_target_its_declaration_named_forward() -> None:
    # `Animal.keeper` names `Keeper` before that class exists; the identity and
    # its target were settled when the model formed, so binding reads neither
    # the annotation nor the import order.
    assert _bound(deep.Keeper.animals.keeper) == [
        _ANIMALS,
        (f"{deep.FAMILY_NS}.Animal.keeper", ()),
    ]


def test_a_narrow_at_an_intermediate_hop_reads_the_subtypes_own_relationship() -> None:
    assert _bound(deep.Keeper.animals.narrow(deep.Dog).gear) == [
        _NARROWED_TO_DOG,
        (f"{deep.FAMILY_NS}.Dog.gear", ()),
    ]


def test_a_continuation_past_a_narrow_spells_the_declaring_ancestor_not_the_subtype() -> None:
    assert _bound(deep.Keeper.animals.narrow(deep.Dog).toys.maker) == [
        _NARROWED_TO_DOG,
        (f"{deep.FAMILY_NS}.Animal.playthings", ()),
        (f"{deep.FAMILY_NS}.Toy.maker", ()),
    ]


def test_a_narrow_to_several_subtypes_continues_through_what_the_hop_points_at() -> None:
    both = deep.Keeper.animals.narrow(deep.Dog, deep.Cat)
    assert _bound(both.toys)[-1] == (f"{deep.FAMILY_NS}.Animal.playthings", ())
    # No single subtype is reached, so a subtype's own member answers nothing,
    # even one both alternatives happen to declare under one Python name.
    with raises_code(UsageError, "query-path-invalid", match="Animal declares no relationship"):
        _bound(both.gear)


def test_a_subtypes_relationship_is_unreachable_past_the_broad_hop() -> None:
    with raises_code(UsageError, "query-path-invalid", match="Animal declares no relationship"):
        _bound(deep.Keeper.animals.gear)


def test_a_narrow_outside_the_hops_target_keeps_its_portable_refusal_when_continued() -> None:
    # The continuation binds through the class the narrow names, and the rule the
    # narrow breaks stays the validator's.
    with raises_code(UsageError, "narrow-outside-relationship-target"):
        _bound(deep.Keeper.animals.narrow(deep.Toy).maker)  # pyright: ignore[reportArgumentType]
