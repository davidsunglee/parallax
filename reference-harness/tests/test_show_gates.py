"""Docker-free tests for the gate-graph display command."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from reference_harness.show_gates import main


def test_an_aggregate_reports_its_dependencies_and_execution_owners(
    gate_graph_dir: Callable[[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    justfile_dir = gate_graph_dir("diamond.just")

    rc = main([str(justfile_dir), "top-check"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "  top-check\n    runtime: slow\n" in out
    assert "    dependencies: left-check-branch, right-check-branch\n" in out
    assert (
        "    execution owners (3):\n"
        "      - leaf-check-shared\n"
        "      - left-check-branch\n"
        "      - right-check-branch\n"
    ) in out
    assert out.endswith("1 recipe(s): 0 execution, 1 aggregate\n")


def test_an_execution_recipe_reports_its_classes_prerequisites_and_command_count(
    gate_graph_dir: Callable[[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    justfile_dir = gate_graph_dir("roles.just")

    rc = main([str(justfile_dir), "harness-coverage-diff", "harness-format-check"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "  harness-coverage-diff\n    runtime: slow   understated (declared: fast)\n" in out
    assert "    prerequisites: harness-test-db\n" in out
    assert "    commands: 1\n" in out
    assert "  harness-format-check\n    runtime: fast   scheduling: dbfree\n" in out
    assert "    doc: the description the resolver reports\n" in out


def test_an_undeclared_runtime_class_reads_as_unclassified(
    gate_graph_dir: Callable[[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    justfile_dir = gate_graph_dir("undeclared-runtime.just")

    rc = main([str(justfile_dir), "core-check-undeclared"])

    assert rc == 0
    assert "  core-check-undeclared\n    runtime: unclassified\n" in capsys.readouterr().out


def test_a_parameterized_recipe_renders_its_signature(
    gate_graph_dir: Callable[[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    justfile_dir = gate_graph_dir("roles.just")

    rc = main([str(justfile_dir), "core-show-language-spec", "_internal-show-detail"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "  core-show-language-spec <language_spec>\n" in out
    assert "  _internal-show-detail (private)\n" in out


def test_the_whole_graph_is_grouped_by_role(
    gate_graph_dir: Callable[[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    justfile_dir = gate_graph_dir("roles.just")

    rc = main([str(justfile_dir)])

    assert rc == 0
    out = capsys.readouterr().out
    assert out.startswith(f"gate graph: {justfile_dir / 'justfile'}\n")
    assert "aggregate recipes (2)\n" in out
    assert "execution recipes (7)\n" in out
    assert out.index("aggregate recipes") < out.index("execution recipes")
    assert out.endswith("9 recipe(s): 7 execution, 2 aggregate\n")


def test_the_repository_graph_renders(repo_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main([str(repo_root)])

    assert rc == 0
    assert "  show-gates <recipes>\n    runtime: fast\n" in capsys.readouterr().out


def test_a_missing_directory_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "does-not-exist"

    rc = main([str(missing)])

    assert rc == 2
    assert f"not a directory: {missing}" in capsys.readouterr().err


def test_no_argument_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main([])

    assert rc == 2
    assert "usage: python -m reference_harness.show_gates" in capsys.readouterr().err


def test_an_unknown_recipe_is_a_usage_error(
    gate_graph_dir: Callable[[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    justfile_dir = gate_graph_dir("diamond.just")

    rc = main([str(justfile_dir), "top-verify"])

    assert rc == 2
    assert "unknown recipe 'top-verify'" in capsys.readouterr().err


def test_a_directory_without_a_justfile_fails_resolution(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main([str(tmp_path)])

    assert rc == 1
    assert "gate graph inspection FAILED" in capsys.readouterr().err
