from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final, Literal

from parallax.core import inheritance
from parallax.core._execution._unit_work.claims import (
    ClaimScope,
    SettledEvidence,
    WriteIntent,
    claimed_object,
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
    "InsertionAuthorizedWrite",
    "KeyedInsert",
    "MutationPhase",
    "ObjectLockedBatch",
    "ObjectLockedWrite",
    "OrderedWrite",
    "PostRemovalInsert",
    "ReadAuthorizedWrite",
    "StateObservedWrite",
    "TargetWrite",
    "TemporalContribution",
    "TemporalKeyedWrite",
    "admitted_write",
    "buffered_claim_scope",
    "buffered_object_key",
    "compose_temporal_write",
    "singleton_transform",
    "target_write",
    "temporal_contribution",
]


_REQUIRES_RETAINED_OBSERVATION: Final = (
    "An observed write requires the retained observation its source read."
)

_REQUIRES_SOURCE: Final = (
    "An object-locked write requires the source evidence it was admitted through."
)


@dataclass(frozen=True, slots=True)
class KeyedInsert:
    """An insert admitted through its own verb: the one row it opens needs no
    licence beyond the insert itself."""

    instruction: PreparedKeyedInstruction

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


@dataclass(frozen=True, slots=True)
class InsertBatch:
    """Inserts batching joined into one multi-row instruction."""

    instruction: PreparedKeyedInstruction


@dataclass(frozen=True, slots=True)
class StateObservedWrite:
    """Carries verb-time evidence through planning without resolving it again.

    ``retained_observation`` is the state the write's source observed, which
    never changes. A source's authority may reach a later state this attempt's
    own completed writes produced from it. For a versioned Non-Temporal source
    ``current`` names that protected state where it is not the observed one,
    and :attr:`scope` is what the write claims and settles against either way;
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
    def scope(self) -> ObjectStateKey:
        """The state the write claims and settles against."""
        current = self.current
        return self.retained_observation.key if current is None else current


@dataclass(frozen=True, slots=True)
class ObjectLockedWrite:
    """Coalesces by object identity, then settles as its own instruction.

    ``source_evidence`` holds, by identity, the observation-free Read Evidence
    of every source whose write composed into this one: it keeps their demand
    alive while the write is pending or planned, and nothing reads it.
    """

    instruction: PreparedKeyedInstruction
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


@dataclass(frozen=True, slots=True)
class ObjectLockedBatch:
    """Object-locked writes batching joined into one multi-row instruction.

    ``source_evidence`` holds, by identity, the Read Evidence every joined
    object-locked write retained, which nothing reads.
    """

    instruction: PreparedKeyedInstruction
    source_evidence: tuple[ReadEvidence, ...]


@dataclass(frozen=True, slots=True)
class InsertionAuthorizedWrite:
    """A keyed write authorized by an admitted insertion rather than by a read.

    ``identity`` is the insertion's authority, which the unit of work checks
    still stands when it admits the write; completion changes nothing of it.
    ``scope`` is the claim scope a Non-Temporal write of a stored row takes —
    the exact version this attempt's own writes left the row at, or the object
    itself when the row is unversioned — so it composes with an observed write
    of the same state. A temporal write composes by object and takes none.
    """

    instruction: PreparedKeyedInstruction
    identity: InsertionIdentity
    scope: VersionedObjectStateKey | ObjectKey | None = None

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


@dataclass(frozen=True, slots=True)
class TargetWrite:
    """A target write of one existing object, carrying the
    starting condition the caller stated rather than a read's evidence.

    ``scope`` is the claim scope that condition names — the exact version a
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
    expectation: TargetExpectation
    scope: VersionedObjectStateKey | ObjectKey
    source_evidence: tuple[ReadEvidence, ...] = ()
    retained: RetainedTargetState | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if self.instruction.mutation in INSERT_MUTATIONS or len(self.instruction.rows) != 1:
            raise ValueError(
                "a caller's condition addresses one existing object: "
                f"`{self.instruction.mutation}` on "
                f"{self.instruction.target.identity.canonical!r} is no such write"
            )


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
        expectation=expectation,
        scope=(
            VersionedObjectStateKey(key, expectation.version)
            if isinstance(expectation, ExpectedVersion)
            else key
        ),
    )


