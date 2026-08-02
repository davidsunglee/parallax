"""m-relationship: the Rule Set, the symmetric facet, and its typed view."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
from _metamodel_support import Declaration, accepted, attribute, identity, key, source

from _support import fake_metamodel as fake
from parallax.conformance import case_format
from parallax.core._formation_profile import BUILTIN_MANIFEST, BUILTIN_PROFILE, form_metamodel
from parallax.core.base import INT64, STRING
from parallax.core.metamodel import (
    METAMODEL_MODULE,
    NOT_PRIMARY_KEY,
    AbstractSubtype,
    AsOfAxisMetadata,
    AttributeIdentity,
    AttributeLocation,
    AttributeMetadata,
    AttributeReference,
    CandidateMetamodel,
    Cardinality,
    Column,
    CompiledMetadata,
    DefiningRelationshipDeclaration,
    EntityDeclaration,
    EntityIdentity,
    ExactEntityReference,
    IndexMetadata,
    InheritanceMetadata,
    IssueCode,
    Metamodel,
    MetamodelIssue,
    NullPlacement,
    PersistenceMode,
    PrimaryKey,
    RelationshipDeclaration,
    RelationshipIdentity,
    RelationshipJoin,
    RelationshipLocation,
    RelationshipOrder,
    RelationshipReference,
    ReverseRelationshipDeclaration,
    SortDirection,
    StorageContainer,
    StorageLayout,
    Table,
    UnresolvedDefiningRelationshipDeclaration,
    UnresolvedEntityDeclaration,
    UnresolvedRelationshipDeclaration,
    UnresolvedRelationshipJoin,
    UnresolvedRelationshipOrder,
    UnresolvedReverseRelationshipDeclaration,
    ValueObjectOccurrenceDeclaration,
)
from parallax.core.model_formation import (
    MODEL_FORMATION_MODULE,
    MetamodelValidationError,
    ModelCompilerRequirement,
    RequiredRuleSet,
)
from parallax.core.relationship import (
    CARDINALITY_JOIN_MISMATCH,
    DEFINING_DUPLICATE,
    FACET_KEY,
    ISSUE_CODES,
    JOIN_SOURCE_INVALID,
    JOIN_TARGET_INVALID,
    MODEL_COMPILER,
    ORDER_ATTRIBUTE_INVALID,
    ORDER_ON_TO_ONE,
    RELATIONSHIP_MODULE,
    REVERSE_CYCLE,
    REVERSE_INCONSISTENT,
    REVERSE_NOT_DEFINING,
    RULE_SET,
    RelationshipFacet,
    RelationshipMetadata,
    view,
)
from parallax.descriptor._adapter import unresolved_metamodel
from parallax.descriptor._serde import parse_document

_ORDER = identity("Order")
_ITEM = identity("Item")
_TAG = identity("Tag")

_CORPUS = sorted(
    (case_format.find_repo_root() / "core" / "compatibility" / "models").glob("*.yaml")
)


# --------------------------------------------------------------------------
# Hand-built formation input.
# --------------------------------------------------------------------------


def _defining(
    owner: EntityIdentity,
    name: str,
    *,
    cardinality: Cardinality = Cardinality.ONE_TO_MANY,
    join_source: AttributeIdentity | None = None,
    target: EntityIdentity,
    target_attribute: str,
    dependent: bool = False,
    order_by: tuple[UnresolvedRelationshipOrder, ...] = (),
) -> UnresolvedDefiningRelationshipDeclaration:
    """One defining declaration whose join source defaults to the owner's key."""
    return UnresolvedDefiningRelationshipDeclaration(
        identity=RelationshipIdentity(owner, name),
        cardinality=cardinality,
        join=UnresolvedRelationshipJoin(
            source=AttributeIdentity(owner, "id") if join_source is None else join_source,
            target=AttributeReference(ExactEntityReference(target), target_attribute),
        ),
        dependent=dependent,
        order_by=order_by,
    )


def _reverse(
    owner: EntityIdentity,
    name: str,
    *,
    peer: EntityIdentity,
    peer_name: str,
    order_by: tuple[UnresolvedRelationshipOrder, ...] = (),
) -> UnresolvedReverseRelationshipDeclaration:
    """One reverse declaration naming its peer exactly."""
    return UnresolvedReverseRelationshipDeclaration(
        identity=RelationshipIdentity(owner, name),
        reverse_of=RelationshipReference(ExactEntityReference(peer), peer_name),
        order_by=order_by,
    )


def _orders(
    order_relationships: tuple[UnresolvedRelationshipDeclaration, ...] = (),
    item_relationships: tuple[UnresolvedRelationshipDeclaration, ...] = (),
) -> tuple[UnresolvedEntityDeclaration, ...]:
    """An Order/Item/Tag model whose relationship declarations the caller supplies."""
    return (
        Declaration(
            identity=_ORDER,
            attributes=(key(_ORDER), attribute(_ORDER, "sku", type=STRING)),
            relationships=order_relationships,
        ),
        Declaration(
            identity=_ITEM,
            attributes=(
                key(_ITEM),
                attribute(_ITEM, "orderId"),
                attribute(_ITEM, "sku", type=STRING),
            ),
            relationships=item_relationships,
        ),
        Declaration(identity=_TAG, attributes=(key(_TAG),)),
    )


