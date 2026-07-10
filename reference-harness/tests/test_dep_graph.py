"""Unit tests for the module-dependency graph check + the catalog coverage gate.

These are Docker-free: the DAG check, the catalog coverage gate, and the profile
gate are pure text / filesystem functions. They guard the normative properties of
the spec:

* the real ``modules.md`` is a legal DAG (acyclic, legal directions);
* every ``active`` module whose coverage source is ``cases`` (read from the
  ``modules.md`` catalog table) has at least one fixture tagged to it;
* no ``active`` module depends on a ``deferred`` one;
* every Conformance Slice is consistent with its canonical claim in
  ``slices.md``, and no case carries a slice tag with no claim.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from reference_harness.dep_graph_check import (
    DepGraphFailure,
    active_deferred_edge_errors,
    catalog_graph_consistency_errors,
    check,
    coverage_errors,
    gated_modules,
    parse_catalog,
    parse_edges,
    parse_profile_claims,
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


def test_parse_catalog_rejects_an_unknown_status() -> None:
    # A typo'd status must fail loudly, not silently drop the module out of the
    # gated set (which would let an uncovered module pass the coverage gate).
    with pytest.raises(DepGraphFailure, match="unknown status 'activ'"):
        parse_catalog(_catalog_md([("m-core", "activ", "cases")]))


def test_parse_catalog_rejects_an_unknown_coverage() -> None:
    with pytest.raises(DepGraphFailure, match="unknown coverage 'case'"):
        parse_catalog(_catalog_md([("m-core", "active", "case")]))


def test_catalog_graph_consistency_flags_an_edged_but_uncatalogued_module() -> None:
    # m-ghost is edged but absent from the catalog: the coverage and
    # active->deferred gates key off the catalog, so without this check it would
    # slip past them (its status resolves to None).
    markdown = _catalog_md(
        [("m-core", "active", "cases")],
        edges=["m-ghost --> m-core"],
    )
    errors = catalog_graph_consistency_errors(markdown)
    assert any("m-ghost" in e and "not the catalog" in e for e in errors)


def test_catalog_graph_consistency_flags_a_catalogued_but_unedged_module() -> None:
    markdown = _catalog_md(
        [
            ("m-core", "active", "cases"),
            ("m-descriptor", "active", "cases"),
            ("m-orphan", "active", "cases"),
        ],
        edges=["m-descriptor --> m-core"],
    )
    errors = catalog_graph_consistency_errors(markdown)
    # m-orphan is the only mismatch: the two edged modules are both catalogued.
    assert errors == ["module m-orphan is catalogued but never appears in the DAG"]


def test_real_catalog_and_graph_are_consistent() -> None:
    markdown = (_SPEC_DIR / "modules.md").read_text(encoding="utf-8")
    assert catalog_graph_consistency_errors(markdown) == []


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


def _claim_block(
    modules: str = '["m-core","m-op-algebra"]',
    shapes: str = '["read","writeSequence"]',
    case_tags: str = '{ "include": ["slice-mvp-1"] }',
) -> str:
    return textwrap.dedent(
        f"""\
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
        """
    )


def _synthetic_slices(
    modules: str = '["m-core","m-op-algebra"]',
    shapes: str = '["read","writeSequence"]',
    case_tags: str = '{ "include": ["slice-mvp-1"] }',
    extra_claims: str = "",
) -> str:
    """A minimal slices.md: a heading, one json claim, optional extra claims."""
    return (
        "## Some Conformance Slice\n\nSome prose about the slice.\n\n"
        + _claim_block(modules, shapes, case_tags)
        + "\nTrailing prose.\n"
        + extra_claims
    )


def _write_case(cases_dir: Path, name: str, doc: dict) -> None:
    cases_dir.mkdir(parents=True, exist_ok=True)
    (cases_dir / name).write_text(yaml.safe_dump(doc), encoding="utf-8")


def _clean_read_case(tags: list[str]) -> dict:
    return {
        "model": "models/orders.yaml",
        "tags": tags,
        "shape": "read",
        "when": {"operation": {"all": {}}},
        "then": {
            "statements": [{"sql": {"postgres": "select t0.id from orders t0"}}],
            "rows": [{"id": 1}],
        },
    }


def test_parse_profile_claims_extracts_every_embedded_claim() -> None:
    claims = parse_profile_claims(_synthetic_slices())
    assert list(claims) == ["slice-mvp-1"]
    assert claims["slice-mvp-1"]["modules"] == ["m-core", "m-op-algebra"]
    assert claims["slice-mvp-1"]["caseShapes"] == ["read", "writeSequence"]


def test_parse_profile_claims_keys_multiple_claims_by_slice_tag() -> None:
    two = _synthetic_slices(extra_claims=_claim_block(case_tags='{ "include": ["slice-other-1"] }'))
    claims = parse_profile_claims(two)
    assert sorted(claims) == ["slice-mvp-1", "slice-other-1"]


def test_parse_profile_claims_rejects_duplicate_slice_tags() -> None:
    dupe = _synthetic_slices(extra_claims=_claim_block())
    with pytest.raises(DepGraphFailure, match="same tag"):
        parse_profile_claims(dupe)


def test_profile_gate_passes_on_a_consistent_slice(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    _write_case(cases, "m-op-algebra-001.yaml", _clean_read_case(["m-core", "slice-mvp-1"]))
    _write_case(cases, "m-op-algebra-002.yaml", _clean_read_case(["m-op-algebra", "slice-mvp-1"]))
    # an untagged case with a stray module must be ignored entirely.
    _write_case(cases, "m-core-001.yaml", _clean_read_case(["m-ghost", "other"]))
    assert profile_errors(_synthetic_slices(), tmp_path) == []


def test_profile_gate_requires_a_single_wellformed_include_tag(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    _write_case(cases, "m-op-algebra-001.yaml", _clean_read_case(["m-core", "slice-mvp-1"]))
    _write_case(cases, "m-op-algebra-002.yaml", _clean_read_case(["m-op-algebra", "slice-mvp-1"]))

    for case_tags in (
        "{}",
        '{ "include": ["renamed-slice"] }',
        '{ "include": ["slice-mvp-1", "slice-extra-1"] }',
    ):
        errors = profile_errors(_synthetic_slices(case_tags=case_tags), tmp_path)
        assert any("caseTags.include" in e for e in errors)


def test_profile_gate_fails_on_a_slice_tag_with_no_claim(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    _write_case(cases, "m-op-algebra-001.yaml", _clean_read_case(["m-core", "slice-mvp-1"]))
    _write_case(
        cases,
        "m-op-algebra-002.yaml",
        _clean_read_case(["m-op-algebra", "slice-mvp-1", "slice-ghost-1"]),
    )
    errors = profile_errors(_synthetic_slices(), tmp_path)
    assert any("slice-ghost-1" in e and "no claim" in e for e in errors)


def test_profile_gate_checks_every_claim_independently(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    # slice-mvp-1 is fully consistent; slice-other-1 claims m-op-algebra with no
    # tagged case carrying it -> exactly the second slice fails.
    _write_case(cases, "m-op-algebra-001.yaml", _clean_read_case(["m-core", "slice-mvp-1"]))
    _write_case(
        cases,
        "m-op-algebra-002.yaml",
        _clean_read_case(["m-op-algebra", "slice-mvp-1"]),
    )
    _write_case(cases, "m-core-001.yaml", _clean_read_case(["m-core", "slice-other-1"]))
    two = _synthetic_slices(extra_claims=_claim_block(case_tags='{ "include": ["slice-other-1"] }'))
    errors = profile_errors(two, tmp_path)
    assert any("[slice-other-1]" in e and "m-op-algebra" in e for e in errors)
    assert not any("[slice-mvp-1]" in e for e in errors)


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
            "shape": "conflict",
            "when": {"write": {"id": 2, "balance": 250.00, "observedVersion": 1}},
            "then": {
                "affectedRows": 0,
                "statements": [
                    {
                        "sql": {"postgres": "update account set balance = ? where id = ?"},
                        "binds": [250.00, 2],
                    }
                ],
            },
        },
    )
    errors = profile_errors(_synthetic_slices(), tmp_path)
    assert any("m-core-001.yaml" in e and "conflict" in e and "outside" in e for e in errors)


def test_profile_gate_fails_on_a_missing_postgres_golden(tmp_path: Path) -> None:
    cases = tmp_path / "cases"
    _write_case(cases, "m-op-algebra-001.yaml", _clean_read_case(["m-core", "slice-mvp-1"]))
    no_golden = _clean_read_case(["m-op-algebra", "slice-mvp-1"])
    no_golden["then"]["statements"] = [{"sql": {"mariadb": "select t0.id from orders t0"}}]
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
            "shape": "scenario",
            "when": {
                "scenario": [
                    {
                        "write": "insert",
                        "roundTrips": 1,
                        "statements": [
                            {
                                "sql": {"postgres": "insert into account(id) values (?)"},
                                "binds": [7],
                            }
                        ],
                    },
                    {
                        "find": {"eq": {"attr": "Account.id", "value": 7}},
                        "roundTrips": 1,
                        "statements": [
                            {
                                "sql": {"postgres": "select t0.id from account t0 where t0.id = ?"},
                                "binds": [7],
                            }
                        ],
                        "expectRows": [{"id": 7}],
                    },
                ],
            },
            "then": {"roundTrips": 2},
        },
    )
    slices = _synthetic_slices(
        modules='["m-core","m-op-algebra","m-unit-work"]',
        shapes='["read","writeSequence","scenario"]',
    )
    assert profile_errors(slices, tmp_path) == []


# --- the profile gate over the real corpus -----------------------------------
#
# Every slice's tagged cases are internally consistent with its canonical claim,
# and the tagged-case counts are drift tripwires — adding or losing a tagged case
# fails the count. The two object-lifecycle slices share the non-lifecycle base
# (dual-tagged cases, including the inheritance read AND write cases);
# slice-snapshot-1 excludes the m-op-list-tagged cases and adds the
# m-snapshot-read cases, slice-managed-1 adds the m-detach lifecycle cases, the
# detached merge-back conflict, and the m-identity-map cases.


def _slice_tag_count(slice_tag: str) -> list[str]:
    cases_dir = _COMPATIBILITY_ROOT / "cases"
    tagged = []
    for path in sorted(cases_dir.glob("**/*.yaml")) + sorted(cases_dir.glob("**/*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            continue
        tags = [t for t in doc.get("tags", []) if isinstance(t, str)]
        if slice_tag in tags:
            tagged.append(path.name)
    return tagged


def test_real_corpus_profile_is_consistent() -> None:
    slices = (_SPEC_DIR / "slices.md").read_text(encoding="utf-8")
    assert profile_errors(slices, _COMPATIBILITY_ROOT) == []


def test_real_corpus_declares_the_two_lifecycle_slices() -> None:
    # slice-mvp-1 is deprecated and survives only until the TypeScript claim
    # migrates to slice-managed-1 (see slices.md).
    slices = (_SPEC_DIR / "slices.md").read_text(encoding="utf-8")
    claims = parse_profile_claims(slices)
    assert sorted(claims) == ["slice-managed-1", "slice-mvp-1", "slice-snapshot-1"]


@pytest.mark.parametrize(
    ("slice_tag", "expected"),
    [
        # The standalone plain-bitemporal-insert witness m-bitemp-write-009 (COR-9
        # Phase 1 extension) carries all three lifecycle slice tags, matching its
        # plain update/terminate siblings m-bitemp-write-006/-007, so each count
        # ticked up by one.
        #
        # COR-9 Phase 3 adds 13 inheritance model-negative `when.model` rejected cases
        # (m-inheritance-020..032), each tagged slice-snapshot-1 + slice-managed-1
        # (never slice-mvp-1), so those two counts rise by 13 and slice-mvp-1 is
        # unchanged. (The Phase 3 review added -031 tph-missing-tag-value and -032
        # missing-root, closing the tagValue-presence and exactly-one-root holes.)
        #
        # COR-9 Phase 4 adds 8 more inheritance cases tagged slice-snapshot-1 +
        # slice-managed-1 (never slice-mvp-1): the 6 table-per-hierarchy abstract /
        # narrow read cases (m-inheritance-011..016) and the 2 operation-level
        # narrow / subtype-scope `rejected` cases (m-inheritance-040/-041). The four
        # rewritten reads (m-inheritance-001..004) keep their existing slice tags, so
        # those two counts rise by 8 and slice-mvp-1 is unchanged.
        #
        # The Phase 4 review then added one more narrow `rejected` case
        # (m-inheritance-042: a nested narrow that broadens back out of the position
        # the enclosing narrow established), tagged slice-snapshot-1 + slice-managed-1,
        # so those two counts rise by one more (229 / 249) and slice-mvp-1 is unchanged.
        #
        # A follow-up Phase 4 review then added one zero-row abstract-root read
        # (m-inheritance-017: an abstract read whose predicate matches no fixture row,
        # `then.rows: []`), tagged slice-snapshot-1 + slice-managed-1, exercising the now
        # row-count-independent abstract-read projection oracle against Postgres; those
        # two counts rise by one more (230 / 250) and slice-mvp-1 is unchanged.
        #
        # COR-9 Phase 5 adds 4 table-per-concrete-subtype `union all` abstract-read
        # cases tagged slice-snapshot-1 + slice-managed-1 (never slice-mvp-1):
        # the abstract-root and abstract-subtype union reads (m-inheritance-050/-051)
        # and the two narrowed union reads (m-inheritance-052 narrow-to-abstract-subtype,
        # -053 narrow-to-multiple-concrete). The two rewritten TPCS concrete reads
        # (m-inheritance-005/-006, renamed off the table-per-leaf spelling) keep their
        # existing slice tags, so those two counts rise by 4 and slice-mvp-1 is unchanged.
        ("slice-mvp-1", 198),
        ("slice-snapshot-1", 234),
        ("slice-managed-1", 254),
    ],
)
def test_profile_slice_tag_counts(slice_tag: str, expected: int) -> None:
    tagged = _slice_tag_count(slice_tag)
    assert len(tagged) == expected, (
        f"expected exactly {expected} cases tagged {slice_tag!r}, "
        f"found {len(tagged)}: {sorted(tagged)}"
    )
