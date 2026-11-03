# In-transaction read locks apply to object finds, not aggregations

An object find inside a transaction takes the shared row lock wherever the level's own Entity resolves to the Locking strategy (ADR 0059), so a read-then-write is protected without the caller writing locking SQL. The lock is attributed to the target Entity rather than to the transaction: one find over a mixed model locks the levels whose Entities supply no gate and leaves the rest lock-free. Aggregation reads follow `m-agg`'s separate never-locking rule. The dialect owns applying the object-find lock.

*Superseded in part (2026-11, [ADR 0083](0083-concurrency-policy-is-a-model-facet-unit-of-work-reads-directly.md)):*
the read's owner, not the dialect, decides whether an object find takes the
shared row lock; the dialect decides only where and how it attaches. Object
finds alone lock, per target Entity, and aggregation reads never lock.
