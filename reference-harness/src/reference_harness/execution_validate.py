"""Referential, arithmetic, and terminal validation of an execution record.

The schemas prove the record's shape on both sides of the mirror: which wrapper
it carries, which completion a call's kind admits, which status may carry a
failure. The rest of the record's obligations are relations between authored
numbers and positions rather than shapes, so no JSON Schema can state them and
this module owns them for the case oracle (`then.execution`) and for the adapter
envelope's matching observation alike (`m-execution-log`):

- a call names its statement by INDEX — into the case's flattened authored golden
  order on the asserted side, into the envelope's own ``emissions`` on the
  observed side — and an Attempt Failure names its call by index into that
  attempt's own flattened calls. Every index must land on something that exists,
  and a record whose index space is non-empty must carry one;
- every level's round-trip count is the count of what sits beneath it, and the
  whole agrees with the record's sole count oracle — ``then.roundTrips`` on a
  case, ``observations.roundTrips`` on an envelope — which the log restates
  rather than competes with;
- each write batch's trigger is a positional claim: a ``read-dependency`` batch
  is the one a dependent read forced, so it stands immediately before the Read
  Trace it enabled, and the ``finalization`` batch is the boundary's own last
  one, so nothing the attempt records follows it;
- the graph is TERMINAL, so a commit ends the invocation: a committed attempt is
  the final attempt, and the attempts number at most one more than the retained
  Retry Policy's maximum re-execution count.

Without these, a record whose numbers are internally consistent but names
nothing — every index ``999``, every count mirrored wrongly at all four levels —
validates and then asserts nothing about the run it grades.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["validate_execution", "validate_execution_observation"]


@dataclass(frozen=True)
class _StatementSpace:
    """What a Database Call's ``statement`` indexes, and how large that order is."""

    size: int
    noun: str
    holder: str

    def phrase(self) -> str:
        return f"{self.holder} {self.size} {self.noun}(s)"


def validate_execution(case: dict[str, Any]) -> list[str]:
    """Every referential, arithmetic, and terminal problem in *case*'s ``then.execution``.

    Returns an empty list for a case authoring no oracle. The caller has already
    validated *case* against the case schema, so this reads only the members the
    schema guarantees and reports one message per distinct problem.
    """
    then = case.get("then")
    if not isinstance(then, dict):
        return []
    space = _StatementSpace(_authored_golden_count(case), "golden statement", "the case authors")
    return _check_record(then.get("execution"), space, then.get("roundTrips", 1))


def validate_execution_observation(envelope: dict[str, Any]) -> list[str]:
    """Every such problem in a conformance adapter ``run`` *envelope*'s ``execution``.

    The envelope's own ``emissions`` is the index space a call's ``statement``
    names, and ``observations.roundTrips`` is the count the record restates.
    Returns an empty list for an envelope reporting no provenance. The caller has
    already validated *envelope* against the conformance-adapter schema.
    """
    observations = envelope.get("observations")
    if not isinstance(observations, dict):
        return []
    space = _StatementSpace(_entry_count(envelope, "emissions"), "emission", "the envelope reports")
    return _check_record(observations.get("execution"), space, observations.get("roundTrips"))


