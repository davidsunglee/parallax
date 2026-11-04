from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[5]


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=repository, text=True).strip()


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "--initial-branch=main")
    _git(tmp_path, "config", "user.name", "Release test")
    _git(tmp_path, "config", "user.email", "release-test@example.invalid")
    (tmp_path / "product.txt").write_text("base\n")
    _git(tmp_path, "add", "product.txt")
    _git(tmp_path, "commit", "-m", "base")
    return tmp_path


def _run_step(repository: Path, source: str, name: str) -> subprocess.CompletedProcess[str]:
    workflow: Any = yaml.safe_load((REPO / ".github/workflows/release.yml").read_text())
    step = next(step for step in workflow["jobs"]["publish"]["steps"] if step.get("name") == name)
    return subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
        cwd=repository,
        env={**os.environ, "SOURCE": source},
        text=True,
        capture_output=True,
    )


def _guard(repository: Path, source: str) -> subprocess.CompletedProcess[str]:
    return _run_step(repository, source, "Require candidate source to be present on main")


def test_production_accepts_original_candidate_ancestor(repository: Path) -> None:
    source = _git(repository, "rev-parse", "HEAD")
    _git(repository, "commit", "--allow-empty", "-m", "later main commit")
    _git(repository, "update-ref", "refs/remotes/origin/main", "HEAD")
    assert _guard(repository, source).returncode == 0


@pytest.mark.parametrize(
    ("same_tree", "advance_main"), [(True, False), (True, True), (False, False), (False, True)]
)
def test_production_rewritten_candidate_requires_exact_tree_identity(
    repository: Path, same_tree: bool, advance_main: bool
) -> None:
    base = _git(repository, "rev-parse", "HEAD")
    _git(repository, "checkout", "-b", "candidate")
    (repository / "product.txt").write_text("candidate\n")
    _git(repository, "commit", "-am", "candidate release")
    source = _git(repository, "rev-parse", "HEAD")
    _git(repository, "checkout", "main")
    assert _git(repository, "rev-parse", "HEAD") == base
    (repository / "product.txt").write_text("candidate\n" if same_tree else "different\n")
    _git(repository, "commit", "-am", "squash merge")
    if advance_main:
        (repository / "later.txt").write_text("later unrelated change\n")
        _git(repository, "add", "later.txt")
        _git(repository, "commit", "-m", "later main commit")
    _git(repository, "update-ref", "refs/remotes/origin/main", "HEAD")
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", source, "origin/main"], cwd=repository
    )
    assert ancestry.returncode == 1
    assert (_guard(repository, source).returncode == 0) is same_tree


def test_production_fetches_original_commit_after_candidate_branch_deletion(
    repository: Path,
) -> None:
    _git(repository, "checkout", "-b", "candidate")
    (repository / "product.txt").write_text("candidate\n")
    _git(repository, "commit", "-am", "candidate release")
    source = _git(repository, "rev-parse", "HEAD")
    _git(repository, "checkout", "main")
    (repository / "product.txt").write_text("candidate\n")
    _git(repository, "commit", "-am", "squash merge")
    _git(repository, "branch", "-D", "candidate")
    origin = repository.parent / f"{repository.name}-origin.git"
    _git(repository, "init", "--bare", str(origin))
    _git(repository, "remote", "add", "origin", str(origin))
    _git(repository, "push", "origin", "main", f"{source}:refs/pull/1/head")
    checkout = repository.parent / f"{repository.name}-checkout"
    _git(
        repository,
        "clone",
        "--no-local",
        "--single-branch",
        "--branch",
        "main",
        str(origin),
        str(checkout),
    )
    absent = subprocess.run(["git", "cat-file", "-e", source], cwd=checkout, capture_output=True)
    assert absent.returncode != 0
    assert _run_step(checkout, source, "Fetch attested candidate source").returncode == 0
    _git(checkout, "cat-file", "-e", source)
    assert _guard(checkout, source).returncode == 0
