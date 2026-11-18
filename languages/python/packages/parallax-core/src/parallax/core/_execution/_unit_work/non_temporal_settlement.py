from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from parallax.core._execution._unit_work._errors import VERSION_UNOBSERVED
from parallax.core._execution._unit_work.flush_facts import FlushFacts
from parallax.core._execution._unit_work.instructions import PreparedKeyedInstruction
from parallax.core._execution._unit_work.strategy import AuditDecoration
from parallax.core._execution._unit_work.write_items import (
    InsertBatch,
    InsertionAuthorized,
    KeyedInsert,
    LicensedWrite,
    NonTemporalOrderedWrite,
    StateObserved,
    UnversionedLocked,
    UnversionedWriteBatch,
    VersionConditioned,
)
from parallax.core._execution._unit_work.write_plan import SettledWrite
from parallax.core.internal.base import InternalError, UsageError
from parallax.core.internal.concurrency import INITIAL_VERSION, ConcurrencyFacet, next_version
from parallax.core.internal.inheritance import InheritanceEntityView, InheritanceFacet
from parallax.core.internal.metamodel import AttributeIdentity, CompiledEntity, EntityIdentity
from parallax.core.internal.planned_step.keys import VersionedObjectStateKey
from parallax.core.internal.planned_step.managed_row import ManagedRow
from parallax.core.internal.planned_step.observe import StateObservation, VersionObservation
from parallax.core.internal.planned_step.planned_rows import (
    WRITE_PLANNING_FAILED,
    entity_view,
    key_target,
    planned_assignments,
    planned_row,
)
from parallax.core.internal.planned_step.steps import (
    FAILED_PRECONDITION,
    NEW_LINEAGE,
    UNGATED,
    UNVERSIONED,
    AffectedRows,
    ExactCount,
    NonTemporalConcurrency,
    PlannedAssignments,
    PlannedDelete,
    PlannedInsert,
    PlannedStep,
    PlannedUpdate,
    Shortfall,
    Versioned,
    VersionGate,
    WriteRow,
    adopt_planned_assignments,
    shortfall_classification,
)
from parallax.core.internal.planned_step.write_effects import BoundRange

__all__ = [
    "NonTemporalSettlement",
    "require_observed_version",
]


@dataclass(frozen=True, slots=True)
class NonTemporalFacts:
    """Every semantic fact one non-temporal mutation settles about its TARGET,
    whatever the verb does to it — decided once per keyed instruction, by Write
    Settlement alone.

    Everything here is a value some producer emitted for THIS mutation: the
    facet's compiled view of the target and the Attribute the Concurrency
    Facet names as its explicit version. No producer is among them, so building a
    step from these facts settles no further decision.

    What is deliberately absent is the row's own observed version: a keyed
    write settles with it, but it is not a fact about the mutation.
    """

    entity: CompiledEntity
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
class Deletion:
    """What a settled non-temporal delete emits: nothing beyond its address.

    A delete assigns no value at all, so its emission carries none — the
    absence is the shape rather than a null field every reader re-checks.
    """


@dataclass(frozen=True, slots=True)
class Revision:
    """What a settled non-temporal update emits: the replacement values every
    row of the mutation writes, and the version Attribute an update against a
    versioned target advances over them."""

    base_assignments: PlannedAssignments
    version: AttributeIdentity | None


type NonTemporalEmission = Deletion | Revision
"""Which non-temporal step one settled mutation emits, and what it assigns.

Decided once per mutation, from the authored verb, by whichever case settled it
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
    key_rows: Sequence[ManagedRow],
    observed_version: int | None,
    affected_rows: AffectedRows,
) -> PlannedStep:
    """The rows ``key_rows`` addresses as the step ``emission`` settled.

    Pure in its settled values: everything it reads was decided by the facts
    Write Settlement settles a mutation through and by the case that settled
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
    base: PlannedAssignments, version: AttributeIdentity | None, observed_version: int | None
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
            version: next_version(observed_version),
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


type _AddressedWrite = (
    UnversionedWriteBatch
    | LicensedWrite[StateObserved | UnversionedLocked | InsertionAuthorized | VersionConditioned]
)
"""A Non-Temporal write of rows that already exist."""


