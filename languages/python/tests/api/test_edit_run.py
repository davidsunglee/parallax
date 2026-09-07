"""Case-driven API-suite grading for native edited-value derivation."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest

from parallax.conformance import case_format, edit_runner
from parallax.conformance.edit_models import LEDGER, Note


def _origin(case: case_format.Case) -> object:
    when = cast("Mapping[str, object]", case.document["when"])
    edit = cast("Mapping[str, object]", when["edit"])
    source = cast("Mapping[str, object]", edit["source"])
    return source["origin"]


_CASES = [case for case in edit_runner.reachable_edit_cases() if _origin(case) == "constructed"]


def _run(case: case_format.Case) -> edit_runner.Observation:
    LEDGER.reset()
    source = edit_runner.constructed_source(case)
    before = edit_runner.probe(source)
    result = source.edit(**edit_runner.changes(case))
    return edit_runner.observe(source, result, before)


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.case_id)
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

    source = cast("Note", edit_runner.constructed_source(case))

    assert source.tag is None
    assert source.marks == ()


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
