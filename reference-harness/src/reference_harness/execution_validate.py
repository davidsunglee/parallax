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
- **topology.** Each activity kind names the kinds that may contain it: an Outer
  Invocation is the root and nothing else, a Joined Invocation and a Transaction
  Attempt each belong under their own one kind, and a Database Call is the direct
  child of the Read, Write Batch, or Stream Batch that owns it. An invocation
  finishes in the vocabulary its own kind admits — a physical commit or failure
  for the outer one, a nested return or raise for a joined one;
- **balance.** Every Started has exactly one Finished, the root activity's is the
  last event of its root, and an activity SPANS what it contains, so no scope
  finishes while a child of its own is still open;
- **attribution.** A ``caused`` failure names a DIRECT child of the failing
  activity that has already finished — an activity whose own ``parent`` is this
  one — because a cause is walked one link at a time and no level may skip to a
  deeper one;
- **statement.** A Database Call names its statement by INDEX — into the case's
  flattened authored golden order on the asserted side, into the envelope's own
  ``emissions`` on the observed side. Every index must land on something that
  exists, the indexes a record names are its whole space, in delivery order
  and once each, and each index is owned by a call of the kind its own statement
  is — a query by a read, DML by a write — or a resolving read taking a write's
  index would cover the space while the write that ran it appears nowhere; the
  calls that name none are the two the space does not hold — every call where
  nothing is authored at all, and the resolving read a keyed write owes, which
  is a read;
- **counts.** The record's sole count oracle — ``then.roundTrips`` on a case,
  ``observations.roundTrips`` on an envelope — counts the Database Call
  activities the stream opened, which the record restates rather than competes
  with;
- **triggers.** A batch's trigger is a POSITIONAL claim: a ``read-dependency``
  batch is the one a dependent read forced, so the sibling after it is the Read
  it enabled and it has already FINISHED when that Read starts, and a
  ``pre-commit`` batch is the boundary's own last one, so nothing its attempt
  does after it but give its connection back;
- **resources.** An activity that owns a connection opens at most one
  Acquisition and at most one Release, the Acquisition FIRST among its children
  and the Release LAST, a Release only where the Acquisition granted something,
  and neither containing anything: they are siblings of the work beside them
  rather than a lease around it;
- **history.** A transaction root is TERMINAL, so a commit ends the invocation:
  attempts run one after another rather than overlapping, at most one commits and
  it is the last, the invocation's own outcome agrees with that last attempt, an
  invocation running no attempt at all is the begin failure that is the only way
  to run none and finishes failed, the attempts number at most one more than the
  invocation's own resolved retry bound, the classifier's verdict and that bound
  agree about where the history stops, and a rollback failure ends the history
  whatever the classifier said about the failure that triggered it.

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
    "acquisitionStarted": "acquisitionFinished",
    "releaseStarted": "releaseFinished",
}

_FINISHED_STARTED: dict[str, str] = {
    finished: started for started, finished in _STARTED_FINISHED.items()
}

_ROOT_ACTIVITY: dict[str, str] = {
    "read": "readStarted",
    "transaction-invocation": "transactionInvocationStarted",
    "snapshot-stream": "snapshotStreamStarted",
}

_OUTER: str = "transactionInvocationStarted:outer"
_JOINED: str = "transactionInvocationStarted:joined"

_OWNS_CONNECTION: tuple[str, ...] = (
    "readStarted",
    "transactionAttemptStarted",
    "snapshotStreamStarted",
)

_RESOURCE_KINDS: tuple[str, ...] = ("acquisitionStarted", "releaseStarted")

_OWNER_FAILED: frozenset[str] = frozenset({"failed", "beginFailed"})

_CONTAINED_BY: dict[str, tuple[str, ...]] = {
    "readStarted": ("transactionAttemptStarted",),
    "writeBatchStarted": ("transactionAttemptStarted",),
    "databaseCallStarted": ("readStarted", "writeBatchStarted", "streamBatchStarted"),
    "transactionAttemptStarted": (_OUTER,),
    "snapshotStreamStarted": ("transactionAttemptStarted",),
    "streamBatchStarted": ("snapshotStreamStarted",),
    "acquisitionStarted": _OWNS_CONNECTION,
    "releaseStarted": _OWNS_CONNECTION,
    _OUTER: (),
    _JOINED: ("transactionAttemptStarted",),
}

