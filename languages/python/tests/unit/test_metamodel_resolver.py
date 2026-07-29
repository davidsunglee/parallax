"""m-metamodel: the fixed foundational resolver and its complete issue vocabulary."""

from __future__ import annotations

import random

import pytest
from _metamodel_support import (
    Declaration,
    accepted,
    attribute,
    codes,
    identity,
    instant,
    key,
    rejection,
    source,
)

from parallax.core import base
from parallax.core.metamodel import (
    AS_OF_ATTRIBUTE_DUPLICATE,
    AS_OF_ATTRIBUTE_MISSING,
    AS_OF_ATTRIBUTE_OWNER,
    AS_OF_ATTRIBUTE_TYPE,
    AS_OF_DIMENSION_DUPLICATE,
    DUPLICATE_ENTITY_IDENTITY,
    INDEX_ATTRIBUTE_DUPLICATE,
    INDEX_ATTRIBUTE_MISSING,
    INDEX_ATTRIBUTE_NOT_LOCAL,
    INDEX_EMPTY,
    INVALID_ENTITY_IDENTITY,
    LOCAL_MEMBER_COLLISION,
    PRIMARY_KEY_MISSING,
    PRIMARY_KEY_MULTIPLE,
    RESOLVER_ISSUE_CODES,
    TEMPORAL_MEMBER_RESERVED,
    UNRESOLVED_ATTRIBUTE_REFERENCE,
    UNRESOLVED_ENTITY_REFERENCE,
    UNRESOLVED_RELATIONSHIP_REFERENCE,
    AbstractRoot,
    AbstractSubtype,
    AsOfAxisMetadata,
    AttributeIdentity,
    AttributeReference,
    Cardinality,
    Column,
    ConcreteSubtype,
    DefiningRelationshipDeclaration,
    EntityIdentity,
    EntityLocation,
    ExactEntityReference,
    IndexIdentity,
    IndexMetadata,
    Multiplicity,
    NestedValueObjectOccurrenceDeclaration,
    RelationshipIdentity,
    RelationshipJoin,
    RelationshipLocation,
    RelationshipOrder,
    RelationshipReference,
    RelativeEntityReference,
    ReverseRelationshipDeclaration,
    SortDirection,
    Table,
    TablePerHierarchy,
    TemporalDimension,
    UnresolvedDefiningRelationshipDeclaration,
    UnresolvedRelationshipJoin,
    UnresolvedRelationshipOrder,
    UnresolvedReverseRelationshipDeclaration,
    ValueObjectAttributeDeclaration,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
)

_ORDER = identity("Order")
_ITEM = identity("Item")
_ANIMAL = identity("Animal")
_PET = identity("Pet")
_DOG = identity("Dog")


def _shape(*attributes: ValueObjectAttributeDeclaration) -> ValueObjectShapeDeclaration:
    return ValueObjectShapeDeclaration(ValueObjectShapeKey(), attributes=attributes)


def _order() -> Declaration:
    """An Entity owning one defining to-many relationship with ordering."""
    return Declaration(
        identity=_ORDER,
        container=Table("orders"),
        attributes=(key(_ORDER), attribute(_ORDER, "sku", type=base.STRING)),
        relationships=(
            UnresolvedDefiningRelationshipDeclaration(
                identity=RelationshipIdentity(_ORDER, "items"),
                cardinality=Cardinality.ONE_TO_MANY,
                join=UnresolvedRelationshipJoin(
                    source=AttributeIdentity(_ORDER, "id"),
                    target=AttributeReference(RelativeEntityReference("Item"), "orderId"),
                ),
                order_by=(UnresolvedRelationshipOrder("sku", SortDirection.DESCENDING),),
            ),
        ),
    )


