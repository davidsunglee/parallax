from __future__ import annotations

from collections.abc import Callable, Collection, Container, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal, Protocol, cast, get_args, runtime_checkable

from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
)
from parallax.core.unit_work.claims import SettledEvidence
from parallax.core.unit_work.clock import TransactionInstant
from parallax.core.unit_work.instructions import KeyedMutation
from parallax.core.unit_work.retain import RetainedObservation
from parallax.core.write_plan.keys import ObjectKey
from parallax.core.write_plan.observe import WriteObservation
from parallax.core.write_plan.planned_rows import WritePlanningError
from parallax.core.write_plan.steps import (
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
    "BatchingStrategy",
    "Concurrency",
    "ConcurrencyStrategy",
    "DatabaseLoginActor",
    "EvidencePolicyLookup",
    "SubjectActor",
    "VersionArithmetic",
    "WriteEvidencePolicy",
    "concurrency_preference",
]

# The closed two-valued concurrency vocabulary (`m-unit-work` "Strategy
# selection"). ONE name spells two related things: the unit of work's resolved
# Concurrency PREFERENCE, and the Effective Concurrency STRATEGY `m-opt-lock`
# derives per Entity from that preference and the Entity's Optimistic Lock
# Facet. They coincide in spelling and differ in scope — a preference is
# transaction-wide, a strategy is per Entity — so a signature naming this type
# says which one it means.
# Declared here, rather than on the unit-of-work shell that names it first in
# prose, because every strategy port switches on it and both the shell
# (`uow.py`) and the planner (`write_planner.py`) need the same value: defining
# it in either would make the other import back.
Concurrency = Literal["locking", "optimistic"]

CONCURRENCY_PREFERENCES: Final[frozenset[str]] = frozenset(get_args(Concurrency))