_ROOT_KINDS: frozenset[str] = frozenset({"readStarted", _OUTER, "snapshotStreamStarted"})

_LEADING_KIND: dict[str, str] = {
    "select": "read",
    "insert": "write",
    "update": "write",
    "delete": "write",
}

_INVOCATION_OUTCOMES: dict[str, tuple[str, ...]] = {
    _OUTER: ("committed", "failed"),
    _JOINED: ("returned", "raised"),
}


def _activity_kind(started: str, payload: dict[str, Any]) -> str:
    """``started``, refined by the one payload field that changes what may
    contain an activity: an Outer Invocation is a root and a Joined Invocation is
    an attempt's child, and the two share one transition name."""
    if started != "transactionInvocationStarted":
        return started
    invocation = payload.get("invocation")
    return f"{started}:{invocation}" if isinstance(invocation, str) else started


@dataclass(frozen=True)
class _StatementSpace:
    """What a Database Call's ``statement`` indexes.

    ``kinds`` is one entry per statement, in the flattened order an index names,
    holding the Database Call kind that statement's own SQL states — ``read``
    for a query, ``write`` for DML, and ``None`` where the SQL states neither,
    which is what keeps an unfamiliar statement from narrowing anything.
    """

    kinds: tuple[str | None, ...]
    noun: str
    holder: str

    @property
    def size(self) -> int:
        return len(self.kinds)

    def phrase(self) -> str:
        return f"{self.holder} {self.size} {self.noun}(s)"


@dataclass(frozen=True)
class _Call:
    """One Database Call as the statement rules read it: where it is, which index
    it named, and whether it read or wrote."""

    label: str
    statement: Any
    kind: str


@dataclass
class _Activity:
    """One activity as the stream describes it, while the stream is being read.

    ``children`` is in opening order and the two positions are delivery
    positions within the root, which is what makes a trigger's positional claim
    checkable: the batch a dependent read forced is the sibling before it, and
    it has already closed when that read opens.
    """

    activity: int
    started: str
    kind: str
    parent: int | None
    label: str
    started_payload: dict[str, Any]
    started_at: int
    open: bool = True
    finished_at: int | None = None
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
    space = _StatementSpace(_authored_golden_kinds(case), "golden statement", "the case authors")
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
    space = _StatementSpace(_entry_kinds(envelope, "emissions"), "emission", "the envelope reports")
    return _check_record(
        observations.get("executionLifecycle"), space, observations.get("roundTrips")
    )


def _check_record(lifecycle: Any, space: _StatementSpace, declared: Any) -> list[str]:
    if not isinstance(lifecycle, dict):
        return []
    roots = lifecycle.get("roots")
    roots = roots if isinstance(roots, list) else []
    problems: list[str] = []
    calls: list[_Call] = []
    for index, root in enumerate(roots):
        if not isinstance(root, dict):  # pragma: no cover - the schema types the item
            continue
        if root.get("execution") != index + 1:
            problems.append(
                f"roots[{index}] declares first observation {root.get('execution')}, but it is "
                f"root {index + 1} in the order this record states them; the index IS that "
                f"order, so a record authoring the two differently names two orders"
            )
        calls.extend(_check_root(root, f"roots[{index}]", problems))
    _check_statements(calls, space, problems)
    _check_total(len(calls), declared, problems)
    return problems


def _check_root(root: dict[str, Any], label: str, problems: list[str]) -> list[_Call]:
    """Report *root*'s own problems and return the Database Calls it opened, in
    delivery order."""
    events = root.get("events")
    events = events if isinstance(events, list) else []
    activities: dict[int, _Activity] = {}
    root_activity: int | None = None
    calls: list[_Call] = []
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
            if _check_started(event, transition, payload, where, position, activities, problems):
                if event.get("parent") is None:
                    root_activity = _check_root_activity(
                        event, transition, root, root_activity, where, problems
                    )
                if transition == "databaseCallStarted":
                    calls.append(
                        _Call(
                            label=where,
                            statement=payload.get("statement"),
                            kind=str(payload.get("kind")),
                        )
                    )
        else:
            _check_finished(event, transition, payload, where, position, activities, problems)
    _check_balance(events, activities, root_activity, label, problems)
    _check_triggers(activities, problems)
    _check_resources(activities, problems)
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
    position: int,
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
    kind = _activity_kind(transition, payload)
    parent = event.get("parent")
    holder = activities.get(parent) if isinstance(parent, int) else None
    if parent is not None:
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
    _check_containment(kind, holder, parent, where, problems)
    activities[activity] = _Activity(
        activity=activity,
        started=transition,
        kind=kind,
        parent=parent,
        label=where,
        started_payload=payload,
        started_at=position,
    )
    return True


