from __future__ import annotations

import datetime as dt
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
    "CompletionRequest",
    "CoverageReadRequest",
    "CoverageTerm",
    "RowConsumer",
    "RowReadRequest",
    "RowRequest",
    "SelectionReadRequest",
    "TargetReadRequest",
    "consume_coverage",
    "consume_selection",
    "consume_target",
]

# The predicate mutations that carry Assignments; the rest take none at all and
# their verbs' signatures say so.
_ASSIGNMENT_BEARING: Final[frozenset[PredicateMutation]] = frozenset({"amend", "amendUntil"})


@dataclass(frozen=True, slots=True)
class SelectionReadRequest:
    """The current rows a materializing predicate-selected write changes: every
    row its predicate selects on a versioned or temporal target.

    ``key_position`` and ``version_position`` place the family key and, on a
    versioned target, its version in the target's member selection. A temporal
    target has no version, and its rows become complete Predecessor Rows, so
    its read projects every declared document (:attr:`predecessors`).

    ``valid_from`` is the Valid-Time instant a Bitemporal amendment selects its
    objects at, each by the row current there; ``None`` selects at Latest on
    every axis. A selection at an instant keeps every row it matches
    (:func:`consume_selection`).
    """

    write: PreparedPredicateWrite
    key_position: int
    version_position: int | None
    valid_from: dt.datetime | None = None

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
    Bitemporal object, which is ``None`` for any other.

    Where it ``retains`` the row, the range the write settles may reuse it as
    coverage, so the row is read whole — every Value Object occurrence and the
    raw Structured Column too — but judged only as a read of the row alone
    judges it: each occurrence reaches the consumer pending, the unexamined
    input its classification takes, for a :class:`CompletionRequest` to judge
    if the row is reused."""

    entity: EntityMetadata
    key: ObjectKey
    valid_from: ManagedValue | None
    retains: bool = False


@dataclass(frozen=True, slots=True)
class CoverageTerm:
    """One object's part of a coverage read: its current rows overlapping any
    of ``valid_time_windows`` — sorted, disjoint, and never adjacent. A
    Transaction-Time-Only object has no Valid Time, so it names no window and
    its one current row is its coverage."""

    key_value: ManagedValue
    valid_time_windows: tuple[TimeInterval, ...]


@dataclass(frozen=True, slots=True)
class CoverageReadRequest:
    """The current coverage deferred ranges bind to: every row each of
    ``terms`` names, read whole, in one statement, under the shared row lock
    when ``locking``. Each row is returned whole however little of it a window
    reaches, and the rows of several objects are told apart by their keys."""

    entity: EntityMetadata
    key_attribute: AttributeIdentity
    terms: tuple[CoverageTerm, ...]
    locking: bool


@dataclass(frozen=True, slots=True)
class CompletionRequest:
    """Rows an earlier :class:`TargetReadRequest` that ``retains`` acquired,
    their Value Object occurrences still pending, to be judged as an ordinary
    read judges them before they become evidence.

    It reads nothing: no statement runs, and its consumer receives the
    completed rows, in order, beside the raw ``documents`` they were read with
    — ``None`` where the read projected no Structured Column."""

    entity: EntityMetadata
    key_attribute: AttributeIdentity
    rows: tuple[tuple[object, ...], ...]
    documents: tuple[object | None, ...] | None


type RowReadRequest = SelectionReadRequest | TargetReadRequest | CoverageReadRequest

type RowRequest = RowReadRequest | CompletionRequest
"""Everything a unit of work asks its row acquisition for: a read, or the
completion of rows a read already acquired."""

type RowConsumer[Request: RowRequest, Result] = Callable[
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
    request reads in the Write Batch whose flush reaches its deferred range. A
    :class:`CompletionRequest` reads nothing: its rows are judged with no
    statement, Database Call, or activity, and its consumer runs over them.
    """

    def __call__[Request: RowRequest, Result](
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
    row's original position. A selection at a Valid-Time instant eliminates
    nothing: its amendment reaches later coverage too, which equality at the
    start says nothing about.
    """
    del root_count
    change = (
        None
        if request.valid_from is not None
        else _effective_change(request.write, selection, absent)
    )
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
) -> tuple[int, tuple[object, ...] | None, object | None]:
    """How many roots the target read returned, and the judged row of a unique
    one beside the raw document it was read with: no other root is judged, so
    a read returning several is decided by its count alone."""
    del request, selection, absent
    if root_count != 1:
        return root_count, None, None
    return root_count, next(rows), None if documents is None else documents[0]


def consume_coverage(
    request: CoverageReadRequest | CompletionRequest,
    selection: EntityMemberSelection,
    rows: Iterator[tuple[object, ...]],
    absent: object,
    documents: Sequence[object | None] | None,
    root_count: int,
) -> PredecessorRows | None:
    """Every current row the coverage read returned, or the completion
    completed, as complete Predecessor Rows, or ``None`` where there was none."""
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
