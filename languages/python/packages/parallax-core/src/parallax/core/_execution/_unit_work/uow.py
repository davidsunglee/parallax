from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass, replace
from types import TracebackType
from typing import Literal, Protocol, cast

from parallax.core import inheritance, temporal_read
from parallax.core._execution._unit_work._errors import (
    WRITE_EVIDENCE_CODES,
    UnitOfWorkError,
    WriteEvidenceError,
    WriteEvidenceErrorCode,
)
from parallax.core._execution._unit_work.acquisition import (
    AcquireRows,
    TargetReadRequest,
    consume_target,
)
from parallax.core._execution._unit_work.admission import BufferOutcome, WriteAdmission
from parallax.core._execution._unit_work.clock import Clock, TransactionInstant
from parallax.core._execution._unit_work.effects import (
    CardinalityCorruptionError,
    WritePreconditionError,
)
from parallax.core._execution._unit_work.instructions import (
    AMEND_MUTATIONS,
    ASSIGNMENT_MUTATIONS,
    ExpectedTxStart,
    PreparedPredicateInstruction,
    PreparedTargetInstruction,
)
from parallax.core._execution._unit_work.lifetime import AttemptLifetime
from parallax.core._execution._unit_work.ranges import RangeBindings
from parallax.core._execution._unit_work.retain import (
    InsertionIdentity,
    KeyedWriteRefusalAdvice,
    RetainedTargetState,
)
from parallax.core._execution._unit_work.source_authority import SourceAuthority
from parallax.core._execution._unit_work.strategy import (
    ActorIdentity,
    AuditDecoration,
    Concurrency,
    EvidencePolicyLookup,
)
from parallax.core._execution._unit_work.write_items import (
    InsertionAuthorizedWrite,
    KeyedInsert,
    ReadAuthorizedWrite,
    TargetWrite,
    target_write,
)
from parallax.core._execution._unit_work.write_planner import WritePlanner, WritePlanningRequest
from parallax.core._execution._unit_work.write_runner import (
    ExecuteCountedStep,
    ExecuteWriteSteps,
    _CurrentRowCapture,  # pyright: ignore[reportPrivateUsage] - the flush's own capture support
)
from parallax.core.base import normalize_instant
from parallax.core.inheritance import InheritanceEntityView
from parallax.core.metamodel import EntityMetadata, Metamodel
from parallax.core.temporal_read import (
    Bitemporal,
    Edge,
    TransactionTimeOnly,
    milestone_edge,
)
from parallax.core.write_plan.keys import ObjectKey, TemporalObjectStateKey
from parallax.core.write_plan.observe import PredecessorRow
from parallax.core.write_plan.plan import (
    CurrentRowOutput,
    TemporalWriteOwnership,
    WriteEffects,
    WriteGroup,
    WritePlan,
)
from parallax.core.write_plan.steps import KeyTarget

__all__ = [
    "WRITE_EVIDENCE_CODES",
    "AttemptLifetime",
    "BufferOutcome",
    "Concurrency",
    "FlushTrigger",
    "OpenFlush",
    "RollbackOnlyError",
    "StoredTarget",
    "TransactionSettings",
    "UnitOfWork",
    "UnitOfWorkError",
    "WriteEvidenceError",
    "WriteEvidenceErrorCode",
]

type FlushTrigger = Literal["read_dependency", "predicate_write", "pre_commit"]
"""The CLOSED set of reasons a unit of work flushes.

``read_dependency`` is the flush :meth:`UnitOfWork.read` forces out so a
dependent read observes it; ``predicate_write`` is the flush a
predicate-selected write executes in, after everything buffered before it
(:meth:`UnitOfWork.execute_predicate`); ``pre_commit`` is the boundary-owned
final flush the transaction attempt runs once its callback has returned. There
is no size-based, periodic, or caller-invoked further trigger, which is what
lets an observer state which of the three produced a flush instead of guessing
from position.

``pre_commit`` is named for WHEN it runs rather than for what it does,
because "finalization" already names the planner stage every flush of any
trigger goes through.
"""


