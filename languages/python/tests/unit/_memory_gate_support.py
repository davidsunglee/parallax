"""Which cost-class item owns each memory gate.

`spec/memory-gates.yaml` states one blocking ceiling per byte-unit reading
address of the structural windows. A ceiling blocks only through a test the
cost class collects and CI runs, so every gate is assigned here to exactly one
such item, by module and function name, and ``test_memory_gate_ownership.py``
grades that each named item is collected in the cost class and that the
assignments partition the gates. Registration of a report member establishes no
ownership; this table does.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from parallax.conformance.budget import MemoryGate, MemoryGates, ScalingDomain

__all__ = ["OWNERS", "GateOwner", "owner_of", "unowned_gates"]

WRITE_SUBJECT: Final = "write-lowering"
SNAPSHOT_SUBJECT: Final = "snapshot-delivery"
WRITE_MODULE: Final = "tests/unit/tools/test_write_lowering_reading_gates.py"
SNAPSHOT_MODULE: Final = "tests/unit/tools/test_snapshot_delivery_reading_gates.py"


@dataclass(frozen=True, slots=True)
class GateOwner:
    """One cost-class item and the gate addresses it grades."""

    module: str
    test: str
    subject: str
    selects: Callable[[str], bool]

    @property
    def nodeid(self) -> str:
        return f"{self.module}::{self.test}"

    def gates(self, gates: MemoryGates | None = None) -> tuple[MemoryGate, ...]:
        active = gates or MemoryGates.load()
        return tuple(
            gate for gate in active.subject_gates(self.subject) if self.selects(gate.workload)
        )

    def workloads(self, gates: MemoryGates | None = None) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for gate in self.gates(gates):
            seen.setdefault(gate.workload, None)
        return tuple(seen)

    def scaling(self, gates: MemoryGates | None = None) -> tuple[ScalingDomain, ...]:
        active = gates or MemoryGates.load()
        return tuple(
            domain
            for domain in active.scaling
            if domain.subject == self.subject and all(map(self.selects, domain.ordered))
        )


def _prefixed(*prefixes: str) -> Callable[[str], bool]:
    return lambda workload: workload.startswith(prefixes)


def _exactly(*names: str) -> Callable[[str], bool]:
    return lambda workload: workload in names


OWNERS: Final[tuple[GateOwner, ...]] = (
    GateOwner(
        WRITE_MODULE,
        "test_the_categorical_keyed_writes_stay_within_their_memory_gates",
        WRITE_SUBJECT,
        _prefixed("txtime.", "plain.", "bitemporal."),
    ),
    GateOwner(
        WRITE_MODULE,
        "test_the_geometry_inserts_stay_within_their_memory_gates",
        WRITE_SUBJECT,
        _prefixed("geometry."),
    ),
    GateOwner(
        WRITE_MODULE,
        "test_the_changed_ancestor_successors_stay_within_their_memory_gates",
        WRITE_SUBJECT,
        _prefixed("ancestor."),
    ),
    GateOwner(
        WRITE_MODULE,
        "test_predicate_acquisition_stays_within_its_gates_and_amortizes_over_rows",
        WRITE_SUBJECT,
        _prefixed("acquisition."),
    ),
    GateOwner(
        WRITE_MODULE,
        "test_the_prepared_model_stays_within_its_memory_gates",
        WRITE_SUBJECT,
        _exactly("model.prepared", "model.prepared.family"),
    ),
    GateOwner(
        SNAPSHOT_MODULE,
        "test_the_depth_reads_stay_within_their_memory_gates",
        SNAPSHOT_SUBJECT,
        _prefixed("read-depth-"),
    ),
    GateOwner(
        SNAPSHOT_MODULE,
        "test_the_many_reads_stay_within_their_memory_gates",
        SNAPSHOT_SUBJECT,
        _prefixed("read-many-"),
    ),
    GateOwner(
        SNAPSHOT_MODULE,
        "test_the_width_and_sparse_reads_stay_within_their_memory_gates",
        SNAPSHOT_SUBJECT,
        _prefixed("read-width-", "read-sparse-"),
    ),
    GateOwner(
        SNAPSHOT_MODULE,
        "test_the_cold_read_plans_stay_within_their_memory_gates",
        SNAPSHOT_SUBJECT,
        _prefixed("plan-", "control-guarded-"),
    ),
)
"""Every memory-gate owner. Together they claim each gate exactly once, which
``test_memory_gate_ownership.py`` grades against the loaded gates."""


def owner_of(test: Callable[[], None]) -> GateOwner:
    """The owner row a gate test grades, found by the test's own name."""
    for owner in OWNERS:
        if owner.test == test.__name__:
            return owner
    raise KeyError(f"{test.__name__!r} owns no memory gates: {[owner.test for owner in OWNERS]}")


def unowned_gates(gates: MemoryGates | None = None) -> tuple[MemoryGate, ...]:
    """Every gate no owner claims, and every gate two owners claim, in one
    tuple: an empty answer is what makes the ownership table a partition."""
    active = gates or MemoryGates.load()
    claims: dict[tuple[str, str, str], int] = dict.fromkeys(active.addresses, 0)
    for owner in OWNERS:
        for gate in owner.gates(active):
            claims[(gate.subject, gate.workload, gate.cell)] += 1
    return tuple(
        gate for gate in active.gates if claims[(gate.subject, gate.workload, gate.cell)] != 1
    )
