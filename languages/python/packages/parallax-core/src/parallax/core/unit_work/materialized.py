from __future__ import annotations

from dataclasses import dataclass

from parallax.core.unit_work.claims import SettledEvidence
from parallax.core.unit_work.columns import ColumnSlice, PredecessorColumns
from parallax.core.unit_work.instructions import (
    INSERT_MUTATIONS,
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    PreparedWrite,
)
from parallax.core.unit_work.observe import WriteObservation
from parallax.core.unit_work.planner import ObjectKey
from parallax.core.unit_work.retain import RetainedObservation

__all__ = [
    "BufferItem",
    "ClaimedKeyedWrite",
    "MaterializedWriteGroup",
    "ObjectClaimedWrite",
    "ObservedKeyedWrite",
    "TemporalColumns",
    "VersionColumns",
    "buffered_instruction",
    "buffered_write",
]


@dataclass(frozen=True, slots=True)
class VersionColumns:
    """One aligned optimistic-lock version value per resolved row."""

    versions: ColumnSlice[int]


@dataclass(frozen=True, slots=True)
class TemporalColumns:
    """Complete predecessor state per resolved row."""

    predecessors: PredecessorColumns


type GroupObservations = VersionColumns | TemporalColumns
"""One authored predicate's aligned observation evidence, one member per
resolved row."""


@dataclass(frozen=True, slots=True)
class MaterializedWriteGroup:
    """One authored predicate's compact, private, indivisible planning input.

    ``key_attributes`` names the canonical primary-key shape once (by declared
    member name, matching the write-instruction row convention); ``key_columns``
    carries one aligned value column per key attribute, in database resolution
    order. Every key and observation column shares the same positive row count.
    The group holds no managed Entity object, no per-row keyed-write wrapper,
    and no per-row Predecessor Row object.

    ``observations`` is not optional, so a group exists only for a target
    entitled to evidence: a predicate write against an unversioned Non-Temporal
    target stays readless and never materializes at all. Which targets those are
    needs the model, so — exactly as for :class:`ObservedKeyedWrite` — the
    model-aware settlement refuses a group whose target turns out to be neither
    versioned nor temporal rather than settling it Unversioned with its
    observation columns dropped.
    """

    mutation: PreparedPredicateWrite
    key_attributes: tuple[str, ...]
    key_columns: tuple[ColumnSlice[object], ...]
    observations: GroupObservations

    def __post_init__(self) -> None:
        if not self.key_attributes:
            raise ValueError("a Materialized Write Group names at least one key Attribute")
        if len(self.key_columns) != len(self.key_attributes):
            raise ValueError(
                "a Materialized Write Group carries one key column per key Attribute: "
                f"expected {len(self.key_attributes)}, got {len(self.key_columns)}"
            )
        length = len(self.key_columns[0])
        if length == 0:
            raise ValueError("a Materialized Write Group addresses at least one row")
        if any(len(column) != length for column in self.key_columns):
            raise ValueError(
                "a Materialized Write Group's key columns share one positive row count"
            )
        if _observation_length(self.observations) != length:
            raise ValueError(
                "a Materialized Write Group's observation column carries the same row count as "
                f"its key columns: expected {length}, got {_observation_length(self.observations)}"
            )

    def __len__(self) -> int:
        return len(self.key_columns[0])


