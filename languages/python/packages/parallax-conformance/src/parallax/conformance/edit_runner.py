"""Case-driven grading for every native ``edit`` compatibility case."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from pydantic import BaseModel

from parallax.conformance import case_format, sweep
from parallax.conformance.edit_models import LEDGER, Note, NoteMark, NoteTag, WitnessReading

__all__ = [
    "AuxiliaryReading",
    "DerivedCacheReading",
    "Observation",
    "Probe",
    "changes",
    "constructed_source",
    "follow_path",
    "grade",
    "observe",
    "probe",
    "reachable_edit_cases",
    "snippet",
    "title",
]

type Editable = Note | NoteTag


def reachable_edit_cases(cases: list[case_format.Case] | None = None) -> list[case_format.Case]:
    """Every edit case in the active implemented slice."""
    return [case for case in sweep.reachable_cases(cases=cases) if case.shape == "edit"]


def _instruction(case: case_format.Case) -> Mapping[str, object]:
    when = cast("Mapping[str, object]", case.document.get("when") or {})
    return cast("Mapping[str, object]", when["edit"])


def _source(case: case_format.Case) -> Mapping[str, object]:
    return cast("Mapping[str, object]", _instruction(case)["source"])


def constructed_source(case: case_format.Case) -> Editable:
    """Build a case's application-constructed source and follow its target path."""
    source = _source(case)
    if source.get("origin") != "constructed":
        raise ValueError(f"{case.case_id}: source is not constructed")
    value = dict(cast("Mapping[str, object]", source["value"]))
    tag = value.get("tag")
    if isinstance(tag, Mapping):
        value["tag"] = NoteTag.model_validate(tag)
    marks = value.get("marks")
    if isinstance(marks, list):
        mark_values = cast("list[object]", marks)
        value["marks"] = tuple(NoteMark.model_validate(mark) for mark in mark_values)
    root = Note.model_validate(value)
    return follow_path(root, case)


def follow_path(root: Note, case: case_format.Case) -> Editable:
    """Return the Entity itself or the Value Object occurrence named by the case."""
    path = _source(case).get("path")
    if path is None:
        return root
    if not isinstance(path, str):
        raise ValueError(f"{case.case_id}: source path is not a string")
    segments = path.split(".")
    try:
        root_index = segments.index(type(root).__name__)
    except ValueError as exc:
        raise ValueError(
            f"{case.case_id}: source path {path!r} does not name {type(root).__name__}"
        ) from exc
    current: object = root
    for segment in segments[root_index + 1 :]:
        current = getattr(current, segment)
    if not isinstance(current, (Note, NoteTag)):
        raise ValueError(f"{case.case_id}: source path {path!r} does not end at an editable value")
    return current


def changes(case: case_format.Case) -> Mapping[str, object]:
    """The authored assignments, empty for a change-free edit."""
    authored = dict(cast("Mapping[str, object]", _instruction(case).get("set") or {}))
    marks = authored.get("marks")
    if isinstance(marks, list):
        mark_values = cast("list[object]", marks)
        authored["marks"] = tuple(NoteMark.model_validate(mark) for mark in mark_values)
    return authored


def _members(value: BaseModel) -> dict[str, object]:
    return cast("dict[str, object]", value.model_dump(mode="json", exclude_unset=True))


@dataclass(frozen=True, slots=True)
class Probe:
    members: Mapping[str, object]
    memo: list[str]
    memo_contents: tuple[str, ...]
    derived_cache: str
    ledger: WitnessReading


def probe(source: Editable) -> Probe:
    """Snapshot source members and witnesses, warming its declared cache."""
    derived_cache = source.shouted
    memo = source.memo
    return Probe(
        members=_members(source),
        memo=memo,
        memo_contents=tuple(memo),
        derived_cache=derived_cache,
        ledger=LEDGER.snapshot(),
    )


@dataclass(frozen=True, slots=True)
class AuxiliaryReading:
    identity: str
    binding: str
    hooks: str


@dataclass(frozen=True, slots=True)
class DerivedCacheReading:
    value: str
    evaluations: int


@dataclass(frozen=True, slots=True)
class Observation:
    result_members: Mapping[str, object]
    auxiliary: AuxiliaryReading
    derived_cache: DerivedCacheReading
    source_unchanged: bool
    distinct: bool


