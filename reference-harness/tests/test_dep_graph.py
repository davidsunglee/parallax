"""Unit tests for the module-dependency graph check + the Phase 12 coverage gate.

These are Docker-free: both the DAG check and the coverage gate are pure text /
filesystem functions. They guard two normative properties of the spec:

* the real ``dependency-graph.md`` is a legal DAG (acyclic, legal directions);
* every in-scope module (MVP / fast-follow / definitely-do, read from
  ``scope-and-tiers.md``) has at least one fixture tagged to it — the coverage
  gate that turns "the spec is complete for parity" into a passing check.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import yaml

from reference_harness.dep_graph_check import (
    _SLICE_TAG,
    check,
    coverage_errors,
    parse_edges,
    parse_in_scope_modules,
    parse_profile_claim,
    profile_errors,
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
    assert ("M14", "M8") in edges  # cross-process coherence is now a numbered edge


# --- a constructed cycle is rejected -----------------------------------------


def test_cycle_is_rejected() -> None:
    cyclic = "```dependency-graph\nM2 --> M1\nM1 --> M2\n```"
    errors = check(cyclic)
    assert any("not a DAG" in e for e in errors)


# --- the coverage gate over the real spec ------------------------------------


def test_real_spec_is_fully_covered() -> None:
    scope = (_SPEC_DIR / "scope-and-tiers.md").read_text(encoding="utf-8")
    assert coverage_errors(scope, _COMPATIBILITY_ROOT) == []


def test_in_scope_modules_match_the_numbered_graph() -> None:
    scope = (_SPEC_DIR / "scope-and-tiers.md").read_text(encoding="utf-8")
    graph = (_SPEC_DIR / "dependency-graph.md").read_text(encoding="utf-8")
    in_scope = parse_in_scope_modules(scope)
    graph_modules = {m for edge in parse_edges(graph) for m in edge}
    # Every numbered module in the graph is an in-scope tier (there is no
    # numbered module in the might-do / won't-do tiers); M6 does not exist.
    assert graph_modules <= in_scope
    assert "M14" in in_scope  # cross-process coherence, now a numbered module
    assert "M6" not in in_scope  # aggregation is folded into M2
    assert "coherence" not in in_scope  # retired: M14 is covered by its m14 tag


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


# --- the profile (conformance-slice) consistency gate, on synthetic inputs ----
#
# These mirror ``test_coverage_gate_fails_on_a_gap``: a synthetic slice claim plus
# a synthetic ``cases/`` tree, one failing assertion per gate dimension plus a
# clean pass. The real-corpus assertion lands in Phase 2.


def _synthetic_scope(
    modules: str = '["m1","m2"]',
    shapes: str = '["read","writeSequence"]',
    case_tags: str = '{ "include": ["first-implementation-mvp"] }',
) -> str:
    """A minimal scope-and-tiers.md carrying the slice heading + a json claim."""
    return textwrap.dedent(
        f"""\
        ## First-implementation Conformance Slice

        Some prose about the slice.

        ```json
        {{
          "schemaVersion": "1", "command": "describe", "status": "ok",
          "adapter": {{ "language": "reference", "name": "parallax-core", "version": "0.1.0" }},
          "capabilities": {{
            "modules": {modules},
            "dialects": ["postgres"],
            "caseShapes": {shapes},
            "caseTags": {case_tags},
            "commands": ["describe","compile","run"],
            "provisioning": "self-managed"
          }}
        }}
        ```

        Trailing prose.
        """
    )


def _write_case(cases_dir: Path, name: str, doc: dict) -> None:
    cases_dir.mkdir(parents=True, exist_ok=True)
    (cases_dir / name).write_text(yaml.safe_dump(doc), encoding="utf-8")


def _clean_read_case(tags: list[str]) -> dict:
    return {
        "model": "models/orders.yaml",
        "tags": tags,
        "operation": {"all": {}},
        "goldenSql": {"postgres": "select t0.id from orders t0"},
        "expectedRows": [{"id": 1}],
    }


def test_parse_profile_claim_extracts_the_embedded_claim() -> None:
    capabilities = parse_profile_claim(_synthetic_scope())
    assert capabilities["modules"] == ["m1", "m2"]
    assert capabilities["caseShapes"] == ["read", "writeSequence"]
    assert capabilities["caseTags"] == {"include": ["first-implementation-mvp"]}


def test_profile_gate_passes_on_a_consistent_slice(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    _write_case(cases, "0001.yaml", _clean_read_case(["m1", "first-implementation-mvp"]))
    _write_case(cases, "0002.yaml", _clean_read_case(["m2", "first-implementation-mvp"]))
    # an untagged case with a stray module must be ignored entirely.
    _write_case(cases, "0003.yaml", _clean_read_case(["m99", "other"]))
    assert profile_errors(_synthetic_scope(), tmp_path) == []


def test_profile_gate_requires_the_canonical_single_include_tag(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    _write_case(cases, "0001.yaml", _clean_read_case(["m1", "first-implementation-mvp"]))
    _write_case(cases, "0002.yaml", _clean_read_case(["m2", "first-implementation-mvp"]))

    for case_tags in (
        "{}",
        '{ "include": ["renamed-slice"] }',
        '{ "include": ["first-implementation-mvp", "extra-slice"] }',
    ):
        errors = profile_errors(_synthetic_scope(case_tags=case_tags), tmp_path)
        assert any("caseTags.include" in e and _SLICE_TAG in e for e in errors)


def test_profile_gate_fails_when_a_claimed_module_is_uncovered(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    # only m1 is carried; the claim also lists m2 -> m2 is uncovered.
    _write_case(cases, "0001.yaml", _clean_read_case(["m1", "first-implementation-mvp"]))
    errors = profile_errors(_synthetic_scope(), tmp_path)
    assert any("m2" in e and "no tagged case" in e for e in errors)


def test_profile_gate_fails_on_a_stray_module_tag(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    _write_case(cases, "0001.yaml", _clean_read_case(["m1", "first-implementation-mvp"]))
    # m9 is on a tagged case but not in the claim's modules.
    _write_case(cases, "0002.yaml", _clean_read_case(["m2", "m9", "first-implementation-mvp"]))
    errors = profile_errors(_synthetic_scope(), tmp_path)
    assert any("0002.yaml" in e and "'m9'" in e for e in errors)


def test_profile_gate_fails_on_a_shape_outside_the_claim(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    _write_case(cases, "0001.yaml", _clean_read_case(["m1", "first-implementation-mvp"]))
    _write_case(cases, "0002.yaml", _clean_read_case(["m2", "first-implementation-mvp"]))
    # a conflict-shaped tagged case while the claim allows only read/writeSequence.
    _write_case(
        cases,
        "0003.yaml",
        {
            "model": "models/account.yaml",
            "tags": ["m2", "first-implementation-mvp"],
            "expectedAffectedRows": 0,
            "goldenSql": {"postgres": "update account set balance = ? where id = ?"},
        },
    )
    errors = profile_errors(_synthetic_scope(), tmp_path)
    assert any("0003.yaml" in e and "conflict" in e and "outside" in e for e in errors)


def test_profile_gate_fails_on_a_missing_postgres_golden(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    _write_case(cases, "0001.yaml", _clean_read_case(["m1", "first-implementation-mvp"]))
    no_golden = _clean_read_case(["m2", "first-implementation-mvp"])
    no_golden["goldenSql"] = {"mariadb": "select t0.id from orders t0"}
    _write_case(cases, "0002.yaml", no_golden)
    errors = profile_errors(_synthetic_scope(), tmp_path)
    assert any("0002.yaml" in e and "Postgres golden" in e for e in errors)


def test_profile_gate_fails_on_an_excluded_tag_when_the_claim_lists_exclude(
    tmp_path: Path,
) -> None:
    cases = tmp_path / "cases"
    _write_case(cases, "0001.yaml", _clean_read_case(["m1", "first-implementation-mvp"]))
    _write_case(
        cases,
        "0002.yaml",
        _clean_read_case(["m2", "aggregate", "first-implementation-mvp"]),
    )
    scope = _synthetic_scope(
        case_tags='{ "include": ["first-implementation-mvp"], "exclude": ["aggregate"] }'
    )
    errors = profile_errors(scope, tmp_path)
    assert any("0002.yaml" in e and "excluded" in e and "aggregate" in e for e in errors)


def test_profile_gate_accepts_a_scenario_with_per_step_golden(tmp_path: Path) -> None:
    # The scenario shape (0607) carries Postgres golden SQL per step, not at the
    # top level; the shape-aware golden check must accept it.
    cases = tmp_path / "cases"
    _write_case(cases, "0001.yaml", _clean_read_case(["m1", "first-implementation-mvp"]))
    _write_case(
        cases,
        "0002.yaml",
        {
            "model": "models/account.yaml",
            "tags": ["m2", "m8", "first-implementation-mvp"],
            "roundTrips": 2,
            "scenario": [
                {
                    "write": "insert",
                    "goldenSql": {"postgres": "insert into account(id) values (?)"},
                    "binds": [7],
                },
                {
                    "find": {"eq": {"attr": "Account.id", "value": 7}},
                    "goldenSql": {"postgres": "select t0.id from account t0 where t0.id = ?"},
                    "binds": [7],
                    "expectRows": [{"id": 7}],
                },
            ],
        },
    )
    scope = _synthetic_scope(
        modules='["m1","m2","m8"]',
        shapes='["read","writeSequence","scenario"]',
    )
    assert profile_errors(scope, tmp_path) == []


# --- the profile gate over the real corpus -----------------------------------
#
# The real-corpus assertions: the family-selected cases are internally
# consistent with the canonical claim, and exactly 99 cases carry the slice tag
# (a drift tripwire — adding or losing a tagged case fails the count). The count
# rose from 97 to 99 when the temporal deep-fetch cases 0335/0336 were added to
# the corpus.


def test_real_corpus_profile_is_consistent() -> None:
    scope = (_SPEC_DIR / "scope-and-tiers.md").read_text(encoding="utf-8")
    assert profile_errors(scope, _COMPATIBILITY_ROOT) == []


def test_profile_slice_tag_count() -> None:
    cases_dir = _COMPATIBILITY_ROOT / "cases"
    tagged = []
    for path in sorted(cases_dir.glob("**/*.yaml")) + sorted(cases_dir.glob("**/*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            continue
        tags = [t for t in doc.get("tags", []) if isinstance(t, str)]
        if _SLICE_TAG in tags:
            tagged.append(path.name)
    assert len(tagged) == 99, (
        f"expected exactly 99 cases tagged {_SLICE_TAG!r}, found {len(tagged)}: {sorted(tagged)}"
    )
