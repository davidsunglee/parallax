"""Every accepted Object Query observation the compatibility corpus asserts.

One accepted read is one operation: it validates what its Object Query and golden
SQL claim, runs the golden statements and the independent ``referenceSql`` oracle
against the executor it was handed, materializes the physical rows into the result
the case authored, and compares every authored observable. It either returns
without a value or raises :class:`..case_assertions.CaseFailure` naming the case —
there is no partial pass and no result to inspect.

A caller states a case and an executor and nothing else. Eager versus streamed
delivery, Includes, Temporal Selection, Snapshot Graph assembly, and milestone
partitioning are decided inside, because each of them is a property of the read
the case already authored rather than a choice orchestration gets to make.

A Unit Work Scenario states its reads as steps, so its caller states an index and
the reader that step's lifecycle selected, and nothing else again. Query,
relationship load, reuse, and retained access stay behaviorally distinct inside,
and what a step published is retained under its index for the steps naming it —
privately, so no observation crosses back out.

What stays outside: case admission and shape routing, rejected-case adjudication,
provisioning, fixtures, Unit Work Scenario step order and transaction lifecycle,
writes, and Scenario-wide accounting.
"""

from __future__ import annotations

from .executor import ReadExecutor
from .ordinary import assert_case_read
from .scenario import ScenarioReads

__all__ = ["ReadExecutor", "ScenarioReads", "assert_case_read"]
