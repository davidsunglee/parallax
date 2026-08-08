"""How a Relationship Path continues past its first hop (python.md §2).

The first hop is the relationship descriptor's own and carries the declaration's
exact facts — its canonical member name and its target's namespaced spelling.
Every hop past it is composed rather than resolved: authoring reaches no model,
so the segment is spelled from the path's target and the member's own name, and
the model states the whole rule at execution preflight.

These fixtures pin both halves — what a composed hop spells, and what preflight
does with it — including the two authoring facts that erase in consequence: a
member its declaration renames, and one an ancestor declares rather than the
target itself. Both are refused rather than accepted wrongly.

This module omits ``from __future__ import annotations`` so a relationship target
spelled as a class object reaches the engine live, which is what lets one module
declare two Entities that share the canonical name ``Customer``.
"""

from typing import Any

import pytest

from _support.query_probes import lowered_operation
from parallax.core import (
    MANY_TO_ONE,
    ONE_TO_MANY,
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    DomainModel,
    Entity,
    QueryDefinitionError,
    Rel,
    TablePerHierarchy,
    attr,
    rel,
)
from parallax.core.entity import RelationshipPath, RelationshipRef
from parallax.core.entity._model import model_of
from parallax.core.op_algebra import DeepFetch, NavigationPath, PathSegment, validate_operation


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
    models: DomainModel, root: type[Entity], path: RelationshipPath[Any, Any]
) -> DeepFetch:
    """Build the include operation ``path`` authors and validate it as a read does."""
    operation = lowered_operation(root.where(root.all).include(path))
    assert isinstance(operation, DeepFetch)
    validate_operation(models.meta(root), operation, model_of(models))
    return operation


def test_a_deeper_hop_spells_its_owner_from_the_paths_target() -> None:
    # The owner is the hop target's own canonical Entity spelling, and the member
    # is the canonical name its Python spelling denotes.
    path = SalesOrder.customer.notes
    assert [segment.rel for segment in path.segments] == [
        "sales.Order.customer",
        "sales.Customer.notes",
    ]


def test_a_deeper_hop_camel_cases_a_snake_case_member_spelling() -> None:
    assert Owner.dogs.some_member.segments[-1].rel == "Dog.someMember"


def test_a_deeper_hop_validates_as_an_include_path() -> None:
    operation = _preflight(LEDGER, SalesOrder, SalesOrder.customer.notes)
    assert operation.paths == (
        NavigationPath(
            segments=(
                PathSegment(rel="sales.Order.customer"),
                PathSegment(rel="sales.Customer.notes"),
            )
        ),
    )


def test_a_deeper_hop_across_namespaces_names_the_target_it_was_composed_from() -> None:
    # The hop is spelled from the path's own target, exactly, so a second
    # namespace declaring the local name `Customer` does not reach it: the same
    # operation validates against both models and addresses `sales.Customer`
    # either way. A bare owner would have named two Entities and therefore none.
    operation = _preflight(LEDGER, SalesOrder, SalesOrder.customer.notes)
    validate_operation(
        TWO_NAMESPACE_LEDGER.meta(SalesOrder), operation, model_of(TWO_NAMESPACE_LEDGER)
    )


def test_a_renamed_deeper_member_erases_and_preflight_refuses_it() -> None:
    # `Branch.leaves` declares the canonical name `canopy`. A composed hop has no
    # declaration to read, so it spells `Branch.leaves` — which the model refuses
    # rather than silently fetching the wrong relationship. Reaching the member
    # through a path rooted at the Entity that declares it keeps the exact name.
    with pytest.raises(ValueError, match="names no declared relationship on Branch"):
        _preflight(ORCHARD, Root, Root.branches.leaves)
    assert Branch.leaves.segments == (PathSegment(rel="orchard.Branch.canopy"),)


def test_an_inherited_deeper_member_erases_and_preflight_refuses_it() -> None:
    # `Dog` declares no relationship of its own; `toys` is its family's, declared
    # on `Animal` under the canonical name `playthings`. A composed hop names
    # neither the declaring Entity nor that name.
    with pytest.raises(ValueError, match="names no declared relationship on Dog"):
        _preflight(PETS, Owner, Owner.dogs.toys)


def test_a_hop_naming_no_relationship_of_the_target_is_refused_at_preflight() -> None:
    with pytest.raises(ValueError, match="names no declared relationship on Customer"):
        _preflight(LEDGER, SalesOrder, SalesOrder.customer.missing)


