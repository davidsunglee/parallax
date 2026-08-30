"""One Unit Work Scenario, graded whole.

One Scenario is one operation: a caller states a case and a provider and nothing
else. It either returns without a value or raises
:class:`..case_assertions.CaseFailure` naming the case path — there is no partial
pass and no result to inspect. A failure a step is answerable for names that
step's authored position exactly once; a defect of the Scenario as a whole — a
case declaring no steps at all, a case-level round-trip total disagreeing with
its steps' — names the case alone, because there is no one step it belongs to. A
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
equivalent-encoding checks, accepted Object Query semantics, Write Plan grading,
and the case-authoring rules :mod:`..schema_validate` asks of every case in the
corpus before any executor runs — which find a settling write may name, and
whether a step's dialect-keyed maps cover its own golden. Those hold whatever
lane runs the case, rather than only where this operation is reached.

**The order defects surface in.** A Scenario is graded in four phases, and the
first one to refuse is the one reported:

1. the caller's own shared checks — case shape, serialization, equivalent
   encodings — before this operation is reached at all;
2. compilation, which is dialect-free and therefore runs on every dialect: what
   kind each step is, which earlier steps it names, which group it joins, and
   which golden entries it lists are read here, and the rules a step's own
   reading settles — a Scenario with no steps, an ``on`` naming something other
   than an earlier step, a boundary action claiming a row observable — refuse
   here, at zero database calls. Which steps a read may reference, and whether
   one is a read at all, are still adjudicated by the read oracle during
   execution;
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
