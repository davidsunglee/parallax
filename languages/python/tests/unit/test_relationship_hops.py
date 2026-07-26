"""How a Relationship Path resolves the hop after its first (python.md §2).

The first hop is the relationship descriptor's own; every hop past it is a model
question the path answers through the Metamodel Binding it carries. These
fixtures pin the two authoring facts a bare canonical name loses — a ``name=``
override on the hop's own member, and a namespaced target whose bare name a
second namespace also carries.

This module omits ``from __future__ import annotations`` so a relationship target
spelled as a class object reaches the engine live, which is what lets one module
declare two Entities that share the canonical name ``Customer``.
"""

import pytest

from parallax.core import (
    MANY_TO_ONE,
    ONE_TO_MANY,
    Attr,
    Entity,
    MetamodelHub,
    Rel,
    attr,
    rel,
)
from parallax.core.op_algebra import DeepFetch, PathSegment

pytestmark = pytest.mark.unit


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


ORCHARD = MetamodelHub(Root, Branch, Leaf)


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


LEDGER = MetamodelHub(SalesOrder, SalesCustomer, SalesNote, CrmCustomer)


def test_a_deeper_hop_reads_the_python_member_off_the_bound_class() -> None:
    # `Branch.leaves` declares the canonical name `canopy`, so re-deriving a
    # canonical name from the Python spelling would miss the declaration.
    path = Root.branches.leaves
    assert [segment.rel for segment in path.segments] == ["Root.branches", "Branch.canopy"]


def test_a_deeper_hop_keeps_the_target_namespace() -> None:
    path = Root.branches.leaves
    assert path.target == "orchard.Leaf"


def test_a_deeper_hop_resolves_a_target_whose_bare_name_two_namespaces_share() -> None:
    # `crm.Customer` carries the same bare name as `sales.Customer`, so a bare
    # target name is ambiguous and resolves to neither.
    path = SalesOrder.customer.notes
    assert [segment.rel for segment in path.segments] == ["Order.customer", "Customer.notes"]
    assert path.target == "sales.Note"


def test_a_renamed_deeper_hop_validates_as_an_include_path() -> None:
    # The segments a hop builds are the wire's own, so the model accepts them:
    # `.include(...)` validates immediately, at statement build.
    statement = Root.where().include(Root.branches.leaves)
    operation = statement.operation()
    assert isinstance(operation, DeepFetch)
    assert operation.paths == (
        (PathSegment(rel="Root.branches"), PathSegment(rel="Branch.canopy")),
    )


def test_a_first_hop_target_is_the_canonical_entity_spelling() -> None:
    assert SalesOrder.customer.target == "sales.Customer"
    assert Root.branches.target == "orchard.Branch"


def test_a_hop_naming_no_relationship_of_the_target_is_refused() -> None:
    with pytest.raises(AttributeError, match="declares no relationship"):
        _ = Root.branches.missing  # pyright: ignore[reportAttributeAccessIssue]


def test_a_hop_naming_an_attribute_of_the_target_is_refused() -> None:
    # `root_id` is a declared member of the hop's target, but not a relationship.
    with pytest.raises(AttributeError, match="declares no relationship"):
        _ = Root.branches.root_id  # pyright: ignore[reportAttributeAccessIssue]


def test_a_hop_narrowed_to_one_class_targets_it_canonically() -> None:
    # The narrow list is the wire's own and names each class locally; the path's
    # target takes the exact spelling.
    path = Root.branches.narrow(Branch)
    assert path.segments[-1].narrow == ("Branch",)
    assert path.target == "orchard.Branch"


def test_a_hop_narrowed_to_a_class_declaring_no_identity_names_it_pythonically() -> None:
    # A narrow reads each class's declared identity structurally; a class
    # carrying none is named by its Python name, and the model refuses it where
    # the narrow is validated.
    class Bare:
        pass

    path = Root.branches.narrow(Bare)
    assert path.segments[-1].narrow == ("Bare",)
    assert path.target == "Bare"


def test_a_hop_past_a_narrow_to_a_class_outside_the_model_is_refused() -> None:
    # A narrow takes any class, so a path can be pointed at an Entity another
    # hub owns; continuing from there has no model to resolve in.
    with pytest.raises(AttributeError, match="is not an Entity Class of the model"):
        _ = Root.branches.narrow(SalesCustomer).notes  # pyright: ignore[reportAttributeAccessIssue]