def _item() -> Declaration:
    """The peer Entity, naming the defining declaration from the reverse side."""
    return Declaration(
        identity=_ITEM,
        container=Table("item"),
        attributes=(
            key(_ITEM),
            attribute(_ITEM, "orderId", column="order_id"),
            attribute(_ITEM, "sku", type=base.STRING),
        ),
        relationships=(
            UnresolvedReverseRelationshipDeclaration(
                identity=RelationshipIdentity(_ITEM, "order"),
                reverse_of=RelationshipReference(RelativeEntityReference("Order"), "items"),
                order_by=(UnresolvedRelationshipOrder("sku"),),
            ),
        ),
        indices=(
            IndexMetadata(
                IndexIdentity(_ITEM, "item_pk"), (AttributeIdentity(_ITEM, "id"),), unique=True
            ),
        ),
    )


def test_a_well_formed_model_resolves_to_a_canonical_candidate() -> None:
    candidate = accepted(source(_order(), _item()))
    assert [entity.identity for entity in candidate.entities] == [_ITEM, _ORDER]
    assert candidate.entity(_ORDER) is not None
    assert candidate.entity(identity("Absent")) is None


def test_local_sequences_keep_their_authored_order() -> None:
    candidate = accepted(source(_order(), _item()))
    item = candidate.entity(_ITEM)
    assert item is not None
    assert [member.identity.name for member in item.attributes] == ["id", "orderId", "sku"]


def test_a_defining_declaration_resolves_its_join_target_and_ordering() -> None:
    candidate = accepted(source(_order(), _item()))
    order = candidate.entity(_ORDER)
    assert order is not None
    declared = order.relationships[0]
    assert declared == DefiningRelationshipDeclaration(
        identity=RelationshipIdentity(_ORDER, "items"),
        cardinality=Cardinality.ONE_TO_MANY,
        join=RelationshipJoin(
            source=AttributeIdentity(_ORDER, "id"), target=AttributeIdentity(_ITEM, "orderId")
        ),
        order_by=(RelationshipOrder(AttributeIdentity(_ITEM, "sku"), SortDirection.DESCENDING),),
    )


def test_a_reverse_declaration_resolves_only_to_its_peer_identity() -> None:
    candidate = accepted(source(_order(), _item()))
    item = candidate.entity(_ITEM)
    assert item is not None
    assert item.relationships[0] == ReverseRelationshipDeclaration(
        identity=RelationshipIdentity(_ITEM, "order"),
        reverse_of=RelationshipIdentity(_ORDER, "items"),
        order_by=(RelationshipOrder(AttributeIdentity(_ORDER, "sku"), SortDirection.ASCENDING),),
    )


def test_an_exact_unnamespaced_reference_is_not_an_owner_relative_name() -> None:
    ownerless = EntityIdentity(None, "Item")
    order = Declaration(
        identity=_ORDER,
        attributes=(key(_ORDER),),
        relationships=(
            UnresolvedDefiningRelationshipDeclaration(
                identity=RelationshipIdentity(_ORDER, "items"),
                cardinality=Cardinality.ONE_TO_MANY,
                join=UnresolvedRelationshipJoin(
                    source=AttributeIdentity(_ORDER, "id"),
                    target=AttributeReference(ExactEntityReference(ownerless), "orderId"),
                ),
            ),
        ),
    )
    namespaced_peer = Declaration(
        identity=_ITEM, attributes=(key(_ITEM), attribute(_ITEM, "orderId"))
    )
    assert codes(source(order, namespaced_peer)) == (UNRESOLVED_ENTITY_REFERENCE,)

    ownerless_peer = Declaration(
        identity=ownerless, attributes=(key(ownerless), attribute(ownerless, "orderId"))
    )
    candidate = accepted(source(order, ownerless_peer))
    resolved = candidate.entity(_ORDER)
    assert resolved is not None
    declared = resolved.relationships[0]
    assert isinstance(declared, DefiningRelationshipDeclaration)
    assert declared.join.target.entity == ownerless


