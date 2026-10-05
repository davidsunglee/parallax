"""Each `uow` group's fate, and the state a state-graded Scenario claims.

A `uow` label names one held session every step of that label shares, opened
lazily at the group's first step and closed at its own last one: committed, or —
where ``then.units`` states the group ``rolledBack`` — rolled back. A group's
steps need not be contiguous, so two groups may hold two live sessions at once,
each closing at its own boundary. A rolled-back group that states a
``flushFailure`` is one its own flush ended, and the golden that flush executed is
graded for that failure: exactly one statement addressing the object it names
affected no row, gated as its Shortfall says.

A state-graded Scenario carries no golden SQL, so nothing of it executes here.
What is graded instead is that the case is consistent with the rows it starts
from, read back once provisioning is done — never that SQL produces its final
rows, which each language runner's own real-database run against the authored
rows is. The proofs read the document and those rows alone:

- **frame** — a table no committed predicate submission writes keeps every row
  of a key no committed submission names exactly as it started, which is also
  what a rolled-back group leaves of the keys only it names;
- **milestones** — every row of a temporal table is a starting row, unchanged or
  closed at a committed group's instant, or a row such a group opened, current
  or closed by a later one; and every starting row survives;
- **overlap** — no two current rows of one key overlap in Valid Time, and a
  Transaction-Time-Only key has at most one;
- **refusals** — each declared refusal has the structure its code needs: an
  already-claimed submission meets an earlier pending write of its object in its
  group, and an inserted-object refusal is a caller-addressed write of an object
  the group inserted earlier;
- **flush failures** — the object a failure names is one the failing flush
  writes, by a submission still pending when it began that the Shortfall can
  arise from.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..case import Case, Entity
from ..case_assertions import CaseFailure, rows_equal, write_value_equal
from ..temporality import temporal_axes
from ..write_plan import (
    has_temporal_gate,
    has_version_gate,
    statement_object,
    version_column,
)
from .compile import (
    CompiledScenario,
    FlushFailure,
    Submission,
    UnitFate,
    _RowPublishingStep,
)

__all__ = [
    "GroupSession",
    "assert_settled_state",
    "finish_group",
    "group_sessions",
]


@dataclass
class GroupSession:
    """One group's held session and the writes it executed.

    The session is ``None`` until the group's FIRST step lazily opens it and again
    once the group has closed. ``executed`` accumulates each ``(step, statement,
    binds, affected)`` the group's writes produced, which is what a flush failure
    is graded on.
    """

    fate: UnitFate
    session: Any = None
    executed: list[tuple[int, str, list[Any], int]] = field(default_factory=list)


def group_sessions(scenario: CompiledScenario) -> dict[str, GroupSession]:
    """Each declared `uow` label's session, keyed by label."""
    return {label: GroupSession(fate) for label, fate in scenario.units.items()}


def finish_group(
    case: Case,
    index: int,
    label: str | None,
    sessions: Mapping[str, GroupSession],
    dialect: str,
) -> None:
    """Close a group's held session when *index* is its LAST step: commit it, or
    roll it back as its fate states, first grading the flush failure that rolled
    it back where it states one. A no-op for any other step."""
    if label is None:
        return
    group = sessions[label]
    fate = group.fate
    if index != fate.last_step:
        return
    if fate.rolls_back:
        if fate.flush_failure is not None:
            _assert_flush_failure(case, fate.flush_failure, group.executed, dialect)
        group.session.rollback()
    else:
        group.session.commit()
    # The group's own steps are exhausted, so no later step ever looks the session
    # up again — cleared anyway, so a (structurally impossible) later step of the
    # SAME label would open a FRESH session rather than reuse a closed one.
    group.session = None