@dataclass(frozen=True, slots=True)
class ObservedKeyedWrite:
    """Carries verb-time evidence through planning without resolving it again.

    A retained ``claim`` is spent only if this write survives to settlement.
    ``restorations`` records members touched and put back: their absent
    assignments must cancel earlier assignments during coalescing.
    """

    instruction: PreparedKeyedWrite
    observation: WriteObservation
    claim: RetainedObservation | None = None
    restorations: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.instruction.mutation in INSERT_MUTATIONS:
            raise ValueError(
                f"an insert carries no Write Observation: `{self.instruction.mutation}` on "
                f"{self.instruction.target.identity.canonical!r} buffers bare "
                "(m-unit-work: absence is structural)"
            )
        if len(self.instruction.rows) != 1:
            raise ValueError(
                "a Write Observation is evidence about one row: "
                f"`{self.instruction.mutation}` on "
                f"{self.instruction.target.identity.canonical!r} addresses "
                f"{len(self.instruction.rows)} rows (m-unit-work: each observed version "
                "belongs to exactly one row)"
            )
        if self.claim is not None and self.claim.evidence is not self.observation:
            raise ValueError(
                "a claim is the retained form of the observation its carrier settles against: "
                f"`{self.instruction.mutation}` on "
                f"{self.instruction.target.identity.canonical!r} was built with a "
                "claim naming other evidence (m-unit-work: one resolution serves the address, "
                "the gate, and the license)"
            )


@dataclass(frozen=True, slots=True)
class ObjectClaimedWrite:
    """Coalesces by object identity, then leaves planning as a bare instruction.

    ``restorations`` has the same cancellation meaning as on ObservedKeyedWrite.
    """

    instruction: PreparedKeyedWrite
    restorations: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.instruction.mutation in INSERT_MUTATIONS:
            raise ValueError(
                f"an insert claims no object: `{self.instruction.mutation}` on "
                f"{self.instruction.target.identity.canonical!r} buffers bare "
                "(m-unit-work: an opening row has no "
                "prior row to claim)"
            )
        if len(self.instruction.rows) != 1:
            raise ValueError(
                "an object claim addresses one object: "
                f"`{self.instruction.mutation}` on "
                f"{self.instruction.target.identity.canonical!r} addresses "
                f"{len(self.instruction.rows)} rows (m-unit-work: a claim is about the object a "
                "write settles against)"
            )


type ClaimedKeyedWrite = ObservedKeyedWrite | ObjectClaimedWrite
"""One keyed write travelling with the claim its verb took for it, at either
scope. The two carriers share what coalescing manipulates — an instruction and
the members its author restored — and differ only in the grain their claims are
taken at."""


def buffered_write(
    instruction: PreparedWrite,
    evidence: SettledEvidence | None,
    *,
    restorations: frozenset[str] = frozenset(),
) -> PreparedWrite | ClaimedKeyedWrite:
    """Retained observations travel with the write so settlement can spend them.

    A bare observation has no retained claim. With no evidence, the instruction
    travels bare and restorations are discarded because it cannot cancel an
    earlier assignment through coalescing.
    """
    if evidence is None:
        return instruction
    if not isinstance(instruction, PreparedKeyedWrite):
        raise TypeError(
            "only a keyed write settles against evidence of its own; a predicate-selected write "
            "materializes to a Materialized Write Group with its own observation columns"
        )
    if isinstance(evidence, ObjectKey):
        return ObjectClaimedWrite(instruction=instruction, restorations=restorations)
    if isinstance(evidence, RetainedObservation):
        return ObservedKeyedWrite(
            instruction=instruction,
            observation=evidence.evidence,
            claim=evidence,
            restorations=restorations,
        )
    return ObservedKeyedWrite(
        instruction=instruction, observation=evidence, restorations=restorations
    )


BufferItem = PreparedWrite | ClaimedKeyedWrite | MaterializedWriteGroup


def buffered_instruction(item: BufferItem) -> PreparedWrite:
    """The write instruction ``item`` carries, unwrapped from any envelope.

    A Materialized Write Group answers the predicate write it materialized,
    which is what dependency ordering ranks it by.
    """
    if isinstance(item, MaterializedWriteGroup):
        return item.mutation
    if isinstance(item, ObservedKeyedWrite | ObjectClaimedWrite):
        return item.instruction
    return item


def _observation_length(observations: GroupObservations) -> int:
    if isinstance(observations, VersionColumns):
        return len(observations.versions)
    return observations.predecessors.length
