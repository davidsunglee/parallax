"""The step driver with grouped temporal openings selected, for proofs that
reach the attempt's grouped opening operation through whole flushes.

Execution's own driver lowers every opening alone. A proof needing a whole
flush around grouped openings — unit reporting, the attempt's rollback-only
state, the failure and retry verdict a transaction reports — substitutes this
driver for one test: each run of compatible openings goes through
``Attempt._run_openings``, and every other step runs alone exactly as execution
runs it on a connection without ordered write transport.
"""

from __future__ import annotations

import pytest

from parallax.core.execution._attempt import Attempt
from parallax.core.execution._write_lowering import LoweringCursor
from parallax.core.write_plan.plan import WriteStepView

__all__ = ["select_grouped_openings"]


def select_grouped_openings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Have every attempt realize its steps through :func:`_grouping` until
    ``monkeypatch`` undoes it."""
    monkeypatch.setattr(Attempt, "_execute_steps", _grouping)


def _grouping(attempt: Attempt, steps: WriteStepView, /, *, allocates: bool) -> tuple[object, ...]:
    assert not allocates, "a grouped-opening proof runs no unit allocating a key"
    cursor = LoweringCursor(
        steps,
        attempt._write.planner.payloads,  # pyright: ignore[reportPrivateUsage] - the planner's own preparer, as execution uses it
        attempt.model.meta,
        attempt._connection.dialect,  # pyright: ignore[reportPrivateUsage] - the attempt's own dialect
    )
    step = cursor.take()
    while step is not None:
        first = cursor.opening(step)
        if first is not None:
            step = attempt._run_openings(first, cursor)  # pyright: ignore[reportPrivateUsage] - the operation under proof
            continue
        attempt._run(step, cursor.lowered(step))  # pyright: ignore[reportPrivateUsage] - a step running alone
        step = cursor.take()
    return ()
