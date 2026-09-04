"""Unit tests for the generated import-linter forbidden-edge complement.

Covers the two canaries the import-linter complement must guarantee:

* a hand-edited generated contract fails ``check_dag_sync.py``; and
* a deliberately illegal scope import fails ``lint-imports``.

plus generator correctness (DAG parsing, closure, and the conformance-family
importer exemption), and the support-scope additions:

* ``SUPPORT_SCOPE_DEPS`` is parity-checked against **both** §7 declarations of
  the support-scope graph — the prose table rows and the ``support-scope-graph``
  fence — with a drift canary per representation, including the state in which
  two of the three are edited consistently and the third is left stale; and
* child scopes are emitted as contract *sources*, and as forbidden *targets*
  only in a sibling's zero-grant row or — for a declared isolated child — in
  every row that overlaps it nowhere, with a ``lint-imports``
  canary proving a child contract blocks an import its parent's row permits, and
  a second canary proving the one asymmetric child grant — the descriptor
  package's Hub-construction seam — is admitted for that child alone and stays
  forbidden to every other module its parent's row governs;
* an isolated child scope, which a grant on its parent does NOT carry, with a
  canary importing the testing-only lifecycle recorder into a production scope
  the parent package is granted to;
* the ``isolated`` and ``sealed`` marks §7's rows carry, each naming the parent
  its guarantee is stated against — mark, scope, and parent compared with the
  tool's tables, with a drift canary per side and one for a falsified parent;
* a zero-grant child scope, whose emptiness IS its contract, with two canaries —
  one importing a scope from outside its own package, one importing a sibling
  child scope inside it, the half a package-scoped row can only reach by naming
  siblings as targets; and
* a child scope named as another scope's GRANT, which is how the typed query
  surface takes the Entity frontend without the rest of `m-object-query` taking
  it — with two canaries, one importing the Database Port into the read-preflight
  seam directly and one reaching it through a chain.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import check_dag_sync as dag

PY_ROOT = Path(__file__).resolve().parents[2]

# The §7 table header the prose parser keys on, for synthetic one-row fixtures.
_HEADER = "| Behavioral/support module | a | b | c | d |"


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
    assert "parallax.postgres" in forbidden["parallax.snapshot.materialize"]


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
    tampered = dict(dag.SUPPORT_SCOPE_DEPS)
    tampered["parallax.core.entity"] = frozenset({"parallax.core.does_not_exist"})
    monkeypatch.setattr(dag, "SUPPORT_SCOPE_DEPS", tampered)
    with pytest.raises(ValueError, match="absent from the §7 enforcement map"):
        dag.build_adjacency([])


def test_conformance_scopes_are_exempt_importers() -> None:
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    # No forbidden contract is *sourced* from a conformance scope.
    assert not (set(forbidden) & dag.CONFORMANCE_SCOPES)


def test_render_block_is_deterministic() -> None:
    assert dag.generate() == dag.generate()


# --------------------------------------------------------------------------
# §7 support-scope parity: the spec fence is the third input.
# --------------------------------------------------------------------------
def test_parse_support_scope_graph_reads_the_spec_fence() -> None:
    declared = dag.parse_support_scope_graph(dag.PYTHON_MD.read_text())
    assert "parallax.snapshot.materialize" in declared["parallax.snapshot.handle"]
    assert declared["parallax.postgres"] == frozenset(
        {
            "parallax.core.base",
            "parallax.core.wire",
            "parallax.core.db_port",
            "parallax.core.db_error",
            "parallax.core.dialect",
        }
    )


def test_parse_support_scope_graph_rejects_missing_block() -> None:
    with pytest.raises(ValueError, match="support-scope-graph"):
        dag.parse_support_scope_graph("no fenced block here")


def test_parse_support_scope_graph_rejects_a_malformed_line() -> None:
    with pytest.raises(ValueError, match="unparseable support-scope-graph line"):
        dag.parse_support_scope_graph("```support-scope-graph\nnot an edge\n```")


def test_the_shared_fence_grammar_skips_blank_lines() -> None:
    # One grammar backs both fences, so this holds for `dependency-graph` too.
    assert dag.parse_support_scope_graph("```support-scope-graph\n\na --> b\n\n```") == {
        "a": frozenset({"b"})
    }
    assert dag.parse_dependency_graph("```dependency-graph\n\nm-a --> m-b\n```") == [("m-a", "m-b")]


def _spec_declarations() -> tuple[dict[str, frozenset[str]], dict[str, frozenset[str]]]:
    """§7's two declarations of the support-scope graph: the fence, then the prose."""
    text = dag.PYTHON_MD.read_text()
    return dag.parse_support_scope_graph(text), dag.parse_support_scope_table(text)


def test_committed_support_scope_table_matches_the_spec() -> None:
    # Parity holds today, so `generate()` never raises on the committed tree.
    dag.check_support_scope_parity(*_spec_declarations())


def test_support_scope_parity_fails_on_a_dropped_grant() -> None:
    declared, prose = _spec_declarations()
    declared["parallax.postgres"] = declared["parallax.postgres"] - {"parallax.core.dialect"}
    prose["parallax.postgres"] = declared["parallax.postgres"]
    with pytest.raises(ValueError, match=r"'parallax\.postgres' has drifted"):
        dag.check_support_scope_parity(declared, prose)


def test_support_scope_parity_fails_on_a_scope_only_the_spec_declares() -> None:
    declared, prose = _spec_declarations()
    declared["parallax.core.ghost"] = frozenset({"parallax.core.base"})
    prose["parallax.core.ghost"] = frozenset({"parallax.core.base"})
    with pytest.raises(ValueError, match="declared only in the spec"):
        dag.check_support_scope_parity(declared, prose)


def test_support_scope_parity_fails_on_a_scope_only_the_tool_declares() -> None:
    declared, prose = _spec_declarations()
    del declared["parallax.snapshot.handle._materializer"]
    del prose["parallax.snapshot.handle._materializer"]
    with pytest.raises(ValueError, match="declared only in the tool"):
        dag.check_support_scope_parity(declared, prose)


