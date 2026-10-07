"""Unit tests for the generated import-linter forbidden-edge complement.

Covers the two canaries the import-linter complement must guarantee:

* a hand-edited generated contract fails ``check_dag_sync.py``; and
* a deliberately illegal scope import fails ``lint-imports``.

plus generator correctness (DAG parsing, closure, and the conformance-family
importer exemption), and the four §7 relations:

* the behavioral mapping §7 declares as one table — module tag to enforcement
  scope — the table grammar, the one pytest-bounded row required as the tool
  spells it, and parity with ``MODULE_SCOPE``, with a drift canary per side;
* the first-party support relation §7 declares as one table — enforcement scope
  to its allowed direct first-party dependencies — the strict cell grammar, the
  write-lowering group row naming its three scopes, and parity with
  ``PYTHON_FIRST_PARTY_GRANTS``, with a drift canary per side;
* child scopes are emitted as contract *sources*, and as forbidden *targets*
  only in a sibling's zero-grant row or — for a declared isolated child — in
  every row that overlaps it nowhere, with a ``lint-imports``
  canary proving a child contract blocks an import its parent's row permits, and
  a second canary proving the one asymmetric child grant — the descriptor
  package's Hub-construction seam — is admitted for that child alone and stays
  forbidden to every other module its parent's row governs;
* an isolated child scope, which a grant on its parent does NOT carry;
* the child topology §7 declares as one table — each child's parent and its
  ``ordinary``, ``sealed``, or ``isolated`` import policy — the table grammar,
  and parity with ``CHILD_SCOPES``, with a drift canary per side and per column;
* a zero-grant child scope, whose emptiness IS its contract, with two canaries —
  one importing a scope from outside its own package, one importing a sibling
  child scope inside it, the half a package-scoped row can only reach by naming
  siblings as targets; and
* a child scope named as another scope's GRANT, which is how the typed query
  surface takes the Entity frontend without the rest of `m-object-query` taking
  it — with two canaries, one importing the Database Port into the read-preflight
  seam directly and one reaching it through a chain; and
* the restricted-external ownership §7 declares as its own relation — the table
  grammar, parity with ``RESTRICTED_EXTERNAL_GRANTS`` in both directions, the
  minimal blocked roots and delegated child exceptions each direct-only contract
  is built from, and ``lint-imports`` canaries naming the four packages
  literally: a Snapshot module importing any of them breaks, an unowned package
  interface importing one breaks, every owner's own import is kept, and the
  indirect Snapshot -> Entity -> Pydantic reach stays legal; and
* the topology derived from the declared scopes rather than inventoried: the
  production scopes, the import-linter roots, and the unowned package
  interfaces, with a first scope in a new package adding its root and a
  conformance scope staying non-production by where it sits.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import check_dag_sync as dag
from tests._support.repo import PY_ROOT


@pytest.fixture(scope="module")
def linted_copy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A throwaway copy of the graded packages beside the contracts grading them.

    A contract canary proves a row by breaking it, and the deliberate violation
    goes here rather than into the tracked module it names: running the tests
    rewrites no tracked source, so an interrupted run leaves nothing behind to
    restore. `lint-imports` resolves the packages it grades off ``PYTHONPATH``,
    which is what makes this copy the tree it reads.
    """
    tree = tmp_path_factory.mktemp("linted-copy")
    shutil.copy(dag.PYPROJECT, tree / dag.PYPROJECT.name)
    ignore_bytecode = shutil.ignore_patterns("__pycache__")
    for src in sorted(PY_ROOT.glob("packages/*/src")):
        shutil.copytree(src, tree / "packages" / src.parent.name / "src", ignore=ignore_bytecode)
    return tree


def _linted_with(tree: Path, module: str, statement: str) -> subprocess.CompletedProcess[str]:
    """Run `lint-imports` over ``tree`` with ``statement`` appended to ``module`` —
    the copied module named by its dotted import path, created inside its
    package when the copy holds no module of that name — and restore the copy."""
    lint_imports = shutil.which("lint-imports")
    assert lint_imports is not None, "lint-imports must be installed in the dev env"

    package, _, name = module.rpartition(".")
    (directory,) = tree.glob(f"packages/*/src/{package.replace('.', '/')}")
    target = directory / f"{name}.py"
    original = target.read_text() if target.exists() else None
    target.write_text(f"{original or ''}{statement}\n")
    try:
        return subprocess.run(
            [lint_imports],
            cwd=tree,
            capture_output=True,
            text=True,
            env=os.environ
            | {"PYTHONPATH": os.pathsep.join(str(src) for src in tree.glob("packages/*/src"))},
        )
    finally:
        if original is None:
            target.unlink()
        else:
            target.write_text(original)


def broken_by(tree: Path, module: str, statement: str) -> str:
    """`lint-imports`' report over ``tree``, unwrapped, with ``statement``
    appended to ``module``.

    Asserts a contract broke, because every caller is a canary whose subject is
    which contract the tool then names and along which edge. The report wraps
    long edges across lines, so it is answered unwrapped.
    """
    result = _linted_with(tree, module, statement)
    assert result.returncode != 0, result.stdout
    return " ".join(result.stdout.split())


def kept_with(tree: Path, module: str, statement: str) -> str:
    """`lint-imports`' report over ``tree``, unwrapped, with ``statement``
    appended to ``module``, asserting every contract was kept: the positive
    half of a grant, which a breaking canary alone cannot prove."""
    result = _linted_with(tree, module, statement)
    assert result.returncode == 0, result.stdout
    return " ".join(result.stdout.split())


def _spec_with(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old: str, new: str) -> None:
    """Point the tool at a copy of the spec with ``old`` replaced by ``new`` once."""
    original = dag.PYTHON_MD.read_text()
    edited = original.replace(old, new, 1)
    assert edited != original
    tampered = tmp_path / "python.md"
    tampered.write_text(edited)
    monkeypatch.setattr(dag, "PYTHON_MD", tampered)


# --------------------------------------------------------------------------
# Generator correctness
# --------------------------------------------------------------------------
def test_parse_dependency_graph_reads_core_edges() -> None:
    edges = dag.parse_dependency_graph(dag.MODULES_MD.read_text())
    assert ("m-descriptor", "m-core") in edges
    assert ("m-snapshot-read", "m-deep-fetch") in edges
    # No malformed pairs slipped through.
    assert all(a and b for a, b in edges)


def test_parse_dependency_graph_rejects_missing_block() -> None:
    with pytest.raises(ValueError, match="dependency-graph"):
        dag.parse_dependency_graph("no fenced block here")


def test_transitive_closure_follows_edges() -> None:
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    closure = dag.transitive_closure(adjacency, "parallax.core.predicate")
    # Predicate depends on metamodel + inheritance, inheritance reaches model
    # formation, and both reach core. No path to the descriptor scope: no
    # behavioral module depends on descriptor.
    assert closure == {
        "parallax.core.inheritance",
        "parallax.core.metamodel",
        "parallax.core.model_formation",
        "parallax.core.base",
        "parallax.core.wire",
    }
    assert dag.transitive_closure(adjacency, "parallax.core.base") == frozenset()


def test_forbidden_respects_the_dag() -> None:
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    # A permitted dependency is never forbidden...
    assert "parallax.core.base" not in forbidden["parallax.core.predicate"]
    # ...while a non-edge is.
    assert "parallax.core.sql_gen" in forbidden["parallax.core.predicate"]
    # Nothing in the common runtime depends on the descriptor distribution, so
    # every core scope — behavioral scopes and the entity frontend alike — is
    # forbidden from importing it. The one descriptor/runtime edge runs the other
    # way, and only from the descriptor package's private hub child scope.
    assert "parallax.descriptor" in forbidden["parallax.core.predicate"]
    assert "parallax.descriptor" in forbidden["parallax.core.inheritance"]
    assert "parallax.descriptor" in forbidden["parallax.core.entity"]
    assert "parallax.core.entity" not in forbidden["parallax.descriptor._hub"]
    # The cross-package rule falls out of the complement.
    assert "parallax.postgres" in forbidden["parallax.snapshot._publication"]


def test_production_scopes_never_import_conformance() -> None:
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    for scope, blocked in forbidden.items():
        # The whole conformance subtree is forbidden as one package edge, which
        # import-linter expands to every parallax.conformance.* scope — so a new
        # conformance module (`.adapter`, `.claim`, `.api_suite`, …) can never
        # slip in as importable from production. Individual conformance scopes
        # are therefore subsumed, not separately enumerated.
        assert dag.CONFORMANCE_ROOT in blocked, scope
        assert "parallax.conformance.case_format" not in blocked, scope
        assert "parallax.conformance.cli" not in blocked, scope


def test_build_adjacency_fails_on_mapped_importer_with_unmapped_target() -> None:
    # A mapped importer that gains a dependency MODULE_SCOPE does not model must
    # abort generation, not silently drop the edge (leaving the §7 map stale).
    with pytest.raises(ValueError, match="MODULE_SCOPE does not model"):
        dag.build_adjacency([("m-descriptor", "m-ghost-999")])


def test_build_adjacency_skips_unmapped_importer() -> None:
    # A deferred / out-of-slice importer the Python target does not enforce is
    # skipped, not treated as a stale-map error.
    adjacency = dag.build_adjacency([("m-agg", "m-predicate")])
    assert adjacency["parallax.core.predicate"] == frozenset()


def test_build_adjacency_fails_on_unknown_support_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tampered = dict(dag.PYTHON_FIRST_PARTY_GRANTS)
    tampered["parallax.core.entity"] = frozenset({"parallax.core.does_not_exist"})
    monkeypatch.setattr(dag, "PYTHON_FIRST_PARTY_GRANTS", tampered)
    with pytest.raises(ValueError, match="absent from the §7 enforcement map"):
        dag.build_adjacency([])


def test_conformance_scopes_are_exempt_importers() -> None:
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    # The two tagged conformance scopes are declared, so parity sees them, and
    # non-production by where they sit, so no forbidden contract is *sourced*
    # from either — nor from any conformance scope declared later.
    conformance = {"parallax.conformance.case_format", "parallax.conformance.cli"}
    assert conformance <= dag.declared_first_party_scopes()
    assert not (conformance & dag.production_scopes())
    assert set(forbidden) == dag.production_scopes()
    assert not any(dag.is_in_scope(scope, dag.CONFORMANCE_ROOT) for scope in forbidden)


def test_production_scopes_are_derived_from_where_a_scope_sits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A conformance scope declared tomorrow is non-production by construction,
    # not by being added to an inventory: nothing is sourced from it, and it is
    # not an owner a restricted external may be granted to.
    monkeypatch.setattr(
        dag,
        "PYTHON_FIRST_PARTY_GRANTS",
        {**dag.PYTHON_FIRST_PARTY_GRANTS, "parallax.conformance.sweep": frozenset[str]()},
    )
    assert "parallax.conformance.sweep" in dag.declared_first_party_scopes()
    assert "parallax.conformance.sweep" not in dag.production_scopes()
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    assert "parallax.conformance.sweep" not in dag.compute_forbidden(adjacency)
    with pytest.raises(ValueError, match=r"'parallax\.conformance\.sweep', which is neither"):
        dag.parse_restricted_external_table(
            "| Restricted external package | Granted enforcement scopes |\n|---|---|\n"
            "| `psycopg` | `parallax.conformance.sweep` |\n"
        )


