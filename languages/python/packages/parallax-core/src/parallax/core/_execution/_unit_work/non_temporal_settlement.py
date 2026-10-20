from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from parallax.core._execution._unit_work.strategy import VersionArithmetic
from parallax.core.inheritance import InheritanceEntityView
from parallax.core.metamodel import AttributeIdentity, EntityMetadata
from parallax.core.write_plan.planned_rows import key_target
from parallax.core.write_plan.steps import (
    UNGATED,
    UNVERSIONED,
    AffectedRows,
    NonTemporalConcurrency,
    PlannedAssignments,
    PlannedDelete,
    PlannedUpdate,
    Shortfall,
    Versioned,
    VersionGate,
    adopt_planned_assignments,
)
from parallax.core.write_plan.steps import PlannedWrite as PlannedStep

__all__ = [
    "DELETION",
    "AddressedFacts",
    "Deletion",
    "NonTemporalEmission",
    "NonTemporalFacts",
    "Revision",
    "VersionOverlay",
    "non_temporal_step",
]


@dataclass(frozen=True, slots=True)
class NonTemporalFacts:
    """Every semantic fact one non-temporal mutation settles about its TARGET,
    whatever the verb does to it — decided once per keyed instruction, by Write
    Settlement alone.

    Everything here is a value some producer emitted for THIS mutation: the
    facet's compiled view of the target and the Attribute the Optimistic Lock
    Facet names as its version source. No producer is among them, so building a
    step from these facts settles no further decision.

    What is deliberately absent is the row's own observed version: a keyed
    write settles with it, but it is not a fact about the mutation.
    """

    entity: EntityMetadata
    view: InheritanceEntityView
    version_attribute: AttributeIdentity | None


@dataclass(frozen=True, slots=True)
class AddressedFacts:
    """What addressing rows that already exist settles, once per non-temporal
    update or delete, by Write Settlement alone.

    An insert opens a new lineage and addresses nothing, so none of this is a
    fact about one: it has no key to address by, nothing observed to gate
    against, and no shortfall a missing row could produce.
    """

    key_attributes: tuple[AttributeIdentity, ...]
    gated: bool
    shortfall: Shortfall


@dataclass(frozen=True, slots=True)
class VersionOverlay:
    """The version Attribute a settled update writes and the arithmetic it
    advances the observed value by.

    Carried by the emission rather than by the target's facts because only an
    update overlays a version: a delete advances nothing, and an unversioned
    update has nothing to advance, so neither obtains the arithmetic.
    """

    attribute: AttributeIdentity
    arithmetic: VersionArithmetic


@dataclass(frozen=True, slots=True)
class Deletion:
    """What a settled non-temporal delete emits: nothing beyond its address.

    A delete assigns no value at all, so its emission carries none — the
    absence is the shape rather than a null field every reader re-checks.
    """


@dataclass(frozen=True, slots=True)
class Revision:
    """What a settled non-temporal update emits: the replacement values every
    row of the mutation writes, and the version overlay an update against a
    versioned target lays over them."""

    base_assignments: PlannedAssignments
    version: VersionOverlay | None


type NonTemporalEmission = Deletion | Revision
"""Which non-temporal step one settled mutation emits, and what it assigns.

Decided once per mutation, from the authored verb, by whichever arm settled it
— which is what leaves the verb behind at settlement: no emitter re-reads it,
and a delete carrying assignments or an update missing them is unconstructable
rather than merely asserted against.
"""

DELETION: Final[Deletion] = Deletion()


def non_temporal_step(
    facts: NonTemporalFacts,
    addressed: AddressedFacts,
    *,
    emission: NonTemporalEmission,
    key_rows: Sequence[Mapping[str, object]],
    observed_version: int | None,
    affected_rows: AffectedRows,
) -> PlannedStep:
    """The rows ``key_rows`` addresses as the step ``emission`` settled.

    Pure in its settled values: everything it reads was decided by the facts
    Write Settlement settles a mutation through and by the arm that settled
    the authored verb, so this reaches no clock, strategy, model, or facet, and
    re-reads no verb.

    An addressed write hands every key it addresses to one call and receives
    ONE aggregate step.
    """
    target = key_target(facts.entity, addressed.key_attributes, key_rows)
    concurrency = _non_temporal_concurrency(
        facts.version_attribute, observed_version, addressed.gated
    )
    match emission:
        case Deletion():
            return PlannedDelete(
                entity=facts.entity.identity,
                target=target,
                concurrency=concurrency,
                affected_rows=affected_rows,
            )
        case Revision(base_assignments, version):
            return PlannedUpdate(
                entity=facts.entity.identity,
                target=target,
                assignments=_versioned_assignments(base_assignments, version, observed_version),
                concurrency=concurrency,
                affected_rows=affected_rows,
            )


def _versioned_assignments(
    base: PlannedAssignments, version: VersionOverlay | None, observed_version: int | None
) -> PlannedAssignments:
    """``base`` with the advanced version at the target's own version Attribute.

    A versioned target advances in BOTH concurrency modes, which is why the new
    version is an assignment rather than a gate member, and the advance happens
    HERE, while an addressed write settles, so no advanced version is ever
    stored.
    """
    if version is None or observed_version is None:
        return base
    return adopt_planned_assignments(
        {
            **base.attributes,
            version.attribute: version.arithmetic.advance(observed_version),
        },
        base.value_objects,
    )


def _non_temporal_concurrency(
    version_attr: AttributeIdentity | None, observed_version: int | None, gated: bool
) -> NonTemporalConcurrency:
    """The settled concurrency decision one addressed non-temporal write
    carries, given the already-decided ``gated`` fact — the version analogue
    of a temporal close's own gate.

    An unversioned target has nothing to gate on. A versioned one binds its
    observation as a gate when gated and records an explicit `Ungated`
    decision otherwise, whose shared read lock is what makes the write correct
    instead.
    """
    if version_attr is None or observed_version is None:
        return UNVERSIONED
    gate = VersionGate(observed_version=observed_version) if gated else UNGATED
    return Versioned(attribute=version_attr, gate=gate)