def test_a_tampered_spec_fence_fails_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The full canary: editing §7 without editing the tool (or the reverse) makes
    # `check_dag_sync.py` refuse to generate, so `python-check-dag-sync` blocks.
    tampered = tmp_path / "python.md"
    original = dag.PYTHON_MD.read_text()
    edited = original.replace("parallax.snapshot.handle --> parallax.core.navigate\n", "", 1)
    assert edited != original
    tampered.write_text(edited)
    monkeypatch.setattr(dag, "PYTHON_MD", tampered)

    with pytest.raises(ValueError, match=r"'parallax\.snapshot\.handle' has drifted"):
        dag.generate()


# --------------------------------------------------------------------------
# §7 prose parity: the authoritative rows are the third input.
#
# §7 states support-scope grants twice ("The prose rows and the block MUST
# agree"), so a check reading only the fence lets a prose row silently disagree
# with what is enforced. These canaries prove each representation is load-bearing.
# --------------------------------------------------------------------------
def test_parse_support_scope_table_reads_the_prose_rows() -> None:
    prose = dag.parse_support_scope_table(dag.PYTHON_MD.read_text())
    assert "parallax.snapshot.materialize" in prose["parallax.snapshot.handle"]
    # `psycopg` sits unbackticked in the Postgres row: a third-party
    # distribution, not an enforcement scope, and so not a grant.
    assert prose["parallax.postgres"] == frozenset(
        {
            "parallax.core.base",
            "parallax.core.wire",
            "parallax.core.db_port",
            "parallax.core.db_error",
            "parallax.core.dialect",
        }
    )
    # The composition-root row is application-owned and declares no scope.
    assert "parallax.snapshot" not in prose


def test_parse_support_scope_table_expands_the_child_group_row() -> None:
    # The write-execution row names three scopes in the *owner* cell, two of
    # them abbreviated, because its enforcement-scope cell says "those three
    # scopes". All three must resolve, sharing one grant row.
    prose = dag.parse_support_scope_table(dag.PYTHON_MD.read_text())
    group = [
        "parallax.snapshot.handle._family",
        "parallax.snapshot.handle._keyed_sql",
        "parallax.snapshot.handle._write_lowering",
    ]
    assert set(group) <= set(prose)
    assert len({prose[scope] for scope in group}) == 1


def test_the_three_declarations_agree_on_the_committed_tree() -> None:
    fence, prose = _spec_declarations()
    assert prose == fence
    assert prose == dict(dag.SUPPORT_SCOPE_DEPS)


def test_parse_support_scope_table_rejects_a_missing_table() -> None:
    with pytest.raises(ValueError, match="no §7 enforcement-topology table"):
        dag.parse_support_scope_table("no table here")


def test_parse_support_scope_table_rejects_an_empty_table() -> None:
    with pytest.raises(ValueError, match="has no rows"):
        dag.parse_support_scope_table(f"{_HEADER}\n|---|---|---|---|---|")


def test_parse_support_scope_table_rejects_a_row_of_the_wrong_width() -> None:
    with pytest.raises(ValueError, match="does not have 5 cells"):
        dag.parse_support_scope_table(f"{_HEADER}\n| one | two |\n")


def test_parse_support_scope_table_rejects_a_support_row_naming_no_scope() -> None:
    with pytest.raises(ValueError, match="names no enforcement scope"):
        dag.parse_support_scope_table(
            f"{_HEADER}\n| Thing (support) | prose | prose | `m-core` | x |\n"
        )


def test_a_scope_cell_of_backticked_prose_falls_back_to_the_owner_cell() -> None:
    # The fallback is keyed on "names no scope", not on the group row's exact
    # wording, so a scope cell whose backticks hold prose rather than a dotted
    # name resolves from the owner column just as the group row does.
    prose = dag.parse_support_scope_table(
        f"{_HEADER}\n| Thing (support) | `parallax.core.thing` | `see owner` | `m-core` | x |\n"
    )
    assert prose == {"parallax.core.thing": frozenset({"parallax.core.base"})}


def test_parse_support_scope_table_rejects_a_leading_dot_with_no_antecedent() -> None:
    with pytest.raises(ValueError, match="has no preceding full name"):
        dag.parse_support_scope_table(
            f"{_HEADER}\n| Thing (support) | `._orphan` | those scopes | `m-core` | x |\n"
        )


def test_parse_support_scope_table_rejects_an_unmodeled_module_tag() -> None:
    with pytest.raises(ValueError, match="MODULE_SCOPE does not model"):
        dag.parse_support_scope_table(
            f"{_HEADER}\n| Thing (support) | `parallax.core.thing` | "
            "`parallax.core.thing` | `m-ghost-999` | x |\n"
        )


def test_parse_support_scope_table_rejects_a_backticked_non_scope_grant() -> None:
    # Backticking `psycopg` would make it read as a declared grant; a token
    # that is neither a module tag nor a scope is a spec error, not a skip.
    with pytest.raises(ValueError, match="neither a module tag nor"):
        dag.parse_support_scope_table(
            f"{_HEADER}\n| Thing (support) | `parallax.core.thing` | "
            "`parallax.core.thing` | `psycopg` | x |\n"
        )


def test_parse_support_scope_table_rejects_no_grants_beside_a_real_grant() -> None:
    # The same contradiction the fence rejects, in the representation that
    # spells an empty grant outright. If only one of the two refused it, §7
    # could state the contradiction in the prose and still pass parity — the
    # fence and `SUPPORT_SCOPE_DEPS` would simply be made to agree with the
    # grant, and nothing would report that the row also declared none.
    with pytest.raises(ValueError, match=r"declares \(none\) beside a real grant"):
        dag.parse_support_scope_table(
            f"{_HEADER}\n| Thing (support) | `parallax.core.thing` | "
            "`parallax.core.thing` | (none), `m-core` | x |\n"
        )


def test_parse_support_scope_table_reads_no_grants_alone_as_an_empty_row() -> None:
    prose = dag.parse_support_scope_table(
        f"{_HEADER}\n| Thing (support) | `parallax.core.thing` | "
        "`parallax.core.thing` | (none) | x |\n"
    )
    assert prose == {"parallax.core.thing": frozenset()}