def _check_containment(
    kind: str, holder: _Activity | None, parent: int | None, where: str, problems: list[str]
) -> None:
    """The kinds ``kind`` may be contained by, against the one containing it here.

    An activity kind does not stand anywhere in the tree: an Outer Invocation IS
    the root, a Joined Invocation runs inside the attempt it joined, an attempt
    runs under the outer invocation that retries it, and a Database Call is the
    direct child of the Read, Write Batch, or Stream Batch that owns it. Without
    this the correlation rules describe a tree of anonymous nodes, which any
    stream can satisfy by naming numbers that happen to be open.
    """
    allowed = _CONTAINED_BY.get(kind)
    if allowed is None:  # pragma: no cover - the table covers every started kind
        return
    if parent is None:
        if kind not in _ROOT_KINDS:
            problems.append(
                f"{where} opens {kind} with no parent, but a Root Execution's own outermost "
                f"activity is one of {', '.join(sorted(_ROOT_KINDS))}; every other kind is "
                f"contained by {' or '.join(allowed) or 'nothing, because it is a root alone'}"
            )
        return
    if not allowed:
        problems.append(
            f"{where} opens {kind} under activity {parent}; an Outer Invocation is the root "
            f"activity, so a nested invocation is a joined one"
        )
        return
    if holder is not None and holder.kind not in allowed:
        problems.append(
            f"{where} opens {kind} under activity {parent}, which started as {holder.kind}; "
            f"{kind} is contained by {' or '.join(allowed)}"
        )
        return
    if kind in _RESOURCE_KINDS and holder is not None and not _owns_connection(holder):
        problems.append(
            f"{where} opens {kind} under activity {parent}, which is participating work; a "
            f"connection is held by a STANDALONE Read, a Transaction Attempt, or a STANDALONE "
            f"Snapshot Stream, and work that inherits one emits neither an Acquisition nor a "
            f"Release"
        )


def _owns_connection(activity: _Activity) -> bool:
    """Whether ``activity`` holds a connection of its own rather than inheriting one.

    Three activities do, and two of them are distinguished from their
    participating namesakes by being their root's outermost activity: a
    standalone Read and a standalone Snapshot Stream own what they take, while a
    Read or a stream running under an attempt is one more thing running on the
    attempt's connection.
    """
    if activity.started == "transactionAttemptStarted":
        return True
    return activity.started in ("readStarted", "snapshotStreamStarted") and activity.parent is None


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
    position: int,
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
    _check_scope(holder, where, activities, problems)
    _check_invocation_outcome(holder, payload, where, problems)
    holder.open = False
    holder.finished_at = position
    holder.finished_payload = payload
    _check_cause(payload, holder, where, activities, problems)


def _check_scope(
    holder: _Activity, where: str, activities: dict[int, _Activity], problems: list[str]
) -> None:
    """An activity SPANS what it contains, so its children close before it does."""
    inside = sorted(child for child in holder.children if activities[child].open)
    if inside:
        problems.append(
            f"{where} finishes activity {holder.activity} while activity(s) {inside} it "
            f"contains are still open; an activity spans everything it caused, so a scope "
            f"cannot end before what it holds"
        )


