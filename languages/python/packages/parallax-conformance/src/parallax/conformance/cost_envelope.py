"""Versioned envelope and provenance for quantitative Python cost reports."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final, Literal, Protocol, cast

from jsonschema import Draft202012Validator

from parallax.conformance import case_format
from parallax.conformance.budget import BudgetContract

__all__ = [
    "Authority",
    "Comparison",
    "CostReportEnvelope",
    "Diagnostic",
    "Provenance",
    "Reading",
    "classify_authority",
    "validate",
]

type Authority = Literal["authoritative", "non-authoritative"]
type ComparisonOutcome = Literal["within", "outside", "unavailable"]

_SCHEMA_PATH: Final = Path("languages/python/spec/cost-report-envelope.schema.json")
_LOCK_PATH: Final = Path("languages/python/uv.lock")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return completed.stdout.strip()


def _sysctl(name: str) -> str | None:
    if sys.platform != "darwin":
        return None
    completed = subprocess.run(["sysctl", "-n", name], capture_output=True, text=True, check=False)
    value = completed.stdout.strip()
    return value or None


@dataclass(frozen=True, slots=True)
class Provenance:
    commit: str
    dirty: bool
    budget_contract_digest: str
    workload_digest: str
    lock_digest: str
    machine: str
    cpu: str
    cores: int
    ram_gib: int
    os: str
    cpython: str
    postgres: str
    sampling: Mapping[str, object]

    @classmethod
    def capture(
        cls,
        contract: BudgetContract,
        *,
        workload_digest: str,
        postgres: PostgresVersionSource,
    ) -> Provenance:
        repo = case_format.find_repo_root()
        memory = _sysctl("hw.memsize")
        if memory is not None:
            ram_gib = round(int(memory) / 1024**3)
        elif "SC_PHYS_PAGES" in os.sysconf_names and "SC_PAGE_SIZE" in os.sysconf_names:
            ram_gib = round(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 1024**3)
        else:
            ram_gib = 1
        physical_cores = _sysctl("hw.physicalcpu")
        return cls(
            commit=_git(repo, "rev-parse", "HEAD"),
            dirty=bool(_git(repo, "status", "--porcelain")),
            budget_contract_digest=contract.digest,
            workload_digest=workload_digest,
            lock_digest=_digest(repo / _LOCK_PATH),
            machine=_sysctl("hw.model") or platform.machine(),
            cpu=_sysctl("machdep.cpu.brand_string") or platform.processor() or "unknown",
            cores=int(physical_cores) if physical_cores is not None else os.cpu_count() or 1,
            ram_gib=ram_gib,
            os=platform.platform(),
            cpython=platform.python_version(),
            postgres=_postgres_version(postgres),
            sampling=contract.sampling,
        )

    def document(self) -> dict[str, object]:
        return {
            "commit": self.commit,
            "dirty": self.dirty,
            "budgetContractDigest": self.budget_contract_digest,
            "workloadDigest": self.workload_digest,
            "lockDigest": self.lock_digest,
            "machine": self.machine,
            "cpu": self.cpu,
            "cores": self.cores,
            "ramGiB": self.ram_gib,
            "os": self.os,
            "cpython": self.cpython,
            "postgres": self.postgres,
            "sampling": dict(self.sampling),
        }

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> Provenance:
        return cls(
            commit=cast("str", document["commit"]),
            dirty=cast("bool", document["dirty"]),
            budget_contract_digest=cast("str", document["budgetContractDigest"]),
            workload_digest=cast("str", document["workloadDigest"]),
            lock_digest=cast("str", document["lockDigest"]),
            machine=cast("str", document["machine"]),
            cpu=cast("str", document["cpu"]),
            cores=cast("int", document["cores"]),
            ram_gib=cast("int", document["ramGiB"]),
            os=cast("str", document["os"]),
            cpython=cast("str", document["cpython"]),
            postgres=cast("str", document["postgres"]),
            sampling=cast("Mapping[str, object]", document["sampling"]),
        )


class PostgresVersionSource(Protocol):
    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[object] = (),
    ) -> Sequence[Mapping[str, object]]: ...


def _postgres_version(source: PostgresVersionSource) -> str:
    rows = source.execute("show server_version", ())
    if len(rows) != 1 or not isinstance(rows[0].get("server_version"), str):
        raise ValueError("PostgreSQL did not report exactly one server_version")
    return cast("str", rows[0]["server_version"])


@dataclass(frozen=True, slots=True)
class Reading:
    workload: str
    cell: str
    value: float
    unit: str
    samples: tuple[float, ...] = ()


@dataclass(frozen=True, slots=True)
class Comparison:
    workload: str
    cell: str
    operator: Literal["at-most", "at-least"]
    limit: float
    unit: str
    outcome: ComparisonOutcome


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class CostReportEnvelope:
    subject: str
    provenance: Provenance
    authority: Authority
    readings: tuple[Reading, ...] = ()
    comparisons: tuple[Comparison, ...] = ()
    incomplete: tuple[Diagnostic, ...] = ()
    errors: tuple[Diagnostic, ...] = ()
    schema_version: int = 1

    def document(self) -> dict[str, object]:
        return {
            "schemaVersion": self.schema_version,
            "subject": self.subject,
            "provenance": self.provenance.document(),
            "authority": self.authority,
            "readings": [
                {**asdict(reading), "samples": list(reading.samples)} for reading in self.readings
            ],
            "comparisons": [asdict(comparison) for comparison in self.comparisons],
            "incomplete": [asdict(diagnostic) for diagnostic in self.incomplete],
            "errors": [asdict(diagnostic) for diagnostic in self.errors],
        }


def classify_authority(provenance: Provenance, contract: BudgetContract) -> Authority:
    expected = contract.authority
    matched = (
        not provenance.dirty
        and provenance.commit != ""
        and provenance.budget_contract_digest == contract.digest
        and provenance.machine == expected.get("machine")
        and provenance.cpu == expected.get("cpu")
        and provenance.cores == expected.get("cores")
        and provenance.ram_gib == expected.get("ramGiB")
        and provenance.cpython == expected.get("cpython")
        and provenance.postgres == expected.get("postgres")
        and provenance.sampling == contract.sampling
    )
    return "authoritative" if matched else "non-authoritative"


def validate(envelope: CostReportEnvelope | Mapping[str, object]) -> None:
    repo = case_format.find_repo_root()
    schema = cast(
        "Mapping[str, object]", json.loads((repo / _SCHEMA_PATH).read_text(encoding="utf-8"))
    )
    document = envelope.document() if isinstance(envelope, CostReportEnvelope) else dict(envelope)
    validator = cast("Any", Draft202012Validator(schema))
    validator.validate(document)
    provenance_document = cast("Mapping[str, object]", document["provenance"])
    provenance = Provenance.from_document(provenance_document)
    try:
        _git(repo, "cat-file", "-e", f"{provenance.commit}^{{commit}}")
    except subprocess.CalledProcessError as error:
        raise ValueError(f"provenance commit {provenance.commit!r} is not a commit") from error
    expected = classify_authority(provenance, BudgetContract.load())
    if document["authority"] != expected:
        raise ValueError(
            f"authority {document['authority']!r} disagrees with provenance "
            f"classification {expected!r}"
        )
