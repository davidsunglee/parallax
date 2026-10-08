from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Final

from parallax.core.base import retain_document_value
from parallax.core.inheritance import InheritanceEntityView
from parallax.core.metamodel import AttributeIdentity, EntityMetadata
from parallax.core.temporal_write.expansion import PredecessorUse, SettledGroup
from parallax.core.unit_work.strategy import AuditDecoration, VersionArithmetic
from parallax.core.write_plan.columns import ColumnSlice
from parallax.core.write_plan.keys import ObservedStateKey
from parallax.core.write_plan.materialized import PredecessorRows
from parallax.core.write_plan.observe import PredecessorRow
from parallax.core.write_plan.plan import ExecutionUnit
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
    assignments_added,
)
from parallax.core.write_plan.steps import PlannedWrite as PlannedStep

__all__ = [
    "DELETION",
    "AddressedFacts",
    "Deletion",
    "NonTemporalEmission",
    "NonTemporalFacts",
    "NonTemporalGroupSegment",
    "Revision",
    "TemporalGroupSegment",
    "VersionOverlay",
    "non_temporal_step",
]


@dataclass(frozen=True, slots=True)
class NonTemporalFacts:
    """Every semantic fact one non-temporal mutation settles about its TARGET,
    whatever the verb does to it — decided once per keyed instruction and once
    per Materialized Write Group, by Write Settlement alone.

    Everything here is a value some producer emitted for THIS mutation: the
    facet's compiled view of the target and the Attribute the Optimistic Lock
    Facet names as its version source. No producer is among them, which is what
    lets a segment hold this by reference and still settle no decision at step
    access.

    What is deliberately absent is any row's own observed version: a keyed
    write's is one value it settles with, a group's is a column it keeps, and
    neither is a fact about the mutation.
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


@dataclass(frozen=True, slots=True)
class NonTemporalGroupSegment:
    """A versioned Materialized Write Group's rows: one Planned Update or
    Planned Delete per resolved row, assembled on demand from already-decided,
    group-wide facts and the group's own compact evidence alone.

    Every semantic decision the group's authored mutation settles — the
    applicable members and version source (``facts``), the family-effective
    primary key, the gate decision and how a shortfall classifies
    (``addressed``), and the assignments and version arithmetic an update lays
    over a row (``emission``) — is resolved once, when the segment is built, and
    reached here through those references. ``step`` only binds one row's own key
    value and observed version into that already-decided shape, through the
    same :func:`non_temporal_step` an eagerly settled keyed write emits from.

    ``versions`` is the group's own evidence column, held by reference: the
    advance is an addition performed at step access, so a row's new version is
    never a second column sized by the resolved row count.

    No group, concurrency mode, Transaction Instant, or strategy object is
    reachable here — every value :meth:`step` reads is either a settled fact or
    an aligned column lookup by row index — and two calls for the same index
    return equal but distinct objects, never a shared mutable flyweight.

    ``audited`` holds, by row, only what a non-neutral audit added to that
    row's update when the group settled.
    """

    facts: NonTemporalFacts
    addressed: AddressedFacts
    key_name: str
    keys: ColumnSlice[object]
    versions: ColumnSlice[int]
    emission: NonTemporalEmission
    affected_rows: AffectedRows
    changed: Iterable[ObservedStateKey]
    audited: Mapping[int, PlannedAssignments] = MappingProxyType({})

    def __len__(self) -> int:
        return len(self.versions)

    def unit(self, end: int) -> ExecutionUnit:
        return ExecutionUnit(end=end, changed=self.changed)

    def step(self, index: int) -> PlannedStep:
        step = self._settled(index)
        stamped = self.audited.get(index)
        if stamped is None or not isinstance(step, PlannedUpdate):
            return step
        return replace(
            step,
            assignments=adopt_planned_assignments(
                {**step.assignments.attributes, **stamped.attributes},
                {**step.assignments.value_objects, **stamped.value_objects},
            ),
        )

    def audited_by(self, audit: AuditDecoration) -> NonTemporalGroupSegment:
        """This segment with what ``audit`` adds to each row's update, decorated
        once per row now rather than when a step is built."""
        added: dict[int, PlannedAssignments] = {}
        for index in range(len(self)):
            update = self._settled(index)
            assert isinstance(update, PlannedUpdate)  # only a revising group is audited
            stamped = assignments_added(
                update.assignments, audit.decorate_update(update).assignments
            )
            if stamped is not None:
                added[index] = stamped
        return replace(self, audited=MappingProxyType(added)) if added else self

    def _settled(self, index: int) -> PlannedStep:
        return non_temporal_step(
            self.facts,
            self.addressed,
            emission=self.emission,
            key_rows=({self.key_name: self.keys[index]},),
            observed_version=self.versions[index],
            affected_rows=self.affected_rows,
        )


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
    the authored verb, so this reaches no clock, strategy,
    model, or facet — and re-reads no verb — and can therefore run either
    eagerly, while the instruction settles, or lazily, when a Materialized Write
    Group's segment is asked for a row.

    Cardinality is the caller's, and it is the one thing the two representations
    do not share: an addressed write hands every key it addresses to one call
    and receives ONE aggregate step, while a group hands one row per call and
    receives one independently gated step per row.
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

    The one version overlay, whichever representation an update arrived as. A
    versioned target advances in BOTH concurrency modes, which is why the new
    version is an assignment rather than a gate member, and the advance happens
    HERE — while an addressed write settles, and when a group's row is asked for
    — so no advanced version is ever stored.
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


@dataclass(frozen=True, slots=True)
class TemporalGroupSegment:
    """A temporal Materialized Write Group's steps, each built on demand from the
    group's own evidence and the immutable ``backing`` its settlement decided.

    The segment owns the evidence and at most one current row's bindable
    predecessor: a row's successors asked for in turn share the one recursively
    immutable copy of its document they bind and patch, and the segment lets go
    of it once the row's last successor is built; asking for another row
    replaces it. A step already returned keeps what it binds, so letting go
    invalidates none, and a step asked for out of order is equal to the one
    built in order though its document may be copied again. The completion
    effects read the backing and evidence alone, never this copy.
    """

    backing: SettledGroup
    evidence: PredecessorRows
    _bindable: tuple[int, PredecessorRow] | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def __len__(self) -> int:
        return len(self.backing)

    def unit(self, end: int) -> ExecutionUnit:
        effects = self.backing.effects(self.evidence)
        return ExecutionUnit(
            end=end,
            changed=effects.changed,
            removed=effects.removed,
            opened=effects.opened,
            derived=effects.derived,
            concludes=effects.concludes,
        )

    def step(self, index: int) -> PlannedStep:
        backing = self.backing
        evidence = self.evidence
        row, slot, use = backing.locate(index)
        values = evidence.rows[row]
        step = backing.step(row, slot, values, self._predecessor(row, values, use))
        if use is PredecessorUse.BINDABLE_LAST:
            object.__setattr__(self, "_bindable", None)
        return step

    def _predecessor(
        self, row: int, values: tuple[object, ...], use: PredecessorUse
    ) -> PredecessorRow | None:
        if use is PredecessorUse.NONE:
            return None
        bindable = self._bindable
        if bindable is not None and bindable[0] == row:
            return bindable[1]
        evidence = self.evidence
        if use is PredecessorUse.MEMBERS:
            return PredecessorRow.over_row(evidence.selection, values, None, evidence.absent)
        document = evidence.document(row)
        predecessor = PredecessorRow.over_row(
            evidence.selection,
            values,
            None if document is None else retain_document_value(document),
            evidence.absent,
        )
        if use is PredecessorUse.BINDABLE:
            object.__setattr__(self, "_bindable", (row, predecessor))
        return predecessor