def _check_invocation_outcome(
    holder: _Activity, payload: dict[str, Any], where: str, problems: list[str]
) -> None:
    """A Transaction Invocation finishes in the vocabulary its own kind admits.

    An Outer Invocation reports what the PHYSICAL transaction did — committed or
    failed — while a joined one reports only how the nested callback left, so the
    two vocabularies are the semantic distinction between them rather than
    interchangeable spellings.
    """
    admitted = _INVOCATION_OUTCOMES.get(holder.kind)
    if admitted is None:
        return
    outcome = payload.get("outcome")
    if outcome not in admitted:
        problems.append(
            f"{where} finishes {holder.kind} as {outcome!r}; that invocation finishes as "
            f"{' or '.join(admitted)}, because returning and raising describe the nested "
            f"callback alone while committing and failing describe the physical transaction"
        )


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
        if trigger == "read-dependency":
            _check_read_dependency(batch, following, activities, problems)
        if trigger == "pre-commit":
            _check_pre_commit(batch, following, activities, problems)


def _check_pre_commit(
    batch: _Activity,
    following: list[int],
    activities: dict[int, _Activity],
    problems: list[str],
) -> None:
    """Nothing the attempt's WORK does follows the boundary's own last batch.

    Its Release does, and only its Release: giving the connection back is what
    an attempt does once its work is over, so the batch is still the final thing
    written and the resource activity after it is the end of the borrowing
    rather than more work.
    """
    trailing = [child for child in following if activities[child].started != "releaseStarted"]
    if trailing:
        problems.append(
            f"{batch.label} carries the `pre-commit` trigger but its attempt opened "
            f"activity {trailing[0]} after it; the boundary owns the FINAL batch, so "
            f"nothing the attempt does follows it but giving its connection back"
        )


def _check_resources(activities: dict[int, _Activity], problems: list[str]) -> None:
    """The Acquisition and Release an activity that owns a connection may open.

    Each claim here is one the correlation rules cannot make. An owner opens AT
    MOST ONE of each, because one operation holds one connection rather than a
    series of them. The Acquisition is its owner's FIRST child and the Release
    its LAST, which is what "held for the operation's own lifetime" means read
    off a stream. And neither opens a child: they are siblings of the execution
    work rather than a lease around it, so a Database Call under one would
    describe a statement running inside a checkout.

    The rest is the relation between the two ends and the operation between
    them, read in BOTH directions rather than one. An owner opens an Acquisition
    unless it is a stream closed before its first page, so the pair cannot be
    omitted by a record that simply declines to mention it. A Release exists
    exactly where the Acquisition granted something and the owner finished, so
    neither a hold that ends without beginning nor one that begins without
    ending validates. Work runs on a connection, so an owner with any child
    besides its own two ends was GRANTED one. And an acquisition that granted
    nothing is the owner's own failure, named as its cause — so a record cannot
    show an operation succeeding, or running statements, on a connection it
    never got.
    """
    for owner in activities.values():
        if not _owns_connection(owner):
            continue
        children = [activities[child] for child in owner.children]
        acquisitions = [child for child in children if child.started == "acquisitionStarted"]
        releases = [child for child in children if child.started == "releaseStarted"]
        _check_resource_count(owner, acquisitions, "acquisition", problems)
        _check_resource_count(owner, releases, "release", problems)
        if acquisitions and children[0] is not acquisitions[0]:
            problems.append(
                f"{acquisitions[0].label} opens activity {acquisitions[0].activity} after "
                f"activity {children[0].activity}, which its owner opened first; a connection "
                f"is taken before the work that runs on it, so an Acquisition is its owner's "
                f"first child"
            )
        if releases and children[-1] is not releases[0]:
            problems.append(
                f"{releases[0].label} opens activity {releases[0].activity} before activity "
                f"{children[-1].activity}, which its owner opened after it; a connection is "
                f"given back once the work that ran on it is over, so a Release is its "
                f"owner's last child"
            )
        if releases and not _granted(acquisitions):
            problems.append(
                f"{releases[0].label} ends a hold its owner never began: activity "
                f"{owner.activity} opens a Release without an Acquisition that granted a "
                f"connection, and an acquisition that granted none has nothing to release"
            )
        if _granted(acquisitions) and not releases:
            problems.append(
                f"activity {owner.activity} acquired a connection and never released it; an "
                f"operation holds one for its OWN lifetime, so a hold this record shows "
                f"beginning is one it shows ending"
            )
        _check_acquired(owner, acquisitions, problems)
        _check_work_acquired(owner, children, acquisitions, problems)
        _check_refusal(owner, acquisitions, problems)
        _check_begin_attribution(owner, acquisitions, problems)
    for activity in activities.values():
        if activity.started in _RESOURCE_KINDS and activity.children:
            problems.append(
                f"{activity.label} opens activity {activity.children[0]} under "
                f"{activity.started}; an Acquisition and a Release are siblings of the work "
                f"beside them rather than scopes it runs inside, so neither contains anything"
            )


