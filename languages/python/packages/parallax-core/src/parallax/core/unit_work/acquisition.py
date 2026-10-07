from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Final, Protocol

from parallax.core.base import ManagedValue
from parallax.core.document_codec import PreparedEffectiveChange, prepare_effective_change
from parallax.core.inheritance import EntityMemberSelection
from parallax.core.metamodel import AttributeIdentity, EntityMetadata
from parallax.core.temporal_read import TimeInterval
from parallax.core.unit_work.instructions import PredicateMutation, PreparedPredicateWrite
from parallax.core.unit_work.materialized import VersionedEvidence, VersionedEvidenceBuilder
from parallax.core.write_plan.keys import ObjectKey
from parallax.core.write_plan.materialized import PredecessorRows, PredecessorRowsBuilder

__all__ = [
    "AcquireRows",
    "CoverageReadRequest",
    "RowConsumer",
    "RowReadRequest",
    "SelectionReadRequest",
    "TargetReadRequest",
    "consume_coverage",
    "consume_selection",
    "consume_target",
]

# The predicate mutations that carry Assignments; the rest take none at all and
# their verbs' signatures say so.
_ASSIGNMENT_BEARING: Final[frozenset[PredicateMutation]] = frozenset({"update", "updateUntil"})


@dataclass(frozen=True, slots=True)
class SelectionReadRequest:
    """The current rows a materializing predicate-selected write changes: every
    row its predicate selects on a versioned or temporal target.

    ``key_position`` and ``version_position`` place the family key and, on a
    versioned target, its version in the target's member selection. A temporal
    target has no version, and its rows become complete Predecessor Rows, so
    its read projects every declared document (:attr:`predecessors`).
    """

    write: PreparedPredicateWrite
    key_position: int
    version_position: int | None

    @property
    def entity(self) -> EntityMetadata:
        return self.write.selection.target

    @property
    def predecessors(self) -> bool:
        """Whether each selected row is retained whole, as a temporal target's
        Predecessor Row, rather than as its key and observed version."""
        return self.version_position is None


@dataclass(frozen=True, slots=True)
class TargetReadRequest:
    """The stored row a caller-addressed write of ``key`` starts from, read under
    the shared row lock: the row current at Valid-Time ``valid_from`` of a
    Bitemporal object, which is ``None`` for any other."""

    entity: EntityMetadata
    key: ObjectKey
    valid_from: ManagedValue | None


@dataclass(frozen=True, slots=True)
class CoverageReadRequest:
    """The current coverage a deferred range binds to: one object's current rows
    overlapping ``valid_time_window``, read under the shared row lock when
    ``locking``. A Transaction-Time-Only object has no Valid Time, so its window
    is ``None`` and its one current row is the coverage."""

    entity: EntityMetadata
    key_attribute: AttributeIdentity
    key_value: ManagedValue
    valid_time_window: TimeInterval | None
    locking: bool


type RowReadRequest = SelectionReadRequest | TargetReadRequest | CoverageReadRequest

type RowConsumer[Request: RowReadRequest, Result] = Callable[
    [
        Request,
        EntityMemberSelection,
        Iterator[tuple[object, ...]],
        object,
        Sequence[object | None] | None,
        int,
    ],
    Result,
]
"""A stable consumer of one acquisition's rows, invoked with the request, the
target's member selection, each root's judged positional member row on demand,
the marker those rows spell an absent member with, each root's raw Structured
Column aligned to its position — ``None`` where the read projected no such
column — and the number of roots the read returned.

It runs while the read's resources are live, retains only the row and document
references the evidence it returns adopts, and never retains the iterator."""


class AcquireRows(Protocol):
    """The execution capability that performs one row read a unit of work
    requests and hands its rows to ``consumer``, returning what the consumer
    returns once the read's resources are settled, however the consumer left.

    Selection and target requests read in a Read of their own; a coverage
    request reads in the Write Batch whose flush reaches its deferred range.
    """

    def __call__[Request: RowReadRequest, Result](
        self, request: Request, consumer: RowConsumer[Request, Result], /
    ) -> Result: ...


def consume_selection(
    request: SelectionReadRequest,
    selection: EntityMemberSelection,
    rows: Iterator[tuple[object, ...]],
    absent: object,
    documents: Sequence[object | None] | None,
    root_count: int,
) -> VersionedEvidence | PredecessorRows | None:
    """The sealed evidence of every selected row that is not a no-op
    (`m-opt-lock` per-row no-op elimination), or ``None`` where none remains.

    A versioned target's evidence is each row's key and observed version; a
    temporal target's is each row whole, its raw document beside it by the
    row's original position.
    """
    del root_count
    change = _effective_change(request.write, selection, absent)
    version_position = request.version_position
    if version_position is not None:
        versioned = VersionedEvidenceBuilder(
            key_position=request.key_position, version_position=version_position
        )
        for row in rows:
            if change is None or change.any_effective(row):
                versioned.append(row)
        return versioned.seal()
    evidence = PredecessorRowsBuilder(
        selection, key_position=request.key_position, absent=absent, documents=documents is not None
    )
    for position, row in enumerate(rows):
        if change is None or change.any_effective(row):
            evidence.append(row, None if documents is None else documents[position])
    return evidence.seal()


def _effective_change(
    write: PreparedPredicateWrite, selection: EntityMemberSelection, absent: object
) -> PreparedEffectiveChange | None:
    """The codec's effective-change comparison for an assignment-bearing verb,
    prepared once for the whole write from the assignments as authored."""
    if write.mutation not in _ASSIGNMENT_BEARING:
        return None
    return prepare_effective_change(
        selection.shape,
        {
            assignment.attr.rpartition(".")[2]: assignment.value
            for assignment in write.managed_assignments
        },
        absent=absent,
    )


def consume_target(
    request: TargetReadRequest,
    selection: EntityMemberSelection,
    rows: Iterator[tuple[object, ...]],
    absent: object,
    documents: Sequence[object | None] | None,
    root_count: int,
) -> tuple[int, tuple[object, ...] | None]:
    """How many roots the target read returned, and the judged row of a unique
    one: no other root is judged, so a read returning several is decided by
    its count alone."""
    del request, selection, absent, documents
    if root_count != 1:
        return root_count, None
    return root_count, next(rows)


def consume_coverage(
    request: CoverageReadRequest,
    selection: EntityMemberSelection,
    rows: Iterator[tuple[object, ...]],
    absent: object,
    documents: Sequence[object | None] | None,
    root_count: int,
) -> PredecessorRows | None:
    """Every current row the coverage read returned, as complete Predecessor
    Rows, or ``None`` where it returned none."""
    del root_count
    evidence = PredecessorRowsBuilder(
        selection,
        key_position=selection.position(request.key_attribute),
        absent=absent,
        documents=documents is not None,
    )
    for position, row in enumerate(rows):
        evidence.append(row, None if documents is None else documents[position])
    return evidence.seal()