def test_root_packages_are_derived_from_the_declared_scopes() -> None:
    assert dag.root_packages() == (
        "parallax.aws",
        "parallax.conformance",
        "parallax.core",
        "parallax.descriptor",
        "parallax.evolution",
        "parallax.postgres",
        "parallax.snapshot",
    )
    assert dag.root_packages() == tuple(sorted(dag.root_packages()))


def test_a_first_scope_in_a_new_package_adds_its_root(monkeypatch: pytest.MonkeyPatch) -> None:
    # A second adapter distribution declares one scope and is an import-linter
    # root from then on, with no inventory to remember. Its package interface
    # is not that scope, so it joins the exactly-sourced interfaces too.
    monkeypatch.setattr(
        dag,
        "PYTHON_FIRST_PARTY_GRANTS",
        {**dag.PYTHON_FIRST_PARTY_GRANTS, "parallax.mariadb.adapter": frozenset[str]()},
    )
    assert "parallax.mariadb" in dag.root_packages()
    assert "parallax.mariadb.adapter" in dag.production_scopes()
    assert dag.unowned_production_interfaces(dag.production_scopes(), dag.root_packages()) == (
        frozenset({"parallax.core", "parallax.evolution", "parallax.mariadb"})
    )
    block = dag.render_block({"parallax.mariadb.adapter": []}, {})
    assert '    "parallax.mariadb",\n' in block
    assert '    "parallax.evolution",\n    "parallax.mariadb",\n]\n' in block


def test_enforcement_root_is_the_distribution_package() -> None:
    assert dag.enforcement_root("parallax.core.entity._layout") == "parallax.core"
    assert dag.enforcement_root("parallax.postgres") == "parallax.postgres"
    with pytest.raises(ValueError, match=r"not inside a parallax package: 'tests\.api'"):
        dag.enforcement_root("tests.api")
    with pytest.raises(ValueError, match="not inside a parallax package: 'parallax'"):
        dag.enforcement_root("parallax")


def test_declared_first_party_scopes_are_the_contract_universe() -> None:
    # The scope universe is the behavioral mapping's scopes and the first-party
    # table's keys — never the pytest-bounded scope, which is a row of the
    # behavioral table and no scope at all.
    declared = dag.declared_first_party_scopes()
    assert declared == frozenset(dag.MODULE_SCOPE.values()) | frozenset(
        dag.PYTHON_FIRST_PARTY_GRANTS
    )
    assert not (declared & set(dag.PYTEST_BOUNDED_SCOPES.values()))
    assert all(scope.startswith("parallax.") for scope in declared)


def test_render_block_is_deterministic() -> None:
    assert dag.generate() == dag.generate()


# --------------------------------------------------------------------------
# §7's behavioral mapping: one table, compared with MODULE_SCOPE.
# --------------------------------------------------------------------------
# The behavioral-scope table header the parser keys on, for synthetic fixtures.
_BEHAVIORAL_HEADER = "| Behavioral module | Enforcement scope |\n|---|---|"


def _behavioral_table(*rows: tuple[str, str]) -> str:
    body = "".join(f"| {module} | {scope} |\n" for module, scope in rows)
    return f"{_BEHAVIORAL_HEADER}\n{body}"


def test_parse_dependency_graph_skips_blank_lines() -> None:
    assert dag.parse_dependency_graph("```dependency-graph\n\nm-a --> m-b\n\n```") == [
        ("m-a", "m-b")
    ]


def test_parse_dependency_graph_rejects_a_malformed_line() -> None:
    with pytest.raises(ValueError, match="unparseable dependency-graph line"):
        dag.parse_dependency_graph("```dependency-graph\nnot an edge\n```")


def test_the_spec_and_the_tool_agree_on_the_behavioral_mapping() -> None:
    declared = dag.parse_behavioral_scope_table(dag.PYTHON_MD.read_text())
    dag.check_behavioral_scope_parity(declared)
    assert declared == dag.declared_behavioral_scopes()


def test_a_module_declared_as_both_contract_source_and_pytest_boundary_fails_parity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Adding the module to MODULE_SCOPE while its pytest-bounded entry stays
    # is the half-finished ownership migration; a merge of the two would keep
    # the entry the spec still carries and let parity pass on it while
    # generation sourced a contract from the other.
    monkeypatch.setattr(
        dag, "MODULE_SCOPE", {**dag.MODULE_SCOPE, "m-api-conformance": "parallax.tests.api"}
    )
    with pytest.raises(
        ValueError,
        match=re.escape(
            "MODULE_SCOPE and PYTEST_BOUNDED_SCOPES both declare ['m-api-conformance']"
        ),
    ):
        dag.generate()


def test_the_pytest_bounded_row_is_required_by_parity() -> None:
    # The core template demands a row per claimed module, so the row exists;
    # import-linter grades no test package, so MODULE_SCOPE omits it. Parity
    # must neither report the row as spec-only nor let the table drop it.
    declared = dag.parse_behavioral_scope_table(dag.PYTHON_MD.read_text())
    assert declared["m-api-conformance"] == "tests.api"
    assert "m-api-conformance" not in dag.MODULE_SCOPE
    dag.check_behavioral_scope_parity(declared)
    del declared["m-api-conformance"]
    with pytest.raises(ValueError, match=r"declared only in the tool \['m-api-conformance'\]"):
        dag.check_behavioral_scope_parity(declared)


def test_a_behavioral_cell_carrying_text_beside_its_name_is_refused() -> None:
    # A bare token beside the backticked name declares nothing here, while a
    # reader counting bare tokens would take it for a row of its own; refusing
    # it keeps the row-per-module rule from being satisfied by smuggled text.
    with pytest.raises(ValueError, match="module cell must hold exactly one backticked name"):
        dag.parse_behavioral_scope_table(
            _behavioral_table(("`m-core` m-api-conformance", "`parallax.core.base`"))
        )
    with pytest.raises(ValueError, match="scope cell must hold exactly one backticked name"):
        dag.parse_behavioral_scope_table(
            _behavioral_table(("`m-core`", "`parallax.core.base` (generated)"))
        )


def test_parse_behavioral_scope_table_reads_module_to_scope() -> None:
    declared = dag.parse_behavioral_scope_table(
        _behavioral_table(
            ("`m-core`", "`parallax.core.base`"),
            ("`m-api-conformance`", "`tests.api`"),
        )
    )
    assert declared == {"m-core": "parallax.core.base", "m-api-conformance": "tests.api"}


def test_parse_behavioral_scope_table_rejects_a_scope_outside_parallax() -> None:
    # Only the pytest-bounded modules may name a scope no contract is sourced
    # from, and only the scope the tool names for them.
    with pytest.raises(ValueError, match=r"maps 'm-core' to 'tests\.core', which is neither"):
        dag.parse_behavioral_scope_table(_behavioral_table(("`m-core`", "`tests.core`")))
    with pytest.raises(ValueError, match=r"maps 'm-api-conformance' to 'tests\.other'"):
        dag.parse_behavioral_scope_table(
            _behavioral_table(("`m-api-conformance`", "`tests.other`"))
        )


def test_parse_behavioral_scope_table_rejects_a_non_module_tag() -> None:
    with pytest.raises(ValueError, match=r"'parallax\.core\.base' is not a behavioral module tag"):
        dag.parse_behavioral_scope_table(
            _behavioral_table(("`parallax.core.base`", "`parallax.core.base`"))
        )


def test_parse_behavioral_scope_table_rejects_a_cell_naming_two_names() -> None:
    with pytest.raises(ValueError, match="module cell must hold exactly one backticked name"):
        dag.parse_behavioral_scope_table(
            _behavioral_table(("`m-core`, `m-wire`", "`parallax.core.base`"))
        )
    with pytest.raises(ValueError, match="scope cell must hold exactly one backticked name"):
        dag.parse_behavioral_scope_table(
            _behavioral_table(("`m-core`", "`parallax.core.base` or `parallax.core.wire`"))
        )


def test_parse_behavioral_scope_table_rejects_a_duplicate_row() -> None:
    with pytest.raises(ValueError, match="declares 'm-core' more than once"):
        dag.parse_behavioral_scope_table(
            _behavioral_table(
                ("`m-core`", "`parallax.core.base`"),
                ("`m-core`", "`parallax.core.wire`"),
            )
        )


def test_parse_behavioral_scope_table_rejects_a_missing_table() -> None:
    with pytest.raises(ValueError, match="no §7 behavioral-scope table"):
        dag.parse_behavioral_scope_table("no table here")


def test_a_behavioral_module_remapped_in_the_spec_alone_fails_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _spec_with(
        tmp_path,
        monkeypatch,
        "| `m-edit` | `parallax.core.entity._edit` |",
        "| `m-edit` | `parallax.core.entity` |",
    )
    with pytest.raises(
        ValueError,
        match=re.escape(
            "behavioral module 'm-edit' has drifted between the spec and the tool: the spec "
            "maps it to 'parallax.core.entity', the tool maps it to 'parallax.core.entity._edit'"
        ),
    ):
        dag.generate()


def test_a_behavioral_row_dropped_from_the_spec_alone_fails_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _spec_with(tmp_path, monkeypatch, "| `m-pk-gen` | `parallax.core.pk_gen` |\n", "")
    with pytest.raises(ValueError, match=r"declared only in the tool \['m-pk-gen'\]"):
        dag.generate()


def test_a_behavioral_row_added_to_the_spec_alone_fails_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _spec_with(
        tmp_path,
        monkeypatch,
        "| `m-pk-gen` | `parallax.core.pk_gen` |\n",
        "| `m-agg` | `parallax.core.agg` |\n| `m-pk-gen` | `parallax.core.pk_gen` |\n",
    )
    with pytest.raises(ValueError, match=r"declared only in the spec \['m-agg'\]"):
        dag.generate()


def test_the_pytest_bounded_module_given_a_parallax_scope_fails_parity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A row mapping it into the package tree would claim a contract source the
    # tool never generates; parity reports the disagreement with the tool's
    # pytest-bounded declaration rather than a module it does not model.
    _spec_with(
        tmp_path,
        monkeypatch,
        "| `m-api-conformance` | `tests.api` |",
        "| `m-api-conformance` | `parallax.tests.api` |",
    )
    with pytest.raises(
        ValueError,
        match=re.escape(
            "behavioral module 'm-api-conformance' has drifted between the spec and the "
            "tool: the spec maps it to 'parallax.tests.api', the tool maps it to 'tests.api'"
        ),
    ):
        dag.generate()


def test_a_behavioral_module_remapped_by_the_tool_alone_fails_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dag, "MODULE_SCOPE", {**dag.MODULE_SCOPE, "m-pk-gen": "parallax.core.keys"})
    with pytest.raises(ValueError, match=r"behavioral module 'm-pk-gen' has drifted"):
        dag.generate()


def test_a_behavioral_module_dropped_by_the_tool_alone_fails_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dag,
        "MODULE_SCOPE",
        {module: scope for module, scope in dag.MODULE_SCOPE.items() if module != "m-pk-gen"},
    )
    with pytest.raises(ValueError, match=r"declared only in the spec \['m-pk-gen'\]"):
        dag.generate()