def _granted(acquisitions: list[_Activity]) -> bool:
    return any(
        acquisition.finished_payload.get("outcome") == "acquired" for acquisition in acquisitions
    )


def _refused(acquisitions: list[_Activity]) -> _Activity | None:
    """The Acquisition this owner opened that granted no connection, if it did."""
    for acquisition in acquisitions:
        if acquisition.finished_payload.get("outcome") == "failed":
            return acquisition
    return None


def _check_acquired(owner: _Activity, acquisitions: list[_Activity], problems: list[str]) -> None:
    """An owner that reached the point of needing a connection asked for one.

    A standalone Read acquires before its first statement and an attempt before
    its boundary is asked to begin, so each opens an Acquisition whatever it
    goes on to report: a begin failure is an attempt that ASKED, refused either
    the connection or the boundary it opened on, and an empty Read is one that
    took a connection and ran nothing on it.

    A standalone Snapshot Stream is the one owner that may open none, because it
    acquires where it reads its FIRST PAGE: a caller who closed the stream
    before asking for one left it never having reached the connection. Every
    other outcome did reach it — exhaustion is discovered by reading a page, and
    a stream fails only over delivery work that starts there.
    """
    if acquisitions:
        return
    if (
        owner.started == "snapshotStreamStarted"
        and owner.finished_payload.get("outcome") == "closedEarly"
    ):
        return
    problems.append(
        f"{owner.label} opens no Acquisition; an operation reaches the database through a "
        f"connection of its own, and only a Snapshot Stream closed before its first page "
        f"finishes without having asked for one"
    )


def _check_work_acquired(
    owner: _Activity,
    children: list[_Activity],
    acquisitions: list[_Activity],
    problems: list[str],
) -> None:
    """An owner that did anything did it on a connection it was granted.

    The Acquisition and the Release are the ends of the hold rather than work
    inside it, so any OTHER child is a statement, a flush, a page, or a nested
    boundary — and every one of those runs on the connection this activity took.
    An owner that opened one without an Acquisition that granted describes work
    on nothing, which is the shape a record whose acquisition was REFUSED would
    take.
    """
    work = [child for child in children if child.started not in _RESOURCE_KINDS]
    if not work or _granted(acquisitions):
        return
    problems.append(
        f"{work[0].label} opens activity {work[0].activity} under activity {owner.activity}, "
        f"which was granted no connection; work reaches the database through the connection "
        f"its owner holds, so an owner that ran any opened one first"
    )


def _check_refusal(owner: _Activity, acquisitions: list[_Activity], problems: list[str]) -> None:
    """An acquisition that granted nothing is the failure of the owner above it.

    The owner holds that failure under the ordinary Holding rule, so it finishes
    failed and names the Acquisition as its cause. A record showing an owner
    that succeeded, or that failed of its own accord, after being refused a
    connection describes an operation that ran without one.
    """
    refused = _refused(acquisitions)
    if refused is None:
        return
    payload = owner.finished_payload
    outcome = payload.get("outcome")
    if outcome not in _OWNER_FAILED:
        problems.append(
            f"activity {owner.activity} finishes {outcome!r} after activity {refused.activity} "
            f"granted it no connection; an operation refused a connection never ran, so its "
            f"owner fails"
        )
        return
    if payload.get("attribution") != "caused" or payload.get("cause") != refused.activity:
        problems.append(
            f"activity {owner.activity} fails without naming activity {refused.activity}, the "
            f"Acquisition that granted it no connection; the owner holds that failure under "
            f"the ordinary Holding rule, so its own failure is caused by it"
        )


