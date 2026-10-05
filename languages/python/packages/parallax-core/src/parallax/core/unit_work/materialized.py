from __future__ import annotations

import datetime as dt
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

from parallax.core import inheritance, temporal_read
from parallax.core.base import INFINITY_LITERAL
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, EntityMetadata, Metamodel
from parallax.core.temporal_read import TemporalShape, milestone_edge
from parallax.core.unit_work.claims import SettledEvidence, WriteIntent, keyed_intent
from parallax.core.unit_work.columns import ChunkedColumnBuilder, ColumnSlice, whole
from parallax.core.unit_work.instructions import (
    INSERT_MUTATIONS,
    UPDATE_MUTATIONS,
    ExpectedTxStart,
    ExpectedVersion,
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    PreparedTargetWrite,
    PreparedTemporalBounds,
    PreparedWrite,
    TargetExpectation,
    derive_opening,
    target_instruction,
)
from parallax.core.unit_work.observe import WriteObservation
from parallax.core.unit_work.plan import Completion
from parallax.core.unit_work.planner import (
    ObjectKey,
    ObservedStateKey,
    TemporalStateKey,
    VersionedStateKey,
    resolve_object_key,
)
from parallax.core.unit_work.retain import InsertionIdentity, RetainedObservation
from parallax.core.unit_work.temporal import (
    EMPTY_TRANSFORM,
    BoundPiece,
    TemporalTransform,
    is_open_bound,
)

if TYPE_CHECKING:
    from parallax.core.inheritance import EntityMemberSelection

__all__ = [
    "AfterRemoval",
    "BufferItem",
    "ChainedTemporalWrite",
    "ClaimedKeyedWrite",
    "ComposedTemporalWrite",
    "FollowingKeyedWrite",
    "GroupStates",
    "InsertionKeyedWrite",
    "MaterializedWriteGroup",
    "ObjectClaimedWrite",
    "ObservedKeyedWrite",
    "PendingOpening",
    "PredecessorRows",
    "PredecessorRowsBuilder",
    "TargetKeyedWrite",
    "TemporalContribution",
    "TemporalKeyedWrite",
    "VersionedEvidence",
    "VersionedEvidenceBuilder",
    "buffered_instruction",
    "buffered_write",
    "chained",
    "composed_alone",
    "composed_temporal_write",
    "group_state_keys",
    "target_write",
    "temporal_contribution",
]


@dataclass(frozen=True, slots=True)
class VersionedEvidence:
    """Each selected row's family key value and the optimistic-lock version it
    was read at, aligned in resolution order."""

    keys: ColumnSlice[object]
    versions: ColumnSlice[int]

    def __post_init__(self) -> None:
        if len(self.keys) != len(self.versions):
            raise ValueError(
                "Versioned Evidence aligns one version with each key: "
                f"{len(self.keys)} keys, {len(self.versions)} versions"
            )
        if not self.versions:
            raise ValueError("Versioned Evidence addresses at least one row")

    def __len__(self) -> int:
        return len(self.versions)


@dataclass(frozen=True, slots=True)
class PredecessorRows:
    """Each selected row's complete Predecessor Row state, in resolution order.

    ``rows`` holds the resolving read's own judged positional member rows,
    aligned to ``selection``, and ``absent`` is the marker those rows carry at a
    member the row does not hold. ``key_position`` is the family key's position
    in ``selection``. ``documents`` aligns each row's raw Structured Column and
    is absent where the read projected none. Rows and documents are adopted by
    reference from the reader that exclusively owned them, and nothing reads
    them except to view or copy them.
    """

    selection: EntityMemberSelection
    key_position: int
    absent: object
    rows: ColumnSlice[tuple[object, ...]]
    documents: ColumnSlice[object] | None = None

    def __post_init__(self) -> None:
        if not self.rows:
            raise ValueError("Predecessor Rows carries at least one row")
        if self.documents is not None and len(self.documents) != len(self.rows):
            raise ValueError(
                "Predecessor Rows aligns one raw document with each row: "
                f"{len(self.rows)} rows, {len(self.documents)} documents"
            )
        if not 0 <= self.key_position < len(self.selection.bindings):
            raise ValueError("Predecessor Rows' key position lies within its selection")

    def __len__(self) -> int:
        return len(self.rows)

    def key(self, index: int) -> object:
        return self.rows[index][self.key_position]

    def document(self, index: int) -> object | None:
        documents = self.documents
        return None if documents is None else documents[index]

    def axis_start(self, at: int, attribute: AttributeIdentity, /) -> object:
        position = self.selection.index.get(attribute)
        return None if position is None else self.rows[at][position]