def test_a_qualified_reference_reaches_another_namespace() -> None:
    other = EntityIdentity("other", "Item")
    order = Declaration(
        identity=_ORDER,
        attributes=(key(_ORDER),),
        relationships=(
            UnresolvedDefiningRelationshipDeclaration(
                identity=RelationshipIdentity(_ORDER, "items"),
                cardinality=Cardinality.ONE_TO_MANY,
                join=UnresolvedRelationshipJoin(
                    source=AttributeIdentity(_ORDER, "id"),
                    target=AttributeReference(ExactEntityReference(other), "orderId"),
                ),
            ),
        ),
    )
    peer = Declaration(identity=other, attributes=(key(other), attribute(other, "orderId")))
    candidate = accepted(source(order, peer))
    resolved = candidate.entity(_ORDER)
    assert resolved is not None
    declared = resolved.relationships[0]
    assert isinstance(declared, DefiningRelationshipDeclaration)
    assert declared.join.target == AttributeIdentity(other, "orderId")


def _family() -> tuple[Declaration, Declaration, Declaration]:
    """A three-position hierarchy whose subtypes declare no key of their own."""
    root = Declaration(
        identity=_ANIMAL,
        container=Table("animal"),
        attributes=(key(_ANIMAL), attribute(_ANIMAL, "ownerId", column="owner_id")),
        inheritance=AbstractRoot(TablePerHierarchy("kind")),
    )
    middle = Declaration(
        identity=_PET,
        attributes=(attribute(_PET, "licenseId", type=base.STRING),),
        inheritance=AbstractSubtype(RelativeEntityReference("Animal")),
    )
    leaf = Declaration(
        identity=_DOG,
        attributes=(attribute(_DOG, "barkVolume"),),
        inheritance=ConcreteSubtype(RelativeEntityReference("Pet"), "dog"),
    )
    return root, middle, leaf


def test_inheritance_parents_resolve_to_identities_without_deriving_the_family() -> None:
    candidate = accepted(source(*_family()))
    middle = candidate.entity(_PET)
    leaf = candidate.entity(_DOG)
    root = candidate.entity(_ANIMAL)
    assert middle is not None and leaf is not None and root is not None
    assert middle.inheritance == AbstractSubtype(_ANIMAL)
    assert leaf.inheritance == ConcreteSubtype(_PET, "dog")
    assert root.inheritance == AbstractRoot(TablePerHierarchy("kind"))


def test_a_join_target_may_name_an_ancestors_attribute() -> None:
    owner = Declaration(
        identity=_ORDER,
        attributes=(key(_ORDER),),
        relationships=(
            UnresolvedDefiningRelationshipDeclaration(
                identity=RelationshipIdentity(_ORDER, "pets"),
                cardinality=Cardinality.ONE_TO_MANY,
                join=UnresolvedRelationshipJoin(
                    source=AttributeIdentity(_ORDER, "id"),
                    target=AttributeReference(RelativeEntityReference("Pet"), "ownerId"),
                ),
            ),
        ),
    )
    candidate = accepted(source(*_family(), owner))
    resolved = candidate.entity(_ORDER)
    assert resolved is not None
    declared = resolved.relationships[0]
    assert isinstance(declared, DefiningRelationshipDeclaration)
    assert declared.join.target == AttributeIdentity(_PET, "ownerId")


def test_an_ancestry_cycle_terminates_the_applicable_attribute_walk() -> None:
    left = Declaration(
        identity=_ANIMAL,
        attributes=(key(_ANIMAL),),
        inheritance=AbstractSubtype(RelativeEntityReference("Pet")),
    )
    right = Declaration(
        identity=_PET, inheritance=AbstractSubtype(RelativeEntityReference("Animal"))
    )
    owner = Declaration(
        identity=_ORDER,
        attributes=(key(_ORDER),),
        relationships=(
            UnresolvedDefiningRelationshipDeclaration(
                identity=RelationshipIdentity(_ORDER, "pets"),
                cardinality=Cardinality.ONE_TO_MANY,
                join=UnresolvedRelationshipJoin(
                    source=AttributeIdentity(_ORDER, "id"),
                    target=AttributeReference(RelativeEntityReference("Pet"), "absent"),
                ),
            ),
        ),
    )
    assert codes(source(left, right, owner)) == (UNRESOLVED_ATTRIBUTE_REFERENCE,)