def _check_begin_attribution(
    owner: _Activity, acquisitions: list[_Activity], problems: list[str]
) -> None:
    """A `beginFailed` attempt is `caused` exactly by a refused Acquisition.

    An attempt whose boundary refused to open on a connection it DID acquire has
    no child holding that failure, so it is `direct`. `caused` therefore names
    the one child a begin failure can have — the Acquisition that granted
    nothing — and naming any other child claims an attribution no begin failure
    can reach.
    """
    payload = owner.finished_payload
    if owner.started != "transactionAttemptStarted" or payload.get("outcome") != "beginFailed":
        return
    if payload.get("attribution") != "caused":
        return
    refused = _refused(acquisitions)
    if refused is None or payload.get("cause") != refused.activity:
        problems.append(
            f"activity {owner.activity} finishes `beginFailed` caused by activity "
            f"{payload.get('cause')}; a begin failure is caused only by an Acquisition of its "
            f"own that granted no connection, and every other one is the attempt's own direct "
            f"refusal"
        )


def _check_resource_count(
    owner: _Activity, opened: list[_Activity], noun: str, problems: list[str]
) -> None:
    if len(opened) > 1:
        problems.append(
            f"{opened[1].label} opens a second {noun} under activity {owner.activity}; one "
            f"operation holds ONE connection for its own lifetime, so it takes it once and "
            f"gives it back once"
        )


def _check_read_dependency(
    batch: _Activity,
    following: list[int],
    activities: dict[int, _Activity],
    problems: list[str],
) -> None:
    """The dependency batch stands in front of the Read it enabled, and is DONE.

    Ordering the two opening events is not the claim: a read that force-flushed
    the buffer waits for that flush, so the batch has already finished when the
    read starts. A stream whose batch merely opened first would describe a read
    running against a buffer still on the wire.
    """
    read = activities[following[0]] if following else None
    if read is None or read.started != "readStarted":
        problems.append(
            f"{batch.label} carries the `read-dependency` trigger but the next activity its "
            f"attempt opened is not a Read; the batch a dependent read forced stands in "
            f"front of the read it enabled, and that position is the whole assertion"
        )
        return
    if batch.finished_at is None or batch.finished_at > read.started_at:
        problems.append(
            f"{batch.label} carries the `read-dependency` trigger but had not finished when "
            f"{read.label} started activity {read.activity}; the read waits on the flush it "
            f"forced, so the batch it enabled it with is over before the read begins"
        )


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
        _check_attemptless(invocation, label, problems)
        return
    for index, attempt in enumerate(attempts[:-1]):
        _check_retried(attempt, attempts[index + 1], problems)
    _check_terminal_attempt(invocation, attempts, label, problems)
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
    if final.get("outcome") == "rolledBack" and final.get("retryEligible") is True:
        if len(attempts) < bound + 1:
            problems.append(
                f"{label} ends on an attempt that rolled back with a retry-eligible failure, "
                f"but only {len(attempts)} of the {bound + 1} attempt(s) its invocation allows "
                f"ran; a failure the classifier admitted re-executes the closure until the "
                f"bound is spent, so a stream terminates on one only at exhaustion"
            )


def _check_attemptless(invocation: _Activity, label: str, problems: list[str]) -> None:
    """An outer invocation that finished holds at least one attempt.

    A Transaction Attempt adopts its Model Edition and starts BEFORE the
    boundary is asked to begin, so even a begin failure is an attempt that ran
    and finished `beginFailed`. An invocation that finished with none beneath
    it therefore describes a transaction whose first attempt was never
    reported, and the terminal-attempt rule cannot catch it because there is no
    attempt to disagree with.
    """
    if invocation.kind != _OUTER or invocation.open:
        return
    problems.append(
        f"{label} opens no Transaction Attempt but its invocation reports "
        f"{invocation.finished_payload.get('outcome')!r}; an attempt starts before its "
        f"boundary is asked to begin, so every finished invocation ran at least one — a "
        f"begin failure included, which finishes its attempt beginFailed"
    )


