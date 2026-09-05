"""The corpus spelling of an Evolution, over the whole closed vocabulary.

The JSON an `evolution` case asserts is a contract, and the corpus reaches only
the operations its own cases carry. The vocabulary is closed and small, so the
encoder is graded here against one value of every name it can be handed —
including the endpoint facts a delta carries, which are what a case author reads
when comparing an authored expectation against a run.
"""

from __future__ import annotations

from typing import Any

import pytest
from _metamodel_support import identity

from parallax.conformance.evolution_wire import EvolutionSpellingError, evolution_observation
from parallax.core.base import STRING, Decimal
from parallax.core.metamodel import (
    APPLICATION_ASSIGNED,
    COLUMNS,
    MAX,
    NOT_PRIMARY_KEY,
    TABLE_PER_CONCRETE_SUBTYPE,
    AbstractRoot,
    AbstractSubtype,
    AttributeIdentity,
    Cardinality,
    Column,
    ConcreteSubtype,
    DefiningRelationshipDeclaration,
    Document,
    IndexIdentity,
    Multiplicity,
    NullPlacement,
    PersistenceMode,
    PrimaryKey,
    RelationshipIdentity,
    RelationshipJoin,
    RelationshipOrder,
    ReverseRelationshipDeclaration,
    Sequence,
    SortDirection,
    Table,
    TablePerHierarchy,
    TemporalDimension,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)
from parallax.evolution.model_evolution import (
    LOCKING_FALLBACK,
    WRITES_DISABLED,
    AsOfAxisAdded,
    AsOfAxisAltered,
    AsOfAxisRemoved,
    AttributeAdded,
    AttributeAltered,
    AttributeRemoved,
    AttributeWriteCapability,
    CardinalityChanged,
    ComponentsChanged,
    ConcreteSubtypeAdded,
    ConcreteSubtypeRemoved,
    ConcurrencyControlChanged,
    CoordinatedEvolution,
    CoordinationReason,
    CoordinationRequirement,
    DeclarationCollection,
    DeclarationOrderChanged,
    DeletePropagation,
    DeletePropagationChanged,
    DependencyChanged,
    EndAttributeChanged,
    EntityAdded,
    EntityAltered,
    EntityRemoved,
    EntitySelectionFacts,
    EntityWriteShape,
    EvolutionOperation,
    IndexAdded,
    IndexAltered,
    IndexRemoved,
    JoinChanged,
    MaximumLengthChanged,
    MultiplicityChanged,
    NullabilityChanged,
    OccurrenceAdmissibility,
    OptimisticLockingChanged,
    OrderingChanged,
    PersistenceChanged,
    ReadOnlyChanged,
    RelationshipAdded,
    RelationshipAltered,
    RelationshipRemoved,
    RelationshipSelectionFacts,
    ReverseOfChanged,
    ScalarAdmissibility,
    StartAttributeChanged,
    StorageChanged,
    StorageContainerChanged,
    TemporalAxisFacts,
    TransactionTimeGated,
    UnilateralEvolution,
    UniquenessChanged,
    UniqueTuple,
    ValueObjectAttributeAdded,
    ValueObjectAttributeAltered,
    ValueObjectAttributeRemoved,
    ValueObjectOccurrenceAdded,
    ValueObjectOccurrenceAltered,
    ValueObjectOccurrenceRemoved,
    VersionGated,
    WritesEnabled,
)

_ORDER = identity("Order")
_PAYMENT = identity("Payment")
_ORDER_SPELLING = "parallax.test.Order"
_PAYMENT_SPELLING = "parallax.test.Payment"

_ID = AttributeIdentity(_ORDER, "id")
_SKU = AttributeIdentity(_ORDER, "sku")
_FROM = AttributeIdentity(_ORDER, "fromZ")
_THRU = AttributeIdentity(_ORDER, "thruZ")
_ITEMS = RelationshipIdentity(_ORDER, "items")
_PEER = RelationshipIdentity(_PAYMENT, "orders")
_ADDRESS = ValueObjectIdentity(_ORDER, ("address",))
_GEO = ValueObjectIdentity(_ORDER, ("address", "geo"))
_CITY = ValueObjectAttributeIdentity(_ADDRESS, "city")
_INDEX = IndexIdentity(_ORDER, "orderSku")
DECIMAL_18_2 = Decimal(18, 2)