def test_an_unresolvable_parent_ends_the_walk_and_reports_the_entity_reference() -> None:
    orphan = Declaration(
        identity=_PET,
        attributes=(attribute(_PET, "licenseId", type=base.STRING),),
        inheritance=ConcreteSubtype(RelativeEntityReference("Missing"), "pet"),
    )
    owner = Declaration(
        identity=_ORDER,
        attributes=(key(_ORDER),),
        relationships=(
            UnresolvedDefiningRelationshipDeclaration(
                identity=RelationshipIdentity(_ORDER, "pets"),
                cardinality=Cardinality.ONE_TO_MANY,
                join=UnresolvedRelationshipJoin(
                    source=AttributeIdentity(_ORDER, "id"),
                    target=AttributeReference(RelativeEntityReference("Pet"), "ownerId"),
                ),
            ),
        ),
    )
    assert codes(source(orphan, owner)) == (
        UNRESOLVED_ATTRIBUTE_REFERENCE,
        UNRESOLVED_ENTITY_REFERENCE,
    )


def test_an_ill_formed_entity_name_is_rejected_with_its_own_location() -> None:
    dotted = identity("a.b")
    issues = rejection(source(Declaration(identity=dotted, attributes=(key(dotted),))))
    assert [issue.code for issue in issues] == [INVALID_ENTITY_IDENTITY]


def test_duplicate_identities_are_legal_input_and_a_rejected_model() -> None:
    declaration = Declaration(identity=_ORDER, attributes=(key(_ORDER),))
    assert codes(source(declaration, declaration)) == (DUPLICATE_ENTITY_IDENTITY,)


def test_a_reference_into_duplicated_identities_ignores_frontend_order() -> None:
    """Frontend order is diagnostic only, so it cannot decide which duplicate a
    reference resolves against."""
    with_sku = Declaration(identity=_ITEM, attributes=(key(_ITEM), attribute(_ITEM, "sku")))
    without_sku = Declaration(identity=_ITEM, attributes=(key(_ITEM),))
    referrer = Declaration(
        identity=_ORDER,
        attributes=(key(_ORDER),),
        relationships=(
            UnresolvedDefiningRelationshipDeclaration(
                identity=RelationshipIdentity(_ORDER, "items"),
                cardinality=Cardinality.ONE_TO_MANY,
                join=UnresolvedRelationshipJoin(
                    source=AttributeIdentity(_ORDER, "id"),
                    target=AttributeReference(RelativeEntityReference("Item"), "sku"),
                ),
            ),
        ),
    )
    assert codes(source(with_sku, without_sku, referrer)) == (DUPLICATE_ENTITY_IDENTITY,)
    assert codes(source(without_sku, with_sku, referrer)) == (DUPLICATE_ENTITY_IDENTITY,)


def test_a_reverse_peer_is_found_through_any_declaration_bearing_its_identity() -> None:
    silent = Declaration(identity=_ORDER, attributes=(key(_ORDER),))
    declaring = Declaration(
        identity=_ORDER,
        attributes=(key(_ORDER),),
        relationships=(
            UnresolvedDefiningRelationshipDeclaration(
                identity=RelationshipIdentity(_ORDER, "items"),
                cardinality=Cardinality.ONE_TO_MANY,
                join=UnresolvedRelationshipJoin(
                    source=AttributeIdentity(_ORDER, "id"),
                    target=AttributeReference(RelativeEntityReference("Item"), "orderId"),
                ),
            ),
        ),
    )
    peer = Declaration(
        identity=_ITEM,
        attributes=(key(_ITEM), attribute(_ITEM, "orderId")),
        relationships=(
            UnresolvedReverseRelationshipDeclaration(
                identity=RelationshipIdentity(_ITEM, "order"),
                reverse_of=RelationshipReference(RelativeEntityReference("Order"), "items"),
            ),
        ),
    )
    assert codes(source(silent, declaring, peer)) == (DUPLICATE_ENTITY_IDENTITY,)
    assert codes(source(declaring, silent, peer)) == (DUPLICATE_ENTITY_IDENTITY,)


