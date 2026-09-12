"""Machine-readable Python Snapshot delivery budget contract."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import MappingProxyType
from typing import Final, cast

from parallax.conformance import case_format

__all__ = ["BudgetCell", "BudgetContract"]

_CONTRACT_PATH: Final = Path("languages/python/spec/budget-contract.yaml")


@dataclass(frozen=True, slots=True)
class BudgetCell:
    """One numeric threshold addressed within one workload."""

    workload: str
    path: str
    value: int | float


@dataclass(frozen=True, slots=True)
class BudgetContract:
    """The parsed Budget Contract and the digest of its authored bytes."""

    path: Path
    schema_version: int
    authority: Mapping[str, object]
    sampling: Mapping[str, object]
    workloads: Mapping[str, Mapping[str, object]]
    digest: str

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
        )

    @property
    def workload_ids(self) -> tuple[str, ...]:
        return tuple(self.workloads)

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