type GroupEvidence = VersionedEvidence | PredecessorRows
"""One authored predicate's aligned evidence, one entry per selected row."""


@dataclass(frozen=True, slots=True)
class MaterializedWriteGroup:
    """One authored predicate's compact, private, indivisible planning input.

    The group holds no managed Entity object, no per-row keyed-write wrapper,
    and no per-row Predecessor Row object.

    ``evidence`` is not optional, so a group exists only for a target entitled
    to evidence: a predicate write against an unversioned Non-Temporal target
    stays readless and never materializes at all. Which targets those are needs
    the model, so — exactly as for :class:`ObservedKeyedWrite` — the model-aware
    settlement refuses a group whose target turns out to be neither versioned
    nor temporal rather than settling it Unversioned with its evidence dropped.
    """

    mutation: PreparedPredicateWrite
    evidence: GroupEvidence

    def __len__(self) -> int:
        return len(self.evidence)


class VersionedEvidenceBuilder:
    """Accumulates :class:`VersionedEvidence` from judged positional rows."""

    __slots__ = ("_key_position", "_keys", "_version_position", "_versions")

    def __init__(self, *, key_position: int, version_position: int) -> None:
        self._key_position = key_position
        self._version_position = version_position
        self._keys: ChunkedColumnBuilder[object] = ChunkedColumnBuilder()
        self._versions: ChunkedColumnBuilder[int] = ChunkedColumnBuilder()

    def append(self, row: tuple[object, ...]) -> None:
        self._keys.append(row[self._key_position])
        self._versions.append(cast("int", row[self._version_position]))

    def seal(self) -> VersionedEvidence | None:
        """The evidence appended so far, or ``None`` when nothing was."""
        if not self._versions:
            return None
        return VersionedEvidence(whole(self._keys.build()), whole(self._versions.build()))


class PredecessorRowsBuilder:
    """Accumulates :class:`PredecessorRows` by reference from judged rows."""

    __slots__ = ("_absent", "_documents", "_key_position", "_rows", "_selection")

    def __init__(
        self,
        selection: EntityMemberSelection,
        *,
        key_position: int,
        absent: object,
        documents: bool,
    ) -> None:
        self._selection = selection
        self._key_position = key_position
        self._absent = absent
        self._rows: ChunkedColumnBuilder[tuple[object, ...]] = ChunkedColumnBuilder()
        self._documents: ChunkedColumnBuilder[object] | None = (
            ChunkedColumnBuilder() if documents else None
        )

    def append(self, row: tuple[object, ...], document: object | None = None) -> None:
        self._rows.append(row)
        documents = self._documents
        if documents is not None:
            documents.append(document)

    def seal(self) -> PredecessorRows | None:
        """The evidence appended so far, or ``None`` when nothing was."""
        if not self._rows:
            return None
        documents = self._documents
        return PredecessorRows(
            selection=self._selection,
            key_position=self._key_position,
            absent=self._absent,
            rows=whole(self._rows.build()),
            documents=None if documents is None else whole(documents.build()),
        )


