"""Read a GitHub Actions workflow as a list of jobs and what each one runs.

`core/spec/language-testing.md` §9 judges CI by its job identifiers and by the
shell commands its steps execute; everything else a workflow declares — runners,
caches, permissions, triggers — is outside that contract. This module reduces the
YAML to those two facts so the rules reading it never touch the workflow format.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

__all__ = ["Job", "jobs"]

_JUST_INVOCATION_RE = re.compile(r"\bjust\s+(?P<recipe>[a-z][a-z0-9-]*)")


@dataclass(frozen=True)
class Job:
    """One CI job, reduced to what the contract judges it by."""

    identifier: str
    invoked: tuple[str, ...]
    commands: tuple[str, ...]


def _run_commands(definition: Any) -> tuple[str, ...]:
    steps: Any = definition.get("steps", []) if isinstance(definition, Mapping) else []
    if not isinstance(steps, Sequence) or isinstance(steps, str):
        return ()
    listed: Sequence[Any] = steps
    return tuple(str(step["run"]) for step in listed if isinstance(step, Mapping) and "run" in step)


def jobs(workflow: Path) -> list[Job] | None:
    """Every job *workflow* declares, or ``None`` when the file does not exist.

    A file that exists but declares no jobs is an empty list, which is a
    workflow covering nothing rather than a workflow that is absent.
    """
    if not workflow.is_file():
        return None
    parsed: Any = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    declared: Any = parsed.get("jobs", {}) if isinstance(parsed, Mapping) else {}
    if not isinstance(declared, Mapping):
        return []
    entries: Mapping[str, Any] = declared
    found: list[Job] = []
    for identifier, definition in entries.items():
        commands = _run_commands(definition)
        found.append(
            Job(
                identifier=str(identifier),
                invoked=tuple(
                    match.group("recipe")
                    for command in commands
                    for match in _JUST_INVOCATION_RE.finditer(command)
                ),
                commands=commands,
            )
        )
    return found