_ITEMS = _defining(
    _ORDER,
    "items",
    target=_ITEM,
    target_attribute="orderId",
    dependent=True,
    order_by=(
        UnresolvedRelationshipOrder("sku", SortDirection.DESCENDING),
        UnresolvedRelationshipOrder("id"),
    ),
)
_ORDER_OF_ITEM = _reverse(_ITEM, "order", peer=_ORDER, peer_name="items")


def _issues(*declarations: UnresolvedEntityDeclaration) -> tuple[MetamodelIssue, ...]:
    """The relationship issues a resolvable model is rejected with."""
    return tuple(RULE_SET.validate(accepted(source(*declarations))))


def _codes(*declarations: UnresolvedEntityDeclaration) -> list[IssueCode]:
    return [issue.code for issue in _issues(*declarations)]


def _facet(*declarations: UnresolvedEntityDeclaration) -> RelationshipFacet:
    """The facet a valid model compiles to, through the built-in composition root."""
    return view(form_metamodel(source(*declarations)))


def _direction(facet: RelationshipFacet, target: RelationshipIdentity) -> RelationshipMetadata:
    found = facet.relationship(target)
    assert found is not None, target
    return found


def _directions(facet: RelationshipFacet, *entities: EntityIdentity) -> list[RelationshipMetadata]:
    collected: list[RelationshipMetadata] = []
    for entity in entities:
        found = facet.relationships(entity)
        assert found is not None, entity
        collected.extend(found)
    return collected


def _document(text: str) -> Mapping[str, object]:
    loaded = case_format.safe_load_yaml(text)
    assert isinstance(loaded, dict)
    return cast("Mapping[str, object]", loaded)


def _formed(text: str) -> Metamodel:
    """The accepted model descriptor ``text`` forms into."""
    return form_metamodel(unresolved_metamodel(parse_document(_document(text))))


# --------------------------------------------------------------------------
# Hand-built candidate and accepted metadata.
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Declared:
    """One resolved Entity declaration, as a Candidate Metamodel presents it.

    Foundational resolution rejects an unresolvable reference before any Rule Set
    observes the model, so a rule judging an already-resolved reference cannot
    fire on the fixed resolver's output. The Rule Set is defined over the
    Candidate Metamodel contract rather than over one producer, and this is a
    candidate stating what that producer cannot.
    """

    identity: EntityIdentity
    attributes: tuple[AttributeMetadata, ...] = ()
    relationships: tuple[RelationshipDeclaration, ...] = ()
    container: StorageContainer | None = None
    persistence: PersistenceMode | None = None
    layout: StorageLayout | None = None
    value_objects: tuple[ValueObjectOccurrenceDeclaration, ...] = ()
    as_of_axes: tuple[AsOfAxisMetadata, ...] = ()
    inheritance: InheritanceMetadata | None = None
    indices: tuple[IndexMetadata, ...] = ()


@dataclass(frozen=True, slots=True)
class _Candidate:
    """A Candidate Metamodel over hand-built declarations."""

    entities: tuple[EntityDeclaration, ...]

    def entity(self, identity: EntityIdentity) -> EntityDeclaration | None:
        return next((entity for entity in self.entities if entity.identity == identity), None)


def _candidate(*entities: EntityDeclaration) -> CandidateMetamodel:
    return _Candidate(entities)


def _compiled(*entities: fake.FakeEntity) -> CompiledMetadata:
    """Accepted metadata the alternate implementation states outright."""
    return fake.FakeMetamodel(entities)


def _scalar(entity: EntityIdentity, name: str, column: str, *, primary: bool) -> AttributeMetadata:
    return AttributeMetadata(
        identity=AttributeIdentity(entity, name),
        type=INT64,
        storage=Column(column),
        primary_key=PrimaryKey() if primary else NOT_PRIMARY_KEY,
    )


# --------------------------------------------------------------------------
# The module's formation contract.
# --------------------------------------------------------------------------


def test_the_owned_issue_code_set_is_closed() -> None:
    assert sorted(ISSUE_CODES) == [
        "relationship-cardinality-join-mismatch",
        "relationship-defining-duplicate",
        "relationship-join-source-invalid",
        "relationship-join-target-invalid",
        "relationship-order-attribute-invalid",
        "relationship-order-on-to-one",
        "relationship-reverse-cycle",
        "relationship-reverse-inconsistent",
        "relationship-reverse-not-defining",
    ]
    assert RULE_SET.owner == RELATIONSHIP_MODULE
    assert RULE_SET.issue_codes == ISSUE_CODES


