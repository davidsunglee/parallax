"""``parallax.conformance.boundary_runner`` — the D-17 case-driven boundary runner.

A `boundary` case (`m-auto-retry` / `m-opt-lock`, `m-case-format` "Boundary
cases") proves a unit-of-work loop-mechanics branch a single-connection
harness cannot provoke: it carries no golden SQL, only a portable
`when.boundary` action list, an OPTIONAL `given.fault`, its retry
configuration (`when.uow`), and the portable `then.outcome`. This module
hosts the machinery ONE parametrized runner drives against EVERY reachable
boundary case — never a per-case hand function (the SAME hand-mirroring D-17
exists to end):

- :func:`boundary_uow` / :func:`boundary_actions` parse a case's own
  `when.uow` / `when.boundary` (schema camelCase -> the Python `db.transact`
  snake_case options).
- :func:`run_boundary_actions` is the ONE deterministic action -> verb
  mapping every boundary case shares (every corpus witness targets
  `models/account.yaml`'s versioned `Account` row).
- :class:`FaultInjectingPort` is the fault-injecting `m-db-port` DECORATOR
  (wraps a REAL adapter): it SIMULATES the case's `given.fault` at the write
  seam; the real classification / retry-loop / optimistic-gate machinery
  does the classifying, never this module.
- :func:`expected_attempts` derives the authored attempt count from the
  SAME fields `m-auto-retry.md` / `m-opt-lock.md` fix the retriability rules
  from (never a per-case hand table).

Exercised by the real-database suite (`tests/api_conformance/test_boundary_
run.py`, over the shipped `parallax-postgres` adapter) and, DB-free, by unit
tests over a fake port (`tests/unit/test_boundary_runner.py`) — the same
split every other engine-adjacent module in this package already follows.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final, cast

from parallax.conformance import case_format
from parallax.conformance.story_models import Account
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import DbPort, Row
from parallax.core.unit_work import Concurrency
from parallax.snapshot.handle import Transaction

__all__ = [
    "TARGET_ID",
    "BoundaryAbort",
    "BoundaryUow",
    "FaultInjectingPort",
    "boundary_actions",
    "boundary_uow",
    "expected_attempts",
    "fault_kind",
    "outcome",
    "reachable_boundary_cases",
    "run_boundary_actions",
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
    """Every `boundary`-shape case in the corpus (parametrized at runtime,
    never a hand list — `m-case-format`: every boundary case is
    `lane: api-conformance`)."""
    corpus = cases if cases is not None else case_format.load_cases()
    return [case for case in corpus if case.shape == "boundary"]


@dataclass(frozen=True, slots=True)
class BoundaryUow:
    """A boundary case's own `when.uow` (m-auto-retry / m-opt-lock retry
    configuration), defaulted exactly as `db.transact`'s own sentinel-backed
    options resolve them (`python.md` §5)."""

    concurrency: Concurrency
    retries: int | None
    retry_optimistic_conflicts: bool


def boundary_uow(case: case_format.Case) -> BoundaryUow:
    when = cast("dict[str, Any]", case.document.get("when") or {})
    uow = cast("dict[str, Any]", when.get("uow") or {})
    concurrency = cast("Concurrency", uow.get("concurrency", "locking"))
    retries = uow.get("retries")
    return BoundaryUow(
        concurrency=concurrency,
        retries=cast("int | None", retries),
        retry_optimistic_conflicts=bool(uow.get("retryOptimisticConflicts", False)),
    )


def boundary_actions(case: case_format.Case) -> list[str]:
    """The case's own `when.boundary` ordered action list (`m-case-format`)."""
    when = cast("dict[str, Any]", case.document.get("when") or {})
    steps = cast("list[dict[str, Any]]", when.get("boundary") or [])
    return [cast("str", step["action"]) for step in steps]


def fault_kind(case: case_format.Case) -> str | None:
    """The case's OPTIONAL `given.fault` — absent for a pure loop-configuration
    case (`retries: 0`, `m-unit-work-004`'s own withheld-value proof)."""
    given = cast("dict[str, Any]", case.document.get("given") or {})
    fault = given.get("fault")
    return cast("str | None", fault) if isinstance(fault, str) else None


def outcome(case: case_format.Case) -> str:
    then = cast("dict[str, Any]", case.document.get("then") or {})
    return cast("str", then["outcome"])