type ReadAuthorizedWrite = StateObservedWrite | ObjectLockedWrite
"""One keyed write travelling with the claim its verb took for it, at either
scope. The two share what coalescing manipulates — an instruction —
and differ only in the grain their claims are taken at."""


def admitted_write(
    instruction: PreparedKeyedInstruction,
    evidence: SettledEvidence | None,
    *,
    source: ReadEvidence | None = None,
    authority: InsertionIdentity | None = None,
) -> KeyedInsert | ReadAuthorizedWrite | InsertionAuthorizedWrite:
    """``instruction`` as the admitted write that settles against ``evidence``,
    retaining ``source``, the Read Evidence it was admitted through, where it
    has one.

    A retained observation travels with the write; so does a versioned state,
    with its ``source``'s observation. An object key requires ``source`` in
    place of an observation. With no evidence, the instruction carries the
    insertion ``authority`` that licenses it, or is an insert, which needs no
    licence.
    """
    if evidence is None:
        if authority is not None:
            return InsertionAuthorizedWrite(instruction=instruction, identity=authority)
        return KeyedInsert(instruction)
    retained = () if source is None else (source,)
    if isinstance(evidence, ObjectKey):
        return ObjectLockedWrite(instruction=instruction, source_evidence=retained)
    if isinstance(evidence, RetainedObservation):
        return StateObservedWrite(
            instruction=instruction, retained_observation=evidence, source_evidence=retained
        )
    observation = None if source is None else source.observation
    if observation is None:
        raise ValueError(_REQUIRES_RETAINED_OBSERVATION)
    return StateObservedWrite(
        instruction=instruction,
        retained_observation=observation,
        current=None if evidence == observation.key else evidence,
        source_evidence=retained,
    )


@dataclass(frozen=True, slots=True)
class TemporalContribution:
    """What one admitted write of a temporal object keeps once it is composed:
    its source condition and requested window, not its values.

    ``retained_observation`` is the evidence an observed write settles
    against, and ``source_evidence`` the Read Evidence of every source whose
    write it is, by identity, which keeps their demand alive while the write is
    pending or planned and which only binding reads, for their pins. A
    target write has neither, and ``condition`` is the Transaction-Time
    start its caller requires of the coverage at its window's start. A write
    an admitted insertion authorized has none of them: its condition is the
    coverage at its window's start, the insertion's own anchor, which execution
    requires. Values the write assigned live in the composed transform, where a
    later write may overwrite them; the condition stays required whatever
    happens to them. ``retained`` is the starting row a target
    write's Locking admission read whole: data its range may reuse, not part
    of what the write is.
    """

    kind: Literal["assignment", "destructive"]
    valid_time_window: TimeInterval | None
    retained_observation: RetainedObservation | None
    condition: ExpectedTxStart | None = None
    retained: RetainedTargetState | None = field(default=None, compare=False)
    source_evidence: tuple[ReadEvidence, ...] = field(default=(), compare=False)

    @property
    def observation(self) -> StateObservation | None:
        retained = self.retained_observation
        return None if retained is None else retained.evidence


@dataclass(frozen=True, slots=True)
class ComposedTemporalWrite:
    """Every pending observed write of one temporal object, composed in
    authored order at the position of the first.

    ``key`` is the object's identity row. ``contributions`` keeps each admitted
    write's original condition and window, overwritten ones included;
    ``transform`` holds only the assignments that still survive.
    """

    target: EntityMetadata
    key: Mapping[str, object]
    contributions: tuple[TemporalContribution, ...]
    transform: CoverageTransform

    @property
    def assigns(self) -> bool:
        """Whether the composition still assigns somewhere, rather than only
        destroying."""
        return self.transform.assigns


type TemporalKeyedWrite = StateObservedWrite | InsertionAuthorizedWrite | TargetWrite
"""One keyed write of a temporal object that composes with that object's other
pending writes: an observed one, one an admitted insertion authorized, or a
target write."""


def temporal_contribution(item: TemporalKeyedWrite) -> TemporalContribution:
    """``item``'s lasting part once composed."""
    observed = isinstance(item, StateObservedWrite)
    targeted = isinstance(item, TargetWrite)
    expectation = item.expectation if targeted else None
    return TemporalContribution(
        kind="assignment" if item.instruction.mutation in ASSIGNMENT_MUTATIONS else "destructive",
        valid_time_window=item.instruction.valid_time_window,
        retained_observation=item.retained_observation if observed else None,
        condition=expectation if isinstance(expectation, ExpectedTxStart) else None,
        retained=item.retained if targeted else None,
        source_evidence=item.source_evidence if observed else (),
    )