def test_one_defect_reached_from_two_declarations_reports_one_issue_identity() -> None:
    """A repeated ``(code, location, related)`` is a formation contract failure, so
    aggregation reports each identity once however many times it was reached."""
    keyless = Declaration(identity=_ORDER, attributes=(attribute(_ORDER, "sku"),))
    issues = rejection(source(keyless, keyless))
    assert [issue.code for issue in issues] == [DUPLICATE_ENTITY_IDENTITY, PRIMARY_KEY_MISSING]
    assert len(set(issues)) == len(issues)


def test_a_component_repeated_three_times_reports_one_duplicate_identity() -> None:
    component = AttributeIdentity(_ORDER, "id")
    declaration = Declaration(
        identity=_ORDER,
        attributes=(key(_ORDER),),
        indices=(
            IndexMetadata(IndexIdentity(_ORDER, "orders_pk"), (component, component, component)),
        ),
    )
    issues = rejection(source(declaration))
    assert [issue.code for issue in issues] == [INDEX_ATTRIBUTE_DUPLICATE]


def test_every_repetition_a_legal_model_allows_still_reports_each_defect_once() -> None:
    """One model repeating every position a defect can be reached from twice.

    The formation seam holds the resolver to distinct issue identities, so a
    repetition that a frontend is allowed to hand over — a duplicated
    declaration, a repeated Index component, a redeclared Temporal Dimension, a
    name declared three times, an ordering term repeating a missing Attribute —
    must not turn a model defect into a contract failure.
    """
    component = AttributeIdentity(_ORDER, "absent")
    axis = AsOfAxisMetadata(
        TemporalDimension.VALID_TIME,
        AttributeIdentity(_ORDER, "gone"),
        AttributeIdentity(_ORDER, "gone"),
    )
    declaration = Declaration(
        identity=_ORDER,
        attributes=(attribute(_ORDER, "sku"), attribute(_ORDER, "sku"), attribute(_ORDER, "sku")),
        relationships=(
            UnresolvedDefiningRelationshipDeclaration(
                identity=RelationshipIdentity(_ORDER, "items"),
                cardinality=Cardinality.ONE_TO_MANY,
                join=UnresolvedRelationshipJoin(
                    source=AttributeIdentity(_ORDER, "id"),
                    target=AttributeReference(RelativeEntityReference("Item"), "nowhere"),
                ),
                order_by=(
                    UnresolvedRelationshipOrder("nowhere"),
                    UnresolvedRelationshipOrder("nowhere"),
                ),
            ),
        ),
        as_of_axes=(axis, axis),
        indices=(IndexMetadata(IndexIdentity(_ORDER, "orders_ix"), (component, component)),),
    )
    peer = Declaration(identity=_ITEM, attributes=(key(_ITEM),))
    issues = rejection(source(declaration, declaration, peer))
    assert len(set(issues)) == len(issues)
    assert sorted({issue.code for issue in issues}) == [
        AS_OF_ATTRIBUTE_DUPLICATE,
        AS_OF_ATTRIBUTE_MISSING,
        AS_OF_DIMENSION_DUPLICATE,
        DUPLICATE_ENTITY_IDENTITY,
        INDEX_ATTRIBUTE_DUPLICATE,
        INDEX_ATTRIBUTE_MISSING,
        LOCAL_MEMBER_COLLISION,
        PRIMARY_KEY_MISSING,
        UNRESOLVED_ATTRIBUTE_REFERENCE,
    ]