class FlushScope(Protocol):
    """The composition-layer scope one flush runs inside.

    Left however the flush leaves — a planning refusal, a failed statement, a
    shortfall the enforcer raised, or success — so a composition layer that
    observes the transaction can never be told a flush began and not told how it
    ended.
    """

    def __enter__(self) -> object: ...

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: TracebackType | None,
        /,
    ) -> None: ...


class OpenFlush(Protocol):
    """The composition-layer opener a flush announces itself to.

    Called once per flush that has something to flush — buffered writes, or a
    predicate-selected write's own statement — BEFORE the buffered writes are
    planned and therefore before any statement exists, and the scope it
    answers spans planning as well as execution. A flush that fails in
    planning is therefore inside the scope and never executes a step, which
    is the whole distinction this exists to make available: an observer can tell
    a flush that failed before it ran anything from work that is not a flush at
    all. Optional, because the shell itself needs nothing from it.
    """

    def __call__(self, trigger: FlushTrigger, /) -> FlushScope: ...


@dataclass(frozen=True, slots=True)
class StoredTarget:
    """What a target acquisition found of the stored state a target
    write starts from: its version, where its family has one, or its current
    Transaction-Time start, where its family is temporal."""

    version: int | None = None
    tx_start: object | None = None


class EscapedTransactionError(UnitOfWorkError):
    """A transaction reference was used after its attempt ended."""


class RollbackOnlyError(UnitOfWorkError):
    """A doomed (rollback-only) transaction refused work, a join, or commit.

    Raised when further work, a joining invocation, or the outermost attempt's
    commit reaches a transaction a failure doomed, carrying the original failure
    as its cause (``__cause__``), so its retriability classification survives
    for the outermost retry loop.
    """


@dataclass(frozen=True, slots=True)
class TransactionSettings:
    """A unit of work's fixed Concurrency Preference, and what its database's
    write counts report.

    The default is `optimistic` (`m-unit-work` "Strategy selection"): a
    preference, not a uniform strategy — each Entity's own Optimistic Lock Facet
    decides whether it yields Optimistic or the mandatory Locking fallback
    (`m-opt-lock`). ``counts_unchanged_rows`` is the connection's dialect fact
    every flush plans with
    (:class:`~parallax.core._execution._unit_work.write_planner.WritePlanningRequest`).
    """

    concurrency: Concurrency = "optimistic"
    counts_unchanged_rows: bool = False


