"""The Entity class frontend: the authoring grammar and what it compiles to.

This module omits ``from __future__ import annotations`` so the engine sees live
annotation objects; ``test_declaration_engine`` covers the stringized path and
``test_entity_definition_codes`` covers every rejection on both.
"""

import ast
import datetime as dt
import inspect
import sys
from collections.abc import Callable
from decimal import Decimal

import pytest
from pydantic import ValidationError

from parallax.core import (
    MANY_TO_ONE,
    ONE_TO_MANY,
    ONE_TO_ONE,
    READ_ONLY,
    Attr,
    Bitemporal,
    ConcreteSubtype,
    Document,
    Entity,
    EntityDefinitionError,
    QueryDefinitionError,
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
)
from parallax.core.entity import _declaration as engine
from parallax.core.entity import _entity as entity_module
from parallax.core.entity._entity import CHANGE_RECORD_SLOT, wire_names_of
from parallax.core.entity._errors import EditError
from parallax.core.entity._query import lower_find_query
from parallax.core.metamodel import (
    APPLICATION_ASSIGNED,
    MAX,
    Column,
    EntityIdentity,
    ExactEntityReference,
    Max,
    NullPlacement,
    PrimaryKey,
    RelativeEntityReference,
    Sequence,
    SortDirection,
    Table,
    UnresolvedDefiningRelationshipDeclaration,
    UnresolvedRelationshipOrder,
    UnresolvedReverseRelationshipDeclaration,
    derive_temporal_structure,
)
from parallax.core.metamodel import Document as AcceptedDocument
from parallax.core.predicate import Comparison, PathSegment, serialize


class Customer(Entity, table="customer", namespace="sales"):
    id: Attr[int] = attr(primary_key=True)
    tax_id: Attr[str] = attr(name="taxID", column="tax_id")
    legacy_id: Attr[str] = attr(name="legacyID")
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


def test_the_storage_layout_is_declared_only_where_it_is_exceptional() -> None:
    class Bare(Entity, table="bare", layout=Document):
        id: Attr[int] = attr(primary_key=True)

    class Empty(Entity, table="empty", layout=Document()):
        id: Attr[int] = attr(primary_key=True)

    class Named(Entity, table="named", layout=Document(column="body")):
        id: Attr[int] = attr(primary_key=True)

    assert Order.layout is None
    assert Bare.layout == AcceptedDocument(Column("payload"))
    assert Empty.layout == Bare.layout
    assert Named.layout == AcceptedDocument(Column("body"))


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
    assert set(by_name) == {"id", "taxID", "legacyID", "binNo"}
    assert by_name["taxID"].storage == Column("tax_id")
    assert by_name["legacyID"].storage == Column("legacy_i_d")
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


@pytest.mark.parametrize(
    ("call", "code", "message"),
    [
        (
            lambda: ConcreteSubtype(""),
            "entity-option-invalid-value",
            "a concrete-subtype tag value is either absent or nonempty",
        ),
        (
            lambda: attr(column=""),
            "entity-option-invalid-value",
            "column= takes a nonempty string, got ''",
        ),
        (
            lambda: attr(type=str),
            "entity-option-invalid-value",
            "type= takes Int32 or Float32, got <class 'str'>",
        ),
        (
            lambda: attr(precision=-1, scale=0),
            "entity-option-invalid-value",
            "precision= takes a non-negative integer, got -1",
        ),
        (
            lambda: attr(read_only=1),  # pyright: ignore[reportArgumentType] - deliberate bad type
            "entity-option-invalid-value",
            "read_only= takes a bool, got 1",
        ),
        (
            lambda: asc(""),
            "entity-option-invalid-value",
            "asc() takes a nonempty member name, got ''",
        ),
        (
            lambda: rel(cardinality="MANY_TO_ONE", join=("customer_id", "id")),  # pyright: ignore[reportArgumentType] - deliberate bad type
            "entity-option-invalid-value",
            "cardinality= takes ONE_TO_ONE, MANY_TO_ONE, or ONE_TO_MANY, got 'MANY_TO_ONE'",
        ),
        (
            lambda: rel(cardinality=MANY_TO_ONE, join=("customer_id",)),  # pyright: ignore[reportArgumentType] - deliberate bad shape
            "entity-option-invalid-value",
            "join= takes a (source_member, target_member) pair, got ('customer_id',)",
        ),
        (
            lambda: attr(precision=4),
            "entity-option-context-invalid",
            "precision= and scale= are declared together or not at all",
        ),
    ],
    ids=[
        "blank-tag-value",
        "blank-column",
        "unnarrowable-type",
        "negative-precision",
        "non-bool-flag",
        "blank-order-term",
        "unspellable-cardinality",
        "one-sided-join",
        "half-declared-decimal",
    ],
)
def test_an_intrinsically_invalid_factory_argument_is_refused_at_the_call(
    call: Callable[[], object], code: str, message: str
) -> None:
    # A factory validates its own arguments, so a malformed option never reaches
    # class creation and the rejection points at the call the developer wrote.
    with pytest.raises(EntityDefinitionError) as caught:
        call()
    assert caught.value.code == code
    assert caught.value.message == message