def _assert_flush_failure(
    case: Case,
    failure: FlushFailure,
    executed: list[tuple[int, str, list[Any], int]],
    dialect: str,
) -> None:
    """Assert the failing flush's golden carries the shortfall it reports.

    Exactly one statement of the write steps that flush ran, addressing the
    object the failure names, affected no row; it is gated where the Shortfall is
    a gate's — an optimistic conflict or a failed precondition, both of which only
    the Optimistic strategy gates — and ungated otherwise. A rollback that merely
    discarded writes that all succeeded therefore fails the case rather than
    passing on the rollback.

    Failures here are authored as local detail: this runs inside the step boundary
    that names the Scenario position.
    """
    entity = failure.entity
    key = _identity_value(entity, failure.key)
    short = [
        statement
        for step, statement, binds, affected in executed
        if step in failure.flushed
        and affected == 0
        and _addresses(statement, binds, dialect, entity, key)
    ]
    if len(short) != 1:
        raise CaseFailure(
            f"the group's flush failure names {entity.name} {dict(failure.key)!r}, so exactly "
            f"one statement of the failing flush addressing it MUST have affected no row; "
            f"found {len(short)}."
        )
    gated = _gated(short[0], entity, dialect)
    if failure.shortfall in ("optimisticConflict", "failedPrecondition"):
        if case.concurrency_mode != "optimistic" or not gated:
            raise CaseFailure(
                f"the group's flush failure is {failure.shortfall!r}, a gate's shortfall, but "
                f"the statement that fell short is {'gated' if gated else 'ungated'} under "
                f"`concurrency: {case.concurrency_mode}`."
            )
    elif gated:
        raise CaseFailure(
            f"the group's flush failure is {failure.shortfall!r}, an ungated shortfall, but "
            f"the statement that fell short is gated."
        )


def _addresses(statement: str, binds: list[Any], dialect: str, entity: Entity, key: Any) -> bool:
    address = statement_object(statement, binds, dialect)
    return (
        address is not None
        and address.names_table(entity.table)
        and address.names_key_column(entity.identity_column)
        and write_value_equal(address.key, key)
    )


def _gated(statement: str, entity: Entity, dialect: str) -> bool:
    axes = {axis.dimension: axis for axis in temporal_axes(entity.runtime_facts)}
    tx_axis = axes.get("transaction-time")
    if tx_axis is not None:
        return has_temporal_gate(statement, tx_axis.start.column, dialect)
    column = version_column(entity)
    return column is not None and has_version_gate(statement, column, dialect)


def _identity_value(entity: Entity, key: Mapping[str, Any]) -> Any:
    """The value of *entity*'s primary key in an attribute-named *key*."""
    for attribute in entity.attributes:
        if attribute.get("primaryKey"):
            return key.get(attribute["name"])
    return next(iter(key.values()), None)


# --- the state a state-graded Scenario claims -------------------------------------


def assert_settled_state(
    scenario: CompiledScenario, starting: Mapping[str, list[dict[str, Any]]]
) -> None:
    """Assert a state-graded Scenario is consistent with the rows it starts from.

    *starting* holds every table ``then.tableState`` states, read back after
    provisioning.
    """
    case = scenario.case
    submissions = scenario.submissions()
    for submission in submissions:
        if submission.refusal is not None:
            _assert_refusal(scenario, submission)
    for fate in scenario.units.values():
        if fate.flush_failure is not None:
            _assert_failure_subject(scenario, fate, fate.flush_failure)
    group_of = {step.index: step.group for step in scenario.steps}
    committed = [
        submission
        for submission in submissions
        if submission.refusal is None
        and not scenario.units[_group(group_of, submission)].rolls_back
    ]
    instants = sorted(
        {
            _instant(fate.instant)
            for fate in scenario.units.values()
            if not fate.rolls_back and fate.instant is not None
        }
    )
    for table, final in case.expected_table_state.items():
        entity = _table_entity(case, table)
        before = starting[table]
        _assert_frame(case, table, entity, before, final, committed, submissions)
        axes = {axis.dimension: axis for axis in temporal_axes(entity.runtime_facts)}
        if "transaction-time" in axes:
            _assert_milestones(case, table, axes, before, final, instants)
            _assert_no_overlap(case, table, entity, axes, final)


def _group(group_of: Mapping[int, str | None], submission: Submission) -> str:
    label = group_of[submission.step]
    assert label is not None  # a submission is an entry of a grouped write step
    return label


