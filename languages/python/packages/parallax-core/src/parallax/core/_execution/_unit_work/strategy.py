from __future__ import annotations

from collections.abc import Collection, Container
from dataclasses import dataclass
from typing import Final, Protocol, runtime_checkable

from parallax.core._execution._unit_work.clock import TransactionInstant
from parallax.core.internal.base import InternalError
from parallax.core.internal.write_plan.managed_row import ManagedRow
from parallax.core.internal.write_plan.planned_rows import WRITE_PLANNING_FAILED
from parallax.core.internal.write_plan.steps import (
    PlannedAssignments,
    PlannedClose,
    PlannedUpdate,
    WriteRow,
)

__all__ = [
    "NO_AUDIT",
    "ActorIdentity",
    "AuditDecoration",
    "AuditStrategy",
    "DatabaseLoginActor",
    "SubjectActor",
]


@dataclass(frozen=True, slots=True)
class SubjectActor:
    """A validated application Subject Identity carried through planning."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value:  # pyright: ignore[reportUnnecessaryIsInstance] - validate runtime callers
            raise ValueError("SubjectActor.value must be a nonempty string")
        if self.value.startswith("db-login:"):
            raise ValueError("SubjectActor.value must not begin with 'db-login:'")


@dataclass(frozen=True, slots=True)
class DatabaseLoginActor:
    """A validated database-authenticated login carried through planning."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value:  # pyright: ignore[reportUnnecessaryIsInstance] - validate runtime callers
            raise ValueError("DatabaseLoginActor.value must be a nonempty string")


type ActorIdentity = SubjectActor | DatabaseLoginActor


@runtime_checkable
class AuditStrategy(Protocol):
    """How Audit Provenance stamps what a write stores (`m-unit-work`).

    :meth:`finalize_row` gives one represented row — a new lineage's opening,
    or a successor carried or changed from its predecessor — its final values,
    once, before settlement compares or realizes it. Every value it adds or
    changes is an executed assignment of the row it returns, beside the row's
    authored ones, and every other member keeps the value it had.
    :meth:`decorate_update` stamps a Non-Temporal update, keyed or readless,
    without a complete row, and :meth:`decorate_close` stamps a closed
    predecessor. Each adds ordinary planned values and changes no topology,
    target, gate, cause, or affected-row policy, and emits no SQL: none states
    a primary key, temporal bound, or optimistic version. A guard, a
    removal, a delete, and a milestone kept unchanged store no represented
    value and meet none of them.

    ``actor_identity`` and ``transaction_instant`` are the request-scoped inputs
    a real provenance adapter needs — the identity to stamp and the shared
    instant to stamp it at — passed through unevaluated: an implementation that
    never resolves ``transaction_instant`` costs the surviving flush no clock
    access beyond what its own topology already required (`m-unit-work` "The
    Transaction Instant").
    """

    def finalize_row(
        self,
        write_row: WriteRow,
        *,
        actor_identity: ActorIdentity,
        transaction_instant: TransactionInstant,
    ) -> WriteRow: ...

    def decorate_update(
        self,
        update: PlannedUpdate,
        *,
        actor_identity: ActorIdentity,
        transaction_instant: TransactionInstant,
    ) -> PlannedUpdate: ...

    def decorate_close(
        self,
        close: PlannedClose,
        *,
        actor_identity: ActorIdentity,
        transaction_instant: TransactionInstant,
    ) -> PlannedClose: ...


@dataclass(frozen=True, slots=True)
class UndecoratedAudit:
    """The audit-neutral default: every row, update, and close passes through
    unchanged."""

    def finalize_row(
        self,
        write_row: WriteRow,
        *,
        actor_identity: ActorIdentity,
        transaction_instant: TransactionInstant,
    ) -> WriteRow:
        return write_row

    def decorate_update(
        self,
        update: PlannedUpdate,
        *,
        actor_identity: ActorIdentity,
        transaction_instant: TransactionInstant,
    ) -> PlannedUpdate:
        return update

    def decorate_close(
        self,
        close: PlannedClose,
        *,
        actor_identity: ActorIdentity,
        transaction_instant: TransactionInstant,
    ) -> PlannedClose:
        return close


NO_AUDIT: Final[UndecoratedAudit] = UndecoratedAudit()


