"""The closed Model Evolution vocabulary: immutability and canonical order.

The values are records with no behavior, so what there is to grade is that each
is genuinely inert and that the one law over them — canonical inspection order —
is the Model Location order `m-metamodel` already owns, applied to every
operation kind rather than to the handful a corpus case happens to reach.
"""

from __future__ import annotations

import dataclasses
import random
from dataclasses import FrozenInstanceError
from typing import Any

import pytest
from _metamodel_support import identity

from parallax.core.base import INT64
from parallax.core.metamodel import (
    AttributeIdentity,
    Column,
    IndexIdentity,
    RelationshipIdentity,
    TemporalDimension,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)
from parallax.evolution.model_evolution import (
    AsOfAxisAdded,
    AsOfAxisAltered,
    AsOfAxisRemoved,
    AttributeAdded,
    AttributeAltered,
    AttributeRemoved,
    ConcreteSubtypeAdded,
    ConcreteSubtypeRemoved,
    CoordinationReason,
    CoordinationRequirement,
    DeclarationCollection,
    DeclarationOrderChanged,
    EndAttributeChanged,
    EntityAdded,
    EntityAltered,
    EntityRemoved,
    EvolutionOperation,
    IndexAdded,
    IndexAltered,
    IndexRemoved,
    NullabilityChanged,
    RelationshipAdded,
    RelationshipAltered,
    RelationshipRemoved,
    StorageChanged,
    StorageContainerChanged,
    TypeChanged,
    UniquenessChanged,
    ValueObjectAttributeAdded,
    ValueObjectAttributeAltered,
    ValueObjectAttributeRemoved,
    ValueObjectOccurrenceAdded,
    ValueObjectOccurrenceAltered,
    ValueObjectOccurrenceRemoved,
    canonical_operation_key,
)

_ORDER = identity("Order")
_PAYMENT = identity("Payment")
_SHIPMENT = identity("Shipment")
_CARD = identity("Card")
_LEDGER = identity("Ledger")
_WIRE = identity("Wire")

_ADDRESS = ValueObjectIdentity(_ORDER, ("address",))
_BILLING = ValueObjectIdentity(_ORDER, ("billing",))
_CONTACT = ValueObjectIdentity(_ORDER, ("contact",))
_NESTED = ValueObjectIdentity(_ORDER, ("address", "geo"))


def _one_of_every_kind() -> tuple[EvolutionOperation, ...]:
    """One operation of every kind the closed algebra admits.

    No two share a logical identity, because add, remove, and alter cannot tie
    at one — which is exactly what lets canonical order carry no operation-kind
    rank. Every member operation sits on one Entity so the member ranks are
    comparable; the entity-level kinds need one Entity each.
    """
    return (
        EntityAdded(_ORDER),
        EntityRemoved(_PAYMENT),
        EntityAltered(_SHIPMENT, (StorageContainerChanged(None, None),)),
        ConcreteSubtypeAdded(_CARD),
        ConcreteSubtypeRemoved(_WIRE),
        AttributeAdded(AttributeIdentity(_ORDER, "added")),
        AttributeRemoved(AttributeIdentity(_ORDER, "removed")),
        AttributeAltered(AttributeIdentity(_ORDER, "altered"), (TypeChanged(INT64, INT64),)),
        ValueObjectOccurrenceAdded(_ADDRESS),
        ValueObjectOccurrenceRemoved(_BILLING),
        ValueObjectOccurrenceAltered(_CONTACT, (StorageChanged(Column("a"), Column("b")),)),
        ValueObjectAttributeAdded(ValueObjectAttributeIdentity(_ADDRESS, "added")),
        ValueObjectAttributeRemoved(ValueObjectAttributeIdentity(_ADDRESS, "removed")),
        ValueObjectAttributeAltered(
            ValueObjectAttributeIdentity(_ADDRESS, "altered"),
            (NullabilityChanged(False, True),),
        ),
        RelationshipAdded(RelationshipIdentity(_ORDER, "added")),
        RelationshipRemoved(RelationshipIdentity(_ORDER, "removed")),
        RelationshipAltered(RelationshipIdentity(_ORDER, "altered"), ()),
        AsOfAxisAdded(_ORDER, TemporalDimension.VALID_TIME),
        AsOfAxisRemoved(_ORDER, TemporalDimension.TRANSACTION_TIME),
        AsOfAxisAltered(
            _LEDGER,
            TemporalDimension.VALID_TIME,
            (
                EndAttributeChanged(
                    AttributeIdentity(_LEDGER, "thru"), AttributeIdentity(_LEDGER, "until")
                ),
            ),
        ),
        IndexAdded(IndexIdentity(_ORDER, "added")),
        IndexRemoved(IndexIdentity(_ORDER, "removed")),
        IndexAltered(IndexIdentity(_ORDER, "altered"), (UniquenessChanged(False, True),)),
        DeclarationOrderChanged(
            DeclarationCollection.ENTITY_ATTRIBUTES,
            _ORDER,
            (AttributeIdentity(_ORDER, "a"), AttributeIdentity(_ORDER, "b")),
            (AttributeIdentity(_ORDER, "b"), AttributeIdentity(_ORDER, "a")),
        ),
    )


def test_every_operation_kind_has_a_witness() -> None:
    # The closed algebra is 24 arms wide, so a witness set that quietly shrinks
    # would leave the ordering law below graded over a subset of it.
    assert len({type(operation) for operation in _one_of_every_kind()}) == 24