def _table_entity(case: Case, table: str) -> Entity:
    """The concrete Entity whose rows *table* stores; a shared table's members
    share its key and axes."""
    for entity in case.model.entities:
        if not entity.is_abstract and entity.table == table:
            return entity
    raise CaseFailure(
        f"{case.path.name}: then.tableState names table {table!r}, which no entity maps."
    )


def _assert_frame(
    case: Case,
    table: str,
    entity: Entity,
    before: list[dict[str, Any]],
    final: list[dict[str, Any]],
    committed: list[Submission],
    submissions: tuple[Submission, ...],
) -> None:
    if any(
        submission.kind == "predicate" and _predicate_table(case, submission) == table
        for submission in committed
    ):
        return
    column = entity.identity_column
    named = {
        _identity(_identity_value(entity, submission.key))
        for submission in committed
        if submission.entity is not None
        and submission.entity.table == table
        and submission.key is not None
    }
    abandoned = {
        _identity(_identity_value(entity, submission.key))
        for submission in submissions
        if submission.entity is not None
        and submission.entity.table == table
        and submission.key is not None
    } - named
    for identity in {_identity(row.get(column)) for row in (*before, *final)} - named:
        kept = [row for row in final if _identity(row.get(column)) == identity]
        started = [row for row in before if _identity(row.get(column)) == identity]
        if not rows_equal(kept, started, case.tolerance):
            reason = (
                "only rolled-back or refused submissions name it, so it keeps its starting rows"
                if identity in abandoned
                else "no committed submission names it"
            )
            raise CaseFailure(
                f"{case.path.name}: then.tableState.{table} changes key {identity}, but "
                f"{reason}.\n  starting: {started!r}\n  stated:   {kept!r}"
            )


def _predicate_table(case: Case, submission: Submission) -> str:
    target = submission.entry.get("target") or {}
    return case.model.entity(str(target.get("entity", ""))).table


def _assert_milestones(
    case: Case,
    table: str,
    axes: Mapping[str, Any],
    before: list[dict[str, Any]],
    final: list[dict[str, Any]],
    instants: Sequence[tuple[int, dt.datetime]],
) -> None:
    """Every stated row is a starting row, unchanged or closed at a committed
    group's instant, or a row a committed group opened; every starting row
    survives so. A Transaction-Time history is never rewritten."""
    tx = axes["transaction-time"]
    start, end = tx.start.column, tx.end.column
    survivors = list(before)
    for row in final:
        match = next(
            (
                position
                for position, origin in enumerate(survivors)
                if _survives_as(case, origin, row, end, instants)
            ),
            None,
        )
        if match is not None:
            survivors.pop(match)
            continue
        opened = _instant(row.get(start))
        closed = _instant(row.get(end))
        if opened in instants and (closed == _OPEN or (closed in instants and opened < closed)):
            continue
        raise CaseFailure(
            f"{case.path.name}: then.tableState.{table} states {row!r}, which is neither a "
            f"starting row, unchanged or closed at a committed group's instant, nor a row a "
            f"committed group opened."
        )
    if survivors:
        raise CaseFailure(
            f"{case.path.name}: then.tableState.{table} drops the starting row(s) "
            f"{survivors!r}; a committed milestone is closed, never removed."
        )


def _survives_as(
    case: Case,
    origin: Mapping[str, Any],
    row: Mapping[str, Any],
    end: str,
    instants: Sequence[tuple[int, dt.datetime]],
) -> bool:
    if rows_equal([dict(row)], [dict(origin)], case.tolerance):
        return True
    if _instant(origin.get(end)) != _OPEN or _instant(row.get(end)) not in instants:
        return False
    return rows_equal(
        [{name: value for name, value in row.items() if name != end}],
        [{name: value for name, value in origin.items() if name != end}],
        case.tolerance,
    )


