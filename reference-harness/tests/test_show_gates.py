"""Docker-free tests for the gate-graph display command."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from reference_harness.gate_graph import GateGraph
from reference_harness.show_gates import main, render


def _report(graph: GateGraph, *names: str) -> str:
    return "\n".join(render(graph, list(names)))


def test_an_aggregate_reports_its_dependencies_and_execution_owners(
    gate_graph: Callable[[str], GateGraph],
) -> None:
    report = _report(gate_graph("diamond.just"), "top-check")

    assert "  top-check\n    runtime: slow\n" in report
    assert "    dependencies: left-check-branch, right-check-branch\n" in report
    assert (
        "    execution owners (3):\n"
        "      - leaf-check-shared\n"
        "      - left-check-branch\n"
        "      - right-check-branch\n"
    ) in report
    assert report.endswith("1 recipe(s): 0 execution, 1 aggregate")


def test_an_aggregate_composing_nothing_is_signalled(
    gate_graph: Callable[[str], GateGraph],
) -> None:
    report = _report(gate_graph("roles.just"), "harness-check-empty")

    assert "  harness-check-empty\n" in report
    assert "    composes nothing: no command body and no dependency\n" in report
    assert "dependencies:" not in report
    assert "execution owners" not in report


def test_an_execution_recipe_reports_its_classes_prerequisites_and_command_count(
    gate_graph: Callable[[str], GateGraph],
) -> None:
    report = _report(gate_graph("roles.just"), "harness-coverage-diff", "harness-format-check")

    assert "  harness-coverage-diff\n    runtime: slow   understated (declared: fast)\n" in report
    assert "    prerequisites: harness-test-db\n" in report
    assert "    commands: 1\n" in report
    assert "  harness-format-check\n    runtime: fast   scheduling: dbfree\n" in report
    assert "    doc: the description the resolver reports\n" in report


def test_an_undeclared_runtime_class_reads_as_unclassified(
    gate_graph: Callable[[str], GateGraph],
) -> None:
    report = _report(gate_graph("undeclared-runtime.just"), "core-check-undeclared")

    assert "  core-check-undeclared\n    runtime: unclassified\n" in report


def test_a_parameterized_recipe_renders_its_signature(
    gate_graph: Callable[[str], GateGraph],
) -> None:
    report = _report(gate_graph("roles.just"), "core-show-language-spec", "_internal-show-detail")

    assert "  core-show-language-spec <language_spec>\n" in report
    assert "  _internal-show-detail (private)\n" in report


def test_the_whole_graph_is_grouped_by_role(
    gate_graph: Callable[[str], GateGraph], gate_graph_dir: Callable[[str], Path]
) -> None:
    report = _report(gate_graph("roles.just"))

    assert report.startswith(f"gate graph: {gate_graph_dir('roles.just') / 'justfile'}\n")
    assert "aggregate recipes (2)\n" in report
    assert "execution recipes (8)\n" in report
    assert report.index("aggregate recipes") < report.index("execution recipes")
    assert report.endswith("10 recipe(s): 8 execution, 2 aggregate")


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
    rc = main([str(gate_graph_dir("diamond.just")), "top-verify"])

    assert rc == 2
    assert "unknown recipe 'top-verify'" in capsys.readouterr().err


def test_a_directory_without_a_justfile_fails_resolution(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main([str(tmp_path)])

    assert rc == 1
    assert "gate graph inspection FAILED" in capsys.readouterr().err
