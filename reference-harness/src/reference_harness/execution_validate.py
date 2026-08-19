"""Correlation, referential, and terminal validation of an execution-lifecycle record.

The schemas prove the record's shape on both sides of the mirror: which
transition an event carries, which payload that transition admits, which
outcome may carry a failure. What is left is relations BETWEEN events — a
number against a position, an ID against a tree, a trigger against what follows
it — which no JSON Schema can state, so this module owns them for the case
oracle (``then.executionLifecycle``) and for the adapter envelope's matching
observation alike (`m-execution-lifecycle`):

- **correlation.** ``sequence`` is contiguous and one-based within its root;
  ``activity`` is contiguous and one-based, assigned by a Started and reused by
  exactly one Finished of the matching kind; ``parent`` is null on the root
  activity ALONE and otherwise names an activity still OPEN at that point, which
  is what makes the authored stream a tree rather than a list that merely cites
  numbers;
- **balance.** Every Started has exactly one Finished, and the root activity's
  is the last event of its root;
- **attribution.** A ``caused`` failure names a DIRECT child of the failing
  activity that has already finished — an activity whose own ``parent`` is this
  one — because a cause is walked one link at a time and no level may skip to a
  deeper one;
- **statement.** A Database Call names its statement by INDEX — into the case's
  flattened authored golden order on the asserted side, into the envelope's own
  ``emissions`` on the observed side — and every index must land on something
  that exists, while a record whose index space is non-empty must carry one;
- **counts.** The record's sole count oracle — ``then.roundTrips`` on a case,
  ``observations.roundTrips`` on an envelope — counts the Database Call
  activities the stream opened, which the record restates rather than competes
  with;
- **triggers.** A batch's trigger is a POSITIONAL claim: a ``read-dependency``
  batch is the one a dependent read forced, so the sibling after it is the Read
  it enabled, and a ``pre-commit`` batch is the boundary's own last one, so
  nothing its attempt does follows it;
- **history.** A transaction root is TERMINAL, so a commit ends the invocation:
  at most one attempt commits and it is the last, the attempts number at most
  one more than the invocation's own resolved retry bound, and the classifier's
  verdict and that bound agree about where the history stops.

Without these, a record whose events are individually well formed but describe
no tree — every ``parent`` naming an activity that never opened, every count
mirrored wrongly — validates and then asserts nothing about the run it grades.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["validate_execution", "validate_execution_observation"]

_STARTED_FINISHED: dict[str, str] = {
    "readStarted": "readFinished",
    "writeBatchStarted": "writeBatchFinished",
    "databaseCallStarted": "databaseCallFinished",
    "transactionInvocationStarted": "transactionInvocationFinished",
    "transactionAttemptStarted": "transactionAttemptFinished",
    "snapshotStreamStarted": "snapshotStreamFinished",
    "streamBatchStarted": "streamBatchFinished",
}

_FINISHED_STARTED: dict[str, str] = {
    finished: started for started, finished in _STARTED_FINISHED.items()
}

_ROOT_ACTIVITY: dict[str, str] = {
    "read": "readStarted",
    "transaction-invocation": "transactionInvocationStarted",
    "snapshot-stream": "snapshotStreamStarted",
}


@dataclass(frozen=True)
class _StatementSpace:
    """What a Database Call's ``statement`` indexes, and how large that order is."""

    size: int
    noun: str
    holder: str

    def phrase(self) -> str:
        return f"{self.holder} {self.size} {self.noun}(s)"


@dataclass
class _Activity:
    """One activity as the stream describes it, while the stream is being read.

    ``children`` is in opening order, which is what makes a trigger's positional
    claim checkable: the batch a dependent read forced is the sibling before it.
    """

    activity: int
    started: str
    parent: int | None
    label: str
    started_payload: dict[str, Any]
    open: bool = True
    finished_payload: dict[str, Any] = field(default_factory=dict)
    children: list[int] = field(default_factory=list)


