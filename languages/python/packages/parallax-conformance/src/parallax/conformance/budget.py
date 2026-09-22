"""Machine-readable Python Snapshot delivery budget contract, and the memory
gates the cost class blocks on.

The Budget Contract prices Snapshot delivery: its ceilings are compared by the
report and reported as advisories. The memory gates are the other half of the
measurement contract: one blocking ceiling per byte-unit reading address of the
structural read and write windows, derived from the retained capture they name
as their basis by one stated rule and graded by cost-class tests. Both are loaded
here and transcribed nowhere.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Final, cast

from parallax.conformance import case_format

__all__ = [
    "BYTE_UNITS",
    "GATED_WINDOWS",
    "BudgetCell",
    "BudgetContract",
    "MemoryGate",
    "MemoryGates",
    "ScalingDomain",
    "derive_memory_gates",
    "memory_ceiling",
    "reading_bytes",
]

_CONTRACT_PATH: Final = Path("languages/python/spec/budget-contract.yaml")
_GATES_PATH: Final = Path("languages/python/spec/memory-gates.yaml")

BYTE_UNITS: Final = frozenset({"B", "B/row", "KiB"})
"""The reading units a memory gate is stated over: bytes, bytes per row, and
kibibytes, each converted to bytes by :func:`reading_bytes`."""

GATED_WINDOWS: Final = frozenset(
    {
        "keyed-write",
        "predicate-acquisition",
        "model-preparation",
        "provider-free-delivery",
        "read-plan-compilation",
    }
)
"""The structural windows whose byte-unit readings the gates cover."""


@dataclass(frozen=True, slots=True)
class BudgetCell:
    """One numeric threshold addressed within one workload."""

    workload: str
    path: str
    value: int | float


@dataclass(frozen=True, slots=True)
class BudgetContract:
    """The parsed Budget Contract beside the authored bytes ``digest`` hashes.

    ``authored`` is retained so a consumer that must record what the contract
    said can copy the exact bytes rather than re-read the file.
    """

    path: Path
    schema_version: int
    authority: Mapping[str, object]
    sampling: Mapping[str, object]
    workloads: Mapping[str, Mapping[str, object]]
    digest: str
    authored: bytes

    @classmethod
    @cache
    def load(cls, path: Path | None = None) -> BudgetContract:
        resolved = (path or case_format.find_repo_root() / _CONTRACT_PATH).resolve()
        return cls.from_bytes(resolved, resolved.read_bytes())

    @classmethod
    def from_bytes(cls, path: Path, authored: bytes) -> BudgetContract:
        """Parse authored contract bytes while retaining their repository path."""
        resolved = path.resolve()
        loaded = case_format.safe_load_yaml(authored.decode("utf-8"))
        if not isinstance(loaded, Mapping):
            raise ValueError(f"{resolved}: Budget Contract is not a mapping")
        document = cast("Mapping[str, object]", loaded)
        version = document.get("schemaVersion")
        authority = document.get("authority")
        sampling = document.get("sampling")
        workloads = document.get("workloads")
        if version != 1:
            raise ValueError(f"{resolved}: unsupported schemaVersion {version!r}")
        if not isinstance(authority, Mapping):
            raise ValueError(f"{resolved}: authority is not a mapping")
        if not isinstance(sampling, Mapping):
            raise ValueError(f"{resolved}: sampling is not a mapping")
        if not isinstance(workloads, Mapping) or not workloads:
            raise ValueError(f"{resolved}: workloads is not a non-empty mapping")
        typed_authority = cast("Mapping[str, object]", authority)
        typed_sampling = cast("Mapping[str, object]", sampling)
        typed_workloads: dict[str, Mapping[str, object]] = {}
        for workload_id, definition in cast("Mapping[object, object]", workloads).items():
            if not isinstance(workload_id, str) or not isinstance(definition, Mapping):
                raise ValueError(f"{resolved}: every workload is a named mapping")
            typed_definition = cast("Mapping[str, object]", definition)
            typed_workloads[workload_id] = MappingProxyType(dict(typed_definition))
        return cls(
            resolved,
            1,
            MappingProxyType(dict(typed_authority)),
            MappingProxyType(dict(typed_sampling)),
            MappingProxyType(typed_workloads),
            hashlib.sha256(authored).hexdigest(),
            authored,
        )

    @property
    def workload_ids(self) -> tuple[str, ...]:
        return tuple(self.workloads)

    @property
    def timing_warmups(self) -> int:
        return self._sampling_count("timing", "warmups")

    @property
    def timing_measured(self) -> int:
        return self._sampling_count("timing", "measured")

    @property
    def memory_children(self) -> int:
        return self._sampling_count("memory", "children")

    @property
    def memory_collect_at_page_boundary(self) -> bool:
        value = self._sampling_group("memory").get("collectAtPageBoundary")
        if not isinstance(value, bool):
            raise ValueError("sampling.memory.collectAtPageBoundary is not a boolean")
        return value

    @property
    def memory_scaling_arms(self) -> tuple[int, ...]:
        memory = self._sampling_group("memory")
        arms = memory.get("scalingArms")
        if not isinstance(arms, Sequence) or isinstance(arms, str | bytes):
            raise ValueError("sampling.memory.scalingArms is not a sequence")
        counts = tuple(
            self._positive_int(value, "sampling.memory.scalingArms")
            for value in cast("Sequence[object]", arms)
        )
        if len(counts) < 2 or len(set(counts)) != len(counts):
            raise ValueError("sampling.memory.scalingArms must contain distinct scaling counts")
        return counts

    def _sampling_count(self, group: str, name: str) -> int:
        return self._positive_int(self._sampling_group(group).get(name), f"sampling.{group}.{name}")

    def _sampling_group(self, name: str) -> Mapping[str, object]:
        group = self.sampling.get(name)
        if not isinstance(group, Mapping):
            raise ValueError(f"sampling.{name} is not a mapping")
        return cast("Mapping[str, object]", group)

    @staticmethod
    def _positive_int(value: object, address: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{address} is not a positive integer")
        return value

    def fixture(self, workload: str) -> Path:
        definition = self.workloads[workload]
        fixture = definition.get("fixture")
        if not isinstance(fixture, str):
            raise ValueError(f"{workload}: fixture is not a string")
        return self.path.parents[3] / "core" / "compatibility" / fixture

    def cells(self, workload: str) -> tuple[BudgetCell, ...]:
        definition = self.workloads[workload]
        cells = definition.get("cells")
        if not isinstance(cells, Mapping):
            raise ValueError(f"{workload}: cells is not a mapping")
        return tuple(self._walk_cells(workload, cast("Mapping[str, object]", cells)))

    @classmethod
    def _walk_cells(
        cls, workload: str, values: Mapping[str, object], prefix: str = ""
    ) -> Iterator[BudgetCell]:
        for name, value in values.items():
            path = f"{prefix}.{name}" if prefix else name
            if isinstance(value, Mapping):
                yield from cls._walk_cells(workload, cast("Mapping[str, object]", value), path)
            elif isinstance(value, int | float) and not isinstance(value, bool):
                yield BudgetCell(workload, path, value)
            else:
                raise ValueError(f"{workload}.{path}: a budget cell must be numeric")


def reading_bytes(value: float, unit: str) -> float:
    """The byte magnitude of one reading stated in ``unit``, per the unit's own
    denominator: a ``B/row`` reading stays per row."""
    if unit not in BYTE_UNITS:
        raise ValueError(f"{unit!r} is not a byte unit; gates are stated over {sorted(BYTE_UNITS)}")
    return value * 1_024 if unit == "KiB" else value


def memory_ceiling(values: Iterable[float], unit: str, headroom: float) -> int:
    """The gate one address's basis readings support: the largest reading on
    any runtime, scaled by ``headroom`` and rounded up to a whole byte. The
    product is settled to a millionth of a byte first, so a binary fraction of
    the factor cannot round a whole-byte product up to the next byte."""
    largest = max(values)
    return math.ceil(round(reading_bytes(largest, unit) * headroom, 6))


@dataclass(frozen=True, slots=True)
class MemoryGate:
    """One blocking ceiling over one measured address, in bytes per the
    reading's own unit denominator."""

    subject: str
    workload: str
    cell: str
    unit: str
    max_bytes: int

    def within(self, value: float) -> bool:
        """Whether a reading of ``value`` in this gate's unit stays under it."""
        return reading_bytes(value, self.unit) <= self.max_bytes