def test_an_unresolvable_relationship_reference_is_reported_once() -> None:
    item = Declaration(
        identity=_ITEM,
        attributes=(key(_ITEM),),
        relationships=(
            UnresolvedReverseRelationshipDeclaration(
                identity=RelationshipIdentity(_ITEM, "order"),
                reverse_of=RelationshipReference(RelativeEntityReference("Order"), "absent"),
            ),
        ),
    )
    order = Declaration(identity=_ORDER, attributes=(key(_ORDER),))
    issues = rejection(source(order, item))
    assert [issue.code for issue in issues] == [UNRESOLVED_RELATIONSHIP_REFERENCE]
    assert issues[0].related == (RelationshipLocation(RelationshipIdentity(_ORDER, "absent")),)


def test_a_reverse_declaration_reports_an_unresolvable_peer_entity() -> None:
    item = Declaration(
        identity=_ITEM,
        attributes=(key(_ITEM),),
        relationships=(
            UnresolvedReverseRelationshipDeclaration(
                identity=RelationshipIdentity(_ITEM, "order"),
                reverse_of=RelationshipReference(RelativeEntityReference("Missing"), "items"),
            ),
        ),
    )
    assert codes(source(item)) == (UNRESOLVED_ENTITY_REFERENCE,)


def test_a_reverse_declarations_ordering_resolves_against_its_peer_entity() -> None:
    item = Declaration(
        identity=_ITEM,
        attributes=(key(_ITEM), attribute(_ITEM, "orderId"), attribute(_ITEM, "sku")),
        relationships=(
            UnresolvedReverseRelationshipDeclaration(
                identity=RelationshipIdentity(_ITEM, "order"),
                reverse_of=RelationshipReference(RelativeEntityReference("Order"), "items"),
                order_by=(UnresolvedRelationshipOrder("absent"),),
            ),
        ),
    )
    assert codes(source(_order(), item)) == (UNRESOLVED_ATTRIBUTE_REFERENCE,)


def test_a_defining_declarations_ordering_resolves_against_its_target() -> None:
    order = Declaration(
        identity=_ORDER,
        attributes=(key(_ORDER),),
        relationships=(
            UnresolvedDefiningRelationshipDeclaration(
                identity=RelationshipIdentity(_ORDER, "items"),
                cardinality=Cardinality.ONE_TO_MANY,
                join=UnresolvedRelationshipJoin(
                    source=AttributeIdentity(_ORDER, "id"),
                    target=AttributeReference(RelativeEntityReference("Item"), "orderId"),
                ),
                order_by=(UnresolvedRelationshipOrder("absent"),),
            ),
        ),
    )
    item = Declaration(identity=_ITEM, attributes=(key(_ITEM), attribute(_ITEM, "orderId")))
    assert codes(source(order, item)) == (UNRESOLVED_ATTRIBUTE_REFERENCE,)


def test_attributes_relationships_and_value_objects_share_one_namespace() -> None:
    clashing = Declaration(
        identity=_ORDER,
        attributes=(key(_ORDER), attribute(_ORDER, "items", type=base.STRING)),
        relationships=(
            UnresolvedReverseRelationshipDeclaration(
                identity=RelationshipIdentity(_ORDER, "items"),
                reverse_of=RelationshipReference(RelativeEntityReference("Order"), "items"),
            ),
        ),
        value_objects=(
            ValueObjectOccurrenceDeclaration(
                "items",
                Column("items"),
                _shape(ValueObjectAttributeDeclaration("city", base.STRING)),
            ),
        ),
    )
    assert codes(source(clashing)) == (LOCAL_MEMBER_COLLISION, LOCAL_MEMBER_COLLISION)


def test_scalar_and_nested_names_collide_inside_one_value_object() -> None:
    inner = _shape(ValueObjectAttributeDeclaration("city", base.STRING))
    outer = ValueObjectShapeDeclaration(
        ValueObjectShapeKey(),
        attributes=(ValueObjectAttributeDeclaration("geo", base.STRING),),
        value_objects=(NestedValueObjectOccurrenceDeclaration("geo", inner),),
    )
    declaration = Declaration(
        identity=_ORDER,
        attributes=(key(_ORDER),),
        value_objects=(ValueObjectOccurrenceDeclaration("address", Column("address"), outer),),
    )
    assert codes(source(declaration)) == (LOCAL_MEMBER_COLLISION,)


