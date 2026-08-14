"""The unit-of-work shell (m-unit-work).

The transaction scope's stateful machinery around the pure :class:`~parallax.
core.unit_work.write_planner.WritePlanner`: the frame stack (a nested scope
joins the active transaction), the write buffer, the weak index of the observed
states its reads have seen, call-time reads that force-flush pending writes so a
dependent read observes them (read-your-own-writes), and abort — which discards
buffered effects and **withholds** the callback value.

This is deliberately **not** ``db.transact``: there is no public sentinel-backed
option surface and no bounded-retry loop. The shell exposes the
primitives ``db.transact`` composes — :func:`run_unit_of_work` decides join vs. a
new outermost frame, and the outermost frame commits (flushes) or aborts. Because
lowering a Write Plan to DML needs ``m-sql`` (which the DAG forbids ``m-unit-work``
from importing), the shell **delegates** the flush to an injected
:data:`FlushExecutor` supplied by the composition layer that legally sees both;
here it is a neutral callable, so the shell stays DML-free and testable.

A flush has TWO injection points for that reason and not one. The executor
receives a plan, so nothing can be told through it about the work that produces
that plan — and planning is where a flush most often fails. The optional
:class:`WriteBatchStarting` notification is the other half: it carries the
trigger before planning begins, so a composition layer that observes the
transaction learns which batch is under way while the flush can still fail with
nothing executed. Both are plain callables of vocabulary this module already
owns, so neither costs `m-unit-work` a dependency.

The active transaction is tracked **per thread**; the object is owned by its
outermost invocation and is not thread-safe. A reference used after its scope ends
raises :class:`EscapedTransactionError`.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol
from weakref import WeakValueDictionary

from parallax.core.metamodel import Metamodel
from parallax.core.unit_work.clock import Clock, TransactionInstant
from parallax.core.unit_work.instructions import WriteInstruction
from parallax.core.unit_work.materialized import MaterializedWriteGroup, ObservedKeyedWrite
from parallax.core.unit_work.plan import WritePlan
from parallax.core.unit_work.planner import BufferItem, ObservedStateKey
from parallax.core.unit_work.retain import ParticipationToken, RetainedObservation
from parallax.core.unit_work.strategy import Concurrency
from parallax.core.unit_work.write_planner import PlanningRequest, SubjectIdentity, WritePlanner

__all__ = [
    "Concurrency",
    "EscapedTransactionError",
    "FlushExecutor",
    "RollbackOnlyError",
    "TransactionSettings",
    "UnitOfWork",
    "UnitOfWorkError",
    "WriteBatchStarting",
    "WriteBatchTrigger",
    "active_unit_of_work",
    "run_unit_of_work",
]

type WriteBatchTrigger = Literal["read_dependency", "finalization"]
"""The CLOSED set of reasons a unit of work flushes its buffer.