class NonTemporalSettlement:
    """Write Settlement of every ordered write of a Non-Temporal object
    (`m-unit-work`): an insert opens new lineages, and any other write
    revises or deletes existing rows.

    Built once per accepted Metamodel by the Write Planner, over the
    Inheritance and Concurrency facets it reads. What one flush shares
    arrives with each write it settles.
    """

    __slots__ = ("_families", "_versioning")

    def __init__(self, families: InheritanceFacet, versioning: ConcurrencyFacet) -> None:
        self._families = families
        self._versioning = versioning

    def settle(self, item: NonTemporalOrderedWrite, flush: FlushFacts) -> SettledWrite:
        """``item``'s settled steps and completion.

        Its target's facts are settled once, whichever representation the
        write arrived as: which members the family makes applicable, and
        which Attribute (if any) carries the optimistic version. What only a
        write of existing rows settles is added by :meth:`_addressed`.
        """
        entity = item.target
        facts = NonTemporalFacts(
            entity=entity,
            view=entity_view(self._families, entity),
            version_attribute=self._versioning.version_attribute(entity.identity),
        )
        if isinstance(item, KeyedInsert | InsertBatch):
            return SettledWrite.from_bound(
                BoundRange(steps=(_insert(facts, item.instruction, flush.audit),)),
                source_evidence=item.source_evidence,
            )
        return self._addressed(item, facts, flush)

    def _addressed(
        self, item: _AddressedWrite, facts: NonTemporalFacts, flush: FlushFacts
    ) -> SettledWrite:
        """One ordered write of existing objects, one per row: its steps and
        completion.

        A write advances from the version its source observed, or, in place
        of it, from the protected state its source's authority reaches, the
        version this attempt's own writes left a row it inserted at, or the
        version a caller's condition requires; a gate binding that caller's
        condition classifies its shortfall as the condition failing. A
        versioned update advances the state it starts from and a deletion
        destroys every object it addresses; an unversioned write changes each
        object it addresses without advancing anything.
        """
        instruction = item.instruction
        entity = instruction.target
        own_version: int | None = None
        conditioned = False
        observation: StateObservation | None = None
        if isinstance(item, UnversionedWriteBatch):
            objects = item.object_keys
        else:
            objects = (item.object_key,)
            authority = item.authority
            if isinstance(authority, StateObserved):
                observation = authority.retained_observation.evidence
            scope = item.claim_scope
            if isinstance(scope, VersionedObjectStateKey):
                own_version = scope.version
            conditioned = isinstance(authority, VersionConditioned)
        gated = self._versioning.gates(entity.identity, flush.preference)
        addressed = AddressedFacts(
            key_attributes=(facts.view.primary_key.identity,),
            gated=gated,
            shortfall=(
                FAILED_PRECONDITION
                if conditioned and gated
                else shortfall_classification(
                    observing=facts.version_attribute is not None, gated=gated
                )
            ),
        )
        observed_version = (
            _observed_version(entity, instruction, facts.version_attribute, observation)
            if observation is not None or own_version is None
            else None
        )
        if own_version is not None:
            observed_version = own_version
        step = _decorated(
            flush.audit,
            non_temporal_step(
                facts,
                addressed,
                emission=(
                    DELETION
                    if instruction.mutation == "delete"
                    else Revision(
                        _addressed_assignments(addressed, instruction.rows[0]),
                        facts.version_attribute,
                    )
                ),
                key_rows=instruction.rows,
                observed_version=observed_version,
                # One addressed instruction is ONE step however many keys it
                # addresses, so its expectation is the whole batch's (ADR 0044)
                # rather than a per-row one.
                affected_rows=ExactCount(
                    expected=len(instruction.rows), on_shortfall=addressed.shortfall
                ),
            ),
        )
        destroyed = objects if instruction.mutation == "delete" else ()
        if observed_version is None:
            bound = BoundRange(steps=(step,), changed=objects, destroyed=destroyed)
        else:
            (target,) = objects  # an observed version addresses exactly one row
            state = VersionedObjectStateKey(target, observed_version)
            bound = BoundRange(
                steps=(step,),
                changed=(state,),
                advanced=() if destroyed else (state,),
                destroyed=destroyed,
            )
        return SettledWrite.from_bound(bound, source_evidence=item.source_evidence)


def _insert(
    facts: NonTemporalFacts, instruction: PreparedKeyedInstruction, audit: AuditDecoration
) -> PlannedInsert:
    """One keyed insert as its rows, each opening a new lineage.

    An insert observes nothing, gates on nothing, and addresses nothing, so
    the only fact it takes from the mutation beyond its target is the
    version a new lineage opens at — and an unversioned target opens at no
    version, so it asks the strategy for no arithmetic either.
    """
    version = (
        None if facts.version_attribute is None else (facts.version_attribute, INITIAL_VERSION)
    )
    entries = tuple(
        audit.finalize_row(WriteRow(row=planned_row(row, version), origin=NEW_LINEAGE))
        for row in instruction.rows
    )
    return PlannedInsert(entity=facts.entity.identity, entries=entries)


