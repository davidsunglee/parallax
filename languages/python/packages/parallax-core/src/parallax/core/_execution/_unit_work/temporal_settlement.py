from __future__ import annotations

from parallax.core._execution._unit_work.flush_facts import FlushFacts
from parallax.core._execution._unit_work.ranges import (
    DeferredRange,
    settle_opening,
    settle_range,
)
from parallax.core._execution._unit_work.write_items import (
    ComposedBitemporalOpening,
    KeyedInsert,
    StateObserved,
    TemporalCoverageAuthority,
    TemporalCoverageWrite,
    TemporalIntent,
    TemporalOrderedWrite,
    is_licensed_by,
)
from parallax.core._execution._unit_work.write_plan import SettledWrite
from parallax.core.internal.base import InternalError
from parallax.core.internal.concurrency import ConcurrencyFacet
from parallax.core.internal.inheritance import InheritanceFacet
from parallax.core.internal.metamodel import CompiledEntity
from parallax.core.internal.planned_step.observe import TemporalObservation
from parallax.core.internal.planned_step.payload import WritePayloadPreparer
from parallax.core.internal.planned_step.planned_rows import WRITE_PLANNING_FAILED, entity_view
from parallax.core.internal.planned_step.steps import PlannedInsert
from parallax.core.internal.planned_step.write_effects import BoundRange, Openings
from parallax.core.internal.temporal_read import Bitemporal, TransactionTimeOnly
from parallax.core.internal.temporal_write.expansion import TemporalFacts, opening, openings

__all__ = ["TemporalSettlement"]


class TemporalSettlement:
    """Write Settlement of every ordered write of a temporal object
    (`m-unit-work`): a range over its existing coverage, a pending Bitemporal
    opening, or a keyed insert's new lineage.

    Built once per accepted Metamodel by the Write Planner, over the
    Inheritance and Concurrency facets it reads and the model's write payload
    preparer, which judges whether produced temporal rows merge. What one
    flush shares arrives with each write it settles.
    """

    __slots__ = ("_families", "_payloads", "_versioning")

    def __init__(
        self,
        families: InheritanceFacet,
        versioning: ConcurrencyFacet,
        payloads: WritePayloadPreparer,
    ) -> None:
        self._families = families
        self._versioning = versioning
        self._payloads = payloads

    def settle(
        self,
        item: TemporalOrderedWrite,
        shape: TransactionTimeOnly | Bitemporal,
        flush: FlushFacts,
    ) -> SettledWrite | DeferredRange:
        """``item``, a write of an object of ``shape``, as the settled write it
        binds now or the deferred range execution binds.

        Reaching a surviving temporal write is what makes the attempt capture
        its instant. Every observation a range holds must be the Temporal
        Observation every close addresses, gates on, and carries state forward
        from, which is refused before the instant is captured.
        """
        intents = _range_intents(item)
        target = item.target
        facts = TemporalFacts(
            entity=target,
            view=entity_view(self._families, target),
            shape=shape,
            instant=flush.instant.value(),
            selection=item.selection,
        )
        if isinstance(item, ComposedBitemporalOpening):
            return self._opening(item, facts, flush)
        if isinstance(item, KeyedInsert):
            return self._insert(item, facts, flush)
        assert intents is not None  # every other temporal write is a range
        return self._range(item, intents, facts, flush)

    def _range(
        self,
        item: TemporalCoverageWrite,
        intents: tuple[TemporalIntent[TemporalCoverageAuthority], ...],
        facts: TemporalFacts,
        flush: FlushFacts,
    ) -> SettledWrite | DeferredRange:
        """``item`` settled as a range over its temporal object's coverage
        (:func:`~parallax.core._execution._unit_work.ranges.settle_range`): a
        range observed inside the predecessors it holds binds them at once,
        and one reaching beyond them reads the rest at execution."""
        entity = item.target
        ranged = settle_range(
            item,
            intents,
            facts=facts,
            read_key=flush.coverage_read_key(
                entity,
                facts.view,
                gated=self._versioning.gates(entity.identity, flush.preference),
            ),
            ownership=flush.ownership,
            audit=flush.audit,
            payloads=self._payloads,
            guards=flush.guards,
        )
        if isinstance(ranged, DeferredRange):
            return ranged
        return SettledWrite.from_bound(ranged, source_evidence=item.source_evidence)

    def _opening(
        self, item: ComposedBitemporalOpening, facts: TemporalFacts, flush: FlushFacts
    ) -> SettledWrite | DeferredRange:
        """A pending Bitemporal insertion and the writes it authorized since,
        settled as the one settled write of new lineages they leave of its
        window, together with any stored coverage a replacement it authorized
        reaches past that window
        (:func:`~parallax.core._execution._unit_work.ranges.settle_opening`):
        bound now, or deferred until execution reads that coverage."""
        entity = item.target
        ranged = settle_opening(
            item,
            facts=facts,
            read_key=flush.coverage_read_key(
                entity,
                facts.view,
                # Only a replacement reaching past the opening reaches stored
                # rows, whose closes the strategy gates.
                gated=item.beyond is not None
                and self._versioning.gates(entity.identity, flush.preference),
            ),
            ownership=flush.ownership,
            audit=flush.audit,
            payloads=self._payloads,
            guards=flush.guards,
        )
        if isinstance(ranged, DeferredRange):
            return ranged
        return SettledWrite.from_bound(ranged, source_evidence=item.source_evidence)

    def _insert(self, item: KeyedInsert, facts: TemporalFacts, flush: FlushFacts) -> SettledWrite:
        """One temporal insert as the new lineage it opens over its prepared
        window, the row recorded under the key it states. Unpacking its one
        row is the last structural check before SQL that a keyed instruction
        on a temporal target is singular."""
        instruction = item.instruction
        (row,) = instruction.rows
        inserts = (
            PlannedInsert(
                entity=facts.entity.identity,
                entries=(
                    flush.audit.finalize_row(opening(facts, row, instruction.valid_time_window)),
                ),
            ),
        )
        return SettledWrite.from_bound(
            BoundRange(steps=inserts, opened=Openings(continued=openings(facts, inserts))),
            source_evidence=item.source_evidence,
        )


def _range_intents(
    item: TemporalOrderedWrite,
) -> tuple[TemporalIntent[TemporalCoverageAuthority], ...] | None:
    """The intents ``item`` answers where it settles as a range over existing
    coverage, or ``None`` for an opening or an insert."""
    if isinstance(item, ComposedBitemporalOpening | KeyedInsert):
        return None
    intents = item.intents
    if any(
        is_licensed_by(intent, StateObserved)
        and not isinstance(intent.authority.retained_observation.evidence, TemporalObservation)
        for intent in intents
    ):
        raise _unobserved_close(item.target)
    return intents


def _unobserved_close(entity: CompiledEntity) -> InternalError:
    return InternalError(
        WRITE_PLANNING_FAILED,
        f"{entity.identity.name!r}: a temporal write of existing coverage closes the "
        "current milestone, and every close requires the Temporal Observation it "
        "addresses, gates on, and carries state forward from (m-unit-work)",
    )