def test_the_builtin_manifest_declares_this_modules_rule_set_and_compiler() -> None:
    (entry,) = (entry for entry in BUILTIN_MANIFEST.entries if entry.owner == RELATIONSHIP_MODULE)
    assert isinstance(entry.rule_set, RequiredRuleSet)
    assert entry.issue_codes == ISSUE_CODES
    assert entry.compiler == ModelCompilerRequirement(FACET_KEY)
    assert entry.required_facets == frozenset()
    assert entry.required_modules == frozenset({METAMODEL_MODULE, MODEL_FORMATION_MODULE})
    assert RULE_SET in BUILTIN_PROFILE.rule_sets
    assert MODEL_COMPILER in BUILTIN_PROFILE.model_compilers
    assert MODEL_COMPILER.owner == RELATIONSHIP_MODULE
    assert MODEL_COMPILER.facet_key == FACET_KEY
    assert MODEL_COMPILER.requires == frozenset()


def test_a_formed_model_serves_its_facet_through_the_typed_view() -> None:
    model = form_metamodel(source(*_orders((_ITEMS,), (_ORDER_OF_ITEM,))))
    assert view(model) is model.facet(FACET_KEY)


# --------------------------------------------------------------------------
# The compiled directions.
# --------------------------------------------------------------------------


def test_a_defining_declaration_keeps_its_own_join_cardinality_and_ordering() -> None:
    facet = _facet(*_orders((_ITEMS,), (_ORDER_OF_ITEM,)))
    assert _direction(facet, RelationshipIdentity(_ORDER, "items")) == RelationshipMetadata(
        identity=RelationshipIdentity(_ORDER, "items"),
        cardinality=Cardinality.ONE_TO_MANY,
        join=RelationshipJoin(
            source=AttributeIdentity(_ORDER, "id"), target=AttributeIdentity(_ITEM, "orderId")
        ),
        reverse="order",
        dependent=True,
        order_by=(
            RelationshipOrder(AttributeIdentity(_ITEM, "sku"), SortDirection.DESCENDING),
            RelationshipOrder(AttributeIdentity(_ITEM, "id"), SortDirection.ASCENDING),
        ),
    )


def test_a_reverse_declaration_swaps_the_join_and_inverts_the_cardinality() -> None:
    facet = _facet(*_orders((_ITEMS,), (_ORDER_OF_ITEM,)))
    assert _direction(facet, RelationshipIdentity(_ITEM, "order")) == RelationshipMetadata(
        identity=RelationshipIdentity(_ITEM, "order"),
        cardinality=Cardinality.MANY_TO_ONE,
        join=RelationshipJoin(
            source=AttributeIdentity(_ITEM, "orderId"), target=AttributeIdentity(_ORDER, "id")
        ),
        reverse="items",
        dependent=True,
        order_by=(),
    )


@pytest.mark.parametrize(
    ("declared", "opposite"),
    [
        (Cardinality.ONE_TO_ONE, Cardinality.ONE_TO_ONE),
        (Cardinality.MANY_TO_ONE, Cardinality.ONE_TO_MANY),
        (Cardinality.ONE_TO_MANY, Cardinality.MANY_TO_ONE),
    ],
    ids=lambda value: value.name,
)
def test_every_cardinality_inverts_into_its_opposite_direction(
    declared: Cardinality, opposite: Cardinality
) -> None:
    """Both keys join, so each variant is identified whichever side is the One."""
    defining = _defining(_ITEM, "order", cardinality=declared, target=_ORDER, target_attribute="id")
    peer = _reverse(_ORDER, "items", peer=_ITEM, peer_name="order")
    facet = _facet(*_orders((peer,), (defining,)))
    assert _direction(facet, RelationshipIdentity(_ITEM, "order")).cardinality is declared
    assert _direction(facet, RelationshipIdentity(_ORDER, "items")).cardinality is opposite


def test_a_one_way_defining_declaration_has_no_reverse_name() -> None:
    facet = _facet(*_orders((_ITEMS,)))
    assert _direction(facet, RelationshipIdentity(_ORDER, "items")).reverse is None


def test_a_direction_carries_no_duplicated_target_foreign_key_or_reverse_pair() -> None:
    assert {field.name for field in dataclasses.fields(RelationshipMetadata)} == {
        "identity",
        "cardinality",
        "join",
        "reverse",
        "dependent",
        "order_by",
    }
    items = _direction(_facet(*_orders((_ITEMS,))), RelationshipIdentity(_ORDER, "items"))
    assert items.join.target.entity == _ITEM


def test_a_reverse_name_is_either_absent_or_nonempty() -> None:
    with pytest.raises(ValueError, match="either absent or nonempty"):
        RelationshipMetadata(
            identity=RelationshipIdentity(_ORDER, "items"),
            cardinality=Cardinality.ONE_TO_MANY,
            join=RelationshipJoin(
                source=AttributeIdentity(_ORDER, "id"), target=AttributeIdentity(_ITEM, "orderId")
            ),
            reverse="",
        )


