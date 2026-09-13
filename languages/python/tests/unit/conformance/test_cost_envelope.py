from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import cast

import pytest

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


def test_validation_uses_the_producing_commits_contract(
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


def test_semantic_validation_recomputes_authority_and_requires_a_commit() -> None:
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
    provenance = dict(provenance_document)
    provenance["commit"] = "f" * 40
    document["provenance"] = provenance
    with pytest.raises(ValueError, match="is not a commit"):
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