def _check_record(execution: Any, space: _StatementSpace, declared: Any) -> list[str]:
    if not isinstance(execution, dict):
        return []

    problems: list[str] = []
    read_trace = execution.get("readTrace")
    if isinstance(read_trace, dict):
        _check_trace(read_trace, "readTrace", space, problems)
        _check_total(read_trace.get("roundTrips"), declared, "readTrace", problems)
        return problems

    log = execution.get("transactionLog")
    if not isinstance(log, dict):  # pragma: no cover - the schema closes the union
        return problems
    attempts = log.get("attempts")
    attempts = attempts if isinstance(attempts, list) else []
    for index, attempt in enumerate(attempts):
        if isinstance(attempt, dict):
            _check_attempt(attempt, f"transactionLog.attempts[{index}]", space, problems)
    _check_history(log, attempts, problems)
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

    A call's ``statement`` indexes that order, so bounding an index needs its
    size. Goldens are authored case-level (``then.statements``), per scenario or
    coherence step, per conflict attempt, or per concurrency-round node — every
    shape that reaches the database and may therefore carry the oracle. A lane
    authoring none — the ``api-conformance`` lane, where a call carries no index
    at all — yields zero, and any index is then out of range.
    """
    total = _entry_count(case.get("then"), "statements")
    when = case.get("when")
    if not isinstance(when, dict):
        return total
    for key in ("scenario", "coherence", "attempts"):
        group = when.get(key)
        if isinstance(group, list):
            total += sum(_entry_count(entry, "statements") for entry in group)
    concurrency = when.get("concurrency")
    rounds = concurrency.get("rounds") if isinstance(concurrency, dict) else None
    if isinstance(rounds, list):
        for entry in rounds:
            if isinstance(entry, dict):
                total += sum(_entry_count(entry.get(node), "statements") for node in ("A", "B"))
    return total


def _entry_count(holder: Any, key: str) -> int:
    if not isinstance(holder, dict):
        return 0
    entries = holder.get(key)
    return len(entries) if isinstance(entries, list) else 0


def _check_attempt(
    attempt: dict[str, Any], label: str, space: _StatementSpace, problems: list[str]
) -> None:
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
        running += _check_trace(body, f"{label}.traces[{index}].{member}", space, problems)
        _check_trigger(body.get("trigger"), traces, index, label, problems)
    _check_sum(
        attempt.get("roundTrips"),
        [_trace_round_trips(trace) for trace in traces if isinstance(trace, dict)],
        label,
        "its traces'",
        problems,
    )
    _check_failure_call(attempt, label, running, problems)


def _check_trigger(
    trigger: Any, traces: list[Any], index: int, label: str, problems: list[str]
) -> None:
    if trigger == "read-dependency" and not _enables_a_read(traces, index):
        problems.append(
            f"{label}.traces[{index}] carries the `read-dependency` trigger but is not "
            f"immediately followed by a readTrace; the batch a dependent read forced "
            f"stands in front of the read it enabled, and that position is the whole "
            f"assertion"
        )
    if trigger == "finalization" and index != len(traces) - 1:
        problems.append(
            f"{label}.traces[{index}] carries the `finalization` trigger but is not the "
            f"attempt's last trace; the boundary owns the final batch, so nothing the "
            f"attempt records follows it"
        )


def _enables_a_read(traces: list[Any], index: int) -> bool:
    following = traces[index + 1] if index + 1 < len(traces) else None
    return isinstance(following, dict) and "readTrace" in following


def _trace_round_trips(trace: dict[str, Any]) -> Any:
    body = trace.get("readTrace") or trace.get("writeBatch")
    return body.get("roundTrips") if isinstance(body, dict) else None


def _check_history(log: dict[str, Any], attempts: list[Any], problems: list[str]) -> None:
    """The attempt history a TERMINAL graph admits (`m-execution-log`)."""
    last = len(attempts) - 1
    for index, attempt in enumerate(attempts):
        if isinstance(attempt, dict) and attempt.get("status") == "committed" and index != last:
            problems.append(
                f"transactionLog.attempts[{index}] committed but is not the last attempt; a "
                f"commit ends the invocation, so a terminal graph holds at most one committed "
                f"attempt and it is the final one"
            )
    policy = log.get("retryPolicy")
    bound = policy.get("maxRetries") if isinstance(policy, dict) else None
    if isinstance(bound, int) and len(attempts) > bound + 1:
        problems.append(
            f"transactionLog records {len(attempts)} attempts but its retryPolicy allows "
            f"{bound} re-execution(s); the original execution plus that bound is "
            f"{bound + 1} attempt(s) at most"
        )


def _check_trace(
    trace: dict[str, Any], label: str, space: _StatementSpace, problems: list[str]
) -> int:
    """Report the trace's own problems and return how many calls it holds."""
    calls = trace.get("calls")
    calls = calls if isinstance(calls, list) else []
    for index, call in enumerate(calls):
        if not isinstance(call, dict):  # pragma: no cover - the schema types the item
            continue
        _check_statement(call.get("statement"), f"{label}.calls[{index}]", space, problems)
    _check_count(trace.get("roundTrips"), len(calls), label, "its calls", problems)
    return len(calls)


def _check_statement(
    statement: Any, label: str, space: _StatementSpace, problems: list[str]
) -> None:
    if statement is None:
        if space.size:
            problems.append(
                f"{label} names no statement, but {space.phrase()}; a call names the statement "
                f"it ran, and omits the index only where there is none to name"
            )
        return
    if isinstance(statement, int) and not 0 <= statement < space.size:
        problems.append(f"{label} names statement {statement}, but {space.phrase()}")


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
            f"{label} declares roundTrips {observed} but the record declares roundTrips "
            f"{declared}; the case's own `then.roundTrips` (or the envelope's "
            f"`observations.roundTrips`) is the sole count oracle and the execution record "
            f"counts the same calls"
        )
