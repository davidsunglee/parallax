"""Scratch Python workspaces for the dependency checks, laid out as the real one
is: a repository root holding ``languages/python`` with members under
``packages/``."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path

WORKSPACE = Path("languages/python")


def _array(values: Iterable[str]) -> str:
    return json.dumps(list(values))


def write_root(
    repo: Path,
    *,
    sources: Iterable[str],
    members: Iterable[str] = ("packages/*",),
    dev: Iterable[str] = (),
    addopts: str = "",
) -> Path:
    """The workspace root manifest; returns the workspace directory."""
    root = repo / WORKSPACE
    root.mkdir(parents=True, exist_ok=True)
    source_lines = "".join(f"{name} = {{ workspace = true }}\n" for name in sources)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "workspace-root"\nversion = "0"\n\n'
        f"[tool.uv.workspace]\nmembers = {_array(members)}\n\n"
        f"[tool.uv.sources]\n{source_lines}\n"
        f"[dependency-groups]\ndev = {_array(dev)}\n\n"
        f"[tool.pytest.ini_options]\naddopts = {json.dumps(addopts)}\n",
        encoding="utf-8",
    )
    return root


def write_member(
    repo: Path,
    name: str,
    modules: Mapping[str, str],
    *,
    dependencies: Iterable[str] = (),
    extras: Mapping[str, Iterable[str]] | None = None,
) -> Path:
    """A member distribution; ``modules`` maps paths under ``src/`` to source."""
    directory = repo / WORKSPACE / "packages" / name
    directory.mkdir(parents=True, exist_ok=True)
    optional = "".join(
        f"{extra} = {_array(requirements)}\n" for extra, requirements in (extras or {}).items()
    )
    (directory / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "0"\ndependencies = {_array(dependencies)}\n'
        + (f"\n[project.optional-dependencies]\n{optional}" if optional else ""),
        encoding="utf-8",
    )
    for relative, source in modules.items():
        path = directory / "src" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return directory


def write_file(repo: Path, relative: str, text: str) -> Path:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
