"""Docker-free tests for the completed language-spec validator."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from reference_harness.language_spec_validate import main

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC_DIR = _REPO_ROOT / "core" / "spec"
_FIXTURES = Path(__file__).parent / "fixtures" / "language-specs"


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


def test_missing_input_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    missing = _FIXTURES / "does-not-exist.md"

    rc = main([str(missing), str(_SPEC_DIR)])

    assert rc == 2
    assert f"not a file: {missing}" in capsys.readouterr().err