# --------------------------------------------------------------------------
# Facet lookup and enumeration.
# --------------------------------------------------------------------------


def test_lookup_is_by_exact_identity_and_returns_absence_on_a_miss() -> None:
    facet = _facet(*_orders((_ITEMS,), (_ORDER_OF_ITEM,)))
    assert facet.relationship(RelationshipIdentity(_ORDER, "items")) is not None
    assert facet.relationship(RelationshipIdentity(_ITEM, "items")) is None
    assert facet.relationship(RelationshipIdentity(_ORDER, "absent")) is None


def test_enumeration_distinguishes_an_unknown_entity_from_a_known_empty_one() -> None:
    facet = _facet(*_orders((_ITEMS,), (_ORDER_OF_ITEM,)))
    assert facet.relationships(EntityIdentity("elsewhere", "Order")) is None
    assert facet.relationships(_TAG) == ()
    assert [direction.identity.name for direction in _directions(facet, _ORDER)] == ["items"]


def test_enumeration_preserves_local_declaration_order() -> None:
    tags = _defining(_ORDER, "tags", target=_TAG, target_attribute="id")
    facet = _facet(*_orders((_ITEMS, tags), (_ORDER_OF_ITEM,)))
    assert [direction.identity.name for direction in _directions(facet, _ORDER)] == [
        "items",
        "tags",
    ]


def test_the_facet_offers_no_global_enumeration_or_reverse_pair_lookup() -> None:
    facet = _facet(*_orders((_ITEMS,), (_ORDER_OF_ITEM,)))
    assert {name for name in dir(facet) if not name.startswith("_")} == {
        "relationship",
        "relationships",
    }


# --------------------------------------------------------------------------
# Joins and cardinality.
# --------------------------------------------------------------------------


def test_a_valid_model_reports_nothing() -> None:
    assert _codes(*_orders((_ITEMS,), (_ORDER_OF_ITEM,))) == []


def test_a_join_source_naming_no_local_attribute_is_rejected() -> None:
    absent = _defining(
        _ORDER,
        "items",
        join_source=AttributeIdentity(_ORDER, "missing"),
        target=_ITEM,
        target_attribute="orderId",
    )
    (issue,) = _issues(*_orders((absent,)))
    assert issue.code == JOIN_SOURCE_INVALID
    assert issue.location == RelationshipLocation(RelationshipIdentity(_ORDER, "items"))
    assert issue.related == (AttributeLocation(AttributeIdentity(_ORDER, "missing")),)


def test_a_join_source_addressed_at_another_entity_is_rejected() -> None:
    foreign = _defining(
        _ORDER,
        "items",
        join_source=AttributeIdentity(_TAG, "id"),
        target=_ITEM,
        target_attribute="orderId",
    )
    assert _codes(*_orders((foreign,))) == [JOIN_SOURCE_INVALID]


_INHERITED_SOURCE = """
entities:
  - name: Document
    namespace: parallax.test
    inheritance: { role: root, strategy: table-per-concrete-subtype }
    attributes:
      - { name: id, type: int64, primaryKey: true }
  - name: Memo
    namespace: parallax.test
    table: memo
    inheritance: { role: concrete-subtype, parent: Document }
    relationships:
      - name: tags
        cardinality: one-to-many
        join:
          source: id
          target: { entity: Tag, attribute: memoId }
  - name: Tag
    namespace: parallax.test
    table: tag
    attributes:
      - { name: id, type: int64, primaryKey: true }
      - { name: memoId, type: int64, column: memo_id }
"""
"""A subtype joining on the primary key its family root owns and it never redeclares."""


def test_a_join_source_the_ancestry_declares_is_the_entitys_own() -> None:
    facet = view(_formed(_INHERITED_SOURCE))
    tags = _direction(facet, RelationshipIdentity(identity("Memo"), "tags"))
    assert tags.join.source == AttributeIdentity(identity("Memo"), "id")


def test_a_join_target_naming_no_attribute_of_its_entity_is_rejected() -> None:
    order = _Declared(
        identity=_ORDER,
        attributes=(key(_ORDER),),
        relationships=(
            DefiningRelationshipDeclaration(
                identity=RelationshipIdentity(_ORDER, "items"),
                cardinality=Cardinality.ONE_TO_MANY,
                join=RelationshipJoin(
                    source=AttributeIdentity(_ORDER, "id"),
                    target=AttributeIdentity(_ITEM, "missing"),
                ),
            ),
        ),
    )
    (issue,) = RULE_SET.validate(_candidate(order, _Declared(_ITEM, (key(_ITEM),))))
    assert issue.code == JOIN_TARGET_INVALID
    assert issue.related == (AttributeLocation(AttributeIdentity(_ITEM, "missing")),)


