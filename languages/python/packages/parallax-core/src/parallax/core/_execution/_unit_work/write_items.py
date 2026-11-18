from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Final, Generic, Literal, TypeIs, TypeVar, cast, overload

from parallax.core._execution._unit_work.claims import (
    ClaimScope,
    SettledEvidence,
    WriteIntent,
    keyed_intent,
)
from parallax.core._execution._unit_work.evidence import (
    InsertionIdentity,
    ReadEvidence,
    RetainedObservation,
)
from parallax.core._execution._unit_work.instructions import (
    ASSIGNMENT_MUTATIONS,
    INSERT_MUTATIONS,
    REPLACE_MUTATIONS,
    ExpectedTxStart,
    ExpectedVersion,
    PreparedKeyedInstruction,
    PreparedTargetInstruction,
    keyed_instruction_from_target,
)
from parallax.core._execution._unit_work.keys import resolve_object_key
from parallax.core._execution._unit_work.row_acquisition import RetainedStartingRow
from parallax.core.internal import inheritance
from parallax.core.internal.base import INFINITY, TemporalBound
from parallax.core.internal.metamodel import CompiledEntity
from parallax.core.internal.planned_step.keys import ObjectKey, VersionedObjectStateKey
from parallax.core.internal.planned_step.managed_row import ManagedRow, RowSelection
from parallax.core.internal.temporal_read import TimeInterval
from parallax.core.internal.temporal_write.coverage import (
    NO_TRANSFORM,
    CoverageTransform,
    Successor,
)

__all__ = [
    "AdmittedWrite",
    "CallerConditioned",
    "ComposedBitemporalOpening",
    "ComposedTemporalWrite",
    "ComposedWrite",
    "InsertBatch",
    "InsertionAuthorized",
    "KeyedInsert",
    "LicensedWrite",
    "MutationPhase",
    "NonTemporalOrderedWrite",
    "OrderedWrite",
    "PostRemovalInsert",
    "StateObserved",
    "TemporalCoverageAuthority",
    "TemporalCoverageWrite",
    "TemporalIntent",
    "TemporalOrderedWrite",
    "TxStartConditioned",
    "UnversionedLocked",
    "UnversionedWriteBatch",
    "VersionConditioned",
    "WriteAuthority",
    "WritePhase",
    "admitted_write",
    "compact_observed_run",
    "compose_temporal_write",
    "distinct_evidence",
    "is_licensed_by",
    "target_write",
]


_REQUIRES_RETAINED_OBSERVATION: Final = (
    "An observed write requires the retained observation its source read."
)

_REQUIRES_SOURCE: Final = (
    "A write of an unversioned object requires the source evidence it was admitted through."
)

type WritePhase = Literal["insert", "update", "delete"]
"""The mutation phase ordering places a write in."""


def _revision_phase(instruction: PreparedKeyedInstruction) -> WritePhase:
    return "update" if instruction.mutation in ASSIGNMENT_MUTATIONS else "delete"


def _check_unlicensed(instruction: PreparedKeyedInstruction) -> None:
    """Refuse ``instruction`` as an admitted insert unless it is an insert
    opening one row."""
    if instruction.mutation not in INSERT_MUTATIONS:
        raise ValueError(
            f"only an insert is admitted unlicensed: `{instruction.mutation}` on "
            f"{instruction.target.identity.canonical!r} writes existing state, which "
            "a read's evidence or an insertion's authority must license"
        )
    if len(instruction.rows) != 1:
        raise ValueError(
            "an admitted insert opens one row: "
            f"`{instruction.mutation}` on "
            f"{instruction.target.identity.canonical!r} opens "
            f"{len(instruction.rows)} rows"
        )


@dataclass(frozen=True, slots=True)
class KeyedInsert:
    """An insert admitted through its own verb: the one row it opens needs no
    licence beyond the insert itself.

    ``object_key`` is the object its row names.
    """

    instruction: PreparedKeyedInstruction
    object_key: ObjectKey

    def __post_init__(self) -> None:
        _check_unlicensed(self.instruction)

    @property
    def phase(self) -> WritePhase:
        return "insert"

    @property
    def target(self) -> CompiledEntity:
        return self.instruction.target

    @property
    def source_evidence(self) -> tuple[ReadEvidence, ...]:
        return ()

    @property
    def selection(self) -> RowSelection:
        """The row selection its one row is of."""
        return self.instruction.rows[0].selection