@dataclass(frozen=True, slots=True)
class ScalingDomain:
    """Workloads ordered by scale whose per-unit readings must not grow with it."""

    name: str
    subject: str
    ordered: tuple[str, ...]
    non_increasing: tuple[str, ...]


type GatesDocument = dict[str, dict[str, dict[str, dict[str, object]]]]
"""``gates`` as authored: subject, then workload, then cell, then ``unit`` and
``maxBytes``."""


def _gate_readings(portfolio: Mapping[str, object]) -> Iterator[tuple[str, str, str, str, float]]:
    """Every byte-unit reading of a gated window in ``portfolio``'s members, as
    ``(subject, workload, cell, unit, value)``."""
    for member in cast("Sequence[Mapping[str, object]]", portfolio.get("members", ())):
        subject = str(member.get("subject"))
        for reading in cast("Sequence[Mapping[str, object]]", member.get("readings", ())):
            unit = str(reading.get("unit"))
            if unit not in BYTE_UNITS or reading.get("window") not in GATED_WINDOWS:
                continue
            value = reading["value"]
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise TypeError(f"{subject} reading value is not a number: {value!r}")
            yield subject, str(reading["workload"]), str(reading["cell"]), unit, float(value)


def derive_memory_gates(portfolio: Mapping[str, object], headroom: float) -> GatesDocument:
    """The ``gates`` block a portfolio supports under the derivation rule.

    Every byte-unit reading of a gated window becomes one gate at its
    ``(subject, workload, cell)`` address; readings of one address on several
    runtimes share it, and the ceiling is :func:`memory_ceiling` over them. A
    unit that differs between runtimes at one address is a malformed portfolio.
    """
    values: dict[tuple[str, str, str], list[float]] = {}
    units: dict[tuple[str, str, str], str] = {}
    for subject, workload, cell, unit, value in _gate_readings(portfolio):
        address = (subject, workload, cell)
        if units.setdefault(address, unit) != unit:
            raise ValueError(f"{subject} {workload}.{cell} is read in more than one unit")
        values.setdefault(address, []).append(value)
    derived: GatesDocument = {}
    for address in sorted(values):
        subject, workload, cell = address
        unit = units[address]
        derived.setdefault(subject, {}).setdefault(workload, {})[cell] = {
            "unit": unit,
            "maxBytes": memory_ceiling(values[address], unit, headroom),
        }
    return derived