def test_a_cardinality_no_key_side_can_identify_is_rejected() -> None:
    unkeyed = _defining(
        _ORDER,
        "items",
        join_source=AttributeIdentity(_ORDER, "sku"),
        target=_ITEM,
        target_attribute="orderId",
    )
    (issue,) = _issues(*_orders((unkeyed,)))
    assert issue.code == CARDINALITY_JOIN_MISMATCH
    assert issue.related == (
        AttributeLocation(AttributeIdentity(_ORDER, "sku")),
        AttributeLocation(AttributeIdentity(_ITEM, "orderId")),
    )


def test_a_many_to_one_is_identified_by_the_key_on_its_target_side() -> None:
    to_one = _defining(
        _ITEM,
        "order",
        cardinality=Cardinality.MANY_TO_ONE,
        join_source=AttributeIdentity(_ITEM, "orderId"),
        target=_ORDER,
        target_attribute="id",
    )
    assert _codes(*_orders((), (to_one,))) == []


# --------------------------------------------------------------------------
# Reverse pairing.
# --------------------------------------------------------------------------


def test_a_reverse_declaration_naming_another_reverse_is_rejected() -> None:
    chained = _reverse(_TAG, "order", peer=_ITEM, peer_name="order")
    order, item, _ = _orders((_ITEMS,), (_ORDER_OF_ITEM,))
    tag = Declaration(identity=_TAG, attributes=(key(_TAG),), relationships=(chained,))
    (issue,) = _issues(order, item, tag)
    assert issue.code == REVERSE_NOT_DEFINING
    assert issue.location == RelationshipLocation(RelationshipIdentity(_TAG, "order"))
    assert issue.related == (RelationshipLocation(RelationshipIdentity(_ITEM, "order")),)


def test_a_reverse_only_cycle_is_rejected_at_every_declaration_on_it() -> None:
    mutual = _reverse(_ORDER, "items", peer=_ITEM, peer_name="order")
    assert _codes(*_orders((mutual,), (_ORDER_OF_ITEM,))) == [REVERSE_CYCLE, REVERSE_CYCLE]


def test_a_reverse_declaration_naming_itself_is_a_cycle() -> None:
    itself = _reverse(_ORDER, "items", peer=_ORDER, peer_name="items")
    assert _codes(*_orders((itself,))) == [REVERSE_CYCLE]


def test_a_reverse_declaration_whose_peer_is_absent_is_rejected() -> None:
    order = _Declared(
        identity=_ORDER,
        attributes=(key(_ORDER),),
        relationships=(
            ReverseRelationshipDeclaration(
                identity=RelationshipIdentity(_ORDER, "items"),
                reverse_of=RelationshipIdentity(_ITEM, "order"),
            ),
        ),
    )
    (issue,) = RULE_SET.validate(_candidate(order))
    assert issue.code == REVERSE_NOT_DEFINING


def test_a_reverse_declaration_the_defining_direction_does_not_target_is_rejected() -> None:
    misdirected = _reverse(_TAG, "order", peer=_ORDER, peer_name="items")
    order, item, _ = _orders((_ITEMS,))
    tag = Declaration(identity=_TAG, attributes=(key(_TAG),), relationships=(misdirected,))
    (issue,) = _issues(order, item, tag)
    assert issue.code == REVERSE_INCONSISTENT
    assert issue.related == (RelationshipLocation(RelationshipIdentity(_ORDER, "items")),)


def test_several_defining_declarations_may_join_one_attribute_pair() -> None:
    """Two directions over one foreign key are distinct one-way associations.

    Each owns its own ordering, so a second declaration over one Attribute pair
    is a modelling choice rather than a duplicated claim.
    """
    ordered = _defining(
        _ORDER,
        "itemsByName",
        target=_ITEM,
        target_attribute="orderId",
        order_by=(UnresolvedRelationshipOrder("sku"),),
    )
    facet = _facet(*_orders((_ITEMS, ordered)))
    assert [direction.identity.name for direction in _directions(facet, _ORDER)] == [
        "items",
        "itemsByName",
    ]
    assert _direction(facet, RelationshipIdentity(_ORDER, "itemsByName")).order_by == (
        RelationshipOrder(AttributeIdentity(_ITEM, "sku"), SortDirection.ASCENDING),
    )


def test_two_reverse_declarations_naming_one_defining_peer_are_rejected() -> None:
    second = _reverse(_ITEM, "parent", peer=_ORDER, peer_name="items")
    (issue,) = _issues(*_orders((_ITEMS,), (_ORDER_OF_ITEM, second)))
    assert issue.code == DEFINING_DUPLICATE
    assert issue.location == RelationshipLocation(RelationshipIdentity(_ITEM, "parent"))
    assert issue.related == (RelationshipLocation(RelationshipIdentity(_ITEM, "order")),)


# --------------------------------------------------------------------------
# Ordering.
# --------------------------------------------------------------------------


