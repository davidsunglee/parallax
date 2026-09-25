from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from parallax.core import inheritance
from parallax.core.metamodel import (
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    entity_by_name,
)
from parallax.core.temporal_read import Edge, TemporalShape, milestone_edge
from parallax.core.unit_work.instructions import (
    KeyedWrite,
    PreparedKeyedWrite,
    PreparedWrite,
    WriteInstruction,
)
from parallax.core.unit_work.observe import TemporalObservation, WriteObservation

__all__ = [
    "ObjectKey",
    "ObservedStateKey",
    "object_key",
    "observed_state_key",
    "resolve_object_key",
]


@dataclass(frozen=True, slots=True)
class ObjectKey:
    """One object's identity: its Entity and its ordered
    ``(pk-attribute-name, value)`` pairs. The coalescing scope is keyed by it,
    and it is the identity half of every :data:`ObservedStateKey`.

    It is deliberately STATE-independent — no version, no milestone — so it
    addresses the object across its states, which is what write coalescing,
    cancellation, and buffered-insert recognition each ask about.

    ``entity`` is the structured Entity Identity rather than a spelling of one,
    so no producer stringifies an identity it already holds and two entities
    sharing a bare name across namespaces cannot resolve one another's
    observations.
    """

    entity: EntityIdentity
    primary_key: tuple[tuple[str, object], ...]


@dataclass(frozen=True, slots=True)
class VersionedStateKey:
    """One exact observed state of a versioned Non-Temporal object: the object,
    and the optimistic-lock version the read saw it at.

    The version is part of the key rather than payload beside it, so two reads
    that saw two generations of one row address two states and neither can erase
    the other's evidence.
    """

    object: ObjectKey
    version: int


@dataclass(frozen=True, slots=True)
class TemporalStateKey:
    """One exact observed state of a temporal object: the object, and the
    milestone the read saw it at.

    A milestone chain holds more than one row per primary key at a time, so
    identity alone cannot address the evidence a write needs. Two reads of ONE
    milestone at different pins share one coordinate and therefore one state: an
    observation records the row that was read and nothing about the read that
    reached it, so the two are equal.
    """

    object: ObjectKey
    milestone: Edge


type ObservedStateKey = VersionedStateKey | TemporalStateKey
"""What one Write Observation is evidence ABOUT: one exact observed state.

Closed and structural. An insert and an unversioned Non-Temporal write observe
no state and therefore have no Observed State Key at all — the absence is the
missing arm, never a key with an empty coordinate.
"""


def observed_state_key(
    object_key: ObjectKey, observation: WriteObservation, shape: TemporalShape
) -> ObservedStateKey:
    """The exact state ``observation`` is evidence about: ``object_key``
    qualified by the coordinate the observation itself carries.

    The coordinate is derived from the observation's OWN evidence rather than
    supplied beside it, so a recorder cannot file an observation under a state
    other than the one it is recording — the two-sides-agree property holds by
    construction rather than by every recording site being careful.

    ``shape`` is the observed object's family Temporal Shape, whose axis start
    Attributes name the members a temporal coordinate is read from.
    """
    if not isinstance(observation, TemporalObservation):
        return VersionedStateKey(object_key, observation.observed_version)
    return TemporalStateKey(object_key, milestone_edge(shape, observation.predecessor, None))


def object_key(instruction: WriteInstruction | PreparedWrite, model: Metamodel) -> ObjectKey | None:
    """The identity of the single object a keyed write targets, or ``None``.

    Prepared input consumes its retained target Metadata; the raw authored-input utility
    resolves an entity spelling against ``model``. ``None`` results when the instruction
    is not a single-row keyed write, that raw spelling is unresolved, or the row lacks
    every primary-key attribute (a pk-generated insert whose key is entirely
    DB-computed), or when a carried primary-key VALUE is itself a DB-computed
    marker (`m-pk-gen`'s `{computed: ...}` / `{increment: ...}` — a
    marker-shaped pk value has no coalescing identity, exactly like an absent
    one) — an unidentifiable write is never coalesced nor observation-bound.
    """
    if isinstance(instruction, PreparedKeyedWrite):
        return resolve_object_key(instruction, inheritance.view(model))
    if not isinstance(instruction, KeyedWrite) or len(instruction.rows) != 1:
        return None
    entity = entity_by_name(model, instruction.entity)
    if entity is None:
        return None
    return _row_identity(entity, inheritance.view(model), instruction.rows[0])


def resolve_object_key(
    instruction: PreparedWrite, families: inheritance.InheritanceFacet
) -> ObjectKey | None:
    """:func:`object_key` for a caller that already holds the Inheritance Facet.

    The key is the family's: an inheritance participant's key is declared on the
    root alone (m-inheritance "Inherited members"), so the Entity's own
    declarations are wrongly empty for a concrete subtype, and the compiled view
    names the root's key Attribute at every position.
    """
    if not isinstance(instruction, PreparedKeyedWrite) or len(instruction.rows) != 1:
        return None
    return _row_identity(instruction.target, families, instruction.rows[0])


def _row_identity(
    entity: EntityMetadata, families: inheritance.InheritanceFacet, row: Mapping[str, object]
) -> ObjectKey | None:
    """``row``'s Object Key under ``entity`` — the one key derivation both
    entry points share, so the family primary key stays one decision."""
    position = families.entity(entity.identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        raise ValueError(f"{entity.identity.canonical}: the model declares no such entity")
    name = position.primary_key.identity.name
    if name not in row:
        return None
    value = row[name]
    if isinstance(value, Mapping):
        return None
    return ObjectKey(entity.identity, ((name, value),))
