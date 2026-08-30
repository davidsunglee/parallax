"""One Unit Work Scenario, graded whole.

One Scenario is one operation: a caller states a case and a provider and nothing
else. It either returns without a value or raises
:class:`..case_assertions.CaseFailure` naming the case path and the authored step
position exactly once — there is no partial pass and no result to inspect. A
native database-driver exception is not an authored failure and arrives
unchanged.

Step interpretation, ordered semantic refusal, golden-SQL normalization,
round-trip and statement accounting, write settlement against a named find,
provisioning and ``given.apply`` at the Scenario-defined point, Unit Work
grouping, transaction lifecycle, reader selection, publication sequencing, and
conflict-abort adjudication are all decided inside, because each is a property of
the Scenario the case already authored rather than a choice orchestration gets to
make.

What stays outside: shared case-shape routing, serialization and
equivalent-encoding checks, accepted Object Query semantics, and Write Plan
grading.

**The order defects surface in.** A Scenario is graded in four phases, and the
first one to refuse is the one reported:

1. the caller's own shared checks — case shape, serialization, equivalent
   encodings — before this operation is reached at all;
2. compilation, which is dialect-free and therefore runs on every dialect: a
   malformed topology is refused here, at zero database calls;
3. judgement, which reads golden SQL and therefore runs only where the executing
   dialect carries one;
4. execution, which is the first phase to touch a database.

That ordering is part of the interface rather than an accident of call order: a
case broken in two places reports its serialization or encoding defect ahead of
its Scenario-structural one, and a Scenario-structural defect ahead of a
dialect-keyed one. It is stated here and pinned by test rather than left to be
rediscovered.
"""

from .assertion import assert_unit_work_scenario

__all__ = ["assert_unit_work_scenario"]