def test_no_grants_beside_unbackticked_prose_is_still_an_empty_row() -> None:
    # The other direction of the same rule: §7 says only a backticked module tag
    # or `parallax.*` scope declares a grant, so `psycopg` — the exact
    # unbackticked spelling the Postgres row already carries — contradicts
    # nothing. Rejecting on "text survived removing (none)" would refuse a row
    # this section explicitly permits.
    prose = dag.parse_support_scope_table(
        f"{_HEADER}\n| Thing (support) | `parallax.core.thing` | "
        "`parallax.core.thing` | (none), psycopg | x |\n"
    )
    assert prose == {"parallax.core.thing": frozenset()}
    explained = dag.parse_support_scope_table(
        f"{_HEADER}\n| Thing (support) | `parallax.core.thing` | "
        "`parallax.core.thing` | (none) — nothing first-party at all | x |\n"
    )
    assert explained == {"parallax.core.thing": frozenset()}


def test_a_tampered_prose_row_alone_fails_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # THE canary this arm exists for: the fence and `SUPPORT_SCOPE_DEPS` are
    # untouched and agree, so the pre-existing comparison passes; only the
    # prose row is edited, and generation must still refuse.
    tampered = tmp_path / "python.md"
    original = dag.PYTHON_MD.read_text()
    edited = original.replace(
        "| `parallax.snapshot.handle._materializer` | `parallax.snapshot.materialize`, "
        "`parallax.snapshot._inspection`, `parallax.core.entity`, `m-metamodel`,",
        "| `parallax.snapshot.handle._materializer` | `parallax.snapshot.materialize`, "
        "`parallax.snapshot._inspection`, `parallax.core.entity`, `m-sql`, `m-metamodel`,",
        1,
    )
    assert edited != original
    tampered.write_text(edited)
    monkeypatch.setattr(dag, "PYTHON_MD", tampered)

    # The fence still matches the tool exactly — the pre-existing arm passes,
    # so only the new prose arm can reject this edit.
    assert dag.parse_support_scope_graph(edited) == dict(dag.SUPPORT_SCOPE_DEPS)
    with pytest.raises(
        ValueError, match=r"'parallax\.snapshot\.handle\._materializer' has drifted"
    ):
        dag.generate()


def test_a_prose_row_deleted_alone_fails_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The set-difference arm, prose side: dropping a whole support row leaves
    # the fence declaring a scope the prose does not.
    tampered = tmp_path / "python.md"
    original = dag.PYTHON_MD.read_text()
    edited = "\n".join(
        line
        for line in original.splitlines()
        if not line.startswith("| Snapshot graph materialization (support")
    )
    assert edited != original
    tampered.write_text(edited)
    monkeypatch.setattr(dag, "PYTHON_MD", tampered)

    with pytest.raises(ValueError, match="internally inconsistent"):
        dag.generate()


def test_fence_and_tool_edited_consistently_still_fail_a_stale_prose_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The third state: two of the three representations edited together and
    # agreeing, the third left behind. Before the prose arm this passed
    # silently and shipped the over-grant.
    tampered = tmp_path / "python.md"
    original = dag.PYTHON_MD.read_text()
    edited = original.replace(
        "parallax.snapshot.handle._materializer --> parallax.core.metamodel\n",
        "parallax.snapshot.handle._materializer --> parallax.core.metamodel\n"
        "parallax.snapshot.handle._materializer --> parallax.core.sql_gen\n",
        1,
    )
    assert edited != original
    tampered.write_text(edited)
    monkeypatch.setattr(dag, "PYTHON_MD", tampered)
    monkeypatch.setattr(
        dag,
        "SUPPORT_SCOPE_DEPS",
        {
            **dag.SUPPORT_SCOPE_DEPS,
            "parallax.snapshot.handle._materializer": dag.SUPPORT_SCOPE_DEPS[
                "parallax.snapshot.handle._materializer"
            ]
            | {"parallax.core.sql_gen"},
        },
    )

    with pytest.raises(
        ValueError, match=r"'parallax\.snapshot\.handle\._materializer' has drifted"
    ):
        dag.generate()


def test_a_tampered_prose_row_alone_exits_one_at_the_command() -> None:
    # Command level, not library level: `python-check-dag-sync` runs the script, so the
    # prose arm has to block there too. Same write-run-restore shape as the
    # `lint-imports` canaries below, against the real committed spec.
    original = dag.PYTHON_MD.read_text()
    edited = original.replace(
        "| `parallax.snapshot.handle._materializer` | `parallax.snapshot.materialize`, "
        "`parallax.snapshot._inspection`, `parallax.core.entity`, `m-metamodel`,",
        "| `parallax.snapshot.handle._materializer` | `parallax.snapshot.materialize`, "
        "`parallax.snapshot._inspection`, `parallax.core.entity`, `m-sql`, `m-metamodel`,",
        1,
    )
    assert edited != original
    dag.PYTHON_MD.write_text(edited)
    try:
        result = subprocess.run(
            [sys.executable, str(PY_ROOT / "tools/check_dag_sync.py")],
            cwd=PY_ROOT,
            capture_output=True,
            text=True,
        )
    finally:
        dag.PYTHON_MD.write_text(original)

    assert result.returncode == 1, result.stdout
    assert "parallax.snapshot.handle._materializer" in result.stderr
    assert "prose table" in result.stderr


# --------------------------------------------------------------------------
# The handle grant row.
# --------------------------------------------------------------------------
def test_handle_scope_no_longer_grants_pk_gen() -> None:
    handle = dag.SUPPORT_SCOPE_DEPS["parallax.snapshot.handle"]
    assert "parallax.core.pk_gen" not in handle
    # Removing it genuinely forbids the scope: nothing else reaches pk_gen.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    assert "parallax.core.pk_gen" in forbidden["parallax.snapshot.handle"]


def test_handle_scope_still_grants_navigate() -> None:
    # Deliberate, per spec/python.md §7: `Transaction.find` is a claimed find and
    # composes `parallax.core.navigate.canonicalize` directly.
    assert "parallax.core.navigate" in dag.SUPPORT_SCOPE_DEPS["parallax.snapshot.handle"]


