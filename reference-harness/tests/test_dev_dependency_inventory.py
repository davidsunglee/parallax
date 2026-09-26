"""Docker-free tests for the development-dependency inventory."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from reference_harness.dev_dependency_inventory import Inventory, audit, main

_PROJECT = "project"


@dataclass(frozen=True)
class _Tree:
    """A scratch repository holding one project, and a scratch environment
    standing in for the project's installed distributions.

    Installed metadata lists only files that exist, so every file a
    distribution records is created, laid out as an installer lays out a
    virtual environment: executables three levels above ``site-packages``."""

    repository: Path
    site: Path

    @property
    def project(self) -> Path:
        return self.repository / _PROJECT

    def declare(
        self, *requirements: str, extra: str = "dev", group: str = f'["{_PROJECT}[dev]"]'
    ) -> None:
        """Declare *requirements* as the project's *extra*, and *group*, a TOML
        array, as its development group."""
        listed = ", ".join(f'"{requirement}"' for requirement in requirements)
        (self.project / "pyproject.toml").write_text(
            f'[project]\nname = "{_PROJECT}"\nversion = "0"\n'
            f"[project.optional-dependencies]\n{extra} = [{listed}]\n"
            f"[dependency-groups]\ndev = {group}\n",
            encoding="utf-8",
        )

    def install(
        self,
        name: str,
        files: Sequence[str] = (),
        *,
        console_scripts: Sequence[str] = (),
        top_level: Sequence[str] = (),
    ) -> None:
        info = self.site / f"{name.replace('-', '_')}-1.0.dist-info"
        info.mkdir(parents=True)
        (info / "METADATA").write_text(
            f"Metadata-Version: 2.1\nName: {name}\nVersion: 1.0\n", encoding="utf-8"
        )
        for file in files:
            installed = self.site / file
            installed.parent.mkdir(parents=True, exist_ok=True)
            installed.touch()
        record = [*files, f"{info.name}/METADATA", f"{info.name}/RECORD"]
        (info / "RECORD").write_text("".join(f"{file},,\n" for file in record), encoding="utf-8")
        if console_scripts:
            entries = "".join(f"{script} = tool:main\n" for script in console_scripts)
            (info / "entry_points.txt").write_text(
                f"[console_scripts]\n{entries}", encoding="utf-8"
            )
        if top_level:
            (info / "top_level.txt").write_text("\n".join(top_level) + "\n", encoding="utf-8")

    def source(self, relative: str, text: str) -> None:
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def recipes(self, text: str) -> None:
        (self.repository / "justfile").write_text(text, encoding="utf-8")

    def workflow(self, text: str) -> None:
        workflows = self.repository / ".github" / "workflows"
        workflows.mkdir(parents=True, exist_ok=True)
        (workflows / "ci.yml").write_text(text, encoding="utf-8")

    def audit(self) -> Inventory:
        return audit(self.project, self.repository, [str(self.site)])


@pytest.fixture
def tree(tmp_path: Path) -> _Tree:
    site = tmp_path / "environment" / "lib" / "python3" / "site-packages"
    created = _Tree(tmp_path / "repository", site)
    created.project.mkdir(parents=True)
    created.site.mkdir(parents=True)
    created.recipes("default:\n    echo nothing\n")
    return created


def _evidence(inventory: Inventory, dependency: str) -> set[str]:
    (found,) = (
        classification
        for classification in inventory.classifications
        if classification.dependency == dependency
    )
    return {evidence.kind for evidence in found.evidence}


def _codes(inventory: Inventory) -> list[str]:
    return [diagnostic.code for diagnostic in inventory.diagnostics]


def test_the_harness_classifies_every_development_dependency(repo_root: Path) -> None:
    inventory = audit(repo_root / "reference-harness", repo_root, sys.path)

    assert inventory.diagnostics == ()
    assert {classification.dependency for classification in inventory.classifications} == {
        "basedpyright",
        "pytest",
        "ruff",
    }


def test_an_unclassified_development_dependency_fails(tree: _Tree) -> None:
    tree.declare("idle-tool>=1")
    tree.install("idle-tool", ["idle_tool/__init__.py"], console_scripts=["idle-tool"])
    tree.source("tests/test_nothing.py", "import json\n")

    inventory = tree.audit()

    assert _codes(inventory) == ["dev-dependency-unclassified"]
    assert "`idle-tool`" in inventory.diagnostics[0].message


def test_a_module_imported_by_a_test_classifies_its_distribution(tree: _Tree) -> None:
    tree.declare("Helper_Lib")
    tree.install("helper-lib", ["helper/__init__.py"], top_level=["helper"])
    tree.source("tests/test_helper.py", "from helper.sub import thing\n")

    inventory = tree.audit()

    assert inventory.diagnostics == ()
    assert _evidence(inventory, "helper-lib") == {"imported"}


def test_a_console_script_run_by_a_recipe_is_invoked(tree: _Tree) -> None:
    tree.declare("cli-tool")
    tree.install("cli-tool", ["cli_tool/__init__.py"], console_scripts=["cli-tool"])
    tree.recipes(f"lint:\n    cd {_PROJECT} && uv run --frozen --with extra==1 cli-tool check .\n")

    inventory = tree.audit()

    assert inventory.diagnostics == ()
    assert _evidence(inventory, "cli-tool") == {"invoked"}


def test_an_installed_executable_without_an_entry_point_is_invoked(tree: _Tree) -> None:
    tree.declare("binary-tool")
    tree.install("binary-tool", ["binary_tool/__init__.py", "../../../bin/binary-tool"])
    tree.recipes(f"lint:\n    @cd {_PROJECT} && FORCE=1 uv run binary-tool\n")

    assert _evidence(tree.audit(), "binary-tool") == {"invoked"}


def test_a_module_run_with_python_dash_m_is_invoked(tree: _Tree) -> None:
    tree.declare("module-tool")
    tree.install("module-tool", ["module_tool/__main__.py"])
    tree.recipes(f"check:\n    uv run --directory {_PROJECT} python -m module_tool.cli\n")

    assert _evidence(tree.audit(), "module-tool") == {"invoked"}


def test_a_workflow_step_in_the_project_directory_is_invoked(tree: _Tree) -> None:
    tree.declare("step-tool", "job-tool")
    tree.install("step-tool", console_scripts=["step-tool"])
    tree.install("job-tool", console_scripts=["job-tool"])
    tree.workflow(
        "jobs:\n"
        "  step:\n"
        "    steps:\n"
        f"      - working-directory: {_PROJECT}\n"
        "        run: uv run step-tool\n"
        "  job:\n"
        "    defaults:\n"
        "      run:\n"
        f"        working-directory: {_PROJECT}\n"
        "    steps:\n"
        "      - run: |\n"
        "          uv sync --frozen\n"
        "          uv run job-tool\n"
    )

    inventory = tree.audit()

    assert inventory.diagnostics == ()
    assert _evidence(inventory, "step-tool") == {"invoked"}
    assert _evidence(inventory, "job-tool") == {"invoked"}


def test_a_command_run_against_another_project_does_not_classify(tree: _Tree) -> None:
    tree.declare("cli-tool")
    tree.install("cli-tool", console_scripts=["cli-tool"])
    (tree.repository / "other").mkdir()
    tree.recipes("lint:\n    cd other && uv run cli-tool\n    uvx cli-tool\n")
    tree.workflow("jobs:\n  lint:\n    steps:\n      - run: uv run cli-tool\n")

    assert _codes(tree.audit()) == ["dev-dependency-unclassified"]


def test_stubs_for_an_imported_module_are_a_type_stub_provider(tree: _Tree) -> None:
    tree.declare("types-thing")
    tree.install("types-thing", ["thing-stubs/__init__.pyi", "thing-stubs/METADATA.toml"])
    tree.source("src/project/reader.py", "import thing\n")

    inventory = tree.audit()

    assert inventory.diagnostics == ()
    assert _evidence(inventory, "types-thing") == {"type-stubs"}


def test_stubs_for_a_module_nothing_imports_are_unclassified(tree: _Tree) -> None:
    tree.declare("types-thing")
    tree.install("types-thing", ["thing-stubs/__init__.pyi"])
    tree.source("src/project/reader.py", "import other\n")

    assert _codes(tree.audit()) == ["dev-dependency-unclassified"]


def test_a_group_entry_naming_the_projects_own_extra_resolves_to_its_members(
    tree: _Tree,
) -> None:
    tree.declare("helper-lib>=1", extra="tools", group=f'["{_PROJECT.upper()}[Tools]", "cli-tool"]')
    tree.install("helper-lib", ["helper_lib.py"])
    tree.install("cli-tool", console_scripts=["cli-tool"])
    tree.source("tests/test_helper.py", "import helper_lib\n")
    tree.recipes(f"lint:\n    cd {_PROJECT} && uv run cli-tool\n")

    inventory = tree.audit()

    assert inventory.diagnostics == ()
    assert _evidence(inventory, "helper-lib") == {"imported"}
    assert _evidence(inventory, "cli-tool") == {"invoked"}


@pytest.mark.parametrize(
    "group",
    [
        pytest.param(f'["{_PROJECT}[absent]"]', id="missing-extra"),
        pytest.param(f'["{_PROJECT}"]', id="no-extra"),
        pytest.param('[{include-group = "other"}]', id="include-group"),
    ],
)
def test_an_unresolvable_group_entry_cannot_be_read(tree: _Tree, group: str) -> None:
    tree.declare("helper-lib", group=group)

    with pytest.raises(ValueError):
        tree.audit()


def test_the_command_line_reports_an_unreadable_manifest(
    tree: _Tree, capsys: pytest.CaptureFixture[str]
) -> None:
    tree.declare("helper-lib", group=f'["{_PROJECT}[absent]"]')

    assert main([str(tree.project), str(tree.repository)]) == 1
    assert "selects the extra `absent`" in capsys.readouterr().err


def test_a_declared_but_uninstalled_dependency_fails(tree: _Tree) -> None:
    tree.declare("absent-tool")

    assert _codes(tree.audit()) == ["dev-dependency-not-installed"]


def test_the_command_line_reports_a_failing_inventory(
    tree: _Tree, capsys: pytest.CaptureFixture[str]
) -> None:
    tree.declare("absent-tool-not-in-this-environment")

    assert main([str(tree.project), str(tree.repository)]) == 1
    assert "dev-dependency-not-installed" in capsys.readouterr().err


def test_the_command_line_rejects_a_wrong_argument_count() -> None:
    assert main(["only-one"]) == 2
