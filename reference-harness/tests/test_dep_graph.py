"""Unit tests for the module-dependency graph check + the catalog coverage gate.

These are Docker-free: the DAG check, the catalog coverage gate, and the profile
gate are pure text / filesystem functions. They guard the normative properties of
the spec:

* the real ``modules.md`` is a legal DAG (acyclic, legal directions);
* every ``active`` module whose coverage source is ``cases`` (read from the
  ``modules.md`` catalog table) has at least one fixture tagged to it;
* no ``active`` module depends on a ``deferred`` one;
* the ``slice-mvp-1`` slice is consistent with its canonical claim in ``slices.md``.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import yaml

from reference_harness.dep_graph_check import (
    _SLICE_TAG,
    active_deferred_edge_errors,
    check,
    coverage_errors,
    gated_modules,
    parse_catalog,
    parse_edges,
    parse_profile_claim,
    profile_errors,
)

# reference-harness/tests/ -> reference-harness/ -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC_DIR = _REPO_ROOT / "core" / "spec"
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"


# --- the real dependency graph is a legal DAG --------------------------------


def test_real_dependency_graph_is_a_legal_dag() -> None:
    markdown = (_SPEC_DIR / "modules.md").read_text(encoding="utf-8")
    assert check(markdown) == []
    edges = parse_edges(markdown)
    assert ("m-sql", "m-op-algebra") in edges  # sanity: a known edge is present
    assert ("m-deep-fetch", "m-navigate") in edges  # the "surprising" direction is declared
    assert ("m-coherence", "m-process-cache") in edges  # coherence keeps caches coherent


def test_cycle_is_rejected() -> None:
    cyclic = (
        "```dependency-graph\nm-op-algebra --> m-descriptor\nm-descriptor --> m-op-algebra\n```"
    )
    errors = check(cyclic)
    assert any("not a DAG" in e for e in errors)


# --- the module catalog table -------------------------------------------------


def _catalog_md(rows: list[tuple[str, str, str]], edges: list[str] | None = None) -> str:
    """A minimal modules.md carrying the catalog table (and optional fenced graph)."""
    lines = [
        "## The module catalog",
        "",
        "Intro prose the parser skips.",
        "",
        "| Module | Summary | Status | Coverage |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| `{module}` | some behavior | {status} | {coverage} |"
        for module, status, coverage in rows
    ]
    lines += ["", "## The dependency graph", ""]
    if edges is not None:
        lines += ["```dependency-graph", *edges, "```"]
    return "\n".join(lines) + "\n"


def test_parse_catalog_reads_status_and_coverage() -> None:
    catalog = parse_catalog(
        _catalog_md([("m-core", "active", "cases"), ("m-agg", "deferred", "cases")])
    )
    assert catalog["m-core"] == {"status": "active", "coverage": "cases"}
    assert catalog["m-agg"] == {"status": "deferred", "coverage": "cases"}


def test_real_catalog_matches_the_graph() -> None:
    markdown = (_SPEC_DIR / "modules.md").read_text(encoding="utf-8")
    catalog = parse_catalog(markdown)
    graph_modules = {m for edge in parse_edges(markdown) for m in edge}
    # The catalog table and the dependency graph list exactly the same modules.
    assert graph_modules == set(catalog)
    assert catalog["m-db-port"]["coverage"] == "contract"  # the sole contract-covered module
    assert catalog["m-agg"]["status"] == "deferred"  # aggregation is deferred
    assert catalog["m-core"]["status"] == "active"


# --- the coverage gate over the real spec ------------------------------------


def test_real_spec_is_fully_covered() -> None:
    markdown = (_SPEC_DIR / "modules.md").read_text(encoding="utf-8")
    assert coverage_errors(markdown, _COMPATIBILITY_ROOT) == []


def test_real_spec_has_no_active_to_deferred_edge() -> None:
    markdown = (_SPEC_DIR / "modules.md").read_text(encoding="utf-8")
    assert active_deferred_edge_errors(markdown) == []


# --- the coverage gate FAILS when an active/cases module is uncovered ---------


def test_coverage_gate_fails_on_a_gap() -> None:
    markdown = _catalog_md([("m-core", "active", "cases"), ("m-nonexistent", "active", "cases")])
    errors = coverage_errors(markdown, _COMPATIBILITY_ROOT)
    assert any("m-nonexistent" in e for e in errors)
    # m-core IS covered by a real fixture, so it must not be reported as a gap.
    assert not any("m-core" in e for e in errors)


def test_deferred_and_contract_modules_are_excluded_from_the_gate() -> None:
    # A `deferred` module and a `contract`-covered module are not gated, so even
    # with zero fixtures they do not fail the coverage gate.
    markdown = _catalog_md(
        [
            ("m-op-algebra", "active", "cases"),
            ("m-ghost-deferred", "deferred", "cases"),
            ("m-ghost-port", "active", "contract"),
        ]
    )
    catalog = parse_catalog(markdown)
    assert gated_modules(catalog) == ["m-op-algebra"]
    assert coverage_errors(markdown, _COMPATIBILITY_ROOT) == []


# --- the active -> deferred rule ---------------------------------------------


def test_active_to_deferred_edge_is_rejected() -> None:
    markdown = _catalog_md(
        [("m-op-algebra", "active", "cases"), ("m-agg", "deferred", "cases")],
        edges=["m-op-algebra --> m-agg"],
    )
    errors = active_deferred_edge_errors(markdown)
    assert any("m-op-algebra" in e and "m-agg" in e for e in errors)


def test_deferred_to_active_edge_is_allowed() -> None:
    markdown = _catalog_md(
        [("m-op-algebra", "active", "cases"), ("m-agg", "deferred", "cases")],
        edges=["m-agg --> m-op-algebra"],
    )
    assert active_deferred_edge_errors(markdown) == []


# --- the profile (conformance-slice) consistency gate, on synthetic inputs ----
#
# A synthetic slice claim plus a synthetic ``cases/`` tree, one failing assertion
# per gate dimension plus a clean pass.


def _synthetic_slices(
    modules: str = '["m-core","m-op-algebra"]',
    shapes: str = '["read","writeSequence"]',
    case_tags: str = '{ "include": ["slice-mvp-1"] }',
) -> str:
    """A minimal slices.md carrying the slice heading + a json claim."""
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
    capabilities = parse_profile_claim(_synthetic_slices())
    assert capabilities["modules"] == ["m-core", "m-op-algebra"]
    assert capabilities["caseShapes"] == ["read", "writeSequence"]
    assert capabilities["caseTags"] == {"include": ["slice-mvp-1"]}


def test_profile_gate_passes_on_a_consistent_slice(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    _write_case(cases, "m-op-algebra-001.yaml", _clean_read_case(["m-core", "slice-mvp-1"]))
    _write_case(cases, "m-op-algebra-002.yaml", _clean_read_case(["m-op-algebra", "slice-mvp-1"]))
    # an untagged case with a stray module must be ignored entirely.
    _write_case(cases, "m-core-001.yaml", _clean_read_case(["m-ghost", "other"]))
    assert profile_errors(_synthetic_slices(), tmp_path) == []


def test_profile_gate_requires_the_canonical_single_include_tag(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    _write_case(cases, "m-op-algebra-001.yaml", _clean_read_case(["m-core", "slice-mvp-1"]))
    _write_case(cases, "m-op-algebra-002.yaml", _clean_read_case(["m-op-algebra", "slice-mvp-1"]))

    for case_tags in (
        "{}",
        '{ "include": ["renamed-slice"] }',
        '{ "include": ["slice-mvp-1", "extra-slice"] }',
    ):
        errors = profile_errors(_synthetic_slices(case_tags=case_tags), tmp_path)
        assert any("caseTags.include" in e and _SLICE_TAG in e for e in errors)


def test_profile_gate_fails_when_a_claimed_module_is_uncovered(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    # only m-core is carried; the claim also lists m-op-algebra -> uncovered.
    _write_case(cases, "m-op-algebra-001.yaml", _clean_read_case(["m-core", "slice-mvp-1"]))
    errors = profile_errors(_synthetic_slices(), tmp_path)
    assert any("m-op-algebra" in e and "no tagged case" in e for e in errors)


def test_profile_gate_fails_on_a_stray_module_tag(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    _write_case(cases, "m-op-algebra-001.yaml", _clean_read_case(["m-core", "slice-mvp-1"]))
    # m-detach is on a tagged case but not in the claim's modules.
    _write_case(
        cases,
        "m-op-algebra-002.yaml",
        _clean_read_case(["m-op-algebra", "m-detach", "slice-mvp-1"]),
    )
    errors = profile_errors(_synthetic_slices(), tmp_path)
    assert any("m-op-algebra-002.yaml" in e and "'m-detach'" in e for e in errors)


def test_profile_gate_fails_on_a_shape_outside_the_claim(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    _write_case(cases, "m-op-algebra-001.yaml", _clean_read_case(["m-core", "slice-mvp-1"]))
    _write_case(cases, "m-op-algebra-002.yaml", _clean_read_case(["m-op-algebra", "slice-mvp-1"]))
    # a conflict-shaped tagged case while the claim allows only read/writeSequence.
    _write_case(
        cases,
        "m-core-001.yaml",
        {
            "model": "models/account.yaml",
            "tags": ["m-op-algebra", "slice-mvp-1"],
            "expectedAffectedRows": 0,
            "goldenSql": {"postgres": "update account set balance = ? where id = ?"},
        },
    )
    errors = profile_errors(_synthetic_slices(), tmp_path)
    assert any("m-core-001.yaml" in e and "conflict" in e and "outside" in e for e in errors)


def test_profile_gate_fails_on_a_missing_postgres_golden(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    _write_case(cases, "m-op-algebra-001.yaml", _clean_read_case(["m-core", "slice-mvp-1"]))
    no_golden = _clean_read_case(["m-op-algebra", "slice-mvp-1"])
    no_golden["goldenSql"] = {"mariadb": "select t0.id from orders t0"}
    _write_case(cases, "m-op-algebra-002.yaml", no_golden)
    errors = profile_errors(_synthetic_slices(), tmp_path)
    assert any("m-op-algebra-002.yaml" in e and "Postgres golden" in e for e in errors)


def test_profile_gate_fails_on_an_excluded_tag_when_the_claim_lists_exclude(
    tmp_path: Path,
) -> None:
    cases = tmp_path / "cases"
    _write_case(cases, "m-op-algebra-001.yaml", _clean_read_case(["m-core", "slice-mvp-1"]))
    _write_case(
        cases,
        "m-op-algebra-002.yaml",
        _clean_read_case(["m-op-algebra", "aggregate", "slice-mvp-1"]),
    )
    slices = _synthetic_slices(case_tags='{ "include": ["slice-mvp-1"], "exclude": ["aggregate"] }')
    errors = profile_errors(slices, tmp_path)
    assert any(
        "m-op-algebra-002.yaml" in e and "excluded" in e and "aggregate" in e for e in errors
    )


def test_profile_gate_accepts_a_scenario_with_per_step_golden(tmp_path: Path) -> None:
    # The scenario shape carries Postgres golden SQL per step, not at the top
    # level; the shape-aware golden check must accept it.
    cases = tmp_path / "cases"
    _write_case(cases, "m-op-algebra-001.yaml", _clean_read_case(["m-core", "slice-mvp-1"]))
    _write_case(
        cases,
        "m-op-algebra-002.yaml",
        {
            "model": "models/account.yaml",
            "tags": ["m-core", "m-op-algebra", "m-unit-work", "slice-mvp-1"],
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
    slices = _synthetic_slices(
        modules='["m-core","m-op-algebra","m-unit-work"]',
        shapes='["read","writeSequence","scenario"]',
    )
    assert profile_errors(slices, tmp_path) == []


# --- the profile gate over the real corpus -----------------------------------
#
# The family-selected cases are internally consistent with the canonical claim,
# and exactly 123 cases carry the slice tag (a drift tripwire — adding or losing a
# tagged case fails the count). The cutover to the slugged catalog preserved
# slice membership exactly; only the claim vocabulary changed.


def test_real_corpus_profile_is_consistent() -> None:
    slices = (_SPEC_DIR / "slices.md").read_text(encoding="utf-8")
    assert profile_errors(slices, _COMPATIBILITY_ROOT) == []


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
    assert len(tagged) == 123, (
        f"expected exactly 123 cases tagged {_SLICE_TAG!r}, found {len(tagged)}: {sorted(tagged)}"
    )