def observe(source: Editable, result: Editable, before: Probe) -> Observation:
    """Observe carry, cache recomputation, binding independence, and source state."""
    shared = result.memo is source.memo
    result.remember(["result-only"])
    independent = (
        result.memo is not source.memo
        and source.memo is before.memo
        and tuple(source.memo) == before.memo_contents
    )
    cache_value = result.shouted
    after_result_cache = LEDGER.snapshot()
    source_cache = source.shouted
    after_source_cache = LEDGER.snapshot()
    source_unchanged = (
        _members(source) == before.members
        and source.memo is before.memo
        and tuple(source.memo) == before.memo_contents
        and source_cache == before.derived_cache
        and after_source_cache == after_result_cache
    )
    return Observation(
        result_members=_members(result),
        auxiliary=AuxiliaryReading(
            identity="shared" if shared else "distinct",
            binding="independent" if independent else "shared",
            hooks=(
                "none" if after_source_cache.hook_calls == before.ledger.hook_calls else "invoked"
            ),
        ),
        derived_cache=DerivedCacheReading(
            value=cache_value,
            evaluations=after_source_cache.cache_evaluations - before.ledger.cache_evaluations,
        ),
        source_unchanged=source_unchanged,
        distinct=result is not source,
    )


def grade(case: case_format.Case, observation: Observation) -> tuple[str, ...]:
    """Return every mismatch between a case's ``then`` oracle and one observation."""
    then = cast("Mapping[str, Any]", case.document["then"])
    expected_members = cast("Mapping[str, object]", then["result"]["members"])
    expected_auxiliary = cast("Mapping[str, str]", then["carry"]["auxiliary"])
    expected_cache = cast("Mapping[str, object]", then["carry"]["derivedCache"])
    expected_source = cast("Mapping[str, bool]", then["source"])
    mismatches: list[str] = []
    if observation.result_members != expected_members:
        mismatches.append(
            f"result.members: expected {expected_members!r}, "
            f"observed {observation.result_members!r}"
        )
    for name in ("identity", "binding", "hooks"):
        actual = getattr(observation.auxiliary, name)
        if actual != expected_auxiliary[name]:
            mismatches.append(
                f"carry.auxiliary.{name}: expected {expected_auxiliary[name]!r}, "
                f"observed {actual!r}"
            )
    if observation.derived_cache.value != expected_cache["value"]:
        mismatches.append(
            "carry.derivedCache.value: "
            f"expected {expected_cache['value']!r}, observed {observation.derived_cache.value!r}"
        )
    if observation.derived_cache.evaluations != expected_cache["evaluations"]:
        mismatches.append(
            "carry.derivedCache.evaluations: "
            f"expected {expected_cache['evaluations']!r}, "
            f"observed {observation.derived_cache.evaluations!r}"
        )
    if observation.source_unchanged != expected_source["unchanged"]:
        mismatches.append(
            f"source.unchanged: expected {expected_source['unchanged']!r}, "
            f"observed {observation.source_unchanged!r}"
        )
    if not observation.distinct:
        mismatches.append("result: edit returned the source object")
    return tuple(mismatches)


def _target_expression(case: case_format.Case) -> str:
    path = _source(case).get("path")
    if not isinstance(path, str):
        return "note"
    segments = path.split(".")
    return ".".join(["note", *segments[segments.index("Note") + 1 :]])


def snippet(case: case_format.Case) -> str:
    """Render the one-line idiomatic edit expression stated by the case."""
    arguments = ", ".join(_argument(name, value) for name, value in changes(case).items())
    return f"{_target_expression(case)}.edit({arguments})"


def _argument(name: str, value: object) -> str:
    if name == "marks":
        marks = cast("tuple[NoteMark, ...]", value)
        elements = ", ".join(
            f'NoteMark(kind="{mark.kind}", weight={mark.weight!r})' for mark in marks
        )
        return f"marks=({elements},)"
    return f"{name}={value!r}"


def title(case: case_format.Case) -> str:
    """Render a title from target kind, branch, and source origin."""
    kind = "Value Object" if _source(case).get("path") else "Entity"
    branch = "changed" if changes(case) else "change-free"
    origin = str(_source(case)["origin"])
    return f"{kind} {branch} edit from a {origin} source"
