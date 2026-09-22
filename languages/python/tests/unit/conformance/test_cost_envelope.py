from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import cast

import pytest

import cost_report
from parallax.conformance import case_format
from parallax.conformance.budget import BudgetContract
from parallax.conformance.cost_envelope import (
    Comparison,
    CostReportEnvelope,
    Diagnostic,
    Provenance,
    Reading,
    classify_authority,
    validate,
)


class _VersionSource:
    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[object] = (),
    ) -> list[Mapping[str, object]]:
        assert (sql, binds, document_reads) == ("show server_version", (), ())
        return [{"server_version": "18.6"}]


class _MissingVersionSource:
    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[object] = ()
    ) -> list[Mapping[str, object]]:
        return []


def _provenance(contract: BudgetContract, *, dirty: bool = False) -> Provenance:
    authority = contract.authority
    cores = authority["cores"]
    ram_gib = authority["ramGiB"]
    assert isinstance(cores, int)
    assert isinstance(ram_gib, int)
    repo = case_format.find_repo_root()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return Provenance(
        commit=commit,
        dirty=dirty,
        budget_contract_digest=contract.digest,
        budget_contract=contract.authored.decode("utf-8"),
        workload_digest="b" * 64,
        lock_digest="c" * 64,
        machine=str(authority["machine"]),
        cpu=str(authority["cpu"]),
        cores=cores,
        ram_gib=ram_gib,
        os="recorded but not matched",
        cpython=str(authority["cpython"]),
        postgres=str(authority["postgres"]),
        sampling=contract.sampling,
    )


def test_envelope_round_trips_through_its_schema() -> None:
    contract = BudgetContract.load()
    provenance = _provenance(contract)
    envelope = CostReportEnvelope(
        "snapshot-delivery",
        provenance,
        classify_authority(provenance, contract),
        readings=(Reading("conventional-fanout", "live.page32", 18.9, "ms", (18.9,)),),
        comparisons=(
            Comparison("conventional-fanout", "live.page32", "at-most", 20, "ms", "within"),
        ),
        incomplete=(Diagnostic("cell-unavailable", "one optional cell was unavailable"),),
    )
    validate(envelope)
    assert envelope.document()["authority"] == "authoritative"
    assert envelope.document()["schemaVersion"] == 2


def test_validation_uses_the_embedded_contract_not_the_checkout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = BudgetContract.load()
    provenance = _provenance(contract)
    envelope = CostReportEnvelope(
        "snapshot-delivery",
        provenance,
        classify_authority(provenance, contract),
    )
    current_checkout_contract = replace(contract, digest="0" * 64)

    def load_current_checkout_contract() -> BudgetContract:
        return current_checkout_contract

    monkeypatch.setattr(BudgetContract, "load", staticmethod(load_current_checkout_contract))
    validate(envelope)