def test_a_shape_graph_that_re_enters_one_key_stops_the_collision_walk() -> None:
    """A containment cycle belongs to ``m-value-object``, so the walk only stops."""
    shared = ValueObjectShapeKey()
    inner = ValueObjectShapeDeclaration(
        shared, attributes=(ValueObjectAttributeDeclaration("city", base.STRING),)
    )
    outer = ValueObjectShapeDeclaration(
        shared, value_objects=(NestedValueObjectOccurrenceDeclaration("inner", inner),)
    )
    declaration = Declaration(
        identity=_ORDER,
        attributes=(key(_ORDER),),
        value_objects=(ValueObjectOccurrenceDeclaration("address", Column("address"), outer),),
    )
    assert accepted(source(declaration)).entity(_ORDER) is not None


def test_a_temporal_shape_reserves_its_conventional_member_names() -> None:
    entity = identity("Ledger")
    declaration = Declaration(
        identity=entity,
        attributes=(
            key(entity),
            instant(entity, "from_ts"),
            instant(entity, "to_ts"),
            attribute(entity, "tx_start", type=base.STRING),
        ),
        relationships=(
            UnresolvedReverseRelationshipDeclaration(
                identity=RelationshipIdentity(entity, "tx_end"),
                reverse_of=RelationshipReference(RelativeEntityReference("Order"), "items"),
            ),
        ),
        value_objects=(
            ValueObjectOccurrenceDeclaration(
                "tx_end",
                Column("tx_end"),
                _shape(ValueObjectAttributeDeclaration("city", base.STRING)),
            ),
        ),
        as_of_axes=(
            AsOfAxisMetadata(
                TemporalDimension.TRANSACTION_TIME,
                AttributeIdentity(entity, "from_ts"),
                AttributeIdentity(entity, "to_ts"),
            ),
        ),
    )
    reported = codes(source(declaration, _order(), _item()))
    assert reported.count(TEMPORAL_MEMBER_RESERVED) == 3
    assert LOCAL_MEMBER_COLLISION in reported


def test_conventional_axis_attributes_are_not_reserved_against_their_own_axis() -> None:
    entity = identity("Balance")
    declaration = Declaration(
        identity=entity,
        attributes=(key(entity), instant(entity, "tx_start"), instant(entity, "tx_end")),
        as_of_axes=(
            AsOfAxisMetadata(
                TemporalDimension.TRANSACTION_TIME,
                AttributeIdentity(entity, "tx_start"),
                AttributeIdentity(entity, "tx_end"),
            ),
        ),
    )
    assert accepted(source(declaration)).entity(entity) is not None


def test_a_standalone_entity_declares_exactly_one_primary_key() -> None:
    keyless = Declaration(identity=_ORDER, attributes=(attribute(_ORDER, "sku"),))
    assert codes(source(keyless)) == (PRIMARY_KEY_MISSING,)

    composite = Declaration(identity=_ORDER, attributes=(key(_ORDER), key(_ORDER, "sku")))
    issues = rejection(source(composite))
    assert [issue.code for issue in issues] == [PRIMARY_KEY_MULTIPLE]
    assert len(issues[0].related) == 2


def test_an_inheritance_participant_leaves_primary_keys_to_its_family() -> None:
    accepted(source(*_family()))


@pytest.mark.parametrize(
    ("components", "expected"),
    [
        pytest.param((), INDEX_EMPTY, id="empty"),
        pytest.param((AttributeIdentity(_ORDER, "absent"),), INDEX_ATTRIBUTE_MISSING, id="missing"),
        pytest.param(
            (AttributeIdentity(_ITEM, "id"),), INDEX_ATTRIBUTE_NOT_LOCAL, id="other-entity"
        ),
        pytest.param(
            (AttributeIdentity(_ORDER, "id"), AttributeIdentity(_ORDER, "id")),
            INDEX_ATTRIBUTE_DUPLICATE,
            id="duplicate",
        ),
    ],
)
def test_index_components_are_local_distinct_and_nonempty(
    components: tuple[AttributeIdentity, ...], expected: str
) -> None:
    declaration = Declaration(
        identity=_ORDER,
        attributes=(key(_ORDER),),
        indices=(IndexMetadata(IndexIdentity(_ORDER, "orders_pk"), components),),
    )
    assert expected in codes(source(declaration))


