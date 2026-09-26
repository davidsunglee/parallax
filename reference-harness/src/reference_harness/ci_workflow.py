"""Read a GitHub Actions workflow as a list of jobs and what each one runs.

`core/spec/language-testing.md` §9 judges CI by its job identifiers and by the
shell commands its steps execute; everything else a workflow declares — runners,
caches, permissions, triggers — is outside that contract. This module reduces the
YAML to those facts, together with the directory each command starts in, so the
rules reading it never touch the workflow format.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

__all__ = ["Job", "RunStep", "jobs"]

_JUST_INVOCATION_RE = re.compile(r"\bjust\s+(?P<recipe>[a-z][a-z0-9-]*)")


@dataclass(frozen=True)
class RunStep:
    """One ``run`` step: its shell script, and the directory GitHub starts it in
    relative to the repository root — ``None`` for the root itself."""

    command: str
    working_directory: str | None


@dataclass(frozen=True)
class Job:
    """One CI job, reduced to what the contract judges it by."""

    identifier: str
    invoked: tuple[str, ...]
    steps: tuple[RunStep, ...]

    @property
    def commands(self) -> tuple[str, ...]:
        return tuple(step.command for step in self.steps)


def _default_working_directory(owner: Any, inherited: str | None) -> str | None:
    defaults: Any = owner.get("defaults") if isinstance(owner, Mapping) else None
    run: Any = defaults.get("run") if isinstance(defaults, Mapping) else None
    directory: Any = run.get("working-directory") if isinstance(run, Mapping) else None
    return inherited if directory is None else str(directory)


def _run_steps(definition: Any, workflow_directory: str | None) -> tuple[RunStep, ...]:
    steps: Any = definition.get("steps", []) if isinstance(definition, Mapping) else []
    if not isinstance(steps, Sequence) or isinstance(steps, str):
        return ()
    listed: Sequence[Any] = steps
    job_directory = _default_working_directory(definition, workflow_directory)
    found: list[RunStep] = []
    for step in listed:
        if isinstance(step, Mapping) and "run" in step:
            directory: Any = step.get("working-directory", job_directory)
            found.append(RunStep(str(step["run"]), None if directory is None else str(directory)))
    return tuple(found)


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
    workflow_directory = _default_working_directory(parsed, None)
    found: list[Job] = []
    for identifier, definition in entries.items():
        steps = _run_steps(definition, workflow_directory)
        found.append(
            Job(
                identifier=str(identifier),
                invoked=tuple(
                    match.group("recipe")
                    for step in steps
                    for match in _JUST_INVOCATION_RE.finditer(step.command)
                ),
                steps=steps,
            )
        )
    return found
