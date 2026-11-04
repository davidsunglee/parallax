"""The Retry Policy rules JSON Schema cannot state (`m-case-format` *Retry
policies*): a delay is finite, and a policy's ``maxDelay`` is at least its
``baseDelay`` once a field it omits takes its built-in value.

``exclusiveMinimum`` admits a YAML ``.inf`` and ``.nan``, and no schema keyword
compares two members or sees the built-in a member omitted, so a base delay
above the built-in maximum is refused here rather than at a language's policy
constructor. This is the portable statement of those rules, independent of any
binding's policy type.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from typing import Any

from .case import complete_retry_policy

__all__ = ["retry_policy_problems"]


def retry_policy_problems(case: dict[str, Any]) -> list[str]:
    """Every problem with a policy *case* configures, requests, or expects.

    The caller has already validated *case* against the case schema, so this
    reads only the members the schema guarantees.
    """
    return [
        problem for where, authored in _policies(case) for problem in _problems(where, authored)
    ]


def _policies(case: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    given = case.get("given", {})
    when = case.get("when", {})
    then = case.get("then", {})
    if "retry" in given.get("databaseOptions", {}):
        yield "given.databaseOptions.retry", given["databaseOptions"]["retry"]
    if "retry" in when.get("uow", {}):
        yield "when.uow.retry", when["uow"]["retry"]
    for index, step in enumerate(when.get("boundary", [])):
        if "retry" in step:
            yield f"when.boundary[{index}].retry", step["retry"]
    for root_index, root in enumerate(then.get("executionLifecycle", {}).get("roots", [])):
        for event_index, event in enumerate(root["events"]):
            started = event.get("transactionInvocationStarted", {})
            if "retry" in started:
                yield (
                    f"then.executionLifecycle.roots[{root_index}].events[{event_index}]"
                    ".transactionInvocationStarted.retry",
                    started["retry"],
                )


def _problems(where: str, authored: dict[str, Any]) -> list[str]:
    backoff = complete_retry_policy(authored)["backoff"]
    infinite = [name for name, value in backoff.items() if not _finite(value)]
    if infinite:
        return [f"{where}.backoff.{name} must be a finite number of seconds" for name in infinite]
    if float(backoff["maxDelay"]) < float(backoff["baseDelay"]):
        return [
            f"{where}.backoff resolves baseDelay {backoff['baseDelay']} above maxDelay "
            f"{backoff['maxDelay']}; an omitted field takes its built-in value"
        ]
    return []


def _finite(value: float) -> bool:
    try:
        return math.isfinite(value)
    except OverflowError:
        return False