def _blank_table() -> type:
    """A ``table=`` present but empty, which no container name can be."""

    class BlankTable(Entity, table=""):
        id: Attr[int] = attr(primary_key=True)

    return BlankTable


def _unspellable_persistence() -> type:
    """A ``persistence=`` outside the Persistence Mode algebra."""

    class LooseMode(Entity, table="loose_mode", persistence="READ_ONLY"):
        id: Attr[int] = attr(primary_key=True)

    return LooseMode


def _unspellable_layout() -> type:
    """A ``layout=`` outside the Storage Layout algebra."""

    class LooseLayout(Entity, table="loose_layout", layout="document"):
        id: Attr[int] = attr(primary_key=True)

    return LooseLayout


def _blank_structured_column() -> type:
    """A ``Document(column=)`` present but empty, which no Column can be."""

    class BlankColumn(Entity, table="blank_column", layout=Document(column="")):
        id: Attr[int] = attr(primary_key=True)

    return BlankColumn


def _blank_namespace() -> type:
    """A ``namespace=`` present but empty, which no namespace can be."""

    class BlankNamespace(Entity, table="blank_namespace", namespace=""):
        id: Attr[int] = attr(primary_key=True)

    return BlankNamespace


def _decimal_scale_past_its_precision() -> type:
    """Decimal parameters the Neutral Type itself refuses."""

    class WideScale(Entity, table="wide_scale"):
        id: Attr[int] = attr(primary_key=True)
        amount: Attr[Decimal] = attr(precision=2, scale=5)

    return WideScale


def _decimal_parameters_on_a_non_decimal() -> type:
    """``precision=``/``scale=`` where the annotation names no decimal."""

    class CountedPrecision(Entity, table="counted_precision"):
        id: Attr[int] = attr(primary_key=True)
        qty: Attr[int] = attr(precision=4, scale=2)

    return CountedPrecision


def _bounded_length_on_a_non_text_member() -> type:
    """A maximum length on a member with no text width to bound."""

    class BoundedCount(Entity, table="bounded_count"):
        id: Attr[int] = attr(primary_key=True)
        qty: Attr[int] = attr(max_length=8)

    return BoundedCount


def _relationship_target_that_is_not_an_entity() -> type:
    """A live ``Rel[T]`` inner type that is no Entity Class."""

    class ScalarTarget(Entity, table="scalar_target"):
        id: Attr[int] = attr(primary_key=True)
        peer_id: Attr[int]
        peer: Rel[int] = rel(cardinality=MANY_TO_ONE, join=("peer_id", "id"))

    return ScalarTarget