def _spelled(*operations: EvolutionOperation) -> list[dict[str, Any]]:
    """``operations`` as the corpus spells them, through the whole encoder."""
    observation = evolution_observation(
        UnilateralEvolution(
            earlier=None,
            later=_MODEL,
            operations=operations,
            behavioral_impacts=(),
            overlap_visible_operations=operations,
        )
    )
    assert observation["overlapVisibleOperations"] == observation["operations"]
    return observation["operations"]


# The encoder reads no model: an Evolution's endpoints are the caller's, and the
# spelling is a pure function of the identities and values the operations carry.
_MODEL: Any = None


def test_the_encoder_spells_every_entity_level_operation() -> None:
    assert _spelled(
        EntityAdded(_ORDER),
        EntityRemoved(_PAYMENT),
        ConcreteSubtypeAdded(_ORDER),
        ConcreteSubtypeRemoved(_PAYMENT),
        EntityAltered(
            _ORDER,
            (
                StorageContainerChanged(None, Table("orders")),
                PersistenceChanged(PersistenceMode.READ_WRITE, PersistenceMode.READ_ONLY),
            ),
        ),
    ) == [
        {"kind": "EntityAdded", "entity": _ORDER_SPELLING},
        {"kind": "EntityRemoved", "entity": _PAYMENT_SPELLING},
        {"kind": "ConcreteSubtypeAdded", "entity": _ORDER_SPELLING},
        {"kind": "ConcreteSubtypeRemoved", "entity": _PAYMENT_SPELLING},
        {
            "kind": "EntityAltered",
            "entity": _ORDER_SPELLING,
            "deltas": [
                {"kind": "StorageContainerChanged", "earlier": None, "later": "orders"},
                {
                    "kind": "PersistenceChanged",
                    "earlier": "read-write",
                    "later": "read-only",
                },
            ],
        },
    ]


def test_the_encoder_spells_every_attribute_operation() -> None:
    assert _spelled(
        AttributeAdded(_ID),
        AttributeRemoved(_SKU),
        AttributeAltered(
            _SKU,
            (
                StorageChanged(Column("sku"), Column("stock_keeping_unit")),
                NullabilityChanged(False, True),
                MaximumLengthChanged(32, None),
                ReadOnlyChanged(True, False),
                OptimisticLockingChanged(False, True),
            ),
        ),
    ) == [
        {"kind": "AttributeAdded", "attribute": f"{_ORDER_SPELLING}.id"},
        {"kind": "AttributeRemoved", "attribute": f"{_ORDER_SPELLING}.sku"},
        {
            "kind": "AttributeAltered",
            "attribute": f"{_ORDER_SPELLING}.sku",
            "deltas": [
                {"kind": "StorageChanged", "earlier": "sku", "later": "stock_keeping_unit"},
                {"kind": "NullabilityChanged", "earlier": False, "later": True},
                {"kind": "MaximumLengthChanged", "earlier": 32, "later": None},
                {"kind": "ReadOnlyChanged", "earlier": True, "later": False},
                {"kind": "OptimisticLockingChanged", "earlier": False, "later": True},
            ],
        },
    ]


def test_the_encoder_spells_every_value_object_operation() -> None:
    assert _spelled(
        ValueObjectOccurrenceAdded(_ADDRESS),
        ValueObjectOccurrenceRemoved(_GEO),
        ValueObjectOccurrenceAltered(
            _ADDRESS, (MultiplicityChanged(Multiplicity.ONE, Multiplicity.MANY),)
        ),
        ValueObjectAttributeAdded(_CITY),
        ValueObjectAttributeRemoved(_CITY),
        ValueObjectAttributeAltered(_CITY, (NullabilityChanged(True, False),)),
    ) == [
        {"kind": "ValueObjectOccurrenceAdded", "valueObject": f"{_ORDER_SPELLING}.address"},
        {
            "kind": "ValueObjectOccurrenceRemoved",
            "valueObject": f"{_ORDER_SPELLING}.address.geo",
        },
        {
            "kind": "ValueObjectOccurrenceAltered",
            "valueObject": f"{_ORDER_SPELLING}.address",
            "deltas": [{"kind": "MultiplicityChanged", "earlier": "one", "later": "many"}],
        },
        {
            "kind": "ValueObjectAttributeAdded",
            "valueObjectAttribute": f"{_ORDER_SPELLING}.address.city",
        },
        {
            "kind": "ValueObjectAttributeRemoved",
            "valueObjectAttribute": f"{_ORDER_SPELLING}.address.city",
        },
        {
            "kind": "ValueObjectAttributeAltered",
            "valueObjectAttribute": f"{_ORDER_SPELLING}.address.city",
            "deltas": [{"kind": "NullabilityChanged", "earlier": True, "later": False}],
        },
    ]


