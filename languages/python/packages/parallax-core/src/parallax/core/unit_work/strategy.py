from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal, Protocol, cast, get_args, runtime_checkable

from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    TemporalDimension,
)
from parallax.core.temporal_read import Bitemporal, TransactionTimeOnly
from parallax.core.unit_work.clock import TransactionInstant
from parallax.core.unit_work.observe import WriteObservation
from parallax.core.unit_work.planned import CloseCause, PlannedWrite

__all__ = [
    "AUTHORED_FROM",
    "AUTHORED_STATE",
    "AUTHORED_UNTIL",
    "CARRIED_STATE",
    "CHANGED_STATE",
    "NO_AUDIT",
    "OPEN_END",
    "PREDECESSOR_END",
    "PREDECESSOR_START",
    "ActorIdentity",
    "AuditStrategy",
    "AuthoredFrom",
    "AuthoredState",
    "AuthoredUntil",
    "BatchingStrategy",
    "CarriedState",
    "ChangedState",
    "Concurrency",
    "ConcurrencyStrategy",
    "DatabaseLoginActor",
    "MilestoneClosure",
    "MilestoneSuccessor",
    "MilestoneTopology",
    "OpenEnd",
    "PredecessorEnd",
    "PredecessorStart",
    "SubjectActor",
    "SuccessorState",
    "TemporalStrategy",
    "ValidTimeBound",
    "ValidTimeWindow",
    "VersionArithmetic",
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


@dataclass(frozen=True, slots=True)
class AuthoredFrom:
    """The mutation's own Valid-Time start."""


AUTHORED_FROM: Final[AuthoredFrom] = AuthoredFrom()


@dataclass(frozen=True, slots=True)
class AuthoredUntil:
    """The mutation's own Valid-Time exclusive end, on a bounded verb."""


AUTHORED_UNTIL: Final[AuthoredUntil] = AuthoredUntil()


@dataclass(frozen=True, slots=True)
class PredecessorStart:
    """The observed predecessor rectangle's Valid-Time start."""


PREDECESSOR_START: Final[PredecessorStart] = PredecessorStart()


@dataclass(frozen=True, slots=True)
class PredecessorEnd:
    """The observed predecessor rectangle's Valid-Time exclusive end."""


PREDECESSOR_END: Final[PredecessorEnd] = PredecessorEnd()


@dataclass(frozen=True, slots=True)
class OpenEnd:
    """The open Valid-Time bound: the rectangle runs on without end."""


OPEN_END: Final[OpenEnd] = OpenEnd()

type ValidTimeBound = AuthoredFrom | AuthoredUntil | PredecessorStart | PredecessorEnd | OpenEnd
"""Where one Valid-Time bound of a successor comes from.

Naming the *source* rather than a value is what keeps the description scoped to
the whole mutation: every resolved row of a predicate-selected mutation shares
one topology while each supplies its own predecessor bounds.
"""


@dataclass(frozen=True, slots=True)
class ValidTimeWindow:
    """The half-open Valid-Time interval one successor covers."""

    start: ValidTimeBound
    end: ValidTimeBound


@dataclass(frozen=True, slots=True)
class CarriedState:
    """The successor represents its predecessor's state, unchanged."""


CARRIED_STATE: Final[CarriedState] = CarriedState()


@dataclass(frozen=True, slots=True)
class ChangedState:
    """The successor represents its predecessor's state with the authored change
    set overlaid."""


CHANGED_STATE: Final[ChangedState] = ChangedState()


@dataclass(frozen=True, slots=True)
class AuthoredState:
    """The successor represents the authored row alone, having no predecessor."""


AUTHORED_STATE: Final[AuthoredState] = AuthoredState()

type SuccessorState = CarriedState | ChangedState | AuthoredState
"""Which represented state one successor opens with.

It is what an Insert Origin is derived from: carried and changed state name the
observed predecessor they came from, while authored state begins a lineage.
"""


@dataclass(frozen=True, slots=True)
class MilestoneSuccessor:
    """One current milestone an authored temporal mutation opens.

    ``valid_window`` is absent on a Transaction-Time-Only target, which has no
    second axis to bound.
    """

    state: SuccessorState
    valid_window: ValidTimeWindow | None = None


@dataclass(frozen=True, slots=True)
class MilestoneClosure:
    """The current milestone an authored temporal mutation stops being current.

    ``gate_basis`` names the As-Of Axis whose observed start an optimistic close
    binds; whether it is bound at all is the concurrency decision, made while
    the close is settled.
    """

    cause: CloseCause
    gate_basis: TemporalDimension


@dataclass(frozen=True, slots=True)
class MilestoneTopology:
    """One authored temporal mutation's neutral topology.

    ``closure`` is absent for a mutation that opens history rather than
    revising it. Successors are in the facet's canonical order — head, middle,
    tail where each exists — which is the order they are expanded in.
    """

    closure: MilestoneClosure | None
    successors: tuple[MilestoneSuccessor, ...]


@runtime_checkable
class TemporalStrategy(Protocol):
    """How one temporal facet describes an authored mutation's topology.

    ``shape`` is the target family's compiled Temporal Shape: selecting the
    Transaction-Time-Only facet versus the Bitemporal one is itself part of "how
    a temporal facet describes a mutation" (the two facet modules are optional
    policy this scope cannot import), so the injected adapter dispatches on the
    shape's variant rather than the caller doing so.
    """

    def topology(
        self, shape: TransactionTimeOnly | Bitemporal, mutation: str
    ) -> MilestoneTopology: ...


@runtime_checkable
class BatchingStrategy(Protocol):
    """Which buffered rows may share one statement (`m-batch-write`).

    Eligibility and physical grouping are separate questions: the first is a
    write-shape decision the batching policy owns, the second compares the
    layout selections two rows make and belongs to the composition root.
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


@runtime_checkable
class AuditStrategy(Protocol):
    """How Audit Provenance decorates one finalized step.

    Decoration consumes the settled Insert Origins and Close Causes and adds
    ordinary planned values; it changes no topology, classifies no gate, and
    emits no SQL. ``actor_identity`` and ``transaction_instant`` are the
    request-scoped inputs a real provenance adapter needs — the identity to
    stamp and the shared instant to stamp it at — passed through unevaluated:
    an implementation that never resolves ``transaction_instant`` costs the
    surviving flush no clock access beyond what its own topology already
    required (`m-unit-work` "The Transaction Instant").

    Only eagerly settled steps reach this port. A Materialized Write Group's
    rows are rebuilt on demand from a segment holding no strategy object and
    no unevaluated instant, so they cannot be decorated one step at a time;
    every row of one group shares one authored mutation, one Actor Identity,
    and one instant, so a group's provenance is one overlay resolved at settle
    time rather than a per-row decoration.
    """

    def decorate(
        self,
        step: PlannedWrite,
        *,
        actor_identity: ActorIdentity,
        transaction_instant: TransactionInstant,
    ) -> PlannedWrite: ...


@dataclass(frozen=True, slots=True)
class UndecoratedAudit:
    """The audit-neutral default: every step passes through unchanged."""

    def decorate(
        self,
        step: PlannedWrite,
        *,
        actor_identity: ActorIdentity,
        transaction_instant: TransactionInstant,
    ) -> PlannedWrite:
        return step


NO_AUDIT: Final[UndecoratedAudit] = UndecoratedAudit()
