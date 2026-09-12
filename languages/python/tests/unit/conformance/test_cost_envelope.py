from __future__ import annotations

import os
import sys

import pytest

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


def _provenance(contract: BudgetContract, *, dirty: bool = False) -> Provenance:
    authority = contract.authority
    cores = authority["cores"]
    ram_gib = authority["ramGiB"]
    assert isinstance(cores, int)
    assert isinstance(ram_gib, int)
    return Provenance(
        commit="a" * 40,
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
        comparisons=(Comparison("conventional-fanout", "live.page32", 20, "within"),),
        incomplete=(Diagnostic("cell-unavailable", "one optional cell was unavailable"),),
    )
    validate(envelope)
    assert envelope.document()["authority"] == "authoritative"


def test_dirty_or_os_different_runs_are_classified_from_the_fingerprint_only() -> None:
    contract = BudgetContract.load()
    clean = _provenance(contract)
    assert classify_authority(clean, contract) == "authoritative"
    assert classify_authority(_provenance(contract, dirty=True), contract) == "non-authoritative"


def test_provenance_capture_records_the_current_host() -> None:
    contract = BudgetContract.load()
    captured = Provenance.capture(contract, workload_digest="d" * 64, postgres="18.6")
    assert captured.commit
    assert captured.ram_gib >= 1
    assert captured.os


def test_provenance_capture_has_portable_memory_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = BudgetContract.load()
    monkeypatch.setattr(sys, "platform", "test-platform")
    monkeypatch.setattr(os, "sysconf_names", {})
    fallback = Provenance.capture(contract, workload_digest="d" * 64, postgres="18.6")
    assert fallback.ram_gib == 1

    monkeypatch.setattr(os, "sysconf_names", {"SC_PHYS_PAGES": 1, "SC_PAGE_SIZE": 2})

    def one_mib(_name: str | int) -> int:
        return 1024**2

    monkeypatch.setattr(os, "sysconf", one_mib)
    measured = Provenance.capture(contract, workload_digest="d" * 64, postgres="18.6")
    assert measured.ram_gib == 1024