@pytest.mark.parametrize(
    ("declare", "code", "message"),
    [
        (
            _blank_table,
            "entity-header-invalid-value",
            "BlankTable: table= takes a nonempty string, got ''",
        ),
        (
            _unspellable_persistence,
            "entity-header-invalid-value",
            "LooseMode: persistence= takes READ_ONLY, got 'READ_ONLY'",
        ),
        (
            _unspellable_layout,
            "entity-header-invalid-value",
            "LooseLayout: layout= takes Document or Document(column=...), got 'document'",
        ),
        (
            _blank_structured_column,
            "entity-header-invalid-value",
            "BlankColumn: Document(column=) takes a nonempty string, got ''",
        ),
        (
            _blank_namespace,
            "entity-header-invalid-value",
            "BlankNamespace: namespace= takes a nonempty string, got ''",
        ),
        (
            _decimal_scale_past_its_precision,
            "entity-option-invalid-value",
            "WideScale.amount: decimal scale must be between 0 and the precision 2, got 5",
        ),
        (
            _decimal_parameters_on_a_non_decimal,
            "entity-option-context-invalid",
            "CountedPrecision.qty: precision= and scale= apply only to a decimal member",
        ),
        (
            _bounded_length_on_a_non_text_member,
            "entity-option-context-invalid",
            "BoundedCount.qty: only a String Attribute bounds its length, not Int64()",
        ),
        (
            _relationship_target_that_is_not_an_entity,
            "entity-annotation-invalid",
            "ScalarTarget.peer: a relationship target is an Entity Class or its name",
        ),
    ],
    ids=[
        "blank-table",
        "unspellable-persistence",
        "unspellable-layout",
        "blank-structured-column",
        "blank-namespace",
        "decimal-scale-past-precision",
        "decimal-parameters-without-a-decimal",
        "bounded-length-without-text",
        "non-entity-relationship-target",
    ],
)
def test_an_option_the_declaration_context_refuses_names_the_member_it_came_from(
    declare: Callable[[], type], code: str, message: str
) -> None:
    # These rules need the whole declaration rather than the factory call alone:
    # the header's own values, the annotation an option is read against, and the
    # value layer's refusals reclassified as declaration-context defects.
    with pytest.raises(EntityDefinitionError) as caught:
        declare()
    assert caught.value.code == code
    assert caught.value.message == message


def test_the_remaining_attribute_options_reach_the_declaration() -> None:
    label = Ticket.attributes[1]
    assert label.max_length == 32
    assert label.read_only is True
    version = next(m for m in Order.attributes if m.identity.name == "version")
    assert version.optimistic_locking is True


def test_the_three_designations_stay_distinct_on_the_declaration() -> None:
    # A rejection can say WHICH of the three it is only while the declaration
    # keeps them apart: the version names a role AND is framework-owned, a
    # read-only member is authored once by the caller, and neither implies the
    # other.
    version = next(m for m in Order.attributes if m.identity.name == "version")
    assert (version.optimistic_locking, version.framework_owned, version.read_only) == (
        True,
        True,
        False,
    )
    label = Ticket.attributes[1]
    assert (label.optimistic_locking, label.framework_owned, label.read_only) == (
        False,
        False,
        True,
    )


def test_a_temporal_endpoint_is_framework_owned_without_naming_a_role() -> None:
    # The other designated category. The endpoint carries neither of the two
    # authored flags — its designation comes from the Entity's As-Of Axis, which
    # the shared derivation reads and an Attribute alone cannot.
    tx_start = next(m for m in Reading.attributes if m.identity.name == "txStart")
    assert tx_start.framework_owned is True
    assert (tx_start.optimistic_locking, tx_start.read_only) == (False, False)


def test_an_ordinary_attribute_carries_no_designation() -> None:
    qty = next(m for m in Order.attributes if m.identity.name == "qty")
    assert (qty.optimistic_locking, qty.framework_owned, qty.read_only) == (False, False, False)


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


def test_only_an_explicit_direction_term_can_choose_a_null_placement() -> None:
    class Basket(Entity, table="basket"):
        id: Attr[int] = attr(primary_key=True)
        lines: Rel[tuple[Line, ...]] = rel(
            cardinality=ONE_TO_MANY,
            join=("id", "basket_id"),
            order_by=("id", asc("id").nulls_first(), desc("id").nulls_last()),
        )

    bare, placed_asc, placed_desc = Basket.relationships[0].order_by
    assert bare.nulls is NullPlacement.NULLS_LAST
    assert placed_asc == UnresolvedRelationshipOrder(
        "id", SortDirection.ASCENDING, NullPlacement.NULLS_FIRST
    )
    assert placed_desc == UnresolvedRelationshipOrder(
        "id", SortDirection.DESCENDING, NullPlacement.NULLS_LAST
    )


