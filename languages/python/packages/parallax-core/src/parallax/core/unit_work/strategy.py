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
from typing import Final, Protocol, runtime_checkable

from parallax.core.metamodel import EntityMetadata, Metamodel, TemporalDimension
from parallax.core.unit_work.planned import CloseCause, PlannedWrite
from parallax.core.unit_work.uow import Concurrency

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
    "ConcurrencyStrategy",
    "MilestoneClosure",
    "MilestoneSuccessor",
    "MilestoneTopology",
    "OpenEnd",
    "PredecessorEnd",
    "PredecessorStart",
    "SuccessorState",
    "TemporalStrategy",
    "UndecoratedAudit",
    "ValidTimeBound",
    "ValidTimeWindow",
]


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
    """How one temporal facet describes an authored mutation's topology."""

    def topology(self, mutation: str) -> MilestoneTopology: ...


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
    """Whether a transaction's mode renders gates (`m-opt-lock`)."""

    def gates(self, concurrency: Concurrency) -> bool: ...


@runtime_checkable
class AuditStrategy(Protocol):
    """How Audit Provenance decorates one finalized step.

    Decoration consumes the settled Insert Origins and Close Causes and adds
    ordinary planned values; it changes no topology, classifies no gate, and
    emits no SQL.
    """

    def decorate(self, step: PlannedWrite) -> PlannedWrite: ...


@dataclass(frozen=True, slots=True)
class UndecoratedAudit:
    """The audit-neutral default: every step passes through unchanged."""

    def decorate(self, step: PlannedWrite) -> PlannedWrite:
        return step


NO_AUDIT: Final[UndecoratedAudit] = UndecoratedAudit()