def validate_execution(case: dict[str, Any]) -> list[str]:
    """Every correlation, referential, and terminal problem in *case*'s
    ``then.executionLifecycle``.

    Returns an empty list for a case authoring no oracle. The caller has already
    validated *case* against the case schema, so this reads only the members the
    schema guarantees and reports one message per distinct problem.
    """
    then = case.get("then")
    if not isinstance(then, dict):
        return []
    space = _StatementSpace(_authored_golden_count(case), "golden statement", "the case authors")
    return _check_record(then.get("executionLifecycle"), space, then.get("roundTrips", 1))


def validate_execution_observation(envelope: dict[str, Any]) -> list[str]:
    """Every such problem in a conformance adapter ``run`` *envelope*'s
    ``executionLifecycle``.

    The envelope's own ``emissions`` is the index space a call's ``statement``
    names, and ``observations.roundTrips`` is the count the record restates.
    Returns an empty list for an envelope reporting no lifecycle. The caller has
    already validated *envelope* against the conformance-adapter schema.
    """
    observations = envelope.get("observations")
    if not isinstance(observations, dict):
        return []
    space = _StatementSpace(_entry_count(envelope, "emissions"), "emission", "the envelope reports")
    return _check_record(
        observations.get("executionLifecycle"), space, observations.get("roundTrips")
    )


def _check_record(lifecycle: Any, space: _StatementSpace, declared: Any) -> list[str]:
    if not isinstance(lifecycle, dict):
        return []
    roots = lifecycle.get("roots")
    roots = roots if isinstance(roots, list) else []
    problems: list[str] = []
    calls = 0
    for index, root in enumerate(roots):
        if not isinstance(root, dict):  # pragma: no cover - the schema types the item
            continue
        if root.get("execution") != index + 1:
            problems.append(
                f"roots[{index}] declares first observation {root.get('execution')}, but it is "
                f"root {index + 1} in the order this record states them; the index IS that "
                f"order, so a record authoring the two differently names two orders"
            )
        calls += _check_root(root, f"roots[{index}]", space, problems)
    _check_total(calls, declared, problems)
    return problems


def _check_root(
    root: dict[str, Any], label: str, space: _StatementSpace, problems: list[str]
) -> int:
    """Report *root*'s own problems and return how many Database Calls it opened."""
    events = root.get("events")
    events = events if isinstance(events, list) else []
    activities: dict[int, _Activity] = {}
    root_activity: int | None = None
    calls = 0
    for position, event in enumerate(events):
        if not isinstance(event, dict):  # pragma: no cover - the schema types the item
            continue
        where = f"{label}.events[{position}]"
        if event.get("sequence") != position + 1:
            problems.append(
                f"{where} declares sequence {event.get('sequence')} at delivery position "
                f"{position + 1}; a sequence is the one-based contiguous delivery position "
                f"within its root, so the two cannot disagree"
            )
        transition = _transition(event)
        if transition is None:  # pragma: no cover - the schema closes the union
            continue
        raw = event.get(transition)
        payload = raw if isinstance(raw, dict) else {}
        if transition in _STARTED_FINISHED:
            if _check_started(event, transition, payload, where, activities, problems):
                if event.get("parent") is None:
                    root_activity = _check_root_activity(
                        event, transition, root, root_activity, where, problems
                    )
                if transition == "databaseCallStarted":
                    calls += 1
                    _check_statement(payload.get("statement"), where, space, problems)
        else:
            _check_finished(event, transition, payload, where, activities, problems)
    _check_balance(events, activities, root_activity, label, problems)
    _check_triggers(activities, problems)
    _check_history(activities, root_activity, label, problems)
    return calls


def _transition(event: dict[str, Any]) -> str | None:
    for name in event:
        if name in _STARTED_FINISHED or name in _FINISHED_STARTED:
            return name
    return None  # pragma: no cover - the schema requires exactly one