def _assert_no_overlap(
    case: Case,
    table: str,
    entity: Entity,
    axes: Mapping[str, Any],
    final: list[dict[str, Any]],
) -> None:
    tx_end = axes["transaction-time"].end.column
    valid = axes.get("valid-time")
    current: dict[str, list[dict[str, Any]]] = {}
    for row in final:
        if _instant(row.get(tx_end)) == _OPEN:
            current.setdefault(_identity(row.get(entity.identity_column)), []).append(row)
    for identity, rows in current.items():
        if valid is None:
            if len(rows) > 1:
                raise CaseFailure(
                    f"{case.path.name}: then.tableState.{table} states {len(rows)} current "
                    f"rows of key {identity}; a Transaction-Time-Only key has one."
                )
            continue
        spans = sorted(
            (_instant(row.get(valid.start.column)), _instant(row.get(valid.end.column)))
            for row in rows
        )
        for (_, earlier_end), (later_start, _) in zip(spans, spans[1:], strict=False):
            if later_start < earlier_end:
                raise CaseFailure(
                    f"{case.path.name}: then.tableState.{table} states current rows of key "
                    f"{identity} whose Valid-Time intervals overlap."
                )


def _assert_refusal(scenario: CompiledScenario, submission: Submission) -> None:
    case = scenario.case
    earlier = _earlier_in_group(scenario, submission)
    if submission.refusal == "write-evidence-already-claimed":
        pending = [
            other
            for other in earlier
            if _names_same_object(other, submission) and _pending_at(scenario, other, submission)
        ]
        if not pending:
            raise CaseFailure(
                f"{case.path.name}: {submission.pointer} is refused as already claimed, but no "
                f"earlier write of its object is pending in its group — a claim is held only by "
                f"pending work."
            )
    elif submission.refusal == "write-evidence-inserted":
        inserted = [
            other for other in earlier if other.inserts and _names_same_object(other, submission)
        ]
        if submission.kind != "target" or not inserted:
            raise CaseFailure(
                f"{case.path.name}: {submission.pointer} is refused as a write of an inserted "
                f"object, which only a caller-addressed write of an object its group inserted "
                f"earlier is."
            )


def _earlier_in_group(scenario: CompiledScenario, submission: Submission) -> list[Submission]:
    group_of = {step.index: step.group for step in scenario.steps}
    label = group_of[submission.step]
    return [
        other
        for other in scenario.submissions()
        if other.refusal is None
        and group_of[other.step] == label
        and (other.step, other.position) < (submission.step, submission.position)
    ]


def _names_same_object(first: Submission, second: Submission) -> bool:
    return (
        second.entity is not None
        and second.key is not None
        and first.names(second.entity, second.key)
    )


def _pending_at(scenario: CompiledScenario, earlier: Submission, later: Submission) -> bool:
    """Whether *earlier* is still pending when *later* is submitted: no find of
    their group runs between them, since a find flushes what is pending."""
    group_of = {step.index: step.group for step in scenario.steps}
    label = group_of[later.step]
    return not any(
        isinstance(step, _RowPublishingStep)
        and step.group == label
        and earlier.step < step.index < later.step
        for step in scenario.steps
    )


def _assert_failure_subject(
    scenario: CompiledScenario, fate: UnitFate, failure: FlushFailure
) -> None:
    case = scenario.case
    writers = [
        submission
        for submission in scenario.submissions()
        if submission.refusal is None
        and submission.step in failure.flushed
        and submission.names(failure.entity, failure.key)
    ]
    if failure.shortfall == "failedPrecondition":
        able = [submission for submission in writers if submission.kind == "target"]
    elif failure.shortfall == "missingTarget":
        able = [submission for submission in writers if not submission.inserts]
    else:
        able = [
            submission
            for submission in writers
            if submission.kind == "keyed" and not submission.inserts
        ]
    if not able:
        raise CaseFailure(
            f"{case.path.name}: then.units.{fate.label}.flushFailure names "
            f"{failure.entity.name} {dict(failure.key)!r} with {failure.shortfall!r}, but no "
            f"submission pending at that flush writes it so that it could fall short that way."
        )


def _identity(value: Any) -> str:
    return str(value)


_OPEN: tuple[int, dt.datetime] = (1, dt.datetime.min.replace(tzinfo=dt.UTC))


def _instant(value: Any) -> tuple[int, dt.datetime]:
    """An instant in comparable form; ``infinity`` and absence are the open end,
    later than every instant."""
    if value is None or value == "infinity":
        return _OPEN
    if isinstance(value, dt.datetime):
        return (0, value if value.tzinfo is not None else value.replace(tzinfo=dt.UTC))
    return (0, dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")))
