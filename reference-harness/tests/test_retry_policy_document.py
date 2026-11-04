"""The Retry Policy rules a schema cannot state (`m-case-format` *Retry
policies*), asked of whole documents where every other case-authoring rule is.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from reference_harness.case import complete_retry_policy
from reference_harness.corpus_yaml import load_corpus_yaml, read_corpus_yaml
from reference_harness.retry_policy_validate import retry_policy_problems
from reference_harness.schema_validate import validate_tree, validation_error
from reference_harness.schemas import build_registry, load_schemas

_CORE = Path(__file__).resolve().parents[2] / "core"
_COMPLETE = {"maxRetries": 10, "backoff": {"baseDelay": 0.008, "maxDelay": 1.0}}


def _at_root(policy: dict[str, Any]) -> dict[str, Any]:
    return {"given": {"databaseOptions": {"retry": policy}}}


def _at_invocation(policy: dict[str, Any]) -> dict[str, Any]:
    return {"when": {"uow": {"retry": policy}}}


def _at_join(policy: dict[str, Any]) -> dict[str, Any]:
    return {"when": {"boundary": [{"action": "read"}, {"action": "join", "retry": policy}]}}


def _at_observation(policy: dict[str, Any]) -> dict[str, Any]:
    started = {"invocation": "outer", "retry": policy}
    event = {"sequence": 1, "transactionInvocationStarted": started}
    return {"then": {"executionLifecycle": {"roots": [{"events": [event]}]}}}


_PLACEMENTS = pytest.mark.parametrize(
    ("place", "where"),
    [
        (_at_root, "given.databaseOptions.retry"),
        (_at_invocation, "when.uow.retry"),
        (_at_join, r"when.boundary[1].retry"),
        (
            _at_observation,
            "then.executionLifecycle.roots[0].events[0].transactionInvocationStarted.retry",
        ),
    ],
    ids=["root", "invocation", "join", "observation"],
)


@_PLACEMENTS
@pytest.mark.parametrize(
    "backoff",
    [
        {"baseDelay": 2},
        {"baseDelay": 1.5},
        {"maxDelay": 0.001},
        {"baseDelay": 0.5, "maxDelay": 0.25},
    ],
    ids=["base-above-built-in", "float-base-above-built-in", "max-below-built-in", "both-named"],
)
def test_a_base_delay_above_the_maximum_is_refused_once_built_ins_are_filled(
    place: Any, where: str, backoff: dict[str, float]
) -> None:
    (problem,) = retry_policy_problems(place({"backoff": backoff}))
    assert problem.startswith(f"{where}.backoff resolves baseDelay")


@_PLACEMENTS
@pytest.mark.parametrize("carrier", [math.inf, math.nan, 10**400], ids=["inf", "nan", "huge-int"])
@pytest.mark.parametrize("field", ["baseDelay", "maxDelay"])
def test_a_non_finite_carrier_is_refused(place: Any, where: str, carrier: Any, field: str) -> None:
    (problem,) = retry_policy_problems(place({"backoff": {field: carrier}}))
    assert problem == f"{where}.backoff.{field} must be a finite number of seconds"


def test_every_non_finite_delay_is_reported() -> None:
    backoff = {"baseDelay": math.inf, "maxDelay": math.nan}
    assert len(retry_policy_problems(_at_root({"backoff": backoff}))) == 2


@_PLACEMENTS
@pytest.mark.parametrize(
    "policy",
    [
        {},
        {"maxRetries": 0},
        {"backoff": {}},
        {"backoff": {"baseDelay": 1}},
        {"backoff": {"maxDelay": 0.008}},
        {"backoff": {"baseDelay": 0.25, "maxDelay": 0.25}},
        {"backoff": {"baseDelay": 2, "maxDelay": 3}},
        _COMPLETE,
    ],
    ids=[
        "empty",
        "bound-only",
        "empty-backoff",
        "base-at-built-in-max",
        "max-at-built-in-base",
        "equal",
        "both-above-built-in",
        "complete",
    ],
)
def test_a_policy_within_the_rules_is_no_problem(
    place: Any, where: str, policy: dict[str, Any]
) -> None:
    del where
    assert retry_policy_problems(place(policy)) == []


def test_a_document_naming_no_policy_has_no_problem() -> None:
    assert retry_policy_problems({}) == []
    assert retry_policy_problems({"given": {}, "when": {"boundary": [{"action": "read"}]}}) == []


def test_built_ins_fill_one_policy_alone() -> None:
    assert complete_retry_policy({}) == _COMPLETE
    assert complete_retry_policy({"maxRetries": 3, "backoff": {"maxDelay": 2}}) == {
        "maxRetries": 3,
        "backoff": {"baseDelay": 0.008, "maxDelay": 2},
    }


def test_a_yaml_non_finite_carrier_survives_the_schema_and_is_refused_here() -> None:
    # Why this rule cannot be a schema constraint: the case schema admits both
    # carriers as numbers above zero.
    schemas = load_schemas(_CORE)
    template = (
        _CORE / "compatibility" / "cases" / "m-auto-retry-004-retries-zero-disables-loop.yaml"
    )
    for carrier in (".inf", ".nan"):
        case = read_corpus_yaml(template)
        case["when"]["uow"]["retry"] = load_corpus_yaml(f"backoff: {{maxDelay: {carrier}}}")
        assert (
            validation_error(
                case, schemas["compatibility-case.schema.json"], build_registry(schemas)
            )
            is None
        )
        assert retry_policy_problems(case)


def test_the_validation_stage_reports_a_refused_policy_against_its_case(tmp_path: Path) -> None:
    compatibility = tmp_path / "core" / "compatibility"
    cases = compatibility / "cases"
    cases.mkdir(parents=True)
    source = _CORE / "compatibility"
    (compatibility / "models").symlink_to(source / "models")
    (compatibility / "fixtures").symlink_to(source / "fixtures")
    (tmp_path / "core" / "schemas").symlink_to(_CORE / "schemas")
    name = "m-auto-retry-004-retries-zero-disables-loop.yaml"
    authored = (source / "cases" / name).read_text(encoding="utf-8")
    assert "retry: {maxRetries: 0}" in authored
    (cases / name).write_text(
        authored.replace("retry: {maxRetries: 0}", "retry: {backoff: {baseDelay: 2}}"),
        encoding="utf-8",
    )

    problems = validate_tree(compatibility)

    assert [problem for problem in problems if "baseDelay" in problem] == [
        f"case {name}: when.uow.retry.backoff resolves baseDelay 2 above maxDelay 1.0; "
        "an omitted field takes its built-in value"
    ]