def test_the_read_composition_row_forbids_every_write_policy_the_parent_grants() -> None:
    # The exclusion the read scope exists for: a read ladder composes over the
    # executor and reaches no write policy, which only a row narrower than the
    # parent's can state — the parent is granted all three outright.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    scope = "parallax.snapshot.handle._read_scope"
    writes = (
        "parallax.core.batch_write",
        "parallax.core.txtime_write",
        "parallax.core.bitemp_write",
    )
    for policy in writes:
        assert policy in dag.SUPPORT_SCOPE_DEPS["parallax.snapshot.handle"], policy
        assert policy not in forbidden["parallax.snapshot.handle"], policy
        assert policy in forbidden[scope], policy


def test_the_read_composition_row_inherits_retry_rather_than_forbidding_it() -> None:
    # `modules.md` routes `m-auto-retry` through `m-execution-lifecycle`, which
    # the re-entry gate and the read roots both require, and a forbidden row is
    # the complement of a closure — so retry rides in and §7's prose records the
    # closure fact instead of claiming an exclusion no row could carry.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    scope = "parallax.snapshot.handle._read_scope"
    assert "parallax.core.execution_lifecycle" in adjacency[scope]
    assert "parallax.core.auto_retry" in dag.transitive_closure(adjacency, scope)
    assert "parallax.core.auto_retry" not in dag.compute_forbidden(adjacency)[scope]


# --------------------------------------------------------------------------
# Child scopes: contract sources, and forbidden targets in a sibling's
# zero-grant row.
# --------------------------------------------------------------------------
def test_child_scopes_are_declared_under_their_parent() -> None:
    dag.check_child_scopes()
    for child, parent in dag.CHILD_SCOPE_PARENT.items():
        assert child.startswith(f"{parent}.")
        assert child in dag.SUPPORT_SCOPE_DEPS


def test_check_child_scopes_rejects_an_undeclared_parent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dag, "CHILD_SCOPE_PARENT", {"parallax.core.ghost.child": "parallax.core.ghost"}
    )
    with pytest.raises(ValueError, match="undeclared parent scope"):
        dag.check_child_scopes()


def test_check_child_scopes_rejects_a_child_outside_its_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dag, "CHILD_SCOPE_PARENT", {"parallax.core.base": "parallax.snapshot.handle"}
    )
    with pytest.raises(ValueError, match="not nested inside its parent"):
        dag.check_child_scopes()


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
    assert set(dag.CHILD_SCOPE_PARENT) <= set(forbidden)
    for scope, blocked in forbidden.items():
        children_named = set(blocked) & set(dag.CHILD_SCOPE_PARENT)
        overlapping = dag.scope_ancestors(scope) | dag.scope_descendants(scope) | {scope}
        expected = dag.ISOLATED_CHILD_SCOPES - overlapping
        if not adjacency[scope]:
            expected = expected | dag.scope_siblings(scope)
        assert children_named == expected, scope
        # Whatever a row names, it never names something it overlaps.
        assert not (children_named & overlapping)
    # A parent still never forbids its own children.
    for parent in set(dag.CHILD_SCOPE_PARENT.values()):
        assert not (set(forbidden[parent]) & dag.scope_descendants(parent)), parent


def test_an_isolated_child_is_forbidden_to_a_scope_granted_its_parent() -> None:
    # The whole point of declaring one: `parallax.snapshot.handle` and
    # `parallax.snapshot._read_result` are both granted
    # `parallax.core.execution_lifecycle`, so the recorder inside it would ride
    # in on that package grant if the row did not name it.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    recorder = "parallax.core.execution_lifecycle.testing"
    for granted in ("parallax.snapshot.handle", "parallax.snapshot._read_result"):
        assert "parallax.core.execution_lifecycle" in dag.transitive_closure(adjacency, granted)
        assert recorder in forbidden[granted], granted
    # Its own package is the one place a row cannot reach: naming the recorder
    # in its parent's row would overlap that contract's source package. That edge
    # is enforced over the files instead, by `tools/check_scope_ownership.py`.
    assert recorder not in forbidden["parallax.core.execution_lifecycle"]


def test_check_child_scopes_rejects_an_isolated_scope_that_is_not_a_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dag, "ISOLATED_CHILD_SCOPES", frozenset({"parallax.core.ghost"}))
    with pytest.raises(ValueError, match="not declared child scopes"):
        dag.check_child_scopes()


def test_scope_siblings_are_the_other_children_of_one_parent() -> None:
    assert dag.scope_siblings("parallax.snapshot.handle._errors") == frozenset(
        {
            "parallax.snapshot.handle._materializer",
            "parallax.snapshot.handle._preflight",
            "parallax.snapshot.handle._read_scope",
            "parallax.snapshot.handle._family",
            "parallax.snapshot.handle._keyed_sql",
            "parallax.snapshot.handle._write_lowering",
            "parallax.snapshot.handle._retention",
        }
    )
    # A scope's own name is never among its siblings, an only child has none,
    # and a scope that is nobody's child has none either.
    assert dag.scope_siblings("parallax.descriptor._hub") == frozenset()
    assert dag.scope_siblings("parallax.snapshot.handle") == frozenset()
    assert dag.scope_siblings("parallax.core.base") == frozenset()


def test_only_a_zero_grant_row_takes_its_siblings_as_targets() -> None:
    # A scope with grants has a closure to complement; widening every child row
    # to name its siblings would forbid intra-package edges §7 permits — the
    # write-execution cluster's three modules import one another.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    assert adjacency["parallax.snapshot.handle._family"]
    assert (
        "parallax.snapshot.handle._keyed_sql" not in forbidden["parallax.snapshot.handle._family"]
    )


def test_a_child_row_omits_its_own_ancestors() -> None:
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    assert "parallax.snapshot.handle" not in forbidden["parallax.snapshot.handle._materializer"]
    assert dag.scope_ancestors("parallax.snapshot.handle._materializer") == frozenset(
        {"parallax.snapshot.handle"}
    )
    assert dag.scope_ancestors("parallax.snapshot.handle") == frozenset()


