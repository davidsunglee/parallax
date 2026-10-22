from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Protocol

from parallax.core.base import ManagedValue
from parallax.core.inheritance import EntityMemberSelection
from parallax.core.metamodel import AttributeIdentity, EntityMetadata
from parallax.core.temporal_read import TimeInterval
from parallax.core.write_plan.keys import ObjectKey
from parallax.core.write_plan.predecessor_rows import PredecessorRows, PredecessorRowsBuilder

__all__ = [
    "AcquireRows",
    "CompletionRequest",
    "CoverageReadRequest",
    "CoverageTerm",
    "RowConsumer",
    "RowReadRequest",
    "RowRequest",
    "TargetReadRequest",
    "consume_coverage",
    "consume_target",
]


@dataclass(frozen=True, slots=True)
class TargetReadRequest:
    """The stored row a target write of ``key`` starts from, read under
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


type RowReadRequest = TargetReadRequest | CoverageReadRequest

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

    A target request reads in a Read of its own; a coverage request reads in
    the Flush activity of the flush reaching its deferred range. A
    :class:`CompletionRequest` reads nothing: its rows are judged with no
    statement, Database Call, or activity, and its consumer runs over them.
    """

    def __call__[Request: RowRequest, Result](
        self, request: Request, consumer: RowConsumer[Request, Result], /
    ) -> Result: ...


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
    try:
        if root_count != 1:
            return root_count, None, None
        return root_count, next(rows), None if documents is None else documents[0]
    finally:
        del rows, documents


def consume_coverage(
    request: CoverageReadRequest | CompletionRequest,
    selection: EntityMemberSelection,
    rows: Iterator[tuple[object, ...]],
    absent: object,
    documents: Sequence[object | None] | None,
    root_count: int,
) -> PredecessorRows | None:
    """Every current row the coverage read returned, or the completion
    completed, as complete Predecessor Rows, or ``None`` where there was none.

    However it leaves, it drops the builder and its borrowed row and document
    references; only the returned evidence keeps what it adopted."""
    del root_count
    evidence = PredecessorRowsBuilder(
        selection,
        key_position=selection.position(request.key_attribute),
        absent=absent,
        documents=documents is not None,
    )
    row: tuple[object, ...] | None = None
    try:
        for position, row in enumerate(rows):
            evidence.append(row, None if documents is None else documents[position])
        return evidence.seal()
    finally:
        del evidence, rows, documents, row