class UnitOfWork:
    """The buffering, observing, flushing coordinator of one writable
    transaction attempt's work (m-unit-work).

    It is not the transaction: the attempt owns the native transaction and its
    lifetime, and hands this the lifetime to consult and doom rather than a
    state of its own. The attempt drives it with :meth:`buffer`,
    :meth:`buffer_insert`, :meth:`buffer_target`, :meth:`execute_predicate`,
    and :meth:`read`, asking its :attr:`source_authority` what a keyed write's
    source licenses here, flushes it once more before commit, and has it
    :meth:`discard` its state when the attempt does not commit. Its reads
    file their evidence into that same authority.

    Every row a write reads — a target's starting state, a
    deferred range's coverage — is read through ``acquire_rows`` and consumed
    into evidence while the read's resources are live.
    """

    __slots__ = (
        "_actor_identity",
        "_admission",
        "_evidence_policy_for",
        "_lifetime",
        "_planner",
        "_transaction_instant",
        "acquire_rows",
        "clock",
        "execute_counted_step",
        "execute_write_steps",
        "flush_opening",
        "meta",
        "settings",
        "source_authority",
    )

    def __init__(
        self,
        *,
        settings: TransactionSettings,
        lifetime: AttemptLifetime,
        clock: Clock,
        meta: Metamodel,
        execute_write_steps: ExecuteWriteSteps,
        execute_counted_step: ExecuteCountedStep,
        acquire_rows: AcquireRows,
        planner: WritePlanner,
        actor_identity: ActorIdentity,
        evidence_policy_for: EvidencePolicyLookup,
        flush_opening: OpenFlush | None = None,
    ) -> None:
        self.settings = settings
        self._lifetime = lifetime
        self.clock = clock
        self.meta = meta
        self.execute_write_steps = execute_write_steps
        self.execute_counted_step = execute_counted_step
        self.acquire_rows = acquire_rows
        self.flush_opening = flush_opening
        # The injected Write Planner (`m-unit-work`'s single finalization
        # authority) — constructed once per accepted Metamodel by the
        # execution's model preparation (`parallax.core.execution.prepare_model`),
        # which alone may wire the optional policy modules the planner reaches
        # only through its strategy ports. Production and the conformance
        # engine both drive writes through this SAME shell.
        self._planner = planner
        # The Actor Identity execution orchestration supplies for every flush
        # this attempt plans. A forced flush reuses it unchanged; a retry attempt
        # receives its own new `UnitOfWork` and therefore its own copy.
        self._actor_identity = actor_identity
        # The connected model's write-evidence policy, bound once per accepted
        # model by model preparation, which alone may reach `m-opt-lock`.
        self._evidence_policy_for = evidence_policy_for
        # The attempt's one authority over what its sources and insertions
        # still authorize, which its reads, keyed ingress, buffering, and
        # completion all consult. It holds nothing of this shell.
        self.source_authority = SourceAuthority(
            meta,
            lifetime=lifetime,
            concurrency=settings.concurrency,
            evidence_policy_for=evidence_policy_for,
            version_after=planner.inserted_version,
        )
        # The accepted writes, composed as each is admitted, each carrying the
        # claims its verbs resolved for it and the evidence of the sources it
        # was admitted through — the strong reference that keeps that evidence
        # alive after its source value is released.
        self._admission = WriteAdmission(meta, authority=self.source_authority)
        # One attempt, one lazy instant: constructing it reads no clock, and
        # every flush this scope plans carries the SAME holder, so all
        # timestamp-requiring work in the attempt shares one captured value
        # while work that needs none never captures at all.
        self._transaction_instant = TransactionInstant(clock)

    def buffer(
        self, item: ReadAuthorizedWrite | InsertionAuthorizedWrite | TargetWrite
    ) -> BufferOutcome:
        """Admit ``item``, a write of existing state, under the authority it
        carries and buffer it for flush at the unit-of-work boundary — all of
        it, or nothing
        (:meth:`~parallax.core._execution._unit_work.admission.WriteAdmission.admit`).

        The claim is read off the admitted write itself
        (:func:`~parallax.core._execution._unit_work.write_items.admitted_write`): a
        retained observation claims the state it observed, and an
        object-locked write claims the object it writes (`m-unit-work`
        "Observed-State Coalescing"). An arriving
        keyed intent the held claim cannot absorb raises
        :class:`WriteEvidenceError` (``write-evidence-already-claimed``), and
        the pending writes, their claims, and the pending inserts are left as
        they were.

        An admitted write built from a read's evidence brings it along, so the buffer
        is what keeps a write's evidence alive once the caller releases the
        source value it came from.

        A target write
        (:class:`~parallax.core._execution._unit_work.write_items.TargetWrite`)
        is admitted as :meth:`buffer_target` describes, its caller's revision
        confirmed under this attempt's concurrency strategy. A write an
        insertion authorized
        (:class:`~parallax.core._execution._unit_work.write_items.InsertionAuthorizedWrite`) is
        admitted only while that authority stands, and a write leaving nothing
        of what a still-unflushed insertion opened ends it.

        The outcome reports the pending-insert transition buffering made: a
        destructive write that leaves nothing of an object's still-unflushed
        insert, and reaches no stored coverage past it, cancels that pair —
        recognized when the pair is complete rather than when it is planned.
        """
        self._ensure_open()
        return self._admission.admit(item, confirm_target=self._confirm_target)

    def buffer_insert(
        self, insert: KeyedInsert, *, insertion_advice: KeyedWriteRefusalAdvice | None
    ) -> InsertionIdentity | None:
        """Admit ``insert`` and buffer it — all of it, or nothing — answering
        the identity of the insertion it opens, which a source the insertion
        was stated through carries from then on
        (:meth:`~parallax.core._execution._unit_work.admission.WriteAdmission.admit_insert`).

        An insert of an object whose admitted insertion still stands is refused
        (:class:`~parallax.core._execution._unit_work._errors.KeyedWriteValueError`,
        ``write-value-already-stored``) with the advice that insertion's opener
        supplied, and ``insertion_advice`` is kept for a repeat of this one.
        Where an earlier insertion of the object is stored and a pending write
        removes all of it, the insert executes after that removal. An insert
        whose key the database allocates opens no insertion and answers
        ``None``.
        """
        self._ensure_open()
        return self._admission.admit_insert(insert, insertion_advice=insertion_advice)

    def execute_predicate(self, prepared: PreparedPredicateInstruction) -> int:
        """Execute a prepared predicate-selected write now, as one readless
        statement (`m-batch-write` "Predicate-selected readless forms"), and
        answer the affected-row count its driver reported: preparation has
        refused every target that needs an observation.

        An amendment that assigns no member is the empty write, and so is a
        replacement of an Entity whose only writable member is its key: having
        been validated, it answers ``0`` here, opening no Flush and leaving the
        buffered writes pending. Any other runs in one ``predicate_write``
        Flush: everything buffered before it executes and completes first,
        exactly as a dependent read's flush runs it, and the predicate's one
        statement after. It never enters the buffer, claims nothing, and
        publishes nothing about the rows it reached.

        A refusal planning the buffered writes leaves them pending and the
        transaction usable, and a failure executing them dooms it before the
        predicate is planned. A refusal planning the predicate's own statement
        fails the Flush without dooming the transaction or restoring the
        buffered writes it already executed; a failure lowering, executing, or
        enforcing that statement dooms it."""
        self._ensure_open()
        if prepared.mutation in ASSIGNMENT_MUTATIONS and not prepared.assigns:
            return 0
        opening = self.flush_opening
        if opening is None:
            return self._execute_predicate(prepared)
        with opening("predicate_write"):
            return self._execute_predicate(prepared)

    def _execute_predicate(self, prepared: PreparedPredicateInstruction) -> int:
        if self._admission:
            self._flush_buffer("predicate_write")
        step = self._planner.predicate_step(
            prepared,
            actor_identity=self._actor_identity,
            transaction_instant=self._transaction_instant,
        )
        try:
            return self.execute_counted_step(step)
        except BaseException as failure:
            self._lifetime.doom(failure)
            raise

    def buffer_target(self, prepared: PreparedTargetInstruction) -> None:
        """Admit a target write and buffer it — all of it, or nothing.

        An amendment that assigns no member is the empty write: it is dropped
        here, having been validated, before any condition, participation, or
        other pending work is consulted. A deletion or termination assigns
        nothing either and is never empty: it reaches the condition like every
        other target write. Every other target write is refused, with nothing
        buffered and the pending writes as they were, where:

        * this attempt admitted an insertion of the object, before or after a
          flush (``write-evidence-inserted``) — such an object is written
          through its insertion's source or a fresh read until commit;
        * it cannot join the object's pending writes
          (``write-evidence-already-claimed``) — another write of the object
          stands at another stated revision or observed state, a temporal one
          overlaps its window without stating exactly that window, an observed
          rectangle holding its start stands at another revision, or the write
          it meets is a destruction it would undo; or
        * under the Locking strategy, the stored state does not match the
          caller's stated revision (:class:`WritePreconditionError`).

        Under Locking, the participation the write needs is taken from a write
        of the same state already pending — over exactly its window, for a
        temporal object — else from a live read of exactly that state this
        attempt holds, else by reading the stored row under the shared lock
        through ``acquire_rows``, executing nothing pending. That read's root
        count decides first: more than one stored row is Cardinality
        Corruption, whatever those rows hold, and none means no row stands.
        A temporal object's row is read whole and kept with the write, for its
        range to reuse while it is still current (:class:`RetainedTargetState`).
        The Optimistic strategy reads nothing: the caller's revision becomes
        the write's gate.
        A temporal target names its state by its stated Transaction-Time start
        and, on a Bitemporal object, by the coverage at its ``valid_from``.
        """
        self._ensure_open()
        if prepared.mutation in AMEND_MUTATIONS and not prepared.assigns:
            return
        item = target_write(prepared, inheritance.view(self.meta))
        self._admission.admit(item, confirm_target=self._confirm_target)

    def _confirm_target(self, item: TargetWrite) -> TargetWrite:
        """``item`` once its caller's revision is confirmed under its target's
        Effective Concurrency Strategy, answered with the row it read where it
        read one, or refused.

        Admission has already found no pending write proving that revision.
        Under Locking a live read of exactly that state this attempt holds
        proves it, else the stored row is read under the shared lock; the
        Optimistic strategy reads nothing.
        """
        target = item.instruction.target
        policy = self._evidence_policy_for(target.identity)
        if policy.effective_strategy(self.settings.concurrency) != "locking":
            return item
        expectation = item.expectation
        scope = item.claim_scope
        key = item.object_key
        if isinstance(expectation, ExpectedTxStart):
            return self._confirm_temporal_target(item, key, expectation)
        if isinstance(scope, ObjectKey) or not self.source_authority.has_live_observation(scope):
            stored, _row, _document = self._stored_target(target, key, None)
            if stored is None or stored.version != expectation.version:
                raise WritePreconditionError(
                    target.identity, dict(key.primary_key), expectation.version
                )
        return item

    def _confirm_temporal_target(
        self, item: TargetWrite, key: ObjectKey, expectation: ExpectedTxStart
    ) -> TargetWrite:
        """Prove a Locking target write of a temporal object starts
        from the state its caller stated, or refuse it, answering the write
        with the row it read where it read one.

        A live read of the state this attempt holds proves it, else it is
        read, whole, and kept with the write as the state the read found at
        this point of the attempt's changes.
        """
        window = item.instruction.valid_time_window
        valid_from = None if window is None else window.start
        authority = self.source_authority
        if authority.has_live_observation(
            TemporalObjectStateKey(key, Edge(tx_time=expectation.instant, valid_time=valid_from))
        ):
            return item
        target = item.instruction.target
        read_at = authority.freshness
        stored, row, document = self._stored_target(target, key, valid_from, retains=True)
        if stored is None or stored.tx_start != expectation.instant:
            raise WritePreconditionError(
                target.identity, dict(key.primary_key), expectation.instant
            )
        assert row is not None  # a stored revision was read off this row
        selection = self._family(target).member_selection
        shape = temporal_read.view(self.meta).shape(target.identity)
        assert isinstance(shape, TransactionTimeOnly | Bitemporal)  # a temporal target
        state = TemporalObjectStateKey(
            key, milestone_edge(shape, PredecessorRow.over_row(selection, row, None, None), None)
        )
        return replace(item, retained=RetainedTargetState(state, read_at, row, document))

    def _stored_target(
        self,
        target: EntityMetadata,
        key: ObjectKey,
        valid_from: dt.datetime | None,
        *,
        retains: bool = False,
    ) -> tuple[StoredTarget | None, tuple[object, ...] | None, object | None]:
        """The stored revision of the row ``key`` names, read under the shared
        lock, or ``None`` where no row stands — judged once the read is over,
        from its root count first and the unique row's revision cell after —
        beside that row and its raw document, read whole where it ``retains``
        them."""
        count, row, document = self.acquire_rows(
            TargetReadRequest(target, key, valid_from, retains=retains), consume_target
        )
        view = self._family(target)
        if count > 1:
            ((_name, value),) = key.primary_key
            raise CardinalityCorruptionError(
                target.identity,
                KeyTarget(key_attributes=(view.primary_key.identity,), key_values=((value,),)),
                1,
                count,
            )
        if row is None:
            return None, None, None
        selection = view.member_selection
        shape = temporal_read.view(self.meta).shape(target.identity)
        if isinstance(shape, TransactionTimeOnly | Bitemporal):
            start = row[selection.position(shape.transaction_time.start_attribute)]
            stored = StoredTarget(tx_start=normalize_instant(cast("dt.datetime", start)))
            return stored, row, document
        version = self._planner.version_attribute(target.identity)
        assert version is not None  # preparation refuses a target with no revision
        return StoredTarget(cast("int", row[selection.position(version)])), row, document

    def _family(self, entity: EntityMetadata) -> InheritanceEntityView:
        view = inheritance.view(self.meta).entity(entity.identity)
        if view is None:  # pragma: no cover - the facet covers every accepted Entity
            raise ValueError(f"{entity.identity.canonical}: the model declares no such entity")
        return view

    def read[T](self, read_fn: Callable[[], T]) -> T:
        """Serve a call-time read, force-flushing pending writes first.

        Read-your-own-writes: buffered writes are flushed inside the still-open
        atomic scope before the dependent read runs, so the read never observes
        stale in-transaction state. An abort still erases the force-flushed write
        (the DB rollback the enclosing transaction performs, upstream).
        """
        self._ensure_open()
        if self._admission:
            self.flush(trigger="read_dependency")
        return read_fn()

    def flush(self, *, trigger: FlushTrigger) -> None:
        """Plan the buffered writes and run the plan Write Group by Write
        Group, each group's steps executed and enforced through the injected
        :class:`~parallax.core._execution._unit_work.write_runner.ExecuteWriteSteps`.

        ``trigger`` names which flush reason this call is, and every caller
        already knows its own: :meth:`read` serves a read dependency and the
        attempt runs the boundary's pre-commit flush. The whole
        flush runs inside the injected :class:`OpenFlush`'s scope, so a
        planning refusal is inside the Flush rather than beside it and a Flush
        planning reduces to no DML at all still ends the way it began.

        Each settled write of the plan completes as soon as its group's steps
        succeed, before any step of a later group executes: it records the
        states it changed, continues or ends the authority of the sources whose
        state it advanced, transformed, or removed, retires the owned rows it
        removed, and registers the rows it opened. A deferred settled write
        binds at its turn against what every earlier group published, and
        executes in one group with the ready deferred writes bound beside it.
        What a
        flush's writes leave for its sources outlives the flush, and the
        current rows a later submission may continue from are captured as they
        execute. The pre-commit flush, which no submission follows and none of
        whose writes continues from another, captures none and records nothing
        its writes leave for a source.

        A failure while executing, binding, or completing dooms the attempt's
        lifetime before it propagates, so a caller that catches it can do no
        further work and cannot commit. A planning refusal precedes
        execution and leaves the transaction usable.

        The claims the pending writes took travel out with them: what a later
        write may claim is decided by what is still pending, and after a flush
        nothing is.
        """
        self._ensure_open()
        if not self._admission:
            return
        opening = self.flush_opening
        if opening is None:
            self._flush_buffer(trigger)
            return
        with opening(trigger):
            self._flush_buffer(trigger)

    def _flush_buffer(self, trigger: FlushTrigger) -> None:
        admission = self._admission
        # The planning request is the flush's last reference to the writes it
        # planned, so it ends with the call: once planning succeeds and the
        # buffer drains, what a plan's deferred settled write took over is
        # released as it executes rather than held until the flush ends.
        concluding = trigger == "pre_commit"
        ownership = self.source_authority.planning_ownership(concluding=concluding)
        plan = self._planner.finalize(
            WritePlanningRequest(
                actor_identity=self._actor_identity,
                transaction_instant=self._transaction_instant,
                concurrency=self.settings.concurrency,
                composed_writes=admission.composed_writes(),
                ownership=ownership,
                counts_unchanged_rows=self.settings.counts_unchanged_rows,
            )
        )
        admission.drain_planned()
        try:
            self._run_write_plan(plan, ownership=ownership, captures=not concluding)
        except BaseException as failure:
            self._lifetime.doom(failure)
            raise

    def _run_write_plan(
        self, plan: WritePlan, *, ownership: TemporalWriteOwnership, captures: bool
    ) -> None:
        """Execute ``plan``'s entries in order, completing each write of a
        Write Group, in order, as soon as the group's steps succeeded and before
        any step of a later group executes.

        A deferred settled write binds at its turn under ``ownership``, as
        every earlier group's completion left it, and executes in the group of
        the ready writes bound with it: the leading writes of its acquisition
        span whose coverage is read, or itself alone outside any span. The
        coverage reads of a span can run before an earlier group of it
        completes. A write with no step still completes. A group that fails
        completes none of its writes, and nothing after it is read, bound, or
        executed.

        Where it ``captures``, the current rows a write describes are captured
        as their payloads are demanded and published with its completion.
        """
        audit: AuditDecoration | None = None
        entries = plan.entries
        spans = iter(plan.acquisition_spans)
        span = next(spans, None)
        position = 0
        while position < len(entries):
            entry = entries[position]
            if isinstance(entry, WriteGroup):
                position += 1
                self._execute_write_group(entry, captures=captures)
                continue
            stop = position + 1
            if span is not None and span.start == position:
                stop = span.stop
                span = next(spans, None)
            if audit is None:
                audit = self._audit_decoration()
            self._execute_deferred(
                plan, position, stop, ownership=ownership, audit=audit, captures=captures
            )
            position = stop

    def _audit_decoration(self) -> AuditDecoration:
        return self._planner.audit_decoration(
            actor_identity=self._actor_identity, transaction_instant=self._transaction_instant
        )

    def _execute_deferred(
        self,
        plan: WritePlan,
        start: int,
        stop: int,
        *,
        ownership: TemporalWriteOwnership,
        audit: AuditDecoration,
        captures: bool,
    ) -> None:
        """Bind ``plan``'s deferred settled writes ``[start, stop)`` group by
        ready group, executing and completing each group before the next binds
        or reads."""
        with RangeBindings(
            plan,
            start=start,
            stop=stop,
            acquire_rows=self.acquire_rows,
            current=self.source_authority.is_unchanged_since,
            ownership=ownership,
            audit=audit,
            payloads=self._planner.payloads,
        ) as bindings:
            while (group := next(bindings, None)) is not None:
                try:
                    self._execute_write_group(group, captures=captures)
                finally:
                    group = None

    def _execute_write_group(self, group: WriteGroup, *, captures: bool) -> None:
        """Execute ``group``'s steps once and complete each of its writes, in
        order, once they all succeeded and the keys the database allocated
        are as many as its writes open with keys it allocates, with the
        current rows its execution captured where it ``captures``.

        However it ends, what the group's capture staged is released, and
        nothing here keeps the group or a write's captured rows."""
        writes = group.writes
        steps = group.steps
        expected = sum(len(write.opened.allocated) for write in writes)
        capture = _CurrentRowCapture.for_writes(writes) if captures else None
        write: WriteEffects | None = None
        captured: tuple[tuple[CurrentRowOutput, object | None], ...] = ()
        try:
            if capture is None:
                allocated = self.execute_write_steps(steps, allocates=bool(expected))
            else:
                allocated = capture.execute(
                    self.execute_write_steps, steps, allocates=bool(expected)
                )
            if len(allocated) != expected:
                raise UnitOfWorkError(
                    f"a Write Group opening {expected} row(s) whose keys the database allocates "
                    f"executed answering {len(allocated)} key(s)"
                )
            first = 0
            for write in writes:
                stop = first + len(write.opened.allocated)
                if capture is not None:
                    captured = capture.take_rows(write.current_outputs)
                self.source_authority.complete_write(
                    write, allocated[first:stop], captured=captured
                )
                captured = ()
                first = stop
        finally:
            if capture is not None:
                capture.release()
            del group, writes, steps, write, captured

    def _ensure_open(self) -> None:
        self._lifetime.ensure_open()

    def discard(self) -> None:
        """Drop every buffered and in-memory effect of an attempt that will not
        commit.

        The rollback the attempt performs erases any force-flushed rows, and
        buffered claims are released with it: nothing this attempt
        wrote survives, so evidence a later attempt is handed is still about
        stored state.
        """
        self._admission.discard()
        self.source_authority.clear()
