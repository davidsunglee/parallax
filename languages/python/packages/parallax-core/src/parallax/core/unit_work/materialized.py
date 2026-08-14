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
aligned version column or complete Predecessor Columns.

A keyed write's evidence is resolved once, at the developer verb that holds the
value being written, and rides beside the instruction from there — the retained
claim included, so which write spends which evidence is a fact about the buffered
item rather than a list kept beside it. What the author touched and then put back
rides there too, because several writes of one observed state merge and the last
word on a member decides whether it is written at all.

:data:`BufferItem` and :func:`buffered_instruction` live here for that reason:
the envelopes ARE the buffer's shapes, so the alias naming them and the unwrap
that reads through them belong beside the two rather than in the planning
foundation that consumes them.
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
from parallax.core.unit_work.observe import WriteObservation
from parallax.core.unit_work.retain import RetainedObservation

__all__ = [
    "BufferItem",
    "GroupObservations",
    "MaterializedWriteGroup",
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
    either — is not decidable from an instruction alone (it needs the model), so
    it is enforced where a carrier is SETTLED, which REFUSES a carrier whose
    target is neither versioned nor temporal rather than planning it with the
    observation dropped. A carrier the earlier stages retire — coalesced into a
    pending insert, cancelled against one, or eliminated as a no-op — is never
    settled and never planned, so it reaches no write for a dropped observation
    to mislead.

    One observation is evidence about ONE row, so the wrapped instruction carries
    exactly one: the milestone it names, the version it advances from, and the
    gate it binds all address a single primary key (`m-unit-work` "each observed
    version belongs to exactly one row"; `m-opt-lock` "the version the unit of
    work observed *for that row*"). A multi-row instruction paired with one
    observation would let one row's evidence license another — a multi-key
    target advancing every row from the one version observed for one of them —
    so it is refused here rather than at the far end of planning. Batching never
    reaches this state either: a run of carriers is excluded from merging, and
    the merged instruction a collapsing run produces is always bare.

    ``claim`` is the RETAINED observation this write settles against, present
    when the evidence came from a read's own claim and absent when the producer
    held the observation as a bare value with nothing to spend. It rides here
    rather than in a list kept beside the buffer because consumption follows the
    write: a carrier the earlier stages retire takes its claim out of the flush
    with it, and only a carrier that reaches settlement can spend one. Its
    evidence IS this carrier's observation, so the two can never name different
    states.

    ``restorations`` names the members this write's author touched and put back,
    which the instruction itself cannot carry: a row states assignments, and a
    restoration is the absence of one. It matters because several writes of one
    observed state coalesce, and the later word on a member wins — so a write
    that restored a member cancels an earlier write's assignment to it, and a
    write that restored every member it touched cancels itself. Finalization
    drops each restored member from the merged row before weighing what is left,
    which is what makes a net-zero chain emit no DML however many verbs it took.
    """

    instruction: KeyedWrite
    observation: WriteObservation
    claim: RetainedObservation | None = None
    restorations: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.instruction.mutation in INSERT_MUTATIONS:
            raise ValueError(
                f"an insert carries no Write Observation: `{self.instruction.mutation}` on "
                f"{self.instruction.entity!r} buffers bare (m-unit-work: absence is structural)"
            )
        if len(self.instruction.rows) != 1:
            raise ValueError(
                "a Write Observation is evidence about one row: "
                f"`{self.instruction.mutation}` on {self.instruction.entity!r} addresses "
                f"{len(self.instruction.rows)} rows (m-unit-work: each observed version "
                "belongs to exactly one row)"
            )
        if self.claim is not None and self.claim.evidence is not self.observation:
            raise ValueError(
                "a claim is the retained form of the observation its carrier settles against: "
                f"`{self.instruction.mutation}` on {self.instruction.entity!r} was built with a "
                "claim naming other evidence (m-unit-work: one resolution serves the address, "
                "the gate, and the license)"
            )


def buffered_write(
    instruction: WriteInstruction,
    evidence: WriteObservation | RetainedObservation | None,
    *,
    restorations: frozenset[str] = frozenset(),
) -> WriteInstruction | ObservedKeyedWrite:
    """``instruction`` as the buffer item it travels to planning as: wrapped in
    its carrier when its verb resolved evidence for it, bare when it resolved
    none.

    The one place the optional-evidence-to-carrier decision is made, so every
    producer — the developer verbs, the conformance engine's case translation,
    and the test probes that stand in for both — spells absence the same way and
    inherits the carrier's own refusals: an insert and a multi-row instruction
    are both refused here, whatever produced the evidence.

    ``evidence`` says which of the two things a producer holds. A
    :class:`~parallax.core.unit_work.RetainedObservation` is a READ's own claim,
    and travels whole so the flush that emits its write can spend it; a bare
    :class:`~parallax.core.unit_work.observe.WriteObservation` is a value the
    caller holds directly, and claims nothing for a flush to spend.

    ``restorations`` is what the producer's author touched and put back, empty
    for a producer holding no such record. A write with no evidence at all
    carries none either: nothing coalesces with it, so there is no earlier
    assignment for a restoration to cancel.
    """
    if evidence is None:
        return instruction
    if not isinstance(instruction, KeyedWrite):
        raise TypeError(
            "only a keyed write carries a Write Observation; a predicate-selected write "
            "materializes to a Materialized Write Group with its own observation columns"
        )
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


# One buffer item: an ordinary write instruction, a keyed write travelling with
# the observation its verb resolved for it, or a materializing predicate write's
# compact Materialized Write Group (`m-unit-work` "Materialized Write Groups",
# ADR 0014). A group is buffered as ONE opaque item at the call
# position (never split, never reordered internally) — EXEMPT from same-object
# coalescing (a materializing resolve only ever matches EXISTING rows, which
# read-your-own-writes has already flushed past any pending same-key insert,
# so no coalescing candidate can structurally arise) and from cross-unit
# reordering (dependency ordering moves it as ONE block, ranked by its own
# target entity, never reordering its rows internally). An observed keyed write
# coalesces and orders exactly as its bare instruction would, and — like an
# observed write today — never merges into a multi-row batch, because everything
# an observation licenses is per-row (the milestone the write addresses, the
# version it advances from, the gate it binds under optimistic mode, and the
# single row each expects to affect) while a merged statement holds one address,
# one assignment shape, and one affected-row total. Both settle directly into
# Planned Steps at finalization; a frozen Write Plan never carries either type
# at all.
BufferItem = WriteInstruction | ObservedKeyedWrite | MaterializedWriteGroup


def buffered_instruction(item: BufferItem) -> WriteInstruction:
    """The write instruction ``item`` carries, unwrapped from any envelope.

    A Materialized Write Group answers the predicate write it materialized,
    which is what dependency ordering ranks it by.
    """
    if isinstance(item, MaterializedWriteGroup):
        return item.mutation
    if isinstance(item, ObservedKeyedWrite):
        return item.instruction
    return item


def _observation_length(observations: GroupObservations) -> int:
    if isinstance(observations, VersionColumns):
        return len(observations.versions)
    return observations.predecessors.length
