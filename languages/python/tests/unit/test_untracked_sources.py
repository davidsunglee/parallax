"""Unit tests for the untracked-source guard.

Mirrors the drift-canary pattern in ``test_dag_sync.py``: the tool is imported as
a library (``pythonpath = ["tools", "tests"]``), the clean tree must pass, and a
deliberately planted untracked file must block. The canary proves the guard
actually closes the vacuous-diff-cover hole it exists for — a guard that only
ever returns 0 is indistinguishable from no guard.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import check_untracked_sources as untracked

pytestmark = pytest.mark.unit

PY_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------
# Classifier correctness
# --------------------------------------------------------------------------
def test_production_classifier_matches_package_src_only() -> None:
    assert untracked.is_production_source(
        "packages/parallax-snapshot/src/parallax/snapshot/handle/_read.py"
    )
    assert untracked.is_production_source("packages/parallax-core/src/parallax/core/base/x.py")
    # Not under a `src` root, not Python, or not a package at all.
    assert not untracked.is_production_source("packages/parallax-core/tests/helper.py")
    assert not untracked.is_production_source("packages/parallax-core/src/parallax/core/py.typed")
    assert not untracked.is_production_source("tools/check_dag_sync.py")
    assert not untracked.is_production_source("packages/parallax-core/pyproject.toml")


def test_test_classifier_matches_test_tree_only() -> None:
    assert untracked.is_test_source("tests/unit/test_transact.py")
    assert untracked.is_test_source("tests/unit/_transact_support.py")
    assert not untracked.is_test_source("tests/api_surface/public_api.json")
    assert not untracked.is_test_source("tools/check_dag_sync.py")


def test_classify_drops_unguarded_roots() -> None:
    findings = untracked.classify(
        [
            "packages/parallax-core/src/parallax/core/base/ghost.py",
            "tests/unit/ghost.py",
            "tools/ghost.py",
            "packages/parallax-core/src/parallax/core/base/ghost.txt",
        ]
    )
    assert findings == {
        untracked.PRODUCTION_LABEL: ["packages/parallax-core/src/parallax/core/base/ghost.py"],
        untracked.TEST_LABEL: ["tests/unit/ghost.py"],
    }


# --------------------------------------------------------------------------
# Canary: the clean tree passes, a planted untracked source blocks.
# --------------------------------------------------------------------------
def test_clean_tree_has_no_untracked_sources() -> None:
    # Also guards against a leaked canary from this module or test_dag_sync.py.
    assert untracked.main([]) == 0
    assert untracked.main(["--check"]) == 0


def test_untracked_production_source_fails() -> None:
    canary = PY_ROOT / "packages/parallax-core/src/parallax/core/base/_canary_untracked.py"
    canary.write_text("# deliberately unstaged production module\n")
    try:
        assert untracked.main([]) == 1
    finally:
        canary.unlink()
    assert untracked.main([]) == 0


def test_untracked_test_source_fails() -> None:
    # Named `_canary_*` rather than `test_*` so it can never be collected.
    canary = PY_ROOT / "tests/unit/_canary_untracked.py"
    canary.write_text("# deliberately unstaged test module\n")
    try:
        assert untracked.main([]) == 1
    finally:
        canary.unlink()
    assert untracked.main([]) == 0


def test_untracked_non_python_file_is_ignored() -> None:
    canary = PY_ROOT / "packages/parallax-core/src/parallax/core/base/_canary_untracked.txt"
    canary.write_text("not a Python source\n")
    try:
        assert untracked.main([]) == 0
    finally:
        canary.unlink()


def test_gitignored_production_source_still_fails() -> None:
    # `--exclude-standard` is deliberately not passed: being ignored on purpose
    # does not make a module visible to diff-cover. Coverage follows imports, so
    # an ignored module under packages/*/src is still measured while
    # contributing zero changed lines — the same vacuous pass an untracked file
    # produces. A local `.gitignore` is the cheapest way to prove the flag is
    # really absent; `git check-ignore` confirms the rule actually bites first,
    # so this cannot pass for the trivial reason that nothing was ignored.
    directory = PY_ROOT / "packages/parallax-core/src/parallax/core/base"
    canary = directory / "_canary_ignored.py"
    ignore_file = directory / ".gitignore"
    ignore_file.write_text("_canary_ignored.py\n")
    canary.write_text("# deliberately gitignored production module\n")
    try:
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", str(canary)],
            cwd=PY_ROOT,
            check=False,
        )
        assert ignored.returncode == 0, "canary was not actually ignored by git"
        assert untracked.main([]) == 1
    finally:
        canary.unlink()
        ignore_file.unlink()
    assert untracked.main([]) == 0