@dataclass(frozen=True, slots=True)
class InsertBatch:
    """Inserts batching joined into one multi-row instruction.

    ``object_keys`` names the object each of its rows opens, in row order.
    """

    instruction: PreparedKeyedInstruction
    object_keys: tuple[ObjectKey, ...]

    @property
    def phase(self) -> WritePhase:
        return "insert"

    @property
    def target(self) -> CompiledEntity:
        return self.instruction.target

    @property
    def source_evidence(self) -> tuple[ReadEvidence, ...]:
        return ()


@dataclass(frozen=True, slots=True)
class UnversionedWriteBatch:
    """Writes of unversioned objects batching joined into one multi-row instruction.

    ``object_keys`` names the object each of its rows writes, in row order.
    ``source_evidence`` holds, by identity, the Read Evidence every joined
    write retained, which nothing reads.
    """

    instruction: PreparedKeyedInstruction
    object_keys: tuple[ObjectKey, ...]
    source_evidence: tuple[ReadEvidence, ...]

    @property
    def phase(self) -> WritePhase:
        return _revision_phase(self.instruction)

    @property
    def target(self) -> CompiledEntity:
        return self.instruction.target


@dataclass(frozen=True, slots=True)
class StateObserved:
    """A read's State Observation licenses the write.

    ``retained_observation`` is the state the write's source observed, which
    never changes. A source's authority may reach a later state this attempt's
    own completed writes produced from it: for a versioned Non-Temporal source
    ``current`` names that protected state where it is not the observed one,
    and the write claims and settles against it; a temporal write settles
    against what those writes left of its observed state when its range binds.

    ``source_evidence`` holds, by identity, the Read Evidence of every source
    whose write composed into this one, which keeps their demand alive while
    the write is pending or planned and which only binding reads, for their
    pins.
    """

    retained_observation: RetainedObservation
    current: VersionedObjectStateKey | None = None
    source_evidence: tuple[ReadEvidence, ...] = field(default=(), compare=False)

    def __post_init__(self) -> None:
        if not isinstance(cast("object", self.retained_observation), RetainedObservation):
            raise ValueError(_REQUIRES_RETAINED_OBSERVATION)


@dataclass(frozen=True, slots=True)
class UnversionedLocked:
    """The read's shared lock on an unversioned Non-Temporal object, which has
    no state to observe, licenses the write.

    ``source_evidence`` holds, by identity, the observation-free Read Evidence
    of every source whose write composed into this one: it keeps their demand
    alive while the write is pending or planned, and nothing reads it.
    """

    source_evidence: tuple[ReadEvidence, ...] = field(compare=False)

    def __post_init__(self) -> None:
        if not self.source_evidence:
            raise ValueError(_REQUIRES_SOURCE)


@dataclass(frozen=True, slots=True)
class InsertionAuthorized:
    """This attempt's own admitted insertion of the object licenses the write.

    ``identity`` is the insertion's authority, which the unit of work checks
    still stands when it admits the write; completion changes nothing of it.
    ``claim_scope`` is the claim scope a Non-Temporal write of a stored row
    takes — the exact version this attempt's own writes left the row at, or
    the object itself when the row is unversioned — so it composes with an
    observed write of the same state. A temporal write composes by object and
    takes none, and neither does a write folding into its object's pending
    insert.
    """

    identity: InsertionIdentity
    claim_scope: VersionedObjectStateKey | ObjectKey | None = None


@dataclass(frozen=True, slots=True)
class VersionConditioned:
    """A caller's stated version licenses the write of a versioned
    Non-Temporal object.

    ``source_evidence`` holds, by identity, the Read Evidence of the
    source-backed writes composed into it, kept even where a destruction
    superseded their assignments, which nothing reads; the caller's condition
    stays whatever values survive.
    """

    expected: ExpectedVersion
    source_evidence: tuple[ReadEvidence, ...] = field(default=(), compare=False)