# The retained captures name producing commits no fresh clone need contain.
# Validating every committed member while any subprocess is refused pins that an
# envelope's authority is classified from the envelope alone, never from history.
def test_validation_of_committed_evidence_asks_git_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    members = [
        member
        for capture in ("recovered", "before", "after")
        for member in cast(
            "Sequence[Mapping[str, object]]",
            json.loads(
                (cost_report.EVIDENCE_DIRECTORY / capture / "portfolio.json").read_text(
                    encoding="utf-8"
                )
            )["members"],
        )
    ]

    def refuse(command: Sequence[str], **_: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError(f"validation ran {list(command)}")

    monkeypatch.setattr(subprocess, "run", refuse)
    for member in members:
        validate(member)


def test_dirty_or_os_different_runs_are_classified_from_the_fingerprint_only() -> None:
    contract = BudgetContract.load()
    clean = _provenance(contract)
    assert classify_authority(clean, contract) == "authoritative"
    assert classify_authority(_provenance(contract, dirty=True), contract) == "non-authoritative"


def test_provenance_capture_records_the_current_host() -> None:
    contract = BudgetContract.load()
    captured = Provenance.capture(contract, workload_digest="d" * 64, postgres=_VersionSource())
    assert captured.commit
    assert captured.ram_gib >= 1
    assert captured.os
    assert captured.postgres == "18.6"
    with pytest.raises(ValueError, match="exactly one server_version"):
        Provenance.capture(contract, workload_digest="d" * 64, postgres=_MissingVersionSource())


def test_provenance_capture_retains_a_members_own_sampling_protocol() -> None:
    contract = BudgetContract.load()
    sampling = {"timing": {"measuredPairs": 2}}
    captured = Provenance.capture(
        contract,
        workload_digest="d" * 64,
        postgres=_VersionSource(),
        sampling=sampling,
    )
    assert captured.sampling == sampling
    assert classify_authority(captured, contract) == "non-authoritative"


def test_semantic_validation_recomputes_authority_and_checks_the_embedded_contract() -> None:
    contract = BudgetContract.load()
    envelope = CostReportEnvelope(
        "snapshot-delivery", _provenance(contract, dirty=True), "authoritative"
    )
    with pytest.raises(ValueError, match="disagrees with provenance classification"):
        validate(envelope)
    document = CostReportEnvelope(
        "snapshot-delivery", _provenance(contract), "authoritative"
    ).document()
    provenance_document = cast("Mapping[str, object]", document["provenance"])
    edited = dict(provenance_document)
    edited["budgetContract"] = f"{edited['budgetContract']}\n# edited"
    document["provenance"] = edited
    with pytest.raises(ValueError, match="does not hash to budgetContractDigest"):
        validate(document)
    unresolvable = dict(provenance_document)
    unresolvable["commit"] = "f" * 40
    document["provenance"] = unresolvable
    validate(document)


def test_provenance_capture_has_portable_memory_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = BudgetContract.load()
    monkeypatch.setattr(sys, "platform", "test-platform")
    monkeypatch.setattr(os, "sysconf_names", {})
    fallback = Provenance.capture(contract, workload_digest="d" * 64, postgres=_VersionSource())
    assert fallback.ram_gib == 1

    monkeypatch.setattr(os, "sysconf_names", {"SC_PHYS_PAGES": 1, "SC_PAGE_SIZE": 2})

    def one_mib(_name: str | int) -> int:
        return 1024**2

    monkeypatch.setattr(os, "sysconf", one_mib)
    measured = Provenance.capture(contract, workload_digest="d" * 64, postgres=_VersionSource())
    assert measured.ram_gib == 1024


def test_provenance_capture_reads_the_darwin_fingerprint_through_sysctl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = BudgetContract.load()
    answers = {
        "hw.memsize": str(48 * 1024**3),
        "hw.physicalcpu": "10",
        "hw.model": "Mac17,4",
        "machdep.cpu.brand_string": "Apple M5",
    }

    def sysctl(command: Sequence[str], **_: object) -> subprocess.CompletedProcess[str]:
        assert command[:2] == ["sysctl", "-n"]
        return subprocess.CompletedProcess(list(command), 0, answers.get(command[2], ""), "")

    monkeypatch.setattr(sys, "platform", "darwin")
    captured_git = {"rev-parse": "a" * 40, "status": ""}

    def git(command: Sequence[str], **_: object) -> subprocess.CompletedProcess[str]:
        if command[0] == "git":
            return subprocess.CompletedProcess(list(command), 0, captured_git[command[1]], "")
        return sysctl(command)

    monkeypatch.setattr(subprocess, "run", git)
    provenance = Provenance.capture(contract, workload_digest="d" * 64, postgres=_VersionSource())

    assert provenance.ram_gib == 48
    assert provenance.cores == 10
    assert provenance.machine == "Mac17,4"
    assert provenance.cpu == "Apple M5"


def test_a_reading_states_its_window_and_runtime_only_when_it_has_them() -> None:
    bare = Reading("w", "c", 1.0, "ms", (1.0,))
    labeled = Reading("w", "c", 1.0, "ms", (1.0,), window="live-delivery", runtime="3.14")
    assert bare.document() == {
        "workload": "w",
        "cell": "c",
        "value": 1.0,
        "unit": "ms",
        "samples": [1.0],
    }
    assert labeled.document() == {**bare.document(), "window": "live-delivery", "runtime": "3.14"}
    contract = BudgetContract.load()
    provenance = _provenance(contract)
    envelope = CostReportEnvelope(
        "snapshot-delivery",
        provenance,
        classify_authority(provenance, contract),
        readings=(bare, labeled),
    )
    validate(envelope)
    assert envelope.document()["readings"] == [bare.document(), labeled.document()]