def _check_retried(attempt: _Activity, successor: _Activity, problems: list[str]) -> None:
    """What an attempt that is NOT the last one may have reported.

    Four things end a history: a commit, a failure the classifier refused, a
    rollback that itself failed, and a boundary that never opened. The third is
    the one a retry budget cannot override — the connection's state is unknown,
    so re-executing the closure on it is exactly what must not happen, however
    retriable the failure that triggered the rollback was — and the fourth is
    terminal by rule, because no callback ran that a re-execution could repeat.
    """
    finished = attempt.finished_payload
    outcome = finished.get("outcome")
    if attempt.finished_at is not None and attempt.finished_at > successor.started_at:
        problems.append(
            f"{attempt.label} had not finished when attempt {successor.activity} started; a "
            f"retry re-executes the closure on a new physical attempt, so one attempt of an "
            f"invocation is running at a time"
        )
    if outcome == "committed":
        problems.append(
            f"{attempt.label} committed but is not the last attempt of its invocation; a "
            f"commit ends the invocation, so a terminal stream holds at most one committed "
            f"attempt and it is the final one"
        )
    elif outcome == "rollbackFailed":
        problems.append(
            f"{attempt.label} failed to roll back but attempt {successor.activity} follows it; "
            f"a rollback failure leaves the connection uncertain and never retries, even when "
            f"the failure that triggered it was retry-eligible"
        )
    elif outcome == "beginFailed":
        problems.append(
            f"{attempt.label} never opened its boundary but attempt {successor.activity} "
            f"follows it; a begin failure is terminal by rule, whatever category the error "
            f"carries, because no callback ran that a re-execution could repeat"
        )
    elif finished.get("retryEligible") is not True:
        problems.append(
            f"{attempt.label} records a failure the classifier judged ineligible for retry, "
            f"but attempt {successor.activity} follows it; a non-retriable failure surfaces to "
            f"the caller instead of re-executing the closure"
        )


def _check_terminal_attempt(
    invocation: _Activity, attempts: list[_Activity], label: str, problems: list[str]
) -> None:
    """The invocation's own outcome against the attempt it ended on.

    An Outer Invocation reports what the physical transaction did, and the last
    attempt IS that transaction's last word on it, so the two cannot disagree.
    """
    committed_attempt = attempts[-1].finished_payload.get("outcome") == "committed"
    committed_invocation = invocation.finished_payload.get("outcome") == "committed"
    if committed_attempt != committed_invocation:
        problems.append(
            f"{label} ends on an attempt that "
            f"{'committed' if committed_attempt else 'did not commit'} while its invocation "
            f"reports {invocation.finished_payload.get('outcome')!r}; an Outer Invocation "
            f"reports what the physical transaction did, so it commits exactly when its last "
            f"attempt did"
        )


def _check_statements(calls: list[_Call], space: _StatementSpace, problems: list[str]) -> None:
    """The index space against the calls that name it.

    A call names the statement it ran by index, and omits the index only where
    the space holds none to name. There are two such places, and they are the
    reason this is a claim about the WHOLE record rather than about one call: a
    lane authoring no golden at all — `api-conformance` — where nothing is
    indexed, and the resolving read a keyed write owes, which reaches the
    database and is counted but which the case authors no statement for
    (`m-case-format` "Resolving reads a write owes").

    What keeps that second omission honest is coverage: the indexes the calls do
    name are the whole space, in delivery order, once each. A call omitting an
    index it should have named leaves an authored statement unnamed, and a call
    taking an index that belongs to a later one shifts every index after it, so
    both land here even though each index in isolation is in range. A WRITE call
    is additionally never one of the two omissions — a statement a case authors
    as golden DML is one some write call ran — so it must name one wherever the
    space is non-empty.

    Coverage alone would still admit a record whose calls are the wrong ones:
    one authored UPDATE and one resolving read carrying its index cover the
    space exactly, while the write that ran the UPDATE appears nowhere. So each
    index is additionally owned by a call of the kind its own statement is
    (:func:`_check_statement_kinds`).
    """
    named = [call for call in calls if call.statement is not None]
    for call in named:
        if isinstance(call.statement, int) and not 0 <= call.statement < space.size:
            problems.append(f"{call.label} names statement {call.statement}, but {space.phrase()}")
    if not space.size:
        return
    for call in calls:
        if call.statement is None and call.kind != "read":
            problems.append(
                f"{call.label} names no statement, but {space.phrase()}; a call omits the index "
                f"only where the space holds none to name, and every golden DML statement is one "
                f"a write call ran"
            )
    _check_statement_kinds(named, space, problems)
    indexes = [call.statement for call in named]
    if indexes != list(range(space.size)):
        problems.append(
            f"the record's database calls name statements {indexes}, but {space.phrase()}; the "
            f"space is named in delivery order and once each, so a call that skipped its own "
            f"index or took another's leaves the two orders disagreeing"
        )


