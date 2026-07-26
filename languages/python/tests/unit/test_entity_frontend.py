"""The Entity class frontend: the authoring grammar and what it compiles to.

This module omits ``from __future__ import annotations`` so the engine sees live
annotation objects; ``test_declaration_engine`` covers the stringized path and
``test_entity_definition_codes`` covers every rejection on both.
"""

import ast
import datetime as dt
import inspect
from decimal import Decimal

import pytest

from parallax.core import (
    MANY_TO_ONE,
    ONE_TO_MANY,
    ONE_TO_ONE,
    READ_ONLY,
    Attr,
    Bitemporal,
    Entity,
    EntityDefinitionError,
    Rel,
    TxTemporal,
    asc,
    attr,
    desc,
    index,
    rel,
)
from parallax.core.base import Decimal as NeutralDecimal
from parallax.core.base import Float32, Int32, Int64, String, Timestamp
from parallax.core.entity import (
    UNLOADED,
    AttributeExpr,
    Predicate,
    RelationshipPath,
    UnloadedRelationshipError,
    canonical_row,
    changed_fields,
    effective_change_set,
    full_row,
    primary_key_row,
    wire_names_of,
)
from parallax.core.entity import _declaration as engine
from parallax.core.entity import _entity as entity_module
from parallax.core.entity._errors import FrameworkOwnedAxisError, ModelCopyError, ProvenanceError
from parallax.core.metamodel import (
    APPLICATION_ASSIGNED,
    MAX,
    Column,
    EntityIdentity,
    ExactEntityReference,
    Max,
    PrimaryKey,
    RelativeEntityReference,
    Sequence,
    SortDirection,
    Table,
    TemporalDimension,
    UnresolvedDefiningRelationshipDeclaration,
    UnresolvedRelationshipOrder,
    UnresolvedReverseRelationshipDeclaration,
)
from parallax.core.op_algebra import Comparison, serialize

pytestmark = pytest.mark.unit


class Customer(Entity, table="customer", namespace="sales"):
    id: Attr[int] = attr(primary_key=True)
    tax_id: Attr[str] = attr(name="taxID")
    bin_no: Attr[str] = attr(column="BIN_NO")
    orders: Rel[tuple["Order", ...]] = rel(
        reverse_of="customer", order_by=("placed_at", desc("id"))
    )


class Coupon(Entity, table="coupon", namespace="sales"):
    id: Attr[int] = attr(primary_key=True)


class Order(
    Entity,
    table="orders",
    namespace="sales",
    indices=(index("order_customer", "customer_id"),),
):
    id: Attr[int] = attr(primary_key=True)
    placed_at: Attr[dt.datetime]
    qty: Attr[int] = attr(type=Int32)
    rating: Attr[float] = attr(type=Float32)
    amount: Attr[Decimal] = attr(precision=18, scale=2)
    version: Attr[int] = attr(optimistic_locking=True)
    customer_id: Attr[int]
    customer: Rel[Customer] = rel(cardinality=MANY_TO_ONE, join=("customer_id", "id"))
    coupon_id: Attr[int | None]
    coupon: Rel[Coupon | None] = rel(cardinality=MANY_TO_ONE, join=("coupon_id", "id"))


class Ticket(Entity, table="ticket"):
    id: Attr[int] = attr(
        primary_key=Sequence(name="ticket_seq", initial_value=1000, increment_size=5)
    )
    label: Attr[str] = attr(max_length=32, read_only=True)


class Widget(Entity, table="widget", name="WIDGET"):
    id: Attr[int] = attr(primary_key=MAX)
    label: Attr[str]


class Reading(TxTemporal, table="reading"):
    id: Attr[int] = attr(primary_key=True)
    celsius: Attr[float]


class Episode(Bitemporal, table="episode"):
    id: Attr[int] = attr(primary_key=True)


class Line(Entity, table="line"):
    id: Attr[int] = attr(primary_key=True)
    basket_id: Attr[int]


class Account(Entity, table="account"):
    id: Attr[int] = attr(primary_key=True)


def _order() -> Order:
    return Order(
        id=1,
        placed_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
        qty=2,
        rating=4.5,
        amount=Decimal("1.50"),
        version=1,
        customer_id=7,
    )


def test_the_entity_name_is_the_class_name_unless_the_header_overrides_it() -> None:
    assert Order.identity == EntityIdentity("sales", "Order")
    assert Widget.identity == EntityIdentity(None, "WIDGET")
    assert Order.container == Table("orders")


def test_persistence_is_declared_only_where_it_is_exceptional() -> None:
    class Archive(Entity, table="archive", persistence=READ_ONLY):
        id: Attr[int] = attr(primary_key=True)

    assert Order.persistence is None
    assert Archive.persistence is READ_ONLY


