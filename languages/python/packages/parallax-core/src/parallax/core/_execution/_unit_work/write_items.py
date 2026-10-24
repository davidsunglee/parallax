from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final, Literal, overload

from parallax.core import inheritance
from parallax.core._execution._unit_work.claims import (
    SettledEvidence,
    WriteIntent,
    keyed_intent,
)
from parallax.core._execution._unit_work.instructions import (
    ASSIGNMENT_MUTATIONS,
    INSERT_MUTATIONS,
    REPLACE_MUTATIONS,
    ExpectedTxStart,
    ExpectedVersion,
    PreparedKeyedInstruction,
    PreparedTargetInstruction,
    TargetExpectation,
    keyed_instruction_from_target,
)
from parallax.core._execution._unit_work.keys import resolve_object_key
from parallax.core._execution._unit_work.retain import (
    InsertionIdentity,
    ReadEvidence,
    RetainedObservation,
    RetainedTargetState,
)
from parallax.core.base import INFINITY, TemporalBound
from parallax.core.metamodel import EntityMetadata
from parallax.core.temporal_read import TimeInterval
from parallax.core.temporal_write.coverage import NO_TRANSFORM, CoverageTransform, Successor
from parallax.core.write_plan.keys import ObjectKey, ObjectStateKey, VersionedObjectStateKey
from parallax.core.write_plan.observe import StateObservation

__all__ = [
    "AdmittedWrite",
    "ComposedBitemporalOpening",
    "ComposedTemporalWrite",
    "ComposedWrite",
    "InsertBatch",
    "InsertionAuthorizedIntent",
    "InsertionAuthorizedWrite",
    "KeyedInsert",
    "MutationPhase",
    "ObjectLockedBatch",
    "ObjectLockedWrite",
    "OrderedWrite",
    "PostRemovalInsert",
    "ReadAuthorizedWrite",
    "StateObservedIntent",
    "StateObservedWrite",
    "TargetIntent",
    "TargetWrite",
    "TemporalCoverageWrite",
    "TemporalIntent",
    "WritePhase",
    "admitted_write",
    "compact_observed_run",
    "compose_temporal_write",
    "target_write",
    "temporal_intent",
]


_REQUIRES_RETAINED_OBSERVATION: Final = (
    "An observed write requires the retained observation its source read."
)

_REQUIRES_SOURCE: Final = (
    "An object-locked write requires the source evidence it was admitted through."
)

type WritePhase = Literal["insert", "update", "delete"]
"""The mutation phase ordering places a write in."""


def _revision_phase(instruction: PreparedKeyedInstruction) -> WritePhase:
    return "update" if instruction.mutation in ASSIGNMENT_MUTATIONS else "delete"


@dataclass(frozen=True, slots=True)
class KeyedInsert:
    """An insert admitted through its own verb: the one row it opens needs no
    licence beyond the insert itself.

    ``object_key`` is the object its row names, or ``None`` where the database
    computes that key.
    """

    instruction: PreparedKeyedInstruction
    object_key: ObjectKey | None

    def __post_init__(self) -> None:
        if self.instruction.mutation not in INSERT_MUTATIONS:
            raise ValueError(
                f"only an insert is admitted unlicensed: `{self.instruction.mutation}` on "
                f"{self.instruction.target.identity.canonical!r} writes existing state, which "
                "a read's evidence or an insertion's authority must license"
            )
        if len(self.instruction.rows) != 1:
            raise ValueError(
                "an admitted insert opens one row: "
                f"`{self.instruction.mutation}` on "
                f"{self.instruction.target.identity.canonical!r} opens "
                f"{len(self.instruction.rows)} rows"
            )

    @property
    def phase(self) -> WritePhase:
        return "insert"

    @property
    def target(self) -> EntityMetadata:
        return self.instruction.target

    @property
    def source_evidence(self) -> tuple[ReadEvidence, ...]:
        return ()


@dataclass(frozen=True, slots=True)
class InsertBatch:
    """Inserts batching joined into one multi-row instruction.

    ``object_keys`` names the object each of its rows opens, in row order.
    """

    instruction: PreparedKeyedInstruction
    object_keys: tuple[ObjectKey | None, ...]

    @property
    def phase(self) -> WritePhase:
        return "insert"

    @property
    def target(self) -> EntityMetadata:
        return self.instruction.target

    @property
    def source_evidence(self) -> tuple[ReadEvidence, ...]:
        return ()