@dataclass(frozen=True, slots=True)
class MemoryGates:
    """The parsed memory gates and the digest of their authored bytes.

    ``basis_portfolio`` is the repository-relative capture every gate was
    derived from and ``headroom`` the factor applied to its largest reading;
    :func:`derive_memory_gates` over that capture is what the authored
    ``gates`` block must equal. ``advisory`` carries the allowances the
    advisory comparisons read timing and byte deltas against, which never gate.
    """

    path: Path
    schema_version: int
    basis_portfolio: Path
    headroom: float
    advisory: Mapping[str, float]
    gates: tuple[MemoryGate, ...]
    scaling: tuple[ScalingDomain, ...]
    digest: str

    @classmethod
    @cache
    def load(cls, path: Path | None = None) -> MemoryGates:
        resolved = (path or case_format.find_repo_root() / _GATES_PATH).resolve()
        return cls.from_bytes(resolved, resolved.read_bytes())

    @classmethod
    def from_bytes(cls, path: Path, authored: bytes) -> MemoryGates:
        """Parse authored gate bytes while retaining their repository path."""
        resolved = path.resolve()
        loaded = case_format.safe_load_yaml(authored.decode("utf-8"))
        if not isinstance(loaded, Mapping):
            raise ValueError(f"{resolved}: memory gates are not a mapping")
        document = cast("Mapping[str, object]", loaded)
        if document.get("schemaVersion") != 1:
            raise ValueError(
                f"{resolved}: unsupported schemaVersion {document.get('schemaVersion')!r}"
            )
        basis = document.get("basis")
        if not isinstance(basis, Mapping):
            raise ValueError(f"{resolved}: basis is not a mapping")
        typed_basis = cast("Mapping[str, object]", basis)
        portfolio = typed_basis.get("portfolio")
        headroom = typed_basis.get("headroom")
        if not isinstance(portfolio, str):
            raise ValueError(f"{resolved}: basis.portfolio is not a path")
        if isinstance(headroom, bool) or not isinstance(headroom, int | float) or headroom < 1:
            raise ValueError(f"{resolved}: basis.headroom is not a factor of at least 1")
        advisory = document.get("advisory")
        if not isinstance(advisory, Mapping):
            raise ValueError(f"{resolved}: advisory is not a mapping")
        typed_advisory: dict[str, float] = {}
        for name, value in cast("Mapping[object, object]", advisory).items():
            if (
                not isinstance(name, str)
                or isinstance(value, bool)
                or not isinstance(value, int | float)
            ):
                raise ValueError(f"{resolved}: every advisory allowance is a named number")
            typed_advisory[name] = float(value)
        gates = document.get("gates")
        if not isinstance(gates, Mapping) or not gates:
            raise ValueError(f"{resolved}: gates is not a non-empty mapping")
        return cls(
            resolved,
            1,
            Path(portfolio),
            float(headroom),
            MappingProxyType(typed_advisory),
            tuple(cls._walk_gates(resolved, cast("Mapping[object, object]", gates))),
            tuple(cls._walk_scaling(resolved, document.get("scaling"))),
            hashlib.sha256(authored).hexdigest(),
        )

    @staticmethod
    def _walk_gates(resolved: Path, gates: Mapping[object, object]) -> Iterator[MemoryGate]:
        for subject, workloads in gates.items():
            if not isinstance(subject, str) or not isinstance(workloads, Mapping):
                raise ValueError(f"{resolved}: every gated subject is a named mapping")
            for workload, cells in cast("Mapping[object, object]", workloads).items():
                if not isinstance(workload, str) or not isinstance(cells, Mapping):
                    raise ValueError(
                        f"{resolved}: {subject}: every gated workload is a named mapping"
                    )
                for cell, gate in cast("Mapping[object, object]", cells).items():
                    if not isinstance(cell, str) or not isinstance(gate, Mapping):
                        raise ValueError(
                            f"{resolved}: {subject} {workload}: every gate is a named mapping"
                        )
                    typed_gate = cast("Mapping[str, object]", gate)
                    unit = typed_gate.get("unit")
                    max_bytes = typed_gate.get("maxBytes")
                    if not isinstance(unit, str) or unit not in BYTE_UNITS:
                        raise ValueError(
                            f"{resolved}: {subject} {workload}.{cell}: unit is not a byte unit"
                        )
                    if (
                        isinstance(max_bytes, bool)
                        or not isinstance(max_bytes, int)
                        or max_bytes <= 0
                    ):
                        raise ValueError(
                            f"{resolved}: {subject} {workload}.{cell}: "
                            "maxBytes is not a positive integer"
                        )
                    yield MemoryGate(subject, workload, cell, unit, max_bytes)

    @staticmethod
    def _walk_scaling(resolved: Path, scaling: object) -> Iterator[ScalingDomain]:
        if scaling is None:
            return
        if not isinstance(scaling, Mapping):
            raise ValueError(f"{resolved}: scaling is not a mapping")
        for name, domain in cast("Mapping[object, object]", scaling).items():
            if not isinstance(name, str) or not isinstance(domain, Mapping):
                raise ValueError(f"{resolved}: every scaling domain is a named mapping")
            typed_domain = cast("Mapping[str, object]", domain)
            subject = typed_domain.get("subject")
            ordered = typed_domain.get("ordered")
            non_increasing = typed_domain.get("nonIncreasing")
            if not isinstance(subject, str):
                raise ValueError(f"{resolved}: scaling {name}: subject is not a string")
            yield ScalingDomain(
                name,
                subject,
                MemoryGates._names(resolved, name, "ordered", ordered, fewest=2),
                MemoryGates._names(resolved, name, "nonIncreasing", non_increasing, fewest=1),
            )

    @staticmethod
    def _names(
        resolved: Path, domain: str, field_name: str, value: object, *, fewest: int
    ) -> tuple[str, ...]:
        if isinstance(value, Sequence) and not isinstance(value, str | bytes):
            names = tuple(cast("Sequence[object]", value))
            if len(names) >= fewest and all(isinstance(name, str) for name in names):
                return cast("tuple[str, ...]", names)
        raise ValueError(
            f"{resolved}: scaling {domain}: {field_name} names fewer than {fewest} cells"
        )

    @property
    def addresses(self) -> tuple[tuple[str, str, str], ...]:
        return tuple((gate.subject, gate.workload, gate.cell) for gate in self.gates)

    def gate(self, subject: str, workload: str, cell: str) -> MemoryGate:
        for gate in self.gates:
            if (gate.subject, gate.workload, gate.cell) == (subject, workload, cell):
                return gate
        raise KeyError(f"no memory gate at {subject} {workload}.{cell}")

    def subject_gates(self, subject: str) -> tuple[MemoryGate, ...]:
        return tuple(gate for gate in self.gates if gate.subject == subject)

    def workload_gates(self, subject: str, workload: str) -> tuple[MemoryGate, ...]:
        return tuple(
            gate for gate in self.gates if gate.subject == subject and gate.workload == workload
        )

    def document(self) -> GatesDocument:
        """The authored ``gates`` block, for comparison with a derivation."""
        rendered: GatesDocument = {}
        for gate in self.gates:
            rendered.setdefault(gate.subject, {}).setdefault(gate.workload, {})[gate.cell] = {
                "unit": gate.unit,
                "maxBytes": gate.max_bytes,
            }
        return rendered