def test_handle_child_rows_are_narrower_than_the_parent_row() -> None:
    # The whole point of the audit: each handle child forbids strictly more than
    # the broad parent scope does.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    parent = set(forbidden["parallax.snapshot.handle"])
    for child, declared_parent in dag.CHILD_SCOPE_PARENT.items():
        if declared_parent != "parallax.snapshot.handle":
            continue
        assert parent < set(forbidden[child]), child
    # `_materializer` may not reach SQL generation, the read lock, or the
    # write-policy modules; the lowering cluster may not reach the read side.
    # Neither restriction exists on the parent. SQL generation survives the
    # `m-snapshot-read --> m-execution-lifecycle` edge only because that edge
    # belongs to `parallax.snapshot._read_result` and not to the `parallax.snapshot
    # .materialize` grant this child holds: a closure complement has no way to
    # grant a scope and withhold what that scope reaches.
    assert "parallax.core.sql_gen" in forbidden["parallax.snapshot.handle._materializer"]
    assert "parallax.core.read_lock" in forbidden["parallax.snapshot.handle._materializer"]
    assert "parallax.core.batch_write" in forbidden["parallax.snapshot.handle._materializer"]
    assert "parallax.snapshot.materialize" in forbidden["parallax.snapshot.handle._keyed_sql"]


def test_scope_descendants_inverts_the_child_chain() -> None:
    assert dag.scope_descendants("parallax.descriptor") == frozenset({"parallax.descriptor._hub"})
    assert dag.scope_descendants("parallax.snapshot.handle") == frozenset(
        {
            "parallax.snapshot.handle._materializer",
            "parallax.snapshot.handle._preflight",
            "parallax.snapshot.handle._read_scope",
            "parallax.snapshot.handle._errors",
            "parallax.snapshot.handle._family",
            "parallax.snapshot.handle._keyed_sql",
            "parallax.snapshot.handle._write_lowering",
            "parallax.snapshot.handle._retention",
        }
    )
    assert dag.scope_descendants("parallax.core.base") == frozenset()


def test_an_asymmetric_child_grant_becomes_one_named_exception() -> None:
    # `parallax.descriptor._hub` holds a grant its parent lacks. A package-scoped
    # `forbidden` source governs the child too, so the parent's row would break on
    # the seam the child legitimately imports; naming that one edge as an
    # exception keeps the row tight for every other descriptor module instead.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    assert dag.SUPPORT_SCOPE_DEPS["parallax.descriptor._hub"] == frozenset({"parallax.core.entity"})
    assert "parallax.core.entity" not in adjacency["parallax.descriptor"]
    assert "parallax.core.entity" in forbidden["parallax.descriptor"]
    assert "parallax.core.entity" not in forbidden["parallax.descriptor._hub"]
    assert dag.child_grant_exceptions(adjacency, "parallax.descriptor") == [
        "parallax.descriptor._hub -> parallax.core.entity.**"
    ]
    # Only the *direct* extra grant needs naming: ignoring the first hop also
    # withdraws every indirect chain that reaches further through it.
    assert "parallax.core.predicate" in forbidden["parallax.descriptor"]
    # A symmetric child chain — every handle child is narrower — needs none.
    assert dag.child_grant_exceptions(adjacency, "parallax.snapshot.handle") == []


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
    assert siblings <= dag.SUPPORT_SCOPE_DEPS["parallax.core.entity._instance_state"]
    assert not siblings & adjacency["parallax.core.entity"]
    assert all(dag.scope_ancestors(one) == frozenset({"parallax.core.entity"}) for one in siblings)
    assert dag.child_grant_exceptions(adjacency, "parallax.core.entity") == []
    # What the generator gives up here it does not merely lose: emitting nothing
    # means the row permits every module of that package, so the scope is
    # declared SEALED and `tools/check_scope_ownership.py` refuses the imports
    # into that package no granted scope covers — the two halves are what make
    # the grant complete.
    assert "parallax.core.entity._instance_state" in dag.SEALED_CHILD_SCOPES


def test_the_spec_marks_the_child_scopes_the_tool_isolates_and_seals() -> None:
    marked = dag.parse_child_scope_marks(dag.PYTHON_MD.read_text())
    assert set(marked["isolated"]) == dag.ISOLATED_CHILD_SCOPES
    assert set(marked["sealed"]) == dag.SEALED_CHILD_SCOPES
    for scopes in marked.values():
        for scope, parent in scopes.items():
            assert dag.CHILD_SCOPE_PARENT[scope] == parent
    dag.check_child_scope_marks(marked)


def test_a_seal_dropped_by_the_tool_alone_fails_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Sealing generates no contract, so unsealing a scope leaves every emitted
    # row byte-identical while the guarantee the spec still promises goes
    # ungraded. The mark comparison is the only thing that reports it.
    monkeypatch.setattr(
        dag,
        "SEALED_CHILD_SCOPES",
        dag.SEALED_CHILD_SCOPES - {"parallax.snapshot.handle._retention"},
    )
    with pytest.raises(ValueError, match="sealed child scopes have drifted"):
        dag.generate()


def test_a_mark_dropped_by_the_spec_alone_fails_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tampered = tmp_path / "python.md"
    original = dag.PYTHON_MD.read_text()
    edited = original.replace(
        "(support, isolated child of `parallax.core.execution_lifecycle`)",
        "(support, child of `parallax.core.execution_lifecycle`)",
        1,
    )
    assert edited != original
    tampered.write_text(edited)
    monkeypatch.setattr(dag, "PYTHON_MD", tampered)

    with pytest.raises(ValueError, match="isolated child scopes have drifted"):
        dag.generate()


def test_a_mark_naming_another_parent_fails_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A mark constrains a relationship, not a scope: §7 states each mark's
    # guarantee against the parent the row names, and the ownership walk takes
    # that parent from CHILD_SCOPE_PARENT. A row naming a different one promises
    # a guarantee nothing enforces while every scope set still matches.
    tampered = tmp_path / "python.md"
    original = dag.PYTHON_MD.read_text()
    edited = original.replace(
        "(support, sealed child of `parallax.snapshot.handle`)",
        "(support, sealed child of `parallax.core.entity`)",
        1,
    )
    assert edited != original
    tampered.write_text(edited)
    monkeypatch.setattr(dag, "PYTHON_MD", tampered)

    with pytest.raises(ValueError, match=re.escape("a sealed child of 'parallax.core.entity'")):
        dag.generate()


