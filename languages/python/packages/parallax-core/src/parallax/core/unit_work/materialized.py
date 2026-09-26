from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from parallax.core import inheritance, temporal_read
from parallax.core.metamodel import AttributeIdentity, Metamodel
from parallax.core.temporal_read import milestone_edge
from parallax.core.unit_work.claims import SettledEvidence
from parallax.core.unit_work.columns import ChunkedColumnBuilder, ColumnSlice, whole
from parallax.core.unit_work.instructions import (
    INSERT_MUTATIONS,
    PreparedKeyedWrite,
    PreparedPredicateWrite,
    PreparedWrite,
)
from parallax.core.unit_work.observe import PredecessorRow, WriteObservation
from parallax.core.unit_work.planner import (
    ObjectKey,
    ObservedStateKey,
    TemporalStateKey,
    VersionedStateKey,
)
from parallax.core.unit_work.retain import RetainedObservation

if TYPE_CHECKING:
    from parallax.core.inheritance import EntityMemberSelection

__all__ = [
    "BufferItem",
    "ClaimedKeyedWrite",
    "MaterializedWriteGroup",
    "ObjectClaimedWrite",
    "ObservedKeyedWrite",
    "PredecessorRows",
    "PredecessorRowsBuilder",
    "VersionedEvidence",
    "VersionedEvidenceBuilder",
    "buffered_instruction",
    "buffered_write",
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

    def predecessor(self, index: int) -> PredecessorRow:
        """Row ``index`` as its Predecessor Row, sharing the retained row and
        document rather than copying them."""
        return PredecessorRow.over_row(
            self.selection, self.rows[index], self.document(index), self.absent
        )


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


def group_state_keys(group: MaterializedWriteGroup, meta: Metamodel) -> Iterator[ObservedStateKey]:
    """Each exact state ``group`` selected, in resolution order, keyed as a
    keyed read's own observation of that row would be."""
    entity = group.mutation.selection.target
    position = inheritance.view(meta).entity(entity.identity)
    if position is None:  # pragma: no cover - the facet covers every accepted Entity
        raise ValueError(f"{entity.identity.canonical}: the model declares no such entity")
    key = position.primary_key.identity.name
    evidence = group.evidence
    if isinstance(evidence, VersionedEvidence):
        for value, version in zip(evidence.keys, evidence.versions, strict=True):
            yield VersionedStateKey(ObjectKey(entity.identity, ((key, value),)), version)
        return
    shape = temporal_read.view(meta).shape(entity.identity)
    if shape is None:  # pragma: no cover - the facet covers every accepted Entity
        raise ValueError(f"{entity.identity.canonical}: the model declares no such entity")
    for index in range(len(evidence)):
        yield TemporalStateKey(
            ObjectKey(entity.identity, ((key, evidence.key(index)),)),
            milestone_edge(shape, evidence, index),
        )


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
            "materializes to a Materialized Write Group with its own aligned evidence"
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
