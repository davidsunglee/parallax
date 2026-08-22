"""Unit tests for the production-file enforcement-scope ownership check.

Each of the tool's six findings gets a canary that drives ``main()`` to a
non-zero exit, because a gate that runs but cannot block buys nothing:

* an unowned production file (the ``parallax/snapshot/wrap.py`` shape the check
  exists for) is written to disk for real;
* an undeclared nested scope produces overlapping owners;
* an import-free module written beside a zero-grant scope, a shape neither half
  of that scope's forbidden row names;
* a module inside an isolated scope's ancestors importing it, the one edge a
  forbidden row structurally cannot state, in every spelling that reaches it;
* a sealed scope importing its own parent package beyond its grants, which is
  that same overlap seen from the other side, in every spelling that reaches it
  — and, in every one of those spellings, a granted sibling staying legal;
* an exemption that stops describing the tree — in both directions.

plus the coupling that makes the overlap arm load-bearing: a nested scope
present in ``SUPPORT_SCOPE_DEPS`` but missing from ``CHILD_SCOPE_PARENT`` is
exactly the state in which ``check_dag_sync`` would emit it into its own
parent's forbidden row, where import-linter silently skips it.

The guarantee under test is **one most-specific owner plus any declared
ancestor scopes**, not one owner outright: a file inside a declared child scope
legitimately matches the child and every declared scope above it, which is what
child scopes are for. ``test_child_scope_files_are_owned_by_their_whole_declared_chain``
pins that as a property of the scope tables, at whatever nesting depth they
declare, so the documented claim and the implemented behaviour cannot drift
apart again.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import check_dag_sync as dag
import check_scope_ownership as own

PY_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------
# Resolution correctness
# --------------------------------------------------------------------------
def test_module_path_folds_package_interfaces() -> None:
    assert (
        own.module_path("parallax-core/src/parallax/core/base/__init__.py") == "parallax.core.base"
    )
    assert (
        own.module_path("parallax-snapshot/src/parallax/snapshot/handle/_materializer.py")
        == "parallax.snapshot.handle._materializer"
    )


def test_owning_scopes_returns_the_chain_outermost_first() -> None:
    owners = own.owning_scopes("parallax.snapshot.handle._materializer", own.declared_scopes())
    assert owners == ["parallax.snapshot.handle", "parallax.snapshot.handle._materializer"]
    # ...and the most specific scope is the file's owner.
    assert owners[-1] == "parallax.snapshot.handle._materializer"


def test_a_declared_child_chain_is_not_an_overlap() -> None:
    chain = ["parallax.snapshot.handle", "parallax.snapshot.handle._materializer"]
    assert own.is_declared_chain(chain, dag.CHILD_SCOPE_PARENT)
    assert not own.is_declared_chain(chain, {})


def test_the_conformance_tree_is_out_of_scope() -> None:
    # The conformance distribution is development-only (spec §8), and its
    # exclusion is derived from `check_dag_sync.CONFORMANCE_ROOT` rather than a
    # hand-listed distribution name.
    walked = own.production_files()
    assert walked, "the production walk found no files at all"
    assert not [p for p in walked if own.module_path(p).startswith("parallax.conformance")]
    # Production distributions are all present.
    assert {p.split("/")[0] for p in walked} == {
        "parallax-core",
        "parallax-descriptor",
        "parallax-postgres",
        "parallax-snapshot",
    }


def test_every_exemption_is_genuinely_unowned_today() -> None:
    scopes = own.declared_scopes()
    for relative in own.EXEMPTIONS:
        assert own.owning_scopes(own.module_path(relative), scopes) == [], relative


def test_child_scope_files_are_owned_by_their_whole_declared_chain() -> None:
    # The check does NOT promise one owner per file. It promises one
    # most-specific owner plus ANY declared ancestor scopes, and a file inside a
    # declared child scope is the intended multi-owner state child scopes exist
    # to create — not a defect and not something to weaken the check into
    # forbidding. Asserted at whatever depth the tables declare, because
    # `scope_ancestors` and `is_declared_chain` are both recursive: a
    # parent -> child -> grandchild declaration gives three owners and is just as
    # legal. Stated as a property of the scope tables rather than as a file list,
    # so declaring another child scope does not move a literal here.
    scopes = own.declared_scopes()
    nested: dict[str, list[str]] = {}
    for path in own.production_files():
        owners = own.owning_scopes(own.module_path(path), scopes)
        if len(owners) > 1:
            nested[path] = owners
    for path, owners in nested.items():
        assert own.is_declared_chain(owners, dag.CHILD_SCOPE_PARENT), path
        assert set(owners[:-1]) == dag.scope_ancestors(owners[-1]), path
    # Every declared child scope owns at least one file, and every multiply owned
    # file belongs to one — so the nested set is exactly what §7 declares.
    assert {owners[-1] for owners in nested.values()} == set(dag.CHILD_SCOPE_PARENT)
    # ...and the tree is clean regardless: declared overlap never fails.
    assert own.main([]) == 0


# --------------------------------------------------------------------------
# The settled tree passes.
# --------------------------------------------------------------------------
def test_settled_tree_passes() -> None:
    assert own.main([]) == 0
    assert own.main(["--check"]) == 0


def test_the_success_message_states_the_guarantee_it_actually_proves(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The message is the only thing most readers of this gate ever see, so it
    # must not promise one owner per file while a file inside a declared child
    # scope has its whole chain.
    scopes = own.declared_scopes()
    nested = sum(
        1
        for path in own.production_files()
        if len(own.owning_scopes(own.module_path(path), scopes)) > 1
    )
    assert own.main([]) == 0
    out = capsys.readouterr().out
    assert "most-specific" in out
    assert "declared ancestor scopes" in out
    assert f"{nested} file(s) sit inside a declared child scope" in out


# --------------------------------------------------------------------------
# Canary 1: a real production file owned by no scope fails the check.
# --------------------------------------------------------------------------
def test_unowned_production_file_fails(capsys: pytest.CaptureFixture[str]) -> None:
    # `parallax.snapshot` is a distribution package interface, not an enforcement
    # scope, so a module dropped beside it belongs to nothing — the exact shape
    # `parallax/snapshot/wrap.py` had before it was retired.
    canary = PY_ROOT / "packages/parallax-snapshot/src/parallax/snapshot/_canary_unowned.py"
    canary.write_text('"""Deliberately outside every enforcement scope."""\n')
    try:
        assert own.main([]) == 1
    finally:
        canary.unlink()
    assert "_canary_unowned.py" in capsys.readouterr().err
    assert own.main([]) == 0


# --------------------------------------------------------------------------
# Canary 2: an undeclared nested scope produces overlapping owners.
# --------------------------------------------------------------------------
def test_undeclared_nested_scope_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Declaring `parallax.core.entity._members` as a scope without registering it
    # as a child of `parallax.core.entity` is precisely the state in which the
    # generator emits it into its parent's forbidden row and import-linter skips
    # it. The ownership check refuses it instead.
    tampered = dict(dag.SUPPORT_SCOPE_DEPS)
    tampered["parallax.core.entity._members"] = frozenset({"parallax.core.base"})
    monkeypatch.setattr(dag, "SUPPORT_SCOPE_DEPS", tampered)

    assert own.main([]) == 1
    err = capsys.readouterr().err
    assert "no declared nesting" in err
    assert "_members.py" in err


def test_a_declared_nested_scope_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    # The same nested scope, correctly registered, passes — so the failure above
    # is the missing declaration, not the nesting itself.
    tampered = dict(dag.SUPPORT_SCOPE_DEPS)
    tampered["parallax.core.entity._members"] = frozenset({"parallax.core.base"})
    monkeypatch.setattr(dag, "SUPPORT_SCOPE_DEPS", tampered)
    monkeypatch.setattr(
        dag,
        "CHILD_SCOPE_PARENT",
        {**dag.CHILD_SCOPE_PARENT, "parallax.core.entity._members": "parallax.core.entity"},
    )
    assert own.main([]) == 0


def test_dropping_a_child_declaration_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The committed child scopes depend on this coupling too: unregister one and
    # the five lowering/wrap modules stop having a legal owner chain.
    tampered = {
        child: parent
        for child, parent in dag.CHILD_SCOPE_PARENT.items()
        if child != "parallax.snapshot.handle._materializer"
    }
    monkeypatch.setattr(dag, "CHILD_SCOPE_PARENT", tampered)
    assert own.main([]) == 1
    assert "_materializer.py" in capsys.readouterr().err


# --------------------------------------------------------------------------
# Canary 3: an import-free module beside a zero-grant scope.
# --------------------------------------------------------------------------
_STDLIB_LEAF = PY_ROOT / "packages/parallax-snapshot/src/parallax/snapshot/handle/_stdlib_leaf.py"
_IMPORT_FREE = '"""Deliberately import-free, and outside every declared child scope."""\n'
_FIRST_PARTY = (
    f"{_IMPORT_FREE}\n"
    "from parallax.core.metamodel import EntityDescriptor\n"
    "\n"
    "_ = EntityDescriptor\n"
)


def test_import_free_module_beside_a_zero_grant_scope_fails(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # A shape neither half of a zero-grant scope's forbidden row names: it is not
    # a declared sibling scope, so the row cannot name it, and it reaches nothing
    # outside the package, so no indirect chain catches it either. Written to
    # disk for real, like canary 1.
    _STDLIB_LEAF.write_text(_IMPORT_FREE)
    try:
        assert own.main([]) == 1
    finally:
        _STDLIB_LEAF.unlink()
    err = capsys.readouterr().err
    assert "_stdlib_leaf.py" in err
    assert "parallax.snapshot.handle._errors cannot name it" in err
    assert own.main([]) == 0


def test_a_sibling_that_imports_first_party_is_left_to_the_import_gate() -> None:
    # What this check refuses is import-freedom, not the module's existence. The
    # same undeclared module with one first-party import passes here and is left
    # to `lint-imports`, which reports an import of it wherever the chain through
    # it leaves the package — as this module's import of `parallax.core` does.
    _STDLIB_LEAF.write_text(_FIRST_PARTY)
    try:
        assert own.main([]) == 0
    finally:
        _STDLIB_LEAF.unlink()


def test_the_rule_applies_only_where_a_zero_grant_scope_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Scoped to the reason it exists. Grant the refusal leaf anything and the
    # package stops being special: its row then has a closure to complement, and
    # an import-free sibling is no longer the row's blind spot.
    assert own.zero_grant_scopes() == {
        "parallax.snapshot.handle._errors": "parallax.snapshot.handle"
    }
    tampered = dict(dag.SUPPORT_SCOPE_DEPS)
    tampered["parallax.snapshot.handle._errors"] = frozenset({"parallax.core.base"})
    monkeypatch.setattr(dag, "SUPPORT_SCOPE_DEPS", tampered)
    assert own.zero_grant_scopes() == {}
    _STDLIB_LEAF.write_text(_IMPORT_FREE)
    try:
        assert own.main([]) == 0
    finally:
        _STDLIB_LEAF.unlink()


_NEST = PY_ROOT / "packages/parallax-snapshot/src/parallax/snapshot/handle/_nest"
_NESTED = '"""Declared beneath a sibling scope, and import-free."""\n'


def test_a_declared_grandchild_beside_a_zero_grant_scope_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A forbidden target is package-scoped, so the zero-grant row's entry for the
    # sibling `_nest` covers everything declared beneath it — an import of
    # `_nest._leaf` is reported against `_nest`. Reading only the most-specific
    # owner would reject this import-free grandchild although the row reaches it,
    # so ANY nameable owner in the chain settles the module, at any depth.
    monkeypatch.setattr(
        dag,
        "SUPPORT_SCOPE_DEPS",
        {
            **dag.SUPPORT_SCOPE_DEPS,
            "parallax.snapshot.handle._nest": frozenset({"parallax.core.base"}),
            "parallax.snapshot.handle._nest._leaf": frozenset({"parallax.core.base"}),
        },
    )
    monkeypatch.setattr(
        dag,
        "CHILD_SCOPE_PARENT",
        {
            **dag.CHILD_SCOPE_PARENT,
            "parallax.snapshot.handle._nest": "parallax.snapshot.handle",
            "parallax.snapshot.handle._nest._leaf": "parallax.snapshot.handle._nest",
        },
    )
    assert "parallax.snapshot.handle._nest" in dag.scope_siblings(
        "parallax.snapshot.handle._errors"
    )
    _NEST.mkdir()
    (_NEST / "__init__.py").write_text(_NESTED)
    (_NEST / "_leaf.py").write_text(_NESTED)
    try:
        assert own.owning_scopes("parallax.snapshot.handle._nest._leaf", own.declared_scopes()) == [
            "parallax.snapshot.handle",
            "parallax.snapshot.handle._nest",
            "parallax.snapshot.handle._nest._leaf",
        ]
        assert own.main([]) == 0
    finally:
        (_NEST / "_leaf.py").unlink()
        (_NEST / "__init__.py").unlink()
        _NEST.rmdir()


def test_first_party_imports_sees_every_import_form() -> None:
    source = (
        "import os\n"
        "import parallax.core.base\n"
        "from parallax.snapshot.handle import _errors\n"
        "from . import sibling\n"
        "from .child import leaf\n"
        "from ..materialize import view\n"
        "from .star import *\n"
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from parallax.core.metamodel import EntityDescriptor\n"
    )
    # An imported NAME is carried as a possible submodule beside the package it
    # came from, because `from p import q` is how a submodule is imported and
    # nothing in the syntax says whether `q` is one. An attribute read that way
    # contributes a dotted path no scope declares, which costs nothing.
    assert own.first_party_imports(source, "parallax.snapshot.handle") == frozenset(
        {
            "parallax.core.base",
            "parallax.snapshot.handle",
            "parallax.snapshot.handle._errors",
            "parallax.snapshot.handle.sibling",
            "parallax.snapshot.handle.child",
            "parallax.snapshot.handle.child.leaf",
            "parallax.snapshot.handle.star",
            "parallax.snapshot.materialize",
            "parallax.snapshot.materialize.view",
            "parallax.core.metamodel",
            "parallax.core.metamodel.EntityDescriptor",
        }
    )
    assert own.first_party_imports("import os\nfrom typing import Final\n", "p.q") == frozenset()


def test_first_party_reaches_keep_a_package_form_import_whole() -> None:
    source = (
        "import parallax.core.base\n"
        "from parallax.core.entity import _layout\n"
        "from parallax.core.entity._layout import EntityLayout\n"
        "from . import sibling\n"
        "from .star import *\n"
    )
    # The flattened view answers "was this module touched"; a reach answers "what
    # did one import mean". `from p import q` could have landed on `p.q` or on
    # `p`, so both candidates travel together, most specific first, and a caller
    # weighing the import against a rule reads it at whichever candidate the rule
    # covers. A star import binds no name that could be a submodule, so it
    # reaches its own module alone.
    assert own.first_party_reaches(source, "parallax.core.entity._row") == frozenset(
        {
            ("parallax.core.base",),
            ("parallax.core.entity._layout", "parallax.core.entity"),
            ("parallax.core.entity._layout.EntityLayout", "parallax.core.entity._layout"),
            ("parallax.core.entity._row.sibling", "parallax.core.entity._row"),
            ("parallax.core.entity._row.star",),
        }
    )


def test_containing_package_folds_only_a_package_interface() -> None:
    # A relative import in `handle/_read.py` is spelled against `handle`, while
    # one in `handle/__init__.py` is spelled against `handle` itself, so the two
    # file shapes resolve the same dot to the same package.
    interface = "parallax-snapshot/src/parallax/snapshot/handle/__init__.py"
    module = "parallax-snapshot/src/parallax/snapshot/handle/_read.py"
    assert own.containing_package(interface) == "parallax.snapshot.handle"
    assert own.containing_package(module) == "parallax.snapshot.handle"


# --------------------------------------------------------------------------
# Canary 4: an isolated scope imported from inside its own ancestors.
# --------------------------------------------------------------------------
_LIFECYCLE = PY_ROOT / "packages/parallax-core/src/parallax/core/execution_lifecycle"
_INTRUDER = _LIFECYCLE / "_intruder.py"
_ABSOLUTE = (
    '"""Written by a test: production code reaching its own isolated child."""\n'
    "\n"
    "from parallax.core.execution_lifecycle.testing import RecordingLifecycleProvider\n"
    "\n"
    "_ = RecordingLifecycleProvider\n"
)
_RELATIVE = (
    '"""Written by a test: the same import, spelled relatively."""\n'
    "\n"
    "from .testing import RecordingLifecycleProvider\n"
    "\n"
    "_ = RecordingLifecycleProvider\n"
)
_ABSOLUTE_PACKAGE = (
    '"""Written by a test: the child package itself, by its dotted path."""\n'
    "\n"
    "from parallax.core.execution_lifecycle import testing\n"
    "\n"
    "_ = testing\n"
)
_RELATIVE_PACKAGE = (
    '"""Written by a test: the child package itself, spelled relatively."""\n'
    "\n"
    "from . import testing\n"
    "\n"
    "_ = testing\n"
)


@pytest.mark.parametrize("source", [_ABSOLUTE, _RELATIVE, _ABSOLUTE_PACKAGE, _RELATIVE_PACKAGE])
def test_a_production_module_importing_its_own_isolated_child_fails(
    source: str, capsys: pytest.CaptureFixture[str]
) -> None:
    # The half of "no production scope imports the recorder" that no forbidden
    # row can carry: a row sourced at `parallax.core.execution_lifecycle` may not
    # name a module inside its own source package, so import-linter skips the
    # entry. Every spelling of that import is the same edge: relative or dotted,
    # naming a member of the scope or naming the scope itself — the last one
    # binds the child package through its parent, which is the form a reader is
    # likeliest to mistake for an import of the parent alone.
    _INTRUDER.write_text(source)
    try:
        assert own.main([]) == 1
    finally:
        _INTRUDER.unlink()
    err = capsys.readouterr().err
    assert "imports of an isolated scope from inside its own ancestors" in err
    assert "_intruder.py (imports parallax.core.execution_lifecycle.testing" in err
    assert own.main([]) == 0


def test_the_isolated_scope_may_import_its_own_parent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Scoped to the direction that has no contract: the recorder's own row DOES
    # state what it may reach, and it is granted the parent package, so a module
    # written inside the isolated scope is left to `lint-imports`.
    inside = _LIFECYCLE / "testing" / "_probe.py"
    inside.write_text(
        '"""Written by a test: inside the isolated scope, reaching its parent."""\n'
        "\n"
        "from parallax.core.execution_lifecycle import RootExecution\n"
        "\n"
        "_ = RootExecution\n"
    )
    try:
        assert own.main([]) == 0
    finally:
        inside.unlink()


# --------------------------------------------------------------------------
# Canary 5: a sealed scope reaching its own parent package.
# --------------------------------------------------------------------------
_ROW = "parallax.core.entity._row"
_ROW_FILE = "parallax-core/src/parallax/core/entity/_row.py"


def _without_sibling_grants(monkeypatch: pytest.MonkeyPatch) -> None:
    """Withdraw the two sibling grants the row scope's imports stand on."""
    monkeypatch.setattr(
        dag,
        "SUPPORT_SCOPE_DEPS",
        {**dag.SUPPORT_SCOPE_DEPS, _ROW: frozenset({"parallax.core.metamodel"})},
    )


