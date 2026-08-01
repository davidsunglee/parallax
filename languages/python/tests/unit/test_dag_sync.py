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
* child scopes are emitted as contract *sources* only, with a ``lint-imports``
  canary proving a child contract blocks an import its parent's row permits, and
  a second canary proving the one asymmetric child grant — the descriptor
  package's Hub-construction seam — is admitted for that child alone and stays
  forbidden to every other module its parent's row governs;
* a zero-grant child scope, whose emptiness IS its contract, with a canary
  proving any first-party import inside it breaks the gate; and
* closure exclusions, the second contract that asks whether a scope NAMES a
  boundary its own granted closure reaches — with a canary importing the
  Database Port directly into the read-preflight seam.
"""

from __future__ import annotations

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
    closure = dag.transitive_closure(adjacency, "parallax.core.op_algebra")
    # op-algebra depends on metamodel + inheritance, inheritance reaches model
    # formation, and both reach core. No path to the descriptor scope: no
    # behavioral module depends on descriptor.
    assert closure == {
        "parallax.core.inheritance",
        "parallax.core.metamodel",
        "parallax.core.model_formation",
        "parallax.core.base",
    }
    assert dag.transitive_closure(adjacency, "parallax.core.base") == frozenset()


def test_forbidden_respects_the_dag() -> None:
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    # A permitted dependency is never forbidden...
    assert "parallax.core.base" not in forbidden["parallax.core.op_algebra"]
    # ...while a non-edge is.
    assert "parallax.core.sql_gen" in forbidden["parallax.core.op_algebra"]
    # Nothing in the common runtime depends on the descriptor distribution, so
    # every core scope — behavioral scopes and the entity frontend alike — is
    # forbidden from importing it. The one descriptor/runtime edge runs the other
    # way, and only from the descriptor package's private hub child scope.
    assert "parallax.descriptor" in forbidden["parallax.core.op_algebra"]
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
    adjacency = dag.build_adjacency([("m-agg", "m-op-algebra")])
    assert adjacency["parallax.core.op_algebra"] == frozenset()


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
    del declared["parallax.snapshot.handle._wrap"]
    del prose["parallax.snapshot.handle._wrap"]
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
            "parallax.core.db_port",
            "parallax.core.db_error",
            "parallax.core.dialect",
        }
    )
    # The composition-root row is application-owned and declares no scope.
    assert "parallax.snapshot" not in prose


def test_parse_support_scope_table_expands_the_child_group_row() -> None:
    # The write-lowering row names five scopes in the *owner* cell, four of
    # them abbreviated (`._write_types`), because its enforcement-scope cell
    # says "those five scopes". All five must resolve, sharing one grant row.
    prose = dag.parse_support_scope_table(dag.PYTHON_MD.read_text())
    group = [
        "parallax.snapshot.handle._family",
        "parallax.snapshot.handle._write_types",
        "parallax.snapshot.handle._keyed_sql",
        "parallax.snapshot.handle._write_lowering",
        "parallax.snapshot.handle._step_lowering",
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


def test_a_tampered_prose_row_alone_fails_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # THE canary this arm exists for: the fence and `SUPPORT_SCOPE_DEPS` are
    # untouched and agree, so the pre-existing comparison passes; only the
    # prose row is edited, and generation must still refuse.
    tampered = tmp_path / "python.md"
    original = dag.PYTHON_MD.read_text()
    edited = original.replace(
        "| `parallax.snapshot.handle._wrap` | `parallax.snapshot.materialize`, "
        "`parallax.core.entity`, `m-metamodel`,",
        "| `parallax.snapshot.handle._wrap` | `parallax.snapshot.materialize`, "
        "`parallax.core.entity`, `m-sql`, `m-metamodel`,",
        1,
    )
    assert edited != original
    tampered.write_text(edited)
    monkeypatch.setattr(dag, "PYTHON_MD", tampered)

    # The fence still matches the tool exactly — the pre-existing arm passes,
    # so only the new prose arm can reject this edit.
    assert dag.parse_support_scope_graph(edited) == dict(dag.SUPPORT_SCOPE_DEPS)
    with pytest.raises(ValueError, match=r"'parallax\.snapshot\.handle\._wrap' has drifted"):
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
        if not line.startswith("| Snapshot handle wrapping (support")
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
        "parallax.snapshot.handle._wrap --> parallax.core.metamodel\n",
        "parallax.snapshot.handle._wrap --> parallax.core.metamodel\n"
        "parallax.snapshot.handle._wrap --> parallax.core.sql_gen\n",
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
            "parallax.snapshot.handle._wrap": dag.SUPPORT_SCOPE_DEPS[
                "parallax.snapshot.handle._wrap"
            ]
            | {"parallax.core.sql_gen"},
        },
    )

    with pytest.raises(ValueError, match=r"'parallax\.snapshot\.handle\._wrap' has drifted"):
        dag.generate()


def test_a_tampered_prose_row_alone_exits_one_at_the_command() -> None:
    # Command level, not library level: `python-check-dag-sync` runs the script, so the
    # prose arm has to block there too. Same write-run-restore shape as the
    # `lint-imports` canaries below, against the real committed spec.
    original = dag.PYTHON_MD.read_text()
    edited = original.replace(
        "| `parallax.snapshot.handle._wrap` | `parallax.snapshot.materialize`, "
        "`parallax.core.entity`, `m-metamodel`,",
        "| `parallax.snapshot.handle._wrap` | `parallax.snapshot.materialize`, "
        "`parallax.core.entity`, `m-sql`, `m-metamodel`,",
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
    assert "parallax.snapshot.handle._wrap" in result.stderr
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


# --------------------------------------------------------------------------
# Child scopes: sources only.
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


def test_child_scopes_are_never_forbidden_targets() -> None:
    # import-linter >= 2.12 silently skips a forbidden module that overlaps the
    # contract's own source package, so a child inside its parent's row would be
    # a contract that looks present and enforces nothing. Children are sources
    # only; the parent's row already covers every descendant for other scopes.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    assert set(dag.CHILD_SCOPE_PARENT) <= set(forbidden)
    for scope, blocked in forbidden.items():
        assert not (set(blocked) & set(dag.CHILD_SCOPE_PARENT)), scope


def test_a_child_row_omits_its_own_ancestors() -> None:
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    forbidden = dag.compute_forbidden(adjacency)
    assert "parallax.snapshot.handle" not in forbidden["parallax.snapshot.handle._wrap"]
    assert dag.scope_ancestors("parallax.snapshot.handle._wrap") == frozenset(
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
    # `_wrap` may not reach SQL generation; the lowering cluster may not reach
    # the read side. Neither restriction exists on the parent.
    assert "parallax.core.sql_gen" in forbidden["parallax.snapshot.handle._wrap"]
    assert "parallax.snapshot.materialize" in forbidden["parallax.snapshot.handle._keyed_sql"]


def test_scope_descendants_inverts_the_child_chain() -> None:
    assert dag.scope_descendants("parallax.descriptor") == frozenset({"parallax.descriptor._hub"})
    assert dag.scope_descendants("parallax.snapshot.handle") == frozenset(
        {
            "parallax.snapshot.handle._wrap",
            "parallax.snapshot.handle._preflight",
            "parallax.snapshot.handle._errors",
            "parallax.snapshot.handle._family",
            "parallax.snapshot.handle._write_types",
            "parallax.snapshot.handle._keyed_sql",
            "parallax.snapshot.handle._write_lowering",
            "parallax.snapshot.handle._step_lowering",
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
    assert "parallax.core.op_algebra" in forbidden["parallax.descriptor"]
    # A symmetric child chain — every handle child is narrower — needs none.
    assert dag.child_grant_exceptions(adjacency, "parallax.snapshot.handle") == []


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
# Closure exclusions: the boundary a scope's own grants reach.
# --------------------------------------------------------------------------
def test_the_preflight_seam_is_forbidden_the_port_its_own_closure_reaches() -> None:
    # The gap the complement alone leaves open: `parallax.core.entity` reaches
    # `_formation_profile -> opt_lock -> unit_work -> db_port`, so the port is
    # inside the seam's closure and its row can never forbid it.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    scope = "parallax.snapshot.handle._preflight"
    assert "parallax.core.db_port" in dag.transitive_closure(adjacency, scope)
    assert "parallax.core.db_port" not in dag.compute_forbidden(adjacency)[scope]
    # The exclusion is what closes it, as a second contract carrying
    # `allow_indirect_imports` — the granted chain stays legal, the name does not.
    assert dag.CLOSURE_EXCLUSIONS[scope] == frozenset({"parallax.core.db_port"})
    block = dag.generate()
    assert f'name = "{scope} names none of its excluded scopes itself"' in block
    assert "allow_indirect_imports = true" in block


def test_check_closure_exclusions_rejects_an_excluded_direct_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Permitting and forbidding one edge is a spec contradiction, not a stricter
    # rule: the row would grant `m-op-algebra` while the exclusion refused it.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    monkeypatch.setattr(
        dag,
        "CLOSURE_EXCLUSIONS",
        {"parallax.snapshot.handle._preflight": frozenset({"parallax.core.op_algebra"})},
    )
    with pytest.raises(ValueError, match="both grants and excludes"):
        dag.check_closure_exclusions(adjacency)


def test_check_closure_exclusions_rejects_an_exclusion_that_carries_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A scope the source cannot reach at all is already forbidden by the
    # complement — and forbidden more strongly, indirect chains included — so an
    # exclusion there would look load-bearing and enforce nothing new.
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    monkeypatch.setattr(
        dag,
        "CLOSURE_EXCLUSIONS",
        {"parallax.snapshot.handle._preflight": frozenset({"parallax.core.sql_gen"})},
    )
    with pytest.raises(ValueError, match="grant closure does not reach"):
        dag.check_closure_exclusions(adjacency)


def test_check_closure_exclusions_rejects_an_undeclared_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adjacency = dag.build_adjacency(dag.parse_dependency_graph(dag.MODULES_MD.read_text()))
    monkeypatch.setattr(dag, "CLOSURE_EXCLUSIONS", {"parallax.core.ghost": frozenset[str]()})
    with pytest.raises(ValueError, match="undeclared scope"):
        dag.check_closure_exclusions(adjacency)


# --------------------------------------------------------------------------
# Canary 3: a child contract blocks what the parent contract permits.
# --------------------------------------------------------------------------
def test_child_scope_contract_blocks_an_import_the_parent_permits() -> None:
    lint_imports = shutil.which("lint-imports")
    assert lint_imports is not None, "lint-imports must be installed in the dev env"

    # `m-sql` IS in the parent handle grant row, so the broad contract permits
    # this import; only the `_wrap` child contract can reject it.
    assert "parallax.core.sql_gen" in dag.SUPPORT_SCOPE_DEPS["parallax.snapshot.handle"]
    target = PY_ROOT / "packages/parallax-snapshot/src/parallax/snapshot/handle/_wrap.py"
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
    assert "parallax.snapshot.handle._wrap" in result.stdout
    assert "not allowed to import parallax.core.sql_gen" in result.stdout


# --------------------------------------------------------------------------
# Canary 4: the named exception admits one edge, not the whole child grant.
# --------------------------------------------------------------------------
def test_the_hub_seam_stays_confined_to_the_descriptor_child_scope() -> None:
    lint_imports = shutil.which("lint-imports")
    assert lint_imports is not None, "lint-imports must be installed in the dev env"

    canary = PY_ROOT / "packages/parallax-descriptor/src/parallax/descriptor/_canary_seam.py"
    canary.write_text("import parallax.core.entity._hub  # deliberate seam violation\n")
    try:
        result = subprocess.run([lint_imports], cwd=PY_ROOT, capture_output=True, text=True)
    finally:
        canary.unlink()

    assert result.returncode != 0, result.stdout
    assert "parallax.descriptor may import only its permitted dependencies BROKEN" in result.stdout
    assert "not allowed to import parallax.core.entity" in result.stdout


# --------------------------------------------------------------------------
# Canary 5: the read-preflight seam may not name a Database Port.
# --------------------------------------------------------------------------
def test_a_direct_port_import_in_the_preflight_seam_fails_lint_imports() -> None:
    lint_imports = shutil.which("lint-imports")
    assert lint_imports is not None, "lint-imports must be installed in the dev env"

    # The seam's own row cannot reject this — `parallax.core.db_port` is inside
    # the closure its `parallax.core.entity` grant reaches — so only the closure
    # exclusion's contract can, which is the whole reason the module is scoped
    # apart from its package.
    target = PY_ROOT / "packages/parallax-snapshot/src/parallax/snapshot/handle/_preflight.py"
    original = target.read_text()
    target.write_text(f"{original}import parallax.core.db_port  # deliberate port violation\n")
    try:
        result = subprocess.run([lint_imports], cwd=PY_ROOT, capture_output=True, text=True)
    finally:
        target.write_text(original)

    assert result.returncode != 0, result.stdout
    assert (
        "parallax.snapshot.handle._preflight names none of its excluded scopes itself BROKEN"
        in result.stdout
    )
    # The reported chain is one hop long: what the contract catches is the name,
    # not the reach.
    assert "parallax.snapshot.handle._preflight -> parallax.core.db_port" in result.stdout


# --------------------------------------------------------------------------
# Canary 6: the refusal leaf may name no first-party scope at all.
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
    # base (m-core) has no permitted dependencies, so importing op_algebra is illegal.
    canary.write_text("import parallax.core.op_algebra  # deliberate DAG violation\n")
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
    assert "not allowed to import parallax.core.op_algebra" in result.stdout


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