def test_ordering_declared_on_a_to_one_defining_direction_is_rejected() -> None:
    to_one = _defining(
        _ORDER,
        "item",
        cardinality=Cardinality.ONE_TO_ONE,
        target=_ITEM,
        target_attribute="orderId",
        order_by=(UnresolvedRelationshipOrder("sku"),),
    )
    (issue,) = _issues(*_orders((to_one,)))
    assert issue.code == ORDER_ON_TO_ONE
    assert issue.related == ()


def test_ordering_declared_on_a_to_one_reverse_direction_is_rejected() -> None:
    ordered = _reverse(
        _ITEM,
        "order",
        peer=_ORDER,
        peer_name="items",
        order_by=(UnresolvedRelationshipOrder("sku"),),
    )
    assert _codes(*_orders((_ITEMS,), (ordered,))) == [ORDER_ON_TO_ONE]


def test_ordering_on_a_to_many_reverse_direction_is_scoped_to_its_own_target() -> None:
    to_one = _defining(
        _ITEM,
        "order",
        cardinality=Cardinality.MANY_TO_ONE,
        join_source=AttributeIdentity(_ITEM, "orderId"),
        target=_ORDER,
        target_attribute="id",
    )
    ordered = _reverse(
        _ORDER,
        "items",
        peer=_ITEM,
        peer_name="order",
        order_by=(UnresolvedRelationshipOrder("sku", SortDirection.DESCENDING),),
    )
    facet = _facet(*_orders((ordered,), (to_one,)))
    assert _direction(facet, RelationshipIdentity(_ORDER, "items")).order_by == (
        RelationshipOrder(AttributeIdentity(_ITEM, "sku"), SortDirection.DESCENDING),
    )


def test_an_empty_ordering_stays_empty_rather_than_becoming_a_default_term() -> None:
    facet = _facet(*_orders((_defining(_ORDER, "tags", target=_TAG, target_attribute="id"),)))
    assert _direction(facet, RelationshipIdentity(_ORDER, "tags")).order_by == ()


def test_an_authored_ordering_without_a_direction_is_ascending() -> None:
    ordered = _defining(
        _ORDER,
        "items",
        target=_ITEM,
        target_attribute="orderId",
        order_by=(UnresolvedRelationshipOrder("sku"),),
    )
    (term,) = _direction(
        _facet(*_orders((ordered,))), RelationshipIdentity(_ORDER, "items")
    ).order_by
    assert term.direction is SortDirection.ASCENDING


def test_an_authored_ordering_without_a_placement_is_nulls_last() -> None:
    ordered = _defining(
        _ORDER,
        "items",
        target=_ITEM,
        target_attribute="orderId",
        order_by=(UnresolvedRelationshipOrder("sku", SortDirection.DESCENDING),),
    )
    (term,) = _direction(
        _facet(*_orders((ordered,))), RelationshipIdentity(_ORDER, "items")
    ).order_by
    assert term.nulls is NullPlacement.NULLS_LAST


def test_an_authored_nulls_first_placement_survives_compilation_on_either_direction() -> None:
    ordered = _defining(
        _ORDER,
        "items",
        target=_ITEM,
        target_attribute="orderId",
        order_by=(
            UnresolvedRelationshipOrder("sku", nulls=NullPlacement.NULLS_FIRST),
            UnresolvedRelationshipOrder("id", SortDirection.DESCENDING, NullPlacement.NULLS_FIRST),
        ),
    )
    assert _direction(
        _facet(*_orders((ordered,))), RelationshipIdentity(_ORDER, "items")
    ).order_by == (
        RelationshipOrder(
            AttributeIdentity(_ITEM, "sku"), SortDirection.ASCENDING, NullPlacement.NULLS_FIRST
        ),
        RelationshipOrder(
            AttributeIdentity(_ITEM, "id"), SortDirection.DESCENDING, NullPlacement.NULLS_FIRST
        ),
    )


def test_a_reverse_direction_ordering_keeps_its_authored_placement() -> None:
    to_one = _defining(
        _ITEM,
        "order",
        cardinality=Cardinality.MANY_TO_ONE,
        join_source=AttributeIdentity(_ITEM, "orderId"),
        target=_ORDER,
        target_attribute="id",
    )
    ordered = _reverse(
        _ORDER,
        "items",
        peer=_ITEM,
        peer_name="order",
        order_by=(
            UnresolvedRelationshipOrder("sku", SortDirection.DESCENDING, NullPlacement.NULLS_FIRST),
        ),
    )
    assert _direction(
        _facet(*_orders((ordered,), (to_one,))), RelationshipIdentity(_ORDER, "items")
    ).order_by == (
        RelationshipOrder(
            AttributeIdentity(_ITEM, "sku"), SortDirection.DESCENDING, NullPlacement.NULLS_FIRST
        ),
    )


