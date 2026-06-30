"""DB-free tests for the conformance-adapter output schema."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from reference_harness.paths import schemas_dir

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"
_SPEC_DIR = _REPO_ROOT / "core" / "spec"


def _validator() -> Draft202012Validator:
    schema_path = schemas_dir(_COMPATIBILITY_ROOT) / "conformance-adapter.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _slice_claim_block() -> str:
    """Extract the canonical slice describe JSON fenced under the slice heading."""
    scope = (_SPEC_DIR / "scope-and-tiers.md").read_text(encoding="utf-8")
    in_section = False
    fence: list[str] | None = None
    for line in scope.splitlines():
        if line.startswith("## "):
            in_section = (
                line[3:].strip().lower() == "first-implementation conformance slice"
            )
            continue
        if not in_section:
            continue
        if fence is None:
            if line.strip() == "```json":
                fence = []
            continue
        if line.strip() == "```":
            return "\n".join(fence)
        fence.append(line)
    raise AssertionError("no ```json slice claim found under the slice heading")


def _valid_describe() -> dict:
    return {
        "schemaVersion": "1",
        "command": "describe",
        "status": "ok",
        "adapter": {
            "language": "typescript",
            "name": "@parallax/typescript",
            "version": "0.1.0",
        },
        "capabilities": {
            "modules": ["m0", "m1", "m2", "m3", "m8", "m11", "m12"],
            "dialects": ["postgres"],
            "caseShapes": ["read", "writeSequence"],
            "caseTags": {
                "exclude": ["aggregate", "identity cache", "query cache"]
            },
            "commands": ["describe", "compile", "run"],
            "provisioning": "self-managed",
        },
    }


def _valid_benchmark() -> dict:
    return {
        "schemaVersion": "1",
        "command": "benchmark",
        "status": "ok",
        "adapter": {
            "language": "typescript",
            "name": "@parallax/typescript",
            "version": "0.1.0",
        },
        "benchmark": "core/compatibility/benchmarks/read-mix.yaml",
        "report": {
            "generatedAt": "2026-06-27T00:00:00+00:00",
            "dialect": "postgres",
            "benchmarks": [
                {
                    "fixture": "read-mix.yaml",
                    "model": "models/account.yaml",
                    "datasetRows": 1000,
                    "workloads": [
                        {
                            "name": "point-read",
                            "iterations": 200,
                            "wallTimeMs": {
                                "p50": 2.8,
                                "p95": 4.7,
                            },
                            "roundTrips": 1,
                            "expectRoundTrips": 1,
                            "roundTripsOk": True,
                        }
                    ],
                }
            ],
            "memory": {
                "peakBytes": 12582912,
                "steadyBytes": 10485760,
            },
        },
    }


def test_describe_accepts_case_tag_claims() -> None:
    errors = list(_validator().iter_errors(_valid_describe()))
    assert errors == []


def test_case_tag_claims_must_have_include_or_exclude() -> None:
    describe = _valid_describe()
    describe["capabilities"]["caseTags"] = {}

    assert list(_validator().iter_errors(describe))


def test_case_tag_claims_reject_duplicate_tags() -> None:
    describe = _valid_describe()
    describe["capabilities"]["caseTags"] = {
        "exclude": ["aggregate", "aggregate"]
    }

    assert list(_validator().iter_errors(describe))


def test_describe_still_allows_omitting_case_tags_for_all_or_nothing_claims() -> None:
    describe = copy.deepcopy(_valid_describe())
    del describe["capabilities"]["caseTags"]

    errors = list(_validator().iter_errors(describe))
    assert errors == []


def test_describe_accepts_m14_coherence_module_claim() -> None:
    describe = copy.deepcopy(_valid_describe())
    describe["capabilities"]["modules"] = ["m0", "m8", "m14"]

    errors = list(_validator().iter_errors(describe))
    assert errors == []


def test_describe_rejects_retired_coherence_module_claim() -> None:
    # Cross-process coherence is module m14 now; the un-numbered "coherence"
    # module claim is retired (it survives only as an ordinary case tag, not a
    # module-like capability claim), so an adapter MUST claim m14 instead.
    describe = copy.deepcopy(_valid_describe())
    describe["capabilities"]["modules"] = ["m0", "coherence"]

    assert list(_validator().iter_errors(describe))


def test_benchmark_accepts_m13_report_shape() -> None:
    errors = list(_validator().iter_errors(_valid_benchmark()))
    assert errors == []


def test_benchmark_rejects_legacy_metrics_shape() -> None:
    benchmark = {
        "schemaVersion": "1",
        "command": "benchmark",
        "status": "ok",
        "adapter": {
            "language": "typescript",
            "name": "@parallax/typescript",
            "version": "0.1.0",
        },
        "benchmark": "core/compatibility/benchmarks/read-mix.yaml",
        "dialect": "postgres",
        "metrics": {
            "iterations": 100,
            "p50Ms": 2.8,
            "p95Ms": 4.7,
            "roundTrips": 1,
        },
    }

    assert list(_validator().iter_errors(benchmark))


# --- the canonical first-implementation-mvp slice claim ----------------------


def test_canonical_slice_claim_is_schema_valid() -> None:
    # The embedded slice describe claim in scope-and-tiers.md is the single source
    # of truth; it must be a legal describe document.
    claim = json.loads(_slice_claim_block())
    errors = list(_validator().iter_errors(claim))
    assert errors == []


def test_canonical_slice_claim_carries_no_profile_wire_key() -> None:
    # The `profile` name is documentation only; describeOk is
    # additionalProperties:false at the top level and inside capabilities, so the
    # canonical claim must NOT carry a `profile` key (Question C).
    claim = json.loads(_slice_claim_block())
    assert "profile" not in claim
    assert "profile" not in claim["capabilities"]


def test_canonical_slice_claim_is_include_driven() -> None:
    claim = json.loads(_slice_claim_block())
    assert claim["capabilities"]["caseTags"] == {
        "include": ["first-implementation-mvp"]
    }
