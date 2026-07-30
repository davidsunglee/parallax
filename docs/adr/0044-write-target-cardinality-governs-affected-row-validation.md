# Write target cardinality governs affected-row validation

Every non-insert Planned Write validates affected rows according to its Write
Target rather than according to whether optimistic locking happens to apply. A
Key Target update or delete expects exactly its nonempty distinct-key count; a
Milestone Target close expects exactly one row; and a Predicate Write Target
accepts any count, including zero. Inserts retain their database constraint and
execution contract rather than using existing-target cardinality.

A shortfall is classified by the write's already-decided concurrency semantics:
a gated miss is an Optimistic Lock Conflict, an ungated
observation-requiring miss is a Stale Write, and a remaining keyed shortfall is
a non-retriable Missing Target. An excess is always non-retriable Cardinality
Corruption, never an optimistic conflict eligible for retry. Target cardinality
and concurrency gating are therefore orthogonal facts in the Write Plan. Each
non-insert step carries the resolved policy as
`AnyCount | ExactCount(expected, on_shortfall)`, so lowering does not
reconstruct it from the target and gate. The excess failure is invariant and is
not repeated in the policy; inserts carry no affected-row policy. Unit Work's
single affected-row enforcer consumes this policy and the adapter-reported
count; lowering and adapters do not interpret the result.

Affected-row attribution constrains execution batching. Multiple Exact Count
logical steps may share one driver batch only when the adapter returns one
count aligned to each logical step, so Unit Work can enforce and identify each
step independently. An aggregate count is sufficient for one multi-key Planned
Write because that complete Key Target owns one expectation. An
aggregate-only backend must execute distinct Exact Count steps separately,
although it may still reuse prepared statements and stream binds.

The previous behavior attached an affected-row expectation only when a keyed
write carried a version observation, allowing an unversioned keyed update or
delete of a missing row to succeed silently and classifying every versioned or
temporal mismatch alike. Reladomo provides the useful prior-art distinction
between a missing optimistic target and an impossible multi-row singleton
result. Its JDBC batch path checks the returned count array against individual
operations, while its set-based multi-update can attribute an aggregate
shortfall only to the candidate group. Parallax adopts the invariant
consistently and preserves exact target attribution rather than copying
historical exceptions.