@pytest.mark.parametrize(
    "value",
    [
        *_one_of_every_kind(),
        NullabilityChanged(False, True),
        CoordinationRequirement(
            EntityAdded(_ORDER), (CoordinationReason.DATABASE_MIGRATION_REQUIRED,)
        ),
    ],
    ids=lambda value: type(value).__name__,
)
def test_every_value_is_frozen_and_slotted(value: Any) -> None:
    field = next(iter(dataclasses.fields(value))).name
    with pytest.raises(FrozenInstanceError):
        setattr(value, field, None)
    assert not hasattr(value, "__dict__"), "a slotted record carries no instance dict"


def test_canonical_order_is_the_model_location_order() -> None:
    # Entity Identity is the outer key, the member ranks order the positions
    # inside one Entity, and every declaration-order operation follows all of
    # them — the same law `m-metamodel` states over Model Locations.
    ordered = sorted(_one_of_every_kind(), key=canonical_operation_key)
    kinds = [type(operation).__name__ for operation in ordered]
    assert kinds.index("EntityAdded") < kinds.index("AttributeAdded")
    assert kinds.index("AttributeAdded") < kinds.index("RelationshipAdded")
    assert kinds.index("RelationshipAdded") < kinds.index("ValueObjectOccurrenceAdded")
    assert kinds.index("ValueObjectOccurrenceAdded") < kinds.index("ValueObjectAttributeAdded")
    assert kinds.index("ValueObjectAttributeAdded") < kinds.index("AsOfAxisAdded")
    assert kinds.index("AsOfAxisAdded") < kinds.index("IndexAdded")
    assert kinds[-1] == "DeclarationOrderChanged"


def test_the_order_is_stable_under_a_shuffled_input() -> None:
    operations = list(_one_of_every_kind())
    expected = sorted(operations, key=canonical_operation_key)
    shuffled = list(operations)
    random.Random(0).shuffle(shuffled)
    assert sorted(shuffled, key=canonical_operation_key) == expected


def test_valid_time_precedes_transaction_time_at_one_entity() -> None:
    valid = AsOfAxisAdded(_ORDER, TemporalDimension.VALID_TIME)
    transaction = AsOfAxisAdded(_ORDER, TemporalDimension.TRANSACTION_TIME)
    assert canonical_operation_key(valid) < canonical_operation_key(transaction)


def test_a_rename_stays_in_identity_order_rather_than_removal_first() -> None:
    # A rename is one removal and one addition of INDEPENDENT identities, and the
    # order carries no operation-kind rank, so the pair sorts by the names alone.
    removed = AttributeRemoved(AttributeIdentity(_ORDER, "sku"))
    added = AttributeAdded(AttributeIdentity(_ORDER, "code"))
    assert canonical_operation_key(added) < canonical_operation_key(removed)


def test_a_nested_occurrence_sorts_after_its_container() -> None:
    outer = ValueObjectOccurrenceAdded(_ADDRESS)
    inner = ValueObjectOccurrenceAdded(_NESTED)
    assert canonical_operation_key(outer) < canonical_operation_key(inner)


def test_declaration_order_operations_sort_by_owner_then_collection() -> None:
    attribute = AttributeIdentity(_ORDER, "id")
    index = IndexIdentity(_ORDER, "order_sku")
    attributes = DeclarationOrderChanged(
        DeclarationCollection.ENTITY_ATTRIBUTES, _ORDER, (attribute,), (attribute,)
    )
    indices = DeclarationOrderChanged(
        DeclarationCollection.ENTITY_INDICES, _ORDER, (index,), (index,)
    )
    other_owner = DeclarationOrderChanged(DeclarationCollection.ENTITY_ATTRIBUTES, _PAYMENT, (), ())
    nested = DeclarationOrderChanged(
        DeclarationCollection.VALUE_OBJECT_ATTRIBUTES, _ADDRESS, (), ()
    )
    assert canonical_operation_key(attributes) < canonical_operation_key(indices)
    # A Value Object owner sorts at its own containment path, after every
    # collection its owning Entity holds directly.
    assert canonical_operation_key(indices) < canonical_operation_key(nested)
    assert canonical_operation_key(indices) < canonical_operation_key(other_owner)


def test_one_delta_class_serves_every_owner_that_carries_its_name() -> None:
    # `NullabilityChanged` is one class whether it sits on an Attribute, on a
    # Value Object occurrence, or on a Value Object leaf, so the corpus spells
    # the delta the same way everywhere.
    delta = NullabilityChanged(False, True)
    leaf = ValueObjectAttributeIdentity(_ADDRESS, "city")
    assert AttributeAltered(AttributeIdentity(_ORDER, "sku"), (delta,)).deltas[0] is delta
    assert ValueObjectOccurrenceAltered(_ADDRESS, (delta,)).deltas[0] is delta
    assert ValueObjectAttributeAltered(leaf, (delta,)).deltas[0] is delta


def test_an_operation_retains_identities_rather_than_declarations() -> None:
    # An add or remove resolves its full declaration through the retained
    # endpoint, so the operation itself holds nothing that could outlive one.
    attribute = AttributeIdentity(_ORDER, "id")
    added = AttributeAdded(attribute)
    assert added.attribute is attribute
    assert [field.name for field in dataclasses.fields(added)] == ["attribute"]