def test_an_inherited_index_component_is_reported_as_not_local() -> None:
    root, middle, leaf = _family()
    indexed = Declaration(
        identity=leaf.identity,
        attributes=leaf.attributes,
        inheritance=leaf.inheritance,
        indices=(IndexMetadata(IndexIdentity(_DOG, "dog_pk"), (AttributeIdentity(_DOG, "id"),)),),
    )
    assert codes(source(root, middle, indexed)) == (INDEX_ATTRIBUTE_NOT_LOCAL,)


def test_as_of_axes_are_distinct_typed_and_locally_owned() -> None:
    entity = identity("Policy")
    declaration = Declaration(
        identity=entity,
        attributes=(
            key(entity),
            instant(entity, "valid_start"),
            attribute(entity, "valid_end", type=base.INT64),
            instant(entity, "tx_start"),
        ),
        as_of_axes=(
            AsOfAxisMetadata(
                TemporalDimension.VALID_TIME,
                AttributeIdentity(entity, "valid_start"),
                AttributeIdentity(entity, "valid_end"),
            ),
            AsOfAxisMetadata(
                TemporalDimension.TRANSACTION_TIME,
                AttributeIdentity(entity, "tx_start"),
                AttributeIdentity(entity, "tx_start"),
            ),
            AsOfAxisMetadata(
                TemporalDimension.TRANSACTION_TIME,
                AttributeIdentity(_ORDER, "id"),
                AttributeIdentity(entity, "absent"),
            ),
        ),
    )
    reported = codes(source(declaration))
    assert set(reported) == {
        AS_OF_ATTRIBUTE_TYPE,
        AS_OF_ATTRIBUTE_DUPLICATE,
        AS_OF_DIMENSION_DUPLICATE,
        AS_OF_ATTRIBUTE_OWNER,
        AS_OF_ATTRIBUTE_MISSING,
    }


def test_resolution_aggregates_every_issue_rather_than_the_first() -> None:
    first = Declaration(identity=_ORDER, attributes=())
    second = Declaration(identity=_ITEM, attributes=(key(_ITEM), key(_ITEM, "sku")))
    assert codes(source(first, second)) == (PRIMARY_KEY_MULTIPLE, PRIMARY_KEY_MISSING)


def test_the_issue_sequence_is_stable_under_frontend_permutation() -> None:
    names = ("Delta", "Alpha", "Charlie", "Bravo")
    declarations = [Declaration(identity=identity(name), attributes=()) for name in names]
    expected = rejection(source(*declarations))
    assert [issue.location for issue in expected] == [
        EntityLocation(identity(name)) for name in sorted(names)
    ]
    shuffler = random.Random(20260722)
    for _ in range(10):
        permuted = list(declarations)
        shuffler.shuffle(permuted)
        assert rejection(source(*permuted)) == expected


def test_the_resolver_owns_exactly_the_manifest_issue_code_set() -> None:
    assert len(RESOLVER_ISSUE_CODES) == 18
    assert all(code.startswith("metamodel-") for code in RESOLVER_ISSUE_CODES)


def test_value_object_occurrences_reach_the_candidate_unchanged() -> None:
    shape = _shape(ValueObjectAttributeDeclaration("city", base.STRING))
    occurrence = ValueObjectOccurrenceDeclaration(
        "address", Column("address"), shape, multiplicity=Multiplicity.MANY
    )
    declaration = Declaration(
        identity=_ORDER, attributes=(key(_ORDER),), value_objects=(occurrence,)
    )
    candidate = accepted(source(declaration))
    resolved = candidate.entity(_ORDER)
    assert resolved is not None
    assert resolved.value_objects == (occurrence,)
