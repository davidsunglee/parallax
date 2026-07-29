"""Docker-free tests for the verification-command graph resolver."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from reference_harness.gate_graph import (
    UNCLASSIFIED,
    GateGraph,
    GateGraphError,
    load_graph,
    parse_name,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = Path(__file__).parent / "fixtures" / "gate-graphs"


def _graph(fixture: str, tmp_path: Path) -> GateGraph:
    shutil.copyfile(_FIXTURES / fixture, tmp_path / "justfile")
    return load_graph(tmp_path)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("check", (None, "check", None)),
        ("check-dbfree", (None, "check", "dbfree")),
        ("show-gates", (None, "show", "gates")),
        ("report-matrix", (None, "report", "matrix")),
        ("lint-md", (None, "lint", "md")),
        ("harness-format-check", ("harness", "format-check", None)),
        ("harness-format", ("harness", "format", None)),
        ("python-check-dbfree", ("python", "check", "dbfree")),
        ("python-test-provider-contract", ("python", "test", "provider-contract")),
        ("core-check-slice-profiles", ("core", "check", "slice-profiles")),
        ("verify", (None, "verify", None)),
        ("matrix", (None, "matrix", None)),
        ("python-static", ("python", "static", None)),
        ("core-dep-graph", ("core", "dep-graph", None)),
        ("core-language-spec-check", ("core", "language-spec-check", None)),
        ("oracle-typecheck", ("oracle", "typecheck", None)),
    ],
)
def test_names_decompose_into_scope_operation_and_qualifier(
    name: str, expected: tuple[str | None, str, str | None]
) -> None:
    assert parse_name(name) == expected


def test_role_follows_the_presence_of_a_command_body(tmp_path: Path) -> None:
    graph = _graph("roles.just", tmp_path)

    assert graph.recipe("harness-check-dbfree").role == "aggregate"
    assert graph.recipe("harness-lint").role == "execution"
    assert graph.recipe("harness-coverage-diff").role == "execution"
    assert graph.recipe("harness-coverage-diff").dependencies == ("harness-test-db",)


def test_groups_split_into_runtime_and_scheduling_classes(tmp_path: Path) -> None:
    graph = _graph("roles.just", tmp_path)

    format_check = graph.recipe("harness-format-check")
    assert format_check.groups == frozenset({"fast", "dbfree"})
    assert format_check.declared_runtime_classes == frozenset({"fast"})
    assert format_check.scheduling_classes == frozenset({"dbfree"})
    assert graph.recipe("harness-lint").groups == frozenset()


def test_only_the_doc_attribute_describes_a_recipe(tmp_path: Path) -> None:
    graph = _graph("roles.just", tmp_path)

    assert graph.recipe("harness-format-check").doc == "the description the resolver reports"
    assert graph.recipe("harness-lint").doc is None


def test_bodies_reproduce_variable_interpolation(tmp_path: Path) -> None:
    graph = _graph("roles.just", tmp_path)

    assert graph.recipe("harness-lint").body == ("cd {{module}} && echo lint",)


def test_parameters_and_privacy_are_exposed(tmp_path: Path) -> None:
    graph = _graph("roles.just", tmp_path)

    assert graph.recipe("core-show-language-spec").parameters == ("language_spec",)
    assert graph.recipe("show-gates").parameters == ("recipes",)
    assert graph.recipe("harness-lint").parameters == ()
    assert graph.recipe("_internal-show-detail").private is True
    assert graph.recipe("harness-lint").private is False


def test_closure_runs_a_shared_dependency_once_in_run_order(tmp_path: Path) -> None:
    graph = _graph("diamond.just", tmp_path)

    assert [recipe.name for recipe in graph.closure("top-check")] == [
        "leaf-check-shared",
        "left-check-branch",
        "right-check-branch",
        "top-check",
    ]
    assert [recipe.name for recipe in graph.closure("left-check-branch")] == [
        "leaf-check-shared",
        "left-check-branch",
    ]


def test_runtime_class_is_the_slowest_in_the_closure(tmp_path: Path) -> None:
    graph = _graph("diamond.just", tmp_path)

    assert graph.runtime_class("leaf-check-shared") == "fast"
    assert graph.runtime_class("left-check-branch") == "medium"
    assert graph.runtime_class("top-check") == "slow"


def test_a_declared_runtime_class_cannot_understate_a_prerequisite(tmp_path: Path) -> None:
    graph = _graph("roles.just", tmp_path)

    assert graph.recipe("harness-coverage-diff").declared_runtime_classes == frozenset({"fast"})
    assert graph.runtime_class("harness-coverage-diff") == "slow"


def test_runtime_class_is_unclassified_only_when_nothing_declares_one(tmp_path: Path) -> None:
    graph = _graph("undeclared-runtime.just", tmp_path)

    assert graph.runtime_class("core-check-undeclared") == UNCLASSIFIED
    assert graph.runtime_class("core-check") == "medium"


def test_an_unknown_recipe_names_the_graph_it_is_missing_from(tmp_path: Path) -> None:
    graph = _graph("diamond.just", tmp_path)

    with pytest.raises(GateGraphError) as failure:
        graph.recipe("top-verify")

    assert "unknown recipe 'top-verify'" in str(failure.value)
    assert "top-check" in str(failure.value)


def test_a_directory_without_a_justfile_is_a_resolution_failure(tmp_path: Path) -> None:
    with pytest.raises(GateGraphError) as failure:
        load_graph(tmp_path)

    assert "not a file" in str(failure.value)


def test_the_repository_graph_resolves_every_recipe_it_declares() -> None:
    graph = load_graph(_REPO_ROOT)

    assert graph.source == _REPO_ROOT / "justfile"
    assert {"show-gates", "verify", "lint"} <= {recipe.name for recipe in graph.recipes}
    for recipe in graph.recipes:
        closure = graph.closure(recipe.name)
        assert closure[-1] is recipe
        assert len({resolved.name for resolved in closure}) == len(closure)
        assert (recipe.role == "aggregate") is (recipe.body == ())