def compose_temporal_write(
    held: TemporalKeyedWrite | ComposedTemporalWrite, arriving: TemporalKeyedWrite, key_name: str
) -> ComposedTemporalWrite:
    """``held`` followed by ``arriving``, one temporal object's writes composed
    in authored order.

    The arriving write's values replace earlier ones per member inside its own
    window and destroy coverage there if it is destructive; every earlier
    condition stays. A caller's condition already held over the same window
    adds nothing to keep.
    """
    if not isinstance(held, ComposedTemporalWrite):
        held = _composed(held, key_name)
    contribution = temporal_contribution(arriving)
    contributions = held.contributions
    if contribution.condition is None or contribution not in contributions:
        contributions = (*contributions, contribution)
    return ComposedTemporalWrite(
        target=held.target,
        key=held.key,
        contributions=contributions,
        transform=_contributed(held.transform, arriving.instruction, key_name),
    )


def _composed(item: TemporalKeyedWrite, key_name: str) -> ComposedTemporalWrite:
    row = item.instruction.rows[0]
    return ComposedTemporalWrite(
        target=item.instruction.target,
        key={key_name: row[key_name]},
        contributions=(temporal_contribution(item),),
        transform=singleton_transform(item, key_name),
    )


def singleton_transform(item: TemporalKeyedWrite, key_name: str) -> CoverageTransform:
    """What ``item`` alone does to its object's existing coverage, built from
    the write itself rather than from a composition of one write."""
    return _contributed(NO_TRANSFORM, item.instruction, key_name)


def _contributed(
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


AdmittedWrite = KeyedInsert | ReadAuthorizedWrite | InsertionAuthorizedWrite | TargetWrite


type OrderedWrite = (
    KeyedInsert
    | InsertBatch
    | StateObservedWrite
    | ObjectLockedWrite
    | ObjectLockedBatch
    | InsertionAuthorizedWrite
    | TargetWrite
    | ComposedTemporalWrite
    | ComposedBitemporalOpening
)
"""One element of the sequence settlement reads: an admitted write once the
planner's rewriting stages have finished with it.

Batching joins inserts into an :class:`InsertBatch` and object-locked writes
into an :class:`ObjectLockedBatch`, which keeps their source evidence; every
stage after coalescing measures a write by its instruction.
"""

type MutationPhase = tuple[OrderedWrite, ...]
"""A region's ordered writes of one mutation kind: its inserts, its updates,
or its deletes. The planner hands settlement a flush's phases in flush
order."""

type ComposedWrite = OrderedWrite | PostRemovalInsert
"""One composed write as finalization receives it: what settlement
reads, or inserts that must follow an earlier removal."""


def buffered_object_key(
    item: AdmittedWrite,
    families: inheritance.InheritanceFacet,
) -> ObjectKey | None:
    """The one object ``item`` writes, or ``None`` where it names none.

    A retained observation, an insertion's identity, and a caller's scope
    already name it; only a write carrying none of them is resolved from its
    row.
    """
    if isinstance(item, StateObservedWrite):
        return item.retained_observation.key.object
    if isinstance(item, InsertionAuthorizedWrite):
        return item.identity.object_key
    if isinstance(item, TargetWrite):
        return claimed_object(item.scope)
    return resolve_object_key(item.instruction, families)


def buffered_claim_scope(
    item: AdmittedWrite,
    object_key: ObjectKey | None,
) -> ClaimScope | None:
    """The scope ``item`` claims where it composes by claimed scope rather than
    by temporal object, given ``object_key``, the object it writes
    (:func:`buffered_object_key`).

    ``None`` for a write that claims nothing there: an insert, and a
    write an insertion authorized while it folds into its object's pending
    opening.
    """
    if isinstance(item, StateObservedWrite):
        return item.scope
    if isinstance(item, ObjectLockedWrite):
        return object_key
    if isinstance(item, InsertionAuthorizedWrite | TargetWrite):
        return item.scope
    return None