def _addressed_assignments(addressed: AddressedFacts, row: ManagedRow) -> PlannedAssignments:
    """The replacement values an addressed update writes, before its version
    overlay.

    Key members address the write rather than change it, so they never appear
    among the assignments. A multi-row update reaching here is one the batching
    strategy collapsed, and it collapses only a run assigning identical values to
    every key (`m-batch-write` keeps incompatible writes in separate steps), so
    the first row settles the whole step's assignments. Every admitted write
    is single-row, so no multi-row update arrives here any other way.
    """
    index = row.selection.members.index
    keys = 0
    for attribute in addressed.key_attributes:
        keys |= 1 << index[attribute]
    return planned_assignments(row, without=keys)


def _decorated(audit: AuditDecoration, step: PlannedStep) -> PlannedStep:
    """An addressed Non-Temporal step as audit leaves it: an update decorated
    once, a delete as it is."""
    return audit.decorate_update(step) if isinstance(step, PlannedUpdate) else step


def _observed_version(
    entity: CompiledEntity,
    instruction: PreparedKeyedInstruction,
    version_attr: AttributeIdentity | None,
    observation: StateObservation | None,
) -> int | None:
    """The version an addressed write against a versioned row advances
    from, or ``None`` for an unversioned target.

    The observation is required under both strategies, because the
    framework never issues a resolving read on behalf of a keyed write.

    A returned version therefore came off an observed write, which
    wraps exactly one row — so the Key Target the caller builds from
    ``instruction.rows`` is a singleton whenever this returns a version to
    advance from or gate on (`m-unit-work`: a Version Gate requires a
    singleton Key Target). The alternative — one row's observed version
    licensing every key a merged statement addresses — is unconstructable
    rather than merely unreached.

    An unversioned target has no version to advance from AND is entitled to
    no observation at all, so an observation arriving for one is refused
    rather than dropped: this is the model-aware half of the rule
    :class:`~parallax.core._execution._unit_work.write_items.StateObserved`
    delegates here, and discarding the evidence instead would be the
    silently-unobserved mode `m-unit-work` forbids.
    """
    if version_attr is None:
        _require_unobserved(entity, instruction.mutation, observation)
        return None
    return require_observed_version(entity.identity, observation)


def require_observed_version(entity: EntityIdentity, observation: StateObservation | None) -> int:
    """The version a keyed update or delete of an explicitly versioned row of
    ``entity`` advances from; refused with :data:`VERSION_UNOBSERVED` where the
    write reached settlement observing none."""
    if not isinstance(observation, VersionObservation):
        raise UsageError(
            VERSION_UNOBSERVED,
            f"{entity.name}: a keyed update/delete of a versioned row requires the version its "
            "source observed (a prior find) — the framework never issues an implicit "
            "resolving read on behalf of a keyed write",
        )
    return observation.observed_version


def _require_unobserved(
    entity: CompiledEntity, mutation: str, observation: StateObservation | None
) -> None:
    """Refuse ``observation`` when the target it arrived for is entitled to none.

    Reached only once the caller has established that the target is neither
    temporal nor versioned, which is the one shape `m-unit-work` declares
    observationless ("unversioned Non-Temporal writes have no observation",
    absence structural). Whether a write may hold evidence at all needs the
    model, so the admitted write, a keyed
    :class:`~parallax.core._execution._unit_work.write_items.StateObserved`
    write, can only refuse the instruction-local half and
    delegate this half to the model-aware settlement. This is that delegation:
    every write that IS settled crosses it, whatever produced it, so a
    producer that resolves evidence a target cannot carry is told rather than
    quietly stripped.

    Settled is the whole reach of that guarantee. Coalescing and no-op
    elimination run first, and a write they retire — folded into a pending
    insert, cancelled against one, or eliminated as a key-only no-op — is never
    settled at all. Nothing is
    stripped there either: the write itself is gone, so its observation gates,
    advances, and attributes nothing.
    """
    if observation is None:
        return
    raise InternalError(
        WRITE_PLANNING_FAILED,
        f"{entity.identity.name!r}: an unversioned Non-Temporal {mutation!r} carries no Write "
        "Observation, yet one was resolved for it — absence is structural (m-unit-work "
        "'unversioned Non-Temporal writes have no observation'), and settling this write "
        "would discard the evidence rather than gate or advance anything with it",
    )