# --------------------------------------------------------------------------
# §7's first-party support relation: one table, compared with
# PYTHON_FIRST_PARTY_GRANTS.
# --------------------------------------------------------------------------
# The first-party support table header the parser keys on, for synthetic fixtures.
_FIRST_PARTY_HEADER = "| Enforcement scope | Allowed direct first-party dependencies |\n|---|---|"


def _first_party_table(*rows: tuple[str, str]) -> str:
    body = "".join(f"| {scope} | {deps} |\n" for scope, deps in rows)
    return f"{_FIRST_PARTY_HEADER}\n{body}"


def _spec_first_party_grants() -> dict[str, frozenset[str]]:
    return dag.parse_first_party_support_table(dag.PYTHON_MD.read_text())


def test_the_spec_and_the_tool_agree_on_first_party_grants() -> None:
    declared = _spec_first_party_grants()
    dag.check_first_party_support_parity(declared)
    assert declared == dict(dag.PYTHON_FIRST_PARTY_GRANTS)


def test_parse_first_party_support_table_reads_the_committed_rows() -> None:
    declared = _spec_first_party_grants()
    assert "parallax.core.read_delivery._page" in declared["parallax.snapshot._publication"]
    # The Postgres row grants first-party scopes alone: the driver it imports is
    # declared by the restricted-external table, not by this column.
    assert declared["parallax.postgres"] == frozenset(
        {
            "parallax.core.base",
            "parallax.core.wire",
            "parallax.core.db_port",
            "parallax.core.db_error",
            "parallax.core.dialect",
        }
    )
    # The lifecycle extension's one Python-only edge is the Entity frontend its
    # values are stated over; every other edge it has is a module tag's.
    assert declared["parallax.snapshot"] == frozenset({"parallax.core.entity"})


def test_the_write_lowering_group_row_names_its_three_scopes() -> None:
    # One row, three scopes in its scope cell, one shared grant.
    declared = _spec_first_party_grants()
    group = [
        "parallax.core.execution._family",
        "parallax.core.execution._keyed_sql",
        "parallax.core.execution._write_lowering",
    ]
    assert set(group) <= set(declared)
    assert len({declared[scope] for scope in group}) == 1
    assert declared[group[0]] == dag.PYTHON_FIRST_PARTY_GRANTS[group[0]]


def test_first_party_support_parity_fails_on_a_dropped_grant() -> None:
    declared = _spec_first_party_grants()
    declared["parallax.postgres"] = declared["parallax.postgres"] - {"parallax.core.dialect"}
    with pytest.raises(ValueError, match=r"'parallax\.postgres' has drifted"):
        dag.check_first_party_support_parity(declared)


def test_first_party_support_parity_fails_on_a_scope_only_the_spec_declares() -> None:
    declared = _spec_first_party_grants()
    declared["parallax.core.ghost"] = frozenset({"parallax.core.base"})
    with pytest.raises(ValueError, match="declared only in the spec"):
        dag.check_first_party_support_parity(declared)


def test_first_party_support_parity_fails_on_a_scope_only_the_tool_declares() -> None:
    declared = _spec_first_party_grants()
    del declared["parallax.core.execution._read_policy"]
    with pytest.raises(ValueError, match="declared only in the tool"):
        dag.check_first_party_support_parity(declared)


def test_parse_first_party_support_table_rejects_a_missing_table() -> None:
    with pytest.raises(ValueError, match="no §7 first-party support table"):
        dag.parse_first_party_support_table("no table here")


def test_parse_first_party_support_table_rejects_an_empty_table() -> None:
    with pytest.raises(ValueError, match="has no rows"):
        dag.parse_first_party_support_table(f"{_FIRST_PARTY_HEADER}\n")


def test_parse_first_party_support_table_rejects_a_row_of_the_wrong_width() -> None:
    with pytest.raises(ValueError, match="does not have 2 cells"):
        dag.parse_first_party_support_table(f"{_FIRST_PARTY_HEADER}\n| one | two | three |\n")


def test_parse_first_party_support_table_reads_a_group_row_as_one_shared_grant() -> None:
    declared = dag.parse_first_party_support_table(
        _first_party_table(("`parallax.core.thing`, `parallax.core.other`", "`m-core`"))
    )
    assert declared == {
        "parallax.core.thing": frozenset({"parallax.core.base"}),
        "parallax.core.other": frozenset({"parallax.core.base"}),
    }


def test_parse_first_party_support_table_rejects_a_scope_cell_of_prose() -> None:
    # The scope cell is the relation's key: a cell that spells no backticked
    # name, or one whose backticked text is not a scope, declares nothing and is
    # refused rather than resolved from somewhere else.
    with pytest.raises(ValueError, match="scope cell must hold comma-separated backticked"):
        dag.parse_first_party_support_table(_first_party_table(("those three scopes", "`m-core`")))
    with pytest.raises(ValueError, match=r"'see owner' is not a `parallax\.\*` enforcement scope"):
        dag.parse_first_party_support_table(_first_party_table(("`see owner`", "`m-core`")))


def test_parse_first_party_support_table_rejects_an_abbreviated_scope() -> None:
    # A group row names every member outright; a sibling abbreviated against
    # the preceding name is not a scope.
    with pytest.raises(
        ValueError, match=r"'\._keyed_sql' is not a `parallax\.\*` enforcement scope"
    ):
        dag.parse_first_party_support_table(
            _first_party_table(("`parallax.core.execution._family`, `._keyed_sql`", "`m-core`"))
        )


def test_parse_first_party_support_table_rejects_a_duplicate_scope_row() -> None:
    with pytest.raises(ValueError, match=r"declares 'parallax\.core\.thing' more than once"):
        dag.parse_first_party_support_table(
            _first_party_table(
                ("`parallax.core.thing`", "`m-core`"),
                ("`parallax.core.thing`", "`m-wire`"),
            )
        )


def test_parse_first_party_support_table_rejects_an_unmodeled_module_tag() -> None:
    with pytest.raises(ValueError, match="MODULE_SCOPE does not model"):
        dag.parse_first_party_support_table(
            _first_party_table(("`parallax.core.thing`", "`m-ghost-999`"))
        )


def test_parse_first_party_support_table_rejects_a_backticked_non_scope_grant() -> None:
    # A third-party package is never a first-party grant, however it is spelled:
    # backticked, a token that is neither a module tag nor a scope is a spec
    # error rather than a skip, and its owners belong in the restricted-external
    # table instead.
    with pytest.raises(ValueError, match="neither a module tag nor"):
        dag.parse_first_party_support_table(
            _first_party_table(("`parallax.core.thing`", "`m-core`, `psycopg`"))
        )


def test_parse_first_party_support_table_rejects_unbackticked_prose_in_the_grant_cell() -> None:
    # The cell is a relation's column: a token nobody parses would be a grant
    # nobody enforces, so it is refused rather than read past.
    with pytest.raises(ValueError, match="dependencies cell must hold comma-separated backticked"):
        dag.parse_first_party_support_table(
            _first_party_table(("`parallax.core.thing`", "`m-core`, psycopg"))
        )


def test_parse_first_party_support_table_rejects_no_grants_beside_a_real_grant() -> None:
    with pytest.raises(ValueError, match=r"declares \(none\) beside a real grant"):
        dag.parse_first_party_support_table(
            _first_party_table(("`parallax.core.thing`", "(none), `m-core`"))
        )
    # Beside prose it is the prose that is refused, as it would be anywhere else.
    with pytest.raises(ValueError, match="dependencies cell must hold comma-separated backticked"):
        dag.parse_first_party_support_table(
            _first_party_table(("`parallax.core.thing`", "(none), psycopg"))
        )


def test_parse_first_party_support_table_reads_no_grants_alone_as_an_empty_row() -> None:
    declared = dag.parse_first_party_support_table(
        _first_party_table(("`parallax.core.thing`", "(none)"))
    )
    assert declared == {"parallax.core.thing": frozenset()}


def test_parse_first_party_support_table_rejects_a_grant_no_row_declares() -> None:
    # A grant is an edge to a scope some contract is sourced from; naming a
    # scope neither the behavioral mapping nor this table declares would grant
    # an edge to nothing.
    with pytest.raises(
        ValueError, match=r"grants scopes no §7 row declares: \['parallax\.core\.ghost'\]"
    ):
        dag.parse_first_party_support_table(
            _first_party_table(("`parallax.core.thing`", "`m-core`, `parallax.core.ghost`"))
        )
    # A scope another row of the same table declares is fine, in either order.
    declared = dag.parse_first_party_support_table(
        _first_party_table(
            ("`parallax.core.thing`", "`parallax.core.other`"),
            ("`parallax.core.other`", "(none)"),
        )
    )
    assert declared["parallax.core.thing"] == frozenset({"parallax.core.other"})


def test_a_first_party_row_edited_in_the_spec_alone_fails_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _spec_with(
        tmp_path,
        monkeypatch,
        "| `parallax.core.execution._read_policy` | `parallax.core.entity`, `m-read-delivery`, ",
        "| `parallax.core.execution._read_policy` | `parallax.core.entity`, `m-batch-write`, "
        "`m-read-delivery`, ",
    )
    with pytest.raises(ValueError, match=r"'parallax\.core\.execution\._read_policy' has drifted"):
        dag.generate()


def test_a_first_party_row_dropped_from_the_spec_alone_fails_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = dag.PYTHON_MD.read_text()
    row = next(
        line
        for line in original.splitlines()
        if line.startswith("| `parallax.core.execution._read_policy` | `parallax.core.")
    )
    _spec_with(tmp_path, monkeypatch, f"{row}\n", "")
    with pytest.raises(
        ValueError,
        match=r"declared only in the tool \['parallax\.core\.execution\._read_policy'\]",
    ):
        dag.generate()


def test_a_first_party_grant_added_to_the_tool_alone_fails_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dag,
        "PYTHON_FIRST_PARTY_GRANTS",
        {
            **dag.PYTHON_FIRST_PARTY_GRANTS,
            "parallax.core.execution._read_policy": dag.PYTHON_FIRST_PARTY_GRANTS[
                "parallax.core.execution._read_policy"
            ]
            | {"parallax.core.batch_write"},
        },
    )
    with pytest.raises(ValueError, match=r"'parallax\.core\.execution\._read_policy' has drifted"):
        dag.generate()


def test_a_first_party_scope_dropped_by_the_tool_alone_fails_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dag,
        "PYTHON_FIRST_PARTY_GRANTS",
        {
            scope: grants
            for scope, grants in dag.PYTHON_FIRST_PARTY_GRANTS.items()
            if scope != "parallax.core.execution._read_policy"
        },
    )
    with pytest.raises(
        ValueError,
        match=r"declared only in the spec \['parallax\.core\.execution\._read_policy'\]",
    ):
        dag.generate()