def test_a_sealed_scope_reaching_its_parent_package_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The mirror image of canary 4: a row sourced at the child overlaps its own
    # parent package, so import-linter can neither forbid a module of that
    # package nor except one. Withdrawing the two grants the row scope's imports
    # stand on states an undeclared intra-package reach without editing
    # production source, and both are refused — one finding per import, not one
    # per file.
    assert own.imports_escaping_a_sealed_child_row(own.production_files()) == []
    _without_sibling_grants(monkeypatch)
    assert own.main([]) == 1
    err = capsys.readouterr().err
    assert "imports of its own parent package a sealed scope's contract cannot reject" in err
    assert f"{_ROW_FILE} (imports parallax.core.entity._graph_input, which {_ROW}" in err
    assert f"{_ROW_FILE} (imports parallax.core.entity._layout, which {_ROW}" in err


_PROBE = PY_ROOT / "packages/parallax-core/src/parallax/core/entity/_probe.py"
_PROBE_SCOPE = "parallax.core.entity._probe"


def _sealed_probe_scope(monkeypatch: pytest.MonkeyPatch, granted: str) -> None:
    """Declare `_probe` a sealed child of the Entity frontend granted `granted`."""
    monkeypatch.setattr(
        dag,
        "SUPPORT_SCOPE_DEPS",
        {**dag.SUPPORT_SCOPE_DEPS, _PROBE_SCOPE: frozenset({granted})},
    )
    monkeypatch.setattr(
        dag,
        "CHILD_SCOPE_PARENT",
        {**dag.CHILD_SCOPE_PARENT, _PROBE_SCOPE: "parallax.core.entity"},
    )
    monkeypatch.setattr(dag, "SEALED_CHILD_SCOPES", dag.SEALED_CHILD_SCOPES | {_PROBE_SCOPE})