def test_the_encoder_spells_every_relationship_operation() -> None:
    order = RelationshipOrder(_SKU, SortDirection.DESCENDING, NullPlacement.NULLS_FIRST)
    assert _spelled(
        RelationshipAdded(_ITEMS),
        RelationshipRemoved(_ITEMS),
        RelationshipAltered(
            _ITEMS,
            (
                CardinalityChanged(Cardinality.ONE_TO_ONE, Cardinality.MANY_TO_ONE),
                JoinChanged(RelationshipJoin(_ID, _SKU), RelationshipJoin(_SKU, _ID)),
                ReverseOfChanged(_PEER, _PEER),
                DependencyChanged(False, True),
                OrderingChanged((), (order,)),
            ),
        ),
    ) == [
        {"kind": "RelationshipAdded", "relationship": f"{_ORDER_SPELLING}.items"},
        {"kind": "RelationshipRemoved", "relationship": f"{_ORDER_SPELLING}.items"},
        {
            "kind": "RelationshipAltered",
            "relationship": f"{_ORDER_SPELLING}.items",
            "deltas": [
                {
                    "kind": "CardinalityChanged",
                    "earlier": "one-to-one",
                    "later": "many-to-one",
                },
                {
                    "kind": "JoinChanged",
                    "earlier": {
                        "source": f"{_ORDER_SPELLING}.id",
                        "target": f"{_ORDER_SPELLING}.sku",
                    },
                    "later": {
                        "source": f"{_ORDER_SPELLING}.sku",
                        "target": f"{_ORDER_SPELLING}.id",
                    },
                },
                {
                    "kind": "ReverseOfChanged",
                    "earlier": f"{_PAYMENT_SPELLING}.orders",
                    "later": f"{_PAYMENT_SPELLING}.orders",
                },
                {"kind": "DependencyChanged", "earlier": False, "later": True},
                {
                    "kind": "OrderingChanged",
                    "earlier": [],
                    "later": [
                        {
                            "attribute": f"{_ORDER_SPELLING}.sku",
                            "direction": "desc",
                            "nulls": "first",
                        }
                    ],
                },
            ],
        },
    ]


def test_the_encoder_spells_every_axis_and_index_operation() -> None:
    assert _spelled(
        AsOfAxisAdded(_ORDER, TemporalDimension.VALID_TIME),
        AsOfAxisRemoved(_ORDER, TemporalDimension.TRANSACTION_TIME),
        AsOfAxisAltered(
            _ORDER,
            TemporalDimension.VALID_TIME,
            (StartAttributeChanged(_FROM, _ID), EndAttributeChanged(_THRU, _SKU)),
        ),
        IndexAdded(_INDEX),
        IndexRemoved(_INDEX),
        IndexAltered(
            _INDEX,
            (ComponentsChanged((_ID,), (_SKU, _ID)), UniquenessChanged(False, True)),
        ),
    ) == [
        {"kind": "AsOfAxisAdded", "entity": _ORDER_SPELLING, "dimension": "valid-time"},
        {
            "kind": "AsOfAxisRemoved",
            "entity": _ORDER_SPELLING,
            "dimension": "transaction-time",
        },
        {
            "kind": "AsOfAxisAltered",
            "entity": _ORDER_SPELLING,
            "dimension": "valid-time",
            "deltas": [
                {
                    "kind": "StartAttributeChanged",
                    "earlier": f"{_ORDER_SPELLING}.fromZ",
                    "later": f"{_ORDER_SPELLING}.id",
                },
                {
                    "kind": "EndAttributeChanged",
                    "earlier": f"{_ORDER_SPELLING}.thruZ",
                    "later": f"{_ORDER_SPELLING}.sku",
                },
            ],
        },
        {"kind": "IndexAdded", "index": f"{_ORDER_SPELLING}.orderSku"},
        {"kind": "IndexRemoved", "index": f"{_ORDER_SPELLING}.orderSku"},
        {
            "kind": "IndexAltered",
            "index": f"{_ORDER_SPELLING}.orderSku",
            "deltas": [
                {
                    "kind": "ComponentsChanged",
                    "earlier": [f"{_ORDER_SPELLING}.id"],
                    "later": [f"{_ORDER_SPELLING}.sku", f"{_ORDER_SPELLING}.id"],
                },
                {"kind": "UniquenessChanged", "earlier": False, "later": True},
            ],
        },
    ]


