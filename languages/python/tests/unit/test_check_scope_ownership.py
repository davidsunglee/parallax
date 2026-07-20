"""Unit tests for the production-file enforcement-scope ownership check.

Each of the tool's three findings gets a canary that drives ``main()`` to a
non-zero exit, because a gate that runs but cannot block buys nothing:

* an unowned production file (the ``parallax/snapshot/wrap.py`` shape the check
  exists for) is written to disk for real;
* an undeclared nested scope produces overlapping owners;
* an exemption that stops describing the tree — in both directions.

plus the coupling that makes the overlap arm load-bearing: a nested scope
present in ``SUPPORT_SCOPE_DEPS`` but missing from ``CHILD_SCOPE_PARENT`` is
exactly the state in which ``check_dag_sync`` would emit it into its own
parent's forbidden row, where import-linter silently skips it.

The guarantee under test is **one most-specific owner plus any declared
ancestor scopes**, not one owner outright: five committed files legitimately
match both a child scope and its parent, which is what child scopes are for.
``test_declared_child_scope_files_are_owned_twice`` pins that, so the
documented claim and the implemented behaviour cannot drift apart again.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import check_dag_sync as dag
import check_scope_ownership as own

pytestmark = pytest.mark.unit

PY_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------
# Resolution correctness
# --------------------------------------------------------------------------
def test_module_path_folds_package_interfaces() -> None:
    assert (
        own.module_path("parallax-core/src/parallax/core/base/__init__.py") == "parallax.core.base"
    )
    assert (
        own.module_path("parallax-snapshot/src/parallax/snapshot/handle/_wrap.py")
        == "parallax.snapshot.handle._wrap"
    )


def test_owning_scopes_returns_the_chain_outermost_first() -> None:
    owners = own.owning_scopes("parallax.snapshot.handle._wrap", own.declared_scopes())
    assert owners == ["parallax.snapshot.handle", "parallax.snapshot.handle._wrap"]
    # ...and the most specific scope is the file's owner.
    assert owners[-1] == "parallax.snapshot.handle._wrap"


def test_a_declared_child_chain_is_not_an_overlap() -> None:
    chain = ["parallax.snapshot.handle", "parallax.snapshot.handle._wrap"]
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
        "parallax-postgres",
        "parallax-snapshot",
    }


def test_every_exemption_is_genuinely_unowned_today() -> None:
    scopes = own.declared_scopes()
    for relative in own.EXEMPTIONS:
        assert own.owning_scopes(own.module_path(relative), scopes) == [], relative


def test_declared_child_scope_files_are_owned_twice() -> None:
    # The check does NOT promise one owner per file. It promises one
    # most-specific owner plus declared ancestors, and these five files are the
    # intended two-owner state child scopes exist to create — not a defect and
    # not something to weaken the check into forbidding.
    scopes = own.declared_scopes()
    doubled = {
        path: own.owning_scopes(own.module_path(path), scopes)
        for path in own.production_files()
        if len(own.owning_scopes(own.module_path(path), scopes)) > 1
    }
    assert sorted(Path(path).name for path in doubled) == [
        "_family.py",
        "_keyed_sql.py",
        "_wrap.py",
        "_write_lowering.py",
        "_write_types.py",
    ]
    for path, owners in doubled.items():
        assert own.is_declared_chain(owners, dag.CHILD_SCOPE_PARENT), path
        assert owners[0] == "parallax.snapshot.handle", path
        assert owners[-1].startswith("parallax.snapshot.handle."), path
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
    # must not promise one owner per file when five files have two.
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
    # `parallax/snapshot/wrap.py` had before COR-42 retired it.
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
    # Declaring `parallax.core.entity.expressions` as a scope without registering
    # it as a child of `parallax.core.entity` is precisely the state in which the
    # generator emits it into its parent's forbidden row and import-linter skips
    # it. The ownership check refuses it instead.
    tampered = dict(dag.SUPPORT_SCOPE_DEPS)
    tampered["parallax.core.entity.expressions"] = frozenset({"parallax.core.descriptor"})
    monkeypatch.setattr(dag, "SUPPORT_SCOPE_DEPS", tampered)

    assert own.main([]) == 1
    err = capsys.readouterr().err
    assert "no declared nesting" in err
    assert "expressions.py" in err


def test_a_declared_nested_scope_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    # The same nested scope, correctly registered, passes — so the failure above
    # is the missing declaration, not the nesting itself.
    tampered = dict(dag.SUPPORT_SCOPE_DEPS)
    tampered["parallax.core.entity.expressions"] = frozenset({"parallax.core.descriptor"})
    monkeypatch.setattr(dag, "SUPPORT_SCOPE_DEPS", tampered)
    monkeypatch.setattr(
        dag,
        "CHILD_SCOPE_PARENT",
        {**dag.CHILD_SCOPE_PARENT, "parallax.core.entity.expressions": "parallax.core.entity"},
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
        if child != "parallax.snapshot.handle._wrap"
    }
    monkeypatch.setattr(dag, "CHILD_SCOPE_PARENT", tampered)
    assert own.main([]) == 1
    assert "_wrap.py" in capsys.readouterr().err


# --------------------------------------------------------------------------
# Canary 3: an exemption that no longer describes the tree.
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
    owned = "parallax-snapshot/src/parallax/snapshot/handle/_wrap.py"
    monkeypatch.setattr(own, "EXEMPTIONS", {**own.EXEMPTIONS, owned: "stale justification"})
    assert own.main([]) == 1
    err = capsys.readouterr().err
    assert "no longer describe the tree" in err
    assert "now owned by parallax.snapshot.handle._wrap" in err
