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
_TS_SPEC = _REPO_ROOT / "languages" / "typescript" / "spec" / "01-implementation-spec.md"


def _validator() -> Draft202012Validator:
    schema_path = schemas_dir(_COMPATIBILITY_ROOT) / "conformance-adapter.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _first_json_fence_under_heading(markdown: str, heading_prefix: str, heading_text: str) -> str:
    """Return the first ```json fenced block under the matching heading.

    ``heading_prefix`` is the exact markdown heading marker (e.g. ``"## "`` or
    ``"### "``); a heading at the same depth (matching ``heading_prefix``) whose
    text does *not* match ``heading_text`` ends the section. Matching is
    case-insensitive and trims trailing punctuation/whitespace.
    """
    target = heading_text.strip().lower()
    depth = len(heading_prefix.strip())
    in_section = False
    fence: list[str] | None = None
    for line in markdown.splitlines():
        if line.startswith(heading_prefix):
            in_section = line[len(heading_prefix) :].strip().lower() == target
            continue
        # A new heading at the same depth (or shallower) closes the section.
        if in_section and line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            if level <= depth:
                break
        if not in_section:
            continue
        if fence is None:
            if line.strip() == "```json":
                fence = []
            continue
        if line.strip() == "```":
            return "\n".join(fence)
        fence.append(line)
    raise AssertionError(f"no ```json block found under heading {heading_text!r}")


def _slice_claim_block() -> str:
    """Extract the canonical slice describe JSON fenced under the slice heading."""
    slices = (_SPEC_DIR / "slices.md").read_text(encoding="utf-8")
    return _first_json_fence_under_heading(slices, "## ", "First-implementation Conformance Slice")


def _ts_v1_claim_block() -> str:
    """Extract the TypeScript V1 describe JSON fenced under §1.1."""
    ts_spec = _TS_SPEC.read_text(encoding="utf-8")
    return _first_json_fence_under_heading(ts_spec, "### ", "1.1 V1 conformance capability claims")


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
            "modules": [
                "m-core",
                "m-descriptor",
                "m-op-algebra",
                "m-sql",
                "m-unit-work",
                "m-dialect",
                "m-conformance-adapter",
            ],
            "dialects": ["postgres"],
            "caseShapes": ["read", "writeSequence"],
            "caseTags": {"exclude": ["aggregate", "identity cache", "query cache"]},
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


def _valid_run(observations: dict) -> dict:
    return {
        "schemaVersion": "1",
        "command": "run",
        "status": "ok",
        "adapter": {
            "language": "typescript",
            "name": "@parallax/typescript",
            "version": "0.1.0",
        },
        "case": "core/compatibility/cases/m-deep-fetch-013-deferred-load-batches-latest.yaml",
        "dialect": "postgres",
        "caseShape": "scenario",
        "emissions": [],
        "observations": observations,
    }


# --- milestone-set graph observations ----------------------------------------


def test_run_accepts_ordered_milestone_set_graph_observations() -> None:
    observations = {
        "roundTrips": 1,
        "graphs": [
            {
                "pin": {"processingDate": "2024-01-01T00:00:00+00:00"},
                "graph": {"InvoiceLine": [{"id": 1000, "amount": 50.0}]},
            },
            {
                "pin": {"processingDate": "2024-04-01T00:00:00+00:00"},
                "graph": {"InvoiceLine": [{"id": 1000, "amount": 75.0}]},
            },
        ],
    }

    assert list(_validator().iter_errors(_valid_run(observations))) == []


def test_run_rejects_milestone_set_graph_entry_without_graph() -> None:
    observations = {
        "roundTrips": 1,
        "graphs": [
            {"pin": {"processingDate": "2024-01-01T00:00:00+00:00"}},
        ],
    }

    assert list(_validator().iter_errors(_valid_run(observations)))


# --- lifecycle observations: stateChecks + errors (COR-30) --------------------


def test_run_accepts_lifecycle_observations() -> None:
    observations = {
        "roundTrips": 1,
        "identityChecks": [{"left": "/scenario/1", "right": "/scenario/0", "same": False}],
        "stateChecks": [
            {"at": "/scenario/1", "expected": "detached", "observed": "detached", "pass": True}
        ],
        "errors": [{"at": "/scenario/2", "errorClass": "detached-relationship-load"}],
    }
    assert list(_validator().iter_errors(_valid_run(observations))) == []


def test_run_still_valid_without_lifecycle_observations() -> None:
    # The two new keys are optional/additive: an existing run output (roundTrips
    # plus rows / identityChecks) stays valid unchanged.
    observations = {
        "roundTrips": 1,
        "rows": [{"id": 1}],
        "identityChecks": [{"left": "/scenario/1", "right": "/scenario/0", "same": True}],
    }
    assert list(_validator().iter_errors(_valid_run(observations))) == []


def test_run_rejects_unknown_expected_state() -> None:
    observations = {
        "roundTrips": 1,
        "stateChecks": [
            {"at": "/scenario/1", "expected": "zombie", "observed": "x", "pass": False}
        ],
    }
    assert list(_validator().iter_errors(_valid_run(observations)))


def test_run_rejects_unknown_error_class() -> None:
    observations = {
        "roundTrips": 1,
        "errors": [{"at": "/scenario/2", "errorClass": "not-a-real-error"}],
    }
    assert list(_validator().iter_errors(_valid_run(observations)))


