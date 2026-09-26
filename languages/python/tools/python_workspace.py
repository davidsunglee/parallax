"""The Python workspace's members, the namespace scope each owns, and the
modules a source file statically imports.

Every workspace member is a distribution under ``packages/`` that ships exactly
one package beneath the shared PEP 420 ``parallax`` namespace:
``src/parallax/<scope>`` is what the member owns, and no two members own the same
scope. :func:`load_workspace` states every way a member could fall outside that
model — a ``packages/`` directory the workspace globs miss, a member outside
``packages/``, no or several scopes, a shared scope, a namespace-level module, a
member uv would not resolve from the workspace — as a finding rather than
silently leaving the member out, so each check built over the loaded members
analyzes every distribution the workspace builds.
"""

from __future__ import annotations

import ast
import re
import tomllib
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

NAMESPACE = "parallax"
PACKAGES_DIRECTORY = "packages"

_REQUIREMENT_NAME = re.compile(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def normalize(name: str) -> str:
    """A distribution or extra name in its PEP 503 comparison form."""
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_name(requirement: str) -> str:
    """The normalized distribution name a PEP 508 requirement string names."""
    match = _REQUIREMENT_NAME.match(requirement)
    if match is None:
        raise ValueError(f"not a requirement: {requirement!r}")
    return normalize(match.group(1))


@dataclass(frozen=True, slots=True)
class Member:
    name: str
    directory: Path
    scope: str
    dependencies: tuple[str, ...]
    optional_dependencies: Mapping[str, tuple[str, ...]]

    @property
    def package(self) -> str:
        return f"{NAMESPACE}.{self.scope}"

    @property
    def source(self) -> Path:
        return self.directory / "src" / NAMESPACE / self.scope


@dataclass(frozen=True, slots=True)
class Workspace:
    root: Path
    members: tuple[Member, ...]
    findings: tuple[str, ...]

    def owner(self, module: str) -> Member | None:
        """The member owning the ``parallax.<scope>`` package ``module`` lies in."""
        parts = module.split(".")
        if len(parts) < 2 or parts[0] != NAMESPACE:
            return None
        return next((member for member in self.members if member.scope == parts[1]), None)


def read_toml(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def table(document: Mapping[str, Any], *keys: str) -> Mapping[str, Any]:
    """The nested table at ``keys``, empty where any level is absent."""
    current: Mapping[str, Any] = document
    for key in keys:
        nested = current.get(key, {})
        current = cast("Mapping[str, Any]", nested) if isinstance(nested, dict) else {}
    return current


def strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in cast("list[object]", value) if isinstance(item, str))


def load_workspace(root: Path) -> Workspace:
    """Every analyzable member of the workspace rooted at ``root``, and every
    structural finding that keeps a member from being analyzed."""
    manifest = read_toml(root / "pyproject.toml")
    findings: list[str] = []
    directories = _member_directories(root, table(manifest, "tool", "uv", "workspace"), findings)
    members: list[Member] = []
    for directory in directories:
        member = _member(root, directory, findings)
        if member is not None:
            members.append(member)
    _check_unique_scopes(members, findings)
    _check_sources(table(manifest, "tool", "uv", "sources"), members, findings)
    return Workspace(root, tuple(members), tuple(findings))


def _member_directories(
    root: Path, workspace: Mapping[str, Any], findings: list[str]
) -> tuple[Path, ...]:
    included = {path for glob in strings(workspace.get("members")) for path in root.glob(glob)}
    excluded = {path for glob in strings(workspace.get("exclude")) for path in root.glob(glob)}
    members = {path for path in included - excluded if path.is_dir()}
    packages = root / PACKAGES_DIRECTORY
    candidates = (
        {
            path
            for path in packages.iterdir()
            if path.is_dir() and not path.name.startswith((".", "_"))
        }
        if packages.is_dir()
        else set[Path]()
    )
    for missed in sorted(candidates - members):
        findings.append(
            f"{_relative(root, missed)}: not matched by [tool.uv.workspace].members, "
            "so no workspace check analyzes it"
        )
    for outside in sorted(members - candidates):
        findings.append(
            f"{_relative(root, outside)}: a workspace member outside {PACKAGES_DIRECTORY}/"
        )
    return tuple(sorted(members & candidates))


def _member(root: Path, directory: Path, findings: list[str]) -> Member | None:
    where = _relative(root, directory)
    manifest_path = directory / "pyproject.toml"
    if not manifest_path.is_file():
        findings.append(f"{where}: has no pyproject.toml")
        return None
    project = table(read_toml(manifest_path), "project")
    name = project.get("name")
    if not isinstance(name, str):
        findings.append(f"{where}: pyproject.toml declares no [project].name")
        return None
    scope = _owned_scope(directory / "src" / NAMESPACE, where, findings)
    if scope is None:
        return None
    optional = table(project, "optional-dependencies")
    return Member(
        name=normalize(name),
        directory=directory,
        scope=scope,
        dependencies=strings(project.get("dependencies")),
        optional_dependencies={extra: strings(optional[extra]) for extra in optional},
    )


def _owned_scope(namespace: Path, where: str, findings: list[str]) -> str | None:
    if not namespace.is_dir():
        findings.append(f"{where}: has no src/{NAMESPACE}/ namespace directory")
        return None
    entries = [entry for entry in namespace.iterdir() if entry.name != "__pycache__"]
    modules = sorted(entry.name for entry in entries if entry.suffix in {".py", ".pyi"})
    if modules:
        findings.append(
            f"{where}: src/{NAMESPACE}/ holds modules {modules}; the namespace carries "
            "only one scope package per distribution"
        )
    scopes = sorted(entry.name for entry in entries if (entry / "__init__.py").is_file())
    if len(scopes) != 1:
        findings.append(
            f"{where}: owns {scopes or 'no'} scope packages under src/{NAMESPACE}/; "
            "a distribution owns exactly one"
        )
        return None
    return scopes[0]


def _check_unique_scopes(members: list[Member], findings: list[str]) -> None:
    owners: dict[str, list[str]] = {}
    for member in members:
        owners.setdefault(member.scope, []).append(member.name)
    for scope, names in sorted(owners.items()):
        if len(names) > 1:
            findings.append(f"{NAMESPACE}.{scope}: owned by several members {sorted(names)}")


def _check_sources(sources: Mapping[str, Any], members: list[Member], findings: list[str]) -> None:
    workspace_sources = {
        normalize(name)
        for name, source in sources.items()
        if isinstance(source, dict) and cast("dict[str, object]", source).get("workspace") is True
    }
    names = {member.name for member in members}
    for missing in sorted(names - workspace_sources):
        findings.append(
            f"{missing}: missing from [tool.uv.sources] as a workspace source, so a sibling "
            "requirement on it would not resolve to the workspace"
        )
    for stray in sorted(workspace_sources - names):
        findings.append(f"{stray}: a [tool.uv.sources] workspace source that is no member")


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()


def python_files(directory: Path) -> Iterator[Path]:
    for path in sorted(directory.rglob("*.py")):
        if "__pycache__" not in path.parts:
            yield path


def module_name(path: Path, source_root: Path) -> str:
    """The dotted module a file under ``source_root`` (a ``src`` directory) defines."""
    parts = list(path.relative_to(source_root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def imported_modules(path: Path, module: str | None = None) -> dict[str, int]:
    """Every module ``path`` statically imports, absolute, mapped to the first
    line importing it.

    Imports anywhere count — in a function body or under ``TYPE_CHECKING`` alike.
    ``from package import name`` records both ``package`` and ``package.name``,
    since the name may be a submodule. A relative import resolves against
    ``module``, the file's own dotted name, and is skipped without it.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = _package_of(path, module)
    found: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            for name in _import_targets(node, package):
                found.setdefault(name, node.lineno)
    return found


def _package_of(path: Path, module: str | None) -> str | None:
    if module is None:
        return None
    return module if path.name == "__init__.py" else module.rpartition(".")[0]


def _import_targets(node: ast.Import | ast.ImportFrom, package: str | None) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    base = _absolute_base(node, package)
    if base is None:
        return []
    joined = [f"{base}.{alias.name}" if base else alias.name for alias in node.names]
    return [base, *joined] if base else joined


def _absolute_base(node: ast.ImportFrom, package: str | None) -> str | None:
    if node.level == 0:
        return node.module
    if package is None:
        return None
    parts = package.split(".") if package else []
    if node.level - 1 > len(parts):
        return None
    anchor = parts[: len(parts) - (node.level - 1)]
    return ".".join([*anchor, *([node.module] if node.module else [])])
