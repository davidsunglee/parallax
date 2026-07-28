"""Docker-free tests for the slice-inspection command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from reference_harness.slice_inspect import main

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC_DIR = _REPO_ROOT / "core" / "spec"
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"

_EXPECTED_MODULE_UNIONS = {
    "slice-snapshot-1": [
        "m-api-conformance",
        "m-auto-retry",
        "m-batch-write",
        "m-bitemp-write",
        "m-case-format",
        "m-conformance-adapter",
        "m-core",
        "m-db-error",
        "m-deep-fetch",
        "m-descriptor",
        "m-dialect",
        "m-inheritance",
        "m-metamodel",
        "m-model-formation",
        "m-navigate",
        "m-op-algebra",
        "m-opt-lock",
        "m-pk-gen",
        "m-read-lock",
        "m-relationship",
        "m-snapshot-read",
        "m-sql",
        "m-storage-layout",
        "m-temporal-read",
        "m-txtime-write",
        "m-unit-work",
        "m-value-object",
    ],
    "slice-managed-1": [
        "m-api-conformance",
        "m-auto-retry",
        "m-batch-write",
        "m-bitemp-write",
        "m-case-format",
        "m-conformance-adapter",
        "m-core",
        "m-db-error",
        "m-deep-fetch",
        "m-descriptor",
        "m-detach",
        "m-dialect",
        "m-identity-map",
        "m-inheritance",
        "m-metamodel",
        "m-model-formation",
        "m-navigate",
        "m-op-algebra",
        "m-op-list",
        "m-opt-lock",
        "m-pk-gen",
        "m-read-lock",
        "m-relationship",
        "m-sql",
        "m-storage-layout",
        "m-temporal-read",
        "m-txtime-write",
        "m-unit-work",
        "m-value-object",
    ],
}

_STORAGE_LAYOUT_CONTRACT_CASES = {
    "core/compatibility/cases/m-storage-layout-001-rejected-standalone-attribute-value-object-column-collision.yaml",
    "core/compatibility/cases/m-storage-layout-002-rejected-tpcs-inherited-column-collision.yaml",
    "core/compatibility/cases/m-storage-layout-003-rejected-tph-sibling-column-collision.yaml",
    "core/compatibility/cases/m-storage-layout-004-rejected-tph-tag-column-collision.yaml",
    "core/compatibility/cases/m-storage-layout-005-rejected-table-mapping-collision.yaml",
}

_MATERIALIZATION_KEY_CASES = {
    "core/compatibility/cases/m-inheritance-115-rejected-attribute-relationship-materialization-key-collision.yaml",
    "core/compatibility/cases/m-inheritance-116-rejected-narrowed-view-materialization-key-collision.yaml",
    "core/compatibility/cases/m-inheritance-117-rejected-family-variant-materialization-key-collision.yaml",
    "core/compatibility/cases/m-inheritance-118-value-object-relationship-name-overlap-graph.yaml",
    "core/compatibility/cases/m-inheritance-119-value-object-family-variant-overlap-graph.yaml",
    "core/compatibility/cases/m-inheritance-120-qualified-duplicate-local-variants-graph.yaml",
}


def test_storage_layout_rejected_witnesses_pin_distinct_issue_namespaces() -> None:
    expected_rules = {
        "m-storage-layout-001-rejected-standalone-attribute-value-object-column-collision.yaml": (
            "storage-layout-column-collision"
        ),
        "m-storage-layout-002-rejected-tpcs-inherited-column-collision.yaml": (
            "storage-layout-column-collision"
        ),
        "m-storage-layout-003-rejected-tph-sibling-column-collision.yaml": (
            "storage-layout-column-collision"
        ),
        "m-storage-layout-004-rejected-tph-tag-column-collision.yaml": (
            "storage-layout-column-collision"
        ),
        "m-storage-layout-005-rejected-table-mapping-collision.yaml": (
            "storage-layout-table-mapping-collision"
        ),
    }

    cases_dir = _COMPATIBILITY_ROOT / "cases"
    for filename, expected_rule in expected_rules.items():
        case = yaml.safe_load((cases_dir / filename).read_text(encoding="utf-8"))
        assert case["then"]["rejectedRule"] == expected_rule

    mapping_case = yaml.safe_load(
        (cases_dir / "m-storage-layout-005-rejected-table-mapping-collision.yaml").read_text(
            encoding="utf-8"
        )
    )
    entities = mapping_case["when"]["model"]["entities"]
    assert [entity["name"] for entity in entities] == ["FirstRecord", "SecondRecord"]
    assert {entity["table"] for entity in entities} == {"shared_record"}
    first_columns = {attribute.get("column") for attribute in entities[0]["attributes"]}
    second_columns = {attribute.get("column") for attribute in entities[1]["attributes"]}
    assert first_columns.isdisjoint(second_columns)
    assert [
        next(attribute["column"] for attribute in entity["attributes"] if attribute["primaryKey"])
        for entity in entities
    ] == ["first_id", "second_id"]


@pytest.mark.parametrize(
    ("slice_tag", "lifecycle_module", "excluded_module", "prerequisites"),
    [
        (
            "slice-snapshot-1",
            "m-snapshot-read",
            "m-identity-map",
            ["m-db-port"],
        ),
        ("slice-managed-1", "m-identity-map", "m-snapshot-read", ["m-db-port"]),
    ],
)
def test_json_report_derives_each_lifecycle_slice(
    slice_tag: str,
    lifecycle_module: str,
    excluded_module: str,
    prerequisites: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(
        [
            "--json",
            str(_SPEC_DIR),
            str(_COMPATIBILITY_ROOT),
            slice_tag,
        ]
    )

    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["slice"] == slice_tag
    assert report["canonicalClaim"]["capabilities"]["caseTags"] == {"include": [slice_tag]}
    assert report["supported"] == {
        "caseShapes": [
            "read",
            "writeSequence",
            "scenario",
            "conflict",
            "boundary",
            "error",
            "concurrencySuccess",
            "rejected",
        ],
        "commands": ["describe", "compile", "run"],
        "dialects": ["postgres"],
    }
    assert lifecycle_module in report["moduleTagUnion"]
    assert excluded_module not in report["moduleTagUnion"]
    assert report["moduleTagUnion"] == _EXPECTED_MODULE_UNIONS[slice_tag]
    assert report["transitivePrerequisitesOutsideClaim"] == prerequisites
    assert report["cases"] == sorted(report["cases"])
    assert "core/compatibility/cases/m-core-001-scalar-types-roundtrip.yaml" in report["cases"]
    assert _STORAGE_LAYOUT_CONTRACT_CASES <= set(report["cases"])
    assert _MATERIALIZATION_KEY_CASES <= set(report["cases"])
    assert not any(
        f"/m-inheritance-{case_number}-" in case
        for case in report["cases"]
        for case_number in range(111, 115)
    )


def test_text_report_names_every_required_view(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(
        [
            str(_SPEC_DIR),
            str(_COMPATIBILITY_ROOT),
            "slice-snapshot-1",
        ]
    )

    assert rc == 0
    output = capsys.readouterr().out
    assert "Slice: slice-snapshot-1" in output
    assert "Canonical claim:" in output
    assert "Case membership" in output
    assert "Module-tag union" in output
    assert "Supported case shapes:" in output
    assert "Supported dialects:" in output
    assert "Supported commands:" in output
    assert "Transitive prerequisites outside claim coverage" in output
    assert "m-db-port" in output


def test_unknown_slice_is_an_actionable_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(
        [
            str(_SPEC_DIR),
            str(_COMPATIBILITY_ROOT),
            "slice-unknown-1",
        ]
    )

    assert rc == 2
    error = capsys.readouterr().err
    assert "unknown slice 'slice-unknown-1'" in error
    assert "slice-managed-1" in error
    assert "slice-snapshot-1" in error


def test_relative_root_recipe_paths_render_repo_relative_cases(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(_REPO_ROOT / "reference-harness")

    rc = main(["--json", "../core/spec", "../core/compatibility", "slice-snapshot-1"])

    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["cases"][0].startswith("core/compatibility/cases/")


def test_all_slice_check_exercises_every_canonical_claim(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["--check-all", str(_SPEC_DIR), str(_COMPATIBILITY_ROOT)])

    assert rc == 0
    assert capsys.readouterr().out == "slice inspection OK: 2 canonical claim(s)\n"
