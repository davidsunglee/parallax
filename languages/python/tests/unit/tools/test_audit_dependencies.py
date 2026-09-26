"""The dependency-audit coordinator: one deptry run per workspace member with the
shared flags stated once, every native check after them, and a failure in any
part failing the whole."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

import audit_dependencies
from audit_dependencies import NativeCheck, audit, deptry_arguments, run_deptry
from python_workspace import Workspace, load_workspace
from tests.unit.tools._workspace_support import write_member, write_root

_MEMBERS = {
    "parallax-core": {"parallax/core/__init__.py": ""},
    "parallax-postgres": {"parallax/postgres/__init__.py": "import parallax.core\n"},
    "parallax-snapshot": {"parallax/snapshot/__init__.py": "import parallax.core\n"},
}


class _RecordingDeptry:
    def __init__(self, failing: frozenset[str] = frozenset()) -> None:
        self.calls: list[list[str]] = []
        self._failing = failing

    def __call__(self, arguments: Sequence[str]) -> int:
        self.calls.append(list(arguments))
        config = Path(arguments[arguments.index("--config") + 1]).resolve()
        return 1 if config.parent.name in self._failing else 0


def _workspace(repo: Path, members: dict[str, dict[str, str]] = _MEMBERS) -> Path:
    root = write_root(repo, sources=members.keys())
    for name, modules in members.items():
        write_member(repo, name, modules)
    return root


def _option(arguments: Sequence[str], option: str) -> str:
    return arguments[arguments.index(option) + 1]


def test_deptry_runs_once_per_member_against_its_manifest_and_source(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    deptry = _RecordingDeptry()

    assert audit(load_workspace(root), deptry, native_checks=()) == []

    members = root / "packages"
    assert [Path(_option(call, "--config")).resolve() for call in deptry.calls] == [
        members / name / "pyproject.toml" for name in sorted(_MEMBERS)
    ]
    assert [Path(call[-1]).resolve() for call in deptry.calls] == [
        members / name / "src" for name in sorted(_MEMBERS)
    ]
    assert root / "pyproject.toml" not in {
        Path(_option(call, "--config")).resolve() for call in deptry.calls
    }


def test_every_member_shares_the_flags_stated_once(tmp_path: Path) -> None:
    workspace = load_workspace(_workspace(tmp_path))

    for member in workspace.members:
        arguments = deptry_arguments(workspace, member)
        assert _option(arguments, "--known-first-party") == "parallax"
        assert _option(arguments, "--package-module-name-map") == (
            "psycopg-pool=psycopg_pool,pyyaml=yaml"
        )
        assert _option(arguments, "--per-rule-ignores") == (
            "DEP002=parallax-core|parallax-postgres|parallax-snapshot"
        )


def test_the_sibling_ignore_follows_the_workspace_members(tmp_path: Path) -> None:
    members = {**_MEMBERS, "parallax-aws": {"parallax/aws/__init__.py": ""}}
    workspace = load_workspace(_workspace(tmp_path, members))

    assert _option(deptry_arguments(workspace, workspace.members[0]), "--per-rule-ignores") == (
        "DEP002=parallax-aws|parallax-core|parallax-postgres|parallax-snapshot"
    )


def test_every_part_runs_and_each_failure_is_named(tmp_path: Path) -> None:
    deptry = _RecordingDeptry(failing=frozenset({"parallax-postgres"}))
    ran: list[str] = []

    def native(name: str, status: int) -> NativeCheck:
        def check() -> int:
            ran.append(name)
            return status

        return name, check

    checks = [native("siblings", 1), native("inventory", 0)]

    failed = audit(load_workspace(_workspace(tmp_path)), deptry, checks)

    assert failed == ["deptry parallax-postgres", "siblings"]
    assert len(deptry.calls) == len(_MEMBERS)
    assert ran == ["siblings", "inventory"]


def _probe(repo: Path, dependencies: Sequence[str]) -> Workspace:
    root = write_root(repo, sources=["parallax-probe"])
    write_member(
        repo,
        "parallax-probe",
        {"parallax/probe/__init__.py": "import yaml\n"},
        dependencies=dependencies,
    )
    return load_workspace(root)


def test_deptry_reports_an_undeclared_import(tmp_path: Path) -> None:
    workspace = _probe(tmp_path, [])

    assert run_deptry(deptry_arguments(workspace, workspace.members[0])) == 1


def test_deptry_passes_a_declared_import_under_the_shared_module_map(tmp_path: Path) -> None:
    workspace = _probe(tmp_path, ["pyyaml"])

    assert run_deptry(deptry_arguments(workspace, workspace.members[0])) == 0


@pytest.mark.parametrize(("failed", "status"), [([], 0), (["deptry parallax-core"], 1)])
def test_main_exits_non_zero_exactly_when_a_part_failed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failed: list[str],
    status: int,
) -> None:
    def audit(*_: object) -> list[str]:
        return failed

    monkeypatch.setattr(audit_dependencies, "audit", audit)

    assert audit_dependencies.main([]) == status
    output = capsys.readouterr()
    assert ("deptry parallax-core" in output.err) is bool(failed)