def test_a_first_party_row_edited_alone_exits_one_at_the_command(tmp_path: Path) -> None:
    # Command level, not library level: `python-check-dag-sync` runs the script, so
    # parity has to block there too. The script resolves the three files it reads
    # from its own location, so a copy of it laid out beside a tampered spec is the
    # command run against that spec, and the committed spec is never written.
    checkout = tmp_path / "languages" / "python"
    shutil.copytree(
        PY_ROOT / "tools", checkout / "tools", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copy(dag.PYPROJECT, checkout / dag.PYPROJECT.name)
    (checkout / "spec").mkdir()
    (tmp_path / "core" / "spec").mkdir(parents=True)
    shutil.copy(dag.MODULES_MD, tmp_path / "core" / "spec" / dag.MODULES_MD.name)
    original = dag.PYTHON_MD.read_text()
    edited = original.replace(
        "| `parallax.core.execution._read_policy` | `parallax.core.entity`, `m-read-delivery`, ",
        "| `parallax.core.execution._read_policy` | `parallax.core.entity`, `m-batch-write`, "
        "`m-read-delivery`, ",
        1,
    )
    assert edited != original
    (checkout / "spec" / dag.PYTHON_MD.name).write_text(edited)

    result = subprocess.run(
        [sys.executable, str(checkout / "tools" / "check_dag_sync.py")],
        cwd=checkout,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1, result.stdout
    assert "first-party support scope 'parallax.core.execution._read_policy'" in result.stderr
    assert "the spec grants" in result.stderr


# --------------------------------------------------------------------------
# The execution scope and its narrower children.
# --------------------------------------------------------------------------
def test_no_runtime_scope_reaches_primary_key_generation() -> None:
    # Nothing in execution or the lifecycle extension imports primary-key
    # generation, and no edge reaches it, so the complement forbids it.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    for scope in ("parallax.core.execution", "parallax.snapshot"):
        assert "parallax.core.pk_gen" not in dag.transitive_closure(adjacency, scope), scope
        assert "parallax.core.pk_gen" in forbidden[scope], scope


def test_the_read_policy_row_forbids_the_write_policy_the_parent_reaches() -> None:
    # The exclusion the read policy scope exists for: a read ladder composes over
    # read delivery and reaches no write policy, which only a row narrower than
    # the parent's can state — model preparation gives the parent that edge.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    scope = "parallax.core.execution._read_policy"
    policy = "parallax.core.batch_write"
    assert policy in adjacency["parallax.core.execution"]
    assert policy not in forbidden["parallax.core.execution"]
    assert policy in forbidden[scope]


def test_the_keyed_write_ingress_row_forbids_the_read_half_the_parent_reaches() -> None:
    # The exclusion the ingress row exists for: a keyed write addresses a row its
    # caller already holds, so it delivers no read, takes no read lock, and pages
    # no continuation — which only a row narrower than the parent's can state,
    # since the parent reaches all three.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    scope = "parallax.core.execution._keyed_writes"
    parent = dag.transitive_closure(adjacency, "parallax.core.execution")
    for reach in (
        "parallax.core.read_delivery",
        "parallax.core.read_lock",
        "parallax.core.continuation",
    ):
        assert reach in parent, reach
        assert reach not in forbidden["parallax.core.execution"], reach
        assert reach in forbidden[scope], reach


def test_the_keyed_write_ingress_row_inherits_the_port_rather_than_forbidding_it() -> None:
    # `modules.md` routes `m-db-port` through `m-execution-lifecycle`, which the
    # re-entry gate requires, and a forbidden row is the complement of a closure
    # — so the port rides in although a keyed write never reads or writes over
    # one, and §7's prose records the closure fact instead of claiming an
    # exclusion no row could carry.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    scope = "parallax.core.execution._keyed_writes"
    assert "parallax.core.execution_lifecycle" in adjacency[scope]
    assert "parallax.core.db_port" in dag.transitive_closure(adjacency, scope)
    assert "parallax.core.db_port" not in dag.compute_forbidden(adjacency)[scope]


def test_the_read_policy_row_inherits_retry_rather_than_forbidding_it() -> None:
    # `modules.md` routes `m-auto-retry` through `m-execution-lifecycle`, which
    # the re-entry gate and the read roots both require, and a forbidden row is
    # the complement of a closure — so retry rides in and §7's prose records the
    # closure fact instead of claiming an exclusion no row could carry.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    scope = "parallax.core.execution._read_policy"
    assert "parallax.core.execution_lifecycle" in adjacency[scope]
    assert "parallax.core.auto_retry" in dag.transitive_closure(adjacency, scope)
    assert "parallax.core.auto_retry" not in dag.compute_forbidden(adjacency)[scope]


# --------------------------------------------------------------------------
# Child scopes: behavioral or support contract sources, and forbidden targets
# in a sibling's zero-grant row.
# --------------------------------------------------------------------------
# The child-scope table header the parser keys on, for synthetic fixtures.
_CHILD_HEADER = (
    "| Child enforcement scope | Parent enforcement scope | Import policy |\n|---|---|---|"
)


def _child_table(*rows: tuple[str, str, str]) -> str:
    body = "".join(f"| {child} | {parent} | {policy} |\n" for child, parent, policy in rows)
    return f"{_CHILD_HEADER}\n{body}"


def test_the_spec_and_the_tool_agree_on_the_child_topology() -> None:
    declared = dag.parse_child_scope_table(dag.PYTHON_MD.read_text())
    assert declared == dict(dag.CHILD_SCOPES)
    dag.check_child_scope_parity(declared)
    declared_scopes = set(dag.PYTHON_FIRST_PARTY_GRANTS) | set(dag.MODULE_SCOPE.values())
    for child, scope in declared.items():
        assert child.startswith(f"{scope.parent}.")
        assert child in declared_scopes
        assert scope.parent in declared_scopes


def test_parse_child_scope_table_reads_child_parent_and_policy() -> None:
    declared = dag.parse_child_scope_table(
        _child_table(
            ("`parallax.core.entity._layout`", "`parallax.core.entity`", "sealed"),
            ("`parallax.core.entity._edit`", "`parallax.core.entity`", "ordinary"),
        )
    )
    assert declared == {
        "parallax.core.entity._layout": dag.ChildScope(
            parent="parallax.core.entity", policy="sealed"
        ),
        "parallax.core.entity._edit": dag.ChildScope(
            parent="parallax.core.entity", policy="ordinary"
        ),
    }


def test_parse_child_scope_table_rejects_an_unknown_policy() -> None:
    # The vocabulary is closed: a policy nothing grades would be a promise no
    # tool carries, so it is refused rather than read as ordinary.
    with pytest.raises(ValueError, match="import policy 'porous', which is none of"):
        dag.parse_child_scope_table(
            _child_table(("`parallax.core.entity._layout`", "`parallax.core.entity`", "porous"))
        )


def test_parse_child_scope_table_rejects_an_undeclared_parent() -> None:
    with pytest.raises(ValueError, match=r"undeclared parent scope 'parallax\.core\.ghost'"):
        dag.parse_child_scope_table(
            _child_table(("`parallax.core.entity._layout`", "`parallax.core.ghost`", "sealed"))
        )


def test_parse_child_scope_table_rejects_an_undeclared_child() -> None:
    # Both policies beyond ordinary describe a child relationship, so neither can
    # describe a scope nothing declares.
    with pytest.raises(ValueError, match=r"'parallax\.core\.ghost', which is not a declared"):
        dag.parse_child_scope_table(
            _child_table(("`parallax.core.ghost`", "`parallax.core.entity`", "sealed"))
        )


def test_parse_child_scope_table_rejects_a_child_outside_its_parent() -> None:
    with pytest.raises(ValueError, match="not nested inside its parent"):
        dag.parse_child_scope_table(
            _child_table(("`parallax.core.base`", "`parallax.core.execution`", "ordinary"))
        )


def test_parse_child_scope_table_rejects_a_duplicate_row() -> None:
    # Keeping the last row would let a wrong parent or policy stand in the spec
    # while the comparison, reading only what survived, matched the tool.
    with pytest.raises(
        ValueError, match=r"declares 'parallax\.core\.entity\._layout' more than once"
    ):
        dag.parse_child_scope_table(
            _child_table(
                ("`parallax.core.entity._layout`", "`parallax.core.entity`", "sealed"),
                ("`parallax.core.entity._layout`", "`parallax.core.entity`", "ordinary"),
            )
        )


def test_parse_child_scope_table_rejects_a_cell_naming_two_scopes() -> None:
    with pytest.raises(ValueError, match="child cell must hold exactly one backticked"):
        dag.parse_child_scope_table(
            _child_table(
                (
                    "`parallax.core.entity._layout`, `parallax.core.entity._edit`",
                    "`parallax.core.entity`",
                    "sealed",
                )
            )
        )


def test_parse_child_scope_table_rejects_a_row_of_the_wrong_width() -> None:
    with pytest.raises(ValueError, match="child-scope table row does not have 3 cells"):
        dag.parse_child_scope_table(f"{_CHILD_HEADER}\n| one | two |\n")


def test_parse_child_scope_table_rejects_a_missing_table() -> None:
    with pytest.raises(ValueError, match="no §7 child-scope table"):
        dag.parse_child_scope_table(_first_party_table(("`parallax.core.thing`", "(none)")))


def test_a_child_scope_is_a_forbidden_target_only_where_it_overlaps_nothing() -> None:
    # import-linter >= 2.12 silently skips a forbidden module that overlaps the
    # contract's own source package, so a child inside its parent's row would be
    # a contract that looks present and enforces nothing — and naming a child in
    # any unrelated scope's row would only restate the parent's own entry WHERE
    # THAT ENTRY EXISTS. Two rows therefore name children: a zero-grant scope's,
    # over its siblings, and every row whose scope is not the isolated child's
    # own ancestor or descendant, over that child, because a grant on the parent
    # would otherwise carry it.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    assert set(dag.CHILD_SCOPES) <= set(forbidden)
    for scope, blocked in forbidden.items():
        children_named = set(blocked) & set(dag.CHILD_SCOPES)
        overlapping = dag.scope_ancestors(scope) | dag.scope_descendants(scope) | {scope}
        expected = dag.scopes_with_policy("isolated") - overlapping
        if not adjacency[scope]:
            expected = expected | dag.scope_siblings(scope)
        assert children_named == expected, scope
        # Whatever a row names, it never names something it overlaps.
        assert not (children_named & overlapping)
    # A parent still never forbids its own children.
    for parent in {declared.parent for declared in dag.CHILD_SCOPES.values()}:
        assert not (set(forbidden[parent]) & dag.scope_descendants(parent)), parent


def test_an_isolated_child_is_forbidden_to_a_scope_granted_its_parent() -> None:
    # The whole point of declaring one: a scope granted `parallax.aws` would
    # carry the engine slice inside it in on that package grant if the row did
    # not name it. No production scope holds that grant, so this states one.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    granted = "parallax.core.execution"
    forbidden = dag.compute_forbidden({**adjacency, granted: adjacency[granted] | {"parallax.aws"}})
    engine_slice = "parallax.aws.postgres"
    assert "parallax.aws" not in forbidden[granted]
    assert engine_slice in forbidden[granted]
    # Its own package is the one place a row cannot reach: naming the slice in
    # its parent's row would overlap that contract's source package. That edge
    # is enforced over the files instead, by `tools/check_scope_ownership.py`.
    assert engine_slice not in forbidden["parallax.aws"]


def test_scope_siblings_are_the_other_children_of_one_parent() -> None:
    assert dag.scope_siblings("parallax.core.execution._preflight") == frozenset(
        {
            "parallax.core.execution._read_policy",
            "parallax.core.execution._keyed_writes",
            "parallax.core.execution._family",
            "parallax.core.execution._keyed_sql",
            "parallax.core.execution._write_lowering",
            "parallax.core.execution._retention",
            "parallax.core.execution._publication",
        }
    )
    # A scope's own name is never among its siblings, an only child has none,
    # and a scope that is nobody's child has none either.
    assert dag.scope_siblings("parallax.descriptor._hub") == frozenset()
    assert dag.scope_siblings("parallax.core.execution") == frozenset()
    assert dag.scope_siblings("parallax.core.base") == frozenset()


def test_only_a_zero_grant_row_takes_its_siblings_as_targets() -> None:
    # A scope with grants has a closure to complement; widening every child row
    # to name its siblings would forbid intra-package edges §7 permits — the
    # write-execution cluster's three modules import one another.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    assert adjacency["parallax.core.execution._family"]
    assert "parallax.core.execution._keyed_sql" not in forbidden["parallax.core.execution._family"]


def test_a_child_row_omits_its_own_ancestors() -> None:
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    assert "parallax.core.execution" not in forbidden["parallax.core.execution._read_policy"]
    assert dag.scope_ancestors("parallax.core.execution._read_policy") == frozenset(
        {"parallax.core.execution"}
    )
    assert dag.scope_ancestors("parallax.core.execution") == frozenset()


def test_runtime_child_rows_are_narrower_than_their_parent_rows() -> None:
    # The whole point of a narrowing child: each forbids strictly more than the
    # broad parent scope does.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    for parent in ("parallax.core.execution", "parallax.snapshot"):
        broad = set(forbidden[parent])
        for child, declared in dag.CHILD_SCOPES.items():
            if declared.parent == parent:
                assert broad < set(forbidden[child]), child
    # The read policy owns lowering, the port, and the lifecycle activities but
    # still cannot reach batch writes; the lowering cluster may not reach the
    # read side; and value publication reaches the Page child alone, so read
    # planning's SQL generation and lifecycle stay outside it.
    assert "parallax.core.db_port" not in forbidden["parallax.core.execution._read_policy"]
    assert (
        "parallax.core.execution_lifecycle" not in forbidden["parallax.core.execution._read_policy"]
    )
    assert "parallax.core.batch_write" in forbidden["parallax.core.execution._read_policy"]
    assert "parallax.core.read_delivery" in forbidden["parallax.core.execution._keyed_sql"]
    assert "parallax.core.sql_gen" in forbidden["parallax.snapshot._publication"]
    assert "parallax.core.execution_lifecycle" in forbidden["parallax.snapshot._publication"]
    assert "parallax.core.execution" in forbidden["parallax.snapshot._publication"]


def test_scope_descendants_inverts_the_child_chain() -> None:
    assert dag.scope_descendants("parallax.descriptor") == frozenset({"parallax.descriptor._hub"})
    assert dag.scope_descendants("parallax.core.execution") == frozenset(
        {
            "parallax.core.execution._preflight",
            "parallax.core.execution._read_policy",
            "parallax.core.execution._keyed_writes",
            "parallax.core.execution._family",
            "parallax.core.execution._keyed_sql",
            "parallax.core.execution._write_lowering",
            "parallax.core.execution._retention",
            "parallax.core.execution._publication",
        }
    )
    assert dag.scope_descendants("parallax.snapshot") == frozenset(
        {"parallax.snapshot._inspection", "parallax.snapshot._publication"}
    )
    assert dag.scope_descendants("parallax.core.base") == frozenset()


def test_an_asymmetric_child_grant_becomes_one_named_exception() -> None:
    # `parallax.descriptor._hub` holds a grant its parent lacks. A package-scoped
    # `forbidden` source governs the child too, so the parent's row would break on
    # the seam the child legitimately imports; naming that one edge as an
    # exception keeps the row tight for every other descriptor module instead.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    assert dag.PYTHON_FIRST_PARTY_GRANTS["parallax.descriptor._hub"] == frozenset(
        {"parallax.core.entity"}
    )
    assert "parallax.core.entity" not in adjacency["parallax.descriptor"]
    assert "parallax.core.entity" in forbidden["parallax.descriptor"]
    assert "parallax.core.entity" not in forbidden["parallax.descriptor._hub"]
    # Both spellings of the one grant, because a grant is scope-wide while the
    # spelling the child reaches it by is not derivable from the tables: this
    # seam names a module beneath the granted scope, while `parallax.aws.postgres`
    # names the granted scope's own interface.
    assert dag.child_grant_exceptions(adjacency, "parallax.descriptor") == [
        "parallax.descriptor._hub -> parallax.core.entity",
        "parallax.descriptor._hub -> parallax.core.entity.**",
    ]
    # Only the *direct* extra grant needs naming: ignoring the first hop also
    # withdraws every indirect chain that reaches further through it.
    assert "parallax.core.predicate" in forbidden["parallax.descriptor"]
    # A symmetric child chain — every execution child is narrower — needs none.
    assert dag.child_grant_exceptions(adjacency, "parallax.core.execution") == []


def test_a_child_granted_its_own_sibling_needs_no_exception() -> None:
    # `parallax.core.entity._instance_state` is granted two scopes its parent's
    # row does not name — but both sit inside that parent's own package, which a
    # row can neither forbid nor except. An entry for either would be an ignored
    # import matching nothing, which `unmatched_ignore_imports_alerting` rejects,
    # so the asymmetry test has to read containment rather than the grant table
    # alone.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    siblings = frozenset(
        {
            "parallax.core.entity._construction_input",
            "parallax.core.entity._pydantic_storage",
        }
    )
    assert siblings <= dag.PYTHON_FIRST_PARTY_GRANTS["parallax.core.entity._instance_state"]
    assert not siblings & adjacency["parallax.core.entity"]
    assert all(dag.scope_ancestors(one) == frozenset({"parallax.core.entity"}) for one in siblings)
    assert dag.child_grant_exceptions(adjacency, "parallax.core.entity") == []
    # What the generator gives up here it does not merely lose: emitting nothing
    # means the row permits every module of that package, so the scope is
    # declared SEALED and `tools/check_scope_ownership.py` refuses the imports
    # into that package no granted scope covers — the two halves are what make
    # the grant complete.
    assert dag.CHILD_SCOPES["parallax.core.entity._instance_state"].policy == "sealed"


