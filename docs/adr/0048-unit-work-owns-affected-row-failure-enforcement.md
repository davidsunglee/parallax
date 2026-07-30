# Unit Work owns affected-row failure enforcement

The finalized Affected Rows Policy uses a Unit Work-owned neutral shortfall
algebra: `MissingTarget | StaleWrite | OptimisticConflict`. `ExactCount` carries
one of these tags rather than an exception instance or class. A single Unit
Work operation, `enforce_affected_rows(step, actual_count)`, is the authoritative
interpreter for every non-insert execution result.

Unit Work owns the public Write Effect Error family produced by that operation:
Missing Target Error, Stale Write Error, Optimistic Lock Conflict Error, and
Cardinality Corruption Error. A shortfall selects the error named by the plan;
an excess over any exact count always produces Cardinality Corruption Error;
`AnyCount` accepts every nonnegative result. SQL lowering and database adapters
report affected counts but never reconstruct or reinterpret these semantics.
Every concrete error carries the same semantic diagnostic payload:
`entity: EntityIdentity`, `target: KeyTarget | MilestoneTarget`,
`expected: PositiveInt`, and `actual: NonNegativeInt`. It retains the target by
reference rather than copying it and carries no SQL, statement index, driver
exception, complete Planned Write, assignments, or observation.

Optimistic Locking continues to own the policy that chooses
`OptimisticConflict` for a gated write, but it does not own the execution
carrier. This direction respects the declared `m-opt-lock --> m-unit-work`
dependency and lets Auto Retry, which already depends on Unit Work, recognize
the canonical Optimistic Lock Conflict Error without a reverse edge. An
implementation may temporarily re-export moved error types from an older import
path, but their canonical ownership is Unit Work.
