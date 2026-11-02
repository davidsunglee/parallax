"""Read a GitHub Actions workflow as a list of jobs and what each one runs.

`core/spec/language-testing.md` §9 judges CI by its job identifiers, by the
shell commands its steps execute, and — for a relevance-gated class — by how its
relevance, class, and verdict jobs depend on and condition one another. Runners,
caches, and permissions are outside that contract. This module reduces the YAML
to those facts, together with the directory each command starts in, so the rules
reading it never touch the workflow format.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

__all__ = ["Job", "RunStep", "Workflow", "jobs", "read"]

_JUST_INVOCATION_RE = re.compile(r"\bjust\s+(?P<recipe>[a-z][a-z0-9-]*)")
_EXPRESSION_RE = re.compile(r"^\$\{\{\s*(?P<body>.*?)\s*\}\}$", re.DOTALL)


@dataclass(frozen=True)
class RunStep:
    """One ``run`` step: its shell script, and the directory GitHub starts it in
    relative to the repository root — ``None`` for the root itself."""

    command: str
    working_directory: str | None


@dataclass(frozen=True)
class Job:
    """One CI job, reduced to what the contract judges it by.

    ``condition`` is the job's ``if`` with any ``${{ }}`` wrapper removed, since
    GitHub evaluates a job condition as an expression either way. ``matrix`` is
    the job's ``strategy.matrix`` as written, or ``None`` when it expands nothing.
    """

    identifier: str
    invoked: tuple[str, ...]
    steps: tuple[RunStep, ...]
    name: str | None = None
    needs: tuple[str, ...] = ()
    condition: str | None = None
    outputs: tuple[str, ...] = ()
    matrix: Mapping[str, Any] | None = field(default=None, compare=False)
    runs_on: str | None = None

    @property
    def commands(self) -> tuple[str, ...]:
        return tuple(step.command for step in self.steps)


@dataclass(frozen=True)
class Workflow:
    """A workflow's triggers and its jobs, in the order it declares them."""

    triggers: frozenset[str]
    jobs: tuple[Job, ...]


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


def _unwrapped(condition: Any) -> str | None:
    if condition is None:
        return None
    text = str(condition).strip()
    match = _EXPRESSION_RE.match(text)
    return match.group("body").strip() if match else text


def _needs(definition: Mapping[str, Any]) -> tuple[str, ...]:
    needs: Any = definition.get("needs")
    if needs is None:
        return ()
    if isinstance(needs, str):
        return (needs,)
    if isinstance(needs, Sequence):
        listed: Sequence[Any] = needs
        return tuple(str(need) for need in listed)
    return ()


def _matrix(definition: Mapping[str, Any]) -> Mapping[str, Any] | None:
    strategy: Any = definition.get("strategy")
    matrix: Any = strategy.get("matrix") if isinstance(strategy, Mapping) else None
    return matrix if isinstance(matrix, Mapping) else None


def _job(identifier: str, definition: Any, workflow_directory: str | None) -> Job:
    steps = _run_steps(definition, workflow_directory)
    mapping: Mapping[str, Any] = definition if isinstance(definition, Mapping) else {}
    outputs: Any = mapping.get("outputs")
    name: Any = mapping.get("name")
    runs_on: Any = mapping.get("runs-on")
    return Job(
        identifier=identifier,
        invoked=tuple(
            match.group("recipe")
            for step in steps
            for match in _JUST_INVOCATION_RE.finditer(step.command)
        ),
        steps=steps,
        name=None if name is None else str(name),
        needs=_needs(mapping),
        condition=_unwrapped(mapping.get("if")),
        outputs=tuple(str(key) for key in outputs) if isinstance(outputs, Mapping) else (),
        matrix=_matrix(mapping),
        runs_on=None if runs_on is None else str(runs_on),
    )


def _triggers(parsed: Mapping[Any, Any]) -> frozenset[str]:
    # YAML 1.1 reads a bare `on` key as the boolean true, which is how PyYAML
    # returns the trigger block of every workflow spelling it that way.
    declared: Any = parsed.get("on", parsed.get(True))
    if isinstance(declared, str):
        return frozenset({declared})
    if isinstance(declared, Mapping):
        return frozenset(str(event) for event in declared)
    if isinstance(declared, Sequence):
        listed: Sequence[Any] = declared
        return frozenset(str(event) for event in listed)
    return frozenset()


def read(workflow: Path) -> Workflow | None:
    """*workflow*'s triggers and jobs, or ``None`` when the file does not exist.

    A file that exists but declares no jobs has an empty job list, which is a
    workflow covering nothing rather than a workflow that is absent.
    """
    if not workflow.is_file():
        return None
    parsed: Any = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    if not isinstance(parsed, Mapping):
        return Workflow(frozenset(), ())
    document: Mapping[Any, Any] = parsed
    declared: Any = document.get("jobs", {})
    workflow_directory = _default_working_directory(document, None)
    entries: Mapping[str, Any] = declared if isinstance(declared, Mapping) else {}
    return Workflow(
        triggers=_triggers(document),
        jobs=tuple(
            _job(str(identifier), definition, workflow_directory)
            for identifier, definition in entries.items()
        ),
    )


def jobs(workflow: Path) -> list[Job] | None:
    """Every job *workflow* declares, or ``None`` when the file does not exist."""
    parsed = read(workflow)
    return None if parsed is None else list(parsed.jobs)