@dataclass(frozen=True, slots=True)
class TxStartConditioned:
    """A caller's stated Transaction-Time start licenses the write of a
    temporal object.

    ``starting_row`` is the starting row a Locking write's admission read
    whole: data its range may reuse, not part of what licenses the write.
    """

    expected: ExpectedTxStart
    starting_row: RetainedStartingRow | None = field(default=None, compare=False)


type WriteAuthority = (
    StateObserved
    | UnversionedLocked
    | InsertionAuthorized
    | VersionConditioned
    | TxStartConditioned
)
"""What licenses one write of existing state."""

type CallerConditioned = VersionConditioned | TxStartConditioned
"""The authorities a caller's stated revision grants."""

type TemporalCoverageAuthority = StateObserved | InsertionAuthorized | TxStartConditioned
"""The authorities a write against temporal coverage can carry."""

Authority_co = TypeVar("Authority_co", bound="WriteAuthority", covariant=True)


@dataclass(frozen=True, slots=True)
class LicensedWrite(Generic[Authority_co]):  # noqa: UP046 - PEP 695 infers invariance through the synthesized __replace__
    """One write of one existing object, travelling with the ``authority``
    that licenses it.

    ``object_key`` is the object it writes. What it claims and the Read
    Evidence it keeps are its authority's; a write against temporal coverage
    also answers, alone, the intents and transform a composition of it keeps.
    An update's row is its literal assignment set: the identity plus every
    member its producer expressed.
    """

    instruction: PreparedKeyedInstruction
    object_key: ObjectKey
    authority: Authority_co

    def __post_init__(self) -> None:
        if self.instruction.mutation in INSERT_MUTATIONS:
            raise ValueError(
                f"an insert is admitted by its own verb: `{self.instruction.mutation}` on "
                f"{self.instruction.target.identity.canonical!r} needs no licence "
                "(m-unit-work: absence is structural)"
            )
        if len(self.instruction.rows) != 1:
            raise ValueError(
                "a licensed write addresses one existing object: "
                f"`{self.instruction.mutation}` on "
                f"{self.instruction.target.identity.canonical!r} addresses "
                f"{len(self.instruction.rows)} rows"
            )

    @property
    def phase(self) -> WritePhase:
        return _revision_phase(self.instruction)

    @property
    def target(self) -> CompiledEntity:
        return self.instruction.target

    @property
    def claim_scope(self) -> ClaimScope | None:
        """The state or object the write claims and settles against, or
        ``None`` where an insertion's write has not yet been given one."""
        match self.authority:
            case StateObserved(retained_observation=observed, current=current):
                return observed.key if current is None else current
            case UnversionedLocked() | TxStartConditioned():
                return self.object_key
            case InsertionAuthorized(claim_scope=scope):
                return scope
            case VersionConditioned(expected=expected):
                return VersionedObjectStateKey(self.object_key, expected.version)

    @property
    def source_evidence(self) -> tuple[ReadEvidence, ...]:
        match self.authority:
            case (
                StateObserved(source_evidence=evidence)
                | UnversionedLocked(source_evidence=evidence)
                | VersionConditioned(source_evidence=evidence)
            ):
                return evidence
            case InsertionAuthorized() | TxStartConditioned():
                return ()

    @property
    def intents(
        self: LicensedWrite[TemporalCoverageAuthority],
    ) -> tuple[TemporalIntent[TemporalCoverageAuthority], ...]:
        """This write of a temporal object alone, as the one intent a
        composition of it keeps — under this write's own authority — built
        when asked."""
        write_intent = keyed_intent(self.instruction)
        assert write_intent is not None  # a write against existing coverage is no insert
        return (TemporalIntent(write_intent, self.authority),)

    @property
    def transform(self: LicensedWrite[TemporalCoverageAuthority]) -> CoverageTransform:
        """What this write of a temporal object alone does to its existing
        coverage, built when asked."""
        ((key_name, _),) = self.object_key.primary_key
        return _transformed(NO_TRANSFORM, self.instruction, key_name)

    @property
    def selection(self: LicensedWrite[TemporalCoverageAuthority]) -> RowSelection:
        """The row selection this write's rows are of."""
        return self.instruction.rows[0].selection


