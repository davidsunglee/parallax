"""``parallax.conformance.boundary_runner`` — the case-driven boundary runner.

A `boundary` case (`m-auto-retry` / `m-opt-lock`, `m-case-format` "Boundary
cases") proves a unit-of-work loop-mechanics branch a single-connection
harness cannot provoke: it carries no golden SQL, only a portable
`when.boundary` action list, an OPTIONAL `given.fault` and `given.sessionDefault`,
its retry configuration (`when.uow`), and the portable `then.outcome`. This module
hosts the machinery ONE parametrized runner drives against EVERY reachable
boundary case — never a per-case hand function (the hand-mirroring this runner
exists to end):

- :func:`boundary_uow` / :func:`boundary_steps` parse a case's own
  `when.uow` / `when.boundary` (schema camelCase -> the Python `db.transact`
  snake_case options), and :func:`outcome` resolves a `then.outcome` that
  differs by engine against the dialect actually running.
- :func:`run_boundary_actions` is the ONE deterministic action -> verb
  mapping every boundary case shares (every corpus witness targets
  `models/account.yaml`'s versioned `Account` row).
- :class:`FaultInjectingPort` is the fault-injecting `m-db-port` DECORATOR
  (wraps a REAL adapter): it SIMULATES the case's `given.fault` at the seam
  that fault belongs to — the write seam for one the WORK meets, and the
  boundary seam for a session setup that fails before any work; the real
  classification / retry-loop / optimistic-gate machinery does the classifying,
  never this module, and how many attempts ran is read off the delivered
  lifecycle events rather than counted here.
- :func:`expected_attempts` derives the authored attempt count from the
  SAME fields `m-auto-retry.md` / `m-opt-lock.md` fix the retriability rules
  from (never a per-case hand table).

Exercised by the real-database suite (`tests/api/test_boundary_run.py`, over
the shipped `parallax-postgres` adapter) and, DB-free, by unit
tests over a fake port (`tests/unit/test_boundary_runner.py`) — the same
split every other engine-adjacent module in this package already follows.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final, Literal, cast

from parallax.conformance import case_format, sweep
from parallax.conformance.story_models import Account
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import (
    BeginFailed,
    DbPort,
    DocumentReadOrdinals,
    IsolationLevel,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import Dialect
from parallax.core.unit_work import Concurrency
from parallax.snapshot.handle import Database, Transaction

__all__ = [
    "TARGET_ID",
    "BoundaryAbort",
    "BoundaryStep",
    "BoundaryUow",
    "FaultInjectingPort",
    "boundary_steps",
    "boundary_uow",
    "expected_attempts",
    "fault_kind",
    "outcome",
    "reachable_boundary_cases",
    "run_boundary_actions",
    "session_default",
    "translated_fault",
]

# The SAME versioned row every reachable m-opt-lock/m-read-lock case targets
# (account.yaml fixtures: id 2, Linus, balance 250.00, version 1) — every
# boundary case's model is `models/account.yaml`.
TARGET_ID: Final[int] = 2

# A no-op update's effective change set would elide to zero DML (m-opt-lock
# "No-op updates issue no DML") — every boundary `update` action therefore
# advances the balance by a fixed, non-zero amount so it always issues real DML.
_BUMP: Final[Decimal] = Decimal("1.00")


class BoundaryAbort(RuntimeError):
    """The scripted closure's OWN deliberate failure — `m-unit-work-004`'s
    "the closure itself throws after its actions" (no injected fault): the
    boundary runner raises this after running the case's own actions when
    the case declares no `given.fault` and its `then.outcome` is `aborted`.
    """


def reachable_boundary_cases(cases: list[case_format.Case] | None = None) -> list[case_format.Case]:
    """Every `boundary`-shape case this implementation can drive (parametrized
    at runtime, never a hand list — `m-case-format`: every boundary case is
    `lane: api-conformance`).

    Reachability is the same intersection every other lane uses
    (:func:`~parallax.conformance.sweep.reachable_cases`): the active slice's
    own selection, narrowed to cases whose every module tag is implemented. A
    boundary case tagged for an unbuilt module has no verb sequence to drive
    and no outcome to grade, so admitting it here would fail the runner rather
    than report the gap — which the API-suite coverage partition already does.
    """
    return [case for case in sweep.reachable_cases(cases=cases) if case.shape == "boundary"]


@dataclass(frozen=True, slots=True)
class BoundaryUow:
    """A boundary case's own `when.uow` (m-auto-retry / m-opt-lock retry
    configuration), as `db.transact` arguments.

    An option the case omits stays ``None`` — `db.transact`'s OWN sentinel
    (`python.md` §5) — so the case runs under whatever production resolves the
    omission to, rather than under a copy of that answer kept here that a
    changed default would silently strand.
    """

    concurrency: Concurrency | None
    retries: int | None
    retry_optimistic_conflicts: bool | None
    isolation: IsolationLevel | None


def boundary_uow(case: case_format.Case) -> BoundaryUow:
    when = cast("dict[str, Any]", case.document.get("when") or {})
    uow = cast("dict[str, Any]", when.get("uow") or {})
    return BoundaryUow(
        concurrency=cast("Concurrency | None", uow.get("concurrency")),
        retries=cast("int | None", uow.get("retries")),
        retry_optimistic_conflicts=cast("bool | None", uow.get("retryOptimisticConflicts")),
        isolation=case_format.uow_isolation(case),
    )


@dataclass(frozen=True, slots=True)
class BoundaryStep:
    """One `when.boundary` step: the portable action, and the Isolation Level a
    `join` names for the boundary it joins.

    ``isolation`` is ``None`` on every other action and on a `join` that names
    none, which is the omission that INHERITS the active level (`m-unit-work`).
    """

    action: str
    isolation: IsolationLevel | None


def boundary_steps(case: case_format.Case) -> list[BoundaryStep]:
    """The case's own `when.boundary` ordered step list (`m-case-format`)."""
    when = cast("dict[str, Any]", case.document.get("when") or {})
    steps = cast("list[dict[str, Any]]", when.get("boundary") or [])
    return [BoundaryStep(cast("str", step["action"]), _join_isolation(step)) for step in steps]


