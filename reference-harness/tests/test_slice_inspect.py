"""Docker-free tests for the slice-inspection command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reference_harness.slice_inspect import main

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC_DIR = _REPO_ROOT / "core" / "spec"
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"


@pytest.mark.parametrize(
    ("slice_tag", "lifecycle_module", "excluded_module", "prerequisites"),
    [
        (
            "slice-snapshot-1",
            "m-snapshot-read",
            "m-identity-map",
            ["m-db-port", "m-op-list"],
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
    assert report["transitivePrerequisitesOutsideClaim"] == prerequisites
    assert report["cases"] == sorted(report["cases"])
    assert "core/compatibility/cases/m-core-001-scalar-types-roundtrip.yaml" in report["cases"]


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
    assert capsys.readouterr().out == "slice inspection OK: 3 canonical claim(s)\n"
