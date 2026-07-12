"""Canonical claim (`parallax.conformance.claim`) tests."""

from __future__ import annotations

import pytest

from conftest import canonical_snapshot_claim
from parallax.conformance.claim import ADAPTER, SNAPSHOT_CLAIM, Adapter, Claim

pytestmark = pytest.mark.unit


def test_adapter_identity_is_python() -> None:
    assert ADAPTER.to_json() == {
        "language": "python",
        "name": "parallax-core",
        "version": "0.1.0",
    }


def test_snapshot_claim_capabilities_match_slices_md() -> None:
    canonical = canonical_snapshot_claim()
    assert SNAPSHOT_CLAIM.capabilities() == canonical["capabilities"]


def test_claim_capabilities_include_and_exclude_shape() -> None:
    claim = Claim(
        modules=("m-core",),
        dialects=("postgres",),
        case_shapes=("read",),
        include=("slice-x",),
        exclude=("skip-me",),
        commands=("describe",),
        provisioning="self-managed",
    )
    assert claim.capabilities()["caseTags"] == {"include": ["slice-x"], "exclude": ["skip-me"]}


def test_claim_capabilities_omit_empty_case_tags() -> None:
    claim = Claim(
        modules=("m-core",),
        dialects=("postgres",),
        case_shapes=("read",),
        include=(),
        exclude=(),
        commands=("describe",),
        provisioning="self-managed",
    )
    assert "caseTags" not in claim.capabilities()


def test_adapter_is_a_frozen_value() -> None:
    assert Adapter("python", "parallax-core", "0.1.0") == ADAPTER