def _join_isolation(step: dict[str, Any]) -> IsolationLevel | None:
    declared = cast("str | None", step.get("isolation"))
    return None if declared is None else case_format.isolation_literal(declared)


def fault_kind(case: case_format.Case) -> str | None:
    """The case's OPTIONAL `given.fault` — absent for a pure loop-configuration
    case (`retries: 0`, `m-unit-work-004`'s own withheld-value proof)."""
    given = cast("dict[str, Any]", case.document.get("given") or {})
    fault = given.get("fault")
    return cast("str | None", fault) if isinstance(fault, str) else None


def session_default(case: case_format.Case) -> str | None:
    """The case's OPTIONAL `given.sessionDefault` — the Isolation Level the
    connection already defaults to when the adapter takes it."""
    given = cast("dict[str, Any]", case.document.get("given") or {})
    declared = given.get("sessionDefault")
    return cast("str | None", declared) if isinstance(declared, str) else None


def outcome(case: case_format.Case, dialect: Dialect) -> str | None:
    """The portable outcome ``dialect`` must produce, or ``None`` where the case
    does not apply to it.

    A dialect-keyed `then.outcome` states an outcome that differs by engine, and
    a dialect the map omits is one the case makes no claim about — the same rule
    `then.sql` and `then.nativeCode` already carry, so a nonportable engine floor
    is graded where it holds and skipped where it does not.
    """
    then = cast("dict[str, Any]", case.document.get("then") or {})
    declared = then["outcome"]
    if isinstance(declared, str):
        return declared
    return cast("str | None", cast("dict[str, Any]", declared).get(dialect.name))


