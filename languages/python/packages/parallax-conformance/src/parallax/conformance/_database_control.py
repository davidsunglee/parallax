"""``parallax.conformance._database_control`` — the harness's own scoped controls.

A conformance run needs two things the shipped ``Database`` deliberately does not
offer, and both are provisioning rather than application concerns:

- a driver session the harness drives DIRECTLY — the per-case schema reset, the
  generated DDL, fixture binds, catalog reads, a case's verbatim golden SQL, and a
  peer holding its own transaction open across statements;
- for the adversarial interleaved lane, a session the harness may CANCEL or
  DESTROY to unstick a worker parked in real driver I/O.

Both are stated here as protocols with no driver in them, so the engine consumes a
declared capability instead of discovering one by duck-typing an adapter's shape.
The native implementation is :mod:`parallax.conformance._postgres_control`, whose
import stays deferred so naming a control costs no psycopg import.

A control is SCOPED: whoever opens one closes it, on success, on failure, and on a
refusal to start. Nothing here is a Session interface for applications — every
value below is development-only, and modeled work still runs through the shipped
``Database`` a control's own connection stands under.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from parallax.core.db_port import DbPort

if TYPE_CHECKING:
    from parallax.core.dialect import Dialect
    from parallax.core.entity import DomainModel
    from parallax.core.execution_lifecycle import ExecutionLifecycleProvider
    from parallax.core.unit_work import Clock
    from parallax.snapshot import handle
    from parallax.snapshot.handle import ServingModel

__all__ = [
    "DriverControl",
    "InterleavedExecution",
    "InterleavedExecutionFactory",
    "ModeledExecution",
    "TerminationReport",
]


@dataclass(frozen=True, slots=True)
class TerminationReport:
    """What one termination attempt established, and every rung that did not.

    ``terminated`` is true only once a rung actually completed, so a caller can
    say whether the session it condemned is really gone. ``failures`` carries
    every miss and every raise the escalation recorded, in the order it met them:
    a rung that fails is never silently swallowed, and a rung that succeeds after
    one that missed leaves that miss in the trail rather than erasing it.
    """

    terminated: bool
    failures: tuple[str, ...] = ()


class DriverControl(DbPort, Protocol):
    """A separately owned driver session the harness executes through directly.

    It is a ``m-db-port`` — same four verbs, same dialect, same translated errors —
    plus the three things provisioning needs and an application never does:
    ``rollback`` to end a held transaction the harness opened itself,
    ``terminate_session`` to end ANOTHER control's session from this one, and
    ``close`` to release this one. Its lifetime belongs to whoever opened it.
    """

    def rollback(self) -> None:
        """Undo whatever this session's own open transaction has done so far."""
        ...

    def terminate_session(self, target: DbPort) -> None:
        """End ``target``'s database session from this separate one.

        The one way to make a genuine ROLLBACK fail: the session an undo would run
        in no longer exists. It reaches the target through the server rather than
        through the target's own transport, so the target is any port that can
        still answer which session it is executing in — a transaction-scoped one
        included.
        """
        ...

    def close(self) -> None:
        """Release this session, ending anything it still holds."""
        ...


class ModeledExecution(Protocol):
    """One connection's own ``Database`` handle and the dialect it spells SQL in.

    A run lane lowers a step in the spelling of the connection about to execute it
    (`m-dialect`), so the two travel together: a handle whose dialect is read off
    somewhere else can lower in one connection's spelling and execute in another's.
    """

    @property
    def database(self) -> handle.Database: ...

    @property
    def dialect(self) -> Dialect: ...


class InterleavedExecution(ModeledExecution, Protocol):
    """A dedicated, support-owned session the interleaved lane may destroy.

    The lane holds two units of work open at once and sequences their steps across
    two worker threads, so a missing hand-off can leave a thread parked in real
    driver I/O that no turnstile release reaches. Unsticking it is destructive, so
    the target is always a session the harness itself opened for this one
    choreography — never a fixture's own connection and never a pooled application
    session.

    ``termination_ladder_trusted`` is a GRANT, not an inspection: declaring it
    truthfully means :meth:`terminate_active` deterministically unblocks whatever
    this session's I/O is doing, so the lane's post-termination join can be
    unbounded. A structural check could never establish that — every rung of an
    implementation can be callable and every one of them can raise — so the lane
    refuses an execution that does not declare it rather than discovering the
    problem as an indefinite hang.
    """

    @property
    def termination_ladder_trusted(self) -> bool: ...

    def cancel_active(self) -> None:
        """Interrupt whatever this session is running, without destroying it.

        Best effort by nature: a cancellation request can be refused, arrive late,
        or have nothing to interrupt. A session that wakes here is never needlessly
        destroyed, which is the only thing this rung promises.
        """
        ...

    def terminate_active(self) -> TerminationReport:
        """Destroy this session, escalating until something establishes it.

        Guaranteed rather than best effort: the caller may rely on the reported
        termination to have unblocked this session's own I/O.
        """
        ...

    def close(self) -> None:
        """Release this execution and the session under it."""
        ...


class InterleavedExecutionFactory(Protocol):
    """How the interleaved lane asks for one dedicated execution.

    The lane opens one per group and never constructs a connection itself, so
    what it holds is this: a call that opens a session, composes the Database
    over it under the model, clock and observation the group runs with, and hands
    both back as one value.
    """

    def __call__(
        self,
        model: DomainModel | ServingModel,
        *,
        clock: Clock | None = None,
        lifecycle_provider: ExecutionLifecycleProvider | None = None,
    ) -> InterleavedExecution: ...
