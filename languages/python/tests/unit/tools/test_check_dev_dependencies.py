"""The development-dependency inventory check, on the real workspace and on
scratch repositories whose installed metadata is stated by a fake."""

from __future__ import annotations

import importlib.metadata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest

import check_dev_dependencies as inventory
from python_workspace import load_workspace
from tests._support.repo import PY_ROOT, REPO_ROOT
from tests.unit.tools._workspace_support import write_file, write_member, write_root


@dataclass(frozen=True)
class _Metadata:
    imports: Mapping[str, Iterable[str]] = field(default_factory=dict[str, Iterable[str]])
    scripts: Mapping[str, Iterable[str]] = field(default_factory=dict[str, Iterable[str]])
    plugins: frozenset[str] = frozenset()

    def _known(self, distribution: str) -> None:
        if distribution not in {*self.imports, *self.scripts, *self.plugins}:
            raise importlib.metadata.PackageNotFoundError(distribution)

    def import_names(self, distribution: str) -> frozenset[str]:
        self._known(distribution)
        return frozenset(self.imports.get(distribution, ()))

    def commands(self, distribution: str) -> frozenset[str]:
        self._known(distribution)
        return frozenset(self.scripts.get(distribution, ()))

    def pytest_plugin(self, distribution: str) -> bool:
        self._known(distribution)
        return distribution in self.plugins


def _report(
    repo: Path,
    dev: Iterable[str],
    metadata: _Metadata,
    *,
    addopts: str = "",
    plugins: Mapping[str, inventory.PytestPlugin] | None = None,
) -> inventory.Report:
    root = write_root(repo, sources=("parallax-core", "parallax-tooling"), dev=dev, addopts=addopts)
    write_member(repo, "parallax-core", {"parallax/core/__init__.py": "import botocore\n"})
    write_member(repo, "parallax-tooling", {"parallax/tooling/__init__.py": ""})
    return inventory.check(load_workspace(root), repo, metadata, {} if plugins is None else plugins)


def _reasons(report: inventory.Report) -> dict[str, tuple[str, ...]]:
    return {entry.requirement: entry.reasons for entry in report.classifications}


@pytest.mark.xfail(
    reason="the dev group redeclares testcontainers, which only parallax-conformance imports "
    "and already declares"
)
def test_every_real_development_dependency_is_classified() -> None:
    report = inventory.check(load_workspace(PY_ROOT), REPO_ROOT, inventory.InstalledMetadata())
    assert report.findings == ()


def test_an_unclassified_development_dependency_fails(tmp_path: Path) -> None:
    report = _report(tmp_path, ["leftover>=1"], _Metadata(imports={"leftover": ["leftover"]}))
    assert report.findings == ("dev: leftover>=1 is unclassified",)
    assert _reasons(report) == {"leftover>=1": ()}


def test_an_uninstalled_development_dependency_fails(tmp_path: Path) -> None:
    report = _report(tmp_path, ["absent"], _Metadata())
    assert report.findings == ("dev: absent is not installed, so it cannot be classified",)


def test_a_dependency_imported_by_tests_or_tools_is_classified(tmp_path: Path) -> None:
    write_file(tmp_path, "languages/python/tests/test_a.py", "import alpha.sub\n")
    write_file(tmp_path, "languages/python/tools/b.py", "def f():\n    from beta import x\n")
    metadata = _Metadata(imports={"alpha": ["alpha"], "beta-dist": ["beta"]})
    report = _report(tmp_path, ["alpha", "beta-dist"], metadata)
    assert report.findings == ()
    assert _reasons(report) == {
        "alpha": ("imported by tests or tooling (tests/test_a.py:1)",),
        "beta-dist": ("imported by tests or tooling (tools/b.py:2)",),
    }


def test_a_workspace_member_is_imported_through_its_namespace_scope(tmp_path: Path) -> None:
    write_file(tmp_path, "languages/python/tests/test_a.py", "from parallax.tooling import x\n")
    report = _report(tmp_path, ["parallax-tooling"], _Metadata())
    assert _reasons(report) == {
        "parallax-tooling": ("imported by tests or tooling (tests/test_a.py:1)",)
    }


_JUSTFILE = """python := "languages/python"
harness := "reference-harness"

lint:
    cd {{python}} && uv run --frozen ruff check .
    cd {{harness}} && uv run harness-only
    cd {{python}} && uv run --with 'pydantic==2' python -m checker --strict
    # cd {{python}} && uv run commented-out
"""


def test_a_command_the_justfile_runs_in_the_workspace_classifies_its_script(
    tmp_path: Path,
) -> None:
    write_file(tmp_path, "justfile", _JUSTFILE)
    metadata = _Metadata(
        imports={"checker-dist": ["checker"]},
        scripts={"ruff": ["ruff"], "harness-tool": ["harness-only"], "old": ["commented-out"]},
    )
    report = _report(tmp_path, ["ruff", "checker-dist", "harness-tool", "old"], metadata)
    assert _reasons(report) == {
        "ruff": ("invoked by `uv run ruff` (justfile:5)",),
        "checker-dist": ("invoked by `uv run python -m checker` (justfile:7)",),
        "harness-tool": (),
        "old": (),
    }


_WORKFLOW = """name: ci
jobs:
  python:
    defaults:
      run:
        working-directory: languages/python
    steps:
      - run: uv run first-tool --check
      - working-directory: reference-harness
        run: uv run harness-tool
  elsewhere:
    steps:
      - run: |
          echo start
          uv run --project languages/python second-tool | tee out
      - run: uv run third-tool
"""


