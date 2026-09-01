"""Running a compiled Scenario's steps against a provisioned database, in order.

The loop owns the Scenario, not its reads. Each step executes on the reader or
connection its own lifecycle selected — a grouped step on its group's held
session, an ungrouped one on the provider's autocommit connection — and a group
closes at its own declared last step. What a read then observes is
:mod:`.reads`'.

A step carrying the OPTIONAL `uow` grouping key (`m-case-format`) executes on a
HELD session shared with every other step of the SAME label: a grouped write
applies through the session (never committed per-step) and a grouped find reads
THROUGH the session (read-your-own-writes, mid-transaction). Two groups MAY
interleave (non-contiguous in authored order): each group's own session, once
opened, stays open across the OTHER group's steps in between, closing only at ITS
OWN last step. An UNGROUPED step keeps exactly a single-step boundary — a
committed write applies on the provider's autocommit connection, a rolled-back
write opens its OWN single-step session, and a find reads on the autocommit
connection.
"""

from __future__ import annotations

import contextlib
from typing import Any

from .._case_execution import CaseExecution
from ..providers import DatabaseProvider
from .compile import (
    CompiledScenario,
    _BoundaryAction,
    _GroupedWrite,
    _Read,
    _UngroupedWrite,
    _UnresolvedList,
)
from .groups import UowGroupState, assert_conflict_abort, finish_group, group_states
from .reads import ScenarioReads
from .report import reported_against

__all__ = ["execute_scenario"]


def execute_scenario(scenario: CompiledScenario, db: DatabaseProvider) -> None:
    """Execute *scenario*'s steps and assert what each of them observes."""
    case = scenario.case
    execution = CaseExecution(case, db)
    dialect = execution.dialect
    states = group_states(scenario)
    reads = ScenarioReads(case)

    # One stack for the whole Scenario, so every session opened during it is
    # CLOSED on return or on raise. Whether each one committed or rolled back was
    # decided earlier and per group, at that group's own last step.
    with contextlib.ExitStack() as stack:
        for step in scenario.steps:
            state = states.get(step.group) if step.group is not None else None
            session: Any = None
            if state is not None:
                if state.session is None:
                    state.session = stack.enter_context(execution.open_session())
                session = state.session

            with reported_against(case, step.index):
                match step:
                    case _GroupedWrite():
                        assert state is not None  # a grouped step always has a state
                        _apply_grouped_write(step, state, session, dialect)
                    case _UngroupedWrite():
                        _apply_ungrouped_write(scenario, step, execution, dialect)
                    case _BoundaryAction():
                        _apply_boundary_action(step, execution, dialect)
                    case _Read():
                        reads.assert_step(step.index, session if session is not None else execution)
                    case _UnresolvedList():
                        pass
                finish_group(case, step.index, step.group, states, dialect)


def _apply_grouped_write(
    step: _GroupedWrite,
    state: UowGroupState,
    session: CaseExecution,
    dialect: str,
) -> None:
    """Apply a grouped write on the group's own held session.

    The GROUP commits or rolls back as ONE unit at its last step
    (:func:`.groups.finish_group`), never this step alone, so what the step
    contributes is the executed statements the group's fate is graded on.
    """
    for statement, binds in step.statements.pairs(dialect):
        state.executed.append((statement, session.execute(statement, binds)))


def _apply_ungrouped_write(
    scenario: CompiledScenario,
    step: _UngroupedWrite,
    execution: CaseExecution,
    dialect: str,
) -> None:
    """Apply a write that is its own unit of work.

    A ROLLED-BACK one applies each DML statement inside a manual-commit session
    and then discards it: the write lands in the atomic scope the abort discards,
    so a later find MUST re-resolve and observe the ORIGINAL rows, never the
    aborted write. A COMMITTED one applies on the provider's autocommit connection
    (read-your-own-writes / cache invalidation) and captures no rows; a later find
    observes the committed state.
    """
    pairs = step.statements.pairs(dialect)
    if not step.rolls_back:
        for statement, binds in pairs:
            execution.execute(statement, binds)
        return
    with execution.open_session() as session:
        executed: list[tuple[str, int]] = []
        for statement, binds in pairs:
            executed.append((statement, session.execute(statement, binds)))
        # The SAME conflict-abort reasoning a doomed group is closed under
        # (:func:`.groups.finish_group`) — the ungrouped, single-step form.
        if scenario.case.expected_affected_rows is not None:
            assert_conflict_abort(scenario.case, executed, dialect)
        session.rollback()


def _apply_boundary_action(step: _BoundaryAction, execution: CaseExecution, dialect: str) -> None:
    """Execute a non-read-verb action step's golden DML.

    A `flush` / `mergeBack` / `commit` commits its buffered statements on the unit
    of work's connection, and a `mutate` / `abort` / `detachCopy` commits whatever
    golden DML it authors (a Valid-Time-past correction's split write); none of
    them observes rows, and the observables they may declare are adapter-delegated
    — validated by the schema, graded by each language's API Conformance Suite —
    so the wire harness runs the DML and nothing else.

    Always the provider's autocommit connection: the schema forbids `uow` on an
    action step, because it routes through the lifecycle-object engine path, which
    never observes grouping. Whether its `on` names real earlier steps, and that it
    claims no row observable, were both decided at compile time.
    """
    for statement, binds in step.statements.pairs(dialect):
        execution.execute(statement, binds)