@pytest.mark.parametrize(
    ("owner", "spelling"),
    [(_ORDER, _ORDER_SPELLING), (_ADDRESS, f"{_ORDER_SPELLING}.address")],
    ids=["entity-owner", "value-object-owner"],
)
def test_the_encoder_spells_a_reordered_collection(owner: Any, spelling: str) -> None:
    assert _spelled(
        DeclarationOrderChanged(
            DeclarationCollection.ENTITY_ATTRIBUTES, owner, (_ID, _SKU), (_SKU, _ID)
        )
    ) == [
        {
            "kind": "DeclarationOrderChanged",
            "collection": "entityAttributes",
            "owner": spelling,
            "earlier": [f"{_ORDER_SPELLING}.id", f"{_ORDER_SPELLING}.sku"],
            "later": [f"{_ORDER_SPELLING}.sku", f"{_ORDER_SPELLING}.id"],
        }
    ]


@pytest.mark.parametrize(
    ("declaration", "spelling"),
    [
        (_ITEMS, f"{_ORDER_SPELLING}.items"),
        (_INDEX, f"{_ORDER_SPELLING}.orderSku"),
        (_CITY, f"{_ORDER_SPELLING}.address.city"),
        (_ADDRESS, f"{_ORDER_SPELLING}.address"),
    ],
    ids=["relationship", "index", "value-object-attribute", "value-object"],
)
def test_a_reordered_collection_spells_every_declaration_identity_kind(
    declaration: Any, spelling: str
) -> None:
    operation = DeclarationOrderChanged(
        DeclarationCollection.ENTITY_INDICES, _ORDER, (declaration,), (declaration,)
    )
    assert _spelled(operation)[0]["earlier"] == [spelling]


def test_an_impact_names_its_scope_by_the_kind_of_identity_it_is() -> None:
    # One dotted spelling is a legal Attribute, Relationship, and Value Object
    # reference alike, and an impact's own kind does not decide which, so the
    # scope is a single-key object naming the kind.
    impacts = evolution_observation(
        UnilateralEvolution(
            earlier=None,
            later=_MODEL,
            operations=(RelationshipRemoved(_ITEMS),),
            behavioral_impacts=(
                ConcurrencyControlChanged(
                    scope=_ORDER,
                    earlier=VersionGated(_ID),
                    later=VersionGated(_SKU),
                    caused_by=(RelationshipRemoved(_ITEMS),),
                ),
                DeletePropagationChanged(
                    scope=_ITEMS,
                    earlier=DeletePropagation.PROPAGATES,
                    later=DeletePropagation.DOES_NOT_PROPAGATE,
                    caused_by=(RelationshipRemoved(_ITEMS),),
                ),
            ),
            overlap_visible_operations=(),
        )
    )["behavioralImpacts"]
    assert [impact["scope"] for impact in impacts] == [
        {"entity": _ORDER_SPELLING},
        {"relationship": f"{_ORDER_SPELLING}.items"},
    ]
    assert impacts[1]["kind"] == "DeletePropagationChanged"
    assert impacts[1]["earlier"] == "Propagates"
    assert impacts[1]["causedBy"] == [
        {"kind": "RelationshipRemoved", "relationship": f"{_ORDER_SPELLING}.items"}
    ]


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        (_ID, {"attribute": f"{_ORDER_SPELLING}.id"}),
        (_ADDRESS, {"valueObject": f"{_ORDER_SPELLING}.address"}),
        (_CITY, {"valueObjectAttribute": f"{_ORDER_SPELLING}.address.city"}),
    ],
    ids=["attribute", "value-object", "value-object-attribute"],
)
def test_every_member_scope_kind_has_its_own_spelling(scope: Any, expected: dict[str, str]) -> None:
    impact = ConcurrencyControlChanged(
        scope=scope, earlier=_MODEL, later=_MODEL, caused_by=(EntityAdded(_ORDER),)
    )
    observed = evolution_observation(
        UnilateralEvolution(
            earlier=None,
            later=_MODEL,
            operations=(EntityAdded(_ORDER),),
            behavioral_impacts=(impact,),
            overlap_visible_operations=(),
        )
    )
    assert observed["behavioralImpacts"][0]["scope"] == expected