def test_an_ordering_term_naming_no_target_attribute_is_rejected() -> None:
    stray = AttributeIdentity(_TAG, "missing")
    order = _Declared(
        identity=_ORDER,
        attributes=(key(_ORDER),),
        relationships=(
            DefiningRelationshipDeclaration(
                identity=RelationshipIdentity(_ORDER, "items"),
                cardinality=Cardinality.ONE_TO_MANY,
                join=RelationshipJoin(
                    source=AttributeIdentity(_ORDER, "id"),
                    target=AttributeIdentity(_ITEM, "orderId"),
                ),
                order_by=(RelationshipOrder(stray), RelationshipOrder(stray)),
            ),
        ),
    )
    item = _Declared(_ITEM, (key(_ITEM), attribute(_ITEM, "orderId")))
    (issue,) = RULE_SET.validate(_candidate(order, item))
    assert issue.code == ORDER_ATTRIBUTE_INVALID
    assert issue.related == (AttributeLocation(stray),)


def test_a_reverse_directions_ordering_is_scoped_to_the_defining_declarers_entity() -> None:
    order = _Declared(
        identity=_ORDER,
        attributes=(key(_ORDER),),
        relationships=(
            DefiningRelationshipDeclaration(
                identity=RelationshipIdentity(_ORDER, "items"),
                cardinality=Cardinality.MANY_TO_ONE,
                join=RelationshipJoin(
                    source=AttributeIdentity(_ORDER, "id"),
                    target=AttributeIdentity(_ITEM, "id"),
                ),
            ),
        ),
    )
    item = _Declared(
        identity=_ITEM,
        attributes=(key(_ITEM), attribute(_ITEM, "orderId")),
        relationships=(
            ReverseRelationshipDeclaration(
                identity=RelationshipIdentity(_ITEM, "order"),
                reverse_of=RelationshipIdentity(_ORDER, "items"),
                order_by=(RelationshipOrder(AttributeIdentity(_ITEM, "orderId")),),
            ),
        ),
    )
    (issue,) = RULE_SET.validate(_candidate(order, item))
    assert issue.code == ORDER_ATTRIBUTE_INVALID


# --------------------------------------------------------------------------
# Aggregation and the formation gate.
# --------------------------------------------------------------------------


def test_a_family_cycle_still_terminates_the_ancestry_walk() -> None:
    """Family coherence is another module's rule, so this candidate reaches here."""
    left, right = identity("Left"), identity("Right")
    declarations = (
        Declaration(
            identity=left,
            inheritance=AbstractSubtype(ExactEntityReference(right)),
            relationships=(
                _defining(
                    left,
                    "tags",
                    join_source=AttributeIdentity(left, "missing"),
                    target=_TAG,
                    target_attribute="id",
                ),
            ),
        ),
        Declaration(identity=right, inheritance=AbstractSubtype(ExactEntityReference(left))),
        Declaration(identity=_TAG, attributes=(key(_TAG),)),
    )
    assert _codes(*declarations) == [JOIN_SOURCE_INVALID]


def test_every_defect_of_one_model_is_reported_together() -> None:
    unkeyed = _defining(
        _ORDER,
        "items",
        join_source=AttributeIdentity(_ORDER, "sku"),
        target=_ITEM,
        target_attribute="orderId",
    )
    itself = _reverse(_ITEM, "tag", peer=_ITEM, peer_name="tag")
    assert sorted(_codes(*_orders((unkeyed,), (itself,)))) == sorted(
        [CARDINALITY_JOIN_MISMATCH, REVERSE_CYCLE]
    )


def test_a_relationship_defect_fails_formation_before_any_facet_is_compiled() -> None:
    itself = _reverse(_ITEM, "order", peer=_ITEM, peer_name="order")
    with pytest.raises(MetamodelValidationError) as failure:
        form_metamodel(source(*_orders((), (itself,))))
    assert [issue.code for issue in failure.value.issues] == [REVERSE_CYCLE]


def test_compiling_a_reverse_without_its_defining_peer_is_an_impossible_state() -> None:
    order = fake.FakeEntity(
        _ORDER,
        declared_attributes=(key(_ORDER),),
        declared_relationships=(
            ReverseRelationshipDeclaration(
                identity=RelationshipIdentity(_ORDER, "items"),
                reverse_of=RelationshipIdentity(_ITEM, "order"),
            ),
        ),
    )
    with pytest.raises(RuntimeError, match="defining declaration"):
        MODEL_COMPILER.compile(_compiled(order), {})


# --------------------------------------------------------------------------
# Parity between the descriptor-backed and the alternate implementation.
# --------------------------------------------------------------------------


def test_both_implementations_compile_identical_symmetric_metadata() -> None:
    descriptor_backed = view(_formed(fake.PARITY_DESCRIPTOR))
    alternate = MODEL_COMPILER.compile(fake.parity_model(), {})
    entities = (fake.ACCOUNT, fake.AUDIT, fake.ENTRY, fake.LEDGER)
    assert _directions(descriptor_backed, *entities) == _directions(alternate, *entities)
    entries = _direction(descriptor_backed, RelationshipIdentity(fake.ACCOUNT, "entries"))
    assert entries.reverse == "account"
    assert entries.dependent


