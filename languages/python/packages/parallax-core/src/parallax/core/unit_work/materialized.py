"""The buffered writes that carry the claim their verb took for them
(`m-unit-work`).

A write against existing state settles against evidence a prior read retained,
or — where its target observes no state — against the object whose shared row
lock licenses it. Both address one row, so an instruction naming several is
derived neither and travels as the bare instruction it is; evidence a caller
supplies with such an instruction is refused by the carrier that would hold it,
before the write takes any claim. The
observation-bearing shapes here pair one buffered mutation with the evidence
resolved for it, so the address a write takes, the gate it binds, and the license
it holds are all read off one object rather than looked up
separately. Each shape is an input to planning, never a member of a Write Plan,
and each disappears before the plan is frozen; the two observation-bearing ones
additionally stay indivisible through batching and dependency ordering, because
everything an observation licenses is per-row.

A predicate-selected write whose target requires per-row observation cannot be
planned from buffered data alone. Its resolving read happens before the pure
planning call, in Unit Work's write-input preparation, and settles into
exactly one compact private group per authored predicate: one shared
primary-key shape, one immutable value column per key attribute, and either an
aligned version column or complete Predecessor Columns.

A keyed write's claim is resolved once, at the developer verb that holds the
value being written, and rides beside the instruction from there — the retained
claim included, so which write spends which evidence is a fact about the buffered
item rather than a list kept beside it. What the author touched and then put back
rides there too, because several writes claiming one scope merge and the last
word on a member decides whether it is written at all.

:data:`BufferItem` and :func:`buffered_instruction` live here for that reason:
the envelopes ARE the buffer's shapes, so the alias naming them and the unwrap
that reads through them belong beside them rather than in the planning
foundation that consumes them.
"""

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
    "GroupObservations",
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
    """One keyed write and the Write Observation resolved for it.

    Resolution happens at the developer verb, which alone holds the value being
    written and therefore alone knows which milestone that value came from; the
    planner reads the observation off this envelope rather than resolving one of
    its own from a transaction-wide map. That is what makes a close's address,
    its gate, and its license derive from a single object.

    The observation is always present. A write that has none takes a shape with
    no observation field at all — a bare ``KeyedWrite`` for an insert, or for an
    instruction naming several rows, which no claim can address; an
    :class:`ObjectClaimedWrite` for a single-row unversioned Non-Temporal
    write — so absence stays structural (`m-unit-work`) rather than becoming a
    null field that flows downstream. A write that REQUIRES one and arrives
    without this carrier is refused where every buffered write is settled: the
    settlement stage finds no observed version or milestone to advance from, and
    `m-opt-lock`'s prior-observation rule raises there.

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

    instruction: PreparedKeyedWrite
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


@dataclass(frozen=True, slots=True)
class ObjectClaimedWrite:
    """One keyed write against an existing UNVERSIONED Non-Temporal row: the
    instruction, and what its author touched and put back.

    Such a row observes no state, so this carrier holds no observation — and the
    absence stays structural, exactly as :class:`ObservedKeyedWrite` requires the
    presence. What makes it a carrier at all is the other half of the claim: its
    write claims the OBJECT it addresses, because the shared row lock its
    evidence rule demands is held on the object and covers every state the row
    can be in (`m-unit-work` "Observed-State Coalescing"). Coalescing therefore
    combines two of these by object where it combines two
    :class:`ObservedKeyedWrite`\\ s by observed state, and neither ever meets the
    other: one Entity's writes take one arm.

    Construction refuses an insert and a multi-row instruction for the reasons
    :class:`ObservedKeyedWrite` refuses them: an insert opens a row rather than
    writing against one and claims nothing at all, and a claim addresses one
    object, so an instruction naming several rows would let one object's claim
    speak for another's.

    It is stage-1 vocabulary. Everything it carries — which grain to combine on,
    and which members the last word restored — is fully consumed by coalescing,
    which hands the surviving write on as the ordinary instruction it always was.
    No later stage sees this type: batching, ordering, and settlement measure an
    unversioned write as the bare instruction it is.
    """

    instruction: PreparedKeyedWrite
    restorations: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.instruction.mutation in INSERT_MUTATIONS:
            raise ValueError(
                f"an insert claims no object: `{self.instruction.mutation}` on "
                f"{self.instruction.entity!r} buffers bare (m-unit-work: an opening row has no "
                "prior row to claim)"
            )
        if len(self.instruction.rows) != 1:
            raise ValueError(
                "an object claim addresses one object: "
                f"`{self.instruction.mutation}` on {self.instruction.entity!r} addresses "
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
    """``instruction`` as the buffer item it travels to planning as: wrapped in
    the carrier its evidence implies, bare when it settles against nothing.

    The one place the evidence-to-carrier decision is made, so every
    producer — the developer verbs, the conformance engine's case translation,
    and the test probes that stand in for both — spells absence the same way and
    inherits the carriers' own refusals: an insert and a multi-row instruction
    are both refused here, whatever produced the evidence.

    ``evidence`` says which of the three things a producer holds
    (:data:`~parallax.core.unit_work.claims.SettledEvidence`). A
    :class:`~parallax.core.unit_work.RetainedObservation` is a READ's own claim,
    and travels whole so the flush that emits its write can spend it; a bare
    :class:`~parallax.core.unit_work.observe.WriteObservation` is a value the
    caller holds directly, and claims nothing for a flush to spend; an
    :class:`~parallax.core.unit_work.ObjectKey` is what an unversioned
    Non-Temporal row's write settles against, and it claims that object rather
    than any state of it. ``None`` is an insert, a write against an object this
    transaction has already buffered an insert of, or an instruction addressing
    no single object — none of them settles against anything a second intent
    could compete for.

    ``restorations`` is what the producer's author touched and put back, empty
    for a producer holding no such record. A write with no claim at all carries
    none either: nothing coalesces with it, so there is no earlier assignment for
    a restoration to cancel.
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


# One buffer item: an ordinary write instruction, a keyed write travelling with
# the claim its verb took for it (the observation it settles against, or the
# object an unversioned Non-Temporal write claims), or a materializing predicate
# write's compact Materialized Write Group (`m-unit-work` "Materialized Write Groups",
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
# one assignment shape, and one affected-row total. An OBJECT-claimed write
# carries no such per-row licence — the lock its evidence rule demands is held on
# the object, and a batch of unversioned rows is exactly what `m-batch-write`
# collapses — so it merges into a multi-row batch as freely as the bare
# instruction it is, which is what coalescing hands on once it has combined by
# object. All three settle directly into Planned Steps at finalization; a frozen
# Write Plan never carries any of these types at all.
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