def _spellings(module: str, name: str) -> list[tuple[str, str, str]]:
    """Every way one file reaches `parallax.core.entity.<module>`, with what escapes.

    The third element is the module a reach touching no grant is reported at:
    the package-form spellings bind the sibling through its parent, and the
    parent is the candidate that certainly is a module.
    """
    dotted = f"parallax.core.entity.{module}"
    return [
        (f"from {dotted} import {name}", name, dotted),
        (f"from .{module} import {name}", name, dotted),
        (f"from parallax.core.entity import {module}", module, "parallax.core.entity"),
        (f"from . import {module}", module, "parallax.core.entity"),
        (f"import {dotted}", dotted, dotted),
    ]


def _write_probe(statement: str, bound: str) -> None:
    _PROBE.write_text(
        '"""Written by a test: one spelling of a sealed scope\'s intra-package reach."""\n'
        "\n"
        f"{statement}\n"
        "\n"
        f"_ = {bound}\n"
    )


@pytest.mark.parametrize(
    ("statement", "bound", "escaped"), _spellings("_errors", "EntityDefinitionError")
)
def test_a_sealed_scope_reaching_what_its_row_already_permits_fails(
    statement: str,
    bound: str,
    escaped: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The reach no contract could report, which is the whole reason to seal a
    # scope: `parallax.core.entity._errors` imports the accepted Metamodel and
    # nothing else, so a neighbour granted the Metamodel reaches it without any
    # chain leaving the row for import-linter to name. Declared here as a scope
    # of its own so the shape is stated over a file written for it, rather than
    # over the committed source of a scope that does not make this reach. Every
    # spelling is the same reach, including the two that bind the neighbour
    # through the parent package and are reported there.
    _sealed_probe_scope(monkeypatch, "parallax.core.metamodel")
    _write_probe(statement, bound)
    try:
        assert own.main([]) == 1
    finally:
        _PROBE.unlink()
    err = capsys.readouterr().err
    assert f"_probe.py (imports {escaped}, which {_PROBE_SCOPE}" in err
    assert own.main([]) == 0


@pytest.mark.parametrize(
    ("statement", "bound"),
    [(statement, bound) for statement, bound, _ in _spellings("_layout", "EntityLayout")],
)
def test_a_sealed_scope_reaching_a_granted_sibling_passes_in_every_spelling(
    statement: str, bound: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The other edge of the same rule, and the one a seal must not cost: a grant
    # is what the row would have permitted had it been able to speak, so the
    # sibling it names stays legal however the import is written. `from parent
    # import sibling` binds the sibling exactly as its dotted path does, so
    # reading that form as a reach at the parent alone would reject a dependency
    # §7 grants — and would make the seal a rule about spelling, not about reach.
    _sealed_probe_scope(monkeypatch, "parallax.core.entity._layout")
    _write_probe(statement, bound)
    try:
        assert own.imports_escaping_a_sealed_child_row(own.production_files()) == []
        assert own.main([]) == 0
    finally:
        _PROBE.unlink()


def test_the_sealed_rule_applies_only_to_a_scope_declared_sealed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Scoped to the declaration rather than to the package: an intra-package
    # import is what child scopes ordinarily do — `_expressions` reaches the
    # frontend's shared error module, and every write-lowering scope reaches its
    # siblings — so nothing here judges a scope §7 has not sealed.
    assert set(dag.CHILD_SCOPE_PARENT) >= dag.SEALED_CHILD_SCOPES
    _without_sibling_grants(monkeypatch)
    monkeypatch.setattr(dag, "SEALED_CHILD_SCOPES", frozenset[str]())
    assert own.main([]) == 0


def test_sealing_a_scope_that_reaches_its_parent_today_would_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The other half of the same boundary, over untampered grants: `_expressions`
    # is narrower than its parent for the same reason the sealed three are, but
    # it does reach a module of that parent its row does not name — so sealing it
    # would be a claim about the tree that is not true, and the gate says so.
    monkeypatch.setattr(
        dag, "SEALED_CHILD_SCOPES", frozenset({"parallax.core.entity._expressions"})
    )
    assert own.imports_escaping_a_sealed_child_row(own.production_files()) == [
        "parallax-core/src/parallax/core/entity/_expressions.py "
        "(imports parallax.core.entity._errors, which "
        "parallax.core.entity._expressions's own row cannot reject)"
    ]


# --------------------------------------------------------------------------
# Canary 6: an exemption that no longer describes the tree.
# --------------------------------------------------------------------------
def test_exemption_for_a_missing_file_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # An exemption outliving the file it excused would quietly widen the check's
    # blind spot the next time a file took that path.
    gone = "parallax-core/src/parallax/core/gone.py"
    monkeypatch.setattr(own, "EXEMPTIONS", {**own.EXEMPTIONS, gone: "moved away"})
    assert own.main([]) == 1
    err = capsys.readouterr().err
    assert "no longer describe the tree" in err
    assert f"{gone} (no such file)" in err


def test_exemption_for_an_owned_file_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # An exemption kept alive after a scope grew to cover the file is dead weight
    # that hides which scope actually owns it.
    owned = "parallax-snapshot/src/parallax/snapshot/handle/_materializer.py"
    monkeypatch.setattr(own, "EXEMPTIONS", {**own.EXEMPTIONS, owned: "stale justification"})
    assert own.main([]) == 1
    err = capsys.readouterr().err
    assert "no longer describe the tree" in err
    assert "now owned by parallax.snapshot.handle._materializer" in err
