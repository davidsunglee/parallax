"""The shared declaration engine in isolation.

Header parsing, the framework-mint capability token, the temporal-axis marker
read off the MRO, the eagerly built declaration payload, and annotation
resolution against the class body before module globals. This module declares
under ``from __future__ import annotations`` deliberately: the stringized path is
the one where class-body resolution matters.

The closing section drives the two ``frontend_probes`` modules together, because
the live and stringized paths are separate code and one authored spelling has to
compile to one declaration on both.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from _support import frontend_probes, frontend_probes_stringized
from parallax.core import (
    MANY_TO_ONE,
    ONE_TO_MANY,
    READ_ONLY,
    TABLE_PER_CONCRETE_SUBTYPE,
    AbstractRoot,
    AbstractSubtype,
    Attr,
    Bitemporal,
    ConcreteSubtype,
    Entity,
    EntityDefinitionError,
    Rel,
    TablePerHierarchy,
    TxTemporal,
    ValueObject,
    attr,
    desc,
    index,
    rel,
)
from parallax.core.entity._declaration import (
    DeclarationKind,
    build_class,
    declaration_of,
    inherited_axes,
    is_declared_class,
    members_of,
    shape_of,
    snake_to_camel,
)
from parallax.core.metamodel import (
    NOT_PRIMARY_KEY,
    AttributeIdentity,
    Column,
    EntityIdentity,
    EntityReference,
    ExactEntityReference,
    IndexIdentity,
    IndexMetadata,
    Multiplicity,
    PersistenceMode,
    PrimaryKey,
    RelationshipIdentity,
    RelativeEntityReference,
    SortDirection,
    Table,
    TemporalDimension,
    UnresolvedDefiningRelationshipDeclaration,
    UnresolvedEntityDeclaration,
    UnresolvedRelationshipDeclaration,
    UnresolvedReverseRelationshipDeclaration,
)
from parallax.core.metamodel import AbstractSubtype as AcceptedAbstractSubtype
from parallax.core.metamodel import ConcreteSubtype as AcceptedConcreteSubtype


class Warehouse(
    Entity,
    table="warehouse",
    name="WAREHOUSE",
    namespace="ops",
    persistence=READ_ONLY,
    indices=(index("warehouse_code", "code", unique=True),),
):
    id: Attr[int] = attr(primary_key=True)
    code: Attr[str] = attr(column="wh_code", max_length=8)
    crates: Rel[tuple[Crate, ...]] = rel(reverse_of="warehouse", order_by=(desc("id"),))


class Crate(Entity, table="crate", namespace="ops"):
    id: Attr[int] = attr(primary_key=True)
    warehouse_id: Attr[int]
    warehouse: Rel[Warehouse] = rel(cardinality=MANY_TO_ONE, join=("warehouse_id", "id"))


@pytest.mark.parametrize(
    ("snake", "camel"),
    [("id", "id"), ("order_id", "orderId"), ("tax_id_no", "taxIdNo"), ("a_b_c", "aBC")],
)
def test_canonical_member_names_convert_deterministically(snake: str, camel: str) -> None:
    assert snake_to_camel(snake) == camel


def test_the_class_header_supplies_every_entity_level_fact() -> None:
    declaration = declaration_of(Warehouse)
    assert declaration.identity == EntityIdentity("ops", "WAREHOUSE")
    assert declaration.container == Table("warehouse")
    assert declaration.persistence is PersistenceMode.READ_ONLY
    assert declaration.indices == (
        IndexMetadata(
            identity=IndexIdentity(declaration.identity, "warehouse_code"),
            attributes=(AttributeIdentity(declaration.identity, "code"),),
            unique=True,
        ),
    )


def test_an_entity_class_is_its_own_unresolved_declaration() -> None:
    view: UnresolvedEntityDeclaration = Warehouse
    assert view.identity == EntityIdentity("ops", "WAREHOUSE")
    assert [member.identity.name for member in view.attributes] == ["id", "code"]
    assert [member.identity.name for member in view.relationships] == ["crates"]
    assert view.value_objects == ()
    assert view.as_of_axes == ()
    assert view.inheritance is None


def test_attribute_facts_come_from_the_annotation_and_the_factory_together() -> None:
    identity, code = Warehouse.attributes
    assert identity.primary_key == PrimaryKey()
    assert identity.storage == Column("id")
    assert code.primary_key is NOT_PRIMARY_KEY
    assert code.storage == Column("wh_code")
    assert code.max_length == 8
    assert code.nullable is False


def test_storage_defaults_after_canonical_identity_and_explicit_columns_win() -> None:
    class Shipment(Entity, table="shipment"):
        id: Attr[int] = attr(primary_key=True)
        tracking_code: Attr[str]
        tax_id: Attr[str] = attr(name="taxID")
        legacy_code: Attr[str] = attr(name="legacyCode", column="legacyCode")
        bin_no: Attr[str] = attr(column="BIN_NO")

    by_name = {member.identity.name: member for member in Shipment.attributes}
    assert by_name["trackingCode"].storage == Column("tracking_code")
    assert by_name["taxID"].storage == Column("tax_i_d")
    assert by_name["legacyCode"].storage == Column("legacyCode")
    assert by_name["binNo"].storage == Column("BIN_NO")


def test_nullability_comes_from_the_annotation_alone() -> None:
    class Coupon(Entity, table="coupon"):
        id: Attr[int] = attr(primary_key=True)
        label: Attr[str | None]

    assert Coupon.attributes[1].nullable is True
    assert Coupon(id=1).label is None


def test_a_stringized_target_is_relative_however_its_source_spelled_it() -> None:
    # `Crate.warehouse` names the class object, but under stringized annotations
    # the engine only ever sees the name `Warehouse` — indistinguishable from a
    # bare `Rel["Warehouse"]` — so both read as Relative to the declaring
    # namespace. `test_entity_frontend` holds the live class-object twin.
    defining = Crate.relationships[0]
    assert isinstance(defining, UnresolvedDefiningRelationshipDeclaration)
    assert defining.identity == RelationshipIdentity(Crate.identity, "warehouse")
    assert defining.cardinality is MANY_TO_ONE
    assert defining.join.source == AttributeIdentity(Crate.identity, "warehouseId")
    assert defining.join.target.entity == RelativeEntityReference("Warehouse")
    assert defining.join.target.name == "id"

    reverse = Warehouse.relationships[0]
    assert isinstance(reverse, UnresolvedReverseRelationshipDeclaration)
    assert reverse.reverse_of.entity == RelativeEntityReference("Crate")
    assert reverse.reverse_of.name == "warehouse"
    assert reverse.order_by[0].attribute == "id"
    assert reverse.order_by[0].direction is SortDirection.DESCENDING


def test_a_many_relationship_is_spelled_as_a_tuple_annotation() -> None:
    class Bin(Entity, table="bin"):
        id: Attr[int] = attr(primary_key=True)
        crates: Rel[tuple[Crate, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "warehouse_id"))

    declaration = Bin.relationships[0]
    assert isinstance(declaration, UnresolvedDefiningRelationshipDeclaration)
    assert declaration.cardinality is ONE_TO_MANY


def test_framework_axes_travel_on_the_mro_marker() -> None:
    assert inherited_axes((Entity,)) == ()
    assert inherited_axes((TxTemporal,)) == (TemporalDimension.TRANSACTION_TIME,)
    assert inherited_axes((Bitemporal,)) == (
        TemporalDimension.VALID_TIME,
        TemporalDimension.TRANSACTION_TIME,
    )


def test_a_temporal_shape_owner_receives_the_framework_members_in_canonical_order() -> None:
    class Reading(Bitemporal, table="reading"):
        id: Attr[int] = attr(primary_key=True)

    names = [member.identity.name for member in Reading.attributes]
    assert names == ["id", "validStart", "validEnd", "txStart", "txEnd"]
    columns = [member.storage.name for member in Reading.attributes]
    assert columns == ["id", "from_z", "thru_z", "in_z", "out_z"]
    assert [axis.dimension for axis in Reading.as_of_axes] == [
        TemporalDimension.VALID_TIME,
        TemporalDimension.TRANSACTION_TIME,
    ]


def test_a_descendant_inherits_the_family_axes_and_declares_none_of_its_own() -> None:
    class Meter(TxTemporal, table="meter", inheritance=AbstractRoot(TablePerHierarchy("kind"))):
        id: Attr[int] = attr(primary_key=True)

    class GasMeter(Meter, inheritance=ConcreteSubtype(tag_value="gas")):
        pressure: Attr[float | None]

    assert Meter.as_of_axes != ()
    assert GasMeter.as_of_axes == ()
    assert GasMeter.container is None
    assert GasMeter.inheritance == AcceptedConcreteSubtype(
        ExactEntityReference(Meter.identity), "gas"
    )


def test_the_bare_subtype_role_spellings_are_accepted() -> None:
    class Vehicle(Entity, inheritance=AbstractRoot(TABLE_PER_CONCRETE_SUBTYPE)):
        id: Attr[int] = attr(primary_key=True)

    class Wheeled(Vehicle, inheritance=AbstractSubtype):
        axles: Attr[int | None]

    class Car(Wheeled, table="car", inheritance=ConcreteSubtype):
        doors: Attr[int | None]

    assert Vehicle.container is None
    assert Wheeled.inheritance == AcceptedAbstractSubtype(ExactEntityReference(Vehicle.identity))
    assert Car.inheritance == AcceptedConcreteSubtype(ExactEntityReference(Wheeled.identity), None)
    assert Car.container == Table("car")


def test_a_nested_value_object_shape_resolves_against_the_class_body_first() -> None:
    class Parcel(Entity, table="parcel"):
        class Dimensions(ValueObject):
            width: Attr[float]
            height: Attr[float]

        id: Attr[int] = attr(primary_key=True)
        size: Attr[Dimensions | None]

    occurrence = Parcel.value_objects[0]
    assert occurrence.name == "size"
    assert occurrence.nullable is True
    assert occurrence.multiplicity is Multiplicity.ONE
    assert [leaf.name for leaf in occurrence.shape.attributes] == ["width", "height"]


class Tag(ValueObject):
    """A reusable shape both occurrences below name."""

    label: Attr[str]


class Note(ValueObject):
    """A reusable shape reached through a Many occurrence."""

    body: Attr[str]


def test_one_shape_key_is_minted_per_value_object_class_and_reused_by_occurrences() -> None:
    class Left(Entity, table="left"):
        id: Attr[int] = attr(primary_key=True)
        tag: Attr[Tag | None]

    class Right(Entity, table="right"):
        id: Attr[int] = attr(primary_key=True)
        tag: Attr[Tag | None]

    assert Left.value_objects[0].shape.key is Right.value_objects[0].shape.key
    assert shape_of(Tag).shape.key is Left.value_objects[0].shape.key


def test_the_attribute_descriptor_returns_the_instance_value_on_direct_invocation() -> None:
    # Pydantic's instance ``__dict__`` shadows the descriptor under ordinary
    # attribute access, so the instance branch of ``Attr.__get__`` is reached
    # only by invoking the descriptor directly.
    warehouse = Warehouse(id=7, code="WH")
    descriptor = vars(Warehouse)["id"]
    assert descriptor.__get__(warehouse, Warehouse) == 7


def test_the_element_descriptor_returns_the_instance_value_on_direct_invocation() -> None:
    tag = Tag(label="priority")
    descriptor = vars(Tag)["label"]
    assert descriptor.__get__(tag, Tag) == "priority"


def test_a_many_value_object_occurrence_defaults_to_the_empty_tuple() -> None:
    class Ledger(Entity, table="ledger"):
        id: Attr[int] = attr(primary_key=True)
        notes: Attr[tuple[Note, ...]]

    assert Ledger.value_objects[0].multiplicity is Multiplicity.MANY
    assert Ledger(id=1).notes == ()


def test_the_mint_token_is_the_only_way_to_declare_a_framework_root() -> None:
    with pytest.raises(EntityDefinitionError) as caught:
        build_class(
            type,
            "Counterfeit",
            (Entity,),
            {},
            kind=DeclarationKind.ENTITY,
            mint=object(),
            axes=(),
            header=None,
        )
    assert caught.value.code == "entity-header-unknown-option"


def test_a_framework_root_declares_nothing_and_is_never_a_candidate() -> None:
    assert is_declared_class(Entity, DeclarationKind.ENTITY)
    assert is_declared_class(ValueObject, DeclarationKind.VALUE_OBJECT)
    with pytest.raises(EntityDefinitionError) as caught:
        declaration_of(Entity)
    assert caught.value.code == "entity-base-invalid"


def test_both_declaration_lookups_refuse_a_class_the_engine_never_built() -> None:
    # The two lookups answer for one class fact, so they refuse together: an
    # ordinary Python class carries neither payload.
    with pytest.raises(EntityDefinitionError) as declaration:
        declaration_of(int)
    with pytest.raises(EntityDefinitionError) as names:
        members_of(int)
    assert declaration.value.code == names.value.code == "entity-base-invalid"
    assert names.value.message == "int is not a Parallax Entity Class"


def test_a_relationship_target_spelled_as_nothing_at_all_is_refused() -> None:
    # A target spelling is never evaluated, so an empty one reaches the
    # reference reader as text and is refused there rather than resolving to the
    # declaring namespace.
    def declare() -> type:
        class Blank(Entity, table="blank"):
            id: Attr[int] = attr(primary_key=True)
            peer_id: Attr[int]
            peer: Rel[""] = rel(  # type: ignore[valid-type]  # noqa: F722 - empty forward ref
                cardinality=MANY_TO_ONE, join=("peer_id", "id")
            )

        return Blank

    with pytest.raises(EntityDefinitionError) as caught:
        declare()
    assert caught.value.code == "entity-annotation-invalid"
    assert caught.value.message == "Blank.peer: a relationship target names a nonempty Entity"


def test_member_correspondences_are_built_from_the_same_walk_as_the_declaration() -> None:
    names = members_of(Warehouse)
    assert names.py_to_name == {"id": "id", "code": "code"}
    assert names.column_to_py == {"id": "id", "wh_code": "code"}
    assert names.relationship_py == {"crates": "crates"}
    assert names.pk_py == frozenset({"id"})


def _target_of(declaration: UnresolvedRelationshipDeclaration) -> EntityReference:
    if isinstance(declaration, UnresolvedDefiningRelationshipDeclaration):
        return declaration.join.target.entity
    return declaration.reverse_of.entity


def _occurrences(cls: type) -> list[tuple[str, Multiplicity, bool, list[str]]]:
    return [
        (
            occurrence.name,
            occurrence.multiplicity,
            occurrence.nullable,
            [leaf.name for leaf in occurrence.shape.attributes],
        )
        for occurrence in declaration_of(cls).value_objects
    ]


def test_both_annotation_paths_read_one_relationship_spelling_the_same_way() -> None:
    live = declaration_of(frontend_probes.accepted_relationship_targets())
    stringized = declaration_of(frontend_probes_stringized.accepted_relationship_targets())
    assert live.relationships == stringized.relationships
    assert {member.identity.name: _target_of(member) for member in live.relationships} == {
        "bare": RelativeEntityReference("Peer"),
        "qualified": ExactEntityReference(EntityIdentity("ops", "Peer")),
        "unionOptional": RelativeEntityReference("Peer"),
        "aliasOptional": RelativeEntityReference("Peer"),
        "many": RelativeEntityReference("Peer"),
    }


def test_both_annotation_paths_read_one_relationship_shape_the_same_way() -> None:
    live = members_of(frontend_probes.accepted_relationship_targets()).relationship_shapes
    stringized = members_of(
        frontend_probes_stringized.accepted_relationship_targets()
    ).relationship_shapes
    assert live == stringized
    assert {name: (shape.multiplicity, shape.nullable) for name, shape in live.items()} == {
        "bare": (Multiplicity.ONE, False),
        "qualified": (Multiplicity.ONE, False),
        "unionOptional": (Multiplicity.ONE, True),
        "aliasOptional": (Multiplicity.ONE, True),
        "many": (Multiplicity.MANY, False),
    }


def test_both_annotation_paths_resolve_one_quoted_value_object_spelling() -> None:
    live = _occurrences(frontend_probes.accepted_value_object_spellings())
    stringized = _occurrences(frontend_probes_stringized.accepted_value_object_spellings())
    assert live == stringized
    assert live == [
        ("home", Multiplicity.ONE, True, ["city"]),
        ("tags", Multiplicity.MANY, False, ["label"]),
    ]


@pytest.mark.parametrize(
    "build",
    [frontend_probes.accepted_class_var, frontend_probes_stringized.accepted_class_var],
    ids=["live", "stringized"],
)
def test_a_class_variable_is_passed_over_on_both_annotation_paths(
    build: Callable[[], type],
) -> None:
    marked = build()
    assert [member.identity.name for member in declaration_of(marked).attributes] == ["id"]
    assert getattr(marked, "kind", None) == "marked"