def test_the_scalar_families_narrow_only_through_the_type_option() -> None:
    by_name = {member.identity.name: member for member in Order.attributes}
    assert by_name["id"].type == Int64()
    assert by_name["qty"].type == Int32()
    assert by_name["rating"].type == Float32()
    assert by_name["amount"].type == NeutralDecimal(18, 2)
    assert by_name["placedAt"].type == Timestamp()
    assert Customer.attributes[1].type == String()


def test_name_overrides_the_canonical_member_and_column_overrides_its_storage() -> None:
    by_name = {member.identity.name: member for member in Customer.attributes}
    assert set(by_name) == {"id", "taxID", "binNo"}
    assert by_name["taxID"].storage == Column("taxID")
    assert by_name["binNo"].storage == Column("BIN_NO")


def test_the_primary_key_algebra_carries_its_generation_on_the_key_branch() -> None:
    assert Order.attributes[0].primary_key == PrimaryKey(APPLICATION_ASSIGNED)
    assert Widget.attributes[0].primary_key == PrimaryKey(MAX)
    assert Ticket.attributes[0].primary_key == PrimaryKey(
        Sequence(name="ticket_seq", batch_size=1, initial_value=1000, increment_size=5)
    )


def test_a_generation_is_spelled_as_its_value_and_never_as_its_type() -> None:
    with pytest.raises(EntityDefinitionError) as caught:
        attr(primary_key=Max)
    assert caught.value.code == "entity-option-invalid-value"


def test_the_remaining_attribute_options_reach_the_declaration() -> None:
    label = Ticket.attributes[1]
    assert label.max_length == 32
    assert label.read_only is True
    version = next(m for m in Order.attributes if m.identity.name == "version")
    assert version.optimistic_locking is True


def test_relationship_facts_split_between_the_annotation_and_the_factory() -> None:
    reverse = Customer.relationships[0]
    assert reverse.order_by == (
        UnresolvedRelationshipOrder("placedAt", SortDirection.ASCENDING),
        UnresolvedRelationshipOrder("id", SortDirection.DESCENDING),
    )
    defining = next(m for m in Order.relationships if m.identity.name == "customer")
    assert isinstance(defining, UnresolvedDefiningRelationshipDeclaration)
    assert defining.cardinality is MANY_TO_ONE
    assert defining.dependent is False
    assert defining.join.source.name == "customerId"


def test_a_class_object_target_is_exact_and_carries_the_targets_own_namespace() -> None:
    # The live twin of `test_declaration_engine`'s stringized case: only here is
    # the target a class object, so only here does the reference carry an
    # identity the annotation text never spelled.
    defining = next(m for m in Order.relationships if m.identity.name == "customer")
    assert isinstance(defining, UnresolvedDefiningRelationshipDeclaration)
    assert defining.join.target.entity == ExactEntityReference(Customer.identity)
    assert Customer.identity == EntityIdentity("sales", "Customer")

    reverse = Customer.relationships[0]
    assert isinstance(reverse, UnresolvedReverseRelationshipDeclaration)
    assert reverse.reverse_of.entity == RelativeEntityReference("Order")


def test_a_dependent_ordered_defining_relationship_records_both_facts() -> None:
    class Basket(Entity, table="basket"):
        id: Attr[int] = attr(primary_key=True)
        lines: Rel[tuple[Line, ...]] = rel(
            cardinality=ONE_TO_MANY,
            join=("id", "basket_id"),
            dependent=True,
            order_by=(asc("id"),),
            name="basketLines",
        )

    declaration = Basket.relationships[0]
    assert isinstance(declaration, UnresolvedDefiningRelationshipDeclaration)
    assert declaration.identity.name == "basketLines"
    assert declaration.dependent is True
    assert declaration.order_by[0].direction is SortDirection.ASCENDING


def test_a_one_to_one_join_names_members_by_their_python_spelling() -> None:
    class Profile(Entity, table="profile"):
        id: Attr[int] = attr(primary_key=True)
        account_id: Attr[int]
        account: Rel[Account] = rel(cardinality=ONE_TO_ONE, join=("account_id", "id"))

    declaration = Profile.relationships[0]
    assert isinstance(declaration, UnresolvedDefiningRelationshipDeclaration)
    assert declaration.join.source.name == "accountId"
    assert declaration.join.target.name == "id"


def test_indices_are_local_declaration_ordered_and_lowered_to_identities() -> None:
    (declared,) = Order.indices
    assert declared.identity.name == "order_customer"
    assert [component.name for component in declared.attributes] == ["customerId"]
    assert declared.unique is False