def group_state_keys(group: MaterializedWriteGroup, meta: Metamodel) -> GroupStates:
    """Each exact state ``group`` selected, in resolution order, keyed as a
    keyed read's own observation of that row would be."""
    entity = group.mutation.selection.target
    position = inheritance.view(meta).entity(entity.identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        raise ValueError(f"{entity.identity.canonical}: the model declares no such entity")
    shape = temporal_read.view(meta).shape(entity.identity)
    if shape is None:  # pragma: no cover - the facet covers every accepted Entity
        raise ValueError(f"{entity.identity.canonical}: the model declares no such entity")
    return GroupStates(entity.identity, position.primary_key.identity.name, group.evidence, shape)


@dataclass(frozen=True, slots=True)
class GroupStates:
    """Each exact state a group's ``evidence`` selected, in resolution order,
    read on demand from the facts a facet already answered for the group."""

    entity: EntityIdentity
    key: str
    evidence: GroupEvidence
    shape: TemporalShape

    def __iter__(self) -> Iterator[ObservedStateKey]:
        entity, key, evidence = self.entity, self.key, self.evidence
        if isinstance(evidence, VersionedEvidence):
            for value, version in zip(evidence.keys, evidence.versions, strict=True):
                yield VersionedStateKey(ObjectKey(entity, ((key, value),)), version)
            return
        for index in range(len(evidence)):
            yield TemporalStateKey(
                ObjectKey(entity, ((key, evidence.key(index)),)),
                milestone_edge(self.shape, evidence, index),
            )


@dataclass(frozen=True, slots=True)
class ObservedKeyedWrite:
    """Carries verb-time evidence through planning without resolving it again.

    A retained ``claim`` is spent only if this write survives to settlement.
    ``twins`` are the distinct retained observations of the same state that
    writes coalesced into this one were admitted through — independent
    standalone reads of one state retain one each — and its completion spends
    them with ``claim``. An update's row is its literal assignment set: the
    identity plus every member its producer expressed, each written whatever
    value the source observed for it.
    """

    instruction: PreparedKeyedWrite
    observation: WriteObservation
    claim: RetainedObservation | None = None
    twins: tuple[RetainedObservation, ...] = ()

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

    ``source`` is the observation-free source authority the write was admitted
    through, which the successful flush it is pending in spends whatever
    becomes of the write itself.
    """

    instruction: PreparedKeyedWrite
    source: Completion | None = None

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


@dataclass(frozen=True, slots=True)
class InsertionKeyedWrite:
    """A keyed write authorized by an admitted insertion rather than by a read.

    ``identity`` is the insertion's authority, which the unit of work checks
    still stands when it admits the write; completion spends nothing of it.
    ``scope`` is the claim scope a Non-Temporal write of a stored row takes —
    the exact version this attempt's own writes left the row at, or the object
    itself when the row is unversioned — so it composes with an observed write
    of the same state. A temporal write composes by object and takes none.
    """

    instruction: PreparedKeyedWrite
    identity: InsertionIdentity
    scope: VersionedStateKey | ObjectKey | None = None

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
class TargetKeyedWrite:
    """A keyed write of an existing object a caller addressed, carrying the
    starting condition the caller stated rather than a read's evidence.

    ``scope`` is the claim scope that condition names — the exact version a
    versioned object is required to stand at, or the object itself when it is
    unversioned or temporal — which is the scope an observed write of the same
    state takes, so the two compose there; a temporal object's writes compose by
    object instead. ``claims`` are the retained observations of observed writes
    composed into a Non-Temporal one, which its completion spends; the caller's
    condition stays whatever values survive, and a destruction superseding the
    write keeps it too. ``replaces`` says the row states a complete writable
    state, whose window a temporal replacement fills.
    """

    instruction: PreparedKeyedWrite
    expectation: TargetExpectation
    scope: VersionedStateKey | ObjectKey
    claims: tuple[RetainedObservation, ...] = ()
    replaces: bool = False

    def __post_init__(self) -> None:
        if self.instruction.mutation in INSERT_MUTATIONS or len(self.instruction.rows) != 1:
            raise ValueError(
                "a caller's condition addresses one existing object: "
                f"`{self.instruction.mutation}` on "
                f"{self.instruction.target.identity.canonical!r} is no such write"
            )


def target_write(
    prepared: PreparedTargetWrite, families: inheritance.InheritanceFacet
) -> TargetKeyedWrite:
    """``prepared`` as the buffer item that carries its caller's condition: the
    keyed update it executes as, claimed at the scope its expectation names."""
    instruction = target_instruction(prepared)
    key = resolve_object_key(instruction, families)
    assert key is not None  # preparation required the key
    expectation = prepared.expectation
    return TargetKeyedWrite(
        instruction=instruction,
        expectation=expectation,
        scope=(
            VersionedStateKey(key, expectation.version)
            if isinstance(expectation, ExpectedVersion)
            else key
        ),
        replaces=prepared.replaces,
    )


type ClaimedKeyedWrite = ObservedKeyedWrite | ObjectClaimedWrite
"""One keyed write travelling with the claim its verb took for it, at either
scope. The two carriers share what coalescing manipulates — an instruction —
and differ only in the grain their claims are taken at."""


def buffered_write(
    instruction: PreparedWrite,
    evidence: SettledEvidence | None,
    *,
    source: Completion | None = None,
    authority: InsertionIdentity | None = None,
) -> PreparedWrite | ClaimedKeyedWrite | InsertionKeyedWrite:
    """``instruction`` as the buffer item that settles against ``evidence``.

    Retained observations travel with the write so settlement can spend them,
    while a bare observation has no retained claim. With no evidence, the
    instruction travels bare, or carries the insertion ``authority`` that
    licenses it. ``source`` is the authority an object-claimed write's source
    carries in place of an observation; any other evidence already is its
    source's authority.
    """
    if evidence is None:
        if authority is not None:
            if not isinstance(instruction, PreparedKeyedWrite):
                raise TypeError("an insertion's authority licenses keyed writes alone")
            return InsertionKeyedWrite(instruction=instruction, identity=authority)
        return instruction
    if not isinstance(instruction, PreparedKeyedWrite):
        raise TypeError(
            "only a keyed write settles against evidence of its own; a predicate-selected write "
            "materializes to a Materialized Write Group with its own aligned evidence"
        )
    if isinstance(evidence, ObjectKey):
        return ObjectClaimedWrite(instruction=instruction, source=source)
    if isinstance(evidence, RetainedObservation):
        return ObservedKeyedWrite(
            instruction=instruction, observation=evidence.evidence, claim=evidence
        )
    return ObservedKeyedWrite(instruction=instruction, observation=evidence)


@dataclass(frozen=True, slots=True)
class TemporalContribution:
    """What one admitted write of a temporal object keeps once it is composed:
    its source condition and requested window, not its values.

    ``observation`` is the evidence an observed write settles against and
    ``claim`` its retained form, which successful completion spends. A write a
    caller addressed has neither, and ``condition`` is the Transaction-Time
    start its caller requires of the coverage at its window's start. A write an
    admitted insertion authorized has none of the three: its condition is the
    coverage at its window's start, the insertion's own anchor, which execution
    requires. Values the write assigned live in the composed transform, where a
    later write may overwrite them; the condition stays required whatever
    happens to them.
    """

    kind: Literal["assignment", "destructive"]
    bounds: PreparedTemporalBounds
    observation: WriteObservation | None
    claim: RetainedObservation | None
    condition: ExpectedTxStart | None = None


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
    transform: TemporalTransform

    @property
    def assigns(self) -> bool:
        """Whether the composition still assigns somewhere, rather than only
        destroying."""
        return self.transform.assigns


@dataclass(frozen=True, slots=True)
class ChainedTemporalWrite(ComposedTemporalWrite):
    """One ordering-barrier region's composition of a temporal object whose
    other pending writes stand in other regions of the same buffer.

    A barrier keeps every write on its own side, so each region's writes of the
    object execute as their own unit. ``follows`` marks a composition an
    earlier region's writes of the object precede: it binds to the coverage
    those left, carrying the conditions they already proved. ``leads`` marks
    one a later region's writes follow: it records what it derived from each
    original it transformed, for them.
    """

    leads: bool = False
    follows: bool = False


def chained(
    held: TemporalKeyedWrite | ComposedTemporalWrite,
    key_name: str,
    *,
    leads: bool = False,
    follows: bool = False,
) -> ChainedTemporalWrite:
    """``held`` as a composition of its barrier region, leading or following
    the object's writes in other regions as stated, and as it already did."""
    composed = held if isinstance(held, ComposedTemporalWrite) else _composed(held, key_name)
    if isinstance(composed, ChainedTemporalWrite):
        leads = leads or composed.leads
        follows = follows or composed.follows
    return ChainedTemporalWrite(
        target=composed.target,
        key=composed.key,
        contributions=composed.contributions,
        transform=composed.transform,
        leads=leads,
        follows=follows,
    )


type TemporalKeyedWrite = ObservedKeyedWrite | InsertionKeyedWrite | TargetKeyedWrite
"""One keyed write of a temporal object that composes with that object's other
pending writes: an observed one, one an admitted insertion authorized, or one a
caller addressed."""


def temporal_contribution(item: TemporalKeyedWrite) -> TemporalContribution:
    """``item``'s lasting part once composed."""
    observed = isinstance(item, ObservedKeyedWrite)
    expectation = item.expectation if isinstance(item, TargetKeyedWrite) else None
    return TemporalContribution(
        kind="assignment" if item.instruction.mutation in UPDATE_MUTATIONS else "destructive",
        bounds=item.instruction.bounds,
        observation=item.observation if observed else None,
        claim=item.claim if observed else None,
        condition=expectation if isinstance(expectation, ExpectedTxStart) else None,
    )


def composed_temporal_write(
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
        transform=_composed_transform(
            held.transform, arriving.instruction, key_name, replaces=_replaces(arriving)
        ),
    )


def _composed(item: TemporalKeyedWrite, key_name: str) -> ComposedTemporalWrite:
    row = item.instruction.rows[0]
    return ComposedTemporalWrite(
        target=item.instruction.target,
        key={key_name: row[key_name]},
        contributions=(temporal_contribution(item),),
        transform=_composed_transform(
            EMPTY_TRANSFORM, item.instruction, key_name, replaces=_replaces(item)
        ),
    )


def _replaces(item: TemporalKeyedWrite) -> bool:
    return isinstance(item, TargetKeyedWrite) and item.replaces


def composed_alone(item: TemporalKeyedWrite, key_name: str) -> ComposedTemporalWrite:
    """``item`` as the composition of itself alone."""
    return _composed(item, key_name)


def _composed_transform(
    transform: TemporalTransform,
    instruction: PreparedKeyedWrite,
    key_name: str,
    *,
    replaces: bool = False,
) -> TemporalTransform:
    bounds = instruction.bounds
    assigned = (
        {name: value for name, value in instruction.rows[0].items() if name != key_name}
        if instruction.mutation in UPDATE_MUTATIONS
        else None
    )
    return transform.then(
        valid_from=bounds.valid_from, until=bounds.until, assigned=assigned, replaces=replaces
    )


@dataclass(frozen=True, slots=True)
class PendingOpening:
    """A still-unflushed insert of a Bitemporal object, with the writes its
    insertion authorized since composed over the coverage it opens.

    ``transform`` applies to the opening's own window exactly as a stored
    range's transform applies to stored coverage: assigned members replace the
    opening's values inside each write's window, destruction removes coverage
    there, and nothing outside the opening is ever created. ``intents`` keeps
    each composed write's window so admission can judge the next one.
    """

    insert: PreparedKeyedWrite
    transform: TemporalTransform
    intents: tuple[WriteIntent, ...]

    def then(self, instruction: PreparedKeyedWrite, key_name: str) -> PendingOpening:
        """This opening with ``instruction`` composed after its earlier writes."""
        intent = keyed_intent(instruction)
        assert intent is not None  # an opening's own writes are no inserts
        return PendingOpening(
            insert=self.insert,
            transform=_composed_transform(self.transform, instruction, key_name),
            intents=(*self.intents, intent),
        )

    @property
    def survives(self) -> bool:
        """Whether any of the opened coverage survives its composed writes."""
        return bool(self._bound_pieces())

    def pieces(self) -> tuple[PreparedKeyedWrite, ...]:
        """The inserts the opening flushes as: one per nonempty interval its
        composed writes leave, carrying the opening's values with each
        interval's assignments overlaid."""
        insert = self.insert
        row = insert.rows[0]
        pieces: list[PreparedKeyedWrite] = []
        for piece in self._bound_pieces():
            assert isinstance(piece.start, dt.datetime)  # an opening's own bound or an edit's
            end = piece.end
            pieces.append(
                derive_opening(
                    insert,
                    row if piece.assigned is None else {**row, **piece.assigned},
                    valid_from=piece.start,
                    until=None if is_open_bound(end) else cast("dt.datetime", end),
                )
            )
        return tuple(pieces)

    def _bound_pieces(self) -> tuple[BoundPiece, ...]:
        bounds = self.insert.bounds
        valid_from = bounds.valid_from
        assert valid_from is not None  # a Bitemporal opening states its start
        until = bounds.until
        return self.transform.pieces(valid_from, INFINITY_LITERAL if until is None else until)


@dataclass(frozen=True, slots=True)
class AfterRemoval:
    """Inserts of an object whose earlier insertion an earlier pending write
    removes completely, which execute only after everything authored before
    them: an insert ordinarily runs ahead of every removal, and these must
    follow the one that clears their way."""

    inserts: tuple[PreparedKeyedWrite, ...]


@dataclass(frozen=True, slots=True)
class FollowingKeyedWrite:
    """A Non-Temporal write of one claimed scope that an ordering barrier keeps
    after the writes of that scope standing before it.

    Those writes execute first, each advancing a versioned row once, so this
    one starts from the state they leave: ``advances`` versions past the state
    its own scope names.
    """

    write: ObservedKeyedWrite | InsertionKeyedWrite | TargetKeyedWrite
    advances: int


BufferItem = (
    PreparedWrite
    | ClaimedKeyedWrite
    | InsertionKeyedWrite
    | TargetKeyedWrite
    | MaterializedWriteGroup
)


def buffered_instruction(item: BufferItem) -> PreparedWrite:
    """The write instruction ``item`` carries, unwrapped from any envelope.

    A Materialized Write Group answers the predicate write it materialized,
    which is what dependency ordering ranks it by.
    """
    if isinstance(item, MaterializedWriteGroup):
        return item.mutation
    if isinstance(
        item, ObservedKeyedWrite | ObjectClaimedWrite | InsertionKeyedWrite | TargetKeyedWrite
    ):
        return item.instruction
    return item