def _check_started(
    event: dict[str, Any],
    transition: str,
    payload: dict[str, Any],
    where: str,
    activities: dict[int, _Activity],
    problems: list[str],
) -> bool:
    """Open the activity this Started assigns, reporting an ID that is not next."""
    activity = event.get("activity")
    if not isinstance(activity, int):  # pragma: no cover - the schema types the field
        return False
    if activity != len(activities) + 1:
        problems.append(
            f"{where} assigns activity {activity}, but {len(activities)} activity(s) were "
            f"assigned before it; an Activity ID is one-based and contiguous within its root, "
            f"so a Started takes the next one"
        )
        return False
    parent = event.get("parent")
    if parent is not None:
        holder = activities.get(parent) if isinstance(parent, int) else None
        if holder is None:
            problems.append(
                f"{where} names parent activity {parent}, which no earlier Started assigned; a "
                f"parent is an activity of this same root"
            )
        elif not holder.open:
            problems.append(
                f"{where} names parent activity {parent}, which had already finished; an "
                f"activity is contained by one still open, or the tree it states never existed"
            )
        else:
            holder.children.append(activity)
    activities[activity] = _Activity(
        activity=activity,
        started=transition,
        parent=parent,
        label=where,
        started_payload=payload,
    )
    return True


def _check_root_activity(
    event: dict[str, Any],
    transition: str,
    root: dict[str, Any],
    root_activity: int | None,
    where: str,
    problems: list[str],
) -> int:
    """The one activity a root opens with, and the kind that root claims."""
    activity: int = event["activity"]
    if root_activity is not None:
        problems.append(
            f"{where} names no parent, but activity {root_activity} already opened this root "
            f"without one; a Root Execution has exactly one root activity, and everything else "
            f"it contains names a parent"
        )
        return root_activity
    expected = _ROOT_ACTIVITY.get(str(root.get("kind")))
    if expected is not None and transition != expected:
        problems.append(
            f"{where} opens a root of kind {root.get('kind')!r} with {transition}; the kind "
            f"names which outermost operation opened the root, so its root activity is "
            f"{expected}"
        )
    return activity


def _check_finished(
    event: dict[str, Any],
    transition: str,
    payload: dict[str, Any],
    where: str,
    activities: dict[int, _Activity],
    problems: list[str],
) -> None:
    """Close the activity this Finished reuses, reporting every way it cannot."""
    activity = event.get("activity")
    holder = activities.get(activity) if isinstance(activity, int) else None
    if holder is None:
        problems.append(
            f"{where} finishes activity {activity}, which no Started assigned; a Finished "
            f"REUSES the ID its own Started took"
        )
        return
    if not holder.open:
        problems.append(
            f"{where} finishes activity {activity}, which already finished; an activity starts "
            f"once and finishes once"
        )
        return
    if _FINISHED_STARTED[transition] != holder.started:
        problems.append(
            f"{where} finishes activity {activity} as {transition}, but {holder.label} started "
            f"it as {holder.started}; a Finished names the same activity KIND its Started did"
        )
    if event.get("parent") != holder.parent:
        problems.append(
            f"{where} finishes activity {activity} under parent {event.get('parent')}, but "
            f"{holder.label} started it under parent {holder.parent}; one activity has one "
            f"place in the tree"
        )
    holder.open = False
    holder.finished_payload = payload
    _check_cause(payload, holder, where, activities, problems)


def _check_cause(
    payload: dict[str, Any],
    holder: _Activity,
    where: str,
    activities: dict[int, _Activity],
    problems: list[str],
) -> None:
    """A cause names a DIRECT child that has already finished."""
    cause = payload.get("cause")
    if not isinstance(cause, int):
        return
    child = activities.get(cause)
    if child is None or child.parent != holder.activity:
        problems.append(
            f"{where} attributes its failure to activity {cause}, which is no direct child of "
            f"activity {holder.activity}; every level names its OWN child, so a cause is walked "
            f"one link at a time rather than skipped to"
        )
        return
    if child.open:
        problems.append(
            f"{where} attributes its failure to activity {cause}, which had not finished; an "
            f"activity is caused to fail by a child that already reported"
        )


def _check_triggers(activities: dict[int, _Activity], problems: list[str]) -> None:
    """Each Write Batch trigger against the position it claims."""
    for batch in activities.values():
        if batch.started != "writeBatchStarted":
            continue
        trigger = batch.started_payload.get("trigger")
        siblings = _siblings(batch, activities)
        position = siblings.index(batch.activity)
        following = siblings[position + 1 :]
        if trigger == "read-dependency" and not _enables_a_read(following, activities):
            problems.append(
                f"{batch.label} carries the `read-dependency` trigger but the next activity its "
                f"attempt opened is not a Read; the batch a dependent read forced stands in "
                f"front of the read it enabled, and that position is the whole assertion"
            )
        if trigger == "pre-commit" and following:
            problems.append(
                f"{batch.label} carries the `pre-commit` trigger but its attempt opened "
                f"activity {following[0]} after it; the boundary owns the FINAL batch, so "
                f"nothing the attempt does follows it"
            )