def test_execution_authority_is_a_top_level_scope_with_core_only_edges() -> None:
    scope = "parallax.core.execution_authority"
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))

    assert dag.MODULE_SCOPE["m-execution-authority"] == scope
    assert scope not in dag.CHILD_SCOPES
    assert adjacency[scope] == frozenset({"parallax.core.db_port", "parallax.core.unit_work"})
    assert scope in adjacency["parallax.core.execution._read_policy"]
    # A top-level row forbids the whole of execution, which the scope's
    # consumers sit in.
    assert "parallax.core.execution" in dag.compute_forbidden(adjacency)[scope]


_RETENTION_ROW = "| `parallax.core.execution._retention` | `parallax.core.execution` | sealed |"
_ENGINE_SLICE_ROW = "| `parallax.aws.postgres` | `parallax.aws` | isolated |"


def test_a_seal_dropped_by_the_tool_alone_fails_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Sealing generates no contract, so unsealing a scope leaves every emitted
    # row byte-identical while the guarantee the spec still promises goes
    # ungraded. The table comparison is the only thing that reports it.
    monkeypatch.setattr(
        dag,
        "CHILD_SCOPES",
        {
            **dag.CHILD_SCOPES,
            "parallax.core.execution._retention": dag.ChildScope(
                parent="parallax.core.execution", policy="ordinary"
            ),
        },
    )
    with pytest.raises(
        ValueError,
        match=re.escape(
            "child scope 'parallax.core.execution._retention' has drifted between the spec "
            "and the tool: the spec declares a sealed child of 'parallax.core.execution', "
            "the tool declares an ordinary child of 'parallax.core.execution'"
        ),
    ):
        dag.generate()


def test_a_policy_changed_by_the_spec_alone_fails_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _spec_with(
        tmp_path, monkeypatch, _ENGINE_SLICE_ROW, _ENGINE_SLICE_ROW.replace("isolated", "ordinary")
    )
    with pytest.raises(ValueError, match=r"'parallax\.aws\.postgres' has drifted between the spec"):
        dag.generate()


def test_a_child_row_dropped_by_the_spec_alone_fails_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _spec_with(tmp_path, monkeypatch, f"{_RETENTION_ROW}\n", "")
    with pytest.raises(
        ValueError, match=r"declared only in the tool \['parallax\.core\.execution\._retention'\]"
    ):
        dag.generate()


def test_a_child_dropped_by_the_tool_alone_fails_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tampered = {
        child: declared
        for child, declared in dag.CHILD_SCOPES.items()
        if child != "parallax.core.execution._retention"
    }
    monkeypatch.setattr(dag, "CHILD_SCOPES", tampered)
    with pytest.raises(
        ValueError, match=r"declared only in the spec \['parallax\.core\.execution\._retention'\]"
    ):
        dag.generate()


def test_a_parent_differing_between_the_spec_and_the_tool_fails_parity() -> None:
    # A policy constrains a relationship, not a scope: §7 states each policy's
    # guarantee against the parent the row names, and the ownership walk takes
    # that parent from CHILD_SCOPES. Two declarations agreeing on every child and
    # every policy but one parent still promise a guarantee nothing enforces.
    declared = dag.parse_child_scope_table(dag.PYTHON_MD.read_text())
    declared["parallax.core.execution._retention"] = dag.ChildScope(
        parent="parallax.core", policy="sealed"
    )
    with pytest.raises(
        ValueError,
        match=re.escape("the spec declares a sealed child of 'parallax.core', the tool"),
    ):
        dag.check_child_scope_parity(declared)


def test_a_child_declared_by_two_rows_fails_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _spec_with(
        tmp_path,
        monkeypatch,
        _RETENTION_ROW,
        f"{_RETENTION_ROW.replace('sealed', 'ordinary')}\n{_RETENTION_ROW}",
    )
    with pytest.raises(ValueError, match="more than once"):
        dag.generate()


def test_a_first_party_scope_declared_by_two_rows_fails_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A second row for the same scope is a contradiction the parity check
    # would never see: the later grants would replace the earlier ones, and
    # agreeing with the tool would clear a row that disagrees with it.
    original = dag.PYTHON_MD.read_text()
    row = next(
        line
        for line in original.splitlines()
        if line.startswith("| `parallax.core.execution._retention` |") and "`m-metamodel`" in line
    )
    contradiction = row.replace("`m-metamodel`", "`m-sql`", 1)
    assert contradiction != row
    _spec_with(tmp_path, monkeypatch, row, f"{contradiction}\n{row}")

    with pytest.raises(ValueError, match="more than once"):
        dag.generate()


# --------------------------------------------------------------------------
# The zero-grant child scope: emptiness as a contract.
# --------------------------------------------------------------------------
_ZERO_GRANT_CHILD = "parallax.core.entity._construction_input"


