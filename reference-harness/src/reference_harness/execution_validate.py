"""Referential and arithmetic validation for the ``then.execution`` oracle.

The case schema proves the oracle's shape: which wrapper a case authors, which
completion a call's kind admits, which status may carry a failure. Three of the
oracle's obligations are relations between authored numbers rather than shapes,
so no JSON Schema can state them and this module owns them instead
(`m-execution-log`):

- a call names its statement by INDEX into the case's flattened authored golden
  order, and an Attempt Failure names its call by index into that attempt's own
  flattened calls, so both indexes must land on something that exists;
- every level's round-trip count is the count of what sits beneath it, and the
  whole agrees with ``then.roundTrips`` — the sole count oracle, which the log
  restates rather than competes with;
- a ``read-dependency`` write batch is the batch a dependent read forced, so it
  stands immediately before the Read Trace it enabled.

Without these, an oracle whose numbers are internally consistent but name
nothing — every index ``999``, every count mirrored wrongly at all four levels —
validates and then asserts nothing about the run it grades.
"""

from __future__ import annotations

from typing import Any

__all__ = ["validate_execution"]


def validate_execution(case: dict[str, Any]) -> list[str]:
    """Every referential and arithmetic problem in *case*'s ``then.execution``.

    Returns an empty list for a case authoring no oracle. The caller has already
    validated *case* against the case schema, so this reads only the members the
    schema guarantees and reports one message per distinct problem.
    """
    then = case.get("then")
    if not isinstance(then, dict):
        return []
    execution = then.get("execution")
    if not isinstance(execution, dict):
        return []

    problems: list[str] = []
    goldens = _authored_golden_count(case)
    declared = then.get("roundTrips", 1)

    read_trace = execution.get("readTrace")
    if isinstance(read_trace, dict):
        _check_trace(read_trace, "readTrace", goldens, problems)
        _check_total(read_trace.get("roundTrips"), declared, "readTrace", problems)
        return problems

    log = execution.get("transactionLog")
    if not isinstance(log, dict):  # pragma: no cover - the schema closes the union
        return problems
    attempts = log.get("attempts")
    attempts = attempts if isinstance(attempts, list) else []
    for index, attempt in enumerate(attempts):
        if isinstance(attempt, dict):
            _check_attempt(attempt, f"transactionLog.attempts[{index}]", goldens, problems)
    _check_sum(
        log.get("roundTrips"),
        [attempt.get("roundTrips") for attempt in attempts if isinstance(attempt, dict)],
        "transactionLog",
        "its attempts'",
        problems,
    )
    _check_total(log.get("roundTrips"), declared, "transactionLog", problems)
    return problems


def _authored_golden_count(case: dict[str, Any]) -> int:
    """How many golden statements the case's FLATTENED authored order holds.

    A call's ``statement`` indexes that order. Goldens are authored case-level
    (``then.statements``), per scenario step, or per conflict attempt; the
    flattening walks the case in document order, so a lane authoring none — the
    ``api-conformance`` lane, where a call carries no index at all — yields zero
    and any index at all is then out of range.
    """
    total = _entry_count(case.get("then"), "statements")
    when = case.get("when")
    if isinstance(when, dict):
        for key in ("scenario", "attempts"):
            group = when.get(key)
            if isinstance(group, list):
                total += sum(_entry_count(entry, "statements") for entry in group)
    return total


def _entry_count(holder: Any, key: str) -> int:
    if not isinstance(holder, dict):
        return 0
    entries = holder.get(key)
    return len(entries) if isinstance(entries, list) else 0


def _check_attempt(attempt: dict[str, Any], label: str, goldens: int, problems: list[str]) -> None:
    traces = attempt.get("traces")
    traces = traces if isinstance(traces, list) else []
    running = 0
    for index, trace in enumerate(traces):
        if not isinstance(trace, dict):  # pragma: no cover - the schema closes the union
            continue
        member = "readTrace" if "readTrace" in trace else "writeBatch"
        body = trace.get(member)
        if not isinstance(body, dict):  # pragma: no cover - the schema requires the member
            continue
        running += len(body.get("calls") or [])
        _check_trace(body, f"{label}.traces[{index}].{member}", goldens, problems)
        if body.get("trigger") == "read-dependency" and not _enables_a_read(traces, index):
            problems.append(
                f"{label}.traces[{index}] carries the `read-dependency` trigger but is not "
                f"immediately followed by a readTrace; the batch a dependent read forced "
                f"stands in front of the read it enabled, and that position is the whole "
                f"assertion"
            )
    _check_sum(
        attempt.get("roundTrips"),
        [_trace_round_trips(trace) for trace in traces if isinstance(trace, dict)],
        label,
        "its traces'",
        problems,
    )
    _check_failure_call(attempt, label, running, problems)


def _enables_a_read(traces: list[Any], index: int) -> bool:
    following = traces[index + 1] if index + 1 < len(traces) else None
    return isinstance(following, dict) and "readTrace" in following


def _trace_round_trips(trace: dict[str, Any]) -> Any:
    body = trace.get("readTrace") or trace.get("writeBatch")
    return body.get("roundTrips") if isinstance(body, dict) else None


def _check_trace(trace: dict[str, Any], label: str, goldens: int, problems: list[str]) -> None:
    calls = trace.get("calls")
    calls = calls if isinstance(calls, list) else []
    for index, call in enumerate(calls):
        if not isinstance(call, dict):  # pragma: no cover - the schema types the item
            continue
        statement = call.get("statement")
        if isinstance(statement, int) and not 0 <= statement < goldens:
            problems.append(
                f"{label}.calls[{index}] names golden statement {statement}, but the case "
                f"authors {goldens} golden statement(s)"
            )
    _check_count(trace.get("roundTrips"), len(calls), label, "its calls", problems)


def _check_failure_call(
    attempt: dict[str, Any], label: str, calls: int, problems: list[str]
) -> None:
    failure = attempt.get("failure")
    if not isinstance(failure, dict):
        return
    index = failure.get("databaseCall")
    if isinstance(index, int) and not 0 <= index < calls:
        problems.append(
            f"{label}.failure names database call {index}, but the attempt records "
            f"{calls} call(s); the index is attempt-local and names a call that already exists"
        )


def _check_count(declared: Any, actual: int, label: str, of: str, problems: list[str]) -> None:
    if declared != actual:
        problems.append(f"{label} declares roundTrips {declared} but {of} number {actual}")


def _check_sum(declared: Any, parts: list[Any], label: str, of: str, problems: list[str]) -> None:
    if any(not isinstance(part, int) for part in parts):  # pragma: no cover - schema-required
        return
    _check_count(declared, sum(parts), label, of, problems)


def _check_total(observed: Any, declared: Any, label: str, problems: list[str]) -> None:
    if observed != declared:
        problems.append(
            f"{label} declares roundTrips {observed} but the case declares then.roundTrips "
            f"{declared}; `then.roundTrips` is the sole count oracle and the execution "
            f"record counts the same calls"
        )