def concurrency_preference(value: object) -> Concurrency:
    """Return the vocabulary's own spelling of ``value``, or raise ``ValueError``.

    The vocabulary is closed, so a name outside it names no strategy any Entity
    could resolve — the caller's mistake, reportable before a unit of work opens.
    Every value outside it is refused the one way, whatever its type: the
    candidate is compared to each preference rather than looked up in the set,
    since a value no set can be asked about (an unhashable ``str`` subclass)
    would make membership alone raise ``TypeError``. What comes back is the
    matched preference itself, never the caller's own object.
    """
    known = sorted(CONCURRENCY_PREFERENCES)
    if isinstance(value, str):
        for preference in known:
            if value == preference:
                return cast("Concurrency", preference)
    raise ValueError(f"concurrency must be one of {known}, got {value!r}")


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
class BatchingStrategy(Protocol):
    """Which buffered rows may share one statement (`m-batch-write`).

    Eligibility and physical grouping are separate questions: the first is a
    write-shape decision the batching policy owns, the second compares the
    layout selections two rows make and belongs to model preparation.
    """

    def collapses(
        self,
        model: Metamodel,
        entity: EntityMetadata,
        mutation: str,
        rows: Sequence[Mapping[str, object]],
    ) -> bool: ...

    def group_key(
        self,
        model: Metamodel,
        entity: EntityMetadata,
        mutation: str,
        row: Mapping[str, object],
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class VersionArithmetic:
    """The two numbers `m-opt-lock` fixes for every versioned write: the version
    a new lineage opens at, and the step a successful write advances by.

    Data rather than policy — it decides nothing beyond addition — which is what
    lets a settled write keep it. A packed run of a Materialized Write Group's
    rows advances each row's observed version at step access from the value here
    rather than from a precomputed second column, and holding the strategy that
    produced it would instead put a policy object inside a Write Plan.
    """

    initial: int
    increment: int

    def advance(self, observed: int) -> int:
        return observed + self.increment


@runtime_checkable
class ConcurrencyStrategy(Protocol):
    """How one transaction's Concurrency Preference settles a versioned write's
    gate and version arithmetic (`m-opt-lock`).

    Every method mirrors one `m-opt-lock` policy question the planner cannot
    answer itself, because the module DAG runs `m-opt-lock --> m-unit-work`:
    which Attribute (if any) carries an entity's optimistic version, whether the
    write's own Entity gates at all, the arithmetic every version value derives
    from, whether a required version was actually observed, and whether a row
    still authors an explicit version value. Each raises the policy's own error
    on refusal; the planner never inspects or re-raises a specific type.

    ``gates`` takes the write's own Entity beside the preference because a gate
    is settled per Entity, not per transaction: the preference combines with
    that Entity's Optimistic Lock Facet into its Effective Concurrency
    Strategy, and only the Optimistic one gates. Both entity-scoped questions
    take the accepted model the caller already holds, so one stateless
    implementation serves every model.
    """

    def version_attribute(
        self, model: Metamodel, entity: EntityIdentity
    ) -> AttributeIdentity | None: ...

    def gates(self, concurrency: Concurrency, model: Metamodel, entity: EntityIdentity) -> bool: ...

    def version_arithmetic(self) -> VersionArithmetic: ...

    def require_version(
        self, entity: EntityIdentity, observation: WriteObservation | None
    ) -> int: ...

    def reject_authored_version(
        self, entity: EntityIdentity, attribute: AttributeIdentity
    ) -> None: ...


class WriteEvidencePolicy(Protocol):
    """One target Entity's write-evidence policy (`m-opt-lock`), which the unit
    of work applies to its own transaction state when it admits a keyed write.

    Both answers are declared facts about the target's family, never about a
    source's evidence: :meth:`effective_strategy` combines the unit of work's
    Concurrency Preference with the family's version source, and
    :meth:`settled_evidence` names what a keyed write settles against — and so
    claims — from the mutation alone: nothing for an insert, the supplied
    observation for a versioned or temporal family, and the supplied object
    key for an unversioned Non-Temporal one. Neither reads participation,
    consumption, or claims, which are the unit of work's own state, and
    neither refuses anything.
    """

    def effective_strategy(self, preference: Concurrency, /) -> Concurrency: ...

    def settled_evidence(
        self,
        mutation: KeyedMutation,
        /,
        *,
        object_key: ObjectKey | None,
        observation: WriteObservation | RetainedObservation | None,
    ) -> SettledEvidence | None: ...


type EvidencePolicyLookup = Callable[[EntityIdentity], WriteEvidencePolicy]
"""The connected model's write-evidence policy for one accepted Entity.

Bound once per accepted model by model preparation, because the policy is
`m-opt-lock`'s and the module DAG runs `m-opt-lock --> m-unit-work`. An identity
the model does not declare raises ``KeyError`` rather than answering a default
policy: what an unrecognized Entity's write may claim cannot be read off what
was missing.
"""


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
    version — which no answer may state. ``neutral`` says the strategy is the
    audit-neutral default, which answers every input unchanged: a settlement
    holding rows only as compact backing then builds none merely to ask, and
    keeps what any other strategy adds (``assignments_added``) rather than the
    steps it answered.
    """

    audit: AuditStrategy
    actor_identity: ActorIdentity
    transaction_instant: TransactionInstant
    settled: Container[object]

    @property
    def neutral(self) -> bool:
        return isinstance(self.audit, UndecoratedAudit)

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
        or not _keeps(write_row.row.attributes, finalized.row.attributes, executed)
        or not _keeps(write_row.row.value_objects, finalized.row.value_objects, executed)
    ):
        raise _audit_refused("a row's finalization")


def _keeps[K](
    members: Mapping[K, object], final: Mapping[K, object], stated: Collection[object]
) -> bool:
    """Whether ``final`` holds every member of ``members`` as it was, but for
    the ``stated`` ones, and adds none it does not state."""
    return all(
        member in final and (final[member] is value or member in stated)
        for member, value in members.items()
    ) and all(member in members or member in stated for member in final)


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


def _audit_refused(what: str) -> WritePlanningError:
    return WritePlanningError(
        f"{what} must state every value it adds or changes as an assignment, state no "
        "primary key, temporal bound, or optimistic version, and keep the origin, address, "
        "gate, and affected-row policy it was given (m-unit-work)"
    )