def test_a_zero_grant_scope_is_forbidden_every_first_party_scope() -> None:
    # The construction-input vocabulary is read by scopes that deliberately
    # cannot reach one another, so nothing but its emptiness makes that legal,
    # and the row forbids every production scope outside its own package.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    scope = _ZERO_GRANT_CHILD
    assert dag.PYTHON_FIRST_PARTY_GRANTS[scope] == frozenset()
    assert dag.transitive_closure(adjacency, scope) == frozenset()
    blocked = set(forbidden[scope])
    assert "parallax.core.base" in blocked
    assert "parallax.core.metamodel" in blocked
    assert dag.CONFORMANCE_ROOT in blocked
    # ...and only its own package's ancestors escape, for the overlap reason
    # every child row omits them.
    assert set(dag.PYTHON_FIRST_PARTY_GRANTS) - set(dag.CHILD_SCOPES) - blocked == {
        "parallax.core.entity"
    }


def test_a_zero_grant_row_also_forbids_every_sibling_child_scope() -> None:
    # The half a scope-outside-the-package row cannot state: the shared parent
    # package overlaps the source and is skipped, but a sibling is neither
    # ancestor nor descendant, so it is a target the row can name — which makes
    # importing a declared sibling a gate failure rather than a convention.
    # `check_scope_ownership.py` covers the undeclared import-free sibling.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    scope = _ZERO_GRANT_CHILD
    blocked = set(forbidden[scope])
    assert dag.scope_siblings(scope) <= blocked
    assert "parallax.core.entity._layout" in blocked
    # The parent itself stays out, because a package-scoped row cannot forbid
    # the package it sits inside.
    assert "parallax.core.entity" not in blocked


def test_the_table_spells_a_zero_grant_scope_with_none() -> None:
    # A scope contributing no edge at all still has a row, and parity holds on
    # it: the emptiness is the declaration.
    declared = _spec_first_party_grants()
    assert declared[_ZERO_GRANT_CHILD] == frozenset()
    assert dag.PYTHON_FIRST_PARTY_GRANTS[_ZERO_GRANT_CHILD] == frozenset()


# --------------------------------------------------------------------------
# A child scope as a GRANT: the narrow part of a wide package.
# --------------------------------------------------------------------------
def test_the_preflight_seam_grants_the_query_module_not_the_frontend() -> None:
    # The whole point of the narrowing: the frontend PACKAGE reaches the port
    # (`_formation_profile -> opt_lock -> unit_work -> db_port`), and a forbidden
    # row is the complement of a closure, so granting the package would put the
    # port permanently out of the row's reach. The Object Query module does not
    # reach it, so the ordinary row forbids it.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    scope = "parallax.core.execution._preflight"
    assert dag.PYTHON_FIRST_PARTY_GRANTS[scope] == frozenset(
        {
            "parallax.core.metamodel",
            "parallax.core.predicate",
            "parallax.core.object_query",
        }
    )
    assert "parallax.core.db_port" in dag.transitive_closure(adjacency, "parallax.core.entity")
    assert "parallax.core.db_port" not in dag.transitive_closure(adjacency, scope)
    blocked = dag.compute_forbidden(adjacency)[scope]
    assert "parallax.core.db_port" in blocked
    # And every hop of the chain the frontend would have carried in with it.
    assert "parallax.core._formation_profile" in blocked
    assert "parallax.core.opt_lock" in blocked
    assert "parallax.core.unit_work" in blocked
    # No second first-party contract and no exception mechanism: one ordinary
    # row per scope, reporting indirect chains.
    (row,) = [
        contract
        for contract in dag.generate().split("\n\n")
        if f'source_modules = ["{scope}"]' in contract
    ]
    assert "allow_indirect_imports" not in row


def test_granting_a_child_scope_omits_that_childs_ancestors_from_the_row() -> None:
    # A forbidden entry is package-scoped, so naming `parallax.core.entity` would
    # also forbid the `parallax.core.entity._expressions` the row exists to
    # permit. Only the ancestor's NAME is given up — what the rest of that
    # package reaches stays forbidden.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    scope = "parallax.core.object_query._fluent"
    assert "parallax.core.entity" in dag.transitive_closure(adjacency, scope)
    assert "parallax.core.entity" not in forbidden[scope]
    # A scope granted neither the child nor its parent is still forbidden the
    # parent outright.
    assert "parallax.core.entity" in forbidden["parallax.descriptor"]


def test_the_expression_scope_is_narrower_than_the_frontend_it_sits_in() -> None:
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    parent = dag.CHILD_SCOPES["parallax.core.entity._expressions"].parent
    assert parent == "parallax.core.entity"
    assert set(forbidden["parallax.core.entity"]) < set(
        forbidden["parallax.core.entity._expressions"]
    )
    assert "parallax.core._formation_profile" in forbidden["parallax.core.entity._expressions"]
    # A child named as another scope's grant needs no `ignore_imports` entry from
    # its own parent's row: the parent package already covers it.
    assert dag.child_grant_exceptions(adjacency, "parallax.snapshot") == []


# --------------------------------------------------------------------------
# Canary 3: a child contract blocks what the parent contract permits.
# --------------------------------------------------------------------------
def test_child_scope_contract_blocks_an_import_the_parent_permits(linted_copy: Path) -> None:
    # `m-batch-write` IS an edge of the parent execution scope, so the broad
    # contract permits this import; only the read policy's child contract can
    # reject it.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    assert "parallax.core.batch_write" in adjacency["parallax.core.execution"]
    reported = broken_by(
        linted_copy,
        "parallax.core.execution._read_policy",
        "import parallax.core.batch_write  # deliberate child-scope violation",
    )

    assert "parallax.core.execution._read_policy -> parallax.core.batch_write" in reported


# --------------------------------------------------------------------------
# Canary 4: the named exception admits one edge, not the whole child grant.
# --------------------------------------------------------------------------
def test_the_hub_seam_stays_confined_to_the_descriptor_child_scope(linted_copy: Path) -> None:
    reported = broken_by(
        linted_copy,
        "parallax.descriptor._canary_seam",
        "import parallax.core.entity._model  # deliberate seam violation",
    )

    assert "parallax.descriptor may import only its permitted dependencies BROKEN" in reported
    assert "not allowed to import parallax.core.entity" in reported


# --------------------------------------------------------------------------
# Canary 4b: a credential provider is a LEAF beside the adapters. Only its
# engine-specific slice is granted one, and these three are what lint-imports
# proves of it: the base scope may reach neither the adapter nor the driver, and
# the leaf may reach both. The fourth half — the base scope reaching the adapter
# THROUGH the leaf, which the leaf's own exception withdraws from every contract
# — is the leaf's isolation, graded over the files by `check_scope_ownership`.
# --------------------------------------------------------------------------
def test_an_adapter_import_outside_the_engine_slice_fails_lint_imports(linted_copy: Path) -> None:
    reported = broken_by(
        linted_copy,
        "parallax.aws._rds",
        "import parallax.postgres  # deliberate adapter violation",
    )

    assert "parallax.aws may import only its permitted dependencies BROKEN" in reported
    assert "parallax.aws._rds -> parallax.postgres" in reported


def test_a_driver_import_outside_the_engine_slice_fails_lint_imports(linted_copy: Path) -> None:
    # The restricted-external contract is the half the first-party row cannot
    # carry: a scope granted no adapter could still name the driver directly.
    reported = broken_by(
        linted_copy,
        "parallax.aws._rds",
        "import psycopg  # deliberate driver violation",
    )

    assert "Direct imports of psycopg require an explicit §7 grant BROKEN" in reported
    assert "parallax.aws._rds -> psycopg" in reported


def test_the_engine_slice_may_import_the_adapter_and_the_driver(linted_copy: Path) -> None:
    # The positive half, which the two breaking canaries cannot prove: the
    # grant is delegated to this one module rather than withdrawn from the
    # package, so what the slice composes its configuration out of is reachable
    # exactly where it is spelled.
    kept_with(
        linted_copy,
        "parallax.aws.postgres",
        "import parallax.postgres\nimport psycopg",
    )


# --------------------------------------------------------------------------
# Canary 5: the read-preflight seam may not reach a Database Port — by name...
# --------------------------------------------------------------------------
def test_a_direct_port_import_in_the_preflight_seam_fails_lint_imports(linted_copy: Path) -> None:
    reported = broken_by(
        linted_copy,
        "parallax.core.execution._preflight",
        "import parallax.core.db_port  # deliberate port violation",
    )

    assert (
        "parallax.core.execution._preflight may import only its permitted dependencies BROKEN"
        in reported
    )
    assert "parallax.core.execution._preflight -> parallax.core.db_port" in reported


# --------------------------------------------------------------------------
# ...and Canary 6: nor through a chain. This is the half a row carrying
# `allow_indirect_imports` cannot prove.
# --------------------------------------------------------------------------
def test_an_indirect_reach_out_of_the_preflight_seam_fails_lint_imports(linted_copy: Path) -> None:
    # The seam's row forbids `parallax.core.entity` outright, so naming
    # `parallax.core.entity._model` breaks it on that edge alone. What this canary
    # adds is the half a row carrying `allow_indirect_imports` cannot prove: where
    # that name LEADS — the Domain Model's model-formation edge, and through it the
    # chain toward the port that made the whole frontend too wide a grant.
    reported = broken_by(
        linted_copy,
        "parallax.core.execution._preflight",
        "import parallax.core.entity._model  # deliberate reach violation",
    )

    assert (
        "parallax.core.execution._preflight may import only its permitted dependencies BROKEN"
        in reported
    )
    # Two hops: the seam names the Domain Model, which names model formation.
    assert "parallax.core.execution._preflight -> parallax.core.entity._model" in reported
    assert "parallax.core.entity._model -> parallax.core._formation_profile" in reported


# --------------------------------------------------------------------------
# Canary 5b: the keyed write ingress delivers no read, which the parent scope's
# own row permits.
# --------------------------------------------------------------------------
def test_a_read_delivery_import_in_the_keyed_write_ingress_fails_lint_imports(
    linted_copy: Path,
) -> None:
    # Read delivery IS an edge of the parent execution scope — every read the
    # runtime executes goes through it — so the broad contract permits this
    # import and only the child row can reject it.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    assert "parallax.core.read_delivery" in adjacency["parallax.core.execution"]
    reported = broken_by(
        linted_copy,
        "parallax.core.execution._keyed_writes",
        "import parallax.core.read_delivery  # deliberate read-half violation",
    )

    # The contract's name fills the report's line exactly, so no space survives
    # before its verdict; the edge is what names the broken row.
    assert "parallax.core.execution._keyed_writes may import only its permitted" in reported
    assert "parallax.core.execution._keyed_writes -> parallax.core.read_delivery" in reported