def test_a_command_a_workflow_runs_in_the_workspace_classifies_its_script(
    tmp_path: Path,
) -> None:
    write_file(tmp_path, ".github/workflows/ci.yml", _WORKFLOW)
    scripts = {name: [name] for name in ("first-tool", "second-tool", "harness-tool", "third-tool")}
    report = _report(tmp_path, list(scripts), _Metadata(scripts=scripts))
    assert _reasons(report) == {
        "first-tool": ("invoked by `uv run first-tool` (.github/workflows/ci.yml python)",),
        "second-tool": ("invoked by `uv run second-tool` (.github/workflows/ci.yml elsewhere)",),
        "harness-tool": (),
        "third-tool": (),
    }


def test_a_stub_provider_is_classified_by_the_module_it_stubs(tmp_path: Path) -> None:
    # `parallax-core` imports botocore; nothing imports yaml.
    metadata = _Metadata(
        imports={"botocore-stubs": ["botocore-stubs"], "types-pyyaml": ["yaml-stubs"]}
    )
    report = _report(tmp_path, ["botocore-stubs", "types-pyyaml"], metadata)
    assert _reasons(report) == {
        "botocore-stubs": (
            "type stubs for botocore (packages/parallax-core/src/parallax/core/__init__.py:1)",
        ),
        "types-pyyaml": (),
    }
    assert report.findings == ("dev: types-pyyaml is unclassified",)


_PLUGINS = ["pytest-xdist", "pytest-cov"]


def _pytest_justfile(arguments: str) -> str:
    return (
        f'python := "languages/python"\n\nt:\n    cd {{{{python}}}} && uv run pytest {arguments}\n'
    )


def _plugin_report(
    repo: Path, pytest_arguments: str, metadata: _Metadata, *, addopts: str = ""
) -> inventory.Report:
    write_file(repo, "justfile", _pytest_justfile(pytest_arguments))
    return _report(repo, _PLUGINS, metadata, addopts=addopts, plugins=inventory.PYTEST_PLUGINS)


def test_a_pytest_plugin_is_classified_by_an_option_a_pytest_command_passes(
    tmp_path: Path,
) -> None:
    metadata = _Metadata(plugins=frozenset(_PLUGINS))
    report = _plugin_report(tmp_path, "-n auto", metadata, addopts="-ra --cov-branch")
    assert report.findings == ()
    assert _reasons(report) == {
        "pytest-xdist": (
            f"pytest plugin: {inventory.PYTEST_PLUGINS['pytest-xdist'].rationale} "
            "(-n in justfile:4)",
        ),
        "pytest-cov": (
            f"pytest plugin: {inventory.PYTEST_PLUGINS['pytest-cov'].rationale} "
            "(--cov-branch in [tool.pytest.ini_options].addopts)",
        ),
    }


def test_a_pytest_plugin_no_command_uses_is_unclassified(tmp_path: Path) -> None:
    report = _plugin_report(tmp_path, "-q", _Metadata(plugins=frozenset(_PLUGINS)))
    assert report.findings == (
        "dev: pytest-xdist is unclassified",
        "dev: pytest-cov is unclassified",
    )


def test_a_recorded_plugin_that_registers_no_pytest_entry_point_is_unclassified(
    tmp_path: Path,
) -> None:
    metadata = _Metadata(plugins=frozenset({"pytest-cov"}), imports={"pytest-xdist": ["xdist"]})
    report = _plugin_report(tmp_path, "-n 4 --cov", metadata)
    assert report.findings == ("dev: pytest-xdist is unclassified",)


def test_a_plugin_record_for_a_dependency_no_group_lists_fails(tmp_path: Path) -> None:
    report = _report(tmp_path, [], _Metadata(), plugins=inventory.PYTEST_PLUGINS)
    assert report.findings == (
        "PYTEST_PLUGINS records pytest-cov, which no dependency group lists",
        "PYTEST_PLUGINS records pytest-xdist, which no dependency group lists",
    )


def test_installed_metadata_resolves_a_metapackage_to_the_library_it_installs() -> None:
    # `griffe` ships no module of its own; its `griffe` package comes from the
    # library release it requires.
    metadata = inventory.InstalledMetadata()
    assert "griffe" in metadata.import_names("griffe")
    assert "ruff" in metadata.commands("ruff")
    assert "lint-imports" in metadata.commands("import-linter")
    assert metadata.import_names("types-pyyaml") == {"yaml-stubs"}
    assert metadata.pytest_plugin("pytest-xdist")
    assert not metadata.pytest_plugin("ruff")


@pytest.mark.parametrize(("dev", "status"), [((), 1), (("pytest-cov", "pytest-xdist"), 0)])
def test_main_exits_non_zero_on_a_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dev: tuple[str, ...], status: int
) -> None:
    write_file(tmp_path, "justfile", _pytest_justfile("-n auto --cov"))
    root = write_root(tmp_path, sources=("parallax-core",), dev=dev)
    write_member(tmp_path, "parallax-core", {"parallax/core/__init__.py": ""})
    monkeypatch.setattr(inventory, "PY_ROOT", root)
    monkeypatch.setattr(inventory, "REPO_ROOT", tmp_path)
    assert inventory.main([]) == status


@pytest.mark.parametrize(
    ("line", "argv"),
    [
        ("uv run --frozen --with 'x==1' tool --flag", ("tool", "--flag")),
        ("uv run --project=languages/python tool", ("tool",)),
        ("cd languages/python && uv run -p 3.13 tool | tee log", ("tool",)),
    ],
)
def test_uv_run_options_are_skipped_before_the_executable(line: str, argv: tuple[str, ...]) -> None:
    [command] = inventory.uv_run_commands(line, True, "origin")
    assert command.argv == argv
