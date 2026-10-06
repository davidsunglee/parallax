from __future__ import annotations

from dataclasses import dataclass

from parallax.core.metamodel import EntityIdentity
from parallax.core.temporal_read import Edge, TemporalShape, milestone_edge
from parallax.core.write_plan.observe import TemporalObservation, WriteObservation

__all__ = [
    "ObjectKey",
    "ObservedStateKey",
    "TemporalStateKey",
    "VersionedStateKey",
    "observed_state_key",
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