def test_a_null_placement_is_single_shot_on_an_ordering_term() -> None:
    # A declaration term is not a query construct, so its rejection stays a plain
    # ValueError rather than joining the query-definition family an operation Sort
    # Key's identical single-shot rule raises.
    with pytest.raises(ValueError, match="single-shot") as caught:
        desc("id").nulls_first().nulls_last()
    assert type(caught.value) is ValueError
    assert not isinstance(caught.value, QueryDefinitionError)


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
    derived, declared = Order.indices
    assert derived.identity.name == "orders_pk"
    assert [component.name for component in derived.attributes] == ["id"]
    assert derived.unique is True
    assert declared.identity.name == "order_customer"
    assert [component.name for component in declared.attributes] == ["customerId"]
    assert declared.unique is False


def test_class_level_member_access_seeds_operation_nodes() -> None:
    assert isinstance(Order.id, AttributeExpr)
    predicate = Order.id == 1
    assert isinstance(predicate, Predicate)
    assert isinstance(predicate.node, Comparison)
    assert serialize(predicate.node) == {"eq": {"attr": "sales.Order.id", "value": 1}}
    path = Order.customer
    assert isinstance(path, RelationshipPath)
    # A relationship reference names its owner locally, as the wire does; the
    # path's own target keeps the namespace a continuing hop resolves in.
    assert path.segments == (PathSegment(rel="sales.Order.customer"),)
    assert path.target == "sales.Customer"


def test_a_query_over_a_class_no_model_composed_still_builds() -> None:
    # Query authoring reaches no model, so composition is not a precondition of
    # it: every class in this module belongs to no DomainModel, and a query over
    # one is an ordinary query. Whether the queried Entity is declared is the
    # connected model's question, answered at execution preflight.
    lowered = lower_find_query(Order.where(Order.id == 1))
    assert lowered.target == Order.identity
    assert serialize(lowered.operation) == {"eq": {"attr": "sales.Order.id", "value": 1}}


def test_instance_access_returns_the_member_value_and_relationships_stay_closed_world() -> None:
    order = _order()
    assert order.qty == 2
    assert order.coupon_id is None
    object.__setattr__(order, "customer", UNLOADED)
    with pytest.raises(UnloadedRelationshipError):
        _ = order.customer


def test_a_temporal_shape_owner_receives_the_framework_members_and_axes() -> None:
    names = [member.identity.name for member in Reading.attributes]
    assert names == ["id", "celsius", "txStart", "txEnd"]
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
    injected = {
        profile: [
            (
                engine._python_spelling(endpoint.name),  # pyright: ignore[reportPrivateUsage] - reads an engine internal
                "Attr[_dt.datetime]",
            )
            for axis in derive_temporal_structure(profile)
            for endpoint in (axis.start, axis.end)
        ]
        for profile in ("transaction-time", "bitemporal")
    }
    assert mirrors == {
        "TxTemporal": injected["transaction-time"],
        "Bitemporal": injected["bitemporal"],
    }


def test_wire_names_expose_the_member_roles_the_write_path_needs() -> None:
    names = wire_names_of(Order)
    assert names.name_to_py["placedAt"] == "placed_at"
    assert names.column_to_py["BIN_NO" if "BIN_NO" in names.column_to_py else "id"] is not None
    assert names.pk_py == frozenset({"id"})
    assert names.relationship_py == {"customer": "customer", "coupon": "coupon"}
    # The member map carries the declared Metadata each name resolves to, which
    # is what decides assignability — there is no second name set restating it.
    assert set(names.members) == set(names.py_to_name)
    assert names.members["qty"] in Order.attributes
    # The framework-owned names are that map projected, not a set recorded
    # beside it: they move when the designation does.
    assert names.framework_owned_py == frozenset({"version"})
    assert wire_names_of(Episode).framework_owned_py == frozenset(
        {"valid_start", "valid_end", "tx_start", "tx_end"}
    )


