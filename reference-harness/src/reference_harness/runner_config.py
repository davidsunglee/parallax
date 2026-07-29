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

Adding a runner means adding a profile, and adding one whose configuration is not
TOML means giving it a reader too; :func:`read` deliberately covers only the
TOML form the profiles below declare.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = ["PROFILES", "PYTEST", "RunnerConfiguration", "RunnerProfile", "read"]


@dataclass(frozen=True)
class RunnerProfile:
    """Where one test runner declares what the contract needs to read.

    ``settings_path`` is the chain of TOML tables leading to the runner's
    settings inside ``packaging_file``. ``catalog_key`` holds the class names
    the runner accepts, each entry spelled ``<name><separator><description>``.
    ``strictness_flag`` in ``options_key`` is what makes an unlisted class an
    error instead of an empty selection. ``root_files`` are the files this
    runner requires at the root of a test tree, and therefore the only files
    §4's closed root may hold beyond its directories.
    """

    runner: str
    packaging_file: str
    settings_path: tuple[str, ...]
    catalog_key: str
    catalog_separator: str
    options_key: str
    strictness_flag: str
    test_paths_key: str
    root_files: frozenset[str]


PYTEST = RunnerProfile(
    runner="pytest",
    packaging_file="pyproject.toml",
    settings_path=("tool", "pytest", "ini_options"),
    catalog_key="markers",
    catalog_separator=":",
    options_key="addopts",
    strictness_flag="--strict-markers",
    test_paths_key="testpaths",
    root_files=frozenset({"conftest.py"}),
)
"""The Python ecosystem's runner, the only one any scope here uses."""

PROFILES: tuple[RunnerProfile, ...] = (PYTEST,)
"""Every runner whose configuration this tooling can read, in the order tried."""


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
        return self.profile.strictness_flag in self.options


def _settings(module_dir: Path, profile: RunnerProfile) -> Mapping[str, Any] | None:
    packaging = module_dir / profile.packaging_file
    if not packaging.is_file():
        return None
    try:
        parsed: dict[str, Any] = tomllib.loads(packaging.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return None
    settings: Mapping[str, Any] = parsed
    for key in profile.settings_path:
        nested: Any = settings.get(key)
        if not isinstance(nested, Mapping):
            return None
        settings = nested
    return settings


def read(module_dir: Path) -> RunnerConfiguration | None:
    """The runner configuration *module_dir* declares, or ``None`` when no
    profile in :data:`PROFILES` recognizes one there."""
    for profile in PROFILES:
        settings = _settings(module_dir, profile)
        if settings is None:
            continue
        catalog: Any = settings.get(profile.catalog_key, [])
        test_paths: Any = settings.get(profile.test_paths_key, [])
        return RunnerConfiguration(
            profile=profile,
            catalog=frozenset(
                str(entry).split(profile.catalog_separator, 1)[0].strip() for entry in catalog
            ),
            options=str(settings.get(profile.options_key, "")),
            test_paths=tuple(str(path) for path in test_paths),
        )
    return None
