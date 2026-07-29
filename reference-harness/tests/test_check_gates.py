"""Docker-free tests for the blocking check over the verification-command graph."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

from reference_harness.check_gates import (
    AGENT_GUIDANCE,
    CI_WORKFLOW,
    OPERATIONAL_MAP,
    SUPPORT_DIRECTORY,
    SURFACES,
    main,
)
from reference_harness.runner_config import PYTEST

_INVALID_CASES = Path(__file__).parent / "fixtures" / "gate-graphs" / "invalid-cases.yaml"

_MIRRORED_PYTHON_MAP = Path("languages") / "python" / OPERATIONAL_MAP
_MIRRORED_PYTHON_SPEC = Path("languages") / "python" / "spec" / "python.md"
_MIRRORED_FILES = (
    "justfile",
    str(CI_WORKFLOW),
    AGENT_GUIDANCE,
    OPERATIONAL_MAP,
    str(_MIRRORED_PYTHON_MAP),
    str(_MIRRORED_PYTHON_SPEC),
    "reference-harness/pyproject.toml",
    "languages/python/pyproject.toml",
)
_MIRRORED_TEST_ROOT = Path("languages") / "python" / "tests"


@pytest.fixture(scope="session")
def conforming_repository(repo_root: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A scratch repository holding exactly what the gate check reads.

    The check's subject is the tree it runs in, so a drift case has to mutate a
    tree rather than an input. Mirroring the real files rather than authoring a
    miniature repository is what keeps the mutations honest: each one asserts
    that its target text occurs exactly once, so an edit to the real justfile,
    workflow, or runner configuration that invalidates a case fails loudly
    instead of passing over a fixture nobody maintains.
    """
    root = tmp_path_factory.mktemp("conforming-repository")
    for relative in _MIRRORED_FILES:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo_root / relative, destination)
    tests = root / _MIRRORED_TEST_ROOT
    for directory in (*SURFACES.values(), SUPPORT_DIRECTORY):
        (tests / directory).mkdir(parents=True)
    for name in PYTEST.root_files:
        (tests / name).touch()
    return root


def _copy(conforming_repository: Path, destination: Path) -> Path:
    shutil.copytree(conforming_repository, destination)
    return destination


def _mutate(root: Path, scenario: Mapping[str, Any]) -> None:
    target = root / scenario["file"]
    base = target.read_text(encoding="utf-8")
    assert base.count(scenario["old"]) == 1, scenario["name"]
    target.write_text(base.replace(scenario["old"], scenario["new"]), encoding="utf-8")


def test_the_mirrored_repository_conforms(
    conforming_repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main([str(conforming_repository)])

    assert rc == 0
    assert "gate check OK" in capsys.readouterr().out


def test_each_drift_reports_its_own_code(
    conforming_repository: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    scenarios = yaml.safe_load(_INVALID_CASES.read_text(encoding="utf-8"))
    assert isinstance(scenarios, list)

    for scenario in scenarios:
        root = _copy(conforming_repository, tmp_path / scenario["name"])
        _mutate(root, scenario)

        rc = main([str(root)])

        assert rc == 1, scenario["name"]
        error = capsys.readouterr().err
        assert f"[{scenario['code']}]" in error, (scenario["name"], error)
        assert scenario["message"] in error, (scenario["name"], error)


def test_a_renamed_surface_directory_is_reported(
    conforming_repository: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _copy(conforming_repository, tmp_path / "renamed-surface")
    (root / _MIRRORED_TEST_ROOT / "dialect").rename(root / _MIRRORED_TEST_ROOT / "dialects")

    rc = main([str(root)])

    assert rc == 1
    error = capsys.readouterr().err
    assert "[missing-surface-directory] `python` has no `dialect/` under tests/" in error
    assert "[unexpected-test-root-entry] `python` holds `dialects` at the root" in error


def test_a_stray_file_at_the_test_root_is_reported(
    conforming_repository: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _copy(conforming_repository, tmp_path / "stray-root-file")
    (root / _MIRRORED_TEST_ROOT / "helpers.py").touch()

    rc = main([str(root)])

    assert rc == 1
    assert "[unexpected-test-root-entry] `python` holds `helpers.py` at the root" in (
        capsys.readouterr().err
    )


def test_a_scope_without_an_operational_map_is_reported(
    conforming_repository: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _copy(conforming_repository, tmp_path / "no-operational-map")
    (root / _MIRRORED_PYTHON_MAP).unlink()

    rc = main([str(root)])

    assert rc == 1
    assert f"[doc-missing-operational-map] `python` has no {_MIRRORED_PYTHON_MAP}" in (
        capsys.readouterr().err
    )


def test_a_scope_without_runner_configuration_is_reported(
    conforming_repository: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _copy(conforming_repository, tmp_path / "no-runner-configuration")
    (root / "reference-harness" / "pyproject.toml").unlink()

    rc = main([str(root)])

    assert rc == 1
    assert "[missing-runner-configuration] `harness` declares a scheduling partition" in (
        capsys.readouterr().err
    )


def test_a_repository_without_a_ci_workflow_is_reported(
    conforming_repository: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _copy(conforming_repository, tmp_path / "no-workflow")
    (root / CI_WORKFLOW).unlink()

    rc = main([str(root)])

    assert rc == 1
    assert f"[missing-ci-workflow] {CI_WORKFLOW} does not exist" in capsys.readouterr().err


def test_an_unresolvable_graph_is_a_failure_not_a_crash(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main([str(tmp_path)])

    assert rc == 1
    assert "gate check FAILED" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [[], ["one", "two"]])
def test_a_wrong_argument_count_is_a_usage_error(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(argv)

    assert rc == 2
    assert "usage: python -m reference_harness.check_gates" in capsys.readouterr().err


def test_a_missing_root_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "does-not-exist"

    rc = main([str(missing)])

    assert rc == 2
    assert f"not a directory: {missing}" in capsys.readouterr().err
