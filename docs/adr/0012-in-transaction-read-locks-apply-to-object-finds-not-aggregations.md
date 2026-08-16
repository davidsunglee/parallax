# In-transaction read locks apply to object finds, not aggregations

An object find inside a transaction takes the shared row lock wherever the level's own Entity resolves to the Locking strategy (ADR 0059), so a read-then-write is protected without the caller writing locking SQL. The lock is attributed to the target Entity rather than to the transaction: one find over a mixed model locks the levels whose Entities supply no gate and leaves the rest lock-free. Aggregation reads follow `m-agg`'s separate never-locking rule. The dialect owns applying the object-find lock.