# --------------------------------------------------------------------------
# Canary 5c: value publication reaches the Page child of read delivery and
# nothing of the rest of it, which the parent lifecycle scope's row permits.
# --------------------------------------------------------------------------
def test_a_read_planning_import_in_value_publication_fails_lint_imports(
    linted_copy: Path,
) -> None:
    # The lifecycle extension reaches read delivery whole, so its broad contract
    # permits this import. The publication child is granted only the Page child,
    # whose ancestor's name the row gives up; what read planning reaches beyond
    # it — SQL generation — is what the row reports.
    reported = broken_by(
        linted_copy,
        "parallax.snapshot._publication._root",
        "import parallax.core.read_delivery._read_plan  # deliberate planning violation",
    )

    assert (
        "parallax.snapshot._publication may import only its permitted dependencies BROKEN"
        in reported
    )
    assert "parallax.snapshot._publication._root -> parallax.core.read_delivery._read_plan" in (
        reported
    )


# --------------------------------------------------------------------------
# Canary 6b: query authoring reaches no model. The expression scope's row is
# what proves it — the module docstring's claim is otherwise unenforced.
# --------------------------------------------------------------------------
def test_reaching_model_formation_from_the_expression_scope_fails_lint_imports(
    linted_copy: Path,
) -> None:
    reported = broken_by(
        linted_copy,
        "parallax.core.entity._expressions",
        "import parallax.core._formation_profile  # deliberate reach",
    )

    assert (
        "parallax.core.entity._expressions may import only its permitted dependencies BROKEN"
        in reported
    )
    assert "parallax.core.entity._expressions -> parallax.core._formation_profile" in reported


# --------------------------------------------------------------------------
# Canary 7: a zero-grant scope may name no first-party scope outside its package.
# --------------------------------------------------------------------------
def test_a_first_party_import_in_a_zero_grant_scope_fails_lint_imports(linted_copy: Path) -> None:
    # `m-metamodel` sits in the closure of every reader of the vocabulary, so
    # none of their rows would report it; the zero-grant row is what turns the
    # module's dependency-free claim into a gate.
    reported = broken_by(
        linted_copy,
        _ZERO_GRANT_CHILD,
        "import parallax.core.metamodel  # deliberate leaf violation",
    )

    assert f"{_ZERO_GRANT_CHILD} may import only its permitted dependencies BROKEN" in reported


# --------------------------------------------------------------------------
# ...and Canary 8: nor a sibling INSIDE its package. This is the half the
# outside-the-package row cannot state, and the reason the row names siblings.
# --------------------------------------------------------------------------
def test_a_sibling_import_in_a_zero_grant_scope_fails_lint_imports(linted_copy: Path) -> None:
    # The zero-grant row names the layout child directly, so an import inside
    # the shared parent package is rejected rather than escaping package-scoped
    # enforcement.
    reported = broken_by(
        linted_copy,
        _ZERO_GRANT_CHILD,
        "import parallax.core.entity._layout  # deliberate sibling violation",
    )

    assert f"{_ZERO_GRANT_CHILD} may import only its permitted dependencies BROKEN" in reported
    assert f"{_ZERO_GRANT_CHILD} -> parallax.core.entity._layout" in reported


# --------------------------------------------------------------------------
# Canary 1: the committed contracts are in sync, and a hand edit is caught.
# --------------------------------------------------------------------------
def test_committed_contracts_are_in_sync() -> None:
    assert dag.main([]) == 0
    assert dag.main(["--check"]) == 0


def test_hand_edited_contract_fails_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tampered = tmp_path / "pyproject.toml"
    original = dag.PYPROJECT.read_text()
    # Drop a forbidden entry from inside the generated region — a hand edit.
    edited = original.replace('    "parallax.postgres",\n', "", 1)
    assert edited != original
    tampered.write_text(edited)
    monkeypatch.setattr(dag, "PYPROJECT", tampered)

    assert dag.main(["--check"]) == 1
    # --write repairs it back to the canonical, in-sync form.
    assert dag.main(["--write"]) == 0
    assert dag.main(["--check"]) == 0


# --------------------------------------------------------------------------
# Canary 2: a deliberately illegal scope import fails lint-imports.
# --------------------------------------------------------------------------
def test_illegal_scope_import_fails_lint_imports(linted_copy: Path) -> None:
    # base (m-core) has no permitted dependencies, so importing predicate is illegal.
    reported = broken_by(
        linted_copy,
        "parallax.core.base._canary_illegal_import",
        "import parallax.core.predicate  # deliberate DAG violation",
    )

    assert "parallax.core.base" in reported
    assert "not allowed to import parallax.core.predicate" in reported


def test_lint_imports_is_green_without_the_canary() -> None:
    # Guards against a leaked canary file: the clean tree must pass.
    result = subprocess.run(
        [sys.executable, "-c", "import parallax.core.base"],
        cwd=PY_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_production_import_of_unmodeled_conformance_scope_fails_lint_imports(
    linted_copy: Path,
) -> None:
    # A production scope importing an *unmodeled* conformance scope (`.adapter`,
    # not `.case_format`/`.cli`) must still be caught — the whole subtree is
    # forbidden, so a new conformance module can never become importable.
    reported = broken_by(
        linted_copy,
        "parallax.core.base._canary_conformance_import",
        "import parallax.conformance.adapter  # deliberate boundary violation",
    )

    assert "parallax.core.base" in reported
    assert "parallax.conformance" in reported


# --------------------------------------------------------------------------
# Restricted externals: §7's fourth relation, parity-checked and enforced as
# one direct-only contract per package.
# --------------------------------------------------------------------------
# The restricted-external table header the parser keys on, for one-row fixtures.
_EXTERNAL_HEADER = "| Restricted external package | Granted enforcement scopes |\n|---|---|"


def _external_table(package_cell: str, owners_cell: str) -> str:
    return f"{_EXTERNAL_HEADER}\n| {package_cell} | {owners_cell} |\n"


def test_the_spec_and_the_tool_agree_on_restricted_externals() -> None:
    declared = dag.parse_restricted_external_table(dag.PYTHON_MD.read_text())
    assert declared == dict(dag.RESTRICTED_EXTERNAL_GRANTS)
    dag.check_restricted_external_parity(declared)
    # The five names are literal on purpose: a package misspelled consistently
    # in spec and tool would generate a contract forbidding a node the graph
    # never holds, which import-linter drops without a word.
    assert set(declared) == {"pydantic", "pydantic_core", "psycopg", "psycopg_pool", "botocore"}


def test_parse_restricted_external_table_reads_one_top_level_name_per_row() -> None:
    declared = dag.parse_restricted_external_table(
        _external_table("`pydantic`", "`parallax.core.entity`, `parallax.conformance`")
    )
    assert declared == {
        "pydantic": frozenset({"parallax.core.entity", dag.CONFORMANCE_ROOT}),
    }


def test_parse_restricted_external_table_rejects_a_dotted_package() -> None:
    # import-linter squashes every submodule import into the top-level node and
    # refuses a dotted external outright, so a grant at that granularity would
    # be one nothing could enforce.
    with pytest.raises(ValueError, match="exactly one backticked top-level import name"):
        dag.parse_restricted_external_table(
            _external_table("`pydantic.fields`", "`parallax.core.entity`")
        )


def test_parse_restricted_external_table_rejects_a_cell_naming_two_packages() -> None:
    with pytest.raises(ValueError, match="exactly one backticked top-level import name"):
        dag.parse_restricted_external_table(
            _external_table("`pydantic`, `pydantic_core`", "`parallax.core.entity`")
        )


def test_parse_restricted_external_table_rejects_an_unbackticked_package() -> None:
    with pytest.raises(ValueError, match="exactly one backticked top-level import name"):
        dag.parse_restricted_external_table(_external_table("pydantic", "`parallax.core.entity`"))


def test_parse_restricted_external_table_rejects_text_beside_a_name() -> None:
    # Either cell is a relation's column, not prose: a label beside the package
    # or an unbackticked owner is refused rather than skipped.
    with pytest.raises(ValueError, match="exactly one backticked top-level import name"):
        dag.parse_restricted_external_table(
            _external_table("`pydantic` (v2)", "`parallax.core.entity`")
        )
    with pytest.raises(ValueError, match="owners cell must hold comma-separated backticked"):
        dag.parse_restricted_external_table(
            _external_table("`pydantic`", "`parallax.core.entity`, parallax.postgres")
        )


def test_parse_restricted_external_table_rejects_the_first_party_namespace() -> None:
    with pytest.raises(ValueError, match="first-party namespace"):
        dag.parse_restricted_external_table(_external_table("`parallax`", "`parallax.core.entity`"))


def test_parse_restricted_external_table_rejects_empty_owners() -> None:
    with pytest.raises(ValueError, match="grants no enforcement scope"):
        dag.parse_restricted_external_table(_external_table("`pydantic`", "(none)"))


def test_parse_restricted_external_table_rejects_an_undeclared_owner() -> None:
    with pytest.raises(ValueError, match=r"'parallax\.core\.ghost', which is neither"):
        dag.parse_restricted_external_table(
            _external_table("`pydantic`", "`parallax.core.entity`, `parallax.core.ghost`")
        )


def test_parse_restricted_external_table_rejects_a_conformance_scope_as_owner() -> None:
    # The conformance root is the one development-only grant; a conformance
    # scope beneath it is not a production scope and sources no contract.
    with pytest.raises(ValueError, match=r"'parallax\.conformance\.cli', which is neither"):
        dag.parse_restricted_external_table(
            _external_table("`psycopg`", "`parallax.conformance.cli`")
        )


def test_parse_restricted_external_table_rejects_a_duplicate_package() -> None:
    table = (
        f"{_EXTERNAL_HEADER}\n"
        "| `pydantic` | `parallax.core.entity` |\n"
        "| `pydantic` | `parallax.postgres` |\n"
    )
    with pytest.raises(ValueError, match="declares 'pydantic' more than once"):
        dag.parse_restricted_external_table(table)


def test_parse_restricted_external_table_rejects_a_row_of_the_wrong_width() -> None:
    with pytest.raises(ValueError, match="restricted-external table row does not have 2 cells"):
        dag.parse_restricted_external_table(f"{_EXTERNAL_HEADER}\n| one | two | three |\n")


def test_parse_restricted_external_table_rejects_a_missing_table() -> None:
    with pytest.raises(ValueError, match="no §7 restricted-external table"):
        dag.parse_restricted_external_table(_first_party_table(("`parallax.core.thing`", "(none)")))


def test_an_owner_added_to_the_spec_alone_fails_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tampered = tmp_path / "python.md"
    original = dag.PYTHON_MD.read_text()
    edited = original.replace(
        "| `psycopg_pool` | `parallax.postgres` |",
        "| `psycopg_pool` | `parallax.postgres`, `parallax.snapshot` |",
        1,
    )
    assert edited != original
    tampered.write_text(edited)
    monkeypatch.setattr(dag, "PYTHON_MD", tampered)

    with pytest.raises(ValueError, match=r"restricted external package 'psycopg_pool' has drifted"):
        dag.generate()


def test_a_package_added_to_the_spec_alone_fails_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tampered = tmp_path / "python.md"
    original = dag.PYTHON_MD.read_text()
    edited = original.replace(
        "| `psycopg_pool` | `parallax.postgres` |",
        "| `psycopg_pool` | `parallax.postgres` |\n| `sqlalchemy` | `parallax.postgres` |",
        1,
    )
    assert edited != original
    tampered.write_text(edited)
    monkeypatch.setattr(dag, "PYTHON_MD", tampered)

    with pytest.raises(ValueError, match=r"declared only in the spec \['sqlalchemy'\]"):
        dag.generate()


def test_an_owner_added_to_the_tool_alone_fails_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dag,
        "RESTRICTED_EXTERNAL_GRANTS",
        {
            **dag.RESTRICTED_EXTERNAL_GRANTS,
            "pydantic": dag.RESTRICTED_EXTERNAL_GRANTS["pydantic"] | {"parallax.snapshot"},
        },
    )
    with pytest.raises(ValueError, match=r"restricted external package 'pydantic' has drifted"):
        dag.generate()