def run_boundary_actions(
    tx: Transaction, steps: Sequence[BoundaryStep], *, database: Database | None = None
) -> Account | None:
    """The ONE deterministic `when.boundary` action -> verb mapping every
    boundary case shares (never a per-case hand function): every
    reachable case targets `models/account.yaml`'s versioned :data:`TARGET_ID`
    row.

    - ``read`` observes the target row (`tx.find`) — licenses a later keyed
      write's version advance/gate (`m-opt-lock`) and, read-your-own-writes,
      forces the flush of an ALREADY-buffered write (`m-unit-work-004`'s own
      "a dependent find observes the flushed write" step).
    - ``update`` bumps the last-read row's balance by :data:`_BUMP` (a real,
      non-no-op change, `m-opt-lock` "No-op updates issue no DML") and
      buffers it.
    - ``create`` inserts a synthetic new row (id 90, outside the fixture
      range 1-3) — no reachable corpus witness authors this action, but the
      mapping is total, not partial.
    - ``delete`` removes the last-read row.
    - ``join`` opens a joined unit of work through ``database``, at the level
      the step names, and runs every REMAINING action inside it, carrying the
      row already observed. A joined call shares the outer transaction
      (`m-unit-work`), so its closure receives the same :class:`Transaction` and
      its buffered writes reach the database in the OUTER boundary's own
      pre-commit batch — which is exactly what `m-execution-lifecycle-006`
      asserts. It needs the ``Database`` that opened the boundary, since only
      that object joins. A level the boundary was not opened with is refused
      there rather than here: the refusal under test is production's own.
    - ``terminate`` has no legal target on this NON-temporal model — a loud
      refusal (no reachable corpus witness authors it either).

    Returns the LAST tracked :class:`Account` (the closure's own return
    value — `then.outcome: committed`'s "callback value returned" half),
    ``None`` after a ``delete``.
    """
    return _run_actions(tx, list(steps), None, database)


def _run_actions(
    tx: Transaction,
    steps: list[BoundaryStep],
    current: Account | None,
    database: Database | None,
) -> Account | None:
    for index, step in enumerate(steps):
        action = step.action
        if action == "read":
            current = tx.find(Account.where(Account.id == TARGET_ID)).result()
        elif action == "update":
            if current is None:
                raise AssertionError("an `update` action needs a prior `read` observation")
            current = current.edit(balance=current.balance + _BUMP)
            tx.update(current)
        elif action == "create":
            current = Account(id=90, owner="Boundary", balance=Decimal("0.00"))
            tx.insert(current)
        elif action == "delete":
            if current is None:
                raise AssertionError("a `delete` action needs a prior `read` observation")
            tx.delete(current)
            current = None
        elif action == "join":
            if database is None:
                raise AssertionError(
                    "a `join` action needs the Database that opened the boundary — only that "
                    "object joins it (`python.md` §5)"
                )
            return database.transact(
                lambda joined, rest=steps[index + 1 :], seen=current: _run_actions(
                    joined, rest, seen, database
                ),
                isolation=step.isolation,
            )
        elif action == "terminate":
            raise AssertionError(
                "`terminate` has no legal target on the non-temporal account.yaml model "
                "(no reachable boundary case authors it)"
            )
        else:  # pragma: no cover - m-case-format's `when.boundary.action` enum is closed
            raise AssertionError(f"unrecognized boundary action {action!r}")
    return current


@dataclass(frozen=True, slots=True)
class _Fault:
    """One `given.fault` kind, in the three terms this module ever asks about it.

    ``seam`` is where the kind is simulated, and it settles the attempt count
    too: a ``work`` fault is a failure the work meets at the write seam, inside
    an attempt that ran, while a ``boundary`` fault stops the boundary from
    opening, so no attempt runs at all. ``retriable`` is `m-auto-retry` /
    `m-opt-lock`'s verdict on the kind, ``opt-in`` where
    `retryOptimisticConflicts` decides it. ``error`` builds the translated
    :class:`DatabaseError` the real adapter's own classification would produce,
    and is ``None`` for the one kind that raises nothing: an optimistic conflict
    is simulated as the gated update's zero-row shortfall.

    Every seam reads this record rather than testing the kind itself, so a kind
    added here is injected, classified, and counted from one declaration.
    """

    seam: Literal["work", "boundary"]
    retriable: Literal["always", "never", "opt-in"]
    error: Callable[[], DatabaseError] | None


