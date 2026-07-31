"""The strategy ports write finalization reaches its sibling policies through
(m-unit-work).

The module DAG runs from each optional policy module *to* this scope, so
finalization cannot import batching, concurrency, temporal, or provenance
policy directly. It declares the ports here instead and the composition root
injects one implementation of each. Implementations are structural: nothing
inherits these Protocols, exactly as no clock inherits ``Clock``.

The temporal port is the load-bearing one. Its answer is a **neutral topology
description**, scoped to one authored mutation rather than to one resolved row:
which milestone closes and why, what an optimistic close gates on, and the
interval and state of each successor the mutation opens. A predicate-selected
mutation resolving many rows therefore yields one description, not one per row,
so the description's size never grows with the result set. The description names
no SQL, dialect, physical column, or statement — which is exactly what lets
temporal expansion live inside finalization while column participation and
quoting stay in lowering.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal, Protocol, runtime_checkable

from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    EntityMetadata,
    Metamodel,
    TemporalDimension,
)
from parallax.core.unit_work.clock import TransactionInstant
from parallax.core.unit_work.observe import TransactionTimeBasis, WriteObservation
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
    "AuditStrategy",
    "AuthoredFrom",
    "AuthoredState",
    "AuthoredUntil",
    "BatchingStrategy",
    "CarriedState",
    "ChangedState",
    "Concurrency",
    "ConcurrencyStrategy",
    "MilestoneClosure",
    "MilestoneSuccessor",
    "MilestoneTopology",
    "OpenEnd",
    "PredecessorEnd",
    "PredecessorStart",
    "SubjectIdentity",
    "SuccessorState",
    "TemporalStrategy",
    "UndecoratedAudit",
    "ValidTimeBound",
    "ValidTimeWindow",
    "capture_subject_identity",
]

# The per-unit-of-work participation mode (`m-unit-work` "Strategy selection").
# Declared here, rather than on the unit-of-work shell that names it first in
# prose, because every strategy port switches on it and both the shell
# (`uow.py`) and the planner (`write_planner.py`) need the same value: defining
# it in either would make the other import back.
Concurrency = Literal["locking", "optimistic"]


@dataclass(frozen=True, slots=True)
class SubjectIdentity:
    """The stable, opaque planning-input identifying the Principal captured at
    the outer database operation boundary (ADR 0034).

    Unit Work owns this value type exactly as it already owns the Write
    Observation vocabulary, so a Planning Request is well-typed before any
    provenance behavior exists. Construction performs no validation: an
    audit-neutral implementation MUST NOT inspect, validate, retain,
    serialize, persist, lower, or bind the supplied value, and two planning
    calls differing only in Subject Identity MUST produce equal Write Plans
    and identical emitted SQL and binds —
    ``test_subject_identity_neutrality.py`` demonstrates this. The nonempty
    requirement `m-unit-work.md` states is enforced where a raw value is
    captured (:func:`capture_subject_identity`), not by this type.
    """

    value: str


def capture_subject_identity(value: str) -> SubjectIdentity:
    """Construct a Subject Identity from a freshly captured value.

    Capture belongs to the Principal boundary, not to Write Planning
    (`m-unit-work.md` "Subject Identity") — this is where the boundary's
    nonempty check runs, once, at the moment a raw value becomes a Subject
    Identity, so the value type itself stays inert.
    """
    if not value:
        raise ValueError("a Subject Identity is nonempty")
    return SubjectIdentity(value)


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

    ``entity`` is the declaring root: selecting the Transaction-Time-Only facet
    versus the Bitemporal one is itself part of "how a temporal facet describes
    a mutation" (the two facet modules are optional policy this scope cannot
    import), so the injected adapter dispatches on the entity's own declared
    As-Of Axes rather than the caller doing so.
    """

    def topology(self, entity: EntityMetadata, mutation: str) -> MilestoneTopology: ...


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


@runtime_checkable
class ConcurrencyStrategy(Protocol):
    """How one transaction's concurrency mode settles a versioned write's gate
    and version arithmetic, and what a temporal observation's basis licenses
    (`m-opt-lock`).

    Every method mirrors one `m-opt-lock` policy question the planner cannot
    answer itself, because the module DAG runs `m-opt-lock --> m-unit-work`:
    which Attribute (if any) carries an entity's optimistic version, whether
    the mode renders a gate at all, the derived initial and advanced version
    values, whether a required version was actually observed, whether a row
    still authors an explicit version value, and whether a locking-mode write's
    Transaction-Time Basis licenses it. Each raises the policy's own error on
    refusal; the planner never inspects or re-raises a specific type.
    """

    def version_attribute(self, entity: EntityMetadata) -> AttributeIdentity | None: ...

    def gates(self, concurrency: Concurrency) -> bool: ...

    def initial_version(self) -> int: ...

    def advance(self, observed_version: int) -> int: ...

    def require_version(
        self, entity: EntityIdentity, observation: WriteObservation | None
    ) -> int: ...

    def reject_authored_version(
        self, entity: EntityIdentity, attribute: AttributeIdentity
    ) -> None: ...

    def check_locking_license(
        self, concurrency: Concurrency, basis: TransactionTimeBasis
    ) -> None: ...


@runtime_checkable
class AuditStrategy(Protocol):
    """How Audit Provenance decorates one finalized step.

    Decoration consumes the settled Insert Origins and Close Causes and adds
    ordinary planned values; it changes no topology, classifies no gate, and
    emits no SQL. ``subject_identity`` and ``transaction_instant`` are the
    request-scoped inputs a real provenance adapter needs — the identity to
    stamp and the shared instant to stamp it at — passed through unevaluated:
    an implementation that never resolves ``transaction_instant`` costs the
    surviving flush no clock access beyond what its own topology already
    required (`m-unit-work` "The Transaction Instant").

    Only eagerly settled steps reach this port. A Materialized Write Group's
    rows are rebuilt on demand from a segment holding no strategy object and
    no unevaluated instant, so they cannot be decorated one step at a time;
    every row of one group shares one authored mutation, one Subject Identity,
    and one instant, so a group's provenance is one overlay resolved at settle
    time rather than a per-row decoration.
    """

    def decorate(
        self,
        step: PlannedWrite,
        *,
        subject_identity: SubjectIdentity,
        transaction_instant: TransactionInstant,
    ) -> PlannedWrite: ...


@dataclass(frozen=True, slots=True)
class UndecoratedAudit:
    """The audit-neutral default: every step passes through unchanged."""

    def decorate(
        self,
        step: PlannedWrite,
        *,
        subject_identity: SubjectIdentity,
        transaction_instant: TransactionInstant,
    ) -> PlannedWrite:
        return step


NO_AUDIT: Final[UndecoratedAudit] = UndecoratedAudit()
