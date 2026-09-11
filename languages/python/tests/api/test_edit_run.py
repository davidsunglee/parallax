"""Case-driven API-suite grading for native edited-value derivation."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from typing import Any, cast

import pytest

from parallax.conformance import case_format, edit_runner, engine
from parallax.conformance.edit_models import LEDGER, NOTE_MODEL, Note, NoteMark
from parallax.snapshot import SnapshotInspectionError, connect, pin_of
from tests._support.corpus import case_fixtures


def _origin(case: case_format.Case) -> object:
    when = cast("Mapping[str, object]", case.document["when"])
    edit = cast("Mapping[str, object]", when["edit"])
    source = cast("Mapping[str, object]", edit["source"])
    return source["origin"]


_CASES = edit_runner.reachable_edit_cases()
_CONSTRUCTED_CASES = [case for case in _CASES if _origin(case) == "constructed"]
_READ_CASES = [case for case in _CASES if _origin(case) == "read"]


def _run(case: case_format.Case) -> edit_runner.Observation:
    LEDGER.reset()
    source = edit_runner.constructed_source(case)
    before = edit_runner.probe(source)
    result = source.target.edit(**edit_runner.changes(case))
    return edit_runner.observe(source, result, before)


@pytest.mark.parametrize("case", _CONSTRUCTED_CASES, ids=lambda case: case.case_id)
def test_constructed_edit_case(case: case_format.Case) -> None:
    observation = _run(case)

    assert edit_runner.grade(case, observation) == ()


def _case(case_id: str) -> case_format.Case:
    return next(case for case in _CASES if case.case_id == case_id)


def _with_source(case: case_format.Case, **updates: object) -> case_format.Case:
    document = deepcopy(case.document)
    when = cast("dict[str, object]", document["when"])
    edit = cast("dict[str, object]", when["edit"])
    source = cast("dict[str, object]", edit["source"])
    source.update(updates)
    return replace(case, document=document)


def _read_id(case: case_format.Case) -> int:
    when = cast("Mapping[str, object]", case.document["when"])
    edit = cast("Mapping[str, object]", when["edit"])
    source = cast("Mapping[str, object]", edit["source"])
    query = cast("Mapping[str, object]", source["objectQuery"])
    predicate = cast("Mapping[str, object]", query["predicate"])
    equality = cast("Mapping[str, object]", predicate["eq"])
    return cast("int", equality["value"])


def _pin_refusal(value: object) -> SnapshotInspectionError:
    with pytest.raises(SnapshotInspectionError) as caught:
        pin_of(value)
    return caught.value


@pytest.mark.parametrize("case", _READ_CASES, ids=lambda case: case.case_id)
def test_read_edit_case(case: case_format.Case, profile_run: Any) -> None:
    profile_run.reset(engine.load_case_metamodel(case), case_fixtures(case))
    db = connect(profile_run.port, NOTE_MODEL)
    root = db.find(Note.where(Note.id == _read_id(case))).result()
    source = edit_runner.follow_path(root, case)
    target = source.target
    memo_value = target.title if isinstance(target, Note) else target.label
    LEDGER.reset()
    source.root.remember([source.root.title])
    target.remember([memo_value])
    before = edit_runner.probe(source)

    result = target.edit(**edit_runner.changes(case))
    observation = edit_runner.observe(source, result, before)

    assert edit_runner.grade(case, observation) == ()
    expected_pin_code = (
        "snapshot-pin-unavailable" if isinstance(target, Note) else "snapshot-node-required"
    )
    source_refusal = _pin_refusal(target)
    result_refusal = _pin_refusal(result)
    assert (source_refusal.code, source_refusal.entity) == (
        result_refusal.code,
        result_refusal.entity,
    )
    assert result_refusal.code == expected_pin_code


def _with_value(case: case_format.Case, **updates: object) -> case_format.Case:
    document = deepcopy(case.document)
    when = cast("dict[str, object]", document["when"])
    edit = cast("dict[str, object]", when["edit"])
    source = cast("dict[str, object]", edit["source"])
    value = cast("dict[str, object]", source["value"])
    value.update(updates)
    return replace(case, document=document)


def test_constructed_source_rejects_a_read_origin() -> None:
    case = _with_source(_case("m-edit-001"), origin="read")

    with pytest.raises(ValueError, match="source is not constructed"):
        edit_runner.constructed_source(case)


def test_constructed_source_accepts_native_optional_and_many_occurrences() -> None:
    case = _with_value(_case("m-edit-001"), tag=None, marks=())

    source = cast("Note", edit_runner.constructed_source(case).target)

    assert source.tag is None
    assert source.marks == ()


def test_changes_builds_a_native_many_occurrence_assignment() -> None:
    case = _case("m-edit-009")

    authored = edit_runner.changes(case)
    marks = cast("tuple[NoteMark, ...]", authored["marks"])

    assert tuple(mark.model_dump() for mark in marks) == ({"kind": "x", "weight": 1},)
    assert edit_runner.snippet(case) == 'note.edit(marks=(NoteMark(kind="x", weight=1),))'


@pytest.mark.parametrize(
    ("path", "message"),
    [
        (1, "source path is not a string"),
        ("parallax.compatibility.Other.tag", "does not name Note"),
        ("parallax.compatibility.Note.title", "does not end at an editable value"),
    ],
)
def test_follow_path_rejects_non_editable_targets(path: object, message: str) -> None:
    case = _with_source(_case("m-edit-003"), path=path)

    with pytest.raises(ValueError, match=message):
        edit_runner.constructed_source(case)


def test_grading_rejects_a_stale_cache_after_a_change_free_edit() -> None:
    case = _case("m-edit-002")
    observed = _run(case)
    stale = replace(
        observed,
        derived_cache=replace(observed.derived_cache, evaluations=0),
    )

    assert edit_runner.grade(case, stale) == (
        "carry.derivedCache.evaluations: expected 1, observed 0",
    )


def test_grading_rejects_a_setter_altered_memo_after_a_changed_edit() -> None:
    case = _case("m-edit-001")
    observed = _run(case)
    intercepted = replace(
        observed,
        auxiliary=replace(observed.auxiliary, identity="distinct", hooks="invoked"),
    )

    assert edit_runner.grade(case, intercepted) == (
        "carry.auxiliary.identity: expected 'shared', observed 'distinct'",
        "carry.auxiliary.hooks: expected 'none', observed 'invoked'",
    )


def test_grading_rejects_mutation_of_the_containing_entity_source() -> None:
    case = _case("m-edit-003")
    source = edit_runner.constructed_source(case)
    before = edit_runner.probe(source)
    result = source.target.edit(**edit_runner.changes(case))
    cast("dict[str, object]", source.root.__dict__)["body"] = "damaged"

    observation = edit_runner.observe(source, result, before)

    assert edit_runner.grade(case, observation) == (
        "source.unchanged: expected True, observed False",
    )


def test_observe_compares_result_identity_with_the_edit_target() -> None:
    case = _case("m-edit-003")
    source = edit_runner.constructed_source(case)
    before = edit_runner.probe(source)

    observation = edit_runner.observe(source, source.target, before)

    assert observation.distinct is False


def test_grading_reports_every_remaining_observation_mismatch() -> None:
    case = _case("m-edit-001")
    observed = _run(case)
    mismatched = replace(
        observed,
        result_members={},
        auxiliary=replace(observed.auxiliary, binding="shared"),
        derived_cache=replace(observed.derived_cache, value="stale"),
        source_unchanged=False,
        distinct=False,
    )

    assert edit_runner.grade(case, mismatched) == (
        "result.members: expected {'id': 1, 'title': 'alpha', 'body': None, "
        "'tag': {'label': 'a', 'weight': 3}, 'marks': []}, observed {}",
        "carry.auxiliary.binding: expected 'independent', observed 'shared'",
        "carry.derivedCache.value: expected 'ALPHA', observed 'stale'",
        "source.unchanged: expected True, observed False",
        "result: edit returned the source object",
    )