def test_a_hop_naming_an_attribute_of_the_target_is_refused_at_preflight() -> None:
    # `customerId` is a declared member of the hop's target, but not a relationship.
    with pytest.raises(ValueError, match="names no declared relationship on Customer"):
        _preflight(LEDGER, SalesOrder, SalesOrder.customer.customer_id)


def test_a_first_hop_target_is_the_canonical_entity_spelling() -> None:
    assert SalesOrder.customer.target == "sales.Customer"
    assert Root.branches.target == "orchard.Branch"


def test_a_first_hop_reference_names_its_owner_exactly_and_its_declared_member() -> None:
    # The reference splits the first segment the way the wire spells it: the
    # owner's canonical Entity spelling, and the relationship's own declared
    # name rather than the Python member it was authored as.
    assert Root.branches.ref == RelationshipRef("orchard.Root", "branches")
    assert Branch.leaves.ref == RelationshipRef("orchard.Branch", "canopy")
    assert SalesOrder.customer.ref == RelationshipRef("sales.Order", "customer")


def test_a_hop_narrowed_to_one_class_targets_it_canonically() -> None:
    # A narrow list is a reference position like any other, so it names each
    # class exactly — the same spelling the path's own target takes.
    path = Root.branches.narrow(Branch)
    assert path.segments[-1].narrow == ("orchard.Branch",)
    assert path.target == "orchard.Branch"


def test_a_hop_narrowed_to_a_class_declaring_no_identity_names_it_pythonically() -> None:
    # A narrow reads each class's declared identity structurally; a class
    # carrying none is named by its Python name, and the model refuses it where
    # the narrow is validated. The hop's own target bounds what it may narrow
    # to, so a class outside it is refused statically as well — the suppression
    # is what lets this probe reach the runtime spelling behind that rule.
    class Bare:
        pass

    path = Root.branches.narrow(Bare)  # pyright: ignore[reportArgumentType]
    assert path.segments[-1].narrow == ("Bare",)
    assert path.target == "Bare"


def test_a_hop_narrow_to_no_subtype_is_refused_rather_than_erased() -> None:
    # A segment spells "no narrow" as an empty alternative list, so a narrow to
    # nothing would answer a path byte-identical to the broad one — the request
    # would disappear and the deep fetch would mark the broad relationship
    # loaded. The sibling narrowing forms lower to a `narrow` node the model
    # refuses as `narrow-empty-effective-set`; this one lowers to no node, so the
    # arity is its own rule (`python.md` "Every Python narrowing form requires at
    # least one subtype alternative").
    with pytest.raises(QueryDefinitionError, match="at least one subtype") as caught:
        Root.branches.narrow()
    assert caught.value.code == "query-path-invalid"


def test_a_second_narrow_on_one_hop_is_refused_rather_than_replacing_the_first() -> None:
    # Narrowing is single-shot per segment: a segment carries one alternative
    # list, so a second narrow on the same hop could only intersect or replace
    # the first, and either silently answers something neither call asked for.
    # The receiver's own target is all its parameter states, so nothing about the
    # first narrow is typed and this is the whole rule.
    with pytest.raises(QueryDefinitionError, match="single-shot") as caught:
        Root.branches.narrow(Branch).narrow(Branch)
    assert caught.value.code == "query-path-invalid"


def test_a_deeper_hop_narrows_independently_of_the_hop_it_continued() -> None:
    # Single-shot is per segment rather than per path: continuing to another
    # relationship starts a fresh alternative list, and the hop it continued
    # keeps the one it was given.
    path = Root.branches.narrow(Branch).leaves.narrow(Leaf)
    assert [(segment.rel, segment.narrow) for segment in path.segments] == [
        ("orchard.Root.branches", ("orchard.Branch",)),
        ("orchard.Branch.leaves", ("orchard.Leaf",)),
    ]


def test_a_path_that_already_continued_cannot_continue_again() -> None:
    # What a composed hop points at is a declaration fact of an Entity this path
    # reaches no class for, so a third hop has no owner to spell itself from.
    continued = SalesOrder.customer.notes
    assert continued.target is None
    with pytest.raises(AttributeError, match="already continued past the hop"):
        _ = continued.deeper


def test_a_directly_built_path_carries_no_target_and_cannot_continue() -> None:
    built: RelationshipPath[SalesOrder, Any] = RelationshipPath(
        segments=(PathSegment(rel="sales.Order.customer"),), target=None
    )
    with pytest.raises(AttributeError, match="already continued past the hop"):
        _ = built.notes