CoverageAuthority_co = TypeVar(
    "CoverageAuthority_co", bound="TemporalCoverageAuthority", covariant=True
)


@dataclass(frozen=True, slots=True)
class TemporalIntent(Generic[CoverageAuthority_co]):  # noqa: UP046 - PEP 695 infers invariance through the synthesized __replace__
    """What one write of a temporal object keeps once composed: the window and
    kind it states, and the very authority it was admitted under.

    Its values live in the composed transform, where a later write may
    overwrite them; its authority stays whatever happens to them.
    """

    write_intent: WriteIntent
    authority: CoverageAuthority_co


@overload
def is_licensed_by[T: WriteAuthority](
    item: ComposedWrite | OrderedWrite, authority: type[T]
) -> TypeIs[LicensedWrite[T]]: ...


@overload
def is_licensed_by[T: TemporalCoverageAuthority](
    item: TemporalIntent[TemporalCoverageAuthority], authority: type[T]
) -> TypeIs[TemporalIntent[T]]: ...


def is_licensed_by(
    item: ComposedWrite | OrderedWrite | TemporalIntent[TemporalCoverageAuthority],
    authority: type[WriteAuthority],
) -> bool:
    """Whether ``item`` is one licensed write, or one composed temporal
    intent, whose authority is an ``authority``."""
    return isinstance(item, (LicensedWrite, TemporalIntent)) and isinstance(
        item.authority, authority
    )


def distinct_evidence(groups: Iterable[tuple[ReadEvidence, ...]]) -> tuple[ReadEvidence, ...]:
    """Every Read Evidence of ``groups`` once, by identity, in first-occurrence
    order — the first group itself where the others add none."""
    remaining = iter(groups)
    first = next(remaining, ())
    distinct: dict[int, ReadEvidence] | None = None
    added = False
    for group in remaining:
        for evidence in group:
            if distinct is None:
                distinct = {id(held): held for held in first}
            if id(evidence) not in distinct:
                distinct[id(evidence)] = evidence
                added = True
    return first if distinct is None or not added else tuple(distinct.values())


def target_write(
    prepared: PreparedTargetInstruction, families: inheritance.InheritanceFacet
) -> LicensedWrite[CallerConditioned]:
    """``prepared`` as the licensed write that carries its caller's condition:
    the keyed write it executes as, under the condition preparation judged."""
    instruction = keyed_instruction_from_target(prepared)
    key = resolve_object_key(instruction, families)
    assert key is not None  # preparation required the key
    match prepared.expectation:
        case ExpectedVersion() as expected:
            authority = VersionConditioned(expected)
        case ExpectedTxStart() as expected:
            authority = TxStartConditioned(expected)
    return LicensedWrite(instruction, key, authority)


@overload
def admitted_write(
    instruction: PreparedKeyedInstruction,
    evidence: None,
    object_key: ObjectKey | None,
    *,
    insertion: None = None,
) -> KeyedInsert: ...


@overload
def admitted_write(
    instruction: PreparedKeyedInstruction,
    evidence: None,
    object_key: ObjectKey | None,
    *,
    insertion: InsertionIdentity,
) -> LicensedWrite[InsertionAuthorized]: ...


@overload
def admitted_write(
    instruction: PreparedKeyedInstruction,
    evidence: SettledEvidence,
    object_key: ObjectKey | None,
    *,
    source: ReadEvidence | None = None,
) -> LicensedWrite[StateObserved | UnversionedLocked]: ...


@overload
def admitted_write(
    instruction: PreparedKeyedInstruction,
    evidence: SettledEvidence | None,
    object_key: ObjectKey | None,
    *,
    source: ReadEvidence | None = None,
) -> KeyedInsert | LicensedWrite[StateObserved | UnversionedLocked]: ...


