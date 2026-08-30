"""One Unit Work group's coordinated lifecycle.

A `uow` label names one held session every step of that label shares, opened
lazily at the group's first step and closed at its own declared last one — by a
commit, or, when any of its write steps declares ``rollback: true``, by the
rollback the whole group shares. A group's steps need not be contiguous, so two
groups may hold two live sessions at once, each closing at its own boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..case import Case
from ..case_assertions import CaseFailure
from ..write_plan import has_version_gate, version_column
from .compile import CompiledScenario, _GroupedWrite

__all__ = ["UowGroupState", "assert_conflict_abort", "finish_group", "group_states"]


@dataclass
class UowGroupState:
    """One group's held session, its fate, its executed writes, and its boundary.

    The session is ``None`` until the group's FIRST step lazily opens it and again
    once the group has closed. ``executed`` accumulates the ``(statement,
    affected)`` pairs the group's writes produced, which is the conflict-abort
    proof a doomed group is graded on.
    """

    doomed: bool
    last_step: int
    session: Any = None
    executed: list[tuple[str, int]] = field(default_factory=list)


def group_states(scenario: CompiledScenario) -> dict[str, UowGroupState]:
    """Each declared `uow` label's state, keyed by label.

    A group is DOOMED when at least one of its OWN write steps declares
    ``rollback: true`` — the WHOLE group is then the doomed unit of work
    (`m-case-format` scenario `uow` grouping), not just that one step; a later step
    in the SAME group (a find re-issued to force-flush a pending write) still runs
    inside the still-open transaction before the eventual rollback.
    """
    states: dict[str, UowGroupState] = {}
    for step in scenario.steps:
        if step.group is None:
            continue
        state = states.setdefault(step.group, UowGroupState(doomed=False, last_step=step.index))
        state.last_step = step.index
        if isinstance(step, _GroupedWrite) and step.rolls_back:
            state.doomed = True
    return states


def finish_group(
    case: Case,
    index: int,
    label: str | None,
    states: dict[str, UowGroupState],
    dialect: str,
) -> None:
    """Close a group's held session when *index* is its declared LAST step.

    COMMIT is the default; a doomed group asserts the conflict-abort proof on its
    own accumulated executed writes — exactly as the ungrouped single-step
    rollback does for one step — and ROLLS BACK instead. A no-op for a step whose
    group has not yet reached its last step, or for an ungrouped step.
    """
    if label is None:
        return
    state = states[label]
    if index != state.last_step:
        return
    if state.doomed:
        # A group that declares `then.affectedRows` is a conflict-abort group
        # (m-opt-lock + m-unit-work): the UoW aborts BECAUSE a version-gated
        # write conflicted. Assert the conflict was actually DETECTED before
        # rolling back, so a rollback that merely discarded a NON-conflicting
        # write fails the case rather than passing on a vacuous abort.
        if case.expected_affected_rows is not None and state.executed:
            assert_conflict_abort(case, state.executed, dialect)
        state.session.rollback()
    else:
        state.session.commit()
    # The group's own steps are exhausted, so no later step ever looks the session
    # up again — cleared anyway, so a (structurally impossible) later step of the
    # SAME label would open a FRESH session rather than reuse a closed one.
    state.session = None


def assert_conflict_abort(case: Case, executed: list[tuple[str, int]], dialect: str) -> None:
    """Assert an aborted step aborted BECAUSE a versioned write conflicted.

    A scenario that declares ``then.affectedRows`` (the m-opt-lock conflict signal) is
    a conflict-abort case (m-opt-lock + m-unit-work): the rollback must be the
    CONSEQUENCE of a genuinely detected optimistic-lock conflict, not a vacuous abort.
    The step's version-gated write (identified by its ``and <version> = ?`` gate) MUST
    have affected ``then.affectedRows`` rows — ``0`` for a stale-version gate that
    matched no row (``updatedRows != 1``). A gated write that unexpectedly affects 1
    row is NO conflict, so the case fails rather than passing on the rollback alone.

    Failures here are authored as local detail: this runs inside the step boundary
    that names the Scenario position (:func:`.report.reported_against`).
    """
    expected = case.expected_affected_rows
    if case.concurrency_mode != "optimistic":
        raise CaseFailure(
            "declares then.affectedRows (an optimistic-lock conflict) but the unit of work "
            "is not `concurrency: optimistic` — a conflict abort requires the version gate."
        )
    if expected == 1:
        raise CaseFailure(
            "declares then.affectedRows 1, which is NOT a conflict — `updatedRows != 1` is "
            "the conflict signal. A conflict-abort scenario MUST declare a != 1 count "
            "(0 for a stale-version gate)."
        )
    # A scenario queries a single entity (cache / identity over one type), so the
    # version column is the model root's.
    version_col = version_column(case.model.root_entity)
    if version_col is None:
        raise CaseFailure(
            "declares a conflict abort but the entity carries no optimistic-lock version "
            "column to gate on."
        )
    gated = [
        (sql, affected) for sql, affected in executed if has_version_gate(sql, version_col, dialect)
    ]
    if len(gated) != 1:
        raise CaseFailure(
            f"conflict-abort step MUST list exactly one version-gated write (the conflicting "
            f"statement), found {len(gated)}."
        )
    _sql, affected = gated[0]
    if affected != expected:
        raise CaseFailure(
            f"gated versioned write affected {affected} row(s) but then.affectedRows is "
            f"{expected}. The UoW abort MUST be a CONSEQUENCE of a detected optimistic-lock "
            f"conflict (`updatedRows != 1`); a gated write affecting 1 row is NO conflict."
        )
