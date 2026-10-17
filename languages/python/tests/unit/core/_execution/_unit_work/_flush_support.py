"""A unit of work's flush as simulated step execution runs it: the kind of
each statement a span lowered to, and the execution of each span observed, or
failed, as the flush reaches it."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Final

from parallax.conformance._simulated_write_steps import SimulatedWriteSteps
from parallax.core.sql_gen import LoweredStatement
from parallax.core.write_plan.plan import WriteStepView

__all__ = ["ObservedSteps", "statement_kinds"]

# A close sets the Transaction-Time end alone, which also addresses the
# current row it ends.
_CLOSE: Final = re.compile(r"update \S+ set (\w+) = \? where .*\b\1 = \?")


def statement_kinds(statements: Iterable[LoweredStatement]) -> list[str]:
    """What each statement does, in order: ``insert``, ``delete``, ``close``,
    ``guard`` for an update assigning nothing, or ``update``."""
    kinds: list[str] = []
    for statement in statements:
        sql = statement.sql
        verb = sql.split(" ", 1)[0]
        if verb != "update":
            kinds.append(verb)
        elif "= ?" not in sql.split(" where ", 1)[0]:
            kinds.append("guard")
        else:
            kinds.append("close" if _CLOSE.match(sql) else "update")
    return kinds


@dataclass(slots=True)
class ObservedSteps:
    """``simulated`` executing each span a flush hands it, after ``observe``
    is called with the span's position among those handed so far; the span
    at ``failing`` raises ``failure`` instead of executing."""

    simulated: SimulatedWriteSteps
    observe: Callable[[int], object] | None = None
    failing: int | None = None
    failure: BaseException | None = None
    spans: int = 0

    def __call__(self, steps: WriteStepView, /, *, allocates: bool) -> tuple[object, ...]:
        position = self.spans
        self.spans = position + 1
        if self.observe is not None:
            self.observe(position)
        if position == self.failing and self.failure is not None:
            raise self.failure
        return self.simulated(steps, allocates=allocates)