def admitted_write(
    instruction: PreparedKeyedInstruction,
    evidence: SettledEvidence | None,
    object_key: ObjectKey | None,
    *,
    source: ReadEvidence | None = None,
    insertion: InsertionIdentity | None = None,
) -> AdmittedWrite:
    """``instruction`` as the admitted write of ``object_key`` that settles
    against ``evidence``, retaining ``source``, the Read Evidence it was
    admitted through, where it has one.

    A retained observation travels with the write; so does a versioned state,
    with its ``source``'s observation. An object key requires ``source`` in
    place of an observation. With no evidence, the instruction carries the
    ``insertion`` that licenses it, or is an insert, which needs no licence;
    evidence and an insertion never license one write together. Every write
    names the object it writes, an insert the one it opens.
    """
    if evidence is not None and insertion is not None:
        raise ValueError(
            f"`{instruction.mutation}` on {instruction.target.identity.canonical!r} is "
            "licensed by a read's evidence or by an insertion's authority, never by both"
        )
    if evidence is None and insertion is None:
        _check_unlicensed(instruction)
        if object_key is None:
            raise ValueError(
                f"`{instruction.mutation}` on {instruction.target.identity.canonical!r} "
                "names no object to open"
            )
        return KeyedInsert(instruction, object_key)
    if object_key is None:
        raise ValueError(
            f"`{instruction.mutation}` on {instruction.target.identity.canonical!r} writes "
            "existing state, so it names the object it writes"
        )
    if evidence is None:
        assert insertion is not None  # only an insert carries neither
        return LicensedWrite(instruction, object_key, InsertionAuthorized(insertion))
    retained = () if source is None else (source,)
    if isinstance(evidence, ObjectKey):
        return LicensedWrite(instruction, object_key, UnversionedLocked(retained))
    if isinstance(evidence, RetainedObservation):
        return LicensedWrite(
            instruction, object_key, StateObserved(evidence, source_evidence=retained)
        )
    observation = None if source is None else source.observation
    if observation is None:
        raise ValueError(_REQUIRES_RETAINED_OBSERVATION)
    return LicensedWrite(
        instruction,
        object_key,
        StateObserved(
            observation,
            current=None if evidence == observation.key else evidence,
            source_evidence=retained,
        ),
    )


@dataclass(frozen=True, slots=True)
class ComposedTemporalWrite:
    """Every pending write of one temporal object against its existing
    coverage once a second arrives, composed in authored order at the position
    of the first; a first write stays alone until then and answers its intents
    and transform when asked.

    ``intents`` keeps each admitted write's authority and window, overwritten
    ones included, except that an initial run of observed writes of one
    observation over one window keeps one intent; ``transform`` holds only the
    assignments that still survive. ``selection`` is the row selection every
    composed write's rows are of.
    """

    target: CompiledEntity
    object_key: ObjectKey
    intents: tuple[TemporalIntent[TemporalCoverageAuthority], ...]
    transform: CoverageTransform
    selection: RowSelection

    @property
    def phase(self) -> WritePhase:
        """An update while the composition still assigns somewhere, otherwise a
        deletion."""
        return "update" if self.transform.assigns else "delete"

    @property
    def source_evidence(self) -> tuple[ReadEvidence, ...]:
        """The distinct Read Evidence of every source whose write the
        composition holds, by identity, in authored order."""
        return distinct_evidence(
            intent.authority.source_evidence
            for intent in self.intents
            if is_licensed_by(intent, StateObserved)
        )


type TemporalCoverageWrite = LicensedWrite[TemporalCoverageAuthority] | ComposedTemporalWrite
"""One temporal object's pending writes against its existing coverage: an
admitted write still alone, or the composition of several. Either answers its
target, object key, intents, and transform."""


