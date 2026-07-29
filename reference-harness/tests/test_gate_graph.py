"""Docker-free tests for the verification-command graph resolver."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from reference_harness.gate_graph import (
    GateGraph,
    GateGraphError,
    RecipeName,
    load_graph,
    parse_name,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("check", RecipeName(None, "check", None)),
        ("check-dbfree", RecipeName(None, "check", "dbfree")),
        ("show-gates", RecipeName(None, "show", "gates")),
        ("report-matrix", RecipeName(None, "report", "matrix")),
        ("lint-markdown", RecipeName(None, "lint", "markdown")),
        ("harness-format-check", RecipeName("harness", "format-check", None)),
        ("harness-format", RecipeName("harness", "format", None)),
        ("python-check-dbfree", RecipeName("python", "check", "dbfree")),
        ("python-test-provider-contract", RecipeName("python", "test", "provider-contract")),
        ("core-check-slice-profiles", RecipeName("core", "check", "slice-profiles")),
        ("harness-test-contract-tools", RecipeName("harness", "test", "contract-tools")),
        # Deliberately not repository recipes: a name outside the grammar must still
        # decompose, so the caller reports what it found rather than failing to read
        # the graph containing it.
        ("smoke", RecipeName(None, "smoke", None)),
        ("python-smoke", RecipeName("python", "smoke", None)),
        ("core-model-sweep", RecipeName("core", "model-sweep", None)),
        ("core-graph-check", RecipeName("core", "graph-check", None)),
        ("java-typecheck", RecipeName("java", "typecheck", None)),
    ],
)
def test_names_decompose_into_scope_operation_and_qualifier(
    name: str, expected: RecipeName
) -> None:
    parsed = parse_name(name)

    assert parsed == expected


def test_role_follows_the_presence_of_a_command_body(
    gate_graph: Callable[[str], GateGraph],
) -> None:
    graph = gate_graph("roles.just")

    assert graph.recipe("harness-check-dbfree").role == "aggregate"
    assert graph.recipe("harness-lint").role == "execution"
    assert graph.recipe("harness-coverage-diff").role == "execution"
    assert graph.recipe("harness-coverage-diff").dependencies == ("harness-test-db",)


def test_a_recipe_composing_nothing_is_an_empty_aggregate(
    gate_graph: Callable[[str], GateGraph],
) -> None:
    graph = gate_graph("roles.just")

    empty = graph.recipe("harness-check-empty")
    assert empty.role == "aggregate"
    assert empty.dependencies == ()
    assert empty.body == ()


def test_metadata_splits_into_runtime_and_scheduling_classes(
    gate_graph: Callable[[str], GateGraph],
) -> None:
    graph = gate_graph("roles.just")

    format_check = graph.recipe("harness-format-check")
    assert format_check.metadata == ("runtime:fast", "scheduling:dbfree")
    assert format_check.declared_runtime_classes == frozenset({"fast"})
    assert format_check.declared_scheduling_classes == frozenset({"dbfree"})
    assert graph.recipe("harness-lint").metadata == ()
    assert graph.recipe("harness-lint").declared_runtime_classes == frozenset()
    assert graph.recipe("harness-lint").declared_scheduling_classes == frozenset()


def test_a_group_declares_no_class(gate_graph: Callable[[str], GateGraph]) -> None:
    graph = gate_graph("roles.just")

    format_check = graph.recipe("harness-format-check")
    assert "slow" not in format_check.metadata
    assert format_check.declared_runtime_classes == frozenset({"fast"})
    assert graph.resolve("harness-format-check").runtime_class == "fast"


def test_repeated_metadata_attributes_accumulate(
    gate_graph: Callable[[str], GateGraph],
) -> None:
    graph = gate_graph("roles.just")

    assert graph.recipe("harness-audit").declared_runtime_classes == frozenset({"fast", "slow"})


def test_only_the_doc_attribute_describes_a_recipe(
    gate_graph: Callable[[str], GateGraph],
) -> None:
    graph = gate_graph("roles.just")

    assert graph.recipe("harness-format-check").doc == "the description the resolver reports"
    assert graph.recipe("harness-lint").doc is None


def test_bodies_reproduce_variable_interpolation(
    gate_graph: Callable[[str], GateGraph],
) -> None:
    graph = gate_graph("roles.just")

    assert graph.recipe("harness-lint").body == ("cd {{module}} && echo lint",)


def test_parameters_and_privacy_are_exposed(gate_graph: Callable[[str], GateGraph]) -> None:
    graph = gate_graph("roles.just")

    assert graph.recipe("core-show-language-spec").parameters == ("language_spec",)
    assert graph.recipe("show-gates").parameters == ("recipes",)
    assert graph.recipe("harness-lint").parameters == ()
    assert graph.recipe("_internal-show-detail").private is True
    assert graph.recipe("harness-lint").private is False


def test_closure_runs_a_shared_dependency_once_in_run_order(
    gate_graph: Callable[[str], GateGraph],
) -> None:
    graph = gate_graph("diamond.just")

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


def test_execution_owners_exclude_the_aggregates_that_compose_them(
    gate_graph: Callable[[str], GateGraph],
) -> None:
    graph = gate_graph("diamond.just")

    assert graph.resolve("top-check").execution_owners == (
        "leaf-check-shared",
        "left-check-branch",
        "right-check-branch",
    )


def test_runtime_class_is_the_slowest_in_the_closure(
    gate_graph: Callable[[str], GateGraph],
) -> None:
    graph = gate_graph("diamond.just")

    assert graph.resolve("leaf-check-shared").runtime_class == "fast"
    assert graph.resolve("left-check-branch").runtime_class == "medium"
    assert graph.resolve("top-check").runtime_class == "slow"


def test_a_prerequisite_slower_than_the_declaration_is_reported_as_understated(
    gate_graph: Callable[[str], GateGraph],
) -> None:
    graph = gate_graph("roles.just")

    resolved = graph.resolve("harness-coverage-diff")
    assert resolved.recipe.declared_runtime_classes == frozenset({"fast"})
    assert resolved.runtime_class == "slow"
    assert resolved.understated_runtime_class == "slow"


def test_the_fastest_of_several_declarations_decides_understatement(
    gate_graph: Callable[[str], GateGraph],
) -> None:
    graph = gate_graph("roles.just")

    resolved = graph.resolve("harness-audit")
    assert resolved.runtime_class == "slow"
    assert resolved.understated_runtime_class == "slow"


def test_a_declaration_covering_its_closure_understates_nothing(
    gate_graph: Callable[[str], GateGraph],
) -> None:
    graph = gate_graph("diamond.just")

    assert graph.resolve("left-check-branch").understated_runtime_class is None
    assert graph.resolve("right-check-branch").understated_runtime_class is None
    assert graph.resolve("top-check").understated_runtime_class is None


def test_runtime_class_is_absent_only_when_nothing_declares_one(
    gate_graph: Callable[[str], GateGraph],
) -> None:
    graph = gate_graph("undeclared-runtime.just")

    undeclared = graph.resolve("core-check-undeclared")
    assert undeclared.runtime_class is None
    assert undeclared.understated_runtime_class is None
    assert graph.resolve("core-check").runtime_class == "medium"


def test_an_unknown_recipe_names_the_graph_it_is_missing_from(
    gate_graph: Callable[[str], GateGraph],
) -> None:
    graph = gate_graph("diamond.just")

    with pytest.raises(GateGraphError) as failure:
        graph.recipe("top-verify")

    assert "unknown recipe 'top-verify'" in str(failure.value)
    assert "top-check" in str(failure.value)


def test_a_directory_without_a_justfile_is_a_resolution_failure(tmp_path: Path) -> None:
    with pytest.raises(GateGraphError) as failure:
        load_graph(tmp_path)

    assert "not a file" in str(failure.value)


def test_the_repository_graph_resolves_every_recipe_it_declares(
    repository_graph: GateGraph, repo_root: Path
) -> None:
    assert repository_graph.source == repo_root / "justfile"
    assert {"check", "check-dbfree", "check-db", "show-gates"} <= {
        recipe.name for recipe in repository_graph.recipes
    }
    for recipe in repository_graph.recipes:
        closure = repository_graph.closure(recipe.name)
        assert closure[-1] is recipe
        assert len({resolved.name for resolved in closure}) == len(closure)
        assert (recipe.role == "aggregate") is (recipe.body == ())