_FAULTS: Final[Mapping[str, _Fault]] = {
    "serialization-failure": _Fault(
        seam="work",
        retriable="always",
        error=lambda: DatabaseError(
            category="deadlock", native_code="40001", message="serialization failure"
        ),
    ),
    "deadlock": _Fault(
        seam="work",
        retriable="always",
        error=lambda: DatabaseError(
            category="deadlock", native_code="40P01", message="deadlock detected"
        ),
    ),
    "lock-wait-timeout": _Fault(
        seam="work",
        retriable="never",
        error=lambda: DatabaseError(
            category="lockWaitTimeout", native_code="55P03", message="lock wait timeout"
        ),
    ),
    "optimistic-lock-conflict": _Fault(seam="work", retriable="opt-in", error=None),
    # Uncategorized on purpose: a refused session setup is a request the engine
    # would not honor, not a contention the classifier has a neutral category
    # for, so nothing above may read it as retriable.
    "isolation-setup-failure": _Fault(
        seam="boundary",
        retriable="never",
        error=lambda: DatabaseError(
            category=None, native_code="22023", message="invalid isolation level request"
        ),
    ),
}


def _fault(kind: str) -> _Fault:
    try:
        return _FAULTS[kind]
    except KeyError as unknown:  # pragma: no cover - `given.fault` is a closed enum
        raise ValueError(f"unrecognized fault kind {kind!r}") from unknown


def translated_fault(kind: str) -> DatabaseError:
    """The SAME translated :class:`DatabaseError` the real adapter's own
    classification would produce for a `given.fault` kind (`m-db-error`
    vocabulary) — the decorator SIMULATES the failure; the real retry loop
    still classifies it via `DatabaseError.category` / `.is_retriable`, never a
    value this module invents.

    :class:`ValueError` for a kind that raises no error at all, which the write
    seam answers with a zero-row shortfall instead.
    """
    build = _fault(kind).error
    if build is None:  # pragma: no cover - only the conflict kind, simulated as a shortfall
        raise ValueError(f"{kind!r} is simulated as a zero-row shortfall, not a raised error")
    return build()


@dataclass(slots=True)
class _FaultState:
    """Shared, mutable state one :class:`FaultInjectingPort` chain (the
    top-level instance plus every nested copy `.transaction()` wraps) tracks
    across a WHOLE `db.transact` retry loop — never reset per attempt.

    Whether the fault has already fired, and nothing else. How many attempts ran
    is the delivered lifecycle stream's to answer (`m-execution-lifecycle`), so
    this decorator counts none: a second count kept here could disagree with the
    one the retry loop actually produced."""

    fired: bool = False