def test_run_rejects_state_check_missing_pass() -> None:
    observations = {
        "roundTrips": 1,
        "stateChecks": [{"at": "/scenario/1", "expected": "detached", "observed": "detached"}],
    }
    assert list(_validator().iter_errors(_valid_run(observations)))


# --- error-shape run observations: errorClass + nativeCode --------------------


def test_run_accepts_error_classification_observations() -> None:
    # An error-shape run reports the neutral m-db-error category the trigger
    # classified to plus the preserved native witness (SQLSTATE string or errno
    # integer — both wire forms are legal).
    for native in ("23505", 1062):
        observations = {"roundTrips": 2, "errorClass": "uniqueViolation", "nativeCode": native}
        assert list(_validator().iter_errors(_valid_run(observations))) == []


def test_run_rejects_application_lifecycle_class_in_error_classification() -> None:
    # The scalar pair carries the m-db-error taxonomy only; the application-
    # lifecycle vocabulary lives in the `errors` observation, not here.
    observations = {
        "roundTrips": 1,
        "errorClass": "detached-relationship-load",
        "nativeCode": "23505",
    }
    assert list(_validator().iter_errors(_valid_run(observations)))


def test_run_rejects_unpaired_error_classification() -> None:
    # errorClass and nativeCode travel together (dependentRequired, both ways).
    for observations in (
        {"roundTrips": 1, "errorClass": "deadlock"},
        {"roundTrips": 1, "nativeCode": "40P01"},
    ):
        assert list(_validator().iter_errors(_valid_run(observations)))


# --- rejected-shape run observation: rejectedRule ------------------------------


def test_run_accepts_rejected_rule_observation() -> None:
    # A rejected-case run touches no database: it reports the classified rule
    # with roundTrips: 0 (m-conformance-adapter, resolved DQ3/DQ8).
    observations = {"roundTrips": 0, "rejectedRule": "narrow-outside-position"}
    assert list(_validator().iter_errors(_valid_run(observations))) == []


def test_run_still_valid_without_rejected_rule_observation() -> None:
    # Additive/optional at the schema layer: an existing run output that never
    # claims the `rejected` shape stays valid unchanged.
    observations = {"roundTrips": 1, "rows": [{"id": 1}]}
    assert list(_validator().iter_errors(_valid_run(observations))) == []


def test_run_rejects_non_string_rejected_rule() -> None:
    observations = {"roundTrips": 0, "rejectedRule": 12345}
    assert list(_validator().iter_errors(_valid_run(observations)))


def test_describe_accepts_case_tag_claims() -> None:
    errors = list(_validator().iter_errors(_valid_describe()))
    assert errors == []


def test_case_tag_claims_must_have_include_or_exclude() -> None:
    describe = _valid_describe()
    describe["capabilities"]["caseTags"] = {}

    assert list(_validator().iter_errors(describe))


def test_case_tag_claims_reject_duplicate_tags() -> None:
    describe = _valid_describe()
    describe["capabilities"]["caseTags"] = {"exclude": ["aggregate", "aggregate"]}

    assert list(_validator().iter_errors(describe))


def test_describe_still_allows_omitting_case_tags_for_all_or_nothing_claims() -> None:
    describe = copy.deepcopy(_valid_describe())
    del describe["capabilities"]["caseTags"]

    errors = list(_validator().iter_errors(describe))
    assert errors == []


def test_describe_accepts_coherence_module_claim() -> None:
    describe = copy.deepcopy(_valid_describe())
    describe["capabilities"]["modules"] = ["m-core", "m-unit-work", "m-coherence"]

    errors = list(_validator().iter_errors(describe))
    assert errors == []


def test_describe_rejects_bare_coherence_module_claim() -> None:
    # Cross-process coherence is module `m-coherence`; a bare, un-prefixed
    # "coherence" claim does not match the `m-<slug>` module grammar, so an
    # adapter MUST claim `m-coherence` instead.
    describe = copy.deepcopy(_valid_describe())
    describe["capabilities"]["modules"] = ["m-core", "coherence"]

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


# --- the canonical slice-mvp-1 slice claim ----------------------


def test_canonical_slice_claim_is_schema_valid() -> None:
    # The embedded slice describe claim in slices.md is the single source
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
    assert claim["capabilities"]["caseTags"] == {"include": ["slice-mvp-1"]}


# --- TypeScript V1 adopts the canonical slice (anti-drift) --------------------


def test_typescript_v1_claim_is_schema_valid() -> None:
    # The §4.5 describe claim must itself be a legal describe document.
    claim = json.loads(_ts_v1_claim_block())
    errors = list(_validator().iter_errors(claim))
    assert errors == []


def test_typescript_v1_capabilities_equal_the_canonical_slice() -> None:
    # TS V1 *is* the canonical slice-mvp-1 slice (Resolved
    # Question E): its capabilities must equal the canonical claim's
    # capabilities exactly, so the two can never silently diverge. Only the
    # adapter identity (language/name/version) is allowed to differ.
    ts_claim = json.loads(_ts_v1_claim_block())
    canonical_claim = json.loads(_slice_claim_block())
    assert ts_claim["capabilities"] == canonical_claim["capabilities"]


def test_typescript_v1_claim_adapter_identity_is_typescript() -> None:
    # Sanity: the one place the two claims are allowed to differ is the adapter
    # identity. Guards against accidentally copying the reference adapter block.
    ts_claim = json.loads(_ts_v1_claim_block())
    assert ts_claim["adapter"]["language"] == "typescript"
    assert ts_claim["adapter"]["name"] == "@parallax/typescript"
