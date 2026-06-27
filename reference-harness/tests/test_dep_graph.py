"""Unit tests for the module-dependency graph check + the Phase 12 coverage gate.

These are Docker-free: both the DAG check and the coverage gate are pure text /
filesystem functions. They guard two normative properties of the spec:

* the real ``dependency-graph.md`` is a legal DAG (acyclic, legal directions);
* every in-scope module (MVP / fast-follow / definitely-do, read from
  ``scope-and-tiers.md``) has at least one fixture tagged to it — the coverage
  gate that turns "the spec is complete for parity" into a passing check.
"""

from __future__ import annotations

from pathlib import Path

from reference_harness.dep_graph_check import (
    check,
    coverage_errors,
    parse_edges,
    parse_in_scope_modules,
)

# reference-harness/tests/ -> reference-harness/ -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC_DIR = _REPO_ROOT / "core" / "spec"
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"


# --- the real dependency graph is a legal DAG --------------------------------


def test_real_dependency_graph_is_a_legal_dag() -> None:
    markdown = (_SPEC_DIR / "dependency-graph.md").read_text(encoding="utf-8")
    assert check(markdown) == []
    edges = parse_edges(markdown)
    assert ("M3", "M2") in edges  # sanity: a known edge is present
    assert ("M4", "M5") in edges  # the "surprising" direction is declared


# --- a constructed cycle is rejected -----------------------------------------


def test_cycle_is_rejected() -> None:
    cyclic = "```dependency-graph\nM2 --> M1\nM1 --> M2\n```"
    errors = check(cyclic)
    assert any("not a DAG" in e for e in errors)


# --- the coverage gate over the real spec ------------------------------------


def test_real_spec_is_fully_covered() -> None:
    scope = (_SPEC_DIR / "scope-and-tiers.md").read_text(encoding="utf-8")
    assert coverage_errors(scope, _COMPATIBILITY_ROOT) == []


def test_in_scope_modules_match_the_numbered_graph_plus_coherence() -> None:
    scope = (_SPEC_DIR / "scope-and-tiers.md").read_text(encoding="utf-8")
    graph = (_SPEC_DIR / "dependency-graph.md").read_text(encoding="utf-8")
    in_scope = parse_in_scope_modules(scope)
    graph_modules = {m for edge in parse_edges(graph) for m in edge}
    # Every numbered module in the graph is an in-scope tier (there is no
    # numbered module in the might-do / won't-do tiers); M6 does not exist.
    assert graph_modules <= in_scope
    assert "coherence" in in_scope  # the un-numbered fast-follow capability
    assert "M6" not in in_scope  # aggregation is folded into M2


# --- the gate FAILS when an in-scope module is uncovered ---------------------


def test_coverage_gate_fails_on_a_gap() -> None:
    scope = (
        "### MVP\n"
        "- **M0** core conventions\n"
        "- **M99** a module with no fixtures\n"
        "### Won't-do (round 1)\n"
        "- something out of scope\n"
    )
    errors = coverage_errors(scope, _COMPATIBILITY_ROOT)
    assert any("M99" in e for e in errors)
    # M0 IS covered by a real fixture, so it must not be reported as a gap.
    assert not any("M0" in e for e in errors)


def test_might_do_and_wont_do_tiers_are_excluded_from_the_gate() -> None:
    # A module mentioned ONLY under might-do / won't-do is not in scope, so even
    # with zero fixtures it does not fail the gate.
    scope = (
        "### MVP\n"
        "- **M2** operation algebra\n"
        "### Might-do\n"
        "- **M98** an optional, uncovered module\n"
        "### Won't-do (round 1)\n"
        "- **M97** an excluded, uncovered module\n"
    )
    in_scope = parse_in_scope_modules(scope)
    assert "M98" not in in_scope
    assert "M97" not in in_scope
    assert coverage_errors(scope, _COMPATIBILITY_ROOT) == []
