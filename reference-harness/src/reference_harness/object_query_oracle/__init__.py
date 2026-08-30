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

A Unit Work Scenario's reads are graded here too, but not through this interface.
:mod:`..unit_work_scenario` owns a Scenario whole and hands one step at a time to
:class:`.scenario.ScenarioReads`, which is package-private: it is offered under no
name here, and ``unit_work_scenario/reads.py`` is its only importer. A step index
and a reader cross that seam and nothing comes back — query, relationship load,
reuse, and retained access stay behaviorally distinct inside, and what a step
published is retained under its index for the steps naming it.

What stays outside: case admission and shape routing, rejected-case adjudication,
provisioning, fixtures, Unit Work Scenario step interpretation, step order and
transaction lifecycle, writes, and Scenario-wide accounting.
"""

from __future__ import annotations

from .executor import ReadExecutor
from .ordinary import assert_case_read

__all__ = ["ReadExecutor", "assert_case_read"]