@pytest.mark.skipif(
    sys.version_info < (3, 14),
    reason="PEP 649 / PEP 749 defer class-body annotations only on Python 3.14+",
)
def test_deferred_annotations_are_recovered_without_the_future_import() -> None:
    # This module omits ``from __future__ import annotations``, so on Python
    # 3.14+ a class body carries a deferred ``__annotate_func__`` the engine
    # must evaluate to see the live member types. The eager 3.12/3.13 path is
    # exercised throughout this module; this pins the deferred recovery on its
    # own runtime, so a broken ``annotationlib`` recovery fails here rather than
    # silently yielding a memberless declaration.
    class Deferred(Entity, table="deferred"):
        id: Attr[int] = attr(primary_key=True)
        label: Attr[str]
        customer_id: Attr[int]
        customer: Rel[Customer] = rel(cardinality=MANY_TO_ONE, join=("customer_id", "id"))

    declaration = engine.declaration_of(Deferred)
    assert [member.identity.name for member in declaration.attributes] == [
        "id",
        "label",
        "customerId",
    ]
    assert [member.identity.name for member in declaration.relationships] == ["customer"]


def test_authoring_a_temporal_endpoint_is_refused_at_construction() -> None:
    # Refused where the mistake is, rather than several steps later when a row
    # is derived from it — and as an ordinary construction rejection, because
    # construction is not an edit.
    with pytest.raises(ValidationError, match="tx_start"):
        Reading(id=1, celsius=1.0, tx_start=dt.datetime(2026, 1, 1, tzinfo=dt.UTC))


def test_authoring_the_version_column_is_refused_at_construction() -> None:
    with pytest.raises(ValidationError, match="version"):
        Order(
            id=1,
            placed_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
            qty=2,
            rating=4.5,
            amount=Decimal("1.50"),
            customer_id=7,
            version=1,
        )


def test_every_framework_owned_member_of_one_call_is_reported_together() -> None:
    # The refusal rides Pydantic's own report, so it aggregates across fields
    # for free and lands beside every other rejection of that call.
    with pytest.raises(ValidationError) as caught:
        Episode(
            id=1,
            valid_start=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
            tx_end=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
        )
    assert {error["loc"][0] for error in caught.value.errors()} == {"valid_start", "tx_end"}


def test_a_framework_owned_member_is_omitted_rather_than_required() -> None:
    # The caller never supplies the value, so requiring one would make the
    # Entity unconstructible; it reads as absent until hydration supplies it.
    fresh = Reading(id=1, celsius=1.0)
    assert fresh.tx_start is None
    assert "tx_start" not in fresh.model_fields_set


def test_a_hydrated_framework_owned_value_is_readable_and_survives_an_edit() -> None:
    # Hydration builds through the validation-free path, so the stored value
    # reaches the instance; an edit then carries it forward untouched rather
    # than resubmitting it to the constructor that refuses authored ones.
    hydrated = Reading.model_construct(
        id=1, celsius=1.0, tx_start=dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    )
    edited = hydrated.edit(celsius=2.0)
    assert edited.tx_start == dt.datetime(2026, 1, 1, tzinfo=dt.UTC)


def test_an_edited_copy_records_its_earliest_original() -> None:
    # What that record then means to a write — the effective change set and the
    # derived row — is the Entity Row Codec's, and is pinned in
    # ``test_row_codec.py``.
    order = _order()
    assert CHANGE_RECORD_SLOT not in order.__dict__
    once = order.edit(qty=5)
    assert once.__dict__[CHANGE_RECORD_SLOT] == {"qty": 2}
    assert (
        once.__dict__[CHANGE_RECORD_SLOT]
        == order.edit(qty=5).edit(qty=2).__dict__[CHANGE_RECORD_SLOT]
    )


@pytest.mark.parametrize("member", ["id", "version", "customer", "nonesuch"])
def test_an_unassignable_copy_target_is_rejected(member: str) -> None:
    with pytest.raises(EditError):
        _order().edit(**{member: 1})


def test_every_entity_class_is_frozen_without_declaring_it() -> None:
    order = _order()
    with pytest.raises(ValueError, match="frozen"):
        order.qty = 3  # pyright: ignore[reportAttributeAccessIssue] - frozen: the write must raise
