"""Corpus models and keyed effects of them, as grouped effects are formed from:
updates and deletes of one key, and closes, guards, revisions, and removals of
one milestone."""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from typing import Final, cast

from parallax.core import inheritance
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Metamodel,
    ValueObjectIdentity,
    entity_by_name,
)
from parallax.core.write_plan.steps import (
    INFINITY,
    MISSING_TARGET,
    OPTIMISTIC_CONFLICT,
    STALE_WRITE,
    SUPERSEDED,
    UNGATED,
    UNVERSIONED,
    ExactCount,
    Finite,
    KeyTarget,
    MilestoneTarget,
    PlannedAssignments,
    PlannedClose,
    PlannedDelete,
    PlannedTemporalGuard,
    PlannedTemporalRemoval,
    PlannedTemporalRevision,
    PlannedUpdate,
    TemporalConcurrency,
    TemporalGate,
    Versioned,
    VersionGate,
)
from tests.unit._corpus_model_support import model

__all__ = [
    "ACCOUNT",
    "BALANCE",
    "CLOSED_AT",
    "COVERAGE_DOCUMENT",
    "INSTRUMENT",
    "POSITION",
    "WALLET",
    "attribute_identity",
    "close",
    "delete",
    "entity_identity",
    "guard",
    "instant",
    "milestone",
    "removal",
    "revision",
    "update",
]

WALLET = model("wallet")
ACCOUNT = model("account")
BALANCE = model("balance")
POSITION = model("position")
INSTRUMENT = model("instrument")
COVERAGE_DOCUMENT = model("shared-coverage-layout-twin-document")


def instant(month: int, *, year: int = 2024) -> dt.datetime:
    return dt.datetime(year, month, 1, tzinfo=dt.UTC)


CLOSED_AT: Final = instant(10)
"""The Transaction Instant every close here assigns."""


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


def delete(
    meta: Metamodel,
    entity: str,
    key: object,
    *,
    observed: int | None = None,
    versioned: bool = False,
    key_members: Sequence[str] = ("id",),
) -> PlannedDelete:
    """``entity``'s delete of ``key``, gated on version ``observed`` where
    given, and otherwise ungated under its version where ``versioned``."""
    concurrency = UNVERSIONED
    shortfall = MISSING_TARGET
    if observed is not None or versioned:
        version = attribute_identity(meta, entity, "version")
        if observed is None:
            concurrency, shortfall = Versioned(version, UNGATED), STALE_WRITE
        else:
            concurrency, shortfall = Versioned(version, VersionGate(observed)), OPTIMISTIC_CONFLICT
    return PlannedDelete(
        entity=entity_identity(meta, entity),
        target=KeyTarget(
            key_attributes=tuple(attribute_identity(meta, entity, name) for name in key_members),
            key_values=(cast("tuple[object, ...]", key) if isinstance(key, tuple) else (key,),),
        ),
        concurrency=concurrency,
        affected_rows=ExactCount(1, shortfall),
    )


def milestone(
    meta: Metamodel,
    entity: str,
    key: object,
    *,
    valid_end: dt.datetime | None = None,
    bitemporal: bool = True,
    key_members: Sequence[str] = ("id",),
) -> MilestoneTarget:
    """The current milestone of ``entity`` ``key``: its Valid-Time end, open
    where ``valid_end`` is ``None``, on a Bitemporal Entity, then its open
    Transaction-Time end."""
    ends: list[tuple[str, object]] = []
    if bitemporal:
        ends.append(("validEnd", INFINITY if valid_end is None else Finite(valid_end)))
    ends.append(("txEnd", INFINITY))
    return MilestoneTarget(
        key_attributes=tuple(attribute_identity(meta, entity, name) for name in key_members),
        key_values=cast("tuple[object, ...]", key) if isinstance(key, tuple) else (key,),
        end_attributes=tuple(attribute_identity(meta, entity, name) for name, _ in ends),
        end_values=cast("tuple[Finite, ...]", tuple(bound for _, bound in ends)),
    )


def _temporal(
    meta: Metamodel, entity: str, observed: dt.datetime | None
) -> tuple[TemporalConcurrency, ExactCount]:
    if observed is None:
        return UNGATED, ExactCount(1, STALE_WRITE)
    gate = TemporalGate(attribute_identity(meta, entity, "txStart"), observed)
    return gate, ExactCount(1, OPTIMISTIC_CONFLICT)


def close(
    meta: Metamodel, entity: str, target: MilestoneTarget, *, observed: dt.datetime | None = None
) -> PlannedClose:
    """The close of ``target`` at :data:`CLOSED_AT`, gated on its observed
    Transaction-Time start where given."""
    concurrency, affected = _temporal(meta, entity, observed)
    return PlannedClose(
        entity=entity_identity(meta, entity),
        target=target,
        assignments=PlannedAssignments({attribute_identity(meta, entity, "txEnd"): CLOSED_AT}),
        cause=SUPERSEDED,
        concurrency=concurrency,
        affected_rows=affected,
    )


def guard(
    meta: Metamodel, entity: str, target: MilestoneTarget, *, observed: dt.datetime
) -> PlannedTemporalGuard:
    gate = TemporalGate(attribute_identity(meta, entity, "txStart"), observed)
    return PlannedTemporalGuard(
        entity=entity_identity(meta, entity),
        target=target,
        concurrency=gate,
        affected_rows=ExactCount(1, OPTIMISTIC_CONFLICT),
    )


def removal(
    meta: Metamodel, entity: str, target: MilestoneTarget, *, observed: dt.datetime | None = None
) -> PlannedTemporalRemoval:
    concurrency, affected = _temporal(meta, entity, observed)
    return PlannedTemporalRemoval(
        entity=entity_identity(meta, entity),
        target=target,
        concurrency=concurrency,
        affected_rows=affected,
    )


def revision(
    meta: Metamodel,
    entity: str,
    target: MilestoneTarget,
    assigned: Mapping[str, object],
    *,
    observed: dt.datetime | None = None,
    document_is_object: bool = True,
) -> PlannedTemporalRevision:
    concurrency, affected = _temporal(meta, entity, observed)
    return PlannedTemporalRevision(
        entity=entity_identity(meta, entity),
        target=target,
        assignments=PlannedAssignments(
            {attribute_identity(meta, entity, name): value for name, value in assigned.items()}
        ),
        concurrency=concurrency,
        affected_rows=affected,
        predecessor_document_is_object=document_is_object,
    )