def test_a_mark_declared_twice_for_one_scope_fails_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # §7 declares each mark exactly once, so a second declaration for the same
    # scope is a contradiction rather than a restatement. Keeping the last would
    # let a wrong parent stand in the spec while the comparison — reading only
    # what survived — matched CHILD_SCOPE_PARENT and passed.
    tampered = tmp_path / "python.md"
    original = dag.PYTHON_MD.read_text()
    edited = original.replace(
        "(support, sealed child of `parallax.snapshot.handle`)",
        "(support, sealed child of `parallax.core.entity`, sealed child of "
        "`parallax.snapshot.handle`)",
        1,
    )
    assert edited != original
    tampered.write_text(edited)
    monkeypatch.setattr(dag, "PYTHON_MD", tampered)

    with pytest.raises(ValueError, match="a sealed child more than once"):
        dag.generate()


def test_a_support_scope_declared_by_two_prose_rows_fails_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The prose rows are one of three declarations of the support-scope graph,
    # so a second row for the same scope is a contradiction the parity check
    # never sees: the later grants would replace the earlier ones, and agreeing
    # with the fence would clear a row that disagrees with it.
    original = dag.PYTHON_MD.read_text()
    row = next(
        line
        for line in original.splitlines()
        if line.startswith("| Snapshot write-observation retention (support")
    )
    contradiction = row.replace("`m-metamodel`", "`m-sql`", 1)
    assert contradiction != row
    tampered = tmp_path / "python.md"
    tampered.write_text(original.replace(row, f"{contradiction}\n{row}", 1))
    monkeypatch.setattr(dag, "PYTHON_MD", tampered)

    with pytest.raises(ValueError, match="more than once"):
        dag.generate()


def test_check_child_scopes_rejects_a_sealed_scope_that_is_not_a_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Sealing is a property of a child relationship — the grants are complete
    # inside the package the child sits in — so it cannot describe a scope whose
    # parent nothing declares.
    monkeypatch.setattr(dag, "SEALED_CHILD_SCOPES", frozenset({"parallax.core.ghost"}))
    with pytest.raises(ValueError, match="sealed scopes are not declared child scopes"):
        dag.check_child_scopes()


# --------------------------------------------------------------------------
# The zero-grant child scope: emptiness as a contract.
# --------------------------------------------------------------------------
def test_a_zero_grant_scope_is_forbidden_every_first_party_scope() -> None:
    # `_errors` exists so `_preflight` and `_family` can raise one error class
    # while granting disjoint dependencies. Nothing but the emptiness makes that
    # legal, so the row forbids every production scope outside its own package.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    scope = "parallax.snapshot.handle._errors"
    assert dag.SUPPORT_SCOPE_DEPS[scope] == frozenset()
    assert dag.transitive_closure(adjacency, scope) == frozenset()
    blocked = set(forbidden[scope])
    assert "parallax.core.base" in blocked
    assert "parallax.core.metamodel" in blocked
    assert dag.CONFORMANCE_ROOT in blocked
    # ...and only its own package's ancestors escape, for the overlap reason
    # every child row omits them.
    assert set(dag.SUPPORT_SCOPE_DEPS) - set(dag.CHILD_SCOPE_PARENT) - blocked == {
        "parallax.snapshot.handle"
    }


def test_a_zero_grant_row_also_forbids_every_sibling_child_scope() -> None:
    # The half a scope-outside-the-package row cannot state: the shared parent
    # package overlaps the source and is skipped, but a sibling is neither
    # ancestor nor descendant, so it is a target the row can name — which makes
    # importing a declared sibling a gate failure rather than a convention.
    # `check_scope_ownership.py` covers the undeclared import-free sibling.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    scope = "parallax.snapshot.handle._errors"
    blocked = set(forbidden[scope])
    assert dag.scope_siblings(scope) <= blocked
    assert "parallax.snapshot.handle._keyed_sql" in blocked
    # The parent itself stays out, because a package-scoped row cannot forbid
    # the package it sits inside.
    assert "parallax.snapshot.handle" not in blocked


def test_the_fence_spells_a_zero_grant_scope_with_the_no_grants_target() -> None:
    declared = dag.parse_support_scope_graph(dag.PYTHON_MD.read_text())
    assert declared["parallax.snapshot.handle._errors"] == frozenset()
    # And the prose column spells the same thing, so parity holds on a scope
    # that contributes no edge at all.
    prose = dag.parse_support_scope_table(dag.PYTHON_MD.read_text())
    assert prose["parallax.snapshot.handle._errors"] == frozenset()


