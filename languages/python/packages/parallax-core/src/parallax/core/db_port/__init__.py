"""``parallax.core.db_port`` enforcement scope (m-db-port).

The abstract database seam, in two halves that are used by different callers.

**Execution.** :class:`DatabaseConnection` is what the layers above the seam
call to run compiled SQL and demarcate transactions. It names ``dialect`` (the
SQL spelling its statements are written in), ``execute`` (row-oriented),
``execute_pipeline`` (independent reads in one transport round trip),
``execute_write`` (affected-row count), and ``transaction`` (callback reporting a
:data:`TransactionOutcome`, at an optionally requested isolation) — and nothing
more. The portable isolation vocabulary that option is named in lives here too,
because the connection is what carries the value from a caller to an adapter and
neither end may name a level the other cannot. The dialect is the connection's
because the connection is what executes: a caller reads it off the value it
already has rather than choosing a second one beside it.

**Lifetime.** :class:`DatabaseAdapter` is immutable configuration,
:class:`DatabaseRuntime` is the running resource one connected handle owns, and
:class:`ConnectionContext` is one single-use acquisition that yields a scoped
:class:`DatabaseConnection` and reports a :data:`CleanupResult` when it ends.
Query code receives execution alone; composition receives the lifetime. That
split is what lets a connection be acquired for exactly one operation without
any statement being able to acquire or release one.

A runtime that manages a pool also publishes a :class:`PoolMetricsSource`, whose
:data:`PoolSample` answers with :class:`PoolMeasurements`, with an ordinary
failure to read them, or with the runtime having closed. That is the whole
pool-wide contract here: what may be measured belongs to the resource, and who
is interested belongs to `m-execution-lifecycle`.

The seam depends on nothing application-specific (no driver, no pool library, no
concrete database) — the dialect layer is pure and the diagnostic projection a
cleanup issue carries is standard-library-only — so any layer may hold either
half without acquiring a database dependency. Concrete adapters
(`parallax.postgres`) implement both at the composition root and carry the
normalize-at-boundary contract: rows come back as managed values, never raw
driver representations. They carry the failure-identity contract too: an error
the connection makes to report a failure — raised by a statement call, or carried
by a transaction outcome — is an instance shared with no other invocation.
``m-db-port`` depends on ``m-core`` and ``m-dialect``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal, Protocol, cast, get_args, runtime_checkable

from parallax.core.base import DocumentReadOrdinals
from parallax.core.db_port._pool_metrics import (
    PoolAvailable,
    PoolDetached,
    PoolMeasurements,
    PoolMetricsSource,
    PoolSample,
    PoolUnavailable,
)
from parallax.core.db_port._resource_logging import (
    RESOURCE_LOGGER_NAME,
    ResourceCondition,
    report_resource_issues,
    report_unregistration_failure,
)
from parallax.core.db_port._resources import (
    AcquisitionReason,
    CleanupCode,
    CleanupIssue,
    CleanupPhase,
    CleanupResult,
    ConnectionAcquisitionError,
    ConnectionContext,
    DatabaseAdapter,
    DatabaseRuntime,
    DatabaseStartupError,
    Invalidated,
    Returned,
    StartupPhase,
    Unrelinquished,
)
from parallax.core.dialect import Dialect

__all__ = [
    "ISOLATION_LEVELS",
    "RESOURCE_LOGGER_NAME",
    "AcquisitionReason",
    "BeginFailed",
    "Bind",
    "CallbackRaised",
    "CleanupCode",
    "CleanupIssue",
    "CleanupPhase",
    "CleanupResult",
    "CommitFailed",
    "Committed",
    "ConnectionAcquisitionError",
    "ConnectionContext",
    "DatabaseAdapter",
    "DatabaseConnection",
    "DatabaseRuntime",
    "DatabaseStartupError",
    "DeclaresDialect",
    "DocumentReadOrdinals",
    "Invalidated",
    "IsolationLevel",
    "JsonDocument",
    "MappingRow",
    "PipelineStatement",
    "PoolAvailable",
    "PoolDetached",
    "PoolMeasurements",
    "PoolMetricsSource",
    "PoolSample",
    "PoolUnavailable",
    "ResourceCondition",
    "Returned",
    "RollbackFailed",
    "RollbackTrigger",
    "RolledBack",
    "Row",
    "StartupPhase",
    "TransactionOutcome",
    "Unrelinquished",
    "isolation_level",
    "report_resource_issues",
    "report_unregistration_failure",
]

# A neutral bind value (m-core scalars) or the language's managed carriers.
Bind = object
# A managed result row in statement select-list order.
Row = tuple[object, ...]
MappingRow = Mapping[str, object]


@dataclass(frozen=True, slots=True)
class PipelineStatement:
    """One independent row-returning statement in a pipeline batch."""

    sql: str
    binds: tuple[Bind, ...] = ()
    document_reads: tuple[DocumentReadOrdinals, ...] = ()


# The closed portable isolation vocabulary (m-db-port). Each level names the
# anomalies it forbids rather than any database's own spelling: `read_committed`
# forbids dirty reads, `repeatable_read` also forbids nonrepeatable reads, and
# `serializable` additionally makes the committed participating transactions
# equivalent to some serial order. Read Uncommitted and vendor-specific levels are
# outside it, so there is no spelling here to request one by.
IsolationLevel = Literal["read_committed", "repeatable_read", "serializable"]

ISOLATION_LEVELS: Final[frozenset[str]] = frozenset(get_args(IsolationLevel))


def isolation_level(value: object) -> IsolationLevel:
    """Return the vocabulary's own spelling of ``value``, or raise ``ValueError``.

    The vocabulary is closed, so a name outside it names no guarantee any adapter
    could map — which makes it the caller's mistake rather than a database's
    refusal, reportable before anything opens. Every value outside it is refused
    the one way, whatever its type: the candidate is compared to each level rather
    than looked up in the set, since a value no set can be asked about (an
    unhashable ``str`` subclass) would make membership alone raise ``TypeError``.

    What comes back is the matched level itself, never the caller's own object, so
    an accepted value is a plain hashable ``str`` an adapter can key its per-level
    spelling table by.
    """
    known = sorted(ISOLATION_LEVELS)
    if isinstance(value, str):
        for level in known:
            if value == level:
                return cast("IsolationLevel", level)
    raise ValueError(f"isolation must be one of {known}, got {value!r}")


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
    """The boundary never opened as asked, so the body never ran.

    No work of the caller's was attempted and nothing of it needs undoing, which
    is what separates this from every other unhappy outcome. An adapter may have
    driven its driver as far as a physical transaction and then failed to bring
    it to the boundary that was asked for — a refused ``isolation``, say; undoing
    that empty transaction is the adapter's own business and is finished before
    this outcome is reported, so what a caller holds is a boundary that never
    opened either way.
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
class DatabaseConnection(Protocol):
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

    @property
    def dialect(self) -> Dialect:
        """The SQL spelling every statement crossing this port is written in.

        A decorating or transaction-scoped port reports the dialect of the port
        it stands in for rather than one of its own, so the answer is the same
        whichever port in a chain a caller happens to hold.
        """
        ...

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

    def execute_pipeline(self, statements: Sequence[PipelineStatement]) -> list[list[Row]]:
        """Run independent row reads in one transport round trip, preserving order."""
        ...

    def execute_write(self, sql: str, binds: Sequence[Bind]) -> int:
        """Run a DML statement and return the driver's affected-row count."""
        ...

    def transaction[T](
        self, body: Callable[[DatabaseConnection], T], *, isolation: IsolationLevel | None = None
    ) -> TransactionOutcome[T]:
        """Run ``body`` inside one database transaction and report how it ended.

        Commit on the body's normal return, roll back on any exception it raises,
        and answer which of begin, callback, commit, or rollback decided that —
        distinctions a caller cannot recover from a raised error alone, and which
        decide whether the work may be retried and whether the connection is still
        trustworthy. No boundary failure is raised; the caller consumes the outcome
        and decides what its own caller sees.

        ``isolation`` is the portable :data:`IsolationLevel` this boundary is
        asked to open at, carried across unchanged; ``None`` asks for nothing and
        leaves whatever the adapter or its driver already defaults to. An
        implementation MAPS it to whatever its own database needs to forbid that
        level's anomalies for this attempt, and one that cannot forbid them
        reports a boundary failure rather than opening at a level it can — a
        request silently weakened is indistinguishable from one honored. The
        setting is the BOUNDARY's rather than the connection's: it governs this
        transaction alone and no later one on the same connection.
        """
        ...


class DeclaresDialect(Protocol):
    """Dialect metadata readable off a port's CLASS, before any connection opens.

    A composition root selects a concrete adapter and needs the dialect it will
    execute in without building one — nothing here reaches a driver, a socket, or
    a container. It is a separate protocol because :class:`DatabaseConnection` states
    ``dialect`` as a read-only property, and a property is unreachable through
    ``type[...]``.
    """

    dialect: Dialect
