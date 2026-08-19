"""The Root Execution descriptor and the closed event algebra its activities emit.

Every transition is its own immutable concrete type admitting only its own
fields: there is no generic attribute bag, no kind-plus-payload record, and no
callback return value. :data:`ActivityStarted` and :data:`ActivityFinished` are
union aliases over those concretes, which is what lets a consumer match them
exhaustively.

The correlation envelope is shared by inheritance rather than restated per
transition, so ``event.sequence`` reads the same off any member of the union
while the union itself stays a closed set of concrete types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from parallax.core.execution_lifecycle._diagnostics import (
    ActivityFailure,
    DatabaseFailureDiagnostic,
)
from parallax.core.sql_gen import LoweredStatement

type RootExecutionKind = Literal["READ", "TRANSACTION_INVOCATION", "SNAPSHOT_STREAM"]
"""Which outermost Handle operation a Root Execution describes."""

type ReadInterface = Literal["TYPED", "WIRE", "ROWS"]
"""Which read interface published a Read's result; ``ROWS`` is the internal
values lane."""

type DatabaseCallKind = Literal["READ", "WRITE"]
"""Whether a Database Call ran a query or DML — carried so a FAILED call stays
classifiable without parsing its SQL."""


@dataclass(frozen=True, slots=True)
class RootExecution:
    """One outermost Handle operation and everything it causally contains.

    ``id`` is a random UUIDv4 whose equality and canonical text are meaningful;
    concurrent outermost operations are distinct roots with independent
    sequences and no implied global order.
    """

    id: UUID
    kind: RootExecutionKind


@dataclass(frozen=True, slots=True)
class _Event:
    """The correlation envelope every transition carries.

    ``sequence`` is the one-based contiguous delivery position within the root,
    assigned immediately before delivery. ``activity_id`` is one-based and
    contiguous within the root, assigned by a Started transition and reused by
    its Finished peer. ``parent_activity_id`` is absent only for the root
    activity; otherwise it names an activity started earlier in the same root.

    Never constructed directly: it exists so the envelope has one definition
    rather than fourteen, while the event union stays a closed set of concrete
    transitions.
    """

    execution_id: UUID
    sequence: int
    activity_id: int
    parent_activity_id: int | None


@dataclass(frozen=True, slots=True)
class ReadCompleted:
    """The Read published its public result."""


@dataclass(frozen=True, slots=True)
class ReadFailed:
    """The Read did not reach publication."""

    failure: ActivityFailure


type ReadOutcome = ReadCompleted | ReadFailed
"""How a Read ended, a closed union of exactly one member."""


@dataclass(frozen=True, slots=True)
class ReadStarted(_Event):
    """A Read opened over ``target`` through ``interface``.

    It starts after public preflight and any read-dependency Write Batch, and
    spans planning, lowering, all of its Database Calls, conversion,
    materialization, and publication.
    """

    target: str
    interface: ReadInterface


@dataclass(frozen=True, slots=True)
class ReadFinished(_Event):
    """The Read reached its terminal outcome."""

    outcome: ReadOutcome


@dataclass(frozen=True, slots=True)
class DatabaseReadCompleted:
    """A query call's completion: the PHYSICAL number of rows the statement
    returned — never a count of result roots, unique graph nodes, or projection
    views."""

    returned_rows: int


@dataclass(frozen=True, slots=True)
class DatabaseWriteCompleted:
    """A DML call's completion: the affected-row count the driver reported.

    A count that falls short of what the step addressed is still a COMPLETION —
    the call reached the database and came back — and post-call enforcement of
    that shortfall is the enclosing Write Batch's failure, not the call's.
    """

    affected_rows: int


@dataclass(frozen=True, slots=True)
class DatabaseCallFailed:
    """The port could not complete the call."""

    diagnostic: DatabaseFailureDiagnostic


type DatabaseCallOutcome = DatabaseReadCompleted | DatabaseWriteCompleted | DatabaseCallFailed
"""How a Database Call ended, a closed union of exactly one member."""


@dataclass(frozen=True, slots=True)
class DatabaseCallStarted(_Event):
    """One attempted round trip to the database is about to run.

    ``statement`` is the exact deeply immutable Lowered Statement presented to
    the port. It is BORROWED for synchronous delivery: neither its text nor its
    binds are copied, and a Handler that retains it violates the Handler
    contract.
    """

    target: str
    kind: DatabaseCallKind
    statement: LoweredStatement


@dataclass(frozen=True, slots=True)
class DatabaseCallFinished(_Event):
    """The round trip came back, however it came back.

    ``statement`` repeats the same borrowed value Started carried.
    ``duration_ns`` is monotonic elapsed time around the port invocation alone:
    the clock starts after Started has been delivered and stops before Finished
    is constructed, so Handler time stays outside it.
    """

    statement: LoweredStatement
    duration_ns: int
    outcome: DatabaseCallOutcome


type ActivityStarted = ReadStarted | DatabaseCallStarted
"""Every transition that opens an activity and assigns its ``activity_id``."""

type ActivityFinished = ReadFinished | DatabaseCallFinished
"""Every transition that closes an activity with its terminal outcome."""

type ExecutionEvent = ActivityStarted | ActivityFinished
"""The closed union of concrete transitions a Handler receives."""