@dataclass(frozen=True, slots=True)
class StateObservedWrite:
    """Carries verb-time evidence through planning without resolving it again.

    ``retained_observation`` is the state the write's source observed, which
    never changes. A source's authority may reach a later state this attempt's
    own completed writes produced from it. For a versioned Non-Temporal source
    ``current`` names that protected state where it is not the observed one,
    and :attr:`claim_scope` is what the write claims and settles against either way;
    a temporal write settles against what those writes left of its observed
    state when its range binds.

    ``source_evidence`` holds, by identity, the Read Evidence of every source
    whose write composed into this one — it keeps their demand alive while the
    write is pending or planned, and nothing reads it. A caller-conditioned
    write that absorbs this one keeps it, even where that write's deletion
    supersedes this one, and so does this write where a write an insertion
    authorized meets it. An update's row is its literal assignment set: the
    identity plus every member its producer expressed, each written whatever
    value the source observed for it.
    """

    instruction: PreparedKeyedInstruction
    object_key: ObjectKey
    retained_observation: RetainedObservation
    current: VersionedObjectStateKey | None = None
    source_evidence: tuple[ReadEvidence, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.retained_observation, RetainedObservation):  # pyright: ignore[reportUnnecessaryIsInstance] - validates runtime callers
            raise ValueError(_REQUIRES_RETAINED_OBSERVATION)
        if self.instruction.mutation in INSERT_MUTATIONS:
            raise ValueError(
                f"an insert carries no State Observation: `{self.instruction.mutation}` on "
                f"{self.instruction.target.identity.canonical!r} is admitted as its own insert "
                "(m-unit-work: absence is structural)"
            )
        if len(self.instruction.rows) != 1:
            raise ValueError(
                "a State Observation is evidence about one row: "
                f"`{self.instruction.mutation}` on "
                f"{self.instruction.target.identity.canonical!r} addresses "
                f"{len(self.instruction.rows)} rows (m-unit-work: each observed version "
                "belongs to exactly one row)"
            )

    @property
    def observation(self) -> StateObservation:
        return self.retained_observation.evidence

    @property
    def claim_scope(self) -> ObjectStateKey:
        """The state the write claims and settles against."""
        current = self.current
        return self.retained_observation.key if current is None else current

    @property
    def phase(self) -> WritePhase:
        return _revision_phase(self.instruction)

    @property
    def target(self) -> EntityMetadata:
        return self.instruction.target

    @property
    def intents(self) -> tuple[TemporalIntent, ...]:
        """This write of a temporal object alone, as the one intent a
        composition of it keeps, built when asked."""
        return _alone_intents(self)

    @property
    def transform(self) -> CoverageTransform:
        """What this write of a temporal object alone does to its existing
        coverage, built when asked."""
        return _alone_transform(self)


