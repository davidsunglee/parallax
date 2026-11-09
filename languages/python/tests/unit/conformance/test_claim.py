"""Canonical claim (`parallax.conformance.claim`) tests."""

from __future__ import annotations

import psycopg
import pytest

from parallax.conformance import adapter, case_format, sweep
from parallax.conformance.claim import SNAPSHOT_CLAIM, Claim
from tests._support.repo import canonical_snapshot_claim


@pytest.fixture
def pipelines_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(psycopg.capabilities, "has_pipeline", lambda: True)


@pytest.mark.usefixtures("pipelines_available")
def test_snapshot_claim_capabilities_match_slices_md() -> None:
    canonical = canonical_snapshot_claim()
    assert SNAPSHOT_CLAIM.capabilities() == canonical["capabilities"]


def test_a_libpq_without_pipelines_excludes_ordered_write_transport_cases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(psycopg.capabilities, "has_pipeline", lambda: False)
    assert SNAPSHOT_CLAIM.capabilities()["caseTags"] == {
        "include": ["slice-snapshot-1"],
        "exclude": ["ordered-write-transport"],
    }
    tagged = [case for case in case_format.load_cases() if "ordered-write-transport" in case.tags]
    assert tagged
    reachable = {case.case_id for case in sweep.reachable_cases()}
    assert not reachable & {case.case_id for case in tagged}
    for case in tagged:
        diagnostic = adapter.classify("compile", "postgres", case)
        assert diagnostic is not None
        assert diagnostic.code == "unsupported-case-tag"


@pytest.mark.usefixtures("pipelines_available")
def test_claim_capabilities_omit_empty_case_tags() -> None:
    claim = Claim(
        modules=("m-core",),
        case_shapes=("read",),
        include=(),
        exclude=(),
        commands=("describe",),
        provisioning="self-managed",
    )
    assert "caseTags" not in claim.capabilities()
