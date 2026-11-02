"""Read one scope's test-runner configuration through a declared runner profile.

`core/spec/language-testing.md` deliberately fixes no test framework and no
runner mechanism, but two of its rules can only be checked in the runner's own
configuration: §5's "mechanically" — a scheduling class a scope selects must be
one the runner knows, and a misspelling must fail rather than select nothing —
and §4's closed test root, whose permitted files are exactly the ones the runner
demands there.

Every fact needed to check those is a fact about a *runner*, not about the
contract, so each is named in a :class:`RunnerProfile` rather than spread through
the rules as a literal. :data:`PROFILES` is the closed set of runners this
tooling can read. A scope configured for a runner outside it is reported as
unreadable rather than judged by another runner's conventions — pytest's marker
catalog says nothing about a scope that does not run pytest.

Adding a runner means adding a profile together with the reader for the file
its configuration lives in.
"""

from __future__ import annotations

import json
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["PROFILES", "PYTEST", "VITEST", "RunnerConfiguration", "RunnerProfile", "read"]


@dataclass(frozen=True)
class RunnerConfiguration:
    """One scope's runner settings, read through the profile that recognized it."""

    profile: RunnerProfile
    catalog: frozenset[str]
    options: str
    test_paths: tuple[str, ...]

    @property
    def rejects_unknown_classes(self) -> bool:
        """Whether a class outside :attr:`catalog` fails rather than selecting
        nothing."""
        flag = self.profile.strictness_flag
        return flag is None or flag in self.options


@dataclass(frozen=True)
class RunnerProfile:
    """Where one test runner declares what the contract needs to read.

    ``configuration_file`` is the file in a scope's directory holding the class
    catalog, which ``reader`` turns into a :class:`RunnerConfiguration`, or
    ``None`` when the file is absent or does not declare one. ``selection_flag``
    is the command-line flag whose argument names which classes an invocation
    selects, which lets a class-owning command be read for the selection it
    makes rather than only for the class it declares.

    ``strictness_flag`` is the option that makes an unlisted class an error
    instead of an empty selection, or ``None`` for a runner that always refuses
    one. ``root_files`` are the files this runner requires at the root of a
    test tree, and therefore the only files §4's closed root may hold beyond its
    directories.
    """

    runner: str
    configuration_file: str
    selection_flag: str
    strictness_flag: str | None
    root_files: frozenset[str]
    reader: Callable[[RunnerProfile, Path], RunnerConfiguration | None]


def _toml_settings(path: Path) -> Mapping[str, Any] | None:
    if not path.is_file():
        return None
    try:
        parsed: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return None
    settings: Mapping[str, Any] = parsed
    for key in ("tool", "pytest", "ini_options"):
        nested: Any = settings.get(key)
        if not isinstance(nested, Mapping):
            return None
        settings = nested
    return settings


def _read_pytest(profile: RunnerProfile, module_dir: Path) -> RunnerConfiguration | None:
    """pytest's ``[tool.pytest.ini_options]``: its ``markers`` catalog, each
    entry spelled ``<name>: <description>``, its ``addopts``, and its
    ``testpaths``."""
    settings = _toml_settings(module_dir / profile.configuration_file)
    if settings is None:
        return None
    catalog: Any = settings.get("markers", [])
    test_paths: Any = settings.get("testpaths", [])
    return RunnerConfiguration(
        profile=profile,
        catalog=frozenset(str(entry).split(":", 1)[0].strip() for entry in catalog),
        options=str(settings.get("addopts", "")),
        test_paths=tuple(str(path) for path in test_paths),
    )


def _read_vitest(profile: RunnerProfile, module_dir: Path) -> RunnerConfiguration | None:
    """The JSON list of Vitest projects a scope's ``vitest.config.ts`` builds
    its projects from, one per scheduling class, each named by ``name``."""
    path = module_dir / profile.configuration_file
    if not path.is_file():
        return None
    try:
        projects: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(projects, list):
        return None
    entries: list[Any] = projects
    names = [entry.get("name") for entry in entries if isinstance(entry, Mapping)]
    return RunnerConfiguration(
        profile=profile,
        catalog=frozenset(str(name) for name in names if name is not None),
        options="",
        test_paths=(),
    )


PYTEST = RunnerProfile(
    runner="pytest",
    configuration_file="pyproject.toml",
    selection_flag="-m",
    strictness_flag="--strict-markers",
    root_files=frozenset({"conftest.py"}),
    reader=_read_pytest,
)
"""The Python ecosystem's runner, selecting a class by marker expression."""

VITEST = RunnerProfile(
    runner="vitest",
    configuration_file="vitest.projects.json",
    selection_flag="--project",
    strictness_flag=None,
    root_files=frozenset(),
    reader=_read_vitest,
)
"""The TypeScript runner, selecting a class by project name. Vitest refuses a
``--project`` that names no project, so a misspelled class fails on its own."""

PROFILES: tuple[RunnerProfile, ...] = (PYTEST, VITEST)
"""Every runner whose configuration this tooling can read, in the order tried."""


def read(module_dir: Path) -> RunnerConfiguration | None:
    """The runner configuration *module_dir* declares, or ``None`` when no
    profile in :data:`PROFILES` recognizes one there."""
    for profile in PROFILES:
        configuration = profile.reader(profile, module_dir)
        if configuration is not None:
            return configuration
    return None