class FaultInjectingPort:
    """A pass-through ``m-db-port`` DECORATOR over a REAL adapter, injecting
    ``fault`` at the seam that fault belongs to: the decorator SIMULATES the
    fault — the real classification / retry-loop / optimistic-gate machinery
    does the rest, end to end.

    Which seam a kind belongs to is the kind's own declaration (:data:`_FAULTS`)
    rather than a test made here: a ``work`` fault is a failure the work meets at
    the write seam, and a ``boundary`` fault is the boundary failing to open,
    answered as ``BeginFailed``.

    ``persistent`` fires the fault on EVERY attempt's write (a case whose
    `then.outcome` is a failure kind needs this — an outcome OTHER than
    `committed` means the fault must survive to exhaustion, or (a
    non-retriable / disabled-loop case) is a don't-care since only one
    attempt ever runs either way); a `committed` outcome needs the fault to
    fire ONCE only, so the retry succeeds. ``optimistic-lock-conflict``
    never raises from here — it returns ``0`` from the gated update's
    ``execute_write`` (the concurrent-writer simulation), letting the real
    Affected Rows Policy shortfall -> ``enforce_affected_rows`` ->
    ``OptimisticLockConflictError`` fire through the genuine write-seam
    code path.
    """

    def __init__(
        self,
        inner: DbPort,
        *,
        fault: str | None,
        persistent: bool,
        state: _FaultState | None = None,
    ) -> None:
        self._inner = inner
        self._fault = fault
        self._persistent = persistent
        self._state = state if state is not None else _FaultState()

    @property
    def dialect(self) -> Dialect:
        return self._inner.dialect

    def execute(
        self,
        sql: str,
        binds: Any,
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        return self._inner.execute(sql, binds, document_reads)

    def execute_write(self, sql: str, binds: Any) -> int:
        armed = self._armed_at("work")
        if armed is not None:
            self._state.fired = True
            if armed.error is None:
                return 0
            raise armed.error()
        return self._inner.execute_write(sql, binds)

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: IsolationLevel | None = None
    ) -> TransactionOutcome[T]:
        # A boundary-seam fault is a boundary that never opened, so this ANSWERS
        # `BeginFailed` instead of raising and never reaches the inner port: the
        # callback does not run, no attempt begins, and the handle's own rule
        # surfaces the error terminally (`m-db-port` "Mapping obligations"). A
        # fault the WORK meets fires at the write seam above instead.
        armed = self._armed_at("boundary")
        if armed is not None and armed.error is not None:
            self._state.fired = True
            return BeginFailed(armed.error())
        inner = self

        def wrapped(conn: DbPort) -> T:
            return body(
                FaultInjectingPort(
                    conn, fault=inner._fault, persistent=inner._persistent, state=inner._state
                )
            )

        return self._inner.transaction(wrapped, isolation=isolation)

    def _armed_at(self, seam: Literal["work", "boundary"]) -> _Fault | None:
        """The case's own fault where ``seam`` is the one it belongs to and this
        chain has not already spent a one-shot injection."""
        if self._fault is None or not (self._persistent or not self._state.fired):
            return None
        armed = _fault(self._fault)
        return armed if armed.seam == seam else None


def expected_attempts(
    *,
    fault: str | None,
    outcome_kind: str,
    retries: int | None,
    retry_optimistic_conflicts: bool | None,
) -> int:
    """The authored attempt count (`m-auto-retry.md` / `m-opt-lock.md`'s own
    retriability rules, never a per-case hand table): no fault surfaces or
    commits after exactly one attempt; a NON-retriable fault (a
    `lock-wait-timeout`, or an `optimistic-lock-conflict` without the
    opt-in) surfaces after one; a retriable fault retried to `committed`
    succeeds on the SECOND attempt (`persistent` — see
    :class:`FaultInjectingPort` — is a don't-care there, injected once);
    a retriable fault that PERSISTS to a failure-kind outcome exhausts the
    bound (`retries` re-executions, so ``bound + 1`` total attempts).

    A BOUNDARY-seam fault answers ZERO: a boundary that never opened ran no
    attempt at all, which is a different count from an attempt that ran and
    failed, and it is the count that separates "the callback never ran" from
    "the callback ran and was undone".

    Which seam a kind belongs to and whether it is retriable are read off
    :data:`_FAULTS` rather than tested here, so one kind's declaration answers
    the injection point and the count together.

    This is the ONE place the retry defaults an omitting case inherits are
    restated, because an oracle needs the resolved numbers: ``None`` retries
    means 10 (`m-auto-retry.md` "The bound is configurable with a default of
    10") and an absent opt-in means off (`m-opt-lock.md`).
    """
    if fault is None:
        return 1
    kind = _fault(fault)
    if kind.seam == "boundary":
        return 0
    retriable = (
        bool(retry_optimistic_conflicts)
        if kind.retriable == "opt-in"
        else kind.retriable == "always"
    )
    if not retriable:
        return 1
    bound = retries if retries is not None else 10
    if outcome_kind == "committed":
        return 1 if bound < 1 else 2
    return bound + 1