def test_a_coordinated_evolution_spells_its_requirements_and_names_no_overlap() -> None:
    observed = evolution_observation(
        CoordinatedEvolution(
            earlier=_MODEL,
            later=_MODEL,
            operations=(EntityRemoved(_ORDER),),
            behavioral_impacts=(),
            coordination_requirements=(
                CoordinationRequirement(
                    EntityRemoved(_ORDER),
                    (
                        CoordinationReason.AUTHORING_SURFACE_CHANGE_REQUIRED,
                        CoordinationReason.DATABASE_MIGRATION_REQUIRED,
                    ),
                ),
            ),
        )
    )
    assert observed["kind"] == "coordinated"
    assert observed["overlapVisibleOperations"] == []
    assert observed["coordinationRequirements"] == [
        {
            "operation": {"kind": "EntityRemoved", "entity": _ORDER_SPELLING},
            "reasons": ["AuthoringSurfaceChangeRequired", "DatabaseMigrationRequired"],
        }
    ]


def test_a_fact_outside_the_spelled_shapes_is_refused_rather_than_guessed() -> None:
    # An authored expectation compares against this spelling exactly, so a value
    # the encoder has no spelling for must not be rendered as whatever `repr`
    # happens to say about it.
    refused = UnilateralEvolution(
        earlier=None,
        later=_MODEL,
        operations=(AttributeAltered(_ID, (NullabilityChanged(object(), False),)),),  # pyright: ignore[reportArgumentType]
        behavioral_impacts=(),
        overlap_visible_operations=(),
    )
    with pytest.raises(EvolutionSpellingError, match="no corpus spelling"):
        evolution_observation(refused)


def test_an_unspellable_declaration_or_scope_is_refused_the_same_way() -> None:
    reorder = DeclarationOrderChanged(
        DeclarationCollection.ENTITY_ATTRIBUTES,
        _ORDER,
        (object(),),  # pyright: ignore[reportArgumentType]
        (),
    )
    with pytest.raises(EvolutionSpellingError, match="no declaration spelling"):
        _spelled(reorder)
    impact = ConcurrencyControlChanged(
        scope=object(),  # pyright: ignore[reportArgumentType]
        earlier=_MODEL,
        later=_MODEL,
        caused_by=(),
    )
    with pytest.raises(EvolutionSpellingError, match="no scope spelling"):
        evolution_observation(
            UnilateralEvolution(
                earlier=None,
                later=_MODEL,
                operations=(),
                behavioral_impacts=(impact,),
                overlap_visible_operations=(),
            )
        )


def test_a_plain_integer_fact_survives_the_closed_vocabulary_lookup() -> None:
    # Every closed vocabulary the encoder spells is an enum over ints, so the
    # integer arm has to run AFTER them or a maximum length would be read as one.
    assert _spelled(AttributeAltered(_ID, (MaximumLengthChanged(64, 128),)))[0]["deltas"] == [
        {"kind": "MaximumLengthChanged", "earlier": 64, "later": 128}
    ]


_ROOT = identity("Instrument")
_SEQUENCE = Sequence("order_seq", batch_size=10, initial_value=5, increment_size=2)
_JOIN = RelationshipJoin(_ID, _SKU)
_TERM = RelationshipOrder(_SKU, SortDirection.ASCENDING, NullPlacement.NULLS_LAST)
_TERM_SPELLING = {
    "attribute": f"{_ORDER_SPELLING}.sku",
    "direction": "asc",
    "nulls": "last",
}
_JOIN_SPELLING = {"source": f"{_ORDER_SPELLING}.id", "target": f"{_ORDER_SPELLING}.sku"}


