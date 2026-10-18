from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from parallax.core._execution._family import family_view
from parallax.core._execution._keyed_writes import (
    Provenance,
    ResolvedKeyedInsert,
    ResolvedKeyedWriteSource,
)
from parallax.core._execution._unit_work.retain import KeyedWriteRefusalAdvice
from parallax.core.entity import Entity as EntityBase
from parallax.core.entity import lifecycle_state_of
from parallax.core.metamodel import EntityMetadata, Metamodel
from parallax.core.write_plan import ObjectKey
from parallax.snapshot._inspection import (
    RootConformance,
    SnapshotNodeState,
    insertion_of,
    snapshot_state_of,
)
from parallax.snapshot._publication._wire import (
    WireEntity,
    authoring_of,
    read_evidence_of,
    stored_entity_of,
    wire_pin_of,
)

__all__ = [
    "TYPED_KEYED_WRITE_ADVICE",
    "WIRE_KEYED_WRITE_ADVICE",
    "object_key_from_row",
    "resolve_keyed_insert",
    "resolve_keyed_write_source",
]

TYPED_KEYED_WRITE_ADVICE: Final = KeyedWriteRefusalAdvice(
    not_stored="write it with `tx.insert(...)`, or amend or replace a value a `find` returned",
    already_stored="change it with `value.edit(...)` and write it with `tx.amend(...)`",
    repeated_insert=(
        "write the change with `tx.amend(inserted.edit(...))`, where `inserted` is the value "
        "the first insert took"
    ),
)

WIRE_KEYED_WRITE_ADVICE: Final = KeyedWriteRefusalAdvice(
    not_stored=TYPED_KEYED_WRITE_ADVICE.not_stored,
    already_stored="write the change with `tx.wire.amend(value, {...})`",
    repeated_insert=(
        "write the change with `tx.wire.amend(opened, {...})`, where `opened` is the node "
        "the first insert answered"
    ),
)
"""Each repeated-insert repair names the carrier its own opening produced:
``tx.insert`` leaves the caller holding the instance it passed, while
``tx.wire.insert`` answers a frozen node and took a mapping that is no keyed
source. The not-stored repair is one spelling for both interfaces."""


def resolve_keyed_write_source(
    entity: EntityMetadata, source: EntityBase | WireEntity, /
) -> ResolvedKeyedWriteSource:
    """What ``source`` states about the state a keyed write of ``entity``
    revises, read from the carrier its publication or insertion filed.

    A Wire ``source`` must already be recognized as a conforming read node or
    the node a Wire insert answered. The insert-answered node was published by
    no read, so it answers ``"none"`` beside the authority it carries, which
    the insertion's standing lifts exactly as it does for the instance a Typed
    insert took.
    """
    if isinstance(source, WireEntity):
        if stored_entity_of(source) is None:
            return ResolvedKeyedWriteSource(
                entity=entity,
                pin=None,
                read_evidence=None,
                provenance="none",
                advice=WIRE_KEYED_WRITE_ADVICE,
                authoring=authoring_of(source),
            )
        return ResolvedKeyedWriteSource(
            entity=entity,
            pin=wire_pin_of(source),
            read_evidence=read_evidence_of(source),
            provenance="this",
            advice=WIRE_KEYED_WRITE_ADVICE,
        )
    state = snapshot_state_of(source)
    return ResolvedKeyedWriteSource(
        entity=entity,
        pin=None if state is None else state.pin,
        read_evidence=None if state is None else state.read_evidence,
        provenance=_typed_provenance(source, state),
        advice=TYPED_KEYED_WRITE_ADVICE,
        authoring=insertion_of(source),
    )


def resolve_keyed_insert(
    entity: EntityMetadata, value: EntityBase | Mapping[str, object], /
) -> ResolvedKeyedInsert:
    """What ``value`` states about the row an insert of ``entity`` opens.

    A Wire payload has two answers rather than three: a node a read published
    from conforming stored state, or the node an insert answered, is one this
    store published, and anything else is a document a caller built — so it
    must be the original payload, not a captured copy of it. Only the stored
    read node carries a view whose pin the insert judges. A Typed value answers
    as it does for a source-backed write, so an instance carrying insertion
    authority alone reaches the repeated-opening check once its row is
    prepared.
    """
    if isinstance(value, EntityBase):
        state = snapshot_state_of(value)
        return ResolvedKeyedInsert(
            entity=entity,
            pin=None if state is None else state.pin,
            provenance=_typed_provenance(value, state),
            advice=TYPED_KEYED_WRITE_ADVICE,
        )
    if not isinstance(value, WireEntity):
        return ResolvedKeyedInsert(
            entity=entity, pin=None, provenance="none", advice=WIRE_KEYED_WRITE_ADVICE
        )
    stored = stored_entity_of(value) is not None
    return ResolvedKeyedInsert(
        entity=entity,
        pin=wire_pin_of(value) if stored else None,
        provenance="this" if stored or authoring_of(value) is not None else "none",
        advice=WIRE_KEYED_WRITE_ADVICE,
    )


def object_key_from_row(
    entity: EntityMetadata, model: Metamodel, row: Mapping[str, object]
) -> ObjectKey:
    """The object an authored ``row`` of ``entity`` addresses — the same
    :class:`~parallax.core.write_plan.ObjectKey` Read Evidence names its object
    by and `unit_work.object_key` computes at flush, so a verb-time refusal and
    the flush-time settle never name the object two different ways.

    The key keeps the row's own concrete Entity Identity, never
    family-normalized, and pairs the family key's canonical attribute name with
    the value ``row`` states for it. ``row`` comes from the representation's
    own authoring, so this neither acquires nor re-encodes one.
    """
    name = family_view(model, entity).primary_key.identity.name
    return ObjectKey(entity.identity, ((name, row[name]),))


def _typed_provenance(value: EntityBase, state: SnapshotNodeState | None) -> Provenance:
    """Which framework-managed source published Typed ``value``.

    ``state`` is the narrowed answer that authenticates THIS Snapshot
    lifecycle, and its root conformance says whether that lifecycle published
    valid stored Entity State: diagnostic data from an invalid root is ``none``
    whatever it carries. Without it, the un-narrowed lifecycle state separates
    another framework-managed source's value from one no managed source
    produced, and an admitted insertion's authority is no read.
    """
    if state is not None:
        return "this" if state.root_conformance is RootConformance.CONFORMING else "none"
    if lifecycle_state_of(value) is None or insertion_of(value) is not None:
        return "none"
    return "foreign"
