"""Corpus models and keyed updates of them, as grouped effects are formed from."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from parallax.core import inheritance
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Metamodel,
    ValueObjectIdentity,
    entity_by_name,
)
from parallax.core.write_plan.steps import (
    MISSING_TARGET,
    OPTIMISTIC_CONFLICT,
    UNVERSIONED,
    ExactCount,
    KeyTarget,
    PlannedAssignments,
    PlannedUpdate,
    Versioned,
    VersionGate,
)
from tests.unit._corpus_model_support import model

__all__ = ["ACCOUNT", "WALLET", "attribute_identity", "entity_identity", "update"]

WALLET = model("wallet")
ACCOUNT = model("account")


def entity_identity(meta: Metamodel, name: str) -> EntityIdentity:
    entity = entity_by_name(meta, name)
    assert entity is not None
    return entity.identity


def attribute_identity(meta: Metamodel, entity: str, member: str) -> AttributeIdentity:
    position = inheritance.view(meta).entity(entity_identity(meta, entity))
    assert position is not None
    attribute = position.applicable_attribute(member)
    assert attribute is not None
    return attribute.identity


def _value_object(meta: Metamodel, entity: str, member: str) -> ValueObjectIdentity:
    position = inheritance.view(meta).entity(entity_identity(meta, entity))
    assert position is not None
    value_object = position.applicable_value_object(member)
    assert value_object is not None
    return value_object.identity


def update(
    meta: Metamodel,
    entity: str,
    key: object,
    assigned: Mapping[str, object],
    *,
    value_objects: Mapping[str, object] | None = None,
    observed: int | None = None,
    key_members: Sequence[str] = ("id",),
) -> PlannedUpdate:
    """``entity``'s update of ``key`` assigning ``assigned``, gated on version
    ``observed`` and advancing it where given."""
    attributes: dict[AttributeIdentity, object] = {
        attribute_identity(meta, entity, name): value for name, value in assigned.items()
    }
    concurrency = UNVERSIONED
    shortfall = MISSING_TARGET
    if observed is not None:
        version = attribute_identity(meta, entity, "version")
        attributes[version] = observed + 1
        concurrency = Versioned(version, VersionGate(observed))
        shortfall = OPTIMISTIC_CONFLICT
    return PlannedUpdate(
        entity=entity_identity(meta, entity),
        target=KeyTarget(
            key_attributes=tuple(attribute_identity(meta, entity, name) for name in key_members),
            key_values=(cast("tuple[object, ...]", key) if isinstance(key, tuple) else (key,),),
        ),
        assignments=PlannedAssignments(
            attributes=attributes,
            value_objects={
                _value_object(meta, entity, name): value
                for name, value in (value_objects or {}).items()
            },
        ),
        concurrency=concurrency,
        affected_rows=ExactCount(1, shortfall),
    )