def compose_temporal_write(
    held: TemporalCoverageWrite,
    item: LicensedWrite[TemporalCoverageAuthority],
    arriving: TemporalIntent[TemporalCoverageAuthority],
    key_name: str,
) -> ComposedTemporalWrite:
    """``held`` followed by ``item``, which keeps ``arriving``: one temporal
    object's writes composed in authored order.

    The arriving write's values replace earlier ones per member inside its own
    window and destroy coverage there if it is destructive; every earlier
    intent stays. A caller's condition already held over the same window adds
    nothing to keep.
    """
    intents = held.intents
    if not isinstance(arriving.authority, TxStartConditioned) or arriving not in intents:
        intents = (*intents, arriving)
    return ComposedTemporalWrite(
        target=held.target,
        object_key=held.object_key,
        intents=intents,
        transform=_transformed(held.transform, item.instruction, key_name),
        selection=held.selection,
    )


def compact_observed_run(
    held: TemporalCoverageWrite,
    item: LicensedWrite[TemporalCoverageAuthority],
    arriving: TemporalIntent[StateObserved],
    key_name: str,
) -> ComposedTemporalWrite:
    """``held``, one observed intent, with ``item`` composed into it as that
    same intent: an observed write, keeping ``arriving``, of the identical
    observation over the same window, which the claim algebra coalesces,
    supersedes, or deduplicates.

    The one intent states the arriving write's kind, which only a superseding
    destruction changes, and keeps every source's Read Evidence by identity,
    first authored first; the transform takes the arriving write as usual.
    """
    (only,) = held.intents
    assert is_licensed_by(only, StateObserved)  # only an observed run compacts
    authority = only.authority
    evidence = distinct_evidence((authority.source_evidence, arriving.authority.source_evidence))
    if evidence is not authority.source_evidence:
        only = TemporalIntent(arriving.write_intent, replace(authority, source_evidence=evidence))
    elif only.write_intent != arriving.write_intent:
        only = TemporalIntent(arriving.write_intent, authority)
    return ComposedTemporalWrite(
        target=held.target,
        object_key=held.object_key,
        intents=(only,),
        transform=_transformed(held.transform, item.instruction, key_name),
        selection=held.selection,
    )


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


def _assigned(instruction: PreparedKeyedInstruction, key_name: str) -> ManagedRow | None:
    if instruction.mutation not in ASSIGNMENT_MUTATIONS:
        return None
    (row,) = instruction.rows
    key = row.selection.members.shape.position(key_name)
    return row if key is None else row.without(1 << key)


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
    def object_key(self) -> ObjectKey:
        return self.insert.object_key

    @property
    def phase(self) -> WritePhase:
        return "insert"

    @property
    def target(self) -> CompiledEntity:
        return self.insert.target

    @property
    def source_evidence(self) -> tuple[ReadEvidence, ...]:
        return ()

    @property
    def selection(self) -> RowSelection:
        """The row selection the insert's row, and every part it opens, is of."""
        return self.insert.selection

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
    def target(self) -> CompiledEntity:
        return self.insert.target


type AdmittedWrite = KeyedInsert | LicensedWrite[WriteAuthority]
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
    | UnversionedWriteBatch
)
"""One element of the sequence settlement reads: a composed write once the
planner's rewriting stages have finished with it.

Batching joins inserts into an :class:`InsertBatch` and writes of unversioned
objects into an :class:`UnversionedWriteBatch`, and ordering consumes every
:class:`PostRemovalInsert`.
"""

type TemporalOrderedWrite = TemporalCoverageWrite | ComposedBitemporalOpening | KeyedInsert
"""An ordered write of a temporal object: a range over its existing
coverage, a pending Bitemporal opening, or a keyed insert, which batching
never joins on a temporal target."""

type NonTemporalOrderedWrite = (
    KeyedInsert
    | InsertBatch
    | UnversionedWriteBatch
    | LicensedWrite[StateObserved | UnversionedLocked | InsertionAuthorized | VersionConditioned]
)
"""An ordered write of a Non-Temporal object: an insert, a batch, or a
licensed write of an existing row under any authority but a stated
Transaction-Time start."""

type MutationPhase = tuple[OrderedWrite, ...]
"""A region's ordered writes of one mutation kind: its inserts, its updates,
or its deletes. The planner hands settlement a flush's phases in flush
order."""