def run_boundary_actions(tx: Transaction, actions: Sequence[str]) -> Account | None:
    """The ONE deterministic `when.boundary` action -> verb mapping every
    boundary case shares (D-17; never a per-case hand function): every
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
    - ``terminate`` has no legal target on this NON-temporal model — a loud
      refusal (no reachable corpus witness authors it either).

    Returns the LAST tracked :class:`Account` (the closure's own return
    value — `then.outcome: committed`'s "callback value returned" half),
    ``None`` after a ``delete``.
    """
    current: Account | None = None
    for action in actions:
        if action == "read":
            current = tx.find(Account.where(Account.id == TARGET_ID)).result()
        elif action == "update":
            if current is None:
                raise AssertionError("an `update` action needs a prior `read` observation")
            current = current.model_copy(update={"balance": current.balance + _BUMP})
            tx.update(current)
        elif action == "create":
            current = Account(id=90, owner="Boundary", balance=Decimal("0.00"), version=1)
            tx.insert(current)
        elif action == "delete":
            if current is None:
                raise AssertionError("a `delete` action needs a prior `read` observation")
            tx.delete(current)
            current = None
        elif action == "terminate":
            raise AssertionError(
                "`terminate` has no legal target on the non-temporal account.yaml model "
                "(no reachable boundary case authors it)"
            )
        else:  # pragma: no cover - m-case-format's `when.boundary.action` enum is closed
            raise AssertionError(f"unrecognized boundary action {action!r}")
    return current


def translated_fault(kind: str) -> DatabaseError:
    """The SAME translated :class:`DatabaseError` the real adapter's own
    classification would produce for a transient `given.fault` kind
    (`m-db-error` vocabulary) — the decorator SIMULATES the failure; the
    real retry loop still classifies it via `DatabaseError.category` /
    `.is_retriable`, never a value this module invents."""
    if kind == "serialization-failure":
        return DatabaseError(
            category="deadlock", native_code="40001", message="serialization failure"
        )
    if kind == "deadlock":
        return DatabaseError(category="deadlock", native_code="40P01", message="deadlock detected")
    if kind == "lock-wait-timeout":
        return DatabaseError(
            category="lockWaitTimeout", native_code="55P03", message="lock wait timeout"
        )
    raise ValueError(f"unrecognized fault kind {kind!r}")  # pragma: no cover - schema-closed enum


@dataclass(slots=True)
class _FaultState:
    """Shared, mutable state one :class:`FaultInjectingPort` chain (the
    top-level instance plus every nested copy `.transaction()` wraps) tracks
    across a WHOLE `db.transact` retry loop — never reset per attempt."""

    attempts: int = 0
    fired: bool = False


class FaultInjectingPort:
    """A pass-through ``m-db-port`` DECORATOR over a REAL adapter, injecting
    ``fault`` at the write seam (D-17): the decorator SIMULATES the fault —
    the real classification / retry-loop / optimistic-gate machinery does
    the rest, end to end.

    ``persistent`` fires the fault on EVERY attempt's write (a case whose
    `then.outcome` is a failure kind needs this — an outcome OTHER than
    `committed` means the fault must survive to exhaustion, or (a
    non-retriable / disabled-loop case) is a don't-care since only one
    attempt ever runs either way); a `committed` outcome needs the fault to
    fire ONCE only, so the retry succeeds. ``optimistic-lock-conflict``
    never raises from here — it returns ``0`` from the gated update's
    ``execute_write`` (the concurrent-writer simulation), letting the real
    ``expected_affected`` mismatch -> ``classify_mismatch`` ->
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
    def attempts(self) -> int:
        return self._state.attempts

    def execute(self, sql: str, binds: Any) -> list[Row]:
        return self._inner.execute(sql, binds)

    def execute_write(self, sql: str, binds: Any) -> int:
        if self._fault is not None and (self._persistent or not self._state.fired):
            self._state.fired = True
            if self._fault == "optimistic-lock-conflict":
                return 0
            raise translated_fault(self._fault)
        return self._inner.execute_write(sql, binds)

    def transaction[T](self, body: Callable[[DbPort], T]) -> T:
        self._state.attempts += 1
        inner = self

        def wrapped(conn: DbPort) -> T:
            return body(
                FaultInjectingPort(
                    conn, fault=inner._fault, persistent=inner._persistent, state=inner._state
                )
            )

        return self._inner.transaction(wrapped)


def expected_attempts(
    *,
    fault: str | None,
    outcome_kind: str,
    retries: int | None,
    retry_optimistic_conflicts: bool,
) -> int:
    """The authored attempt count (`m-auto-retry.md` / `m-opt-lock.md`'s own
    retriability rules, never a per-case hand table): no fault surfaces or
    commits after exactly one attempt; a NON-retriable fault (a
    `lock-wait-timeout`, or an `optimistic-lock-conflict` without the
    opt-in) surfaces after one; a retriable fault retried to `committed`
    succeeds on the SECOND attempt (`persistent` — see
    :class:`FaultInjectingPort` — is a don't-care there, injected once);
    a retriable fault that PERSISTS to a failure-kind outcome exhausts the
    bound (`retries` re-executions, so ``bound + 1`` total attempts;
    `retries` defaults to 10, `m-auto-retry.md` "The bound is configurable
    with a default of 10").
    """
    if fault is None:
        return 1
    if fault == "optimistic-lock-conflict":
        retriable = retry_optimistic_conflicts
    elif fault == "lock-wait-timeout":
        retriable = False
    else:  # serialization-failure / deadlock — always retriable (m-auto-retry.md)
        retriable = True
    if not retriable:
        return 1
    bound = retries if retries is not None else 10
    if outcome_kind == "committed":
        return 1 if bound < 1 else 2
    return bound + 1