@dataclass(frozen=True, slots=True)
class AuditDecoration:
    """The configured Audit Strategy applied with the attempt's Actor Identity
    and Transaction Instant, whether settlement runs at planning or binds a
    range at execution. Built for one settlement and never retained by what it
    settles.

    Each hook's answer is held to its contract before settlement uses it, so a
    strategy cannot move what a step addresses or change a value without
    stating it as an executed assignment. ``settled`` holds the Attributes
    settlement alone decides — every primary key, temporal bound, and optimistic
    version — which no answer may state.
    """

    audit: AuditStrategy
    actor_identity: ActorIdentity
    transaction_instant: TransactionInstant
    settled: Container[object]

    def finalize_row(self, write_row: WriteRow) -> WriteRow:
        finalized = self.audit.finalize_row(
            write_row,
            actor_identity=self.actor_identity,
            transaction_instant=self.transaction_instant,
        )
        if finalized is not write_row:
            _require_finalized(write_row, finalized, self.settled)
        return finalized

    def decorate_update(self, update: PlannedUpdate) -> PlannedUpdate:
        decorated = self.audit.decorate_update(
            update,
            actor_identity=self.actor_identity,
            transaction_instant=self.transaction_instant,
        )
        if decorated is not update and (
            decorated.entity != update.entity
            or decorated.target != update.target
            or decorated.concurrency != update.concurrency
            or decorated.affected_rows != update.affected_rows
            or not _extends(update.assignments, decorated.assignments, self.settled)
        ):
            raise _audit_refused("an update's decoration")
        return decorated

    def decorate_close(self, close: PlannedClose) -> PlannedClose:
        decorated = self.audit.decorate_close(
            close,
            actor_identity=self.actor_identity,
            transaction_instant=self.transaction_instant,
        )
        if decorated is not close and (
            decorated.entity != close.entity
            or decorated.target != close.target
            or decorated.cause != close.cause
            or decorated.concurrency != close.concurrency
            or decorated.affected_rows != close.affected_rows
            or not _extends(close.assignments, decorated.assignments, self.settled)
        ):
            raise _audit_refused("a close's decoration")
        return decorated


def _require_finalized(
    write_row: WriteRow, finalized: WriteRow, settled: Container[object]
) -> None:
    """Refuse a finalized row that changed its origin, dropped an executed
    member, changed a member it does not state as executed, or states a
    ``settled`` one."""
    executed = finalized.executed
    if (
        finalized.origin is not write_row.origin
        or any(member not in executed for member in write_row.executed)
        or any(member in settled for member in executed if member not in write_row.executed)
        or not _keeps(write_row.row, finalized.row, executed)
    ):
        raise _audit_refused("a row's finalization")


def _keeps(row: ManagedRow, final: ManagedRow, stated: Collection[object]) -> bool:
    """Whether ``final`` holds every member of ``row`` as it was, but for the
    ``stated`` ones, and adds none it does not state."""
    if final.selection is not row.selection:
        return False
    identities = row.selection.members.identities
    for position in range(row.selection.width):
        held = row.stated(position)
        if not held and not final.stated(position):
            continue
        if held:
            if not final.stated(position):
                return False
            if final.at(position) is row.at(position):
                continue
        if identities[position] not in stated:
            return False
    return True


def _extends(
    stated: PlannedAssignments, final: PlannedAssignments, settled: Container[object]
) -> bool:
    """Whether ``final`` keeps every assignment ``stated`` makes, as stated,
    and adds none to a ``settled`` Attribute."""
    return (
        all(
            identity in final.attributes and final.attributes[identity] is value
            for identity, value in stated.attributes.items()
        )
        and all(
            identity in final.value_objects and final.value_objects[identity] is value
            for identity, value in stated.value_objects.items()
        )
        and not any(
            identity in settled and identity not in stated.attributes
            for identity in final.attributes
        )
    )


def _audit_refused(what: str) -> InternalError:
    return InternalError(
        WRITE_PLANNING_FAILED,
        f"{what} must state every value it adds or changes as an assignment, state no "
        "primary key, temporal bound, or optimistic version, and keep the origin, address, "
        "gate, and affected-row policy it was given (m-unit-work)",
    )