def _enables_a_read(following: list[int], activities: dict[int, _Activity]) -> bool:
    return bool(following) and activities[following[0]].started == "readStarted"


def _siblings(activity: _Activity, activities: dict[int, _Activity]) -> list[int]:
    parent = activities.get(activity.parent) if isinstance(activity.parent, int) else None
    return parent.children if parent is not None else [activity.activity]


def _check_balance(
    events: list[Any],
    activities: dict[int, _Activity],
    root_activity: int | None,
    label: str,
    problems: list[str],
) -> None:
    """Balance, and the claim the whole stream makes about its own end."""
    still_open = sorted(key for key, value in activities.items() if value.open)
    if still_open:
        problems.append(
            f"{label} ends with activity(s) {still_open} still open; every Started has exactly "
            f"one Finished, because a scope emits its end however its body leaves"
        )
    if root_activity is None:
        problems.append(
            f"{label} opens no root activity; a Root Execution is one outermost operation, so "
            f"exactly one of its activities has no parent"
        )
        return
    last = events[-1] if events else None
    if isinstance(last, dict) and last.get("activity") != root_activity:
        problems.append(
            f"{label} ends on activity {last.get('activity')} rather than on root activity "
            f"{root_activity}; the root contains everything it caused, so its own end is the "
            f"last event delivered"
        )


def _check_history(
    activities: dict[int, _Activity], root_activity: int | None, label: str, problems: list[str]
) -> None:
    """The attempt history a TERMINAL transaction stream admits."""
    invocation = activities.get(root_activity) if root_activity is not None else None
    if invocation is None or invocation.started != "transactionInvocationStarted":
        return
    attempts = [
        activities[child]
        for child in invocation.children
        if activities[child].started == "transactionAttemptStarted"
    ]
    if not attempts:
        return
    for index, attempt in enumerate(attempts[:-1]):
        if attempt.finished_payload.get("outcome") == "committed":
            problems.append(
                f"{attempt.label} committed but is not the last attempt of its invocation; a "
                f"commit ends the invocation, so a terminal stream holds at most one committed "
                f"attempt and it is the final one"
            )
        elif attempt.finished_payload.get("retryEligible") is not True:
            problems.append(
                f"{attempt.label} records a failure the classifier judged ineligible for retry, "
                f"but attempt {attempts[index + 1].activity} follows it; a non-retriable "
                f"failure surfaces to the caller instead of re-executing the closure"
            )
    bound = invocation.started_payload.get("retries")
    if not isinstance(bound, int):
        return
    if len(attempts) > bound + 1:
        problems.append(
            f"{label} ran {len(attempts)} attempt(s), but its invocation resolved {bound} "
            f"re-execution(s); the original execution plus that bound is {bound + 1} "
            f"attempt(s) at most"
        )
    final = attempts[-1].finished_payload
    if final.get("outcome") != "committed" and final.get("retryEligible") is True:
        if len(attempts) < bound + 1:
            problems.append(
                f"{label} ends on an attempt that rolled back with a retry-eligible failure, "
                f"but only {len(attempts)} of the {bound + 1} attempt(s) its invocation allows "
                f"ran; a failure the classifier admitted re-executes the closure until the "
                f"bound is spent, so a stream terminates on one only at exhaustion"
            )


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


def _check_total(calls: int, declared: Any, problems: list[str]) -> None:
    if calls != declared:
        problems.append(
            f"the lifecycle opens {calls} Database Call(s) but the record declares roundTrips "
            f"{declared}; `then.roundTrips` (or the envelope's `observations.roundTrips`) is "
            f"the sole count oracle and the lifecycle counts the same calls, so a record "
            f"authoring both states one number twice"
        )


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