def _check_statement_kinds(named: list[_Call], space: _StatementSpace, problems: list[str]) -> None:
    """Each named index against the kind of call its own statement admits.

    A call names the statement IT ran, so a read call cannot own an authored
    ``UPDATE`` and a write call cannot own an authored query. This is what makes
    the resolving-read omission provable rather than merely permitted: the read
    a keyed write owes authors no golden, so a read carrying a DML index is one
    that took the index of the write call that ran it — and that write call is
    then missing from a record coverage alone reports as complete.
    """
    for call in named:
        index = call.statement
        if not isinstance(index, int) or not 0 <= index < space.size:
            continue
        expected = space.kinds[index]
        if expected is None or call.kind == expected:
            continue
        problems.append(
            f"{call.label} is a {call.kind} call naming statement {index}, which "
            f"{space.holder} as {'a query' if expected == 'read' else 'DML'}; a call names the "
            f"statement IT ran, so an index belongs to a call of the kind its own statement is"
        )


def _check_total(calls: int, declared: Any, problems: list[str]) -> None:
    if calls != declared:
        problems.append(
            f"the lifecycle opens {calls} Database Call(s) but the record declares roundTrips "
            f"{declared}; `then.roundTrips` (or the envelope's `observations.roundTrips`) is "
            f"the sole count oracle and the lifecycle counts the same calls, so a record "
            f"authoring both states one number twice"
        )


def _authored_golden_kinds(case: dict[str, Any]) -> tuple[str | None, ...]:
    """The case's FLATTENED authored golden order, statement by statement.

    A call's ``statement`` indexes that order, so both bounding an index and
    judging which call may own it read it here. Goldens are authored case-level
    (``then.statements``), per scenario or coherence step, per conflict attempt,
    or per concurrency-round node — every shape that reaches the database and
    may therefore carry the oracle. A lane authoring none — the
    ``api-conformance`` lane, where a call carries no index at all — yields an
    empty order, and any index is then out of range.
    """
    kinds = _entry_kinds(case.get("then"), "statements")
    when = case.get("when")
    if not isinstance(when, dict):
        return kinds
    for key in ("scenario", "coherence", "attempts"):
        group = when.get(key)
        if isinstance(group, list):
            for entry in group:
                kinds += _entry_kinds(entry, "statements")
    concurrency = when.get("concurrency")
    rounds = concurrency.get("rounds") if isinstance(concurrency, dict) else None
    if isinstance(rounds, list):
        for entry in rounds:
            if isinstance(entry, dict):
                for node in ("A", "B"):
                    kinds += _entry_kinds(entry.get(node), "statements")
    return kinds


def _entry_kinds(holder: Any, key: str) -> tuple[str | None, ...]:
    if not isinstance(holder, dict):
        return ()
    entries = holder.get(key)
    return tuple(_statement_kind(entry) for entry in entries) if isinstance(entries, list) else ()


def _statement_kind(entry: Any) -> str | None:
    """The Database Call kind *entry*'s SQL states, or ``None`` where it states
    none.

    The two sides hold the same evidence in different shapes — a case authors
    its SQL under each dialect it states, an envelope reports one rendered
    string — and the leading keyword is what separates a query a Read call
    issued from the DML a Write Batch call issued. A lead outside that
    vocabulary, or dialects disagreeing about it, yields no claim, so the
    unfamiliar statement is left to the rules that do not need its kind.
    """
    sql = entry.get("sql") if isinstance(entry, dict) else None
    texts = sql.values() if isinstance(sql, dict) else [sql]
    stated = {_LEADING_KIND.get(_leading_keyword(text)) for text in texts if isinstance(text, str)}
    return stated.pop() if len(stated) == 1 else None


def _leading_keyword(sql: str) -> str:
    lead = sql.split(maxsplit=1)
    return lead[0].lower() if lead else ""