@pytest.mark.parametrize(
    ("fact", "expected"),
    [
        (_ORDER, _ORDER_SPELLING),
        (COLUMNS, "columns"),
        (Document(Column("doc")), {"document": {"column": "doc"}}),
        (NOT_PRIMARY_KEY, False),
        (PrimaryKey(APPLICATION_ASSIGNED), {"generation": "application-assigned"}),
        (PrimaryKey(MAX), {"generation": "max"}),
        (
            PrimaryKey(_SEQUENCE),
            {
                "generation": {
                    "strategy": "sequence",
                    "name": "order_seq",
                    "batchSize": 10,
                    "initialValue": 5,
                    "incrementSize": 2,
                }
            },
        ),
        (
            AbstractRoot(TablePerHierarchy("kind")),
            {"role": "root", "strategy": "table-per-hierarchy", "tag": {"column": "kind"}},
        ),
        (
            AbstractRoot(TABLE_PER_CONCRETE_SUBTYPE),
            {"role": "root", "strategy": "table-per-concrete-subtype"},
        ),
        (
            AbstractSubtype(_ROOT),
            {"role": "abstract-subtype", "parent": "parallax.test.Instrument"},
        ),
        (
            ConcreteSubtype(_ROOT),
            {"role": "concrete-subtype", "parent": "parallax.test.Instrument"},
        ),
        (
            ConcreteSubtype(_ROOT, "BOND"),
            {
                "role": "concrete-subtype",
                "parent": "parallax.test.Instrument",
                "tag": {"value": "BOND"},
            },
        ),
        (_JOIN, _JOIN_SPELLING),
        (_TERM, _TERM_SPELLING),
        (
            DefiningRelationshipDeclaration(
                _ITEMS, Cardinality.ONE_TO_MANY, _JOIN, dependent=True, order_by=(_TERM,)
            ),
            {
                "name": "items",
                "cardinality": "one-to-many",
                "join": _JOIN_SPELLING,
                "dependent": True,
                "orderBy": [_TERM_SPELLING],
            },
        ),
        (
            ReverseRelationshipDeclaration(_ITEMS, _PEER, (_TERM,)),
            {
                "name": "items",
                "reverseOf": f"{_PAYMENT_SPELLING}.orders",
                "orderBy": [_TERM_SPELLING],
            },
        ),
        (UniqueTuple((_ID, _SKU)), [f"{_ORDER_SPELLING}.id", f"{_ORDER_SPELLING}.sku"]),
        (
            ScalarAdmissibility(STRING, nullable=True, max_length=64),
            {"type": "string", "nullable": True, "maxLength": 64},
        ),
        (OccurrenceAdmissibility(nullable=False), {"nullable": False}),
        (LOCKING_FALLBACK, {"gate": "LockingFallback"}),
        (VersionGated(_ID), {"gate": "VersionGated", "attribute": f"{_ORDER_SPELLING}.id"}),
        (
            TransactionTimeGated(_FROM),
            {"gate": "TransactionTimeGated", "startAttribute": f"{_ORDER_SPELLING}.fromZ"},
        ),
        (
            TemporalAxisFacts(TemporalDimension.TRANSACTION_TIME, _FROM, _THRU),
            {
                "dimension": "transaction-time",
                "startAttribute": f"{_ORDER_SPELLING}.fromZ",
                "endAttribute": f"{_ORDER_SPELLING}.thruZ",
            },
        ),
        (
            EntitySelectionFacts((_ORDER,), ()),
            {"concreteEntities": [_ORDER_SPELLING], "axes": []},
        ),
        (
            RelationshipSelectionFacts(_PAYMENT, _JOIN),
            {"target": _PAYMENT_SPELLING, "join": _JOIN_SPELLING},
        ),
        (WRITES_DISABLED, {"writes": "Disabled"}),
        (
            WritesEnabled(EntityWriteShape.BITEMPORAL),
            {"writes": "Enabled", "shape": "Bitemporal"},
        ),
        (AttributeWriteCapability.CALLER_INSERT_ONLY, "CallerInsertOnly"),
        (DECIMAL_18_2, "decimal(18,2)"),
    ],
    ids=lambda value: repr(value)[:40],
)
def test_the_encoder_spells_every_endpoint_fact(fact: Any, expected: Any) -> None:
    # A delta is the carrier: `earlier` and `later` are the two positions every
    # accepted value reaches the corpus through, and one arm of the spelling has
    # to answer for each shape the closed vocabulary can hold.
    spelled = _spelled(AttributeAltered(_ID, (NullabilityChanged(fact, fact),)))
    assert spelled[0]["deltas"] == [
        {"kind": "NullabilityChanged", "earlier": expected, "later": expected}
    ]