def test_a_package_dropped_by_the_tool_alone_fails_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tampered = {
        package: owners
        for package, owners in dag.RESTRICTED_EXTERNAL_GRANTS.items()
        if package != "pydantic_core"
    }
    monkeypatch.setattr(dag, "RESTRICTED_EXTERNAL_GRANTS", tampered)
    with pytest.raises(ValueError, match=r"declared only in the spec \['pydantic_core'\]"):
        dag.generate()


def test_a_parity_error_exits_one_with_one_line_and_no_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tampered = tmp_path / "python.md"
    original = dag.PYTHON_MD.read_text()
    edited = original.replace(
        "| `psycopg_pool` | `parallax.postgres` |",
        "| `psycopg_pool` | `parallax.postgres`, `parallax.snapshot` |",
        1,
    )
    assert edited != original
    tampered.write_text(edited)
    monkeypatch.setattr(dag, "PYTHON_MD", tampered)

    assert dag.main([]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("tools/check_dag_sync.py: ")
    assert "'psycopg_pool' has drifted between the spec and the tool" in captured.err
    # Both sides are printed, so the developer sees which declaration to move.
    assert "the spec grants ['parallax.postgres', 'parallax.snapshot']" in captured.err
    assert "the tool grants ['parallax.postgres']" in captured.err
    assert "Traceback" not in captured.err
    assert captured.err.count("\n") == 1


def test_a_programming_defect_keeps_its_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    # Only the expected declaration failures are condensed; anything else is a
    # defect in the tool and must surface as one.
    monkeypatch.setattr(dag, "RESTRICTED_EXTERNAL_GRANTS", None)
    with pytest.raises(TypeError):
        dag.main([])


def test_minimal_scope_roots_drops_a_scope_beneath_another_member() -> None:
    assert dag.minimal_scope_roots(
        {
            "parallax.core.execution",
            "parallax.core.execution._preflight",
            "parallax.core.entity._layout",
            "parallax.core.base",
        }
    ) == ("parallax.core.base", "parallax.core.entity._layout", "parallax.core.execution")


def test_external_contract_sources_keep_a_blocked_child_of_a_granted_parent() -> None:
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    production = frozenset(dag.compute_forbidden(adjacency))
    sources = dag.external_contract_sources(dag.RESTRICTED_EXTERNAL_GRANTS["pydantic"], production)
    # The frontend is granted, so its package covers nothing as a source, and
    # each ungranted child is a root of its own.
    assert "parallax.core.entity" not in sources
    assert {
        "parallax.core.entity._construction_input",
        "parallax.core.entity._expressions",
        "parallax.core.entity._layout",
    } <= set(sources)
    # A blocked child of a blocked parent is left to the parent's entry.
    assert "parallax.snapshot" in sources
    assert not any(source.startswith("parallax.snapshot.") for source in sources)
    # Granted scopes never appear, and neither does the conformance root.
    assert not set(sources) & dag.RESTRICTED_EXTERNAL_GRANTS["pydantic"]
    assert sources == tuple(sorted(sources))


def test_a_granted_child_beneath_a_blocked_ancestor_becomes_two_exceptions() -> None:
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    production = frozenset(dag.compute_forbidden(adjacency))
    granted = dag.RESTRICTED_EXTERNAL_GRANTS["pydantic_core"]
    sources = dag.external_contract_sources(granted, production)
    assert "parallax.core.entity" in sources
    assert dag.external_child_grant_exceptions(
        sources=sources, external="pydantic_core", granted_scopes=granted
    ) == (
        "parallax.core.entity._instance_state -> pydantic_core",
        "parallax.core.entity._instance_state.** -> pydantic_core",
    )
    # No granted scope of `pydantic` sits beneath a blocked one, so that
    # contract carries no exception at all.
    assert (
        dag.external_child_grant_exceptions(
            sources=dag.external_contract_sources(
                dag.RESTRICTED_EXTERNAL_GRANTS["pydantic"], production
            ),
            external="pydantic",
            granted_scopes=dag.RESTRICTED_EXTERNAL_GRANTS["pydantic"],
        )
        == ()
    )


def test_a_delegated_child_that_is_not_a_leaf_fails_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `child.**` would also cover a declared scope nested beneath the child,
    # whose own policy might differ, and import-linter has no expression for
    # "this package minus a declared child"; so the grant is refused rather
    # than widened.
    monkeypatch.setattr(
        dag,
        "CHILD_SCOPES",
        {
            **dag.CHILD_SCOPES,
            "parallax.core.entity._instance_state._nested": dag.ChildScope(
                parent="parallax.core.entity._instance_state", policy="ordinary"
            ),
        },
    )
    with pytest.raises(
        ValueError,
        match=r"not leaves of the child topology: \['parallax\.core\.entity\._instance_state'\]",
    ):
        dag.external_child_grant_exceptions(
            sources=("parallax.core.entity",),
            external="pydantic_core",
            granted_scopes=frozenset({"parallax.core.entity._instance_state"}),
        )


def test_unowned_production_interfaces_are_the_roots_no_scope_owns() -> None:
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    production = frozenset(dag.compute_forbidden(adjacency))
    assert production == dag.production_scopes()
    assert dag.unowned_production_interfaces(production, dag.root_packages()) == frozenset(
        {"parallax.core", "parallax.evolution"}
    )
    # A root that is itself a scope is owned, and the conformance root sources
    # nothing.
    assert "parallax.postgres" in production
    assert "parallax.descriptor" in production


def test_the_rendered_block_carries_the_external_contracts() -> None:
    block = dag.generate()
    assert "include_external_packages = true" in block
    for package in dag.RESTRICTED_EXTERNAL_GRANTS:
        assert f'name = "Direct imports of {package} require an explicit §7 grant"' in block
    # Alerting is relaxed in exactly the contracts that write an exception, and
    # nowhere else: every exception is generated from a §7 grant as the pair of
    # spellings that grant could be reached by, so at most one of the pair has
    # an import to match and a permission may have none at all yet.
    assert block.count('unmatched_ignore_imports_alerting = "none"') == block.count(
        "ignore_imports = ["
    )
    assert block.count('unmatched_ignore_imports_alerting = "none"') > 1
    assert "parallax.core.entity._instance_state.** -> pydantic_core" in block
    assert 'name = "Unowned production interfaces import no restricted externals directly"' in block
    assert block.count("as_packages = false") == 1
    assert block.count("allow_indirect_imports = true") == len(dag.RESTRICTED_EXTERNAL_GRANTS) + 1
    # The first-party family stays first, then one contract per package sorted
    # by name, then the interface contract last.
    names = re.findall(r'^name = "(.*)"$', block, re.MULTILINE)
    externals = [name for name in names if name.startswith("Direct imports of ")]
    assert externals == sorted(externals)
    assert names[-1] == "Unowned production interfaces import no restricted externals directly"
    assert names.index(externals[0]) == len(names) - len(externals) - 1


def test_render_block_omits_the_interface_contract_when_every_root_is_owned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A tree whose only declared scope is a distribution's root package derives
    # that root and no unowned interface, so the exact-module contract is not
    # emitted with an empty source list.
    monkeypatch.setattr(dag, "MODULE_SCOPE", {"m-db-port": "parallax.postgres"})
    monkeypatch.setattr(dag, "PYTHON_FIRST_PARTY_GRANTS", {})
    assert dag.root_packages() == ("parallax.conformance", "parallax.postgres")
    block = dag.render_block({"parallax.postgres": []}, {})
    assert "Unowned production interfaces" not in block
    assert "as_packages = false" not in block


# --------------------------------------------------------------------------
# Canary 10: a Snapshot module may name none of the five restricted packages.
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "package", ["pydantic", "pydantic_core", "psycopg", "psycopg_pool", "botocore"]
)
def test_a_restricted_import_in_a_snapshot_module_fails_lint_imports(
    linted_copy: Path, package: str
) -> None:
    reported = broken_by(
        linted_copy,
        "parallax.snapshot._inspection",
        f"import {package}  # deliberate restricted-external violation",
    )

    assert f"Direct imports of {package} require an explicit §7 grant BROKEN" in reported
    assert f"parallax.snapshot._inspection -> {package}" in reported
    # The first-party rows say nothing about it: only the external contract broke.
    assert "may import only its permitted dependencies BROKEN" not in reported


# --------------------------------------------------------------------------
# Canary 11: the package interfaces no scope owns are graded exactly.
# --------------------------------------------------------------------------
def test_a_restricted_import_in_an_unowned_interface_fails_lint_imports(
    linted_copy: Path,
) -> None:
    reported = broken_by(
        linted_copy,
        "parallax.core.__init__",
        "import pydantic  # deliberate interface violation",
    )

    assert "Unowned production interfaces import no restricted externals directly BROKEN" in (
        reported
    )
    assert "parallax.core -> pydantic" in reported


# --------------------------------------------------------------------------
# Canary 12: every owner's own import is kept, and the indirect reach stays legal.
# --------------------------------------------------------------------------
def test_the_untouched_copy_keeps_every_contract(linted_copy: Path) -> None:
    # An import of the Entity frontend reaches Pydantic only indirectly; the
    # direct-only shape of the contract is what keeps that chain unreported.
    reported = kept_with(
        linted_copy,
        "parallax.snapshot._inspection",
        "import parallax.core.entity._declaration  # granted frontend reach",
    )
    assert "Direct imports of pydantic require an explicit §7 grant KEPT" in reported


def test_an_entity_module_may_import_pydantic(linted_copy: Path) -> None:
    kept_with(linted_copy, "parallax.core.entity._canary_owner", "import pydantic")


def test_the_instance_state_child_may_import_pydantic_core(linted_copy: Path) -> None:
    kept_with(linted_copy, "parallax.core.entity._instance_state", "import pydantic_core")


def test_a_postgres_module_may_import_the_driver(linted_copy: Path) -> None:
    kept_with(
        linted_copy,
        "parallax.postgres._canary_driver",
        "import psycopg\nimport psycopg_pool",
    )


def test_an_aws_module_may_import_the_credential_chain(linted_copy: Path) -> None:
    kept_with(linted_copy, "parallax.aws._canary_chain", "import botocore.session")


def test_an_ungranted_entity_child_may_not_import_pydantic(linted_copy: Path) -> None:
    # The parent is granted, so its package covers nothing as a source; the
    # child's own root is what refuses the import.
    reported = broken_by(
        linted_copy,
        "parallax.core.entity._layout",
        "import pydantic  # deliberate child violation",
    )

    assert "Direct imports of pydantic require an explicit §7 grant BROKEN" in reported
    assert "parallax.core.entity._layout -> pydantic" in reported
