"""Docker-free tests for the verification-command graph resolver."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from reference_harness.gate_graph import GateGraphError, load_graph, parse_name


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


def test_role_follows_the_presence_of_a_command_body(
    gate_graph_dir: Callable[[str], Path],
) -> None:
    graph = load_graph(gate_graph_dir("roles.just"))

    assert graph.recipe("harness-check-dbfree").role == "aggregate"
    assert graph.recipe("harness-lint").role == "execution"
    assert graph.recipe("harness-coverage-diff").role == "execution"
    assert graph.recipe("harness-coverage-diff").dependencies == ("harness-test-db",)


def test_a_recipe_composing_nothing_is_an_empty_aggregate(
    gate_graph_dir: Callable[[str], Path],
) -> None:
    graph = load_graph(gate_graph_dir("roles.just"))

    empty = graph.recipe("harness-check-empty")
    assert empty.role == "aggregate"
    assert empty.dependencies == ()
    assert empty.body == ()


def test_groups_split_into_runtime_and_scheduling_classes(
    gate_graph_dir: Callable[[str], Path],
) -> None:
    graph = load_graph(gate_graph_dir("roles.just"))

    format_check = graph.recipe("harness-format-check")
    assert format_check.groups == frozenset({"fast", "dbfree"})
    assert format_check.declared_runtime_classes == frozenset({"fast"})
    assert format_check.scheduling_classes == frozenset({"dbfree"})
    assert graph.recipe("harness-lint").groups == frozenset()


def test_only_the_doc_attribute_describes_a_recipe(
    gate_graph_dir: Callable[[str], Path],
) -> None:
    graph = load_graph(gate_graph_dir("roles.just"))

    assert graph.recipe("harness-format-check").doc == "the description the resolver reports"
    assert graph.recipe("harness-lint").doc is None


def test_bodies_reproduce_variable_interpolation(
    gate_graph_dir: Callable[[str], Path],
) -> None:
    graph = load_graph(gate_graph_dir("roles.just"))

    assert graph.recipe("harness-lint").body == ("cd {{module}} && echo lint",)


def test_parameters_and_privacy_are_exposed(gate_graph_dir: Callable[[str], Path]) -> None:
    graph = load_graph(gate_graph_dir("roles.just"))

    assert graph.recipe("core-show-language-spec").parameters == ("language_spec",)
    assert graph.recipe("show-gates").parameters == ("recipes",)
    assert graph.recipe("harness-lint").parameters == ()
    assert graph.recipe("_internal-show-detail").private is True
    assert graph.recipe("harness-lint").private is False


def test_closure_runs_a_shared_dependency_once_in_run_order(
    gate_graph_dir: Callable[[str], Path],
) -> None:
    graph = load_graph(gate_graph_dir("diamond.just"))

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


def test_runtime_class_is_the_slowest_in_the_closure(
    gate_graph_dir: Callable[[str], Path],
) -> None:
    graph = load_graph(gate_graph_dir("diamond.just"))

    assert graph.runtime_class("leaf-check-shared") == "fast"
    assert graph.runtime_class("left-check-branch") == "medium"
    assert graph.runtime_class("top-check") == "slow"


def test_a_prerequisite_slower_than_the_declaration_is_reported_as_understated(
    gate_graph_dir: Callable[[str], Path],
) -> None:
    graph = load_graph(gate_graph_dir("roles.just"))

    assert graph.recipe("harness-coverage-diff").declared_runtime_classes == frozenset({"fast"})
    assert graph.runtime_class("harness-coverage-diff") == "slow"
    assert graph.understated_runtime_class("harness-coverage-diff") == "slow"


def test_a_declaration_covering_its_closure_understates_nothing(
    gate_graph_dir: Callable[[str], Path],
) -> None:
    graph = load_graph(gate_graph_dir("diamond.just"))

    assert graph.understated_runtime_class("left-check-branch") is None
    assert graph.understated_runtime_class("right-check-branch") is None
    assert graph.understated_runtime_class("top-check") is None


def test_runtime_class_is_absent_only_when_nothing_declares_one(
    gate_graph_dir: Callable[[str], Path],
) -> None:
    graph = load_graph(gate_graph_dir("undeclared-runtime.just"))

    assert graph.runtime_class("core-check-undeclared") is None
    assert graph.understated_runtime_class("core-check-undeclared") is None
    assert graph.runtime_class("core-check") == "medium"


def test_an_unknown_recipe_names_the_graph_it_is_missing_from(
    gate_graph_dir: Callable[[str], Path],
) -> None:
    graph = load_graph(gate_graph_dir("diamond.just"))

    with pytest.raises(GateGraphError) as failure:
        graph.recipe("top-verify")

    assert "unknown recipe 'top-verify'" in str(failure.value)
    assert "top-check" in str(failure.value)


def test_a_directory_without_a_justfile_is_a_resolution_failure(tmp_path: Path) -> None:
    with pytest.raises(GateGraphError) as failure:
        load_graph(tmp_path)

    assert "not a file" in str(failure.value)


def test_the_repository_graph_resolves_every_recipe_it_declares(repo_root: Path) -> None:
    graph = load_graph(repo_root)

    assert graph.source == repo_root / "justfile"
    assert {"show-gates", "verify", "lint"} <= {recipe.name for recipe in graph.recipes}
    for recipe in graph.recipes:
        closure = graph.closure(recipe.name)
        assert closure[-1] is recipe
        assert len({resolved.name for resolved in closure}) == len(closure)
        assert (recipe.role == "aggregate") is (recipe.body == ())
