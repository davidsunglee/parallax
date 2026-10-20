# Write Groups run every effect before any insert

A flush executes its Write Plan as Write Groups: consecutive settled writes of
one mutation phase over distinct objects, at most 64 of them, that execute as
one sequence of Planned Steps and complete together. A group lays out every
settled write's effects first and every settled write's inserts after them,
each write's own order kept (`m-unit-work` *Write Group formation*). This
supersedes the part of ADR 0045 that kept a temporal close adjacent to its
successors with no unrelated step between them. A temporal mutation still
expands in place, at its ordered position, and its own steps still keep its
close ahead of its successors; only other objects' steps may now come between.

Executing writes one at a time cost at least one call per object, because
execution batches only contiguous steps. Laying a group out effects-first makes
the effects contiguous for ordered transport and the inserts contiguous for a
grouped insert, so a keyed loop over many objects costs a few calls per group
rather than one or two per object. The layout is chosen once, at settlement,
from the mutation phases ordering already formed, so nothing reads
relationships or recomputes keys at execution. It moves only successors, and
only past other objects' steps: an insert-phase write produces only inserts, so
no plain insert moves behind an effect, and an effect never moves past another
effect. A group spans one mutation phase of one region, so barriers and
removal-dependent reinsertions keep their positions.

The bound limits what a failing insert wastes. Every insert of a group waits
behind every effect of the group, which has already executed and taken its
locks, so the bound keeps that work proportional to 64 objects rather than to
the flush. It is the planner's own constant, separate from execution's
per-call statement and row caps, and correctness does not depend on it: the
attempt is doomed either way.

The accepted cost is failure precedence. Where two objects of one group would
each fail, the one presented first is reported, so a later object's effect
shortfall can precede an earlier object's insert violation, and the two can
differ in retry eligibility. A grouped insert across objects reports its
statement's own error, which can name another violation than its earliest
failing row would alone. Both extend departures `m-execution` already accepted
for ordered transport and grouped temporal openings.

Three alternatives were rejected. Keeping each object's close next to its
successors would leave effects and inserts interleaved, so neither call shape
could batch across objects. Sorting a group by key would order nothing across
groups or transactions, and under Locking it would not prevent the deadlock on
the shared lock's upgrade; a cross-transaction lock-order protocol is separate
work. An unbounded group would let a failing insert waste work, and hold
locks, in proportion to the whole flush.