_ASSOCIATION = """
entities:
  - name: Course
    namespace: parallax.test
    table: course
    attributes:
      - { name: id, type: int64, primaryKey: true }
  - name: Enrollment
    namespace: parallax.test
    table: enrollment
    attributes:
      - { name: id, type: int64, primaryKey: true }
      - { name: studentId, type: int64, column: student_id }
      - { name: courseId, type: int64, column: course_id }
    relationships:
      - name: student
        cardinality: many-to-one
        join:
          source: studentId
          target: { entity: Student, attribute: id }
      - name: course
        cardinality: many-to-one
        join:
          source: courseId
          target: { entity: Course, attribute: id }
  - name: Student
    namespace: parallax.test
    table: student
    attributes:
      - { name: id, type: int64, primaryKey: true }
    relationships:
      - name: enrollments
        reverseOf: Enrollment.student
"""
"""A many-to-many model as its explicit association Entity plus two directions."""


def _association_alternate() -> CompiledMetadata:
    student, course, enrollment = identity("Student"), identity("Course"), identity("Enrollment")
    return _compiled(
        fake.FakeEntity(
            course,
            declared_container=Table("course"),
            declared_attributes=(_scalar(course, "id", "id", primary=True),),
        ),
        fake.FakeEntity(
            enrollment,
            declared_container=Table("enrollment"),
            declared_attributes=(
                _scalar(enrollment, "id", "id", primary=True),
                _scalar(enrollment, "studentId", "student_id", primary=False),
                _scalar(enrollment, "courseId", "course_id", primary=False),
            ),
            declared_relationships=(
                DefiningRelationshipDeclaration(
                    identity=RelationshipIdentity(enrollment, "student"),
                    cardinality=Cardinality.MANY_TO_ONE,
                    join=RelationshipJoin(
                        source=AttributeIdentity(enrollment, "studentId"),
                        target=AttributeIdentity(student, "id"),
                    ),
                ),
                DefiningRelationshipDeclaration(
                    identity=RelationshipIdentity(enrollment, "course"),
                    cardinality=Cardinality.MANY_TO_ONE,
                    join=RelationshipJoin(
                        source=AttributeIdentity(enrollment, "courseId"),
                        target=AttributeIdentity(course, "id"),
                    ),
                ),
            ),
        ),
        fake.FakeEntity(
            student,
            declared_container=Table("student"),
            declared_attributes=(_scalar(student, "id", "id", primary=True),),
            declared_relationships=(
                ReverseRelationshipDeclaration(
                    identity=RelationshipIdentity(student, "enrollments"),
                    reverse_of=RelationshipIdentity(enrollment, "student"),
                ),
            ),
        ),
    )


def test_an_association_entity_navigates_identically_across_implementations() -> None:
    student, course, enrollment = identity("Student"), identity("Course"), identity("Enrollment")
    descriptor_backed = view(_formed(_ASSOCIATION))
    alternate = MODEL_COMPILER.compile(_association_alternate(), {})
    entities = (course, enrollment, student)
    assert _directions(descriptor_backed, *entities) == _directions(alternate, *entities)

    enrollments = _direction(descriptor_backed, RelationshipIdentity(student, "enrollments"))
    assert enrollments.cardinality is Cardinality.ONE_TO_MANY
    assert enrollments.join == RelationshipJoin(
        source=AttributeIdentity(student, "id"),
        target=AttributeIdentity(enrollment, "studentId"),
    )
    assert _direction(descriptor_backed, RelationshipIdentity(enrollment, "course")).reverse is None


# --------------------------------------------------------------------------
# The corpus.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", _CORPUS, ids=lambda path: path.stem)
def test_every_corpus_relationship_compiles_into_exactly_one_direction(path: Path) -> None:
    model = _formed(path.read_text(encoding="utf-8"))
    facet = view(model)
    for entity in model.entities:
        directions = facet.relationships(entity.identity)
        assert directions is not None
        assert [direction.identity for direction in directions] == [
            declaration.identity for declaration in entity.declared_relationships
        ]
        for direction in directions:
            assert facet.relationship(direction.identity) is direction


def test_a_corpus_reverse_pairing_names_both_directions_of_one_association() -> None:
    person = EntityIdentity("parallax.compatibility", "Person")
    passport = EntityIdentity("parallax.compatibility", "Passport")
    path = next(candidate for candidate in _CORPUS if candidate.stem == "person")
    facet = view(_formed(path.read_text(encoding="utf-8")))

    holder = _direction(facet, RelationshipIdentity(passport, "holder"))
    assert holder.reverse == "passport"
    assert holder.cardinality is Cardinality.ONE_TO_ONE
    assert holder.join == RelationshipJoin(
        source=AttributeIdentity(passport, "personId"), target=AttributeIdentity(person, "id")
    )
    assert holder.dependent
    assert _direction(facet, RelationshipIdentity(person, "passport")).reverse == "holder"
