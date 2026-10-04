from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

from parallax.core import inheritance, temporal_read
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, EntityMetadata, Metamodel
from parallax.core.temporal_read import TemporalShape, milestone_edge
from parallax.core.unit_work.claims import SettledEvidence
from parallax.core.unit_work.columns import ChunkedColumnBuilder, ColumnSlice, whole
from parallax.core.unit_work.instructions import (
    INSERT_MUTATIONS,
    UPDATE_MUTATIONS,
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    PreparedTemporalBounds,
    PreparedWrite,
)
from parallax.core.unit_work.observe import WriteObservation
from parallax.core.unit_work.plan import Completion
from parallax.core.unit_work.planner import (
    ObjectKey,
    ObservedStateKey,
    TemporalStateKey,
    VersionedStateKey,
)
from parallax.core.unit_work.retain import RetainedObservation
from parallax.core.unit_work.temporal import EMPTY_TRANSFORM, TemporalTransform

if TYPE_CHECKING:
    from parallax.core.inheritance import EntityMemberSelection

__all__ = [
    "BufferItem",
    "ClaimedKeyedWrite",
    "ComposedTemporalWrite",
    "GroupStates",
    "MaterializedWriteGroup",
    "ObjectClaimedWrite",
    "ObservedKeyedWrite",
    "PredecessorRows",
    "PredecessorRowsBuilder",
    "TemporalContribution",
    "VersionedEvidence",
    "VersionedEvidenceBuilder",
    "buffered_instruction",
    "buffered_write",
    "composed_alone",
    "composed_temporal_write",
    "group_state_keys",
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
    An update's row is its literal assignment set: the identity plus every
    member its producer expressed, each written whatever value the source
    observed for it.
    """

    instruction: PreparedKeyedWrite
    observation: WriteObservation
    claim: RetainedObservation | None = None

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


type ClaimedKeyedWrite = ObservedKeyedWrite | ObjectClaimedWrite
"""One keyed write travelling with the claim its verb took for it, at either
scope. The two carriers share what coalescing manipulates — an instruction —
and differ only in the grain their claims are taken at."""


def buffered_write(
    instruction: PreparedWrite,
    evidence: SettledEvidence | None,
    *,
    source: Completion | None = None,
) -> PreparedWrite | ClaimedKeyedWrite:
    """``instruction`` as the buffer item that settles against ``evidence``.

    Retained observations travel with the write so settlement can spend them,
    while a bare observation has no retained claim. With no evidence, the
    instruction travels bare. ``source`` is the authority an object-claimed
    write's source carries in place of an observation; any other evidence
    already is its source's authority.
    """
    if evidence is None:
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
    """What one admitted observed write of a temporal object keeps once it is
    composed: its source condition and requested window, not its values.

    ``observation`` is the evidence the write settles against and ``claim`` its
    retained form, which successful completion spends; ``scope`` is the exact
    state that evidence observed. Values the write assigned live in the
    composed transform, where a later write may overwrite them; the condition
    stays required whatever happens to them.
    """

    kind: Literal["assignment", "destructive"]
    bounds: PreparedTemporalBounds
    observation: WriteObservation
    claim: RetainedObservation | None


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


def temporal_contribution(item: ObservedKeyedWrite) -> TemporalContribution:
    """``item``'s lasting part once composed."""
    return TemporalContribution(
        kind="assignment" if item.instruction.mutation in UPDATE_MUTATIONS else "destructive",
        bounds=item.instruction.bounds,
        observation=item.observation,
        claim=item.claim,
    )


def composed_temporal_write(
    held: ObservedKeyedWrite | ComposedTemporalWrite, arriving: ObservedKeyedWrite, key_name: str
) -> ComposedTemporalWrite:
    """``held`` followed by ``arriving``, one temporal object's writes composed
    in authored order.

    The arriving write's values replace earlier ones per member inside its own
    window and destroy coverage there if it is destructive; every earlier
    condition stays.
    """
    if isinstance(held, ObservedKeyedWrite):
        held = _composed(held, key_name)
    return ComposedTemporalWrite(
        target=held.target,
        key=held.key,
        contributions=(*held.contributions, temporal_contribution(arriving)),
        transform=_composed_transform(held.transform, arriving, key_name),
    )


def _composed(item: ObservedKeyedWrite, key_name: str) -> ComposedTemporalWrite:
    row = item.instruction.rows[0]
    return ComposedTemporalWrite(
        target=item.instruction.target,
        key={key_name: row[key_name]},
        contributions=(temporal_contribution(item),),
        transform=_composed_transform(EMPTY_TRANSFORM, item, key_name),
    )


def composed_alone(item: ObservedKeyedWrite, key_name: str) -> ComposedTemporalWrite:
    """``item`` as the composition of itself alone."""
    return _composed(item, key_name)


def _composed_transform(
    transform: TemporalTransform, item: ObservedKeyedWrite, key_name: str
) -> TemporalTransform:
    instruction = item.instruction
    bounds = instruction.bounds
    assigned = (
        {name: value for name, value in instruction.rows[0].items() if name != key_name}
        if instruction.mutation in UPDATE_MUTATIONS
        else None
    )
    return transform.then(valid_from=bounds.valid_from, until=bounds.until, assigned=assigned)


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