``read_dependency`` is the batch :meth:`UnitOfWork.read` forces out so a
dependent read observes it; ``finalization`` is the boundary-owned final batch
:meth:`UnitOfWork.run_outermost` flushes. There is no size-based, periodic, or
caller-invoked third trigger, which is what lets an observer state which of the
two produced a batch instead of guessing from position.
"""


class FlushExecutor(Protocol):
    """The composition-layer sink a Write Plan is handed to for lowering and
    execution. It is neutral because m-unit-work takes no m-sql edge.

    ``trigger`` travels with the plan rather than being inferred by the sink: the
    unit of work is the only participant that knows why it flushed, and an
    observer downstream would otherwise have to reconstruct the reason from the
    order it saw batches arrive in.
    """

    def __call__(self, plan: WritePlan, /, *, trigger: WriteBatchTrigger) -> None: ...


class WriteBatchStarting(Protocol):
    """The composition-layer notification that a write batch is beginning.

    Called once per flush that has something to flush, BEFORE the buffered
    writes are planned and therefore before any statement exists. A flush that
    fails in planning reaches the notification and never reaches the executor,
    which is the whole distinction it exists to make available: an observer can
    tell a batch that failed before it ran anything from work that is not a batch
    at all. Optional, because the shell itself needs nothing from it.
    """

    def __call__(self, trigger: WriteBatchTrigger, /) -> None: ...


class UnitOfWorkError(RuntimeError):
    """A unit of work was driven into an illegal state."""


class EscapedTransactionError(UnitOfWorkError):
    """A unit-of-work reference was used after its owning scope ended."""


class RollbackOnlyError(UnitOfWorkError):
    """A doomed (rollback-only) transaction refused commit or re-entry.

    Raised when the outermost boundary would commit a transaction an inner failure
    marked rollback-only, and when a nested scope tries to join one — carrying the
    original failure as its cause (``__cause__``), so its retriability classification
    survives for the outermost retry loop.
    """


@dataclass(frozen=True, slots=True)
class TransactionSettings:
    """A unit of work's fixed Concurrency Preference.

    The default is `optimistic` (`m-unit-work` "Strategy selection"): a
    preference, not a uniform strategy — each Entity's own Optimistic Lock Facet
    decides whether it yields Optimistic or the mandatory Locking fallback
    (`m-opt-lock`).
    """

    concurrency: Concurrency = "optimistic"


class UnitOfWork:
    """The buffering, observing, flushing transaction scope (m-unit-work).

    Construct via :func:`run_unit_of_work` (which owns the frame lifecycle); the
    body receives the unit of work and drives it with :meth:`buffer`, :meth:`retain`,
    and :meth:`read`.
    """

    __slots__ = (
        "_buffer",
        "_claims",
        "_closed",
        "_frame_depth",
        "_observations",
        "_participation",
        "_planner",
        "_rollback_cause",
        "_rollback_only",
        "_subject_identity",
        "_transaction_instant",
        "clock",
        "companion",
        "flush_executor",
        "meta",
        "settings",
        "write_batch_starting",
    )

    def __init__(
        self,
        *,
        settings: TransactionSettings,
        clock: Clock,
        meta: Metamodel,
        flush_executor: FlushExecutor,
        planner: WritePlanner,
        subject_identity: SubjectIdentity,
        write_batch_starting: WriteBatchStarting | None = None,
    ) -> None:
        self.settings = settings
        self.clock = clock
        self.meta = meta
        self.flush_executor = flush_executor
        self.write_batch_starting = write_batch_starting
        # The injected Write Planner (`m-unit-work`'s single finalization
        # authority) — constructed once per accepted Metamodel by the
        # composition layer (`parallax.snapshot.handle.build_write_planner`),
        # which alone may wire the optional policy modules the planner reaches
        # only through its strategy ports. Production and the conformance
        # engine both drive writes through this SAME shell.
        self._planner = planner
        # The boundary-captured Subject Identity every flush this attempt
        # plans with (`m-principal`'s eventual capture point; a transitional
        # constant until then). Reused unchanged by a forced flush; a retry
        # attempt receives its own new `UnitOfWork` and therefore its own copy.
        self._subject_identity = subject_identity
        # An opaque demarcation-layer companion (the `db.transact` transaction
        # facade), published for the scope's duration so a joining call recovers
        # it via `active_unit_of_work()`. The shell never reads it, and it needs
        # no cleanup of its own: it is reachable only through the per-thread
        # active binding, which `run_outermost` already clears on every exit.
        self.companion: object | None = None
        self._buffer: list[BufferItem] = []
        # The ledger is an INDEX, not an owner: a retained observation lives as
        # long as some source value or buffered write reaches it, and this entry
        # disappears with the last of them (`m-unit-work` "Observation lifetime").
        # What the index is for is recognizing a state this transaction has
        # already seen, so a reread of one state answers the evidence the earlier
        # read's values already carry rather than a second copy of it.
        self._observations: WeakValueDictionary[ObservedStateKey, RetainedObservation] = (
            WeakValueDictionary()
        )
        # The claims the buffered writes carry, in buffer order — the strong
        # reference that keeps a write's evidence alive after its source value is
        # released, and what a successful flush spends.
        self._claims: list[RetainedObservation] = []
        # This scope's participation identity: what a read of THIS unit of work
        # stamps on the values it produces, and what an effective-Locking write
        # tests its source against.
        self._participation = ParticipationToken()
        self._frame_depth = 0
        self._rollback_only = False
        self._rollback_cause: BaseException | None = None
        # One attempt, one lazy instant: constructing it reads no clock, and
        # every flush this scope plans carries the SAME holder, so all
        # timestamp-requiring work in the attempt shares one captured value
        # while work that needs none never captures at all.
        self._transaction_instant = TransactionInstant(clock)
        self._closed = False

    # --- caller surface --------------------------------------------------- #
    @property
    def participation(self) -> ParticipationToken:
        """This scope's participation identity — what its own reads stamp on the
        values they produce, and what an effective-Locking keyed write proves its
        source against."""
        self._ensure_open()
        return self._participation

    def buffer(
        self,
        instruction: WriteInstruction | ObservedKeyedWrite | MaterializedWriteGroup,
        *,
        claim: RetainedObservation | None = None,
    ) -> None:
        """Buffer a write instruction — bare, travelling with the observation its
        verb resolved for it
        (:class:`~parallax.core.unit_work.materialized.ObservedKeyedWrite`), or as
        a materializing predicate write's
        :class:`~parallax.core.unit_work.materialized.MaterializedWriteGroup` —
        for flush at the unit-of-work boundary.

        ``claim`` is the retained observation this write settles against, held
        here for as long as the write is buffered. That is what keeps a write's
        evidence alive once the caller releases the source value it came from,
        and what a successful flush spends.
        """
        self._ensure_open()
        self._buffer.append(instruction)
        if claim is not None:
            self._claims.append(claim)

    def retain(self, observation: RetainedObservation) -> RetainedObservation:
        """Index ``observation`` under the state it observed, answering the
        evidence this unit of work already holds for that state where it holds
        any.

        A reread that resolves to a state some live value already observed
        answers THAT value's evidence, so one observed state has one claim
        within a transaction however many reads reach it — the same rule
        graph aliases already follow. A state whose evidence a flush has spent
        is not reused: the row has moved on, so a fresh read is fresh evidence.
        """
        self._ensure_open()
        held = self._observations.get(observation.key)
        if held is not None and not held.consumed:
            return held
        self._observations[observation.key] = observation
        return observation

    def retained_for(self, key: ObservedStateKey) -> RetainedObservation | None:
        """The evidence this unit of work holds for one exact observed state, if
        any is still reachable — the read side of :meth:`retain`.

        Absence covers both a state no read of this scope observed and one whose
        every source value and buffered write has been released: liveness is
        strong reachability, so an index entry never outlives the evidence it
        names.
        """
        self._ensure_open()
        return self._observations.get(key)

    def read[T](self, read_fn: Callable[[], T]) -> T:
        """Serve a call-time read, force-flushing pending writes first.

        Read-your-own-writes: buffered writes are flushed inside the still-open
        atomic scope before the dependent read runs, so the read never observes
        stale in-transaction state. An abort still erases the force-flushed write
        (the DB rollback the enclosing transaction performs, upstream).
        """
        self._ensure_open()
        if self._buffer:
            self.flush(trigger="read_dependency")
        return read_fn()

    def flush(self, *, trigger: WriteBatchTrigger) -> None:
        """Plan and execute the buffered writes (the injected executor lowers them).

        ``trigger`` names which of the two flush reasons this call is, and every
        caller already knows its own: :meth:`read` serves a read dependency and
        :meth:`run_outermost` finalizes the boundary. It reaches the injected
        :class:`WriteBatchStarting` notification first and the executor second,
        so the batch is announced before planning can fail it.

        Evidence is spent AFTER the executor returns, and only by a flush that
        emitted DML: a plan finalization eliminated entirely leaves the buffered
        intent's evidence eligible, because no write of it survived to the
        database. A flush that fails aborts the transaction, so evidence needs no
        restoring.
        """
        self._ensure_open()
        if not self._buffer:
            return
        if self.write_batch_starting is not None:
            self.write_batch_starting(trigger)
        request = PlanningRequest(
            subject_identity=self._subject_identity,
            transaction_instant=self._transaction_instant,
            concurrency=self.settings.concurrency,
            buffered_writes=tuple(self._buffer),
        )
        plan = self._planner.plan(request)
        claims = tuple(self._claims)
        self._buffer.clear()
        self._claims.clear()
        self.flush_executor(plan, trigger=trigger)
        if plan.steps:
            for claim in claims:
                claim.consume()

    def mark_rollback_only(self, cause: BaseException) -> None:
        """Doom the transaction: commit will be refused. The first cause is kept."""
        self._rollback_only = True
        if self._rollback_cause is None:
            self._rollback_cause = cause

    @property
    def is_rollback_only(self) -> bool:
        """Whether the transaction is marked rollback-only (commit will be refused)."""
        return self._rollback_only

    @property
    def is_joined(self) -> bool:
        """Whether the unit of work is inside a joined (nested) frame."""
        return self._frame_depth > 0

    # --- internals -------------------------------------------------------- #
    def _ensure_open(self) -> None:
        if self._closed:
            raise EscapedTransactionError(
                "the unit of work has ended; a reference escaped its scope"
            )

    def _discard(self) -> None:
        # Abort: drop buffered + force-flushed in-memory state. The DB rollback the
        # enclosing transaction performs (upstream) erases any force-flushed rows.
        # Buffered claims are released rather than spent: nothing this scope wrote
        # survives, so evidence a later scope is handed is still about stored state.
        self._buffer.clear()
        self._claims.clear()
        self._observations.clear()

    def run_outermost[T](self, body: Callable[[UnitOfWork], T]) -> T:
        """Run ``body`` as the outermost frame: commit (flush) on success, else abort.

        Driven by :func:`run_unit_of_work`; not part of the developer surface.
        """
        _bind_active(self)
        try:
            result = body(self)
            if self._rollback_only:
                # An inner failure doomed the scope; commit is refused even though
                # the outer body returned normally, and the value is withheld.
                raise RollbackOnlyError(
                    "transaction is rollback-only; commit refused"
                ) from self._rollback_cause
            self.flush(trigger="finalization")
            return result
        except BaseException:
            # Abort: discard buffered effects and withhold the callback value.
            self._discard()
            raise
        finally:
            self._closed = True
            _clear_active()

    def run_joined[T](self, body: Callable[[UnitOfWork], T]) -> T:
        """Run ``body`` as a joined (nested) frame: return immediately, doom on failure.

        Driven by :func:`run_unit_of_work`; not part of the developer surface.
        """
        if self._rollback_only:
            # No new work may start inside a doomed scope.
            raise RollbackOnlyError(
                "cannot join a rollback-only transaction"
            ) from self._rollback_cause
        self._frame_depth += 1
        try:
            # The joined body returns immediately; commit/abort/retry belong to the
            # outermost boundary. An inner failure dooms the whole txn.
            return body(self)
        except BaseException as exc:
            self.mark_rollback_only(exc)
            raise
        finally:
            self._frame_depth -= 1


class _ActiveState(threading.local):
    """Per-thread holder for the active unit of work (the class default is the
    per-thread fallback until a thread binds its own instance attribute)."""

    uow: UnitOfWork | None = None


_active = _ActiveState()


def active_unit_of_work() -> UnitOfWork | None:
    """The unit of work active on the current thread, or ``None``."""
    return _active.uow


def _bind_active(uow: UnitOfWork) -> None:
    _active.uow = uow


def _clear_active() -> None:
    _active.uow = None


def run_unit_of_work[T](
    body: Callable[[UnitOfWork], T],
    *,
    settings: TransactionSettings,
    clock: Clock,
    meta: Metamodel,
    flush_executor: FlushExecutor,
    planner: WritePlanner,
    subject_identity: SubjectIdentity,
    write_batch_starting: WriteBatchStarting | None = None,
) -> T:
    """Run ``body`` in a unit of work — joining the active one or opening a new frame.

    A call while a transaction is active on the current thread **joins** it: the
    body receives the same unit of work and its return value is returned
    immediately (commit and abort belong to the outermost frame), and the passed
    ``settings`` / ``clock`` / ``meta`` / ``flush_executor`` /
    ``write_batch_starting`` / ``planner`` / ``subject_identity`` are ignored in
    favor of the active transaction's (``db.transact`` performs the
    option-conflict check before calling).
    Otherwise a new outermost frame is opened, and its value is returned only
    after a durable flush; an abort withholds it. ``planner`` is the injected
    Write Planner a new outermost frame's flushes call, and ``subject_identity``
    the boundary-captured Subject Identity every one of its Planning Requests
    carries.
    """
    active = active_unit_of_work()
    if active is not None:
        return active.run_joined(body)
    uow = UnitOfWork(
        settings=settings,
        clock=clock,
        meta=meta,
        flush_executor=flush_executor,
        planner=planner,
        subject_identity=subject_identity,
        write_batch_starting=write_batch_starting,
    )
    return uow.run_outermost(body)