@dataclass(frozen=True, slots=True)
class ObjectLockedWrite:
    """Coalesces by object identity, then settles as its own instruction.

    ``source_evidence`` holds, by identity, the observation-free Read Evidence
    of every source whose write composed into this one: it keeps their demand
    alive while the write is pending or planned, and nothing reads it.
    """

    instruction: PreparedKeyedInstruction
    object_key: ObjectKey
    source_evidence: tuple[ReadEvidence, ...]

    def __post_init__(self) -> None:
        if not self.source_evidence:
            raise ValueError(_REQUIRES_SOURCE)
        if self.instruction.mutation in INSERT_MUTATIONS:
            raise ValueError(
                f"an insert claims no object: `{self.instruction.mutation}` on "
                f"{self.instruction.target.identity.canonical!r} is admitted as its own insert "
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

    @property
    def claim_scope(self) -> ObjectKey:
        return self.object_key

    @property
    def phase(self) -> WritePhase:
        return _revision_phase(self.instruction)

    @property
    def target(self) -> EntityMetadata:
        return self.instruction.target


@dataclass(frozen=True, slots=True)
class ObjectLockedBatch:
    """Object-locked writes batching joined into one multi-row instruction.

    ``object_keys`` names the object each of its rows writes, in row order.
    ``source_evidence`` holds, by identity, the Read Evidence every joined
    object-locked write retained, which nothing reads.
    """

    instruction: PreparedKeyedInstruction
    object_keys: tuple[ObjectKey, ...]
    source_evidence: tuple[ReadEvidence, ...]

    @property
    def phase(self) -> WritePhase:
        return _revision_phase(self.instruction)

    @property
    def target(self) -> EntityMetadata:
        return self.instruction.target


@dataclass(frozen=True, slots=True)
class InsertionAuthorizedWrite:
    """A keyed write authorized by an admitted insertion rather than by a read.

    ``identity`` is the insertion's authority, which the unit of work checks
    still stands when it admits the write; completion changes nothing of it.
    ``claim_scope`` is the claim scope a Non-Temporal write of a stored row takes —
    the exact version this attempt's own writes left the row at, or the object
    itself when the row is unversioned — so it composes with an observed write
    of the same state. A temporal write composes by object and takes none,
    and neither does a write folding into its object's pending insert.
    """

    instruction: PreparedKeyedInstruction
    object_key: ObjectKey
    identity: InsertionIdentity
    claim_scope: VersionedObjectStateKey | ObjectKey | None = None

    def __post_init__(self) -> None:
        if self.instruction.mutation in INSERT_MUTATIONS:
            raise ValueError(
                f"an insert is admitted by its own verb: `{self.instruction.mutation}` on "
                f"{self.instruction.target.identity.canonical!r} carries no insertion authority"
            )
        if len(self.instruction.rows) != 1:
            raise ValueError(
                "an insertion's authority licenses writes of the one object it opened: "
                f"`{self.instruction.mutation}` on "
                f"{self.instruction.target.identity.canonical!r} addresses "
                f"{len(self.instruction.rows)} rows"
            )

    @property
    def phase(self) -> WritePhase:
        return _revision_phase(self.instruction)

    @property
    def target(self) -> EntityMetadata:
        return self.instruction.target

    @property
    def source_evidence(self) -> tuple[ReadEvidence, ...]:
        return ()

    @property
    def intents(self) -> tuple[TemporalIntent, ...]:
        """This write of a temporal object alone, as the one intent a
        composition of it keeps, built when asked."""
        return _alone_intents(self)

    @property
    def transform(self) -> CoverageTransform:
        """What this write of a temporal object alone does to its existing
        coverage, built when asked."""
        return _alone_transform(self)


@dataclass(frozen=True, slots=True)
class TargetWrite:
    """A target write of one existing object, carrying the
    starting condition the caller stated rather than a read's evidence.

    ``claim_scope`` is the claim scope that condition names — the exact version a
    versioned object is required to stand at, or the object itself when it is
    temporal — which is the scope an observed write of the same state takes, so
    the two compose there; a temporal object's writes compose by object
    instead. ``source_evidence`` holds, by identity, the Read Evidence of the
    source-backed writes composed into a Non-Temporal one, kept even where a
    destruction superseded their assignments, which nothing reads; the
    caller's condition stays whatever values survive, and a destruction
    superseding the write keeps it too. ``retained`` is the starting row a
    Locking temporal write's admission read whole, which its range may reuse.
    """

    instruction: PreparedKeyedInstruction
    object_key: ObjectKey
    expectation: TargetExpectation
    claim_scope: VersionedObjectStateKey | ObjectKey
    source_evidence: tuple[ReadEvidence, ...] = ()
    retained: RetainedTargetState | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if self.instruction.mutation in INSERT_MUTATIONS or len(self.instruction.rows) != 1:
            raise ValueError(
                "a caller's condition addresses one existing object: "
                f"`{self.instruction.mutation}` on "
                f"{self.instruction.target.identity.canonical!r} is no such write"
            )

    @property
    def phase(self) -> WritePhase:
        return _revision_phase(self.instruction)

    @property
    def target(self) -> EntityMetadata:
        return self.instruction.target

    @property
    def intents(self) -> tuple[TemporalIntent, ...]:
        """This write of a temporal object alone, as the one intent a
        composition of it keeps, built when asked."""
        return _alone_intents(self)

    @property
    def transform(self) -> CoverageTransform:
        """What this write of a temporal object alone does to its existing
        coverage, built when asked."""
        return _alone_transform(self)


def target_write(
    prepared: PreparedTargetInstruction, families: inheritance.InheritanceFacet
) -> TargetWrite:
    """``prepared`` as the admitted write that carries its caller's condition: the
    keyed write it executes as, claimed at the scope its expectation names."""
    instruction = keyed_instruction_from_target(prepared)
    key = resolve_object_key(instruction, families)
    assert key is not None  # preparation required the key
    expectation = prepared.expectation
    return TargetWrite(
        instruction=instruction,
        object_key=key,
        expectation=expectation,
        claim_scope=(
            VersionedObjectStateKey(key, expectation.version)
            if isinstance(expectation, ExpectedVersion)
            else key
        ),
    )


type ReadAuthorizedWrite = StateObservedWrite | ObjectLockedWrite
"""One keyed write travelling with the claim its verb took for it, at either
scope. The two share what coalescing manipulates — an instruction —
and differ only in the grain their claims are taken at."""


@overload
def admitted_write(
    instruction: PreparedKeyedInstruction,
    evidence: None,
    object_key: ObjectKey | None,
    *,
    source: ReadEvidence | None = None,
    authority: None = None,
) -> KeyedInsert: ...


@overload
def admitted_write(
    instruction: PreparedKeyedInstruction,
    evidence: None,
    object_key: ObjectKey | None,
    *,
    source: ReadEvidence | None = None,
    authority: InsertionIdentity,
) -> InsertionAuthorizedWrite: ...


@overload
def admitted_write(
    instruction: PreparedKeyedInstruction,
    evidence: SettledEvidence,
    object_key: ObjectKey | None,
    *,
    source: ReadEvidence | None = None,
    authority: InsertionIdentity | None = None,
) -> ReadAuthorizedWrite: ...


@overload
def admitted_write(
    instruction: PreparedKeyedInstruction,
    evidence: SettledEvidence | None,
    object_key: ObjectKey | None,
    *,
    source: ReadEvidence | None = None,
    authority: InsertionIdentity | None = None,
) -> KeyedInsert | ReadAuthorizedWrite | InsertionAuthorizedWrite: ...


def admitted_write(
    instruction: PreparedKeyedInstruction,
    evidence: SettledEvidence | None,
    object_key: ObjectKey | None,
    *,
    source: ReadEvidence | None = None,
    authority: InsertionIdentity | None = None,
) -> KeyedInsert | ReadAuthorizedWrite | InsertionAuthorizedWrite:
    """``instruction`` as the admitted write of ``object_key`` that settles
    against ``evidence``, retaining ``source``, the Read Evidence it was
    admitted through, where it has one.

    A retained observation travels with the write; so does a versioned state,
    with its ``source``'s observation. An object key requires ``source`` in
    place of an observation. With no evidence, the instruction carries the
    insertion ``authority`` that licenses it, or is an insert, which needs no
    licence. Only an insert may name no object.
    """
    if evidence is None and authority is None:
        return KeyedInsert(instruction, object_key)
    if object_key is None:
        raise ValueError(
            f"`{instruction.mutation}` on {instruction.target.identity.canonical!r} writes "
            "existing state, so it names the object it writes"
        )
    if evidence is None:
        assert authority is not None  # only an insert carries neither
        return InsertionAuthorizedWrite(
            instruction=instruction, object_key=object_key, identity=authority
        )
    retained = () if source is None else (source,)
    if isinstance(evidence, ObjectKey):
        return ObjectLockedWrite(
            instruction=instruction, object_key=object_key, source_evidence=retained
        )
    if isinstance(evidence, RetainedObservation):
        return StateObservedWrite(
            instruction=instruction,
            object_key=object_key,
            retained_observation=evidence,
            source_evidence=retained,
        )
    observation = None if source is None else source.observation
    if observation is None:
        raise ValueError(_REQUIRES_RETAINED_OBSERVATION)
    return StateObservedWrite(
        instruction=instruction,
        object_key=object_key,
        retained_observation=observation,
        current=None if evidence == observation.key else evidence,
        source_evidence=retained,
    )


@dataclass(frozen=True, slots=True)
class StateObservedIntent:
    """What one observed write of a temporal object keeps once composed: the
    window and kind it states, the observation it settles against, and, by
    identity, the Read Evidence of every source whose write it is, which keeps
    their demand alive while the write is pending or planned and which only
    binding reads, for their pins. Its values live in the composed transform,
    where a later write may overwrite them; the observation stays required
    whatever happens to them."""

    intent: WriteIntent
    retained_observation: RetainedObservation
    source_evidence: tuple[ReadEvidence, ...] = field(compare=False)


@dataclass(frozen=True, slots=True)
class InsertionAuthorizedIntent:
    """What one write an admitted insertion authorized keeps once composed: its
    window's start is that insertion's anchor, where execution requires
    current coverage."""

    intent: WriteIntent


@dataclass(frozen=True, slots=True)
class TargetIntent:
    """What one target write of a temporal object keeps once composed: the
    Transaction-Time start its caller requires of the coverage at its window's
    start. ``retained`` is the starting row the write's Locking admission read
    whole: data its range may reuse, not part of what the write is."""

    intent: WriteIntent
    expected: ExpectedTxStart
    retained: RetainedTargetState | None = field(default=None, compare=False)


type TemporalIntent = StateObservedIntent | InsertionAuthorizedIntent | TargetIntent
"""One composed temporal write's intent and the authority it was admitted
under."""


@dataclass(frozen=True, slots=True)
class ComposedTemporalWrite:
    """Every pending write of one temporal object against its existing
    coverage once a second arrives, composed in authored order at the position
    of the first; a first write stays alone until then and answers its intents
    and transform when asked.

    ``intents`` keeps each admitted write's authority and window, overwritten
    ones included, except that an initial run of observed writes of one
    observation over one window keeps one intent; ``transform`` holds only the
    assignments that still survive.
    """

    target: EntityMetadata
    object_key: ObjectKey
    intents: tuple[TemporalIntent, ...]
    transform: CoverageTransform

    @property
    def phase(self) -> WritePhase:
        """An update while the composition still assigns somewhere, otherwise a
        deletion."""
        return "update" if self.transform.assigns else "delete"

    @property
    def source_evidence(self) -> tuple[ReadEvidence, ...]:
        """The distinct Read Evidence of every source whose write the
        composition holds, by identity, in authored order."""
        distinct: tuple[ReadEvidence, ...] = ()
        for intent in self.intents:
            if isinstance(intent, StateObservedIntent):
                distinct = _with_distinct(distinct, intent.source_evidence)
        return distinct


type TemporalCoverageWrite = (
    StateObservedWrite | InsertionAuthorizedWrite | TargetWrite | ComposedTemporalWrite
)
"""One temporal object's pending writes against its existing coverage: an
admitted write still alone, or the composition of several. Either answers its
target, object key, intents, and transform."""


def temporal_intent(
    write: StateObservedWrite | InsertionAuthorizedWrite | TargetWrite, intent: WriteIntent
) -> TemporalIntent:
    """What ``write``, stating ``intent``, keeps once composed."""
    if isinstance(write, StateObservedWrite):
        return StateObservedIntent(intent, write.retained_observation, write.source_evidence)
    if isinstance(write, InsertionAuthorizedWrite):
        return InsertionAuthorizedIntent(intent)
    expected = write.expectation
    assert isinstance(expected, ExpectedTxStart)  # preparation states a temporal target's start
    return TargetIntent(intent, expected, write.retained)


def compose_temporal_write(
    held: TemporalCoverageWrite,
    arriving: StateObservedWrite | InsertionAuthorizedWrite | TargetWrite,
    intent: TemporalIntent,
    key_name: str,
) -> ComposedTemporalWrite:
    """``held`` followed by ``arriving``, which keeps ``intent``: one temporal
    object's writes composed in authored order.

    The arriving write's values replace earlier ones per member inside its own
    window and destroy coverage there if it is destructive; every earlier
    intent stays. A caller's condition already held over the same window adds
    nothing to keep.
    """
    instruction = arriving.instruction
    intents = held.intents
    if not isinstance(intent, TargetIntent) or intent not in intents:
        intents = (*intents, intent)
    return ComposedTemporalWrite(
        target=held.target,
        object_key=held.object_key,
        intents=intents,
        transform=_transformed(held.transform, instruction, key_name),
    )


def compact_observed_run(
    held: TemporalCoverageWrite,
    arriving: StateObservedWrite,
    intent: StateObservedIntent,
    key_name: str,
) -> ComposedTemporalWrite:
    """``held``, one observed intent, with ``arriving`` composed into it as
    that same intent: an observed write of the identical observation over the
    same window, which the claim algebra coalesces, supersedes, or
    deduplicates.

    The one intent states the arriving write's kind, which only a superseding
    destruction changes, and keeps every source's Read Evidence by identity,
    first authored first; the transform takes the arriving write as usual.
    """
    (only,) = held.intents
    assert isinstance(only, StateObservedIntent)  # only an observed run compacts
    evidence = _with_distinct(only.source_evidence, intent.source_evidence)
    if evidence is not only.source_evidence or only.intent != intent.intent:
        only = StateObservedIntent(intent.intent, only.retained_observation, evidence)
    return ComposedTemporalWrite(
        target=held.target,
        object_key=held.object_key,
        intents=(only,),
        transform=_transformed(held.transform, arriving.instruction, key_name),
    )


def _alone_intents(
    write: StateObservedWrite | InsertionAuthorizedWrite | TargetWrite,
) -> tuple[TemporalIntent, ...]:
    intent = keyed_intent(write.instruction)
    assert intent is not None  # a write against existing coverage is no insert
    return (temporal_intent(write, intent),)


def _alone_transform(
    write: StateObservedWrite | InsertionAuthorizedWrite | TargetWrite,
) -> CoverageTransform:
    ((key_name, _),) = write.object_key.primary_key
    return _transformed(NO_TRANSFORM, write.instruction, key_name)


def _with_distinct(
    held: tuple[ReadEvidence, ...], arriving: tuple[ReadEvidence, ...]
) -> tuple[ReadEvidence, ...]:
    """``held`` followed by each of ``arriving`` it does not already hold, by
    identity — ``held`` itself where it holds them all."""
    for evidence in arriving:
        if all(evidence is not kept for kept in held):
            held = (*held, evidence)
    return held


def _transformed(
    transform: CoverageTransform, instruction: PreparedKeyedInstruction, key_name: str
) -> CoverageTransform:
    """``transform`` followed by one prepared keyed write over its prepared
    window: an amendment or a replacement assigns every member its row names
    but the key, which addresses the object rather than changing it, and a
    replacement's window becomes a replacement's extent whatever authorized
    it; any other write destroys."""
    return transform.followed_by(
        instruction.valid_time_window,
        _assigned(instruction, key_name),
        replaces=instruction.mutation in REPLACE_MUTATIONS,
    )


def _assigned(instruction: PreparedKeyedInstruction, key_name: str) -> Mapping[str, object] | None:
    if instruction.mutation not in ASSIGNMENT_MUTATIONS:
        return None
    return {name: value for name, value in instruction.rows[0].items() if name != key_name}


@dataclass(frozen=True, slots=True)
class ComposedBitemporalOpening:
    """A still-unflushed insert of a Bitemporal object, with the writes its
    insertion authorized since composed over the coverage it opens.

    ``transform`` applies to the opening's own window exactly as a stored
    range's transform applies to stored coverage: assigned members replace the
    opening's values inside each write's window, and destruction removes
    coverage there. Settlement opens each part that survives as a new lineage
    seeded with the insert's own state. A replacement reaching past the
    opening establishes its complete state over that reach too
    (:attr:`beyond`), and every other write reaches no further than the
    opening and its replacements do. ``intents`` keeps each composed write's
    window so admission can judge the next one.
    """

    insert: KeyedInsert
    transform: CoverageTransform
    intents: tuple[WriteIntent, ...]

    @property
    def object_key(self) -> ObjectKey | None:
        return self.insert.object_key

    @property
    def phase(self) -> WritePhase:
        return "insert"

    @property
    def target(self) -> EntityMetadata:
        return self.insert.target

    @property
    def source_evidence(self) -> tuple[ReadEvidence, ...]:
        return ()

    def followed_by(
        self, instruction: PreparedKeyedInstruction, key_name: str
    ) -> ComposedBitemporalOpening:
        """This opening with ``instruction`` composed after its earlier writes,
        an amendment's or a destruction's window clipped to the coverage the
        opening and its replacements establish."""
        intent = keyed_intent(instruction)
        assert intent is not None  # an opening's own writes are no inserts
        window = instruction.valid_time_window
        assert window is not None  # a Bitemporal write states its window
        replaces = instruction.mutation in REPLACE_MUTATIONS
        if not replaces:
            end = self._covered_end()
            clipped = window.clipped(end=None if end is INFINITY else end)
            # Every write an insertion authorized starts at its anchor, inside
            # the opening.
            assert clipped is not None
            window = clipped
        return ComposedBitemporalOpening(
            insert=self.insert,
            transform=self.transform.followed_by(
                window, _assigned(instruction, key_name), replaces=replaces
            ),
            intents=(*self.intents, intent),
        )

    @property
    def beyond(self) -> TimeInterval | None:
        """The stretch past the opening's window that a composed replacement
        reached — every write composed after it reaching there too, so the
        stored coverage there takes the whole transform — or ``None`` where no
        replacement reached past it."""
        window = self.insert.instruction.valid_time_window
        assert window is not None  # a Bitemporal opening states its window
        end = window.end
        if end is INFINITY or not self.transform.segments:
            return None
        reach = self.transform.valid_time_window
        assert reach is not None  # every segment of a Valid-Time transform has an extent
        return TimeInterval(end, reach.end) if reach.ends_after(end) else None

    @property
    def survives(self) -> bool:
        """Whether any of the opened coverage survives its composed writes."""
        return bool(self._surviving())

    def _covered_end(self) -> dt.datetime | Literal[TemporalBound.INFINITY]:
        """Where the coverage the opening and its replacements establish ends."""
        beyond = self.beyond
        if beyond is not None:
            return beyond.end
        window = self.insert.instruction.valid_time_window
        assert window is not None  # a Bitemporal opening states its window
        return window.end

    def _surviving(self) -> tuple[Successor, ...]:
        window = self.insert.instruction.valid_time_window
        assert window is not None  # a Bitemporal opening states its window
        return self.transform.successors_of(window)


@dataclass(frozen=True, slots=True)
class PostRemovalInsert:
    """An insert of an object whose earlier insertion an earlier pending write
    removes completely, which executes only after everything authored before
    it: an insert ordinarily runs ahead of every removal, and this one must
    follow the one that clears its way."""

    insert: KeyedInsert | ComposedBitemporalOpening

    @property
    def phase(self) -> WritePhase:
        return "insert"

    @property
    def target(self) -> EntityMetadata:
        return self.insert.target


type AdmittedWrite = (
    KeyedInsert | StateObservedWrite | ObjectLockedWrite | InsertionAuthorizedWrite | TargetWrite
)
"""What admission accepts: one write of one row, under the authority it
carries."""

type ComposedWrite = (
    AdmittedWrite | ComposedTemporalWrite | ComposedBitemporalOpening | PostRemovalInsert
)
"""One write as admission composed it and finalization receives it: an
admitted write it passed through, a composition, or an insert that must
follow an earlier removal."""

type OrderedWrite = (
    AdmittedWrite
    | ComposedTemporalWrite
    | ComposedBitemporalOpening
    | InsertBatch
    | ObjectLockedBatch
)
"""One element of the sequence settlement reads: a composed write once the
planner's rewriting stages have finished with it.

Batching joins inserts into an :class:`InsertBatch` and object-locked writes
into an :class:`ObjectLockedBatch`, and ordering consumes every
:class:`PostRemovalInsert`.
"""

type MutationPhase = tuple[OrderedWrite, ...]
"""A region's ordered writes of one mutation kind: its inserts, its updates,
or its deletes. The planner hands settlement a flush's phases in flush
order."""
