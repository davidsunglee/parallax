# In-transaction read locks apply to object finds, not aggregations

Reads through a transaction take the shared row lock by default when they return managed objects, so a read-then-write is protected without the caller writing locking SQL. Aggregation and projection reads never take the lock: their results have no identifiable base row to lock and (per ADR 0002) return plain, unmanaged data, so there is nothing for a lock to protect — such a read proceeds unlocked rather than erroring. The dialect owns applying the lock.
