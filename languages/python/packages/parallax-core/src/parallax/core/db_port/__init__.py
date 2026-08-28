"""``parallax.core.db_port`` enforcement scope (m-db-port).

The abstract runtime database port: the execution interface the layers above the
seam call to run compiled SQL and demarcate transactions. It names
``execute`` (row-oriented), ``execute_write`` (affected-row count), and
``transaction`` (callback reporting a :data:`TransactionOutcome`, at an
optionally requested isolation) — and nothing
more. The port depends on nothing
application-specific (no driver, no concrete database), so any layer may hold it
without acquiring a database dependency. Concrete adapters (`parallax.postgres`)
implement it at the composition root and carry the normalize-at-boundary contract:
rows come back as managed values, never raw driver representations. They carry the
failure-identity contract too: an error the port makes to report a failure — raised
by a statement call, or carried by a transaction outcome — is an instance shared
with no other invocation. ``m-db-port`` depends only on ``m-core``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from parallax.core.base import DocumentReadOrdinals

__all__ = [
    "BeginFailed",
    "Bind",
    "CallbackRaised",
    "CommitFailed",
    "Committed",
    "DbPort",
    "DocumentReadOrdinals",
    "JsonDocument",
    "RollbackFailed",
    "RollbackTrigger",
    "RolledBack",
    "Row",
    "TransactionOutcome",
]

# A neutral bind value (m-core scalars) or the language's managed carriers.
Bind = object
# A managed result row: attribute/column name -> managed value.
Row = dict[str, object]


@dataclass(frozen=True, slots=True)
class JsonDocument:
    """A neutral managed carrier for a ``json`` (value-object document) bind.

    Above-seam code (fixture provisioning, the write path) wraps a
    structured-document value in this carrier rather than a driver-specific bind
    type; the concrete adapter recognizes it at its boundary and hands the driver
    its native structured-document bind (psycopg ``Jsonb``, …). Keeping the carrier
    neutral is what lets a concrete adapter own its driver's bind mechanics without
    leaking them into the developer surface (m-db-port: managed carriers only).
    """

    value: object


@dataclass(frozen=True, slots=True)
class Committed[T]:
    """The body returned and the transaction committed; ``value`` is what it returned."""

    value: T


@dataclass(frozen=True, slots=True)
class BeginFailed:
    """The transaction never began, so the body never ran.

    Nothing was attempted and nothing needs undoing, which is what separates this
    from every other unhappy outcome.
    """

    error: Exception


@dataclass(frozen=True, slots=True)
class CallbackRaised:
    """The body raised, and this carries the SAME object it raised.

    The port neither translates nor replaces a caller's own failure, so a driver
    exception the body itself raised arrives here unchanged rather than as a port
    error (which would make a body-authored transient read as one the database
    reported).
    """

    error: BaseException


@dataclass(frozen=True, slots=True)
class CommitFailed:
    """The body returned, and the durability call failed."""

    error: Exception


type RollbackTrigger = CallbackRaised | CommitFailed
"""What made a begun transaction end in a rollback rather than a commit."""


@dataclass(frozen=True, slots=True)
class RolledBack:
    """The trigger ended the transaction and the rollback completed.

    Whatever the body wrote is gone, and the connection is usable again.
    """

    trigger: RollbackTrigger


@dataclass(frozen=True, slots=True)
class RollbackFailed:
    """The rollback the trigger required did not complete.

    Both live errors survive — the one that ended the transaction and the one the
    rollback raised — because either alone misreports what happened. What the
    transaction left behind is unknown, so the connection is no longer trustworthy.
    """

    trigger: RollbackTrigger
    rollback_error: Exception


type TransactionOutcome[T] = Committed[T] | BeginFailed | RolledBack | RollbackFailed
"""How one ``transaction`` call ended: a closed, ephemeral union its caller
consumes immediately. It is neither a public return value nor retained provenance."""


@runtime_checkable
class DbPort(Protocol):
    """The abstract database execution port (m-db-port).

    Every error an implementation MAKES ITSELF to report a failure — a statement
    failure raised by ``execute`` or ``execute_write``, or a transaction-boundary
    failure carried by a ``transaction`` outcome, meaning its begin, its commit, or
    its rollback — is an instance SHARED WITH NO OTHER INVOCATION, built where
    the failure occurs, never cached or pooled, however identical two failures'
    category, native code, and message are. Above the seam a failure is recognized
    by the object caught, and a caller may catch one failed call and keep going, so
    that object is the only thing that says which invocation failed;
    one instance reported twice makes an enclosing activity attribute its failure to
    a sibling call. Nothing above the port can detect a violation, so this holds at
    the failure site or nowhere.

    An exception raised by ``body`` is not the port's error: ``transaction``
    carries the same object back and governs nothing about its identity.
    """

    def execute(
        self,
        sql: str,
        binds: Sequence[Bind],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        """Run a row-returning statement and return managed rows.

        Each document-read pair is folded into one :class:`DocumentRead` under
        the document cell's result key before the row crosses this boundary.
        """
        ...

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        """Run a DML statement and return the driver's affected-row count."""
        ...

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:
        """Run ``body`` inside one database transaction and report how it ended.

        Commit on the body's normal return, roll back on any exception it raises,
        and answer which of begin, callback, commit, or rollback decided that —
        distinctions a caller cannot recover from a raised error alone, and which
        decide whether the work may be retried and whether the connection is still
        trustworthy. No boundary failure is raised; the caller consumes the outcome
        and decides what its own caller sees.

        ``isolation`` is the transaction isolation the caller asked this boundary
        to open at, named in the concrete database's own vocabulary and carried
        through unchanged; ``None`` asks for nothing and leaves whatever the
        adapter or its driver already defaults to. The port neither validates the
        value nor promises what any value means, so an implementation that cannot
        open a boundary as asked reports that failure rather than opening one at
        another level. The setting is the BOUNDARY's rather than the connection's:
        it governs this transaction alone and no later one on the same connection.
        """
        ...
