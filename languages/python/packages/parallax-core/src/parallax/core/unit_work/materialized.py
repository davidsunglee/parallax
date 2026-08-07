"""The buffered writes that carry their own observation evidence (`m-unit-work`).

A write against existing state settles against the database evidence a prior
read retained. Both shapes here pair one buffered mutation with the evidence
resolved for it, so the address a write takes, the gate it binds, and the
license it holds are all read off one object rather than looked up separately.
Each is an input to planning, never a member of a Write Plan; each stays
indivisible through batching and dependency ordering and disappears during
finalization.

A predicate-selected write whose target requires per-row observation cannot be
planned from buffered data alone. Its resolving read happens before the pure
planning call, in Unit Work's write-input preparation, and settles into
exactly one compact private group per authored predicate: one shared
primary-key shape, one immutable value column per key attribute, and either an
aligned version column or complete Predecessor Columns under one group-wide
Transaction-Time Basis.

A keyed write's evidence is resolved once, at the developer verb that holds the
value being written, and rides beside the instruction from there.
"""

from __future__ import annotations

from dataclasses import dataclass

from parallax.core.unit_work.columns import ColumnSlice, PredecessorColumns
from parallax.core.unit_work.instructions import (
    INSERT_MUTATIONS,
    KeyedWrite,
    PredicateWrite,
    WriteInstruction,
)
from parallax.core.unit_work.observe import TransactionTimeBasis, WriteObservation

__all__ = [
    "GroupObservations",
    "MaterializedWriteGroup",
    "ObservedKeyedWrite",
    "TemporalColumns",
    "VersionColumns",
    "buffered_write",
]


@dataclass(frozen=True, slots=True)
class VersionColumns:
    """One aligned optimistic-lock version value per resolved row."""

    versions: ColumnSlice[int]


@dataclass(frozen=True, slots=True)
class TemporalColumns:
    """Complete predecessor state per resolved row, under one group-wide basis.

    The one Transaction-Time pin the resolving read used determines this basis
    for every row; a resolving read can never mix latest- and historical-pinned
    rows, so there is no per-row basis column.
    """

    predecessors: PredecessorColumns
    transaction_time_basis: TransactionTimeBasis


type GroupObservations = VersionColumns | TemporalColumns
"""One authored predicate's aligned observation evidence, one member per
resolved row and one basis (if temporal) for the whole group."""


@dataclass(frozen=True, slots=True)
class MaterializedWriteGroup:
    """One authored predicate's compact, private, indivisible planning input.

    ``key_attributes`` names the canonical primary-key shape once (by declared
    member name, matching the write-instruction row convention); ``key_columns``
    carries one aligned value column per key attribute, in database resolution
    order. Every key and observation column shares the same positive row count.
    The group holds no managed Entity object, no per-row keyed-write wrapper,
    and no per-row Predecessor Row object.
    """

    mutation: PredicateWrite
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
    """One keyed write and the Write Observation resolved for it.

    Resolution happens at the developer verb, which alone holds the value being
    written and therefore alone knows which milestone that value came from; the
    planner reads the observation off this envelope rather than resolving one of
    its own from a transaction-wide map. That is what makes a close's address,
    its gate, and its license derive from a single object.

    The observation is always present. A write that has none — every insert, and
    every unversioned Non-Temporal write — buffers as a bare ``KeyedWrite``, so
    absence stays structural (`m-unit-work`) rather than becoming a null field
    that flows downstream. A write that REQUIRES one and arrives bare is refused
    while it is settled, exactly where it is today.

    Absence being structural cuts both ways, so construction REFUSES an insert:
    an opening row observes nothing, and a carrier around one would be evidence
    about a milestone that does not yet exist. That refusal is what lets
    coalescing fold an update into a pending insert without unwrapping, and lets
    opening-row canonicalization treat every carrier as a revising write. The
    other half of the rule — an unversioned Non-Temporal write observes nothing
    either — is not decidable from an instruction alone (it needs the model), and
    is settled where the observation is resolved.
    """

    instruction: KeyedWrite
    observation: WriteObservation

    def __post_init__(self) -> None:
        if self.instruction.mutation in INSERT_MUTATIONS:
            raise ValueError(
                f"an insert carries no Write Observation: `{self.instruction.mutation}` on "
                f"{self.instruction.entity!r} buffers bare (m-unit-work: absence is structural)"
            )


def buffered_write(
    instruction: WriteInstruction, observation: WriteObservation | None
) -> WriteInstruction | ObservedKeyedWrite:
    """``instruction`` as the buffer item it travels to planning as: wrapped in
    its carrier when its verb resolved an observation for it, bare when it
    resolved none.

    The one place the optional-observation-to-carrier decision is made, so every
    producer — the developer verbs, the conformance engine's case translation,
    and the test probes that stand in for both — spells absence the same way and
    inherits the carrier's own refusals.
    """
    if observation is None:
        return instruction
    if not isinstance(instruction, KeyedWrite):
        raise TypeError(
            "only a keyed write carries a Write Observation; a predicate-selected write "
            "materializes to a Materialized Write Group with its own observation columns"
        )
    return ObservedKeyedWrite(instruction=instruction, observation=observation)


def _observation_length(observations: GroupObservations) -> int:
    if isinstance(observations, VersionColumns):
        return len(observations.versions)
    return observations.predecessors.length
