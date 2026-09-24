"""Docker-free tests for the completed language-spec validator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from reference_harness.dep_graph_check import parse_profile_envelopes
from reference_harness.language_spec_validate import main, validate_language_spec

_TESTS_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _TESTS_ROOT.parents[1]
_SPEC_DIR = _REPO_ROOT / "core" / "spec"
_FIXTURES = _TESTS_ROOT / "fixtures" / "language-specs"


@pytest.mark.parametrize(
    ("fixture", "slice_tag", "lifecycle"),
    [
        ("valid-snapshot.md", "slice-snapshot-1", "snapshot"),
        ("valid-managed.md", "slice-managed-1", "managed-object"),
    ],
)
def test_valid_completed_specs_pass(
    fixture: str,
    slice_tag: str,
    lifecycle: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    spec_path = _FIXTURES / fixture

    rc = main([str(spec_path), str(_SPEC_DIR)])

    assert rc == 0
    assert capsys.readouterr().out == (
        f"language spec OK: {spec_path} ({slice_tag}, {lifecycle} lifecycle)\n"
    )


def test_focused_invalid_specs_report_the_precise_decision(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    scenarios = yaml.safe_load((_FIXTURES / "invalid-cases.yaml").read_text(encoding="utf-8"))
    assert isinstance(scenarios, list)

    for scenario in scenarios:
        base = (_FIXTURES / scenario["base"]).read_text(encoding="utf-8")
        assert base.count(scenario["old"]) == 1, scenario["name"]
        invalid = base.replace(scenario["old"], scenario["new"])
        spec_path = tmp_path / f"{scenario['name']}.md"
        spec_path.write_text(invalid, encoding="utf-8")

        rc = main([str(spec_path), str(_SPEC_DIR)])

        assert rc == 1, scenario["name"]
        error = capsys.readouterr().err
        assert f"[{scenario['code']}]" in error, (scenario["name"], error)
        assert scenario["message"] in error, (scenario["name"], error)


def test_discovery_validates_every_completed_spec(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main([str(_REPO_ROOT)])

    assert rc == 0
    out = capsys.readouterr().out
    assert f"language spec OK: {_REPO_ROOT / 'languages' / 'python' / 'spec' / 'python.md'}" in out
    assert "language specs OK:" in out


def test_a_language_target_without_a_spec_is_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "languages" / "rust" / "spec").mkdir(parents=True)

    rc = main([str(tmp_path)])

    assert rc == 1
    assert "missing language binding:" in capsys.readouterr().err


def test_missing_input_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    missing = _FIXTURES / "does-not-exist.md"

    rc = main([str(missing), str(_SPEC_DIR)])

    assert rc == 2
    assert f"not a file: {missing}" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("manifest", "code"),
    [
        ("", "binding-manifest"),
        ('{"slice":', "binding-manifest"),
        ('{"slice":"slice-snapshot-1","slice":"slice-managed-1"}', "binding-manifest"),
        ('{"slice":"slice-snapshot-1","unknown":true}', "binding-manifest"),
        ("[]", "binding-manifest"),
        ("{}", "binding-manifest"),
        ('{"slice":null}', "slice-selection"),
        ('{"slice":42}', "slice-selection"),
    ],
)
def test_invalid_binding_manifest(
    manifest: str, code: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "binding.md"
    path.write_text(f"```language-binding\n{manifest}\n```\n", encoding="utf-8")
    assert main([str(path), str(_SPEC_DIR)]) == 1
    assert f"[{code}]" in capsys.readouterr().err


@pytest.mark.parametrize("suffix", ["\n```language-binding\n", "\n```language-binding\n{}\n```"])
def test_duplicate_or_unclosed_binding_fences(
    suffix: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "binding.md"
    path.write_text(
        '```language-binding\n{"slice":"slice-snapshot-1"}\n```\n' + suffix,
        encoding="utf-8",
    )
    assert main([str(path), str(_SPEC_DIR)]) == 1
    assert "[binding-manifest]" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("schema", "invalid-describe-envelope"),
        ("neither-lifecycle", "lifecycle-incomplete-slice"),
        ("both-lifecycles", "lifecycle-incomplete-slice"),
    ],
)
def test_canonical_claim_schema_and_lifecycle_are_still_enforced(mutation: str, code: str) -> None:
    envelope = parse_profile_envelopes((_SPEC_DIR / "slices.md").read_text())["slice-snapshot-1"]
    if mutation == "schema":
        envelope["capabilities"]["unknownCapability"] = None
    elif mutation == "neither-lifecycle":
        envelope["capabilities"]["modules"].remove("m-snapshot-read")
    else:
        envelope["capabilities"]["modules"].append("m-identity-map")
    issues, _, _ = validate_language_spec(
        (_FIXTURES / "valid-snapshot.md").read_text(),
        "```json\n" + json.dumps(envelope) + "\n```\n",
        (_SPEC_DIR / "modules.md").read_text(),
        (_SPEC_DIR / "language-spec-template.md").read_text(),
        json.loads((_SPEC_DIR.parent / "schemas" / "conformance-adapter.schema.json").read_text()),
    )
    assert code in {issue.code for issue in issues}


def test_discovery_ignores_supporting_pages(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec_dir = tmp_path / "languages" / "example" / "spec"
    spec_dir.mkdir(parents=True)
    (spec_dir / "example.md").write_text((_FIXTURES / "valid-snapshot.md").read_text())
    (spec_dir / "notes.md").write_text("Supporting prose needs no manifest or repeated topology.")
    for relative in (
        "spec/slices.md",
        "spec/modules.md",
        "spec/language-spec-template.md",
        "schemas/conformance-adapter.schema.json",
    ):
        destination = tmp_path / "core" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((_SPEC_DIR.parent / relative).read_text())
    assert main([str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "1 completed spec(s)" in output
    assert "notes.md" not in output