def test_class_level_member_access_seeds_operation_nodes() -> None:
    assert isinstance(Order.id, AttributeExpr)
    predicate = Order.id == 1
    assert isinstance(predicate, Predicate)
    assert isinstance(predicate.op, Comparison)
    assert serialize(predicate.op) == {"eq": {"attr": "Order.id", "value": 1}}
    path = Order.customer
    assert isinstance(path, RelationshipPath)
    assert path.target == "Customer"


def test_instance_access_returns_the_member_value_and_relationships_stay_closed_world() -> None:
    order = _order()
    assert order.qty == 2
    assert order.coupon_id is None
    object.__setattr__(order, "customer", UNLOADED)
    with pytest.raises(UnloadedRelationshipError):
        _ = order.customer


def test_a_temporal_shape_owner_receives_the_framework_members_and_axes() -> None:
    names = [member.identity.name for member in Reading.attributes]
    assert names == ["id", "celsius", "tx_start", "tx_end"]
    assert [member.storage.name for member in Reading.attributes[2:]] == ["in_z", "out_z"]
    assert len(Episode.as_of_axes) == 2
    assert Reading(id=1, celsius=1.5).tx_start is None


def test_the_type_checking_mirror_matches_the_engine_injection_table() -> None:
    # The `if TYPE_CHECKING:` blocks on TxTemporal/Bitemporal are the one
    # hand-maintained static duplicate of the engine's injection metadata; drift
    # would type-check a surface the engine never installs, or hide one it does.
    tree = ast.parse(inspect.getsource(entity_module))
    mirrors: dict[str, list[tuple[str, str]]] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name in ("TxTemporal", "Bitemporal")):
            continue
        for stmt in node.body:
            if not (
                isinstance(stmt, ast.If)
                and isinstance(stmt.test, ast.Name)
                and stmt.test.id == "TYPE_CHECKING"
            ):
                continue
            entries: list[tuple[str, str]] = []
            for decl in stmt.body:
                assert isinstance(decl, ast.AnnAssign), ast.dump(decl)
                assert isinstance(decl.target, ast.Name)
                entries.append((decl.target.id, ast.unparse(decl.annotation)))
            mirrors[node.name] = entries
    injection = engine._TEMPORAL_MEMBERS  # pyright: ignore[reportPrivateUsage]
    valid_time = TemporalDimension.VALID_TIME
    transaction_time = TemporalDimension.TRANSACTION_TIME
    expected = {
        "TxTemporal": [
            (py_name, "Attr[_dt.datetime]") for py_name, _ in injection[transaction_time]
        ],
        "Bitemporal": [
            (py_name, "Attr[_dt.datetime]")
            for dimension in (valid_time, transaction_time)
            for py_name, _ in injection[dimension]
        ],
    }
    assert mirrors == expected


def test_wire_names_expose_the_member_roles_the_write_path_needs() -> None:
    names = wire_names_of(Order)
    assert names.name_to_py["placedAt"] == "placed_at"
    assert names.column_to_py["BIN_NO" if "BIN_NO" in names.column_to_py else "id"] is not None
    assert names.pk_py == frozenset({"id"})
    assert names.framework_owned_py == frozenset({"version"})
    assert names.relationship_py == {"customer": "customer", "coupon": "coupon"}
    assert "id" not in names.assignable_py
    assert "version" not in names.assignable_py


def test_a_write_row_carries_only_the_members_the_caller_set() -> None:
    order = _order()
    row = full_row(order)
    assert row["id"] == 1
    assert row["qty"] == 2
    assert "couponId" not in row
    assert primary_key_row(order) == {"id": 1}
    assert canonical_row(order, {"qty": 3}) == {"qty": 3}


def test_setting_a_framework_stamped_axis_member_is_rejected_before_any_row_is_built() -> None:
    fresh = Reading(id=1, celsius=1.0, tx_start=dt.datetime(2026, 1, 1, tzinfo=dt.UTC))
    with pytest.raises(FrameworkOwnedAxisError, match="tx_start"):
        full_row(fresh)


def test_an_edited_copy_records_its_earliest_original_and_drops_a_net_zero_change() -> None:
    order = _order()
    assert changed_fields(order) is None
    with pytest.raises(ProvenanceError):
        effective_change_set(order)
    once = order.model_copy(update={"qty": 5})
    assert changed_fields(once) == {"qty": 2}
    assert effective_change_set(once) == {"qty": 5}
    back = once.model_copy(update={"qty": 2})
    assert effective_change_set(back) == {}


@pytest.mark.parametrize("member", ["id", "version", "customer", "nonesuch"])
def test_an_unassignable_copy_target_is_rejected(member: str) -> None:
    with pytest.raises(ModelCopyError):
        _order().model_copy(update={member: 1})


def test_every_entity_class_is_frozen_without_declaring_it() -> None:
    order = _order()
    with pytest.raises(ValueError, match="frozen"):
        order.qty = 3  # pyright: ignore[reportAttributeAccessIssue]