def test_parse_support_scope_graph_rejects_no_grants_beside_a_real_grant() -> None:
    with pytest.raises(ValueError, match=r"declare \(none\) beside a real grant"):
        dag.parse_support_scope_graph(
            "```support-scope-graph\na --> (none)\na --> parallax.core.base\n```"
        )


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
    scope = "parallax.snapshot.handle._preflight"
    assert dag.SUPPORT_SCOPE_DEPS[scope] == frozenset(
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
    # No second contract and no exception mechanism: one ordinary row per scope.
    block = dag.generate()
    assert "allow_indirect_imports" not in block
    assert block.count(f'source_modules = ["{scope}"]') == 1


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
    parent = dag.CHILD_SCOPE_PARENT["parallax.core.entity._expressions"]
    assert parent == "parallax.core.entity"
    assert set(forbidden["parallax.core.entity"]) < set(
        forbidden["parallax.core.entity._expressions"]
    )
    assert "parallax.core._formation_profile" in forbidden["parallax.core.entity._expressions"]
    # A child named as another scope's grant needs no `ignore_imports` entry from
    # its own parent's row: the parent package already covers it.
    assert dag.child_grant_exceptions(adjacency, "parallax.snapshot.handle") == []


# --------------------------------------------------------------------------
# Canary 3: a child contract blocks what the parent contract permits.
# --------------------------------------------------------------------------
def test_child_scope_contract_blocks_an_import_the_parent_permits() -> None:
    lint_imports = shutil.which("lint-imports")
    assert lint_imports is not None, "lint-imports must be installed in the dev env"

    # `m-sql` IS in the parent handle grant row, so the broad contract permits
    # this import; only the `_materializer` child contract can reject it.
    assert "parallax.core.sql_gen" in dag.SUPPORT_SCOPE_DEPS["parallax.snapshot.handle"]
    target = PY_ROOT / "packages/parallax-snapshot/src/parallax/snapshot/handle/_materializer.py"
    original = target.read_text()
    target.write_text(
        f"{original}import parallax.core.sql_gen  # deliberate child-scope violation\n"
    )
    try:
        result = subprocess.run(
            [lint_imports],
            cwd=PY_ROOT,
            capture_output=True,
            text=True,
        )
    finally:
        target.write_text(original)

    assert result.returncode != 0, result.stdout
    assert "parallax.snapshot.handle._materializer -> parallax.core.sql_gen" in result.stdout


# --------------------------------------------------------------------------
# Canary 4: the named exception admits one edge, not the whole child grant.
# --------------------------------------------------------------------------
def test_the_hub_seam_stays_confined_to_the_descriptor_child_scope() -> None:
    lint_imports = shutil.which("lint-imports")
    assert lint_imports is not None, "lint-imports must be installed in the dev env"

    canary = PY_ROOT / "packages/parallax-descriptor/src/parallax/descriptor/_canary_seam.py"
    canary.write_text("import parallax.core.entity._model  # deliberate seam violation\n")
    try:
        result = subprocess.run([lint_imports], cwd=PY_ROOT, capture_output=True, text=True)
    finally:
        canary.unlink()

    assert result.returncode != 0, result.stdout
    assert "parallax.descriptor may import only its permitted dependencies BROKEN" in result.stdout
    assert "not allowed to import parallax.core.entity" in result.stdout


# --------------------------------------------------------------------------
# Canary 5: the read-preflight seam may not reach a Database Port — by name...
# --------------------------------------------------------------------------
def test_a_direct_port_import_in_the_preflight_seam_fails_lint_imports() -> None:
    lint_imports = shutil.which("lint-imports")
    assert lint_imports is not None, "lint-imports must be installed in the dev env"

    target = PY_ROOT / "packages/parallax-snapshot/src/parallax/snapshot/handle/_preflight.py"
    original = target.read_text()
    target.write_text(f"{original}import parallax.core.db_port  # deliberate port violation\n")
    try:
        result = subprocess.run([lint_imports], cwd=PY_ROOT, capture_output=True, text=True)
    finally:
        target.write_text(original)

    assert result.returncode != 0, result.stdout
    assert (
        "parallax.snapshot.handle._preflight may import only its permitted dependencies BROKEN"
        in result.stdout
    )
    assert "parallax.snapshot.handle._preflight -> parallax.core.db_port" in result.stdout


# --------------------------------------------------------------------------
# ...and Canary 6: nor through a chain. This is the half a row carrying
# `allow_indirect_imports` cannot prove.
# --------------------------------------------------------------------------
def test_an_indirect_reach_out_of_the_preflight_seam_fails_lint_imports() -> None:
    lint_imports = shutil.which("lint-imports")
    assert lint_imports is not None, "lint-imports must be installed in the dev env"

    # The seam's row forbids `parallax.core.entity` outright, so naming
    # `parallax.core.entity._model` breaks it on that edge alone. What this canary
    # adds is the half a row carrying `allow_indirect_imports` cannot prove: where
    # that name LEADS — the Domain Model's model-formation edge, and through it the
    # chain toward the port that made the whole frontend too wide a grant.
    target = PY_ROOT / "packages/parallax-snapshot/src/parallax/snapshot/handle/_preflight.py"
    original = target.read_text()
    target.write_text(
        f"{original}import parallax.core.entity._model  # deliberate reach violation\n"
    )
    try:
        result = subprocess.run([lint_imports], cwd=PY_ROOT, capture_output=True, text=True)
    finally:
        target.write_text(original)

    assert result.returncode != 0, result.stdout
    assert (
        "parallax.snapshot.handle._preflight may import only its permitted dependencies BROKEN"
        in result.stdout
    )
    # Two hops: the seam names the Domain Model, which names model formation.
    assert "parallax.snapshot.handle._preflight -> parallax.core.entity._model" in result.stdout
    assert "parallax.core.entity._model -> parallax.core._formation_profile" in result.stdout


# --------------------------------------------------------------------------
# Canary 5b: the read composition reaches no write policy, which the parent
# scope's own row permits.
# --------------------------------------------------------------------------
def test_a_write_policy_import_in_the_read_composition_fails_lint_imports() -> None:
    lint_imports = shutil.which("lint-imports")
    assert lint_imports is not None, "lint-imports must be installed in the dev env"

    # `m-batch-write` IS in the parent handle grant row — the Write Planner's
    # strategy adapters are wired there — so the broad contract permits this
    # import and only the child row can reject it.
    assert "parallax.core.batch_write" in dag.SUPPORT_SCOPE_DEPS["parallax.snapshot.handle"]
    target = PY_ROOT / "packages/parallax-snapshot/src/parallax/snapshot/handle/_read_scope.py"
    original = target.read_text()
    target.write_text(
        f"{original}import parallax.core.batch_write  # deliberate write-policy violation\n"
    )
    try:
        result = subprocess.run([lint_imports], cwd=PY_ROOT, capture_output=True, text=True)
    finally:
        target.write_text(original)

    assert result.returncode != 0, result.stdout
    reported = " ".join(result.stdout.split())
    assert (
        "parallax.snapshot.handle._read_scope may import only its permitted dependencies BROKEN"
        in reported
    )
    assert "parallax.snapshot.handle._read_scope -> parallax.core.batch_write" in reported


# --------------------------------------------------------------------------
# Canary 6b: query authoring reaches no model. The expression scope's row is
# what proves it — the module docstring's claim is otherwise unenforced.
# --------------------------------------------------------------------------
def test_reaching_model_formation_from_the_expression_scope_fails_lint_imports() -> None:
    lint_imports = shutil.which("lint-imports")
    assert lint_imports is not None, "lint-imports must be installed in the dev env"

    target = PY_ROOT / "packages/parallax-core/src/parallax/core/entity/_expressions.py"
    original = target.read_text()
    target.write_text(f"{original}import parallax.core._formation_profile  # deliberate reach\n")
    try:
        result = subprocess.run([lint_imports], cwd=PY_ROOT, capture_output=True, text=True)
    finally:
        target.write_text(original)

    assert result.returncode != 0, result.stdout
    assert (
        "parallax.core.entity._expressions may import only its permitted dependencies BROKEN"
        in result.stdout
    )
    assert "parallax.core.entity._expressions -> parallax.core._formation_profile" in result.stdout


# --------------------------------------------------------------------------
# Canary 7: the refusal leaf may name no first-party scope outside its package.
# --------------------------------------------------------------------------
def test_a_first_party_import_in_the_refusal_leaf_fails_lint_imports() -> None:
    lint_imports = shutil.which("lint-imports")
    assert lint_imports is not None, "lint-imports must be installed in the dev env"

    # `m-metamodel` sits in the closure of BOTH consumer scopes, so neither
    # consumer's row would report it; the zero-grant row is what turns the
    # module's dependency-free claim into a gate.
    target = PY_ROOT / "packages/parallax-snapshot/src/parallax/snapshot/handle/_errors.py"
    original = target.read_text()
    target.write_text(f"{original}import parallax.core.metamodel  # deliberate leaf violation\n")
    try:
        result = subprocess.run([lint_imports], cwd=PY_ROOT, capture_output=True, text=True)
    finally:
        target.write_text(original)

    assert result.returncode != 0, result.stdout
    assert (
        "parallax.snapshot.handle._errors may import only its permitted dependencies BROKEN"
        in result.stdout
    )


# --------------------------------------------------------------------------
# ...and Canary 8: nor a sibling INSIDE its package. This is the half the
# outside-the-package row cannot state, and the reason the row names siblings.
# --------------------------------------------------------------------------
def test_a_sibling_import_in_the_refusal_leaf_fails_lint_imports() -> None:
    lint_imports = shutil.which("lint-imports")
    assert lint_imports is not None, "lint-imports must be installed in the dev env"

    # The zero-grant row names the preflight child directly, so an import inside
    # the shared parent package is rejected rather than escaping package-scoped
    # enforcement.
    target = PY_ROOT / "packages/parallax-snapshot/src/parallax/snapshot/handle/_errors.py"
    original = target.read_text()
    target.write_text(
        f"{original}import parallax.snapshot.handle._preflight  # deliberate sibling violation\n"
    )
    try:
        result = subprocess.run([lint_imports], cwd=PY_ROOT, capture_output=True, text=True)
    finally:
        target.write_text(original)

    assert result.returncode != 0, result.stdout
    assert (
        "parallax.snapshot.handle._errors may import only its permitted dependencies BROKEN"
        in result.stdout
    )
    assert (
        "parallax.snapshot.handle._errors -> parallax.snapshot.handle._preflight" in result.stdout
    )


# --------------------------------------------------------------------------
# Canary 9: an isolated child is not carried by a grant on its parent package.
# --------------------------------------------------------------------------
def test_importing_the_lifecycle_recorder_from_production_fails_lint_imports() -> None:
    lint_imports = shutil.which("lint-imports")
    assert lint_imports is not None, "lint-imports must be installed in the dev env"

    # The Snapshot handle is granted `parallax.core.execution_lifecycle` and
    # imports its private activity seam legally, so nothing about the package
    # grant stops the recorder inside it — only the isolated-child entry does.
    target = PY_ROOT / "packages/parallax-snapshot/src/parallax/snapshot/handle/_database.py"
    original = target.read_text()
    target.write_text(
        f"{original}import parallax.core.execution_lifecycle.testing  # deliberate violation\n"
    )
    try:
        result = subprocess.run([lint_imports], cwd=PY_ROOT, capture_output=True, text=True)
    finally:
        target.write_text(original)

    assert result.returncode != 0, result.stdout
    # The report wraps a long edge across lines, so it is read unwrapped.
    reported = " ".join(result.stdout.split())
    assert "parallax.snapshot.handle may import only its permitted dependencies BROKEN" in reported
    assert (
        "parallax.snapshot.handle._database -> parallax.core.execution_lifecycle.testing"
        in reported
    )


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
def test_illegal_scope_import_fails_lint_imports() -> None:
    lint_imports = shutil.which("lint-imports")
    assert lint_imports is not None, "lint-imports must be installed in the dev env"

    canary = PY_ROOT / "packages/parallax-core/src/parallax/core/base/_canary_illegal_import.py"
    # base (m-core) has no permitted dependencies, so importing predicate is illegal.
    canary.write_text("import parallax.core.predicate  # deliberate DAG violation\n")
    try:
        result = subprocess.run(
            [lint_imports],
            cwd=PY_ROOT,
            capture_output=True,
            text=True,
        )
    finally:
        canary.unlink()

    assert result.returncode != 0, result.stdout
    assert "parallax.core.base" in result.stdout
    assert "not allowed to import parallax.core.predicate" in result.stdout


def test_lint_imports_is_green_without_the_canary() -> None:
    # Guards against a leaked canary file: the clean tree must pass.
    result = subprocess.run(
        [sys.executable, "-c", "import parallax.core.base"],
        cwd=PY_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_production_import_of_unmodeled_conformance_scope_fails_lint_imports() -> None:
    # A production scope importing an *unmodeled* conformance scope (`.adapter`,
    # not `.case_format`/`.cli`) must still be caught — the whole subtree is
    # forbidden, so a new conformance module can never become importable.
    lint_imports = shutil.which("lint-imports")
    assert lint_imports is not None, "lint-imports must be installed in the dev env"

    canary = PY_ROOT / "packages/parallax-core/src/parallax/core/base/_canary_conformance_import.py"
    canary.write_text("import parallax.conformance.adapter  # deliberate boundary violation\n")
    try:
        result = subprocess.run(
            [lint_imports],
            cwd=PY_ROOT,
            capture_output=True,
            text=True,
        )
    finally:
        canary.unlink()

    assert result.returncode != 0, result.stdout
    assert "parallax.core.base" in result.stdout
    assert "parallax.conformance" in result.stdout
